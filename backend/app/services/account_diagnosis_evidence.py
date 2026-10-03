"""Deterministic, snapshot-local facts for an XHS account diagnosis."""

from __future__ import annotations

import json
import re
from datetime import UTC
from statistics import median
from typing import Any

from app.services.creator_analysis_scope import note_published_at

METRIC_KEYS = ("liked", "collected", "comments", "shares")
RECENT_CHANGE_PERFORMANCE_TERMS = re.compile(
    r"点赞|收藏|评论量|分享量|曝光|点击|流量|爆款|转化|涨粉|推荐量|算法|增长|下滑|下降|变好|变差"
)


def profile_stage_input(snapshot: dict[str, Any], snapshot_at: str) -> tuple[dict, dict | None]:
    """The exact profile model input, shared with the read-only check script."""
    observations = build_account_observations(snapshot, snapshot_at)
    historical_posts = str(snapshot["historicalPosts"]["content"])
    chronology = (observations or {}).get("chronology", {})
    if chronology.get("status") == "comparable":
        historical_posts += (
            "\n\n可比较的前后发布时间组（只比较内容方向，不比较累计互动）：\n"
            + json.dumps(chronology, ensure_ascii=False)
        )
    return {"positioning": str(snapshot["accountPositioning"]),
            "historicalPosts": historical_posts}, observations


def _nonnegative_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


def build_chronology(notes: list[dict[str, Any]]) -> dict[str, Any]:
    """Find two sufficiently populated publication periods, without comparing performance."""
    dated = sorted(
        (date, str(note.get("noteId")))
        for note in notes
        if note.get("noteId") and (date := note_published_at(note)) is not None
    )
    if len(dated) < 6:
        return {"status": "insufficient_data", "reason": "有发布时间的笔记少于 6 条"}
    if len({note_id for _, note_id in dated}) != len(dated):
        return {"status": "insufficient_data", "reason": "笔记 ID 重复，无法可靠比较前后时期"}
    if (dated[-1][0] - dated[0][0]).days < 30:
        return {"status": "insufficient_data", "reason": "所选笔记的发布时间跨度不足 30 天"}
    possible_splits = [
        index
        for index in range(3, len(dated) - 2)
        if dated[index - 1][0].date() < dated[index][0].date()
    ]
    if not possible_splits:
        return {"status": "insufficient_data", "reason": "无法分出各至少 3 条的前后时期"}
    split = min(possible_splits, key=lambda index: abs(index - len(dated) / 2))

    def period(items: list[tuple[Any, str]]) -> dict[str, Any]:
        return {
            "noteIds": [note_id for _, note_id in items],
            "start": items[0][0].astimezone(UTC).date().isoformat(),
            "end": items[-1][0].astimezone(UTC).date().isoformat(),
        }

    return {
        "status": "comparable",
        "earlier": period(dated[:split]),
        "later": period(dated[split:]),
    }


def build_account_observations(snapshot: dict[str, Any], snapshot_at: str) -> dict[str, Any] | None:
    """Build facts from the already-selected notes, never the current mutable asset."""
    source = snapshot.get("xhsCreatorProfile")
    if not isinstance(source, dict) or not isinstance(source.get("notes"), list):
        return None

    notes = [note for note in source["notes"] if isinstance(note, dict)]
    dated = [date for note in notes if (date := note_published_at(note)) is not None]
    missing_metrics = {key: 0 for key in METRIC_KEYS}
    observations: list[dict[str, Any]] = []
    for note in notes:
        raw_metrics = note.get("metrics") if isinstance(note.get("metrics"), dict) else {}
        metrics = {key: _nonnegative_int(raw_metrics.get(key)) for key in METRIC_KEYS}
        for key, value in metrics.items():
            if value is None:
                missing_metrics[key] += 1
        published_at = note_published_at(note)
        observations.append(
            {
                "noteId": str(note.get("noteId") or ""),
                "title": str(note.get("title") or "未命名笔记"),
                "publishedAt": published_at.astimezone(UTC).isoformat() if published_at else None,
                "type": str(note.get("type") or "normal"),
                "metrics": metrics,
                "capturedCommentCount": len(note.get("comments"))
                if isinstance(note.get("comments"), list)
                else 0,
            }
        )

    metric_summaries = []
    for key in METRIC_KEYS:
        values = [item["metrics"][key] for item in observations if item["metrics"][key] is not None]
        ranks = {value: index + 1 for index, value in enumerate(sorted(set(values), reverse=True))}
        metric_summaries.append({
            "metric": key,
            "validCount": len(values),
            "missingCount": len(observations) - len(values),
            "median": median(values) if values else None,
            "rankMethod": "dense_descending",
        })
        for observation in observations:
            observation.setdefault("metricRanksInSelection", {})[key] = ranks.get(
                observation["metrics"][key]
            )

    for observation in observations:
        # Keep the original field for existing renderers and history readers.
        observation["likesRankInSelection"] = observation["metricRanksInSelection"]["liked"]

    source_metadata = source.get("source") if isinstance(source.get("source"), dict) else {}
    range_metadata = (
        snapshot.get("analysisRange") if isinstance(snapshot.get("analysisRange"), dict) else {}
    )
    return {
        "schemaVersion": "xhs-account-observations/v1",
        "coverage": {
            "selectedNoteIds": [item["noteId"] for item in observations],
            "selectedCount": len(observations),
            "availableCount": range_metadata.get("availableNoteCount", len(observations)),
            "snapshotAt": snapshot_at,
            "sourceFetchedAt": source_metadata.get("importedAt"),
            "dateRange": {
                "earliest": min(dated).astimezone(UTC).isoformat(),
                "latest": max(dated).astimezone(UTC).isoformat(),
            }
            if dated
            else None,
            "missingDateCount": len(notes) - len(dated),
            "missingMetricCounts": missing_metrics,
            "capturedCommentCount": sum(item["capturedCommentCount"] for item in observations),
        },
        "chronology": build_chronology(notes),
        "metricSummaries": metric_summaries,
        "notes": observations,
    }


def verified_portrait(
    portrait: dict[str, Any] | None,
    snapshot: dict[str, Any],
    chronology: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Keep only claims whose quotes occur in selected, correctly identified notes."""
    if not portrait or not isinstance(portrait, dict):
        return None
    source = snapshot.get("xhsCreatorProfile")
    if not isinstance(source, dict):
        return None
    identified = [
        str(note.get("noteId"))
        for note in source.get("notes", [])
        if isinstance(note, dict) and note.get("noteId")
    ]
    if len(identified) != len(set(identified)):
        return None
    notes = {
        str(note.get("noteId")): note
        for note in source.get("notes", [])
        if isinstance(note, dict) and note.get("noteId")
    }

    def verified_refs(value: Any, limit: int = 3) -> list[dict[str, str]]:
        if not isinstance(value, list):
            return []
        verified = []
        seen = set()
        for ref in value:
            if not isinstance(ref, dict):
                continue
            note_id = ref.get("noteId")
            quote = ref.get("quote")
            note = notes.get(note_id) if isinstance(note_id, str) else None
            if (
                note is not None
                and isinstance(quote, str)
                and 0 < len(quote.strip()) <= 240
                and quote in f"{note.get('title') or ''}\n{note.get('desc') or ''}"
                and (note_id, quote) not in seen
            ):
                verified.append({"noteId": note_id, "quote": quote})
                seen.add((note_id, quote))
                if len(verified) >= limit:
                    break
        return verified

    def verified_claim(value: Any) -> dict[str, Any] | None:
        if not isinstance(value, dict):
            return None
        statement = value.get("statement")
        if not isinstance(statement, str) or not 0 < len(statement.strip()) <= 200:
            return None
        evidence = verified_refs(value.get("evidence"))
        if not evidence:
            return None
        supporting_ids = {item["noteId"] for item in evidence}
        counterexamples = [
            item
            for item in verified_refs(value.get("counterexamples"), limit=2)
            if item["noteId"] not in supporting_ids
        ]
        return {
            "statement": statement.strip(),
            "evidence": evidence,
            "counterexamples": counterexamples,
        }

    summary = verified_claim(portrait.get("summary"))
    keywords = []
    seen_keywords: set[str] = set()
    keyword_values = portrait.get("keywords")
    for value in keyword_values[:20] if isinstance(keyword_values, list) else []:
        claim = verified_claim(value)
        if claim and len(claim["statement"]) <= 12 and claim["statement"] not in seen_keywords:
            keywords.append(claim)
            seen_keywords.add(claim["statement"])
        if len(keywords) >= 6:
            break
    strengths = (
        [claim for value in portrait["strengths"][:12] if (claim := verified_claim(value))][:3]
        if isinstance(portrait.get("strengths"), list)
        else []
    )
    encouragement = verified_claim(portrait.get("encouragement"))
    sections = {}
    for key in ("recurringThemes", "readerValue", "expressionPatterns"):
        values = portrait.get(key)
        limit = 4 if key == "recurringThemes" else 3
        claims = (
            [claim for value in values[:20] if (claim := verified_claim(value))]
            if isinstance(values, list)
            else []
        )
        if key == "recurringThemes":
            # A single cited note is an example, not a recurring account direction.
            claims = [
                claim
                for claim in claims
                if len({ref["noteId"] for ref in claim["evidence"]}) >= 2
            ]
        sections[key] = claims[:limit]
    recent_change = verified_claim(portrait.get("recentChange"))
    if recent_change:
        earlier_ids = set((chronology or {}).get("earlier", {}).get("noteIds", []))
        later_ids = set((chronology or {}).get("later", {}).get("noteIds", []))
        cited_ids = {item["noteId"] for item in recent_change["evidence"]}
        if (
            (chronology or {}).get("status") != "comparable"
            or not cited_ids.intersection(earlier_ids)
            or not cited_ids.intersection(later_ids)
            or RECENT_CHANGE_PERFORMANCE_TERMS.search(recent_change["statement"])
        ):
            recent_change = None
    if not any(
        (summary, any(sections.values()), recent_change, keywords, strengths, encouragement)
    ):
        return None
    result = {"summary": summary, **sections, "recentChange": recent_change}
    if "keywords" in portrait:
        result["keywords"] = keywords
    if "strengths" in portrait:
        result["strengths"] = strengths
    if "encouragement" in portrait:
        result["encouragement"] = encouragement
    return result
