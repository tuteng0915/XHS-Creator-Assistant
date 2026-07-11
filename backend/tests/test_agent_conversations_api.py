from fastapi import FastAPI
from test_workspace_api import create_workspace, send

from app.services.agent_conversations import AgentConversationReply


def test_agent_conversation_uses_broad_workspace_context(app: FastAPI) -> None:
    workspace = create_workspace(app)
    send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials",
        json={
            "type": "comments",
            "name": "评论样本",
            "content": "这个账号定位可以更具体一点。",
        },
    )
    agents = send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
    agent = next(item for item in agents if item["agentId"] == "creator_material_curator")

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/agent-conversations",
        json={"agentAssetId": agent["id"], "title": "整理账号定位"},
    )
    assert created.status_code == 201
    conversation = created.json()
    assert conversation["messages"] == []

    replied = send(
        app,
        "POST",
        f"/api/agent-conversations/{conversation['id']}/messages",
        json={"content": "帮我看看账号定位要不要修改"},
    )
    assert replied.status_code == 200
    body = replied.json()
    assert len(body["messages"]) == 2
    user_message, assistant_message = body["messages"]
    assert user_message["role"] == "user"
    assert assistant_message["role"] == "assistant"
    assert "Creator Material Curator" in assistant_message["content"]
    assert assistant_message["contextPack"]["mode"] == "workspace_pack"
    assert assistant_message["contextPack"]["scope"] == "broad"
    item_keys = {item["key"] for item in assistant_message["contextPack"]["items"]}
    assert {
        "account_profile",
        "source_materials_overview",
        "analysis_history_overview",
        "topic_library_overview",
        "draft_history_overview",
        "simulation_history_overview",
    }.issubset(item_keys)
    assert assistant_message["assetRefs"]
    assert assistant_message["proposedActions"][0]["type"] == "workspace.update_profile"
    assert assistant_message["modelMetadata"]["operation"] == "agent_chat"

    loaded = send(app, "GET", f"/api/agent-conversations/{conversation['id']}")
    assert loaded.status_code == 200
    assert len(loaded.json()["messages"]) == 2


def test_live_agent_conversation_uses_injected_model_provider(app: FastAPI) -> None:
    class StubProvider:
        def __init__(self) -> None:
            self.seen_context_pack = None
            self.seen_messages = None

        async def reply(self, *, agent, user_content, context_pack, messages):
            self.seen_context_pack = context_pack
            self.seen_messages = messages
            return AgentConversationReply(
                reply=f"模型回复：{user_content}",
                proposed_actions=[
                    {
                        "type": "topic.create_or_update",
                        "status": "requires_confirmation",
                        "description": "建议沉淀一个选题。",
                    }
                ],
                model_metadata={
                    "provider": "stub",
                    "model": "test-model",
                    "operation": "agent_chat",
                },
            )

    workspace = create_workspace(app)
    agents = send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
    agent = next(item for item in agents if item["agentId"] == "creator_material_curator")
    conversation = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/agent-conversations",
        json={"agentAssetId": agent["id"]},
    ).json()

    provider = StubProvider()
    app.state.agent_conversation_service.live_provider = provider
    replied = send(
        app,
        "POST",
        f"/api/agent-conversations/{conversation['id']}/messages",
        json={"content": "帮我做一个新选题", "mode": "live"},
    )

    assert replied.status_code == 200
    assistant_message = replied.json()["messages"][1]
    assert assistant_message["content"] == "模型回复：帮我做一个新选题"
    assert assistant_message["modelMetadata"]["provider"] == "stub"
    assert assistant_message["proposedActions"][0]["type"] == "topic.create_or_update"
    assert provider.seen_context_pack["mode"] == "workspace_pack"
    assert provider.seen_messages[0]["role"] == "user"
