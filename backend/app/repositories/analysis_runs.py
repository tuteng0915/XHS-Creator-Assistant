from __future__ import annotations

import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError, ValidationError

TERMINAL_STATUSES = {"completed", "partially_completed", "failed"}


class AnalysisRunRepository:
    def create(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        workflow_type: str,
        input_snapshot_json: str,
        idempotency_key: str | None,
        now: str,
    ) -> dict:
        run_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO analysis_runs(
                id, workspace_id, workflow_type, status, input_snapshot_json,
                stage_results_json, stage_errors_json, model_metadata_json,
                idempotency_key, created_at, updated_at
            ) VALUES (?, ?, ?, 'pending', ?, '{}', '{}', '{}', ?, ?, ?)
            """,
            (
                run_id,
                workspace_id,
                workflow_type,
                input_snapshot_json,
                idempotency_key,
                now,
                now,
            ),
        )
        return self.get(connection, run_id)

    def get_by_idempotency_key(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        idempotency_key: str,
    ) -> dict | None:
        row = connection.execute(
            """
            SELECT * FROM analysis_runs
            WHERE workspace_id = ? AND idempotency_key = ?
            """,
            (workspace_id, idempotency_key),
        ).fetchone()
        return dict(row) if row is not None else None

    def list(self, connection: sqlite3.Connection, workspace_id: str) -> list[dict]:
        rows = connection.execute(
            """
            SELECT * FROM analysis_runs
            WHERE workspace_id = ?
            ORDER BY updated_at DESC, id
            """,
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_unfinished(self, connection: sqlite3.Connection) -> list[dict]:
        rows = connection.execute(
            """
            SELECT * FROM analysis_runs
            WHERE status IN ('pending', 'running')
            ORDER BY created_at ASC, id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, connection: sqlite3.Connection, run_id: str) -> dict:
        row = connection.execute(
            "SELECT * FROM analysis_runs WHERE id = ?", (run_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Analysis run not found")
        return dict(row)

    def set_status(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        status: str,
        model_metadata_json: str,
        now: str,
    ) -> dict:
        current = self.get(connection, run_id)
        if current["status"] in TERMINAL_STATUSES:
            raise ConflictError("Completed analysis runs are immutable")

        started_at = current["started_at"]
        completed_at = current["completed_at"]
        if status == "running" and started_at is None:
            started_at = now
        if status in TERMINAL_STATUSES:
            completed_at = now
            if started_at is None:
                started_at = current["created_at"]
        if status == "pending":
            raise ValidationError("Analysis run cannot be transitioned back to pending")

        connection.execute(
            """
            UPDATE analysis_runs
            SET status = ?, model_metadata_json = ?, started_at = ?,
                completed_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, model_metadata_json, started_at, completed_at, now, run_id),
        )
        return self.get(connection, run_id)

    def update_stage(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        status: str,
        stage_results_json: str,
        stage_errors_json: str,
        model_metadata_json: str,
        now: str,
    ) -> dict:
        current = self.get(connection, run_id)
        if current["status"] in TERMINAL_STATUSES:
            raise ConflictError("Completed analysis runs are immutable")

        started_at = current["started_at"] or now
        run_status = current["status"]
        if run_status == "pending":
            run_status = "running"

        connection.execute(
            """
            UPDATE analysis_runs
            SET status = ?, stage_results_json = ?, stage_errors_json = ?,
                model_metadata_json = ?, started_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                run_status,
                stage_results_json,
                stage_errors_json,
                model_metadata_json,
                started_at,
                now,
                run_id,
            ),
        )
        return self.get(connection, run_id)

    def update_review(
        self,
        connection: sqlite3.Connection,
        *,
        run_id: str,
        user_notes: str,
        review_status: str,
        expected_updated_at: str,
        now: str,
    ) -> dict:
        self.get(connection, run_id)
        cursor = connection.execute(
            """
            UPDATE analysis_runs
            SET user_notes = ?, review_status = ?, updated_at = ?
            WHERE id = ? AND updated_at = ?
            """,
            (user_notes, review_status, now, run_id, expected_updated_at),
        )
        if cursor.rowcount == 0:
            raise ConflictError("Analysis run changed since it was loaded")
        return self.get(connection, run_id)
