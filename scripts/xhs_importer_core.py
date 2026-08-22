"""Core helpers for the local Xiaohongshu profile importer.

This module intentionally contains no browser automation. It normalizes visible
page snapshots into a durable JSON/Markdown export that can be reviewed before
being copied into the product as input assets.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

SCHEMA_VERSION = "xhs-profile-import/v1"


@dataclass(frozen=True)
class XhsNote:
    title: str
    note_url: str
    card_text: str = ""
    detail_text: str = ""
    cover_url: str = ""
    engagement_text: str = ""


@dataclass(frozen=True)
class XhsProfileImport:
    platform: str
    source_url: str
    imported_at: str
    import_method: str
    profile_text: str
    notes: list[XhsNote]
    warnings: list[str]


def normalize_whitespace(value: str | None, *, max_chars: int | None = None) -> str:
    text = " ".join((value or "").replace("\u200b", "").split())
    if max_chars is not None and len(text) > max_chars:
        return text[: max_chars - 1].rstrip() + "…"
    return text


def is_likely_note_url(url: str) -> bool:
    return (
        "xiaohongshu.com" in url
        and (
            "/explore/" in url
            or "/discovery/item/" in url
            or "/search_result/" in url
        )
    )


def normalize_note_candidates(
    candidates: list[dict[str, Any]],
    *,
    limit: int,
) -> tuple[list[XhsNote], list[str]]:
    notes: list[XhsNote] = []
    warnings: list[str] = []
    seen_urls: set[str] = set()
    seen_titles: set[str] = set()

    for candidate in candidates:
        raw_url = normalize_whitespace(str(candidate.get("noteUrl") or ""))
        if not raw_url or not is_likely_note_url(raw_url):
            continue

        title = normalize_whitespace(
            str(candidate.get("title") or candidate.get("text") or ""),
            max_chars=120,
        )
        card_text = normalize_whitespace(str(candidate.get("text") or ""), max_chars=1200)
        detail_text = normalize_whitespace(
            str(candidate.get("detailText") or ""), max_chars=6000
        )
        cover_url = normalize_whitespace(str(candidate.get("coverUrl") or ""))
        engagement_text = normalize_whitespace(
            str(candidate.get("engagementText") or ""), max_chars=240
        )

        if not title and not card_text and not detail_text:
            continue
        if not title:
            title = first_content_line(detail_text or card_text)

        dedupe_key = raw_url.split("#", 1)[0]
        title_key = title.lower()
        if dedupe_key in seen_urls or (title_key and title_key in seen_titles):
            continue

        seen_urls.add(dedupe_key)
        if title_key:
            seen_titles.add(title_key)
        notes.append(
            XhsNote(
                title=title,
                note_url=raw_url,
                card_text=card_text,
                detail_text=detail_text,
                cover_url=cover_url,
                engagement_text=engagement_text,
            )
        )
        if len(notes) >= limit:
            break

    if not notes:
        warnings.append(
            "没有从当前页面快照中识别到笔记链接。请确认已登录、主页已加载，并向下滚动后重试。"
        )

    return notes, warnings


def first_content_line(text: str) -> str:
    for line in (text or "").splitlines():
        cleaned = normalize_whitespace(line, max_chars=120)
        if cleaned:
            return cleaned
    return "未命名笔记"


def build_profile_import(
    *,
    source_url: str,
    profile_text: str,
    candidates: list[dict[str, Any]],
    limit: int,
    extra_warnings: list[str] | None = None,
) -> XhsProfileImport:
    notes, warnings = normalize_note_candidates(candidates, limit=limit)
    warnings.extend(extra_warnings or [])
    return XhsProfileImport(
        platform="xiaohongshu",
        source_url=source_url,
        imported_at=datetime.now(UTC).isoformat(),
        import_method="browser_assisted_visible_page",
        profile_text=trim_profile_text(profile_text),
        notes=notes,
        warnings=warnings,
    )


def trim_profile_text(value: str | None) -> str:
    text = normalize_whitespace(value, max_chars=5000)
    if not text:
        return ""

    account_marker = "小红书号："
    account_index = text.find(account_marker)
    if account_index >= 0:
        start_candidates = [
            text.rfind("电话：9501-3888", 0, account_index),
            text.rfind("更多 关于我们", 0, account_index),
            text.rfind("首页", 0, account_index),
        ]
        start = max(start_candidates)
        if start >= 0:
            if text.startswith("电话：9501-3888", start):
                start += len("电话：9501-3888")
            elif text.startswith("更多 关于我们", start):
                start += len("更多 关于我们")
            elif text.startswith("首页", start):
                start = max(text.rfind(" ", 0, account_index - 1), 0)
        else:
            start = max(0, account_index - 80)
        text = text[start:].strip()

    for marker in [" 笔记 收藏 点赞", " 笔记・", " 收藏 点赞"]:
        marker_index = text.find(marker)
        if marker_index > 0:
            text = text[:marker_index].strip()
            break
    return normalize_whitespace(text, max_chars=2000)


def to_jsonable(profile_import: XhsProfileImport) -> dict[str, Any]:
    return {
        "schemaVersion": SCHEMA_VERSION,
        "platform": profile_import.platform,
        "sourceUrl": profile_import.source_url,
        "importedAt": profile_import.imported_at,
        "importMethod": profile_import.import_method,
        "creator": {
            "profileText": profile_import.profile_text,
        },
        "notes": [
            {
                "title": note.title,
                "url": note.note_url,
                "cardText": note.card_text,
                "detailText": note.detail_text,
                "coverUrl": note.cover_url,
                "engagementText": note.engagement_text,
            }
            for note in profile_import.notes
        ],
        "warnings": list(profile_import.warnings),
    }


def to_legacy_jsonable(profile_import: XhsProfileImport) -> dict[str, Any]:
    return asdict(profile_import)


def format_historical_posts_markdown(profile_import: XhsProfileImport) -> str:
    lines = [
        "# 小红书主页导入",
        "",
        f"- 平台：{profile_import.platform}",
        f"- 来源：{profile_import.source_url}",
        f"- 导入时间：{profile_import.imported_at}",
        f"- 导入方式：{profile_import.import_method}",
        "",
    ]
    if profile_import.profile_text:
        lines.extend(["## 主页可见信息", "", profile_import.profile_text, ""])
    lines.extend(["## 笔记列表", ""])
    for index, note in enumerate(profile_import.notes, start=1):
        content = note.detail_text or note.card_text
        lines.extend(
            [
                f"### {index}. {note.title}",
                "",
                f"- 链接：{note.note_url}",
            ]
        )
        if note.cover_url:
            lines.append(f"- 封面：{note.cover_url}")
        if note.engagement_text:
            lines.append(f"- 可见互动信息：{note.engagement_text}")
        lines.extend(["", content or "（未抓取到正文，仅保留链接和标题。）", ""])
    if profile_import.warnings:
        lines.extend(["## 导入提示", ""])
        lines.extend(f"- {warning}" for warning in profile_import.warnings)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
