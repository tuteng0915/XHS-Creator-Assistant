"""Durable product records for the bounded content-collaboration flow.

The repository deliberately knows nothing about LangGraph, providers, or HTTP.
It stores only workspace-scoped sessions, immutable addressed messages, and
claimable execution runs.  Callers must own a SQLite transaction.
"""

from __future__ import annotations

import json
import sqlite3
from uuid import uuid4

from app.errors import ConflictError, NotFoundError, ValidationError

SESSION_STATUSES = {"active", "archived"}
SESSION_EXECUTION_STATUSES = {
    "idle",
    "queued",
    "running",
    "waiting_creator",
    "completed",
    "failed",
}
MESSAGE_ROLES = {"creator", "research", "writing", "review", "system"}
RECIPIENT_ROLES = {"creator", "research", "writing", "review"}
RUN_STATUSES = {"queued", "running", "waiting_creator", "completed", "failed"}
RUN_FINISH_STATUSES = {"waiting_creator", "completed", "failed"}


def _nonblank(value: str | None, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValidationError(f"{field} 不能为空")
    return value


def _json_object(value: str, field: str) -> str:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{field} 必须是 JSON 对象") from error
    if not isinstance(decoded, dict):
        raise ValidationError(f"{field} 必须是 JSON 对象")
    return value


def _json_array(value: str, field: str) -> str:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{field} 必须是 JSON 数组") from error
    if not isinstance(decoded, list):
        raise ValidationError(f"{field} 必须是 JSON 数组")
    return value


class ContentCollaborationRepository:
    """Workspace-scoped persistence with append-only collaboration messages."""

    def create_session(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        title: str,
        context_target_type: str,
        context_target_id: str,
        initial_context_snapshot_json: str,
        create_request_key: str | None = None,
        create_request_fingerprint: str | None = None,
        now: str,
    ) -> dict:
        _nonblank(workspace_id, "账号")
        _nonblank(title, "协作标题")
        if context_target_type != "topic":
            raise ValidationError("协作上下文目前只支持 Topic")
        _nonblank(context_target_id, "上下文目标")
        _json_object(initial_context_snapshot_json, "初始上下文快照")
        self._validate_idempotency_pair(
            create_request_key, create_request_fingerprint, "创建请求"
        )
        self._require_workspace(connection, workspace_id)
        self._require_topic_target(connection, workspace_id, context_target_id)

        if create_request_key is not None:
            existing = connection.execute(
                """
                SELECT * FROM content_collaboration_sessions
                WHERE workspace_id = ? AND create_request_key = ?
                """,
                (workspace_id, create_request_key),
            ).fetchone()
            if existing is not None:
                row = dict(existing)
                if row["create_request_fingerprint"] != create_request_fingerprint:
                    raise ConflictError("此创建请求标识已用于另一份协作会话")
                return row

        session_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO content_collaboration_sessions(
                id, workspace_id, title, context_target_type, context_target_id,
                initial_context_snapshot_json, status, execution_status, revision,
                create_request_key, create_request_fingerprint,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, 'active', 'idle', 1, ?, ?, ?, ?)
            """,
            (
                session_id,
                workspace_id,
                title,
                context_target_type,
                context_target_id,
                initial_context_snapshot_json,
                create_request_key,
                create_request_fingerprint,
                now,
                now,
            ),
        )
        return self.get_session(connection, workspace_id=workspace_id, session_id=session_id)

    def get_session(
        self, connection: sqlite3.Connection, *, workspace_id: str, session_id: str
    ) -> dict:
        row = connection.execute(
            """
            SELECT * FROM content_collaboration_sessions
            WHERE id = ? AND workspace_id = ?
            """,
            (session_id, workspace_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("协作会话不存在")
        return dict(row)

    def list_sessions(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        include_archived: bool = False,
    ) -> list[dict]:
        clause = "" if include_archived else "AND status != 'archived'"
        rows = connection.execute(
            f"""
            SELECT * FROM content_collaboration_sessions
            WHERE workspace_id = ? {clause}
            ORDER BY updated_at DESC, id DESC
            """,
            (workspace_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def update_session(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        session_id: str,
        expected_revision: int,
        title: str | None = None,
        status: str | None = None,
        now: str,
    ) -> dict:
        if title is None and status is None:
            raise ValidationError("至少需要修改一个协作会话字段")
        if expected_revision < 1:
            raise ValidationError("协作会话版本无效")
        if title is not None:
            _nonblank(title, "协作标题")
        if status is not None and status not in SESSION_STATUSES:
            raise ValidationError("协作会话状态不受支持")
        current = self.get_session(
            connection, workspace_id=workspace_id, session_id=session_id
        )
        if current["revision"] != expected_revision:
            raise ConflictError("协作会话已被其他操作更新")
        cursor = connection.execute(
            """
            UPDATE content_collaboration_sessions
            SET title = ?, status = ?, revision = revision + 1, updated_at = ?
            WHERE id = ? AND workspace_id = ? AND revision = ?
            """,
            (
                current["title"] if title is None else title,
                current["status"] if status is None else status,
                now,
                session_id,
                workspace_id,
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("协作会话已被其他操作更新")
        return self.get_session(connection, workspace_id=workspace_id, session_id=session_id)

    def append_message(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        session_id: str,
        sender_role: str,
        recipient_role: str | None,
        content: str,
        artifact_refs_json: str,
        context_snapshot_json: str,
        model_metadata_json: str,
        reply_to_message_id: str | None = None,
        client_request_key: str | None = None,
        client_request_fingerprint: str | None = None,
        now: str,
    ) -> dict:
        session = self.get_session(
            connection, workspace_id=workspace_id, session_id=session_id
        )
        if sender_role not in MESSAGE_ROLES:
            raise ValidationError("协作消息发送者不受支持")
        if recipient_role is not None and recipient_role not in RECIPIENT_ROLES:
            raise ValidationError("协作消息收件人不受支持")
        _nonblank(content, "协作消息")
        _json_array(artifact_refs_json, "素材引用")
        _json_object(context_snapshot_json, "消息上下文快照")
        _json_object(model_metadata_json, "模型元数据")
        self._validate_idempotency_pair(
            client_request_key, client_request_fingerprint, "消息请求"
        )
        if client_request_key is not None and sender_role != "creator":
            raise ValidationError("只有创作者消息可以携带请求标识")

        if client_request_key is not None:
            existing = connection.execute(
                """
                SELECT * FROM content_collaboration_messages
                WHERE session_id = ? AND client_request_key = ?
                """,
                (session_id, client_request_key),
            ).fetchone()
            if existing is not None:
                row = dict(existing)
                if row["client_request_fingerprint"] != client_request_fingerprint:
                    raise ConflictError("此消息请求标识已用于另一条消息")
                return row

        if session["status"] != "active":
            raise ConflictError("已归档的协作会话不能继续发送消息")

        if reply_to_message_id is not None:
            reply = connection.execute(
                """
                SELECT id FROM content_collaboration_messages
                WHERE id = ? AND session_id = ?
                """,
                (reply_to_message_id, session_id),
            ).fetchone()
            if reply is None:
                raise ValidationError("回复目标不属于当前协作会话")

        sequence_no = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(sequence_no), 0) + 1
                FROM content_collaboration_messages WHERE session_id = ?
                """,
                (session_id,),
            ).fetchone()[0]
        )
        message_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO content_collaboration_messages(
                id, session_id, sequence_no, sender_role, recipient_role, content,
                reply_to_message_id, artifact_refs_json, context_snapshot_json,
                model_metadata_json, client_request_key, client_request_fingerprint,
                created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message_id,
                session_id,
                sequence_no,
                sender_role,
                recipient_role,
                content,
                reply_to_message_id,
                artifact_refs_json,
                context_snapshot_json,
                model_metadata_json,
                client_request_key,
                client_request_fingerprint,
                now,
            ),
        )
        self._touch_session(
            connection, workspace_id=workspace_id, session_id=session_id, now=now
        )
        return self.get_message(
            connection,
            workspace_id=workspace_id,
            session_id=session_id,
            message_id=message_id,
        )

    def get_message(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        session_id: str,
        message_id: str,
    ) -> dict:
        self.get_session(connection, workspace_id=workspace_id, session_id=session_id)
        row = connection.execute(
            """
            SELECT * FROM content_collaboration_messages
            WHERE id = ? AND session_id = ?
            """,
            (message_id, session_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("协作消息不存在")
        return dict(row)

    def list_messages(
        self, connection: sqlite3.Connection, *, workspace_id: str, session_id: str
    ) -> list[dict]:
        self.get_session(connection, workspace_id=workspace_id, session_id=session_id)
        rows = connection.execute(
            """
            SELECT * FROM content_collaboration_messages
            WHERE session_id = ?
            ORDER BY sequence_no ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def create_run(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        session_id: str,
        request_key: str,
        request_fingerprint: str,
        input_snapshot_json: str,
        trigger_message_id: str | None = None,
        graph_state_json: str = "{}",
        now: str,
    ) -> dict:
        session = self.get_session(
            connection, workspace_id=workspace_id, session_id=session_id
        )
        _nonblank(request_key, "执行请求标识")
        _nonblank(request_fingerprint, "执行请求指纹")
        _json_object(input_snapshot_json, "执行输入快照")
        _json_object(graph_state_json, "图执行状态")
        existing = connection.execute(
            """
            SELECT * FROM content_collaboration_runs
            WHERE session_id = ? AND request_key = ?
            """,
            (session_id, request_key),
        ).fetchone()
        if existing is not None:
            row = dict(existing)
            if row["request_fingerprint"] != request_fingerprint:
                raise ConflictError("此执行请求标识已用于不同输入")
            return row

        if session["status"] != "active":
            raise ConflictError("已归档的协作会话不能执行")

        if trigger_message_id is not None:
            trigger = connection.execute(
                """
                SELECT id, sender_role FROM content_collaboration_messages
                WHERE id = ? AND session_id = ?
                """,
                (trigger_message_id, session_id),
            ).fetchone()
            if trigger is None or trigger["sender_role"] != "creator":
                raise ValidationError("协作执行必须由当前会话中的创作者消息触发")
            trigger_run = connection.execute(
                """
                SELECT id FROM content_collaboration_runs
                WHERE trigger_message_id = ?
                """,
                (trigger_message_id,),
            ).fetchone()
            if trigger_run is not None:
                raise ConflictError("这条创作者消息已经创建过协作执行")

        active = connection.execute(
            """
            SELECT id FROM content_collaboration_runs
            WHERE session_id = ? AND status IN ('queued', 'running')
            LIMIT 1
            """,
            (session_id,),
        ).fetchone()
        if active is not None:
            raise ConflictError("当前协作会话已有执行中的请求")

        run_id = str(uuid4())
        connection.execute(
            """
            INSERT INTO content_collaboration_runs(
                id, session_id, trigger_message_id, request_key, request_fingerprint,
                input_snapshot_json, graph_state_json, status, revision,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'queued', 1, ?, ?)
            """,
            (
                run_id,
                session_id,
                trigger_message_id,
                request_key,
                request_fingerprint,
                input_snapshot_json,
                graph_state_json,
                now,
                now,
            ),
        )
        self._set_session_execution(
            connection,
            workspace_id=workspace_id,
            session_id=session_id,
            execution_status="queued",
            failure_code="",
            failure_detail="",
            now=now,
        )
        return self.get_run(
            connection, workspace_id=workspace_id, session_id=session_id, run_id=run_id
        )

    def get_run(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        session_id: str,
        run_id: str,
    ) -> dict:
        self.get_session(connection, workspace_id=workspace_id, session_id=session_id)
        row = connection.execute(
            """
            SELECT * FROM content_collaboration_runs
            WHERE id = ? AND session_id = ?
            """,
            (run_id, session_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("协作执行记录不存在")
        return dict(row)

    def list_runs(
        self, connection: sqlite3.Connection, *, workspace_id: str, session_id: str
    ) -> list[dict]:
        self.get_session(connection, workspace_id=workspace_id, session_id=session_id)
        rows = connection.execute(
            """
            SELECT * FROM content_collaboration_runs
            WHERE session_id = ?
            ORDER BY created_at ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def list_queued_runs(self, connection: sqlite3.Connection) -> list[dict]:
        """Worker discovery only; never expose this cross-workspace listing publicly."""
        rows = connection.execute(
            """
            SELECT run.*, session.workspace_id AS workspace_id
            FROM content_collaboration_runs AS run
            JOIN content_collaboration_sessions AS session ON session.id = run.session_id
            WHERE run.status = 'queued' AND session.status = 'active'
            ORDER BY run.created_at ASC, run.id ASC
            """
        ).fetchall()
        return [dict(row) for row in rows]

    def claim_run(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        session_id: str,
        run_id: str,
        now: str,
    ) -> dict | None:
        session = self.get_session(
            connection, workspace_id=workspace_id, session_id=session_id
        )
        if session["status"] != "active":
            return None
        current = self.get_run(
            connection, workspace_id=workspace_id, session_id=session_id, run_id=run_id
        )
        if current["status"] != "queued":
            return None
        claim_token = str(uuid4())
        cursor = connection.execute(
            """
            UPDATE content_collaboration_runs
            SET status = 'running', claim_token = ?, attempt_count = attempt_count + 1,
                started_at = COALESCE(started_at, ?), updated_at = ?, revision = revision + 1
            WHERE id = ? AND session_id = ? AND status = 'queued' AND revision = ?
            """,
            (claim_token, now, now, run_id, session_id, current["revision"]),
        )
        if cursor.rowcount != 1:
            return None
        self._set_session_execution(
            connection,
            workspace_id=workspace_id,
            session_id=session_id,
            execution_status="running",
            failure_code="",
            failure_detail="",
            now=now,
        )
        return self.get_run(
            connection, workspace_id=workspace_id, session_id=session_id, run_id=run_id
        )

    def save_run_state(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        session_id: str,
        run_id: str,
        claim_token: str,
        expected_revision: int,
        graph_state_json: str,
        now: str,
    ) -> dict:
        _json_object(graph_state_json, "图执行状态")
        current = self.get_run(
            connection, workspace_id=workspace_id, session_id=session_id, run_id=run_id
        )
        if current["status"] != "running" or current["claim_token"] != claim_token:
            raise ConflictError("协作执行未由当前工作者领取，或已经结束")
        if current["revision"] != expected_revision:
            raise ConflictError("协作执行状态已更新")
        cursor = connection.execute(
            """
            UPDATE content_collaboration_runs
            SET graph_state_json = ?, updated_at = ?, revision = revision + 1
            WHERE id = ? AND session_id = ? AND status = 'running'
              AND claim_token = ? AND revision = ?
            """,
            (
                graph_state_json,
                now,
                run_id,
                session_id,
                claim_token,
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("协作执行状态已更新")
        return self.get_run(
            connection, workspace_id=workspace_id, session_id=session_id, run_id=run_id
        )

    def finish_run(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        session_id: str,
        run_id: str,
        claim_token: str,
        expected_revision: int,
        status: str,
        graph_state_json: str,
        error_code: str = "",
        error_detail: str = "",
        now: str,
    ) -> dict:
        if status not in RUN_FINISH_STATUSES:
            raise ValidationError("协作执行只能结束为等待创作者、完成或失败")
        _json_object(graph_state_json, "图执行状态")
        current = self.get_run(
            connection, workspace_id=workspace_id, session_id=session_id, run_id=run_id
        )
        if current["status"] != "running" or current["claim_token"] != claim_token:
            raise ConflictError("协作执行未由当前工作者领取，或已经结束")
        if current["revision"] != expected_revision:
            raise ConflictError("协作执行状态已更新")
        cursor = connection.execute(
            """
            UPDATE content_collaboration_runs
            SET graph_state_json = ?, status = ?, claim_token = NULL,
                error_code = ?, error_detail = ?, completed_at = ?,
                updated_at = ?, revision = revision + 1
            WHERE id = ? AND session_id = ? AND status = 'running'
              AND claim_token = ? AND revision = ?
            """,
            (
                graph_state_json,
                status,
                error_code if status == "failed" else "",
                error_detail if status == "failed" else "",
                now if status in {"completed", "failed"} else None,
                now,
                run_id,
                session_id,
                claim_token,
                expected_revision,
            ),
        )
        if cursor.rowcount != 1:
            raise ConflictError("协作执行状态已更新")
        self._set_session_execution(
            connection,
            workspace_id=workspace_id,
            session_id=session_id,
            execution_status=status,
            failure_code=error_code if status == "failed" else "",
            failure_detail=error_detail if status == "failed" else "",
            now=now,
        )
        return self.get_run(
            connection, workspace_id=workspace_id, session_id=session_id, run_id=run_id
        )

    def interrupt_running_runs(self, connection: sqlite3.Connection, *, now: str) -> int:
        """Explicit startup recovery after the prior in-process worker has stopped."""
        rows = connection.execute(
            """
            SELECT run.id, run.session_id, session.workspace_id
            FROM content_collaboration_runs AS run
            JOIN content_collaboration_sessions AS session ON session.id = run.session_id
            WHERE run.status = 'running'
            """
        ).fetchall()
        for row in rows:
            connection.execute(
                """
                UPDATE content_collaboration_runs
                SET status = 'failed', claim_token = NULL, error_code = 'interrupted',
                    error_detail = 'Worker stopped before this collaboration turn completed.',
                    completed_at = ?, updated_at = ?, revision = revision + 1
                WHERE id = ? AND status = 'running'
                """,
                (now, now, row["id"]),
            )
            self._set_session_execution(
                connection,
                workspace_id=row["workspace_id"],
                session_id=row["session_id"],
                execution_status="failed",
                failure_code="interrupted",
                failure_detail="Worker stopped before this collaboration turn completed.",
                now=now,
            )
        return len(rows)

    @staticmethod
    def _validate_idempotency_pair(
        key: str | None, fingerprint: str | None, field: str
    ) -> None:
        if (key is None) != (fingerprint is None):
            raise ValidationError(f"{field}标识和指纹必须同时提供")
        if key is not None:
            _nonblank(key, f"{field}标识")
            _nonblank(fingerprint, f"{field}指纹")

    def _touch_session(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        session_id: str,
        now: str,
    ) -> None:
        cursor = connection.execute(
            """
            UPDATE content_collaboration_sessions
            SET last_message_at = ?, updated_at = ?, revision = revision + 1
            WHERE id = ? AND workspace_id = ?
            """,
            (now, now, session_id, workspace_id),
        )
        if cursor.rowcount != 1:
            raise NotFoundError("协作会话不存在")

    def _set_session_execution(
        self,
        connection: sqlite3.Connection,
        *,
        workspace_id: str,
        session_id: str,
        execution_status: str,
        failure_code: str,
        failure_detail: str,
        now: str,
    ) -> None:
        if execution_status not in SESSION_EXECUTION_STATUSES:
            raise ValidationError("协作执行状态不受支持")
        cursor = connection.execute(
            """
            UPDATE content_collaboration_sessions
            SET execution_status = ?, failure_code = ?, failure_detail = ?,
                completed_at = CASE WHEN ? = 'completed' THEN ? ELSE NULL END,
                updated_at = ?, revision = revision + 1
            WHERE id = ? AND workspace_id = ?
            """,
            (
                execution_status,
                failure_code,
                failure_detail,
                execution_status,
                now,
                now,
                session_id,
                workspace_id,
            ),
        )
        if cursor.rowcount != 1:
            raise NotFoundError("协作会话不存在")

    @staticmethod
    def _require_workspace(connection: sqlite3.Connection, workspace_id: str) -> None:
        row = connection.execute(
            "SELECT id FROM creator_workspaces WHERE id = ?", (workspace_id,)
        ).fetchone()
        if row is None:
            raise NotFoundError("Workspace not found")

    @staticmethod
    def _require_topic_target(
        connection: sqlite3.Connection, workspace_id: str, topic_id: str
    ) -> None:
        row = connection.execute(
            "SELECT id FROM topics WHERE id = ? AND workspace_id = ?",
            (topic_id, workspace_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("协作上下文 Topic 不存在")
