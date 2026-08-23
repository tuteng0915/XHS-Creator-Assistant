import asyncio
from dataclasses import replace
from typing import Any

import httpx
from fastapi import FastAPI
from test_workspace_api import create_workspace, send

from app.services.agent_conversations import (
    AgentConversationReply,
    RealAgentConversationModelProvider,
)
from app.services.model_calls import ModelCallService


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
    assert "Creator Dossier Curator" in assistant_message["content"]
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
    input_overview = next(
        item for item in assistant_message["contextPack"]["items"]
        if item["key"] == "input_assets_overview"
    )
    assert input_overview["data"][0]["assetGroup"] == "creator_dossier"
    assert input_overview["data"][0]["assetGroupLabel"] == "创作者档案"
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


def test_maker_conversation_includes_selected_capability_asset_context(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    agents = send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
    maker = next(item for item in agents if item["agentId"] == "capability_maker")
    skills = send(app, "GET", f"/api/workspaces/{workspace['id']}/skills").json()
    selected_skill = next(
        item for item in skills if item["skillId"] == "analysis.profile_from_history"
    )

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/agent-conversations",
        json={
            "agentAssetId": maker["id"],
            "title": "改造 Skill",
            "contextTarget": {
                "assetType": "skill",
                "assetId": selected_skill["id"],
            },
        },
    )
    assert created.status_code == 201
    conversation = created.json()
    assert conversation["contextTarget"] == {
        "assetType": "skill",
        "assetId": selected_skill["id"],
    }

    replied = send(
        app,
        "POST",
        f"/api/agent-conversations/{conversation['id']}/messages",
        json={"content": "基于当前 Skill 帮我改进一下"},
    )

    assert replied.status_code == 200
    assistant_message = replied.json()["messages"][1]
    selected_item = next(
        item
        for item in assistant_message["contextPack"]["items"]
        if item["key"] == "selected_capability_asset"
    )
    assert selected_item["assetRef"]["assetType"] == "skill"
    assert selected_item["assetRef"]["assetId"] == selected_skill["id"]
    assert selected_item["data"]["skillId"] == "analysis.profile_from_history"


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


def test_live_agent_conversation_post_returns_queued_message_without_waiting(
    app: FastAPI,
) -> None:
    class SlowProvider:
        async def reply(self, *, agent, user_content, context_pack, messages):
            await asyncio.sleep(0.1)
            return AgentConversationReply(
                reply="slow reply",
                proposed_actions=[],
                model_metadata={"provider": "slow", "operation": "agent_chat"},
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
    app.state.agent_conversation_service.live_provider = SlowProvider()

    replied = send(
        app,
        "POST",
        f"/api/agent-conversations/{conversation['id']}/messages",
        json={"content": "慢请求", "mode": "live"},
    )

    assert replied.status_code == 200
    messages = replied.json()["messages"]
    assert messages[0]["role"] == "user"
    assert messages[1]["role"] == "assistant"
    assert messages[1]["content"] == "Agent 正在生成回复…"
    assert messages[1]["modelMetadata"]["status"] in {"queued", "running"}


def test_live_agent_conversation_can_call_qwen_compatible_api_with_mocked_http(
    app: FastAPI,
    monkeypatch,
) -> None:
    class FakeQwenClient:
        requests: list[dict[str, Any]] = []

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "FakeQwenClient":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        async def post(
            self,
            url: str,
            *,
            headers: dict[str, str],
            json: dict[str, Any],
        ) -> httpx.Response:
            self.requests.append({"url": url, "headers": headers, "json": json})
            return httpx.Response(
                200,
                json={
                    "model": "qwen-plus",
                    "choices": [
                        {
                            "message": {
                                "content": (
                                    '{"reply":"qwen 已根据 workspace context 返回。",'
                                    '"proposedActions":[]}'
                                )
                            }
                        }
                    ],
                    "usage": {"total_tokens": 42},
                },
            )

    FakeQwenClient.requests = []
    monkeypatch.setattr(httpx, "AsyncClient", FakeQwenClient)
    app.state.agent_conversation_service.live_provider = (
        RealAgentConversationModelProvider(
            ModelCallService(
                replace(
                    app.state.settings,
                    model_provider="qwen",
                    qwen_api_key="placeholder-key",
                    qwen_model="qwen-plus",
                    qwen_base_url=(
                        "https://workspace-id.cn-beijing.maas.aliyuncs.com"
                        "/compatible-mode/v1"
                    ),
                )
            )
        )
    )

    workspace = create_workspace(app)
    agents = send(app, "GET", f"/api/workspaces/{workspace['id']}/agents").json()
    agent = next(item for item in agents if item["agentId"] == "capability_maker")
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
        json={"content": "帮我设计一个 skill", "mode": "live"},
    )

    assert replied.status_code == 200
    assistant_message = replied.json()["messages"][1]
    assert assistant_message["content"] == "qwen 已根据 workspace context 返回。"
    assert assistant_message["modelMetadata"]["provider"] == "qwen"
    assert assistant_message["modelMetadata"]["model"] == "qwen-plus"
    request = FakeQwenClient.requests[0]
    assert request["url"] == (
        "https://workspace-id.cn-beijing.maas.aliyuncs.com"
        "/compatible-mode/v1/chat/completions"
    )
    assert request["json"]["model"] == "qwen-plus"
    assert request["json"]["messages"][0]["role"] == "system"
    assert request["json"]["messages"][1]["role"] == "user"
    assert "capability_maker" in request["json"]["messages"][1]["content"]


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
    agent = next(item for item in agents if item["agentId"] == "capability_maker")
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
