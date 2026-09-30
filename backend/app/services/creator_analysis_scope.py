from datetime import UTC, datetime, timedelta

from app.errors import ValidationError


def note_published_at(note: dict) -> datetime | None:
    raw = note.get("publishedAt")
    if raw is None or raw == "":
        return None
    try:
        numeric = float(raw)
        return datetime.fromtimestamp(numeric / 1000 if numeric >= 1e12 else numeric, UTC)
    except (ValueError, TypeError, OverflowError, OSError):
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
        except ValueError:
            return None


def scope_creator_profile(
    profile: dict, scope: str, *, now: datetime | None = None,
    selected_note_ids: list[str] | None = None,
) -> tuple[dict, dict]:
    now = now or datetime.now(UTC)
    notes = [note for note in profile.get("notes", []) if isinstance(note, dict)]
    selected = notes
    cutoff = None
    if selected_note_ids is not None:
        # Match the browser's stable fallback for legacy imports without note IDs.
        notes = [{**note, "noteId": str(note.get("noteId") or index)}
                 for index, note in enumerate(notes)]
        requested = set(selected_note_ids)
        available = [note["noteId"] for note in notes]
        if (not requested or len(requested) != len(selected_note_ids)
                or not requested.issubset(available)
                or any(available.count(note_id) != 1 for note_id in requested)):
            raise ValidationError("所选笔记无效或已变更，请重新选择当前账号的笔记。")
        selected = [note for note in notes if note["noteId"] in requested]
        scope = "custom"
    elif scope == "recent_10":
        selected = sorted(
            notes, key=lambda note: note_published_at(note) or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )[:10]
    elif scope.startswith("last_"):
        cutoff = now - timedelta(days=int(scope.split("_")[1]))
        selected = [
            note for note in notes
            if (date := note_published_at(note)) is not None and cutoff <= date <= now
        ]
    if not selected:
        raise ValidationError("所选分析范围内没有笔记，请调整范围或重新导入账号。")
    # The crawler's profileText summarizes all notes. Do not leak that summary
    # into a diagnosis that explicitly selected only a subset.
    creator = dict(profile.get("creator") or {})
    if scope != "all":
        creator.pop("profileText", None)
    return {**profile, "creator": creator, "notes": selected}, {
        "scope": scope,
        "asOf": now.isoformat(),
        "since": cutoff.isoformat() if cutoff else None,
        "availableNoteCount": len(notes),
        "selectedNoteIds": [note.get("noteId") for note in selected],
        "selectedNoteCount": len(selected),
        "unknownDateCount": sum(note_published_at(note) is None for note in notes),
    }
