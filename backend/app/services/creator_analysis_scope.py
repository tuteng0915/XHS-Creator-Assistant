import math
from datetime import UTC, datetime, timedelta

from app.errors import ValidationError


def note_published_at(note: dict) -> datetime | None:
    raw = note.get("publishedAt")
    if raw is None or raw == "" or isinstance(raw, bool):
        return None
    try:
        numeric = float(raw)
        return (datetime.fromtimestamp(numeric / 1000 if numeric >= 1e12 else numeric, UTC)
                if numeric > 0 else None)
    except (ValueError, TypeError, OverflowError, OSError):
        try:
            parsed = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
            parsed = parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed
            return parsed if parsed.timestamp() > 0 else None
        except ValueError:
            return None


METRIC_KEYS = ("liked", "collected", "comments", "shares")


def valid_note_metric(value) -> int | float | None:
    return (value if isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0 else None)


def note_rank_value(note: dict, scope: str) -> int | float | None:
    metrics = note.get("metrics") or {}
    if not isinstance(metrics, dict):
        return None
    keys = ("liked",) if scope == "most_liked_10" else METRIC_KEYS
    values = [value for key in keys if (value := valid_note_metric(metrics.get(key))) is not None]
    return sum(values) if values else None


def ordered_notes(notes: list[dict], *, ranking: str | None = None) -> list[dict]:
    # Stable ID settles ties identically to the browser; missing dates sort last.
    def order(note):
        date = note_published_at(note)
        timestamp = date.timestamp() if date else 0
        return (-(note_rank_value(note, ranking) or 0) if ranking else 0,
                -timestamp, str(note.get("noteId") or ""))
    return sorted(notes, key=order)


def scope_creator_profile(
    profile: dict, scope: str, *, now: datetime | None = None,
    selected_note_ids: list[str] | None = None,
) -> tuple[dict, dict]:
    now = now or datetime.now(UTC)
    notes = [note for note in profile.get("notes", []) if isinstance(note, dict)]
    # Match the browser's stable fallback for legacy imports without note IDs.
    notes = [{**note, "noteId": str(note.get("noteId") or index)}
             for index, note in enumerate(notes)]
    requested_scope = scope
    selected = notes
    cutoff = None
    if selected_note_ids is not None:
        requested = set(selected_note_ids)
        available = [note["noteId"] for note in notes]
        if (not requested or len(requested) != len(selected_note_ids)
                or not requested.issubset(available)
                or any(available.count(note_id) != 1 for note_id in requested)):
            raise ValidationError("所选笔记无效或已变更，请重新选择当前账号的笔记。")
        selected = [note for note in notes if note["noteId"] in requested]
        scope = "custom"
    elif scope == "recent_10":
        selected = ordered_notes(notes)[:10]
    elif scope in {"most_liked_10", "most_engaged_10"}:
        selected = ordered_notes(
            [note for note in notes if note_rank_value(note, scope) is not None], ranking=scope,
        )[:10]
    elif scope.startswith("last_"):
        cutoff = now - timedelta(days=int(scope.split("_")[1]))
        selected = ordered_notes([
            note for note in notes
            if (date := note_published_at(note)) is not None and cutoff <= date <= now
        ])
    if not selected:
        raise ValidationError("所选分析范围内没有笔记，请调整范围或重新导入账号。")
    # The crawler's profileText summarizes all notes. Do not leak that summary
    # into a diagnosis that explicitly selected only a subset.
    creator = dict(profile.get("creator") or {})
    if scope != "all":
        creator.pop("profileText", None)
    metadata = {
        "scope": scope,
        "selectionMethod": "explicit_ids" if selected_note_ids is not None else "preset",
        "asOf": now.isoformat(),
        "since": cutoff.isoformat() if cutoff else None,
        "availableNoteCount": len(notes),
        "selectedNoteIds": [note.get("noteId") for note in selected],
        "selectedNoteCount": len(selected),
        "unknownDateCount": sum(note_published_at(note) is None for note in notes),
    }
    if requested_scope in {"most_liked_10", "most_engaged_10"}:
        keys = ("liked",) if requested_scope == "most_liked_10" else METRIC_KEYS
        observations = []
        for note in selected:
            metrics = note.get("metrics") if isinstance(note.get("metrics"), dict) else {}
            observations.append({
                "noteId": note.get("noteId"),
                "value": note_rank_value(note, requested_scope),
                "includedMetrics": [
                    k for k in keys if valid_note_metric(metrics.get(k)) is not None
                ],
                "missingMetrics": [k for k in keys if valid_note_metric(metrics.get(k)) is None],
            })
        metadata["ranking"] = {
            "basis": ("recorded_likes" if requested_scope == "most_liked_10"
                      else "recorded_interaction_sum"),
            "tieBreak": ["publishedAt_desc", "noteId_asc"],
            "observations": observations,
        }
    return {**profile, "creator": creator, "notes": selected}, metadata
