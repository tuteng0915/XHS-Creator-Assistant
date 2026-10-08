import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError as SchemaError
from test_audience_simulation_workflow import collect
from test_creator_experience import topic
from test_simulated_fans import seeded as seeded
from test_workspace_api import create_workspace, send

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import PanelTask, SimulationRunCreate
from app.services.panel_retests import PanelRetestCreate
from app.workflows.audience_simulation import FakeAudienceSimulationModelProvider


class SavedReaderProvider(FakeAudienceSimulationModelProvider):
    async def initial_reaction(self, *, persona, topic):
        return {"reaction": {"personaId": persona["id"], "stance": "理解",
                             "action": "comment", "quote": "我理解第一步了"}}

    async def debate_response(self, *, persona, topic, other_reactions, prior_reaction=None):
        return {"debateResponse": {"personaId": persona["id"], "response": "同意这个理解",
                                    "replyToId": other_reactions[0]["messageId"]}}


def edit(app, target, **fields):
    response = send(app, "PATCH", f"/api/topics/{target['id']}", json={
        "expectedUpdatedAt": target["updatedAt"], **fields,
    })
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture
def case(app, seeded, request):
    wid, _, _, fans = seeded
    app.state.simulation_workflow_service.fake_provider = SavedReaderProvider()
    target = edit(app, topic(app, wid, "练习方法🌱"), body="先写一句，再读给自己听。")
    run = app.state.simulation_service.create(wid, SimulationRunCreate(
        topic_id=target["id"], simulated_fan_ids=[f["id"] for f in fans[:2]],
        panel_task=PanelTask(reading_mode="guided", focus_questions=["第一步清楚吗？"],
                             discussion_enabled=getattr(request, "param", False)),
    ))
    collect(app, run.id)
    parent = app.state.simulation_service.get(run.id)
    assert parent.status == "completed", parent.stage_errors
    new = edit(app, target, body="先用一句话写下今天的收获，再读给自己听。")
    payload = PanelRetestCreate(request_key="retest-1", expected_updated_at=new["updatedAt"],
                               confirmed=True)
    return wid, parent, new, payload


def test_snapshot_keeps_actual_people_task_and_new_text_without_old_results(app, case, seeded):
    wid, parent, target, payload = case
    before = parent.model_dump(mode="json")
    for fan in seeded[3][:2]:
        response = send(app, "PATCH", f"/api/simulated-fans/{fan['id']}", json={
            **fan["editable"], "name": "后来完全不同的名字", "status": "archived",
            "expectedUpdatedAt": fan["updatedAt"],
        })
        assert response.status_code == 200
    child = app.state.simulation_service.create_retest(wid, parent.id, payload)
    assert child.parent_simulation_id == parent.id
    assert child.status == "pending"
    snapshot = child.input_snapshot
    assert snapshot["audiencePersonas"] == parent.persona_definitions
    assert snapshot["panelTask"] == parent.input_snapshot["panelTask"]
    assert snapshot["mode"] == parent.input_snapshot["mode"]
    assert snapshot["topic"]["body"] == target["body"]
    assert snapshot["targetContentHash"] != parent.input_snapshot["targetContentHash"]
    assert (snapshot["retest"]["parentTargetContentHash"]
            == parent.input_snapshot["targetContentHash"])
    for key in ("readerSelection", "reactionResults", "debateResults", "synthesis"):
        assert key not in snapshot
    assert child.persona_definitions == child.reaction_results == child.debate_results == []
    assert child.synthesis == child.stage_errors == child.model_metadata == {}
    assert app.state.simulation_service.get(parent.id).model_dump(mode="json") == before
    edit(app, target, body="复测创建后又写了另一份稿件。")
    assert app.state.simulation_service.get(child.id).input_snapshot == snapshot
    summary = next(r for r in app.state.simulation_service.list(wid) if r.id == child.id)
    assert summary.parent_simulation_id == parent.id


def test_same_key_replays_after_later_edits_but_changed_request_conflicts(app, case):
    wid, parent, target, payload = case
    service = app.state.simulation_service
    child = service.create_retest(wid, parent.id, payload)
    new = edit(app, target, body="后来改稿。")
    app.state.topic_service.archive(target["id"])
    assert service.create_retest(wid, parent.id, payload) == child
    changed = payload.model_copy(update={
        "expected_updated_at": PanelRetestCreate(
            request_key="other", confirmed=True, expected_updated_at=new["updatedAt"],
        ).expected_updated_at,
    })
    with pytest.raises(ConflictError, match="请求"):
        service.create_retest(wid, parent.id, changed)
    assert len(service.list(wid)) == 2


def test_concurrent_same_request_creates_only_one_child(app, case):
    wid, parent, _, payload = case
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: app.state.simulation_service.create_retest(
            wid, parent.id, payload,
        ).id, range(2)))
    assert ids[0] == ids[1]
    assert len(app.state.simulation_service.list(wid)) == 2


@pytest.mark.parametrize("change", ["stale", "archived", "unchanged", "other_workspace"])
def test_invalid_current_target_does_not_create_any_record(app, case, change):
    wid, parent, target, payload = case
    if change == "stale":
        edit(app, target, body="新改动")
        error = ConflictError
    elif change == "archived":
        app.state.topic_service.archive(target["id"])
        error = ValidationError
    elif change == "unchanged":
        target = edit(app, target, body=parent.input_snapshot["topic"]["body"])
        payload = PanelRetestCreate(request_key="same-text", confirmed=True,
                                   expected_updated_at=target["updatedAt"])
        error = ValidationError
    else:
        wid = create_workspace(app)["id"]
        error = NotFoundError
    with pytest.raises(error):
        app.state.simulation_service.create_retest(wid, parent.id, payload)
    assert len(app.state.simulation_service.list(parent.workspace_id)) == 1


@pytest.mark.parametrize("mutation", [
    "legacy_task", "unknown_task", "missing_body", "bad_hash", "no_people", "partial_persona",
    "duplicate_persona", "wrong_roster", "different_method", "pending", "failed", "manual",
])
def test_incomplete_or_incompatible_parent_cannot_be_silently_reconstructed(app, case, mutation):
    wid, parent, _, payload = case
    snapshot = deepcopy(parent.input_snapshot)
    people = deepcopy(parent.persona_definitions)
    status = "completed"
    if mutation == "legacy_task":
        snapshot.pop("panelTask")
    elif mutation == "unknown_task":
        snapshot["panelTask"]["protocolVersion"] = "panel/v999"
    elif mutation == "missing_body":
        snapshot["topic"].pop("body")
    elif mutation == "bad_hash":
        snapshot["targetContentHash"] = "bad"
    elif mutation == "no_people":
        people = []
    elif mutation == "partial_persona":
        people[0].pop("profile")
    elif mutation == "duplicate_persona":
        people[1] = deepcopy(people[0])
    elif mutation == "wrong_roster":
        snapshot["simulatedFanIds"].reverse()
    elif mutation == "different_method":
        snapshot["simulationMethod"] = "old-method"
    elif mutation in {"pending", "failed"}:
        status = mutation
    else:
        snapshot["targetType"] = "manual"
    with app.state.database.transaction() as c:
        c.execute("UPDATE simulation_runs SET input_snapshot_json=?, persona_definitions_json=?, "
                  "status=? WHERE id=?",
                  (json.dumps(snapshot), json.dumps(people), status, parent.id))
    with pytest.raises(ValidationError):
        app.state.simulation_service.create_retest(wid, parent.id, payload)
    assert len(app.state.simulation_service.list(wid)) == 1


def test_partial_parent_retests_full_panel_including_previous_failed_reader(app, case):
    wid, parent, _, payload = case
    with app.state.database.transaction() as c:
        c.execute("UPDATE simulation_runs SET status='partially_completed', "
                  "reaction_results_json='[]', "
                  "stage_errors_json=? WHERE id=?",
                  (json.dumps({"initial_reactions": "旧失败信息"}), parent.id))
    child = app.state.simulation_service.create_retest(wid, parent.id, payload)
    assert child.input_snapshot["audiencePersonas"] == parent.persona_definitions
    assert child.stage_errors == {}


@pytest.mark.parametrize("case", [False, True], indirect=True)
def test_execution_uses_exact_personas_and_no_previous_answers_even_after_resume(app, case):
    wid, parent, _, payload = case
    calls = []
    discussions = []
    enabled = parent.input_snapshot["panelTask"]["discussionEnabled"]

    class Recorder(SavedReaderProvider):
        async def personas(self, **kwargs):
            pytest.fail("must not regenerate saved readers")

        async def initial_reaction(self, *, persona, topic):
            calls.append(deepcopy({"persona": persona, "topic": topic}))
            return await super().initial_reaction(persona=persona, topic=topic)

        async def debate_response(self, **kwargs):
            assert enabled, "discussion was disabled in the original task"
            discussions.append(deepcopy(kwargs))
            return await super().debate_response(**kwargs)

    app.state.simulation_workflow_service.fake_provider = Recorder()
    service = app.state.simulation_service
    child = service.create_retest(wid, parent.id, payload)
    collect(app, child.id, stop_after_node="derive_personas")
    assert service.get(child.id).persona_definitions == parent.persona_definitions
    assert calls == []
    collect(app, child.id)
    completed = service.get(child.id)
    assert completed.status == "completed"
    assert len(discussions) == (len(parent.persona_definitions) if enabled else 0)
    assert [c["persona"] for c in calls] == parent.persona_definitions
    for call in calls:
        assert set(call) == {"persona", "topic"}
        assert set(call["topic"]) == {
            "targetType", "title", "body", "previewLevel", "limitations", "panelTask",
        }
        assert call["topic"]["body"] == child.input_snapshot["topic"]["body"]
    collect(app, child.id)
    assert len(calls) == len(parent.persona_definitions)
    assert service.create_retest(wid, parent.id, payload).status == "completed"


@pytest.mark.parametrize("origin_shape", ["absent", "null", "value"])
def test_retest_preserves_legacy_optional_origin_metadata_shape(app, case, origin_shape):
    wid, parent, _, payload = case
    people = deepcopy(parent.persona_definitions)
    for persona in people:
        if origin_shape == "absent":
            persona.pop("sourceGroupId", None)
        elif origin_shape == "null":
            persona["sourceGroupId"] = None
        else:
            persona["sourceGroupId"] = "original-group"
    with app.state.database.transaction() as connection:
        connection.execute("UPDATE simulation_runs SET persona_definitions_json=? WHERE id=?",
                           (json.dumps(people), parent.id))
    service = app.state.simulation_service
    original = service.get(parent.id)
    supplied = []

    class Recorder(SavedReaderProvider):
        async def personas(self, **kwargs):
            pytest.fail("legacy readers must not be regenerated")

        async def initial_reaction(self, *, persona, topic):
            supplied.append(deepcopy(persona))
            return await super().initial_reaction(persona=persona, topic=topic)

    app.state.simulation_workflow_service.fake_provider = Recorder()
    child = service.create_retest(wid, parent.id, payload)
    assert child.input_snapshot["audiencePersonas"] == people
    collect(app, child.id, stop_after_node="derive_personas")
    assert service.get(child.id).persona_definitions == people
    collect(app, child.id)
    finished = service.get(child.id)
    assert finished.status == "completed", finished.stage_errors
    assert finished.persona_definitions == supplied == people
    assert service.get(parent.id) == original


def test_worker_restart_resumes_child_without_duplicate_execution(app, case, pytestconfig):
    wid, parent, _, payload = case
    child = app.state.simulation_service.create_retest(wid, parent.id, payload)
    collect(app, child.id, stop_after_node="derive_personas")
    restarted = pytestconfig._create_test_app(app.state.settings)
    reactions = []

    class Recorder(SavedReaderProvider):
        async def initial_reaction(self, **kwargs):
            reactions.append(kwargs["persona"]["id"])
            await asyncio.sleep(0.01)
            return await super().initial_reaction(**kwargs)

    restarted.state.simulation_workflow_service.fake_provider = Recorder()

    async def resume():
        assert await restarted.state.workflow_worker.resume_unfinished() == 1
        assert await restarted.state.workflow_worker.enqueue_simulation_run(child.id) is False
        await restarted.state.workflow_worker.wait_for_idle()
        assert await restarted.state.workflow_worker.enqueue_simulation_run(child.id) is False

    asyncio.run(resume())
    finished = restarted.state.simulation_service.get(child.id)
    assert finished.status == "completed"
    assert finished.persona_definitions == parent.persona_definitions
    assert reactions == [p["id"] for p in parent.persona_definitions]
    assert restarted.state.simulation_service.create_retest(wid, parent.id, payload) == finished


def test_retest_can_parent_another_retest_without_changing_first_history(app, case):
    wid, parent, target, payload = case
    service = app.state.simulation_service
    child = service.create_retest(wid, parent.id, payload)
    collect(app, child.id)
    before = service.get(child.id)
    target = edit(app, target, title="第三版练习标题")
    next_payload = PanelRetestCreate(request_key="retest-2", confirmed=True,
                                    expected_updated_at=target["updatedAt"])
    next_run = service.create_retest(wid, child.id, next_payload)
    assert next_run.parent_simulation_id == child.id
    assert next_run.input_snapshot["audiencePersonas"] == parent.persona_definitions
    assert service.get(child.id) == before
    with pytest.raises(ConflictError, match="请求"):
        service.create_retest(wid, parent.id, next_payload)


def test_missing_parent_is_not_found_and_missing_people_never_fall_back(app, case):
    wid, parent, _, payload = case
    service = app.state.simulation_service
    with pytest.raises(NotFoundError):
        service.create_retest(wid, "does-not-exist", payload)
    child = service.create_retest(wid, parent.id, payload)
    snapshot = deepcopy(child.input_snapshot)
    snapshot["audiencePersonas"] = []
    with app.state.database.transaction() as c:
        c.execute("UPDATE simulation_runs SET input_snapshot_json=? WHERE id=?",
                  (json.dumps(snapshot), child.id))
    provider = SavedReaderProvider()
    app.state.simulation_workflow_service.fake_provider = provider
    collect(app, child.id)
    failed = service.get(child.id)
    assert "当时人物快照" in failed.stage_errors["personas"]
    assert failed.persona_definitions == []
    assert "personas" not in provider.calls


def test_api_requires_confirmation_and_reuses_worker_and_persisted_child(app, case, monkeypatch):
    wid, parent, _, payload = case
    worker = app.state.workflow_worker
    enqueue = AsyncMock(return_value=True)
    monkeypatch.setattr(worker, "enqueue_simulation_run", enqueue)
    path = f"/api/workspaces/{wid}/simulation-runs/{parent.id}/retests"
    body = payload.model_dump(mode="json", by_alias=True)
    for invalid in ({**body, "confirmed": False}, {**body, "confirmed": "true"},
                    {**body, "mode": "live"}, {**body, "panelTask": {}}):
        assert send(app, "POST", path, json=invalid).status_code == 422
    assert enqueue.await_count == 0
    first = send(app, "POST", path, json=body)
    second = send(app, "POST", path, json=body)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["parentSimulationId"] == parent.id
    assert {call.args[0] for call in enqueue.await_args_list} == {first.json()["id"]}
    assert len(app.state.simulation_service.list(wid)) == 2


@pytest.mark.parametrize("fields", [
    {"requestKey": " "}, {"requestKey": "x" * 121},
    {"expectedUpdatedAt": "2026-10-05T10:00:00"}, {"confirmed": 1},
])
def test_request_contract_rejects_ambiguous_values(fields):
    with pytest.raises(SchemaError):
        PanelRetestCreate.model_validate({"requestKey": "ok", "confirmed": True,
                                         "expectedUpdatedAt": "2026-10-05T10:00:00Z", **fields})


def test_child_write_failure_rolls_back_creation(app, case, monkeypatch):
    wid, parent, _, payload = case
    repository = app.state.simulation_service.repository
    create = repository.create

    def fail_after_insert(*args, **kwargs):
        create(*args, **kwargs)
        raise RuntimeError("injected failure after insert")

    monkeypatch.setattr(repository, "create", fail_after_insert)
    with pytest.raises(RuntimeError):
        app.state.simulation_service.create_retest(wid, parent.id, payload)
    assert len(app.state.simulation_service.list(wid)) == 1


def test_retest_migration_preserves_old_rows_and_enforces_request_identity():
    migration = Path(__file__).parents[1] / "app/db/migrations/0037_panel_retests.sql"
    with sqlite3.connect(":memory:") as c:
        c.execute("PRAGMA foreign_keys=ON")
        c.execute("CREATE TABLE creator_workspaces(id TEXT PRIMARY KEY)")
        c.execute("INSERT INTO creator_workspaces VALUES ('w')")
        c.execute("CREATE TABLE simulation_runs(id TEXT PRIMARY KEY, workspace_id TEXT "
                  "REFERENCES creator_workspaces(id) ON DELETE CASCADE, input_snapshot_json TEXT)")
        c.executemany("INSERT INTO simulation_runs VALUES (?, 'w', ?)",
                      [("old", '{"title":"旧稿🌱"}'), ("second", '{}')])
        c.commit()
        before = c.execute("SELECT * FROM simulation_runs ORDER BY id").fetchall()
        c.executescript(migration.read_text())
        after = c.execute("SELECT * FROM simulation_runs ORDER BY id").fetchall()
        assert [row[:3] for row in after] == before
        assert all(row[3:] == (None, None, None) for row in after)
        c.execute("UPDATE simulation_runs SET parent_simulation_id='old', "
                  "retest_request_key='key', retest_request_hash='hash' WHERE id='second'")
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE simulation_runs SET retest_request_key='key' WHERE id='old'")
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("UPDATE simulation_runs SET parent_simulation_id='missing' WHERE id='second'")
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
        c.execute("DELETE FROM creator_workspaces WHERE id='w'")
        assert c.execute("SELECT COUNT(*) FROM simulation_runs").fetchone()[0] == 0


def test_preview_returns_fixed_readers_current_text_and_never_enqueues(app, case, monkeypatch):
    wid, parent, target, _ = case
    enqueue = AsyncMock()
    monkeypatch.setattr(app.state.workflow_worker, "enqueue_simulation_run", enqueue)
    path = f"/api/workspaces/{wid}/simulation-runs/{parent.id}/retest-preview"
    response = send(app, "GET", path)
    assert response.status_code == 200
    preview = response.json()
    assert preview["readers"] == [{"id": p["id"], "name": p["name"], "profile": p["profile"]}
                                  for p in parent.persona_definitions]
    assert preview["panelTask"] == parent.input_snapshot["panelTask"]
    assert preview["body"] == target["body"]
    assert preview["topicId"] == target["id"]
    assert preview["parentSimulationId"] == parent.id
    assert len(app.state.simulation_service.list(wid)) == 1
    enqueue.assert_not_called()


def test_preview_scoping_and_stale_confirmation_use_server_versions(app, case):
    wid, parent, target, payload = case
    other = create_workspace(app)["id"]
    path = f"/api/workspaces/{other}/simulation-runs/{parent.id}/retest-preview"
    assert send(app, "GET", path).status_code == 404
    preview = app.state.simulation_service.preview_retest(wid, parent.id)
    edit(app, target, body="预览以后又修改的正文")
    with pytest.raises(ConflictError):
        app.state.simulation_service.create_retest(wid, parent.id, payload)
    assert preview["body"] == target["body"]


def test_preview_rejects_unchanged_text_without_starting_work(app, case):
    wid, parent, target, _ = case
    edit(app, target, body=parent.input_snapshot["topic"]["body"])
    path = f"/api/workspaces/{wid}/simulation-runs/{parent.id}/retest-preview"
    response = send(app, "GET", path)
    assert response.status_code == 422
    assert "尚未改变" in response.text
    assert len(app.state.simulation_service.list(wid)) == 1
