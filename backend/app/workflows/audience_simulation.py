# ruff: noqa: E501

from __future__ import annotations

import asyncio
import contextvars
from collections.abc import AsyncIterator, Awaitable, Callable
from copy import deepcopy
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, model_validator
from pydantic import ValidationError as PydanticValidationError

from app.db.database import SQLiteDatabase
from app.errors import ConflictError, ValidationError
from app.models import ModelOperation, SimulationRunStatus
from app.repositories.graph_checkpoints import GraphCheckpointRepository
from app.repositories.simulation_runs import SIMULATION_TERMINAL_STATUSES
from app.services.audience_evidence import (
    DISCUSSION_SKIPPED_REASON,
    AudienceEvidence,
    ObservedEpisode,
    public_reactions,
    reader_persona_context,
)
from app.services.common import utc_now
from app.services.model_calls import ModelCallService
from app.services.simulation_runs import SimulationRunService
from app.workflows.account_diagnosis import GraphExecutionPaused

AUDIENCE_SIMULATION_NODE_ORDER = [
    "derive_personas",
    "parallel_initial_reactions",
    "parallel_debate_responses",
    "synthesis",
    "finalize",
]
SIMULATION_STAGE_ORDER = [
    "personas",
    "initial_reactions",
    "debate_responses",
    "synthesis",
]
ACTIVE_SIMULATION_EXECUTION: contextvars.ContextVar[
    _AudienceSimulationGraphExecution | None
] = contextvars.ContextVar("audience_simulation_execution", default=None)


class SimulationActivityEvent(TypedDict):
    eventId: str
    runId: str
    runType: Literal["audience_simulation"]
    stageKey: str | None
    status: str
    sequence: int
    occurredAt: str
    data: dict[str, Any]


class AudienceSimulationState(TypedDict, total=False):
    simulation_id: str
    workspace_id: str
    topic_id: str | None
    positioning_snapshot: str
    topic: dict[str, Any]
    personas: list[dict[str, Any]]
    initial_reactions: list[dict[str, Any]]
    debate_responses: list[dict[str, Any]]
    synthesis: dict[str, Any]
    stage_errors: dict[str, str]


class PersonaDefinition(BaseModel):
    id: str
    name: str
    profile: str
    coreConcern: str = ""
    contentPreference: str = ""
    expressionStyle: str = ""
    fanAssetId: str | None = None
    sourceAnalysisId: str | None = None
    updatedAt: str | None = None
    userAdjusted: bool = False
    archetype: str = ""
    background: str = ""
    personality: str = ""
    concerns: str = ""
    color: str = ""
    evidence: list[str] = Field(default_factory=list)
    evidenceRefs: list[AudienceEvidence] = Field(default_factory=list)
    evidenceBasis: Literal["comment_observed", "content_inferred", "mixed"] | None = None
    evidenceStatus: Literal["verified", "legacy_unverified", "hypothesis"] = "hypothesis"
    limitations: str = ""
    unknowns: list[str] = Field(default_factory=list)
    observedEpisodes: list[ObservedEpisode] = Field(default_factory=list)


class PersonaDefinitionsResult(BaseModel):
    personas: list[PersonaDefinition] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_personas(self):
        if len({p.id for p in self.personas}) != len(self.personas):
            raise ValueError("模拟角色 ID 不可重复")
        return self


class PersonaReaction(BaseModel):
    personaId: str
    stance: str
    quote: str = ""
    concerns: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)
    text: str = ""
    sentiment: str = ""
    action: Literal["comment", "no_comment", "skip"] = "comment"
    understanding: str = ""
    triggerQuote: str = ""

    @model_validator(mode="after")
    def comment_matches_action(self):
        if self.action != "comment":
            self.quote = ""
            self.text = ""
        return self


class PersonaReactionResult(BaseModel):
    reaction: PersonaReaction


class DebateResponse(BaseModel):
    personaId: str
    response: str
    changedMind: bool = False
    newConcerns: list[str] = Field(default_factory=list)
    strongerSignals: list[str] = Field(default_factory=list)
    text: str = ""
    targetedAt: str = ""
    stance: str = ""
    replyToId: str | None = None
    changeReason: str = ""

    @model_validator(mode="after")
    def silence_is_not_a_changed_mind(self):
        if not (self.response or self.text).strip():
            self.changedMind = False
            self.replyToId = None
            self.changeReason = ""
            self.targetedAt = ""
        return self


class DebateResponseResult(BaseModel):
    debateResponse: DebateResponse


class SimulationSynthesis(BaseModel):
    verdict: str
    mainResistance: str = ""
    strongestAngle: str = ""
    contentAdjustments: list[str] = Field(default_factory=list)
    riskWarnings: list[str] = Field(default_factory=list)
    topResonance: dict[str, Any] = Field(default_factory=dict)
    controversyPoints: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    limitations: str = ""


class SimulationSynthesisResult(BaseModel):
    synthesis: SimulationSynthesis


def validate_trigger_quote(quote: str, target: dict) -> None:
    def texts(value):
        if isinstance(value, str):
            yield value
        elif isinstance(value, dict):
            for item in value.values():
                yield from texts(item)
        elif isinstance(value, list):
            for item in value:
                yield from texts(item)

    visible = [target.get("title", ""), target.get("body", ""), target.get("draft", {})]
    if quote and (not quote.strip() or not any(quote in text for text in texts(visible))):
        raise ValueError("触发表达不是本次内容的原文")


class AudienceSimulationModelProvider(Protocol):
    async def personas(
        self, *, positioning: str, topic: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def initial_reaction(
        self, *, persona: dict[str, Any], topic: dict[str, Any]
    ) -> dict[str, Any]: ...

    async def debate_response(
        self,
        *,
        persona: dict[str, Any],
        topic: dict[str, Any],
        other_reactions: list[dict[str, Any]],
        prior_reaction: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    async def synthesis(
        self,
        *,
        topic: dict[str, Any],
        personas: list[dict[str, Any]],
        reactions: list[dict[str, Any]],
        debate_responses: list[dict[str, Any]],
    ) -> dict[str, Any]: ...


SAMPLE_SIMULATION_ACCOUNT = {
    "personas": [
        {
            "id": "anxious",
            "name": "李明",
            "archetype": "双非焦虑备考生",
            "profile": "双非本科，均分82，正在准备申请英国G5。容易自我怀疑，喜欢横向比较，对结论性内容依赖强。",
            "coreConcern": "自己的背景够不够、花的钱值不值",
            "contentPreference": "具体预算拆解、适用前提、可执行申请步骤",
            "background": "双非本科，均分82，正在准备申请英国G5",
            "personality": "容易自我怀疑，喜欢横向比较，对结论性内容依赖强",
            "concerns": "自己的背景够不够、花的钱值不值",
            "color": "#4f46e5",
        },
        {
            "id": "experienced",
            "name": "周美",
            "archetype": "已出国的过来人",
            "profile": "双非逆袭UCL，现读研一年级，热衷分享经验。务实、有自己判断、容易对过于焦虑的内容反感。",
            "coreConcern": "内容是否准确、有没有真实信息增量",
            "contentPreference": "边界条件、反例、真实经验增量",
            "background": "双非逆袭UCL，现读研一年级，热衷分享经验",
            "personality": "务实、有自己判断、容易对过于焦虑的内容反感",
            "concerns": "内容是否准确、有没有真实信息增量",
            "color": "#16a34a",
        },
        {
            "id": "returnee",
            "name": "张宇",
            "archetype": "海归回国踩坑者",
            "profile": "曼彻斯特硕士，回国工作1年，感受到落差。略带负面情绪，理性，容易提出尖锐问题。",
            "coreConcern": "海归含金量、留学长期ROI",
            "contentPreference": "长期价值判断、成本收益、避免伪问题",
            "background": "曼彻斯特硕士，回国工作1年，感受到落差",
            "personality": "略带负面情绪，理性，容易提出尖锐问题",
            "concerns": "海归含金量、留学长期ROI",
            "color": "#d97706",
        },
    ],
    "reactions": [
        {
            "personaId": "anxious",
            "stance": "喜欢",
            "quote": "这个太说到我了！我现在就在纠结到底要不要花5万找中介，感觉什么都不懂。标题那个「该花的是这3步」让我特别想点进来，终于有人教我怎么分配这笔钱了。",
            "text": "这个太说到我了！我现在就在纠结到底要不要花5万找中介，感觉什么都不懂。标题那个「该花的是这3步」让我特别想点进来，终于有人教我怎么分配这笔钱了。",
            "sentiment": "positive",
            "concerns": ["自己的背景够不够", "中介费花得值不值"],
            "opportunities": ["明确预算分配框架会强烈触发收藏"],
        },
        {
            "personaId": "experienced",
            "stance": "犹豫",
            "quote": "内容方向是对的，把中介费按环节拆开比二选一更有用。但「剩下4步自己做更好」这个结论对信息素养高的人成立——对真的信息不对称的同学，某些环节还是需要专业支持。不加这个前提，容易误导人。",
            "text": "内容方向是对的，把中介费按环节拆开比二选一更有用。但「剩下4步自己做更好」这个结论对信息素养高的人成立——对真的信息不对称的同学，某些环节还是需要专业支持。不加这个前提，容易误导人。",
            "sentiment": "mixed",
            "concerns": ["结论过于绝对", "缺少适用前提"],
            "opportunities": ["补充边界条件会提高可信度"],
        },
        {
            "personaId": "returnee",
            "stance": "反感",
            "quote": "说实话，花多少中介费是次要的——真正的问题是得先搞清楚留学对你的长期价值是什么。我当时也精心规划每一分钱，结果回来发现海归溢价基本没有。只讲怎么花钱、不讲「值不值得花」，可能解决的是伪问题。",
            "text": "说实话，花多少中介费是次要的——真正的问题是得先搞清楚留学对你的长期价值是什么。我当时也精心规划每一分钱，结果回来发现海归溢价基本没有。只讲怎么花钱、不讲「值不值得花」，可能解决的是伪问题。",
            "sentiment": "negative",
            "concerns": ["留学长期ROI", "讨论可能跑偏到值不值得留学"],
            "opportunities": ["开头限定适用人群可以避免误读"],
        },
    ],
    "debate": [
        {
            "personaId": "anxious",
            "response": "@已出国的过来人 你说要加适用前提，但对我们这种信息不对称的人，这篇已经比那些「大概率要找中介」的内容好太多了。能把钱拆开说清楚，就是很大的进步了。",
            "text": "@已出国的过来人 你说要加适用前提，但对我们这种信息不对称的人，这篇已经比那些「大概率要找中介」的内容好太多了。能把钱拆开说清楚，就是很大的进步了。",
            "targetedAt": "experienced",
            "stance": "disagree",
            "changedMind": False,
            "newConcerns": [],
            "strongerSignals": ["分环节拆预算比二选一更有帮助"],
        },
        {
            "personaId": "experienced",
            "response": "@海归回国踩坑者 你说的ROI问题我理解，但这篇的受众本来就是「已决定要留学、在纠结怎么执行」的人，这时候再质疑留学值不值，不是这篇文章该解决的问题。批评角度对，但打错靶了。",
            "text": "@海归回国踩坑者 你说的ROI问题我理解，但这篇的受众本来就是「已决定要留学、在纠结怎么执行」的人，这时候再质疑留学值不值，不是这篇文章该解决的问题。批评角度对，但打错靶了。",
            "targetedAt": "returnee",
            "stance": "disagree",
            "changedMind": False,
            "newConcerns": ["需要限定文章适用范围"],
            "strongerSignals": ["清楚说明目标读者能减少跑题争议"],
        },
        {
            "personaId": "returnee",
            "response": "@已出国的过来人 我同意「打错靶」——我确实在用另一个问题回应这篇。但我觉得可以在开头加一句「你是否已确认留学适合你」作为前置，而不是默认所有人都已经想清楚了。",
            "text": "@已出国的过来人 我同意「打错靶」——我确实在用另一个问题回应这篇。但我觉得可以在开头加一句「你是否已确认留学适合你」作为前置，而不是默认所有人都已经想清楚了。",
            "targetedAt": "experienced",
            "stance": "nuanced",
            "changedMind": True,
            "newConcerns": ["默认读者已想清楚留学价值"],
            "strongerSignals": ["前置判断问题能提升内容成熟度"],
        },
    ],
    "synthesis": {
        "verdict": "值得做，最能打中正在纠结预算和执行方式的申请者。",
        "mainResistance": "「剩下4步自己做更好」容易被过来人认为过于绝对，也可能引出留学ROI跑题讨论。",
        "strongestAngle": "把中介费从二选一拆成按申请环节分配预算。",
        "contentAdjustments": [
            "开头加一行适用范围：「本篇适合已确认要出国、正在规划预算的同学」",
            "「自己做更好」改为「信息素养够的话可以自己做」，降低绝对感",
        ],
        "riskWarnings": [
            "避免暗示所有人都适合DIY",
            "不要默认读者已经确认留学长期价值",
        ],
        "topResonance": {
            "persona": "双非焦虑备考生（李明类）",
            "reason": "内容直接命中「钱该怎么花」的决策焦虑，给出了可执行的分配框架，这类读者最缺的就是具体方法",
            "expectedBehavior": "高收藏率、评论区会有人问「我这个情况该怎么选」",
        },
        "controversyPoints": [
            "「剩下4步自己做更好」——过来人群体可能认为这个结论过于绝对，会有评论「不一定，要看情况」",
            "海归回国群体可能在评论区引入留学ROI话题，让讨论跑偏",
        ],
        "suggestions": [
            "开头加一行适用范围：「本篇适合已确认要出国、正在规划预算的同学」",
            "「自己做更好」改为「信息素养够的话可以自己做」，降低绝对感",
            "预留评论区互动钩子，邀请过来人分享各环节实际花费，把争议变成内容资产",
        ],
    },
}

SAMPLE_SIMULATION_TREND = {
    "personas": [
        {
            "id": "wannabe",
            "name": "想转型的传统职场人",
            "archetype": "想转型的传统职场人",
            "profile": "大厂运营岗3年，月薪1.5万，想逃离格子间但不知道自己有没有可以远程的技能。焦虑但理性，对路径清单类内容收藏意愿极强。",
            "coreConcern": "自己够不够格、能不能养活自己、要不要冒险",
            "contentPreference": "具体路径、技能门槛、收入数字",
            "background": "大厂运营岗3年，月薪1.5万，想逃离格子间但不知道自己有没有可以远程的技能",
            "personality": "焦虑但理性，对「路径清单」类内容收藏意愿极强，容易被具体数字打动",
            "concerns": "自己够不够格、能不能养活自己、要不要冒险",
            "color": "#4f46e5",
        },
        {
            "id": "nomad",
            "name": "已实现的数字游民",
            "archetype": "已实现的数字游民",
            "profile": "曾做内容运营，现在做独立站+线上课，在巴厘岛旅居两年，月入2~4万不等。务实、不贩卖幻觉。",
            "coreConcern": "内容是否准确、有没有夸大路径的容易程度",
            "contentPreference": "真实门槛、失败成本、路径细节",
            "background": "曾做内容运营，现在做独立站+线上课，在巴厘岛旅居两年，月入2~4万不等",
            "personality": "务实、不贩卖幻觉，容易对「太容易」的描述反感，但会认可真实干货",
            "concerns": "内容是否准确、有没有夸大路径的容易程度",
            "color": "#16a34a",
        },
        {
            "id": "skeptic",
            "name": "理性风险厌恶者",
            "archetype": "理性风险厌恶者",
            "profile": "有稳定工作，对数字游民感兴趣但顾虑多，主要卡在收入空窗期怎么活。喜欢追问细节。",
            "coreConcern": "过渡期生活成本、失败兜底方案、收入稳定性",
            "contentPreference": "真实数据、冷启动周期、兜底方案",
            "background": "有稳定工作，对数字游民感兴趣但顾虑多，主要卡在「收入空窗期怎么活」",
            "personality": "喜欢追问细节，不轻易被励志叙事打动，但遇到真实数据会转变态度",
            "concerns": "过渡期生活成本、失败兜底方案、收入稳定性",
            "color": "#d97706",
        },
    ],
    "reactions": [
        {
            "personaId": "wannabe",
            "stance": "喜欢",
            "quote": "这篇完全说到我了！我一直以为数字游民必须会编程，原来还有这6条路径。线上教学和AI辅助服务那两条我觉得我能试，终于有一篇给出了具体方向而不是泛泛「你要有技能」。",
            "text": "这篇完全说到我了！我一直以为数字游民必须会编程，原来还有这6条路径。线上教学和AI辅助服务那两条我觉得我能试，终于有一篇给出了具体方向而不是泛泛「你要有技能」。",
            "sentiment": "positive",
            "concerns": ["不知道自己有没有远程技能"],
            "opportunities": ["路径清单会触发高收藏"],
        },
        {
            "personaId": "nomad",
            "stance": "犹豫",
            "quote": "方向是对的，这6条路径我身边都有人在走。但有几条写得太轻松了——比如「跨境电商运营」，光选品测品就能让人半年没收入。如果不加门槛说明，容易让人低估实际难度。",
            "text": "方向是对的，这6条路径我身边都有人在走。但有几条写得太轻松了——比如「跨境电商运营」，光选品测品就能让人半年没收入。如果不加门槛说明，容易让人低估实际难度。",
            "sentiment": "mixed",
            "concerns": ["路径门槛被低估", "收入冷启动周期被忽略"],
            "opportunities": ["补充门槛说明能获得老手认可"],
        },
        {
            "personaId": "skeptic",
            "stance": "犹豫",
            "quote": "内容有价值，但我最想知道的没有说——转型初期没有稳定收入的那几个月怎么过？这6条路径每条「初期能赚多少」「多久才能达到稳定收入」没有回答，对我这种有房贷的人来说，这才是真正的决策门槛。",
            "text": "内容有价值，但我最想知道的没有说——转型初期没有稳定收入的那几个月怎么过？这6条路径每条「初期能赚多少」「多久才能达到稳定收入」没有回答，对我这种有房贷的人来说，这才是真正的决策门槛。",
            "sentiment": "mixed",
            "concerns": ["收入空窗期", "多久达到稳定收入"],
            "opportunities": ["真实账单和冷启动周期可以成为下一篇"],
        },
    ],
    "debate": [
        {
            "personaId": "wannabe",
            "response": "@已实现的数字游民 你说写得太容易，那你觉得6条里哪一条是最被夸大的？我想在决定走哪条之前先把坑搞清楚。",
            "text": "@已实现的数字游民 你说写得太容易，那你觉得6条里哪一条是最被夸大的？我想在决定走哪条之前先把坑搞清楚。",
            "targetedAt": "nomad",
            "stance": "nuanced",
            "changedMind": False,
            "newConcerns": ["哪条路径最容易被夸大"],
            "strongerSignals": ["坑点说明会提升信任"],
        },
        {
            "personaId": "nomad",
            "response": "@理性风险厌恶者 你说的启动成本问题我完全同意——这其实就是这篇缺失的「第二篇」。作者如果能出一篇「转型第一年真实账单」，把每条路径的冷启动周期和最低生活成本写清楚，两篇放在一起才是完整的入门指南。",
            "text": "@理性风险厌恶者 你说的启动成本问题我完全同意——这其实就是这篇缺失的「第二篇」。作者如果能出一篇「转型第一年真实账单」，把每条路径的冷启动周期和最低生活成本写清楚，两篇放在一起才是完整的入门指南。",
            "targetedAt": "skeptic",
            "stance": "agree",
            "changedMind": False,
            "newConcerns": ["需要补充转型第一年真实账单"],
            "strongerSignals": ["系列化内容更完整"],
        },
        {
            "personaId": "skeptic",
            "response": "@已实现的数字游民 你说得对，这篇适合当「方向地图」，不适合当「执行手册」。@想转型的传统职场人 建议你把这篇和一篇真实成本拆解一起看，两个结合才能做出理性决策。",
            "text": "@已实现的数字游民 你说得对，这篇适合当「方向地图」，不适合当「执行手册」。@想转型的传统职场人 建议你把这篇和一篇真实成本拆解一起看，两个结合才能做出理性决策。",
            "targetedAt": "wannabe",
            "stance": "nuanced",
            "changedMind": True,
            "newConcerns": ["方向地图不能替代执行手册"],
            "strongerSignals": ["成本拆解能降低决策风险"],
        },
    ],
    "synthesis": {
        "verdict": "值得做，适合作为数字游民入门系列的第一篇方向地图。",
        "mainResistance": "路径清单容易让人低估真实门槛，风险厌恶者会继续追问收入空窗期和失败兜底。",
        "strongestAngle": "把「没有远程技能」拆成六条具体可验证路径。",
        "contentAdjustments": [
            "每条路径加上初期月收入区间和达到稳定需要多久",
            "结尾明确下一篇会拆转型第一年真实账单",
        ],
        "riskWarnings": [
            "不要把跨境电商、独立站等路径写得过轻松",
            "避免制造裸辞即可自由的幻觉",
        ],
        "topResonance": {
            "persona": "想转型的传统职场人",
            "reason": "内容精准命中「我没有远程技能怎么办」这个最高频入门卡点，给了可选择的方向清单，这类读者最缺的就是从0到1的路径感",
            "expectedBehavior": "高收藏、评论区会有大量「我适合走哪条」的提问",
        },
        "controversyPoints": [
            "「6条路径」的表述可能让人觉得门槛很低，已实现的数字游民群体可能评论「没那么简单」",
            "跨境电商和独立站路径竞争激烈，老手可能在评论区泼冷水",
        ],
        "suggestions": [
            "每条路径加上「初期月收入区间」和「达到稳定需要多久」的具体数字，让内容从「方向地图」升级为「决策依据」",
            "结尾推荐下一篇选题：「转型第一年真实账单」，形成系列，同时回应评论区的核心疑问",
        ],
    },
}


def simulation_demo_sample(
    *, positioning: str, topic: dict[str, Any]
) -> dict[str, Any]:
    text = " ".join(
        [
            positioning,
            str(topic.get("title", "")),
            str(topic.get("angle", "")),
            str(topic.get("sourceWorkflow", "")),
        ]
    )
    if "数字游民" in text or topic.get("sourceWorkflow") == "trend_analysis":
        return deepcopy(SAMPLE_SIMULATION_TREND)
    return deepcopy(SAMPLE_SIMULATION_ACCOUNT)


class FakeAudienceSimulationModelProvider:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.calls: list[str] = []

    async def personas(
        self, *, positioning: str, topic: dict[str, Any]
    ) -> dict[str, Any]:
        self.calls.append("personas")
        if "personas" in self.failures:
            raise RuntimeError("personas failed")
        return {
            "personas": simulation_demo_sample(
                positioning=positioning, topic=topic
            )["personas"]
        }

    async def initial_reaction(
        self, *, persona: dict[str, Any], topic: dict[str, Any]
    ) -> dict[str, Any]:
        persona_id = str(persona.get("id", ""))
        self.calls.append(f"reaction:{persona_id}")
        if f"reaction:{persona_id}" in self.failures or "reaction" in self.failures:
            raise RuntimeError(f"reaction failed for {persona_id}")
        sample = simulation_demo_sample(positioning="", topic=topic)
        reaction = next(
            item for item in sample["reactions"] if item["personaId"] == persona_id
        )
        return {"reaction": reaction}

    async def debate_response(
        self,
        *,
        persona: dict[str, Any],
        topic: dict[str, Any],
        other_reactions: list[dict[str, Any]],
        prior_reaction: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        persona_id = str(persona.get("id", ""))
        self.calls.append(f"debate:{persona_id}")
        if f"debate:{persona_id}" in self.failures or "debate" in self.failures:
            raise RuntimeError(f"debate failed for {persona_id}")
        sample = simulation_demo_sample(positioning="", topic=topic)
        debate = next(
            item for item in sample["debate"] if item["personaId"] == persona_id
        )
        target = next((r for r in other_reactions if r["personaId"] == debate.get("targetedAt")),
                      other_reactions[0] if other_reactions else None)
        return {"debateResponse": {
            **debate, "replyToId": target["messageId"] if target else None,
            "changeReason": "示例中的公开回应补充了可操作的步骤。" if debate.get("changedMind") else "",
        }}

    async def synthesis(
        self,
        *,
        topic: dict[str, Any],
        personas: list[dict[str, Any]],
        reactions: list[dict[str, Any]],
        debate_responses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append("synthesis")
        if "synthesis" in self.failures:
            raise RuntimeError("synthesis failed")
        return {
            "synthesis": simulation_demo_sample(positioning="", topic=topic)[
                "synthesis"
            ]
        }


class RealAudienceSimulationModelProvider:
    def __init__(self, model_call_service: ModelCallService) -> None:
        self.model_call_service = model_call_service

    async def personas(
        self, *, positioning: str, topic: dict[str, Any]
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.SIMULATION_PERSONAS,
            {"positioning": positioning, "topic": topic},
        )
        return response.output

    async def initial_reaction(
        self, *, persona: dict[str, Any], topic: dict[str, Any]
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.SIMULATION_REACTION,
            {"persona": persona, "topic": topic},
        )
        return response.output

    async def debate_response(
        self,
        *,
        persona: dict[str, Any],
        topic: dict[str, Any],
        other_reactions: list[dict[str, Any]],
        prior_reaction: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.SIMULATION_DEBATE,
            {
                "persona": persona,
                "topic": topic,
                "otherReactions": other_reactions,
                "priorReaction": prior_reaction,
            },
        )
        return response.output

    async def synthesis(
        self,
        *,
        topic: dict[str, Any],
        personas: list[dict[str, Any]],
        reactions: list[dict[str, Any]],
        debate_responses: list[dict[str, Any]],
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.SIMULATION_SYNTHESIS,
            {
                "topic": topic,
                "personas": personas,
                "reactions": reactions,
                "debateResponses": debate_responses,
            },
        )
        return response.output


class AudienceSimulationWorkflowService:
    def __init__(
        self,
        *,
        database: SQLiteDatabase,
        checkpoint_repository: GraphCheckpointRepository,
        simulation_service: SimulationRunService,
        fake_provider: AudienceSimulationModelProvider,
        live_provider: AudienceSimulationModelProvider,
    ) -> None:
        self.database = database
        self.checkpoint_repository = checkpoint_repository
        self.simulation_service = simulation_service
        self.fake_provider = fake_provider
        self.live_provider = live_provider
        self.graph = self._build_graph()

    def initial_state_for_run(self, simulation_id: str) -> AudienceSimulationState:
        run = self.simulation_service.get(simulation_id)
        snapshot = run.input_snapshot
        return AudienceSimulationState(
            simulation_id=run.id,
            workspace_id=run.workspace_id,
            topic_id=run.topic_id,
            positioning_snapshot=str(snapshot["accountPositioning"]),
            topic=self._simulation_target_context(snapshot),
            personas=run.persona_definitions,
            initial_reactions=run.reaction_results,
            debate_responses=run.debate_results,
            synthesis=run.synthesis,
            stage_errors=run.stage_errors,
        )

    @staticmethod
    def _simulation_target_context(snapshot: dict[str, Any]) -> dict[str, Any]:
        topic = snapshot["topic"]
        target = {
            "targetType": snapshot.get("targetType", "topic"),
            "title": topic.get("title", ""),
            "body": topic.get("body", ""),
            "previewLevel": "text_draft" if topic.get("body") else "concept",
            "limitations": "仅预演提供的文字，不评价未提供的图片或真实传播效果。",
        }
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
            target["draft"] = {
                "editableContent": visible,
            }
            target["previewLevel"] = "outline"
        return target

    async def stream_events(
        self, simulation_id: str, *, stop_after_node: str | None = None
    ) -> AsyncIterator[SimulationActivityEvent]:
        queue: asyncio.Queue[SimulationActivityEvent | None] = asyncio.Queue()
        runner = _AudienceSimulationGraphExecution(
            service=self,
            simulation_id=simulation_id,
            queue=queue,
            stop_after_node=stop_after_node,
        )
        task = asyncio.create_task(runner.run())
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
            await task
        finally:
            if not task.done():
                task.cancel()

    async def collect_events(
        self, simulation_id: str, *, stop_after_node: str | None = None
    ) -> list[SimulationActivityEvent]:
        return [
            event
            async for event in self.stream_events(
                simulation_id, stop_after_node=stop_after_node
            )
        ]

    def _build_graph(self):
        builder = StateGraph(AudienceSimulationState)
        builder.add_node("derive_personas", self._derive_personas)
        builder.add_node("parallel_initial_reactions", self._parallel_initial_reactions)
        builder.add_node("parallel_debate_responses", self._parallel_debate_responses)
        builder.add_node("synthesis", self._synthesis)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "derive_personas")
        builder.add_edge("derive_personas", "parallel_initial_reactions")
        builder.add_edge("parallel_initial_reactions", "parallel_debate_responses")
        builder.add_edge("parallel_debate_responses", "synthesis")
        builder.add_edge("synthesis", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile()

    async def _derive_personas(
        self, state: AudienceSimulationState
    ) -> AudienceSimulationState:
        return await _AudienceSimulationGraphExecution.current().derive_personas(state)

    async def _parallel_initial_reactions(
        self, state: AudienceSimulationState
    ) -> AudienceSimulationState:
        return await _AudienceSimulationGraphExecution.current().initial_reactions(state)

    async def _parallel_debate_responses(
        self, state: AudienceSimulationState
    ) -> AudienceSimulationState:
        return await _AudienceSimulationGraphExecution.current().debate_responses(state)

    async def _synthesis(self, state: AudienceSimulationState) -> AudienceSimulationState:
        return await _AudienceSimulationGraphExecution.current().synthesis(state)

    async def _finalize(self, state: AudienceSimulationState) -> AudienceSimulationState:
        return await _AudienceSimulationGraphExecution.current().finalize(state)


class _AudienceSimulationGraphExecution:
    def __init__(
        self,
        *,
        service: AudienceSimulationWorkflowService,
        simulation_id: str,
        queue: asyncio.Queue[SimulationActivityEvent | None],
        stop_after_node: str | None,
    ) -> None:
        self.service = service
        self.simulation_id = simulation_id
        self.queue = queue
        self.stop_after_node = stop_after_node
        self.sequence = 0

    @classmethod
    def current(cls) -> _AudienceSimulationGraphExecution:
        active = ACTIVE_SIMULATION_EXECUTION.get()
        if active is None:
            raise RuntimeError("No active audience simulation graph execution")
        return active

    async def run(self) -> None:
        token = ACTIVE_SIMULATION_EXECUTION.set(self)
        try:
            run = self.service.simulation_service.get(self.simulation_id)
            if run.status.value in SIMULATION_TERMINAL_STATUSES:
                await self._emit_existing_terminal_run(run)
                return
            await self.emit("run.created", None, run.status.value, {})
            if run.status == SimulationRunStatus.PENDING:
                self.service.simulation_service.save_progress(
                    self.simulation_id,
                    status=SimulationRunStatus.RUNNING,
                    model_metadata={"engine": "langgraph"},
                )
            await self.emit("run.started", None, "running", {})
            try:
                await self.service.graph.ainvoke(
                    self.service.initial_state_for_run(self.simulation_id),
                    config={"configurable": {"thread_id": self.simulation_id}},
                )
            except GraphExecutionPaused:
                return
        finally:
            ACTIVE_SIMULATION_EXECUTION.reset(token)
            await self.queue.put(None)

    async def derive_personas(
        self, state: AudienceSimulationState
    ) -> AudienceSimulationState:
        updated = dict(state)
        if updated.get("personas"):
            await self.save_checkpoint("derive_personas", updated)
            return AudienceSimulationState(**updated)
        await self.emit("stage.started", "personas", "running", {})
        try:
            saved_personas = self.service.simulation_service.get(self.simulation_id).input_snapshot.get('audiencePersonas')
            output = {'personas': saved_personas} if saved_personas else await self.provider().personas(
                positioning=updated["positioning_snapshot"], topic=updated["topic"],
            )
            if not saved_personas:
                for persona in output.get("personas", []):
                    persona.update(evidence=[], evidenceRefs=[], observedEpisodes=[], evidenceStatus="hypothesis",
                                   limitations="未使用已核验的受众分析，仅为假设性阅读视角。")
            result = PersonaDefinitionsResult.model_validate(output).model_dump(
                mode="json", by_alias=True
            )
            result["personas"] = [reader_persona_context(p, updated["topic"])
                                  for p in result["personas"]]
            updated["personas"] = result["personas"]
            self.service.simulation_service.save_progress(
                self.simulation_id,
                status=SimulationRunStatus.RUNNING,
                persona_definitions=result["personas"],
                model_metadata={"engine": "langgraph"},
            )
            await self.emit("stage.succeeded", "personas", "completed", result)
        except Exception as error:
            await self.stage_failed("personas", error, updated)
        await self.save_checkpoint("derive_personas", updated)
        return AudienceSimulationState(**updated)

    async def initial_reactions(
        self, state: AudienceSimulationState
    ) -> AudienceSimulationState:
        updated = dict(state)
        personas = updated.get("personas") or []
        if updated.get("initial_reactions") or not personas:
            await self.save_checkpoint("parallel_initial_reactions", updated)
            return AudienceSimulationState(**updated)
        await self.emit("stage.started", "initial_reactions", "running", {})

        async def run_one(persona: dict[str, Any]) -> dict[str, Any] | None:
            persona_id = str(persona.get("id", "unknown"))
            try:
                output = await self.retry(
                    lambda: self.provider().initial_reaction(
                        persona=persona, topic=updated["topic"]
                    )
                )
                result = PersonaReactionResult.model_validate(output).model_dump(
                    mode="json"
                )
                if result["reaction"]["personaId"] != persona_id:
                    raise ValueError("反应角色与请求不一致")
                validate_trigger_quote(result["reaction"]["triggerQuote"], updated["topic"])
                result["reaction"].update(messageId=f"initial:{persona_id}", round=1)
                return result["reaction"]
            except Exception as error:
                updated.setdefault("stage_errors", {})[
                    f"initial_reactions.{persona_id}"
                ] = self.error_message(error)
                return None

        results = await asyncio.gather(*(run_one(persona) for persona in personas))
        reactions = [result for result in results if result is not None]
        updated["initial_reactions"] = reactions
        self.service.simulation_service.save_progress(
            self.simulation_id,
            status=SimulationRunStatus.RUNNING,
            reaction_results=reactions,
            stage_errors=updated.get("stage_errors", {}),
            model_metadata={"engine": "langgraph"},
        )
        if reactions:
            await self.emit(
                "stage.succeeded",
                "initial_reactions",
                "completed",
                {"reactions": reactions},
            )
        else:
            await self.emit(
                "stage.failed",
                "initial_reactions",
                "failed",
                {"error": "All persona reactions failed"},
            )
        await self.save_checkpoint("parallel_initial_reactions", updated)
        return AudienceSimulationState(**updated)

    async def debate_responses(
        self, state: AudienceSimulationState
    ) -> AudienceSimulationState:
        updated = dict(state)
        personas = updated.get("personas") or []
        reactions = updated.get("initial_reactions") or []
        public_comments = public_reactions(reactions)
        prior_by_id = {str(r["personaId"]): r for r in reactions}
        debate_personas = [
            persona for persona in personas
            if str(persona.get("id", "")) in prior_by_id
            and any(p["personaId"] != persona["id"] for p in public_comments)
        ]
        if updated.get("debate_responses"):
            await self.save_checkpoint("parallel_debate_responses", updated)
            return AudienceSimulationState(**updated)
        if not debate_personas:
            await self.emit("stage.succeeded", "debate_responses", "completed", {
                "debateResponses": [], "skippedReason": DISCUSSION_SKIPPED_REASON,
            })
            await self.save_checkpoint("parallel_debate_responses", updated)
            return AudienceSimulationState(**updated)
        await self.emit("stage.started", "debate_responses", "running", {})

        async def run_one(persona: dict[str, Any]) -> dict[str, Any] | None:
            persona_id = str(persona.get("id", "unknown"))
            others = [
                reaction
                for reaction in public_comments
                if str(reaction.get("personaId", "")) != persona_id
            ]
            try:
                output = await self.retry(
                    lambda: self.provider().debate_response(
                        persona=persona,
                        topic=updated["topic"],
                        other_reactions=others,
                        prior_reaction=prior_by_id[persona_id],
                    )
                )
                result = DebateResponseResult.model_validate(output).model_dump(
                    mode="json"
                )
                if result["debateResponse"]["personaId"] != persona_id:
                    raise ValueError("回应角色与请求不一致")
                response = result["debateResponse"]
                visible = {r["messageId"]: r for r in others}
                if (response["response"] or response["text"]).strip():
                    if response["replyToId"] not in visible:
                        raise ValueError("回应对象不是本轮可见的公开评论")
                    response["targetedAt"] = visible[response["replyToId"]]["personaId"]
                    if response["changedMind"] and not response["changeReason"].strip():
                        raise ValueError("观点改变缺少具体说明")
                response.update(messageId=f"reply:{persona_id}", round=2,
                                visibleMessageIds=list(visible))
                return response
            except Exception as error:
                updated.setdefault("stage_errors", {})[
                    f"debate_responses.{persona_id}"
                ] = self.error_message(error)
                return None

        results = await asyncio.gather(*(run_one(persona) for persona in debate_personas))
        debate_responses = [result for result in results if result is not None]
        updated["debate_responses"] = debate_responses
        self.service.simulation_service.save_progress(
            self.simulation_id,
            status=SimulationRunStatus.RUNNING,
            debate_results=debate_responses,
            stage_errors=updated.get("stage_errors", {}),
            model_metadata={"engine": "langgraph"},
        )
        if debate_responses:
            await self.emit(
                "stage.succeeded",
                "debate_responses",
                "completed",
                {"debateResponses": debate_responses},
            )
        else:
            await self.emit(
                "stage.failed",
                "debate_responses",
                "failed",
                {"error": "All debate responses failed"},
            )
        await self.save_checkpoint("parallel_debate_responses", updated)
        return AudienceSimulationState(**updated)

    async def synthesis(
        self, state: AudienceSimulationState
    ) -> AudienceSimulationState:
        updated = dict(state)
        if updated.get("synthesis"):
            await self.save_checkpoint("synthesis", updated)
            return AudienceSimulationState(**updated)
        if not updated.get("initial_reactions"):
            await self.save_checkpoint("synthesis", updated)
            return AudienceSimulationState(**updated)
        await self.emit("stage.started", "synthesis", "running", {})
        try:
            output = await self.provider().synthesis(
                topic=updated["topic"],
                personas=updated.get("personas", []),
                reactions=updated.get("initial_reactions", []),
                debate_responses=updated.get("debate_responses", []),
            )
            result = SimulationSynthesisResult.model_validate(output).model_dump(
                mode="json"
            )
            updated["synthesis"] = result["synthesis"]
            self.service.simulation_service.save_progress(
                self.simulation_id,
                status=SimulationRunStatus.RUNNING,
                synthesis=result["synthesis"],
                stage_errors=updated.get("stage_errors", {}),
                model_metadata={"engine": "langgraph"},
            )
            await self.emit("stage.succeeded", "synthesis", "completed", result)
        except Exception as error:
            await self.stage_failed("synthesis", error, updated)
        await self.save_checkpoint("synthesis", updated)
        return AudienceSimulationState(**updated)

    async def finalize(
        self, state: AudienceSimulationState
    ) -> AudienceSimulationState:
        updated = dict(state)
        run = self.service.simulation_service.get(self.simulation_id)
        has_errors = bool(run.stage_errors)
        has_results = bool(
            run.persona_definitions
            or run.reaction_results
            or run.debate_results
            or run.synthesis
        )
        if has_errors and has_results:
            status = SimulationRunStatus.PARTIALLY_COMPLETED
            event_type = "run.partial"
        elif has_errors:
            status = SimulationRunStatus.FAILED
            event_type = "run.failed"
        else:
            status = SimulationRunStatus.COMPLETED
            event_type = "run.succeeded"
        completed = self.service.simulation_service.save_progress(
            self.simulation_id,
            status=status,
            model_metadata={"engine": "langgraph"},
            complete=True,
        )
        await self.save_checkpoint("finalize", updated)
        await self.emit(
            event_type,
            None,
            completed.status.value,
            {
                "personaDefinitions": completed.persona_definitions,
                "reactionResults": completed.reaction_results,
                "debateResults": completed.debate_results,
                "synthesis": completed.synthesis,
                "stageErrors": completed.stage_errors,
            },
        )
        return AudienceSimulationState(**updated)

    def provider(self) -> AudienceSimulationModelProvider:
        run = self.service.simulation_service.get(self.simulation_id)
        if run.input_snapshot.get("mode") == "live":
            return self.service.live_provider
        return self.service.fake_provider

    async def stage_failed(
        self, stage_key: str, error: Exception, state: dict[str, Any]
    ) -> None:
        message = self.error_message(error)
        state.setdefault("stage_errors", {})[stage_key] = message
        self.service.simulation_service.save_progress(
            self.simulation_id,
            status=SimulationRunStatus.RUNNING,
            stage_errors=state.get("stage_errors", {}),
            model_metadata={"engine": "langgraph"},
        )
        await self.emit("stage.failed", stage_key, "failed", {"error": message})

    async def retry(
        self, call: Callable[[], Awaitable[dict[str, Any]]], *, attempts: int = 2
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for _attempt in range(attempts):
            try:
                return await call()
            except Exception as error:
                last_error = error
        if last_error is None:
            raise RuntimeError("retry failed without an exception")
        raise last_error

    async def save_checkpoint(self, node_key: str, state: dict[str, Any]) -> None:
        checkpoint_state = {
            "simulation_id": state.get("simulation_id"),
            "workspace_id": state.get("workspace_id"),
            "topic_id": state.get("topic_id"),
            "topic": state.get("topic"),
            "personas": state.get("personas", []),
            "initial_reactions": state.get("initial_reactions", []),
            "debate_responses": state.get("debate_responses", []),
            "synthesis": state.get("synthesis", {}),
            "stage_errors": state.get("stage_errors", {}),
        }
        with self.service.database.transaction() as connection:
            self.service.checkpoint_repository.save(
                connection,
                analysis_run_id=self.simulation_id,
                workflow_type="audience_simulation",
                node_key=node_key,
                state=checkpoint_state,
                now=utc_now(),
            )
        if self.stop_after_node == node_key:
            raise GraphExecutionPaused()

    async def emit(
        self,
        event_type: str,
        stage_key: str | None,
        status: str,
        data: dict[str, Any],
    ) -> None:
        self.sequence += 1
        await self.queue.put(
            SimulationActivityEvent(
                eventId=str(uuid4()),
                runId=self.simulation_id,
                runType="audience_simulation",
                stageKey=stage_key,
                status=status,
                sequence=self.sequence,
                occurredAt=utc_now(),
                data={"eventType": event_type, **data},
            )
        )

    async def _emit_existing_terminal_run(self, run) -> None:
        if run.persona_definitions:
            await self.emit(
                "stage.succeeded",
                "personas",
                "completed",
                {"personas": run.persona_definitions},
            )
        if run.reaction_results:
            await self.emit(
                "stage.succeeded",
                "initial_reactions",
                "completed",
                {"reactions": run.reaction_results},
            )
        if run.debate_results:
            await self.emit(
                "stage.succeeded",
                "debate_responses",
                "completed",
                {"debateResponses": run.debate_results},
            )
        if run.synthesis:
            await self.emit(
                "stage.succeeded",
                "synthesis",
                "completed",
                {"synthesis": run.synthesis},
            )
        for key, message in run.stage_errors.items():
            await self.emit("stage.failed", key, "failed", {"error": message})
        event_type = (
            "run.succeeded"
            if run.status == SimulationRunStatus.COMPLETED
            else "run.partial"
            if run.status == SimulationRunStatus.PARTIALLY_COMPLETED
            else "run.failed"
        )
        await self.emit(
            event_type,
            None,
            run.status.value,
            {
                "personaDefinitions": run.persona_definitions,
                "reactionResults": run.reaction_results,
                "debateResults": run.debate_results,
                "synthesis": run.synthesis,
                "stageErrors": run.stage_errors,
            },
        )

    @staticmethod
    def error_message(error: Exception) -> str:
        if isinstance(error, PydanticValidationError):
            return "Model response failed structured validation"
        if isinstance(error, (ValidationError, ConflictError)):
            return str(error)
        return str(error) or error.__class__.__name__
