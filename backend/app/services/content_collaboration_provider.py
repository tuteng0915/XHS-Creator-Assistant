"""Live, read-only specialist provider for content-collaboration sessions.

The session service owns persistence and the graph owns turn routing.  This
adapter is deliberately narrower: it projects an already-frozen session
snapshot into a bounded model input, validates the model's structured handoff,
and never reads or writes product storage itself.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic import ValidationError as PydanticValidationError

from app.errors import ValidationError
from app.models import ModelOperation
from app.services.content_collaboration import (
    CollaborationMessage,
    SpecialistRole,
    SpecialistTurn,
)
from app.services.model_calls import ModelCallService

_MAX_SOURCE_CHARS = 1_600
_MAX_TARGET_SOURCE_CHARS = 6_000
_MAX_TRANSCRIPT_MESSAGE_CHARS = 1_800
_ALLOWED_NEXT_RECIPIENTS: dict[SpecialistRole, set[str]] = {
    "research": {"writing", "creator"},
    "writing": {"research", "review", "creator"},
    "review": {"research", "writing", "creator"},
}
_ALLOWED_SUGGESTION_KINDS: dict[SpecialistRole, set[str]] = {
    "research": {"evidence", "open_question"},
    "writing": {"outline", "copy_option", "open_question"},
    "review": {"review_note", "open_question"},
}

# Each specialist sees a task packet tailored to the decision it is expected
# to improve.  This is deliberately more than a role label: the role packet
# controls which frozen material is foregrounded and tells the model what a
# useful handoff looks like.  We keep the source list bounded so an old draft
# or unrelated account overview cannot drown out the immediately addressed
# handoff.
_ROLE_TASKS: dict[SpecialistRole, dict[str, Any]] = {
    "research": {
        "stage": "evidence_to_writing_brief",
        "objective": "把创作者的问题拆成可写的事实锚点、证据边界和真正影响写法的缺口。",
        "handoff": "让写作角色知道哪些细节可以直接使用、哪些地方必须留白或向创作者追问。",
        "candidatePlan": "优先给 1–2 条可写证据；只有会改变叙事取舍的缺口才提问。",
        "qualityBar": [
            "证据候选要说明它将支撑哪一个叙事动作，而不是只复述原文。",
            "问题必须具体到创作者能补充的经历、判断或结果，不能泛泛追问受众或风格。",
            "如果材料已经足够，交给 writing；若关键事实缺失，交给 creator。",
        ],
    },
    "writing": {
        "stage": "evidence_to_readable_structure",
        "objective": "把上游确认过的材料组织成读者愿意跟下去的叙事路径，而不是重述研究结论。",
        "handoff": (
            "给评审一份可检查的写作结构：开场抓什么、怎样推进、转折落在哪里、"
            "读者最后带走什么。"
        ),
        "candidatePlan": (
            "按创作者本次要求选择产物：明确要求起草或改写时给 copy_option，body 是"
            "可直接使用的正文或标题，不要只给提纲；讨论结构时给 outline。"
            "只有关键事实缺失时才用 open_question 追问。"
        ),
        "qualityBar": [
            "outline 应清楚区分开场、推进、转折和收束中的至少三个动作。",
            "用户只要求改标题、开头或某段时，只给该部分的表述，不擅自改动其他段落。",
            "可选表述只能服务于该结构，且不能替创作者补造经历。",
            "结构已成形时交给 review；发现写作无法成立的事实空洞时交给 research 或 creator。",
        ],
    },
    "review": {
        "stage": "structure_to_revision_priority",
        "objective": "针对眼前的写作结构判断哪里最有辨识度、哪里会让读者停住，以及先改哪一处。",
        "handoff": "给创作者一份有排序的修改判断，而不是泛泛说‘更具体’或重新写一篇。",
        "candidatePlan": (
            "优先给 1–2 条 review_note，分别说明保留点和最高优先级的修改；"
            "事实无法判断时再提问。"
        ),
        "qualityBar": [
            "每条评审要落在上游结构中的具体动作、承诺或信息缺口上。",
            "指出一处值得保留的张力或表达，并给出一处最值得修改的地方及理由。",
            "把证据判断和新增写法分开：若补入输入中没有的时间、经历或句子，明确标为待确认的创作建议。",
            "有可执行修改时交给 creator；需要核对事实时交给 research 或 creator。",
        ],
    },
}

_ROLE_SOURCE_KEYS: dict[SpecialistRole, tuple[str, ...]] = {
    "research": (
        "selected_topic",
        "account_profile",
        "input_assets_overview",
        "analysis_history_overview",
    ),
    "writing": (
        "selected_topic",
        "account_profile",
        "input_assets_overview",
        "draft_history_overview",
    ),
    "review": (
        "selected_topic",
        "account_profile",
        "input_assets_overview",
        "draft_history_overview",
    ),
}
_MAX_PRIOR_HANDOFF_SOURCES = 3


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _excerpt(value: Any, *, limit: int) -> str:
    text = value if isinstance(value, str) else _canonical(value)
    text = text.strip()
    return text if len(text) <= limit else text[:limit]


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class _EvidenceRef(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source_id: str = Field(alias="sourceId", min_length=1, max_length=160)
    quote: str = Field(min_length=1, max_length=240)


class _CandidateSuggestion(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    kind: Literal["evidence", "open_question", "outline", "copy_option", "review_note"]
    title: str = Field(min_length=1, max_length=120)
    body: str = Field(min_length=1, max_length=1_200)
    confidence: Literal["supported", "inference", "needs_creator"]
    evidence_refs: list[_EvidenceRef] = Field(
        default_factory=list, alias="evidenceRefs", max_length=3
    )

    @model_validator(mode="after")
    def validate_confidence(self) -> _CandidateSuggestion:
        if self.confidence == "supported" and not self.evidence_refs:
            raise ValueError("supported 候选必须提供冻结来源")
        if self.kind == "open_question" and self.confidence != "needs_creator":
            raise ValueError("open_question 必须标记为 needs_creator")
        return self


class _WireTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    summary: str = Field(min_length=1, max_length=1_200)
    next_recipient: Literal["research", "writing", "review", "creator"] = Field(
        alias="nextRecipient"
    )
    candidate_suggestions: list[_CandidateSuggestion] = Field(
        default_factory=list, alias="candidateSuggestions", max_length=3
    )
    used_candidate_ids: list[str] = Field(
        default_factory=list, alias="usedCandidateIds", max_length=3
    )


class _WireOutput(BaseModel):
    """Exact response envelope accepted from the model, with no aliases or extras."""

    model_config = ConfigDict(extra="forbid")

    turn: _WireTurn


class RealContentCollaborationProvider:
    """Invoke one Qwen turn without granting it product read/write capabilities."""

    def __init__(self, model_call_service: ModelCallService) -> None:
        self.model_call_service = model_call_service

    async def run(
        self,
        *,
        role: SpecialistRole,
        message: CollaborationMessage,
        context: dict[str, Any],
    ) -> SpecialistTurn:
        provider = self.model_call_service.settings.model_provider.strip().lower()
        # This product's live specialist path is intentionally Qwen-only for
        # now.  It keeps a demo request from unexpectedly switching providers
        # just because another provider is globally configured.
        if provider not in {"qwen", "dashscope"}:
            raise ValidationError("实时协作目前仅支持已配置的 Qwen / DashScope 模型")

        all_sources = self._allowed_sources(context)
        upstream_candidates = self._upstream_candidates(context)
        sources = self._sources_for_role(
            role=role,
            message=message,
            context=context,
            sources=all_sources,
        )
        response = await self.model_call_service.call_operation(
            ModelOperation.CONTENT_COLLABORATION_TURN,
            self._model_context(role=role, message=message, context=context, sources=sources),
        )
        try:
            output = _WireOutput.model_validate(response.output)
        except PydanticValidationError as error:
            raise ValidationError("协作角色返回格式不符合本轮交接契约") from error

        turn = output.turn
        single_writer = context.get("assistantMode") == "single_writer"
        if single_writer and (role != "writing" or turn.next_recipient != "creator"):
            raise ValidationError("创作助手应直接回复作者，不转交其他角色")
        self._validate_turn(
            role=role,
            turn=turn,
            sources=sources,
            upstream_candidates=upstream_candidates,
            single_writer=single_writer,
        )
        candidates = [item.model_dump(by_alias=True) for item in turn.candidate_suggestions]
        return SpecialistTurn(
            content=self._render_turn(turn),
            to=turn.next_recipient,
            # Candidate suggestions are immutable discussion material, not
            # artifacts or Topic updates.  Keeping them in metadata makes the
            # provenance available without granting a model a write path.
            model_metadata={
                **response.model_metadata,
                "contract": ("creator-writing-turn/v1" if single_writer
                             else "content-collaboration-turn/v2"),
                "candidateSuggestions": candidates,
                "usedCandidateIds": list(turn.used_candidate_ids),
            },
        )

    @staticmethod
    def _allowed_sources(context: dict[str, Any]) -> dict[str, dict[str, str]]:
        """Build the source IDs exposed to this turn from frozen state only."""
        sources: dict[str, dict[str, str]] = {}

        def add(source_id: str, label: str, value: Any, *, limit: int) -> None:
            text = _excerpt(value, limit=limit)
            if not text:
                return
            sources[source_id] = {
                "id": source_id,
                "label": label,
                "text": text,
                "contentHash": _content_hash(text),
            }

        target = context.get("target")
        if isinstance(target, dict):
            target_limit = (len(_canonical(target))
                            if context.get("assistantMode") == "single_writer"
                            else _MAX_TARGET_SOURCE_CHARS)
            add("target:topic", "冻结选题", target, limit=target_limit)

        focus = context.get("writingFocus")
        if isinstance(focus, dict):
            selection = focus.get("selection")
            if isinstance(selection, dict):
                add("writing:selected_text", "作者选中的正文片段", selection.get("text", ""),
                    limit=100_000)
            reader = focus.get("readerMessage")
            if isinstance(reader, dict):
                add("writing:reader_opinion", "模拟读者公开意见（不是作者事实）",
                    {key: reader[key] for key in ("senderName", "content", "authorQuestion")
                     if key in reader}, limit=8_000)

        session_context = context.get("sessionContext")
        if context.get("assistantMode") == "single_writer" and isinstance(session_context, dict):
            snapshot = session_context.get("creatorContextSnapshot", {})
            for reference in snapshot.get("references", []):
                source_id = f"reference:{reference['kind']}:{reference['id']}"
                if reference["kind"] == "imported_note":
                    # Multiple selected notes share a material ID. Hash the
                    # pair to retain uniqueness within the bounded source ID.
                    source_id = "reference:imported_note:" + _content_hash(_canonical(
                        {"id": reference["id"], "noteId": reference["noteId"]},
                    ))
                add(
                    source_id,
                    {"account_analysis": "作者选择的账号分析",
                     "audience_analysis": "作者选择的受众分析",
                     "imported_note": "作者选择的原笔记"}[reference["kind"]],
                    {"scope": reference.get("scope", {}), "result": reference["content"],
                     "sourceOrigin": reference.get("sourceOrigin", "unknown")},
                    limit=100_000,
                )
                # Keep the use boundary adjacent to each long reference, not
                # only in a distant system paragraph or an ID grouping.
                sources[source_id]["useBoundary"] = (
                    "原笔记中明确写过的事实，保留原主体与历史时点；不补写新事件。"
                    if reference["kind"] == "imported_note" else
                    "写法与选题参考，不是作者亲历或当前读者的确定处境。"
                    "其中评论属于历史评论者，不移植其时间、成绩、专业等条件。"
                )
        workspace_context = (
            session_context.get("workspaceContext")
            if isinstance(session_context, dict) and context.get("assistantMode") != "single_writer"
            else None
        )
        if isinstance(workspace_context, dict):
            for item in workspace_context.get("items", []):
                if not isinstance(item, dict):
                    continue
                key = item.get("key")
                if not isinstance(key, str) or not key.strip():
                    continue
                add(
                    f"workspace:{key}",
                    f"冻结工作区资料：{key}",
                    item.get("data"),
                    limit=_MAX_SOURCE_CHARS,
                )

        for item in context.get("transcript", []):
            if not isinstance(item, dict):
                continue
            if context.get("assistantMode") == "single_writer" and item.get("sender") != "creator":
                # Generated prose remains discussable, but cannot be cited as
                # evidence that an event happened to the author.
                continue
            message_id = item.get("id")
            content = item.get("content")
            if isinstance(message_id, str) and isinstance(content, str):
                add(
                    f"message:{message_id}",
                    f"协作消息：{item.get('sender', 'unknown')} → {item.get('to', 'unknown')}",
                    content,
                    limit=(8_000 if context.get("assistantMode") == "single_writer"
                           else _MAX_TRANSCRIPT_MESSAGE_CHARS),
                )
        return sources

    @staticmethod
    def _sources_for_role(
        *,
        role: SpecialistRole,
        message: CollaborationMessage,
        context: dict[str, Any],
        sources: dict[str, dict[str, str]],
    ) -> dict[str, dict[str, str]]:
        """Retrieve a compact, role-relevant subset from the frozen source map.

        The addressed message is always present.  Research additionally sees
        historic evidence summaries; writing and review see the account voice
        plus the upstream handoff and only the material that can support a
        concrete structure or revision.  This is deterministic retrieval over
        the already-frozen pack, never a fresh database read.
        """
        if context.get("assistantMode") == "single_writer":
            return {
                key: source for key, source in sources.items()
                if key == "target:topic" or key.startswith(("writing:", "reference:", "message:"))
            }
        requested_ids = ["target:topic"]
        requested_ids.extend(["writing:selected_text", "writing:reader_opinion"])
        requested_ids.extend(f"workspace:{key}" for key in _ROLE_SOURCE_KEYS[role])
        requested_ids.append(f"message:{message.id}")

        # Preserve a short chain of prior handoffs for continuity without
        # showing the role a full, noisy transcript.  The newest relevant
        # message is already the addressed one, so it is not added twice.
        prior_ids: list[str] = []
        for item in reversed(context.get("transcript", [])):
            if not isinstance(item, dict):
                continue
            message_id = item.get("id")
            if not isinstance(message_id, str) or message_id == message.id:
                continue
            source_id = f"message:{message_id}"
            if source_id in sources:
                prior_ids.append(source_id)
            if len(prior_ids) >= _MAX_PRIOR_HANDOFF_SOURCES:
                break
        requested_ids.extend(reversed(prior_ids))

        # A writing or review turn must be able to inspect the original
        # material that its upstream candidate cites, not only a rendered
        # sentence from the previous specialist.
        for candidate in RealContentCollaborationProvider._upstream_candidates(context):
            for evidence in candidate.get("evidenceRefs", []):
                if isinstance(evidence, dict) and isinstance(evidence.get("sourceId"), str):
                    requested_ids.append(evidence["sourceId"])

        selected: dict[str, dict[str, str]] = {}
        for source_id in requested_ids:
            source = sources.get(source_id)
            if source is not None:
                selected[source_id] = source
        return selected

    @staticmethod
    def _model_context(
        *,
        role: SpecialistRole,
        message: CollaborationMessage,
        context: dict[str, Any],
        sources: dict[str, dict[str, str]],
    ) -> dict[str, Any]:
        source_groups = RealContentCollaborationProvider._source_groups(
            role=role,
            message=message,
            sources=sources,
        )
        packet = {
            "schemaVersion": "content-collaboration-role-packet/v2",
            "role": role,
            "roleTask": _ROLE_TASKS[role],
            "creativeBrief": {
                "target": context.get("target")
                if isinstance(context.get("target"), dict)
                else {},
                "creatorRequest": {
                    "sender": message.sender,
                    "content": message.content,
                    "sourceId": f"message:{message.id}",
                },
            },
            "upstreamHandoff": {
                "sender": message.sender,
                "recipient": message.to,
                "content": message.content,
                "sourceId": f"message:{message.id}",
                "instruction": "这是本轮必须推进的上游工作；不要只复述它。",
                "candidates": RealContentCollaborationProvider._upstream_candidates(context),
            },
            "evidence": {
                "sourceGroups": source_groups,
                "allowedSources": list(sources.values()),
                "transcriptTruncated": bool(context.get("transcriptTruncated")),
            },
        }
        focus = context.get("writingFocus")
        if isinstance(focus, dict):
            packet["writingFocus"] = focus
            packet["roleTask"] = {
                **_ROLE_TASKS[role],
                "writingFocusRules": [
                    "writingFocus 是服务端核对过的本次修改范围，所有角色都必须遵守。",
                    "有 selection 时只改选中片段：copy_option.body 是可直接替换的片段正文，"
                    "不得返回整篇、标题、范围外段落或用说明包裹替换片段；其余正文保持原样。",
                    "无 selection 时先根据读者意见与当前稿的差异讨论或起草，不自动覆盖正文。",
                    "readerMessage 是模拟读者的可选择建议，不是作者已确认的事实；"
                    "authorQuestion 是当次追问语境，不将问句和假设当成事实承诺。",
                    "读者意见针对 sourceTarget 的历史版本；当前改稿以 baseBody/baseTitle 为准，"
                    "明确哪些问题最新稿已解决，不机械把旧意见重新执行。",
                    "保留作者口吻和已确认事实；材料不足以支持新增经历、数据或结论时，"
                    "提出一个具体问题，不能把补造内容写入 copy_option。",
                ],
            }
        if context.get("assistantMode") == "single_writer":
            packet["schemaVersion"] = "creator-writing-packet/v1"
            packet["assistantMode"] = "single_writer"
            packet["roleTask"] = {
                "objective": "直接帮助作者讨论角度、起草或精修眼前稿件，保留其具体经历与表达特点。",
                "candidatePlan": (
                    "作者要正文就给可用正文；只聊角度则先讨论；局部精修只返回替换片段。"
                ),
                "qualityBar": [
                    "用已有事实或给读者的具体行动建议推进，不为生动而补造作者亲历；初稿同样适用。",
                    "默认给一个最值得采用的方案和简短理由；只有确有选择价值才给备选。",
                    "只使用当前稿件、这个上下文段内的对话，以及作者显式选择的参考。",
                    "参考分析是建议和观察，不是新稿必须照搬的选题，更不是作者新经历。",
                    "原笔记是作者选中的历史文本，可借鉴表达或已有材料；"
                    "不把其中过去的经历、时间、场景或结果自动移植成当前稿的新事实。",
                    "不同原文中的学校、做法与判断不能拼成作者做过的一次比较；"
                    "助手先前生成的稿件也不是作者确认的事实。",
                ],
                **({"writingFocusRules": packet["roleTask"]["writingFocusRules"]}
                   if isinstance(focus, dict) else {}),
            }
            packet.pop("upstreamHandoff", None)
            packet["previousSuggestions"] = [
                {"id": item["id"], "content": _excerpt(item["content"], limit=8_000)}
                for item in context.get("transcript", [])
                if isinstance(item, dict) and item.get("sender") == "writing"
                and isinstance(item.get("id"), str) and isinstance(item.get("content"), str)
            ]
            packet["evidence"]["sourceGroups"] = {
                "manuscript": [key for key in sources if key == "target:topic"],
                "originalNotes": [key for key in sources
                                  if key.startswith("reference:imported_note:")],
                "analysisObservationsNotPersonalFacts": [key for key in sources
                                                        if key.startswith((
                                                            "reference:account_analysis:",
                                                            "reference:audience_analysis:",
                                                        ))],
                "authorMessages": [f"message:{item['id']}" for item in context.get("transcript", [])
                                   if isinstance(item, dict) and item.get("sender") == "creator"
                                   and f"message:{item.get('id')}" in sources],
                "writingFocus": [key for key in sources if key.startswith("writing:")],
            }
        return packet

    @staticmethod
    def _source_groups(
        *,
        role: SpecialistRole,
        message: CollaborationMessage,
        sources: dict[str, dict[str, str]],
    ) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = {
            "creativeBrief": [
                source_id
                for source_id in ("target:topic", "workspace:selected_topic")
                if source_id in sources
            ],
            "accountVoice": [
                source_id
                for source_id in ("workspace:account_profile",)
                if source_id in sources
            ],
            "upstreamHandoff": [f"message:{message.id}"],
        }
        if role == "research":
            groups["researchEvidence"] = [
                source_id
                for source_id in (
                    "workspace:input_assets_overview",
                    "workspace:analysis_history_overview",
                )
                if source_id in sources
            ]
        elif role == "writing":
            groups["writingSupport"] = [
                source_id
                for source_id in (
                    "workspace:input_assets_overview",
                    "workspace:draft_history_overview",
                )
                if source_id in sources
            ]
        else:
            groups["reviewSupport"] = [
                source_id
                for source_id in (
                    "workspace:input_assets_overview",
                    "workspace:draft_history_overview",
                )
                if source_id in sources
            ]
        groups["priorHandoffs"] = [
            source_id
            for source_id in sources
            if source_id.startswith("message:") and source_id != f"message:{message.id}"
        ]
        return groups

    @staticmethod
    def _upstream_candidates(context: dict[str, Any]) -> list[dict[str, Any]]:
        """Keep only the durable, server-shaped candidate fields for a handoff."""
        value = context.get("upstreamCandidates")
        if not isinstance(value, list):
            return []
        candidates: list[dict[str, Any]] = []
        for candidate in value:
            if not isinstance(candidate, dict):
                continue
            candidate_id = candidate.get("candidateId")
            kind = candidate.get("kind")
            title = candidate.get("title")
            body = candidate.get("body")
            confidence = candidate.get("confidence")
            evidence_refs = candidate.get("evidenceRefs")
            if not all(
                isinstance(item, str) and item.strip()
                for item in (candidate_id, kind, title, body, confidence)
            ) or not isinstance(evidence_refs, list):
                continue
            candidates.append(
                {
                    "candidateId": candidate_id,
                    "kind": kind,
                    "title": title,
                    "body": body,
                    "confidence": confidence,
                    "evidenceRefs": [
                        {"sourceId": item["sourceId"], "quote": item["quote"]}
                        for item in evidence_refs
                        if isinstance(item, dict)
                        and isinstance(item.get("sourceId"), str)
                        and isinstance(item.get("quote"), str)
                    ],
                }
            )
        return candidates

    @staticmethod
    def _validate_turn(
        *,
        role: SpecialistRole,
        turn: _WireTurn,
        sources: dict[str, dict[str, str]],
        upstream_candidates: list[dict[str, Any]],
        single_writer: bool = False,
    ) -> None:
        if not turn.summary.strip():
            raise ValidationError("协作交接摘要不能为空")
        if turn.next_recipient not in _ALLOWED_NEXT_RECIPIENTS[role]:
            raise ValidationError(f"{role} 不能将本轮交接给 {turn.next_recipient}")
        upstream_by_id = {
            item["candidateId"]: item
            for item in upstream_candidates
            if isinstance(item.get("candidateId"), str)
        }
        if len(set(turn.used_candidate_ids)) != len(turn.used_candidate_ids):
            raise ValidationError("本轮引用的上游候选不能重复")
        if any(candidate_id not in upstream_by_id for candidate_id in turn.used_candidate_ids):
            raise ValidationError("本轮引用了不存在的上游候选")
        if role in {"writing", "review"} and upstream_by_id and not turn.used_candidate_ids:
            raise ValidationError(f"{role} 必须明确使用至少一条上游候选")
        for candidate in turn.candidate_suggestions:
            if not candidate.title.strip() or not candidate.body.strip():
                raise ValidationError("候选标题和内容不能为空")
            if candidate.kind not in _ALLOWED_SUGGESTION_KINDS[role]:
                raise ValidationError(f"{role} 不能生成 {candidate.kind} 类型的候选")
            if not single_writer and candidate.confidence == "inference" and not any(
                marker in candidate.body for marker in ("推断", "待验证")
            ):
                raise ValidationError("推断候选必须明确标记为推断或待验证")
            for evidence in candidate.evidence_refs:
                if not evidence.quote.strip():
                    raise ValidationError("候选引用不能为空")
                source = sources.get(evidence.source_id)
                if source is None:
                    raise ValidationError("候选引用了本轮未提供的冻结来源")
                if evidence.quote not in source["text"]:
                    raise ValidationError("候选引用无法在冻结来源中逐字定位")

        if role == "research" and turn.next_recipient == "writing" and not any(
            candidate.kind == "evidence" and candidate.confidence == "supported"
            for candidate in turn.candidate_suggestions
        ):
            raise ValidationError("研究交给写作前必须给出至少一条可用证据")
        if role == "writing" and turn.next_recipient == "review" and not any(
            candidate.kind in {"outline", "copy_option"}
            for candidate in turn.candidate_suggestions
        ):
            raise ValidationError("写作交给评审前必须给出可评审的结构或表述")
        if role == "review" and upstream_by_id:
            reviewed = [upstream_by_id[item] for item in turn.used_candidate_ids]
            if not any(item.get("kind") in {"outline", "copy_option"} for item in reviewed):
                raise ValidationError("评审必须指向上游的写作结构或表述")
            if turn.next_recipient == "creator" and not any(
                candidate.kind == "review_note" for candidate in turn.candidate_suggestions
            ):
                raise ValidationError("评审交给创作者前必须给出至少一条修改判断")

    @staticmethod
    def _render_turn(turn: _WireTurn) -> str:
        lines = [turn.summary.strip()]
        for candidate in turn.candidate_suggestions:
            suffix = "（需创作者确认）" if candidate.confidence == "needs_creator" else ""
            lines.append(f"【{candidate.title.strip()}】{candidate.body.strip()}{suffix}")
        return "\n\n".join(lines)
