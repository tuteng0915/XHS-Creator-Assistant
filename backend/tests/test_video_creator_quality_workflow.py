import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from pydantic import ValidationError as PydanticValidationError
from test_workspace_api import create_workspace, send

from app.workflows.video_creator_quality import (
    VIDEO_CREATOR_QUALITY_GRAPH_NODE_ORDER,
    CreatorProfileStageResult,
    FakeVideoCreatorQualityModelProvider,
    IncentiveFitStageResult,
    VideoQualityStageResult,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VIDEO_FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "video_creator_quality"


def create_text_material(
    app: FastAPI, workspace_id: str, material_type: str, content: str
) -> dict:
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace_id}/source-materials",
        json={"type": material_type, "name": material_type, "content": content},
    )
    assert response.status_code == 201
    return response.json()


def create_video_creator_run(app: FastAPI, mode: str = "demo") -> dict:
    workspace = create_workspace(app)
    samples = create_text_material(
        app,
        workspace["id"],
        "video_creator_samples",
        (
            "创作者：@AI短剧研究所\n"
            "样本1：机器人女友觉醒后删除记忆｜赞2.3w｜评论1800｜系列短剧\n"
            "样本2：用AI工具做广告片｜赞3200｜收藏5100｜技术教程\n"
            "运营备注：剧情内容催更多，商单内容互动明显低。"
        ),
    )
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "video_creator_quality",
            "videoCreatorSamplesMaterialId": samples["id"],
            "mode": mode,
        },
    )
    assert response.status_code == 201
    return response.json()


def create_video_creator_run_with_media(app: FastAPI) -> dict:
    workspace = create_workspace(app)
    samples = create_text_material(
        app,
        workspace["id"],
        "video_creator_samples",
        "创作者：@AI短剧研究所\n运营备注：剧情内容催更多。",
    )
    uploaded = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/media-assets/upload",
        data={"type": "image", "name": "主页截图", "purpose": "账号主页视觉参考"},
        files={"file": ("home.png", b"\x89PNG\r\n\x1a\nfake-image", "image/png")},
    )
    assert uploaded.status_code == 201
    image = uploaded.json()
    updated = send(
        app,
        "PATCH",
        f"/api/media-assets/{image['id']}",
        json={
            "derived": {
                "visualSummary": "主页强调连续 AI 短剧角色设定。",
                "imageUnderstanding": {
                    "visualSummary": "主页强调连续 AI 短剧角色设定。",
                    "creatorSignals": ["系列化", "角色驱动"],
                    "risks": [],
                    "uncertainties": [],
                },
                "qwenUnderstanding": {"text": "主页强调连续 AI 短剧角色设定。"},
            },
            "expectedUpdatedAt": image["updatedAt"],
        },
    )
    assert updated.status_code == 200
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "video_creator_quality",
            "videoCreatorSamplesMaterialId": samples["id"],
            "mediaAssetIds": [image["id"]],
            "mode": "demo",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_video_creator_run_from_xhs_profile(app: FastAPI) -> dict:
    workspace = create_workspace(app)
    uploaded = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/media-assets/upload",
        data={"type": "image", "name": "短剧爆款封面", "purpose": "小红书笔记封面"},
        files={"file": ("cover.png", b"\x89PNG\r\n\x1a\nfake-image", "image/png")},
    )
    assert uploaded.status_code == 201
    image = uploaded.json()
    updated = send(
        app,
        "PATCH",
        f"/api/media-assets/{image['id']}",
        json={
            "derived": {
                "visualSummary": "封面突出机器人女友和强冲突标题。",
                "imageUnderstanding": {
                    "visualSummary": "封面突出机器人女友和强冲突标题。",
                    "creatorSignals": ["短剧", "角色驱动"],
                    "risks": [],
                    "uncertainties": [],
                },
            },
            "expectedUpdatedAt": image["updatedAt"],
        },
    )
    assert updated.status_code == 200
    xhs_profile = {
        "schemaVersion": "xhs-creator-profile/v1",
        "source": {
            "platform": "xiaohongshu",
            "fixtureCode": "video-demo",
            "crawler": "MediaCrawler",
        },
        "creator": {
            "displayName": "AI短剧研究所",
            "profileText": "AIGC 短剧创作者，主打连续角色设定。",
        },
        "notes": [
            {
                "noteId": "video-1",
                "type": "video",
                "title": "机器人女友觉醒后删除了我的记忆",
                "desc": "连续短剧第一集，主角设定明确，结尾反转。",
                "tags": ["AIGC", "短剧", "机器人女友"],
                "metrics": {
                    "liked": 23000,
                    "collected": 5100,
                    "comments": 1800,
                    "shares": 900,
                },
                "coverMediaAssetId": image["id"],
                "comments": [
                    {
                        "commentId": "c1",
                        "content": "快更新第二集，剧情很上头",
                        "likeCount": 120,
                        "subCommentCount": 3,
                    }
                ],
            },
            {
                "noteId": "normal-1",
                "type": "normal",
                "title": "用 5 个 AI 工具做一支广告片",
                "desc": "技术教程和工具链拆解。",
                "tags": ["AI工具", "教程"],
                "metrics": {
                    "liked": 3200,
                    "collected": 5100,
                    "comments": 300,
                    "shares": 120,
                },
                "comments": [],
            },
        ],
    }
    xhs_asset = create_text_material(
        app,
        workspace["id"],
        "xhs_creator_profile",
        json.dumps(xhs_profile, ensure_ascii=False),
    )
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "video_creator_quality",
            "xhsCreatorProfileInputAssetId": xhs_asset["id"],
            "mode": "demo",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_minimal_xhs_profile_asset(app: FastAPI, workspace_id: str, name: str) -> dict:
    payload = {
        "schemaVersion": "xhs-creator-profile/v1",
        "source": {"platform": "xiaohongshu", "fixtureCode": name},
        "creator": {"displayName": name, "profileText": f"{name} AIGC 创作者"},
        "notes": [
            {
                "noteId": f"{name}-1",
                "type": "video",
                "title": f"{name} 连续短剧第一集",
                "desc": "剧情反转明确，评论区催更。",
                "tags": ["AIGC", "短剧"],
                "metrics": {"liked": 100, "collected": 20, "comments": 8, "shares": 3},
                "comments": [{"commentId": "c1", "content": "快更下一集"}],
            }
        ],
    }
    return create_text_material(
        app,
        workspace_id,
        "xhs_creator_profile",
        json.dumps(payload, ensure_ascii=False),
    )


def load_xhs_fixture_module():
    module_path = REPO_ROOT / "scripts" / "xhs_mediacrawler_fixture.py"
    spec = importlib.util.spec_from_file_location("xhs_mediacrawler_fixture", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["xhs_mediacrawler_fixture"] = module
    spec.loader.exec_module(module)
    return module


def create_xhs_profile_asset_from_real_fixture(
    app: FastAPI,
    workspace_id: str,
    code: str,
) -> dict:
    module = load_xhs_fixture_module()
    export = module.load_mediacrawler_export(
        REPO_ROOT / "data" / "xhs-fixtures" / code,
        code=code,
    )
    payload = module.build_xhs_creator_profile_payload(export)
    return create_text_material(
        app,
        workspace_id,
        "xhs_creator_profile",
        json.dumps(payload, ensure_ascii=False),
    )


def create_video_creator_run_from_real_xhs_fixture(
    app: FastAPI,
    code: str,
) -> dict:
    workspace = create_workspace(app)
    xhs_asset = create_xhs_profile_asset_from_real_fixture(app, workspace["id"], code)
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "video_creator_quality",
            "xhsCreatorProfileInputAssetId": xhs_asset["id"],
            "mode": "live",
        },
    )
    assert response.status_code == 201
    return response.json()


class QwenVideoFixtureProvider(FakeVideoCreatorQualityModelProvider):
    def __init__(self, outputs: dict[str, Any]) -> None:
        super().__init__()
        self.outputs = outputs

    async def creator_profile(self, **kwargs):
        self.calls.append("creator_profile")
        return self.outputs["creator_profile"]

    async def video_quality(self, **kwargs):
        self.calls.append("video_quality")
        return self.outputs["video_quality"]

    async def incentive_fit(self, **kwargs):
        self.calls.append("incentive_fit")
        return self.outputs["incentive_fit"]


def qwen_video_fixture_outputs(code: str) -> dict[str, Any]:
    fixtures = json.loads(
        (VIDEO_FIXTURE_ROOT / "qwen_stage_outputs.json").read_text(encoding="utf-8")
    )
    return fixtures[code]


def collect(app: FastAPI, run_id: str, stop_after_node: str | None = None) -> list[dict]:
    return asyncio.run(
        app.state.video_workflow_service.collect_events(
            run_id, stop_after_node=stop_after_node
        )
    )


def test_video_creator_quality_scores_accept_qwen_fractional_values() -> None:
    quality = VideoQualityStageResult.model_validate(
        {
            "videoQuality": {
                "overallScore": 0.72,
                "level": "中",
                "dimensionScores": [
                    {"dimension": "visualExecution", "score": "65%", "reason": "封面可用"}
                ],
            }
        }
    )
    fit = IncentiveFitStageResult.model_validate(
        {
            "incentiveFit": {
                "recommendation": "conditional_fit",
                "fitScore": 0.55,
            }
        }
    )

    assert quality.videoQuality.overallScore == 72
    assert quality.videoQuality.dimensionScores[0].score == 65
    assert fit.incentiveFit.fitScore == 55


def test_video_creator_quality_schema_normalizes_common_qwen_labels() -> None:
    profile = CreatorProfileStageResult.model_validate(
        {
            "creatorProfile": {
                "creatorType": "剧本/叙事驱动型",
                "typeConfidence": "high",
            }
        }
    )
    quality = VideoQualityStageResult.model_validate(
        {
            "videoQuality": {
                "overallScore": "68%",
                "level": "medium",
                "dimensionScores": [
                    {
                        "dimension": "scriptAndNarrative",
                        "score": 0.8,
                    }
                ],
            }
        }
    )
    fit = IncentiveFitStageResult.model_validate(
        {
            "incentiveFit": {
                "recommendation": "条件适配",
                "fitScore": "55%",
            }
        }
    )

    assert profile.creatorProfile.creatorType == "script_driven"
    assert profile.creatorProfile.typeConfidence == "高"
    assert quality.videoQuality.overallScore == 68
    assert quality.videoQuality.level == "中"
    assert quality.videoQuality.dimensionScores[0].score == 80
    assert fit.incentiveFit.recommendation == "conditional_fit"
    assert fit.incentiveFit.fitScore == 55


def test_video_creator_quality_recommendation_alias_order_is_stable() -> None:
    assert (
        IncentiveFitStageResult.model_validate(
            {"incentiveFit": {"recommendation": "强适配", "fitScore": 90}}
        ).incentiveFit.recommendation
        == "strong_fit"
    )
    assert (
        IncentiveFitStageResult.model_validate(
            {"incentiveFit": {"recommendation": "弱适配", "fitScore": 35}}
        ).incentiveFit.recommendation
        == "weak_fit"
    )
    assert (
        IncentiveFitStageResult.model_validate(
            {"incentiveFit": {"recommendation": "不适配", "fitScore": 10}}
        ).incentiveFit.recommendation
        == "not_fit"
    )


def test_video_creator_quality_schema_rejects_unknown_recommendation() -> None:
    with pytest.raises(PydanticValidationError):
        IncentiveFitStageResult.model_validate(
            {
                "incentiveFit": {
                    "recommendation": "需要再看看",
                    "fitScore": 50,
                }
            }
        )


def test_video_creator_graph_state_keeps_full_samples_outside_state(
    app: FastAPI,
) -> None:
    run = create_video_creator_run(app)

    assert VIDEO_CREATOR_QUALITY_GRAPH_NODE_ORDER == [
        "creator_profile",
        "video_quality",
        "incentive_fit",
        "finalize",
    ]
    state = app.state.video_workflow_service.initial_state_for_run(run["id"])

    assert state["video_creator_samples_material_id"] == run["inputSnapshot"][
        "videoCreatorSamples"
    ]["materialId"]
    dumped = json.dumps(state, ensure_ascii=False)
    assert "机器人女友" not in dumped
    assert "商单内容互动明显低" not in dumped


def test_video_creator_snapshot_uses_compact_media_asset_context(
    app: FastAPI,
) -> None:
    run = create_video_creator_run_with_media(app)

    media_assets = run["inputSnapshot"]["mediaAssets"]
    assert len(media_assets) == 1
    assert media_assets[0]["name"] == "主页截图"
    assert media_assets[0]["derived"]["visualSummary"] == (
        "主页强调连续 AI 短剧角色设定。"
    )
    assert media_assets[0]["derived"]["imageUnderstanding"]["creatorSignals"] == [
        "系列化",
        "角色驱动",
    ]
    assert media_assets[0]["derived"]["qwenUnderstanding"]["text"] == (
        "主页强调连续 AI 短剧角色设定。"
    )
    assert "storedKey" not in json.dumps(media_assets, ensure_ascii=False)

    state = app.state.video_workflow_service.initial_state_for_run(run["id"])
    assert state["media_asset_ids"] == [media_assets[0]["mediaAssetId"]]
    dumped_state = json.dumps(state, ensure_ascii=False)
    assert "主页强调连续 AI 短剧角色设定" not in dumped_state


def test_video_creator_run_can_use_xhs_profile_evidence_pack(app: FastAPI) -> None:
    run = create_video_creator_run_from_xhs_profile(app)

    snapshot = run["inputSnapshot"]
    evidence_pack = snapshot["videoCreatorEvidencePack"]
    assert snapshot["videoCreatorSamples"]["source"] == "xhs_creator_profile"
    assert snapshot["xhsCreatorProfile"]["name"] == "xhs_creator_profile"
    assert evidence_pack["source"]["type"] == "xhs_creator_profile"
    assert evidence_pack["creator"]["displayName"] == "AI短剧研究所"
    assert evidence_pack["noteStats"]["totalNotes"] == 2
    assert evidence_pack["noteStats"]["videoNotes"] == 1
    assert evidence_pack["videoNotes"][0]["title"] == "机器人女友觉醒后删除了我的记忆"
    assert evidence_pack["scriptDrivenSignals"]
    assert evidence_pack["techExplorationSignals"]
    assert evidence_pack["audienceSignals"][0]["evidenceType"] == "comment"
    assert any(
        "未提供已确认的视频理解结果" in item
        for item in evidence_pack["evidenceLimitations"]
    )
    assert evidence_pack["evidenceScope"]["hasVideoNotes"] is True
    assert evidence_pack["evidenceScope"]["hasVideoUnderstanding"] is False
    assert evidence_pack["evidenceScope"]["hasImageUnderstanding"] is True
    assert evidence_pack["recommendedNextEvidence"]
    assert snapshot["mediaAssets"][0]["name"] == "短剧爆款封面"
    assert evidence_pack["mediaAssetRefs"][0]["hasImageUnderstanding"] is True

    state = app.state.video_workflow_service.initial_state_for_run(run["id"])
    dumped_state = json.dumps(state, ensure_ascii=False)
    assert "机器人女友觉醒" not in dumped_state
    assert state["xhs_creator_profile_material_id"] == snapshot["xhsCreatorProfile"][
        "materialId"
    ]


@pytest.mark.parametrize(
    ("code", "expected_notes", "expected_comments", "expected_video_notes"),
    [
        ("_tt", 4, 26, 0),
        ("QSheep", 20, 137, 1),
    ],
)
def test_video_creator_real_xhs_fixture_runs_with_qwen_stage_outputs(
    app: FastAPI,
    code: str,
    expected_notes: int,
    expected_comments: int,
    expected_video_notes: int,
) -> None:
    run = create_video_creator_run_from_real_xhs_fixture(app, code)
    provider = QwenVideoFixtureProvider(qwen_video_fixture_outputs(code))
    app.state.video_workflow_service.live_provider = provider

    events = collect(app, run["id"])

    assert provider.calls == ["creator_profile", "video_quality", "incentive_fit"]
    assert events[-1]["data"]["eventType"] == "run.succeeded"
    completed = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    evidence_pack = completed["inputSnapshot"]["videoCreatorEvidencePack"]
    assert evidence_pack["source"]["type"] == "xhs_creator_profile"
    assert evidence_pack["source"]["fixtureCode"] == code
    assert evidence_pack["noteStats"]["totalNotes"] == expected_notes
    assert evidence_pack["noteStats"]["commentCount"] == expected_comments
    assert evidence_pack["noteStats"]["videoNotes"] == expected_video_notes
    assert evidence_pack["evidenceScope"]["hasVideoUnderstanding"] is False
    assert "baseDir" not in completed["inputSnapshot"]["xhsCreatorProfile"]["source"]

    creator_profile = completed["stageResults"]["creator_profile"]["creatorProfile"]
    video_quality = completed["stageResults"]["video_quality"]["videoQuality"]
    incentive_fit = completed["stageResults"]["incentive_fit"]["incentiveFit"]
    assert creator_profile["creatorType"] in {
        "script_driven",
        "commercial_driven",
        "tech_exploration_driven",
        "mixed",
        "unclear",
    }
    assert creator_profile["typeConfidence"] in {"高", "中", "低"}
    assert video_quality["level"] in {"高", "中", "低"}
    assert all(
        isinstance(dimension["score"], int)
        for dimension in video_quality["dimensionScores"]
    )
    assert video_quality["cannotAssess"]
    assert any("完整视频" in item for item in video_quality["cannotAssess"])
    assert incentive_fit["recommendation"] in {
        "strong_fit",
        "conditional_fit",
        "weak_fit",
        "not_fit",
    }
    assert isinstance(incentive_fit["fitScore"], int)
    assert incentive_fit["evidenceLimitations"]


def test_video_creator_tt_fixture_preserves_no_video_evidence_boundary(
    app: FastAPI,
) -> None:
    run = create_video_creator_run_from_real_xhs_fixture(app, "_tt")
    app.state.video_workflow_service.live_provider = QwenVideoFixtureProvider(
        qwen_video_fixture_outputs("_tt")
    )

    collect(app, run["id"])

    completed = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    evidence_pack = completed["inputSnapshot"]["videoCreatorEvidencePack"]
    video_quality = completed["stageResults"]["video_quality"]["videoQuality"]
    assert evidence_pack["evidenceScope"]["hasVideoNotes"] is False
    assert any(
        "没有 video 类型笔记" in item
        for item in evidence_pack["evidenceLimitations"]
    )
    assert video_quality["evidenceConfidence"] == "低"
    assert any("间接判断" in item for item in video_quality["cannotAssess"])


def test_video_creator_batch_can_use_multiple_xhs_profiles(app: FastAPI) -> None:
    workspace = create_workspace(app)
    first = create_minimal_xhs_profile_asset(app, workspace["id"], "CreatorA")
    second = create_minimal_xhs_profile_asset(app, workspace["id"], "CreatorB")

    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs/batch",
        json={
            "workflowType": "video_creator_quality",
            "xhsCreatorProfileInputAssetIds": [first["id"], second["id"]],
            "mode": "demo",
        },
    )

    assert response.status_code == 201
    runs = response.json()
    assert len(runs) == 2
    assert runs[0]["workflowType"] == "video_creator_quality"
    assert runs[0]["inputSnapshot"]["xhsCreatorProfile"]["materialId"] == first["id"]
    assert runs[1]["inputSnapshot"]["xhsCreatorProfile"]["materialId"] == second["id"]
    assert runs[0]["inputSnapshot"]["videoCreatorEvidencePack"]["creator"][
        "displayName"
    ] == "CreatorA"
    assert runs[1]["inputSnapshot"]["videoCreatorEvidencePack"]["creator"][
        "displayName"
    ] == "CreatorB"


def test_fake_video_creator_graph_routes_and_persists_successful_stages(
    app: FastAPI,
) -> None:
    run = create_video_creator_run(app)

    events = collect(app, run["id"])

    event_types = [event["data"]["eventType"] for event in events]
    assert event_types.count("stage.succeeded") == 3
    assert events[-1]["data"]["eventType"] == "run.succeeded"

    completed = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    creator_profile = completed["stageResults"]["creator_profile"]["creatorProfile"]
    video_quality = completed["stageResults"]["video_quality"]["videoQuality"]
    incentive_fit = completed["stageResults"]["incentive_fit"]["incentiveFit"]
    assert creator_profile["creatorType"] == "script_driven"
    assert creator_profile["evidenceConfidence"] == "低"
    assert any(
        "未提供已确认的视频理解结果" in item
        for item in creator_profile["evidenceLimitations"]
    )
    assert video_quality["overallScore"]
    assert video_quality["evidenceConfidence"] == "低"
    assert any("镜头调度" in item for item in video_quality["cannotAssess"])
    assert video_quality["recommendedNextEvidence"]
    assert incentive_fit["recommendation"] == "strong_fit"
    assert incentive_fit["evidenceLimitations"]


def test_video_creator_graph_uses_pm_rubric_from_skill_definition(app: FastAPI) -> None:
    class RecordingProvider(FakeVideoCreatorQualityModelProvider):
        def __init__(self) -> None:
            super().__init__()
            self.kwargs_by_stage: dict[str, dict] = {}

        async def video_quality(self, **kwargs):
            self.kwargs_by_stage["video_quality"] = kwargs
            return await super().video_quality(**kwargs)

    run = create_video_creator_run(app, mode="live")
    workspace_id = run["workspaceId"]
    skills = send(app, "GET", f"/api/workspaces/{workspace_id}/skills").json()
    skill = next(item for item in skills if item["skillId"] == "analysis.video_quality")
    detail = send(app, "GET", f"/api/skills/{skill['id']}").json()
    pm_rubric = {
        "qualityDimensions": [
            {
                "dimension": "商业化干扰风险",
                "high": "几乎无商单干扰，内容主线稳定。",
                "medium": "偶有商业化内容，但不破坏主线。",
                "low": "商单明显主导内容选择。",
                "evidenceRequired": "样本标题、正文、评论或运营备注。",
            }
        ],
        "evidenceRules": ["必须区分内容能力和商业动机。"],
    }
    update = send(
        app,
        "PATCH",
        f"/api/skills/{skill['id']}/definition",
        json={
            "displayName": detail["displayName"],
            "category": detail["category"],
            "purpose": detail["purpose"],
            "triggerIntents": detail["triggerIntents"],
            "requiredInputs": detail["requiredInputs"],
            "optionalInputs": detail["optionalInputs"],
            "contextPolicy": {**detail["contextPolicy"], "pmRubric": pm_rubric},
            "outputSchema": detail["outputSchema"],
            "artifactEffect": detail["artifactEffect"],
            "sideEffects": detail["sideEffects"],
            "failureMode": detail["failureMode"],
            "composableWith": detail["composableWith"],
            "implementationRefs": detail["implementationRefs"],
            "version": "pm-rubric-v1",
            "userNotes": detail["userNotes"],
            "expectedUpdatedAt": detail["updatedAt"],
        },
    )
    assert update.status_code == 200
    provider = RecordingProvider()
    app.state.video_workflow_service.live_provider = provider

    collect(app, run["id"])

    assert provider.kwargs_by_stage["video_quality"]["pm_rubric"] == pm_rubric
    completed = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    skill_context = completed["modelMetadata"]["video_quality"]["skillContext"]
    assert skill_context["skillId"] == "analysis.video_quality"
    assert skill_context["skillVersion"] == "pm-rubric-v1"
    assert skill_context["pmRubric"] == pm_rubric


def test_video_creator_stage_failure_allows_partial_result(app: FastAPI) -> None:
    run = create_video_creator_run(app)
    app.state.video_workflow_service.fake_provider = FakeVideoCreatorQualityModelProvider(
        failures={"video_quality"}
    )

    events = collect(app, run["id"])

    assert any(
        event["data"]["eventType"] == "stage.failed"
        and event["stageKey"] == "video_quality"
        for event in events
    )
    assert events[-1]["data"]["eventType"] == "run.partial"
    partial = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert partial["status"] == "partially_completed"
    assert "creator_profile" in partial["stageResults"]
    assert "video_quality" in partial["stageErrors"]
    assert "incentive_fit" in partial["stageResults"]


def test_video_creator_graph_restart_resumes_from_persisted_stage_results(
    app: FastAPI,
) -> None:
    run = create_video_creator_run(app)
    provider = FakeVideoCreatorQualityModelProvider()
    app.state.video_workflow_service.fake_provider = provider

    first_events = collect(app, run["id"], stop_after_node="creator_profile")
    interrupted = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert interrupted["status"] == "running"
    assert "creator_profile" in interrupted["stageResults"]
    assert first_events[-1]["data"]["eventType"] == "stage.succeeded"

    restarted_provider = FakeVideoCreatorQualityModelProvider()
    app.state.video_workflow_service.fake_provider = restarted_provider
    second_events = collect(app, run["id"])

    assert "creator_profile" not in restarted_provider.calls
    assert restarted_provider.calls == ["video_quality", "incentive_fit"]
    assert second_events[-1]["data"]["eventType"] == "run.succeeded"
    completed = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert completed["status"] == "completed"


def test_live_video_creator_graph_uses_injectable_provider_and_validates_output(
    app: FastAPI,
) -> None:
    class InvalidProvider(FakeVideoCreatorQualityModelProvider):
        async def incentive_fit(self, **kwargs):
            self.calls.append("incentive_fit")
            return {"incentiveFit": {"recommendation": "strong_fit"}}

    run = create_video_creator_run(app, mode="live")
    provider = InvalidProvider()
    app.state.video_workflow_service.live_provider = provider

    events = collect(app, run["id"])

    assert provider.calls == ["creator_profile", "video_quality", "incentive_fit"]
    assert any(
        event["data"]["eventType"] == "stage.failed"
        and event["stageKey"] == "incentive_fit"
        for event in events
    )
    result = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert result["status"] == "partially_completed"
    assert (
        result["stageErrors"]["incentive_fit"]
        == "Model response failed structured validation"
    )
