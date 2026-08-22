from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field


def to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part.capitalize() for part in tail)


class APIModel(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class HealthResponse(APIModel):
    status: Literal["ok"]
    service: Literal["creator-workspace-backend"]


class WorkspaceCreate(APIModel):
    name: str = Field(min_length=1, max_length=120)
    account_positioning: str = Field(default="", max_length=100_000)


class WorkspaceUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    account_positioning: str | None = Field(default=None, max_length=100_000)
    expected_updated_at: datetime


class WorkspaceResponse(APIModel):
    id: str
    name: str
    account_positioning: str
    positioning_version: int
    current_topic_id: str | None = None
    created_at: datetime
    updated_at: datetime


class SourceMaterialType(StrEnum):
    ACCOUNT_PROFILE = "account_profile"
    HISTORICAL_POSTS = "historical_posts"
    COMMENTS = "comments"
    TREND_CSV = "trend_csv"
    VIDEO_CREATOR_SAMPLES = "video_creator_samples"
    XHS_CREATOR_PROFILE = "xhs_creator_profile"


class TextSourceMaterialCreate(APIModel):
    type: Literal[
        SourceMaterialType.ACCOUNT_PROFILE,
        SourceMaterialType.HISTORICAL_POSTS,
        SourceMaterialType.COMMENTS,
        SourceMaterialType.VIDEO_CREATOR_SAMPLES,
        SourceMaterialType.XHS_CREATOR_PROFILE,
    ]
    name: str = Field(min_length=1, max_length=160)
    content: str = Field(default="", max_length=1_000_000)


class SourceMaterialUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    content: str | None = Field(default=None, max_length=1_000_000)
    keyword: str | None = Field(default=None, max_length=200)
    expected_updated_at: datetime


class SourceMaterialBase(APIModel):
    id: str
    workspace_id: str
    name: str
    created_at: datetime
    updated_at: datetime


class TextSourceMaterialResponse(SourceMaterialBase):
    type: Literal[
        SourceMaterialType.ACCOUNT_PROFILE,
        SourceMaterialType.HISTORICAL_POSTS,
        SourceMaterialType.COMMENTS,
        SourceMaterialType.VIDEO_CREATOR_SAMPLES,
        SourceMaterialType.XHS_CREATOR_PROFILE,
    ]
    content: str


class TrendCsvSourceMaterialResponse(SourceMaterialBase):
    type: Literal[SourceMaterialType.TREND_CSV]
    keyword: str
    original_filename: str
    media_type: str
    byte_size: int
    sha256: str
    row_count: int
    preview: list[dict[str, str]]


SourceMaterialResponse = Annotated[
    TextSourceMaterialResponse | TrendCsvSourceMaterialResponse,
    Field(discriminator="type"),
]

# Product-facing input asset aliases.
#
# The storage/API compatibility layer still has SourceMaterial names. New
# product code should prefer InputAsset names while old API paths remain active.
InputAssetType = SourceMaterialType
TextInputAssetCreate = TextSourceMaterialCreate
InputAssetUpdate = SourceMaterialUpdate
InputAssetBase = SourceMaterialBase
TextInputAssetResponse = TextSourceMaterialResponse
TrendCsvInputAssetResponse = TrendCsvSourceMaterialResponse
InputAssetResponse = SourceMaterialResponse


class MediaAssetType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


class MediaAssetSourceType(StrEnum):
    UPLOAD = "upload"
    URL = "url"
    GENERATED = "generated"
    EXTRACTED_FRAME = "extracted_frame"


class MediaAssetUpdate(APIModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    purpose: str | None = Field(default=None, max_length=2_000)
    metadata: dict[str, Any] | None = None
    derived: dict[str, Any] | None = None
    user_notes: str | None = Field(default=None, max_length=100_000)
    expected_updated_at: datetime


class VideoPreviewDeriveRequest(APIModel):
    frame_count: int | None = Field(default=None, ge=1, le=12)
    force: bool = False


class MediaAssetResponse(APIModel):
    id: str
    workspace_id: str
    type: MediaAssetType
    name: str
    purpose: str
    source_type: MediaAssetSourceType
    original_filename: str
    media_type: str
    byte_size: int
    sha256: str
    metadata: dict[str, Any]
    derived: dict[str, Any]
    user_notes: str
    file_url: str
    external_url: str = ""
    created_at: datetime
    updated_at: datetime


class VideoPreviewDeriveResponse(APIModel):
    video_asset: MediaAssetResponse
    frames: list[MediaAssetResponse]


class SkillStatus(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class SkillSource(StrEnum):
    BUILTIN = "builtin"
    GENERATED = "generated"


class SkillSummary(APIModel):
    id: str
    workspace_id: str
    skill_id: str
    display_name: str
    category: str
    purpose: str
    artifact_effect: str
    source: SkillSource
    status: SkillStatus
    version: str
    updated_at: datetime


class SkillResponse(SkillSummary):
    trigger_intents: list[str]
    required_inputs: list[str]
    optional_inputs: list[str]
    context_policy: dict[str, Any]
    output_schema: dict[str, Any]
    side_effects: list[str]
    failure_mode: str
    composable_with: list[str]
    implementation_refs: list[str]
    user_notes: str


class SkillUpdate(APIModel):
    status: SkillStatus | None = None
    user_notes: str | None = Field(default=None, max_length=10_000)
    expected_updated_at: datetime


class SkillInvokeRequest(APIModel):
    input: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["demo", "live"] = "demo"


class SkillInvokeResponse(APIModel):
    skill_asset_id: str
    skill_id: str
    status: Literal["completed"]
    output: dict[str, Any]
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class AgentStatus(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class AgentSource(StrEnum):
    BUILTIN = "builtin"
    GENERATED = "generated"


class AgentSummary(APIModel):
    id: str
    workspace_id: str
    agent_id: str
    display_name: str
    purpose: str
    skill_ids: list[str]
    source: AgentSource
    status: AgentStatus
    version: str
    updated_at: datetime


class AgentResponse(AgentSummary):
    system_prompt: str
    default_context_policy: dict[str, Any]
    user_notes: str


class AgentUpdate(APIModel):
    status: AgentStatus | None = None
    user_notes: str | None = Field(default=None, max_length=10_000)
    expected_updated_at: datetime


class AgentConversationStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ConversationContextTarget(APIModel):
    asset_type: Literal["skill", "agent", "workflow"]
    asset_id: str = Field(min_length=1, max_length=80)


class AgentConversationCreate(APIModel):
    agent_asset_id: str
    title: str | None = Field(default=None, max_length=160)
    context_target: ConversationContextTarget | None = None


class AgentMessageCreate(APIModel):
    content: str = Field(min_length=1, max_length=20_000)
    mode: Literal["demo", "live"] = "demo"


class AgentMessageResponse(APIModel):
    id: str
    conversation_id: str
    role: Literal["user", "assistant"]
    content: str
    context_pack: dict[str, Any]
    asset_refs: list[dict[str, Any]]
    proposed_actions: list[dict[str, Any]]
    model_metadata: dict[str, Any]
    created_at: datetime


class AgentConversationSummary(APIModel):
    id: str
    workspace_id: str
    agent_asset_id: str
    title: str
    status: AgentConversationStatus
    context_target: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AgentConversationResponse(AgentConversationSummary):
    messages: list[AgentMessageResponse]


class AssetProposalStatus(StrEnum):
    PENDING = "pending"
    APPLIED = "applied"
    REJECTED = "rejected"
    FAILED = "failed"


class AssetProposalResponse(APIModel):
    id: str
    workspace_id: str
    conversation_id: str
    message_id: str
    action_type: str
    title: str
    description: str
    status: AssetProposalStatus
    proposed_action: dict[str, Any]
    result: dict[str, Any]
    error: str
    created_at: datetime
    updated_at: datetime
    applied_at: datetime | None = None


class WorkflowAssetStatus(StrEnum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class WorkflowAssetSource(StrEnum):
    BUILTIN = "builtin"
    GENERATED = "generated"


class WorkflowAssetSummary(APIModel):
    id: str
    workspace_id: str
    workflow_id: str
    display_name: str
    purpose: str
    entry_agent_ids: list[str]
    artifact_effect: str
    source: WorkflowAssetSource
    status: WorkflowAssetStatus
    version: str
    updated_at: datetime


class WorkflowAssetResponse(WorkflowAssetSummary):
    agent_plan: dict[str, Any]
    user_notes: str


class WorkflowAssetUpdate(APIModel):
    status: WorkflowAssetStatus | None = None
    user_notes: str | None = Field(default=None, max_length=10_000)
    expected_updated_at: datetime


class WorkflowType(StrEnum):
    ACCOUNT_DIAGNOSIS = "account_diagnosis"
    TREND_ANALYSIS = "trend_analysis"
    VIDEO_CREATOR_QUALITY = "video_creator_quality"


class AnalysisRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"


class AnalysisRunCreate(APIModel):
    workflow_type: WorkflowType
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)
    account_profile_input_asset_id: str | None = None
    account_profile_material_id: str | None = None
    manual_account_profile: str | None = Field(default=None, max_length=100_000)
    historical_posts_input_asset_id: str | None = None
    historical_posts_material_id: str | None = None
    comments_input_asset_id: str | None = None
    comments_material_id: str | None = None
    trend_csv_input_asset_id: str | None = None
    trend_csv_material_id: str | None = None
    video_creator_samples_input_asset_id: str | None = None
    video_creator_samples_material_id: str | None = None
    xhs_creator_profile_input_asset_id: str | None = None
    xhs_creator_profile_material_id: str | None = None
    media_asset_ids: list[str] = Field(default_factory=list)
    mode: Literal["demo", "live"] = "demo"


class AnalysisRunBatchCreate(APIModel):
    workflow_type: WorkflowType
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=120)
    account_profile_input_asset_ids: list[str] = Field(default_factory=list)
    account_profile_material_ids: list[str] = Field(default_factory=list)
    xhs_creator_profile_input_asset_ids: list[str] = Field(default_factory=list)
    xhs_creator_profile_material_ids: list[str] = Field(default_factory=list)
    historical_posts_input_asset_id: str | None = None
    historical_posts_material_id: str | None = None
    comments_input_asset_id: str | None = None
    comments_material_id: str | None = None
    trend_csv_input_asset_id: str | None = None
    trend_csv_material_id: str | None = None
    video_creator_samples_input_asset_id: str | None = None
    video_creator_samples_material_id: str | None = None
    media_asset_ids: list[str] = Field(default_factory=list)
    mode: Literal["demo", "live"] = "demo"


class AccountProfileCsvImportResponse(APIModel):
    materials: list[TextSourceMaterialResponse]


class TextInputAssetCsvImportResponse(APIModel):
    materials: list[TextSourceMaterialResponse]


class XhsOfflineImportResponse(APIModel):
    input_asset: TextInputAssetResponse
    parsed_note_count: int
    source_url: str = ""
    warnings: list[str] = Field(default_factory=list)


class AnalysisRunTransition(APIModel):
    status: AnalysisRunStatus
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisStageUpdate(APIModel):
    status: AnalysisRunStatus
    result: dict[str, Any] | list[Any] | str | None = None
    error: str | None = Field(default=None, max_length=10_000)
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisRunSummary(APIModel):
    id: str
    workspace_id: str
    workflow_type: WorkflowType
    status: AnalysisRunStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class AnalysisRunResponse(AnalysisRunSummary):
    input_snapshot: dict[str, Any]
    stage_results: dict[str, Any]
    stage_errors: dict[str, str]
    model_metadata: dict[str, Any]


class TopicStatus(StrEnum):
    CANDIDATE = "candidate"
    SELECTED = "selected"
    ARCHIVED = "archived"


class TopicSourceWorkflow(StrEnum):
    ACCOUNT_DIAGNOSIS = "account_diagnosis"
    TREND_ANALYSIS = "trend_analysis"
    MANUAL = "manual"


class TopicCreate(APIModel):
    title: str = Field(min_length=1, max_length=300)
    angle: str = Field(default="", max_length=2_000)
    associated_pain_point: str = Field(default="", max_length=500)
    why_it_fits: str = Field(default="", max_length=4_000)
    source_analysis_run_id: str | None = None
    source_workflow: TopicSourceWorkflow | None = None
    generated_snapshot: dict[str, Any] | None = None


class TopicUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    angle: str | None = Field(default=None, max_length=2_000)
    expected_updated_at: datetime


class TopicResponse(APIModel):
    id: str
    workspace_id: str
    title: str
    angle: str
    associated_pain_point: str
    why_it_fits: str
    generated_snapshot: dict[str, Any]
    source_analysis_run_id: str | None
    source_workflow: TopicSourceWorkflow
    status: TopicStatus
    created_at: datetime
    updated_at: datetime


class DraftStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DraftGenerateRequest(APIModel):
    mode: Literal["demo", "live"] = "demo"


class DraftUpdate(APIModel):
    editable_content: dict[str, Any]
    expected_updated_at: datetime


class DraftSummary(APIModel):
    id: str
    workspace_id: str
    topic_id: str
    source_analysis_run_id: str | None
    source_workflow: TopicSourceWorkflow
    status: DraftStatus
    created_at: datetime
    completed_at: datetime | None
    updated_at: datetime


class DraftResponse(DraftSummary):
    generated_snapshot: dict[str, Any]
    editable_content: dict[str, Any]
    input_snapshot: dict[str, Any]
    stage_errors: dict[str, str]
    model_metadata: dict[str, Any]


class ModelOperation(StrEnum):
    PROFILE = "profile"
    PAIN_POINTS = "pain_points"
    TOPICS = "topics"
    STRUCTURE = "structure"
    TREND_ANALYSIS = "trend_analysis"
    TREND_TOPICS = "trend_topics"
    SIMULATION_PERSONAS = "simulation_personas"
    SIMULATION_REACTION = "simulation_reaction"
    SIMULATION_DEBATE = "simulation_debate"
    SIMULATION_SYNTHESIS = "simulation_synthesis"
    AGENT_CHAT = "agent_chat"
    VIDEO_CREATOR_PROFILE = "video_creator_profile"
    VIDEO_QUALITY_ANALYSIS = "video_quality_analysis"
    INCENTIVE_FIT_ANALYSIS = "incentive_fit_analysis"


class ModelCallRequest(APIModel):
    operation: ModelOperation
    context: dict[str, Any]


class ModelCallResponse(APIModel):
    output: dict[str, Any]
    model_metadata: dict[str, Any]


class SimulationRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIALLY_COMPLETED = "partially_completed"
    FAILED = "failed"


class SimulationRunCreate(APIModel):
    topic_id: str | None = None
    draft_id: str | None = None
    manual_topic: str | None = Field(default=None, min_length=1, max_length=1_000)
    mode: Literal["demo", "live"] = "demo"


class SimulationRunSummary(APIModel):
    id: str
    workspace_id: str
    topic_id: str | None
    draft_id: str | None = None
    status: SimulationRunStatus
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    updated_at: datetime


class SimulationRunResponse(SimulationRunSummary):
    input_snapshot: dict[str, Any]
    persona_definitions: list[dict[str, Any]]
    reaction_results: list[dict[str, Any]]
    debate_results: list[dict[str, Any]]
    synthesis: dict[str, Any]
    stage_errors: dict[str, str]
    model_metadata: dict[str, Any]
