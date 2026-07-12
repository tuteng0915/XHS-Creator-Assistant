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
        "input_assets_overview",
        "analysis_history_overview",
        "topic_library_overview",
        "draft_history_overview",
        "simulation_history_overview",
        "capability_catalog",
    }.issubset(item_keys)
    catalog = next(
        item for item in assistant_message["contextPack"]["items"]
        if item["key"] == "capability_catalog"
    )
    assert any(
        skill["skillId"] == "analysis.profile_from_history"
        for skill in catalog["data"]["skills"]
    )
    assert any(
        agent_item["agentId"] == "creator_material_curator"
        for agent_item in catalog["data"]["agents"]
    )
    assert any(
        workflow["workflowId"] == "account_diagnosis"
        for workflow in catalog["data"]["workflows"]
    )
    assert assistant_message["assetRefs"]
    assert assistant_message["proposedActions"][0]["type"] == "workspace.update_profile"
    assert assistant_message["modelMetadata"]["operation"] == "agent_chat"

    proposals = send(
        app,
        "GET",
        f"/api/agent-conversations/{conversation['id']}/asset-proposals",
    )
    assert proposals.status_code == 200
    proposal = proposals.json()[0]
    assert proposal["actionType"] == "workspace.update_profile"
    assert proposal["status"] == "pending"

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


def test_asset_proposal_apply_creates_topic(app: FastAPI) -> None:
    workspace = create_workspace(app)
    agents = send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
    agent = next(item for item in agents if item["agentId"] == "creator_material_curator")
    conversation = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/agent-conversations",
        json={"agentAssetId": agent["id"]},
    ).json()

    replied = send(
        app,
        "POST",
        f"/api/agent-conversations/{conversation['id']}/messages",
        json={"content": "帮我新增一个选题：AI短剧激励计划"},
    )
    assert replied.status_code == 200
    proposals = send(
        app,
        "GET",
        f"/api/agent-conversations/{conversation['id']}/asset-proposals",
    ).json()
    topic_proposal = next(
        proposal for proposal in proposals
        if proposal["actionType"] == "topic.create_or_update"
    )

    applied = send(
        app,
        "POST",
        f"/api/asset-proposals/{topic_proposal['id']}/apply",
    )

    assert applied.status_code == 200
    body = applied.json()
    assert body["status"] == "applied"
    assert body["result"]["assetType"] == "topic"
    topics = send(app, "GET", f"/api/workspaces/{workspace['id']}/topics").json()
    assert topics[0]["title"] == "帮我新增一个选题：AI短剧激励计划"


def test_live_agent_conversation_failure_is_saved_as_assistant_message(
    app: FastAPI,
) -> None:
    class FailingProvider:
        async def reply(self, *, agent, user_content, context_pack, messages):
            raise RuntimeError("provider unavailable")

    workspace = create_workspace(app)
    agents = send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
    agent = next(item for item in agents if item["agentId"] == "creator_material_curator")
    conversation = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/agent-conversations",
        json={"agentAssetId": agent["id"]},
    ).json()
    app.state.agent_conversation_service.live_provider = FailingProvider()

    replied = send(
        app,
        "POST",
        f"/api/agent-conversations/{conversation['id']}/messages",
        json={"content": "帮我写一个 skill", "mode": "live"},
    )

    assert replied.status_code == 200
    messages = replied.json()["messages"]
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert "模型调用失败" in messages[1]["content"]
    assert messages[1]["modelMetadata"]["status"] == "failed"


def test_asset_proposal_apply_creates_generated_skill(app: FastAPI) -> None:
    class SkillProposalProvider:
        async def reply(self, *, agent, user_content, context_pack, messages):
            return AgentConversationReply(
                reply="建议创建一个视频评分 skill。",
                proposed_actions=[
                    {
                        "type": "skill.propose_definition",
                        "status": "requires_confirmation",
                        "description": "创建视频评分 skill。",
                        "payload": {
                            "definition": {
                                "skillId": "analysis.generated_video_score",
                                "displayName": "Generated Video Score",
                                "category": "analysis",
                                "purpose": "Score AIGC video creator quality.",
                                "requiredInputs": ["video_creator_samples"],
                                "artifactEffect": "AnalysisRun.stageResults.video_score",
                                "failureMode": "partial_allowed",
                                "implementationRefs": ["proposal.generated"],
                            }
                        },
                    }
                ],
                model_metadata={"provider": "stub", "operation": "agent_chat"},
            )

    workspace = create_workspace(app)
    agents = send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
    agent = next(item for item in agents if item["agentId"] == "skill_maker")
    conversation = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/agent-conversations",
        json={"agentAssetId": agent["id"]},
    ).json()
    app.state.agent_conversation_service.live_provider = SkillProposalProvider()

    send(
        app,
        "POST",
        f"/api/agent-conversations/{conversation['id']}/messages",
        json={"content": "做一个视频评分 skill", "mode": "live"},
    )
    proposal = send(
        app,
        "GET",
        f"/api/agent-conversations/{conversation['id']}/asset-proposals",
    ).json()[0]

    applied = send(app, "POST", f"/api/asset-proposals/{proposal['id']}/apply")

    assert applied.status_code == 200
    assert applied.json()["status"] == "applied"
    skills = send(app, "GET", f"/api/workspaces/{workspace['id']}/skills").json()
    generated = next(
        skill for skill in skills
        if skill["skillId"] == "analysis.generated_video_score"
    )
    assert generated["source"] == "generated"
