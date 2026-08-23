from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any

import httpx

from app.config import Settings
from app.errors import ValidationError
from app.models import MediaAssetType, MediaAssetUpdate
from app.services.media_assets import MediaAssetService


class QwenMediaService:
    """Small product-facing wrapper for Qwen/DashScope media capabilities."""

    IMAGE_UNDERSTAND_SKILL = "media.understand_image"
    VIDEO_UNDERSTAND_SKILL = "media.understand_video"
    IMAGE_GENERATE_SKILL = "media.generate_image"
    VIDEO_GENERATE_SKILL = "media.generate_video"

    def __init__(
        self,
        settings: Settings,
        media_asset_service: MediaAssetService,
    ) -> None:
        self.settings = settings
        self.media_asset_service = media_asset_service

    def invoke(
        self,
        *,
        workspace_id: str,
        skill_id: str,
        input_payload: dict[str, Any],
        mode: str,
    ) -> dict[str, Any]:
        if mode != "live":
            return self._demo_output(skill_id, input_payload)
        if skill_id == self.IMAGE_UNDERSTAND_SKILL:
            return self.understand_image(workspace_id, input_payload)
        if skill_id == self.VIDEO_UNDERSTAND_SKILL:
            return self.understand_video(workspace_id, input_payload)
        if skill_id == self.IMAGE_GENERATE_SKILL:
            return self.generate_image(workspace_id, input_payload)
        if skill_id == self.VIDEO_GENERATE_SKILL:
            return self.generate_video(workspace_id, input_payload)
        raise ValidationError(f"Unsupported Qwen media skill: {skill_id}")

    def understand_image(
        self, workspace_id: str, input_payload: dict[str, Any]
    ) -> dict[str, Any]:
        prompt = self._required_text(input_payload, "prompt")
        image_url = self._optional_text(input_payload, "imageUrl")
        media_asset_id = self._optional_text(input_payload, "mediaAssetId")
        source_asset: dict[str, Any] | None = None
        if not image_url and media_asset_id:
            asset, image_url = self.media_asset_service.get_model_reference(media_asset_id)
            if asset.workspace_id != workspace_id:
                raise ValidationError("Media asset does not belong to this workspace")
            if asset.type != MediaAssetType.IMAGE:
                raise ValidationError("mediaAssetId must reference an image media asset")
            source_asset = {"mediaAssetId": asset.id, "name": asset.name}
        if not image_url:
            raise ValidationError("imageUrl or mediaAssetId is required")
        text, metadata = self._chat_with_media(
            [
                {"type": "image_url", "image_url": {"url": image_url}},
                {"type": "text", "text": self._structured_image_prompt(prompt)},
            ]
        )
        understanding = self._parse_image_understanding(text)
        return {
            "kind": "image_understanding",
            "imageUnderstanding": understanding,
            "text": understanding["visualSummary"],
            "sourceAsset": source_asset,
            "modelMetadata": metadata,
        }

    def understand_video(
        self, workspace_id: str, input_payload: dict[str, Any]
    ) -> dict[str, Any]:
        prompt = self._required_text(input_payload, "prompt")
        frame_urls = input_payload.get("videoFrameUrls") or input_payload.get(
            "video_frame_urls"
        )
        video_url = self._optional_text(input_payload, "videoUrl")
        media_asset_id = self._optional_text(input_payload, "mediaAssetId")
        source_asset: dict[str, Any] | None = None
        extracted_frame_ids: list[str] = []
        derived_video_asset: dict[str, Any] | None = None
        derived_frame_assets: list[dict[str, Any]] = []
        if isinstance(frame_urls, str):
            frame_urls = [frame_urls]
        if frame_urls is None and video_url:
            frame_urls = [video_url]
        content: list[dict[str, Any]]
        if frame_urls is None and media_asset_id:
            asset = self.media_asset_service.get(media_asset_id)
            if asset.workspace_id != workspace_id:
                raise ValidationError("Media asset does not belong to this workspace")
            if asset.type != MediaAssetType.VIDEO:
                raise ValidationError("mediaAssetId must reference a video asset")
            preview = self.media_asset_service.derive_video_preview(media_asset_id)
            derived_video_asset = preview.video_asset.model_dump(
                mode="json", by_alias=True
            )
            derived_frame_assets = [
                frame.model_dump(mode="json", by_alias=True) for frame in preview.frames
            ]
            frame_references: list[str] = []
            for frame in preview.frames:
                frame_asset, frame_reference = self.media_asset_service.get_model_reference(
                    frame.id
                )
                if frame_asset.workspace_id != workspace_id:
                    raise ValidationError(
                        "Media asset does not belong to this workspace"
                    )
                frame_references.append(frame_reference)
                extracted_frame_ids.append(frame.id)
            content = [
                {"type": "image_url", "image_url": {"url": frame_reference}}
                for frame_reference in frame_references
            ]
            source_asset = {
                "mediaAssetId": asset.id,
                "name": asset.name,
                "derivedFrameAssetIds": extracted_frame_ids,
            }
        else:
            if (
                not isinstance(frame_urls, list)
                or not frame_urls
                or not all(isinstance(item, str) and item.strip() for item in frame_urls)
            ):
                raise ValidationError("videoFrameUrls, videoUrl, or mediaAssetId is required")
            content = [{"type": "video", "video": [item.strip() for item in frame_urls]}]
        if (
            not content
            or not all(isinstance(item, dict) for item in content)
        ):
            raise ValidationError("No video references are available")
        content.append({"type": "text", "text": self._structured_video_prompt(prompt)})
        text, metadata = self._chat_with_media(
            content
        )
        understanding = self._parse_video_understanding(text)
        return {
            "kind": "video_understanding",
            "videoUnderstanding": understanding,
            "text": understanding["sceneSummary"],
            "frameCount": len(extracted_frame_ids)
            if extracted_frame_ids
            else len(frame_urls or []),
            "sourceAsset": source_asset,
            "videoAsset": derived_video_asset,
            "derivedFrameAssets": derived_frame_assets,
            "modelMetadata": metadata,
        }

    def generate_image(
        self, workspace_id: str, input_payload: dict[str, Any]
    ) -> dict[str, Any]:
        prompt = self._required_text(input_payload, "prompt")
        name = self._optional_text(input_payload, "name") or "Qwen 生成图片"
        purpose = self._optional_text(input_payload, "purpose") or "AI image generation"
        parameters = {
            "size": self._optional_text(input_payload, "size") or "1024*1024",
            "n": int(input_payload.get("n") or 1),
        }
        task = self._run_dashscope_task(
            endpoint="/services/aigc/text2image/image-synthesis",
            model=self.settings.qwen_image_model,
            input_body={"prompt": prompt},
            parameters=parameters,
        )
        url = self._extract_generated_url(task, expected="image")
        content, media_type, filename = self._download_generated_media(
            url, fallback_filename="qwen-image.png", fallback_media_type="image/png"
        )
        asset = self.media_asset_service.create_upload(
            workspace_id,
            asset_type=MediaAssetType.IMAGE,
            name=name,
            purpose=purpose,
            filename=filename,
            media_type=media_type,
            content=content,
            source_type="generated",
            external_url=url,
        )
        asset = self.media_asset_service.update(
            asset.id,
            payload=self._media_metadata_update(
                asset.updated_at,
                metadata={
                    "prompt": prompt,
                    "provider": "qwen",
                    "model": self.settings.qwen_image_model,
                    "taskId": self._task_id(task),
                    "parameters": parameters,
                },
                derived={"visualSummary": "", "extractedText": "", "tags": []},
            ),
        )
        return {
            "kind": "image_generation",
            "mediaAsset": asset.model_dump(mode="json", by_alias=True),
            "task": task,
        }

    def generate_video(
        self, workspace_id: str, input_payload: dict[str, Any]
    ) -> dict[str, Any]:
        prompt = self._required_text(input_payload, "prompt")
        name = self._optional_text(input_payload, "name") or "Qwen 生成视频"
        purpose = self._optional_text(input_payload, "purpose") or "AI video generation"
        resolution, ratio = self._video_resolution_and_ratio(input_payload)
        parameters = {
            "resolution": resolution,
            "ratio": ratio,
            "duration": int(input_payload.get("duration") or 5),
            "prompt_extend": bool(input_payload.get("promptExtend", False)),
            "watermark": bool(input_payload.get("watermark", False)),
        }
        task = self._run_dashscope_task(
            endpoint="/services/aigc/video-generation/video-synthesis",
            model=self.settings.qwen_video_model,
            input_body={"prompt": prompt},
            parameters=parameters,
        )
        url = self._extract_generated_url(task, expected="video")
        content, media_type, filename = self._download_generated_media(
            url, fallback_filename="qwen-video.mp4", fallback_media_type="video/mp4"
        )
        asset = self.media_asset_service.create_upload(
            workspace_id,
            asset_type=MediaAssetType.VIDEO,
            name=name,
            purpose=purpose,
            filename=filename,
            media_type=media_type,
            content=content,
            source_type="generated",
            external_url=url,
        )
        asset = self.media_asset_service.update(
            asset.id,
            payload=self._media_metadata_update(
                asset.updated_at,
                metadata={
                    "prompt": prompt,
                    "provider": "qwen",
                    "model": self.settings.qwen_video_model,
                    "taskId": self._task_id(task),
                    "parameters": parameters,
                },
                derived={
                    "transcript": "",
                    "sceneSummary": "",
                    "visualSummary": "",
                    "audioSummary": "",
                    "tags": [],
                    "metrics": {},
                },
            ),
        )
        return {
            "kind": "video_generation",
            "mediaAsset": asset.model_dump(mode="json", by_alias=True),
            "task": task,
        }

    def _chat_with_media(self, content: list[dict[str, Any]]) -> tuple[str, dict[str, Any]]:
        self._require_key()
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{self.settings.qwen_base_url.rstrip('/')}/chat/completions",
                headers={
                    "content-type": "application/json",
                    "authorization": f"Bearer {self.settings.qwen_api_key}",
                },
                json={
                    "model": self.settings.qwen_vision_model,
                    "response_format": {"type": "json_object"},
                    "messages": [{"role": "user", "content": content}],
                },
            )
        body = self._json_or_error(response)
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            raise ValidationError("Qwen vision response missing choices")
        message = choices[0].get("message") if isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise ValidationError("Qwen vision response missing message")
        text = message.get("content")
        if not isinstance(text, str):
            raise ValidationError("Qwen vision response content must be text")
        return text, {
            "provider": "qwen",
            "model": body.get("model", self.settings.qwen_vision_model),
            "usage": body.get("usage", {}),
        }

    @staticmethod
    def _structured_image_prompt(user_prompt: str) -> str:
        return (
            f"{user_prompt}\n\n"
            "只输出 JSON，不要 markdown。schema:\n"
            '{"imageUnderstanding":{"visualSummary":"","extractedText":"",'
            '"styleTags":[],"creatorSignals":[],"risks":[],"uncertainties":[]}}'
        )

    @staticmethod
    def _structured_video_prompt(user_prompt: str) -> str:
        return (
            f"{user_prompt}\n\n"
            "只输出 JSON，不要 markdown。schema:\n"
            '{"videoUnderstanding":{"sceneSummary":"","transcript":"",'
            '"visualSummary":"","audioSummary":"","qualitySignals":[],'
            '"creatorSignals":[],"incentiveFitSignals":[],"risks":[],'
            '"uncertainties":[]}}'
        )

    @classmethod
    def _parse_image_understanding(cls, text: str) -> dict[str, Any]:
        parsed = cls._parse_json_object(text)
        data = parsed.get("imageUnderstanding") if parsed else None
        if not isinstance(data, dict):
            data = {"visualSummary": text.strip()}
        return {
            "visualSummary": str(data.get("visualSummary") or ""),
            "extractedText": str(data.get("extractedText") or ""),
            "styleTags": cls._string_list(data.get("styleTags")),
            "creatorSignals": cls._string_list(data.get("creatorSignals")),
            "risks": cls._string_list(data.get("risks")),
            "uncertainties": cls._string_list(data.get("uncertainties")),
        }

    @classmethod
    def _parse_video_understanding(cls, text: str) -> dict[str, Any]:
        parsed = cls._parse_json_object(text)
        data = parsed.get("videoUnderstanding") if parsed else None
        if not isinstance(data, dict):
            data = {"sceneSummary": text.strip()}
        return {
            "sceneSummary": str(data.get("sceneSummary") or ""),
            "transcript": str(data.get("transcript") or ""),
            "visualSummary": str(data.get("visualSummary") or ""),
            "audioSummary": str(data.get("audioSummary") or ""),
            "qualitySignals": cls._string_list(data.get("qualitySignals")),
            "creatorSignals": cls._string_list(data.get("creatorSignals")),
            "incentiveFitSignals": cls._string_list(data.get("incentiveFitSignals")),
            "risks": cls._string_list(data.get("risks")),
            "uncertainties": cls._string_list(data.get("uncertainties")),
        }

    @staticmethod
    def _parse_json_object(text: str) -> dict[str, Any]:
        candidates = [text.strip()]
        fenced = re.search(
            r"```(?:json|JSON)?\s*(?P<body>.*?)\s*```",
            text.strip(),
            flags=re.DOTALL,
        )
        if fenced:
            candidates.append(fenced.group("body").strip())
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            candidates.append(text[start : end + 1])
        for candidate in candidates:
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
        return {}

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item) for item in value if str(item).strip()]

    def _download_generated_media(
        self,
        url: str,
        *,
        fallback_filename: str,
        fallback_media_type: str,
    ) -> tuple[bytes, str, str]:
        with httpx.Client(timeout=120) as client:
            response = client.get(url, headers={})
        if response.status_code >= 400:
            raise ValidationError(f"Generated media download failed ({response.status_code})")
        content = response.content
        if not content:
            raise ValidationError("Generated media download was empty")
        filename = url.split("?", 1)[0].rstrip("/").rsplit("/", 1)[-1] or fallback_filename
        if "." not in filename:
            filename = fallback_filename
        media_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
        return content, media_type or fallback_media_type, filename

    @staticmethod
    def _media_metadata_update(
        expected_updated_at: datetime,
        *,
        metadata: dict[str, Any],
        derived: dict[str, Any],
    ) -> MediaAssetUpdate:
        return MediaAssetUpdate(
            metadata=metadata,
            derived=derived,
            expected_updated_at=expected_updated_at,
        )

    def _run_dashscope_task(
        self,
        *,
        endpoint: str,
        model: str,
        input_body: dict[str, Any],
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        self._require_key()
        with httpx.Client(timeout=120) as client:
            response = client.post(
                f"{self.settings.qwen_dashscope_base_url.rstrip('/')}{endpoint}",
                headers={
                    "content-type": "application/json",
                    "authorization": f"Bearer {self.settings.qwen_api_key}",
                    "x-dashscope-async": "enable",
                },
                json={
                    "model": model,
                    "input": input_body,
                    "parameters": parameters,
                },
            )
            body = self._json_or_error(response)
            task_id = self._task_id(body)
            if not task_id or self._task_status(body) in {"SUCCEEDED", "FAILED", "CANCELED"}:
                return body
            for _attempt in range(self.settings.qwen_task_poll_attempts):
                poll_response = client.get(
                    f"{self.settings.qwen_dashscope_base_url.rstrip('/')}/tasks/{task_id}",
                    headers={"authorization": f"Bearer {self.settings.qwen_api_key}"},
                )
                poll_body = self._json_or_error(poll_response)
                status = self._task_status(poll_body)
                if status == "SUCCEEDED":
                    return poll_body
                if status in {"FAILED", "CANCELED"}:
                    raise ValidationError(f"Qwen media task {status.lower()}")
                time.sleep(self.settings.qwen_task_poll_interval_seconds)
        raise ValidationError("Qwen media task did not complete before timeout")

    @staticmethod
    def _extract_generated_url(body: dict[str, Any], *, expected: str) -> str:
        output = body.get("output", body)
        if not isinstance(output, dict):
            raise ValidationError("Qwen media response missing output")
        candidates = []
        for key in ["results", "images", "videos"]:
            value = output.get(key)
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, dict))
        candidates.append(output)
        url_keys = (
            ["url", "image_url", "imageUrl"]
            if expected == "image"
            else ["video_url", "videoUrl", "url"]
        )
        for item in candidates:
            for key in url_keys:
                value = item.get(key)
                if isinstance(value, str) and value.startswith(("http://", "https://")):
                    return value
        raise ValidationError("Qwen media response did not include a generated URL")

    @staticmethod
    def _task_id(body: dict[str, Any]) -> str:
        output = body.get("output", body)
        if isinstance(output, dict):
            value = output.get("task_id") or output.get("taskId")
            return value if isinstance(value, str) else ""
        return ""

    @staticmethod
    def _task_status(body: dict[str, Any]) -> str:
        output = body.get("output", body)
        if isinstance(output, dict):
            value = output.get("task_status") or output.get("taskStatus")
            return value if isinstance(value, str) else ""
        return ""

    @staticmethod
    def _json_or_error(response: httpx.Response) -> dict[str, Any]:
        try:
            body = response.json()
        except ValueError as error:
            raise ValidationError("Qwen media response was not JSON") from error
        if response.status_code >= 400:
            message = body.get("message") or body.get("error") or f"HTTP {response.status_code}"
            raise ValidationError(f"Qwen media call failed: {message}")
        if not isinstance(body, dict):
            raise ValidationError("Qwen media response JSON must be an object")
        return body

    @staticmethod
    def _video_resolution_and_ratio(input_payload: dict[str, Any]) -> tuple[str, str]:
        resolution = (
            QwenMediaService._optional_text(input_payload, "resolution") or "720P"
        )
        ratio = QwenMediaService._optional_text(input_payload, "ratio")
        size = QwenMediaService._optional_text(input_payload, "size")
        if ratio:
            return resolution, ratio
        size_to_ratio = {
            "1280*720": ("720P", "16:9"),
            "720*1280": ("720P", "9:16"),
            "960*960": ("720P", "1:1"),
            "1920*1080": ("1080P", "16:9"),
            "1080*1920": ("1080P", "9:16"),
            "1440*1440": ("1080P", "1:1"),
        }
        if size in size_to_ratio:
            return size_to_ratio[size]
        return resolution, "16:9"

    def _require_key(self) -> None:
        if not self.settings.qwen_api_key:
            raise ValidationError(
                "QWEN_API_KEY or DASHSCOPE_API_KEY is required for Qwen media calls"
            )

    @staticmethod
    def _required_text(input_payload: dict[str, Any], key: str) -> str:
        value = QwenMediaService._optional_text(input_payload, key)
        if not value:
            raise ValidationError(f"{key} is required")
        return value

    @staticmethod
    def _optional_text(input_payload: dict[str, Any], key: str) -> str:
        value = input_payload.get(key) or input_payload.get(_to_snake(key))
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _demo_output(skill_id: str, input_payload: dict[str, Any]) -> dict[str, Any]:
        prompt = str(input_payload.get("prompt", ""))
        if skill_id == QwenMediaService.IMAGE_UNDERSTAND_SKILL:
            return {
                "kind": "image_understanding",
                "mode": "demo",
                "imageUnderstanding": {
                    "visualSummary": "Demo 图片理解结果：画面清爽可信，适合作为创作者视觉参考。",
                    "extractedText": "",
                    "styleTags": ["demo"],
                    "creatorSignals": ["视觉定位明确"],
                    "risks": [],
                    "uncertainties": ["未调用真实模型"],
                },
                "text": "Demo 图片理解结果：画面清爽可信，适合作为创作者视觉参考。",
                "prompt": prompt,
            }
        if skill_id == QwenMediaService.VIDEO_UNDERSTAND_SKILL:
            return {
                "kind": "video_understanding",
                "mode": "demo",
                "videoUnderstanding": {
                    "sceneSummary": "Demo 视频理解结果：短剧开场冲突明确。",
                    "transcript": "",
                    "visualSummary": "竖屏节奏较快。",
                    "audioSummary": "",
                    "qualitySignals": ["叙事驱动"],
                    "creatorSignals": ["适合系列化"],
                    "incentiveFitSignals": ["可被激励计划放大"],
                    "risks": [],
                    "uncertainties": ["未调用真实模型"],
                },
                "text": "Demo 视频理解结果：短剧开场冲突明确。",
                "prompt": prompt,
            }
        return {
            "kind": skill_id,
            "mode": "demo",
            "prompt": prompt,
            "note": "Demo mode does not call Qwen media APIs.",
        }


def _to_snake(value: str) -> str:
    chars: list[str] = []
    for char in value:
        if char.isupper():
            chars.append("_")
            chars.append(char.lower())
        else:
            chars.append(char)
    return "".join(chars).lstrip("_")
