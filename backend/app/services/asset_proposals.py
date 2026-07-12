from __future__ import annotations

import json
from typing import Any

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import AssetProposalResponse
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
            row = self.skill_repository.create(
                connection,
                workspace_id=proposal["workspace_id"],
                skill_id=self._required_string(definition, "skillId"),
                display_name=self._required_string(definition, "displayName"),
                category=str(definition.get("category") or "custom"),
                purpose=str(definition.get("purpose") or ""),
                trigger_intents_json=json.dumps(
                    self._list(definition.get("triggerIntents")), ensure_ascii=False
                ),
                required_inputs_json=json.dumps(
                    self._list(definition.get("requiredInputs")), ensure_ascii=False
                ),
                optional_inputs_json=json.dumps(
                    self._list(definition.get("optionalInputs")), ensure_ascii=False
                ),
                context_policy_json=json.dumps(
                    self._dict(definition.get("contextPolicy")), ensure_ascii=False
                ),
                output_schema_json=json.dumps(
                    self._dict(definition.get("outputSchema")), ensure_ascii=False
                ),
                artifact_effect=str(definition.get("artifactEffect") or ""),
                side_effects_json=json.dumps(
                    self._list(definition.get("sideEffects")), ensure_ascii=False
                ),
                failure_mode=str(definition.get("failureMode") or "proposal_defined"),
                composable_with_json=json.dumps(
                    self._list(definition.get("composableWith")), ensure_ascii=False
                ),
                implementation_refs_json=json.dumps(
                    self._list(definition.get("implementationRefs")), ensure_ascii=False
                ),
                version=str(definition.get("version") or "v1"),
                now=now,
                source="generated",
            )
            return {"assetType": "skill", "assetId": row["id"], "operation": "create"}
        if action_type == "agent.propose_definition":
            row = self.agent_repository.create(
                connection,
                workspace_id=proposal["workspace_id"],
                agent_id=self._required_string(definition, "agentId"),
                display_name=self._required_string(definition, "displayName"),
                purpose=str(definition.get("purpose") or ""),
                system_prompt=str(definition.get("systemPrompt") or ""),
                skill_ids_json=json.dumps(
                    self._list(definition.get("skillIds")), ensure_ascii=False
                ),
                default_context_policy_json=json.dumps(
                    self._dict(definition.get("defaultContextPolicy")),
                    ensure_ascii=False,
                ),
                version=str(definition.get("version") or "v1"),
                now=now,
                source="generated",
            )
            return {"assetType": "agent", "assetId": row["id"], "operation": "create"}
        row = self.workflow_repository.create(
            connection,
            workspace_id=proposal["workspace_id"],
            workflow_id=self._required_string(definition, "workflowId"),
            display_name=self._required_string(definition, "displayName"),
            purpose=str(definition.get("purpose") or ""),
            entry_agent_ids_json=json.dumps(
                self._list(definition.get("entryAgentIds")), ensure_ascii=False
            ),
            agent_plan_json=json.dumps(
                self._dict(definition.get("agentPlan")), ensure_ascii=False
            ),
            artifact_effect=str(definition.get("artifactEffect") or ""),
            version=str(definition.get("version") or "v1"),
            now=now,
            source="generated",
        )
        return {"assetType": "workflow", "assetId": row["id"], "operation": "create"}

    @staticmethod
    def _required_string(value: dict[str, Any], key: str) -> str:
        result = value.get(key)
        if not isinstance(result, str) or not result.strip():
            raise ValidationError(f"Capability definition requires {key}")
        return result.strip()

    @staticmethod
    def _list(value: Any) -> list[Any]:
        return value if isinstance(value, list) else []

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
