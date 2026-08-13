from __future__ import annotations

import asyncio
import contextvars
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field
from pydantic import ValidationError as PydanticValidationError

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
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

VIDEO_CREATOR_QUALITY_STAGE_ORDER = [
    "creator_profile",
    "video_quality",
    "incentive_fit",
]
VIDEO_CREATOR_QUALITY_GRAPH_NODE_ORDER = [
    "creator_profile",
    "video_quality",
    "incentive_fit",
    "finalize",
]
ACTIVE_VIDEO_EXECUTION: contextvars.ContextVar[
    _VideoCreatorQualityGraphExecution | None
] = contextvars.ContextVar("video_creator_quality_execution", default=None)


class VideoCreatorQualityEvent(TypedDict):
    eventId: str
    runId: str
    runType: Literal["video_creator_quality"]
    stageKey: str | None
    status: str
    sequence: int
    occurredAt: str
    data: dict[str, Any]


class VideoCreatorQualityState(TypedDict, total=False):
    run_id: str
    workspace_id: str
    positioning_snapshot: str
    video_creator_samples_material_id: str
    media_asset_ids: list[str]
    creator_profile: dict[str, Any]
    video_quality: dict[str, Any]
    incentive_fit: dict[str, Any]
    stage_errors: dict[str, str]


class CreatorProfileData(BaseModel):
    creatorType: str
    typeConfidence: str
    summary: str = ""
    audiencePositioning: str = ""
    contentPillars: list[str] = Field(default_factory=list)
    motivationSignals: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    uncertainties: list[str] = Field(default_factory=list)


class CreatorProfileStageResult(BaseModel):
    creatorProfile: CreatorProfileData


class VideoQualityDimensionScore(BaseModel):
    dimension: str
    score: int
    reason: str = ""


class VideoQualityData(BaseModel):
    overallScore: int
    level: str
    dimensionScores: list[VideoQualityDimensionScore] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class VideoQualityStageResult(BaseModel):
    videoQuality: VideoQualityData


class ProgramMatch(BaseModel):
    bestProgramType: str = ""
    why: str = ""
    avoid: str = ""


class IncentiveFitData(BaseModel):
    recommendation: str
    fitScore: int
    rationale: str = ""
    conditions: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    operatorActions: list[str] = Field(default_factory=list)
    programMatch: ProgramMatch = Field(default_factory=ProgramMatch)


class IncentiveFitStageResult(BaseModel):
    incentiveFit: IncentiveFitData


class VideoCreatorQualityModelProvider(Protocol):
    async def creator_profile(
        self,
        *,
        positioning: str,
        video_creator_samples: str,
        media_assets: list[dict[str, Any]],
    ) -> dict[str, Any]: ...

    async def video_quality(
        self,
        *,
        positioning: str,
        video_creator_samples: str,
        media_assets: list[dict[str, Any]],
        creator_profile: dict[str, Any] | None,
    ) -> dict[str, Any]: ...

    async def incentive_fit(
        self,
        *,
        positioning: str,
        creator_profile: dict[str, Any] | None,
        video_quality: dict[str, Any] | None,
    ) -> dict[str, Any]: ...


SAMPLE_VIDEO_CREATOR_RESULT = {
    "creatorProfile": {
        "creatorType": "script_driven",
        "typeConfidence": "高",
        "summary": "该创作者以连续短剧式 AIGC 视频为主，稳定围绕角色冲突和反转剧情生产。",
        "audiencePositioning": "喜欢 AI 短剧、奇幻反转和轻量连续剧情的泛娱乐用户。",
        "contentPillars": ["连续角色设定", "强冲突短剧", "AIGC 奇幻视觉"],
        "motivationSignals": ["持续更新同一世界观", "评论区催更", "不以商单口播为主"],
        "evidence": ["样本记录显示 8 条视频使用同一主角设定", "高互动视频集中在剧情反转段落"],
        "uncertainties": ["缺少完整 30 天更新频次数据"],
    },
    "videoQuality": {
        "overallScore": 82,
        "level": "高",
        "dimensionScores": [
            {"dimension": "scriptAndNarrative", "score": 88, "reason": "冲突明确，反转稳定"},
            {"dimension": "visualExecution", "score": 78, "reason": "画面统一但动作细节偶有跳变"},
            {"dimension": "aigcTechniqueUse", "score": 80, "reason": "技术服务剧情而非单纯炫技"},
            {"dimension": "productionRepeatability", "score": 84, "reason": "角色和模板可复用"},
        ],
        "strengths": ["叙事驱动强", "系列化潜力高", "AIGC 视觉与内容目标一致"],
        "weaknesses": ["部分镜头连贯性不足", "缺少明确商业化边界"],
        "evidence": ["三条最高互动视频都有明确冲突和结尾悬念"],
    },
    "incentiveFit": {
        "recommendation": "strong_fit",
        "fitScore": 86,
        "rationale": "剧本驱动和系列化能力明显，激励计划能放大稳定更新与剧情迭代。",
        "conditions": ["激励指标应偏向连续更新和有效完播", "提供剧本模板和角色设定支持"],
        "risks": ["过度追求产量可能降低画面稳定性"],
        "operatorActions": ["纳入短剧型 AIGC 创作者池", "给出 4 周系列化激励任务"],
        "programMatch": {
            "bestProgramType": "系列内容更新激励",
            "why": "创作者有明确世界观和可复制剧本结构",
            "avoid": "不要只按单条播放量补贴",
        },
    },
}


class FakeVideoCreatorQualityModelProvider:
    def __init__(self, failures: set[str] | None = None) -> None:
        self.failures = failures or set()
        self.calls: list[str] = []

    async def creator_profile(
        self,
        *,
        positioning: str,
        video_creator_samples: str,
        media_assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.calls.append("creator_profile")
        if "creator_profile" in self.failures:
            raise RuntimeError("creator profile failed")
        return {"creatorProfile": SAMPLE_VIDEO_CREATOR_RESULT["creatorProfile"]}

    async def video_quality(
        self,
        *,
        positioning: str,
        video_creator_samples: str,
        media_assets: list[dict[str, Any]],
        creator_profile: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self.calls.append("video_quality")
        if "video_quality" in self.failures:
            raise RuntimeError("video quality failed")
        return {"videoQuality": SAMPLE_VIDEO_CREATOR_RESULT["videoQuality"]}

    async def incentive_fit(
        self,
        *,
        positioning: str,
        creator_profile: dict[str, Any] | None,
        video_quality: dict[str, Any] | None,
    ) -> dict[str, Any]:
        self.calls.append("incentive_fit")
        if "incentive_fit" in self.failures:
            raise RuntimeError("incentive fit failed")
        return {"incentiveFit": SAMPLE_VIDEO_CREATOR_RESULT["incentiveFit"]}


class RealVideoCreatorQualityModelProvider:
    def __init__(self, model_call_service: ModelCallService) -> None:
        self.model_call_service = model_call_service

    async def creator_profile(
        self,
        *,
        positioning: str,
        video_creator_samples: str,
        media_assets: list[dict[str, Any]],
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.VIDEO_CREATOR_PROFILE,
            {
                "positioning": positioning,
                "videoCreatorSamples": video_creator_samples,
                "mediaAssets": media_assets,
            },
        )
        return response.output

    async def video_quality(
        self,
        *,
        positioning: str,
        video_creator_samples: str,
        media_assets: list[dict[str, Any]],
        creator_profile: dict[str, Any] | None,
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.VIDEO_QUALITY_ANALYSIS,
            {
                "positioning": positioning,
                "videoCreatorSamples": video_creator_samples,
                "mediaAssets": media_assets,
                "creatorProfile": creator_profile,
            },
        )
        return response.output

    async def incentive_fit(
        self,
        *,
        positioning: str,
        creator_profile: dict[str, Any] | None,
        video_quality: dict[str, Any] | None,
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.INCENTIVE_FIT_ANALYSIS,
            {
                "positioning": positioning,
                "creatorProfile": creator_profile,
                "videoQuality": video_quality,
            },
        )
        return response.output


class VideoGraphExecutionPaused(Exception):
    pass


class VideoCreatorQualityWorkflowService:
    def __init__(
        self,
        *,
        database: SQLiteDatabase,
        checkpoint_repository: GraphCheckpointRepository,
        analysis_service: AnalysisRunService,
        fake_provider: VideoCreatorQualityModelProvider,
        live_provider: VideoCreatorQualityModelProvider,
    ) -> None:
        self.database = database
        self.checkpoint_repository = checkpoint_repository
        self.analysis_service = analysis_service
        self.fake_provider = fake_provider
        self.live_provider = live_provider
        self.graph = self._build_graph()

    def initial_state_for_run(self, run_id: str) -> VideoCreatorQualityState:
        run = self.analysis_service.get(run_id)
        if run.workflow_type != WorkflowType.VIDEO_CREATOR_QUALITY:
            raise ValidationError("Only video creator quality runs can use this workflow")
        snapshot = run.input_snapshot
        samples = snapshot["videoCreatorSamples"]
        return VideoCreatorQualityState(
            run_id=run.id,
            workspace_id=run.workspace_id,
            positioning_snapshot=str(snapshot["accountPositioning"]),
            video_creator_samples_material_id=str(samples["materialId"]),
            media_asset_ids=[
                str(asset.get("mediaAssetId"))
                for asset in snapshot.get("mediaAssets", [])
                if isinstance(asset, dict) and asset.get("mediaAssetId")
            ],
            creator_profile=run.stage_results.get("creator_profile", {}).get(
                "creatorProfile"
            ),
            video_quality=run.stage_results.get("video_quality", {}).get(
                "videoQuality"
            ),
            incentive_fit=run.stage_results.get("incentive_fit", {}).get(
                "incentiveFit"
            ),
            stage_errors=run.stage_errors,
        )

    async def stream_events(
        self, run_id: str, *, stop_after_node: str | None = None
    ) -> AsyncIterator[VideoCreatorQualityEvent]:
        queue: asyncio.Queue[VideoCreatorQualityEvent | None] = asyncio.Queue()
        runner = _VideoCreatorQualityGraphExecution(
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
    ) -> list[VideoCreatorQualityEvent]:
        return [
            event
            async for event in self.stream_events(
                run_id, stop_after_node=stop_after_node
            )
        ]

    def _build_graph(self):
        builder = StateGraph(VideoCreatorQualityState)
        builder.add_node("creator_profile", self._creator_profile)
        builder.add_node("video_quality", self._video_quality)
        builder.add_node("incentive_fit", self._incentive_fit)
        builder.add_node("finalize", self._finalize)
        builder.add_edge(START, "creator_profile")
        builder.add_edge("creator_profile", "video_quality")
        builder.add_edge("video_quality", "incentive_fit")
        builder.add_edge("incentive_fit", "finalize")
        builder.add_edge("finalize", END)
        return builder.compile()

    async def _creator_profile(
        self, state: VideoCreatorQualityState
    ) -> VideoCreatorQualityState:
        return await _VideoCreatorQualityGraphExecution.current().creator_profile(state)

    async def _video_quality(
        self, state: VideoCreatorQualityState
    ) -> VideoCreatorQualityState:
        return await _VideoCreatorQualityGraphExecution.current().video_quality(state)

    async def _incentive_fit(
        self, state: VideoCreatorQualityState
    ) -> VideoCreatorQualityState:
        return await _VideoCreatorQualityGraphExecution.current().incentive_fit(state)

    async def _finalize(
        self, state: VideoCreatorQualityState
    ) -> VideoCreatorQualityState:
        return await _VideoCreatorQualityGraphExecution.current().finalize(state)


class _VideoCreatorQualityGraphExecution:
    def __init__(
        self,
        *,
        service: VideoCreatorQualityWorkflowService,
        run_id: str,
        queue: asyncio.Queue[VideoCreatorQualityEvent | None],
        stop_after_node: str | None,
    ) -> None:
        self.service = service
        self.run_id = run_id
        self.queue = queue
        self.stop_after_node = stop_after_node
        self.sequence = 0

    @classmethod
    def current(cls) -> _VideoCreatorQualityGraphExecution:
        active = ACTIVE_VIDEO_EXECUTION.get()
        if active is None:
            raise RuntimeError("No active video creator quality graph execution")
        return active

    async def run(self) -> None:
        token = ACTIVE_VIDEO_EXECUTION.set(self)
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
            except VideoGraphExecutionPaused:
                return
        finally:
            ACTIVE_VIDEO_EXECUTION.reset(token)
            await self.queue.put(None)

    async def creator_profile(
        self, state: VideoCreatorQualityState
    ) -> VideoCreatorQualityState:
        updated = dict(state)
        if updated.get("creator_profile"):
            await self.save_checkpoint("creator_profile", updated)
            return VideoCreatorQualityState(**updated)
        await self.emit("stage.started", "creator_profile", "running", {})
        try:
            output = await self.provider().creator_profile(
                positioning=str(self.snapshot()["accountPositioning"]),
                video_creator_samples=str(
                    self.snapshot()["videoCreatorSamples"]["content"]
                ),
                media_assets=self.snapshot().get("mediaAssets", []),
            )
            result = CreatorProfileStageResult.model_validate(output).model_dump(
                mode="json"
            )
            self.service.analysis_service.update_stage(
                self.run_id,
                "creator_profile",
                AnalysisStageUpdate(
                    status=AnalysisRunStatus.COMPLETED,
                    result=result,
                    model_metadata={"engine": "langgraph"},
                ),
            )
            updated["creator_profile"] = result["creatorProfile"]
            await self.emit("stage.succeeded", "creator_profile", "completed", result)
        except Exception as error:
            await self.stage_failed("creator_profile", error, updated)
        await self.save_checkpoint("creator_profile", updated)
        return VideoCreatorQualityState(**updated)

    async def video_quality(
        self, state: VideoCreatorQualityState
    ) -> VideoCreatorQualityState:
        updated = dict(state)
        if updated.get("video_quality"):
            await self.save_checkpoint("video_quality", updated)
            return VideoCreatorQualityState(**updated)
        await self.emit("stage.started", "video_quality", "running", {})
        try:
            output = await self.provider().video_quality(
                positioning=str(self.snapshot()["accountPositioning"]),
                video_creator_samples=str(
                    self.snapshot()["videoCreatorSamples"]["content"]
                ),
                media_assets=self.snapshot().get("mediaAssets", []),
                creator_profile=updated.get("creator_profile"),
            )
            result = VideoQualityStageResult.model_validate(output).model_dump(
                mode="json"
            )
            self.service.analysis_service.update_stage(
                self.run_id,
                "video_quality",
                AnalysisStageUpdate(
                    status=AnalysisRunStatus.COMPLETED,
                    result=result,
                    model_metadata={"engine": "langgraph"},
                ),
            )
            updated["video_quality"] = result["videoQuality"]
            await self.emit("stage.succeeded", "video_quality", "completed", result)
        except Exception as error:
            await self.stage_failed("video_quality", error, updated)
        await self.save_checkpoint("video_quality", updated)
        return VideoCreatorQualityState(**updated)

    async def incentive_fit(
        self, state: VideoCreatorQualityState
    ) -> VideoCreatorQualityState:
        updated = dict(state)
        if updated.get("incentive_fit"):
            await self.save_checkpoint("incentive_fit", updated)
            return VideoCreatorQualityState(**updated)
        if not updated.get("creator_profile") and not updated.get("video_quality"):
            await self.save_checkpoint("incentive_fit", updated)
            return VideoCreatorQualityState(**updated)
        await self.emit("stage.started", "incentive_fit", "running", {})
        try:
            output = await self.provider().incentive_fit(
                positioning=str(self.snapshot()["accountPositioning"]),
                creator_profile=updated.get("creator_profile"),
                video_quality=updated.get("video_quality"),
            )
            result = IncentiveFitStageResult.model_validate(output).model_dump(
                mode="json"
            )
            self.service.analysis_service.update_stage(
                self.run_id,
                "incentive_fit",
                AnalysisStageUpdate(
                    status=AnalysisRunStatus.COMPLETED,
                    result=result,
                    model_metadata={"engine": "langgraph"},
                ),
            )
            updated["incentive_fit"] = result["incentiveFit"]
            await self.emit("stage.succeeded", "incentive_fit", "completed", result)
        except Exception as error:
            await self.stage_failed("incentive_fit", error, updated)
        await self.save_checkpoint("incentive_fit", updated)
        return VideoCreatorQualityState(**updated)

    async def finalize(
        self, state: VideoCreatorQualityState
    ) -> VideoCreatorQualityState:
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
        return VideoCreatorQualityState(**updated)

    def provider(self) -> VideoCreatorQualityModelProvider:
        run = self.service.analysis_service.get(self.run_id)
        if run.input_snapshot.get("mode") == "live":
            return self.service.live_provider
        return self.service.fake_provider

    def snapshot(self) -> dict[str, Any]:
        return self.service.analysis_service.get(self.run_id).input_snapshot

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
            "video_creator_samples_material_id": state.get(
                "video_creator_samples_material_id"
            ),
            "media_asset_ids": state.get("media_asset_ids", []),
            "creator_profile": state.get("creator_profile"),
            "video_quality": state.get("video_quality"),
            "incentive_fit": state.get("incentive_fit"),
            "stage_errors": state.get("stage_errors", {}),
        }
        with self.service.database.transaction() as connection:
            self.service.checkpoint_repository.save(
                connection,
                analysis_run_id=self.run_id,
                workflow_type=WorkflowType.VIDEO_CREATOR_QUALITY.value,
                node_key=node_key,
                state=checkpoint_state,
                now=utc_now(),
            )
        if self.stop_after_node == node_key:
            raise VideoGraphExecutionPaused()

    async def emit(
        self,
        event_type: str,
        stage_key: str | None,
        status: str,
        data: dict[str, Any],
    ) -> None:
        self.sequence += 1
        await self.queue.put(
            {
                "eventId": str(uuid4()),
                "runId": self.run_id,
                "runType": "video_creator_quality",
                "stageKey": stage_key,
                "status": str(status),
                "sequence": self.sequence,
                "occurredAt": utc_now(),
                "data": {"eventType": event_type, **data},
            }
        )

    async def _emit_existing_terminal_run(self, run) -> None:
        event_type = "run.succeeded"
        if run.status == AnalysisRunStatus.PARTIALLY_COMPLETED:
            event_type = "run.partial"
        elif run.status == AnalysisRunStatus.FAILED:
            event_type = "run.failed"
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
        return str(error) or error.__class__.__name__
