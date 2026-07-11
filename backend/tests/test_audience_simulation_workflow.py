import asyncio

from fastapi import FastAPI
from test_workspace_api import create_workspace, send

from app.workflows.audience_simulation import (
    AUDIENCE_SIMULATION_NODE_ORDER,
    FakeAudienceSimulationModelProvider,
)


def create_topic(app: FastAPI, workspace_id: str) -> dict:
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace_id}/topics",
        json={
            "title": "非技术背景如何开始数字游民",
            "angle": "拆成六条可验证路径",
            "associatedPainPoint": "不知道靠什么远程赚钱",
            "whyItFits": "符合真实记录和可操作指南定位",
            "sourceWorkflow": "manual",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_simulation_run(app: FastAPI, *, saved_topic: bool = True) -> dict:
    workspace = create_workspace(app)
    payload: dict
    if saved_topic:
        topic = create_topic(app, workspace["id"])
        payload = {"topicId": topic["id"], "mode": "demo"}
    else:
        payload = {"manualTopic": "手动输入的受众模拟选题", "mode": "demo"}
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/simulation-runs",
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def collect(
    app: FastAPI, simulation_id: str, stop_after_node: str | None = None
) -> list[dict]:
    return asyncio.run(
        app.state.simulation_workflow_service.collect_events(
            simulation_id, stop_after_node=stop_after_node
        )
    )


def test_simulation_graph_from_saved_topic_persists_full_result(app: FastAPI) -> None:
    run = create_simulation_run(app)

    assert AUDIENCE_SIMULATION_NODE_ORDER == [
        "derive_personas",
        "parallel_initial_reactions",
        "parallel_debate_responses",
        "synthesis",
        "finalize",
    ]

    events = collect(app, run["id"])

    assert events[-1]["data"]["eventType"] == "run.succeeded"
    completed = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert completed["personaDefinitions"][0]["archetype"] == "想转型的传统职场人"
    assert len(completed["reactionResults"]) == 3
    assert len(completed["debateResults"]) == 3
    assert completed["synthesis"]["verdict"]
    assert completed["synthesis"]["topResonance"]["persona"] == "想转型的传统职场人"


def test_simulation_can_start_from_manual_topic(app: FastAPI) -> None:
    run = create_simulation_run(app, saved_topic=False)

    assert run["topicId"] is None
    assert run["inputSnapshot"]["topic"]["title"] == "手动输入的受众模拟选题"

    collect(app, run["id"])
    completed = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert completed["status"] == "completed"


def test_failed_persona_reaction_is_preserved_as_partial(app: FastAPI) -> None:
    run = create_simulation_run(app)
    app.state.simulation_workflow_service.fake_provider = (
        FakeAudienceSimulationModelProvider(failures={"reaction:nomad"})
    )

    events = collect(app, run["id"])

    assert events[-1]["data"]["eventType"] == "run.partial"
    partial = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert partial["status"] == "partially_completed"
    assert len(partial["reactionResults"]) == 2
    assert "initial_reactions.nomad" in partial["stageErrors"]
    assert partial["synthesis"]["verdict"]


def test_persona_calls_use_bounded_retry(app: FastAPI) -> None:
    class FlakyProvider(FakeAudienceSimulationModelProvider):
        def __init__(self) -> None:
            super().__init__()
            self.reaction_attempts = 0

        async def initial_reaction(self, **kwargs):
            persona = kwargs["persona"]
            if persona["id"] == "wannabe" and self.reaction_attempts == 0:
                self.reaction_attempts += 1
                raise RuntimeError("transient failure")
            return await super().initial_reaction(**kwargs)

    run = create_simulation_run(app)
    provider = FlakyProvider()
    app.state.simulation_workflow_service.fake_provider = provider

    collect(app, run["id"])

    completed = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert len(completed["reactionResults"]) == 3
    assert provider.reaction_attempts == 1


def test_simulation_history_and_reopen(app: FastAPI) -> None:
    run = create_simulation_run(app)
    workspace_id = run["workspaceId"]
    collect(app, run["id"])

    history = send(
        app, "GET", f"/api/workspaces/{workspace_id}/simulation-runs"
    ).json()
    assert history[0]["id"] == run["id"]
    assert history[0]["status"] == "completed"

    reopened = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert reopened["id"] == run["id"]
    assert reopened["synthesis"]["strongestAngle"]
