from __future__ import annotations

import json
from typing import Any, Protocol

from pydantic import ValidationError as PydanticValidationError

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import DraftGenerateRequest, DraftResponse, DraftStatus, ModelOperation
from app.repositories.analysis_runs import AnalysisRunRepository
from app.repositories.drafts import DraftRepository
from app.repositories.topics import TopicRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import utc_now
from app.services.drafts import DraftService
from app.services.model_calls import ModelCallService
from app.workflows.account_diagnosis import StructureStageResult


class StructureModelProvider(Protocol):
    async def structure(self, *, context: dict[str, Any]) -> dict[str, Any]: ...


class FakeStructureModelProvider:
    async def structure(self, *, context: dict[str, Any]) -> dict[str, Any]:
        topic = str(context.get("topic") or "")
        background = str(context.get("background") or "")
        return {
            "structure": {
                "topicChosen": topic,
                "outline": [
                    {"sec": "开场钩子", "ct": f"用一个具体问题切入：{topic}"},
                    {"sec": "核心拆解", "ct": "分步骤说明判断标准、执行路径和常见误区。"},
                    {"sec": "行动收束", "ct": "给出读者可以立即收藏或执行的清单。"},
                ],
                "reuse": background or "问题切入 → 标准拆解 → 行动清单。",
            }
        }


class RealStructureModelProvider:
    def __init__(self, model_call_service: ModelCallService) -> None:
        self.model_call_service = model_call_service

    async def structure(self, *, context: dict[str, Any]) -> dict[str, Any]:
        response = await self.model_call_service.call_operation(
            ModelOperation.STRUCTURE,
            context,
        )
        return response.output


class DraftGenerationService:
    def __init__(
        self,
        database: SQLiteDatabase,
        draft_repository: DraftRepository,
        draft_service: DraftService,
        workspace_repository: WorkspaceRepository,
        topic_repository: TopicRepository,
        analysis_repository: AnalysisRunRepository,
        fake_provider: StructureModelProvider,
        live_provider: StructureModelProvider,
    ) -> None:
        self.database = database
        self.draft_repository = draft_repository
        self.draft_service = draft_service
        self.workspace_repository = workspace_repository
        self.topic_repository = topic_repository
        self.analysis_repository = analysis_repository
        self.fake_provider = fake_provider
        self.live_provider = live_provider

    async def generate_from_topic(
        self, topic_id: str, payload: DraftGenerateRequest
    ) -> DraftResponse:
        with self.database.read() as connection:
            topic = self.topic_repository.get(connection, topic_id)
            workspace = self.workspace_repository.get(connection, topic["workspace_id"])
            source_run = (
                self.analysis_repository.get(connection, topic["source_analysis_run_id"])
                if topic["source_analysis_run_id"]
                else None
            )

        input_snapshot = self._input_snapshot(workspace, topic, source_run, payload.mode)
        context = self._model_context(input_snapshot)
        provider = self.live_provider if payload.mode == "live" else self.fake_provider
        status = DraftStatus.COMPLETED
        generated_snapshot: dict[str, Any] = {}
        stage_errors: dict[str, str] = {}
        model_metadata = {"engine": "draft_generation", "mode": payload.mode}
        completed_at: str | None = utc_now()
        try:
            output = await provider.structure(context=context)
            generated_snapshot = StructureStageResult.model_validate(output).model_dump(
                mode="json"
            )
        except Exception as error:
            status = DraftStatus.FAILED
            stage_errors["structure"] = self._error_message(error)
            completed_at = utc_now()

        now = utc_now()
        with self.database.transaction() as connection:
            row = self.draft_repository.create(
                connection,
                workspace_id=topic["workspace_id"],
                topic_id=topic["id"],
                source_analysis_run_id=topic["source_analysis_run_id"],
                source_workflow=topic["source_workflow"],
                status=status.value,
                generated_snapshot_json=json.dumps(
                    generated_snapshot, ensure_ascii=False
                ),
                editable_content_json=json.dumps(
                    generated_snapshot, ensure_ascii=False
                ),
                input_snapshot_json=json.dumps(input_snapshot, ensure_ascii=False),
                stage_errors_json=json.dumps(stage_errors, ensure_ascii=False),
                model_metadata_json=json.dumps(model_metadata, ensure_ascii=False),
                now=now,
                completed_at=completed_at,
            )
        return self.draft_service._to_response(row)

    def _input_snapshot(
        self,
        workspace: dict,
        topic: dict,
        source_run: dict | None,
        mode: str,
    ) -> dict[str, Any]:
        stage_results = json.loads(source_run["stage_results_json"]) if source_run else {}
        analysis_context: dict[str, Any] = {}
        if source_run and source_run["workflow_type"] == "account_diagnosis":
            profile = stage_results.get("profile", {}).get("profile", {})
            analysis_context = {
                "voiceFingerprint": profile.get("voiceFingerprint", []),
                "viralStructure": profile.get("viralStructure", {}),
            }
        elif source_run and source_run["workflow_type"] == "trend_analysis":
            trend = stage_results.get("trend_analysis", {}).get("trendAnalysis", {})
            analysis_context = {
                "viralPatterns": trend.get("viralPatterns", []),
                "opportunityWindows": trend.get("opportunityWindows", []),
            }
        return {
            "mode": mode,
            "workspaceId": workspace["id"],
            "workspaceName": workspace["name"],
            "accountPositioning": workspace["account_positioning"],
            "positioningVersion": workspace["positioning_version"],
            "topic": {
                "topicId": topic["id"],
                "title": topic["title"],
                "angle": topic["angle"],
                "associatedPainPoint": topic["associated_pain_point"],
                "whyItFits": topic["why_it_fits"],
                "sourceWorkflow": topic["source_workflow"],
                "sourceAnalysisRunId": topic["source_analysis_run_id"],
            },
            "analysisContext": analysis_context,
        }

    @staticmethod
    def _model_context(snapshot: dict[str, Any]) -> dict[str, Any]:
        topic = snapshot["topic"]
        analysis_context = snapshot.get("analysisContext", {})
        background = ""
        if analysis_context.get("viralStructure"):
            background = json.dumps(
                {
                    "voiceFingerprint": analysis_context.get("voiceFingerprint", []),
                    "viralStructure": analysis_context.get("viralStructure", {}),
                },
                ensure_ascii=False,
            )
        elif analysis_context.get("viralPatterns"):
            background = "；".join(analysis_context.get("viralPatterns", []))
        return {
            "positioning": snapshot.get("accountPositioning", ""),
            "topic": topic.get("title", ""),
            "background": background,
        }

    @staticmethod
    def _error_message(error: Exception) -> str:
        if isinstance(error, PydanticValidationError):
            return "Model response failed structured validation"
        if isinstance(error, ValidationError):
            return str(error)
        return str(error) or error.__class__.__name__
