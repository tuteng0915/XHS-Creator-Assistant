"""Deliver useful new reports without making optional sections all-or-nothing.

The existing compiler remains the authority for source IDs, literal quotes and
reading shapes. This adapter only isolates new v3 sections; historical and already
compiled reports continue through the unchanged legacy path.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.services.account_diagnosis_evidence import build_chronology, verified_portrait
from app.services.account_profile_shape import normalize_profile_stage_result
from app.services.account_report_editorial import compile_editorial_profile

_PORTRAIT_LISTS = ("keywords", "recurringThemes", "strengths")
_READING_FIELDS = {
    "titleReadings": {"noteId", "parts"},
    "expressionReadings": {"kind", "technique", "application", "examples"},
    "structureReading": {"noteId", "kind", "scope", "scopeLabel", "overview", "units"},
    "nextMoves": {"sourceNoteId", "sourceExcerptId", "sourceQuote", "basis", "action"},
}


def _omit(omissions: list[str], path: str) -> None:
    # Only controlled field paths and this fixed code enter diagnostics.
    omissions.append(f"{path}:invalid")


def _packet(field: str | None = None, value: Any = None) -> dict[str, Any]:
    profile = {"reportFormat": "source-led/v3"}
    if field is not None:
        profile[field] = value
    return {"profile": profile}


def _source_led_without_version(profile: dict) -> bool:
    """Recognize current source-reading fields, not a guessed source identity."""
    if {"expressionReadings", "structureReading"} & profile.keys():
        return True
    moves = profile.get("nextMoves")
    if isinstance(moves, list) and any(
        isinstance(item, dict) and "sourceExcerptId" in item for item in moves
    ):
        return True
    portrait = profile.get("accountPortrait")
    if not isinstance(portrait, dict):
        return False
    claims = [portrait.get("summary")]
    for field in _PORTRAIT_LISTS:
        if isinstance(portrait.get(field), list):
            claims.extend(portrait[field])
    return any(
        isinstance(claim, dict) and isinstance(claim.get("evidence"), list)
        and any(isinstance(ref, dict) and "excerptId" in ref for ref in claim["evidence"])
        for claim in claims
    )


def _has_legacy_content(output: dict, snapshot: dict) -> bool:
    """Check new legacy-shaped output after the existing display normalization.

    This is only a generation boundary check. It neither rewrites old saved data
    nor invents source requirements for legacy title/voice/structure text.
    """
    profile = normalize_profile_stage_result(output)["profile"]

    def text(value: Any) -> bool:
        return isinstance(value, str) and bool(value.strip())

    def texts(value: Any) -> bool:
        return isinstance(value, list) and any(text(item) for item in value)

    source = snapshot.get("xhsCreatorProfile")
    notes = source.get("notes") if isinstance(source, dict) else None
    chronology = build_chronology(notes) if isinstance(notes, list) else None
    portrait = verified_portrait(profile.get("accountPortrait"), snapshot, chronology) or {}
    if any(portrait.get(field) for field in (
        "summary", "strengths", "recurringThemes", "readerValue", "expressionPatterns",
        "recentChange", "nextSteps", "encouragement",
    )):
        return True
    if any(texts(profile.get(field)) for field in ("pillars", "hookStyles", "voiceFingerprint")):
        return True
    formulas = profile.get("titleFormulas")
    if isinstance(formulas, list) and any(
        isinstance(item, dict) and (text(item.get("formula")) or texts(item.get("examples")))
        for item in formulas
    ):
        return True
    structure = profile.get("viralStructure")
    if isinstance(structure, dict) and any((
        text(structure.get("name")), text(structure.get("overview")), texts(structure.get("steps")),
    )):
        return True
    contrast = profile.get("contrast")
    if not isinstance(contrast, dict):
        return False
    if any(texts(contrast.get(field)) for field in ("takeaways", "winFactors", "loseFactors")):
        return True
    return any(
        isinstance(contrast.get(field), list) and any(
            isinstance(item, dict) and text(item.get("title")) for item in contrast[field]
        ) for field in ("winners", "losers")
    )


def _references(value: Any, snapshot: dict, path: str, omissions: list[str]) -> list[dict]:
    if not isinstance(value, list):
        _omit(omissions, path)
        return []
    resolved = []
    for index, reference in enumerate(value):
        # Resolve each original reference through the established compiler. Do not
        # strip unknown reference keys: contradictory quote/ID dual writes remain bad.
        claim = {"statement": "引用核验", "evidence": [reference]}
        try:
            compiled = compile_editorial_profile(
                _packet("accountPortrait", {"summary": claim}), snapshot,
            )
            checked = verified_portrait(compiled["profile"]["accountPortrait"], snapshot)
        except ValueError:
            checked = None
        if not checked or not checked.get("summary"):
            _omit(omissions, f"{path}[{index}]")
            continue
        resolved.extend(checked["summary"]["evidence"])
    return resolved


def _claim(value: Any, field: str, snapshot: dict, path: str, omissions: list[str]) -> dict | None:
    if not isinstance(value, dict):
        _omit(omissions, path)
        return None
    statement = value.get("statement")
    if not isinstance(statement, str) or not statement.strip():
        _omit(omissions, path)
        return None
    claim = {
        "statement": statement,
        "evidence": _references(value.get("evidence"), snapshot, f"{path}.evidence", omissions),
    }
    if "counterexamples" in value:
        claim["counterexamples"] = _references(
            value["counterexamples"], snapshot, f"{path}.counterexamples", omissions,
        )
    portrait = {field: [claim] if field in _PORTRAIT_LISTS else claim}
    checked = verified_portrait(portrait, snapshot)
    result = checked.get(field) if checked else None
    if field in _PORTRAIT_LISTS:
        result = result[0] if result else None
    if not result:
        _omit(omissions, path)
    return result


def _reading(value: Any, field: str) -> Any:
    """Ignore extra display annotations without rewriting sources or prose."""
    if not isinstance(value, dict):
        return deepcopy(value)
    reading = {key: deepcopy(item) for key, item in value.items() if key in _READING_FIELDS[field]}
    if field == "structureReading" and reading.get("scope") == "whole_note":
        reading.setdefault("scopeLabel", "")
    nested = {
        "titleReadings": ("parts", {"text", "role"}),
        "structureReading": ("units", {"excerptIds", "label", "reading"}),
    }.get(field)
    if nested and isinstance(reading.get(nested[0]), list):
        key, fields = nested
        reading[key] = [
            {name: child for name, child in item.items() if name in fields}
            if isinstance(item, dict) else item for item in reading[key]
        ]
    # Expression example fields describe provenance, not presentation. Keep them
    # intact so wrong IDs, mixed source formats and guessed quotes cannot disappear.
    return reading


def compile_usable_account_report(
    output: dict[str, Any], snapshot: dict[str, Any], *, omissions: list[str] | None = None,
) -> dict[str, Any]:
    """Compile a new v3 report locally; omit bad optional items, never invent them.

    A new v3 report still needs analysis with at least one verified real source.
    Missing optional keys are ordinary empty sections and are not diagnostics.
    Only known compiler validation errors are isolated; programming failures escape.
    """
    profile = output.get("profile") if isinstance(output, dict) else None
    if not isinstance(profile, dict):
        raise ValueError("账号报告输出必须包含 profile 对象")
    if "reportFormat" not in profile and _source_led_without_version(profile):
        output = deepcopy(output)
        profile = output["profile"]
        profile["reportFormat"] = "source-led/v3"
    if profile.get("reportFormat") != "source-led/v3":
        compiled = compile_editorial_profile(output, snapshot)
        if not _has_legacy_content(compiled, snapshot):
            raise ValueError("账号报告尚无可用的分析内容")
        return compiled
    skipped = omissions if omissions is not None else []
    conflicts: set[str] = set()

    def located(field: str, default: Any = None) -> Any:
        if field in profile and field in output and profile[field] != output[field]:
            if field not in conflicts:
                skipped.append(f"{field}:conflict")
                conflicts.add(field)
            return default
        return profile.get(field, output.get(field, default))

    # Validate the frozen catalog once before isolating optional generated content.
    result = compile_editorial_profile(_packet(), snapshot)
    portrait = located("accountPortrait")
    if not isinstance(portrait, dict):
        if portrait is not None:
            _omit(skipped, "accountPortrait")
        portrait = {}
    else:
        portrait = deepcopy(portrait)
    for field in ("summary", *_PORTRAIT_LISTS):
        if field not in portrait and field in profile:
            portrait[field] = deepcopy(profile[field])
    # Keep the default path's observed flattened-summary compatibility. Restrict
    # normalization to this one claim so unrelated malformed optional fields do
    # not recreate an all-or-nothing report gate.
    if isinstance(portrait.get("summary"), str) and isinstance(portrait.get("evidence"), list):
        summary_fields = {key: portrait[key] for key in ("summary", "evidence", "counterexamples")
                          if key in portrait}
        portrait["summary"] = normalize_profile_stage_result(
            _packet("accountPortrait", summary_fields),
        )["profile"]["accountPortrait"]["summary"]
    summary = (_claim(portrait["summary"], "summary", snapshot,
                      "accountPortrait.summary", skipped)
               if portrait.get("summary") is not None else None)
    compiled_portrait = {"summary": summary}
    for field in _PORTRAIT_LISTS:
        values = portrait.get(field, [])
        if not isinstance(values, list):
            _omit(skipped, f"accountPortrait.{field}")
            values = []
        compiled_portrait[field] = [
            claim for index, value in enumerate(values)
            if (claim := _claim(
                value, field, snapshot, f"accountPortrait.{field}[{index}]", skipped,
            ))
        ]
    # Apply the same portrait normalization as the established delivery path,
    # including keyword deduplication and bounded presentation lists.
    result["profile"]["accountPortrait"] = verified_portrait(compiled_portrait, snapshot)
    structure = located("structureReading")
    moves = located("nextMoves", [])
    if isinstance(structure, dict) and "nextMoves" in structure and "nextMoves" not in conflicts:
        if "nextMoves" not in profile and "nextMoves" not in output:
            moves = structure["nextMoves"]
        elif moves != structure["nextMoves"]:
            # Preserve the established nesting repair, but a contradictory copy
            # does not identify which suggestion was intended. Omit only these
            # suggestions; the structure and other valid sections remain usable.
            skipped.append("nextMoves:conflict")
            moves = []
    for field in ("titleReadings", "expressionReadings", "nextMoves"):
        values = moves if field == "nextMoves" else located(field, [])
        if not isinstance(values, list):
            _omit(skipped, field)
            continue
        for index, value in enumerate(values):
            try:
                compiled = compile_editorial_profile(
                    _packet(field, [_reading(value, field)]), snapshot,
                )["profile"]
            except ValueError:
                _omit(skipped, f"{field}[{index}]")
                continue
            if field == "titleReadings":
                result["profile"]["titleFormulas"].extend(compiled["titleFormulas"])
            elif field == "expressionReadings":
                for destination in ("hookStyles", "voiceFingerprint"):
                    result["profile"][destination].extend(compiled[destination])
            else:
                result["profile"]["contrast"]["takeaways"].extend(compiled["contrast"]["takeaways"])
    if structure is not None:
        try:
            result["profile"]["viralStructure"] = compile_editorial_profile(
                _packet("structureReading", _reading(structure, "structureReading")), snapshot,
            )["profile"]["viralStructure"]
        except ValueError:
            _omit(skipped, "structureReading")
    delivered = result["profile"]
    delivered_portrait = delivered.get("accountPortrait") or {}
    if not any((
        delivered_portrait.get("summary"), delivered_portrait.get("strengths"),
        delivered_portrait.get("recurringThemes"), delivered["titleFormulas"],
        delivered["hookStyles"], delivered["voiceFingerprint"],
        delivered["viralStructure"].get("steps"), delivered["contrast"]["takeaways"],
    )):
        raise ValueError("账号报告尚无带原文来源的有效分析")
    return result
