"""The text a simulated reader can see; excludes the author's internal strategy."""
from copy import deepcopy
from typing import Any


def reader_visible_texts(target: dict[str, Any]) -> list[str]:
    """Text fragments of an already normalized target, without preview metadata.

    Keep fragments separate: joining fields must not make a fabricated quote valid.
    Historical episodes and persona descriptions are never part of this target.
    """
    def strings(value: Any):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from strings(item)
        elif isinstance(value, list):
            for item in value:
                yield from strings(item)

    return list(strings([target.get("title", ""), target.get("body", ""), target.get("draft", {})]))


def reader_visible_target(snapshot: dict[str, Any]) -> dict[str, Any]:
    topic = snapshot["topic"]
    target = {
        "targetType": snapshot.get("targetType", "topic"),
        "title": topic.get("title", ""),
        "body": topic.get("body", ""),
        "previewLevel": "text_draft" if topic.get("body") else "concept",
        "limitations": "仅预演提供的文字，不评价未提供的图片或真实传播效果。",
    }
    if snapshot.get("targetType") == "account":
        scope = deepcopy((snapshot.get("sourceAccount") or {}).get("scope", {}))
        if scope.get("selectionMethod") == "explicit_ids":
            # Account-wide inventory counts belong in the frozen display snapshot,
            # not the selected reading target or its recommendation freshness hash.
            scope = {key: scope[key] for key in (
                "sourceMaterialId", "selectedNoteIds", "selectedNoteCount",
                "sampledNoteCount", "truncatedNoteCount", "selectionMethod",
                "samplingMethod", "omissionNotice",
            ) if key in scope}
        target.update({
            "simulationCategory": "account", "previewLevel": "account",
            "accountScope": scope,
            "limitations": "基于本次账号简介和笔记文字样本，讨论长期阅读期待与内容方向。",
        })
        return deepcopy(target)
    draft = snapshot.get("draft")
    if draft:
        editable = draft.get("editableContent", {})
        structure = editable.get("structure") or {}
        brief = editable.get("brief") or {}
        visible = {}
        if isinstance(structure, dict) and structure:
            visible["structure"] = {
                "topicChosen": structure.get("topicChosen", ""),
                "outline": [
                    {"sec": str(section.get("sec", "")), "ct": str(section.get("ct", ""))}
                    for section in structure.get("outline", []) if isinstance(section, dict)
                ],
            }
        if isinstance(brief, dict) and brief:
            visible["brief"] = {
                key: brief[key] for key in ("corePoint", "openingHook", "argumentPath", "cta")
                if key in brief
            }
        target["draft"] = {"editableContent": visible}
        target["previewLevel"] = "outline"
    return deepcopy(target)
