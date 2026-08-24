from __future__ import annotations

import asyncio
import hashlib
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
    AgentConversationUpdate,
    AgentMessageCreate,
    AgentMessageResponse,
    ModelOperation,
)
from app.repositories.agent_conversations import AgentConversationRepository
from app.repositories.agents import AgentRepository
from app.repositories.asset_proposals import AssetProposalRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import as_iso, utc_now
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
                    "payload": {
                        "definition": self._demo_skill_definition(content),
                    },
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
                    "payload": {
                        "definition": self._demo_agent_definition(content),
                    },
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
                    "payload": {
                        "definition": self._demo_workflow_definition(content),
                    },
                }
            )
        return actions

    @staticmethod
    def _demo_suffix(content: str) -> str:
        digest = hashlib.sha1(content.encode("utf-8")).hexdigest()[:8]
        return digest

    def _demo_skill_definition(self, content: str) -> dict[str, Any]:
        suffix = self._demo_suffix(content)
        return {
            "skillId": f"generated.creator_skill.{suffix}",
            "displayName": "Generated Creator Skill",
            "category": "custom",
            "purpose": content,
            "triggerIntents": [content[:120]],
            "requiredInputs": ["user_requirement"],
            "optionalInputs": ["workspace_context_pack"],
            "contextPolicy": {
                "allowed_fields": ["workspace profile", "relevant content assets"],
                "disallowed_fields": ["secrets", "arbitrary filesystem paths"],
                "scope": "product_specific",
            },
            "outputSchema": {"root": "proposal"},
            "artifactEffect": "Proposed product artifact",
            "sideEffects": ["requires confirmation before writing"],
            "failureMode": "proposal_defined",
            "composableWith": ["meta.design_agent_asset", "meta.design_workflow_asset"],
            "implementationRefs": ["AgentConversationService"],
            "version": "v1",
        }

    def _demo_agent_definition(self, content: str) -> dict[str, Any]:
        suffix = self._demo_suffix(content)
        return {
            "agentId": f"generated.creator_agent.{suffix}",
            "displayName": "Generated Creator Agent",
            "purpose": content,
            "systemPrompt": (
                "You are a product-specific creator workspace agent. "
                "Use approved workspace context and produce proposals for confirmation."
            ),
            "skillIds": ["meta.design_skill_asset"],
            "defaultContextPolicy": {
                "may_read": ["workspace profile", "capability catalog"],
                "must_not_read": ["secrets", "arbitrary filesystem paths"],
                "write_policy": "proposal_only",
            },
            "version": "v1",
        }

    def _demo_workflow_definition(self, content: str) -> dict[str, Any]:
        suffix = self._demo_suffix(content)
        return {
            "workflowId": f"generated.creator_workflow.{suffix}",
            "displayName": "Generated Creator Workflow",
            "purpose": content,
            "entryAgentIds": ["capability_maker"],
            "agentPlan": {
                "tasks": [
                    {
                        "taskId": "design_capability",
                        "agentId": "capability_maker",
                        "skillIds": ["meta.design_workflow_asset"],
                        "dependsOn": [],
                    }
                ]
            },
            "artifactEffect": "Proposed workflow artifact",
            "version": "v1",
        }


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
        self._tasks: dict[str, asyncio.Task] = {}

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
            context_target = (
                payload.context_target.model_dump(mode="json", by_alias=True)
                if payload.context_target is not None
                else {}
            )
            row = self.repository.create(
                connection,
                workspace_id=workspace_id,
                agent_asset_id=payload.agent_asset_id,
                title=title,
                context_target_json=json.dumps(context_target, ensure_ascii=False),
                now=now,
            )
        return self._to_response(row, [])

    def list(self, workspace_id: str) -> list[AgentConversationSummary]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(connection, workspace_id)
            messages_by_id = {
                row["id"]: self.repository.list_messages(connection, row["id"])
                for row in rows
            }
        return [
            AgentConversationSummary.model_validate(
                {
                    **row,
                    "context_target": json.loads(
                        row.get("context_target_json") or "{}"
                    ),
                    "execution_status": self._execution_status(
                        messages_by_id[row["id"]]
                    ),
                }
            )
            for row in rows
        ]

    def get(self, conversation_id: str) -> AgentConversationResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, conversation_id)
            messages = self.repository.list_messages(connection, conversation_id)
        return self._to_response(row, messages)

    def update(
        self, conversation_id: str, payload: AgentConversationUpdate
    ) -> AgentConversationResponse:
        if payload.title is None and payload.status is None:
            raise ValidationError("At least one editable field is required")
        title = payload.title.strip() if payload.title is not None else None
        if title == "":
            raise ValidationError("Conversation title cannot be blank")
        with self.database.transaction() as connection:
            row = self.repository.update(
                connection,
                conversation_id=conversation_id,
                title=title,
                status=payload.status.value if payload.status else None,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
            messages = self.repository.list_messages(connection, conversation_id)
        return self._to_response(row, messages)

    async def send_message(
        self, conversation_id: str, payload: AgentMessageCreate
    ) -> AgentConversationResponse:
        now = utc_now()
        with self.database.transaction() as connection:
            conversation = self.repository.get(connection, conversation_id)
            existing_messages = self.repository.list_messages(connection, conversation_id)
            pending_assistant = self._pending_assistant_message(existing_messages)
            if pending_assistant is not None:
                return self._to_response(conversation, existing_messages)
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
            assistant_message = self.repository.create_message(
                connection,
                conversation_id=conversation_id,
                role="assistant",
                content="Agent 正在生成回复…",
                context_pack_json="{}",
                asset_refs_json="[]",
                proposed_actions_json="[]",
                model_metadata_json=json.dumps(
                    {
                        "operation": ModelOperation.AGENT_CHAT.value,
                        "mode": payload.mode,
                        "status": "queued",
                    },
                    ensure_ascii=False,
                ),
                now=utc_now(),
            )
            row = self.repository.get(connection, conversation_id)
            messages = self.repository.list_messages(connection, conversation_id)

        task = self._enqueue_reply(
            conversation_id=conversation_id,
            assistant_message_id=assistant_message["id"],
            user_content=payload.content,
            mode=payload.mode,
        )
        await asyncio.wait({task}, timeout=0.001)
        with self.database.read() as connection:
            row = self.repository.get(connection, conversation_id)
            messages = self.repository.list_messages(connection, conversation_id)
        return self._to_response(row, messages)

    def resume_unfinished(self) -> None:
        with self.database.read() as connection:
            rows = connection.execute(
                """
                SELECT m.*, c.id AS conversation_id
                FROM agent_messages m
                JOIN agent_conversations c ON c.id = m.conversation_id
                WHERE m.role = 'assistant'
                ORDER BY m.created_at ASC, m.id ASC
                """
            ).fetchall()
        for row in rows:
            message = dict(row)
            try:
                metadata = json.loads(message["model_metadata_json"])
            except json.JSONDecodeError:
                continue
            if metadata.get("status") not in {"queued", "running"}:
                continue
            user_content = self._previous_user_message(message["conversation_id"], message["id"])
            if user_content:
                self._enqueue_reply(
                    conversation_id=message["conversation_id"],
                    assistant_message_id=message["id"],
                    user_content=user_content,
                    mode=str(metadata.get("mode") or "demo"),
                )

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()

    def _enqueue_reply(
        self,
        *,
        conversation_id: str,
        assistant_message_id: str,
        user_content: str,
        mode: str,
    ) -> asyncio.Task:
        existing = self._tasks.get(assistant_message_id)
        if existing and not existing.done():
            return existing
        task = asyncio.create_task(
            self._execute_reply(
                conversation_id=conversation_id,
                assistant_message_id=assistant_message_id,
                user_content=user_content,
                mode=mode,
            )
        )
        self._tasks[assistant_message_id] = task
        task.add_done_callback(lambda _task: self._tasks.pop(assistant_message_id, None))
        return task

    async def _execute_reply(
        self,
        *,
        conversation_id: str,
        assistant_message_id: str,
        user_content: str,
        mode: str,
    ) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            current = self.repository.get_message(connection, assistant_message_id)
            metadata = json.loads(current["model_metadata_json"])
            if metadata.get("status") not in {"queued", "running"}:
                return
            self.repository.update_message(
                connection,
                message_id=assistant_message_id,
                content=current["content"],
                context_pack_json=current["context_pack_json"],
                asset_refs_json=current["asset_refs_json"],
                proposed_actions_json=current["proposed_actions_json"],
                model_metadata_json=json.dumps(
                    {**metadata, "status": "running"}, ensure_ascii=False
                ),
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
            context_target = json.loads(conversation["context_target_json"] or "{}")
            selected_asset_item = (
                self.context_access_service.capability_asset_detail_item(
                    connection,
                    workspace_id=conversation["workspace_id"],
                    context_target=context_target,
                )
                if context_target
                else None
            )
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
                    "selected_capability_asset",
                ],
                deep_items=[selected_asset_item] if selected_asset_item else None,
            )
            asset_refs = context_pack["snapshot"]["sourceRefs"]
            messages = [
                message
                for message in self.repository.list_messages(connection, conversation_id)
                if message["id"] != assistant_message_id
            ]

        provider = self.live_provider if mode == "live" else self.fake_provider
        try:
            reply = await provider.reply(
                agent=agent,
                user_content=user_content,
                context_pack=context_pack,
                messages=messages,
            )
            reply_metadata = {**reply.model_metadata, "status": "completed"}
        except Exception as error:
            reply = AgentConversationReply(
                reply=(
                    "模型调用失败，已保留你的消息。请稍后重试，或切换到演示模式继续。"
                    f"\n\n错误：{str(error) or error.__class__.__name__}"
                ),
                proposed_actions=[],
                model_metadata={
                    "provider": "live" if mode == "live" else "fake",
                    "operation": ModelOperation.AGENT_CHAT.value,
                    "status": "failed",
                    "error": str(error) or error.__class__.__name__,
                },
            )
            reply_metadata = reply.model_metadata

        with self.database.transaction() as connection:
            assistant_message = self.repository.update_message(
                connection,
                message_id=assistant_message_id,
                content=reply.reply,
                context_pack_json=json.dumps(context_pack, ensure_ascii=False),
                asset_refs_json=json.dumps(asset_refs, ensure_ascii=False),
                proposed_actions_json=json.dumps(
                    reply.proposed_actions, ensure_ascii=False
                ),
                model_metadata_json=json.dumps(reply_metadata, ensure_ascii=False),
                now=utc_now(),
            )
            for action in reply.proposed_actions:
                self._create_proposal_for_action(
                    connection,
                    conversation=conversation,
                    message_id=assistant_message["id"],
                    action=action,
                )

    def _previous_user_message(self, conversation_id: str, assistant_message_id: str) -> str:
        with self.database.read() as connection:
            messages = self.repository.list_messages(connection, conversation_id)
        previous_users = []
        for message in messages:
            if message["id"] == assistant_message_id:
                break
            if message["role"] == "user":
                previous_users.append(message)
        if not previous_users:
            return ""
        latest = previous_users[-1]
        return str(latest["content"])

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
                "context_target": json.loads(row.get("context_target_json") or "{}"),
                "execution_status": self._execution_status(messages),
                "messages": [self._to_message(message) for message in messages],
            }
        )

    @staticmethod
    def _execution_status(messages: list[dict]) -> str:
        assistant_messages = [
            message for message in messages if message.get("role") == "assistant"
        ]
        if not assistant_messages:
            return "idle"
        latest = assistant_messages[-1]
        try:
            metadata = json.loads(latest["model_metadata_json"])
        except (json.JSONDecodeError, TypeError):
            return "completed"
        status = str(metadata.get("status") or "")
        if status in {"queued", "running"}:
            return "running"
        if status == "failed":
            return "failed"
        return "completed"

    @classmethod
    def _pending_assistant_message(cls, messages: list[dict]) -> dict | None:
        for message in reversed(messages):
            if message.get("role") != "assistant":
                continue
            try:
                metadata = json.loads(message["model_metadata_json"])
            except (json.JSONDecodeError, TypeError):
                continue
            if metadata.get("status") in {"queued", "running"}:
                return message
            return None
        return None

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
