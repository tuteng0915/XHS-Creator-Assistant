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
