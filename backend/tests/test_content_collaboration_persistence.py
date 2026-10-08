import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from app.db.database import SQLiteDatabase
from app.errors import ConflictError, NotFoundError, ValidationError
from app.repositories.content_collaboration import ContentCollaborationRepository
from app.repositories.topics import TopicRepository
from app.repositories.workspaces import WorkspaceRepository

NOW = "2026-10-06T12:00:00.000000+00:00"


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


@pytest.fixture
def store(tmp_path):
    database = SQLiteDatabase(tmp_path / "collaboration.sqlite3")
    database.migrate()
    workspaces, topics, repository = (
        WorkspaceRepository(),
        TopicRepository(),
        ContentCollaborationRepository(),
    )
    with database.transaction() as connection:
        workspace = workspaces.create(
            connection, name="甲的工作区", account_positioning="写得具体", now=NOW
        )
        topic = topics.create(
            connection,
            workspace_id=workspace["id"],
            title="把经历写清楚",
            angle="从一次选择说起",
            associated_pain_point="不知道怎么开头",
            why_it_fits="已有素材",
            generated_snapshot_json="{}",
            source_analysis_run_id=None,
            source_workflow="manual",
            now=NOW,
        )
        other_workspace = workspaces.create(
            connection, name="乙的工作区", account_positioning="", now=NOW
        )
        other_topic = topics.create(
            connection,
            workspace_id=other_workspace["id"],
            title="另一篇",
            angle="",
            associated_pain_point="",
            why_it_fits="",
            generated_snapshot_json="{}",
            source_analysis_run_id=None,
            source_workflow="manual",
            now=NOW,
        )
    return database, repository, workspace, topic, other_workspace, other_topic


def create_session(database, repository, workspace, topic, *, key="new-session"):
    with database.transaction() as connection:
        return repository.create_session(
            connection,
            workspace_id=workspace["id"],
            title="把这篇写好",
            context_target_type="topic",
            context_target_id=topic["id"],
            initial_context_snapshot_json=encoded(
                {"topicId": topic["id"], "topicUpdatedAt": topic["updated_at"]}
            ),
            create_request_key=key,
            create_request_fingerprint="session/v1",
            now=NOW,
        )


def append_creator_message(database, repository, workspace, session, *, key="message-1"):
    with database.transaction() as connection:
        return repository.append_message(
            connection,
            workspace_id=workspace["id"],
            session_id=session["id"],
            sender_role="creator",
            recipient_role="research",
            content="先核对这里的事实，再给我两个写法方向。",
            artifact_refs_json="[]",
            context_snapshot_json=encoded({"schemaVersion": "context/v1"}),
            model_metadata_json="{}",
            client_request_key=key,
            client_request_fingerprint="creator-message/v1",
            now=NOW,
        )


def test_session_is_workspace_scoped_and_creation_is_idempotent(store):
    database, repository, workspace, topic, other_workspace, other_topic = store
    created = create_session(database, repository, workspace, topic)
    replay = create_session(database, repository, workspace, topic)
    assert replay == created
    assert created["context_target_type"] == "topic"
    assert created["context_target_id"] == topic["id"]
    assert created["execution_status"] == "idle"

    with database.transaction() as connection:
        with pytest.raises(ConflictError):
            repository.create_session(
                connection,
                workspace_id=workspace["id"],
                title="不同会话",
                context_target_type="topic",
                context_target_id=topic["id"],
                initial_context_snapshot_json="{}",
                create_request_key="new-session",
                create_request_fingerprint="different-input",
                now=NOW,
            )
        with pytest.raises(NotFoundError):
            repository.create_session(
                connection,
                workspace_id=workspace["id"],
                title="错误账号目标",
                context_target_type="topic",
                context_target_id=other_topic["id"],
                initial_context_snapshot_json="{}",
                now=NOW,
            )
    with database.read() as connection, pytest.raises(NotFoundError):
        repository.get_session(
            connection, workspace_id=other_workspace["id"], session_id=created["id"]
        )


def test_messages_are_append_only_and_client_request_is_idempotent(store):
    database, repository, workspace, topic, _, _ = store
    session = create_session(database, repository, workspace, topic)
    first = append_creator_message(database, repository, workspace, session)
    replay = append_creator_message(database, repository, workspace, session)
    assert replay == first
    assert first["sequence_no"] == 1
    assert first["id"] and first["created_at"] == NOW

    with database.transaction() as connection:
        with pytest.raises(ConflictError):
            repository.append_message(
                connection,
                workspace_id=workspace["id"],
                session_id=session["id"],
                sender_role="creator",
                recipient_role="research",
                content="不同的内容",
                artifact_refs_json="[]",
                context_snapshot_json="{}",
                model_metadata_json="{}",
                client_request_key="message-1",
                client_request_fingerprint="different-message/v1",
                now=NOW,
            )
        assistant = repository.append_message(
            connection,
            workspace_id=workspace["id"],
            session_id=session["id"],
            sender_role="research",
            recipient_role="creator",
            content="我需要先确认你想强调哪一次选择。",
            artifact_refs_json="[]",
            context_snapshot_json="{}",
            model_metadata_json=encoded({"provider": "fake"}),
            reply_to_message_id=first["id"],
            now="2026-10-06T12:00:01.000000+00:00",
        )
        assert assistant["sequence_no"] == 2
        assert assistant["reply_to_message_id"] == first["id"]
        with pytest.raises(ValidationError):
            repository.append_message(
                connection,
                workspace_id=workspace["id"],
                session_id=session["id"],
                sender_role="research",
                recipient_role="creator",
                content="不应允许假冒用户请求",
                artifact_refs_json="[]",
                context_snapshot_json="{}",
                model_metadata_json="{}",
                client_request_key="not-allowed",
                client_request_fingerprint="x",
                now=NOW,
            )
    with database.read() as connection:
        assert [m["id"] for m in repository.list_messages(
            connection, workspace_id=workspace["id"], session_id=session["id"]
        )] == [first["id"], assistant["id"]]


def test_runs_have_one_claimant_and_version_checked_finish(store):
    database, repository, workspace, topic, _, _ = store
    session = create_session(database, repository, workspace, topic)
    message = append_creator_message(database, repository, workspace, session)
    with database.transaction() as connection:
        run = repository.create_run(
            connection,
            workspace_id=workspace["id"],
            session_id=session["id"],
            request_key="run-1",
            request_fingerprint="run-input/v1",
            input_snapshot_json=encoded({"messages": [message["id"]]}),
            trigger_message_id=message["id"],
            now=NOW,
        )
        assert run["status"] == "queued"

    def claim_once(_):
        with database.transaction() as connection:
            return repository.claim_run(
                connection,
                workspace_id=workspace["id"],
                session_id=session["id"],
                run_id=run["id"],
                now="2026-10-06T12:00:02.000000+00:00",
            )

    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(pool.map(claim_once, range(4)))
    successful = [claim for claim in claims if claim is not None]
    assert len(successful) == 1
    claim = successful[0]
    assert claim["status"] == "running" and claim["attempt_count"] == 1

    with database.transaction() as connection:
        checkpoint = repository.save_run_state(
            connection,
            workspace_id=workspace["id"],
            session_id=session["id"],
            run_id=run["id"],
            claim_token=claim["claim_token"],
            expected_revision=claim["revision"],
            graph_state_json=encoded({"pending": message["id"]}),
            now="2026-10-06T12:00:03.000000+00:00",
        )
        with pytest.raises(ConflictError):
            repository.finish_run(
                connection,
                workspace_id=workspace["id"],
                session_id=session["id"],
                run_id=run["id"],
                claim_token=claim["claim_token"],
                expected_revision=claim["revision"],
                status="waiting_creator",
                graph_state_json="{}",
                now=NOW,
            )
        finished = repository.finish_run(
            connection,
            workspace_id=workspace["id"],
            session_id=session["id"],
            run_id=run["id"],
            claim_token=claim["claim_token"],
            expected_revision=checkpoint["revision"],
            status="waiting_creator",
            graph_state_json=checkpoint["graph_state_json"],
            now="2026-10-06T12:00:04.000000+00:00",
        )
        assert finished["status"] == "waiting_creator"
        assert finished["claim_token"] is None
        session_after = repository.get_session(
            connection, workspace_id=workspace["id"], session_id=session["id"]
        )
        assert session_after["execution_status"] == "waiting_creator"


def test_interrupted_run_is_explicit_recovery_not_silent_resume(store):
    database, repository, workspace, topic, _, _ = store
    session = create_session(database, repository, workspace, topic)
    message = append_creator_message(database, repository, workspace, session)
    with database.transaction() as connection:
        run = repository.create_run(
            connection,
            workspace_id=workspace["id"],
            session_id=session["id"],
            request_key="run-interrupted",
            request_fingerprint="run-interrupted/v1",
            input_snapshot_json="{}",
            trigger_message_id=message["id"],
            now=NOW,
        )
        assert repository.claim_run(
            connection,
            workspace_id=workspace["id"],
            session_id=session["id"],
            run_id=run["id"],
            now=NOW,
        )
    with database.transaction() as connection:
        interrupted = repository.interrupt_running_runs(
            connection, now="2026-10-06T12:00:05.000000+00:00"
        )
        assert interrupted == 1
    with database.read() as connection:
        restored = repository.get_run(
            connection, workspace_id=workspace["id"], session_id=session["id"], run_id=run["id"]
        )
        assert restored["status"] == "failed"
        assert restored["error_code"] == "interrupted"
        assert repository.list_queued_runs(connection) == []
