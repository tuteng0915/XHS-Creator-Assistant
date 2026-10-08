"""Freeze a bounded, distributed sample of an imported account's public writing."""
import json

from app.errors import NotFoundError, ValidationError

MAX_ACCOUNT_NOTES = 12
MAX_NOTE_TEXT = 1200


def account_simulation_target(connection, workspace_id: str, material_id: str) -> dict:
    row = connection.execute(
        "SELECT * FROM source_materials WHERE id=? AND workspace_id=? "
        "AND type='xhs_creator_profile'", (material_id, workspace_id),
    ).fetchone()
    if row is None:
        raise NotFoundError("这份账号资料不在当前账号中")
    try:
        profile = json.loads(row["text_content"])
        if not isinstance(profile, dict) or not isinstance(profile.get("notes"), list):
            raise ValueError("Invalid profile")
    except (ValueError, TypeError) as error:
        raise ValidationError("账号资料暂时无法读取") from error
    usable, seen = [], set()
    for index, note in enumerate(profile["notes"]):
        if not isinstance(note, dict):
            continue
        title, body = str(note.get("title") or ""), str(note.get("desc") or "")
        note_id = str(note.get("noteId") or f"imported-{index}")
        if not (title.strip() or body.strip()) or note_id in seen:
            continue
        seen.add(note_id)
        usable.append({"noteId": note_id, "title": title, "body": body})
    if not usable:
        raise ValidationError("账号资料还没有可供阅读的笔记文字，请先导入笔记")
    count = min(len(usable), MAX_ACCOUNT_NOTES)
    # Includes both ends of the imported sequence, not only the first/recent page.
    indexes = ([0] if count == 1 else
               [i * (len(usable) - 1) // (count - 1) for i in range(count)])
    samples, truncated = [], 0
    for index in indexes:
        note = usable[index]
        title = note["title"][:160]
        body = note["body"][:MAX_NOTE_TEXT - len(title)]
        truncated += int(title != note["title"] or body != note["body"])
        samples.append({"noteId": note["noteId"], "title": title, "body": body})
    creator = profile.get("creator")
    creator = creator if isinstance(creator, dict) else {}
    display_name = str(creator.get("displayName") or "当前账号")[:200]
    biography = str(creator.get("bio") or creator.get("description")
                    or creator.get("profileText") or "")[:1200]
    omitted = len(usable) - count
    notice = f"从 {len(usable)} 篇可读笔记中选取 {count} 篇，沿导入顺序均匀取样。"
    if omitted:
        notice += f"另有 {omitted} 篇未进入本次阅读。"
    if truncated:
        notice += f"其中 {truncated} 篇使用文字节选，每篇最多 {MAX_NOTE_TEXT} 字。"
    return {
        "sourceMaterialId": material_id, "displayName": display_name,
        "biography": biography, "notes": samples,
        "scope": {"sampledNoteCount": count, "totalNoteCount": len(usable),
                  "omittedNoteCount": omitted, "truncatedNoteCount": truncated,
                  "samplingMethod": "evenly_spaced_import_order", "omissionNotice": notice},
        "sourceUpdatedAt": row["updated_at"],
    }


def account_reader_topic(account: dict) -> dict:
    """Same text for retrieval and simulation; never include metrics, comments or strategy."""
    chunks = [f"账号简介：{account['biography']}"] if account.get("biography") else []
    for index, note in enumerate(account["notes"], 1):
        chunks.append(f"笔记 {index}：{note['title']}\n{note['body']}")
    return {"topicId": None, "title": f"{account['displayName']} · 账号整体",
            "body": "\n\n".join(chunks), "sourceWorkflow": "account_simulation"}
