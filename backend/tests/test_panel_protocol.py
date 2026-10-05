import hashlib
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError as SchemaError
from test_audience_simulation_workflow import collect
from test_creator_experience import topic
from test_reader_selection import fan, proposal, snapshot
from test_simulated_fans import seeded as seeded
from test_workspace_api import send

from app.errors import ConflictError, ValidationError
from app.models import ModelCallResponse, ModelOperation, PanelTask, SimulationRunCreate
from app.services.model_calls import PROMPT_SIMULATION_REACTION, ModelCallService
from app.services.panel_protocol import DISCUSSION_DISABLED_REASON
from app.services.reader_selection import prepare_reader_selection, selection_input_hash
from app.services.reader_selection_prompt import selection_prompt
from app.services.reader_selection_requests import ReaderSelectionRequest
from app.workflows.audience_simulation import RealAudienceSimulationModelProvider


def guided(**changes):
    return PanelTask.model_validate({
        "readingMode": "guided", "focusQuestions": ["第一步讲清楚了吗？🌱"], **changes,
    })


@pytest.mark.parametrize("fields", [
    {"protocolVersion": "panel/v2"}, {"readingMode": "unknown"},
    {"discussionEnabled": "false"}, {"discussionEnabled": 0},
    {"readingMode": "guided"}, {"focusQuestions": ["为什么"]},
    {"readingMode": "guided", "focusQuestions": [" "]},
    {"readingMode": "guided", "focusQuestions": [1]},
    {"readingMode": "guided", "focusQuestions": ["长" * 301]},
    {"readingMode": "guided", "focusQuestions": ["一", "二", "三"]},
    {"secretInstruction": "要求赞同"},
])
def test_task_contract_rejects_ambiguous_or_unbounded_parameters(fields):
    with pytest.raises(SchemaError):
        PanelTask.model_validate(fields)


def test_legacy_hash_request_identity_and_model_prompt_remain_unchanged(settings):
    inputs = prepare_reader_selection("w", snapshot(), [fan()])
    old_input = inputs.model_dump(by_alias=True, exclude={"panel_task"})
    old_hash = hashlib.sha256(json.dumps(
        old_input, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode()).hexdigest()
    assert selection_input_hash(inputs) == old_hash
    assert selection_input_hash(type(inputs).model_validate(old_input)) == old_hash
    request = ReaderSelectionRequest(request_key="same", manual_topic="旧标题")
    assert json.loads(request.identity()) == {
        "topicId": None, "draftId": None, "manualTopic": "旧标题", "desiredCount": 3,
    }
    system, user = selection_prompt(inputs)
    assert "panelTask" not in user
    built, _ = ModelCallService(settings)._build_prompt(
        ModelOperation.SIMULATION_REACTION, {"topic": inputs.target, "persona": {}},
    )
    assert built == PROMPT_SIMULATION_REACTION
    assert "panelTask" not in system


def test_task_is_deep_copied_and_all_task_fields_affect_selection_hash():
    task = guided()
    inputs = prepare_reader_selection("w", snapshot(), [fan()], panel_task=task)
    original = selection_input_hash(inputs)
    task.focus_questions.append("外部后来改动")
    assert len(inputs.panel_task.focus_questions) == 1
    for other in (PanelTask(), guided(discussionEnabled=False),
                  guided(focusQuestions=["例子能理解吗？"])):
        changed = prepare_reader_selection("w", snapshot(), [fan()], panel_task=other)
        assert selection_input_hash(changed) != original
        assert changed.candidates == inputs.candidates
    _, user = selection_prompt(inputs)
    assert json.loads(user)["panelTask"] == inputs.panel_task.model_dump(by_alias=True)


def recommendation(app, seeded, task=None):
    wid, _, _, fans = seeded
    target = topic(app, wid, "读者任务快照")
    request = ReaderSelectionRequest(request_key="panel-check", topic_id=target["id"],
                                     panel_task=task)
    saved = app.state.reader_selection_requests.create(wid, request)
    service = app.state.reader_selection_service
    claim = service.claim(wid, saved.id)
    saved = service.complete(wid, saved.id, claim.token, {
        "proposedReaders": [proposal(fans[0]["id"])],
    })
    payload = SimulationRunCreate(topic_id=target["id"], simulated_fan_ids=[fans[0]["id"]],
                                  reader_selection_id=saved.id,
                                  reader_selection_input_hash=saved.input_hash,
                                  panel_task=task.model_copy(deep=True) if task else None)
    return wid, target, saved, request, payload


def test_persisted_task_adoption_and_replay_never_silently_change_task(app, seeded):
    wid, target, saved, request, payload = recommendation(app, seeded, guided())
    assert app.state.reader_selection_requests.observe(wid, saved.id).freshness.status == "current"
    assert app.state.reader_selection_requests.create(wid, request).id == saved.id
    for task in (None, PanelTask(), guided(discussionEnabled=False),
                 guided(focusQuestions=["换一个重点问题"])):
        changed = request.model_copy(update={"panel_task": task})
        with pytest.raises(ConflictError, match="试读任务"):
            app.state.reader_selection_requests.create(wid, changed)
        with pytest.raises(ConflictError, match="试读任务"):
            app.state.simulation_service.create(
                wid, payload.model_copy(update={"panel_task": task}),
            )
    assert app.state.simulation_service.list(wid) == []
    run = app.state.simulation_service.create(wid, payload)
    before = deepcopy(run.input_snapshot)
    assert before["panelTask"] == guided().model_dump(by_alias=True)
    assert len(before["targetContentHash"]) == 64
    assert before["topic"]["updatedAt"]
    payload.panel_task.focus_questions[0] = "创建后修改参数"
    assert send(app, "PATCH", f"/api/topics/{target['id']}", json={
        "body": "后来人工改稿", "expectedUpdatedAt": target["updatedAt"],
    }).status_code == 200
    assert app.state.simulation_service.get(run.id).input_snapshot == before
    assert app.state.reader_selection_requests.observe(wid, saved.id).freshness.status == "stale"
    assert app.state.reader_selection_requests.create(wid, request).id == saved.id


def test_old_stored_request_and_hash_can_still_be_adopted(app, seeded):
    wid, _, saved, request, payload = recommendation(app, seeded)
    # Reproduce storage before this change, rather than only creating a new null-field record.
    raw = saved.input_snapshot.model_dump(by_alias=True, exclude={"panel_task"})
    with app.state.database.transaction() as c:
        c.execute("UPDATE reader_selections SET input_snapshot_json=? WHERE id=?",
                  (json.dumps(raw), saved.id))
    assert app.state.reader_selection_requests.create(wid, request).id == saved.id
    assert app.state.reader_selection_requests.observe(wid, saved.id).freshness.status == "current"
    run = app.state.simulation_service.create(wid, payload)
    assert "panelTask" not in run.input_snapshot
    assert "targetContentHash" not in run.input_snapshot
    with pytest.raises(ConflictError, match="试读任务"):
        app.state.simulation_service.create(
            wid, payload.model_copy(update={"panel_task": PanelTask()}),
        )


def test_new_protocol_requires_saved_readers_and_does_not_generate_them(app, seeded):
    wid, _, _, _ = seeded
    with pytest.raises(ValidationError, match="已保存"):
        app.state.simulation_service.create(wid, SimulationRunCreate(
            manual_topic="新选题", panel_task=PanelTask(),
        ))
    assert app.state.simulation_service.list(wid) == []


@pytest.mark.parametrize("enabled", [False, True])
def test_execution_and_replay_honor_frozen_task_without_leaking_recommendation(
    app, seeded, settings, enabled,
):
    wid, _, _, request, payload = recommendation(app, seeded, guided(discussionEnabled=enabled))
    payload.simulated_fan_ids = [fan["id"] for fan in seeded[3][:2]]
    payload.mode = "live"
    calls = []

    class Model:
        async def call_operation(self, operation, context):
            calls.append((operation, deepcopy(context)))
            if operation == ModelOperation.SIMULATION_REACTION:
                result = {"reaction": {"personaId": context["persona"]["id"],
                          "stance": "喜欢", "quote": "我理解了第一步", "action": "comment"}}
            elif operation == ModelOperation.SIMULATION_DEBATE:
                result = {"debateResponse": {"personaId": context["persona"]["id"],
                          "response": "我也这样理解",
                          "replyToId": context["otherReactions"][0]["messageId"]}}
            else:
                assert operation == ModelOperation.SIMULATION_SYNTHESIS
                result = {"synthesis": {"verdict": "第一步已经清楚"}}
            return ModelCallResponse(output=result, model_metadata={"model": "fake-panel"})

    app.state.simulation_workflow_service.live_provider = RealAudienceSimulationModelProvider(
        Model(),
    )
    run = app.state.simulation_service.create(wid, payload)
    collect(app, run.id, stop_after_node="parallel_initial_reactions")
    # Resume must use the frozen task, not a mutable request or current asset.
    request.panel_task.focus_questions[0] = "之后改变的问题"
    collect(app, run.id)
    completed = app.state.simulation_service.get(run.id)
    assert completed.status.value == "completed"
    assert len(completed.reaction_results) == 2
    assert len(completed.debate_results) == (2 if enabled else 0)
    assert len(calls) == (5 if enabled else 3)
    for operation, context in calls:
        assert context["topic"]["panelTask"]["focusQuestions"] == ["第一步讲清楚了吗？🌱"]
        assert "fitReason" not in str(context) and "contribution" not in str(context)
        system, _ = ModelCallService(settings)._build_prompt(operation, context)
        assert "受邀的定向试读" in system
        if operation == ModelOperation.SIMULATION_REACTION:
            assert "otherReactions" not in context
    coverage = calls[-1][1]["discussionCoverage"]
    assert coverage["missingDiscussionPersonaIds"] == []
    if not enabled:
        assert coverage["discussionEligiblePersonaIds"] == []
        assert coverage["discussionSilentPersonaIds"] == []
    collect(app, run.id)
    assert len(calls) == (5 if enabled else 3)
    response = send(app, "GET", f"/api/simulation-runs/{run.id}/events")
    if not enabled:
        assert DISCUSSION_DISABLED_REASON in response.text
