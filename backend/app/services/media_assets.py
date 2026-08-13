from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from base64 import b64encode
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse
from uuid import uuid4

from app.config import Settings
from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import (
    MediaAssetResponse,
    MediaAssetType,
    MediaAssetUpdate,
    VideoPreviewDeriveResponse,
)
from app.repositories.media_assets import MediaAssetRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import as_iso, utc_now

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
VIDEO_EXTENSIONS = {".mp4", ".mov", ".webm", ".m4v"}


class MediaAssetService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: MediaAssetRepository,
        workspace_repository: WorkspaceRepository,
        settings: Settings,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.settings = settings

    def create_upload(
        self,
        workspace_id: str,
        *,
        asset_type: MediaAssetType,
        name: str,
        purpose: str,
        filename: str,
        media_type: str,
        content: bytes,
        source_type: str = "upload",
        external_url: str = "",
    ) -> MediaAssetResponse:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Media asset name cannot be blank")
        if not content:
            raise ValidationError("Media file cannot be empty")
        if len(content) > self.settings.max_upload_bytes:
            raise ValidationError("Media file exceeds the upload size limit")

        safe_filename = PurePosixPath(filename.replace("\\", "/")).name
        extension = Path(safe_filename).suffix.lower()
        self._validate_extension(asset_type, extension)
        clean_media_type = media_type.strip() or self._default_media_type(
            asset_type, extension
        )
        self._validate_media_type(asset_type, clean_media_type)

        asset_id = str(uuid4())
        stored_name = f"source{extension}"
        stored_key = f"{workspace_id}/media/{asset_id}/{stored_name}"
        final_path = self.settings.upload_directory / stored_key
        final_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = final_path.with_suffix(final_path.suffix + ".tmp")
        temporary_path.write_bytes(content)
        temporary_path.replace(final_path)

        metadata = self._initial_metadata(asset_type)
        derived = self._initial_derived(asset_type)
        try:
            with self.database.transaction() as connection:
                self.workspace_repository.get(connection, workspace_id)
                row = self.repository.create(
                    connection,
                    asset_id=asset_id,
                    workspace_id=workspace_id,
                    asset_type=asset_type.value,
                    name=clean_name,
                    purpose=purpose,
                    source_type=source_type,
                    original_filename=safe_filename,
                    stored_key=stored_key,
                    media_type=clean_media_type,
                    byte_size=len(content),
                    sha256=hashlib.sha256(content).hexdigest(),
                    metadata_json=json.dumps(metadata, ensure_ascii=False),
                    derived_json=json.dumps(derived, ensure_ascii=False),
                    user_notes="",
                    now=utc_now(),
                    external_url=external_url,
                )
        except Exception:
            final_path.unlink(missing_ok=True)
            raise
        return self._to_response(row)

    def create_external(
        self,
        workspace_id: str,
        *,
        asset_type: MediaAssetType,
        name: str,
        purpose: str,
        source_type: str,
        external_url: str,
        media_type: str,
        metadata: dict,
        derived: dict,
    ) -> MediaAssetResponse:
        clean_name = name.strip()
        if not clean_name:
            raise ValidationError("Media asset name cannot be blank")
        clean_url = external_url.strip()
        parsed = urlparse(clean_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValidationError("Media external URL must be an http(s) URL")
        asset_id = str(uuid4())
        filename = PurePosixPath(parsed.path).name or f"{asset_id}.{asset_type.value}"
        now = utc_now()
        with self.database.transaction() as connection:
            self.workspace_repository.get(connection, workspace_id)
            row = self.repository.create(
                connection,
                asset_id=asset_id,
                workspace_id=workspace_id,
                asset_type=asset_type.value,
                name=clean_name,
                purpose=purpose,
                source_type=source_type,
                original_filename=filename,
                stored_key="",
                media_type=media_type,
                byte_size=0,
                sha256=hashlib.sha256(clean_url.encode("utf-8")).hexdigest(),
                metadata_json=json.dumps(metadata, ensure_ascii=False),
                derived_json=json.dumps(derived, ensure_ascii=False),
                user_notes="",
                now=now,
                external_url=clean_url,
            )
        return self._to_response(row)

    def list(
        self, workspace_id: str, asset_type: MediaAssetType | None = None
    ) -> list[MediaAssetResponse]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(
                connection,
                workspace_id,
                asset_type.value if asset_type is not None else None,
            )
        return [self._to_response(row) for row in rows]

    def get(self, asset_id: str) -> MediaAssetResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, asset_id)
        return self._to_response(row)

    def get_file(self, asset_id: str) -> tuple[Path, str, str]:
        with self.database.read() as connection:
            row = self.repository.get(connection, asset_id)
        if row.get("external_url") and not row.get("stored_key"):
            raise ValidationError("External media assets do not have a local file")
        path = self.settings.upload_directory / row["stored_key"]
        if not path.is_file():
            raise ValidationError("Media file is missing from storage")
        return path, row["media_type"], row["original_filename"]

    def get_model_reference(self, asset_id: str) -> tuple[MediaAssetResponse, str]:
        with self.database.read() as connection:
            row = self.repository.get(connection, asset_id)
        asset = self._to_response(row)
        if row.get("external_url"):
            return asset, row["external_url"]
        if asset.type != MediaAssetType.IMAGE:
            raise ValidationError(
                "Uploaded video files cannot be sent to Qwen directly; use public frame URLs"
            )
        path = self.settings.upload_directory / row["stored_key"]
        if not path.is_file():
            raise ValidationError("Media file is missing from storage")
        encoded = b64encode(path.read_bytes()).decode("ascii")
        return asset, f"data:{row['media_type']};base64,{encoded}"

    def update(self, asset_id: str, payload: MediaAssetUpdate) -> MediaAssetResponse:
        if (
            payload.name is None
            and payload.purpose is None
            and payload.metadata is None
            and payload.derived is None
            and payload.user_notes is None
        ):
            raise ValidationError("At least one editable field is required")
        name = payload.name.strip() if payload.name is not None else None
        if name == "":
            raise ValidationError("Media asset name cannot be blank")
        metadata_json = (
            json.dumps(payload.metadata, ensure_ascii=False)
            if payload.metadata is not None
            else None
        )
        derived_json = (
            json.dumps(payload.derived, ensure_ascii=False)
            if payload.derived is not None
            else None
        )
        with self.database.transaction() as connection:
            row = self.repository.update(
                connection,
                asset_id=asset_id,
                name=name,
                purpose=payload.purpose,
                metadata_json=metadata_json,
                derived_json=derived_json,
                user_notes=payload.user_notes,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    def derive_video_preview(
        self,
        asset_id: str,
        *,
        frame_count: int | None = None,
        force: bool = False,
    ) -> VideoPreviewDeriveResponse:
        target_count = self._clean_frame_count(frame_count)
        with self.database.read() as connection:
            row = self.repository.get(connection, asset_id)
            existing = self._existing_preview_frames(connection, row, force)
            if existing is not None:
                return VideoPreviewDeriveResponse(
                    video_asset=self._to_response(row),
                    frames=[self._to_response(frame) for frame in existing],
                )

        if row["type"] != MediaAssetType.VIDEO.value:
            raise ValidationError("Video preview can only be derived from video assets")
        if row.get("external_url") and not row.get("stored_key"):
            raise ValidationError("External video assets do not have a local file")
        source_path = self.settings.upload_directory / row["stored_key"]
        if not source_path.is_file():
            raise ValidationError("Media file is missing from storage")

        extracted_paths = self._extract_video_frames(source_path, target_count)
        if not extracted_paths:
            raise ValidationError("No frames were extracted from the video")

        final_paths: list[tuple[Path, bytes, str]] = []
        extraction_id = str(uuid4())
        for extracted_path in extracted_paths:
            content = extracted_path.read_bytes()
            extracted_path.unlink(missing_ok=True)
            frame_asset_id = str(uuid4())
            stored_key = (
                f"{row['workspace_id']}/media/{asset_id}/frames/"
                f"{extraction_id}/{frame_asset_id}.jpg"
            )
            final_paths.append((self.settings.upload_directory / stored_key, content, stored_key))

        now = utc_now()
        created_frame_rows: list[dict] = []
        parent_row: dict
        try:
            with self.database.transaction() as connection:
                current = self.repository.get(connection, asset_id)
                if current["type"] != MediaAssetType.VIDEO.value:
                    raise ValidationError(
                        "Video preview can only be derived from video assets"
                    )
                for index, (final_path, content, stored_key) in enumerate(
                    final_paths, start=1
                ):
                    final_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary_path = final_path.with_suffix(".tmp")
                    temporary_path.write_bytes(content)
                    temporary_path.replace(final_path)
                    frame_row = self.repository.create(
                        connection,
                        asset_id=Path(stored_key).stem,
                        workspace_id=current["workspace_id"],
                        asset_type=MediaAssetType.IMAGE.value,
                        name=f"{current['name']} - 抽帧 {index:02d}",
                        purpose=f"从视频素材「{current['name']}」抽取的预览帧",
                        source_type="extracted_frame",
                        original_filename=f"{Path(current['original_filename']).stem}-frame-{index:02d}.jpg",
                        stored_key=stored_key,
                        media_type="image/jpeg",
                        byte_size=len(content),
                        sha256=hashlib.sha256(content).hexdigest(),
                        metadata_json=json.dumps(
                            {
                                "sourceVideoAssetId": asset_id,
                                "frameIndex": index,
                                "extractionId": extraction_id,
                                "method": "ffmpeg",
                            },
                            ensure_ascii=False,
                        ),
                        derived_json=json.dumps(
                            {
                                "extractedText": "",
                                "visualSummary": "",
                                "tags": [],
                                "sourceVideoAssetId": asset_id,
                                "frameIndex": index,
                            },
                            ensure_ascii=False,
                        ),
                        user_notes="",
                        now=now,
                    )
                    created_frame_rows.append(frame_row)

                current_derived = json.loads(current["derived_json"])
                current_derived["videoPreview"] = {
                    "sourceVideoAssetId": asset_id,
                    "extractionId": extraction_id,
                    "frameCount": len(created_frame_rows),
                    "requestedFrameCount": target_count,
                    "method": "ffmpeg",
                    "generatedAt": now,
                    "frames": [
                        {
                            "mediaAssetId": frame["id"],
                            "fileUrl": f"/api/media-assets/{frame['id']}/file",
                            "frameIndex": index,
                            "sha256": frame["sha256"],
                        }
                        for index, frame in enumerate(created_frame_rows, start=1)
                    ],
                }
                parent_row = self.repository.update(
                    connection,
                    asset_id=asset_id,
                    name=None,
                    purpose=None,
                    metadata_json=None,
                    derived_json=json.dumps(current_derived, ensure_ascii=False),
                    user_notes=None,
                    expected_updated_at=current["updated_at"],
                    now=now,
                )
        except Exception:
            for final_path, _content, _stored_key in final_paths:
                final_path.unlink(missing_ok=True)
            raise
        return VideoPreviewDeriveResponse(
            video_asset=self._to_response(parent_row),
            frames=[self._to_response(frame) for frame in created_frame_rows],
        )

    @staticmethod
    def _validate_extension(asset_type: MediaAssetType, extension: str) -> None:
        allowed = IMAGE_EXTENSIONS if asset_type == MediaAssetType.IMAGE else VIDEO_EXTENSIONS
        if extension not in allowed:
            raise ValidationError(
                "Only image files are supported"
                if asset_type == MediaAssetType.IMAGE
                else "Only video files are supported"
            )

    @staticmethod
    def _validate_media_type(asset_type: MediaAssetType, media_type: str) -> None:
        if asset_type == MediaAssetType.IMAGE and not media_type.startswith("image/"):
            raise ValidationError("Uploaded file media type must be image/*")
        if asset_type == MediaAssetType.VIDEO and not media_type.startswith("video/"):
            raise ValidationError("Uploaded file media type must be video/*")

    @staticmethod
    def _default_media_type(asset_type: MediaAssetType, extension: str) -> str:
        if asset_type == MediaAssetType.IMAGE:
            return {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".webp": "image/webp",
                ".gif": "image/gif",
            }.get(extension, "image/*")
        return {
            ".mp4": "video/mp4",
            ".mov": "video/quicktime",
            ".webm": "video/webm",
            ".m4v": "video/mp4",
        }.get(extension, "video/*")

    def _extract_video_frames(self, source_path: Path, frame_count: int) -> list[Path]:
        temporary_root = self.settings.upload_directory / "_tmp"
        temporary_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            prefix="video-preview-", dir=temporary_root
        ) as directory:
            output_pattern = Path(directory) / "frame_%03d.jpg"
            command = [
                self.settings.ffmpeg_path,
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(source_path),
                "-vf",
                "fps=1,scale=720:-2",
                "-frames:v",
                str(frame_count),
                str(output_pattern),
            ]
            try:
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except FileNotFoundError as error:
                raise ValidationError("ffmpeg is not available") from error
            except subprocess.TimeoutExpired as error:
                raise ValidationError("Video preview extraction timed out") from error
            if result.returncode != 0:
                detail = (result.stderr or result.stdout or "").strip()
                raise ValidationError(
                    f"Video preview extraction failed: {detail[:500]}"
                    if detail
                    else "Video preview extraction failed"
                )
            persisted: list[Path] = []
            for path in sorted(Path(directory).glob("frame_*.jpg"))[:frame_count]:
                copy_path = temporary_root / f"{uuid4()}.jpg"
                shutil.copyfile(path, copy_path)
                persisted.append(copy_path)
            return persisted

    def _existing_preview_frames(
        self, connection, row: dict, force: bool
    ) -> list[dict] | None:
        if force:
            return None
        if row["type"] != MediaAssetType.VIDEO.value:
            return None
        derived = json.loads(row["derived_json"])
        preview = derived.get("videoPreview")
        if not isinstance(preview, dict):
            return None
        frames = preview.get("frames")
        if not isinstance(frames, list) or not frames:
            return None
        rows: list[dict] = []
        try:
            for frame in frames:
                if not isinstance(frame, dict):
                    return None
                frame_id = frame.get("mediaAssetId")
                if not isinstance(frame_id, str) or not frame_id:
                    return None
                frame_row = self.repository.get(connection, frame_id)
                if (
                    frame_row["workspace_id"] != row["workspace_id"]
                    or frame_row["type"] != MediaAssetType.IMAGE.value
                    or frame_row["source_type"] != "extracted_frame"
                ):
                    return None
                rows.append(frame_row)
        except Exception:
            return None
        return rows

    def _clean_frame_count(self, frame_count: int | None) -> int:
        value = frame_count or self.settings.video_preview_frame_count
        return max(1, min(12, int(value)))

    @staticmethod
    def _initial_metadata(asset_type: MediaAssetType) -> dict:
        if asset_type == MediaAssetType.IMAGE:
            return {"width": None, "height": None}
        return {"durationSeconds": None, "width": None, "height": None, "fps": None}

    @staticmethod
    def _initial_derived(asset_type: MediaAssetType) -> dict:
        if asset_type == MediaAssetType.IMAGE:
            return {"extractedText": "", "visualSummary": "", "tags": []}
        return {
            "transcript": "",
            "sceneSummary": "",
            "visualSummary": "",
            "audioSummary": "",
            "tags": [],
            "metrics": {},
        }

    @staticmethod
    def _to_response(row: dict) -> MediaAssetResponse:
        return MediaAssetResponse.model_validate(
            {
                **row,
                "metadata": json.loads(row["metadata_json"]),
                "derived": json.loads(row["derived_json"]),
                "file_url": f"/api/media-assets/{row['id']}/file"
                if row.get("stored_key")
                else row.get("external_url", ""),
                "external_url": row.get("external_url", ""),
            }
        )
