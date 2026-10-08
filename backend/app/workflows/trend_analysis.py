from __future__ import annotations

import asyncio
import contextvars
from collections.abc import AsyncIterator
from typing import Annotated, Any, Protocol, TypedDict

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.db.database import SQLiteDatabase
from app.errors import ConflictError, ValidationError
from app.models import (
    AnalysisRunStatus,
    AnalysisRunTransition,
    AnalysisStageUpdate,
    ModelOperation,
    WorkflowType,
)
from app.repositories.analysis_runs import TERMINAL_STATUSES
from app.repositories.graph_checkpoints import GraphCheckpointRepository
from app.services.analysis_runs import AnalysisRunService
from app.services.common import utc_now
from app.services.model_calls import ModelCallService
from app.services.run_events import RunEvent, RunEventEmitter, RunEventType
from app.workflows.account_diagnosis import (
    GraphExecutionPaused,
    TopicsStageResult,
)

TREND_GRAPH_NODE_ORDER = [
    "trend_pattern_analysis",
    "pain_point_analysis",
    "topic_generation",
    "finalize",
]
TREND_STAGE_ORDER = [
    "trend_analysis",
    "pain_points",
    "topics",
    "titles",
]
ACTIVE_TREND_EXECUTION: contextvars.ContextVar[
    _TrendAnalysisGraphExecution | None
] = contextvars.ContextVar("trend_analysis_execution", default=None)


def merge_stage_errors(
    left: dict[str, str] | None, right: dict[str, str] | None
) -> dict[str, str]:
    return {**(left or {}), **(right or {})}


class TrendAnalysisState(TypedDict, total=False):
    run_id: str
    workspace_id: str
    positioning_snapshot: str
    trend_csv_material_id: str
    trend_keyword: str
    ranked_posts: list[dict[str, Any]]
    trend_analysis: dict[str, Any]
    pain_points: list[dict[str, Any]]
    topics: list[dict[str, Any]]
    titles: list[dict[str, Any]]
    stage_errors: Annotated[dict[str, str], merge_stage_errors]


class TrendTheme(BaseModel):
    theme: str
    count: int
    topPost: str = ""
    engagement: str = ""
    summary: str = ""


class TrendAnalysisData(BaseModel):
    themes: list[TrendTheme] = Field(default_factory=list)
    viralPatterns: list[str] = Field(default_factory=list)
    opportunityWindows: list[str] = Field(default_factory=list)


class TrendAnalysisStageResult(BaseModel):
    trendAnalysis: TrendAnalysisData


class PainPoint(BaseModel):
    theme: str
    intensity: str
    count: int
    evidence: list[str] = Field(default_factory=list)


class PainPointsStageResult(BaseModel):
    painPoints: list[PainPoint]


class TrendAnalysisModelProvider(Protocol):
    async def trend_analysis(
        self, *, positioning: str, trend_keyword: str, posts_text: str
    ) -> dict[str, Any]: ...

    async def pain_points(self, *, trend_keyword: str, posts_text: str) -> dict[str, Any]: ...

    async def topics(
        self,
        *,
        positioning: str,
        trend_analysis: dict[str, Any] | None,
        pain_points: list[dict[str, Any]] | None,
    ) -> dict[str, Any]: ...

SAMPLE_TREND_RESULT = {
    "trendAnalysis": {
        "themes": [
            {
                "theme": "收入揭秘与真实性背书",
                "count": 12,
                "topPost": "一天三份工，还能躺平？巴厘岛游民生活大公开",
                "engagement": "高",
                "summary": "带具体收入数字的内容爆款率最高，读者情绪卷入强。",
            },
            {
                "theme": "远程工作入门路径",
                "count": 10,
                "topPost": "普通人也能成为数字游民（内附找工作渠道）",
                "engagement": "中",
                "summary": "刚需信息，收藏率持续高于赞数。",
            },
        ],
        "viralPatterns": ["收入数字具体化", "反预期钩子", "VLOG形式 + 具体工具/渠道名称"],
        "opportunityWindows": ["AI工具 × 远程接单操作帖", "普通人从0开始的完整路径"],
    },
    "painPoints": [
        {
            "theme": "入门技能：不知道靠什么远程赚钱",
            "intensity": "高",
            "count": 18,
            "evidence": ["没有可以远程的技能怎么办", "非技术人能做数字游民吗"],
        }
    ],
    "topics": [
        {
            "title": "文科生/非技术背景，靠什么开始数字游民？6条真实路径",
            "angle": "把没有远程技能这个卡点拆成具体可行的技能转换方向",
            "pain": "入门技能不清晰",
            "whyFit": "亲历者视角加清单形态，符合真实记录和可操作指南的定位。",
            "whyTrending": "具体路径需求强但供给不足，是当前话题内容空缺。",
        },
        {
            "title": "成为数字游民的第一年，我实际花了多少钱？启动成本完全拆解",
            "angle": "用真实账单打破门槛恐惧，给出最低成本启动建议",
            "pain": "启动门槛不确定",
            "whyFit": "带具体数字，契合不贩卖幻觉的账号主张。",
            "whyTrending": "启动成本是评论区高频问题，机会窗口明显。",
        },
    ],
    "titles": [
        {
            "topic": "文科生/非技术背景，靠什么开始数字游民？6条真实路径",
            "variants": [
                "非技术人做数字游民，先从这6条路径里选",
                "不会写代码，也能远程赚钱的6种方式",
            ],
        }
    ],
}


class FakeTrendAnalysisModelProvider:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.calls: list[str] = []

    async def trend_analysis(
        self, *, positioning: str, trend_keyword: str, posts_text: str
    ) -> dict[str, Any]:
        self.calls.append("trend_analysis")
        if "trend_analysis" in self.failures:
            raise RuntimeError("trend analysis failed")
        return {"trendAnalysis": SAMPLE_TREND_RESULT["trendAnalysis"]}

    async def pain_points(
        self, *, trend_keyword: str, posts_text: str
    ) -> dict[str, Any]:
        self.calls.append("pain_points")
        if "pain_points" in self.failures:
            raise RuntimeError("pain points failed")
        return {"painPoints": SAMPLE_TREND_RESULT["painPoints"]}

    async def topics(
        self,
        *,
        positioning: str,
        trend_analysis: dict[str, Any] | None,
        pain_points: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        self.calls.append("topics")
        if "topics" in self.failures:
            raise RuntimeError("topics failed")
        return {
            "topics": SAMPLE_TREND_RESULT["topics"],
            "titles": SAMPLE_TREND_RESULT["titles"],
        }

class RealTrendAnalysisModelProvider:
    def __init__(self, model_call_service: ModelCallService) -> None:
        self.model_call_service = model_call_service

    async def trend_analysis(
        self, *, positioning: str, trend_keyword: str, posts_text: str
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.TREND_ANALYSIS,
            {
                "positioning": positioning,
                "trendKeyword": trend_keyword,
                "postsText": posts_text,
            },
        )
        return response.output

    async def pain_points(
        self, *, trend_keyword: str, posts_text: str
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.PAIN_POINTS,
            {
                "sourceText": (
                    f"以下是小红书「{trend_keyword or '该话题'}」相关热帖的标题和内容，"
                    f"请从中归纳读者高频痛点：\n{posts_text}"
                )
            },
        )
        return response.output

    async def topics(
        self,
        *,
        positioning: str,
        trend_analysis: dict[str, Any] | None,
        pain_points: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.TREND_TOPICS,
            {
                "positioning": positioning,
                "trendAnalysis": trend_analysis,
                "painPoints": pain_points,
            },
        )
        return response.output

class TrendAnalysisWorkflowService:
    def __init__(
        self,
        *,
        database: SQLiteDatabase,
        checkpoint_repository: GraphCheckpointRepository,
        analysis_service: AnalysisRunService,
        fake_provider: TrendAnalysisModelProvider,
        live_provider: TrendAnalysisModelProvider,
    ) -> None:
        self.database = database
        self.checkpoint_repository = checkpoint_repository
        self.analysis_service = analysis_service
        self.fake_provider = fake_provider
        self.live_provider = live_provider
        self.graph = self._build_graph()

    def initial_state_for_run(self, run_id: str) -> TrendAnalysisState:
        run = self.analysis_service.get(run_id)
        if run.workflow_type != WorkflowType.TREND_ANALYSIS:
            raise ValidationError("Only trend analysis runs can use this workflow")
        snapshot = run.input_snapshot
        trend_csv = snapshot["trendCsv"]
        return TrendAnalysisState(
            run_id=run.id,
            workspace_id=run.workspace_id,
            positioning_snapshot=str(snapshot["accountPositioning"]),
            trend_csv_material_id=str(trend_csv["materialId"]),
            trend_keyword=str(trend_csv["keyword"]),
            ranked_posts=list(trend_csv.get("rankedPosts", [])),
            trend_analysis=run.stage_results.get("trend_analysis", {}).get(
                "trendAnalysis"
            ),
            pain_points=run.stage_results.get("pain_points", {}).get("painPoints"),
            topics=run.stage_results.get("topics", {}).get("topics"),
            titles=run.stage_results.get("titles", {}).get("titles", []),
            stage_errors=run.stage_errors,
        )

    async def stream_events(
        self, run_id: str, *, stop_after_node: str | None = None
    ) -> AsyncIterator[RunEvent]:
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()
        runner = _TrendAnalysisGraphExecution(
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
        builder = StateGraph(TrendAnalysisState)
        builder.add_node("trend_pattern_analysis", self._trend_pattern_analysis)
        builder.add_node("pain_point_analysis", self._pain_point_analysis)
        builder.add_node("topic_generation", self._topic_generation)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "trend_pattern_analysis")
        builder.add_edge(START, "pain_point_analysis")
        builder.add_edge("trend_pattern_analysis", "topic_generation")
        builder.add_edge("pain_point_analysis", "topic_generation")
        builder.add_edge("topic_generation", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile()

    async def _trend_pattern_analysis(
        self, state: TrendAnalysisState
    ) -> dict[str, Any]:
        return await _TrendAnalysisGraphExecution.current().trend_pattern_analysis(state)

    async def _pain_point_analysis(
        self, state: TrendAnalysisState
    ) -> dict[str, Any]:
        return await _TrendAnalysisGraphExecution.current().pain_point_analysis(state)

    async def _topic_generation(
        self, state: TrendAnalysisState
    ) -> TrendAnalysisState:
        return await _TrendAnalysisGraphExecution.current().topic_generation(state)

    async def _finalize(self, state: TrendAnalysisState) -> TrendAnalysisState:
        return await _TrendAnalysisGraphExecution.current().finalize(state)


class _TrendAnalysisGraphExecution:
    def __init__(
        self,
        *,
        service: TrendAnalysisWorkflowService,
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
            run_type=WorkflowType.TREND_ANALYSIS.value,
        )

    @classmethod
    def current(cls) -> _TrendAnalysisGraphExecution:
        active = ACTIVE_TREND_EXECUTION.get()
        if active is None:
            raise RuntimeError("No active trend analysis graph execution")
        return active

    async def run(self) -> None:
        token = ACTIVE_TREND_EXECUTION.set(self)
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
            try:
                await self.service.graph.ainvoke(
                    self.service.initial_state_for_run(self.run_id),
                    config={"configurable": {"thread_id": self.run_id}},
                )
            except GraphExecutionPaused:
                return
        finally:
            ACTIVE_TREND_EXECUTION.reset(token)
            await self.queue.put(None)

    async def trend_pattern_analysis(
        self, state: TrendAnalysisState
    ) -> dict[str, Any]:
        updated = dict(state)
        if updated.get("trend_analysis"):
            return {}
        await self.emit("stage.started", "trend_analysis", "running", {})
        try:
            output = await self.provider().trend_analysis(
                positioning=updated["positioning_snapshot"],
                trend_keyword=updated["trend_keyword"],
                posts_text=self.posts_text(updated["ranked_posts"]),
            )
            result = TrendAnalysisStageResult.model_validate(output).model_dump(
                mode="json"
            )
            self.service.analysis_service.update_stage(
                self.run_id,
                "trend_analysis",
                AnalysisStageUpdate(
                    status=AnalysisRunStatus.COMPLETED,
                    result=result,
                    model_metadata={"engine": "langgraph"},
                ),
            )
            updated["trend_analysis"] = result["trendAnalysis"]
            await self.emit("stage.succeeded", "trend_analysis", "completed", result)
        except Exception as error:
            await self.stage_failed("trend_analysis", error, updated)
        await self.save_checkpoint("trend_pattern_analysis", updated)
        response: dict[str, Any] = {}
        if updated.get("trend_analysis"):
            response["trend_analysis"] = updated["trend_analysis"]
        if updated.get("stage_errors"):
            response["stage_errors"] = updated["stage_errors"]
        return response

    async def pain_point_analysis(
        self, state: TrendAnalysisState
    ) -> dict[str, Any]:
        updated = dict(state)
        if updated.get("pain_points"):
            return {}
        await self.emit("stage.started", "pain_points", "running", {})
        try:
            output = await self.provider().pain_points(
                trend_keyword=updated["trend_keyword"],
                posts_text=self.posts_text(updated["ranked_posts"]),
            )
            result = PainPointsStageResult.model_validate(output).model_dump(
                mode="json"
            )
            self.service.analysis_service.update_stage(
                self.run_id,
                "pain_points",
                AnalysisStageUpdate(
                    status=AnalysisRunStatus.COMPLETED,
                    result=result,
                    model_metadata={"engine": "langgraph"},
                ),
            )
            updated["pain_points"] = result["painPoints"]
            await self.emit("stage.succeeded", "pain_points", "completed", result)
        except Exception as error:
            await self.stage_failed("pain_points", error, updated)
        await self.save_checkpoint("pain_point_analysis", updated)
        response: dict[str, Any] = {}
        if updated.get("pain_points"):
            response["pain_points"] = updated["pain_points"]
        if updated.get("stage_errors"):
            response["stage_errors"] = updated["stage_errors"]
        return response

    async def topic_generation(self, state: TrendAnalysisState) -> TrendAnalysisState:
        updated = dict(state)
        if updated.get("topics"):
            await self.save_checkpoint("topic_generation", updated)
            return TrendAnalysisState(**updated)
        if not updated.get("trend_analysis") and not updated.get("pain_points"):
            await self.save_checkpoint("topic_generation", updated)
            return TrendAnalysisState(**updated)
        await self.emit("stage.started", "topics", "running", {})
        await self.emit("stage.started", "titles", "running", {})
        try:
            output = await self.provider().topics(
                positioning=updated["positioning_snapshot"],
                trend_analysis=updated.get("trend_analysis"),
                pain_points=updated.get("pain_points"),
            )
            result = TopicsStageResult.model_validate(output).model_dump(mode="json")
            self.service.analysis_service.update_stage(
                self.run_id,
                "topics",
                AnalysisStageUpdate(
                    status=AnalysisRunStatus.COMPLETED,
                    result={"topics": result["topics"]},
                    model_metadata={"engine": "langgraph"},
                ),
            )
            self.service.analysis_service.update_stage(
                self.run_id,
                "titles",
                AnalysisStageUpdate(
                    status=AnalysisRunStatus.COMPLETED,
                    result={"titles": result["titles"]},
                    model_metadata={"engine": "langgraph"},
                ),
            )
            updated["topics"] = result["topics"]
            updated["titles"] = result["titles"]
            await self.emit(
                "stage.succeeded", "topics", "completed", {"topics": result["topics"]}
            )
            await self.emit(
                "stage.succeeded", "titles", "completed", {"titles": result["titles"]}
            )
        except Exception as error:
            await self.stage_failed("topics", error, updated)
            await self.stage_failed("titles", error, updated)
        await self.save_checkpoint("topic_generation", updated)
        return TrendAnalysisState(**updated)

    async def finalize(self, state: TrendAnalysisState) -> TrendAnalysisState:
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
                status=status, model_metadata={"engine": "langgraph"}
            ),
        )
        await self.save_checkpoint("finalize", updated)
        await self.emit(
            event_type,
            None,
            completed.status.value,
            {"stageResults": completed.stage_results, "stageErrors": completed.stage_errors},
        )
        return TrendAnalysisState(**updated)

    def provider(self) -> TrendAnalysisModelProvider:
        run = self.service.analysis_service.get(self.run_id)
        if run.input_snapshot.get("mode") == "live":
            return self.service.live_provider
        return self.service.fake_provider

    async def stage_failed(
        self, stage_key: str, error: Exception, state: dict[str, Any]
    ) -> None:
        message = self.error_message(error)
        state.setdefault("stage_errors", {})[stage_key] = message
        self.service.analysis_service.update_stage(
            self.run_id,
            stage_key,
            AnalysisStageUpdate(status=AnalysisRunStatus.FAILED, error=message),
        )
        await self.emit("stage.failed", stage_key, "failed", {"error": message})

    async def save_checkpoint(self, node_key: str, state: dict[str, Any]) -> None:
        checkpoint_state = {
            "run_id": state.get("run_id"),
            "workspace_id": state.get("workspace_id"),
            "positioning_snapshot": state.get("positioning_snapshot"),
            "trend_csv_material_id": state.get("trend_csv_material_id"),
            "trend_keyword": state.get("trend_keyword"),
            "ranked_posts": state.get("ranked_posts", []),
            "trend_analysis": state.get("trend_analysis"),
            "pain_points": state.get("pain_points"),
            "topics": state.get("topics"),
            "titles": state.get("titles"),
            "stage_errors": state.get("stage_errors", {}),
        }
        with self.service.database.transaction() as connection:
            self.service.checkpoint_repository.save(
                connection,
                analysis_run_id=self.run_id,
                workflow_type=WorkflowType.TREND_ANALYSIS.value,
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
        for stage_key in TREND_STAGE_ORDER:
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
    def posts_text(posts: list[dict[str, Any]]) -> str:
        return "\n".join(
            (
                f"{index + 1}. [赞{post.get('likes', 0)}/藏{post.get('collects', 0)}] "
                f"{post.get('title', '')} "
                f"{'标签:' + str(post.get('tags')) if post.get('tags') else ''} "
                f"{str(post.get('contentSnippet') or '')[:60]}"
            )
            for index, post in enumerate(posts[:50])
        )

    @staticmethod
    def error_message(error: Exception) -> str:
        if isinstance(error, PydanticValidationError):
            return "Model response failed structured validation"
        if isinstance(error, (ValidationError, ConflictError)):
            return str(error)
        return str(error) or error.__class__.__name__
