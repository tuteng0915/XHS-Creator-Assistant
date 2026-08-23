"""Helpers for converting MediaCrawler XHS exports into SqsAgent assets."""

from __future__ import annotations

import json
import shutil
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class XhsMediaCrawlerNote:
    note_id: str
    note_type: str
    nickname: str
    title: str
    desc: str
    note_url: str
    tag_list: list[str]
    liked_count: int | None
    collected_count: int | None
    comment_count: int | None
    share_count: int | None
    cover_path: Path | None


@dataclass(frozen=True)
class XhsMediaCrawlerComment:
    comment_id: str
    note_id: str
    content: str
    like_count: int | None
    sub_comment_count: int | None
    create_time: int | None


@dataclass(frozen=True)
class XhsMediaCrawlerExport:
    code: str
    base_dir: Path
    notes: list[XhsMediaCrawlerNote]
    comments: list[XhsMediaCrawlerComment]


@dataclass(frozen=True)
class XhsImportPackageSummary:
    output_dir: Path
    profile_path: Path
    display_name: str
    note_count: int
    comment_count: int
    copied_cover_count: int
    missing_cover_count: int
    warnings: list[str]


def load_mediacrawler_export(base_dir: Path, *, code: str) -> XhsMediaCrawlerExport:
    xhs_dir = base_dir / "xhs"
    if not xhs_dir.exists() and (base_dir / "jsonl").exists():
        xhs_dir = base_dir
    notes_path = _latest_matching_file(xhs_dir / "jsonl", "creator_contents_*.jsonl")
    comments_path = _latest_matching_file(
        xhs_dir / "jsonl", "creator_comments_*.jsonl", required=False
    )
    notes = [
        _parse_note(row, xhs_dir=xhs_dir)
        for row in _read_jsonl(notes_path)
    ]
    comments = (
        [_parse_comment(row) for row in _read_jsonl(comments_path)]
        if comments_path is not None
        else []
    )
    return XhsMediaCrawlerExport(
        code=code,
        base_dir=xhs_dir,
        notes=[note for note in notes if note.note_id and note.title],
        comments=[
            comment
            for comment in comments
            if comment.note_id and (comment.content or comment.comment_id)
        ],
    )


def export_xhs_import_package(
    export: XhsMediaCrawlerExport,
    output_dir: Path,
    *,
    overwrite: bool = True,
) -> XhsImportPackageSummary:
    if output_dir.exists() and not overwrite and any(output_dir.iterdir()):
        raise FileExistsError(f"Output directory already exists and is not empty: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    profile_payload = build_xhs_creator_profile_payload(export)
    profile_path = output_dir / "xhs_creator_profile.json"
    profile_path.write_text(
        json.dumps(profile_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    copied_covers = 0
    missing_covers = 0
    warnings: list[str] = []
    for note in export.notes:
        if note.cover_path is None:
            missing_covers += 1
            warnings.append(f"笔记缺少封面：{note.note_id} {note.title}")
            continue
        note_image_dir = images_dir / note.note_id
        note_image_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(note.cover_path, note_image_dir / note.cover_path.name)
        copied_covers += 1

    missing_relative_paths = [
        note["cover"]["relativePath"]
        for note in profile_payload["notes"]
        if note.get("cover", {}).get("relativePath")
        and not (output_dir / note["cover"]["relativePath"]).is_file()
    ]
    for relative_path in missing_relative_paths:
        warnings.append(f"profile JSON 中的封面相对路径不存在：{relative_path}")

    return XhsImportPackageSummary(
        output_dir=output_dir,
        profile_path=profile_path,
        display_name=infer_creator_display_name(export),
        note_count=len(export.notes),
        comment_count=len(export.comments),
        copied_cover_count=copied_covers,
        missing_cover_count=missing_covers,
        warnings=warnings,
    )


def build_account_profile_markdown(export: XhsMediaCrawlerExport) -> str:
    display_name = infer_creator_display_name(export)
    type_counts = Counter(note.note_type or "unknown" for note in export.notes)
    tag_counts = Counter(tag for note in export.notes for tag in note.tag_list)
    top_notes = sorted(
        export.notes,
        key=lambda note: (
            note.liked_count or 0,
            note.collected_count or 0,
            note.share_count or 0,
        ),
        reverse=True,
    )[:5]
    lines = [
        f"# 小红书账号概况：{display_name}",
        "",
        "这是一份由 MediaCrawler 离线导入结果生成的确定性摘要，不是 LLM 诊断结论。",
        "",
        "## 数据范围",
        "",
        f"- 笔记数：{len(export.notes)}",
        f"- 一级评论数：{len(export.comments)}",
        "- 内容类型：" + _format_counter(type_counts),
    ]
    if tag_counts:
        lines.append("- 高频标签：" + "、".join(tag for tag, _ in tag_counts.most_common(12)))
    lines.extend(["", "## 高互动笔记", ""])
    for index, note in enumerate(top_notes, start=1):
        engagement = (
            f"赞：{_display_count(note.liked_count)}；"
            f"收藏：{_display_count(note.collected_count)}；"
            f"评论：{_display_count(note.comment_count)}；"
            f"分享：{_display_count(note.share_count)}"
        )
        lines.extend(
            [
                f"{index}. {note.title}",
                f"   - {engagement}",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def build_historical_posts_markdown(
    export: XhsMediaCrawlerExport,
    *,
    media_asset_ids_by_note: dict[str, str] | None = None,
) -> str:
    media_asset_ids_by_note = media_asset_ids_by_note or {}
    lines = [
        f"# 小红书历史笔记：{export.code}",
        "",
        f"- 来源代号：{export.code}",
        f"- 笔记数：{len(export.notes)}",
        "",
    ]
    for index, note in enumerate(export.notes, start=1):
        engagement = (
            f"赞：{_display_count(note.liked_count)}；"
            f"收藏：{_display_count(note.collected_count)}；"
            f"评论：{_display_count(note.comment_count)}；"
            f"分享：{_display_count(note.share_count)}"
        )
        lines.extend(
            [
                f"## {index}. {note.title}",
                "",
                f"- note_id：{note.note_id}",
                f"- 类型：{note.note_type or 'unknown'}",
                f"- 链接：{note.note_url or '未知'}",
                f"- {engagement}",
            ]
        )
        if note.tag_list:
            lines.append("- 标签：" + "、".join(note.tag_list))
        if media_asset_id := media_asset_ids_by_note.get(note.note_id):
            lines.append(f"- 封面 MediaAsset：{media_asset_id}")
        lines.extend(["", note.desc or "（未抓取到正文。）", ""])
    return "\n".join(lines).rstrip() + "\n"


def build_comments_markdown(export: XhsMediaCrawlerExport) -> str:
    comments_by_note: dict[str, list[XhsMediaCrawlerComment]] = defaultdict(list)
    for comment in export.comments:
        comments_by_note[comment.note_id].append(comment)
    lines = [
        f"# 小红书一级评论样本：{export.code}",
        "",
        f"- 来源代号：{export.code}",
        f"- 一级评论数：{len(export.comments)}",
        "",
    ]
    for note in export.notes:
        note_comments = comments_by_note.get(note.note_id, [])
        lines.extend(
            [
                f"## {note.title}",
                "",
                f"- note_id：{note.note_id}",
                f"- 抓取评论数：{len(note_comments)}",
                "",
            ]
        )
        if not note_comments:
            lines.extend(["（本次未抓取到一级评论。）", ""])
            continue
        for index, comment in enumerate(note_comments, start=1):
            content = comment.content or "（图片评论或空文本评论）"
            comment_meta = (
                f"comment_id：{comment.comment_id or '未知'}；"
                f"赞：{_display_count(comment.like_count)}；"
                f"二级评论数：{_display_count(comment.sub_comment_count)}"
            )
            lines.extend(
                [
                    f"{index}. {content}",
                    f"   - {comment_meta}",
                ]
            )
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def build_xhs_creator_profile_payload(
    export: XhsMediaCrawlerExport,
    *,
    media_asset_ids_by_note: dict[str, str] | None = None,
) -> dict[str, Any]:
    media_asset_ids_by_note = media_asset_ids_by_note or {}
    comments_by_note: dict[str, list[XhsMediaCrawlerComment]] = defaultdict(list)
    for comment in export.comments:
        comments_by_note[comment.note_id].append(comment)
    display_name = infer_creator_display_name(export)
    return {
        "schemaVersion": "xhs-creator-profile/v1",
        "source": {
            "platform": "xiaohongshu",
            "fixtureCode": export.code,
            "importedAt": datetime.now(UTC).isoformat(),
            "crawler": "MediaCrawler",
            "baseDir": str(export.base_dir),
        },
        "creator": {
            "displayName": display_name,
            "profileText": build_account_profile_markdown(export),
        },
        "notes": [
            {
                "noteId": note.note_id,
                "type": note.note_type or "normal",
                "title": note.title,
                "desc": note.desc,
                "noteUrl": note.note_url,
                "tags": note.tag_list,
                "metrics": {
                    "liked": note.liked_count,
                    "collected": note.collected_count,
                    "comments": note.comment_count,
                    "shares": note.share_count,
                },
                "cover": {
                    "relativePath": _fixture_cover_relative_path(note),
                    "caption": note.desc or note.title,
                },
                "coverMediaAssetId": media_asset_ids_by_note.get(note.note_id),
                "comments": [
                    {
                        "commentId": comment.comment_id,
                        "content": comment.content,
                        "likeCount": comment.like_count,
                        "subCommentCount": comment.sub_comment_count,
                        "createTime": comment.create_time,
                    }
                    for comment in comments_by_note.get(note.note_id, [])
                ],
            }
            for note in export.notes
        ],
    }


def _fixture_cover_relative_path(note: XhsMediaCrawlerNote) -> str:
    if note.cover_path is None:
        return ""
    return f"images/{note.note_id}/{note.cover_path.name}"


def infer_creator_display_name(export: XhsMediaCrawlerExport) -> str:
    nicknames = Counter(note.nickname for note in export.notes if note.nickname)
    if nicknames:
        return nicknames.most_common(1)[0][0]
    return export.code


def _latest_matching_file(directory: Path, pattern: str, *, required: bool = True) -> Path | None:
    matches = sorted(directory.glob(pattern))
    if matches:
        return matches[-1]
    if required:
        raise FileNotFoundError(f"Cannot find {pattern} under {directory}")
    return None


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _parse_note(row: dict[str, Any], *, xhs_dir: Path) -> XhsMediaCrawlerNote:
    note_id = _clean(row.get("note_id"))
    return XhsMediaCrawlerNote(
        note_id=note_id,
        note_type=_clean(row.get("type")),
        nickname=_clean(row.get("nickname")),
        title=_clean(row.get("title")) or "未命名笔记",
        desc=_clean(row.get("desc")),
        note_url=_clean(row.get("note_url")),
        tag_list=_split_tags(row.get("tag_list")),
        liked_count=_to_int(row.get("liked_count")),
        collected_count=_to_int(row.get("collected_count")),
        comment_count=_to_int(row.get("comment_count")),
        share_count=_to_int(row.get("share_count")),
        cover_path=_cover_path(xhs_dir, note_id),
    )


def _parse_comment(row: dict[str, Any]) -> XhsMediaCrawlerComment:
    return XhsMediaCrawlerComment(
        comment_id=_clean(row.get("comment_id")),
        note_id=_clean(row.get("note_id")),
        content=_clean(row.get("content")),
        like_count=_to_int(row.get("like_count")),
        sub_comment_count=_to_int(row.get("sub_comment_count")),
        create_time=_to_int(row.get("create_time")),
    )


def _cover_path(xhs_dir: Path, note_id: str) -> Path | None:
    if not note_id:
        return None
    path = xhs_dir / "images" / note_id / "0.jpg"
    return path if path.is_file() else None


def _split_tags(value: Any) -> list[str]:
    text = _clean(value)
    if not text:
        return []
    return [item.strip() for item in text.split(",") if item.strip()]


def _clean(value: Any) -> str:
    return " ".join(str(value or "").replace("\u200b", "").split())


def _to_int(value: Any) -> int | None:
    text = _clean(value).replace(",", "")
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def _display_count(value: int | None) -> str:
    return str(value) if value is not None else "未知"


def _format_counter(counter: Counter[str]) -> str:
    if not counter:
        return "未知"
    return "、".join(f"{key} {value}" for key, value in counter.most_common())
