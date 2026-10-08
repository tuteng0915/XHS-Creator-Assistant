"""Historical notes remain source assets while recommendation and reading use snapshots."""
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError as SchemaError
from test_reader_selection import proposal
from test_simulated_fans import seeded as seeded
from test_workspace_api import create_workspace, send

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import PanelTask, SimulationRunCreate
from app.services.audience_target import reader_visible_target
from app.services.common import utc_now
from app.services.reader_selection_requests import ReaderSelectionRequest


def replace_notes(app, material_id, notes):
    with app.state.database.transaction() as connection:
        row = connection.execute(
            "SELECT text_content FROM source_materials WHERE id=?", (material_id,),
        ).fetchone()
        profile = json.loads(row["text_content"])
        profile["notes"] = notes
        connection.execute(
            "UPDATE source_materials SET text_content=?,updated_at=? WHERE id=?",
            (json.dumps(profile, ensure_ascii=False), utc_now(), material_id),
        )


@pytest.fixture
def saved_note(app, seeded):
    wid, source, _, fans = seeded
    notes = [{
        "noteId": "published-note", "title": "这篇图文为什么没被看完",
        "desc": "先展示一个例子，再解释读者今天能怎么做。",
        "metrics": {"views": 82, "liked": 2}, "publishedAt": "2026-10-01",
        "comments": [{"content": "历史评论不得冒充本次试读反馈"}],
        "coverMediaAssetId": "existing-cover",
    }]
    replace_notes(app, source["id"], notes)
    return wid, source, fans, notes


def recommended_note(app, saved_note):
    wid, source, fans, notes = saved_note
    payload = ReaderSelectionRequest(
        request_key="recommend-published-note", source_material_id=source["id"],
        note_id=notes[0]["noteId"], panel_task=PanelTask(),
    )
    selection = app.state.reader_selection_requests.create(wid, payload)
    claim = app.state.reader_selection_service.claim(wid, selection.id)
    selection = app.state.reader_selection_service.complete(wid, selection.id, claim.token, {
        "proposedReaders": [proposal(fans[0]["id"])],
    })
    simulation = SimulationRunCreate(
        source_material_id=source["id"], note_id=notes[0]["noteId"],
        simulated_fan_ids=[fans[0]["id"]], panel_task=PanelTask(),
        reader_selection_id=selection.id, reader_selection_input_hash=selection.input_hash,
    )
    return payload, selection, simulation


def test_historical_note_enters_recommendation_and_simulation_without_creating_topic(
    app, saved_note,
):
    wid, source, fans, notes = saved_note
    assert send(app, "GET", f"/api/workspaces/{wid}/topics").json() == []
    _, selection, payload = recommended_note(app, saved_note)
    target = selection.input_snapshot.target
    assert target["targetType"] == "note"
    assert target["title"] == notes[0]["title"]
    assert target["body"] == notes[0]["desc"]
    assert target["previewLevel"] == "text_draft"
    assert "metrics" not in target and "comments" not in target
    assert "历史评论不得冒充" not in json.dumps(target, ensure_ascii=False)
    run = app.state.simulation_service.create(wid, payload)
    assert run.topic_id is None and run.draft_id is None
    assert run.input_snapshot["targetType"] == "note"
    assert reader_visible_target(run.input_snapshot) == target
    assert run.input_snapshot["sourceNote"]["sourceMaterialId"] == source["id"]
    assert run.input_snapshot["sourceNote"]["noteId"] == notes[0]["noteId"]
    assert run.input_snapshot["sourceNote"]["metrics"] == notes[0]["metrics"]
    assert run.input_snapshot["sourceNote"]["publishedAt"] == "2026-10-01"
    assert run.input_snapshot["readerSelection"]["source"] == "recommended"
    assert run.input_snapshot["readerSelection"]["actualFanIds"] == [fans[0]["id"]]
    assert len(run.input_snapshot["targetContentHash"]) == 64
    assert send(app, "GET", f"/api/workspaces/{wid}/topics").json() == []


def test_saved_reading_snapshot_survives_original_note_edit_and_removal(app, saved_note):
    wid, source, _, notes = saved_note
    _, selection, payload = recommended_note(app, saved_note)
    run = app.state.simulation_service.create(wid, payload)
    original = deepcopy(run.input_snapshot)
    changed = [{**notes[0], "title": "后来的标题", "desc": "后来的正文", "metrics": {"views": 900}}]
    replace_notes(app, source["id"], changed)
    assert app.state.simulation_service.get(run.id).input_snapshot == original
    replace_notes(app, source["id"], [])
    assert app.state.simulation_service.get(run.id).input_snapshot == original
    observed = app.state.reader_selection_requests.observe(wid, selection.id)
    assert observed.freshness.status == "unavailable"
    assert observed.input_snapshot == selection.input_snapshot
    assert observed.result == selection.result


@pytest.mark.parametrize("change", ["title", "desc"])
def test_recommendation_adoption_rejects_changed_historical_text(app, saved_note, change):
    wid, source, fans, notes = saved_note
    _, selection, payload = recommended_note(app, saved_note)
    replace_notes(app, source["id"], [{**notes[0], change: "修改后的阅读内容"}])
    observation = app.state.reader_selection_requests.observe(wid, selection.id)
    assert observation.freshness.status == "stale"
    assert "target_changed" in observation.freshness.reasons
    with pytest.raises(ConflictError, match="依据已变化"):
        app.state.simulation_service.create(wid, payload)
    assert app.state.simulation_service.list(wid) == []
    manual = app.state.simulation_service.create(wid, SimulationRunCreate(
        source_material_id=source["id"], note_id=notes[0]["noteId"],
        simulated_fan_ids=[fans[0]["id"]], panel_task=PanelTask(),
    ))
    assert manual.input_snapshot["readerSelection"]["source"] == "manual"
    target_field = "title" if change == "title" else "body"
    assert manual.input_snapshot["topic"][target_field] == "修改后的阅读内容"


def test_metrics_and_comments_refresh_does_not_change_the_reading_target(app, saved_note):
    wid, source, _, notes = saved_note
    _, selection, payload = recommended_note(app, saved_note)
    replace_notes(app, source["id"], [{**notes[0], "metrics": {"views": 900},
                                      "comments": [{"content": "新采集评论"}]}])
    observed = app.state.reader_selection_requests.observe(wid, selection.id)
    assert observed.freshness.status == "current"
    run = app.state.simulation_service.create(wid, payload)
    assert run.input_snapshot["sourceNote"]["metrics"] == {"views": 900}
    assert reader_visible_target(run.input_snapshot) == selection.input_snapshot.target


@pytest.mark.parametrize("mismatch", ["note", "material", "manual"])
def test_same_text_from_a_different_source_cannot_adopt_the_recommendation(
    app, saved_note, mismatch,
):
    wid, source, _, notes = saved_note
    _, _, payload = recommended_note(app, saved_note)
    if mismatch == "note":
        replace_notes(app, source["id"], notes + [{**notes[0], "noteId": "identical-other-note"}])
        payload = payload.model_copy(update={"note_id": "identical-other-note"})
    elif mismatch == "material":
        clone = send(app, "POST", f"/api/workspaces/{wid}/source-materials", json={
            "type": "xhs_creator_profile", "name": "同文的另一份资料",
            "content": json.dumps({"notes": notes}, ensure_ascii=False),
        }).json()
        payload = payload.model_copy(update={"source_material_id": clone["id"]})
    else:
        payload = payload.model_copy(update={
            "source_material_id": None, "note_id": None, "manual_topic": notes[0]["title"],
        })
    with pytest.raises(ConflictError, match="不属于当前"):
        app.state.simulation_service.create(wid, payload)
    assert app.state.simulation_service.list(wid) == []


def test_historical_note_source_cannot_cross_accounts(app, saved_note):
    _, source, _, notes = saved_note
    other = create_workspace(app)["id"]
    with pytest.raises(NotFoundError):
        app.state.reader_selection_requests.create(other, ReaderSelectionRequest(
            request_key="wrong-account", source_material_id=source["id"],
            note_id=notes[0]["noteId"],
        ))
    with pytest.raises(NotFoundError):
        app.state.simulation_service.create(other, SimulationRunCreate(
            source_material_id=source["id"], note_id=notes[0]["noteId"],
        ))
    assert app.state.simulation_service.list(other) == []


@pytest.mark.parametrize("problem", ["missing", "duplicate"])
def test_missing_or_ambiguous_note_cannot_be_recommended_or_simulated(app, saved_note, problem):
    wid, source, _, notes = saved_note
    replace_notes(app, source["id"], [] if problem == "missing" else notes + notes)
    with pytest.raises(NotFoundError, match="不存在或来源不唯一"):
        app.state.reader_selection_requests.create(wid, ReaderSelectionRequest(
            request_key=problem, source_material_id=source["id"], note_id=notes[0]["noteId"],
        ))
    with pytest.raises(NotFoundError, match="不存在或来源不唯一"):
        app.state.simulation_service.create(wid, SimulationRunCreate(
            source_material_id=source["id"], note_id=notes[0]["noteId"],
        ))
    assert app.state.simulation_service.list(wid) == []


@pytest.mark.parametrize("fields", [
    {"sourceMaterialId": "source"}, {"noteId": "note"},
    {"sourceMaterialId": "source", "noteId": "note", "manualTopic": "标题"},
])
def test_saved_note_requires_a_complete_unique_target(app, fields):
    wid = create_workspace(app)["id"]
    with pytest.raises(SchemaError):
        ReaderSelectionRequest.model_validate({"requestKey": "invalid", **fields})
    with pytest.raises(ValidationError):
        app.state.simulation_service.create(wid, SimulationRunCreate.model_validate(fields))
    assert app.state.simulation_service.list(wid) == []


def test_request_replay_retains_snapshot_but_cannot_reuse_key_for_another_note(app, saved_note):
    wid, source, _, notes = saved_note
    request, selection, _ = recommended_note(app, saved_note)
    replace_notes(app, source["id"], [{**notes[0], "desc": "后续修改"},
                                      {**notes[0], "noteId": "another"}])
    replay = app.state.reader_selection_requests.create(wid, request)
    assert replay == selection
    with pytest.raises(ConflictError):
        app.state.reader_selection_requests.create(
            wid, request.model_copy(update={"note_id": "another"}),
        )
