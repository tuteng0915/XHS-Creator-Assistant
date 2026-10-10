"""Keep saved comments when a refresh supplies no comment sample."""

import re
from collections import Counter
from copy import deepcopy
from urllib.parse import urlparse

from app.errors import ValidationError
from app.services.xhs_comment_roles import author_hash


def preserve_unfetched_comments(previous: dict, incoming: dict) -> None:
    """Mutate only the incoming snapshot; an empty sample is not a deletion receipt.

    Nonempty new samples retain the existing replacement behavior. Partial-sample
    merging needs a separate completeness contract, not guessed deletion semantics.
    """
    previous_path, incoming_path = _profile_path(previous), _profile_path(incoming)
    if previous_path and incoming_path and previous_path != incoming_path:
        raise ValidationError("导入链接属于另一个账号，请使用对应的账号档案。")
    previous_notes = _notes(previous)
    incoming_notes = _notes(incoming)
    previous_counts = Counter(note.get("noteId") for note in previous_notes)
    incoming_counts = Counter(note.get("noteId") for note in incoming_notes)
    previous_by_id = {note.get("noteId"): note for note in previous_notes}
    for note in incoming_notes:
        note_id = note.get("noteId")
        # The parser's positional fallback cannot identify a note across imports.
        if (not isinstance(note_id, str) or not note_id.strip()
                or re.fullmatch(r"note-\d+", note_id)
                or previous_counts[note_id] != 1 or incoming_counts[note_id] != 1):
            continue
        old = previous_by_id[note_id]
        new_comments, old_comments = note.get("comments"), old.get("comments")
        if isinstance(new_comments, list) and new_comments:
            continue
        if not isinstance(old_comments, list) or not old_comments:
            continue
        old_author = author_hash(old.get("authorHash"))
        new_author = author_hash(note.get("authorHash") or note.get("creator_hash"))
        if old_author and new_author and old_author != new_author:
            raise ValidationError("同一笔记的作者信息不一致，请检查导入资料。")
        note["comments"] = deepcopy(old_comments)
        # Keep the context needed to identify author replies in the retained sample.
        if old_author and not new_author:
            note["authorHash"] = old_author
        if "commentsObservedAt" in old:
            note["commentsObservedAt"] = old["commentsObservedAt"]
        else:
            note.pop("commentsObservedAt", None)


def _notes(profile: dict) -> list[dict]:
    notes = profile.get("notes")
    if not isinstance(notes, list):
        return []
    return [note for note in notes
            if isinstance(note, dict) and isinstance(note.get("noteId"), str)]


def _profile_path(profile: dict) -> str:
    source = profile.get("source")
    if not isinstance(source, dict):
        return ""
    for key in ("profileUrl", "sourceUrl"):
        value = source.get(key)
        if not isinstance(value, str):
            continue
        parsed = urlparse(value)
        if parsed.hostname == "www.xiaohongshu.com" and parsed.path.startswith("/user/profile/"):
            return parsed.path.rstrip("/")
    return ""
