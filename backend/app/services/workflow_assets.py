from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from app.db.database import SQLiteDatabase
from app.errors import ConflictError, ValidationError
from app.models import (
    CapabilityDefinitionDiffResponse,
    CapabilityDefinitionRevert,
    WorkflowAssetDefinitionUpdate,
    WorkflowAssetResponse,
    WorkflowAssetSummary,
    WorkflowAssetUpdate,
    WorkflowCallBindingUpdate,
)
from app.repositories.workflow_assets import WorkflowAssetRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.agents import AgentService
from app.services.common import as_iso, utc_now


@dataclass(frozen=True)
class BuiltinWorkflowAssetDefinition:
    workflow_id: str
    display_name: str
    purpose: str
    entry_agent_ids: list[str]
    agent_plan: dict[str, Any]
    artifact_effect: str
    version: str = "v1"
    call_binding: str = ""


BUILTIN_WORKFLOW_ASSETS = [
    BuiltinWorkflowAssetDefinition(
        workflow_id="account_diagnosis",
        display_name="Account Diagnosis Workflow",
        purpose="Diagnose account profile and comment pain points, then generate topic candidates.",
        entry_agent_ids=["creator_material_curator", "account_diagnosis_strategist"],
        artifact_effect="AnalysisRun + Topic candidates",
        call_binding="account",
        agent_plan={
            "tasks": [
                {
                    "taskId": "prepare_account_sources",
                    "agentId": "creator_material_curator",
                    "skillIds": [
                        "workspace.update_profile",
                        "source.save_historical_posts",
                        "source.save_comments",
                    ],
                    "dependsOn": [],
                },
                {
                    "taskId": "diagnose_account",
                    "agentId": "account_diagnosis_strategist",
                    "skillIds": [
                        "analysis.profile_from_history",
                        "analysis.pain_points_from_comments",
                    ],
                    "parallel": True,
                    "dependsOn": ["prepare_account_sources"],
                },
                {
                    "taskId": "generate_account_topics",
                    "agentId": "account_diagnosis_strategist",
                    "skillIds": ["topic.generate_from_account_diagnosis"],
                    "dependsOn": ["diagnose_account"],
                },
            ]
        },
    ),
    BuiltinWorkflowAssetDefinition(
        workflow_id="trend_analysis",
        display_name="Trend Analysis Workflow",
        purpose="Analyze uploaded trend data and generate creator-fit topic candidates.",
        entry_agent_ids=["creator_material_curator", "trend_opportunity_strategist"],
        artifact_effect="AnalysisRun + Topic candidates",
        call_binding="trend",
        agent_plan={
            "tasks": [
                {
                    "taskId": "prepare_trend_sources",
                    "agentId": "creator_material_curator",
                    "skillIds": [
                        "workspace.update_profile",
                        "source.upload_trend_csv",
                        "trend.rank_posts",
                    ],
                    "dependsOn": [],
                },
                {
                    "taskId": "analyze_trend",
                    "agentId": "trend_opportunity_strategist",
                    "skillIds": [
                        "analysis.trend_patterns",
                        "analysis.pain_points_from_trend_posts",
                    ],
                    "parallel": True,
                    "dependsOn": ["prepare_trend_sources"],
                },
                {
                    "taskId": "generate_trend_topics",
                    "agentId": "trend_opportunity_strategist",
                    "skillIds": ["topic.generate_from_trend_analysis"],
                    "dependsOn": ["analyze_trend"],
                },
            ]
        },
    ),
    BuiltinWorkflowAssetDefinition(
        workflow_id="video_creator_quality",
        display_name="Video Creator Quality Workflow",
        purpose=(
            "Profile AIGC video creators, diagnose video quality, and judge "
            "whether they fit an incentive program."
        ),
        entry_agent_ids=["creator_material_curator", "video_creator_quality_analyst"],
        artifact_effect="AnalysisRun.video_creator_quality",
        call_binding="video",
        agent_plan={
            "tasks": [
                {
                    "taskId": "prepare_video_creator_evidence",
                    "agentId": "creator_material_curator",
                    "skillIds": ["workspace.update_profile"],
                    "dependsOn": [],
                },
                {
                    "taskId": "profile_video_creator",
                    "agentId": "video_creator_quality_analyst",
                    "skillIds": ["analysis.video_creator_profile"],
                    "dependsOn": ["prepare_video_creator_evidence"],
                },
                {
                    "taskId": "diagnose_video_quality",
                    "agentId": "video_creator_quality_analyst",
                    "skillIds": ["analysis.video_quality"],
                    "dependsOn": ["profile_video_creator"],
                },
                {
                    "taskId": "assess_incentive_fit",
                    "agentId": "video_creator_quality_analyst",
                    "skillIds": ["analysis.incentive_fit"],
                    "dependsOn": ["diagnose_video_quality"],
                },
            ]
        },
    ),
    BuiltinWorkflowAssetDefinition(
        workflow_id="topic_to_draft",
        display_name="Topic to Creative Output Workflow",
        purpose=(
            "Save/select a topic, generate a persistent creative brief, then generate "
            "a persistent content structure."
        ),
        entry_agent_ids=["topic_draft_editor"],
        artifact_effect="Topic + Draft(kind=content_brief) + Draft(kind=content_structure)",
        agent_plan={
            "tasks": [
                {
                    "taskId": "select_topic",
                    "agentId": "topic_draft_editor",
                    "skillIds": ["topic.save_candidate", "topic.select"],
                    "dependsOn": [],
                },
                {
                    "taskId": "generate_brief",
                    "agentId": "topic_draft_editor",
                    "skillIds": ["topic.refine_to_brief"],
                    "dependsOn": ["select_topic"],
                },
                {
                    "taskId": "generate_structure",
                    "agentId": "topic_draft_editor",
                    "skillIds": [
                        "draft.generate_structure_from_brief",
                        "draft.generate_structure",
                    ],
                    "dependsOn": ["generate_brief"],
                },
            ]
        },
    ),
    BuiltinWorkflowAssetDefinition(
        workflow_id="audience_simulation",
        display_name="Audience Simulation Workflow",
        purpose="Simulate audience reactions to a topic or draft and synthesize content guidance.",
        entry_agent_ids=["audience_simulation_researcher"],
        artifact_effect="SimulationRun",
        agent_plan={
            "tasks": [
                {
                    "taskId": "normalize_target",
                    "agentId": "audience_simulation_researcher",
                    "skillIds": ["simulation.normalize_target"],
                    "dependsOn": [],
                },
                {
                    "taskId": "derive_personas",
                    "agentId": "audience_simulation_researcher",
                    "skillIds": ["simulation.derive_personas"],
                    "dependsOn": ["normalize_target"],
                },
                {
                    "taskId": "initial_reactions",
                    "agentId": "audience_simulation_researcher",
                    "skillIds": ["simulation.initial_reactions"],
                    "parallel": True,
                    "dependsOn": ["derive_personas"],
                },
                {
                    "taskId": "debate_responses",
                    "agentId": "audience_simulation_researcher",
                    "skillIds": ["simulation.debate_responses"],
                    "parallel": True,
                    "dependsOn": ["initial_reactions"],
                },
                {
                    "taskId": "synthesis",
                    "agentId": "audience_simulation_researcher",
                    "skillIds": ["simulation.synthesize"],
                    "dependsOn": ["debate_responses"],
                },
            ]
        },
    ),
]


class WorkflowAssetService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: WorkflowAssetRepository,
        workspace_repository: WorkspaceRepository,
        agent_service: AgentService,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.agent_service = agent_service

    def list(self, workspace_id: str) -> list[WorkflowAssetSummary]:
        self.agent_service.list(workspace_id)
        self._sync_builtin_workflows(workspace_id)
        with self.database.read() as connection:
            rows = self.repository.list(connection, workspace_id)
        return [self._to_summary(row) for row in rows]

    def get(self, workflow_asset_id: str) -> WorkflowAssetResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, workflow_asset_id)
        return self._to_response(row)

    def update(
        self, workflow_asset_id: str, payload: WorkflowAssetUpdate
    ) -> WorkflowAssetResponse:
        if payload.status is None and payload.user_notes is None:
            raise ValidationError("At least one editable field is required")
        with self.database.transaction() as connection:
            row = self.repository.update(
                connection,
                workflow_asset_id=workflow_asset_id,
                status=payload.status.value if payload.status else None,
                user_notes=payload.user_notes,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    def update_definition(
        self,
        workflow_asset_id: str,
        payload: WorkflowAssetDefinitionUpdate,
    ) -> WorkflowAssetResponse:
        self._validate_definition_payload(payload)
        with self.database.read() as connection:
            current = self.repository.get(connection, workflow_asset_id)
        workspace_id = current["workspace_id"]
        agent_ids = {agent.agent_id for agent in self.agent_service.list(workspace_id)}
        skill_ids = {
            skill.skill_id for skill in self.agent_service.skill_service.list(workspace_id)
        }
        missing_entry_agents = [
            agent_id
            for agent_id in payload.entry_agent_ids
            if agent_id not in agent_ids
        ]
        if missing_entry_agents:
            raise ValidationError(
                "Workflow references unknown entry agents: "
                f"{', '.join(missing_entry_agents)}"
            )
        missing_task_agents = sorted(
            agent_id
            for agent_id in self._agent_ids_from_plan(payload.agent_plan)
            if agent_id not in agent_ids
        )
        if missing_task_agents:
            raise ValidationError(
                "Workflow task plan references unknown agents: "
                f"{', '.join(missing_task_agents)}"
            )
        missing_task_skills = sorted(
            skill_id
            for skill_id in self._skill_ids_from_plan(payload.agent_plan)
            if skill_id not in skill_ids
        )
        if missing_task_skills:
            raise ValidationError(
                "Workflow task plan references unknown skills: "
                f"{', '.join(missing_task_skills)}"
            )
        with self.database.transaction() as connection:
            current = self.repository.get(connection, workflow_asset_id)
            if current["updated_at"] != as_iso(payload.expected_updated_at):
                raise ConflictError("Workflow changed since it was loaded")
            if current["status"] != "enabled" and payload.call_binding:
                raise ValidationError("Only enabled workflows can be registered for calls")
            row = self.repository.replace_definition(
                connection,
                workflow_asset_id=workflow_asset_id,
                display_name=payload.display_name,
                purpose=payload.purpose,
                entry_agent_ids_json=json.dumps(
                    payload.entry_agent_ids, ensure_ascii=False
                ),
                agent_plan_json=json.dumps(payload.agent_plan, ensure_ascii=False),
                artifact_effect=payload.artifact_effect,
                version=payload.version,
                now=utc_now(),
            )
            row = self.repository.update(
                connection,
                workflow_asset_id=workflow_asset_id,
                status=None,
                user_notes=payload.user_notes,
                expected_updated_at=row["updated_at"],
                now=utc_now(),
            )
            row = self.repository.update_call_binding(
                connection,
                workflow_asset_id=workflow_asset_id,
                call_binding=payload.call_binding,
                expected_updated_at=row["updated_at"],
                now=utc_now(),
            )
        return self._to_response(row)

    def definition_diff(
        self, workflow_asset_id: str
    ) -> CapabilityDefinitionDiffResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, workflow_asset_id)
        current_definition = self._definition_dict_from_row(row)
        builtin = self._builtin_definition_by_workflow_id(row["workflow_id"])
        builtin_definition = (
            self._definition_dict_from_builtin(builtin) if builtin is not None else None
        )
        return CapabilityDefinitionDiffResponse(
            asset_id=row["id"],
            asset_type="workflow",
            stable_id=row["workflow_id"],
            source=row["source"],
            can_revert=row["source"] == "generated" and builtin_definition is not None,
            changed_fields=self._changed_definition_fields(
                current_definition, builtin_definition
            ),
            current_definition=current_definition,
            builtin_definition=builtin_definition,
        )

    def revert_definition(
        self,
        workflow_asset_id: str,
        payload: CapabilityDefinitionRevert,
    ) -> WorkflowAssetResponse:
        with self.database.read() as connection:
            current = self.repository.get(connection, workflow_asset_id)
        builtin = self._builtin_definition_by_workflow_id(current["workflow_id"])
        if builtin is None:
            raise ValidationError("No builtin definition is available for this workflow")
        workspace_id = current["workspace_id"]
        agent_ids = {agent.agent_id for agent in self.agent_service.list(workspace_id)}
        skill_ids = {
            skill.skill_id for skill in self.agent_service.skill_service.list(workspace_id)
        }
        referenced_agent_ids = set(builtin.entry_agent_ids) | self._agent_ids_from_plan(
            builtin.agent_plan
        )
        missing_agents = sorted(referenced_agent_ids - agent_ids)
        if missing_agents:
            raise ValidationError(
                f"Builtin workflow references missing agents: {', '.join(missing_agents)}"
            )
        missing_skills = sorted(self._skill_ids_from_plan(builtin.agent_plan) - skill_ids)
        if missing_skills:
            raise ValidationError(
                f"Builtin workflow references missing skills: {', '.join(missing_skills)}"
            )
        with self.database.transaction() as connection:
            row = self.repository.revert_definition_to_builtin(
                connection,
                workflow_asset_id=workflow_asset_id,
                display_name=builtin.display_name,
                purpose=builtin.purpose,
                entry_agent_ids_json=json.dumps(
                    builtin.entry_agent_ids, ensure_ascii=False
                ),
                agent_plan_json=json.dumps(builtin.agent_plan, ensure_ascii=False),
                artifact_effect=builtin.artifact_effect,
                call_binding=builtin.call_binding,
                version=builtin.version,
                definition_hash=self._definition_hash(builtin),
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    @staticmethod
    def _validate_definition_payload(payload: WorkflowAssetDefinitionUpdate) -> None:
        if not payload.artifact_effect.strip():
            raise ValidationError("Workflow artifactEffect is required")
        for agent_id in payload.entry_agent_ids:
            if not agent_id.strip():
                raise ValidationError("Workflow entryAgentIds cannot contain blank items")
        if not isinstance(payload.agent_plan, dict):
            raise ValidationError("Workflow agentPlan must be an object")

    @staticmethod
    def _builtin_definition_by_workflow_id(
        workflow_id: str,
    ) -> BuiltinWorkflowAssetDefinition | None:
        return next(
            (
                definition
                for definition in BUILTIN_WORKFLOW_ASSETS
                if definition.workflow_id == workflow_id
            ),
            None,
        )

    @staticmethod
    def _definition_dict_from_builtin(
        definition: BuiltinWorkflowAssetDefinition,
    ) -> dict[str, Any]:
        return {
            "displayName": definition.display_name,
            "purpose": definition.purpose,
            "entryAgentIds": definition.entry_agent_ids,
            "agentPlan": definition.agent_plan,
            "artifactEffect": definition.artifact_effect,
            "callBinding": definition.call_binding,
            "version": definition.version,
        }

    @staticmethod
    def _definition_dict_from_row(row: dict) -> dict[str, Any]:
        return {
            "displayName": row["display_name"],
            "purpose": row["purpose"],
            "entryAgentIds": json.loads(row["entry_agent_ids_json"]),
            "agentPlan": json.loads(row["agent_plan_json"]),
            "artifactEffect": row["artifact_effect"],
            "callBinding": row.get("call_binding") or "",
            "version": row["version"],
        }

    @staticmethod
    def _changed_definition_fields(
        current_definition: dict[str, Any],
        builtin_definition: dict[str, Any] | None,
    ) -> list[str]:
        if builtin_definition is None:
            return sorted(current_definition.keys())
        return sorted(
            field
            for field, value in current_definition.items()
            if builtin_definition.get(field) != value
        )

    @staticmethod
    def _agent_ids_from_plan(agent_plan: dict[str, Any]) -> set[str]:
        tasks = agent_plan.get("tasks")
        if not isinstance(tasks, list):
            return set()
        return {
            str(task.get("agentId"))
            for task in tasks
            if isinstance(task, dict) and task.get("agentId")
        }

    @staticmethod
    def _skill_ids_from_plan(agent_plan: dict[str, Any]) -> set[str]:
        tasks = agent_plan.get("tasks")
        if not isinstance(tasks, list):
            return set()
        skill_ids: set[str] = set()
        for task in tasks:
            if not isinstance(task, dict):
                continue
            raw_skill_ids = task.get("skillIds")
            if not isinstance(raw_skill_ids, list):
                continue
            skill_ids.update(str(skill_id) for skill_id in raw_skill_ids if skill_id)
        return skill_ids

    def update_call_binding(
        self, workflow_asset_id: str, payload: WorkflowCallBindingUpdate
    ) -> WorkflowAssetResponse:
        with self.database.transaction() as connection:
            current = self.repository.get(connection, workflow_asset_id)
            if current["status"] != "enabled" and payload.call_binding:
                raise ValidationError("Only enabled workflows can be registered for calls")
            self._validate_call_binding(current, payload.call_binding)
            row = self.repository.update_call_binding(
                connection,
                workflow_asset_id=workflow_asset_id,
                call_binding=payload.call_binding,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    @staticmethod
    def _validate_call_binding(row: dict, call_binding: str) -> None:
        if not call_binding:
            return
        if row["agent_plan_json"] == "{}":
            raise ValidationError("Workflow requires an agent plan before registration")

    def _sync_builtin_workflows(self, workspace_id: str) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            self.workspace_repository.get(connection, workspace_id)
            for definition in BUILTIN_WORKFLOW_ASSETS:
                definition_hash = self._definition_hash(definition)
                existing = self.repository.get_by_workflow_id(
                    connection,
                    workspace_id=workspace_id,
                    workflow_id=definition.workflow_id,
                )
                payload = {
                    "workspace_id": workspace_id,
                    "workflow_id": definition.workflow_id,
                    "display_name": definition.display_name,
                    "purpose": definition.purpose,
                    "entry_agent_ids_json": json.dumps(
                        definition.entry_agent_ids, ensure_ascii=False
                    ),
                    "agent_plan_json": json.dumps(
                        definition.agent_plan, ensure_ascii=False
                    ),
                    "artifact_effect": definition.artifact_effect,
                    "version": definition.version,
                    "call_binding": definition.call_binding,
                    "definition_hash": definition_hash,
                }
                if existing:
                    synced = existing
                    if (
                        existing["source"] == "builtin"
                        and existing.get("definition_hash") != definition_hash
                    ):
                        synced = self.repository.update_builtin_definition(
                            connection,
                            workflow_asset_id=existing["id"],
                            display_name=payload["display_name"],
                            purpose=payload["purpose"],
                            entry_agent_ids_json=payload["entry_agent_ids_json"],
                            agent_plan_json=payload["agent_plan_json"],
                            artifact_effect=payload["artifact_effect"],
                            version=payload["version"],
                            definition_hash=payload["definition_hash"],
                            now=now,
                        )
                    if (
                        synced["source"] == "builtin"
                        and definition.call_binding
                        and not synced.get("call_binding")
                    ):
                        self.repository.repair_builtin_call_binding(
                            connection,
                            workflow_asset_id=synced["id"],
                            call_binding=definition.call_binding,
                            now=now,
                        )
                    continue
                self.repository.create(
                    connection,
                    **payload,
                    now=now,
                )

    @staticmethod
    def _definition_hash(definition: BuiltinWorkflowAssetDefinition) -> str:
        definition_data = asdict(definition)
        definition_data.pop("call_binding", None)
        encoded = json.dumps(definition_data, ensure_ascii=False, sort_keys=True).encode(
            "utf-8"
        )
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _to_summary(row: dict) -> WorkflowAssetSummary:
        return WorkflowAssetSummary.model_validate(
            {
                **row,
                "entry_agent_ids": json.loads(row["entry_agent_ids_json"]),
                "call_binding": row.get("call_binding") or "",
            }
        )

    @staticmethod
    def _to_response(row: dict) -> WorkflowAssetResponse:
        return WorkflowAssetResponse.model_validate(
            {
                **row,
                "call_binding": row.get("call_binding") or "",
                "entry_agent_ids": json.loads(row["entry_agent_ids_json"]),
                "agent_plan": json.loads(row["agent_plan_json"]),
            }
        )
