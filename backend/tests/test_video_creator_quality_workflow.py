import asyncio
import json

from fastapi import FastAPI
from test_workspace_api import create_workspace, send

from app.workflows.video_creator_quality import (
    VIDEO_CREATOR_QUALITY_GRAPH_NODE_ORDER,
    FakeVideoCreatorQualityModelProvider,
)


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


def collect(app: FastAPI, run_id: str, stop_after_node: str | None = None) -> list[dict]:
    return asyncio.run(
        app.state.video_workflow_service.collect_events(
            run_id, stop_after_node=stop_after_node
        )
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
    assert (
        completed["stageResults"]["creator_profile"]["creatorProfile"]["creatorType"]
        == "script_driven"
    )
    assert completed["stageResults"]["video_quality"]["videoQuality"]["overallScore"]
    assert (
        completed["stageResults"]["incentive_fit"]["incentiveFit"]["recommendation"]
        == "strong_fit"
    )


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
