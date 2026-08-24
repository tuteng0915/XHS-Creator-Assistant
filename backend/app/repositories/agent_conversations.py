from __future__ import annotations

import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError


class AgentConversationRepository:
    def create(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        agent_asset_id: str,
        title: str,
        context_target_json: str,
        now: str,
    ) -> dict:
        conversation_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO agent_conversations(
                id, workspace_id, agent_asset_id, title, context_target_json,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                conversation_id,
                workspace_id,
                agent_asset_id,
                title,
                context_target_json,
                now,
                now,
            ),
        )
        return self.get(connection, conversation_id)

    def list(self, connection: sqlite3.Connection, workspace_id: str) -> list[dict]:
        rows = connection.execute(
            """
            SELECT * FROM agent_conversations
            WHERE workspace_id = ?
            ORDER BY updated_at DESC, id
            """,
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, connection: sqlite3.Connection, conversation_id: str) -> dict:
        row = connection.execute(
            "SELECT * FROM agent_conversations WHERE id = ?", (conversation_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Agent conversation not found")
        return dict(row)

    def update(
        self,
        connection: sqlite3.Connection,
        *,
        conversation_id: str,
        title: str | None,
        status: str | None,
        expected_updated_at: str,
        now: str,
    ) -> dict:
        current = self.get(connection, conversation_id)
        if current["updated_at"] != expected_updated_at:
            raise ConflictError("Agent conversation changed since it was loaded")
        cursor = connection.execute(
            """
            UPDATE agent_conversations
            SET title = ?, status = ?, updated_at = ?
            WHERE id = ? AND updated_at = ?
            """,
            (
                current["title"] if title is None else title,
                current["status"] if status is None else status,
                now,
                conversation_id,
                expected_updated_at,
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Agent conversation changed since it was loaded")
        return self.get(connection, conversation_id)

    def touch(
        self, connection: sqlite3.Connection, *, conversation_id: str, now: str
    ) -> dict:
        connection.execute(
            "UPDATE agent_conversations SET updated_at = ? WHERE id = ?",
            (now, conversation_id),
        )
        return self.get(connection, conversation_id)

    def create_message(
        self,
        connection: sqlite3.Connection,
        *,
        conversation_id: str,
        client_message_key: str | None = None,
        role: str,
        content: str,
        context_pack_json: str,
        asset_refs_json: str,
        proposed_actions_json: str,
        model_metadata_json: str,
        now: str,
    ) -> dict:
        message_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO agent_messages(
                id, conversation_id, client_message_key, role, content, context_pack_json,
                asset_refs_json, proposed_actions_json, model_metadata_json,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                conversation_id,
                client_message_key,
                role,
                content,
                context_pack_json,
                asset_refs_json,
                proposed_actions_json,
                model_metadata_json,
                now,
            ),
        )
        self.touch(connection, conversation_id=conversation_id, now=now)
        return self.get_message(connection, message_id)

    def get_user_message_by_client_key(
        self,
        connection: sqlite3.Connection,
        *,
        conversation_id: str,
        client_message_key: str,
    ) -> dict | None:
        row = connection.execute(
            """
            SELECT * FROM agent_messages
            WHERE conversation_id = ?
              AND role = 'user'
              AND client_message_key = ?
            """,
            (conversation_id, client_message_key),
        ).fetchone()
        return dict(row) if row is not None else None

    def update_message(
        self,
        connection: sqlite3.Connection,
        *,
        message_id: str,
        content: str,
        context_pack_json: str,
        asset_refs_json: str,
        proposed_actions_json: str,
        model_metadata_json: str,
        now: str,
    ) -> dict:
        current = self.get_message(connection, message_id)
        connection.execute(
            """
            UPDATE agent_messages
            SET content = ?,
                context_pack_json = ?,
                asset_refs_json = ?,
                proposed_actions_json = ?,
                model_metadata_json = ?
            WHERE id = ?
            """,
            (
                content,
                context_pack_json,
                asset_refs_json,
                proposed_actions_json,
                model_metadata_json,
                message_id,
            ),
        )
        self.touch(connection, conversation_id=current["conversation_id"], now=now)
        return self.get_message(connection, message_id)

    def list_messages(
        self, connection: sqlite3.Connection, conversation_id: str
    ) -> list[dict]:
        rows = connection.execute(
            """
            SELECT * FROM agent_messages
            WHERE conversation_id = ?
            ORDER BY created_at ASC, id
            """,
            (conversation_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_message(self, connection: sqlite3.Connection, message_id: str) -> dict:
        row = connection.execute(
            "SELECT * FROM agent_messages WHERE id = ?", (message_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Agent message not found")
        return dict(row)
