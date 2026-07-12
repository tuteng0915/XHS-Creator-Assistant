from __future__ import annotations

import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError


class SkillRepository:
    def create(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        skill_id: str,
        display_name: str,
        category: str,
        purpose: str,
        trigger_intents_json: str,
        required_inputs_json: str,
        optional_inputs_json: str,
        context_policy_json: str,
        output_schema_json: str,
        artifact_effect: str,
        side_effects_json: str,
        failure_mode: str,
        composable_with_json: str,
        implementation_refs_json: str,
        version: str,
        now: str,
        source: str = "builtin",
        definition_hash: str = "",
    ) -> dict:
        asset_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO workspace_skills(
                id, workspace_id, skill_id, display_name, category, purpose,
                trigger_intents_json, required_inputs_json, optional_inputs_json,
                context_policy_json, output_schema_json, artifact_effect,
                side_effects_json, failure_mode, composable_with_json,
                implementation_refs_json, source, status, version, user_notes,
                created_at, updated_at, definition_hash
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, 'enabled', ?, '', ?, ?, ?
            )
            """,
            (
                asset_id,
                workspace_id,
                skill_id,
                display_name,
                category,
                purpose,
                trigger_intents_json,
                required_inputs_json,
                optional_inputs_json,
                context_policy_json,
                output_schema_json,
                artifact_effect,
                side_effects_json,
                failure_mode,
                composable_with_json,
                implementation_refs_json,
                source,
                version,
                now,
                now,
                definition_hash,
            ),
        )
        return self.get(connection, asset_id)

    def list(self, connection: sqlite3.Connection, workspace_id: str) -> list[dict]:
        rows = connection.execute(
            """
            SELECT * FROM workspace_skills
            WHERE workspace_id = ?
            ORDER BY category, skill_id
            """,
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get(self, connection: sqlite3.Connection, skill_asset_id: str) -> dict:
        row = connection.execute(
            "SELECT * FROM workspace_skills WHERE id = ?", (skill_asset_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Skill not found")
        return dict(row)

    def get_by_skill_id(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        skill_id: str,
    ) -> dict | None:
        row = connection.execute(
            """
            SELECT * FROM workspace_skills
            WHERE workspace_id = ? AND skill_id = ?
            """,
            (workspace_id, skill_id),
        ).fetchone()
        return dict(row) if row is not None else None

    def update(
        self,
        connection: sqlite3.Connection,
        *,
        skill_asset_id: str,
        status: str | None,
        user_notes: str | None,
        expected_updated_at: str,
        now: str,
    ) -> dict:
        current = self.get(connection, skill_asset_id)
        if current["updated_at"] != expected_updated_at:
            raise ConflictError("Skill changed since it was loaded")
        cursor = connection.execute(
            """
            UPDATE workspace_skills
            SET status = ?, user_notes = ?, updated_at = ?
            WHERE id = ? AND updated_at = ?
            """,
            (
                current["status"] if status is None else status,
                current["user_notes"] if user_notes is None else user_notes,
                now,
                skill_asset_id,
                expected_updated_at,
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Skill changed since it was loaded")
        return self.get(connection, skill_asset_id)

    def update_builtin_definition(
        self,
        connection: sqlite3.Connection,
        *,
        skill_asset_id: str,
        display_name: str,
        category: str,
        purpose: str,
        trigger_intents_json: str,
        required_inputs_json: str,
        optional_inputs_json: str,
        context_policy_json: str,
        output_schema_json: str,
        artifact_effect: str,
        side_effects_json: str,
        failure_mode: str,
        composable_with_json: str,
        implementation_refs_json: str,
        version: str,
        definition_hash: str,
        now: str,
    ) -> dict:
        current = self.get(connection, skill_asset_id)
        if current["source"] != "builtin":
            return current
        connection.execute(
            """
            UPDATE workspace_skills
            SET display_name = ?, category = ?, purpose = ?,
                trigger_intents_json = ?, required_inputs_json = ?,
                optional_inputs_json = ?, context_policy_json = ?,
                output_schema_json = ?, artifact_effect = ?,
                side_effects_json = ?, failure_mode = ?,
                composable_with_json = ?, implementation_refs_json = ?,
                version = ?, definition_hash = ?, updated_at = ?
            WHERE id = ? AND source = 'builtin'
            """,
            (
                display_name,
                category,
                purpose,
                trigger_intents_json,
                required_inputs_json,
                optional_inputs_json,
                context_policy_json,
                output_schema_json,
                artifact_effect,
                side_effects_json,
                failure_mode,
                composable_with_json,
                implementation_refs_json,
                version,
                definition_hash,
                now,
                skill_asset_id,
            ),
        )
        return self.get(connection, skill_asset_id)
