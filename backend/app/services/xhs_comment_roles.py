"""Compare MediaCrawler's anonymous author hashes, never names or writing style."""

import re


def author_hash(value: object) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip().lower()
    return value if re.fullmatch(r"[0-9a-f]{16}", value) else ""


def comment_source_role(note: dict, comment: dict) -> str:
    note_author = author_hash(note.get("authorHash"))
    comment_author = author_hash(comment.get("authorHash"))
    if not note_author or not comment_author:
        return "unknown"
    return "author" if note_author == comment_author else "non_author"


def reader_comments_text(profile: dict) -> str:
    """Derived inference input only; keep raw comments and platform counts intact."""
    lines = ["# 小红书一级评论样本（由 xhs_creator_profile 派生）", ""]
    for note in profile.get("notes", []):
        if not isinstance(note, dict):
            continue
        comments = note.get("comments") if isinstance(note.get("comments"), list) else []
        candidates = [(comment, comment_source_role(note, comment)) for comment in comments
                      if isinstance(comment, dict)]
        readers = [(comment, role) for comment, role in candidates if role != "author"]
        lines.extend([
            f"## {note.get('title') or '未命名笔记'}", "",
            f"- note_id：{note.get('noteId') or '未知'}",
            f"- 抓取评论数：{len(comments)}；本次候选评论数：{len(readers)}；"
            f"已排除作者评论数：{sum(role == 'author' for _, role in candidates)}", "",
        ])
        if not readers:
            lines.extend(["（本次没有可用于读者需求推导的评论，不推断评论需求。）", ""])
            continue
        for index, (comment, role) in enumerate(readers, start=1):
            lines.extend([
                f"{index}. {comment.get('content') or '（图片评论或空文本评论）'}",
                f"   - comment_id：{comment.get('commentId') or '未知'}；"
                f"sourceRole：{role}；赞：{comment.get('likeCount', '未知')}；"
                f"二级评论数：{comment.get('subCommentCount', '未知')}",
            ])
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
