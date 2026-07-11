from __future__ import annotations

import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError

SIMULATION_TERMINAL_STATUSES = {"completed", "partially_completed", "failed"}


class SimulationRunRepository:
    def create(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        topic_id: str | None,
        draft_id: str | None,
        input_snapshot_json: str,
        now: str,
    ) -> dict:
        simulation_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO simulation_runs(
                id, workspace_id, topic_id, draft_id, status, input_snapshot_json,
                persona_definitions_json, reaction_results_json, debate_results_json,
                synthesis_json, stage_errors_json, model_metadata_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'pending', ?, '[]', '[]', '[]', '{}', '{}', '{}', ?, ?)
            """,
            (
                simulation_id,
                workspace_id,
                topic_id,
                draft_id,
                input_snapshot_json,
                now,
                now,
            ),
        )
        return self.get(connection, simulation_id)

    def list(self, connection: sqlite3.Connection, workspace_id: str) -> list[dict]:
        rows = connection.execute(
            """
            SELECT * FROM simulation_runs
            WHERE workspace_id = ?
            ORDER BY updated_at DESC, id
            """,
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_unfinished(self, connection: sqlite3.Connection) -> list[dict]:
        rows = connection.execute(
            """
            SELECT * FROM simulation_runs
            WHERE status IN ('pending', 'running')
            ORDER BY created_at ASC, id
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, connection: sqlite3.Connection, simulation_id: str) -> dict:
        row = connection.execute(
            "SELECT * FROM simulation_runs WHERE id = ?", (simulation_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Simulation run not found")
        return dict(row)

    def update(
        self,
        connection: sqlite3.Connection,
        *,
        simulation_id: str,
        status: str,
        persona_definitions_json: str,
        reaction_results_json: str,
        debate_results_json: str,
        synthesis_json: str,
        stage_errors_json: str,
        model_metadata_json: str,
        now: str,
        completed_at: str | None = None,
    ) -> dict:
        current = self.get(connection, simulation_id)
        if current["status"] in SIMULATION_TERMINAL_STATUSES:
            raise ConflictError("Completed simulation runs are immutable")
        started_at = current["started_at"] or now
        connection.execute(
            """
            UPDATE simulation_runs
            SET status = ?, persona_definitions_json = ?, reaction_results_json = ?,
                debate_results_json = ?, synthesis_json = ?, stage_errors_json = ?,
                model_metadata_json = ?, started_at = ?, completed_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                persona_definitions_json,
                reaction_results_json,
                debate_results_json,
                synthesis_json,
                stage_errors_json,
                model_metadata_json,
                started_at,
                completed_at,
                now,
                simulation_id,
            ),
        )
        return self.get(connection, simulation_id)
