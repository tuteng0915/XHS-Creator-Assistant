"""Resolve imported notes without copying them into the creator's topic library."""
import json

from app.errors import NotFoundError, ValidationError


def saved_note_target(connection, workspace_id: str, material_id: str, note_id: str) -> dict:
    row = connection.execute(
        "SELECT * FROM source_materials WHERE id=? AND workspace_id=? "
        "AND type='xhs_creator_profile'",
        (material_id, workspace_id),
    ).fetchone()
    if row is None:
        raise NotFoundError("这份笔记资料不在当前账号中")
    try:
        notes = json.loads(row["text_content"]).get("notes", [])
        matches = [note for note in notes
                   if isinstance(note, dict) and str(note.get("noteId")) == note_id]
    except (ValueError, TypeError, AttributeError) as error:
        raise ValidationError("笔记资料暂时无法读取") from error
    if len(matches) != 1:
        raise NotFoundError("笔记不存在或来源不唯一，请重新选择")
    note = matches[0]
    return {"sourceMaterialId": material_id, "noteId": note_id,
            "title": str(note.get("title") or "未命名笔记"),
            "body": str(note.get("desc") or ""),
            "metrics": note.get("metrics") or {}, "publishedAt": note.get("publishedAt"),
            "sourceUpdatedAt": row["updated_at"]}
