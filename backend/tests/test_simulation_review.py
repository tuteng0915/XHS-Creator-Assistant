"""A shared panel keeps account review, published-note review and editing distinct."""
import asyncio
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError as SchemaError
from test_creator_experience import profile
from test_simulated_fans import adopt_candidates, analyze
from test_workspace_api import create_workspace, send

from app.models import ModelCallResponse, ModelOperation, PanelTask, SimulationRunCreate
from app.services.model_calls import ModelCallService
from app.services.panel_protocol import panel_prompt_context
from app.services.simulation_review import demo_review, simulation_category, validated_review
from app.workflows.audience_simulation import FakeAudienceSimulationModelProvider


def review_run(app, category):
    wid = create_workspace(app)["id"]
    source = profile(app, wid)
    analysis = analyze(app, wid, source["id"])
    readers = adopt_candidates(app, wid, analysis, ["0"])
    target = ({"account_profile_id": source["id"]} if category == "account" else
              {"source_material_id": source["id"], "note_id": "0"}
              if category == "published_note" else {"manual_topic": "下篇创作的选题"})
    run = app.state.simulation_service.create(wid, SimulationRunCreate(
        **target, simulated_fan_ids=[readers[0]["id"]],
        panel_task=PanelTask(discussion_enabled=False), mode="demo",
    ))
    return wid, source, run


@pytest.mark.parametrize("category", ["account", "published_note", "creation"])
def test_demo_reviews_have_category_specific_results_and_never_auto_adopt(app, category):
    wid, source, run = review_run(app, category)
    before = send(app, "GET", f"/api/source-materials/{source['id']}").json()
    asyncio.run(app.state.simulation_workflow_service.collect_events(run.id))
    result = app.state.simulation_service.get(run.id)
    assert result.status == "completed", result.stage_errors
    assert send(app, "GET", f"/api/workspaces/{wid}/topics").json() == []
    assert send(app, "GET", f"/api/source-materials/{source['id']}").json() == before
    if category == "creation":
        assert "review" not in result.synthesis
        assert "editorFeedback" in result.synthesis
    else:
        assert "editorFeedback" not in result.synthesis
        assert result.synthesis["contentAdjustments"] == []
        review = result.synthesis["review"]
        assert review["topicIdeas"][0]["id"] == "idea-1"
        assert "演示" in review["summary"]
        expected = "持续内容需求" if category == "account" else "不改写原笔记"
        assert expected in review["summary"]


@pytest.mark.parametrize("category", ["account", "published_note"])
def test_explicit_adoption_is_idempotent_scoped_and_preserves_edits(app, category):
    wid, source, run = review_run(app, category)
    asyncio.run(app.state.simulation_workflow_service.collect_events(run.id))
    endpoint = f"/api/workspaces/{wid}/simulation-runs/{run.id}/topic-ideas/idea-1/adopt"
    before = send(app, "GET", f"/api/source-materials/{source['id']}").json()
    with app.state.database.read() as connection:
        analysis_count = connection.execute("SELECT count(*) FROM analysis_runs").fetchone()[0]
    response = send(app, "POST", endpoint)
    assert response.status_code == 200, response.text
    adopted = response.json()
    assert adopted["sourceWorkflow"] == "manual"
    assert adopted["sourceAnalysisRunId"] is None
    assert adopted["body"] == ""
    assert adopted["generatedSnapshot"]["sourceSimulationId"] == run.id
    assert adopted["generatedSnapshot"]["sourceTopicIdeaId"] == "idea-1"
    assert adopted["generatedSnapshot"]["sourceSimulationCategory"] == category
    edited = send(app, "PATCH", f"/api/topics/{adopted['id']}", json={
        "title": "作者改过的标题", "body": "自己开始创作的新内容",
        "expectedUpdatedAt": adopted["updatedAt"],
    }).json()
    assert send(app, "POST", endpoint).json() == edited
    assert len(send(app, "GET", f"/api/workspaces/{wid}/topics").json()) == 1
    assert send(app, "GET", f"/api/source-materials/{source['id']}").json() == before
    with app.state.database.read() as connection:
        saved_count = connection.execute("SELECT count(*) FROM analysis_runs").fetchone()[0]
        assert saved_count == analysis_count
    other = create_workspace(app)["id"]
    assert send(app, "POST", endpoint.replace(wid, other)).status_code == 404
    assert send(app, "GET", f"/api/workspaces/{other}/topics").json() == []
    assert send(app, "POST", endpoint.replace("idea-1", "invented")).status_code == 404


def test_unfinished_review_and_creation_cannot_adopt_topic_ideas(app):
    wid, _, run = review_run(app, "account")
    assert send(app, "POST", (
        f"/api/workspaces/{wid}/simulation-runs/{run.id}/topic-ideas/idea-1/adopt"
    )).status_code == 409
    wid, _, run = review_run(app, "creation")
    assert send(app, "POST", (
        f"/api/workspaces/{wid}/simulation-runs/{run.id}/topic-ideas/idea-1/adopt"
    )).status_code == 422


def test_summary_before_recovery_cannot_be_adopted_as_new_review(app):
    wid, _, run = review_run(app, "account")
    asyncio.run(app.state.simulation_workflow_service.collect_events(run.id))
    with app.state.database.transaction() as connection:
        connection.execute("UPDATE simulation_runs SET model_metadata_json=? WHERE id=?",
                           (json.dumps({"recovery": {"summaryStale": True}}), run.id))
    response = send(app, "POST", (
        f"/api/workspaces/{wid}/simulation-runs/{run.id}/topic-ideas/idea-1/adopt"
    ))
    assert response.status_code == 409
    assert "先更新汇总" in response.text
    assert send(app, "GET", f"/api/workspaces/{wid}/topics").json() == []


@pytest.mark.parametrize("category", ["account", "published_note"])
def test_review_prompt_and_model_call_do_not_use_editor_feedback_or_extra_fact_check(
    settings, category,
):
    service = ModelCallService(settings)
    target = {"simulationCategory": category, "title": "样本", "body": "正文样本",
              "panelTask": PanelTask().model_dump(mode="json", by_alias=True)}
    context = {"topic": target, "personas": [], "reactions": [], "debateResponses": []}
    system, user = service._build_prompt(ModelOperation.SIMULATION_SYNTHESIS, context)
    assert '"review"' in system
    assert '"editorFeedback":' not in system
    assert "样本" in user
    assert "nextTimeSuggestions" in system
    result = ModelCallResponse(output={"synthesis": {"review": demo_review(target)}},
                               model_metadata={"model": "test-model"})
    checker = AsyncMock(side_effect=AssertionError("Review must not call the manuscript checker"))
    actual = asyncio.run(service.review_panel_output(
        ModelOperation.SIMULATION_SYNTHESIS, context, result, call_once=checker,
    ))
    assert actual == result
    checker.assert_not_called()
    assert service._output_budget(ModelOperation.SIMULATION_SYNTHESIS, context) == 2400


def test_prompt_purposes_apply_even_to_legacy_targets_without_panel_task():
    assert "长期" not in panel_prompt_context({"targetType": "topic"})
    assert "账号级" in panel_prompt_context({"targetType": "account"})
    assert "下一篇" in panel_prompt_context({"targetType": "note"})
    assert simulation_category({"targetType": "note"}) == "published_note"
    assert simulation_category({"targetType": "topic"}) == "creation"


def test_account_reaction_prompt_reads_multiple_notes_as_an_account(settings):
    service = ModelCallService(settings)
    system, _ = service._build_prompt(ModelOperation.SIMULATION_REACTION, {
        "topic": {"simulationCategory": "account", "previewLevel": "account",
                  "body": "笔记1\n内容1\n笔记2\n内容2", "panelTask": PanelTask().model_dump()},
        "persona": {"id": "reader", "name": "读者", "profile": "希望读有用的内容"},
    })
    assert "不要把所有样本当成一篇长文" in system
    assert "持续关注" in system
    assert "understanding 概括本篇" not in system


def test_review_validator_assigns_own_ids_and_enforces_small_real_candidates():
    raw = demo_review({"simulationCategory": "account"})
    raw["topicIdeas"][0]["id"] = "model-guessed-id"
    result = validated_review(raw)
    assert result["topicIdeas"][0]["id"] == "idea-1"
    assert result == validated_review(raw)
    too_many = deepcopy(raw)
    too_many["topicIdeas"] *= 6
    with pytest.raises(SchemaError):
        validated_review(too_many)
    with pytest.raises(SchemaError):
        validated_review({"readerNeeds": []})
    with pytest.raises(ValueError):
        validated_review({"summary": " "})


def test_invalid_review_fails_synthesis_without_fabricating_editor_advice(app):
    class MissingReview(FakeAudienceSimulationModelProvider):
        async def synthesis(self, **_kwargs):
            return {"synthesis": {"verdict": "错误的单篇改稿结果", "editorFeedback": [],
                                  "contentAdjustments": ["直接替换原文"]}}

    _, _, run = review_run(app, "published_note")
    app.state.simulation_workflow_service.fake_provider = MissingReview()
    asyncio.run(app.state.simulation_workflow_service.collect_events(run.id))
    result = app.state.simulation_service.get(run.id)
    assert result.status == "partially_completed"
    assert "synthesis" in result.stage_errors
    assert result.synthesis == {}
