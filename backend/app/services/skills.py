from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from app.db.database import SQLiteDatabase
from app.errors import ConflictError, ValidationError
from app.models import (
    CapabilityDefinitionDiffResponse,
    CapabilityDefinitionRevert,
    SkillDefinitionUpdate,
    SkillDryRunRequest,
    SkillDryRunResponse,
    SkillInvokeRequest,
    SkillInvokeResponse,
    SkillResponse,
    SkillSummary,
    SkillUpdate,
)
from app.repositories.skills import SkillRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import as_iso, utc_now

if TYPE_CHECKING:
    from app.services.qwen_media import QwenMediaService


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
        display_name="Save Creator Dossier Historical Posts",
        category="input_asset",
        purpose=(
            "Persist reusable Historical Posts as a child asset of the creator "
            "dossier for account diagnosis."
        ),
        required_inputs=["workspace_id", "historical_posts_text"],
        output_schema={"type": "InputAsset", "asset_type": "historical_posts"},
        artifact_effect="InputAsset.historical_posts",
        side_effects=["creates or updates input asset"],
        failure_mode="atomic",
        composable_with=["analysis.profile_from_history"],
        implementation_refs=[
            "SourceMaterialService.create_text",
            "SourceMaterialService.update",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="source.save_comments",
        display_name="Save Creator Dossier Comment Samples",
        category="input_asset",
        purpose=(
            "Persist reusable Comment Samples as child assets of the creator "
            "dossier for pain-point analysis."
        ),
        required_inputs=["workspace_id", "comments_text"],
        output_schema={"type": "InputAsset", "asset_type": "comments"},
        artifact_effect="InputAsset.comments",
        side_effects=["creates or updates input asset"],
        failure_mode="atomic",
        composable_with=["analysis.pain_points_from_comments"],
        implementation_refs=[
            "SourceMaterialService.create_text",
            "SourceMaterialService.update",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="source.upload_trend_csv",
        display_name="Upload Trend Data",
        category="input_asset",
        purpose="Persist uploaded trend data input assets with controlled server storage.",
        required_inputs=["workspace_id", "keyword", "csv_or_tsv_file"],
        output_schema={"type": "InputAsset", "asset_type": "trend_csv"},
        artifact_effect="InputAsset.trend_csv",
        side_effects=["stores upload on disk", "stores metadata in SQLite"],
        failure_mode="atomic",
        composable_with=["trend.rank_posts"],
        implementation_refs=["SourceMaterialService.create_csv"],
    ),
    BuiltinSkillDefinition(
        skill_id="input_asset.format_profile",
        display_name="Format Creator Dossier Account Profile",
        category="input_asset",
        purpose=(
            "Turn pasted raw creator/account notes into an editable Account "
            "Profile child-asset draft inside the creator dossier, without "
            "saving it automatically."
        ),
        required_inputs=["raw_text", "target_asset_type"],
        output_schema={
            "type": "FormattedInputAssetDraft",
            "asset_type": "account_profile",
            "fields": ["name", "content", "notes"],
        },
        artifact_effect="Draft InputAsset.account_profile",
        side_effects=["returns draft only", "requires explicit save before persistence"],
        failure_mode="draft_only",
        composable_with=["source.save_historical_posts", "analysis.profile_from_history"],
        implementation_refs=["InputAssetFormatterAgent", "AgentConversationService"],
    ),
    BuiltinSkillDefinition(
        skill_id="input_asset.format_historical_posts",
        display_name="Format Creator Dossier Historical Posts",
        category="input_asset",
        purpose=(
            "Turn pasted post lists, titles, or metrics into an editable "
            "Historical Posts child-asset draft inside the creator dossier."
        ),
        required_inputs=["raw_text", "target_asset_type"],
        output_schema={
            "type": "FormattedInputAssetDraft",
            "asset_type": "historical_posts",
            "fields": ["name", "content", "notes"],
        },
        artifact_effect="Draft InputAsset.historical_posts",
        side_effects=["returns draft only", "requires explicit save before persistence"],
        failure_mode="draft_only",
        composable_with=["source.save_historical_posts", "analysis.profile_from_history"],
        implementation_refs=["InputAssetFormatterAgent", "AgentConversationService"],
    ),
    BuiltinSkillDefinition(
        skill_id="input_asset.format_comments",
        display_name="Format Creator Dossier Comment Samples",
        category="input_asset",
        purpose=(
            "Turn pasted comment blocks into one-comment-per-line editable "
            "Comment Samples child-asset drafts inside the creator dossier."
        ),
        required_inputs=["raw_text", "target_asset_type"],
        output_schema={
            "type": "FormattedInputAssetDraft",
            "asset_type": "comments",
            "fields": ["name", "content", "notes"],
        },
        artifact_effect="Draft InputAsset.comments",
        side_effects=["returns draft only", "requires explicit save before persistence"],
        failure_mode="draft_only",
        composable_with=["source.save_comments", "analysis.pain_points_from_comments"],
        implementation_refs=["InputAssetFormatterAgent", "AgentConversationService"],
    ),
    BuiltinSkillDefinition(
        skill_id="input_asset.format_trend_csv_brief",
        display_name="Format Trend Data Brief",
        category="input_asset",
        purpose=(
            "Extract a trend keyword and import notes from pasted trend "
            "descriptions while keeping CSV upload explicit."
        ),
        required_inputs=["raw_text", "target_asset_type"],
        output_schema={
            "type": "FormattedInputAssetDraft",
            "asset_type": "trend_csv",
            "fields": ["keyword", "notes"],
        },
        artifact_effect="Draft InputAsset.trend_csv metadata",
        side_effects=["returns draft only", "does not create uploaded file"],
        failure_mode="draft_only",
        composable_with=["source.upload_trend_csv", "trend.rank_posts"],
        implementation_refs=["InputAssetFormatterAgent", "AgentConversationService"],
    ),
    BuiltinSkillDefinition(
        skill_id="input_asset.format_video_creator_samples",
        display_name="Format Creator Dossier Video Creation Samples",
        category="input_asset",
        purpose=(
            "Turn pasted video creator observations into editable Video Creation "
            "Samples child-asset drafts inside the creator dossier."
        ),
        required_inputs=["raw_text", "target_asset_type"],
        output_schema={
            "type": "FormattedInputAssetDraft",
            "asset_type": "video_creator_samples",
            "fields": ["name", "content", "notes"],
        },
        artifact_effect="Draft InputAsset.video_creator_samples",
        side_effects=["returns draft only", "requires explicit save before persistence"],
        failure_mode="draft_only",
        composable_with=["analysis.video_creator_profile"],
        implementation_refs=["InputAssetFormatterAgent", "AgentConversationService"],
    ),
    BuiltinSkillDefinition(
        skill_id="input_asset.format_xhs_creator_profile",
        display_name="Format XHS Creator Dossier Profile",
        category="input_asset",
        purpose=(
            "Turn pasted Xiaohongshu crawler/export text into an editable "
            "XHS Creator Profile draft as the structured root of a creator "
            "dossier, without saving it automatically."
        ),
        required_inputs=["raw_text", "target_asset_type"],
        output_schema={
            "type": "FormattedInputAssetDraft",
            "asset_type": "xhs_creator_profile",
            "fields": ["name", "content", "notes"],
        },
        artifact_effect="Draft InputAsset.xhs_creator_profile",
        side_effects=["returns draft only", "requires explicit save before persistence"],
        failure_mode="draft_only",
        composable_with=["analysis.profile_from_xhs_creator_profile"],
        implementation_refs=["InputAssetFormatterAgent", "AgentConversationService"],
    ),
    BuiltinSkillDefinition(
        skill_id="media.understand_image",
        display_name="Understand Image-text Asset",
        category="media",
        purpose=(
            "Use Qwen vision models to describe, OCR, or inspect an image from a "
            "public image URL or saved image media asset."
        ),
        required_inputs=["prompt"],
        optional_inputs=["imageUrl", "mediaAssetId"],
        output_schema={
            "type": "ImageUnderstandingResult",
            "root": "imageUnderstanding",
            "fields": [
                "visualSummary",
                "extractedText",
                "styleTags",
                "creatorSignals",
                "risks",
                "uncertainties",
            ],
        },
        artifact_effect="MediaAsset.derived draft or standalone interpretation",
        side_effects=["calls Qwen vision API in live mode"],
        failure_mode="atomic",
        composable_with=[
            "analysis.video_quality",
            "draft.generate_structure",
            "media.generate_image",
        ],
        implementation_refs=[
            "QwenMediaService.understand_image",
            "qwen-vl-plus/qwen-vl-max compatible chat.completions",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="media.understand_video",
        display_name="Understand Video Asset",
        category="media",
        purpose=(
            "Use Qwen vision models to inspect a video represented by public video "
            "or frame URLs. Local uploaded videos are understood through extracted "
            "preview frames, not direct video upload."
        ),
        required_inputs=["prompt"],
        optional_inputs=["videoUrl", "videoFrameUrls", "mediaAssetId"],
        output_schema={
            "type": "VideoUnderstandingResult",
            "root": "videoUnderstanding",
            "fields": [
                "sceneSummary",
                "transcript",
                "visualSummary",
                "audioSummary",
                "qualitySignals",
                "creatorSignals",
                "incentiveFitSignals",
                "risks",
                "uncertainties",
            ],
        },
        artifact_effect="MediaAsset.derived draft or standalone interpretation",
        side_effects=["calls Qwen vision API in live mode"],
        failure_mode="atomic",
        composable_with=[
            "analysis.video_creator_profile",
            "analysis.video_quality",
            "analysis.incentive_fit",
        ],
        implementation_refs=[
            "QwenMediaService.understand_video",
            "qwen-vl-plus/qwen-vl-max compatible chat.completions",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="media.generate_image",
        display_name="Generate Image-text Asset",
        category="media",
        purpose=(
            "Generate an image through Qwen/DashScope image generation and persist "
            "the returned media URL as a workspace media asset."
        ),
        required_inputs=["prompt"],
        optional_inputs=["name", "purpose", "size", "n"],
        output_schema={"type": "MediaAsset", "asset_type": "image"},
        artifact_effect="MediaAsset.image",
        side_effects=["calls DashScope async task API", "creates media asset record"],
        failure_mode="atomic",
        composable_with=["media.understand_image", "draft.generate_structure"],
        implementation_refs=[
            "QwenMediaService.generate_image",
            "DashScope image-synthesis async task",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="media.generate_video",
        display_name="Generate Video Asset",
        category="media",
        purpose=(
            "Generate a short video through Qwen/DashScope video generation and "
            "persist the returned media URL as a workspace media asset."
        ),
        required_inputs=["prompt"],
        optional_inputs=[
            "name",
            "purpose",
            "size",
            "resolution",
            "ratio",
            "duration",
            "promptExtend",
            "watermark",
        ],
        output_schema={"type": "MediaAsset", "asset_type": "video"},
        artifact_effect="MediaAsset.video",
        side_effects=["calls DashScope async task API", "creates media asset record"],
        failure_mode="atomic",
        composable_with=["media.understand_video", "analysis.video_quality"],
        implementation_refs=[
            "QwenMediaService.generate_video",
            "DashScope video-synthesis async task",
        ],
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
        purpose="Extract audience pain points from selected Comment Samples input assets.",
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
        skill_id="analysis.video_creator_profile",
        display_name="Profile AIGC Video Creator",
        category="analysis",
        purpose=(
            "Classify an AIGC video creator by motivation and content operating "
            "pattern from collected video samples."
        ),
        required_inputs=["positioning_snapshot", "video_creator_evidence_pack"],
        optional_inputs=[
            "video_creator_samples_material_id",
            "xhs_creator_profile_material_id",
            "media_asset_ids",
        ],
        context_policy={
            "allowed_fields": [
                "positioning",
                "videoCreatorEvidencePack",
                "videoCreatorSamples",
                "mediaAssets",
            ],
            "disallowed_fields": ["full_workspace", "unrelated input assets"],
            "pmRubric": {
                "creatorTypes": [
                    {
                        "type": "剧本驱动型",
                        "fitForIncentive": "高",
                        "rule": (
                            "连续发布剧情/角色/世界观内容，评论区出现催更、追剧情、"
                            "讨论人物关系等信号。"
                        ),
                    },
                    {
                        "type": "商单驱动型",
                        "fitForIncentive": "低",
                        "rule": (
                            "内容以品牌植入、商品转化或短期商业任务为主，"
                            "非商单内容弱或不稳定。"
                        ),
                    },
                    {
                        "type": "技术探索驱动型",
                        "fitForIncentive": "中",
                        "rule": (
                            "主要展示工具链、模型实验或制作流程，需要结合更新稳定性"
                            "和受众反馈判断。"
                        ),
                    },
                ],
                "evidenceRules": [
                    "必须引用标题、正文、互动、评论、封面或已保存媒体理解中的具体证据。",
                    "没有真实视频理解时，不得声称看过镜头、剪辑、口型、配音或完整视频。",
                ],
            },
        },
        output_schema={"root": "creatorProfile"},
        artifact_effect="AnalysisRun.stageResults.creator_profile",
        side_effects=["writes stage result"],
        failure_mode="partial_allowed",
        composable_with=[
            "analysis.video_quality",
            "analysis.incentive_fit",
        ],
        implementation_refs=[
            "ModelOperation.VIDEO_CREATOR_PROFILE",
            "VideoCreatorQualityWorkflowService.creator_profile",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="analysis.video_quality",
        display_name="Analyze AIGC Video Quality",
        category="analysis",
        purpose=(
            "Score and explain AIGC video quality across narrative, visuals, "
            "technique use, originality, consistency, audience fit, and repeatability."
        ),
        required_inputs=[
            "positioning_snapshot",
            "video_creator_evidence_pack",
            "creatorProfile",
        ],
        optional_inputs=[
            "video_creator_samples_material_id",
            "xhs_creator_profile_material_id",
            "media_asset_ids",
        ],
        context_policy={
            "allowed_fields": [
                "positioning",
                "videoCreatorEvidencePack",
                "videoCreatorSamples",
                "mediaAssets",
                "creatorProfile",
            ],
            "disallowed_fields": ["full_workspace", "unrelated input assets"],
            "pmRubric": {
                "qualityDimensions": [
                    {
                        "dimension": "叙事完整度",
                        "high": "有清晰冲突、转折和结尾钩子，适合系列化。",
                        "medium": "有主题但结构松散，缺少强钩子或连续性。",
                        "low": "只有概念展示，缺少故事推进或观看理由。",
                        "evidenceRequired": "标题、正文、评论反馈、视频理解或封面线索。",
                    },
                    {
                        "dimension": "画面完成度",
                        "high": "风格统一、主体清晰、构图稳定，封面/画面能支撑内容承诺。",
                        "medium": "整体可用但存在风格跳变、信息密度不足或封面弱。",
                        "low": "画面粗糙、主体混乱或明显影响可信度。",
                        "evidenceRequired": "封面、截图、视频理解或用户手动样本观察。",
                    },
                    {
                        "dimension": "AIGC 技术使用水平",
                        "high": "技术服务叙事或表达，瑕疵不干扰观看。",
                        "medium": "有技术亮点但稳定性一般。",
                        "low": "技术瑕疵成为主要观感问题。",
                        "evidenceRequired": "视频理解、样本观察或评论中关于技术效果的反馈。",
                    },
                    {
                        "dimension": "系列化潜力",
                        "high": "有可复用人物、世界观、栏目或任务模板。",
                        "medium": "主题可延展但尚未形成稳定栏目。",
                        "low": "主要依赖单点热点或一次性概念。",
                        "evidenceRequired": "近期发布结构、重复栏目、评论催更或收藏转发。",
                    },
                ],
                "evidenceRules": [
                    "score 必须和 evidenceConfidence 匹配；证据弱时不得给出过高确定性。",
                    "cannotAssess 必须列出因为缺少真实视频/图片理解而无法可靠判断的维度。",
                ],
            },
        },
        output_schema={"root": "videoQuality"},
        artifact_effect="AnalysisRun.stageResults.video_quality",
        side_effects=["writes stage result"],
        failure_mode="partial_allowed",
        composable_with=["analysis.incentive_fit"],
        implementation_refs=[
            "ModelOperation.VIDEO_QUALITY_ANALYSIS",
            "VideoCreatorQualityWorkflowService.video_quality",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="analysis.incentive_fit",
        display_name="Assess Incentive Program Fit",
        category="analysis",
        purpose=(
            "Decide whether an AIGC video creator fits an incentive plan based on "
            "creator profile and video quality diagnosis."
        ),
        required_inputs=["positioning_snapshot", "creatorProfile", "videoQuality"],
        context_policy={
            "allowed_fields": ["positioning", "creatorProfile", "videoQuality"],
            "disallowed_fields": ["raw video samples when structured diagnosis exists"],
            "pmRubric": {
                "incentiveRules": [
                    {
                        "signal": "剧本驱动 + 系列化潜力高",
                        "interpretation": "适合用连续更新任务、流量扶持和阶段奖励放大。",
                        "operatorAction": "设计 4 周连续更新激励，要求保留同一世界观或栏目。",
                    },
                    {
                        "signal": "商单占比高 + 非商单互动弱",
                        "interpretation": "激励计划较难改变其内容行为。",
                        "operatorAction": "谨慎纳入，优先谈商业合作或限定非商单内容任务。",
                    },
                    {
                        "signal": "技术探索强 + 更新不稳定",
                        "interpretation": "需要先判断其是否愿意产品化持续创作。",
                        "operatorAction": "给工具资源、样例任务和轻量试运行，不直接给高额激励。",
                    },
                ],
                "evidenceRules": [
                    "recommendation 必须区分适合、谨慎、暂不适合，并说明条件。",
                    "risks 必须包含证据不足、更新稳定性和商业动机相关风险。",
                ],
            },
        },
        output_schema={"root": "incentiveFit"},
        artifact_effect="AnalysisRun.stageResults.incentive_fit",
        side_effects=["writes stage result"],
        failure_mode="partial_allowed",
        composable_with=[],
        implementation_refs=[
            "ModelOperation.INCENTIVE_FIT_ANALYSIS",
            "VideoCreatorQualityWorkflowService.incentive_fit",
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
        composable_with=[
            "topic.select",
            "topic.refine_to_brief",
            "draft.generate_structure",
        ],
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
        composable_with=[
            "topic.refine_to_brief",
            "draft.generate_structure",
            "simulation.normalize_target",
        ],
        implementation_refs=["TopicService.select"],
    ),
    BuiltinSkillDefinition(
        skill_id="topic.refine_to_brief",
        display_name="Generate Creative Brief",
        category="creative_output",
        purpose=(
            "Turn a selected Topic into a persistent creative brief before writing "
            "or structure generation."
        ),
        required_inputs=["topic_id", "positioning_snapshot"],
        optional_inputs=["compact_analysis_context"],
        context_policy={
            "allowed_fields": ["positioning", "topic", "background"],
            "disallowed_fields": ["raw_input_assets", "full_workspace"],
        },
        output_schema={"root": "brief"},
        artifact_effect="Draft(kind=content_brief)",
        side_effects=[
            "creates creative brief artifact",
            "stores generated snapshot and editable content",
        ],
        failure_mode="atomic",
        composable_with=[
            "draft.generate_structure_from_brief",
            "draft.edit",
            "simulation.normalize_target",
        ],
        implementation_refs=[
            "DraftGenerationService.generate_brief_from_topic",
            "ModelOperation.CONTENT_BRIEF",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="draft.generate_structure",
        display_name="Generate Content Structure",
        category="creative_output",
        purpose="Generate a persistent content structure directly from a selected topic.",
        required_inputs=["topic_id", "positioning_snapshot"],
        optional_inputs=["compact_analysis_context"],
        context_policy={
            "allowed_fields": ["positioning", "topic", "background"],
            "disallowed_fields": ["raw_input_assets", "full_workspace"],
        },
        output_schema={"root": "structure"},
        artifact_effect="Draft(kind=content_structure)",
        side_effects=["creates draft", "stores generated snapshot and editable content"],
        failure_mode="atomic",
        composable_with=["draft.edit", "simulation.normalize_target"],
        implementation_refs=[
            "DraftGenerationService.generate_from_topic",
            "ModelOperation.STRUCTURE",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="draft.generate_structure_from_brief",
        display_name="Generate Structure From Brief",
        category="creative_output",
        purpose=(
            "Generate a persistent content structure from a user-confirmed creative "
            "brief, preserving the brief in the structure input snapshot."
        ),
        required_inputs=["content_brief_draft_id", "positioning_snapshot"],
        optional_inputs=["compact_analysis_context"],
        context_policy={
            "allowed_fields": ["positioning", "topic", "sourceBrief", "background"],
            "disallowed_fields": ["raw_input_assets", "full_workspace"],
        },
        output_schema={"root": "structure"},
        artifact_effect="Draft(kind=content_structure)",
        side_effects=[
            "creates content structure artifact",
            "stores source brief reference in input snapshot",
        ],
        failure_mode="atomic",
        composable_with=["draft.edit", "simulation.normalize_target"],
        implementation_refs=[
            "DraftGenerationService.generate_structure_from_brief",
            "ModelOperation.STRUCTURE",
        ],
    ),
    BuiltinSkillDefinition(
        skill_id="draft.edit",
        display_name="Edit Creative Output",
        category="creative_output",
        purpose=(
            "Persist user edits to a creative brief or content structure without "
            "modifying generated snapshot."
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
            "disallowed_fields": ["raw_input_assets", "full_workspace"],
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
                "creator dossier overview",
                "input asset overview",
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
                "creator dossier overview",
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
                "creator dossier overview",
                "input asset overview",
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
                "callBinding",
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
        qwen_media_service: QwenMediaService | None = None,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.qwen_media_service = qwen_media_service

    def list(self, workspace_id: str) -> list[SkillSummary]:
        self._sync_builtin_skills(workspace_id)
        with self.database.read() as connection:
            rows = self.repository.list(connection, workspace_id)
        return [SkillSummary.model_validate(row) for row in rows]

    def get(self, skill_asset_id: str) -> SkillResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, skill_asset_id)
        return self._to_response(row)

    def get_by_skill_id(self, workspace_id: str, skill_id: str) -> SkillResponse:
        self._sync_builtin_skills(workspace_id)
        with self.database.read() as connection:
            row = self.repository.get_by_skill_id(
                connection,
                workspace_id=workspace_id,
                skill_id=skill_id,
            )
        if row is None:
            raise ValidationError("Skill not found")
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

    def update_definition(
        self, skill_asset_id: str, payload: SkillDefinitionUpdate
    ) -> SkillResponse:
        self._validate_definition_payload(payload)
        with self.database.transaction() as connection:
            current = self.repository.get(connection, skill_asset_id)
            if current["updated_at"] != as_iso(payload.expected_updated_at):
                raise ConflictError("Skill changed since it was loaded")
            row = self.repository.replace_definition(
                connection,
                skill_asset_id=skill_asset_id,
                display_name=payload.display_name,
                category=payload.category,
                purpose=payload.purpose,
                trigger_intents_json=json.dumps(
                    payload.trigger_intents, ensure_ascii=False
                ),
                required_inputs_json=json.dumps(
                    payload.required_inputs, ensure_ascii=False
                ),
                optional_inputs_json=json.dumps(
                    payload.optional_inputs, ensure_ascii=False
                ),
                context_policy_json=json.dumps(
                    payload.context_policy, ensure_ascii=False
                ),
                output_schema_json=json.dumps(
                    payload.output_schema, ensure_ascii=False
                ),
                artifact_effect=payload.artifact_effect,
                side_effects_json=json.dumps(payload.side_effects, ensure_ascii=False),
                failure_mode=payload.failure_mode,
                composable_with_json=json.dumps(
                    payload.composable_with, ensure_ascii=False
                ),
                implementation_refs_json=json.dumps(
                    payload.implementation_refs, ensure_ascii=False
                ),
                version=payload.version,
                now=utc_now(),
            )
            row = self.repository.update(
                connection,
                skill_asset_id=skill_asset_id,
                status=None,
                user_notes=payload.user_notes,
                expected_updated_at=row["updated_at"],
                now=utc_now(),
            )
        return self._to_response(row)

    def definition_diff(self, skill_asset_id: str) -> CapabilityDefinitionDiffResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, skill_asset_id)
        current_definition = self._definition_dict_from_row(row)
        builtin = self._builtin_definition_by_skill_id(row["skill_id"])
        builtin_definition = (
            self._definition_dict_from_builtin(builtin) if builtin is not None else None
        )
        changed_fields = self._changed_definition_fields(
            current_definition, builtin_definition
        )
        return CapabilityDefinitionDiffResponse(
            asset_id=row["id"],
            asset_type="skill",
            stable_id=row["skill_id"],
            source=row["source"],
            can_revert=row["source"] == "generated" and builtin_definition is not None,
            changed_fields=changed_fields,
            current_definition=current_definition,
            builtin_definition=builtin_definition,
        )

    def revert_definition(
        self, skill_asset_id: str, payload: CapabilityDefinitionRevert
    ) -> SkillResponse:
        with self.database.transaction() as connection:
            current = self.repository.get(connection, skill_asset_id)
            builtin = self._builtin_definition_by_skill_id(current["skill_id"])
            if builtin is None:
                raise ValidationError("No builtin definition is available for this skill")
            row = self.repository.revert_definition_to_builtin(
                connection,
                skill_asset_id=skill_asset_id,
                display_name=builtin.display_name,
                category=builtin.category,
                purpose=builtin.purpose,
                trigger_intents_json=json.dumps(
                    builtin.trigger_intents, ensure_ascii=False
                ),
                required_inputs_json=json.dumps(
                    builtin.required_inputs, ensure_ascii=False
                ),
                optional_inputs_json=json.dumps(
                    builtin.optional_inputs, ensure_ascii=False
                ),
                context_policy_json=json.dumps(
                    builtin.context_policy, ensure_ascii=False
                ),
                output_schema_json=json.dumps(
                    builtin.output_schema, ensure_ascii=False
                ),
                artifact_effect=builtin.artifact_effect,
                side_effects_json=json.dumps(builtin.side_effects, ensure_ascii=False),
                failure_mode=builtin.failure_mode,
                composable_with_json=json.dumps(
                    builtin.composable_with, ensure_ascii=False
                ),
                implementation_refs_json=json.dumps(
                    builtin.implementation_refs, ensure_ascii=False
                ),
                version=builtin.version,
                definition_hash=self._definition_hash(builtin),
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    @staticmethod
    def _validate_definition_payload(payload: SkillDefinitionUpdate) -> None:
        list_fields = {
            "trigger_intents": payload.trigger_intents,
            "required_inputs": payload.required_inputs,
            "optional_inputs": payload.optional_inputs,
            "side_effects": payload.side_effects,
            "composable_with": payload.composable_with,
            "implementation_refs": payload.implementation_refs,
        }
        for field_name, values in list_fields.items():
            for value in values:
                if not value.strip():
                    raise ValidationError(f"{field_name} cannot contain blank items")
        if not payload.category.strip():
            raise ValidationError("Skill category is required")

    @staticmethod
    def _builtin_definition_by_skill_id(
        skill_id: str,
    ) -> BuiltinSkillDefinition | None:
        return next(
            (definition for definition in BUILTIN_SKILLS if definition.skill_id == skill_id),
            None,
        )

    @staticmethod
    def _definition_dict_from_builtin(
        definition: BuiltinSkillDefinition,
    ) -> dict[str, Any]:
        return {
            "displayName": definition.display_name,
            "category": definition.category,
            "purpose": definition.purpose,
            "triggerIntents": definition.trigger_intents,
            "requiredInputs": definition.required_inputs,
            "optionalInputs": definition.optional_inputs,
            "contextPolicy": definition.context_policy,
            "outputSchema": definition.output_schema,
            "artifactEffect": definition.artifact_effect,
            "sideEffects": definition.side_effects,
            "failureMode": definition.failure_mode,
            "composableWith": definition.composable_with,
            "implementationRefs": definition.implementation_refs,
            "version": definition.version,
        }

    @staticmethod
    def _definition_dict_from_row(row: dict) -> dict[str, Any]:
        return {
            "displayName": row["display_name"],
            "category": row["category"],
            "purpose": row["purpose"],
            "triggerIntents": json.loads(row["trigger_intents_json"]),
            "requiredInputs": json.loads(row["required_inputs_json"]),
            "optionalInputs": json.loads(row["optional_inputs_json"]),
            "contextPolicy": json.loads(row["context_policy_json"]),
            "outputSchema": json.loads(row["output_schema_json"]),
            "artifactEffect": row["artifact_effect"],
            "sideEffects": json.loads(row["side_effects_json"]),
            "failureMode": row["failure_mode"],
            "composableWith": json.loads(row["composable_with_json"]),
            "implementationRefs": json.loads(row["implementation_refs_json"]),
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

    def invoke(
        self, skill_asset_id: str, payload: SkillInvokeRequest
    ) -> SkillInvokeResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, skill_asset_id)
        if row["status"] != "enabled":
            raise ValidationError("Skill is disabled")
        skill_id = row["skill_id"]
        if skill_id.startswith("media."):
            if self.qwen_media_service is None:
                raise ValidationError("Qwen media service is not configured")
            output = self.qwen_media_service.invoke(
                workspace_id=row["workspace_id"],
                skill_id=skill_id,
                input_payload=payload.input,
                mode=payload.mode,
            )
            return SkillInvokeResponse(
                skill_asset_id=row["id"],
                skill_id=skill_id,
                status="completed",
                output=output,
                model_metadata={
                    "provider": "qwen" if payload.mode == "live" else "demo",
                    "mode": payload.mode,
                    "operation": "skill.invoke",
                    "implementation": "qwen_media_service",
                },
            )
        if not skill_id.startswith("input_asset.format_"):
            raise ValidationError(
                "This version only supports direct invocation for input asset "
                "formatter and media skills"
            )
        output = self._invoke_input_asset_formatter(skill_id, payload.input)
        return SkillInvokeResponse(
            skill_asset_id=row["id"],
            skill_id=skill_id,
            status="completed",
            output=output,
            model_metadata={
                "provider": "code",
                "mode": payload.mode,
                "operation": "skill.invoke",
                "implementation": "deterministic_input_asset_formatter",
            },
        )

    def dry_run(
        self, skill_asset_id: str, payload: SkillDryRunRequest
    ) -> SkillDryRunResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, skill_asset_id)
        if row["status"] != "enabled":
            raise ValidationError("Skill is disabled")
        skill_id = row["skill_id"]
        output = self._dry_run_output(skill_id, payload.input)
        return SkillDryRunResponse(
            skill_asset_id=row["id"],
            skill_id=skill_id,
            status="completed",
            output=output,
            model_metadata={
                "provider": "deterministic",
                "mode": payload.mode,
                "operation": "skill.dry_run",
                "writes": [],
            },
        )

    def _dry_run_output(
        self, skill_id: str, input_payload: dict[str, Any]
    ) -> dict[str, Any]:
        if skill_id.startswith("input_asset.format_"):
            return self._invoke_input_asset_formatter(skill_id, input_payload)
        if skill_id.startswith("media."):
            return {
                "dryRun": True,
                "assetType": "media",
                "skillId": skill_id,
                "inputKeys": sorted(input_payload.keys()),
                "note": "dry-run 不调用 Qwen media API，也不创建 MediaAsset。",
            }
        mapping: dict[str, dict[str, Any]] = {
            "analysis.profile_from_history": {
                "profile": {
                    "pillars": ["定位表达", "经验复盘"],
                    "titleFormulas": [
                        {"formula": "明确对象 + 具体问题", "examples": ["留学生如何避坑"]}
                    ],
                    "hookStyles": ["直接指出痛点"],
                    "viralStructure": {
                        "name": "痛点-拆解-建议",
                        "steps": ["指出问题", "解释原因", "给出行动"],
                    },
                    "voiceFingerprint": ["具体", "克制"],
                    "contrast": {
                        "winners": [],
                        "losers": [],
                        "winFactors": ["选题具体"],
                        "loseFactors": [],
                        "takeaways": ["继续强化明确对象"],
                    },
                }
            },
            "analysis.pain_points_from_comments": {
                "painPoints": [
                    {
                        "theme": "决策焦虑",
                        "intensity": "高",
                        "count": 3,
                        "evidence": ["不知道怎么判断"],
                    }
                ]
            },
            "analysis.trend_patterns": {
                "trendAnalysis": {
                    "themes": [
                        {
                            "theme": "趋势主题",
                            "count": 5,
                            "topPost": "高互动样例",
                            "engagement": "高",
                            "summary": "dry-run 主题摘要",
                        }
                    ],
                    "viralPatterns": ["具体场景切入"],
                    "opportunityWindows": ["供给不足的细分角度"],
                }
            },
            "analysis.pain_points_from_trend_posts": {
                "painPoints": [
                    {
                        "theme": "趋势下的真实困惑",
                        "intensity": "中",
                        "count": 2,
                        "evidence": ["评论/标题中的困惑信号"],
                    }
                ]
            },
            "topic.generate_from_account_diagnosis": {
                "topics": [
                    {
                        "title": "dry-run 账号诊断选题",
                        "angle": "从最高频痛点切入",
                        "pain": "决策焦虑",
                        "whyFit": "匹配账号结构和表达风格",
                    }
                ],
                "titles": [{"topic": "dry-run 账号诊断选题", "variants": ["标题 A", "标题 B"]}],
            },
            "topic.generate_from_trend_analysis": {
                "topics": [
                    {
                        "title": "dry-run 热点选题",
                        "angle": "把热点转为账号可讲角度",
                        "pain": "趋势困惑",
                        "whyFit": "与定位匹配",
                        "whyTrending": "当前互动集中",
                    }
                ],
                "titles": [{"topic": "dry-run 热点选题", "variants": ["热点标题 A", "热点标题 B"]}],
            },
            "topic.refine_to_brief": {
                "brief": {
                    "topicTitle": "dry-run 创作 Brief",
                    "refinedAngle": "明确对象和交付",
                    "targetReader": "目标读者",
                    "readerPain": "核心痛点",
                    "contentPromise": "读完能做出判断",
                    "corePoint": "核心论点",
                    "formatRecommendation": "图文笔记",
                    "openingHook": "直接提问",
                    "argumentPath": ["问题", "判断", "建议"],
                    "materialNeeds": ["历史案例"],
                    "titleDirections": ["对象 + 问题"],
                    "cta": "评论补充",
                    "risks": ["不要泛化"],
                    "revisionSuggestions": ["补充例子"],
                }
            },
            "draft.generate_structure": {
                "structure": {
                    "topicChosen": "dry-run 内容结构",
                    "outline": [
                        {"sec": "开头", "ct": "提出具体痛点"},
                        {"sec": "主体", "ct": "拆解原因与判断标准"},
                    ],
                    "reuse": "痛点-标准-行动建议",
                }
            },
            "draft.generate_structure_from_brief": {
                "structure": {
                    "topicChosen": "dry-run Brief 转结构",
                    "outline": [{"sec": "承接 Brief", "ct": "保留内容承诺"}],
                    "reuse": "Brief 到结构的可复用转换",
                }
            },
            "simulation.derive_personas": {
                "personas": [
                    {
                        "id": "p1",
                        "name": "谨慎决策者",
                        "profile": "需要可信证据",
                        "coreConcern": "是否可靠",
                        "contentPreference": "具体案例",
                    }
                ]
            },
            "simulation.initial_reactions": {
                "reaction": {
                    "personaId": "p1",
                    "stance": "犹豫",
                    "quote": "需要更多证据。",
                    "concerns": ["信息是否充分"],
                    "opportunities": ["补充案例会更可信"],
                }
            },
            "simulation.debate_responses": {
                "debateResponse": {
                    "personaId": "p1",
                    "response": "看到其他反馈后仍建议补充证据。",
                    "changedMind": False,
                    "newConcerns": [],
                    "strongerSignals": ["案例需求强"],
                }
            },
            "simulation.synthesize": {
                "synthesis": {
                    "verdict": "值得继续打磨",
                    "mainResistance": "证据不足",
                    "strongestAngle": "用真实案例降低判断成本",
                    "contentAdjustments": ["补充对比"],
                    "riskWarnings": ["避免过度承诺"],
                }
            },
            "analysis.video_creator_profile": {
                "creatorProfile": {
                    "creatorType": "unclear",
                    "typeConfidence": "低",
                    "summary": "dry-run 不基于真实视频判断。",
                    "audiencePositioning": "待确认",
                    "contentPillars": [],
                    "motivationSignals": [],
                    "evidence": [],
                    "uncertainties": ["需要真实视频或封面理解"],
                    "evidenceScope": {"dryRun": True},
                    "evidenceConfidence": "低",
                    "evidenceLimitations": ["未执行模型调用"],
                    "recommendedNextEvidence": ["补充视频链接、封面或转写"],
                }
            },
            "analysis.video_quality": {
                "videoQuality": {
                    "overallScore": 0,
                    "level": "低",
                    "dimensionScores": [],
                    "strengths": [],
                    "weaknesses": [],
                    "evidence": [],
                    "evidenceScope": {"dryRun": True},
                    "evidenceConfidence": "低",
                    "evidenceLimitations": ["未执行模型调用"],
                    "cannotAssess": ["visualExecution", "aigcTechniqueUse"],
                    "recommendedNextEvidence": ["补充真实视频理解结果"],
                }
            },
            "analysis.incentive_fit": {
                "incentiveFit": {
                    "recommendation": "conditional_fit",
                    "fitScore": 50,
                    "rationale": "dry-run 仅验证 contract。",
                    "conditions": ["补充证据后再判断"],
                    "risks": ["证据不足"],
                    "operatorActions": ["收集样本"],
                    "programMatch": {"bestProgramType": "待定", "why": "", "avoid": ""},
                    "evidenceScope": {"dryRun": True},
                    "evidenceConfidence": "低",
                    "evidenceLimitations": ["未执行模型调用"],
                    "recommendedNextEvidence": ["补充真实创作者证据包"],
                }
            },
        }
        output = mapping.get(skill_id)
        if output is None:
            raise ValidationError("This skill does not support dry-run yet")
        return output

    def _invoke_input_asset_formatter(
        self, skill_id: str, input_payload: dict[str, Any]
    ) -> dict[str, Any]:
        raw_text = str(input_payload.get("rawText") or input_payload.get("raw_text") or "")
        if not raw_text.strip():
            raise ValidationError("rawText is required")
        lines = self._normalize_pasted_lines(raw_text)
        if not lines:
            raise ValidationError("rawText did not contain usable content")
        target_type = self._formatter_target_type(skill_id)
        if target_type == "account_profile":
            return {
                "assetType": target_type,
                "name": self._generated_input_asset_name(target_type, lines),
                "content": "\n".join(lines),
                "notes": "已按账号概况整理为可编辑草稿；保存前请确认事实准确。",
            }
        if target_type == "historical_posts":
            metric_tokens = ["赞", "藏", "评", "爆", "平", "差", "收藏", "评论"]
            content = "\n".join(
                line
                if any(token in line for token in metric_tokens)
                else f"{line} ｜ 数据待补充"
                for line in lines
            )
            return {
                "assetType": target_type,
                "name": self._generated_input_asset_name(target_type, lines),
                "content": content,
                "notes": "已整理为一行一条历史笔记；缺少互动数据的行已标注“数据待补充”。",
            }
        if target_type == "comments":
            return {
                "assetType": target_type,
                "name": self._generated_input_asset_name(target_type, lines),
                "content": "\n".join(lines),
                "notes": "已整理为一行一条评论样本。",
            }
        if target_type == "trend_csv":
            trend_tokens = ["关键词", "话题", "主题"]
            keyword_line = next(
                (line for line in lines if any(token in line for token in trend_tokens)),
                lines[0],
            )
            keyword = (
                keyword_line.split(":", 1)[-1]
                .split("：", 1)[-1]
                .replace("，", "")
                .replace(",", "")
                .replace("。", "")
                .strip()
                or keyword_line
            )
            return {
                "assetType": target_type,
                "name": self._generated_input_asset_name(target_type, lines, keyword[:80]),
                "keyword": keyword[:80],
                "notes": "已提取趋势关键词；趋势数据仍需要上传 CSV / TSV 文件后才能保存。",
            }
        if target_type == "xhs_creator_profile":
            return {
                "assetType": target_type,
                "name": self._generated_input_asset_name(target_type, lines),
                "content": "\n".join(lines),
                "notes": (
                    "已整理为小红书创作者主页草稿；建议优先使用 "
                    "xhs local importer 生成的 xhs-creator-profile/v1 JSON。"
                ),
            }
        return {
            "assetType": target_type,
            "name": self._generated_input_asset_name(target_type, lines),
            "content": "\n".join(lines),
            "notes": "已整理为视频创作样本草稿；保存前请确认观察来自真实样本记录。",
        }

    @staticmethod
    def _formatter_target_type(skill_id: str) -> str:
        mapping = {
            "input_asset.format_profile": "account_profile",
            "input_asset.format_historical_posts": "historical_posts",
            "input_asset.format_comments": "comments",
            "input_asset.format_trend_csv_brief": "trend_csv",
            "input_asset.format_video_creator_samples": "video_creator_samples",
            "input_asset.format_xhs_creator_profile": "xhs_creator_profile",
        }
        target_type = mapping.get(skill_id)
        if target_type is None:
            raise ValidationError(f"Unsupported formatter skill: {skill_id}")
        return target_type

    @staticmethod
    def _normalize_pasted_lines(value: str) -> list[str]:
        stripped_quotes = "\"“”'‘’"
        normalized: list[str] = []
        for raw_line in value.splitlines():
            line = raw_line.strip()
            while line and (line[0] in "-*•0123456789.、 "):
                line = line[1:].strip()
            line = line.strip(stripped_quotes).strip()
            if line:
                normalized.append(line)
        return normalized

    @staticmethod
    def _generated_input_asset_name(
        target_type: str, lines: list[str], keyword: str | None = None
    ) -> str:
        first = lines[0] if lines else ""
        if target_type == "account_profile":
            account = ""
            for marker in ["账号:", "账号：", "@"]:
                if marker in first:
                    account = first.split(marker, 1)[-1].split("｜", 1)[0].strip()
                    break
            return f"{account.replace('@', '')} 账号概况" if account else "整理后的账号概况"
        if target_type == "historical_posts":
            return "整理后的历史笔记合集"
        if target_type == "comments":
            return "整理后的评论样本合集"
        if target_type == "trend_csv":
            return f"{keyword or '整理后的趋势'} 趋势数据"
        if target_type == "video_creator_samples":
            creator = ""
            for marker in ["创作者:", "创作者：", "@"]:
                if marker in first:
                    creator = first.split(marker, 1)[-1].split("｜", 1)[0].strip()
                    break
            return (
                f"{creator.replace('@', '')} 视频创作样本"
                if creator
                else "整理后的视频创作样本"
            )
        if target_type == "xhs_creator_profile":
            return "整理后的小红书创作者主页"
        return "整理后的输入素材"

    def _sync_builtin_skills(self, workspace_id: str) -> None:
        now = utc_now()
        with self.database.transaction() as connection:
            self.workspace_repository.get(connection, workspace_id)
            for definition in BUILTIN_SKILLS:
                definition_hash = self._definition_hash(definition)
                existing = self.repository.get_by_skill_id(
                    connection,
                    workspace_id=workspace_id,
                    skill_id=definition.skill_id,
                )
                payload = {
                    "workspace_id": workspace_id,
                    "skill_id": definition.skill_id,
                    "display_name": definition.display_name,
                    "category": definition.category,
                    "purpose": definition.purpose,
                    "trigger_intents_json": json.dumps(
                        definition.trigger_intents, ensure_ascii=False
                    ),
                    "required_inputs_json": json.dumps(
                        definition.required_inputs, ensure_ascii=False
                    ),
                    "optional_inputs_json": json.dumps(
                        definition.optional_inputs, ensure_ascii=False
                    ),
                    "context_policy_json": json.dumps(
                        definition.context_policy, ensure_ascii=False
                    ),
                    "output_schema_json": json.dumps(
                        definition.output_schema, ensure_ascii=False
                    ),
                    "artifact_effect": definition.artifact_effect,
                    "side_effects_json": json.dumps(
                        definition.side_effects, ensure_ascii=False
                    ),
                    "failure_mode": definition.failure_mode,
                    "composable_with_json": json.dumps(
                        definition.composable_with, ensure_ascii=False
                    ),
                    "implementation_refs_json": json.dumps(
                        definition.implementation_refs, ensure_ascii=False
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
                            skill_asset_id=existing["id"],
                            display_name=payload["display_name"],
                            category=payload["category"],
                            purpose=payload["purpose"],
                            trigger_intents_json=payload["trigger_intents_json"],
                            required_inputs_json=payload["required_inputs_json"],
                            optional_inputs_json=payload["optional_inputs_json"],
                            context_policy_json=payload["context_policy_json"],
                            output_schema_json=payload["output_schema_json"],
                            artifact_effect=payload["artifact_effect"],
                            side_effects_json=payload["side_effects_json"],
                            failure_mode=payload["failure_mode"],
                            composable_with_json=payload["composable_with_json"],
                            implementation_refs_json=payload[
                                "implementation_refs_json"
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
    def _definition_hash(definition: BuiltinSkillDefinition) -> str:
        encoded = json.dumps(
            asdict(definition), ensure_ascii=False, sort_keys=True
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

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
