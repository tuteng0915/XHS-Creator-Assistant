from __future__ import annotations

import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError


class AssetProposalRepository:
    def create(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        conversation_id: str,
        message_id: str,
        action_type: str,
        title: str,
        description: str,
        proposed_action_json: str,
        now: str,
    ) -> dict:
        proposal_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO asset_proposals(
                id, workspace_id, conversation_id, message_id, action_type,
                title, description, proposed_action_json, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                proposal_id,
                workspace_id,
                conversation_id,
                message_id,
                action_type,
                title,
                description,
                proposed_action_json,
                now,
                now,
            ),
        )
        return self.get(connection, proposal_id)

    def list(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
    ) -> list[dict]:
        clauses: list[str] = []
        args: list[str] = []
        if workspace_id is not None:
            clauses.append("workspace_id = ?")
            args.append(workspace_id)
        if conversation_id is not None:
            clauses.append("conversation_id = ?")
            args.append(conversation_id)
        if message_id is not None:
            clauses.append("message_id = ?")
            args.append(message_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = connection.execute(
            f"""
            SELECT * FROM asset_proposals
            {where}
            ORDER BY created_at DESC, id
            """,
            args,
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, connection: sqlite3.Connection, proposal_id: str) -> dict:
        row = connection.execute(
            "SELECT * FROM asset_proposals WHERE id = ?", (proposal_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Asset proposal not found")
        return dict(row)

    def set_status(
        self,
        connection: sqlite3.Connection,
        *,
        proposal_id: str,
        status: str,
        result_json: str,
        error: str,
        now: str,
    ) -> dict:
        current = self.get(connection, proposal_id)
        if current["status"] != "pending":
            raise ConflictError("Asset proposal is no longer pending")
        connection.execute(
            """
            UPDATE asset_proposals
            SET status = ?, result_json = ?, error = ?, updated_at = ?,
                applied_at = CASE WHEN ? = 'applied' THEN ? ELSE applied_at END
            WHERE id = ?
            """,
            (status, result_json, error, now, status, now, proposal_id),
        )
        return self.get(connection, proposal_id)

    def update_pending(
        self,
        connection: sqlite3.Connection,
        *,
        proposal_id: str,
        title: str | None,
        description: str | None,
        proposed_action_json: str | None,
        expected_updated_at: str,
        now: str,
    ) -> dict:
        current = self.get(connection, proposal_id)
        if current["status"] != "pending":
            raise ConflictError("Only pending asset proposals can be edited")
        if current["updated_at"] != expected_updated_at:
            raise ConflictError("Asset proposal has changed")
        next_title = title if title is not None else current["title"]
        next_description = (
            description if description is not None else current["description"]
        )
        next_action_json = (
            proposed_action_json
            if proposed_action_json is not None
            else current["proposed_action_json"]
        )
        connection.execute(
            """
            UPDATE asset_proposals
            SET title = ?, description = ?, proposed_action_json = ?, updated_at = ?
            WHERE id = ?
            """,
            (next_title, next_description, next_action_json, now, proposal_id),
        )
        return self.get(connection, proposal_id)
