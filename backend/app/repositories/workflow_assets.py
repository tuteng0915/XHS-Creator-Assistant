from __future__ import annotations

import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError


class WorkflowAssetRepository:
    def create(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        workflow_id: str,
        display_name: str,
        purpose: str,
        entry_agent_ids_json: str,
        agent_plan_json: str,
        artifact_effect: str,
        version: str,
        now: str,
    ) -> dict:
        asset_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO workspace_workflows(
                id, workspace_id, workflow_id, display_name, purpose,
                entry_agent_ids_json, agent_plan_json, artifact_effect,
                source, status, version, user_notes, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'builtin', 'enabled', ?, '', ?, ?)
            """,
            (
                asset_id,
                workspace_id,
                workflow_id,
                display_name,
                purpose,
                entry_agent_ids_json,
                agent_plan_json,
                artifact_effect,
                version,
                now,
                now,
            ),
        )
        return self.get(connection, asset_id)

    def list(self, connection: sqlite3.Connection, workspace_id: str) -> list[dict]:
        rows = connection.execute(
            """
            SELECT * FROM workspace_workflows
            WHERE workspace_id = ?
            ORDER BY workflow_id
            """,
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, connection: sqlite3.Connection, workflow_asset_id: str) -> dict:
        row = connection.execute(
            "SELECT * FROM workspace_workflows WHERE id = ?", (workflow_asset_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Workflow not found")
        return dict(row)

    def get_by_workflow_id(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        workflow_id: str,
    ) -> dict | None:
        row = connection.execute(
            """
            SELECT * FROM workspace_workflows
            WHERE workspace_id = ? AND workflow_id = ?
            """,
            (workspace_id, workflow_id),
        ).fetchone()
        return dict(row) if row is not None else None

    def update(
        self,
        connection: sqlite3.Connection,
        *,
        workflow_asset_id: str,
        status: str | None,
        user_notes: str | None,
        expected_updated_at: str,
        now: str,
    ) -> dict:
        current = self.get(connection, workflow_asset_id)
        if current["updated_at"] != expected_updated_at:
            raise ConflictError("Workflow changed since it was loaded")
        cursor = connection.execute(
            """
            UPDATE workspace_workflows
            SET status = ?, user_notes = ?, updated_at = ?
            WHERE id = ? AND updated_at = ?
            """,
            (
                current["status"] if status is None else status,
                current["user_notes"] if user_notes is None else user_notes,
                now,
                workflow_asset_id,
                expected_updated_at,
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Workflow changed since it was loaded")
        return self.get(connection, workflow_asset_id)
