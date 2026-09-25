"""Bounded, traceable evidence for audience research (never population estimates)."""

from typing import Literal

from pydantic import Field

from app.models import APIModel


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


def validate_evidence(refs: list[AudienceEvidence], context: dict) -> None:
    """Only exact excerpts from the actual model input can count as evidence."""
    if not refs:
        raise ValueError("受众视角缺少可核验的原文引用")
    sources: dict[tuple, list[str]] = {}
    for note in context["notes"]:
        sources.setdefault((note["noteId"], None, "note"), []).extend(
            [note["title"], note["content"]]
        )
        for comment in note["comments"]:
            sources.setdefault((note["noteId"], comment["commentId"], "comment"), []).append(
                comment["content"]
            )
    for ref in refs:
        candidates = sources.get((ref.note_id, ref.comment_id, ref.source_type), [])
        if not ref.quote.strip() or not any(ref.quote in text for text in candidates):
            raise ValueError("受众证据引用与本次输入不符，请重新分析")


def select_audience_personas(audience: dict) -> list[dict]:
    groups = audience.get("groups", [])
    # New results have evidence-ranked order. Keep legacy ordering for old records.
    if audience.get("method") != "evidence_grounded_v1":
        groups = sorted(groups, key=lambda g: g.get("estimatedPercent") or 0, reverse=True)
    return [
        {**g, "limitations": audience.get("limitations", ""),
         "evidenceStatus": "verified" if audience.get("method") == "evidence_grounded_v1"
         else "legacy_unverified"}
        for g in groups[:3]
    ]
