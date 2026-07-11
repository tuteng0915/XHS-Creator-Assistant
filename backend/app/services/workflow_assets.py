from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import WorkflowAssetResponse, WorkflowAssetSummary, WorkflowAssetUpdate
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


BUILTIN_WORKFLOW_ASSETS = [
    BuiltinWorkflowAssetDefinition(
        workflow_id="account_diagnosis",
        display_name="Account Diagnosis Workflow",
        purpose="Diagnose account profile and comment pain points, then generate topic candidates.",
        entry_agent_ids=["creator_material_curator", "account_diagnosis_strategist"],
        artifact_effect="AnalysisRun + Topic candidates",
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
        workflow_id="topic_to_draft",
        display_name="Topic to Draft Workflow",
        purpose="Save/select a topic and generate a persistent content structure draft.",
        entry_agent_ids=["topic_draft_editor"],
        artifact_effect="Topic + Draft",
        agent_plan={
            "tasks": [
                {
                    "taskId": "select_topic",
                    "agentId": "topic_draft_editor",
                    "skillIds": ["topic.save_candidate", "topic.select"],
                    "dependsOn": [],
                },
                {
                    "taskId": "generate_draft",
                    "agentId": "topic_draft_editor",
                    "skillIds": ["draft.generate_structure"],
                    "dependsOn": ["select_topic"],
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

    def _sync_builtin_workflows(self, workspace_id: str) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            self.workspace_repository.get(connection, workspace_id)
            for definition in BUILTIN_WORKFLOW_ASSETS:
                if self.repository.get_by_workflow_id(
                    connection,
                    workspace_id=workspace_id,
                    workflow_id=definition.workflow_id,
                ):
                    continue
                self.repository.create(
                    connection,
                    workspace_id=workspace_id,
                    workflow_id=definition.workflow_id,
                    display_name=definition.display_name,
                    purpose=definition.purpose,
                    entry_agent_ids_json=json.dumps(
                        definition.entry_agent_ids, ensure_ascii=False
                    ),
                    agent_plan_json=json.dumps(
                        definition.agent_plan, ensure_ascii=False
                    ),
                    artifact_effect=definition.artifact_effect,
                    version=definition.version,
                    now=now,
                )

    @staticmethod
    def _to_summary(row: dict) -> WorkflowAssetSummary:
        return WorkflowAssetSummary.model_validate(
            {**row, "entry_agent_ids": json.loads(row["entry_agent_ids_json"])}
        )

    @staticmethod
    def _to_response(row: dict) -> WorkflowAssetResponse:
        return WorkflowAssetResponse.model_validate(
            {
                **row,
                "entry_agent_ids": json.loads(row["entry_agent_ids_json"]),
                "agent_plan": json.loads(row["agent_plan_json"]),
            }
        )
