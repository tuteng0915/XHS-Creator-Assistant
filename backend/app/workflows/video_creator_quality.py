from __future__ import annotations

import asyncio
import contextvars
from collections.abc import AsyncIterator
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, Field, field_validator
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
from app.services.skills import SkillService

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
VIDEO_STAGE_SKILL_IDS = {
    "creator_profile": "analysis.video_creator_profile",
    "video_quality": "analysis.video_quality",
    "incentive_fit": "analysis.incentive_fit",
}
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
    xhs_creator_profile_material_id: str
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
    evidenceScope: dict[str, Any] = Field(default_factory=dict)
    evidenceConfidence: str = ""
    evidenceLimitations: list[str] = Field(default_factory=list)
    recommendedNextEvidence: list[str] = Field(default_factory=list)


class CreatorProfileStageResult(BaseModel):
    creatorProfile: CreatorProfileData


class VideoQualityDimensionScore(BaseModel):
    dimension: str
    score: int
    reason: str = ""

    @field_validator("score", mode="before")
    @classmethod
    def normalize_dimension_score(cls, value: Any) -> int:
        return normalize_score(value)


class VideoQualityData(BaseModel):
    overallScore: int
    level: str
    dimensionScores: list[VideoQualityDimensionScore] = Field(default_factory=list)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    evidenceScope: dict[str, Any] = Field(default_factory=dict)
    evidenceConfidence: str = ""
    evidenceLimitations: list[str] = Field(default_factory=list)
    cannotAssess: list[str] = Field(default_factory=list)
    recommendedNextEvidence: list[str] = Field(default_factory=list)

    @field_validator("overallScore", mode="before")
    @classmethod
    def normalize_overall_score(cls, value: Any) -> int:
        return normalize_score(value)


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
    evidenceScope: dict[str, Any] = Field(default_factory=dict)
    evidenceConfidence: str = ""
    evidenceLimitations: list[str] = Field(default_factory=list)
    recommendedNextEvidence: list[str] = Field(default_factory=list)

    @field_validator("fitScore", mode="before")
    @classmethod
    def normalize_fit_score(cls, value: Any) -> int:
        return normalize_score(value)


class IncentiveFitStageResult(BaseModel):
    incentiveFit: IncentiveFitData


def normalize_score(value: Any) -> int:
    if isinstance(value, str):
        stripped = value.strip().rstrip("%")
        value = float(stripped)
    if isinstance(value, bool):
        raise ValueError("score must be numeric")
    if isinstance(value, int):
        return max(0, min(100, value))
    if isinstance(value, float):
        score = value * 100 if 0 <= value <= 1 else value
        return max(0, min(100, round(score)))
    raise ValueError("score must be numeric")


class VideoCreatorQualityModelProvider(Protocol):
    async def creator_profile(
        self,
        *,
        positioning: str,
        video_creator_samples: str,
        video_creator_evidence_pack: dict[str, Any],
        media_assets: list[dict[str, Any]],
        pm_rubric: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def video_quality(
        self,
        *,
        positioning: str,
        video_creator_samples: str,
        video_creator_evidence_pack: dict[str, Any],
        media_assets: list[dict[str, Any]],
        creator_profile: dict[str, Any] | None,
        pm_rubric: dict[str, Any],
    ) -> dict[str, Any]: ...

    async def incentive_fit(
        self,
        *,
        positioning: str,
        creator_profile: dict[str, Any] | None,
        video_quality: dict[str, Any] | None,
        pm_rubric: dict[str, Any],
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
        "evidenceScope": {},
        "evidenceConfidence": "",
        "evidenceLimitations": [],
        "recommendedNextEvidence": [],
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
        "evidenceScope": {},
        "evidenceConfidence": "",
        "evidenceLimitations": [],
        "cannotAssess": [],
        "recommendedNextEvidence": [],
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
        "evidenceScope": {},
        "evidenceConfidence": "",
        "evidenceLimitations": [],
        "recommendedNextEvidence": [],
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
        video_creator_evidence_pack: dict[str, Any],
        media_assets: list[dict[str, Any]],
        pm_rubric: dict[str, Any],
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
        video_creator_evidence_pack: dict[str, Any],
        media_assets: list[dict[str, Any]],
        creator_profile: dict[str, Any] | None,
        pm_rubric: dict[str, Any],
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
        pm_rubric: dict[str, Any],
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
        video_creator_evidence_pack: dict[str, Any],
        media_assets: list[dict[str, Any]],
        pm_rubric: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.VIDEO_CREATOR_PROFILE,
            {
                "positioning": positioning,
                "videoCreatorSamples": video_creator_samples,
                "videoCreatorEvidencePack": video_creator_evidence_pack,
                "mediaAssets": media_assets,
                "pmRubric": pm_rubric,
            },
        )
        return response.output

    async def video_quality(
        self,
        *,
        positioning: str,
        video_creator_samples: str,
        video_creator_evidence_pack: dict[str, Any],
        media_assets: list[dict[str, Any]],
        creator_profile: dict[str, Any] | None,
        pm_rubric: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.VIDEO_QUALITY_ANALYSIS,
            {
                "positioning": positioning,
                "videoCreatorSamples": video_creator_samples,
                "videoCreatorEvidencePack": video_creator_evidence_pack,
                "mediaAssets": media_assets,
                "creatorProfile": creator_profile,
                "pmRubric": pm_rubric,
            },
        )
        return response.output

    async def incentive_fit(
        self,
        *,
        positioning: str,
        creator_profile: dict[str, Any] | None,
        video_quality: dict[str, Any] | None,
        pm_rubric: dict[str, Any],
    ) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.INCENTIVE_FIT_ANALYSIS,
            {
                "positioning": positioning,
                "creatorProfile": creator_profile,
                "videoQuality": video_quality,
                "pmRubric": pm_rubric,
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
        skill_service: SkillService | None = None,
    ) -> None:
        self.database = database
        self.checkpoint_repository = checkpoint_repository
        self.analysis_service = analysis_service
        self.fake_provider = fake_provider
        self.live_provider = live_provider
        self.skill_service = skill_service
        self.graph = self._build_graph()

    def skill_execution_context(
        self, workspace_id: str, stage_key: str
    ) -> dict[str, Any]:
        skill_id = VIDEO_STAGE_SKILL_IDS[stage_key]
        if self.skill_service is None:
            return {"skillId": skill_id, "pmRubric": {}}
        skill = self.skill_service.get_by_skill_id(workspace_id, skill_id)
        rubric = skill.context_policy.get("pmRubric", {})
        if not isinstance(rubric, dict):
            rubric = {}
        return {
            "skillId": skill.skill_id,
            "skillAssetId": skill.id,
            "skillVersion": skill.version,
            "pmRubric": rubric,
        }

    def initial_state_for_run(self, run_id: str) -> VideoCreatorQualityState:
        run = self.analysis_service.get(run_id)
        if run.workflow_type != WorkflowType.VIDEO_CREATOR_QUALITY:
            raise ValidationError("Only video creator quality runs can use this workflow")
        snapshot = run.input_snapshot
        samples = snapshot["videoCreatorSamples"]
        xhs_profile = snapshot.get("xhsCreatorProfile") or {}
        return VideoCreatorQualityState(
            run_id=run.id,
            workspace_id=run.workspace_id,
            positioning_snapshot=str(snapshot["accountPositioning"]),
            video_creator_samples_material_id=str(samples["materialId"]),
            xhs_creator_profile_material_id=(
                str(xhs_profile.get("materialId"))
                if isinstance(xhs_profile, dict) and xhs_profile.get("materialId")
                else ""
            ),
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
            skill_context = self.service.skill_execution_context(
                str(updated["workspace_id"]), "creator_profile"
            )
            output = await self.provider().creator_profile(
                positioning=str(self.snapshot()["accountPositioning"]),
                video_creator_samples=str(
                    self.snapshot()["videoCreatorSamples"]["content"]
                ),
                video_creator_evidence_pack=self.snapshot().get(
                    "videoCreatorEvidencePack", {}
                ),
                media_assets=self.snapshot().get("mediaAssets", []),
                pm_rubric=skill_context["pmRubric"],
            )
            result = CreatorProfileStageResult.model_validate(output).model_dump(
                mode="json"
            )
            result = self.with_evidence_guardrails(result, "creatorProfile")
            self.service.analysis_service.update_stage(
                self.run_id,
                "creator_profile",
                AnalysisStageUpdate(
                    status=AnalysisRunStatus.COMPLETED,
                    result=result,
                    model_metadata={
                        "engine": "langgraph",
                        "skillContext": skill_context,
                    },
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
            skill_context = self.service.skill_execution_context(
                str(updated["workspace_id"]), "video_quality"
            )
            output = await self.provider().video_quality(
                positioning=str(self.snapshot()["accountPositioning"]),
                video_creator_samples=str(
                    self.snapshot()["videoCreatorSamples"]["content"]
                ),
                video_creator_evidence_pack=self.snapshot().get(
                    "videoCreatorEvidencePack", {}
                ),
                media_assets=self.snapshot().get("mediaAssets", []),
                creator_profile=updated.get("creator_profile"),
                pm_rubric=skill_context["pmRubric"],
            )
            result = VideoQualityStageResult.model_validate(output).model_dump(
                mode="json"
            )
            result = self.with_evidence_guardrails(result, "videoQuality")
            self.service.analysis_service.update_stage(
                self.run_id,
                "video_quality",
                AnalysisStageUpdate(
                    status=AnalysisRunStatus.COMPLETED,
                    result=result,
                    model_metadata={
                        "engine": "langgraph",
                        "skillContext": skill_context,
                    },
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
            skill_context = self.service.skill_execution_context(
                str(updated["workspace_id"]), "incentive_fit"
            )
            output = await self.provider().incentive_fit(
                positioning=str(self.snapshot()["accountPositioning"]),
                creator_profile=updated.get("creator_profile"),
                video_quality=updated.get("video_quality"),
                pm_rubric=skill_context["pmRubric"],
            )
            result = IncentiveFitStageResult.model_validate(output).model_dump(
                mode="json"
            )
            result = self.with_evidence_guardrails(result, "incentiveFit")
            self.service.analysis_service.update_stage(
                self.run_id,
                "incentive_fit",
                AnalysisStageUpdate(
                    status=AnalysisRunStatus.COMPLETED,
                    result=result,
                    model_metadata={
                        "engine": "langgraph",
                        "skillContext": skill_context,
                    },
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

    def with_evidence_guardrails(
        self, result: dict[str, Any], root_key: str
    ) -> dict[str, Any]:
        root = dict(result.get(root_key) or {})
        evidence_pack = self.snapshot().get("videoCreatorEvidencePack", {})
        scope = self.evidence_scope(evidence_pack)
        root["evidenceScope"] = {**dict(root.get("evidenceScope") or {}), **scope}
        root["evidenceLimitations"] = self.merge_strings(
            root.get("evidenceLimitations"), evidence_pack.get("evidenceLimitations")
        )
        root["recommendedNextEvidence"] = self.merge_strings(
            root.get("recommendedNextEvidence"),
            evidence_pack.get("recommendedNextEvidence")
            or self.recommended_next_evidence(scope),
        )
        root["evidenceConfidence"] = self.evidence_confidence(scope)
        if root_key == "videoQuality":
            cannot_assess = []
            if not scope.get("hasVideoUnderstanding"):
                cannot_assess.extend(
                    [
                        "无法可靠评估完整视频的镜头调度、剪辑节奏、口型一致性和音频表现。",
                        "无法确认视频实际完播体验，只能基于标题、正文、评论、封面或已有转写做间接判断。",
                    ]
                )
            if scope.get("mediaAssetCount", 0) and not scope.get(
                "hasImageUnderstanding"
            ):
                cannot_assess.append(
                    "存在封面或截图资产但缺少图片理解结果，无法可靠评价视觉完成度。"
                )
            root["cannotAssess"] = self.merge_strings(root.get("cannotAssess"), cannot_assess)
        return {root_key: root}

    @staticmethod
    def evidence_scope(evidence_pack: dict[str, Any]) -> dict[str, Any]:
        if isinstance(evidence_pack.get("evidenceScope"), dict):
            return dict(evidence_pack["evidenceScope"])
        media_refs = (
            evidence_pack.get("mediaAssetRefs")
            if isinstance(evidence_pack.get("mediaAssetRefs"), list)
            else []
        )
        note_stats = (
            evidence_pack.get("noteStats")
            if isinstance(evidence_pack.get("noteStats"), dict)
            else {}
        )
        return {
            "sourceType": (evidence_pack.get("source") or {}).get("type"),
            "hasVideoNotes": bool(evidence_pack.get("videoNotes")),
            "hasVideoUnderstanding": any(
                isinstance(ref, dict) and ref.get("hasVideoUnderstanding")
                for ref in media_refs
            ),
            "hasImageUnderstanding": any(
                isinstance(ref, dict) and ref.get("hasImageUnderstanding")
                for ref in media_refs
            ),
            "hasComments": bool(note_stats.get("commentCount")),
            "mediaAssetCount": len(media_refs),
        }

    @staticmethod
    def evidence_confidence(scope: dict[str, Any]) -> str:
        if scope.get("hasVideoUnderstanding"):
            return "高"
        if scope.get("hasImageUnderstanding") or scope.get("hasVideoNotes"):
            return "中"
        return "低"

    @staticmethod
    def recommended_next_evidence(scope: dict[str, Any]) -> list[str]:
        recommendations: list[str] = []
        if not scope.get("hasVideoUnderstanding"):
            recommendations.append(
                "补充至少 1 条代表视频的视频理解结果、关键帧理解结果或人工转写。"
            )
        if scope.get("mediaAssetCount", 0) and not scope.get("hasImageUnderstanding"):
            recommendations.append("补充封面或关键截图的图片理解结果。")
        if not scope.get("hasComments"):
            recommendations.append("补充评论样本，验证受众反馈和催更/转化信号。")
        return recommendations

    @staticmethod
    def merge_strings(primary: Any, fallback: Any) -> list[str]:
        values: list[str] = []
        for source in [primary, fallback]:
            if isinstance(source, list):
                candidates = source
            elif source:
                candidates = [source]
            else:
                candidates = []
            for candidate in candidates:
                text = str(candidate).strip()
                if text and text not in values:
                    values.append(text)
        return values

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
            "xhs_creator_profile_material_id": state.get(
                "xhs_creator_profile_material_id"
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
