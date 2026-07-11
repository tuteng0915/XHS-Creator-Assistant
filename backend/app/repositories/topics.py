import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError


class TopicRepository:
    def create(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        title: str,
        angle: str,
        associated_pain_point: str,
        why_it_fits: str,
        generated_snapshot_json: str,
        source_analysis_run_id: str | None,
        source_workflow: str,
        now: str,
    ) -> dict:
        topic_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO topics(
                id, workspace_id, title, angle, associated_pain_point, why_it_fits,
                generated_snapshot_json, source_analysis_run_id, source_workflow,
                status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'candidate', ?, ?)
            """,
            (
                topic_id,
                workspace_id,
                title,
                angle,
                associated_pain_point,
                why_it_fits,
                generated_snapshot_json,
                source_analysis_run_id,
                source_workflow,
                now,
                now,
            ),
        )
        return self.get(connection, topic_id)

    def list(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        source_workflow: str | None = None,
        status: str | None = None,
    ) -> list[dict]:
        clauses = ["workspace_id = ?"]
        args: list[str] = [workspace_id]
        if source_workflow is not None:
            clauses.append("source_workflow = ?")
            args.append(source_workflow)
        if status is not None:
            clauses.append("status = ?")
            args.append(status)
        rows = connection.execute(
            f"""
            SELECT * FROM topics
            WHERE {' AND '.join(clauses)}
            ORDER BY updated_at DESC, id
            """,
            args,
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, connection: sqlite3.Connection, topic_id: str) -> dict:
        row = connection.execute("SELECT * FROM topics WHERE id = ?", (topic_id,)).fetchone()
        if row is None:
            raise NotFoundError("Topic not found")
        return dict(row)

    def update(
        self,
        connection: sqlite3.Connection,
        *,
        topic_id: str,
        title: str | None,
        angle: str | None,
        expected_updated_at: str,
        now: str,
    ) -> dict:
        current = self.get(connection, topic_id)
        if current["updated_at"] != expected_updated_at:
            raise ConflictError("Topic changed since it was loaded")
        cursor = connection.execute(
            """
            UPDATE topics
            SET title = ?, angle = ?, updated_at = ?
            WHERE id = ? AND updated_at = ?
            """,
            (
                current["title"] if title is None else title,
                current["angle"] if angle is None else angle,
                now,
                topic_id,
                expected_updated_at,
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Topic changed since it was loaded")
        return self.get(connection, topic_id)

    def select(self, connection: sqlite3.Connection, *, topic_id: str, now: str) -> dict:
        current = self.get(connection, topic_id)
        connection.execute(
            """
            UPDATE topics
            SET status = 'candidate', updated_at = ?
            WHERE workspace_id = ? AND status = 'selected' AND id != ?
            """,
            (now, current["workspace_id"], topic_id),
        )
        connection.execute(
            """
            UPDATE topics
            SET status = 'selected', updated_at = ?
            WHERE id = ?
            """,
            (now, topic_id),
        )
        connection.execute(
            """
            INSERT INTO workspace_current_topics(workspace_id, topic_id, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(workspace_id) DO UPDATE
            SET topic_id = excluded.topic_id, updated_at = excluded.updated_at
            """,
            (current["workspace_id"], topic_id, now),
        )
        return self.get(connection, topic_id)

    def archive(self, connection: sqlite3.Connection, *, topic_id: str, now: str) -> dict:
        current = self.get(connection, topic_id)
        connection.execute(
            "UPDATE topics SET status = 'archived', updated_at = ? WHERE id = ?",
            (now, topic_id),
        )
        connection.execute(
            "DELETE FROM workspace_current_topics WHERE workspace_id = ? AND topic_id = ?",
            (current["workspace_id"], topic_id),
        )
        return self.get(connection, topic_id)
