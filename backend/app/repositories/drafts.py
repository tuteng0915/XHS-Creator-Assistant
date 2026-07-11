import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError


class DraftRepository:
    def create(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        topic_id: str,
        source_analysis_run_id: str | None,
        source_workflow: str,
        status: str,
        generated_snapshot_json: str,
        editable_content_json: str,
        input_snapshot_json: str,
        stage_errors_json: str,
        model_metadata_json: str,
        now: str,
        completed_at: str | None,
    ) -> dict:
        draft_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO drafts(
                id, workspace_id, topic_id, source_analysis_run_id, source_workflow,
                status, generated_snapshot_json, editable_content_json,
                input_snapshot_json, stage_errors_json, model_metadata_json,
                created_at, completed_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                draft_id,
                workspace_id,
                topic_id,
                source_analysis_run_id,
                source_workflow,
                status,
                generated_snapshot_json,
                editable_content_json,
                input_snapshot_json,
                stage_errors_json,
                model_metadata_json,
                now,
                completed_at,
                now,
            ),
        )
        return self.get(connection, draft_id)

    def list(self, connection: sqlite3.Connection, workspace_id: str) -> list[dict]:
        rows = connection.execute(
            """
            SELECT * FROM drafts
            WHERE workspace_id = ?
            ORDER BY updated_at DESC, id
            """,
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, connection: sqlite3.Connection, draft_id: str) -> dict:
        row = connection.execute(
            "SELECT * FROM drafts WHERE id = ?", (draft_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Draft not found")
        return dict(row)

    def update_editable_content(
        self,
        connection: sqlite3.Connection,
        *,
        draft_id: str,
        editable_content_json: str,
        expected_updated_at: str,
        now: str,
    ) -> dict:
        current = self.get(connection, draft_id)
        if current["updated_at"] != expected_updated_at:
            raise ConflictError("Draft changed since it was loaded")
        cursor = connection.execute(
            """
            UPDATE drafts
            SET editable_content_json = ?, updated_at = ?
            WHERE id = ? AND updated_at = ?
            """,
            (editable_content_json, now, draft_id, expected_updated_at),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Draft changed since it was loaded")
        return self.get(connection, draft_id)
