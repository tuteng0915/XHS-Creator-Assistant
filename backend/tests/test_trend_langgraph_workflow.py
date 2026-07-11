import asyncio
import json

from fastapi import FastAPI
from test_workspace_api import create_workspace, send

from app.workflows.trend_analysis import (
    TREND_GRAPH_NODE_ORDER,
    FakeTrendAnalysisModelProvider,
)


def upload_trend_csv(app: FastAPI, workspace_id: str) -> dict:
    rows = ["标题,点赞,收藏,标签,正文"]
    for index in range(60):
        likes = index
        collects = 60 - index
        if index == 17:
            likes = 999
            collects = 888
        rows.append(f"热帖{index},{likes},{collects},#趋势,内容片段{index}")
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace_id}/source-materials/trend-csv",
        data={"name": "趋势 CSV", "keyword": "数字游民"},
        files={"file": ("trend.csv", "\n".join(rows).encode(), "text/csv")},
    )
    assert response.status_code == 201
    return response.json()


def create_trend_run(app: FastAPI, mode: str = "demo") -> dict:
    workspace = create_workspace(app)
    csv_material = upload_trend_csv(app, workspace["id"])
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "trend_analysis",
            "trendCsvMaterialId": csv_material["id"],
            "mode": mode,
        },
    )
    assert response.status_code == 201
    return response.json()


def collect(app: FastAPI, run_id: str, stop_after_node: str | None = None) -> list[dict]:
    return asyncio.run(
        app.state.trend_workflow_service.collect_events(
            run_id, stop_after_node=stop_after_node
        )
    )


def test_trend_graph_state_uses_ranked_snapshot_not_complete_csv(app: FastAPI) -> None:
    run = create_trend_run(app)

    assert TREND_GRAPH_NODE_ORDER == [
        "trend_pattern_analysis",
        "pain_point_analysis",
        "topic_generation",
        "finalize",
    ]
    snapshot = run["inputSnapshot"]["trendCsv"]
    assert len(snapshot["rankedPosts"]) == 50
    assert snapshot["rankedPosts"][0]["title"] == "热帖17"
    assert "rawText" not in snapshot

    state = app.state.trend_workflow_service.initial_state_for_run(run["id"])
    dumped = json.dumps(state, ensure_ascii=False)
    assert state["trend_csv_material_id"] == snapshot["materialId"]
    assert "ranked_posts" in state
    assert "热帖17" in dumped
    assert "热帖59" not in dumped


def test_fake_trend_graph_routes_and_persists_successful_stages(app: FastAPI) -> None:
    run = create_trend_run(app)

    events = collect(app, run["id"])

    event_types = [event["data"]["eventType"] for event in events]
    assert event_types.count("stage.succeeded") == 4
    assert events[-1]["data"]["eventType"] == "run.succeeded"

    completed = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert completed["stageResults"]["trend_analysis"]["trendAnalysis"]["themes"]
    assert completed["stageResults"]["pain_points"]["painPoints"]
    assert completed["stageResults"]["topics"]["topics"][0]["whyTrending"]
    assert "structure" not in completed["stageResults"]


def test_parallel_trend_failure_allows_partial_result(app: FastAPI) -> None:
    run = create_trend_run(app)
    app.state.trend_workflow_service.fake_provider = FakeTrendAnalysisModelProvider(
        failures={"trend_analysis"}
    )

    events = collect(app, run["id"])

    assert any(
        event["data"]["eventType"] == "stage.failed"
        and event["stageKey"] == "trend_analysis"
        for event in events
    )
    assert events[-1]["data"]["eventType"] == "run.partial"
    partial = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert partial["status"] == "partially_completed"
    assert "trend_analysis" in partial["stageErrors"]
    assert "pain_points" in partial["stageResults"]
    assert "topics" in partial["stageResults"]


def test_trend_graph_restart_resumes_from_persisted_stage_results(
    app: FastAPI,
) -> None:
    run = create_trend_run(app)
    provider = FakeTrendAnalysisModelProvider()
    app.state.trend_workflow_service.fake_provider = provider

    first_events = collect(app, run["id"], stop_after_node="pain_point_analysis")
    interrupted = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert interrupted["status"] == "running"
    assert "trend_analysis" in interrupted["stageResults"]
    assert "pain_points" in interrupted["stageResults"]
    assert first_events[-1]["data"]["eventType"] == "stage.succeeded"

    restarted_provider = FakeTrendAnalysisModelProvider()
    app.state.trend_workflow_service.fake_provider = restarted_provider
    second_events = collect(app, run["id"])

    assert "trend_analysis" not in restarted_provider.calls
    assert "pain_points" not in restarted_provider.calls
    assert restarted_provider.calls == ["topics"]
    assert second_events[-1]["data"]["eventType"] == "run.succeeded"
