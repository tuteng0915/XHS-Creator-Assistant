"""Internal reading-need references, not observed people or ready-made fans.

The catalog is a menu for a later evidence-matching step. A prototype by itself
must never be saved as a SimulatedFan or treated as proof about an account.
"""

from dataclasses import dataclass

from pydantic import ConfigDict, Field

from app.models import APIModel
from app.services.audience_evidence import (
    AudienceEvidence,
    audience_context,
    validate_evidence,
)


@dataclass(frozen=True, slots=True)
class ReadingNeedPrototype:
    id: str
    name: str
    reading_task: str
    match_question: str


READING_NEED_PROTOTYPES: tuple[ReadingNeedPrototype, ...] = (
    ReadingNeedPrototype(
        "scope_check", "确认适用范围", "判断内容是否适用于自己关心的情形。",
        "笔记或评论是否明确提出适用条件、前提或例外？",
    ),
    ReadingNeedPrototype(
        "step_by_step", "拆解操作步骤", "把一个方向转成可执行的先后步骤。",
        "是否出现对流程顺序、材料清单或下一步操作的具体需求？",
    ),
    ReadingNeedPrototype(
        "cost_scope", "核对成本口径", "弄清费用包含什么、遗漏什么。",
        "是否出现对费用构成、额外支出或计算口径的追问？",
    ),
    ReadingNeedPrototype(
        "claim_check", "核验信息依据", "确认说法的来源、时效和可信范围。",
        "是否出现对证据、政策出处、更新时间或真实性的追问？",
    ),
    ReadingNeedPrototype(
        "option_compare", "比较可选路径", "理解不同方案的取舍，而非只寻找单一答案。",
        "是否出现两个以上方案的比较标准或权衡问题？",
    ),
    ReadingNeedPrototype(
        "risk_exception", "识别风险与例外", "提前发现可能让建议失效的条件。",
        "是否出现失败情况、限制条件、潜在损失或反例？",
    ),
    ReadingNeedPrototype(
        "tool_template", "获取实用工具", "寻找可复用的模板、清单或操作工具。",
        "是否明确索取模板、表格、链接、清单或演示？",
    ),
    ReadingNeedPrototype(
        "experience_reference", "寻找经验参照", "借具体经历理解过程中的选择和变化。",
        "是否对内容中的经历、过程或结果提出具体追问？",
    ),
    ReadingNeedPrototype(
        "concept_clarity", "弄懂关键概念", "先澄清术语和基本机制，再判断建议。",
        "是否出现对术语含义、机制或基础背景的解释需求？",
    ),
    ReadingNeedPrototype(
        "resource_discovery", "寻找资源线索", "找到进一步查证或执行所需的资源。",
        "是否明确询问资料、机构、渠道或可访问的资源？",
    ),
    ReadingNeedPrototype(
        "direction_inspiration", "探索新的方向", "从内容中获得可尝试的想法和切入点。",
        "是否出现对新选项、创作角度或可能性的探索？",
    ),
    ReadingNeedPrototype(
        "follow_up", "关注后续进展", "希望知道事情后来怎样、信息是否更新。",
        "是否明确要求后续结果、更新或持续记录？",
    ),
)


def catalog_for_matching() -> list[dict[str, str]]:
    """Return only reference descriptions; matching must supply its own evidence."""
    return [
        {
            "id": item.id,
            "name": item.name,
            "readingTask": item.reading_task,
            "matchQuestion": item.match_question,
        }
        for item in READING_NEED_PROTOTYPES
    ]


def matching_input_from_snapshot(snapshot: dict) -> dict:
    """Prepare only the scoped text a later prototype matcher may cite.

    Keep this separate from the current audience-analysis call until the
    matching result has a reviewed persistence and confirmation path.
    """
    context = audience_context(snapshot)
    return {
        "scope": context["scope"],
        "notes": context["notes"],
        "sampling": context["sampling"],
        "catalog": catalog_for_matching(),
    }


class ReadingNeedCandidate(APIModel):
    """An unconfirmed task match, never a fan or a demographic group."""

    model_config = ConfigDict(extra="forbid")

    prototype_id: str
    match_reason: str = Field(min_length=1, max_length=500)
    evidence_refs: list[AudienceEvidence] = Field(min_length=1, max_length=6)
    counter_evidence_refs: list[AudienceEvidence] = Field(default_factory=list, max_length=6)
    uncertainty: str = Field(min_length=1, max_length=500)


def validate_reading_need_candidates(raw: list[dict], context: dict) -> list[dict]:
    """Validate a bounded proposal against only this analysis's sent source text.

    Exact citations establish provenance, not that the interpretation is true.
    Empty output is valid: the catalog need not match an account.
    """
    if len(raw) > 3:
        raise ValueError("阅读需求候选最多三项")
    catalog = {item.id: item for item in READING_NEED_PROTOTYPES}
    seen: set[str] = set()
    proposals = []
    for item in raw:
        candidate = ReadingNeedCandidate.model_validate(item)
        if candidate.prototype_id not in catalog:
            raise ValueError("未知阅读需求原型")
        if candidate.prototype_id in seen:
            raise ValueError("阅读需求原型不可重复")
        seen.add(candidate.prototype_id)
        validate_evidence(candidate.evidence_refs, context)
        if candidate.counter_evidence_refs:
            validate_evidence(candidate.counter_evidence_refs, context)
        prototype = catalog[candidate.prototype_id]
        cited_types = {ref.source_type for ref in candidate.evidence_refs}
        citation_basis = (
            "mixed" if len(cited_types) == 2
            else "comment_only" if "comment" in cited_types
            else "note_only"
        )
        proposals.append({
            "prototypeId": prototype.id,
            "name": prototype.name,
            "readingTask": prototype.reading_task,
            "matchReason": candidate.match_reason,
            "citationBasis": citation_basis,
            "evidenceRefs": [ref.model_dump(mode="json", by_alias=True)
                             for ref in candidate.evidence_refs],
            "counterEvidenceRefs": [ref.model_dump(mode="json", by_alias=True)
                                    for ref in candidate.counter_evidence_refs],
            "uncertainty": candidate.uncertainty,
            "status": "unconfirmed_proposal",
            "semanticReviewNeeded": True,
        })
    return proposals
