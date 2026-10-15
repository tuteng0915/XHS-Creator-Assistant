from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_serializer,
    model_validator,
)


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
    profile_url: str | None = None
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


class SkillDefinitionUpdate(APIModel):
    display_name: str = Field(min_length=1, max_length=160)
    category: str = Field(min_length=1, max_length=80)
    purpose: str = Field(default="", max_length=2_000)
    trigger_intents: list[str] = Field(default_factory=list, max_length=40)
    required_inputs: list[str] = Field(default_factory=list, max_length=80)
    optional_inputs: list[str] = Field(default_factory=list, max_length=80)
    context_policy: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    artifact_effect: str = Field(default="", max_length=500)
    side_effects: list[str] = Field(default_factory=list, max_length=80)
    failure_mode: str = Field(default="", max_length=300)
    composable_with: list[str] = Field(default_factory=list, max_length=120)
    implementation_refs: list[str] = Field(default_factory=list, max_length=120)
    version: str = Field(default="v1", min_length=1, max_length=40)
    user_notes: str = Field(default="", max_length=10_000)
    expected_updated_at: datetime


class CapabilityDefinitionDiffResponse(APIModel):
    asset_id: str
    asset_type: Literal["skill", "agent", "workflow"]
    stable_id: str
    source: Literal["builtin", "generated"]
    can_revert: bool
    changed_fields: list[str]
    current_definition: dict[str, Any]
    builtin_definition: dict[str, Any] | None = None


class CapabilityDefinitionRevert(APIModel):
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


class SkillDryRunRequest(APIModel):
    input: dict[str, Any] = Field(default_factory=dict)
    mode: Literal["demo", "live"] = "demo"


class SkillDryRunResponse(APIModel):
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


class AgentDefinitionUpdate(APIModel):
    display_name: str = Field(min_length=1, max_length=160)
    purpose: str = Field(default="", max_length=2_000)
    system_prompt: str = Field(default="", max_length=20_000)
    skill_ids: list[str] = Field(default_factory=list, min_length=1, max_length=80)
    default_context_policy: dict[str, Any] = Field(default_factory=dict)
    version: str = Field(default="v1", min_length=1, max_length=40)
    user_notes: str = Field(default="", max_length=10_000)
    expected_updated_at: datetime


class AgentConversationStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ConversationContextTarget(APIModel):
    asset_type: Literal["skill", "agent", "workflow", "topic"]
    asset_id: str = Field(min_length=1, max_length=80)


class AgentConversationCreate(APIModel):
    agent_asset_id: str
    title: str | None = Field(default=None, max_length=160)
    context_target: ConversationContextTarget | None = None


class AgentConversationUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    status: AgentConversationStatus | None = None
    expected_updated_at: datetime


class AgentMessageCreate(APIModel):
    content: str = Field(min_length=1, max_length=20_000)
    mode: Literal["demo", "live"] = "demo"
    client_message_key: str | None = Field(default=None, min_length=1, max_length=120)


class AgentMessageResponse(APIModel):
    id: str
    conversation_id: str
    client_message_key: str | None = None
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
    execution_status: Literal["idle", "running", "failed", "completed"] = "idle"
    context_target: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AgentConversationResponse(AgentConversationSummary):
    messages: list[AgentMessageResponse]


class ContentCollaborationRole(StrEnum):
    """Fixed identities in the product's creator collaboration room."""

    CREATOR = "creator"
    RESEARCH = "research"
    WRITING = "writing"
    REVIEW = "review"
    SYSTEM = "system"


class ContentCollaborationSessionStatus(StrEnum):
    ACTIVE = "active"
    ARCHIVED = "archived"


class ContentCollaborationExecutionStatus(StrEnum):
    IDLE = "idle"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_CREATOR = "waiting_creator"
    COMPLETED = "completed"
    FAILED = "failed"


class ContentCollaborationRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_CREATOR = "waiting_creator"
    COMPLETED = "completed"
    FAILED = "failed"


class ContentCollaborationContextTarget(APIModel):
    """The first collaboration slice is intentionally scoped to one Topic."""

    asset_type: Literal["topic"]
    asset_id: str = Field(min_length=1, max_length=120)


class ContentCollaborationSessionCreate(APIModel):
    assistant_mode: Literal["single_writer", "legacy_team"] = "legacy_team"
    title: str | None = Field(default=None, min_length=1, max_length=160)
    context_target: ContentCollaborationContextTarget
    request_key: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("title", "request_key")
    @classmethod
    def nonblank_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("内容不能为空")
        return value


class ContentCollaborationSessionUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    status: ContentCollaborationSessionStatus | None = None
    expected_revision: int = Field(ge=1)

    @field_validator("title")
    @classmethod
    def nonblank_title(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("标题不能为空")
        return value


class WritingSelection(APIModel):
    model_config = ConfigDict(extra="forbid")

    # Code-point offsets, not the browser's UTF-16 textarea offsets.
    start: int = Field(ge=0, strict=True)
    end: int = Field(ge=1, strict=True)
    text: str = Field(min_length=1, max_length=100_000)

    @model_validator(mode="after")
    def valid_range(self):
        if self.end <= self.start or not self.text.strip():
            raise ValueError("请选择需要改写的正文片段")
        return self


class WritingReaderReference(APIModel):
    model_config = ConfigDict(extra="forbid")

    simulation_id: str = Field(min_length=1, max_length=120)
    stage: Literal["initial", "reply", "interview"]
    message_id: str = Field(min_length=1, max_length=300)
    interview_id: str | None = Field(default=None, min_length=1, max_length=120)

    @model_validator(mode="after")
    def valid_interview(self):
        if (self.stage == "interview") != (self.interview_id is not None):
            raise ValueError("访谈来源需要对应的访谈标识")
        return self


class ContentWritingFocus(APIModel):
    model_config = ConfigDict(extra="forbid")

    expected_updated_at: datetime
    selection: WritingSelection | None = None
    reader_reference: WritingReaderReference | None = None

    @model_validator(mode="after")
    def has_focus(self):
        if self.selection is None and self.reader_reference is None:
            raise ValueError("请提供改写片段或读者意见")
        return self


class CreatorContextReference(APIModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["account_analysis", "audience_analysis", "imported_note"]
    id: str = Field(min_length=1, max_length=120)
    note_id: str | None = Field(default=None, min_length=1, max_length=120)

    @field_validator("id")
    @classmethod
    def nonblank_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("参考记录标识不能为空")
        return value.strip()

    @model_validator(mode="after")
    def valid_note_reference(self):
        if self.kind == "imported_note":
            if self.note_id is None or not self.note_id.strip():
                raise ValueError("原笔记参考需要明确的笔记标识")
            self.note_id = self.note_id.strip()
        elif self.note_id is not None:
            raise ValueError("分析参考不能附带笔记标识")
        return self

    @model_serializer(mode="wrap")
    def serialize_reference(self, handler):
        value = handler(self)
        if self.note_id is None:
            # Keep analysis-only API responses/cache payloads wire-compatible.
            value.pop("note_id", None)
            value.pop("noteId", None)
        return value


class CreatorContextSelection(APIModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["creator-context-selection/v1"] = "creator-context-selection/v1"
    references: list[CreatorContextReference] = Field(default_factory=list, max_length=8)


class ContentCollaborationMessageCreate(APIModel):
    content: str = Field(min_length=1, max_length=8_000)
    recipient: Literal[
        ContentCollaborationRole.RESEARCH,
        ContentCollaborationRole.WRITING,
        ContentCollaborationRole.REVIEW,
    ]
    request_key: str = Field(min_length=1, max_length=120)
    # Collaboration is a quality-facing product surface. It uses the product
    # default Qwen path unless a caller explicitly asks for the local demo.
    mode: Literal["demo", "live"] = "live"
    writing_focus: ContentWritingFocus | None = None
    creator_context_selection: CreatorContextSelection | None = None

    @field_validator("content", "request_key")
    @classmethod
    def nonblank_message_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("内容不能为空")
        return value


class ContentCollaborationMessageResponse(APIModel):
    id: str
    session_id: str
    sequence_no: int
    sender: ContentCollaborationRole
    recipient: ContentCollaborationRole | None = None
    content: str
    reply_to_message_id: str | None = None
    artifact_refs: list[dict[str, Any]] = Field(default_factory=list)
    context_snapshot: dict[str, Any] = Field(default_factory=dict)
    model_metadata: dict[str, Any] = Field(default_factory=dict)
    client_request_key: str | None = None
    created_at: datetime


class ContentCollaborationRunResponse(APIModel):
    id: str
    session_id: str
    trigger_message_id: str | None = None
    request_key: str
    input_snapshot: dict[str, Any]
    graph_state: dict[str, Any]
    status: ContentCollaborationRunStatus
    attempt_count: int
    revision: int
    error_code: str = ""
    error_detail: str = ""
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class ContentCollaborationSessionSummary(APIModel):
    id: str
    workspace_id: str
    title: str
    context_target: ContentCollaborationContextTarget
    assistant_mode: Literal["single_writer", "legacy_team"] = "legacy_team"
    creator_context_selection: CreatorContextSelection | None = None
    context_revision: int = 0
    status: ContentCollaborationSessionStatus
    execution_status: ContentCollaborationExecutionStatus
    revision: int
    failure_code: str = ""
    failure_detail: str = ""
    created_at: datetime
    updated_at: datetime
    last_message_at: datetime | None = None
    completed_at: datetime | None = None


class ContentCollaborationSessionResponse(ContentCollaborationSessionSummary):
    initial_context_snapshot: dict[str, Any] = Field(default_factory=dict)
    messages: list[ContentCollaborationMessageResponse] = Field(default_factory=list)
    runs: list[ContentCollaborationRunResponse] = Field(default_factory=list)


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


class AssetProposalUpdate(APIModel):
    title: str | None = Field(default=None, min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=2_000)
    proposed_action: dict[str, Any] | None = None
    expected_updated_at: datetime


class AssetProposalDiffField(APIModel):
    field: str
    current: Any = None
    proposed: Any = None


class AssetProposalPreviewResponse(APIModel):
    proposal_id: str
    action_type: str
    operation: Literal["create", "update", "unknown"]
    target_asset_type: str
    target_asset_id: str | None = None
    target_stable_id: str | None = None
    changed_fields: list[AssetProposalDiffField] = Field(default_factory=list)
    current_snapshot: dict[str, Any] = Field(default_factory=dict)
    proposed_snapshot: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list[str] = Field(default_factory=list)


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
    call_binding: Literal["", "account", "trend", "video"] = ""
    updated_at: datetime


class WorkflowAssetResponse(WorkflowAssetSummary):
    agent_plan: dict[str, Any]
    user_notes: str


class WorkflowAssetUpdate(APIModel):
    status: WorkflowAssetStatus | None = None
    user_notes: str | None = Field(default=None, max_length=10_000)
    expected_updated_at: datetime


class WorkflowAssetDefinitionUpdate(APIModel):
    display_name: str = Field(min_length=1, max_length=160)
    purpose: str = Field(default="", max_length=2_000)
    entry_agent_ids: list[str] = Field(default_factory=list, min_length=1, max_length=80)
    agent_plan: dict[str, Any] = Field(default_factory=dict)
    artifact_effect: str = Field(default="", max_length=500)
    call_binding: Literal["", "account", "trend", "video"] = ""
    version: str = Field(default="v1", min_length=1, max_length=40)
    user_notes: str = Field(default="", max_length=10_000)
    expected_updated_at: datetime


class WorkflowCallBindingUpdate(APIModel):
    call_binding: Literal["", "account", "trend", "video"]
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
    selected_note_ids: list[str] | None = Field(default=None, min_length=1, max_length=10000)
    analysis_scope: Literal[
        "recent_10", "most_liked_10", "most_engaged_10",
        "last_7_days", "last_30_days", "last_90_days", "all",
    ] = "all"
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


class XhsOfflineImportPackageResponse(XhsOfflineImportResponse):
    media_assets: list[MediaAssetResponse] = Field(default_factory=list)


class XhsCaptureJobStatus(StrEnum):
    PENDING = "pending"
    WAITING_FOR_LOGIN = "waiting_for_login"
    RUNNING = "running"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class XhsCaptureJobCreate(APIModel):
    profile_url: str = Field(min_length=1, max_length=2_000)
    # Zero explicitly requests all visible notes; normal requests stay small.
    note_limit: int = Field(default=10, ge=0, le=1000)
    include_comments: bool = True


class XhsCaptureProgress(APIModel):
    phase: Literal["starting", "login", "notes", "comments", "processing", "completed"] = (
        "starting"
    )
    captured_notes: int = Field(default=0, ge=0)
    captured_comments: int = Field(default=0, ge=0)
    comment_notes_completed: int = Field(default=0, ge=0)
    comment_notes_total: int | None = Field(default=None, ge=0)


class XhsCaptureJobResponse(APIModel):
    id: str
    workspace_id: str
    profile_url: str
    resolved_url: str = ""
    status: XhsCaptureJobStatus
    note_limit: int
    include_comments: bool
    status_message: str = ""
    progress: XhsCaptureProgress = Field(default_factory=XhsCaptureProgress)
    error: str = ""
    result_input_asset_id: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime


class AnalysisRunTransition(APIModel):
    status: AnalysisRunStatus
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class ReviewStatus(StrEnum):
    UNREVIEWED = "unreviewed"
    USEFUL = "useful"
    REJECTED = "rejected"


class RunReviewUpdate(APIModel):
    user_notes: str | None = Field(default=None, max_length=100_000)
    review_status: ReviewStatus | None = None
    expected_updated_at: datetime


class AnalysisStageUpdate(APIModel):
    status: AnalysisRunStatus
    result: dict[str, Any] | list[Any] | str | None = None
    error: str | None = Field(default=None, max_length=10_000)
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class AnalysisRunSummary(APIModel):
    id: str
    origin: str | None = None
    note_count: int | None = Field(default=None, ge=0)
    workspace_id: str
    workflow_type: WorkflowType
    status: AnalysisRunStatus
    user_notes: str = ""
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
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
    body: str | None = Field(default=None, max_length=50_000)
    pinned: bool | None = None
    expected_updated_at: datetime


class TopicResponse(APIModel):
    id: str
    workspace_id: str
    title: str
    angle: str
    body: str = ""
    pinned: bool = False
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


class DraftKind(StrEnum):
    CONTENT_BRIEF = "content_brief"
    CONTENT_STRUCTURE = "content_structure"


class DraftGenerateRequest(APIModel):
    mode: Literal["demo", "live"] = "demo"


class DraftUpdate(APIModel):
    editable_content: dict[str, Any]
    expected_updated_at: datetime


class DraftSummary(APIModel):
    id: str
    workspace_id: str
    topic_id: str
    kind: DraftKind
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
    READER_SELECTION = "reader_selection"
    AUDIENCE_ANALYSIS = "audience_analysis"
    CREATOR_EDIT = "creator_edit"
    PROFILE = "profile"
    PAIN_POINTS = "pain_points"
    TOPICS = "topics"
    CONTENT_BRIEF = "content_brief"
    STRUCTURE = "structure"
    TREND_ANALYSIS = "trend_analysis"
    TREND_TOPICS = "trend_topics"
    SIMULATION_PERSONAS = "simulation_personas"
    SIMULATION_REACTION = "simulation_reaction"
    SIMULATION_DEBATE = "simulation_debate"
    SIMULATION_SYNTHESIS = "simulation_synthesis"
    PANEL_INTERVIEW = "panel_interview"
    AGENT_CHAT = "agent_chat"
    CONTENT_COLLABORATION_TURN = "content_collaboration_turn"
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


class PanelTask(APIModel):
    """Explicit opt-in protocol; absent on legacy requests and snapshots."""
    model_config = ConfigDict(extra="forbid")
    protocol_version: Literal["panel/v1"] = "panel/v1"
    reading_mode: Literal["natural", "guided"] = "natural"
    discussion_enabled: bool = Field(default=True, strict=True)
    focus_questions: list[Annotated[str, Field(strict=True, min_length=1, max_length=300)]] = (
        Field(default_factory=list, max_length=2)
    )

    @field_validator("focus_questions")
    @classmethod
    def nonblank_questions(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("试读问题不能为空")
        return values

    @model_validator(mode="after")
    def questions_match_mode(self):
        if self.reading_mode == "guided" and not self.focus_questions:
            raise ValueError("定向试读需要一到两个问题")
        if self.reading_mode == "natural" and self.focus_questions:
            raise ValueError("自然阅读不携带定向问题")
        return self


class SimulationPersonaOverride(APIModel):
    """A local reading-room adjustment, never a mutation of the saved reader."""
    model_config = ConfigDict(extra="forbid")
    profile: str | None = Field(default=None, strict=True, min_length=1, max_length=4000)
    core_concern: str | None = Field(default=None, strict=True, min_length=1, max_length=2000)
    expression_style: str | None = Field(default=None, strict=True, min_length=1, max_length=2000)

    @field_validator("profile", "core_concern", "expression_style")
    @classmethod
    def nonblank_adjustment(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("本次读者设定不能为空")
        return value

    @model_validator(mode="after")
    def has_adjustment(self):
        if not any((self.profile, self.core_concern, self.expression_style)):
            raise ValueError("请至少调整一项读者设定")
        return self


class AccountNoteSelection(APIModel):
    """An explicit set of imported notes; distinct from the legacy account target."""

    model_config = ConfigDict(extra="forbid")
    source_material_id: str = Field(min_length=1, strict=True)
    selected_note_ids: list[str] = Field(min_length=1)

    @field_validator("source_material_id")
    @classmethod
    def nonblank_source(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请选择笔记所属的账号资料")
        return value

    @field_validator("selected_note_ids")
    @classmethod
    def explicit_note_set(cls, value: list[str]) -> list[str]:
        if any(not note_id.strip() for note_id in value) or len(set(value)) != len(value):
            raise ValueError("请选择不重复的有效笔记")
        # Membership, not click order, defines the target and recommendation identity.
        return sorted(value)


class SimulationRunCreate(APIModel):
    account_note_selection: AccountNoteSelection | None = None
    account_profile_id: str | None = Field(default=None, min_length=1)
    source_material_id: str | None = None
    note_id: str | None = None
    panel_task: PanelTask | None = None
    reader_selection_id: str | None = Field(default=None, min_length=1)
    reader_selection_input_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    simulated_fan_ids: list[str] | None = Field(default=None, min_length=1)
    persona_overrides: dict[str, SimulationPersonaOverride] | None = None
    audience_analysis_id: str | None = None
    topic_id: str | None = None
    draft_id: str | None = None
    manual_topic: str | None = Field(default=None, min_length=1, max_length=1_000)
    mode: Literal["demo", "live"] = "demo"


class SimulationRunSummary(APIModel):
    id: str
    origin: str | None = None
    parent_simulation_id: str | None = None
    workspace_id: str
    topic_id: str | None
    draft_id: str | None = None
    simulation_category: Literal["account", "published_note", "creation"] = "creation"
    target_title: str = ""
    source_material_id: str | None = None
    note_id: str | None = None
    status: SimulationRunStatus
    user_notes: str = ""
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
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
