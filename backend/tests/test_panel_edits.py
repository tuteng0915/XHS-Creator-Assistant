import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path

import pytest
from test_creator_experience import topic
from test_workspace_api import create_workspace, send

from app.errors import ConflictError
from app.models import SimulationRunStatus
from app.services.audience_target import reader_visible_target
from app.services.editor_feedback import validate_editor_feedback
from app.services.panel_edits import PanelEditService


@pytest.fixture
def case(app):
    wid = create_workspace(app)["id"]
    target = topic(app, wid, "原标题")
    send(
        app,
        "PATCH",
        f"/api/topics/{target['id']}",
        json={
            "body": "🌱原句。\n原句。结尾。",
            "expectedUpdatedAt": target["updatedAt"],
        },
    )
    service = app.state.simulation_service
    with service.database.transaction() as connection:
        current = service.topic_repository.get(connection, target["id"])
        snapshot = {
            "targetType": "topic",
            "panelTask": {"protocolVersion": "panel/v1"},
            "topic": {
                "topicId": target["id"],
                "title": current["title"],
                "body": current["body"],
                "updatedAt": current["updated_at"],
            },
        }
        feedback = validate_editor_feedback(
            [
                {
                    "id": "f1",
                    "kind": "rewrite",
                    "sourceType": "editor_optional",
                    "sourceMessageIds": [],
                    "target": {"field": "body", "quote": "原句。", "occurrence": 2},
                    "observation": "第二句可以更具体",
                    "reason": "补充一种表达",
                    "priority": "optional",
                    "suggestedText": "这不是默认替换文本",
                }
            ],
            topic=reader_visible_target(snapshot),
            personas=[],
            reactions=[],
            replies=[],
        )
        snapshot["targetContentHash"] = feedback["editorFeedback"][0]["target"]["contentHash"]
        run = service.repository.create(
            connection,
            workspace_id=wid,
            topic_id=target["id"],
            draft_id=None,
            input_snapshot_json=json.dumps(snapshot),
            now=current["updated_at"],
        )
    service.save_progress(
        run["id"],
        status=SimulationRunStatus.COMPLETED,
        synthesis={"verdict": "可以调整", **feedback},
    )
    return {
        "wid": wid,
        "tid": target["id"],
        "rid": run["id"],
        "snapshot": snapshot,
        "payload": {
            "requestKey": "request-1",
            "feedbackId": "f1",
            "expectedUpdatedAt": current["updated_at"],
            "operation": "replace",
            "text": "新句。",
        },
    }


def create(app, case, **changes):
    return send(
        app,
        "POST",
        f"/api/workspaces/{case['wid']}/simulation-runs/{case['rid']}/edit-proposals",
        json={**case["payload"], **changes},
    )


def url(case, pid):
    return f"/api/workspaces/{case['wid']}/panel-edit-proposals/{pid}"


def current(app, case):
    return send(app, "GET", f"/api/topics/{case['tid']}").json()


@pytest.mark.parametrize(
    "operation,expected",
    [
        ("replace", "🌱原句。\n新句。结尾。"),
        ("insert_before", "🌱原句。\n新句。原句。结尾。"),
        ("insert_after", "🌱原句。\n原句。新句。结尾。"),
    ],
)
def test_preview_and_confirm_preserve_unselected_text_and_frozen_history(
    app, case, operation, expected
):
    before = current(app, case)
    history = app.state.simulation_service.get(case["rid"]).model_dump(mode="json")
    result = create(app, case, operation=operation)
    assert result.status_code == 201
    proposal = result.json()
    assert proposal["snapshot"]["proposed"] == {"title": before["title"], "body": expected}
    assert proposal["status"] == "pending" and proposal["receipt"] == {}
    assert current(app, case) == before
    assert send(app, "GET", url(case, proposal["id"])).json() == proposal
    applied = send(app, "POST", url(case, proposal["id"]) + "/apply", json={"confirmed": True})
    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    assert applied.json()["freshness"] == "current"
    assert current(app, case)["body"] == expected
    assert current(app, case)["generatedSnapshot"] == before["generatedSnapshot"]
    assert app.state.simulation_service.get(case["rid"]).model_dump(mode="json") == history


def test_create_replay_and_apply_replay_do_not_write_twice_or_overwrite_later_edits(app, case):
    first = create(app, case).json()
    assert create(app, case).json() == first
    assert create(app, case, text="不同请求").status_code == 409
    applied = send(app, "POST", url(case, first["id"]) + "/apply", json={"confirmed": True}).json()
    before = current(app, case)
    assert (
        send(app, "POST", url(case, first["id"]) + "/apply", json={"confirmed": True}).json()
        == applied
    )
    assert current(app, case) == before
    send(
        app,
        "PATCH",
        f"/api/topics/{case['tid']}",
        json={
            "body": "后续人工编辑",
            "expectedUpdatedAt": before["updatedAt"],
        },
    )
    replay = send(app, "POST", url(case, first["id"]) + "/apply", json={"confirmed": True}).json()
    assert replay["receipt"] == applied["receipt"] and replay["freshness"] == "stale"
    assert current(app, case)["body"] == "后续人工编辑"
    assert create(app, case).json()["id"] == first["id"]


def test_stale_creation_and_application_conflict_without_changing_either_snapshot(app, case):
    proposal = create(app, case).json()
    before = current(app, case)
    send(
        app,
        "PATCH",
        f"/api/topics/{case['tid']}",
        json={
            "body": before["body"] + "手动修改",
            "expectedUpdatedAt": before["updatedAt"],
        },
    )
    assert create(app, case, requestKey="different").status_code == 409
    assert (
        send(
            app, "POST", url(case, proposal["id"]) + "/apply", json={"confirmed": True}
        ).status_code
        == 409
    )
    observed = send(app, "GET", url(case, proposal["id"])).json()
    assert observed["snapshot"] == proposal["snapshot"] and observed["status"] == "pending"
    assert observed["receipt"] == {} and observed["freshness"] == "stale"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"confirmed": False},
        {"confirmed": 1},
        {"confirmed": "true"},
        {"confirmed": True, "text": "tamper"},
    ],
)
def test_apply_requires_explicit_boolean_confirmation(app, case, payload):
    before = current(app, case)
    proposal = create(app, case).json()
    assert send(app, "POST", url(case, proposal["id"]) + "/apply", json=payload).status_code == 422
    assert current(app, case) == before


def test_rejection_is_idempotent_and_never_applies(app, case):
    before = current(app, case)
    proposal = create(app, case).json()
    rejected = send(app, "POST", url(case, proposal["id"]) + "/reject").json()
    assert rejected["status"] == "rejected"
    assert send(app, "POST", url(case, proposal["id"]) + "/reject").json() == rejected
    assert (
        send(
            app, "POST", url(case, proposal["id"]) + "/apply", json={"confirmed": True}
        ).status_code
        == 409
    )
    assert current(app, case) == before


def test_cross_workspace_create_read_apply_and_reject_are_rejected(app, case):
    proposal = create(app, case).json()
    other = {**case, "wid": create_workspace(app)["id"]}
    assert create(app, other).status_code == 404
    assert send(app, "GET", url(other, proposal["id"])).status_code == 404
    assert (
        send(
            app, "POST", url(other, proposal["id"]) + "/apply", json={"confirmed": True}
        ).status_code
        == 404
    )
    assert send(app, "POST", url(other, proposal["id"]) + "/reject").status_code == 404


@pytest.mark.parametrize(
    "change",
    [
        {"feedbackId": "missing"},
        {"text": "原句。"},
        {"text": "长" * 50_000},
    ],
)
def test_invalid_or_noop_edits_leave_no_proposal(app, case, change):
    before = current(app, case)
    assert create(app, case, **change).status_code == 422
    assert current(app, case) == before
    with app.state.simulation_service.database.read() as connection:
        assert connection.execute("SELECT COUNT(*) FROM panel_edit_proposals").fetchone()[0] == 0


@pytest.mark.parametrize(
    "change",
    [
        {"contentHash": "wrong"},
        {"start": 1, "end": 4},
        {"occurrence": 1},
        {"start": True},
        {"field": "whole"},
        {"quote": "错误原文"},
    ],
)
def test_bad_saved_anchors_are_not_fuzzy_repaired(app, case, change):
    service = app.state.simulation_service
    with service.database.transaction() as connection:
        row = service.repository.get(connection, case["rid"])
        synthesis = json.loads(row["synthesis_json"])
        synthesis["editorFeedback"][0]["target"].update(change)
        connection.execute(
            "UPDATE simulation_runs SET synthesis_json=? WHERE id=?",
            (json.dumps(synthesis), case["rid"]),
        )
    assert create(app, case).status_code == 422


def test_concurrent_confirmation_applies_once(app, case):
    proposal = create(app, case).json()
    service = PanelEditService(app.state.simulation_service.database)
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: service.apply(case["wid"], proposal["id"]), range(2)))
    assert results[0] == results[1]
    assert current(app, case)["body"] == proposal["snapshot"]["proposed"]["body"]


def test_receipt_write_failure_rolls_back_topic_update(app, case):
    proposal = create(app, case).json()
    before = deepcopy(current(app, case))
    service = PanelEditService(app.state.simulation_service.database)
    with service.database.transaction() as connection:
        connection.execute(
            "CREATE TRIGGER fail_receipt BEFORE UPDATE ON panel_edit_proposals "
            "BEGIN SELECT RAISE(ABORT, 'test failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        service.apply(case["wid"], proposal["id"])
    assert current(app, case) == before
    assert service.get(case["wid"], proposal["id"])["status"] == "pending"


def test_list_restores_proposals_without_editing_topic_and_is_workspace_scoped(app, case):
    endpoint = f"/api/workspaces/{case['wid']}/simulation-runs/{case['rid']}/edit-proposals"
    assert send(app, "GET", endpoint).json() == []
    first = create(app, case).json()
    second = create(app, case, requestKey="second", text="备选表达").json()
    send(app, "POST", url(case, second["id"]) + "/reject")
    before = current(app, case)
    items = send(app, "GET", endpoint).json()
    assert [p["id"] for p in items] == [second["id"], first["id"]]
    assert [p["status"] for p in items] == ["rejected", "pending"]
    assert current(app, case) == before
    other = create_workspace(app)["id"]
    assert send(app, "GET", endpoint.replace(case["wid"], other)).status_code == 404
    send(app, "POST", url(case, first["id"]) + "/apply", json={"confirmed": True})
    restored = PanelEditService(app.state.simulation_service.database).list_for_run(
        case["wid"], case["rid"]
    )
    assert restored[1]["status"] == "applied" and restored[1]["receipt"]["after"]


@pytest.mark.parametrize("variant", ["legacy", "unfinished", "manual", "wrong_topic", "keep"])
def test_unsupported_feedback_never_creates_a_proposal(app, case, variant):
    service = app.state.simulation_service
    before = current(app, case)
    with service.database.transaction() as connection:
        row = service.repository.get(connection, case["rid"])
        frozen = json.loads(row["input_snapshot_json"])
        synthesis = json.loads(row["synthesis_json"])
        if variant == "legacy":
            frozen.pop("panelTask")
        elif variant == "wrong_topic":
            frozen["topic"]["topicId"] = "another-topic"
        elif variant == "keep":
            synthesis["editorFeedback"][0]["kind"] = "keep"
        elif variant == "unfinished":
            connection.execute(
                "UPDATE simulation_runs SET status='running' WHERE id=?", (case["rid"],)
            )
        elif variant == "manual":
            connection.execute(
                "UPDATE simulation_runs SET topic_id=NULL WHERE id=?", (case["rid"],)
            )
        connection.execute(
            "UPDATE simulation_runs SET input_snapshot_json=?, synthesis_json=? WHERE id=?",
            (json.dumps(frozen), json.dumps(synthesis), case["rid"]),
        )
    assert create(app, case).status_code == 422
    assert current(app, case) == before


def test_archiving_a_topic_blocks_existing_and_new_proposals(app, case):
    proposal = create(app, case).json()
    service = app.state.simulation_service
    with service.database.transaction() as connection:
        connection.execute("UPDATE topics SET status='archived' WHERE id=?", (case["tid"],))
    before = current(app, case)
    assert create(app, case, requestKey="new").status_code == 409
    assert (
        send(
            app, "POST", url(case, proposal["id"]) + "/apply", json={"confirmed": True}
        ).status_code
        == 409
    )
    assert current(app, case) == before


def test_two_alternative_proposals_cannot_overwrite_each_other(app, case):
    first = create(app, case).json()
    second = create(app, case, requestKey="alternative", text="另一种写法。").json()
    assert (
        send(app, "POST", url(case, first["id"]) + "/apply", json={"confirmed": True}).status_code
        == 200
    )
    before = current(app, case)
    assert (
        send(app, "POST", url(case, second["id"]) + "/apply", json={"confirmed": True}).status_code
        == 409
    )
    assert send(app, "POST", url(case, first["id"]) + "/reject").status_code == 409
    assert current(app, case) == before


@pytest.mark.parametrize(
    "text,status", [("新标题", 201), ("", 422), ("   ", 422), ("长" * 301, 422)]
)
def test_title_edits_preserve_body_and_validate_result(app, case, text, status):
    before = current(app, case)
    service = app.state.simulation_service
    with service.database.transaction() as connection:
        row = service.repository.get(connection, case["rid"])
        synthesis = json.loads(row["synthesis_json"])
        synthesis["editorFeedback"][0]["target"].update(
            field="title",
            quote=before["title"],
            start=0,
            end=len(before["title"]),
            occurrence=1,
        )
        connection.execute(
            "UPDATE simulation_runs SET synthesis_json=? WHERE id=?",
            (json.dumps(synthesis), case["rid"]),
        )
    result = create(app, case, text=text)
    assert result.status_code == status
    assert current(app, case) == before
    if status == 201:
        proposal = result.json()
        applied = send(app, "POST", url(case, proposal["id"]) + "/apply", json={"confirmed": True})
        assert applied.status_code == 200
        assert current(app, case)["title"] == text
        assert current(app, case)["body"] == before["body"]


def apply_proposal(app, case):
    proposal = create(app, case).json()
    return send(app, "POST", url(case, proposal["id"]) + "/apply", json={"confirmed": True}).json()


def test_undo_restores_content_with_new_version_and_keeps_original_receipt(app, case):
    original = current(app, case)
    history = app.state.simulation_service.get(case["rid"]).model_dump(mode="json")
    applied = apply_proposal(app, case)
    result = send(app, "POST", url(case, applied["id"]) + "/undo", json={"confirmed": True})
    assert result.status_code == 200
    undone = result.json()
    assert undone["status"] == "undone" and undone["freshness"] == "current"
    assert undone["receipt"] == applied["receipt"]
    assert undone["snapshot"] == applied["snapshot"]
    assert undone["undoReceipt"]["before"] == applied["receipt"]["after"]
    restored = current(app, case)
    assert restored["title"] == original["title"] and restored["body"] == original["body"]
    assert restored["updatedAt"] not in {
        original["updatedAt"],
        applied["receipt"]["after"]["updatedAt"],
    }
    assert restored["generatedSnapshot"] == original["generatedSnapshot"]
    assert app.state.simulation_service.get(case["rid"]).model_dump(mode="json") == history
    service = PanelEditService(app.state.simulation_service.database)
    assert service.undo(case["wid"], applied["id"]) == undone
    send(
        app,
        "PATCH",
        f"/api/topics/{case['tid']}",
        json={
            "body": "撤销后的新编辑",
            "expectedUpdatedAt": restored["updatedAt"],
        },
    )
    replay = service.undo(case["wid"], applied["id"])
    assert replay["undoReceipt"] == undone["undoReceipt"] and replay["freshness"] == "stale"
    assert current(app, case)["body"] == "撤销后的新编辑"
    assert service.list_for_run(case["wid"], case["rid"])[0]["status"] == "undone"
    for action in ("apply", "reject"):
        assert (
            send(
                app, "POST", url(case, applied["id"]) + f"/{action}", json={"confirmed": True}
            ).status_code
            == 409
        )


@pytest.mark.parametrize("change", ["body", "title", "same_text_new_version", "archived"])
def test_undo_never_overwrites_later_edits_or_archived_topics(app, case, change):
    applied = apply_proposal(app, case)
    version = current(app, case)
    if change == "archived":
        with app.state.simulation_service.database.transaction() as connection:
            connection.execute("UPDATE topics SET status='archived' WHERE id=?", (case["tid"],))
    else:
        payload = {"expectedUpdatedAt": version["updatedAt"]}
        payload["title" if change == "title" else "body"] = (
            version["body"] if change == "same_text_new_version" else "后续编辑"
        )
        send(app, "PATCH", f"/api/topics/{case['tid']}", json=payload)
    before = current(app, case)
    assert (
        send(app, "POST", url(case, applied["id"]) + "/undo", json={"confirmed": True}).status_code
        == 409
    )
    assert current(app, case) == before
    saved = send(app, "GET", url(case, applied["id"])).json()
    assert saved["receipt"] == applied["receipt"] and saved["undoReceipt"] == {}
    assert saved["status"] == "applied"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"confirmed": False},
        {"confirmed": 1},
        {"confirmed": "true"},
        {"confirmed": True, "body": "new"},
    ],
)
def test_undo_requires_explicit_confirmation(app, case, payload):
    applied = apply_proposal(app, case)
    before = current(app, case)
    assert send(app, "POST", url(case, applied["id"]) + "/undo", json=payload).status_code == 422
    assert current(app, case) == before


@pytest.mark.parametrize("status", ["pending", "rejected"])
def test_undo_cannot_change_unapplied_proposals(app, case, status):
    proposal = create(app, case).json()
    if status == "rejected":
        send(app, "POST", url(case, proposal["id"]) + "/reject")
    before = current(app, case)
    assert (
        send(app, "POST", url(case, proposal["id"]) + "/undo", json={"confirmed": True}).status_code
        == 409
    )
    assert current(app, case) == before


def test_undo_is_workspace_scoped_concurrent_and_rolls_back_on_receipt_failure(app, case):
    applied = apply_proposal(app, case)
    other = {**case, "wid": create_workspace(app)["id"]}
    assert (
        send(app, "POST", url(other, applied["id"]) + "/undo", json={"confirmed": True}).status_code
        == 404
    )
    service = PanelEditService(app.state.simulation_service.database)
    before = current(app, case)
    with service.database.transaction() as connection:
        connection.execute(
            "CREATE TRIGGER fail_undo BEFORE UPDATE ON panel_edit_proposals "
            "BEGIN SELECT RAISE(ABORT, 'test failure'); END"
        )
    with pytest.raises(sqlite3.IntegrityError):
        service.undo(case["wid"], applied["id"])
    assert current(app, case) == before
    assert service.get(case["wid"], applied["id"]) == applied
    with service.database.transaction() as connection:
        connection.execute("DROP TRIGGER fail_undo")
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: service.undo(case["wid"], applied["id"]), range(2)))
    assert results[0] == results[1]


def test_undo_rejects_a_later_proposal_even_if_it_is_then_undone(app, case):
    first = apply_proposal(app, case)
    service = PanelEditService(app.state.simulation_service.database)
    # Install a second valid pending proposal on the current applied version.
    # Its creation validation is covered separately; here we exercise the real apply/undo writes.
    with service.database.transaction() as connection:
        row = service._get(connection, case["wid"], first["id"])
        snapshot = json.loads(row["snapshot_json"])
        snapshot["before"] = first["receipt"]["after"]
        snapshot["proposed"]["body"] = "第二份提案正文"
        connection.execute(
            "INSERT INTO panel_edit_proposals(id,workspace_id,simulation_id,topic_id,request_key,"
            "request_json,snapshot_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                "second",
                case["wid"],
                case["rid"],
                case["tid"],
                "second",
                "{}",
                json.dumps(snapshot),
                row["created_at"],
                row["updated_at"],
            ),
        )
    service.apply(case["wid"], "second")
    with pytest.raises(ConflictError):
        service.undo(case["wid"], first["id"])
    service.undo(case["wid"], "second")
    before = current(app, case)
    with pytest.raises(ConflictError):
        service.undo(case["wid"], first["id"])
    assert current(app, case) == before


def test_undo_migration_preserves_existing_proposals_and_constraints():
    migrations = Path(__file__).parents[1] / "app/db/migrations"
    with sqlite3.connect(":memory:") as connection:
        connection.execute("PRAGMA foreign_keys=ON")
        for table in ("creator_workspaces", "simulation_runs", "topics"):
            connection.execute(f"CREATE TABLE {table}(id TEXT PRIMARY KEY)")
            connection.execute(f"INSERT INTO {table} VALUES ('parent')")
        connection.executescript((migrations / "0035_panel_edit_proposals.sql").read_text())
        for status in ("pending", "applied", "rejected"):
            connection.execute(
                "INSERT INTO panel_edit_proposals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    status,
                    "parent",
                    "parent",
                    "parent",
                    status,
                    "request",
                    "snapshot🌱",
                    status,
                    "original receipt",
                    "created",
                    "updated",
                ),
            )
        original = connection.execute("SELECT * FROM panel_edit_proposals ORDER BY id").fetchall()
        connection.commit()
        connection.executescript((migrations / "0036_panel_edit_undo.sql").read_text())
        rows = connection.execute("SELECT * FROM panel_edit_proposals ORDER BY id").fetchall()
        assert [row[:-1] for row in rows] == original
        assert all(row[-1] == "{}" for row in rows)
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        connection.execute("UPDATE panel_edit_proposals SET status='undone' WHERE id='applied'")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE panel_edit_proposals SET request_key='pending' WHERE id='rejected'"
            )
