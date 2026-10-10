"""Freeze selected public writing, with the legacy sampled target kept readable."""
import json
from collections import Counter

from app.errors import NotFoundError, ValidationError
from app.services.audience_target import reader_visible_target

MAX_ACCOUNT_NOTES = 12
MAX_NOTE_TEXT = 1200
# Operational input budget, not a tokenizer/context-window claim. Never drop selected notes.
MAX_ACCOUNT_TARGET_BYTES = 48_000


def account_simulation_target(
    connection, workspace_id: str, material_id: str, *,
    selected_note_ids: list[str] | None = None,
) -> dict:
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
    if selected_note_ids is not None:
        return _selected_account_target(profile, row, material_id, selected_note_ids)
    # Preserve legacy input identities and frozen history semantics. New clients use
    # the separate explicit-selection contract, never this fallback.
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


def _selected_account_target(profile, row, material_id: str, selected_note_ids: list[str]) -> dict:
    requested = set(selected_note_ids)
    # creatorNotes filters malformed rows before assigning index IDs to old imports.
    notes = [note for note in profile["notes"] if isinstance(note, dict)]
    notes = [{**note, "noteId": str(note.get("noteId") or index)}
             for index, note in enumerate(notes)]
    counts = Counter(note["noteId"] for note in notes)
    if (not requested or len(requested) != len(selected_note_ids)
            or any(not isinstance(note_id, str) or not note_id.strip() for note_id in requested)
            or any(counts[note_id] != 1 for note_id in requested)):
        raise ValidationError("所选笔记无效或已变更，请重新选择当前账号的笔记。")
    selected = [note for note in notes if note["noteId"] in requested]
    samples, truncated = [], 0
    for note in selected:
        title, body = str(note.get("title") or ""), str(note.get("desc") or "")
        if not (title.strip() or body.strip()):
            raise ValidationError("所选笔记没有可供阅读的文字，请重新选择；未自动省略笔记。")
        excerpt_title = title[:160]
        excerpt_body = body[:MAX_NOTE_TEXT - len(excerpt_title)]
        truncated += int(excerpt_title != title or excerpt_body != body)
        samples.append({"noteId": note["noteId"], "title": excerpt_title, "body": excerpt_body})
    creator = profile.get("creator")
    creator = creator if isinstance(creator, dict) else {}
    # profileText is crawler-generated from every note, not the creator's actual bio.
    biography = str(creator.get("bio") or creator.get("description") or "")[:1200]
    notice = f"本次明确选择 {len(samples)} 篇笔记，全部进入阅读；未选笔记不参与。"
    if truncated:
        notice += f"其中 {truncated} 篇使用文字节选，每篇最多 {MAX_NOTE_TEXT} 字。"
    target = {
        "sourceMaterialId": material_id,
        "displayName": str(creator.get("displayName") or "当前账号")[:200],
        "biography": biography, "notes": samples,
        "scope": {
            "sourceMaterialId": material_id,
            "selectedNoteIds": sorted(requested), "selectedNoteCount": len(samples),
            "sampledNoteCount": len(samples), "totalNoteCount": len(notes),
            "omittedNoteCount": len(notes) - len(samples), "truncatedNoteCount": truncated,
            "selectionMethod": "explicit_ids", "samplingMethod": "explicit_selection",
            "omissionNotice": notice,
        },
        "sourceUpdatedAt": row["updated_at"],
    }
    visible = reader_visible_target({
        "targetType": "account", "topic": account_reader_topic(target), "sourceAccount": target,
    })
    if len(json.dumps(visible, ensure_ascii=False).encode("utf-8")) > MAX_ACCOUNT_TARGET_BYTES:
        raise ValidationError("所选笔记内容过长，请减少所选篇数后重试；不会自动省略笔记。")
    return target


def account_reader_topic(account: dict) -> dict:
    """Same text for retrieval and simulation; never include metrics, comments or strategy."""
    chunks = [f"账号简介：{account['biography']}"] if account.get("biography") else []
    for index, note in enumerate(account["notes"], 1):
        chunks.append(f"笔记 {index}：{note['title']}\n{note['body']}")
    label = (f"所选 {len(account['notes'])} 篇笔记"
             if account.get("scope", {}).get("selectionMethod") == "explicit_ids" else "账号整体")
    return {"topicId": None, "title": f"{account['displayName']} · {label}",
            "body": "\n\n".join(chunks), "sourceWorkflow": "account_simulation"}
