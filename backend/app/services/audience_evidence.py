"""Bounded, traceable evidence for audience research (never population estimates)."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, StringConstraints

from app.models import APIModel
from app.services.audience_target import reader_visible_texts
from app.services.xhs_comment_roles import comment_source_role

AUDIENCE_METHOD_VERSION = "audience_methods_v2"

# Broad interests, not individual note titles or a whitelist of readable topics.
InterestLabel = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=30),
]


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

    # Include the reader-visible Brief/outline too, not just the parent Topic.
    # Union per fragment avoids manufacturing bigrams across unrelated fields.
    query = set().union(*(terms(text) for text in reader_visible_texts(topic)))
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


def discussion_coverage(
    personas: list[dict], reactions: list[dict], replies: list[dict],
    *, enabled: bool = True,
) -> dict:
    """Describe observed execution coverage; silence is a result, not a missing call."""
    expected = [p["id"] for p in personas]
    initial = {r["personaId"] for r in reactions}
    public = public_reactions(reactions)
    eligible = [pid for pid in expected if enabled and pid in initial
                and any(r["personaId"] != pid for r in public)]
    responded = {r["personaId"] for r in replies}
    return {
        "missingInitialPersonaIds": [pid for pid in expected if pid not in initial],
        "initialSilentPersonaIds": [r["personaId"] for r in reactions
                                    if r.get("action") in {"no_comment", "skip"}],
        "publicInitialCount": len(public),
        "discussionEligiblePersonaIds": eligible,
        "missingDiscussionPersonaIds": [pid for pid in eligible if pid not in responded],
        "discussionSilentPersonaIds": [r["personaId"] for r in replies
                                       if not (r.get("response") or r.get("text") or "").strip()],
        "publicReplyCount": sum(bool((r.get("response") or r.get("text") or "").strip())
                                for r in replies),
    }


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
        # Bound and assign IDs before partitioning so old snapshot references keep
        # their positions and the author background cannot double the token budget.
        comments = [
            {
                "commentId": str(c.get("commentId") or f"snapshot-comment-{j}"),
                "content": str(c.get("content") or "")[:1000],
                "createTime": c.get("createTime"),
                "sourceRole": comment_source_role(note, c),
            }
            for j, c in enumerate(note.get("comments", [])[:50])
        ]
        selected.append({
            "noteId": str(note.get("noteId") or f"snapshot-note-{i}"),
            "title": str(note.get("title") or "")[:1000],
            "content": str(note.get("desc") or "")[:4000],
            "comments": [c for c in comments if c["sourceRole"] != "author"],
            "authorReplies": [c for c in comments if c["sourceRole"] == "author"],
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
            "sentComments": sum(len(n["comments"]) + len(n["authorReplies"]) for n in selected),
            "sentCandidateComments": sum(len(n["comments"]) for n in selected),
            "sentAuthorComments": sum(len(n["authorReplies"]) for n in selected),
            "sentUnknownRoleComments": sum(
                c["sourceRole"] == "unknown" for n in selected for c in n["comments"]
            ),
            "commentRoleMethod": "mediacrawler_author_hash_v1",
            "commentLayout": "reader_comments_author_background_v1",
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
    author_comments: set[tuple] = set()
    for note in context["notes"]:
        note_key = (note["noteId"], None, "note")
        occurrences[note_key] = occurrences.get(note_key, 0) + 1
        sources.setdefault((note["noteId"], None, "note"), []).extend(
            [note["title"], note["content"]]
        )
        for field in ("comments", "authorReplies"):
            for comment in note.get(field, []):
                comment_key = (note["noteId"], comment["commentId"], "comment")
                # Also accept the older mixed-list layout during report replay.
                if field == "authorReplies" or comment.get("sourceRole") == "author":
                    author_comments.add(comment_key)
                occurrences[comment_key] = occurrences.get(comment_key, 0) + 1
                sources.setdefault(comment_key, []).append(comment["content"])
    issues = []
    for index, ref in enumerate(refs):
        key = (ref.note_id, ref.comment_id, ref.source_type)
        if key in author_comments:
            issues.append({
                "referenceIndex": index,
                "code": "author_comment_not_reader_evidence",
                "message": "作者回复可作背景，不能作为读者需求证据",
                "reference": ref.model_dump(mode="json", by_alias=True),
            })
            continue
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


def select_audience_personas(
    audience: dict, snapshot: dict | None = None, *, limit: int | None = 3,
) -> list[dict]:
    groups = audience.get("groups", [])
    # New results have evidence-ranked order. Keep legacy ordering for old records.
    if audience.get("method") != "evidence_grounded_v1":
        groups = sorted(groups, key=lambda g: g.get("estimatedPercent") or 0, reverse=True)
    selected = [
        {**g, "limitations": audience.get("limitations", "")
         + (" 引用仅核验原文存在，阅读视角和个人处境仍是待核对的模型推断。"
            if g.get("evidenceBasis") else ""),
         "evidenceStatus": "hypothesis" if (
             audience.get("origin") == "curated_preset"
             or bool(g.get("evidenceBasis"))
             or (audience.get("method") == "evidence_grounded_v1"
                 and g.get("evidenceRefs")
                 and all(r.get("sourceType") == "note" for r in g["evidenceRefs"]))
         )
         else "verified" if audience.get("method") == "evidence_grounded_v1"
         else "legacy_unverified"}
        for g in groups[:limit]
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
