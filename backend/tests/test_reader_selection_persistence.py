from concurrent.futures import ThreadPoolExecutor

import pytest
from pydantic import ValidationError as PydanticValidationError
from test_reader_selection import fan, proposal, snapshot
from test_simulated_fans import seeded as seeded
from test_workspace_api import send

from app.db.database import SQLiteDatabase
from app.errors import ConflictError, NotFoundError, ValidationError
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import utc_now
from app.services.reader_selection import prepare_reader_selection
from app.services.reader_selections import ReaderSelectionCreate, ReaderSelectionService


@pytest.fixture
def store(tmp_path):
    db = SQLiteDatabase(tmp_path / "readers.sqlite3")
    db.migrate()
    with db.transaction() as c:
        workspace = WorkspaceRepository().create(
            c, name="创作者的工作区", account_positioning="跨领域🌱", now=utc_now(),
        )
    return ReaderSelectionService(db), workspace["id"]


def payload(wid, key="click-1"):
    inputs = prepare_reader_selection(
        wid, snapshot(workspaceId=wid), [fan(workspaceId=wid)],
    )
    return ReaderSelectionCreate(request_key=key, input_snapshot=inputs)


def test_migrate_twice_utf8_snapshot_and_observation_only(store):
    service, wid = store
    service.database.migrate()
    request = payload(wid)
    created = service.create(wid, request)
    assert created.status == "pending"
    assert created.started_at is None and created.completed_at is None
    assert created.result is None and created.error_code is None
    assert "claimToken" not in created.model_dump(by_alias=True)
    before = created.model_dump()
    request.input_snapshot.candidates[0].profile = "后来编辑"
    request.input_snapshot.target["body"] = "后来正文"
    for _ in range(3):
        assert service.get(wid, created.id).model_dump() == before
    assert service.pending()[0].id == created.id
    with service.database.read() as c:
        row = service.repository.get(c, wid, created.id)
        assert "想先试，再核对成本🌱" in row["input_snapshot_json"]
        assert c.execute(
            "SELECT COUNT(*) FROM schema_migrations WHERE version='0033_reader_selections.sql'"
        ).fetchone()[0] == 1
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []


def test_concurrent_create_and_claim_have_one_winner(store):
    service, wid = store
    with ThreadPoolExecutor(max_workers=6) as pool:
        runs = list(pool.map(lambda _: service.create(wid, payload(wid)), range(12)))
    assert len({run.id for run in runs}) == 1
    with ThreadPoolExecutor(max_workers=6) as pool:
        claims = list(pool.map(lambda _: service.claim(wid, runs[0].id), range(12)))
    assert len([claim for claim in claims if claim is not None]) == 1
    assert service.pending() == []
    running = service.get(wid, runs[0].id)
    assert running.status == "running" and running.started_at
    assert running.completed_at is None
    assert service.create(wid, payload(wid)) == running


@pytest.mark.parametrize("change", ["target", "version", "count"])
def test_same_key_changed_input_conflicts_without_replacing_original(store, change):
    service, wid = store
    request = payload(wid)
    original = service.create(wid, request)
    if change == "target":
        request.input_snapshot.target["title"] = "新选题"
    elif change == "version":
        request.input_snapshot.candidates[0].updated_at = "2026-10-04T00:00:00Z"
    else:
        request.input_snapshot.desired_count = 6
    with pytest.raises(ConflictError):
        service.create(wid, request)
    assert service.get(wid, original.id) == original
    request.request_key = "new-click"
    assert service.create(wid, request).id != original.id


def test_account_scoping_and_missing_workspace(store):
    service, wid = store
    created = service.create(wid, payload(wid))
    with pytest.raises(ValidationError):
        service.create("other", payload(wid))
    with pytest.raises(NotFoundError):
        service.create("other", payload("other"))
    for action in (
        lambda: service.get("other", created.id),
        lambda: service.claim("other", created.id),
        lambda: service.complete("other", created.id, "token", {}),
        lambda: service.fail("other", created.id, "token"),
    ):
        with pytest.raises(NotFoundError):
            action()
    with service.database.transaction() as c:
        second = WorkspaceRepository().create(
            c, name="另一个账号", account_positioning="", now=utc_now(),
        )["id"]
    assert service.create(second, payload(second)).id != created.id
    assert service.get(wid, created.id) == created


@pytest.mark.parametrize("key", ["", "   ", "x" * 201])
def test_request_key_validation(store, key):
    _, wid = store
    with pytest.raises(PydanticValidationError):
        payload(wid, key)


@pytest.mark.parametrize(("output", "status", "count", "error"), [
    ({"proposedReaders": [proposal()]}, "completed", 1, None),
    ({"proposedReaders": [], "unmatchedReason": "当前题目暂无合适读者"},
     "completed", 0, None),
    ({"proposedReaders": [proposal(), proposal("unknown")]}, "partially_completed", 1, None),
    ({"proposedReaders": [proposal("unknown")]}, "failed", 0, "invalid_output"),
    ({"proposedReaders": []}, "failed", None, "invalid_output"),
    ({"proposedReaders": [proposal()] * 4}, "failed", None, "invalid_output"),
])
def test_finish_validates_and_persists_results_and_metadata(store, output, status, count, error):
    service, wid = store
    request = payload(wid)
    created = service.create(wid, request)
    claim = service.claim(wid, created.id)
    assert claim is not None
    metadata = {"provider": "test", "model": "fake-only", "usage": {"outputTokens": 12}}
    ended = service.complete(wid, created.id, claim.token, output, model_metadata=metadata)
    assert ended.status == status and ended.error_code == error
    if count is None:
        assert ended.result is None
    else:
        assert ended.result is not None and len(ended.result.proposed_readers) == count
        assert ended.result.status == status
        if status in {"failed", "partially_completed"}:
            assert ended.result.validation_warnings[0].code == "unknown_reader"
    assert ended.created_at <= ended.started_at <= ended.completed_at
    metadata["usage"]["outputTokens"] = 99
    output["proposedReaders"].clear()
    reopened = ReaderSelectionService(SQLiteDatabase(service.database.path))
    assert reopened.get(wid, created.id) == ended
    assert reopened.create(wid, request) == ended
    assert reopened.claim(wid, created.id) is None
    assert reopened.get(wid, created.id).model_metadata["usage"]["outputTokens"] == 12
    for action in (
        lambda: reopened.complete(wid, created.id, claim.token, {"proposedReaders": [proposal()]}),
        lambda: reopened.fail(wid, created.id, claim.token),
    ):
        with pytest.raises(ConflictError):
            action()
    assert reopened.get(wid, created.id) == ended


def test_claim_receipt_cannot_change_validation_pool_and_wrong_tokens_cannot_write(store):
    service, wid = store
    created = service.create(wid, payload(wid))
    with pytest.raises(ConflictError):
        service.fail(wid, created.id, "not-claimed")
    assert service.get(wid, created.id) == created
    claim = service.claim(wid, created.id)
    claim.selection.input_snapshot.candidates[0].id = "injected"
    running = service.get(wid, created.id)
    with pytest.raises(ConflictError):
        service.complete(wid, created.id, "wrong-token", {"proposedReaders": [proposal()]})
    assert service.get(wid, created.id) == running
    ended = service.complete(
        wid, created.id, claim.token, {"proposedReaders": [proposal("injected")]},
    )
    assert ended.status == "failed"
    assert ended.input_snapshot.candidates[0].id == "a"


def test_restart_recovery_preserves_pending_and_terminal_and_rejects_late_write(store):
    service, wid = store
    pending = service.create(wid, payload(wid, "pending"))
    running = service.create(wid, payload(wid, "running"))
    claim = service.claim(wid, running.id)
    failed = service.create(wid, payload(wid, "failed"))
    failure_claim = service.claim(wid, failed.id)
    failed = service.fail(wid, failed.id, failure_claim.token, model_metadata={"model": "fake"})
    completed = service.create(wid, payload(wid, "completed"))
    completion_claim = service.claim(wid, completed.id)
    completed = service.complete(
        wid, completed.id, completion_claim.token, {"proposedReaders": [proposal()]},
    )
    # Constructing an observer/service must not interrupt a live worker.
    restarted = ReaderSelectionService(SQLiteDatabase(service.database.path))
    assert restarted.get(wid, running.id).status == "running"
    assert restarted.interrupt_running() == 1
    assert restarted.interrupt_running() == 0
    interrupted = restarted.get(wid, running.id)
    assert interrupted.status == "failed" and interrupted.error_code == "interrupted"
    assert interrupted.completed_at
    assert restarted.get(wid, failed.id) == failed
    assert restarted.get(wid, completed.id) == completed
    assert restarted.get(wid, pending.id) == pending
    assert restarted.pending() == [pending]
    assert restarted.create(wid, payload(wid, "running")) == interrupted
    assert restarted.claim(wid, running.id) is None
    with pytest.raises(ConflictError):
        service.complete(wid, running.id, claim.token, {"proposedReaders": [proposal()]})
    assert restarted.get(wid, running.id) == interrupted
    assert restarted.claim(wid, pending.id) is not None
    # A deliberate retry has its own record, not a reset of unknown external work.
    assert restarted.create(wid, payload(wid, "retry-click")).status == "pending"


def test_saved_fan_edits_do_not_rewrite_old_selection(app, seeded):
    wid, _, _, _ = seeded
    fans = app.state.simulated_fan_service.list(wid)
    fan_before = fans[0]
    service = ReaderSelectionService(app.state.database)
    inputs = prepare_reader_selection(wid, snapshot(workspaceId=wid), fans)
    created = service.create(
        wid, ReaderSelectionCreate(request_key="before", input_snapshot=inputs),
    )
    claim = service.claim(wid, created.id)
    edited = send(app, "PATCH", f"/api/simulated-fans/{fan_before.id}", json={
        **fan_before.editable.model_dump(by_alias=True),
        "name": "后来改过的读者🌱", "coreConcern": "先核对精力成本再决定",
        "expectedUpdatedAt": fan_before.updated_at,
    })
    assert edited.status_code == 200
    completed = service.complete(wid, created.id, claim.token, {
        "proposedReaders": [proposal(fan_before.id)],
    })
    assert completed.input_snapshot == inputs
    assert completed.input_snapshot.candidates[0].name == fan_before.editable.name
    current_fans = app.state.simulated_fan_service.list(wid)
    next_inputs = prepare_reader_selection(wid, snapshot(workspaceId=wid), current_fans)
    next_run = service.create(wid, ReaderSelectionCreate(
        request_key="after", input_snapshot=next_inputs,
    ))
    assert next_run.input_hash != completed.input_hash
    assert next_run.input_snapshot.candidates[0].name == "后来改过的读者🌱"
    assert service.get(wid, completed.id) == completed
    assert app.state.simulated_fan_service.get(fan_before.id).original == fan_before.original
