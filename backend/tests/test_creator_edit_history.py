import asyncio
import json

import pytest
from test_creator_experience import topic
from test_workspace_api import create_workspace, request, send

from app.main import create_app
from app.models import ModelCallResponse
from app.services.agent_conversations import RealAgentConversationModelProvider


@pytest.fixture
def canvas(app):
    wid = create_workspace(app)["id"]
    original = topic(app, wid, "原有标题")
    original = send(app, "PATCH", f"/api/topics/{original['id']}", json={
        "body": "第一段。\n\n原始正文🌱", "expectedUpdatedAt": original["updatedAt"],
    }).json()
    agent = next(a for a in send(app, "GET", f"/api/workspaces/{wid}/agents").json()
                 if a["agentId"] == "topic_draft_editor")
    conversation = send(app, "POST", f"/api/workspaces/{wid}/agent-conversations", json={
        "agentAssetId": agent["id"],
        "contextTarget": {"assetType": "topic", "assetId": original["id"]},
    }).json()
    return original, conversation


class Model:
    def __init__(self, outcome="applied"):
        self.calls = 0
        self.outcome = outcome

    async def call_operation(self, operation, context):
        self.calls += 1
        if self.outcome == "failed":
            raise ValueError("injected model failure")
        return ModelCallResponse(output={
            "reply": "建议改稿", "update": {"title": "建议标题", "body": "建议正文\n🌱"},
            "pendingSuggestions": [],
            "factCheck": {"safeToApply": self.outcome != "blocked", "supportedClaims": []},
        }, model_metadata={"canvasEditSnapshot": {"forged": True}})


async def post_and_wait(app, conversation):
    response = await request(app, "POST", f"/api/agent-conversations/{conversation['id']}/messages",
                             json={"content": "修改正文", "mode": "live",
                                   "clientMessageKey": "history-check"})
    assert response.status_code == 200
    tasks = list(app.state.agent_conversation_service._tasks.values())
    if tasks:
        await asyncio.gather(*tasks)


def test_canvas_receipt_survives_edit_restart_and_idempotent_replay(app, canvas, settings):
    original, conversation = canvas
    model = Model()
    app.state.agent_conversation_service.live_provider = RealAgentConversationModelProvider(model)
    asyncio.run(post_and_wait(app, conversation))
    url = f"/api/agent-conversations/{conversation['id']}"
    first = send(app, "GET", url).json()
    receipt = first["messages"][-1]["modelMetadata"]["canvasEditSnapshot"]
    saved = send(app, "GET", f"/api/topics/{original['id']}").json()
    edited = send(app, "PATCH", f"/api/topics/{original['id']}", json={
        "body": "我的后续手工修改", "expectedUpdatedAt": saved["updatedAt"],
    }).json()
    reopened = create_app(settings)  # Fresh services, same isolated SQLite file, no server.
    reopened.state.agent_conversation_service.live_provider = RealAgentConversationModelProvider(
        model,
    )
    asyncio.run(post_and_wait(reopened, conversation))
    later = send(reopened, "GET", url).json()
    assert model.calls == 1
    assert later["messages"] == first["messages"]
    assert later["messages"][-1]["modelMetadata"]["canvasEditSnapshot"] == receipt
    assert receipt["before"]["body"] == original["body"]
    assert receipt["after"]["body"] == "建议正文\n🌱"
    assert send(reopened, "GET", f"/api/topics/{original['id']}").json() == edited
    assert edited["generatedSnapshot"] == original["generatedSnapshot"]


@pytest.mark.parametrize("outcome", ["failed", "blocked"])
def test_canvas_failure_does_not_claim_an_applied_revision(app, canvas, outcome):
    original, conversation = canvas
    service = app.state.agent_conversation_service
    service.live_provider = RealAgentConversationModelProvider(Model(outcome))
    asyncio.run(post_and_wait(app, conversation))
    metadata = service.get(conversation["id"]).messages[-1].model_metadata
    assert "canvasEditSnapshot" not in metadata
    assert metadata.get("canvasApplyStatus") == (
        "needs_confirmation" if outcome == "blocked" else None
    )
    assert send(app, "GET", f"/api/topics/{original['id']}").json() == original


def test_canvas_topic_and_receipt_rollback_together(app, canvas, monkeypatch):
    original, conversation = canvas
    service = app.state.agent_conversation_service
    service.live_provider = RealAgentConversationModelProvider(Model())
    update_message = service.repository.update_message

    def fail_final_receipt(connection, **kwargs):
        if "canvasEditSnapshot" in json.loads(kwargs["model_metadata_json"]):
            assert connection.execute("SELECT body FROM topics WHERE id=?",
                                      (original["id"],)).fetchone()[0] == "建议正文\n🌱"
            raise RuntimeError("injected receipt storage failure")
        return update_message(connection, **kwargs)

    monkeypatch.setattr(service.repository, "update_message", fail_final_receipt)
    enqueue = service._enqueue_reply
    submitted = []

    def capture_task(**kwargs):
        task = enqueue(**kwargs)
        submitted.append(task)
        return task

    monkeypatch.setattr(service, "_enqueue_reply", capture_task)

    async def exercise():
        await request(app, "POST", f"/api/agent-conversations/{conversation['id']}/messages",
                      json={"content": "修改正文", "mode": "live",
                            "clientMessageKey": "storage-failure"})
        await asyncio.gather(*submitted)

    with pytest.raises(RuntimeError, match="receipt storage failure"):
        asyncio.run(exercise())
    assert send(app, "GET", f"/api/topics/{original['id']}").json() == original
    metadata = service.get(conversation["id"]).messages[-1].model_metadata
    assert "canvasEditSnapshot" not in metadata
    assert "canvasApplyStatus" not in metadata


def test_legacy_canvas_messages_remain_readable_without_backfill(app, canvas):
    _, conversation = canvas
    service = app.state.agent_conversation_service
    service.live_provider = RealAgentConversationModelProvider(Model())
    asyncio.run(post_and_wait(app, conversation))
    message = service.get(conversation["id"]).messages[-1]
    old_metadata = {k: v for k, v in message.model_metadata.items() if k != "canvasEditSnapshot"}
    with service.database.transaction() as connection:
        connection.execute("UPDATE agent_messages SET model_metadata_json=? WHERE id=?",
                           (json.dumps(old_metadata), message.id))
    response = send(app, "GET", f"/api/agent-conversations/{conversation['id']}")
    assert response.status_code == 200
    assert response.json()["messages"][-1]["modelMetadata"] == old_metadata


def test_canvas_cannot_create_history_for_another_accounts_topic(app, canvas):
    original, _ = canvas
    wid = create_workspace(app)["id"]
    agent = next(a for a in send(app, "GET", f"/api/workspaces/{wid}/agents").json()
                 if a["agentId"] == "topic_draft_editor")
    response = send(app, "POST", f"/api/workspaces/{wid}/agent-conversations", json={
        "agentAssetId": agent["id"],
        "contextTarget": {"assetType": "topic", "assetId": original["id"]},
    })
    assert response.status_code == 422
    assert send(app, "GET", f"/api/workspaces/{wid}/agent-conversations").json() == []
    assert send(app, "GET", f"/api/topics/{original['id']}").json() == original
