"""Durable service boundary for the bounded content-collaboration graph.

The LangGraph graph decides the next fixed specialist, but this service owns
the product contract: every creator/specialist message is appended before the
next turn starts, and the database remains the recovery source of truth.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Any

from app.db.database import SQLiteDatabase
from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import (
    ContentCollaborationMessageCreate,
    ContentCollaborationMessageResponse,
    ContentCollaborationRunResponse,
    ContentCollaborationSessionCreate,
    ContentCollaborationSessionResponse,
    ContentCollaborationSessionSummary,
    ContentCollaborationSessionUpdate,
)
from app.repositories.content_collaboration import ContentCollaborationRepository
from app.repositories.topics import TopicRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import utc_now
from app.services.content_collaboration import (
    CollaborationMessage,
    ContentCollaborationGraph,
    SpecialistProvider,
    SpecialistTurn,
)
from app.services.context_access import ContextAccessService
from app.services.creator_context import canonical_selection, resolve_creator_context
from app.services.writing_focus import resolve_writing_focus

DEFAULT_MAX_TURNS = 3
MAX_CONTEXT_TRANSCRIPT_MESSAGES = 12
_COLLABORATION_ROLES = {"creator", "research", "writing", "review"}


def _encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _decoded_object(value: str, *, field: str) -> dict[str, Any]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{field} 已损坏，无法继续协作") from error
    if not isinstance(decoded, dict):
        raise ValidationError(f"{field} 已损坏，无法继续协作")
    return decoded


def _decoded_array(value: str, *, field: str) -> list[Any]:
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError) as error:
        raise ValidationError(f"{field} 已损坏，无法继续协作") from error
    if not isinstance(decoded, list):
        raise ValidationError(f"{field} 已损坏，无法继续协作")
    return decoded


def _fingerprint(value: dict[str, Any]) -> str:
    return hashlib.sha256(_encoded(value).encode("utf-8")).hexdigest()


class DeterministicContentCollaborationProvider:
    """A deliberately local demo provider; it never calls a model API.

    Keeping the durable execution path usable without an API key lets the
    product exercise session/recovery semantics before a live specialist
    provider is introduced.  A live provider can implement the same
    ``SpecialistProvider`` protocol later without changing persistence.
    """

    async def run(
        self,
        *,
        role: str,
        message: CollaborationMessage,
        context: dict[str, Any],
    ) -> SpecialistTurn:
        topic = context.get("target", {})
        topic_title = topic.get("title") if isinstance(topic, dict) else None
        label = f"《{topic_title}》" if isinstance(topic_title, str) and topic_title else "当前选题"
        if context.get("assistantMode") == "single_writer":
            return SpecialistTurn(
                content=f"可以先围绕{label}确定一个具体场景，再把判断过程写清楚。你最想保留哪一句？",
                to="creator", model_metadata=self._metadata(),
            )
        if role == "research":
            return SpecialistTurn(
                content=(
                    f"研究侧已围绕{label}整理本轮需要先确认的事实与读者关切。"
                    "请写作侧把它们转成清晰、可读的表达结构。"
                ),
                to="writing",
                model_metadata=self._metadata(),
            )
        if role == "writing":
            return SpecialistTurn(
                content=(
                    "写作侧已把研究线索收束为一条可讲述的主线，并保留需要创作者补充的细节。"
                    "请评审侧检查这版是否足够具体、是否忠于原有表达。"
                ),
                to="review",
                model_metadata=self._metadata(),
            )
        return SpecialistTurn(
            content=(
                "评审侧建议：保留最有辨识度的经历细节，把结论放在具体场景之后。"
                "下一步请你确认最想强调的一个转折，或补充不能改动的表达。"
            ),
            to="creator",
            model_metadata=self._metadata(),
        )

    @staticmethod
    def _metadata() -> dict[str, Any]:
        return {
            "provider": "deterministic-content-collaboration",
            "model": "deterministic-content-collaboration",
            "operation": "content_collaboration_turn",
            "requestCount": 0,
        }


class ContentCollaborationSessionService:
    """Product persistence and recovery wrapper around ``ContentCollaborationGraph``."""

    def __init__(
        self,
        database: SQLiteDatabase,
        repository: ContentCollaborationRepository,
        workspace_repository: WorkspaceRepository,
        topic_repository: TopicRepository,
        context_access_service: ContextAccessService,
        provider: SpecialistProvider | None = None,
        *,
        live_provider: SpecialistProvider | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
    ) -> None:
        if max_turns < 1 or max_turns > 8:
            raise ValueError("max_turns must be between 1 and 8")
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.topic_repository = topic_repository
        self.context_access_service = context_access_service
        self.demo_provider = provider or DeterministicContentCollaborationProvider()
        self.live_provider = live_provider
        self.max_turns = max_turns
        self._tasks: dict[str, asyncio.Task[None]] = {}

    # ``provider`` was part of the first persistence slice and is kept as a
    # compatibility seam for deterministic tests and local demo injection.
    @property
    def provider(self) -> SpecialistProvider:
        return self.demo_provider

    @provider.setter
    def provider(self, value: SpecialistProvider) -> None:
        self.demo_provider = value

    def create(
        self,
        workspace_id: str,
        payload: ContentCollaborationSessionCreate,
    ) -> ContentCollaborationSessionResponse:
        title = payload.title.strip() if payload.title is not None else None
        target = payload.context_target
        target_data = target.model_dump(mode="json", by_alias=False)
        request_key = payload.request_key.strip() if payload.request_key else None
        create_fingerprint = (
            _fingerprint({"title": title, "contextTarget": target_data})
            if request_key is not None
            else None
        )
        if request_key is not None and payload.assistant_mode == "single_writer":
            create_fingerprint = _fingerprint({
                "title": title, "contextTarget": target_data, "assistantMode": "single_writer",
            })
        now = utc_now()
        with self.database.transaction() as connection:
            workspace = self.workspace_repository.get(connection, workspace_id)
            topic = self.topic_repository.get(connection, target.asset_id)
            if topic["workspace_id"] != workspace_id:
                raise NotFoundError("协作上下文 Topic 不存在")
            session_context = self._build_session_context(
                connection,
                workspace=workspace,
                topic=topic,
                assistant_mode=payload.assistant_mode,
            )
            row = self.repository.create_session(
                connection,
                workspace_id=workspace_id,
                title=title or self._default_title(topic),
                context_target_type=target.asset_type,
                context_target_id=target.asset_id,
                initial_context_snapshot_json=_encoded(session_context),
                create_request_key=request_key,
                create_request_fingerprint=create_fingerprint,
                now=now,
            )
        return self.get(workspace_id, row["id"])

    def list(self, workspace_id: str) -> list[ContentCollaborationSessionSummary]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list_sessions(connection, workspace_id=workspace_id)
            for row in rows:
                row["creator_context_state"] = self._current_creator_context(connection, row)
        return [self._to_summary(row) for row in rows]

    def get(
        self, workspace_id: str, session_id: str
    ) -> ContentCollaborationSessionResponse:
        with self.database.read() as connection:
            row = self.repository.get_session(
                connection, workspace_id=workspace_id, session_id=session_id
            )
            messages = self.repository.list_messages(
                connection, workspace_id=workspace_id, session_id=session_id
            )
            runs = self.repository.list_runs(
                connection, workspace_id=workspace_id, session_id=session_id
            )
            row["creator_context_state"] = self._current_creator_context(connection, row)
        return self._to_response(row, messages=messages, runs=runs)

    def update(
        self,
        workspace_id: str,
        session_id: str,
        payload: ContentCollaborationSessionUpdate,
    ) -> ContentCollaborationSessionResponse:
        title = payload.title.strip() if payload.title is not None else None
        status = payload.status.value if payload.status is not None else None
        with self.database.transaction() as connection:
            current = self.repository.get_session(
                connection, workspace_id=workspace_id, session_id=session_id
            )
            if (
                status == "archived"
                and current["execution_status"] in {"queued", "running"}
            ):
                raise ConflictError("协作仍在执行，不能归档")
            self.repository.update_session(
                connection,
                workspace_id=workspace_id,
                session_id=session_id,
                expected_revision=payload.expected_revision,
                title=title,
                status=status,
                now=utc_now(),
            )
        return self.get(workspace_id, session_id)

    async def send_message(
        self,
        workspace_id: str,
        session_id: str,
        payload: ContentCollaborationMessageCreate,
    ) -> ContentCollaborationSessionResponse:
        """Append an immutable creator message and schedule its durable run.

        The first response intentionally may still show ``queued`` or
        ``running``.  Clients read the session again to observe the durable
        specialist transcript; no in-memory task result is treated as truth.
        """
        content = payload.content.strip()
        if len(content) > 8_000:
            # The graph contract is deliberately bounded even though the generic
            # API field is shared with UI drafts that permit longer text.
            raise ValidationError("协作消息不能超过 8000 个字符")
        request_key = payload.request_key.strip()
        recipient = payload.recipient.value
        mode = payload.mode
        request_identity = {"content": content, "recipient": recipient, "mode": mode}
        selection = (canonical_selection(payload.creator_context_selection)
                     if payload.creator_context_selection is not None else None)
        if selection is not None:
            request_identity["creatorContextSelection"] = selection
        if payload.writing_focus is not None:
            request_identity["writingFocus"] = payload.writing_focus.model_dump(
                by_alias=True, mode="json", exclude_none=True
            )
        request_fingerprint = _fingerprint(request_identity)
        now = utc_now()
        with self.database.transaction() as connection:
            session = self.repository.get_session(
                connection, workspace_id=workspace_id, session_id=session_id
            )
            # A lost response must remain replayable after the author has
            # edited the draft. Validate identity before freshness or scope.
            existing = connection.execute(
                "SELECT request_fingerprint FROM content_collaboration_runs "
                "WHERE session_id=? AND request_key=?",
                (session_id, request_key),
            ).fetchone()
            if existing is not None:
                if existing["request_fingerprint"] != request_fingerprint:
                    raise ConflictError("此执行请求标识已用于另一条消息")
                return self.get(workspace_id, session_id)
            if session["status"] != "active":
                raise ConflictError("已归档的协作会话不能继续发送消息")
            assistant_mode = self._assistant_mode(session)
            context_revision = 0
            context_snapshot = None
            if assistant_mode == "single_writer":
                if recipient != "writing":
                    raise ValidationError("创作助手只接收写作请求")
                if selection is None:
                    raise ValidationError("请明确本轮参考材料；不使用参考时传入空列表")
                prior = self._current_creator_context(connection, session)
                context_revision = prior["contextRevision"]
                if not context_revision or prior["creatorContextSelection"] != selection:
                    context_revision += 1
                context_snapshot = resolve_creator_context(
                    connection, workspace_id=workspace_id, selection=selection,
                )
            elif selection is not None:
                raise ValidationError("请新建创作助手会话后使用参考材料")
            # Each creator turn starts from the latest saved draft. The
            # original session snapshot and prior run snapshots stay immutable;
            # all specialists within this run share this new frozen version.
            workspace = self.workspace_repository.get(connection, workspace_id)
            topic = self.topic_repository.get(connection, session["context_target_id"])
            if topic["workspace_id"] != workspace_id:
                raise NotFoundError("协作上下文 Topic 不存在")
            session_context = self._build_session_context(
                connection, workspace=workspace, topic=topic, assistant_mode=assistant_mode,
            )
            if assistant_mode == "single_writer":
                session_context.update({
                    "creatorContextSelection": selection,
                    "creatorContextSnapshot": context_snapshot,
                    "contextRevision": context_revision,
                })
            focus = None
            if payload.writing_focus is not None:
                focus = resolve_writing_focus(
                    connection, workspace_id=workspace_id, topic=topic,
                    payload=payload.writing_focus,
                )
                session_context["writingFocus"] = focus
            creator_context = {
                "schemaVersion": "content-collaboration-message/v1",
                "sessionContextRef": {
                    "sessionId": session_id,
                    "contentHash": _fingerprint(session_context),
                },
                "trigger": {
                    "sender": "creator",
                    "recipient": recipient,
                    "content": content,
                },
                "executionMode": mode,
            }
            if focus is not None:
                creator_context["writingFocus"] = focus
            creator_metadata = {"origin": "creator", "executionMode": mode}
            if assistant_mode == "single_writer":
                context_fields = {
                    "assistantMode": assistant_mode, "contextRevision": context_revision,
                    "creatorContextSelection": selection,
                }
                creator_context.update({
                    **context_fields, "creatorContextSnapshot": context_snapshot,
                })
                creator_metadata.update(context_fields)
            if focus is not None:
                creator_metadata["writingFocus"] = focus
            message = self.repository.append_message(
                connection,
                workspace_id=workspace_id,
                session_id=session_id,
                sender_role="creator",
                recipient_role=recipient,
                content=content,
                artifact_refs_json="[]",
                context_snapshot_json=_encoded(creator_context),
                model_metadata_json=_encoded(creator_metadata),
                client_request_key=request_key,
                client_request_fingerprint=request_fingerprint,
                now=now,
            )
            run_input = {
                "schemaVersion": "content-collaboration-run-input/v1",
                "sessionContext": session_context,
                "triggerMessage": self._message_for_graph(message),
                "maxTurns": 1 if assistant_mode == "single_writer" else self.max_turns,
                "mode": mode,
            }
            graph_state = {
                "schemaVersion": "content-collaboration-graph/v1",
                "pendingMessageId": message["id"],
                "remainingTurns": 1 if assistant_mode == "single_writer" else self.max_turns,
                "status": "queued",
            }
            run = self.repository.create_run(
                connection,
                workspace_id=workspace_id,
                session_id=session_id,
                request_key=request_key,
                request_fingerprint=request_fingerprint,
                input_snapshot_json=_encoded(run_input),
                trigger_message_id=message["id"],
                graph_state_json=_encoded(graph_state),
                now=now,
            )

        task = self._enqueue_run(
            workspace_id=workspace_id, session_id=session_id, run_id=run["id"]
        )
        # Give the event loop a chance to claim the run.  The caller still gets
        # a valid response if it remains queued, and can safely poll by session.
        await asyncio.wait({task}, timeout=0.001)
        return self.get(workspace_id, session_id)

    def resume_unfinished(self) -> None:
        """Recover queued work only; running model turns become explicit failures."""
        with self.database.transaction() as connection:
            self.repository.interrupt_running_runs(connection, now=utc_now())
        with self.database.read() as connection:
            queued = self.repository.list_queued_runs(connection)
        for run in queued:
            self._enqueue_run_from_sync(
                workspace_id=run["workspace_id"],
                session_id=run["session_id"],
                run_id=run["id"],
            )

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def _enqueue_run(
        self, *, workspace_id: str, session_id: str, run_id: str
    ) -> asyncio.Task[None]:
        existing = self._tasks.get(run_id)
        if existing is not None and not existing.done():
            return existing
        task = asyncio.create_task(
            self._execute_run(
                workspace_id=workspace_id,
                session_id=session_id,
                run_id=run_id,
            )
        )
        self._tasks[run_id] = task

        def remove_if_current(done: asyncio.Task[None]) -> None:
            if self._tasks.get(run_id) is done:
                self._tasks.pop(run_id, None)

        task.add_done_callback(remove_if_current)
        return task

    def _enqueue_run_from_sync(
        self, *, workspace_id: str, session_id: str, run_id: str
    ) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(
                self._execute_run(
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run_id=run_id,
                )
            )
            return
        self._enqueue_run(
            workspace_id=workspace_id, session_id=session_id, run_id=run_id
        )

    async def _execute_run(
        self, *, workspace_id: str, session_id: str, run_id: str
    ) -> None:
        claim: dict[str, Any] | None = None
        try:
            with self.database.transaction() as connection:
                claim = self.repository.claim_run(
                    connection,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run_id=run_id,
                    now=utc_now(),
                )
            if claim is None:
                return

            while True:
                with self.database.read() as connection:
                    self.repository.get_session(
                        connection, workspace_id=workspace_id, session_id=session_id
                    )
                    run = self.repository.get_run(
                        connection,
                        workspace_id=workspace_id,
                        session_id=session_id,
                        run_id=run_id,
                    )
                    messages = self.repository.list_messages(
                        connection, workspace_id=workspace_id, session_id=session_id
                    )
                if run["status"] != "running" or run["claim_token"] != claim["claim_token"]:
                    return
                graph_state = _decoded_object(run["graph_state_json"], field="协作图状态")
                pending_id = graph_state.get("pendingMessageId")
                if not isinstance(pending_id, str) or not pending_id:
                    await self._finish_failed(
                        workspace_id=workspace_id,
                        session_id=session_id,
                        run=run,
                        code="invalid_graph_state",
                    )
                    return
                pending_row = next((item for item in messages if item["id"] == pending_id), None)
                if pending_row is None:
                    await self._finish_failed(
                        workspace_id=workspace_id,
                        session_id=session_id,
                        run=run,
                        code="missing_pending_message",
                    )
                    return
                pending = CollaborationMessage.model_validate(
                    self._message_for_graph(pending_row)
                )
                input_snapshot = _decoded_object(run["input_snapshot_json"], field="协作执行输入")
                mode = input_snapshot.get("mode", "demo")
                if mode not in {"demo", "live"}:
                    await self._finish_failed(
                        workspace_id=workspace_id,
                        session_id=session_id,
                        run=run,
                        code="invalid_execution_mode",
                    )
                    return
                provider = self._provider_for_mode(mode)
                if provider is None:
                    await self._finish_failed(
                        workspace_id=workspace_id,
                        session_id=session_id,
                        run=run,
                        code="live_provider_unavailable",
                    )
                    return
                session_context = input_snapshot.get("sessionContext")
                if not isinstance(session_context, dict):
                    await self._finish_failed(
                        workspace_id=workspace_id,
                        session_id=session_id,
                        run=run,
                        code="missing_frozen_context",
                    )
                    return
                if session_context.get("assistantMode") == "single_writer":
                    current_revision = session_context.get("contextRevision")
                    messages = [item for item in messages if _decoded_object(
                        item["model_metadata_json"], field="消息上下文版本"
                    ).get("contextRevision") == current_revision]
                transcript = self._graph_transcript(messages)
                handoff_candidates = ({} if session_context.get("assistantMode") == "single_writer"
                                      else self._handoff_candidates(messages))
                remaining = graph_state.get("remainingTurns")
                if not isinstance(remaining, int):
                    await self._finish_failed(
                        workspace_id=workspace_id,
                        session_id=session_id,
                        run=run,
                        code="invalid_graph_state",
                    )
                    return

                used_contexts: dict[str, dict[str, Any]] = {}
                graph = self._graph_for_turn(
                    session_id=session_id,
                    run_id=run_id,
                    session_context=session_context,
                    used_contexts=used_contexts,
                    provider=provider,
                    mode=mode,
                    handoff_candidates=handoff_candidates,
                )
                state = await graph.advance_one(
                    thread_id=session_id,
                    pending_message=pending,
                    transcript=transcript,
                    remaining_turns=remaining,
                )
                outcome = await self._persist_turn_outcome(
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run=run,
                    pending=pending,
                    state=state,
                    session_context=session_context,
                    used_contexts=used_contexts,
                    mode=mode,
                )
                if outcome != "continue":
                    return
        except asyncio.CancelledError:
            # The claim intentionally stays running.  On the next startup it is
            # recorded as interrupted rather than silently replaying a turn.
            raise
        except Exception:
            if claim is not None:
                await self._finish_failed(
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run_id=run_id,
                    claim_token=claim["claim_token"],
                    code="execution_error",
                )

    async def _persist_turn_outcome(
        self,
        *,
        workspace_id: str,
        session_id: str,
        run: dict[str, Any],
        pending: CollaborationMessage,
        state: dict[str, Any],
        session_context: dict[str, Any],
        used_contexts: dict[str, dict[str, Any]],
        mode: str,
    ) -> str:
        state_status = state.get("status")
        output = self._new_graph_output(state=state, pending_id=pending.id)
        with self.database.transaction() as connection:
            current = self.repository.get_run(
                connection,
                workspace_id=workspace_id,
                session_id=session_id,
                run_id=run["id"],
            )
            if (
                current["status"] != "running"
                or current["claim_token"] != run["claim_token"]
            ):
                return "stopped"
            next_pending_id = pending.id
            if output is not None:
                context_snapshot = self._turn_context_snapshot(
                    session_id=session_id,
                    session_context=session_context,
                    pending=pending,
                    transcript=state.get("transcript", []),
                    provider_context=used_contexts.get(pending.id),
                )
                provider_metadata = state.get("turn_metadata")
                message_metadata = (
                    dict(provider_metadata)
                    if isinstance(provider_metadata, dict)
                    else {"provider": "graph-dispatch", "requestCount": 0}
                )
                message_metadata.update(
                    {
                        "runId": run["id"],
                        "graphMessageId": output.id,
                        "turnStatus": state_status,
                        "executionMode": mode,
                    }
                )
                if isinstance(session_context.get("writingFocus"), dict):
                    message_metadata["writingFocus"] = session_context["writingFocus"]
                if session_context.get("assistantMode") == "single_writer":
                    message_metadata.update({key: session_context[key] for key in (
                        "assistantMode", "contextRevision", "creatorContextSelection",
                    )})
                persisted = self.repository.append_message(
                    connection,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    sender_role=output.sender,
                    recipient_role=output.to,
                    content=output.content,
                    artifact_refs_json=_encoded(output.artifact_refs),
                    context_snapshot_json=_encoded(context_snapshot),
                    model_metadata_json=_encoded(message_metadata),
                    reply_to_message_id=pending.id,
                    now=utc_now(),
                )
                next_pending_id = persisted["id"]

            next_pending = state.get("pending")
            next_recipient = (
                output.to
                if output is not None
                else (
                    next_pending.get("to")
                    if isinstance(next_pending, dict)
                    else None
                )
            )
            next_state = {
                "schemaVersion": "content-collaboration-graph/v1",
                "pendingMessageId": next_pending_id,
                "remainingTurns": state.get("remaining_turns", 0),
                "status": state_status,
            }
            if state_status == "failed":
                self.repository.finish_run(
                    connection,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run_id=run["id"],
                    claim_token=run["claim_token"],
                    expected_revision=current["revision"],
                    status="failed",
                    graph_state_json=_encoded(next_state),
                    error_code="specialist_turn_failed",
                    error_detail="协作角色本轮未能完成，请从会话继续补充或重试。",
                    now=utc_now(),
                )
                return "finished"
            if next_pending is None:
                self.repository.finish_run(
                    connection,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run_id=run["id"],
                    claim_token=run["claim_token"],
                    expected_revision=current["revision"],
                    status="completed",
                    graph_state_json=_encoded(next_state),
                    now=utc_now(),
                )
                return "finished"
            if state_status == "waiting_creator" or next_recipient == "creator":
                self.repository.finish_run(
                    connection,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run_id=run["id"],
                    claim_token=run["claim_token"],
                    expected_revision=current["revision"],
                    status="waiting_creator",
                    graph_state_json=_encoded(next_state),
                    now=utc_now(),
                )
                return "finished"
            self.repository.save_run_state(
                connection,
                workspace_id=workspace_id,
                session_id=session_id,
                run_id=run["id"],
                claim_token=run["claim_token"],
                expected_revision=current["revision"],
                graph_state_json=_encoded(next_state),
                now=utc_now(),
            )
        return "continue"

    async def _finish_failed(
        self,
        *,
        workspace_id: str,
        session_id: str,
        code: str,
        run: dict[str, Any] | None = None,
        run_id: str | None = None,
        claim_token: str | None = None,
    ) -> None:
        resolved_run_id = run["id"] if run is not None else run_id
        resolved_token = run["claim_token"] if run is not None else claim_token
        if not isinstance(resolved_run_id, str) or not isinstance(resolved_token, str):
            return
        try:
            with self.database.transaction() as connection:
                current = self.repository.get_run(
                    connection,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run_id=resolved_run_id,
                )
                if (
                    current["status"] != "running"
                    or current["claim_token"] != resolved_token
                ):
                    return
                prior_state = _decoded_object(
                    current["graph_state_json"], field="协作图状态"
                )
                self.repository.finish_run(
                    connection,
                    workspace_id=workspace_id,
                    session_id=session_id,
                    run_id=resolved_run_id,
                    claim_token=resolved_token,
                    expected_revision=current["revision"],
                    status="failed",
                    graph_state_json=_encoded({**prior_state, "status": "failed"}),
                    error_code=code,
                    error_detail="协作执行暂时未完成；已保留此前消息，可重新发起下一条指令。",
                    now=utc_now(),
                )
        except Exception:
            # Preserve the original execution receipt whenever storage itself is
            # unavailable; startup recovery will surface an interrupted turn.
            return

    def _graph_for_turn(
        self,
        *,
        session_id: str,
        run_id: str,
        session_context: dict[str, Any],
        used_contexts: dict[str, dict[str, Any]],
        provider: SpecialistProvider,
        mode: str,
        handoff_candidates: dict[str, list[dict[str, Any]]],
    ) -> ContentCollaborationGraph:
        def context_for(
            role: str,
            message: CollaborationMessage,
            transcript: list[dict[str, Any]],
        ) -> dict[str, Any]:
            bounded = transcript[-MAX_CONTEXT_TRANSCRIPT_MESSAGES:]
            target = session_context.get("target")
            context = {
                "schemaVersion": "content-collaboration-specialist-context/v1",
                "sessionId": session_id,
                "runId": run_id,
                "role": role,
                "executionMode": mode,
                "target": target if isinstance(target, dict) else {},
                "sessionContext": session_context,
                "receivedMessage": message.model_dump(),
                # The immediate addressee receives the previous role's
                # structured candidates (with durable IDs and provenance), not
                # only their flattened display text. This is the collaboration
                # handoff that lets writing build on research and review assess
                # a particular writing option.
                "upstreamCandidates": handoff_candidates.get(message.id, []),
                "transcript": bounded,
                "transcriptTruncated": len(transcript) > len(bounded),
            }
            if session_context.get("assistantMode") == "single_writer":
                context["assistantMode"] = "single_writer"
            if isinstance(session_context.get("writingFocus"), dict):
                context["writingFocus"] = session_context["writingFocus"]
            used_contexts[message.id] = context
            return context

        if session_context.get("assistantMode") == "single_writer":
            # Keep the durable graph boundary, but never let a model/demo route
            # a public writer request to another specialist or a second call.
            delegate = provider

            class SingleWriterProvider:
                async def run(self, *, role, message, context):
                    turn = await delegate.run(role="writing", message=message, context=context)
                    return turn.model_copy(update={"to": "creator"})

            provider = SingleWriterProvider()
        return ContentCollaborationGraph(provider, context_for)

    def _provider_for_mode(self, mode: str) -> SpecialistProvider | None:
        if mode == "demo":
            return self.demo_provider
        if mode == "live":
            return self.live_provider
        return None

    def _build_session_context(
        self,
        connection,
        *,
        workspace: dict[str, Any],
        topic: dict[str, Any],
        assistant_mode: str = "legacy_team",
    ) -> dict[str, Any]:
        target = {
            "assetType": "topic",
            "assetId": topic["id"],
            "title": topic["title"],
            "body": topic["body"],
            "angle": topic["angle"],
            "associatedPainPoint": topic["associated_pain_point"],
            "whyItFits": topic["why_it_fits"],
            "status": topic["status"],
            "updatedAt": topic["updated_at"],
        }
        if assistant_mode == "single_writer":
            # The saved manuscript is always in scope; topic-generation hints,
            # implicit positioning and unrelated workspace assets are not.
            return {
                "schemaVersion": "creator-writing-session/v1", "assistantMode": "single_writer",
                "target": {key: target[key] for key in (
                    "assetType", "assetId", "title", "body", "updatedAt",
                )},
                "creatorContextSelection": {
                    "schemaVersion": "creator-context-selection/v1", "references": [],
                },
                "contextRevision": 0,
            }
        pack = self.context_access_service.build_workspace_pack(
            connection,
            workspace=workspace,
            requester={"workflowId": "content_collaboration"},
            purpose="content_collaboration_session",
            selectors=[
                "account_positioning",
                "input_assets_overview",
                "analysis_history_overview",
                "topic_library_overview",
                "draft_history_overview",
                "simulation_history_overview",
                "selected_topic",
            ],
            deep_items=[
                self.context_access_service.deep_item(
                    key="selected_topic",
                    asset_type="topic",
                    asset_id=topic["id"],
                    selector="content_collaboration_target",
                    role="collaboration_target",
                    workspace_id=workspace["id"],
                    data=target,
                )
            ],
            operation="content_collaboration",
        )
        return {
            "schemaVersion": "content-collaboration-session/v1",
            "target": target,
            "workspaceContext": pack,
        }

    @staticmethod
    def _default_title(topic: dict[str, Any]) -> str:
        title = str(topic.get("title") or "当前选题").strip()
        return f"{title[:80]} 的协作讨论"

    @staticmethod
    def _message_for_graph(row: dict[str, Any]) -> dict[str, Any]:
        recipient = row.get("recipient_role")
        if (
            row.get("sender_role") not in _COLLABORATION_ROLES
            or recipient not in _COLLABORATION_ROLES
        ):
            raise ValidationError("协作消息角色已损坏，无法继续执行")
        refs = _decoded_array(row["artifact_refs_json"], field="协作消息素材引用")
        return {
            "id": row["id"],
            "sender": row["sender_role"],
            "to": recipient,
            "content": row["content"],
            "reply_to": row.get("reply_to_message_id"),
            "artifact_refs": refs,
        }

    def _graph_transcript(self, rows: list[dict[str, Any]]) -> list[CollaborationMessage]:
        messages: list[CollaborationMessage] = []
        for row in rows:
            if row.get("sender_role") not in _COLLABORATION_ROLES:
                continue
            if row.get("recipient_role") not in _COLLABORATION_ROLES:
                continue
            messages.append(CollaborationMessage.model_validate(self._message_for_graph(row)))
        return messages

    @staticmethod
    def _handoff_candidates(rows: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
        """Recover only validated-shaped specialist candidates from durable receipts.

        Candidate suggestions are discussion material, not editable product
        assets. They are nevertheless essential context for the next role, so
        this projection retains their kinds, confidence and evidence refs while
        assigning IDs based on the persisted message that owns them.
        """
        by_message: dict[str, list[dict[str, Any]]] = {}
        allowed_kinds = {"evidence", "open_question", "outline", "copy_option", "review_note"}
        allowed_confidence = {"supported", "inference", "needs_creator"}
        for row in rows:
            if row.get("sender_role") not in {"research", "writing", "review"}:
                continue
            message_id = row.get("id")
            if not isinstance(message_id, str) or not message_id:
                continue
            try:
                metadata = _decoded_object(row["model_metadata_json"], field="协作消息模型元数据")
            except ValidationError:
                # A historic/demo message with malformed optional metadata
                # remains readable; it simply contributes no structured handoff.
                continue
            raw_candidates = metadata.get("candidateSuggestions")
            if not isinstance(raw_candidates, list):
                continue
            recovered: list[dict[str, Any]] = []
            for index, candidate in enumerate(raw_candidates):
                if not isinstance(candidate, dict):
                    continue
                kind = candidate.get("kind")
                title = candidate.get("title")
                body = candidate.get("body")
                confidence = candidate.get("confidence")
                if (
                    kind not in allowed_kinds
                    or confidence not in allowed_confidence
                    or not isinstance(title, str)
                    or not title.strip()
                    or not isinstance(body, str)
                    or not body.strip()
                ):
                    continue
                evidence_refs: list[dict[str, str]] = []
                for evidence in candidate.get("evidenceRefs", []):
                    if not isinstance(evidence, dict):
                        continue
                    source_id = evidence.get("sourceId")
                    quote = evidence.get("quote")
                    if (
                        isinstance(source_id, str)
                        and source_id
                        and isinstance(quote, str)
                        and quote
                    ):
                        evidence_refs.append({"sourceId": source_id, "quote": quote})
                recovered.append(
                    {
                        "candidateId": f"{message_id}:{index}",
                        "kind": kind,
                        "title": title,
                        "body": body,
                        "confidence": confidence,
                        "evidenceRefs": evidence_refs,
                    }
                )
            if recovered:
                by_message[message_id] = recovered
        return by_message

    @staticmethod
    def _new_graph_output(
        *, state: dict[str, Any], pending_id: str
    ) -> CollaborationMessage | None:
        transcript = state.get("transcript")
        if not isinstance(transcript, list):
            return None
        for item in reversed(transcript):
            if not isinstance(item, dict):
                continue
            if item.get("id") == pending_id:
                break
            candidate = CollaborationMessage.model_validate(item)
            if candidate.reply_to == pending_id:
                return candidate
        return None

    @staticmethod
    def _turn_context_snapshot(
        *,
        session_id: str,
        session_context: dict[str, Any],
        pending: CollaborationMessage,
        transcript: Any,
        provider_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        compact_transcript = transcript if isinstance(transcript, list) else []
        compact_transcript = compact_transcript[-MAX_CONTEXT_TRANSCRIPT_MESSAGES:]
        return {
            "schemaVersion": "content-collaboration-turn/v1",
            **({key: session_context[key] for key in (
                "assistantMode", "contextRevision", "creatorContextSelection",
                "creatorContextSnapshot",
            )} if session_context.get("assistantMode") == "single_writer" else {}),
            "sessionContextRef": {
                "sessionId": session_id,
                "contentHash": _fingerprint(session_context),
            },
            "receivedMessageId": pending.id,
            "receivedBy": pending.to,
            "transcript": compact_transcript,
            "specialistInput": provider_context or {},
        }

    def _to_response(
        self,
        row: dict[str, Any],
        *,
        messages: list[dict[str, Any]],
        runs: list[dict[str, Any]],
    ) -> ContentCollaborationSessionResponse:
        return ContentCollaborationSessionResponse.model_validate(
            {
                **self._summary_payload(row),
                "initial_context_snapshot": _decoded_object(
                    row["initial_context_snapshot_json"], field="协作初始上下文"
                ),
                "messages": [self._to_message(item) for item in messages],
                "runs": [self._to_run(item) for item in runs],
            }
        )

    def _to_summary(self, row: dict[str, Any]) -> ContentCollaborationSessionSummary:
        return ContentCollaborationSessionSummary.model_validate(self._summary_payload(row))

    @staticmethod
    def _summary_payload(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "workspace_id": row["workspace_id"],
            "title": row["title"],
            "assistant_mode": ContentCollaborationSessionService._assistant_mode(row),
            "creator_context_selection": row.get("creator_context_state", {}).get(
                "creatorContextSelection"),
            "context_revision": row.get("creator_context_state", {}).get("contextRevision", 0),
            "context_target": {
                "asset_type": row["context_target_type"],
                "asset_id": row["context_target_id"],
            },
            "status": row["status"],
            "execution_status": row["execution_status"],
            "revision": row["revision"],
            "failure_code": row["failure_code"],
            "failure_detail": row["failure_detail"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "last_message_at": row["last_message_at"],
            "completed_at": row["completed_at"],
        }

    @staticmethod
    def _assistant_mode(row: dict[str, Any]) -> str:
        initial = _decoded_object(row["initial_context_snapshot_json"], field="会话上下文")
        return "single_writer" if initial.get("assistantMode") == "single_writer" else "legacy_team"

    @staticmethod
    def _current_creator_context(connection, session: dict[str, Any]) -> dict[str, Any]:
        if ContentCollaborationSessionService._assistant_mode(session) != "single_writer":
            return {"creatorContextSelection": None, "contextRevision": 0}
        latest = connection.execute(
            "SELECT context_snapshot_json FROM content_collaboration_messages "
            "WHERE session_id=? AND sender_role='creator' ORDER BY sequence_no DESC LIMIT 1",
            (session["id"],),
        ).fetchone()
        value = (_decoded_object(latest["context_snapshot_json"], field="消息参考材料")
                 if latest is not None else {})
        return {
            "creatorContextSelection": value.get("creatorContextSelection", {
                "schemaVersion": "creator-context-selection/v1", "references": [],
            }),
            "contextRevision": value.get("contextRevision", 0),
        }

    @staticmethod
    def _to_message(row: dict[str, Any]) -> ContentCollaborationMessageResponse:
        return ContentCollaborationMessageResponse.model_validate(
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "sequence_no": row["sequence_no"],
                "sender": row["sender_role"],
                "recipient": row["recipient_role"],
                "content": row["content"],
                "reply_to_message_id": row["reply_to_message_id"],
                "artifact_refs": _decoded_array(
                    row["artifact_refs_json"], field="协作消息素材引用"
                ),
                "context_snapshot": _decoded_object(
                    row["context_snapshot_json"], field="协作消息上下文"
                ),
                "model_metadata": _decoded_object(
                    row["model_metadata_json"], field="协作消息模型元数据"
                ),
                "client_request_key": row["client_request_key"],
                "created_at": row["created_at"],
            }
        )

    @staticmethod
    def _to_run(row: dict[str, Any]) -> ContentCollaborationRunResponse:
        return ContentCollaborationRunResponse.model_validate(
            {
                "id": row["id"],
                "session_id": row["session_id"],
                "trigger_message_id": row["trigger_message_id"],
                "request_key": row["request_key"],
                "input_snapshot": _decoded_object(
                    row["input_snapshot_json"], field="协作执行输入"
                ),
                "graph_state": _decoded_object(
                    row["graph_state_json"], field="协作图状态"
                ),
                "status": row["status"],
                "attempt_count": row["attempt_count"],
                "revision": row["revision"],
                "error_code": row["error_code"],
                "error_detail": row["error_detail"],
                "created_at": row["created_at"],
                "started_at": row["started_at"],
                "completed_at": row["completed_at"],
                "updated_at": row["updated_at"],
            }
        )
