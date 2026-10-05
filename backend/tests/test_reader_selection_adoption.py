import json

import pytest
from test_audience_simulation_workflow import collect
from test_creator_experience import topic
from test_reader_selection import proposal
from test_simulated_fans import seeded as seeded
from test_workspace_api import create_workspace, send

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import ModelCallResponse, ModelOperation, SimulationRunCreate
from app.repositories.drafts import DraftRepository
from app.repositories.simulated_fans import SimulatedFanRepository
from app.services.common import utc_now
from app.services.reader_selection_requests import ReaderSelectionRequest
from app.services.reader_selections import ReaderSelectionCreate
from app.workflows.audience_simulation import RealAudienceSimulationModelProvider


@pytest.fixture
def recommended(app, seeded):
    wid, _, _, fans = seeded
    selected = topic(app, wid, "一次小练习")
    payload = ReaderSelectionRequest(request_key="click", topic_id=selected["id"])
    selection = app.state.reader_selection_requests.create(wid, payload)
    claim = app.state.reader_selection_service.claim(wid, selection.id)
    selection = app.state.reader_selection_service.complete(wid, selection.id, claim.token, {
        "proposedReaders": [proposal(fans[0]["id"], fitReason="推荐理由不得进入角色上下文XYZ")],
    })
    return wid, fans, selected, selection


def adopting(recommended, **overrides):
    _, fans, selected, selection = recommended
    return SimulationRunCreate.model_validate({
        "topicId": selected["id"], "simulatedFanIds": [fans[0]["id"]],
        "readerSelectionId": selection.id, "readerSelectionInputHash": selection.input_hash,
        **overrides,
    })


def edit_fan(app, fan, **changes):
    response = send(app, "PATCH", f"/api/simulated-fans/{fan['id']}", json={
        **fan["editable"], "expectedUpdatedAt": fan["updatedAt"], **changes,
    })
    assert response.status_code == 200
    return response.json()


@pytest.mark.parametrize(("change", "reason"), [
    ("body", "target_changed"), ("title", "target_changed"),
    ("positioning", "positioning_changed"), ("edit", "readers_changed"),
    ("unselected_edit", "readers_changed"), ("archive", "readers_changed"),
    ("new_reader", "readers_changed"),
])
def test_observation_is_read_only_and_adoption_rechecks_inputs(app, recommended, change, reason):
    wid, fans, selected, selection = recommended
    requests = app.state.reader_selection_requests
    assert requests.observe(wid, selection.id).freshness.status == "current"
    if change in {"body", "title"}:
        response = send(app, "PATCH", f"/api/topics/{selected['id']}", json={
            change: "后来调整的正文或标题", "expectedUpdatedAt": selected["updatedAt"],
        })
        assert response.status_code == 200
    elif change == "positioning":
        workspace = send(app, "GET", f"/api/workspaces/{wid}").json()
        assert send(app, "PATCH", f"/api/workspaces/{wid}", json={
            "accountPositioning": "改变定位", "expectedUpdatedAt": workspace["updatedAt"],
        }).status_code == 200
    elif change == "new_reader":
        original = fans[0]
        with app.state.database.transaction() as c:
            SimulatedFanRepository().create(c, wid, original["sourceAnalysisId"], "new-group",
                                            original["original"], original["editable"])
    else:
        fan = fans[1] if change == "unselected_edit" else fans[0]
        edit_fan(app, fan, **({"status": "archived"} if change == "archive"
                             else {"coreConcern": "先看实际时间成本"}))
    for _ in range(2):
        observed = requests.observe(wid, selection.id)
        assert observed.freshness.status == "stale" and reason in observed.freshness.reasons
        assert observed.freshness.current_input_hash != selection.input_hash
        assert observed.input_snapshot == selection.input_snapshot
        assert observed.result == selection.result and observed.status == "completed"
    with pytest.raises(ConflictError, match="依据已变化"):
        app.state.simulation_service.create(wid, adopting(recommended))
    assert app.state.simulation_service.list(wid) == []
    assert app.state.reader_selection_service.get(wid, selection.id) == selection
    # Deliberate manual continuation does not claim to use the stale recommendation.
    manual_id = fans[1]["id"] if change == "archive" else fans[0]["id"]
    manual = app.state.simulation_service.create(wid, SimulationRunCreate(
        topic_id=selected["id"], simulated_fan_ids=[manual_id],
    ))
    assert manual.input_snapshot["readerSelection"] == {
        "source": "manual", "actualFanIds": [manual_id],
    }


def test_unrelated_topic_fields_do_not_expire_recommendation(app, recommended):
    wid, _, selected, selection = recommended
    assert send(app, "PATCH", f"/api/topics/{selected['id']}", json={
        "pinned": True, "angle": "只给创作者看的角度",
        "expectedUpdatedAt": selected["updatedAt"],
    }).status_code == 200
    observed = app.state.reader_selection_requests.observe(wid, selection.id)
    assert observed.freshness.status == "current"
    app.state.simulation_service.create(wid, adopting(recommended))


def test_missing_source_and_legacy_records_remain_readable(app, recommended):
    wid, _, selected, selection = recommended
    service = app.state.reader_selection_service
    legacy = service.create(wid, ReaderSelectionCreate(
        request_key="legacy-internal", input_snapshot=selection.input_snapshot,
    ))
    assert app.state.reader_selection_requests.observe(wid, legacy.id).freshness.reasons == [
        "missing_source",
    ]
    claim = service.claim(wid, legacy.id)
    service.complete(wid, legacy.id, claim.token, {
        "proposedReaders": [reader.model_dump(by_alias=True)
                            for reader in selection.result.proposed_readers],
    })
    with pytest.raises(ConflictError, match="缺少来源"):
        app.state.simulation_service.create(wid, adopting(
            recommended, readerSelectionId=legacy.id, readerSelectionInputHash=legacy.input_hash,
        ))
    with app.state.database.transaction() as c:
        c.execute("DELETE FROM topics WHERE id=?", (selected["id"],))
    observed = app.state.reader_selection_requests.observe(wid, selection.id)
    assert observed.freshness.status == "unavailable"
    assert observed.freshness.reasons == ["source_unavailable"]
    assert observed.result == selection.result
    with pytest.raises(ConflictError):
        app.state.simulation_service.create(wid, adopting(recommended))
    assert service.get(wid, selection.id) == selection


def test_recommended_adjusted_and_history_snapshots_are_independent(app, recommended):
    wid, fans, _, selection = recommended
    service = app.state.simulation_service
    run = service.create(wid, adopting(recommended))
    summary = run.input_snapshot["readerSelection"]
    assert summary["source"] == "recommended"
    assert summary["readerSelectionId"] == selection.id
    assert summary["proposedReaders"][0]["fanId"] == fans[0]["id"]
    expected_name = next(
        c.name for c in selection.input_snapshot.candidates if c.id == fans[0]["id"]
    )
    assert summary["proposedReaders"][0]["name"] == expected_name
    # Recommended but not selected readers must retain their historical name too.
    unselected = service.create(wid, adopting(recommended, simulatedFanIds=[fans[1]["id"]]))
    unselected_summary = unselected.input_snapshot["readerSelection"]
    assert unselected_summary["proposedReaders"][0]["name"] == expected_name
    # Adjustment may add more readers than the requested recommendation count of three.
    adjusted_ids = [fan["id"] for fan in fans]
    adjusted = service.create(wid, adopting(recommended, simulatedFanIds=adjusted_ids))
    assert adjusted.input_snapshot["readerSelection"]["source"] == "adjusted"
    assert adjusted.input_snapshot["readerSelection"]["actualFanIds"] == adjusted_ids
    edit_fan(app, fans[0], name="后来改名")
    assert service.get(run.id).input_snapshot == run.input_snapshot
    assert service.get(adjusted.id).input_snapshot == adjusted.input_snapshot
    assert service.get(unselected.id).input_snapshot == unselected.input_snapshot
    assert app.state.reader_selection_service.get(wid, selection.id) == selection


@pytest.mark.parametrize("problem", ["target", "hash", "missing_hash", "missing_ids", "duplicate"])
def test_invalid_adoption_never_creates_a_run(app, recommended, problem):
    wid, fans, _, _ = recommended
    changes = {}
    if problem == "target":
        changes["topicId"] = topic(app, wid, "一次小练习")["id"]  # Same text, distinct asset.
    elif problem == "hash":
        changes["readerSelectionInputHash"] = "0" * 64
    elif problem == "missing_hash":
        changes["readerSelectionInputHash"] = None
    elif problem == "missing_ids":
        changes["simulatedFanIds"] = None
    else:
        changes["simulatedFanIds"] = [fans[0]["id"], fans[0]["id"]]
    with pytest.raises((ConflictError, ValidationError)):
        app.state.simulation_service.create(wid, adopting(recommended, **changes))
    assert app.state.simulation_service.list(wid) == []


def test_other_account_cannot_read_or_adopt_selection(app, recommended):
    _, _, _, selection = recommended
    other = create_workspace(app)["id"]
    with pytest.raises(NotFoundError):
        app.state.reader_selection_requests.observe(other, selection.id)
    with pytest.raises(NotFoundError):
        app.state.simulation_service.create(other, adopting(recommended))
    assert app.state.simulation_service.list(other) == []


@pytest.mark.parametrize("outcome", ["pending", "failed", "no_match", "partial"])
def test_only_completed_nonempty_proposals_can_be_adopted(app, recommended, outcome):
    wid, fans, selected, _ = recommended
    service = app.state.reader_selection_service
    selection = app.state.reader_selection_requests.create(wid, ReaderSelectionRequest(
        request_key=outcome, topic_id=selected["id"],
    ))
    if outcome != "pending":
        claim = service.claim(wid, selection.id)
        if outcome == "failed":
            selection = service.fail(wid, selection.id, claim.token)
        else:
            output = ({"proposedReaders": [], "unmatchedReason": "无匹配"}
                      if outcome == "no_match" else {
                          "proposedReaders": [proposal(fans[0]["id"]), proposal("unknown")],
                      })
            selection = service.complete(wid, selection.id, claim.token, output)
    payload = adopting(recommended, readerSelectionId=selection.id,
                       readerSelectionInputHash=selection.input_hash)
    if outcome == "partial":
        run = app.state.simulation_service.create(wid, payload)
        assert run.input_snapshot["readerSelection"]["validationWarnings"]
    else:
        with pytest.raises(ConflictError):
            app.state.simulation_service.create(wid, payload)
        assert app.state.simulation_service.list(wid) == []


def test_recommendation_reasons_never_enter_live_simulation_context(app, recommended):
    wid, _, _, _ = recommended
    run = app.state.simulation_service.create(wid, adopting(recommended, mode="live"))
    captured = []

    class Model:
        async def call_operation(self, operation, context):
            captured.append(context)
            assert "推荐理由不得进入角色上下文XYZ" not in json.dumps(context, ensure_ascii=False)
            assert "readerSelection" not in context
            if operation == ModelOperation.SIMULATION_REACTION:
                output = {"reaction": {"personaId": context["persona"]["id"],
                                       "stance": "无感", "action": "no_comment"}}
            else:
                assert operation == ModelOperation.SIMULATION_SYNTHESIS
                output = {"synthesis": {"verdict": "仅模拟参考"}}
            return ModelCallResponse(output=output, model_metadata={})

    workflow = app.state.simulation_workflow_service
    workflow.live_provider = RealAudienceSimulationModelProvider(Model())
    assert "readerSelection" not in workflow.initial_state_for_run(run.id)
    collect(app, run.id)
    assert len(captured) >= 2
    assert app.state.simulation_service.get(run.id).status.value == "completed"


def test_api_rechecks_after_observation_before_enqueue(app, recommended, monkeypatch):
    wid, fans, selected, selection = recommended
    enqueued = []

    async def enqueue(run_id):
        enqueued.append(run_id)
        return True

    monkeypatch.setattr(app.state.workflow_worker, "enqueue_simulation_run", enqueue)
    endpoint = f"/api/workspaces/{wid}/simulation-runs"
    observation = send(app, "GET", f"/api/workspaces/{wid}/reader-selections/{selection.id}")
    assert observation.json()["freshness"]["status"] == "current"
    payload = adopting(recommended).model_dump(by_alias=True)
    accepted = send(app, "POST", endpoint, json=payload)
    assert accepted.status_code == 201
    assert accepted.json()["inputSnapshot"]["readerSelection"]["source"] == "recommended"
    edit_fan(app, fans[0], coreConcern="读者已编辑")
    blocked = send(app, "POST", endpoint, json=payload)
    assert blocked.status_code == 409
    assert enqueued == [accepted.json()["id"]]
    manual = send(app, "POST", endpoint, json={
        "topicId": selected["id"], "simulatedFanIds": [fans[0]["id"]],
    })
    assert manual.status_code == 201 and len(enqueued) == 2
    reopened = send(app, "GET", f"/api/simulation-runs/{accepted.json()['id']}").json()
    assert reopened["inputSnapshot"] == accepted.json()["inputSnapshot"]


def test_draft_changes_are_checked_but_internal_fields_are_excluded(app, recommended):
    wid, fans, selected, _ = recommended
    with app.state.database.transaction() as c:
        draft = DraftRepository().create(
            c, workspace_id=wid, topic_id=selected["id"], kind="content_structure",
            source_analysis_run_id=None, source_workflow="manual", status="completed",
            generated_snapshot_json="{}", editable_content_json=json.dumps({
                "structure": {"outline": [{"sec": "开篇", "ct": "本次测试正文"}],
                              "reuse": "内部建议"},
            }), input_snapshot_json="{}", stage_errors_json="{}", model_metadata_json="{}",
            now=utc_now(), completed_at=utc_now(),
        )
    requests = app.state.reader_selection_requests
    service = app.state.reader_selection_service
    created = requests.create(wid, ReaderSelectionRequest(
        request_key="draft-recommendation", draft_id=draft["id"],
    ))
    claim = service.claim(wid, created.id)
    created = service.complete(wid, created.id, claim.token, {
        "proposedReaders": [proposal(fans[0]["id"])],
    })
    payload = SimulationRunCreate(draft_id=draft["id"], simulated_fan_ids=[fans[0]["id"]],
                                  reader_selection_id=created.id,
                                  reader_selection_input_hash=created.input_hash)
    first = app.state.simulation_service.create(wid, payload)
    with app.state.database.transaction() as c:
        content = json.loads(draft["editable_content_json"])
        content["structure"]["reuse"] = "只改内部策略"
        c.execute("UPDATE drafts SET editable_content_json=? WHERE id=?",
                  (json.dumps(content), draft["id"]))
    assert requests.observe(wid, created.id).freshness.status == "current"
    with app.state.database.transaction() as c:
        content["structure"]["outline"][0]["ct"] = "更新正文"
        c.execute("UPDATE drafts SET editable_content_json=? WHERE id=?",
                  (json.dumps(content), draft["id"]))
    assert requests.observe(wid, created.id).freshness.reasons == ["target_changed"]
    with pytest.raises(ConflictError):
        app.state.simulation_service.create(wid, payload)
    assert app.state.simulation_service.get(first.id).input_snapshot == first.input_snapshot


def test_hash_without_selection_is_not_silently_ignored(app, recommended):
    wid, _, _, _ = recommended
    with pytest.raises(ValidationError, match="指纹需要配合"):
        app.state.simulation_service.create(wid, adopting(recommended, readerSelectionId=None))
    assert app.state.simulation_service.list(wid) == []
