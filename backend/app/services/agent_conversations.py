from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import (
    AgentConversationCreate,
    AgentConversationResponse,
    AgentConversationSummary,
    AgentMessageCreate,
    AgentMessageResponse,
    ModelOperation,
)
from app.repositories.agent_conversations import AgentConversationRepository
from app.repositories.agents import AgentRepository
from app.repositories.asset_proposals import AssetProposalRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import utc_now
from app.services.context_access import ContextAccessService
from app.services.model_calls import ModelCallService


@dataclass(frozen=True)
class AgentConversationReply:
    reply: str
    proposed_actions: list[dict[str, Any]]
    model_metadata: dict[str, Any]


class AgentConversationModelProvider(Protocol):
    async def reply(
        self,
        *,
        agent: dict,
        user_content: str,
        context_pack: dict,
        messages: list[dict],
    ) -> AgentConversationReply: ...


class FakeAgentConversationModelProvider:
    async def reply(
        self,
        *,
        agent: dict,
        user_content: str,
        context_pack: dict,
        messages: list[dict],
    ) -> AgentConversationReply:
        proposed_actions = self._propose_actions(user_content)
        overview_keys = ", ".join(item["key"] for item in context_pack["items"])
        action_text = (
            "我也识别到一个可能的资产修改意图，已作为 proposedActions 保存，等待后续确认执行。"
            if proposed_actions
            else "这一步我只会引用和分析资产，不会直接修改资产。"
        )
        return AgentConversationReply(
            reply=(
                f"我是 {agent['display_name']}。我已读取当前 workspace 的 broad context pack："
                f"{overview_keys}。\n\n"
                f"你刚才说：{user_content}\n\n"
                "基于当前阶段，我可以先帮你梳理问题、指出相关资产、提出下一步操作建议。"
                f"{action_text}"
            ),
            proposed_actions=proposed_actions,
            model_metadata={
                "provider": "fake",
                "model": "deterministic-agent-conversation",
                "operation": ModelOperation.AGENT_CHAT.value,
                "historyMessageCount": len(messages),
            },
        )

    def _propose_actions(self, content: str) -> list[dict[str, Any]]:
        normalized = content.lower()
        actions: list[dict[str, Any]] = []
        if any(keyword in normalized for keyword in ["账号", "profile", "定位"]):
            actions.append(
                {
                    "type": "workspace.update_profile",
                    "status": "requires_confirmation",
                    "description": (
                        "用户可能希望调整 Account Profile；当前版本只提出建议，"
                        "不自动写入。"
                    ),
                    "payload": {"accountPositioning": content},
                }
            )
        if any(keyword in normalized for keyword in ["选题", "topic"]):
            actions.append(
                {
                    "type": "topic.create_or_update",
                    "status": "requires_confirmation",
                    "description": "用户可能希望新增或调整 Topic；当前版本只提出建议，不自动写入。",
                    "payload": {"title": content, "angle": ""},
                }
            )
        if any(keyword in normalized for keyword in ["草稿", "draft", "结构"]):
            actions.append(
                {
                    "type": "draft.update_editable_content",
                    "status": "requires_confirmation",
                    "description": "用户可能希望修改 Draft；当前版本只提出建议，不自动写入。",
                }
            )
        if any(keyword in normalized for keyword in ["skill", "能力", "技能"]):
            actions.append(
                {
                    "type": "skill.propose_definition",
                    "status": "requires_confirmation",
                    "description": (
                        "用户可能希望新增或修改 Skill；当前版本只生成定义提案，不自动写入。"
                    ),
                }
            )
        if any(keyword in normalized for keyword in ["agent", "智能体", "角色"]):
            actions.append(
                {
                    "type": "agent.propose_definition",
                    "status": "requires_confirmation",
                    "description": (
                        "用户可能希望新增或修改 Agent；当前版本只生成定义提案，不自动写入。"
                    ),
                }
            )
        if any(keyword in normalized for keyword in ["workflow", "工作流", "流程"]):
            actions.append(
                {
                    "type": "workflow.propose_definition",
                    "status": "requires_confirmation",
                    "description": (
                        "用户可能希望新增或修改 Workflow；当前版本只生成定义提案，"
                        "不自动写入。"
                    ),
                }
            )
        return actions


class RealAgentConversationModelProvider:
    def __init__(self, model_call_service: ModelCallService) -> None:
        self.model_call_service = model_call_service

    async def reply(
        self,
        *,
        agent: dict,
        user_content: str,
        context_pack: dict,
        messages: list[dict],
    ) -> AgentConversationReply:
        response = await self.model_call_service.call_operation(
            ModelOperation.AGENT_CHAT,
            {
                "agent": {
                    "agentId": agent["agent_id"],
                    "displayName": agent["display_name"],
                    "purpose": agent["purpose"],
                    "systemPrompt": agent["system_prompt"],
                    "skillIds": json.loads(agent["skill_ids_json"]),
                    "defaultContextPolicy": json.loads(
                        agent["default_context_policy_json"]
                    ),
                },
                "contextPack": context_pack,
                "messages": [
                    {
                        "role": message["role"],
                        "content": message["content"],
                        "createdAt": message["created_at"],
                    }
                    for message in messages[-12:]
                ],
                "userMessage": user_content,
            },
        )
        output = response.output
        reply = output.get("reply")
        if not isinstance(reply, str) or not reply.strip():
            raise ValidationError("Agent chat response missing reply")
        return AgentConversationReply(
            reply=reply.strip(),
            proposed_actions=self._validate_proposed_actions(
                output.get("proposedActions", [])
            ),
            model_metadata=response.model_metadata,
        )

    def _validate_proposed_actions(self, value: Any) -> list[dict[str, Any]]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValidationError("Agent chat proposedActions must be a list")
        actions: list[dict[str, Any]] = []
        for item in value:
            if not isinstance(item, dict):
                raise ValidationError("Agent chat proposedActions entries must be objects")
            action_type = item.get("type")
            description = item.get("description")
            if not isinstance(action_type, str) or not action_type:
                raise ValidationError("Agent chat proposedAction missing type")
            if not isinstance(description, str) or not description:
                raise ValidationError("Agent chat proposedAction missing description")
            actions.append(
                {
                    "type": action_type,
                    "status": "requires_confirmation",
                    "description": description,
                    "payload": item.get("payload") if isinstance(item.get("payload"), dict) else {},
                }
            )
        return actions


class AgentConversationService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: AgentConversationRepository,
        proposal_repository: AssetProposalRepository,
        workspace_repository: WorkspaceRepository,
        agent_repository: AgentRepository,
        context_access_service: ContextAccessService,
        fake_provider: AgentConversationModelProvider,
        live_provider: AgentConversationModelProvider,
        capability_catalog_ensurers: list[Callable[[str], object]] | None = None,
    ) -> None:
        self.database = database
        self.repository = repository
        self.proposal_repository = proposal_repository
        self.workspace_repository = workspace_repository
        self.agent_repository = agent_repository
        self.context_access_service = context_access_service
        self.fake_provider = fake_provider
        self.live_provider = live_provider
        self.capability_catalog_ensurers = capability_catalog_ensurers or []

    def create(
        self, workspace_id: str, payload: AgentConversationCreate
    ) -> AgentConversationResponse:
        now = utc_now()
        with self.database.transaction() as connection:
            self.workspace_repository.get(connection, workspace_id)
            agent = self.agent_repository.get(connection, payload.agent_asset_id)
            if agent["workspace_id"] != workspace_id:
                raise ValidationError("Agent belongs to another workspace")
            if agent["status"] != "enabled":
                raise ValidationError("Agent is disabled")
            title = payload.title or f"与 {agent['display_name']} 对话"
            row = self.repository.create(
                connection,
                workspace_id=workspace_id,
                agent_asset_id=payload.agent_asset_id,
                title=title,
                now=now,
            )
        return self._to_response(row, [])

    def list(self, workspace_id: str) -> list[AgentConversationSummary]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(connection, workspace_id)
        return [AgentConversationSummary.model_validate(row) for row in rows]

    def get(self, conversation_id: str) -> AgentConversationResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, conversation_id)
            messages = self.repository.list_messages(connection, conversation_id)
        return self._to_response(row, messages)

    async def send_message(
        self, conversation_id: str, payload: AgentMessageCreate
    ) -> AgentConversationResponse:
        now = utc_now()
        with self.database.transaction() as connection:
            conversation = self.repository.get(connection, conversation_id)
            agent = self.agent_repository.get(connection, conversation["agent_asset_id"])
            if agent["status"] != "enabled":
                raise ValidationError("Agent is disabled")
            self.repository.create_message(
                connection,
                conversation_id=conversation_id,
                role="user",
                content=payload.content,
                context_pack_json="{}",
                asset_refs_json="[]",
                proposed_actions_json="[]",
                model_metadata_json="{}",
                now=now,
            )

        with self.database.read() as connection:
            conversation = self.repository.get(connection, conversation_id)

        for ensure_catalog in self.capability_catalog_ensurers:
            ensure_catalog(conversation["workspace_id"])

        with self.database.read() as connection:
            conversation = self.repository.get(connection, conversation_id)
            workspace = self.workspace_repository.get(
                connection, conversation["workspace_id"]
            )
            agent = self.agent_repository.get(connection, conversation["agent_asset_id"])
            context_pack = self.context_access_service.build_workspace_pack(
                connection,
                workspace=workspace,
                requester={
                    "workflowId": "agent_conversation",
                    "agentId": agent["agent_id"],
                    "skillId": "agent.chat",
                    "conversationId": conversation_id,
                },
                purpose="agent_conversation_reply",
                selectors=[
                    "account_positioning",
                    "input_assets_overview",
                    "analysis_history_overview",
                    "topic_library_overview",
                    "draft_history_overview",
                    "simulation_history_overview",
                    "capability_catalog",
                    "agent_system_prompt",
                ],
            )
            asset_refs = context_pack["snapshot"]["sourceRefs"]
            messages = self.repository.list_messages(connection, conversation_id)

        provider = self.live_provider if payload.mode == "live" else self.fake_provider
        try:
            reply = await provider.reply(
                agent=agent,
                user_content=payload.content,
                context_pack=context_pack,
                messages=messages,
            )
        except Exception as error:
            reply = AgentConversationReply(
                reply=(
                    "模型调用失败，已保留你的消息。请稍后重试，或切换到演示模式继续。"
                    f"\n\n错误：{str(error) or error.__class__.__name__}"
                ),
                proposed_actions=[],
                model_metadata={
                    "provider": "live" if payload.mode == "live" else "fake",
                    "operation": ModelOperation.AGENT_CHAT.value,
                    "status": "failed",
                    "error": str(error) or error.__class__.__name__,
                },
            )

        with self.database.transaction() as connection:
            assistant_message = self.repository.create_message(
                connection,
                conversation_id=conversation_id,
                role="assistant",
                content=reply.reply,
                context_pack_json=json.dumps(context_pack, ensure_ascii=False),
                asset_refs_json=json.dumps(asset_refs, ensure_ascii=False),
                proposed_actions_json=json.dumps(
                    reply.proposed_actions, ensure_ascii=False
                ),
                model_metadata_json=json.dumps(reply.model_metadata, ensure_ascii=False),
                now=utc_now(),
            )
            for action in reply.proposed_actions:
                self._create_proposal_for_action(
                    connection,
                    conversation=conversation,
                    message_id=assistant_message["id"],
                    action=action,
                )
            row = self.repository.get(connection, conversation_id)
            messages = self.repository.list_messages(connection, conversation_id)
        return self._to_response(row, messages)

    def _create_proposal_for_action(
        self,
        connection,
        *,
        conversation: dict,
        message_id: str,
        action: dict[str, Any],
    ) -> None:
        action_type = str(action.get("type") or "").strip()
        if not action_type:
            return
        description = str(action.get("description") or action_type)
        title = str(action.get("title") or self._proposal_title(action_type))
        normalized = {
            **action,
            "type": action_type,
            "status": "requires_confirmation",
            "description": description,
            "payload": action.get("payload") if isinstance(action.get("payload"), dict) else {},
        }
        self.proposal_repository.create(
            connection,
            workspace_id=conversation["workspace_id"],
            conversation_id=conversation["id"],
            message_id=message_id,
            action_type=action_type,
            title=title,
            description=description,
            proposed_action_json=json.dumps(normalized, ensure_ascii=False),
            now=utc_now(),
        )

    @staticmethod
    def _proposal_title(action_type: str) -> str:
        labels = {
            "workspace.update_profile": "更新 Account Profile",
            "topic.create_or_update": "创建或更新 Topic",
            "draft.update_editable_content": "更新 Draft",
            "skill.propose_definition": "新增或修改 Skill",
            "agent.propose_definition": "新增或修改 Agent",
            "workflow.propose_definition": "新增或修改 Workflow",
        }
        return labels.get(action_type, action_type)

    def _to_response(
        self, row: dict, messages: list[dict]
    ) -> AgentConversationResponse:
        return AgentConversationResponse.model_validate(
            {
                **row,
                "messages": [self._to_message(message) for message in messages],
            }
        )

    def _to_message(self, row: dict) -> AgentMessageResponse:
        return AgentMessageResponse.model_validate(
            {
                **row,
                "context_pack": json.loads(row["context_pack_json"]),
                "asset_refs": json.loads(row["asset_refs_json"]),
                "proposed_actions": json.loads(row["proposed_actions_json"]),
                "model_metadata": json.loads(row["model_metadata_json"]),
            }
        )
