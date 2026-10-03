"""SQLite operations for saved-reader recommendations; caller owns the transaction."""
import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError


class ReaderSelectionRepository:
    def find_request(
        self, c: sqlite3.Connection, workspace_id: str, request_key: str,
    ) -> dict | None:
        row = c.execute(
            "SELECT * FROM reader_selections WHERE workspace_id=? AND request_key=?",
            (workspace_id, request_key),
        ).fetchone()
        return dict(row) if row is not None else None

    def get(self, c: sqlite3.Connection, workspace_id: str, selection_id: str) -> dict:
        row = c.execute(
            "SELECT * FROM reader_selections WHERE id=? AND workspace_id=?",
            (selection_id, workspace_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("读者推荐不存在")
        return dict(row)

    def create(
        self, c: sqlite3.Connection, *, workspace_id: str, request_key: str,
        input_hash: str, snapshot_json: str, now: str, request_json: str | None = None,
    ) -> dict:
        existing = c.execute(
            "SELECT * FROM reader_selections WHERE workspace_id=? AND request_key=?",
            (workspace_id, request_key),
        ).fetchone()
        if existing is not None:
            if (existing["input_hash"] != input_hash
                    or existing["request_json"] != request_json):
                raise ConflictError("这次推荐请求已使用不同输入，请发起新的推荐")
            return dict(existing)
        selection_id = str(uuid4())
        c.execute(
            "INSERT INTO reader_selections "
            "(id, workspace_id, request_key, input_hash, input_snapshot_json, status, created_at, "
            "request_json) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
            (selection_id, workspace_id, request_key, input_hash, snapshot_json, now, request_json),
        )
        return self.get(c, workspace_id, selection_id)

    def pending(self, c: sqlite3.Connection) -> list[dict]:
        return [dict(row) for row in c.execute(
            "SELECT * FROM reader_selections WHERE status='pending' ORDER BY created_at, id"
        )]

    def claim(
        self, c: sqlite3.Connection, workspace_id: str, selection_id: str, now: str,
    ) -> dict | None:
        self.get(c, workspace_id, selection_id)
        changed = c.execute(
            "UPDATE reader_selections SET status='running', claim_token=?, started_at=? "
            "WHERE id=? AND workspace_id=? AND status='pending'",
            (str(uuid4()), now, selection_id, workspace_id),
        ).rowcount
        return self.get(c, workspace_id, selection_id) if changed else None

    def finish(
        self, c: sqlite3.Connection, *, workspace_id: str, selection_id: str,
        claim_token: str, status: str, result_json: str | None, error_code: str | None,
        metadata_json: str, now: str,
    ) -> dict:
        if status not in {"completed", "partially_completed", "failed"}:
            raise ValueError("Expected a terminal reader selection status")
        self.get(c, workspace_id, selection_id)
        changed = c.execute(
            "UPDATE reader_selections SET status=?, result_json=?, error_code=?, "
            "model_metadata_json=?, completed_at=?, claim_token=NULL "
            "WHERE id=? AND workspace_id=? AND status='running' AND claim_token=?",
            (status, result_json, error_code, metadata_json, now,
             selection_id, workspace_id, claim_token),
        ).rowcount
        if not changed:
            raise ConflictError("推荐任务未由当前执行者领取，或已经结束")
        return self.get(c, workspace_id, selection_id)

    def interrupt_running(self, c: sqlite3.Connection, now: str) -> int:
        # Explicit startup recovery only, after the previous worker is known to have stopped.
        return c.execute(
            "UPDATE reader_selections SET status='failed', error_code='interrupted', "
            "completed_at=?, claim_token=NULL WHERE status='running'", (now,),
        ).rowcount
