from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Any

from app.errors import ValidationError
from app.models import (
    SourceMaterialType,
    TextSourceMaterialCreate,
    XhsOfflineImportResponse,
)
from app.services.input_assets import InputAssetService

SUPPORTED_XHS_SCHEMA = "xhs-profile-import/v1"
SUPPORTED_XHS_CREATOR_PROFILE_SCHEMA = "xhs-creator-profile/v1"
XHS_IMPORTABLE_TYPES = {
    SourceMaterialType.HISTORICAL_POSTS,
    SourceMaterialType.VIDEO_CREATOR_SAMPLES,
    SourceMaterialType.XHS_CREATOR_PROFILE,
}


class XhsOfflineImportService:
    def __init__(self, input_asset_service: InputAssetService) -> None:
        self.input_asset_service = input_asset_service

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
            default_name = self._default_asset_name(parsed, safe_filename)
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
            normalized_notes.append(
                {
                    "noteId": note_id,
                    "type": self._clean(raw_note.get("type")) or "normal",
                    "title": title,
                    "desc": desc,
                    "noteUrl": note_url,
                    "tags": [
                        self._clean(tag)
                        for tag in raw_note.get("tags", [])
                        if self._clean(tag)
                    ]
                    if isinstance(raw_note.get("tags"), list)
                    else [],
                    "metrics": metrics,
                    "coverMediaAssetId": raw_note.get("coverMediaAssetId")
                    or raw_note.get("cover_media_asset_id"),
                    "comments": [
                        {
                            "commentId": self._clean(
                                comment.get("commentId") or comment.get("comment_id")
                            ),
                            "content": self._clean(
                                comment.get("content"), max_chars=12_000
                            ),
                            "likeCount": comment.get("likeCount")
                            or comment.get("like_count"),
                            "subCommentCount": comment.get("subCommentCount")
                            or comment.get("sub_comment_count"),
                            "createTime": comment.get("createTime")
                            or comment.get("create_time"),
                        }
                        for comment in comments
                        if isinstance(comment, dict)
                    ],
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
            },
            "creator": {
                "displayName": self._clean(creator.get("displayName")),
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
