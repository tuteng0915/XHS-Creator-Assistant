import json
import sqlite3
from uuid import uuid4


class GraphCheckpointRepository:
    def save(
        self,
        connection: sqlite3.Connection,
        *,
        analysis_run_id: str,
        workflow_type: str,
        node_key: str,
        state: dict,
        now: str,
    ) -> dict:
        checkpoint_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO graph_checkpoints(
                id, analysis_run_id, workflow_type, node_key, state_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                checkpoint_id,
                analysis_run_id,
                workflow_type,
                node_key,
                json.dumps(state, ensure_ascii=False),
                now,
            ),
        )
        return self.latest(connection, analysis_run_id) or {}

    def latest(
        self, connection: sqlite3.Connection, analysis_run_id: str
    ) -> dict | None:
        row = connection.execute(
            """
            SELECT * FROM graph_checkpoints
            WHERE analysis_run_id = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (analysis_run_id,),
        ).fetchone()
        return dict(row) if row is not None else None
