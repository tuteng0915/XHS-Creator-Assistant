import asyncio
import json

from fastapi import FastAPI
from test_workspace_api import create_workspace, send

from app.workflows.account_diagnosis import (
    ACCOUNT_GRAPH_NODE_ORDER,
    FakeAccountDiagnosisModelProvider,
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


def create_account_run(app: FastAPI, mode: str = "demo") -> dict:
    workspace = create_workspace(app)
    historical = create_text_material(
        app,
        workspace["id"],
        "historical_posts",
        "二本逆袭G5?别再被这种标题骗了｜赞1.4k 藏980｜爆",
    )
    comments = create_text_material(
        app,
        workspace["id"],
        "comments",
        "中介那部分太真实了，我现在就纠结要不要DIY。",
    )
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "account_diagnosis",
            "historicalPostsMaterialId": historical["id"],
            "commentsMaterialId": comments["id"],
            "mode": mode,
        },
    )
    assert response.status_code == 201
    return response.json()


def collect(app: FastAPI, run_id: str, stop_after_node: str | None = None) -> list[dict]:
    return asyncio.run(
        app.state.account_workflow_service.collect_events(
            run_id, stop_after_node=stop_after_node
        )
    )


def test_account_graph_state_keeps_full_source_material_outside_state(
    app: FastAPI,
) -> None:
    run = create_account_run(app)

    assert ACCOUNT_GRAPH_NODE_ORDER == [
        "profile_analysis",
        "topic_generation",
        "finalize",
    ]
    state = app.state.account_workflow_service.initial_state_for_run(run["id"])

    assert state["historical_posts_material_id"] == run["inputSnapshot"][
        "historicalPosts"
    ]["materialId"]
    assert state["comments_material_id"] == run["inputSnapshot"]["comments"][
        "materialId"
    ]
    assert "二本逆袭" not in json.dumps(state, ensure_ascii=False)
    assert "纠结要不要DIY" not in json.dumps(state, ensure_ascii=False)


def test_fake_account_graph_routes_and_persists_successful_stages(
    app: FastAPI,
) -> None:
    run = create_account_run(app)
    events = collect(app, run["id"])

    event_types = [event["data"]["eventType"] for event in events]
    assert event_types.count("stage.succeeded") == 3
    assert event_types[-1] == "run.succeeded"
    assert all(
        {"eventId", "runId", "runType", "stageKey", "status", "sequence", "occurredAt", "data"}
        <= set(event)
        for event in events
    )

    completed = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert completed["stageResults"]["profile"]["profile"]["pillars"]
    assert completed["stageResults"]["pain_points"]["painPoints"]
    assert completed["stageResults"]["topics"]["topics"][0]["title"]
    assert "structure" not in completed["stageResults"]

    topics = send(
        app, "GET", f"/api/workspaces/{run['workspaceId']}/topics"
    ).json()
    assert len(topics) == 2
    assert topics[0]["sourceAnalysisRunId"] == run["id"]
    assert topics[0]["sourceWorkflow"] == "account_diagnosis"
    assert topics[0]["status"] == "candidate"
    assert topics[0]["title"]

    duplicate = send(
        app,
        "POST",
        f"/api/workspaces/{run['workspaceId']}/topics",
        json={
            "title": topics[0]["title"],
            "angle": "重复保存不应新增",
            "sourceAnalysisRunId": run["id"],
        },
    )
    assert duplicate.status_code == 201
    topics_after_duplicate_save = send(
        app, "GET", f"/api/workspaces/{run['workspaceId']}/topics"
    ).json()
    assert len(topics_after_duplicate_save) == 2


def test_parallel_stage_failure_allows_partial_account_result(app: FastAPI) -> None:
    run = create_account_run(app)
    app.state.account_workflow_service.fake_provider = FakeAccountDiagnosisModelProvider(
        failures={"profile"}
    )

    events = collect(app, run["id"])

    assert any(
        event["data"]["eventType"] == "stage.failed"
        and event["stageKey"] == "profile"
        for event in events
    )
    assert events[-1]["data"]["eventType"] == "run.partial"
    partial = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert partial["status"] == "partially_completed"
    assert "profile" in partial["stageErrors"]
    assert "pain_points" in partial["stageResults"]
    assert "topics" in partial["stageResults"]


def test_account_graph_restart_resumes_from_persisted_stage_results(
    app: FastAPI,
) -> None:
    run = create_account_run(app)
    provider = FakeAccountDiagnosisModelProvider()
    app.state.account_workflow_service.fake_provider = provider

    first_events = collect(app, run["id"], stop_after_node="profile_analysis")
    interrupted = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert interrupted["status"] == "running"
    assert "profile" in interrupted["stageResults"]
    assert "pain_points" in interrupted["stageResults"]
    assert first_events[-1]["data"]["eventType"] == "stage.succeeded"

    restarted_provider = FakeAccountDiagnosisModelProvider()
    app.state.account_workflow_service.fake_provider = restarted_provider
    second_events = collect(app, run["id"])

    assert "profile" not in restarted_provider.calls
    assert "pain_points" not in restarted_provider.calls
    assert restarted_provider.calls == ["topics"]
    assert second_events[-1]["data"]["eventType"] == "run.succeeded"
    completed = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert completed["status"] == "completed"


def test_live_account_graph_uses_injectable_provider_and_validates_output(
    app: FastAPI,
) -> None:
    class InvalidProvider(FakeAccountDiagnosisModelProvider):
        async def topics(self, **kwargs):
            self.calls.append("topics")
            return {"topics": [{"angle": "缺少 title"}], "titles": []}

    run = create_account_run(app, mode="live")
    provider = InvalidProvider()
    app.state.account_workflow_service.live_provider = provider

    events = collect(app, run["id"])

    assert provider.calls == ["profile", "pain_points", "topics"]
    assert any(
        event["data"]["eventType"] == "stage.failed"
        and event["stageKey"] == "topics"
        for event in events
    )
    result = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert result["status"] == "partially_completed"
    assert result["stageErrors"]["topics"] == "Model response failed structured validation"
