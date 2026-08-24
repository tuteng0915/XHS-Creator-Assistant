from __future__ import annotations

import json
from typing import Any

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import AssetProposalResponse, AssetProposalUpdate
from app.repositories.agents import AgentRepository
from app.repositories.asset_proposals import AssetProposalRepository
from app.repositories.skills import SkillRepository
from app.repositories.topics import TopicRepository
from app.repositories.workflow_assets import WorkflowAssetRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import utc_now


class AssetProposalService:
    def __init__(
        self,
        *,
        database: SQLiteDatabase,
        repository: AssetProposalRepository,
        workspace_repository: WorkspaceRepository,
        topic_repository: TopicRepository,
        skill_repository: SkillRepository,
        agent_repository: AgentRepository,
        workflow_repository: WorkflowAssetRepository,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.topic_repository = topic_repository
        self.skill_repository = skill_repository
        self.agent_repository = agent_repository
        self.workflow_repository = workflow_repository

    def list(
        self,
        *,
        workspace_id: str | None = None,
        conversation_id: str | None = None,
        message_id: str | None = None,
    ) -> list[AssetProposalResponse]:
        with self.database.read() as connection:
            if workspace_id is not None:
                self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(
                connection,
                workspace_id=workspace_id,
                conversation_id=conversation_id,
                message_id=message_id,
            )
        return [self._to_response(row) for row in rows]

    def apply(self, proposal_id: str) -> AssetProposalResponse:
        now = utc_now()
        with self.database.transaction() as connection:
            proposal = self.repository.get(connection, proposal_id)
            action = json.loads(proposal["proposed_action_json"])
            try:
                result = self._apply_action(connection, proposal, action, now)
                row = self.repository.set_status(
                    connection,
                    proposal_id=proposal_id,
                    status="applied",
                    result_json=json.dumps(result, ensure_ascii=False),
                    error="",
                    now=now,
                )
            except Exception as error:
                row = self.repository.set_status(
                    connection,
                    proposal_id=proposal_id,
                    status="failed",
                    result_json="{}",
                    error=str(error) or error.__class__.__name__,
                    now=now,
                )
        return self._to_response(row)

    def update(
        self, proposal_id: str, payload: AssetProposalUpdate
    ) -> AssetProposalResponse:
        now = utc_now()
        proposed_action_json = None
        if payload.proposed_action is not None:
            self._validate_action_payload(payload.proposed_action)
            proposed_action_json = json.dumps(
                payload.proposed_action, ensure_ascii=False
            )
        with self.database.transaction() as connection:
            row = self.repository.update_pending(
                connection,
                proposal_id=proposal_id,
                title=payload.title.strip() if payload.title is not None else None,
                description=(
                    payload.description
                    if payload.description is not None
                    else None
                ),
                proposed_action_json=proposed_action_json,
                expected_updated_at=payload.expected_updated_at.isoformat(),
                now=now,
            )
        return self._to_response(row)

    def reject(self, proposal_id: str) -> AssetProposalResponse:
        now = utc_now()
        with self.database.transaction() as connection:
            row = self.repository.set_status(
                connection,
                proposal_id=proposal_id,
                status="rejected",
                result_json="{}",
                error="",
                now=now,
            )
        return self._to_response(row)

    def _validate_action_payload(self, action: dict[str, Any]) -> None:
        action_type = action.get("type")
        if not isinstance(action_type, str) or not action_type.strip():
            raise ValidationError("Proposal action requires type")
        status = action.get("status")
        if status is not None and status != "requires_confirmation":
            raise ValidationError("Proposal status must remain requires_confirmation")
        payload = action.get("payload")
        if payload is not None and not isinstance(payload, dict):
            raise ValidationError("Proposal action payload must be an object")

    def _apply_action(
        self,
        connection,
        proposal: dict,
        action: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        action_type = proposal["action_type"]
        payload = action.get("payload")
        if not isinstance(payload, dict):
            raise ValidationError("Proposal action requires a structured payload")

        if action_type == "workspace.update_profile":
            return self._apply_workspace_profile(connection, proposal, payload, now)
        if action_type == "topic.create_or_update":
            return self._apply_topic(connection, proposal, payload, now)
        if action_type in {
            "skill.propose_definition",
            "agent.propose_definition",
            "workflow.propose_definition",
        }:
            return self._apply_capability_asset(connection, proposal, action_type, payload, now)
        raise ValidationError(f"Unsupported proposal action type: {action_type}")

    def _apply_workspace_profile(
        self,
        connection,
        proposal: dict,
        payload: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        workspace = self.workspace_repository.get(connection, proposal["workspace_id"])
        name = payload.get("name")
        positioning = payload.get("accountPositioning")
        if name is not None and not isinstance(name, str):
            raise ValidationError("Workspace profile name must be a string")
        if positioning is not None and not isinstance(positioning, str):
            raise ValidationError("Workspace accountPositioning must be a string")
        if name is None and positioning is None:
            raise ValidationError("Workspace proposal needs name or accountPositioning")
        updated = self.workspace_repository.update(
            connection,
            workspace_id=proposal["workspace_id"],
            name=name.strip() if isinstance(name, str) else None,
            account_positioning=positioning,
            expected_updated_at=workspace["updated_at"],
            now=now,
        )
        return {"assetType": "account_profile", "assetId": updated["id"]}

    def _apply_topic(
        self,
        connection,
        proposal: dict,
        payload: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        title = payload.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValidationError("Topic proposal requires title")
        topic_id = payload.get("topicId")
        angle = payload.get("angle")
        associated_pain_point = payload.get("associatedPainPoint")
        why_it_fits = payload.get("whyItFits")
        if topic_id is not None:
            if not isinstance(topic_id, str):
                raise ValidationError("Topic topicId must be a string")
            current = self.topic_repository.get(connection, topic_id)
            if current["workspace_id"] != proposal["workspace_id"]:
                raise ValidationError("Topic belongs to another workspace")
            updated = self.topic_repository.update(
                connection,
                topic_id=topic_id,
                title=title.strip(),
                angle=angle if isinstance(angle, str) else None,
                expected_updated_at=current["updated_at"],
                now=now,
            )
            return {"assetType": "topic", "assetId": updated["id"], "operation": "update"}

        created = self.topic_repository.create(
            connection,
            workspace_id=proposal["workspace_id"],
            title=title.strip(),
            angle=angle if isinstance(angle, str) else "",
            associated_pain_point=(
                associated_pain_point if isinstance(associated_pain_point, str) else ""
            ),
            why_it_fits=why_it_fits if isinstance(why_it_fits, str) else "",
            generated_snapshot_json=json.dumps(
                {"source": "agent_proposal", "payload": payload}, ensure_ascii=False
            ),
            source_analysis_run_id=None,
            source_workflow="manual",
            now=now,
        )
        return {"assetType": "topic", "assetId": created["id"], "operation": "create"}

    def _apply_capability_asset(
        self,
        connection,
        proposal: dict,
        action_type: str,
        payload: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        definition = payload.get("definition", payload)
        if not isinstance(definition, dict):
            raise ValidationError("Capability proposal requires a definition object")
        if action_type == "skill.propose_definition":
            return self._apply_skill_definition(connection, proposal, payload, definition, now)
        if action_type == "agent.propose_definition":
            return self._apply_agent_definition(connection, proposal, payload, definition, now)
        return self._apply_workflow_definition(connection, proposal, payload, definition, now)

    def _apply_skill_definition(
        self,
        connection,
        proposal: dict,
        payload: dict[str, Any],
        definition: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        skill_id = self._required_asset_id(definition, "skillId")
        fields = {
            "display_name": self._required_string(definition, "displayName"),
            "category": self._required_string_or_default(definition, "category", "custom"),
            "purpose": str(definition.get("purpose") or ""),
            "trigger_intents_json": json.dumps(
                self._string_list(definition.get("triggerIntents")), ensure_ascii=False
            ),
            "required_inputs_json": json.dumps(
                self._string_list(definition.get("requiredInputs")), ensure_ascii=False
            ),
            "optional_inputs_json": json.dumps(
                self._string_list(definition.get("optionalInputs")), ensure_ascii=False
            ),
            "context_policy_json": json.dumps(
                self._dict(definition.get("contextPolicy")), ensure_ascii=False
            ),
            "output_schema_json": json.dumps(
                self._dict(definition.get("outputSchema")), ensure_ascii=False
            ),
            "artifact_effect": str(definition.get("artifactEffect") or ""),
            "side_effects_json": json.dumps(
                self._string_list(definition.get("sideEffects")), ensure_ascii=False
            ),
            "failure_mode": str(definition.get("failureMode") or "proposal_defined"),
            "composable_with_json": json.dumps(
                self._string_list(definition.get("composableWith")), ensure_ascii=False
            ),
            "implementation_refs_json": json.dumps(
                self._string_list(definition.get("implementationRefs")), ensure_ascii=False
            ),
            "version": str(definition.get("version") or "v1"),
        }
        target = self._target_skill(connection, proposal["workspace_id"], payload, skill_id)
        if target is not None:
            if target["skill_id"] != skill_id:
                raise ValidationError("Skill stable id cannot be changed by proposal")
            row = self.skill_repository.replace_definition(
                connection,
                skill_asset_id=target["id"],
                now=now,
                **fields,
            )
            return {
                "assetType": "skill",
                "assetId": row["id"],
                "assetStableId": row["skill_id"],
                "operation": "update",
                "source": row["source"],
            }
        row = self.skill_repository.create(
            connection,
            workspace_id=proposal["workspace_id"],
            skill_id=skill_id,
            now=now,
            source="generated",
            **fields,
        )
        return {
            "assetType": "skill",
            "assetId": row["id"],
            "assetStableId": row["skill_id"],
            "operation": "create",
            "source": row["source"],
        }

    def _apply_agent_definition(
        self,
        connection,
        proposal: dict,
        payload: dict[str, Any],
        definition: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        agent_id = self._required_asset_id(definition, "agentId")
        skill_ids = self._string_list(definition.get("skillIds"))
        for skill_id in skill_ids:
            if self.skill_repository.get_by_skill_id(
                connection,
                workspace_id=proposal["workspace_id"],
                skill_id=skill_id,
            ) is None:
                raise ValidationError(f"Agent references unknown skillId: {skill_id}")
        fields = {
            "display_name": self._required_string(definition, "displayName"),
            "purpose": str(definition.get("purpose") or ""),
            "system_prompt": str(definition.get("systemPrompt") or ""),
            "skill_ids_json": json.dumps(skill_ids, ensure_ascii=False),
            "default_context_policy_json": json.dumps(
                self._dict(definition.get("defaultContextPolicy")),
                ensure_ascii=False,
            ),
            "version": str(definition.get("version") or "v1"),
        }
        target = self._target_agent(connection, proposal["workspace_id"], payload, agent_id)
        if target is not None:
            if target["agent_id"] != agent_id:
                raise ValidationError("Agent stable id cannot be changed by proposal")
            row = self.agent_repository.replace_definition(
                connection,
                agent_asset_id=target["id"],
                now=now,
                **fields,
            )
            return {
                "assetType": "agent",
                "assetId": row["id"],
                "assetStableId": row["agent_id"],
                "operation": "update",
                "source": row["source"],
            }
        row = self.agent_repository.create(
            connection,
            workspace_id=proposal["workspace_id"],
            agent_id=agent_id,
            now=now,
            source="generated",
            **fields,
        )
        return {
            "assetType": "agent",
            "assetId": row["id"],
            "assetStableId": row["agent_id"],
            "operation": "create",
            "source": row["source"],
        }

    def _apply_workflow_definition(
        self,
        connection,
        proposal: dict,
        payload: dict[str, Any],
        definition: dict[str, Any],
        now: str,
    ) -> dict[str, Any]:
        workflow_id = self._required_asset_id(definition, "workflowId")
        entry_agent_ids = self._string_list(definition.get("entryAgentIds"))
        agent_plan = self._dict(definition.get("agentPlan"))
        self._validate_workflow_references(
            connection,
            workspace_id=proposal["workspace_id"],
            entry_agent_ids=entry_agent_ids,
            agent_plan=agent_plan,
        )
        fields = {
            "display_name": self._required_string(definition, "displayName"),
            "purpose": str(definition.get("purpose") or ""),
            "entry_agent_ids_json": json.dumps(entry_agent_ids, ensure_ascii=False),
            "agent_plan_json": json.dumps(agent_plan, ensure_ascii=False),
            "artifact_effect": str(definition.get("artifactEffect") or ""),
            "version": str(definition.get("version") or "v1"),
        }
        call_binding = str(definition.get("callBinding") or "")
        if call_binding not in {"", "account", "trend", "video"}:
            raise ValidationError("Workflow callBinding is unsupported")
        target = self._target_workflow(
            connection, proposal["workspace_id"], payload, workflow_id
        )
        if target is not None:
            if target["workflow_id"] != workflow_id:
                raise ValidationError("Workflow stable id cannot be changed by proposal")
            row = self.workflow_repository.replace_definition(
                connection,
                workflow_asset_id=target["id"],
                now=now,
                **fields,
            )
            if call_binding != (row.get("call_binding") or ""):
                row = self.workflow_repository.update_call_binding(
                    connection,
                    workflow_asset_id=row["id"],
                    call_binding=call_binding,
                    expected_updated_at=row["updated_at"],
                    now=now,
                )
            return {
                "assetType": "workflow",
                "assetId": row["id"],
                "assetStableId": row["workflow_id"],
                "operation": "update",
                "source": row["source"],
            }
        row = self.workflow_repository.create(
            connection,
            workspace_id=proposal["workspace_id"],
            workflow_id=workflow_id,
            now=now,
            source="generated",
            call_binding=call_binding,
            **fields,
        )
        return {
            "assetType": "workflow",
            "assetId": row["id"],
            "assetStableId": row["workflow_id"],
            "operation": "create",
            "source": row["source"],
        }

    def _target_skill(
        self,
        connection,
        workspace_id: str,
        payload: dict[str, Any],
        skill_id: str,
    ) -> dict | None:
        target_id = payload.get("targetAssetId")
        if isinstance(target_id, str) and target_id.strip():
            row = self.skill_repository.get(connection, target_id.strip())
            if row["workspace_id"] != workspace_id:
                raise ValidationError("Target skill belongs to another workspace")
            return row
        return self.skill_repository.get_by_skill_id(
            connection, workspace_id=workspace_id, skill_id=skill_id
        )

    def _target_agent(
        self,
        connection,
        workspace_id: str,
        payload: dict[str, Any],
        agent_id: str,
    ) -> dict | None:
        target_id = payload.get("targetAssetId")
        if isinstance(target_id, str) and target_id.strip():
            row = self.agent_repository.get(connection, target_id.strip())
            if row["workspace_id"] != workspace_id:
                raise ValidationError("Target agent belongs to another workspace")
            return row
        return self.agent_repository.get_by_agent_id(
            connection, workspace_id=workspace_id, agent_id=agent_id
        )

    def _target_workflow(
        self,
        connection,
        workspace_id: str,
        payload: dict[str, Any],
        workflow_id: str,
    ) -> dict | None:
        target_id = payload.get("targetAssetId")
        if isinstance(target_id, str) and target_id.strip():
            row = self.workflow_repository.get(connection, target_id.strip())
            if row["workspace_id"] != workspace_id:
                raise ValidationError("Target workflow belongs to another workspace")
            return row
        return self.workflow_repository.get_by_workflow_id(
            connection, workspace_id=workspace_id, workflow_id=workflow_id
        )

    def _validate_workflow_references(
        self,
        connection,
        *,
        workspace_id: str,
        entry_agent_ids: list[str],
        agent_plan: dict[str, Any],
    ) -> None:
        for agent_id in entry_agent_ids:
            if self.agent_repository.get_by_agent_id(
                connection, workspace_id=workspace_id, agent_id=agent_id
            ) is None:
                raise ValidationError(f"Workflow references unknown entryAgentId: {agent_id}")
        tasks = agent_plan.get("tasks")
        if tasks is None:
            return
        if not isinstance(tasks, list):
            raise ValidationError("Workflow agentPlan.tasks must be a list")
        for task in tasks:
            if not isinstance(task, dict):
                raise ValidationError("Workflow agentPlan.tasks entries must be objects")
            agent_id = task.get("agentId")
            if (
                isinstance(agent_id, str)
                and agent_id
                and self.agent_repository.get_by_agent_id(
                    connection, workspace_id=workspace_id, agent_id=agent_id
                )
                is None
            ):
                raise ValidationError(f"Workflow task references unknown agentId: {agent_id}")
            for skill_id in self._string_list(task.get("skillIds")):
                if self.skill_repository.get_by_skill_id(
                    connection, workspace_id=workspace_id, skill_id=skill_id
                ) is None:
                    raise ValidationError(f"Workflow task references unknown skillId: {skill_id}")

    @staticmethod
    def _required_asset_id(value: dict[str, Any], key: str) -> str:
        result = AssetProposalService._required_string(value, key)
        if any(character.isspace() for character in result):
            raise ValidationError(f"Capability definition {key} must not contain whitespace")
        return result

    @staticmethod
    def _required_string(value: dict[str, Any], key: str) -> str:
        result = value.get(key)
        if not isinstance(result, str) or not result.strip():
            raise ValidationError(f"Capability definition requires {key}")
        return result.strip()

    @staticmethod
    def _required_string_or_default(value: dict[str, Any], key: str, default: str) -> str:
        result = value.get(key)
        if result is None:
            return default
        if not isinstance(result, str) or not result.strip():
            raise ValidationError(f"Capability definition {key} must be a string")
        return result.strip()

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list):
            raise ValidationError("Capability definition list field must be a list")
        result: list[str] = []
        for item in value:
            if not isinstance(item, str):
                raise ValidationError("Capability definition list entries must be strings")
            stripped = item.strip()
            if stripped:
                result.append(stripped)
        return result

    @staticmethod
    def _dict(value: Any) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _to_response(row: dict) -> AssetProposalResponse:
        return AssetProposalResponse.model_validate(
            {
                **row,
                "proposed_action": json.loads(row["proposed_action_json"]),
                "result": json.loads(row["result_json"]),
            }
        )
