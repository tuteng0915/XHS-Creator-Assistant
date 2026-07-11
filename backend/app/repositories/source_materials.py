import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError, ValidationError


class SourceMaterialRepository:
    def create_text(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        material_type: str,
        name: str,
        content: str,
        now: str,
    ) -> dict:
        material_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO source_materials(
                id, workspace_id, type, name, text_content, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (material_id, workspace_id, material_type, name, content, now, now),
        )
        return self.get(connection, material_id)

    def create_csv(
        self,
        connection: sqlite3.Connection,
        *,
        material_id: str,
        workspace_id: str,
        name: str,
        keyword: str,
        original_filename: str,
        stored_key: str,
        media_type: str,
        byte_size: int,
        sha256: str,
        row_count: int,
        preview_json: str,
        now: str,
    ) -> dict:
        connection.execute(
            """
            INSERT INTO source_materials(
                id, workspace_id, type, name, keyword, original_filename,
                stored_key, media_type, byte_size, sha256, row_count,
                preview_json, created_at, updated_at
            ) VALUES (?, ?, 'trend_csv', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                material_id,
                workspace_id,
                name,
                keyword,
                original_filename,
                stored_key,
                media_type,
                byte_size,
                sha256,
                row_count,
                preview_json,
                now,
                now,
            ),
        )
        return self.get(connection, material_id)

    def list(
        self,
        connection: sqlite3.Connection,
        workspace_id: str,
        material_type: str | None = None,
    ) -> list[dict]:
        if material_type is None:
            rows = connection.execute(
                """
                SELECT * FROM source_materials
                WHERE workspace_id = ?
                ORDER BY updated_at DESC, id
                """,
                (workspace_id,),
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT * FROM source_materials
                WHERE workspace_id = ? AND type = ?
                ORDER BY updated_at DESC, id
                """,
                (workspace_id, material_type),
            ).fetchall()
        return [dict(row) for row in rows]

    def get(self, connection: sqlite3.Connection, material_id: str) -> dict:
        row = connection.execute(
            "SELECT * FROM source_materials WHERE id = ?", (material_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Source material not found")
        return dict(row)

    def update(
        self,
        connection: sqlite3.Connection,
        *,
        material_id: str,
        name: str | None,
        content: str | None,
        keyword: str | None,
        expected_updated_at: str,
        now: str,
    ) -> dict:
        current = self.get(connection, material_id)
        if current["updated_at"] != expected_updated_at:
            raise ConflictError("Source material changed since it was loaded")
        if current["type"] == "trend_csv" and content is not None:
            raise ValidationError("CSV file content cannot be replaced by a text update")
        if current["type"] != "trend_csv" and keyword is not None:
            raise ValidationError("Keyword is only editable for trend CSV materials")

        cursor = connection.execute(
            """
            UPDATE source_materials
            SET name = ?, text_content = ?, keyword = ?, updated_at = ?
            WHERE id = ? AND updated_at = ?
            """,
            (
                current["name"] if name is None else name,
                current["text_content"] if content is None else content,
                current["keyword"] if keyword is None else keyword,
                now,
                material_id,
                expected_updated_at,
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("Source material changed since it was loaded")
        return self.get(connection, material_id)

