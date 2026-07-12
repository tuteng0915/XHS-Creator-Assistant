from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import AgentResponse, AgentSummary, AgentUpdate
from app.repositories.agents import AgentRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import as_iso, utc_now
from app.services.skills import SkillService


@dataclass(frozen=True)
class BuiltinAgentDefinition:
    agent_id: str
    display_name: str
    purpose: str
    system_prompt: str
    skill_ids: list[str]
    default_context_policy: dict[str, Any] = field(default_factory=dict)
    version: str = "v1"


BUILTIN_AGENTS = [
    BuiltinAgentDefinition(
        agent_id="creator_material_curator",
        display_name="Creator Material Curator",
        purpose="Keeps creator profile and input assets ready for workflow use.",
        system_prompt=(
            "You manage creator workspace materials. Preserve user-provided content, "
            "avoid inventing input asset content, and prepare only product-specific "
            "inputs needed by downstream creator workflows."
        ),
        skill_ids=[
            "workspace.update_profile",
            "source.save_historical_posts",
            "source.save_comments",
            "source.upload_trend_csv",
            "trend.rank_posts",
        ],
        default_context_policy={
            "may_read": ["workspace profile", "input asset metadata"],
            "must_not_read": ["unrelated workspace artifacts"],
        },
    ),
    BuiltinAgentDefinition(
        agent_id="account_diagnosis_strategist",
        display_name="Account Diagnosis Strategist",
        purpose=(
            "Diagnoses account positioning and turns profile/pain point findings "
            "into topic candidates."
        ),
        system_prompt=(
            "You are a creator account strategist. Use only the selected account "
            "positioning, historical posts, and comment samples. Produce structured "
            "diagnosis outputs that can become reusable workspace artifacts."
        ),
        skill_ids=[
            "analysis.profile_from_history",
            "analysis.pain_points_from_comments",
            "topic.generate_from_account_diagnosis",
        ],
        default_context_policy={
            "may_read": ["positioning snapshot", "selected historical posts", "selected comments"],
            "must_not_read": ["drafts", "simulations", "unselected input assets"],
        },
    ),
    BuiltinAgentDefinition(
        agent_id="trend_opportunity_strategist",
        display_name="Trend Opportunity Strategist",
        purpose="Analyzes trend data and converts trend opportunities into creator-fit topics.",
        system_prompt=(
            "You are a creator trend strategist. Use ranked trend data and creator "
            "positioning to identify patterns, pain points, and actionable content "
            "opportunities."
        ),
        skill_ids=[
            "analysis.trend_patterns",
            "analysis.pain_points_from_trend_posts",
            "topic.generate_from_trend_analysis",
        ],
        default_context_policy={
            "may_read": ["positioning snapshot", "ranked top trend posts"],
            "must_not_read": ["full CSV when compact ranking is available"],
        },
    ),
    BuiltinAgentDefinition(
        agent_id="video_creator_quality_analyst",
        display_name="Video Creator Quality Analyst",
        purpose=(
            "Profiles AIGC video creators, diagnoses video quality, and judges "
            "fit for creator incentive programs."
        ),
        system_prompt=(
            "You are an AIGC video creator operations analyst. Use collected video "
            "samples, transcripts, observation notes, and metrics to classify the "
            "creator's operating motivation, diagnose video quality, and recommend "
            "whether they fit an incentive program. Treat script-driven creators as "
            "usually better incentive fits, commercial-driven creators as hard to "
            "move with incentives, and tech-exploration creators as conditional."
        ),
        skill_ids=[
            "analysis.video_creator_profile",
            "analysis.video_quality",
            "analysis.incentive_fit",
        ],
        default_context_policy={
            "may_read": [
                "positioning snapshot",
                "selected video creator samples",
                "related analysis history",
            ],
            "must_not_read": ["unrelated input assets", "raw uploaded video files"],
        },
    ),
    BuiltinAgentDefinition(
        agent_id="topic_draft_editor",
        display_name="Topic and Draft Editor",
        purpose="Turns selected topics into content structures and preserves user edits.",
        system_prompt=(
            "You are a creator content editor. Work from selected Topic artifacts "
            "and compact analysis context. Generated snapshots must remain separate "
            "from user-editable draft content."
        ),
        skill_ids=[
            "topic.save_candidate",
            "topic.select",
            "draft.generate_structure",
            "draft.edit",
        ],
        default_context_policy={
            "may_read": ["selected topic", "compact source analysis context"],
            "must_not_read": ["raw input assets unless explicitly provided"],
        },
    ),
    BuiltinAgentDefinition(
        agent_id="audience_simulation_researcher",
        display_name="Audience Simulation Researcher",
        purpose="Runs product-specific persona simulation for topics and drafts.",
        system_prompt=(
            "You simulate creator audience reactions using product-specific runtime "
            "roles. Do not expose personas as configurable platform agents. Preserve "
            "partial reactions and synthesize practical content guidance."
        ),
        skill_ids=[
            "simulation.normalize_target",
            "simulation.derive_personas",
            "simulation.initial_reactions",
            "simulation.debate_responses",
            "simulation.synthesize",
        ],
        default_context_policy={
            "may_read": ["simulation target", "positioning snapshot", "persona outputs"],
            "must_not_read": ["full workspace", "unrelated analysis runs"],
        },
    ),
    BuiltinAgentDefinition(
        agent_id="skill_maker",
        display_name="Skill Maker",
        purpose=(
            "Converts creator-product requirements into proposed Skill asset "
            "definitions instead of asking users to fill definition forms."
        ),
        system_prompt=(
            "You design product-specific Skill assets for this creator workspace. "
            "Start from the user's concrete need, inspect the existing workspace "
            "assets and capability catalog, then propose a bounded skill definition. "
            "Do not design a generic plugin, marketplace, filesystem tool, or "
            "workflow editor. Output a practical proposal with skillId, inputs, "
            "output schema, context policy, side effects, failure mode, and how it "
            "composes with existing skills. Do not claim that the asset has been "
            "written; propose changes for confirmation."
        ),
        skill_ids=["meta.design_skill_asset"],
        default_context_policy={
            "may_read": [
                "workspace profile",
                "input asset overview",
                "existing skills",
                "existing agents",
                "existing workflows",
                "recent run summaries",
            ],
            "must_not_read": ["secrets", "arbitrary filesystem paths"],
            "write_policy": "proposal_only",
        },
    ),
    BuiltinAgentDefinition(
        agent_id="agent_maker",
        display_name="Agent Maker",
        purpose=(
            "Converts user needs into proposed Agent assets with system prompts "
            "and skill composition."
        ),
        system_prompt=(
            "You design product-specific Agent assets for this creator workspace. "
            "Given a user need, propose the agent's purpose, system prompt, skillIds, "
            "and default context policy. Prefer composing existing skills; if a "
            "missing skill is needed, explicitly mark it as a proposed dependency. "
            "Do not expose this as a generic agent builder. Do not claim writes have "
            "happened; propose changes for confirmation."
        ),
        skill_ids=["meta.design_agent_asset", "meta.design_skill_asset"],
        default_context_policy={
            "may_read": [
                "workspace profile",
                "existing skills",
                "existing agents",
                "existing workflows",
                "recent run summaries",
            ],
            "must_not_read": ["secrets", "unrelated filesystem"],
            "write_policy": "proposal_only",
        },
    ),
    BuiltinAgentDefinition(
        agent_id="workflow_maker",
        display_name="Workflow Maker",
        purpose=(
            "Converts larger creator-product needs into proposed multi-agent "
            "workflow assets."
        ),
        system_prompt=(
            "You design product-specific Workflow assets for this creator workspace. "
            "Given a user need, propose a bounded workflow with entry agents, task "
            "dependencies, parallel sections where useful, expected artifacts, and "
            "failure/retry boundaries. Compose existing or proposed agents and skills. "
            "Do not design a generic workflow editor or platform abstraction. Do not "
            "claim writes have happened; propose changes for confirmation."
        ),
        skill_ids=[
            "meta.design_workflow_asset",
            "meta.design_agent_asset",
            "meta.design_skill_asset",
        ],
        default_context_policy={
            "may_read": [
                "workspace profile",
                "input asset overview",
                "existing skills",
                "existing agents",
                "existing workflows",
                "recent run summaries",
            ],
            "must_not_read": ["secrets", "arbitrary filesystem paths"],
            "write_policy": "proposal_only",
        },
    ),
]


class AgentService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: AgentRepository,
        workspace_repository: WorkspaceRepository,
        skill_service: SkillService,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.skill_service = skill_service

    def list(self, workspace_id: str) -> list[AgentSummary]:
        self.skill_service.list(workspace_id)
        self._sync_builtin_agents(workspace_id)
        with self.database.read() as connection:
            rows = self.repository.list(connection, workspace_id)
        return [self._to_summary(row) for row in rows]

    def get(self, agent_asset_id: str) -> AgentResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, agent_asset_id)
        return self._to_response(row)

    def update(self, agent_asset_id: str, payload: AgentUpdate) -> AgentResponse:
        if payload.status is None and payload.user_notes is None:
            raise ValidationError("At least one editable field is required")
        with self.database.transaction() as connection:
            row = self.repository.update(
                connection,
                agent_asset_id=agent_asset_id,
                status=payload.status.value if payload.status else None,
                user_notes=payload.user_notes,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    def _sync_builtin_agents(self, workspace_id: str) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            self.workspace_repository.get(connection, workspace_id)
            for definition in BUILTIN_AGENTS:
                definition_hash = self._definition_hash(definition)
                existing = self.repository.get_by_agent_id(
                    connection,
                    workspace_id=workspace_id,
                    agent_id=definition.agent_id,
                )
                payload = {
                    "workspace_id": workspace_id,
                    "agent_id": definition.agent_id,
                    "display_name": definition.display_name,
                    "purpose": definition.purpose,
                    "system_prompt": definition.system_prompt,
                    "skill_ids_json": json.dumps(
                        definition.skill_ids, ensure_ascii=False
                    ),
                    "default_context_policy_json": json.dumps(
                        definition.default_context_policy, ensure_ascii=False
                    ),
                    "version": definition.version,
                    "definition_hash": definition_hash,
                }
                if existing:
                    if (
                        existing["source"] == "builtin"
                        and existing.get("definition_hash") != definition_hash
                    ):
                        self.repository.update_builtin_definition(
                            connection,
                            agent_asset_id=existing["id"],
                            display_name=payload["display_name"],
                            purpose=payload["purpose"],
                            system_prompt=payload["system_prompt"],
                            skill_ids_json=payload["skill_ids_json"],
                            default_context_policy_json=payload[
                                "default_context_policy_json"
                            ],
                            version=payload["version"],
                            definition_hash=payload["definition_hash"],
                            now=now,
                        )
                    continue
                self.repository.create(
                    connection,
                    **payload,
                    now=now,
                )

    @staticmethod
    def _definition_hash(definition: BuiltinAgentDefinition) -> str:
        encoded = json.dumps(
            asdict(definition), ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _to_summary(row: dict) -> AgentSummary:
        return AgentSummary.model_validate(
            {**row, "skill_ids": json.loads(row["skill_ids_json"])}
        )

    @staticmethod
    def _to_response(row: dict) -> AgentResponse:
        return AgentResponse.model_validate(
            {
                **row,
                "skill_ids": json.loads(row["skill_ids_json"]),
                "default_context_policy": json.loads(
                    row["default_context_policy_json"]
                ),
            }
        )
