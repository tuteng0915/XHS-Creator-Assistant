import json

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import (
    TopicCreate,
    TopicResponse,
    TopicSourceWorkflow,
    TopicStatus,
    TopicUpdate,
)
from app.repositories.analysis_runs import AnalysisRunRepository
from app.repositories.topics import TopicRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import as_iso, utc_now


class TopicService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: TopicRepository,
        workspace_repository: WorkspaceRepository,
        analysis_repository: AnalysisRunRepository,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.analysis_repository = analysis_repository

    def create(self, workspace_id: str, payload: TopicCreate) -> TopicResponse:
        title = payload.title.strip()
        if not title:
            raise ValidationError("Topic title cannot be blank")
        with self.database.transaction() as connection:
            self.workspace_repository.get(connection, workspace_id)
            source_workflow = payload.source_workflow
            if payload.source_analysis_run_id:
                run = self.analysis_repository.get(connection, payload.source_analysis_run_id)
                if run["workspace_id"] != workspace_id:
                    raise ValidationError("Analysis run belongs to another workspace")
                source_workflow = TopicSourceWorkflow(run["workflow_type"])
            if source_workflow is None:
                source_workflow = TopicSourceWorkflow.MANUAL
            if (
                source_workflow == TopicSourceWorkflow.MANUAL
                and payload.source_analysis_run_id is not None
            ):
                raise ValidationError("Manual topics cannot reference an analysis run")
            if payload.source_analysis_run_id is not None:
                existing_topics = self.repository.list_by_source_analysis_run(
                    connection, payload.source_analysis_run_id
                )
                for existing_topic in existing_topics:
                    if existing_topic["title"] == title:
                        return self._to_response(existing_topic)
            generated_snapshot = payload.generated_snapshot
            if generated_snapshot is None and source_workflow != TopicSourceWorkflow.MANUAL:
                generated_snapshot = {
                    "title": title,
                    "angle": payload.angle,
                    "associatedPainPoint": payload.associated_pain_point,
                    "whyItFits": payload.why_it_fits,
                    "sourceAnalysisRunId": payload.source_analysis_run_id,
                    "sourceWorkflow": source_workflow.value,
                }
            row = self.repository.create(
                connection,
                workspace_id=workspace_id,
                title=title,
                angle=payload.angle,
                associated_pain_point=payload.associated_pain_point,
                why_it_fits=payload.why_it_fits,
                generated_snapshot_json=json.dumps(generated_snapshot or {}, ensure_ascii=False),
                source_analysis_run_id=payload.source_analysis_run_id,
                source_workflow=source_workflow.value,
                now=utc_now(),
            )
        return self._to_response(row)

    def list(
        self,
        workspace_id: str,
        *,
        source_workflow: TopicSourceWorkflow | None,
        status: TopicStatus | None,
    ) -> list[TopicResponse]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(
                connection,
                workspace_id=workspace_id,
                source_workflow=(source_workflow.value if source_workflow is not None else None),
                status=status.value if status is not None else None,
            )
        return [self._to_response(row) for row in rows]

    def get(self, topic_id: str) -> TopicResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, topic_id)
        return self._to_response(row)

    def update(self, topic_id: str, payload: TopicUpdate) -> TopicResponse:
        if all(
            value is None for value in (payload.title, payload.angle, payload.body, payload.pinned)
        ):
            raise ValidationError("At least one editable field is required")
        title = payload.title.strip() if payload.title is not None else None
        if title == "":
            raise ValidationError("Topic title cannot be blank")
        with self.database.transaction() as connection:
            row = self.repository.update(
                connection,
                topic_id=topic_id,
                title=title,
                angle=payload.angle,
                body=payload.body,
                pinned=payload.pinned,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    def select(self, topic_id: str) -> TopicResponse:
        with self.database.transaction() as connection:
            row = self.repository.select(connection, topic_id=topic_id, now=utc_now())
        return self._to_response(row)

    def archive(self, topic_id: str) -> TopicResponse:
        with self.database.transaction() as connection:
            row = self.repository.archive(connection, topic_id=topic_id, now=utc_now())
        return self._to_response(row)

    @staticmethod
    def _to_response(row: dict) -> TopicResponse:
        return TopicResponse.model_validate(
            {
                **row,
                "generated_snapshot": json.loads(row.get("generated_snapshot_json") or "{}"),
            }
        )
