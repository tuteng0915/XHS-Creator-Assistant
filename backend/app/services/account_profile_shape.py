"""Repair only known profile/portrait nesting mistakes, never the claim text.

Model output stays untouched for diagnostics. Evidence is merely relocated with
its claim; source/quote verification still runs after normal schema validation.
"""

from copy import deepcopy
from typing import Any

PORTRAIT_FIELDS = (
    "summary", "keywords", "strengths", "encouragement", "recurringThemes",
    "readerValue", "expressionPatterns", "recentChange",
)
PROFILE_FIELDS = (
    "pillars", "titleFormulas", "hookStyles", "viralStructure", "voiceFingerprint", "contrast",
)


def _relocate(source: dict, destination: dict, key: str) -> None:
    if key not in source:
        return
    if key in destination and destination[key] != source[key]:
        raise ValueError(f"账号报告字段 {key} 的两处内容冲突，请检查原始输出")
    if key not in destination:
        destination[key] = source[key]
    del source[key]


def normalize_profile_stage_result(value: Any) -> Any:
    """Canonical values win only when an accidental duplicate is identical."""
    normalized = deepcopy(value)
    if not isinstance(normalized, dict) or not isinstance(normalized.get("profile"), dict):
        return normalized
    profile = normalized["profile"]
    misplaced_portrait_fields = any(key in profile for key in PORTRAIT_FIELDS)
    if "accountPortrait" not in profile and misplaced_portrait_fields:
        profile["accountPortrait"] = {}
    portrait = profile.get("accountPortrait")
    if not isinstance(portrait, dict):
        if misplaced_portrait_fields:
            raise ValueError("账号报告 accountPortrait 与同层画像字段冲突，请检查原始输出")
        return normalized
    for key in PORTRAIT_FIELDS:
        _relocate(profile, portrait, key)
    for key in PROFILE_FIELDS:
        _relocate(portrait, profile, key)
    # This exact flattened claim shape was observed in a real response. A
    # missing/invalid evidence list is not an invitation to invent one.
    if isinstance(portrait.get("summary"), str) and isinstance(portrait.get("evidence"), list):
        portrait["summary"] = {
            "statement": portrait["summary"],
            "evidence": portrait.pop("evidence"),
            "counterexamples": portrait.pop("counterexamples", []),
        }
    return normalized
