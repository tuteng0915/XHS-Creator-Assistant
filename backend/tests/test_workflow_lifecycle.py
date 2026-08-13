import asyncio

from fastapi import FastAPI
from test_workspace_api import create_workspace, send

from app.main import create_app
from app.models import AnalysisRunCreate, SourceMaterialType, WorkflowType
from app.workflows.account_diagnosis import FakeAccountDiagnosisModelProvider


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


def create_pending_account_run(app: FastAPI) -> dict:
    workspace = create_workspace(app)
    historical = create_text_material(
        app,
        workspace["id"],
        SourceMaterialType.HISTORICAL_POSTS.value,
        "二本逆袭G5?别再被这种标题骗了｜赞1.4k 藏980｜爆",
    )
    comments = create_text_material(
        app,
        workspace["id"],
        SourceMaterialType.COMMENTS.value,
        "中介那部分太真实了，我现在就纠结要不要DIY。",
    )
    return app.state.analysis_service.create(
        workspace["id"],
        AnalysisRunCreate(
            workflow_type=WorkflowType.ACCOUNT_DIAGNOSIS,
            historical_posts_material_id=historical["id"],
            comments_material_id=comments["id"],
            mode="demo",
        ),
    ).model_dump(mode="json", by_alias=True)


def test_worker_completes_without_sse_connection(app: FastAPI) -> None:
    run = create_pending_account_run(app)

    async def execute() -> None:
        queued = await app.state.workflow_worker.enqueue_analysis_run(run["id"])
        assert queued is True
        await app.state.workflow_worker.wait_for_idle()

    asyncio.run(execute())

    completed = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert completed["stageResults"]["topics"]["topics"]


def test_analysis_run_creation_is_idempotent_for_same_client_key(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    historical = create_text_material(
        app,
        workspace["id"],
        SourceMaterialType.HISTORICAL_POSTS.value,
        "二本逆袭G5?别再被这种标题骗了",
    )
    comments = create_text_material(
        app,
        workspace["id"],
        SourceMaterialType.COMMENTS.value,
        "中介那部分太真实了。",
    )
    payload = {
        "workflowType": "account_diagnosis",
        "historicalPostsMaterialId": historical["id"],
        "commentsMaterialId": comments["id"],
        "mode": "demo",
        "idempotencyKey": "workflow-click-001",
    }

    first = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json=payload,
    )
    second = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json=payload,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["id"] == first.json()["id"]
    listed = send(
        app, "GET", f"/api/workspaces/{workspace['id']}/analysis-runs"
    ).json()
    assert [run["id"] for run in listed].count(first.json()["id"]) == 1
    assert len(listed) == 1


def test_duplicate_enqueue_does_not_duplicate_execution(app: FastAPI) -> None:
    class SlowProvider(FakeAccountDiagnosisModelProvider):
        async def profile(self, **kwargs):
            await asyncio.sleep(0.05)
            return await super().profile(**kwargs)

        async def pain_points(self, **kwargs):
            await asyncio.sleep(0.05)
            return await super().pain_points(**kwargs)

        async def topics(self, **kwargs):
            await asyncio.sleep(0.05)
            return await super().topics(**kwargs)

    provider = SlowProvider()
    app.state.account_workflow_service.fake_provider = provider
    run = create_pending_account_run(app)

    async def execute() -> None:
        first = await app.state.workflow_worker.enqueue_analysis_run(run["id"])
        second = await app.state.workflow_worker.enqueue_analysis_run(run["id"])
        assert first is True
        assert second is False
        await app.state.workflow_worker.wait_for_idle()

    asyncio.run(execute())

    assert provider.calls.count("profile") == 1
    assert provider.calls.count("pain_points") == 1
    assert provider.calls.count("topics") == 1


def test_unfinished_run_resumes_after_app_restart(app: FastAPI) -> None:
    run = create_pending_account_run(app)
    asyncio.run(
        app.state.account_workflow_service.collect_events(
            run["id"], stop_after_node="profile_analysis"
        )
    )
    interrupted = send(app, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert interrupted["status"] == "running"
    assert "profile" in interrupted["stageResults"]
    assert "topics" not in interrupted["stageResults"]

    restarted = create_app(app.state.settings)

    async def resume() -> None:
        queued = await restarted.state.workflow_worker.resume_unfinished()
        assert queued == 1
        await restarted.state.workflow_worker.wait_for_idle()

    asyncio.run(resume())

    completed = send(restarted, "GET", f"/api/analysis-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert completed["stageResults"]["topics"]["topics"]


def test_analysis_sse_replay_can_skip_seen_sequence(app: FastAPI) -> None:
    run = create_pending_account_run(app)

    async def execute() -> None:
        await app.state.workflow_worker.enqueue_analysis_run(run["id"])
        await app.state.workflow_worker.wait_for_idle()

    asyncio.run(execute())

    response = send(app, "GET", f"/api/analysis-runs/{run['id']}/events?after=2")

    assert response.status_code == 200
    body = response.text
    assert "id: 1" not in body
    assert "id: 2" not in body
    assert "run.succeeded" in body
