import json
import sqlite3
from uuid import uuid4

from app.errors import NotFoundError


class XhsCaptureJobRepository:
    def create(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        profile_url: str,
        note_limit: int,
        include_comments: bool,
        now: str,
    ) -> dict:
        job_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO xhs_capture_jobs(
                id, workspace_id, profile_url, status, note_limit,
                include_comments, status_message, created_at, updated_at
            ) VALUES (?, ?, ?, 'pending', ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                workspace_id,
                profile_url,
                note_limit,
                int(include_comments),
                "正在准备导入任务",
                now,
                now,
            ),
        )
        return self.get(connection, job_id)

    def get(self, connection: sqlite3.Connection, job_id: str) -> dict:
        row = connection.execute(
            "SELECT * FROM xhs_capture_jobs WHERE id = ?", (job_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("XHS capture job not found")
        return self._as_dict(row)

    def list_for_workspace(
        self, connection: sqlite3.Connection, workspace_id: str
    ) -> list[dict]:
        rows = connection.execute(
            """
            SELECT * FROM xhs_capture_jobs
            WHERE workspace_id = ?
            ORDER BY created_at DESC
            """,
            (workspace_id,),
        ).fetchall()
        return [self._as_dict(row) for row in rows]

    def find_active(
        self, connection: sqlite3.Connection, workspace_id: str
    ) -> dict | None:
        row = connection.execute(
            """
            SELECT * FROM xhs_capture_jobs
            WHERE workspace_id = ?
              AND status IN ('pending', 'waiting_for_login', 'running', 'processing')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workspace_id,),
        ).fetchone()
        return self._as_dict(row) if row is not None else None

    def transition(
        self,
        connection: sqlite3.Connection,
        *,
        job_id: str,
        status: str,
        status_message: str,
        now: str,
        resolved_url: str | None = None,
        error: str | None = None,
        result_input_asset_id: str | None = None,
        progress: dict | None = None,
        started: bool = False,
        completed: bool = False,
    ) -> dict:
        current = self.get(connection, job_id)
        connection.execute(
            """
            UPDATE xhs_capture_jobs
            SET status = ?,
                status_message = ?,
                resolved_url = ?,
                error = ?,
                result_input_asset_id = ?,
                progress_json = ?,
                started_at = ?,
                completed_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                status,
                status_message,
                current["resolved_url"] if resolved_url is None else resolved_url,
                current["error"] if error is None else error,
                (
                    current["result_input_asset_id"]
                    if result_input_asset_id is None
                    else result_input_asset_id
                ),
                current["progress_json"] if progress is None else json.dumps(progress),
                current["started_at"] or (now if started else None),
                now if completed else current["completed_at"],
                now,
                job_id,
            ),
        )
        return self.get(connection, job_id)

    def fail_interrupted(self, connection: sqlite3.Connection, *, now: str) -> int:
        cursor = connection.execute(
            """
            UPDATE xhs_capture_jobs
            SET status = 'failed',
                status_message = '后端重启中断了导入，请重新提交',
                error = 'capture_interrupted_by_backend_restart',
                completed_at = ?,
                updated_at = ?
            WHERE status IN ('pending', 'waiting_for_login', 'running', 'processing')
            """,
            (now, now),
        )
        return cursor.rowcount

    @staticmethod
    def _as_dict(row: sqlite3.Row) -> dict:
        result = dict(row)
        result["include_comments"] = bool(result["include_comments"])
        result["progress"] = json.loads(result["progress_json"])
        return result
