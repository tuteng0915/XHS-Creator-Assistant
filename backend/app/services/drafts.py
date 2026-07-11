from __future__ import annotations

import json

from app.db.database import SQLiteDatabase
from app.models import DraftResponse, DraftSummary, DraftUpdate
from app.repositories.drafts import DraftRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import as_iso, utc_now


class DraftService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: DraftRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository

    def list(self, workspace_id: str) -> list[DraftSummary]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(connection, workspace_id)
        return [DraftSummary.model_validate(row) for row in rows]

    def get(self, draft_id: str) -> DraftResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, draft_id)
        return self._to_response(row)

    def update(self, draft_id: str, payload: DraftUpdate) -> DraftResponse:
        with self.database.transaction() as connection:
            row = self.repository.update_editable_content(
                connection,
                draft_id=draft_id,
                editable_content_json=json.dumps(
                    payload.editable_content, ensure_ascii=False
                ),
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    @staticmethod
    def _to_response(row: dict) -> DraftResponse:
        return DraftResponse.model_validate(
            {
                **row,
                "generated_snapshot": json.loads(row["generated_snapshot_json"]),
                "editable_content": json.loads(row["editable_content_json"]),
                "input_snapshot": json.loads(row["input_snapshot_json"]),
                "stage_errors": json.loads(row["stage_errors_json"]),
                "model_metadata": json.loads(row["model_metadata_json"]),
            }
        )
