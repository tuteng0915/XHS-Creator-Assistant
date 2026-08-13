from __future__ import annotations

import sqlite3

from app.errors import ConflictError, NotFoundError


class MediaAssetRepository:
    def create(
        self,
        connection: sqlite3.Connection,
        *,
        asset_id: str,
        workspace_id: str,
        asset_type: str,
        name: str,
        purpose: str,
        source_type: str,
        original_filename: str,
        stored_key: str,
        media_type: str,
        byte_size: int,
        sha256: str,
        metadata_json: str,
        derived_json: str,
        user_notes: str,
        now: str,
        external_url: str = "",
    ) -> dict:
        connection.execute(
            """
            INSERT INTO media_assets(
                id, workspace_id, type, name, purpose, source_type,
                original_filename, stored_key, media_type, byte_size, sha256,
                metadata_json, derived_json, user_notes, external_url,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                asset_id,
                workspace_id,
                asset_type,
                name,
                purpose,
                source_type,
                original_filename,
                stored_key,
                media_type,
                byte_size,
                sha256,
                metadata_json,
                derived_json,
                user_notes,
                external_url,
                now,
                now,
            ),
        )
        return self.get(connection, asset_id)

    def list(
        self,
        connection: sqlite3.Connection,
        workspace_id: str,
        asset_type: str | None = None,
    ) -> list[dict]:
        if asset_type is None:
            rows = connection.execute(
                """
                SELECT * FROM media_assets
                WHERE workspace_id = ?
                ORDER BY updated_at DESC, id
                """,
                (workspace_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM media_assets
                WHERE workspace_id = ? AND type = ?
                ORDER BY updated_at DESC, id
                """,
                (workspace_id, asset_type),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, connection: sqlite3.Connection, asset_id: str) -> dict:
        row = connection.execute(
            "SELECT * FROM media_assets WHERE id = ?", (asset_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Media asset not found")
        return dict(row)

    def update(
        self,
        connection: sqlite3.Connection,
        *,
        asset_id: str,
        name: str | None,
        purpose: str | None,
        metadata_json: str | None,
        derived_json: str | None,
        user_notes: str | None,
        expected_updated_at: str,
        now: str,
    ) -> dict:
        current = self.get(connection, asset_id)
        if current["updated_at"] != expected_updated_at:
            raise ConflictError("Media asset changed since it was loaded")
        cursor = connection.execute(
            """
            UPDATE media_assets
            SET name = ?, purpose = ?, metadata_json = ?, derived_json = ?,
                user_notes = ?, updated_at = ?
            WHERE id = ? AND updated_at = ?
            """,
            (
                current["name"] if name is None else name,
                current["purpose"] if purpose is None else purpose,
                current["metadata_json"] if metadata_json is None else metadata_json,
                current["derived_json"] if derived_json is None else derived_json,
                current["user_notes"] if user_notes is None else user_notes,
                now,
                asset_id,
                expected_updated_at,
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Media asset changed since it was loaded")
        return self.get(connection, asset_id)
