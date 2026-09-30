import asyncio

import pytest
from test_audience_simulation_workflow import collect
from test_creator_experience import audience_output, profile, topic
from test_workspace_api import create_workspace, send

from app.models import ModelCallResponse, ModelOperation, SimulationRunCreate
from app.services.audience_analyses import AudienceAnalysisCreate
from app.workflows.audience_simulation import RealAudienceSimulationModelProvider


def analyze(app, wid, source_id):
    class Model:
        async def call_operation(self, operation, context):
            return ModelCallResponse(output=audience_output(), model_metadata={})

    service = app.state.audience_analysis_service
    service.model_call_service = Model()

    async def run():
        created = service.create(wid, AudienceAnalysisCreate(source_material_id=source_id))
        await asyncio.gather(*list(service.tasks.values()))
        assert service.get(created.id).status == "completed"
        return created.id
    return asyncio.run(run())


@pytest.fixture
def seeded(app):
    wid = create_workspace(app)["id"]
    source = profile(app, wid)
    analysis = analyze(app, wid, source["id"])
    fans = send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()
    assert len(fans) == 3
    assert [f["sourceGroupId"] for f in fans] == ["3", "2", "1"]
    return wid, source, analysis, fans


def test_fan_edit_original_idempotency_and_new_analysis(app, seeded):
    wid, source, analysis, fans = seeded
    fan = fans[0]
    assert fan["original"]["observedEpisodes"]
    updated = send(app, "PATCH", f"/api/simulated-fans/{fan['id']}", json={
        **fan["editable"], "name": "费用观察员🌱", "expressionStyle": "短句，先问范围",
        "expectedUpdatedAt": fan["updatedAt"],
    }).json()
    assert updated["editable"]["name"] == "费用观察员🌱"
    assert updated["original"] == fan["original"]
    assert send(app, "PATCH", f"/api/simulated-fans/{fan['id']}", json={
        **fan["editable"], "expectedUpdatedAt": fan["updatedAt"],
    }).status_code == 409
    duplicate = send(app, "POST", f"/api/workspaces/{wid}/simulated-fans", json={
        "sourceAnalysisId": analysis, "sourceGroupId": fan["sourceGroupId"],
    }).json()
    assert duplicate == updated
    analyze(app, wid, source["id"])
    assert len(send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()) == 3
    assert send(app, "GET", f"/api/simulated-fans/{fan['id']}").json() == updated
    added = send(app, "POST", f"/api/workspaces/{wid}/simulated-fans", json={
        "sourceAnalysisId": analysis, "sourceGroupId": "0",
    })
    assert added.status_code == 201
    assert added.json()["original"]["evidenceRefs"]


def test_fan_snapshot_survives_edit_archive_and_restart(app, settings, seeded):
    from app.main import create_app

    wid, _, _, fans = seeded
    fan = fans[0]
    selected = topic(app, wid)
    run = app.state.simulation_service.create(wid, SimulationRunCreate(
        topic_id=selected["id"], simulated_fan_ids=[fan["id"]],
    ))
    before = run.input_snapshot
    assert before["audiencePersonas"][0]["fanAssetId"] == fan["id"]
    updated = send(app, "PATCH", f"/api/simulated-fans/{fan['id']}", json={
        **fan["editable"], "profile": "人工假设：关注表达边界", "status": "archived",
        "expectedUpdatedAt": fan["updatedAt"],
    }).json()
    restored_app = create_app(settings)
    assert restored_app.state.simulation_service.get(run.id).input_snapshot == before
    restored = send(restored_app, "PATCH", f"/api/simulated-fans/{fan['id']}", json={
        **updated["editable"], "status": "active", "expectedUpdatedAt": updated["updatedAt"],
    }).json()
    new_run = restored_app.state.simulation_service.create(wid, SimulationRunCreate(
        topic_id=selected["id"], simulated_fan_ids=[restored["id"]], mode="live",
    ))
    persona = new_run.input_snapshot["audiencePersonas"][0]
    assert persona["userAdjusted"] is True
    assert persona["evidenceStatus"] == "hypothesis"
    assert persona["originalDefinition"] == fan["original"]

    class Model:
        async def call_operation(self, operation, context):
            if operation == ModelOperation.SIMULATION_REACTION:
                assert context["persona"]["fanAssetId"] == fan["id"]
                assert context["persona"]["profile"] == "人工假设：关注表达边界"
                output = {"reaction": {"personaId": fan["id"], "stance": "无感",
                                       "action": "no_comment"}}
            else:
                assert operation == ModelOperation.SIMULATION_SYNTHESIS
                output = {"synthesis": {"verdict": "仅模拟参考"}}
            return ModelCallResponse(output=output, model_metadata={"model": "injected"})

    restored_app.state.simulation_workflow_service.live_provider = (
        RealAudienceSimulationModelProvider(Model())
    )
    collect(restored_app, new_run.id)
    completed = restored_app.state.simulation_service.get(new_run.id)
    assert completed.status.value == "completed", completed.stage_errors
    assert completed.persona_definitions[0]["id"] == fan["id"]
    assert completed.persona_definitions[0]["userAdjusted"] is True
    assert completed.input_snapshot == new_run.input_snapshot
    assert restored_app.state.simulated_fan_service.get(fan["id"]).original == fan["original"]


def test_fans_cannot_cross_accounts_or_accept_duplicate_selection(app, seeded):
    wid, _, analysis, fans = seeded
    other = create_workspace(app)["id"]
    fan = fans[0]
    assert send(app, "GET", f"/api/workspaces/{other}/simulated-fans").json() == []
    assert send(app, "POST", f"/api/workspaces/{other}/simulated-fans", json={
        "sourceAnalysisId": analysis, "sourceGroupId": "3",
    }).status_code == 422
    for workspace_id, ids in [(other, [fan["id"]]), (wid, [fan["id"], fan["id"]])]:
        response = send(app, "POST", f"/api/workspaces/{workspace_id}/simulation-runs", json={
            "manualTopic": "测试选题", "simulatedFanIds": ids,
        })
        assert response.status_code == 422
    send(app, "PATCH", f"/api/simulated-fans/{fan['id']}", json={
        **fan["editable"], "status": "archived", "expectedUpdatedAt": fan["updatedAt"],
    })
    assert send(app, "POST", f"/api/workspaces/{wid}/simulation-runs", json={
        "manualTopic": "测试", "simulatedFanIds": [fan["id"]],
    }).status_code == 422
