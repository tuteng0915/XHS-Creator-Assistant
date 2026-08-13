import json

from app.services.context_access import ContextAccessService


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
                }
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
    assert pack["snapshot"]["sourceRefs"] == [item["assetRef"] for item in pack["items"]]

    items_by_key = {item["key"]: item for item in pack["items"]}
    assert items_by_key["account_profile"]["data"]["accountPositioning"] == (
        "服务准备出国读研的文科生"
    )
    assert items_by_key["analysis_history_overview"]["data"][0]["availableStages"] == [
        "profile"
    ]
    assert items_by_key["media_assets_overview"]["data"][0]["mediaAssetId"] == "media-1"
    assert items_by_key["media_assets_overview"]["data"][0]["derived"][
        "visualSummary"
    ] == "主页强调留学申请路径。"
    assert items_by_key["media_assets_overview"]["data"][0]["derived"][
        "imageUnderstanding"
    ]["creatorSignals"] == ["专业可信"]
    assert items_by_key["media_assets_overview"]["data"][1]["mediaAssetId"] == "media-2"
    assert items_by_key["media_assets_overview"]["data"][1]["derived"][
        "sceneSummary"
    ] == "三段式短剧结构。"
    assert items_by_key["media_assets_overview"]["data"][1]["derived"][
        "videoUnderstanding"
    ]["incentiveFitSignals"] == ["适合激励"]
    assert items_by_key["media_assets_overview"]["data"][1]["derived"][
        "videoPreview"
    ]["frameCount"] == 2
    assert items_by_key["capability_catalog"]["data"]["skills"][0]["skillId"] == (
        "analysis.profile_from_history"
    )

    materials = items_by_key["input_assets_overview"]["data"]
    assert materials[0]["summaryText"] == ("留学内容" * 20)[:12]
    assert materials[0]["charCount"] == len("留学内容" * 20)
    assert materials[1]["preview"] == [{"title": "普通人如何开始数字游民"}]
    assert pack["omitted"][0]["reason"] == "text_summarized_for_workspace_pack"
    assert pack["omitted"][0]["omittedChars"] == len("留学内容" * 20) - 12


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
