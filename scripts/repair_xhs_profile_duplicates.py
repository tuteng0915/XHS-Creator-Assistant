"""Remove exact duplicate notes/comments from one imported XHS profile.

This is a one-time repair for existing imports. New MediaCrawler exports are
deduplicated before import by xhs_mediacrawler_fixture.py.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path


def deduplicate_profile(profile: dict) -> tuple[dict, int, int]:
    if profile.get("schemaVersion") != "xhs-creator-profile/v1":
        raise ValueError("不是受支持的小红书创作者档案")
    notes = profile.get("notes")
    if not isinstance(notes, list):
        raise ValueError("档案缺少笔记列表")

    cleaned = {**profile, "notes": []}
    first_notes: dict[str, dict] = {}
    removed_notes = 0
    removed_comments = 0
    for note in notes:
        if not isinstance(note, dict) or not note.get("noteId"):
            raise ValueError("笔记缺少稳定 ID，不能自动去重")
        note_id = str(note["noteId"])
        previous = first_notes.get(note_id)
        if previous is not None:
            if note != previous:
                raise ValueError("同一笔记 ID 的内容不同，需要人工检查")
            removed_notes += 1
            removed_comments += len(note.get("comments", []))
            continue
        first_notes[note_id] = note

        comments = note.get("comments", [])
        if not isinstance(comments, list):
            raise ValueError("评论列表格式错误")
        unique_comments: list[dict] = []
        first_comments: dict[str, dict] = {}
        for comment in comments:
            if not isinstance(comment, dict):
                raise ValueError("评论格式错误")
            comment_id = str(comment.get("commentId") or "")
            previous_comment = first_comments.get(comment_id) if comment_id else None
            if previous_comment is not None:
                if comment != previous_comment:
                    raise ValueError("同一评论 ID 的内容不同，需要人工检查")
                removed_comments += 1
                continue
            if comment_id:
                first_comments[comment_id] = comment
            unique_comments.append(comment)
        cleaned["notes"].append({**note, "comments": unique_comments})
    return cleaned, removed_notes, removed_comments


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--asset-id", required=True)
    parser.add_argument("--apply", action="store_true", help="备份数据库后写入去重结果")
    args = parser.parse_args()

    database = args.database.resolve()
    with sqlite3.connect(f"file:{database}?mode=ro", uri=True) as connection:
        row = connection.execute(
            "SELECT type,text_content,updated_at FROM source_materials WHERE id=?",
            (args.asset_id,),
        ).fetchone()
    if row is None or row[0] != "xhs_creator_profile":
        raise ValueError("找不到指定的小红书创作者档案")
    original = json.loads(row[1])
    cleaned, removed_notes, removed_comments = deduplicate_profile(original)
    print(
        f"笔记 {len(original['notes'])} → {len(cleaned['notes'])}；"
        f"移除重复笔记 {removed_notes}、重复评论 {removed_comments}。"
    )
    if not args.apply or not (removed_notes or removed_comments):
        print("未修改数据库。")
        return

    backup_dir = database.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup_path = backup_dir / f"xhs-profile-dedup-{stamp}.sqlite3"
    if backup_path.exists():
        raise FileExistsError("同名数据库备份已存在")
    with sqlite3.connect(database) as source, sqlite3.connect(backup_path) as backup:
        source.backup(backup)

    with sqlite3.connect(database) as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute(
            "UPDATE source_materials SET text_content=?, updated_at=? "
            "WHERE id=? AND type='xhs_creator_profile' AND updated_at=?",
            (
                json.dumps(cleaned, ensure_ascii=False, indent=2),
                datetime.now(UTC).isoformat(),
                args.asset_id,
                row[2],
            ),
        )
        if cursor.rowcount != 1:
            raise RuntimeError("档案已被其他操作更新；未写入，请重新检查")
    print(f"已更新档案；数据库备份：{backup_path}")


if __name__ == "__main__":
    main()
