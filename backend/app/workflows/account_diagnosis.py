from __future__ import annotations

import asyncio
import contextvars
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, model_serializer, model_validator
from pydantic import ValidationError as PydanticValidationError

from app.db.database import SQLiteDatabase
from app.errors import ConflictError, ValidationError
from app.models import (
    AnalysisRunStatus,
    AnalysisRunTransition,
    AnalysisStageUpdate,
    ModelCallResponse,
    ModelOperation,
    WorkflowType,
)
from app.repositories.analysis_runs import TERMINAL_STATUSES, AnalysisRunRepository
from app.repositories.graph_checkpoints import GraphCheckpointRepository
from app.services.account_diagnosis_evidence import (
    profile_stage_input,
    topic_profile_context,
    verified_portrait,
)
from app.services.account_profile_shape import normalize_profile_stage_result
from app.services.account_report_contract import AccountReportOutputError
from app.services.account_report_delivery import compile_usable_account_report
from app.services.analysis_runs import AnalysisRunService
from app.services.common import utc_now
from app.services.model_calls import ModelCallService, safe_token_usage
from app.services.run_events import RunEvent, RunEventEmitter, RunEventType
from app.services.xhs_comment_roles import reader_comments_text

ACCOUNT_GRAPH_NODE_ORDER = [
    "profile_analysis",
    "topic_generation",
    "finalize",
]
ACCOUNT_STAGE_ORDER = ["profile", "pain_points", "topics"]
ACCOUNT_REPORT_RETRY_EXHAUSTED_MESSAGE = (
    "已自动重试，仍未取得完整账号报告，请重试分析。"
)
ACCOUNT_REPORT_INCOMPLETE_MESSAGE = "暂未取得完整账号报告，请重试分析。"
_REPORT_USAGE_KEYS = (
    "prompt_tokens", "completion_tokens", "total_tokens", "reasoning_tokens",
    "input_tokens", "output_tokens",
)
_REPORT_ERROR_CODES = {
    "output_truncated", "empty_output", "invalid_json", "invalid_response",
    "schema_validation", "source_validation", "request_failed", "processing_failed",
}
ACTIVE_EXECUTION: contextvars.ContextVar[
    _AccountDiagnosisGraphExecution | None
] = contextvars.ContextVar("account_diagnosis_execution", default=None)


def _account_call_metadata(value: dict[str, Any]) -> dict[str, Any]:
    """Keep the provider receipt, not arbitrary data returned by a provider."""
    result = {
        key: value[key] for key in (
            "provider", "operation", "model", "modelSource", "systemPromptHash",
            "responseFormat", "promptVersion",
        )
        if isinstance(value.get(key), str)
        and re.fullmatch(r"[A-Za-z0-9_./:-]{1,160}", value[key])
    }
    for key in ("thinkingBudget", "requestCount"):
        if type(value.get(key)) is int and value[key] >= 0:
            result[key] = value[key]
    if type(value.get("enableThinking")) is bool:
        result["enableThinking"] = value["enableThinking"]
    if isinstance(value.get("usage"), dict):
        result["usage"] = safe_token_usage(value["usage"])
    return result


def _safe_report_failure_metadata(value: Any) -> dict[str, Any]:
    """Persist execution counters, never arbitrary exception/provider contents."""
    if not isinstance(value, dict):
        return {}

    def counters(source: Any, keys: tuple[str, ...]) -> dict[str, int]:
        if not isinstance(source, dict):
            return {}
        return {key: source[key] for key in keys
                if type(source.get(key)) is int and source[key] >= 0}

    def identifiers(source: dict, keys: tuple[str, ...]) -> dict[str, str]:
        return {key: source[key] for key in keys
                if isinstance(source.get(key), str)
                and re.fullmatch(r"[A-Za-z0-9_./:-]{1,160}", source[key])}

    result: dict[str, Any] = identifiers(value, ("promptVersion",))
    if value.get("accountReportMode") == "staged":
        result["accountReportMode"] = "staged"
    result.update(counters(value, ("requestCount", "retryCount")))
    result.update(counters(value, ("omissionCount",)))
    for field in ("omittedStages", "degradedStages"):
        if isinstance(value.get(field), dict):
            result[field] = counters(value[field], ("overview", "read", "synthesis"))
    if isinstance(value.get("usage"), dict):
        result["usage"] = counters(value["usage"], _REPORT_USAGE_KEYS)
    if isinstance(value.get("calls"), list):
        calls = []
        for call in value["calls"]:
            if not isinstance(call, dict):
                continue
            if call.get("stage") not in ("overview", "read", "synthesis"):
                continue
            if call.get("status") not in ("completed", "failed", "cancelled", "omitted"):
                continue
            safe: dict[str, Any] = {"stage": call["stage"], "status": call["status"]}
            safe.update(counters(call, ("attempt", "requestIndex", "omittedItemCount")))
            safe.update(identifiers(call, ("noteId",)))
            if (isinstance(call.get("errorCode"), str)
                    and call["errorCode"] in _REPORT_ERROR_CODES):
                safe["errorCode"] = call["errorCode"]
            if type(call.get("usageUnavailable")) is bool:
                safe["usageUnavailable"] = call["usageUnavailable"]
            source = call.get("metadata")
            if isinstance(source, dict):
                metadata = identifiers(source, (
                    "provider", "operation", "stage", "model", "profileModel", "modelSource",
                    "responseFormat", "responseSchema", "systemPromptHash",
                ))
                metadata.update(counters(source, ("thinkingBudget",)))
                if type(source.get("enableThinking")) is bool:
                    metadata["enableThinking"] = source["enableThinking"]
                if isinstance(source.get("usage"), dict):
                    metadata["usage"] = counters(source["usage"], _REPORT_USAGE_KEYS)
                safe["metadata"] = metadata
            calls.append(safe)
        result["calls"] = calls
    return result


class AccountDiagnosisState(TypedDict, total=False):
    run_id: str
    workspace_id: str
    positioning_snapshot: str
    historical_posts_material_id: str
    comments_material_id: str
    profile: dict[str, Any]
    pain_points: list[dict[str, Any]]
    topics: list[dict[str, Any]]
    titles: list[dict[str, Any]]
    stage_errors: dict[str, str]
    completed_nodes: list[str]


class TitleFormula(BaseModel):
    formula: str = ""
    examples: list[str] = Field(default_factory=list)


class ViralStructure(BaseModel):
    name: str = ""
    steps: list[str] = Field(default_factory=list)
    kind: Literal["narrative", "comparison", "repeated_blocks"] | None = None
    scope: Literal["whole_note", "section"] | None = None
    scopeLabel: str | None = None
    overview: str | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_shape(self, handler):
        values = handler(self)
        for field in ("kind", "scope", "scopeLabel", "overview"):
            if field not in self.model_fields_set:
                values.pop(field, None)
        return values


class ProfileData(BaseModel):
    accountPortrait: dict[str, Any] | None = None
    pillars: list[str] = Field(default_factory=list)
    titleFormulas: list[TitleFormula] = Field(default_factory=list)
    hookStyles: list[str] = Field(default_factory=list)
    viralStructure: ViralStructure = Field(default_factory=ViralStructure)
    voiceFingerprint: list[str] = Field(default_factory=list)
    contrast: dict[str, Any] = Field(default_factory=dict)


class ProfileStageResult(BaseModel):
    profile: ProfileData

    @model_validator(mode="before")
    @classmethod
    def normalize_known_nesting(cls, value):
        return normalize_profile_stage_result(value)


class PainPoint(BaseModel):
    theme: str
    intensity: str
    count: int
    evidence: list[str] = Field(default_factory=list)


class PainPointsStageResult(BaseModel):
    painPoints: list[PainPoint]


class TopicItem(BaseModel):
    title: str
    angle: str = ""
    pain: str = ""
    whyFit: str = ""
    whyTrending: str | None = None
    pendingSuggestions: list[str] = Field(default_factory=list)


class TitleVariants(BaseModel):
    topic: str
    variants: list[str] = Field(default_factory=list)


class TopicsStageResult(BaseModel):
    topics: list[TopicItem]
    titles: list[TitleVariants] = Field(default_factory=list)


class StructureOutlineItem(BaseModel):
    sec: str
    ct: str


class StructureData(BaseModel):
    topicChosen: str
    outline: list[StructureOutlineItem] = Field(default_factory=list)
    reuse: str = ""


class StructureStageResult(BaseModel):
    structure: StructureData


class AccountDiagnosisModelProvider(Protocol):
    async def profile(
        self, *, positioning: str, historical_posts: str
    ) -> dict[str, Any]: ...

    async def pain_points(self, *, comments: str) -> dict[str, Any]: ...

    async def topics(
        self,
        *,
        positioning: str,
        profile: dict[str, Any] | None,
        pain_points: list[dict[str, Any]] | None,
    ) -> dict[str, Any]: ...

SAMPLE_ACCOUNT_RESULT = {
    "profile": {
        "pillars": ["留学决策反思", "申请避坑", "背景评估方法论"],
        "titleFormulas": [
            {
                "formula": "反预期否定式",
                "examples": ["二本逆袭G5?别再被这种标题骗了"],
            },
            {
                "formula": "价值拷问 + 真实账单",
                "examples": ["留学中介到底值不值5万块|我的真实账单与避坑清单"],
            },
        ],
        "hookStyles": ["亲历者第一人称切入，先认同情绪再反转", "用具体数字制造真实感"],
        "viralStructure": {
            "name": "避坑清单体",
            "steps": ["反直觉钩子", "立靶", "亲历账单", "逐条拆解", "可保存清单", "反问互动"],
        },
        "voiceFingerprint": ["不贩卖焦虑", "把模糊焦虑拆成可执行步骤", "克制真诚"],
        "contrast": {
            "winners": [
                {"title": "二本逆袭G5?别再被这种标题骗了", "metric": "赞1.4k·藏980"},
                {"title": "留学中介到底值不值5万块", "metric": "赞1.1k·藏860"},
            ],
            "losers": [{"title": "DIY申请时间线", "metric": "赞60·藏150"}],
            "winFactors": ["选题踩在决策纠结点", "标题带具体数字或反预期钩子"],
            "loseFactors": ["流程工具传播弱，需要更强情绪钩子"],
            "takeaways": ["优先做决策纠结型选题", "标题必须带具体数字或反预期"],
        },
    },
    "painPoints": [
        {
            "theme": "DIY vs 中介：不知道钱该花在哪一步",
            "intensity": "高",
            "count": 4,
            "evidence": ["纠结要不要DIY，自己怕搞砸", "中介和DIY的钱到底该花在哪一步"],
        },
        {
            "theme": "背景评估焦虑：双非/均分够不够得着",
            "intensity": "高",
            "count": 4,
            "evidence": ["双非背景冲英国前30有戏吗", "均分85冲刺前20稳吗"],
        },
    ],
    "topics": [
        {
            "title": "5万块中介费，该花的是这3步，剩下4步你自己做更好",
            "angle": "把 DIY 还是中介从二选一重构成按申请环节拆开外包的决策框架",
            "pain": "DIY vs 中介",
            "whyFit": "命中最高频痛点，延续亲历者加拆解风格，避免重复旧话题。",
        },
        {
            "title": "双非/均分85，到底够得着哪一档？一张自测表替代焦虑",
            "angle": "用可量化维度把有没有戏转成可执行评估",
            "pain": "背景评估焦虑",
            "whyFit": "承接反焦虑的方法论基因，把抽象焦虑拆成步骤。",
        },
    ],
    "titles": [
        {
            "topic": "5万块中介费，该花的是这3步，剩下4步你自己做更好",
            "variants": ["中介费到底该花在哪三步", "5万中介费，我只建议你花在这里"],
        }
    ],
}


class FakeAccountDiagnosisModelProvider:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.calls: list[str] = []

    async def profile(
        self, *, positioning: str, historical_posts: str
    ) -> dict[str, Any]:
        self.calls.append("profile")
        if "profile" in self.failures:
            raise RuntimeError("profile failed")
        return {"profile": SAMPLE_ACCOUNT_RESULT["profile"]}

    async def pain_points(self, *, comments: str) -> dict[str, Any]:
        self.calls.append("pain_points")
        if "pain_points" in self.failures:
            raise RuntimeError("pain points failed")
        return {"painPoints": SAMPLE_ACCOUNT_RESULT["painPoints"]}

    async def topics(
        self,
        *,
        positioning: str,
        profile: dict[str, Any] | None,
        pain_points: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        self.calls.append("topics")
        if "topics" in self.failures:
            raise RuntimeError("topics failed")
        return {
            "topics": SAMPLE_ACCOUNT_RESULT["topics"],
            "titles": SAMPLE_ACCOUNT_RESULT["titles"],
        }

class RealAccountDiagnosisModelProvider:
    def __init__(self, model_call_service: ModelCallService) -> None:
        self.model_call_service = model_call_service

    async def profile(
        self, *, positioning: str, historical_posts: str
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.PROFILE,
            {"positioning": positioning, "historicalPosts": historical_posts},
        )
        return response.output

    async def profile_with_updates(
        self,
        *,
        positioning: str,
        historical_posts: str,
        on_update: Callable[[dict[str, Any]], Awaitable[None]],
    ):
        # Supported account providers share the same report workflow. Explicit
        # single-call rollback and legacy text retain their existing prompt.
        from app.services.account_report_pipeline import (
            StagedReportResult,
            run_staged_account_report,
        )
        from app.services.account_report_prompt import uses_structured_notes

        context = {"positioning": positioning, "historicalPosts": historical_posts}
        if (self.model_call_service.settings.account_report_mode == "staged"
                and self.model_call_service.settings.model_provider.strip().lower()
                in {"qwen", "dashscope", "deepseek"}
                and uses_structured_notes(context)):
            return await run_staged_account_report(
                context,
                self.model_call_service.call_account_report_step,
                on_update=on_update,
            )
        response = await self.model_call_service.call_operation(
            ModelOperation.PROFILE, context,
        )
        return StagedReportResult(
            output=response.output, model_metadata=_account_call_metadata(response.model_metadata),
        )

    async def pain_points(self, *, comments: str) -> dict[str, Any]:
        response = await self.pain_points_with_updates(
            comments=comments, source_profile=None, on_update=None,
        )
        return response.output

    async def pain_points_with_updates(
        self,
        *,
        comments: str,
        source_profile: dict[str, Any] | None,
        on_update: Callable[[dict[str, Any]], Awaitable[None]] | None,
    ):
        from app.services.reader_feedback_pipeline import run_reader_feedback

        return await run_reader_feedback(
            comments,
            source_profile,
            self.model_call_service.call_reader_feedback_step,
            on_update=on_update,
        )

    async def topics(
        self,
        *,
        positioning: str,
        profile: dict[str, Any] | None,
        pain_points: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        response = await self.topics_with_metadata(
            positioning=positioning, profile=profile, pain_points=pain_points,
        )
        return response.output

    async def topics_with_metadata(
        self, *, positioning: str, profile: dict[str, Any] | None,
        pain_points: list[dict[str, Any]] | None,
    ):
        response = await self.model_call_service.call_operation(
            ModelOperation.TOPICS,
            {
                "positioning": positioning,
                "profile": profile,
                "painPoints": pain_points,
            },
        )
        return ModelCallResponse(
            output=response.output, model_metadata=_account_call_metadata(response.model_metadata),
        )

class GraphExecutionPaused(Exception):
    pass


class AccountDiagnosisWorkflowService:
    def __init__(
        self,
        *,
        database: SQLiteDatabase,
        analysis_repository: AnalysisRunRepository,
        checkpoint_repository: GraphCheckpointRepository,
        analysis_service: AnalysisRunService,
        fake_provider: AccountDiagnosisModelProvider,
        live_provider: AccountDiagnosisModelProvider,
    ) -> None:
        self.database = database
        self.analysis_repository = analysis_repository
        self.checkpoint_repository = checkpoint_repository
        self.analysis_service = analysis_service
        self.fake_provider = fake_provider
        self.live_provider = live_provider
        self.graph = self._build_graph()

    def initial_state_for_run(self, run_id: str) -> AccountDiagnosisState:
        run = self.analysis_service.get(run_id)
        if run.workflow_type != WorkflowType.ACCOUNT_DIAGNOSIS:
            raise ValidationError("Only account diagnosis runs can use this workflow")
        snapshot = run.input_snapshot
        return AccountDiagnosisState(
            run_id=run.id,
            workspace_id=run.workspace_id,
            positioning_snapshot=str(snapshot["accountPositioning"]),
            historical_posts_material_id=str(
                snapshot["historicalPosts"]["materialId"]
            ),
            comments_material_id=str(snapshot["comments"]["materialId"]),
            profile=run.stage_results.get("profile", {}).get("profile"),
            pain_points=run.stage_results.get("pain_points", {}).get("painPoints"),
            topics=run.stage_results.get("topics", {}).get("topics"),
            titles=run.stage_results.get("topics", {}).get("titles", []),
            stage_errors=run.stage_errors,
            completed_nodes=[],
        )

    async def stream_events(
        self, run_id: str, *, stop_after_node: str | None = None
    ) -> AsyncIterator[RunEvent]:
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()
        runner = _AccountDiagnosisGraphExecution(
            service=self,
            run_id=run_id,
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
        self, run_id: str, *, stop_after_node: str | None = None
    ) -> list[RunEvent]:
        return [
            event
            async for event in self.stream_events(
                run_id, stop_after_node=stop_after_node
            )
        ]

    def _build_graph(self):
        builder = StateGraph(AccountDiagnosisState)
        builder.add_node("profile_analysis", self._profile_analysis)
        builder.add_node("topic_generation", self._topic_generation)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "profile_analysis")
        builder.add_edge("profile_analysis", "topic_generation")
        builder.add_edge("topic_generation", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile()

    async def _profile_analysis(
        self, state: AccountDiagnosisState
    ) -> AccountDiagnosisState:
        execution = _AccountDiagnosisGraphExecution.current()
        return await execution.profile_analysis(state)

    async def _topic_generation(
        self, state: AccountDiagnosisState
    ) -> AccountDiagnosisState:
        execution = _AccountDiagnosisGraphExecution.current()
        return await execution.topic_generation(state)

    async def _finalize(self, state: AccountDiagnosisState) -> AccountDiagnosisState:
        execution = _AccountDiagnosisGraphExecution.current()
        return await execution.finalize(state)


class _AccountDiagnosisGraphExecution:
    def __init__(
        self,
        *,
        service: AccountDiagnosisWorkflowService,
        run_id: str,
        queue: asyncio.Queue[RunEvent | None],
        stop_after_node: str | None,
    ) -> None:
        self.service = service
        self.run_id = run_id
        self.queue = queue
        self.stop_after_node = stop_after_node
        self.events = RunEventEmitter(
            run_id=run_id,
            run_type=WorkflowType.ACCOUNT_DIAGNOSIS.value,
        )

    @classmethod
    def current(cls) -> _AccountDiagnosisGraphExecution:
        active = ACTIVE_EXECUTION.get()
        if active is None:
            raise RuntimeError("No active account diagnosis graph execution")
        return active

    async def run(self) -> None:
        token = ACTIVE_EXECUTION.set(self)
        try:
            run = self.service.analysis_service.get(self.run_id)
            if run.status.value in TERMINAL_STATUSES:
                await self._emit_existing_terminal_run(run)
                return
            await self.emit("run.created", None, run.status, {})
            if run.status == AnalysisRunStatus.PENDING:
                self.service.analysis_service.transition(
                    self.run_id,
                    AnalysisRunTransition(
                        status=AnalysisRunStatus.RUNNING,
                        model_metadata={"engine": "langgraph"},
                    ),
                )
            await self.emit("run.started", None, "running", {})
            state = self.service.initial_state_for_run(self.run_id)
            try:
                await self.service.graph.ainvoke(
                    state,
                    config={"configurable": {"thread_id": self.run_id}},
                )
            except GraphExecutionPaused:
                return
        finally:
            ACTIVE_EXECUTION.reset(token)
            await self.queue.put(None)

    async def profile_analysis(
        self, state: AccountDiagnosisState
    ) -> AccountDiagnosisState:
        provider = self.provider()
        snapshot = self.snapshot()
        updated = dict(state)

        async def run_profile() -> None:
            if updated.get("profile"):
                return
            await self.emit("stage.started", "profile", "running", {})
            try:
                run = self.service.analysis_service.get(self.run_id)
                context, observations = profile_stage_input(snapshot, run.created_at.isoformat())
                chronology = (observations or {}).get("chronology", {})
                metadata = {"engine": "langgraph"}
                latest_preview = ""

                async def on_update(progress: dict[str, Any]) -> None:
                    nonlocal latest_preview
                    # Keep the last finished reading visible during the next call.
                    if isinstance(progress.get("preview"), str) and progress["preview"]:
                        latest_preview = progress["preview"]
                    progress = {**progress, "preview": latest_preview}
                    self.service.analysis_service.update_stage(
                        self.run_id,
                        "profile",
                        AnalysisStageUpdate(
                            status=AnalysisRunStatus.RUNNING,
                            model_metadata={
                                **metadata, "accountReportMode": "staged",
                                "progress": dict(progress),
                            },
                        ),
                    )
                    await self.emit("stage.progress", "profile", "running", progress)

                with_updates = getattr(provider, "profile_with_updates", None)
                if callable(with_updates):
                    response = await with_updates(
                        positioning=context["positioning"],
                        historical_posts=context["historicalPosts"],
                        on_update=on_update,
                    )
                    output = response.output
                    metadata.update(response.model_metadata)
                    metadata.pop("progress", None)
                else:
                    output = await provider.profile(
                        positioning=context["positioning"],
                        historical_posts=context["historicalPosts"],
                    )
                omissions: list[str] = []
                prepared = compile_usable_account_report(output, snapshot, omissions=omissions)
                if omissions:
                    metadata["omittedReportItems"] = omissions
                result = ProfileStageResult.model_validate(prepared).model_dump(
                    mode="json"
                )
                result["profile"]["accountPortrait"] = verified_portrait(
                    result["profile"].get("accountPortrait"), snapshot, chronology
                )
                if observations is not None:
                    result["observations"] = observations
                self.service.analysis_service.update_stage(
                    self.run_id,
                    "profile",
                    AnalysisStageUpdate(
                        status=AnalysisRunStatus.COMPLETED,
                        result=result,
                        model_metadata=metadata,
                    ),
                )
                updated["profile"] = result["profile"]
                await self.emit("stage.succeeded", "profile", "completed", result)
            except Exception as error:
                await self.stage_failed("profile", error, updated)

        async def run_pain_points() -> None:
            if updated.get("pain_points") is not None:
                return
            await self.emit("stage.started", "pain_points", "running", {})
            try:
                source_profile = snapshot.get("xhsCreatorProfile")
                if not isinstance(source_profile, dict):
                    source_profile = None
                # Rebuild from the frozen raw profile, including old pending runs
                # whose derived text still mixed author and reader comments.
                comments = (reader_comments_text(source_profile)
                            if source_profile is not None
                            else str(snapshot["comments"]["content"]))
                metadata = {"engine": "langgraph"}
                latest_preview = ""

                async def on_update(progress: dict[str, Any]) -> None:
                    nonlocal latest_preview
                    if isinstance(progress.get("preview"), str) and progress["preview"]:
                        latest_preview = progress["preview"]
                    progress = {**progress, "preview": latest_preview}
                    self.service.analysis_service.update_stage(
                        self.run_id,
                        "pain_points",
                        AnalysisStageUpdate(
                            status=AnalysisRunStatus.RUNNING,
                            model_metadata={
                                **metadata, "readerFeedbackMode": "two_stage",
                                "progress": dict(progress),
                            },
                        ),
                    )
                    await self.emit("stage.progress", "pain_points", "running", progress)

                with_updates = getattr(provider, "pain_points_with_updates", None)
                if callable(with_updates):
                    response = await with_updates(
                        comments=comments,
                        source_profile=source_profile,
                        on_update=on_update,
                    )
                    output = response.output
                    metadata.update(response.model_metadata)
                    metadata.pop("progress", None)
                else:
                    output = await provider.pain_points(comments=comments)
                result = PainPointsStageResult.model_validate(output).model_dump(
                    mode="json"
                )
                self.service.analysis_service.update_stage(
                    self.run_id,
                    "pain_points",
                    AnalysisStageUpdate(
                        status=AnalysisRunStatus.COMPLETED,
                        result=result,
                        model_metadata=metadata,
                    ),
                )
                updated["pain_points"] = result["painPoints"]
                await self.emit(
                    "stage.succeeded", "pain_points", "completed", result
                )
            except Exception as error:
                await self.stage_failed("pain_points", error, updated)

        await asyncio.gather(run_profile(), run_pain_points())
        await self.save_checkpoint("profile_analysis", updated)
        return AccountDiagnosisState(**updated)

    async def topic_generation(
        self, state: AccountDiagnosisState
    ) -> AccountDiagnosisState:
        updated = dict(state)
        if updated.get("topics"):
            await self.save_checkpoint("topic_generation", updated)
            return AccountDiagnosisState(**updated)
        if not updated.get("profile") and not updated.get("pain_points"):
            await self.save_checkpoint("topic_generation", updated)
            return AccountDiagnosisState(**updated)
        await self.emit("stage.started", "topics", "running", {})
        try:
            run = self.service.analysis_service.get(self.run_id)
            context = {
                "positioning": str(run.input_snapshot["accountPositioning"]),
                "profile": topic_profile_context(
                    updated.get("profile"), run.input_snapshot, run.created_at.isoformat()
                ),
                "pain_points": updated.get("pain_points"),
            }
            provider = self.provider()
            metadata = {"engine": "langgraph"}
            with_metadata = getattr(provider, "topics_with_metadata", None)
            if callable(with_metadata):
                response = await with_metadata(**context)
                output = response.output
                metadata.update(response.model_metadata)
            else:
                output = await provider.topics(**context)
            result = TopicsStageResult.model_validate(output).model_dump(mode="json")
            self.service.analysis_service.update_stage(
                self.run_id,
                "topics",
                AnalysisStageUpdate(
                    status=AnalysisRunStatus.COMPLETED,
                    result=result,
                    model_metadata=metadata,
                ),
            )
            updated["topics"] = result["topics"]
            updated["titles"] = result["titles"]
            await self.emit("stage.succeeded", "topics", "completed", result)
        except Exception as error:
            await self.stage_failed("topics", error, updated)
        await self.save_checkpoint("topic_generation", updated)
        return AccountDiagnosisState(**updated)

    async def finalize(self, state: AccountDiagnosisState) -> AccountDiagnosisState:
        updated = dict(state)
        run = self.service.analysis_service.get(self.run_id)
        has_errors = bool(run.stage_errors)
        has_results = bool(run.stage_results)
        if has_errors and has_results:
            status = AnalysisRunStatus.PARTIALLY_COMPLETED
            event_type = "run.partial"
        elif has_errors:
            status = AnalysisRunStatus.FAILED
            event_type = "run.failed"
        else:
            status = AnalysisRunStatus.COMPLETED
            event_type = "run.succeeded"
        completed = self.service.analysis_service.transition(
            self.run_id,
            AnalysisRunTransition(
                status=status,
                model_metadata={"engine": "langgraph"},
            ),
        )
        await self.save_checkpoint("finalize", updated)
        await self.emit(
            event_type,
            None,
            completed.status.value,
            {"stageResults": completed.stage_results, "stageErrors": completed.stage_errors},
        )
        return AccountDiagnosisState(**updated)

    def provider(self) -> AccountDiagnosisModelProvider:
        run = self.service.analysis_service.get(self.run_id)
        if run.input_snapshot.get("mode") == "live":
            return self.service.live_provider
        return self.service.fake_provider

    def snapshot(self) -> dict[str, Any]:
        return self.service.analysis_service.get(self.run_id).input_snapshot

    async def stage_failed(
        self, stage_key: str, error: Exception, state: dict[str, Any]
    ) -> None:
        diagnostics = (_safe_report_failure_metadata(getattr(error, "pipeline_metadata", None))
                       if stage_key == "profile" else {})
        report_failure = stage_key == "profile" and isinstance(error, AccountReportOutputError)
        message = self.error_message(error)
        if report_failure:
            message = (ACCOUNT_REPORT_RETRY_EXHAUSTED_MESSAGE
                       if diagnostics.get("retryCount", 0) > 0
                       else ACCOUNT_REPORT_INCOMPLETE_MESSAGE)
        state.setdefault("stage_errors", {})[stage_key] = message
        run = self.service.analysis_service.get(self.run_id)
        saved_metadata = run.model_metadata.get(stage_key)
        metadata = dict(saved_metadata) if isinstance(saved_metadata, dict) else {}
        metadata.pop("progress", None)
        metadata.update(diagnostics)
        self.service.analysis_service.update_stage(
            self.run_id,
            stage_key,
            AnalysisStageUpdate(
                status=AnalysisRunStatus.FAILED, error=message,
                model_metadata=metadata,
            ),
        )
        await self.emit("stage.failed", stage_key, "failed", {"error": message})

    async def save_checkpoint(self, node_key: str, state: dict[str, Any]) -> None:
        checkpoint_state = {
            "run_id": state.get("run_id"),
            "workspace_id": state.get("workspace_id"),
            "positioning_snapshot": state.get("positioning_snapshot"),
            "historical_posts_material_id": state.get("historical_posts_material_id"),
            "comments_material_id": state.get("comments_material_id"),
            "profile": state.get("profile"),
            "pain_points": state.get("pain_points"),
            "topics": state.get("topics"),
            "titles": state.get("titles"),
            "stage_errors": state.get("stage_errors", {}),
        }
        with self.service.database.transaction() as connection:
            self.service.checkpoint_repository.save(
                connection,
                analysis_run_id=self.run_id,
                workflow_type=WorkflowType.ACCOUNT_DIAGNOSIS.value,
                node_key=node_key,
                state=checkpoint_state,
                now=utc_now(),
            )
        if self.stop_after_node == node_key:
            raise GraphExecutionPaused()

    async def emit(
        self,
        event_type: RunEventType,
        stage_key: str | None,
        status: str,
        data: dict[str, Any],
    ) -> None:
        await self.queue.put(
            self.events.event(
                event_type,
                stage_key=stage_key,
                status=status,
                data=data,
            )
        )

    async def _emit_existing_terminal_run(self, run) -> None:
        for stage_key in ACCOUNT_STAGE_ORDER:
            if stage_key in run.stage_results:
                await self.emit(
                    "stage.succeeded",
                    stage_key,
                    "completed",
                    run.stage_results[stage_key],
                )
            if stage_key in run.stage_errors:
                await self.emit(
                    "stage.failed",
                    stage_key,
                    "failed",
                    {"error": run.stage_errors[stage_key]},
                )
        event_type = (
            "run.succeeded"
            if run.status == AnalysisRunStatus.COMPLETED
            else "run.partial"
            if run.status == AnalysisRunStatus.PARTIALLY_COMPLETED
            else "run.failed"
        )
        await self.emit(
            event_type,
            None,
            run.status.value,
            {"stageResults": run.stage_results, "stageErrors": run.stage_errors},
        )

    @staticmethod
    def error_message(error: Exception) -> str:
        if isinstance(error, PydanticValidationError):
            return "Model response failed structured validation"
        if isinstance(error, (ValidationError, ConflictError)):
            return str(error)
        return str(error) or error.__class__.__name__
