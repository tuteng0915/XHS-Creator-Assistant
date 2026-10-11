"""Compile v3 structural and expression readings using only frozen literal sources.

Order and quote checks do not establish the semantic accuracy of an interpretation.
"""

from collections.abc import Callable
from copy import deepcopy
from typing import Any


def _object(value: Any, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError(f"{label} 字段缺失、未知或类型错误")
    return value


def _text(value: Any, label: str, *, empty: bool = False) -> str:
    if not isinstance(value, str) or (not empty and not value.strip()):
        raise ValueError(f"{label} 必须是{'文字' if empty else '非空文字'}")
    return value


def _items(value: Any, minimum: int, maximum: int, label: str) -> list:
    if not isinstance(value, list) or not minimum <= len(value) <= maximum:
        raise ValueError(f"{label} 必须是 {minimum} 至 {maximum} 项的列表")
    return value


def _body(catalog: dict, note_id: str, excerpt_id: Any) -> tuple[int, str]:
    fragments = [(key, text) for key, text in catalog[note_id].items() if key != "t"]
    for position, (key, text) in enumerate(fragments):
        if excerpt_id == key:
            if not text.strip():
                raise ValueError("结构或表达引用不能只包含空白文字")
            return position, text
    raise ValueError("结构或表达只能引用对应笔记的正文 b 片段")


def _structure(reading: Any, catalog: dict, stable_id: Callable[[Any], str]) -> dict:
    if reading is None:
        return {"name": "", "steps": []}
    _object(reading, {"noteId", "kind", "scope", "scopeLabel", "overview", "units"},
            "structureReading")
    note_id = stable_id(reading["noteId"])
    kind, scope = reading["kind"], reading["scope"]
    if not isinstance(kind, str) or kind not in {"narrative", "comparison", "repeated_blocks"}:
        raise ValueError("structureReading.kind 无效")
    if not isinstance(scope, str) or scope not in {"whole_note", "section"}:
        raise ValueError("structureReading.scope 无效")
    scope_label = _text(reading["scopeLabel"], "scopeLabel", empty=scope == "whole_note")
    overview = _text(reading["overview"], "overview")
    available = sum(key != "t" and bool(text.strip()) for key, text in catalog[note_id].items())
    if not available:
        raise ValueError("结构观察需要可引用的非空正文片段")
    previous, steps = -1, []
    for unit in _items(reading["units"], 2, 5, "structureReading.units"):
        _object(unit, {"label", "excerptIds", "reading"}, "结构单元")
        label = _text(unit["label"], "单元 label")
        interpretation = _text(unit["reading"], "单元 reading")
        for excerpt_id in _items(unit["excerptIds"], 1, available, "单元 excerptIds"):
            _text(excerpt_id, "单元 excerptId")
            position, _ = _body(catalog, note_id, excerpt_id)
            if position <= previous:
                raise ValueError("结构单元的正文片段必须严格递增、不重复且互不交叉")
            previous = position
        steps.append(f"{label}：{interpretation}")
    return {"name": catalog[note_id].get("t", ""), "kind": kind, "scope": scope,
            "scopeLabel": scope_label, "overview": overview, "steps": steps}


def _expression_source(
    example: Any, catalog: dict, stable_id: Callable[[Any], str],
) -> tuple[str, int, int, str]:
    span = isinstance(example, dict) and bool({"fromExcerptId", "toExcerptId"} & example.keys())
    fields = ({"noteId", "fromExcerptId", "toExcerptId"} if span
              else {"noteId", "excerptId", "quote"})
    _object(example, fields, "表达例证")
    note_id = stable_id(example["noteId"])
    if not span:
        position, original = _body(catalog, note_id, _text(example["excerptId"], "表达 excerptId"))
        quote = _text(example["quote"], "表达 quote")
        if len(quote) > 100 or quote not in original:
            raise ValueError("表达 quote 必须是对应正文片段内不超过100字的连续原文")
        return note_id, position, position, quote
    first, _ = _body(catalog, note_id, _text(example["fromExcerptId"], "表达 fromExcerptId"))
    last, _ = _body(catalog, note_id, _text(example["toExcerptId"], "表达 toExcerptId"))
    if not first <= last < first + 6:
        raise ValueError("表达引用范围必须正序且不超过6个正文片段")
    fragments = [text for key, text in catalog[note_id].items() if key != "t"]
    # Interior blank fragments are original layout, not missing evidence. Keep
    # every character and count them in both budgets; only endpoints must be text.
    quote = "".join(fragments[first:last + 1])
    if len(quote) > 600:
        raise ValueError("表达引用范围的连续原文不能超过600字")
    return note_id, first, last, quote


def _expressions(
    readings: Any, catalog: dict, stable_id: Callable[[Any], str],
) -> tuple[list, list]:
    hooks, voices = [], []
    for reading in _items(readings, 0, 3, "expressionReadings"):
        _object(reading, {"kind", "technique", "application", "examples"}, "expressionReading")
        kind = reading["kind"]
        if not isinstance(kind, str) or kind not in {
            "opening", "wording", "rhythm", "address", "transition",
        }:
            raise ValueError("expressionReading.kind 无效")
        technique = _text(reading["technique"], "technique")
        application = _text(reading["application"], "application")
        sources, seen, quotes = {}, set(), []
        for example in _items(reading["examples"], 1, 3, "expressionReading.examples"):
            note_id, first, last, quote = _expression_source(example, catalog, stable_id)
            positions = {(note_id, index) for index in range(first, last + 1)}
            if seen & positions:
                raise ValueError("同条表达观察不能重复引用或重叠引用同一笔记的片段")
            seen.update(positions)
            sources[note_id] = catalog[note_id].get("t", "")
            quotes.append((sources[note_id], quote))
        titles = "".join(f"《{title}》" for title in sources.values())
        lead = titles + ("的写法" if len(sources) == 1 else "中都能看到的写法")
        excerpts = "；".join(f"“{quote}”" if len(sources) == 1 else f"《{title}》中的“{quote}”"
                            for title, quote in quotes)
        ending = "" if technique.rstrip().endswith(("。", "！", "？", ".", "!", "?", "…")) else "。"
        text = f"{lead}：{technique}{ending}原句：{excerpts}。借鉴方式：{application}"
        (hooks if kind == "opening" else voices).append(text)
    return hooks, voices


def compile_report_patterns(profile: dict, catalog: dict, stable_id: Callable[[Any], str]) -> dict:
    """Return a compiled copy; reject v3 dual writes instead of overriding old content."""
    result = deepcopy(profile)
    for field in ("hookStyles", "voiceFingerprint"):
        value = result.get(field, [])
        if not isinstance(value, list):
            raise ValueError(f"{field} 必须是列表")
        if value:
            raise ValueError(f"source-led/v3 与非空旧 {field} 冲突")
    old = result.get("viralStructure", {})
    if (not isinstance(old, dict) or not isinstance(old.get("name", ""), str)
            or not isinstance(old.get("steps", []), list)):
        raise ValueError("viralStructure 类型错误")
    if set(old) - {"name", "steps"} or old.get("name") or old.get("steps"):
        raise ValueError("source-led/v3 与非空旧 viralStructure 冲突")
    result["viralStructure"] = _structure(result.get("structureReading"), catalog, stable_id)
    result["hookStyles"], result["voiceFingerprint"] = _expressions(
        result.get("expressionReadings", []), catalog, stable_id,
    )
    result.pop("structureReading", None)
    result.pop("expressionReadings", None)
    return result
