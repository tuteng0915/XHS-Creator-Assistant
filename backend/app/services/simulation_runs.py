from __future__ import annotations

import json

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import (
    RunReviewUpdate,
    SimulationRunCreate,
    SimulationRunResponse,
    SimulationRunStatus,
    SimulationRunSummary,
)
from app.repositories.drafts import DraftRepository
from app.repositories.simulation_runs import SimulationRunRepository
from app.repositories.topics import TopicRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import as_iso, utc_now


class SimulationRunService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: SimulationRunRepository,
        workspace_repository: WorkspaceRepository,
        topic_repository: TopicRepository,
        draft_repository: DraftRepository,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.topic_repository = topic_repository
        self.draft_repository = draft_repository

    def create(self, workspace_id: str, payload: SimulationRunCreate) -> SimulationRunResponse:
        target_count = sum(
            1 for value in (payload.topic_id, payload.draft_id, payload.manual_topic) if value
        )
        if target_count != 1:
            raise ValidationError("Choose exactly one topic, draft, or manual topic")
        with self.database.transaction() as connection:
            workspace = self.workspace_repository.get(connection, workspace_id)
            audience = None
            if payload.audience_analysis_id:
                row = connection.execute(
                    "SELECT * FROM audience_analyses WHERE id=? "
                    "AND workspace_id=? AND status='completed'",
                    (payload.audience_analysis_id, workspace_id),
                ).fetchone()
                if row is None:
                    raise ValidationError("请选择当前账号已完成的受众分析")
                audience = json.loads(row["result_json"])
            topic_snapshot: dict | None = None
            draft_snapshot: dict | None = None
            topic_id: str | None = payload.topic_id
            if payload.draft_id:
                draft = self.draft_repository.get(connection, payload.draft_id)
                if draft["workspace_id"] != workspace_id:
                    raise ValidationError("Draft belongs to another workspace")
                topic_id = draft["topic_id"]
                topic = self.topic_repository.get(connection, draft["topic_id"])
                topic_snapshot = {
                    "topicId": topic["id"],
                    "title": topic["title"],
                    "angle": topic["angle"],
                    "body": topic.get("body", ""),
                    "associatedPainPoint": topic["associated_pain_point"],
                    "whyItFits": topic["why_it_fits"],
                    "sourceWorkflow": topic["source_workflow"],
                }
                draft_snapshot = {
                    "draftId": draft["id"],
                    "topicId": draft["topic_id"],
                    "generatedSnapshot": json.loads(draft["generated_snapshot_json"]),
                    "editableContent": json.loads(draft["editable_content_json"]),
                    "sourceWorkflow": draft["source_workflow"],
                    "updatedAt": draft["updated_at"],
                }
            if payload.topic_id:
                topic = self.topic_repository.get(connection, payload.topic_id)
                if topic["workspace_id"] != workspace_id:
                    raise ValidationError("Topic belongs to another workspace")
                topic_snapshot = {
                    "topicId": topic["id"],
                    "title": topic["title"],
                    "angle": topic["angle"],
                    "body": topic.get("body", ""),
                    "associatedPainPoint": topic["associated_pain_point"],
                    "whyItFits": topic["why_it_fits"],
                    "sourceWorkflow": topic["source_workflow"],
                }
            snapshot = {
                "audienceAnalysisId": payload.audience_analysis_id,
                "audienceAnalysis": audience,
                "audiencePersonas": sorted(
                    audience["groups"], key=lambda g: g["estimatedPercent"], reverse=True
                )[:3]
                if audience
                else [],
                "mode": payload.mode,
                "workspaceId": workspace_id,
                "workspaceName": workspace["name"],
                "accountPositioning": workspace["account_positioning"],
                "targetType": "draft"
                if draft_snapshot
                else "topic"
                if topic_snapshot
                else "manual",
                "draft": draft_snapshot,
                "topic": topic_snapshot
                or {
                    "topicId": None,
                    "title": payload.manual_topic or "",
                    "angle": "",
                    "sourceWorkflow": "manual",
                },
            }
            row = self.repository.create(
                connection,
                workspace_id=workspace_id,
                topic_id=topic_id,
                draft_id=payload.draft_id,
                input_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
                now=utc_now(),
            )
        return self._to_response(row)

    def list(self, workspace_id: str) -> list[SimulationRunSummary]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(connection, workspace_id)
        return [SimulationRunSummary.model_validate(row) for row in rows]

    def get(self, simulation_id: str) -> SimulationRunResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, simulation_id)
        return self._to_response(row)

    def update_review(self, simulation_id: str, payload: RunReviewUpdate) -> SimulationRunResponse:
        current = self.get(simulation_id)
        user_notes = payload.user_notes if payload.user_notes is not None else current.user_notes
        review_status = (
            payload.review_status.value
            if payload.review_status is not None
            else current.review_status.value
        )
        if payload.user_notes is None and payload.review_status is None:
            raise ValidationError("No review changes provided")
        with self.database.transaction() as connection:
            row = self.repository.update_review(
                connection,
                simulation_id=simulation_id,
                user_notes=user_notes,
                review_status=review_status,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    def save_progress(
        self,
        simulation_id: str,
        *,
        status: SimulationRunStatus,
        persona_definitions: list[dict] | None = None,
        reaction_results: list[dict] | None = None,
        debate_results: list[dict] | None = None,
        synthesis: dict | None = None,
        stage_errors: dict[str, str] | None = None,
        model_metadata: dict | None = None,
        complete: bool = False,
    ) -> SimulationRunResponse:
        current = self.get(simulation_id)
        now = utc_now()
        with self.database.transaction() as connection:
            row = self.repository.update(
                connection,
                simulation_id=simulation_id,
                status=status.value,
                persona_definitions_json=json.dumps(
                    persona_definitions
                    if persona_definitions is not None
                    else current.persona_definitions,
                    ensure_ascii=False,
                ),
                reaction_results_json=json.dumps(
                    reaction_results if reaction_results is not None else current.reaction_results,
                    ensure_ascii=False,
                ),
                debate_results_json=json.dumps(
                    debate_results if debate_results is not None else current.debate_results,
                    ensure_ascii=False,
                ),
                synthesis_json=json.dumps(
                    synthesis if synthesis is not None else current.synthesis,
                    ensure_ascii=False,
                ),
                stage_errors_json=json.dumps(
                    stage_errors if stage_errors is not None else current.stage_errors,
                    ensure_ascii=False,
                ),
                model_metadata_json=json.dumps(
                    model_metadata if model_metadata is not None else current.model_metadata,
                    ensure_ascii=False,
                ),
                now=now,
                completed_at=now if complete else None,
            )
        return self._to_response(row)

    @staticmethod
    def _to_response(row: dict) -> SimulationRunResponse:
        return SimulationRunResponse.model_validate(
            {
                **row,
                "input_snapshot": json.loads(row["input_snapshot_json"]),
                "persona_definitions": json.loads(row["persona_definitions_json"]),
                "reaction_results": json.loads(row["reaction_results_json"]),
                "debate_results": json.loads(row["debate_results_json"]),
                "synthesis": json.loads(row["synthesis_json"]),
                "stage_errors": json.loads(row["stage_errors_json"]),
                "model_metadata": json.loads(row["model_metadata_json"]),
            }
        )
