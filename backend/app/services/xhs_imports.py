from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from app.errors import ValidationError
from app.models import (
    MediaAssetResponse,
    MediaAssetType,
    MediaAssetUpdate,
    SourceMaterialType,
    SourceMaterialUpdate,
    TextSourceMaterialCreate,
    TextSourceMaterialResponse,
    XhsOfflineImportPackageResponse,
    XhsOfflineImportResponse,
)
from app.services.input_assets import InputAssetService
from app.services.media_assets import MediaAssetService
from app.services.xhs_comment_refresh import preserve_unfetched_comments
from app.services.xhs_comment_roles import author_hash

SUPPORTED_XHS_SCHEMA = "xhs-profile-import/v1"
SUPPORTED_XHS_CREATOR_PROFILE_SCHEMA = "xhs-creator-profile/v1"
XHS_IMPORTABLE_TYPES = {
    SourceMaterialType.HISTORICAL_POSTS,
    SourceMaterialType.VIDEO_CREATOR_SAMPLES,
    SourceMaterialType.XHS_CREATOR_PROFILE,
}
XHS_PACKAGE_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


@dataclass(frozen=True)
class XhsPackageFile:
    relative_path: str
    filename: str
    media_type: str
    content: bytes


class XhsOfflineImportService:
    def __init__(
        self,
        input_asset_service: InputAssetService,
        media_asset_service: MediaAssetService | None = None,
    ) -> None:
        self.input_asset_service = input_asset_service
        self.media_asset_service = media_asset_service

    def import_file(
        self,
        workspace_id: str,
        *,
        asset_type: SourceMaterialType,
        filename: str,
        content: bytes,
        name: str = "",
    ) -> XhsOfflineImportResponse:
        if asset_type not in XHS_IMPORTABLE_TYPES:
            raise ValidationError(
                "XHS offline imports can only create historical_posts or "
                "video_creator_samples or xhs_creator_profile input assets"
            )
        if not content:
            raise ValidationError("XHS import file cannot be empty")
        if len(content) > self.input_asset_service.settings.max_upload_bytes:
            raise ValidationError("XHS import file exceeds the upload size limit")

        safe_filename = PurePosixPath(filename.replace("\\", "/")).name
        extension = Path(safe_filename).suffix.lower()
        if extension not in {".json", ".md", ".markdown", ".txt"}:
            raise ValidationError("XHS import file must be .json, .md, .markdown, or .txt")

        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValidationError("XHS import file must use UTF-8 encoding") from error

        if extension == ".json":
            raw = self._load_json_export(text)
            schema_version = str(
                raw.get("schemaVersion") or raw.get("schema_version") or ""
            )
            if schema_version == SUPPORTED_XHS_CREATOR_PROFILE_SCHEMA:
                creator_profile = self._parse_creator_profile_export(raw)
                parsed = self._creator_profile_to_legacy_import(creator_profile)
            else:
                parsed = self._parse_profile_import_export(raw)
                creator_profile = self._legacy_import_to_creator_profile(parsed)
            asset_content = (
                json.dumps(creator_profile, ensure_ascii=False, indent=2)
                if asset_type == SourceMaterialType.XHS_CREATOR_PROFILE
                else self._format_markdown(parsed)
            )
            parsed_note_count = len(parsed["notes"])
            source_url = parsed["sourceUrl"]
            warnings = parsed["warnings"]
            default_name = (
                self._default_creator_profile_asset_name(
                    creator_profile, safe_filename
                )
                if asset_type == SourceMaterialType.XHS_CREATOR_PROFILE
                else self._default_asset_name(parsed, safe_filename)
            )
        else:
            asset_content = text.strip()
            if not asset_content:
                raise ValidationError("XHS import text cannot be blank")
            parsed_note_count = self._count_markdown_notes(asset_content)
            source_url = self._extract_source_url_from_markdown(asset_content)
            warnings = []
            default_name = f"小红书主页导入 - {Path(safe_filename).stem or 'Markdown'}"

        material = self.input_asset_service.create_text(
            workspace_id,
            TextSourceMaterialCreate(
                type=asset_type,
                name=(name.strip() or default_name)[:160],
                content=asset_content,
            ),
        )
        return XhsOfflineImportResponse(
            input_asset=material,
            parsed_note_count=parsed_note_count,
            source_url=source_url,
            warnings=warnings,
        )

    def import_package(
        self,
        workspace_id: str,
        *,
        profile_filename: str,
        profile_content: bytes,
        files: list[XhsPackageFile],
        name: str = "",
        save_as_new: bool = False,
    ) -> XhsOfflineImportPackageResponse:
        if self.media_asset_service is None:
            raise ValidationError("XHS package import is not configured")
        if not profile_content:
            raise ValidationError("XHS package profile JSON cannot be empty")
        if len(profile_content) > self.input_asset_service.settings.max_upload_bytes:
            raise ValidationError("XHS package profile JSON exceeds the upload size limit")

        safe_profile_filename = PurePosixPath(profile_filename.replace("\\", "/")).name
        if Path(safe_profile_filename).suffix.lower() != ".json":
            raise ValidationError("XHS package profile file must be .json")
        try:
            text = profile_content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise ValidationError("XHS package profile JSON must use UTF-8 encoding") from error

        raw = self._load_json_export(text)
        schema_version = str(raw.get("schemaVersion") or raw.get("schema_version") or "")
        if schema_version == SUPPORTED_XHS_CREATOR_PROFILE_SCHEMA:
            creator_profile = self._parse_creator_profile_export(raw)
            parsed = self._creator_profile_to_legacy_import(creator_profile)
        else:
            parsed = self._parse_profile_import_export(raw)
            creator_profile = self._legacy_import_to_creator_profile(parsed)

        default_name = self._default_creator_profile_asset_name(
            creator_profile, safe_profile_filename
        )
        material_name = (name.strip() or default_name)[:160]
        existing_material = (
            None
            if save_as_new or name.strip()
            else self._find_existing_creator_profile(workspace_id, material_name)
        )
        if existing_material is not None:
            try:
                previous_profile = json.loads(existing_material.content)
                if not isinstance(previous_profile, dict):
                    raise ValueError("Invalid profile")
            except (ValueError, TypeError) as error:
                raise ValidationError("已有账号资料暂时无法读取，未覆盖原资料。") from error
            preserve_unfetched_comments(previous_profile, creator_profile)

        package_files = self._normalize_package_files(files)
        warnings = list(parsed["warnings"])
        media_assets: list[MediaAssetResponse] = []
        existing_media = self.media_asset_service.list(
            workspace_id, asset_type=MediaAssetType.IMAGE
        )
        existing_media_by_name = {asset.name: asset for asset in existing_media}
        existing_media_by_note = {
            asset.metadata["noteId"]: asset
            for asset in existing_media
            if asset.metadata.get("noteId")
        }

        for note in creator_profile["notes"]:
            relative_path = self._note_cover_relative_path(note, package_files)
            if not relative_path:
                warnings.append(f"笔记「{note['title']}」未找到本地封面图片。")
                continue
            package_file = package_files[relative_path]
            caption = self.cover_media_asset_caption(note)
            media_name = self.cover_media_asset_name(note["title"])
            metadata = {
                "source": "xhs_offline_import_package",
                "relativePath": relative_path,
                "noteId": note.get("noteId") or "",
                "noteUrl": note.get("noteUrl") or "",
                "title": note.get("title") or "",
                "caption": caption,
            }

            media_asset = existing_media_by_note.get(note.get("noteId"))
            if media_asset is None:
                named_asset = existing_media_by_name.get(media_name)
                if named_asset and named_asset.metadata.get("noteId") in {
                    None, "", note.get("noteId")
                }:
                    media_asset = named_asset
            if media_asset is None:
                media_asset = self.media_asset_service.create_upload(
                    workspace_id,
                    asset_type=MediaAssetType.IMAGE,
                    name=media_name,
                    purpose="小红书笔记封面",
                    filename=package_file.filename,
                    media_type=package_file.media_type,
                    content=package_file.content,
                    source_type="upload",
                )
                existing_media_by_name[media_name] = media_asset

            media_asset = self.media_asset_service.update(
                media_asset.id,
                MediaAssetUpdate(
                    metadata={**media_asset.metadata, **metadata},
                    user_notes=caption,
                    expected_updated_at=media_asset.updated_at,
                ),
            )
            media_assets.append(media_asset)
            existing_media_by_name[media_name] = media_asset
            existing_media_by_note[note.get("noteId")] = media_asset
            note["coverMediaAssetId"] = media_asset.id
            note["cover"] = {
                "relativePath": relative_path,
                "caption": caption,
            }

        asset_content = json.dumps(creator_profile, ensure_ascii=False, indent=2)
        if existing_material is None:
            material = self.input_asset_service.create_text(
                workspace_id,
                TextSourceMaterialCreate(
                    type=SourceMaterialType.XHS_CREATOR_PROFILE,
                    name=material_name,
                    content=asset_content,
                ),
            )
        else:
            material = self.input_asset_service.update(
                existing_material.id,
                SourceMaterialUpdate(
                    name=material_name,
                    content=asset_content,
                    expected_updated_at=existing_material.updated_at,
                ),
            )
        return XhsOfflineImportPackageResponse(
            input_asset=material,
            media_assets=media_assets,
            parsed_note_count=len(parsed["notes"]),
            source_url=parsed["sourceUrl"],
            warnings=warnings,
        )

    def _normalize_package_files(
        self, files: list[XhsPackageFile]
    ) -> dict[str, XhsPackageFile]:
        normalized: dict[str, XhsPackageFile] = {}
        for file in files:
            relative_path = self._safe_package_relative_path(file.relative_path)
            if not file.content:
                continue
            if len(file.content) > self.input_asset_service.settings.max_upload_bytes:
                raise ValidationError(
                    f"XHS package image exceeds the upload size limit: {relative_path}"
                )
            extension = Path(relative_path).suffix.lower()
            if extension not in XHS_PACKAGE_IMAGE_EXTENSIONS:
                continue
            normalized[relative_path] = XhsPackageFile(
                relative_path=relative_path,
                filename=PurePosixPath(file.filename.replace("\\", "/")).name
                or PurePosixPath(relative_path).name,
                media_type=file.media_type.strip()
                or self._default_image_media_type(extension),
                content=file.content,
            )
        return normalized

    @staticmethod
    def _safe_package_relative_path(relative_path: str) -> str:
        raw = str(relative_path or "").replace("\\", "/").strip()
        if not raw:
            raise ValidationError("XHS package file path cannot be blank")
        path = PurePosixPath(raw)
        if path.is_absolute() or any(part == ".." for part in path.parts):
            raise ValidationError("XHS package file paths must stay inside the package")
        return str(path)

    def _note_cover_relative_path(
        self, note: dict[str, Any], package_files: dict[str, XhsPackageFile]
    ) -> str:
        cover = note.get("cover") if isinstance(note.get("cover"), dict) else {}
        candidates = [
            cover.get("relativePath"),
            cover.get("relative_path"),
            note.get("coverRelativePath"),
            note.get("cover_relative_path"),
            note.get("coverPath"),
            note.get("cover_path"),
        ]
        note_id = self._clean(note.get("noteId") or note.get("note_id"))
        if note_id:
            candidates.extend(
                f"images/{note_id}/{index}{extension}"
                for index in range(0, 3)
                for extension in XHS_PACKAGE_IMAGE_EXTENSIONS
            )
            candidates.extend(
                f"images/{note_id}{extension}"
                for extension in XHS_PACKAGE_IMAGE_EXTENSIONS
            )
        for candidate in candidates:
            if not candidate:
                continue
            relative_path = self._safe_package_relative_path(str(candidate))
            if relative_path in package_files:
                return relative_path
        return ""

    def _find_existing_creator_profile(
        self, workspace_id: str, name: str
    ) -> TextSourceMaterialResponse | None:
        for material in self.input_asset_service.list(
            workspace_id, SourceMaterialType.XHS_CREATOR_PROFILE
        ):
            if getattr(material, "name", "") == name:
                return material
        return None

    def _load_json_export(self, text: str) -> dict[str, Any]:
        try:
            raw = json.loads(text)
        except json.JSONDecodeError as error:
            raise ValidationError("XHS import JSON is invalid") from error
        if not isinstance(raw, dict):
            raise ValidationError("XHS import JSON must be an object")
        return raw

    def _parse_profile_import_export(self, raw: dict[str, Any]) -> dict[str, Any]:
        schema_version = str(raw.get("schemaVersion") or raw.get("schema_version") or "")
        platform = str(raw.get("platform") or "")
        if schema_version and schema_version != SUPPORTED_XHS_SCHEMA:
            raise ValidationError(f"Unsupported XHS import schema: {schema_version}")
        if platform and platform != "xiaohongshu":
            raise ValidationError("XHS import platform must be xiaohongshu")

        source_url = self._clean(raw.get("sourceUrl") or raw.get("source_url"))
        imported_at = self._clean(raw.get("importedAt") or raw.get("imported_at"))
        import_method = self._clean(raw.get("importMethod") or raw.get("import_method"))
        creator = raw.get("creator") if isinstance(raw.get("creator"), dict) else {}
        profile_text = self._clean(
            creator.get("profileText")
            or creator.get("profile_text")
            or raw.get("profileText")
            or raw.get("profile_text")
        )
        notes = self._parse_notes(raw.get("notes"))
        warnings = [
            self._clean(item)
            for item in raw.get("warnings", [])
            if self._clean(item)
        ]
        if not source_url:
            warnings.append("导出文件缺少 sourceUrl。")
        if not notes:
            raise ValidationError("XHS import JSON does not contain any notes")
        return {
            "schemaVersion": schema_version or SUPPORTED_XHS_SCHEMA,
            "sourceUrl": source_url,
            "importedAt": imported_at,
            "importMethod": import_method or "browser_assisted_visible_page",
            "profileText": profile_text,
            "notes": notes,
            "warnings": warnings,
        }

    def _parse_creator_profile_export(self, raw: dict[str, Any]) -> dict[str, Any]:
        schema_version = str(raw.get("schemaVersion") or raw.get("schema_version") or "")
        if schema_version != SUPPORTED_XHS_CREATOR_PROFILE_SCHEMA:
            raise ValidationError(f"Unsupported XHS import schema: {schema_version}")
        source = raw.get("source") if isinstance(raw.get("source"), dict) else {}
        platform = str(source.get("platform") or raw.get("platform") or "")
        if platform and platform != "xiaohongshu":
            raise ValidationError("XHS import platform must be xiaohongshu")
        creator = raw.get("creator") if isinstance(raw.get("creator"), dict) else {}
        notes = raw.get("notes") if isinstance(raw.get("notes"), list) else []
        if not notes:
            raise ValidationError("XHS import JSON does not contain any notes")
        normalized_notes: list[dict[str, Any]] = []
        for index, raw_note in enumerate(notes, start=1):
            if not isinstance(raw_note, dict):
                continue
            title = self._clean(raw_note.get("title"), max_chars=160)
            desc = self._clean(
                raw_note.get("desc") or raw_note.get("description"),
                max_chars=12_000,
            )
            note_url = self._clean(
                raw_note.get("noteUrl") or raw_note.get("note_url") or raw_note.get("url")
            )
            note_id = self._clean(raw_note.get("noteId") or raw_note.get("note_id"))
            if not note_id:
                note_id = note_url.rstrip("/").split("/")[-1] if note_url else f"note-{index}"
            if not title:
                title = self._first_content_line(desc) or "未命名笔记"
            metrics = raw_note.get("metrics") if isinstance(raw_note.get("metrics"), dict) else {}
            comments = (
                raw_note.get("comments")
                if isinstance(raw_note.get("comments"), list)
                else []
            )
            cover = raw_note.get("cover") if isinstance(raw_note.get("cover"), dict) else {}
            normalized_notes.append(
                {
                    "noteId": note_id,
                    "type": self._clean(raw_note.get("type")) or "normal",
                    "authorHash": author_hash(
                        raw_note.get("authorHash") or raw_note.get("creator_hash")
                    ),
                    "title": title,
                    "desc": desc,
                    "noteUrl": note_url,
                    "publishedAt": raw_note.get("publishedAt") or raw_note.get("time"),
                    "tags": [
                        self._clean(tag)
                        for tag in raw_note.get("tags", [])
                        if self._clean(tag)
                    ]
                    if isinstance(raw_note.get("tags"), list)
                    else [],
                    "metrics": metrics,
                    "cover": {
                        "relativePath": self._clean(
                            cover.get("relativePath") or cover.get("relative_path")
                        ),
                        "caption": self._clean(
                            cover.get("caption"), max_chars=12_000
                        ),
                    }
                    if cover
                    else {},
                    "coverMediaAssetId": raw_note.get("coverMediaAssetId")
                    or raw_note.get("cover_media_asset_id"),
                    "comments": [
                        {
                            "commentId": self._clean(
                                comment.get("commentId") or comment.get("comment_id")
                            ),
                            "authorHash": author_hash(
                                comment.get("authorHash") or comment.get("creator_hash")
                            ),
                            "content": self._clean(
                                comment.get("content"), max_chars=12_000
                            ),
                            "likeCount": (
                                comment.get("likeCount")
                                if comment.get("likeCount") is not None
                                else comment.get("like_count")
                            ),
                            "subCommentCount": (
                                comment.get("subCommentCount")
                                if comment.get("subCommentCount") is not None
                                else comment.get("sub_comment_count")
                            ),
                            "createTime": comment.get("createTime")
                            or comment.get("create_time"),
                        }
                        for comment in comments
                        if isinstance(comment, dict)
                    ],
                    **({"commentsObservedAt": raw_note["commentsObservedAt"]}
                       if "commentsObservedAt" in raw_note else {}),
                }
            )
        if not normalized_notes:
            raise ValidationError("XHS import JSON does not contain any notes")
        return {
            "schemaVersion": SUPPORTED_XHS_CREATOR_PROFILE_SCHEMA,
            "source": {
                "platform": "xiaohongshu",
                "fixtureCode": self._clean(source.get("fixtureCode")),
                "importedAt": self._clean(
                    source.get("importedAt") or raw.get("importedAt")
                ),
                "crawler": self._clean(source.get("crawler")),
                "sourceUrl": self._clean(source.get("sourceUrl") or raw.get("sourceUrl")),
                "profileUrl": self._clean(source.get("profileUrl")),
                "captureNoteLimit": source.get("captureNoteLimit"),
            },
            "creator": {
                "displayName": self._clean(creator.get("displayName")),
                "followers": creator.get("followers"),
                "totalLikes": creator.get("totalLikes"),
                "likesAndCollections": creator.get("likesAndCollections"),
                "profileText": self._clean(
                    creator.get("profileText"), max_chars=100_000
                ),
            },
            "notes": normalized_notes,
            "warnings": [
                self._clean(item)
                for item in raw.get("warnings", [])
                if self._clean(item)
            ],
        }

    def _legacy_import_to_creator_profile(
        self, parsed: dict[str, Any]
    ) -> dict[str, Any]:
        return {
            "schemaVersion": SUPPORTED_XHS_CREATOR_PROFILE_SCHEMA,
            "source": {
                "platform": "xiaohongshu",
                "sourceUrl": parsed["sourceUrl"],
                "importedAt": parsed["importedAt"],
                "crawler": parsed["importMethod"],
            },
            "creator": {
                "displayName": self._infer_creator_display_name(parsed),
                "profileText": parsed["profileText"],
            },
            "notes": [
                {
                    "noteId": note["url"].rstrip("/").split("/")[-1]
                    if note["url"]
                    else f"note-{index}",
                    "type": "normal",
                    "title": note["title"],
                    "desc": note["detailText"] or note["cardText"],
                    "noteUrl": note["url"],
                    "tags": [],
                    "metrics": {"engagementText": note["engagementText"]},
                    "coverUrl": note["coverUrl"],
                    "coverMediaAssetId": None,
                    "comments": [],
                }
                for index, note in enumerate(parsed["notes"], start=1)
            ],
            "warnings": parsed["warnings"],
        }

    def _creator_profile_to_legacy_import(
        self, creator_profile: dict[str, Any]
    ) -> dict[str, Any]:
        source = creator_profile.get("source", {})
        creator = creator_profile.get("creator", {})
        notes = creator_profile.get("notes", [])
        return {
            "schemaVersion": SUPPORTED_XHS_SCHEMA,
            "sourceUrl": self._clean(source.get("sourceUrl")),
            "importedAt": self._clean(source.get("importedAt")),
            "importMethod": self._clean(source.get("crawler")) or "xhs_creator_profile",
            "profileText": self._clean(creator.get("profileText"), max_chars=100_000),
            "notes": [
                {
                    "title": self._clean(note.get("title"), max_chars=160),
                    "url": self._clean(note.get("noteUrl") or note.get("url")),
                    "detailText": self._clean(note.get("desc"), max_chars=12_000),
                    "cardText": "",
                    "coverUrl": self._clean(note.get("coverUrl")),
                    "engagementText": self._format_metrics(note.get("metrics")),
                }
                for note in notes
                if isinstance(note, dict)
            ],
            "warnings": [
                self._clean(item)
                for item in creator_profile.get("warnings", [])
                if self._clean(item)
            ],
        }

    def _parse_notes(self, raw_notes: Any) -> list[dict[str, str]]:
        if not isinstance(raw_notes, list):
            return []
        notes: list[dict[str, str]] = []
        seen_urls: set[str] = set()
        for raw_note in raw_notes:
            if not isinstance(raw_note, dict):
                continue
            url = self._clean(raw_note.get("url") or raw_note.get("note_url"))
            title = self._clean(raw_note.get("title"), max_chars=160)
            detail_text = self._clean(
                raw_note.get("detailText") or raw_note.get("detail_text"),
                max_chars=12_000,
            )
            card_text = self._clean(
                raw_note.get("cardText") or raw_note.get("card_text"),
                max_chars=3_000,
            )
            cover_url = self._clean(raw_note.get("coverUrl") or raw_note.get("cover_url"))
            engagement_text = self._clean(
                raw_note.get("engagementText") or raw_note.get("engagement_text"),
                max_chars=500,
            )
            if not title:
                title = self._first_content_line(detail_text or card_text)
            if not title and not url:
                continue
            dedupe_key = url or title
            if dedupe_key in seen_urls:
                continue
            seen_urls.add(dedupe_key)
            notes.append(
                {
                    "title": title or "未命名笔记",
                    "url": url,
                    "detailText": detail_text,
                    "cardText": card_text,
                    "coverUrl": cover_url,
                    "engagementText": engagement_text,
                }
            )
        return notes

    def _format_markdown(self, parsed: dict[str, Any]) -> str:
        lines = [
            "# 小红书主页导入",
            "",
            "- 平台：xiaohongshu",
            f"- 来源：{parsed['sourceUrl'] or '未知'}",
            f"- 导入时间：{parsed['importedAt'] or '未知'}",
            f"- 导入方式：{parsed['importMethod']}",
            "",
        ]
        if parsed["profileText"]:
            lines.extend(["## 主页可见信息", "", parsed["profileText"], ""])
        lines.extend(["## 笔记列表", ""])
        for index, note in enumerate(parsed["notes"], start=1):
            content = note["detailText"] or note["cardText"]
            lines.extend(
                [
                    f"### {index}. {note['title']}",
                    "",
                    f"- 链接：{note['url'] or '未知'}",
                ]
            )
            if note["coverUrl"]:
                lines.append(f"- 封面：{note['coverUrl']}")
            if note["engagementText"]:
                lines.append(f"- 可见互动信息：{note['engagementText']}")
            lines.extend(["", content or "（未抓取到正文，仅保留链接和标题。）", ""])
        if parsed["warnings"]:
            lines.extend(["## 导入提示", ""])
            lines.extend(f"- {warning}" for warning in parsed["warnings"])
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def _default_asset_name(parsed: dict[str, Any], filename: str) -> str:
        source_tail = parsed["sourceUrl"].rstrip("/").split("/")[-1] if parsed["sourceUrl"] else ""
        label = source_tail or Path(filename).stem or "导入文件"
        return f"小红书主页导入 - {label}"

    @staticmethod
    def _default_creator_profile_asset_name(
        creator_profile: dict[str, Any], filename: str
    ) -> str:
        creator = (
            creator_profile.get("creator")
            if isinstance(creator_profile.get("creator"), dict)
            else {}
        )
        display_name = XhsOfflineImportService._clean(
            creator.get("displayName"), max_chars=80
        )
        if display_name:
            return f"XHS {display_name} 创作者主页"
        return f"小红书主页导入 - {Path(filename).stem or '导入文件'}"

    @staticmethod
    def _infer_creator_display_name(parsed: dict[str, Any]) -> str:
        profile_text = str(parsed.get("profileText") or "")
        first_token = profile_text.split()[0] if profile_text.split() else ""
        if first_token:
            return first_token.removeprefix("账号：").removeprefix("账号:")
        source_url = str(parsed.get("sourceUrl") or "").rstrip("/")
        return source_url.split("/")[-1] if source_url else ""

    @staticmethod
    def _format_metrics(value: Any) -> str:
        if not isinstance(value, dict):
            return ""
        parts: list[str] = []
        labels = {
            "liked": "赞",
            "collected": "收藏",
            "comments": "评论",
            "shares": "分享",
            "engagementText": "可见互动",
        }
        for key, label in labels.items():
            metric = value.get(key)
            if metric not in (None, ""):
                parts.append(f"{label} {metric}")
        return " / ".join(parts)

    @staticmethod
    def cover_media_asset_name(title: Any) -> str:
        cleaned = re.sub(
            r"[\\/:*?\"<>|\n\r\t]+",
            "_",
            XhsOfflineImportService._clean(title, max_chars=120),
        ).strip(" _.")
        return f"{cleaned or '未命名笔记'}_封面"

    @staticmethod
    def cover_media_asset_caption(note: dict[str, Any]) -> str:
        cover = note.get("cover") if isinstance(note.get("cover"), dict) else {}
        caption = XhsOfflineImportService._clean(
            cover.get("caption") or note.get("desc") or note.get("title"),
            max_chars=12_000,
        )
        return caption or "小红书笔记封面"

    @staticmethod
    def _default_image_media_type(extension: str) -> str:
        return {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".webp": "image/webp",
        }.get(extension.lower(), "image/jpeg")

    @staticmethod
    def _count_markdown_notes(text: str) -> int:
        return len(re.findall(r"(?m)^###\s+\d+\.", text))

    @staticmethod
    def _extract_source_url_from_markdown(text: str) -> str:
        match = re.search(r"(?m)^-\s*来源[:：]\s*(.+)$", text)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _first_content_line(text: str) -> str:
        for line in text.splitlines():
            cleaned = XhsOfflineImportService._clean(line, max_chars=160)
            if cleaned:
                return cleaned
        return ""

    @staticmethod
    def _clean(value: Any, *, max_chars: int | None = None) -> str:
        text = " ".join(str(value or "").replace("\u200b", "").split())
        if max_chars is not None and len(text) > max_chars:
            return text[: max_chars - 1].rstrip() + "…"
        return text
