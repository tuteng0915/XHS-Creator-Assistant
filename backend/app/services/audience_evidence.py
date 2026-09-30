"""Bounded, traceable evidence for audience research (never population estimates)."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.models import APIModel

AUDIENCE_METHOD_VERSION = "audience_methods_v2"


class ObservedEpisode(APIModel):
    """A real stimulus/response pair, never a generated teaching example."""

    note_id: str
    comment_id: str
    note_title: str
    note_excerpt: str
    observed_comment: str
    evidence_quote: str
    context_limit: str = "正文为截取片段；评论具体触发位置未知，不代表完整阅读行为。"


def observed_episodes(refs: list[AudienceEvidence], context: dict) -> list[dict]:
    """Materialize validated pairs with cross-note coverage, bounded to six."""
    validate_evidence(refs, context)
    by_note: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    for ref in refs:
        if ref.source_type != "comment" or ref.comment_id is None:
            continue
        key = (ref.note_id, ref.comment_id)
        if key in seen:
            continue
        seen.add(key)
        note = next(n for n in context["notes"] if n["noteId"] == ref.note_id)
        comment = next(c for c in note["comments"] if c["commentId"] == ref.comment_id)
        by_note.setdefault(ref.note_id, []).append(ObservedEpisode(
            note_id=ref.note_id, comment_id=ref.comment_id,
            note_title=note["title"], note_excerpt=note["content"][:1000],
            observed_comment=comment["content"], evidence_quote=ref.quote,
        ).model_dump(by_alias=True))
    # Round-robin prevents one heavily cited note from consuming the whole budget.
    result = []
    while by_note and len(result) < 6:
        for note_id in list(by_note):
            result.append(by_note[note_id].pop(0))
            if not by_note[note_id]:
                del by_note[note_id]
            if len(result) == 6:
                break
    return result


def reader_persona_context(persona: dict, topic: dict) -> dict:
    """Select up to four saved episodes; no extra source lookup or new facts."""
    def terms(text: str) -> set[str]:
        compact = "".join(text.lower().split())
        return {compact[i:i + 2] for i in range(len(compact) - 1)}

    query = terms(str(topic.get("title", "")) + str(topic.get("body", "")))
    episodes = list(persona.get("observedEpisodes", []))
    episodes.sort(key=lambda e: len(query & terms(
        e["noteTitle"] + e["noteExcerpt"] + e["observedComment"]
    )), reverse=True)
    selected, remaining, seen_notes = [], [], set()
    for episode in episodes:
        if episode["noteId"] not in seen_notes:
            selected.append(episode)
            seen_notes.add(episode["noteId"])
        else:
            remaining.append(episode)
    return {**persona, "observedEpisodes": (selected + remaining)[:4]}


def public_reactions(reactions: list[dict]) -> list[dict]:
    return [
        {"messageId": f"initial:{r['personaId']}", "personaId": r["personaId"],
         "quote": r.get("quote") or r.get("text", ""), "round": 1}
        for r in reactions
        if r.get("action", "comment") == "comment"
        and str(r.get("quote") or r.get("text", "")).strip()
    ]


def discussion_skipped(reactions: list[dict], method: str | None) -> bool:
    public = public_reactions(reactions)
    if method != AUDIENCE_METHOD_VERSION:
        return len(public) < 2  # Preserve old history semantics.
    return not any(r["personaId"] != p["personaId"] for r in reactions for p in public)


DISCUSSION_SKIPPED_REASON = "没有可供其他读者回应的公开评论，跳过交流。"


class AudienceEvidence(APIModel):
    note_id: str = Field(min_length=1)
    comment_id: str | None = None
    source_type: Literal["comment", "note"]
    quote: str = Field(min_length=1)


def audience_context(snapshot: dict) -> dict:
    notes = snapshot["notes"]
    selected = []
    for i, note in enumerate(notes[:100]):
        selected.append({
            "noteId": str(note.get("noteId") or f"snapshot-note-{i}"),
            "title": str(note.get("title") or "")[:1000],
            "content": str(note.get("desc") or "")[:4000],
            "comments": [
                {
                    "commentId": str(c.get("commentId") or f"snapshot-comment-{j}"),
                    "content": str(c.get("content") or "")[:1000],
                    "createTime": c.get("createTime"),
                }
                for j, c in enumerate(note.get("comments", [])[:50])
            ],
        })
    return {
        # Do not leak an all-history summary into a scoped analysis.
        "creator": {"displayName": snapshot.get("creator", {}).get("displayName", "")},
        "scope": snapshot.get("scope", {}),
        "notes": selected,
        "sampling": {
            "availableNotes": len(notes),
            "sentNotes": len(selected),
            "availableComments": sum(len(n.get("comments", [])) for n in notes),
            "sentComments": sum(len(n["comments"]) for n in selected),
            "maxCommentsPerNote": 50,
            "selection": "笔记范围内按已保存顺序截取；非随机抽样，不代表粉丝人数",
            "timeBasis": "笔记发布时间；评论为这些笔记下已采集的评论",
        },
    }


def evidence_issues(refs: list[AudienceEvidence], context: dict) -> list[dict]:
    """Explain failed references without accepting paraphrases or guessing sources."""
    if not refs:
        return [{"code": "missing_evidence", "message": "缺少可核验的原文引用"}]
    sources: dict[tuple, list[str]] = {}
    occurrences: dict[tuple, int] = {}
    for note in context["notes"]:
        note_key = (note["noteId"], None, "note")
        occurrences[note_key] = occurrences.get(note_key, 0) + 1
        sources.setdefault((note["noteId"], None, "note"), []).extend(
            [note["title"], note["content"]]
        )
        for comment in note["comments"]:
            comment_key = (note["noteId"], comment["commentId"], "comment")
            occurrences[comment_key] = occurrences.get(comment_key, 0) + 1
            sources.setdefault((note["noteId"], comment["commentId"], "comment"), []).append(
                comment["content"]
            )
    issues = []
    for index, ref in enumerate(refs):
        key = (ref.note_id, ref.comment_id, ref.source_type)
        candidates = sources.get(key, [])
        ambiguous = (occurrences.get(key, 0) > 1
                     or occurrences.get((ref.note_id, None, "note"), 0) > 1)
        if ambiguous or not ref.quote.strip() or not any(ref.quote in text for text in candidates):
            issues.append({
                "referenceIndex": index,
                "code": "ambiguous_source" if ambiguous
                else "source_not_found" if not candidates else "quote_not_exact",
                "message": "引用来源 ID 重复，无法唯一定位" if ambiguous
                else "引用来源 ID 不匹配" if not candidates else "引文不是来源中的连续原文",
                "reference": ref.model_dump(mode="json", by_alias=True),
            })
    return issues


def validate_evidence(refs: list[AudienceEvidence], context: dict) -> None:
    """Only exact excerpts from the actual model input can count as evidence."""
    if evidence_issues(refs, context):
        raise ValueError("受众证据引用与本次输入不符，请重新分析")


def select_audience_personas(audience: dict, snapshot: dict | None = None) -> list[dict]:
    groups = audience.get("groups", [])
    # New results have evidence-ranked order. Keep legacy ordering for old records.
    if audience.get("method") != "evidence_grounded_v1":
        groups = sorted(groups, key=lambda g: g.get("estimatedPercent") or 0, reverse=True)
    selected = [
        {**g, "limitations": audience.get("limitations", ""),
         "evidenceStatus": "hypothesis" if audience.get("origin") == "curated_preset"
         else "verified" if audience.get("method") == "evidence_grounded_v1"
         else "legacy_unverified"}
        for g in groups[:3]
    ]
    if audience.get("origin") == "curated_preset":
        for group in selected:
            group["origin"] = "curated_preset"
    # Older verified analyses have immutable source snapshots but no paired examples.
    # Enrich this new simulation only; never rewrite the historical analysis.
    if snapshot and audience.get("method") == "evidence_grounded_v1":
        context = audience_context(snapshot)
        for group in selected:
            group["observedEpisodes"] = observed_episodes(
                [AudienceEvidence.model_validate(r) for r in group.get("evidenceRefs", [])],
                context,
            )
    return selected
