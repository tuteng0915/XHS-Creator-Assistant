import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError


class WorkspaceRepository:
    SELECT = """
        SELECT
            workspace.id,
            workspace.name,
            positioning.positioning_text AS account_positioning,
            positioning.version_number AS positioning_version,
            current_topic.topic_id AS current_topic_id,
            workspace.created_at,
            workspace.updated_at
        FROM creator_workspaces AS workspace
        JOIN positioning_versions AS positioning
          ON positioning.id = workspace.current_positioning_version_id
        LEFT JOIN workspace_current_topics AS current_topic
          ON current_topic.workspace_id = workspace.id
    """

    def create(
        self,
        connection: sqlite3.Connection,
        *,
        name: str,
        account_positioning: str,
        now: str,
    ) -> dict:
        workspace_id = str(uuid4())
        positioning_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO creator_workspaces(id, name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (workspace_id, name, now, now),
        )
        connection.execute(
            """
            INSERT INTO positioning_versions(
                id, workspace_id, version_number, positioning_text, created_at
            ) VALUES (?, ?, 1, ?, ?)
            """,
            (positioning_id, workspace_id, account_positioning, now),
        )
        connection.execute(
            """
            UPDATE creator_workspaces
            SET current_positioning_version_id = ?
            WHERE id = ?
            """,
            (positioning_id, workspace_id),
        )
        return self.get(connection, workspace_id)

    def list(self, connection: sqlite3.Connection) -> list[dict]:
        rows = connection.execute(
            f"{self.SELECT} ORDER BY workspace.updated_at DESC, workspace.id"
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, connection: sqlite3.Connection, workspace_id: str) -> dict:
        row = connection.execute(
            f"{self.SELECT} WHERE workspace.id = ?", (workspace_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Workspace not found")
        return dict(row)

    def update(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        name: str | None,
        account_positioning: str | None,
        expected_updated_at: str,
        now: str,
    ) -> dict:
        current = self.get(connection, workspace_id)
        if current["updated_at"] != expected_updated_at:
            raise ConflictError("Workspace changed since it was loaded")

        next_name = current["name"] if name is None else name
        current_positioning_id = connection.execute(
            "SELECT current_positioning_version_id FROM creator_workspaces WHERE id = ?",
            (workspace_id,),
        ).fetchone()[0]

        if account_positioning is not None:
            next_version = current["positioning_version"] + 1
            current_positioning_id = str(uuid4())
            connection.execute(
                """
                INSERT INTO positioning_versions(
                    id, workspace_id, version_number, positioning_text, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    current_positioning_id,
                    workspace_id,
                    next_version,
                    account_positioning,
                    now,
                ),
            )

        cursor = connection.execute(
            """
            UPDATE creator_workspaces
            SET name = ?, current_positioning_version_id = ?, updated_at = ?
            WHERE id = ? AND updated_at = ?
            """,
            (
                next_name,
                current_positioning_id,
                now,
                workspace_id,
                expected_updated_at,
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Workspace changed since it was loaded")
        return self.get(connection, workspace_id)
