import json

import pytest

from app.errors import ValidationError
from app.services.context_access import ContextAccessService
from app.services.context_contract import (
    WORKSPACE_PACK_SNAPSHOT_VERSION,
    build_context_envelope,
)


class ListRepository:
    def __init__(self, rows):
        self.rows = rows

    def list(self, *_args, **_kwargs):
        return self.rows


class GetListRepository(ListRepository):
    def get(self, _connection, asset_id):
        for row in self.rows:
            if row["id"] == asset_id:
                return row
        raise AssertionError(f"missing asset {asset_id}")


class GetOnlyRepository(GetListRepository):
    def list(self, *_args, **_kwargs):
        return []


def make_service(**overrides):
    repos = {
        "source_repository": ListRepository([]),
        "media_asset_repository": ListRepository([]),
        "analysis_repository": ListRepository([]),
        "topic_repository": ListRepository([]),
        "draft_repository": ListRepository([]),
        "simulation_repository": ListRepository([]),
        "skill_repository": GetListRepository([]),
        "agent_repository": GetListRepository([]),
        "workflow_repository": GetListRepository([]),
    }
    repos.update(overrides)
    return ContextAccessService(**repos)


def test_workspace_pack_contains_broad_product_context_and_omissions() -> None:
    service = make_service(
        source_repository=ListRepository(
            [
                {
                    "id": "material-long",
                    "workspace_id": "workspace-1",
                    "type": "historical_posts",
                    "name": "历史笔记合集",
                    "text_content": "留学内容" * 20,
                    "updated_at": "2026-07-11T10:00:00Z",
                    "keyword": None,
                    "original_filename": None,
                    "row_count": None,
                    "preview_json": "[]",
                },
                {
                    "id": "trend-1",
                    "workspace_id": "workspace-1",
                    "type": "trend_csv",
                    "name": "趋势 CSV",
                    "text_content": None,
                    "updated_at": "2026-07-11T11:00:00Z",
                    "keyword": "数字游民",
                    "original_filename": "trend.csv",
                    "row_count": 2,
                    "preview_json": json.dumps(
                        [{"title": "普通人如何开始数字游民"}], ensure_ascii=False
                    ),
                },
            ]
        ),
        analysis_repository=ListRepository(
            [
                {
                    "id": "run-1",
                    "workflow_type": "account_diagnosis",
                    "status": "completed",
                    "created_at": "2026-07-11T12:00:00Z",
                    "updated_at": "2026-07-11T12:01:00Z",
                    "completed_at": "2026-07-11T12:01:00Z",
                    "stage_results_json": json.dumps({"profile": {"ok": True}}),
                    "stage_errors_json": json.dumps({}),
                }
            ]
        ),
        media_asset_repository=ListRepository(
            [
                {
                    "id": "media-1",
                    "workspace_id": "workspace-1",
                    "type": "image",
                    "name": "主页截图",
                    "purpose": "账号主页视觉定位参考",
                    "source_type": "upload",
                    "original_filename": "home.png",
                    "media_type": "image/png",
                    "byte_size": 128,
                    "metadata_json": json.dumps({"width": None, "height": None}),
                    "derived_json": json.dumps(
                        {
                            "extractedText": "关注留学申请",
                            "visualSummary": "主页强调留学申请路径。",
                            "tags": ["主页"],
                            "imageUnderstanding": {
                                "visualSummary": "主页强调留学申请路径。",
                                "creatorSignals": ["专业可信"],
                            },
                            "qwenUnderstanding": {
                                "text": "主页强调留学申请路径。",
                                "updatedAt": "2026-07-11T11:30:00Z",
                            },
                        },
                        ensure_ascii=False,
                    ),
                    "updated_at": "2026-07-11T11:30:00Z",
                },
                {
                    "id": "media-2",
                    "workspace_id": "workspace-1",
                    "type": "video",
                    "name": "AI短剧样本",
                    "purpose": "视频质量诊断样本",
                    "source_type": "upload",
                    "original_filename": "sample.mp4",
                    "media_type": "video/mp4",
                    "byte_size": 256,
                    "metadata_json": json.dumps(
                        {"durationSeconds": 42, "width": 1080, "height": 1920, "fps": 30}
                    ),
                    "derived_json": json.dumps(
                        {
                            "transcript": "第一幕：AI短剧开场。",
                            "sceneSummary": "三段式短剧结构。",
                            "visualSummary": "竖屏快节奏剪辑。",
                            "audioSummary": "旁白驱动。",
                            "tags": ["AI短剧"],
                            "metrics": {"likes": 1200},
                            "videoUnderstanding": {
                                "sceneSummary": "三段式短剧结构。",
                                "creatorSignals": ["系列化"],
                                "incentiveFitSignals": ["适合激励"],
                            },
                            "videoPreview": {
                                "frameCount": 2,
                                "frames": [
                                    {
                                        "mediaAssetId": "frame-1",
                                        "fileUrl": "/api/media-assets/frame-1/file",
                                        "frameIndex": 1,
                                    }
                                ],
                            },
                        },
                        ensure_ascii=False,
                    ),
                    "updated_at": "2026-07-11T11:40:00Z",
                },
            ]
        ),
        skill_repository=GetListRepository(
            [
                {
                    "id": "skill-1",
                    "workspace_id": "workspace-1",
                    "skill_id": "analysis.profile_from_history",
                    "display_name": "Analyze Account Profile",
                    "category": "analysis",
                    "purpose": "Analyze profile",
                    "required_inputs_json": json.dumps(["historical_posts"]),
                    "optional_inputs_json": json.dumps([]),
                    "artifact_effect": "AnalysisRun.stageResults.profile",
                    "failure_mode": "partial_allowed",
                    "composable_with_json": json.dumps(["topic.generate"]),
                    "status": "enabled",
                    "source": "builtin",
                    "version": "v1",
                    "trigger_intents_json": json.dumps([]),
                    "context_policy_json": json.dumps({}),
                    "output_schema_json": json.dumps({}),
                    "side_effects_json": json.dumps([]),
                    "implementation_refs_json": json.dumps([]),
                    "user_notes": "",
                }
            ]
        ),
    )

    pack = service.build_workspace_pack(
        None,
        workspace={
            "id": "workspace-1",
            "name": "留学账号",
            "account_positioning": "服务准备出国读研的文科生",
            "positioning_version": 3,
            "updated_at": "2026-07-11T10:00:00Z",
        },
        requester={"type": "agent", "id": "capability_maker"},
        purpose="maker_conversation",
        selectors=["workspace"],
        max_summary_chars=12,
    )

    assert pack["workspaceId"] == "workspace-1"
    assert pack["scope"] == "broad"
    assert pack["snapshot"]["contentHash"]
    assert pack["snapshot"]["version"] == WORKSPACE_PACK_SNAPSHOT_VERSION
    assert pack["snapshot"]["sourceRefs"] == [item["assetRef"] for item in pack["items"]]
    assert pack["contextEnvelope"] == build_context_envelope(
        operation="capability_maker",
        purpose="maker_conversation",
        workspace_id="workspace-1",
        items=pack["items"],
        snapshot=pack["snapshot"],
        omissions=pack["omitted"],
    ).model_dump(by_alias=True)

    items_by_key = {item["key"]: item for item in pack["items"]}
    assert items_by_key["account_profile"]["data"]["accountPositioning"] == (
        "服务准备出国读研的文科生"
    )
    assert items_by_key["analysis_history_overview"]["data"][0]["availableStages"] == ["profile"]
    assert items_by_key["media_assets_overview"]["data"][0]["mediaAssetId"] == "media-1"
    assert (
        items_by_key["media_assets_overview"]["data"][0]["derived"]["visualSummary"]
        == "主页强调留学申请路径。"
    )
    assert items_by_key["media_assets_overview"]["data"][0]["derived"]["imageUnderstanding"][
        "creatorSignals"
    ] == ["专业可信"]
    assert items_by_key["media_assets_overview"]["data"][1]["mediaAssetId"] == "media-2"
    assert (
        items_by_key["media_assets_overview"]["data"][1]["derived"]["sceneSummary"]
        == "三段式短剧结构。"
    )
    assert items_by_key["media_assets_overview"]["data"][1]["derived"]["videoUnderstanding"][
        "incentiveFitSignals"
    ] == ["适合激励"]
    assert (
        items_by_key["media_assets_overview"]["data"][1]["derived"]["videoPreview"]["frameCount"]
        == 2
    )
    assert items_by_key["capability_catalog"]["data"]["skills"][0]["skillId"] == (
        "analysis.profile_from_history"
    )

    materials = items_by_key["input_assets_overview"]["data"]
    assert materials[0]["summaryText"] == ("留学内容" * 20)[:12]
    assert materials[0]["charCount"] == len("留学内容" * 20)
    assert materials[1]["preview"] == [{"title": "普通人如何开始数字游民"}]
    assert pack["omitted"][0]["reason"] == "text_summarized_for_workspace_pack"
    assert pack["omitted"][0]["omittedChars"] == len("留学内容" * 20) - 12
    assert pack["contextEnvelope"]["omissions"] == [
        {
            "reason": "text_summarized_for_workspace_pack",
            "assetRef": {
                "workspaceId": "workspace-1",
                "assetType": "input_asset",
                "assetSubType": "historical_posts",
                "assetId": "material-long",
                "role": "historical_posts",
            },
            "omittedChars": len("留学内容" * 20) - 12,
        }
    ]


def test_capability_asset_detail_item_includes_selected_skill_contract() -> None:
    service = make_service(
        skill_repository=GetListRepository(
            [
                {
                    "id": "skill-1",
                    "workspace_id": "workspace-1",
                    "skill_id": "meta.design_skill_asset",
                    "display_name": "Design Skill Asset",
                    "category": "meta",
                    "purpose": "Design bounded skill proposals",
                    "required_inputs_json": json.dumps(["requirement"]),
                    "optional_inputs_json": json.dumps(["current_asset"]),
                    "artifact_effect": "AssetProposal",
                    "failure_mode": "proposal_only",
                    "composable_with_json": json.dumps(["meta.design_agent_asset"]),
                    "status": "enabled",
                    "source": "builtin",
                    "version": "v1",
                    "trigger_intents_json": json.dumps(["create skill"]),
                    "context_policy_json": json.dumps({"scope": "broad"}),
                    "output_schema_json": json.dumps({"type": "proposal"}),
                    "side_effects_json": json.dumps(["creates proposal"]),
                    "implementation_refs_json": json.dumps(["CapabilityMaker"]),
                    "user_notes": "优先复用已有能力",
                }
            ]
        )
    )

    item = service.capability_asset_detail_item(
        None,
        workspace_id="workspace-1",
        context_target={"assetType": "skill", "assetId": "skill-1"},
    )

    assert item is not None
    assert item["key"] == "selected_capability_asset"
    assert item["selector"] == "selected_skill_detail"
    assert item["data"]["skillId"] == "meta.design_skill_asset"
    assert item["data"]["triggerIntents"] == ["create skill"]
    assert item["data"]["contextPolicy"] == {"scope": "broad"}
    assert item["data"]["userNotes"] == "优先复用已有能力"


@pytest.mark.parametrize(
    ("asset_type", "repository_name", "row"),
    [
        (
            "skill",
            "skill_repository",
            {
                "id": "skill-1",
                "workspace_id": "workspace-1",
                "skill_id": "skill-id",
                "display_name": "Skill",
                "category": "meta",
                "purpose": "purpose",
                "required_inputs_json": "[]",
                "optional_inputs_json": "[]",
                "artifact_effect": "proposal",
                "failure_mode": "proposal_only",
                "composable_with_json": "[]",
                "status": "enabled",
                "source": "builtin",
                "version": "v1",
                "trigger_intents_json": "[]",
                "context_policy_json": "{}",
                "output_schema_json": "{}",
                "side_effects_json": "[]",
                "implementation_refs_json": "[]",
                "user_notes": "",
            },
        ),
        (
            "agent",
            "agent_repository",
            {
                "id": "agent-1",
                "workspace_id": "workspace-1",
                "agent_id": "agent-id",
                "display_name": "Agent",
                "purpose": "purpose",
                "skill_ids_json": "[]",
                "default_context_policy_json": "{}",
                "status": "enabled",
                "source": "builtin",
                "version": "v1",
                "system_prompt": "system",
                "user_notes": "",
            },
        ),
        (
            "workflow",
            "workflow_repository",
            {
                "id": "workflow-1",
                "workspace_id": "workspace-1",
                "workflow_id": "workflow-id",
                "display_name": "Workflow",
                "purpose": "purpose",
                "entry_agent_ids_json": "[]",
                "artifact_effect": "proposal",
                "agent_plan_json": "{}",
                "status": "enabled",
                "source": "builtin",
                "version": "v1",
                "user_notes": "",
            },
        ),
    ],
)
def test_capability_detail_keeps_workspace_identity_in_context_envelope(
    asset_type: str,
    repository_name: str,
    row: dict,
) -> None:
    service = make_service(**{repository_name: GetListRepository([row])})
    item = service.capability_asset_detail_item(
        None,
        workspace_id="workspace-1",
        context_target={"assetType": asset_type, "assetId": row["id"]},
    )

    assert item is not None
    assert item["workspace_id"] == "workspace-1"
    pack = service.build_workspace_pack(
        None,
        workspace={
            "id": "workspace-1",
            "name": "账号",
            "account_positioning": "定位",
            "positioning_version": 1,
            "updated_at": "2026-10-06T10:00:00Z",
        },
        requester={"agentId": "creator"},
        purpose="test_selected_capability",
        selectors=[],
        deep_items=[item],
    )
    source = next(
        source
        for source in pack["contextEnvelope"]["evidenceSources"]
        if source["assetRef"]["assetId"] == row["id"]
    )
    assert source["assetRef"]["workspaceId"] == "workspace-1"


def test_capability_asset_detail_item_rejects_cross_workspace_target() -> None:
    service = make_service(
        skill_repository=GetListRepository(
            [
                {
                    "id": "skill-foreign",
                    "workspace_id": "other-workspace",
                    "skill_id": "meta.design_skill_asset",
                    "display_name": "Design Skill Asset",
                    "category": "meta",
                    "purpose": "Design bounded skill proposals",
                    "required_inputs_json": json.dumps([]),
                    "optional_inputs_json": json.dumps([]),
                    "artifact_effect": "AssetProposal",
                    "failure_mode": "proposal_only",
                    "composable_with_json": json.dumps([]),
                    "status": "enabled",
                    "source": "builtin",
                    "version": "v1",
                    "trigger_intents_json": json.dumps([]),
                    "context_policy_json": json.dumps({}),
                    "output_schema_json": json.dumps({}),
                    "side_effects_json": json.dumps([]),
                    "implementation_refs_json": json.dumps([]),
                    "user_notes": "",
                }
            ]
        )
    )

    assert (
        service.capability_asset_detail_item(
            None,
            workspace_id="workspace-1",
            context_target={"assetType": "skill", "assetId": "skill-foreign"},
        )
        is None
    )


def test_agent_conversation_context_freezes_selected_topic_and_fact_source() -> None:
    source_run = {
        "id": "analysis-1",
        "workspace_id": "workspace-1",
        "input_snapshot_json": json.dumps(
            {"historicalPosts": {"content": "作者的原始笔记证据"}}, ensure_ascii=False
        ),
    }
    topic = {
        "id": "topic-1",
        "workspace_id": "workspace-1",
        "title": "当前选题",
        "body": "正在编辑的正文",
        "angle": "当前角度",
        "updated_at": "2026-10-06T10:00:00Z",
        "generated_snapshot_json": json.dumps({"pendingSuggestions": ["补充例子"]}),
        "source_analysis_run_id": "analysis-1",
    }
    service = make_service(
        topic_repository=GetOnlyRepository([topic]),
        analysis_repository=GetOnlyRepository([source_run]),
    )
    pack = service.build_agent_conversation_context(
        None,
        workspace={
            "id": "workspace-1",
            "name": "账号",
            "account_positioning": "定位",
            "positioning_version": 1,
            "updated_at": "2026-10-06T10:00:00Z",
        },
        agent={"agent_id": "creator", "display_name": "创作助手"},
        conversation_id="conversation-1",
        context_target={"assetType": "topic", "assetId": "topic-1"},
    )
    assert pack["canvasTopic"]["id"] == "topic-1"
    assert pack["canvasTopic"]["pendingSuggestions"] == ["补充例子"]
    assert pack["creatorFactSources"] == [
        {"id": "analysis-original-posts", "text": "作者的原始笔记证据"}
    ]
    sources = pack["contextEnvelope"]["evidenceSources"]
    assert {(source["assetRef"]["assetType"], source["assetRef"]["role"])
            for source in sources} >= {
        ("topic", "selected_topic"),
        ("analysis_run", "creator_fact_source"),
    }


def test_agent_conversation_context_omits_fact_source_from_another_workspace() -> None:
    topic = {
        "id": "topic-1",
        "workspace_id": "workspace-1",
        "title": "当前选题",
        "body": "正在编辑的正文",
        "angle": "当前角度",
        "updated_at": "2026-10-06T10:00:00Z",
        "generated_snapshot_json": "{}",
        "source_analysis_run_id": "analysis-foreign",
    }
    foreign_run = {
        "id": "analysis-foreign",
        "workspace_id": "workspace-other",
        "input_snapshot_json": json.dumps(
            {"historicalPosts": {"content": "不应泄露的另一账号笔记"}},
            ensure_ascii=False,
        ),
    }
    service = make_service(
        topic_repository=GetOnlyRepository([topic]),
        analysis_repository=GetOnlyRepository([foreign_run]),
    )

    pack = service.build_agent_conversation_context(
        None,
        workspace={
            "id": "workspace-1",
            "name": "账号",
            "account_positioning": "定位",
            "positioning_version": 1,
            "updated_at": "2026-10-06T10:00:00Z",
        },
        agent={"agent_id": "creator", "display_name": "创作助手"},
        conversation_id="conversation-1",
        context_target={"assetType": "topic", "assetId": "topic-1"},
    )

    assert pack["creatorFactSources"] == []
    assert "不应泄露" not in json.dumps(pack, ensure_ascii=False)
    assert not any(
        source["assetRef"]["assetId"] == "analysis-foreign"
        for source in pack["contextEnvelope"]["evidenceSources"]
    )


def test_agent_conversation_context_rejects_topic_from_another_workspace() -> None:
    service = make_service(
        topic_repository=GetOnlyRepository(
            [{"id": "topic-foreign", "workspace_id": "other-workspace"}]
        )
    )
    with pytest.raises(ValidationError, match="另一个账号"):
        service.build_agent_conversation_context(
            None,
            workspace={
                "id": "workspace-1",
                "name": "账号",
                "account_positioning": "定位",
                "positioning_version": 1,
                "updated_at": "2026-10-06T10:00:00Z",
            },
            agent={"agent_id": "creator", "display_name": "创作助手"},
            conversation_id="conversation-1",
            context_target={"assetType": "topic", "assetId": "topic-foreign"},
        )


def test_context_envelope_keeps_purpose_evidence_and_source_versions_explicit() -> None:
    envelope = build_context_envelope(
        operation="reader_selection",
        purpose="select_readers_for_current_topic",
        workspace_id="workspace-1",
        items=[
            {
                "assetRef": {
                    "workspaceId": "workspace-1",
                    "assetType": "topic",
                    "assetId": "topic-1",
                    "role": "simulation_target",
                },
                "selector": "saved_topic_body",
                "contentHash": "target-hash",
                "data": {"updatedAt": "2026-10-06T10:00:00Z"},
            },
            {
                "assetRef": {
                    "workspaceId": "workspace-1",
                    "assetType": "simulated_fan",
                    "assetId": "fan-1",
                    "role": "reader_candidate",
                },
                "selector": "active_saved_readers",
                "contentHash": "reader-hash",
                "data": {"version": "fan/v2"},
            },
        ],
        snapshot={
            "version": "reader-selection/v1",
            "createdAt": "2026-10-06T10:01:00Z",
            "contentHash": "snapshot-hash",
        },
    )

    data = envelope.model_dump(by_alias=True)
    assert data["contractVersion"] == "context-envelope/v1"
    assert data["operation"] == "reader_selection"
    assert data["purpose"] == "select_readers_for_current_topic"
    assert data["snapshot"] == {
        "version": "reader-selection/v1",
        "createdAt": "2026-10-06T10:01:00Z",
        "contentHash": "snapshot-hash",
        "sourceRefs": [
            {
                "workspaceId": "workspace-1",
                "assetType": "topic",
                "assetId": "topic-1",
                "role": "simulation_target",
                "assetSubType": None,
            },
            {
                "workspaceId": "workspace-1",
                "assetType": "simulated_fan",
                "assetId": "fan-1",
                "role": "reader_candidate",
                "assetSubType": None,
            },
        ],
    }
    assert [source["sourceVersion"] for source in data["evidenceSources"]] == [
        "2026-10-06T10:00:00Z",
        "fan/v2",
    ]
