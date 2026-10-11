"""Exact, deterministic excerpt IDs for source-led account reports."""

import json
import re
from copy import deepcopy
from typing import Any

from app.services.account_profile_shape import PROFILE_FIELDS, normalize_profile_stage_result
from app.services.account_report_patterns import compile_report_patterns

_SEGMENTS = re.compile(r".*?(?:[\r\n。！？]+|[.!?]+(?=\s|$)|$)", re.DOTALL)
MAX_BODY_EXCERPT = 160


def _catalog(notes: Any, body_field: str) -> dict[str, dict[str, str]]:
    if not isinstance(notes, list):
        raise ValueError("引用目录需要笔记列表")
    catalog = {}
    for note in notes:
        if not isinstance(note, dict):
            raise ValueError("引用目录中的笔记必须是对象")
        note_id = note.get("noteId")
        if not isinstance(note_id, str) or not note_id.strip() or note_id in catalog:
            raise ValueError("引用目录需要唯一且非空的 noteId")
        title, body = note.get("title", ""), note.get(body_field, "")
        if not isinstance(title, str) or not isinstance(body, str):
            raise ValueError("引用目录的标题和正文必须是文字")
        excerpts = {"t": title} if title else {}
        chunks = [part[start:start + MAX_BODY_EXCERPT]
                  for match in _SEGMENTS.finditer(body) if (part := match.group())
                  for start in range(0, len(part), MAX_BODY_EXCERPT)]
        excerpts.update({f"b{index}": text for index, text in enumerate(chunks, 1)})
        catalog[note_id] = excerpts
    return catalog


def build_report_sources(snapshot: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Index original titles and reversible body segments from one frozen snapshot."""
    source = snapshot.get("xhsCreatorProfile") if isinstance(snapshot, dict) else None
    return _catalog(source.get("notes") if isinstance(source, dict) else None, "desc")


def prepare_source_led_context(context: dict[str, Any]) -> dict[str, Any]:
    """Project v2 notes as content-only excerpts with short, request-local note IDs."""
    if not isinstance(context, dict):
        raise ValueError("账号报告上下文必须是对象")
    result = deepcopy(context)
    try:
        packet = json.loads(result.get("historicalPosts", ""))
    except (TypeError, ValueError):
        return result
    if not isinstance(packet, dict) or packet.get("schemaVersion") != "account-reading-input/v2":
        return result
    catalog = _catalog(packet.get("notes"), "body")
    notes = []
    for index, note in enumerate(packet["notes"], 1):
        if "bodyExcerpts" in note:
            raise ValueError("v2 笔记不能同时提供 bodyExcerpts")
        local_id = f"n{index}"
        if local_id in catalog and local_id != note["noteId"]:
            raise ValueError("本次局部 noteId 与稳定 ID 含义冲突，不能唯一映射")
        projected = {
            "noteId": local_id, "title": note.get("title", ""),
            "bodyExcerpts": [{"excerptId": key, "text": text}
                             for key, text in catalog[note["noteId"]].items() if key != "t"],
        }
        if "type" in note:
            if not isinstance(note["type"], str):
                raise ValueError("笔记 type 必须是文字")
            projected["type"] = note["type"]
        notes.append(projected)
    packet = {
        "schemaVersion": "account-reading-input/v3",
        "readingScope": {
            "selectedNoteCount": len(notes),
            "textScope": (
                "仅包含已保存的原标题和正文文字；片段按原文顺序保留全部已提供文字。"
                "未读取图片内文字或视频内容，不保证原始资料全文完整。"
            ),
        },
        "notes": notes,
    }
    result["historicalPosts"] = json.dumps(packet, ensure_ascii=False)
    return result


def resolve_editorial_refs(output: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    """Resolve v2/v3 ID pairs exactly, producing v1 for the existing strict compiler.

    Resolving a literal source does not verify an interpretation's semantic validity.
    Other report versions are returned as independent copies, without reading sources.
    """
    if not isinstance(output, dict):
        raise ValueError("账号报告输出必须是对象")
    result = deepcopy(output)
    profile = result.get("profile")
    if not isinstance(profile, dict) or profile.get("reportFormat") not in (
        "source-led/v2", "source-led/v3",
    ):
        return result
    version = profile["reportFormat"]
    # Known v2 model misnesting: relocate content before resolving local IDs or
    # excerpts. Legacy output and unknown root fields are never guessed at.
    fields = ("accountPortrait", "titleReadings", "nextMoves", *PROFILE_FIELDS)
    if version == "source-led/v3":
        fields += ("structureReading", "expressionReadings")
    for field in fields:
        if field not in result:
            continue
        if field in profile and json.dumps(profile[field], sort_keys=True) != json.dumps(
            result[field], sort_keys=True,
        ):
            raise ValueError(f"账号报告字段 {field} 在根层和 profile 中的内容冲突")
        profile[field] = result.pop(field)
    if version == "source-led/v3":
        structure = profile.get("structureReading")
        if isinstance(structure, dict) and "nextMoves" in structure:
            if "nextMoves" in profile and json.dumps(profile["nextMoves"], sort_keys=True) != (
                json.dumps(structure["nextMoves"], sort_keys=True)
            ):
                raise ValueError("账号报告 nextMoves 在 structureReading 和 profile 中的内容冲突")
            profile["nextMoves"] = structure.pop("nextMoves")
    result = normalize_profile_stage_result(result)
    profile = result["profile"]
    catalog = build_report_sources(snapshot)
    local_ids = {f"n{index}": note_id for index, note_id in enumerate(catalog, 1)}

    def stable_id(value):
        if not isinstance(value, str):
            raise ValueError("引用 noteId 必须是文字")
        candidates = ({value} if value in catalog else set()) | (
            {local_ids[value]} if value in local_ids else set()
        )
        if len(candidates) != 1:
            raise ValueError("引用 noteId 未知或存在局部 ID 歧义")
        return candidates.pop()

    def quote(note_id, excerpt_id):
        if (not isinstance(note_id, str) or not isinstance(excerpt_id, str)
                or note_id not in catalog or excerpt_id not in catalog[note_id]):
            raise ValueError("引用 noteId/excerptId 不在对应笔记的冻结目录中")
        text = catalog[note_id][excerpt_id]
        if not text.strip():
            raise ValueError("引用不能只包含空白文字")
        return text

    if version == "source-led/v3":
        portrait = profile.get("accountPortrait")
        if (isinstance(portrait, dict)
                and {"structureReading", "expressionReadings"} & portrait.keys()):
            raise ValueError("structureReading/expressionReadings 不能错嵌 accountPortrait")
        profile = result["profile"] = compile_report_patterns(profile, catalog, stable_id)

    def claims(value):
        if isinstance(value, list):
            for item in value:
                claims(item)
        elif isinstance(value, dict):
            for field, items in value.items():
                if field not in {"evidence", "counterexamples"}:
                    claims(items)
                    continue
                if not isinstance(items, list):
                    raise ValueError(f"{field} 必须是引用列表")
                resolved = []
                for ref in items:
                    if not isinstance(ref, dict) or set(ref) != {"noteId", "excerptId"}:
                        raise ValueError("v2 引用只允许 noteId 和 excerptId，不得混用 quote")
                    note_id = stable_id(ref["noteId"])
                    resolved.append({"noteId": note_id,
                                     "quote": quote(note_id, ref["excerptId"])})
                value[field] = resolved

    claims(profile.get("accountPortrait"))
    title_readings = profile.get("titleReadings", [])
    if (not isinstance(title_readings, list)
            or any(not isinstance(item, dict) for item in title_readings)):
        raise ValueError("titleReadings 必须是对象列表")
    for reading in title_readings:
        reading["noteId"] = stable_id(reading.get("noteId"))
        # The ordered source fragments/roles carry the reading. Do not amplify a
        # model-supplied umbrella label that may contradict their actual order.
        parts = reading.get("parts")
        whole_title = version == "source-led/v3" and isinstance(parts, list) and len(parts) == 1
        reading["move"] = "原标题解读" if whole_title else "原标题拆解"
    moves = profile.get("nextMoves", [])
    if not isinstance(moves, list) or any(not isinstance(move, dict) for move in moves):
        raise ValueError("nextMoves 必须是对象列表")
    for move in moves:
        if "sourceQuote" in move:
            raise ValueError("v2 nextMoves 不得同时提供 sourceQuote")
        move["sourceNoteId"] = stable_id(move.get("sourceNoteId"))
        move["sourceQuote"] = quote(move["sourceNoteId"], move.get("sourceExcerptId"))
        del move["sourceExcerptId"]
    profile["reportFormat"] = "source-led/v1"
    return result
