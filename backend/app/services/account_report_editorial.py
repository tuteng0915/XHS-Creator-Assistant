"""Compile source-local report readings into the existing display contract.

These checks establish literal provenance, not whether an interpretation or a
suggestion is semantically justified. No assets are read beyond the frozen input.
"""

from __future__ import annotations

from typing import Any

from app.services.account_profile_shape import normalize_profile_stage_result
from app.services.account_report_lean import LEAN_REPORT_FORMAT, compile_lean_profile
from app.services.account_report_sources import resolve_editorial_refs

REPORT_FORMAT = "source-led/v1"
MAX_READINGS = 3


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} 必须是非空文字")
    return value


def _items(value: Any, field: str, *, minimum: int = 0, maximum: int = MAX_READINGS) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{field} 必须是包含 {minimum} 至 {maximum} 项的列表")
    if any(not isinstance(item, dict) for item in value):
        raise ValueError(f"{field} 每项必须是对象")
    return value


def _source_notes(snapshot: dict[str, Any]) -> dict[str, dict[str, str]]:
    source = snapshot.get("xhsCreatorProfile") if isinstance(snapshot, dict) else None
    notes = source.get("notes") if isinstance(source, dict) else None
    if not isinstance(notes, list):
        raise ValueError("source-led/v1 需要冻结的 xhsCreatorProfile.notes 列表")
    indexed = {}
    for note in notes:
        if not isinstance(note, dict):
            raise ValueError("冻结笔记必须是对象")
        note_id = _text(note.get("noteId"), "冻结笔记 noteId")
        if note_id in indexed:
            raise ValueError(f"冻结笔记 noteId 重复，无法唯一核验：{note_id}")
        title, desc = note.get("title", ""), note.get("desc", "")
        if not isinstance(title, str) or not isinstance(desc, str):
            raise ValueError(f"冻结笔记标题和正文必须是文字：{note_id}")
        indexed[note_id] = {"title": title, "desc": desc}
    return indexed


def _note(notes: dict[str, dict[str, str]], value: Any, field: str) -> dict[str, str]:
    note_id = _text(value, field)
    if note_id not in notes:
        raise ValueError(f"{field} 不在本次冻结笔记中：{note_id}")
    return notes[note_id]


def _title_formulas(
    readings: list, notes: dict[str, dict[str, str]], *, allow_whole_title: bool = False,
) -> list[dict]:
    compiled = []
    for reading in readings:
        note = _note(notes, reading.get("noteId"), "titleReadings.noteId")
        move = _text(reading.get("move"), "titleReadings.move")
        parts = _items(reading.get("parts"), "titleReadings.parts",
                       minimum=1 if allow_whole_title else 2, maximum=4)
        cursor, fragments = 0, []
        for part in parts:
            text = _text(part.get("text"), "titleReadings.parts.text")
            role = _text(part.get("role"), "titleReadings.parts.role")
            if len(parts) == 1 and text != note["title"]:
                raise ValueError("单个标题片段必须逐字等于完整原标题")
            start = note["title"].find(text, cursor)
            if start < 0:
                raise ValueError("标题片段必须来自同一原标题，按原顺序且不能重叠")
            cursor = start + len(text)
            fragments.append(f"{text}（{role}）")
        compiled.append({"formula": f"{move}：" + "→".join(fragments),
                         "examples": [note["title"]]})
    return compiled


def _sentence(text: str) -> str:
    return text if text.endswith(("。", "！", "？", ".", "!", "?")) else text + "。"


def _takeaways(moves: list, notes: dict[str, dict[str, str]]) -> list[str]:
    compiled = []
    for move in moves:
        note = _note(notes, move.get("sourceNoteId"), "nextMoves.sourceNoteId")
        quote = _text(move.get("sourceQuote"), "nextMoves.sourceQuote")
        basis = _text(move.get("basis"), "nextMoves.basis")
        action = _text(move.get("action"), "nextMoves.action")
        # Do not accept a quote spanning title/description or coming from another note.
        if quote not in note["title"] and quote not in note["desc"]:
            raise ValueError("nextMoves.sourceQuote 必须是对应笔记标题或正文内的连续原文")
        compiled.append(f"参考《{note['title']}》：{_sentence(basis)}"
                        f"下一篇可尝试：{_sentence(action)}")
    return compiled


def compile_editorial_profile(output: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy with source-led readings compiled for legacy renderers.

    Unversioned historical profiles are unchanged. Malformed source-led output is
    rejected as a whole, never partially dropped or repaired using guessed text.
    """
    if not isinstance(output, dict):
        raise ValueError("账号报告输出必须是对象")
    original_profile = output.get("profile")
    if (isinstance(original_profile, dict)
            and original_profile.get("reportFormat") == LEAN_REPORT_FORMAT):
        return compile_lean_profile(output, snapshot)
    allow_whole_title = (isinstance(original_profile, dict)
                         and original_profile.get("reportFormat") == "source-led/v3")
    result = resolve_editorial_refs(output, snapshot)
    profile = result.get("profile")
    if not isinstance(profile, dict):
        return result
    portrait = profile.get("accountPortrait")
    if isinstance(portrait, dict) and {
        "reportFormat", "titleReadings", "nextMoves",
    } & portrait.keys():
        raise ValueError("reportFormat/titleReadings/nextMoves 必须位于 profile 同层，不能错嵌画像")
    if "reportFormat" not in profile:
        if "titleReadings" in profile or "nextMoves" in profile:
            raise ValueError("titleReadings/nextMoves 缺少 reportFormat")
        return result
    if profile["reportFormat"] != REPORT_FORMAT:
        raise ValueError(f"不支持的账号报告 reportFormat：{profile['reportFormat']!r}")

    # Relocate known old-field nesting mistakes before checking for dual writes.
    # Unversioned historical output above stays an exact deep copy.
    result = normalize_profile_stage_result(result)
    profile = result["profile"]
    old_formulas = profile.get("titleFormulas", [])
    if not isinstance(old_formulas, list):
        raise ValueError("titleFormulas 必须是列表")
    contrast = profile.get("contrast", {})
    if not isinstance(contrast, dict):
        raise ValueError("contrast 必须是对象")
    old_takeaways = contrast.get("takeaways", [])
    if not isinstance(old_takeaways, list):
        raise ValueError("contrast.takeaways 必须是列表")
    if old_formulas or old_takeaways:
        raise ValueError("source-led/v1 与非空旧 titleFormulas/contrast.takeaways 冲突")

    readings = _items(profile.get("titleReadings", []), "titleReadings")
    moves = _items(profile.get("nextMoves", []), "nextMoves")
    notes = _source_notes(snapshot)
    profile["titleFormulas"] = _title_formulas(readings, notes, allow_whole_title=allow_whole_title)
    profile["contrast"] = {**contrast, "takeaways": _takeaways(moves, notes)}
    for field in ("reportFormat", "titleReadings", "nextMoves"):
        profile.pop(field, None)
    return result
