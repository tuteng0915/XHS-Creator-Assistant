from copy import deepcopy

import pytest
from test_audience_simulation_workflow import collect
from test_panel_retests import case as case
from test_simulated_fans import seeded as seeded
from test_workspace_api import create_workspace, send

from app.errors import ValidationError
from app.models import ModelCallResponse, ModelOperation, SimulationRunCreate
from app.services.panel_comparison import compare_panel_runs
from app.workflows.audience_simulation import RealAudienceSimulationModelProvider


def pair(app, case):
    wid, parent, _, payload = case
    child = app.state.simulation_service.create_retest(wid, parent.id, payload)
    collect(app, child.id)
    return parent, app.state.simulation_service.get(child.id)


def test_comparison_is_read_only_and_uses_ids_not_result_order(app, case):
    parent, child = pair(app, case)
    child.reaction_results.reverse()
    first_id = parent.persona_definitions[0]["id"]
    reaction = next(r for r in child.reaction_results if r["personaId"] == first_id)
    reaction["understanding"] = "新版理解"
    before = deepcopy((parent.model_dump(), child.model_dump()))
    result = compare_panel_runs(parent, child)
    assert result["readers"][0]["after"]["understanding"] == "新版理解"
    assert result["readers"][0]["id"] == first_id
    assert result["before"]["body"] != result["after"]["body"]
    assert result["before"]["recordedModels"] == []  # no invented model for demo/old records
    assert before == (parent.model_dump(), child.model_dump())
    url = f"/api/workspaces/{child.workspace_id}/simulation-runs/{child.id}/comparison"
    saved_before = app.state.simulation_service.get(child.id)
    assert send(app, "GET", url).status_code == 200
    assert app.state.simulation_service.get(child.id) == saved_before
    other = create_workspace(app)["id"]
    assert send(app, "GET", url.replace(child.workspace_id, other)).status_code == 404


@pytest.mark.parametrize("action", ["comment", "no_comment", "skip"])
def test_silence_and_empty_concerns_do_not_become_resolved(app, case, action):
    parent, child = pair(app, case)
    parent.reaction_results[0]["concerns"] = ["第一步不清楚"]
    child.reaction_results[0].update(action=action, quote="公开文字", concerns=[])
    side = compare_panel_runs(parent, child)["readers"][0]
    assert side["after"]["initialStatus"] == action
    assert side["after"]["quote"] == ("公开文字" if action == "comment" else "")
    assert side["before"]["concerns"] == ["第一步不清楚"]
    assert side["after"]["concerns"] == []
    assert "resolved" not in side
    assert side["after"]["replyStatus"] == "disabled"


def test_failed_missing_and_partial_results_remain_distinct(app, case):
    parent, child = pair(app, case)
    child.status = "failed"
    child.reaction_results = []
    pid = parent.persona_definitions[0]["id"]
    child.stage_errors[f"initial_reactions.{pid}"] = "request failed"
    readers = compare_panel_runs(parent, child)["readers"]
    assert readers[0]["after"]["initialStatus"] == "failed"
    assert readers[1]["after"]["initialStatus"] == "missing"


@pytest.mark.parametrize("case", [True], indirect=True)
def test_reply_silence_failure_and_missing_are_not_disabled(app, case):
    parent, child = pair(app, case)
    child.debate_results[0].update(response="", text="")
    child.debate_results.pop()
    pid = parent.persona_definitions[1]["id"]
    result = compare_panel_runs(parent, child)
    assert result["readers"][0]["after"]["replyStatus"] == "silent"
    assert result["readers"][1]["after"]["replyStatus"] == "not_recorded"
    child.stage_errors[f"debate_responses.{pid}"] = "failed"
    assert compare_panel_runs(parent, child)["readers"][1]["after"]["replyStatus"] == "failed"


@pytest.mark.parametrize("change", [
    "parent", "task", "personas", "content", "duplicate", "outsider", "conflict", "running",
    "malformed", "malformed_list", "input_workspace", "positioning",
])
def test_incompatible_pair_is_rejected(app, case, change):
    parent, child = pair(app, case)
    if change == "parent":
        child.parent_simulation_id = "other"
    elif change == "task":
        child.input_snapshot["panelTask"]["discussionEnabled"] = True
    elif change == "personas":
        child.persona_definitions[0]["name"] = "changed"
    elif change == "content":
        child.input_snapshot["topic"]["body"] = "changed"
    elif change == "duplicate":
        child.reaction_results.append(child.reaction_results[0])
    elif change == "outsider":
        child.reaction_results[0]["personaId"] = "outside"
    elif change == "conflict":
        child.stage_errors[f"initial_reactions.{child.reaction_results[0]['personaId']}"] = "error"
    elif change == "malformed":
        child.reaction_results[0]["understanding"] = {"text": "wrong type"}
    elif change == "malformed_list":
        child.reaction_results[0]["concerns"] = [123]
    elif change == "input_workspace":
        child.input_snapshot["workspaceId"] = "other"
    elif change == "positioning":
        child.input_snapshot["accountPositioning"] = "changed"
    else:
        child.status = "running"
    with pytest.raises(ValidationError):
        compare_panel_runs(parent, child)


def test_actual_response_metadata_survives_workflow_resume_without_secrets(app, case):
    wid, parent, target, _ = case

    class Model:
        async def call_operation(self, operation, context):
            if operation == ModelOperation.SIMULATION_REACTION:
                output = {"reaction": {"personaId": context["persona"]["id"],
                                       "stance": "理解", "action": "no_comment"}}
            else:
                output = {"synthesis": {"verdict": "可以尝试"}}
            return ModelCallResponse(output=output, model_metadata={
                "provider": "test-provider", "model": "test-model", "systemPromptHash": "abc",
                "usage": {"total_tokens": 10}, "apiKey": "must-not-save",
                "baseUrl": "must-not-save", "rawPrompt": "must-not-save",
            })

    provider = RealAudienceSimulationModelProvider(Model())
    app.state.simulation_workflow_service.live_provider = provider
    run = app.state.simulation_service.create(wid, SimulationRunCreate(
        topic_id=target["id"], simulated_fan_ids=parent.input_snapshot["simulatedFanIds"],
        panel_task=parent.input_snapshot["panelTask"], mode="live",
    ))
    collect(app, run.id, stop_after_node="parallel_initial_reactions")
    intermediate = app.state.simulation_service.get(run.id)
    assert len(intermediate.model_metadata["responseCalls"]) == 2
    collect(app, run.id)
    result = app.state.simulation_service.get(run.id)
    assert result.status == "completed"
    assert result.model_metadata["engine"] == "langgraph"
    assert len(result.model_metadata["responseCalls"]) == 3
    assert "must-not-save" not in str(result.model_metadata)
    assert result.model_metadata["responseCalls"][0]["model"] == "test-model"
    collect(app, run.id)
    assert app.state.simulation_service.get(run.id).model_metadata == result.model_metadata
