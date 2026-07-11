from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import SkillResponse, SkillSummary, SkillUpdate
from app.repositories.skills import SkillRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import as_iso, utc_now


@dataclass(frozen=True)
class BuiltinSkillDefinition:
    skill_id: str
    display_name: str
    category: str
    purpose: str
    artifact_effect: str
    failure_mode: str
    implementation_refs: list[str]
    required_inputs: list[str] = field(default_factory=list)
    optional_inputs: list[str] = field(default_factory=list)
    trigger_intents: list[str] = field(default_factory=list)
    context_policy: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)
    side_effects: list[str] = field(default_factory=list)
    composable_with: list[str] = field(default_factory=list)
    version: str = "v1"


BUILTIN_SKILLS = [
    BuiltinSkillDefinition(
        skill_id="workspace.update_profile",
        display_name="Update Creator Profile",
        category="workspace",
        purpose="Update workspace name and account positioning before downstream generation.",
        required_inputs=["workspace_id", "name", "account_positioning"],
        output_schema={"type": "Workspace"},
        artifact_effect="Workspace",
        side_effects=["updates workspace", "creates positioning version when positioning changes"],
        failure_mode="atomic",
        composable_with=[
            "analysis.profile_from_history",
            "analysis.trend_patterns",
            "simulation.derive_personas",
        ],
        implementation_refs=["WorkspaceService.update"],
    ),
    BuiltinSkillDefinition(
        skill_id="source.save_historical_posts",
        display_name="Save Historical Posts",
        category="source",
        purpose="Persist reusable historical post material for account diagnosis.",
        required_inputs=["workspace_id", "historical_posts_text"],
        output_schema={"type": "SourceMaterial", "material_type": "historical_posts"},
        artifact_effect="SourceMaterial.historical_posts",
        side_effects=["creates or updates source material"],
        failure_mode="atomic",
        composable_with=["analysis.profile_from_history"],
        implementation_refs=[
            "SourceMaterialService.create_text",
            "SourceMaterialService.update",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="source.save_comments",
        display_name="Save Comment Samples",
        category="source",
        purpose="Persist reusable comment samples for pain-point analysis.",
        required_inputs=["workspace_id", "comments_text"],
        output_schema={"type": "SourceMaterial", "material_type": "comments"},
        artifact_effect="SourceMaterial.comments",
        side_effects=["creates or updates source material"],
        failure_mode="atomic",
        composable_with=["analysis.pain_points_from_comments"],
        implementation_refs=[
            "SourceMaterialService.create_text",
            "SourceMaterialService.update",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="source.upload_trend_csv",
        display_name="Upload Trend CSV",
        category="source",
        purpose="Persist uploaded trend CSV or TSV data with controlled server storage.",
        required_inputs=["workspace_id", "keyword", "csv_or_tsv_file"],
        output_schema={"type": "SourceMaterial", "material_type": "trend_csv"},
        artifact_effect="SourceMaterial.trend_csv",
        side_effects=["stores upload on disk", "stores metadata in SQLite"],
        failure_mode="atomic",
        composable_with=["trend.rank_posts"],
        implementation_refs=["SourceMaterialService.create_csv"],
    ),
    BuiltinSkillDefinition(
        skill_id="trend.rank_posts",
        display_name="Rank Trend Posts",
        category="trend",
        purpose="Parse and rank trend CSV rows deterministically before model execution.",
        required_inputs=["trend_csv_material_id"],
        output_schema={"type": "RankedTrendPosts", "limit": 50},
        artifact_effect="AnalysisRun.inputSnapshot.trendCsv.rankedPosts",
        side_effects=["embeds compact ranked snapshot into run input snapshot"],
        failure_mode="atomic",
        composable_with=[
            "analysis.trend_patterns",
            "analysis.pain_points_from_trend_posts",
        ],
        implementation_refs=["AnalysisRunService._rank_trend_posts"],
    ),
    BuiltinSkillDefinition(
        skill_id="analysis.profile_from_history",
        display_name="Analyze Account Profile",
        category="analysis",
        purpose=(
            "Infer content pillars, title formulas, hook styles, viral structure, "
            "voice fingerprint, and performance contrast."
        ),
        required_inputs=["positioning_snapshot", "historical_posts_material_id"],
        context_policy={
            "allowed_fields": ["positioning", "historicalPosts"],
            "disallowed_fields": ["comments", "full_workspace", "drafts", "simulations"],
        },
        output_schema={"root": "profile"},
        artifact_effect="AnalysisRun.stageResults.profile",
        side_effects=["writes stage result"],
        failure_mode="partial_allowed",
        composable_with=[
            "topic.generate_from_account_diagnosis",
            "draft.generate_structure",
        ],
        implementation_refs=[
            "ModelOperation.PROFILE",
            "AccountDiagnosisWorkflowService.profile_analysis",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="analysis.pain_points_from_comments",
        display_name="Extract Comment Pain Points",
        category="analysis",
        purpose="Extract audience pain points from comment source material.",
        required_inputs=["comments_material_id"],
        context_policy={
            "allowed_fields": ["sourceText"],
            "disallowed_fields": ["historicalPosts", "full_workspace", "drafts"],
        },
        output_schema={"root": "painPoints"},
        artifact_effect="AnalysisRun.stageResults.pain_points",
        side_effects=["writes stage result"],
        failure_mode="partial_allowed",
        composable_with=["topic.generate_from_account_diagnosis"],
        implementation_refs=[
            "ModelOperation.PAIN_POINTS",
            "AccountDiagnosisWorkflowService.profile_analysis",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="analysis.trend_patterns",
        display_name="Analyze Trend Patterns",
        category="analysis",
        purpose=(
            "Summarize trend themes, viral patterns, and opportunity windows "
            "from ranked posts."
        ),
        required_inputs=["positioning_snapshot", "trend_keyword", "ranked_posts"],
        context_policy={
            "allowed_fields": ["positioning", "trendKeyword", "postsText"],
            "disallowed_fields": ["full_csv", "comments", "historicalPosts"],
        },
        output_schema={"root": "trendAnalysis"},
        artifact_effect="AnalysisRun.stageResults.trend_analysis",
        side_effects=["writes stage result"],
        failure_mode="partial_allowed",
        composable_with=["topic.generate_from_trend_analysis"],
        implementation_refs=[
            "ModelOperation.TREND_ANALYSIS",
            "TrendAnalysisWorkflowService.trend_pattern_analysis",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="analysis.pain_points_from_trend_posts",
        display_name="Extract Trend Pain Points",
        category="analysis",
        purpose="Infer reader pain points from ranked trend post titles and snippets.",
        required_inputs=["trend_keyword", "ranked_posts"],
        context_policy={
            "allowed_fields": ["sourceText"],
            "disallowed_fields": ["full_csv", "full_workspace", "drafts"],
        },
        output_schema={"root": "painPoints"},
        artifact_effect="AnalysisRun.stageResults.pain_points",
        side_effects=["writes stage result"],
        failure_mode="partial_allowed",
        composable_with=["topic.generate_from_trend_analysis"],
        implementation_refs=[
            "ModelOperation.PAIN_POINTS",
            "TrendAnalysisWorkflowService.pain_point_analysis",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="topic.generate_from_account_diagnosis",
        display_name="Generate Account Topics",
        category="topic",
        purpose="Generate topic candidates from account profile and comment pain points.",
        required_inputs=["positioning_snapshot", "profile", "painPoints"],
        context_policy={
            "allowed_fields": ["positioning", "profile", "painPoints"],
            "disallowed_fields": ["raw_comments", "raw_historical_posts"],
        },
        output_schema={"root": "topics_and_titles"},
        artifact_effect="AnalysisRun.stageResults.topics",
        side_effects=["writes stage result"],
        failure_mode="fails_workflow_if_invalid",
        composable_with=["topic.save_candidate", "draft.generate_structure"],
        implementation_refs=["ModelOperation.TOPICS"],
    ),
    BuiltinSkillDefinition(
        skill_id="topic.generate_from_trend_analysis",
        display_name="Generate Trend Topics",
        category="topic",
        purpose="Generate topic candidates from trend patterns and trend pain points.",
        required_inputs=["positioning_snapshot", "trendAnalysis", "painPoints"],
        context_policy={
            "allowed_fields": ["positioning", "trendAnalysis", "painPoints"],
            "disallowed_fields": ["full_csv", "ranked_posts_text"],
        },
        output_schema={"root": "topics_and_titles"},
        artifact_effect="AnalysisRun.stageResults.topics",
        side_effects=["writes stage result"],
        failure_mode="fails_workflow_if_invalid",
        composable_with=["topic.save_candidate", "draft.generate_structure"],
        implementation_refs=["ModelOperation.TREND_TOPICS"],
    ),
    BuiltinSkillDefinition(
        skill_id="topic.save_candidate",
        display_name="Save Topic Candidate",
        category="topic",
        purpose="Convert a generated or manual topic into a persistent Topic artifact.",
        required_inputs=["workspace_id", "title"],
        optional_inputs=[
            "angle",
            "associated_pain_point",
            "why_it_fits",
            "source_analysis_run_id",
        ],
        output_schema={"type": "Topic"},
        artifact_effect="Topic",
        side_effects=["creates topic artifact"],
        failure_mode="atomic",
        composable_with=["topic.select", "draft.generate_structure"],
        implementation_refs=["TopicService.create"],
    ),
    BuiltinSkillDefinition(
        skill_id="topic.select",
        display_name="Select Current Topic",
        category="topic",
        purpose="Mark a topic as the current topic for the workspace.",
        required_inputs=["topic_id"],
        output_schema={"type": "Topic"},
        artifact_effect="Topic.status + Workspace.currentTopicId",
        side_effects=["updates selected topic status"],
        failure_mode="atomic",
        composable_with=["draft.generate_structure", "simulation.normalize_target"],
        implementation_refs=["TopicService.select"],
    ),
    BuiltinSkillDefinition(
        skill_id="draft.generate_structure",
        display_name="Generate Draft Structure",
        category="draft",
        purpose="Generate a persistent content structure from a selected topic.",
        required_inputs=["topic_id", "positioning_snapshot"],
        optional_inputs=["compact_analysis_context"],
        context_policy={
            "allowed_fields": ["positioning", "topic", "background"],
            "disallowed_fields": ["raw_source_materials", "full_workspace"],
        },
        output_schema={"root": "structure"},
        artifact_effect="Draft",
        side_effects=["creates draft", "stores generated snapshot and editable content"],
        failure_mode="atomic",
        composable_with=["draft.edit", "simulation.normalize_target"],
        implementation_refs=[
            "DraftGenerationService.generate_from_topic",
            "ModelOperation.STRUCTURE",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="draft.edit",
        display_name="Edit Draft",
        category="draft",
        purpose=(
            "Persist user edits to draft editable content without modifying "
            "generated snapshot."
        ),
        required_inputs=["draft_id", "editable_content", "expected_updated_at"],
        output_schema={"type": "Draft"},
        artifact_effect="Draft.editableContent",
        side_effects=["updates draft editable content"],
        failure_mode="atomic",
        composable_with=["simulation.normalize_target"],
        implementation_refs=["DraftService.update"],
    ),
    BuiltinSkillDefinition(
        skill_id="simulation.normalize_target",
        display_name="Normalize Simulation Target",
        category="simulation",
        purpose="Turn topic, draft, or manual topic input into compact simulation context.",
        required_inputs=["topic_id_or_draft_id_or_manual_topic"],
        output_schema={"type": "SimulationTarget"},
        artifact_effect="SimulationRun.inputSnapshot",
        side_effects=["captures immutable input snapshot"],
        failure_mode="atomic",
        composable_with=["simulation.derive_personas"],
        implementation_refs=[
            "SimulationRunService.create",
            "AudienceSimulationWorkflowService._simulation_target_context",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="simulation.derive_personas",
        display_name="Derive Audience Personas",
        category="simulation",
        purpose="Derive product-specific audience personas for a topic or draft.",
        required_inputs=["positioning_snapshot", "simulation_target"],
        context_policy={
            "allowed_fields": ["positioning", "topic"],
            "disallowed_fields": ["full_workspace", "full_analysis_run"],
        },
        output_schema={"root": "personas"},
        artifact_effect="SimulationRun.personaDefinitions",
        side_effects=["writes simulation progress"],
        failure_mode="fails_simulation_if_invalid",
        composable_with=["simulation.initial_reactions"],
        implementation_refs=["ModelOperation.SIMULATION_PERSONAS"],
    ),
    BuiltinSkillDefinition(
        skill_id="simulation.initial_reactions",
        display_name="Simulate Initial Reactions",
        category="simulation",
        purpose="Simulate independent first reactions from each audience persona.",
        required_inputs=["persona", "simulation_target"],
        context_policy={
            "allowed_fields": ["persona", "topic"],
            "disallowed_fields": ["other_reactions", "full_workspace"],
        },
        output_schema={"root": "reaction"},
        artifact_effect="SimulationRun.reactionResults",
        side_effects=["writes partial simulation progress"],
        failure_mode="partial_allowed",
        composable_with=["simulation.debate_responses", "simulation.synthesize"],
        implementation_refs=["ModelOperation.SIMULATION_REACTION"],
    ),
    BuiltinSkillDefinition(
        skill_id="simulation.debate_responses",
        display_name="Simulate Debate Responses",
        category="simulation",
        purpose="Simulate second-round persona responses after seeing other reactions.",
        required_inputs=["persona", "simulation_target", "other_reactions"],
        context_policy={
            "allowed_fields": ["persona", "topic", "otherReactions"],
            "disallowed_fields": ["full_workspace", "synthesis"],
        },
        output_schema={"root": "debateResponse"},
        artifact_effect="SimulationRun.debateResults",
        side_effects=["writes partial simulation progress"],
        failure_mode="partial_allowed",
        composable_with=["simulation.synthesize"],
        implementation_refs=["ModelOperation.SIMULATION_DEBATE"],
    ),
    BuiltinSkillDefinition(
        skill_id="simulation.synthesize",
        display_name="Synthesize Simulation",
        category="simulation",
        purpose="Synthesize persona discussion into content strategy guidance.",
        required_inputs=[
            "simulation_target",
            "personas",
            "initial_reactions",
            "debate_responses",
        ],
        context_policy={
            "allowed_fields": ["topic", "personas", "reactions", "debateResponses"],
            "disallowed_fields": ["raw_source_materials", "full_workspace"],
        },
        output_schema={"root": "synthesis"},
        artifact_effect="SimulationRun.synthesis",
        side_effects=["writes simulation synthesis"],
        failure_mode="partial_allowed",
        composable_with=["draft.rewrite"],
        implementation_refs=["ModelOperation.SIMULATION_SYNTHESIS"],
    ),
    BuiltinSkillDefinition(
        skill_id="meta.design_skill_asset",
        display_name="Design Skill Asset",
        category="meta",
        purpose=(
            "Turn a user requirement into a product-specific skill proposal with "
            "input contract, output schema, context policy, side effects, and "
            "composition boundaries."
        ),
        required_inputs=["user_requirement", "workspace_context_pack"],
        optional_inputs=["related_skills", "target_workflow", "implementation_refs"],
        context_policy={
            "allowed_fields": [
                "workspace profile",
                "source material overview",
                "existing skills",
                "existing agents",
                "existing workflows",
                "recent runs",
            ],
            "disallowed_fields": ["arbitrary filesystem paths", "secrets"],
            "scope": "broad_workspace_view",
        },
        output_schema={
            "root": "skillProposal",
            "fields": [
                "skillId",
                "displayName",
                "category",
                "purpose",
                "requiredInputs",
                "optionalInputs",
                "contextPolicy",
                "outputSchema",
                "artifactEffect",
                "sideEffects",
                "failureMode",
                "composableWith",
                "implementationRefs",
            ],
        },
        artifact_effect="Proposed Skill asset definition",
        side_effects=["proposes asset changes only", "requires confirmation before writing"],
        failure_mode="proposal_only",
        composable_with=["meta.design_agent_asset", "meta.design_workflow_asset"],
        implementation_refs=["AgentConversationService", "ModelOperation.AGENT_CHAT"],
    ),
    BuiltinSkillDefinition(
        skill_id="meta.design_agent_asset",
        display_name="Design Agent Asset",
        category="meta",
        purpose=(
            "Turn a user requirement into a product-specific agent proposal with "
            "system prompt, skill composition, and default context policy."
        ),
        required_inputs=["user_requirement", "workspace_context_pack", "available_skills"],
        optional_inputs=["target_workflow", "runtime_constraints"],
        context_policy={
            "allowed_fields": [
                "workspace profile",
                "existing skills",
                "existing agents",
                "existing workflows",
                "recent runs",
            ],
            "disallowed_fields": ["secrets", "arbitrary platform agents"],
            "scope": "broad_workspace_view",
        },
        output_schema={
            "root": "agentProposal",
            "fields": [
                "agentId",
                "displayName",
                "purpose",
                "systemPrompt",
                "skillIds",
                "defaultContextPolicy",
                "version",
            ],
        },
        artifact_effect="Proposed Agent asset definition",
        side_effects=["proposes asset changes only", "requires confirmation before writing"],
        failure_mode="proposal_only",
        composable_with=["meta.design_workflow_asset"],
        implementation_refs=["AgentConversationService", "ModelOperation.AGENT_CHAT"],
    ),
    BuiltinSkillDefinition(
        skill_id="meta.design_workflow_asset",
        display_name="Design Workflow Asset",
        category="meta",
        purpose=(
            "Turn a user requirement into a product-specific workflow proposal "
            "that composes existing or proposed agents into a bounded node graph."
        ),
        required_inputs=[
            "user_requirement",
            "workspace_context_pack",
            "available_agents",
            "available_skills",
        ],
        optional_inputs=["source_assets", "expected_artifacts", "failure_recovery_policy"],
        context_policy={
            "allowed_fields": [
                "workspace profile",
                "source material overview",
                "existing skills",
                "existing agents",
                "existing workflows",
                "recent runs",
            ],
            "disallowed_fields": ["generic workflow editor concepts", "plugin marketplace"],
            "scope": "broad_workspace_view",
        },
        output_schema={
            "root": "workflowProposal",
            "fields": [
                "workflowId",
                "displayName",
                "purpose",
                "entryAgentIds",
                "agentPlan",
                "artifactEffect",
                "version",
            ],
        },
        artifact_effect="Proposed Workflow asset definition",
        side_effects=["proposes asset changes only", "requires confirmation before writing"],
        failure_mode="proposal_only",
        composable_with=["meta.design_skill_asset", "meta.design_agent_asset"],
        implementation_refs=["AgentConversationService", "ModelOperation.AGENT_CHAT"],
    ),
]


class SkillService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: SkillRepository,
        workspace_repository: WorkspaceRepository,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository

    def list(self, workspace_id: str) -> list[SkillSummary]:
        self._sync_builtin_skills(workspace_id)
        with self.database.read() as connection:
            rows = self.repository.list(connection, workspace_id)
        return [SkillSummary.model_validate(row) for row in rows]

    def get(self, skill_asset_id: str) -> SkillResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, skill_asset_id)
        return self._to_response(row)

    def update(self, skill_asset_id: str, payload: SkillUpdate) -> SkillResponse:
        if payload.status is None and payload.user_notes is None:
            raise ValidationError("At least one editable field is required")
        with self.database.transaction() as connection:
            row = self.repository.update(
                connection,
                skill_asset_id=skill_asset_id,
                status=payload.status.value if payload.status else None,
                user_notes=payload.user_notes,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    def _sync_builtin_skills(self, workspace_id: str) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            self.workspace_repository.get(connection, workspace_id)
            for definition in BUILTIN_SKILLS:
                if self.repository.get_by_skill_id(
                    connection,
                    workspace_id=workspace_id,
                    skill_id=definition.skill_id,
                ):
                    continue
                self.repository.create(
                    connection,
                    workspace_id=workspace_id,
                    skill_id=definition.skill_id,
                    display_name=definition.display_name,
                    category=definition.category,
                    purpose=definition.purpose,
                    trigger_intents_json=json.dumps(
                        definition.trigger_intents, ensure_ascii=False
                    ),
                    required_inputs_json=json.dumps(
                        definition.required_inputs, ensure_ascii=False
                    ),
                    optional_inputs_json=json.dumps(
                        definition.optional_inputs, ensure_ascii=False
                    ),
                    context_policy_json=json.dumps(
                        definition.context_policy, ensure_ascii=False
                    ),
                    output_schema_json=json.dumps(
                        definition.output_schema, ensure_ascii=False
                    ),
                    artifact_effect=definition.artifact_effect,
                    side_effects_json=json.dumps(
                        definition.side_effects, ensure_ascii=False
                    ),
                    failure_mode=definition.failure_mode,
                    composable_with_json=json.dumps(
                        definition.composable_with, ensure_ascii=False
                    ),
                    implementation_refs_json=json.dumps(
                        definition.implementation_refs, ensure_ascii=False
                    ),
                    version=definition.version,
                    now=now,
                )

    @staticmethod
    def _to_response(row: dict) -> SkillResponse:
        return SkillResponse.model_validate(
            {
                **row,
                "trigger_intents": json.loads(row["trigger_intents_json"]),
                "required_inputs": json.loads(row["required_inputs_json"]),
                "optional_inputs": json.loads(row["optional_inputs_json"]),
                "context_policy": json.loads(row["context_policy_json"]),
                "output_schema": json.loads(row["output_schema_json"]),
                "side_effects": json.loads(row["side_effects_json"]),
                "composable_with": json.loads(row["composable_with_json"]),
                "implementation_refs": json.loads(row["implementation_refs_json"]),
            }
        )
