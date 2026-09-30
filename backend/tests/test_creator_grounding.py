import asyncio
from copy import deepcopy

import pytest
from pydantic import ValidationError as PydanticValidationError
from test_analysis_topics_api import create_text_material
from test_workspace_api import create_workspace, request, send

from app.errors import ValidationError
from app.models import AnalysisRunStatus, AnalysisStageUpdate, ModelCallResponse
from app.services.agent_conversations import RealAgentConversationModelProvider
from app.services.creator_grounding import validate_creator_edit
from app.workflows.account_diagnosis import TopicsStageResult


def output():
    return {
        "reply": "已调整", "update": {"title": "申请复盘", "body": "我整理了申请材料。"},
        "pendingSuggestions": [],
        "factCheck": {"safeToApply": True, "supportedClaims": [{
            "text": "我整理了申请材料。", "sourceId": "original", "sourceQuote": "整理了申请材料",
        }]},
    }


def test_checks_exact_sources_not_generated_background():
    sources = [{"id": "original", "text": "昨天我整理了申请材料。"}]
    assert validate_creator_edit(output(), sources)["update"]["body"] == "我整理了申请材料。"
    for changes in [
        {"sourceId": "generated-analysis"}, {"sourceQuote": "我和导师谈话"},
        {"sourceQuote": "  "}, {"text": "我去了后台"},
    ]:
        value = output()
        value["factCheck"]["supportedClaims"][0].update(changes)
        with pytest.raises(ValidationError):
            validate_creator_edit(value, sources)


@pytest.mark.parametrize("change", ["missing_review", "unsafe", "suggestion_in_body", "bad_type"])
def test_unchecked_edits_fail_closed(change):
    value = output()
    if change == "missing_review":
        del value["factCheck"]
    elif change == "unsafe":
        value["factCheck"]["safeToApply"] = False
    elif change == "bad_type":
        value["factCheck"]["safeToApply"] = "false"
    else:
        value["pendingSuggestions"] = [value["update"]["body"]]
    with pytest.raises((ValidationError, PydanticValidationError)):
        validate_creator_edit(value, [{"id": "original", "text": "我整理了申请材料。"}])


def test_discussion_and_safe_general_edit_keep_suggestions_separate():
    value = output()
    value["update"] = {"title": "如何做选择", "body": "先列出可以承担的成本。"}
    value["factCheck"]["supportedClaims"] = []
    value["pendingSuggestions"] = ["请确认是否有放弃保研的经历？"]
    assert validate_creator_edit(value, [])["pendingSuggestions"] == value["pendingSuggestions"]
    value["update"] = None
    value["factCheck"]["safeToApply"] = False
    assert validate_creator_edit(value, [])["update"] is None


@pytest.mark.parametrize("valid", [True, False])
def test_canvas_sources_and_blocked_edits_are_persisted(app, valid):
    wid = create_workspace(app)["id"]
    original = create_text_material(app, wid, "historical_posts", "昨天我整理了申请材料。")
    comments = create_text_material(app, wid, "comments", "想了解材料准备")
    run = send(app, "POST", f"/api/workspaces/{wid}/analysis-runs", json={
        "workflowType": "account_diagnosis", "historicalPostsMaterialId": original["id"],
        "mode": "demo", "commentsMaterialId": comments["id"],
    }).json()
    pending = ["请确认是否有后台交流的经历？"]
    generated = TopicsStageResult.model_validate({"topics": [{
        "title": "如何做选择", "pendingSuggestions": pending,
    }]}).model_dump(mode="json")
    app.state.analysis_service.update_stage(run["id"], "topics", AnalysisStageUpdate(
        status=AnalysisRunStatus.COMPLETED, result=generated,
    ))
    selected = send(app, "GET", f"/api/workspaces/{wid}/topics").json()[0]
    assert selected["generatedSnapshot"]["pendingSuggestions"] == pending
    agents = send(app, "GET", f"/api/workspaces/{wid}/agents").json()
    agent = next(a for a in agents if a["agentId"] == "topic_draft_editor")
    conversation = send(app, "POST", f"/api/workspaces/{wid}/agent-conversations", json={
        "agentAssetId": agent["id"],
        "contextTarget": {"assetType": "topic", "assetId": selected["id"]},
    }).json()

    class Model:
        async def call_operation(self, operation, context):
            assert context["factSources"][0] == {
                "id": "analysis-original-posts", "text": "昨天我整理了申请材料。",
            }
            assert context["factSources"][-1]["text"] == "帮我改写"
            assert context["topic"]["pendingSuggestions"] == pending
            assert "accountContext" in context  # Broad perspective is retained, not evidence.
            value = deepcopy(output())
            value["pendingSuggestions"] = pending
            claim = value["factCheck"]["supportedClaims"][0]
            claim["sourceId"] = "analysis-original-posts"
            if not valid:
                claim["sourceQuote"] = "后台交流"
            return ModelCallResponse(output=value, model_metadata={"model": "test"})

    service = app.state.agent_conversation_service
    service.live_provider = RealAgentConversationModelProvider(Model())

    async def exercise():
        response = await request(
            app, "POST", f"/api/agent-conversations/{conversation['id']}/messages",
            json={"content": "帮我改写", "mode": "live"},
        )
        assert response.status_code == 200
        await asyncio.gather(*list(service._tasks.values()))

    asyncio.run(exercise())
    stored = app.state.topic_service.get(selected["id"])
    assert stored.body == ("我整理了申请材料。" if valid else "")
    history = service.get(conversation["id"])
    metadata = history.messages[-1].model_metadata
    assert metadata["canvasApplyStatus"] == ("applied" if valid else "needs_confirmation")
    assert metadata["pendingSuggestions"] == pending
    sources = history.messages[-1].context_pack["creatorFactSources"]
    assert sources[0]["text"] == "昨天我整理了申请材料。"
    if not valid:
        assert metadata["suggestedCanvasUpdate"]["body"] == "我整理了申请材料。"
        assert "未通过事实核验" in history.messages[-1].content
