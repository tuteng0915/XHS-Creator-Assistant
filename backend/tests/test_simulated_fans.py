import asyncio

import pytest
from test_audience_simulation_workflow import collect
from test_creator_experience import audience_output, profile, topic
from test_workspace_api import create_workspace, send

from app.models import ModelCallResponse, ModelOperation, SimulationRunCreate
from app.services.audience_analyses import AudienceAnalysisCreate
from app.workflows.audience_simulation import RealAudienceSimulationModelProvider


def analyze(app, wid, source_id, output=None):
    class Model:
        async def call_operation(self, operation, context):
            return ModelCallResponse(output=output or audience_output(), model_metadata={})

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
    assert len(fans) == 4
    assert [f["sourceGroupId"] for f in fans] == ["3", "2", "1", "0"]
    return wid, source, analysis, fans


def test_fan_edit_original_idempotency_and_new_analysis(app, seeded):
    wid, source, analysis, fans = seeded
    fan = fans[0]
    assert fan["original"]["observedEpisodes"]
    updated = send(
        app,
        "PATCH",
        f"/api/simulated-fans/{fan['id']}",
        json={
            **fan["editable"],
            "name": "费用观察员🌱",
            "expressionStyle": "短句，先问范围",
            "expectedUpdatedAt": fan["updatedAt"],
        },
    ).json()
    assert updated["editable"]["name"] == "费用观察员🌱"
    assert updated["original"] == fan["original"]
    assert (
        send(
            app,
            "PATCH",
            f"/api/simulated-fans/{fan['id']}",
            json={
                **fan["editable"],
                "expectedUpdatedAt": fan["updatedAt"],
            },
        ).status_code
        == 409
    )
    duplicate = send(
        app,
        "POST",
        f"/api/workspaces/{wid}/simulated-fans",
        json={
            "sourceAnalysisId": analysis,
            "sourceGroupId": fan["sourceGroupId"],
        },
    ).json()
    assert duplicate == updated
    analyze(app, wid, source["id"])
    assert len(send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()) == 8
    assert send(app, "GET", f"/api/simulated-fans/{fan['id']}").json() == updated
    added = send(
        app,
        "POST",
        f"/api/workspaces/{wid}/simulated-fans",
        json={
            "sourceAnalysisId": analysis,
            "sourceGroupId": "0",
        },
    )
    assert added.status_code == 201
    assert added.json()["id"] == fans[3]["id"]
    assert added.json()["original"]["evidenceRefs"]


def test_eight_compact_personas_are_saved_and_selectable_without_truncation(app):
    wid = create_workspace(app)["id"]
    source = profile(app, wid)
    output = audience_output()
    original_group = output["groups"][0]
    styles = ["直说", "温柔", "查证", "质疑", "沉默", "幽默", "热情", "慢条斯理"]
    output["groups"] = [
        {**original_group, "id": f"person-{i}", "name": f"{style}读者",
         "profile": "关心准备过程，有自己的判断", "contentPreference": "清单",
         "expressionStyle": style}
        for i, style in enumerate(styles)
    ]
    analysis_id = analyze(app, wid, source["id"], output)
    fans = send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()
    assert len(fans) == 8
    assert {fan["editable"]["expressionStyle"] for fan in fans} == set(styles)
    service = app.state.audience_analysis_service
    analysis = service.get(analysis_id)
    assert len(analysis.result["groups"]) == 8
    from app.services.simulated_fans import SimulatedFanService

    with service.database.transaction() as connection:
        SimulatedFanService(service.database).save_generated(
            connection, wid, analysis_id, analysis.result, analysis.input_snapshot,
        )
    assert len(send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()) == 8
    run = app.state.simulation_service.create(wid, SimulationRunCreate(
        manual_topic="申请准备", simulated_fan_ids=[fan["id"] for fan in fans],
    ))
    assert len(run.input_snapshot["audiencePersonas"]) == 8
    assert {p["expressionStyle"] for p in run.input_snapshot["audiencePersonas"]} == set(styles)


def test_fan_snapshot_survives_edit_archive_and_restart(app, settings, seeded):
    from app.main import create_app

    wid, _, _, fans = seeded
    fan = fans[0]
    selected = topic(app, wid)
    run = app.state.simulation_service.create(
        wid,
        SimulationRunCreate(
            topic_id=selected["id"],
            simulated_fan_ids=[fan["id"]],
        ),
    )
    before = run.input_snapshot
    assert before["audiencePersonas"][0]["fanAssetId"] == fan["id"]
    updated = send(
        app,
        "PATCH",
        f"/api/simulated-fans/{fan['id']}",
        json={
            **fan["editable"],
            "profile": "人工假设：关注表达边界",
            "status": "archived",
            "expectedUpdatedAt": fan["updatedAt"],
        },
    ).json()
    restored_app = create_app(settings)
    assert restored_app.state.simulation_service.get(run.id).input_snapshot == before
    restored = send(
        restored_app,
        "PATCH",
        f"/api/simulated-fans/{fan['id']}",
        json={
            **updated["editable"],
            "status": "active",
            "expectedUpdatedAt": updated["updatedAt"],
        },
    ).json()
    new_run = restored_app.state.simulation_service.create(
        wid,
        SimulationRunCreate(
            topic_id=selected["id"],
            simulated_fan_ids=[restored["id"]],
            mode="live",
        ),
    )
    persona = new_run.input_snapshot["audiencePersonas"][0]
    assert persona["userAdjusted"] is True
    assert persona["evidenceStatus"] == "hypothesis"
    assert persona["originalDefinition"] == fan["original"]

    class Model:
        async def call_operation(self, operation, context):
            if operation == ModelOperation.SIMULATION_REACTION:
                assert context["persona"]["fanAssetId"] == fan["id"]
                assert context["persona"]["profile"] == "人工假设：关注表达边界"
                output = {
                    "reaction": {"personaId": fan["id"], "stance": "无感", "action": "no_comment"}
                }
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
    assert (
        send(
            app,
            "POST",
            f"/api/workspaces/{other}/simulated-fans",
            json={
                "sourceAnalysisId": analysis,
                "sourceGroupId": "3",
            },
        ).status_code
        == 422
    )
    for workspace_id, ids in [(other, [fan["id"]]), (wid, [fan["id"], fan["id"]])]:
        response = send(
            app,
            "POST",
            f"/api/workspaces/{workspace_id}/simulation-runs",
            json={
                "manualTopic": "测试选题",
                "simulatedFanIds": ids,
            },
        )
        assert response.status_code == 422
    send(
        app,
        "PATCH",
        f"/api/simulated-fans/{fan['id']}",
        json={
            **fan["editable"],
            "status": "archived",
            "expectedUpdatedAt": fan["updatedAt"],
        },
    )
    assert (
        send(
            app,
            "POST",
            f"/api/workspaces/{wid}/simulation-runs",
            json={
                "manualTopic": "测试",
                "simulatedFanIds": [fan["id"]],
            },
        ).status_code
        == 422
    )


def test_more_than_three_saved_fans_run_in_selected_order(app, seeded):
    wid, _, analysis, fans = seeded
    fourth = send(
        app,
        "POST",
        f"/api/workspaces/{wid}/simulated-fans",
        json={
            "sourceAnalysisId": analysis,
            "sourceGroupId": "0",
        },
    ).json()
    selected_ids = [fans[1]["id"], fourth["id"], fans[0]["id"], fans[2]["id"]]
    run = send(
        app,
        "POST",
        f"/api/workspaces/{wid}/simulation-runs",
        json={
            "manualTopic": "测试选题",
            "simulatedFanIds": selected_ids,
            "mode": "live",
        },
    ).json()
    assert [p["fanAssetId"] for p in run["inputSnapshot"]["audiencePersonas"]] == selected_ids

    class Model:
        async def call_operation(self, operation, context):
            if operation == ModelOperation.SIMULATION_REACTION:
                output = {
                    "reaction": {
                        "personaId": context["persona"]["id"],
                        "stance": "无感",
                        "action": "no_comment",
                    }
                }
            else:
                assert operation == ModelOperation.SIMULATION_SYNTHESIS
                output = {"synthesis": {"verdict": "仅模拟参考"}}
            return ModelCallResponse(output=output, model_metadata={})

    app.state.simulation_workflow_service.live_provider = RealAudienceSimulationModelProvider(
        Model()
    )
    collect(app, run["id"])
    completed = app.state.simulation_service.get(run["id"])
    assert completed.status.value == "completed", completed.stage_errors
    assert [r["personaId"] for r in completed.reaction_results] == selected_ids


def test_voice_templates_expand_one_fan_into_distinct_editable_variants(app, seeded):
    wid, _, _, fans = seeded
    source = fans[0]
    templates = send(app, "GET", "/api/simulated-fan-voices").json()
    assert len(templates) == 12
    assert len({item["id"] for item in templates}) == 12
    ids = [item["id"] for item in templates]
    created = send(
        app,
        "POST",
        f"/api/simulated-fans/{source['id']}/variants",
        json={
            "templateIds": ids,
        },
    )
    assert created.status_code == 201, created.text
    variants = created.json()
    assert len(variants) == 12
    assert len({item["editable"]["name"] for item in variants}) == 12
    assert len({item["editable"]["expressionStyle"] for item in variants}) == 12
    assert all(item["original"]["variantOfFanId"] == source["id"] for item in variants)
    assert all(
        item["original"]["evidenceRefs"] == source["original"]["evidenceRefs"] for item in variants
    )
    assert all(item["original"]["evidenceStatus"] == "hypothesis" for item in variants)
    assert len(send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()) == 16

    run = send(app, "POST", f"/api/workspaces/{wid}/simulation-runs", json={
        "manualTopic": "测试选题", "simulatedFanIds": [variants[0]["id"], variants[1]["id"]],
        "mode": "live",
    }).json()
    personas = run["inputSnapshot"]["audiencePersonas"]
    assert personas[0]["expressionStyle"] != personas[1]["expressionStyle"]
    assert personas[0]["evidenceRefs"] == personas[1]["evidenceRefs"]

    first = variants[0]
    changed = send(
        app,
        "PATCH",
        f"/api/simulated-fans/{first['id']}",
        json={
            **first["editable"],
            "name": "我改过的角色",
            "expectedUpdatedAt": first["updatedAt"],
        },
    ).json()
    repeated = send(
        app,
        "POST",
        f"/api/simulated-fans/{source['id']}/variants",
        json={
            "templateIds": [ids[0]],
        },
    ).json()
    assert repeated == [changed]
    nested = send(
        app,
        "POST",
        f"/api/simulated-fans/{first['id']}/variants",
        json={
            "templateIds": [ids[0]],
        },
    ).json()
    assert nested == [changed]
    assert send(app, "GET", f"/api/simulated-fans/{source['id']}").json() == source


def test_voice_variant_request_rejects_invalid_or_duplicate_templates(app, seeded):
    _, _, _, fans = seeded
    fan_id = fans[0]["id"]
    for ids in ([], ["unknown"], ["action_first", "action_first"]):
        response = send(
            app,
            "POST",
            f"/api/simulated-fans/{fan_id}/variants",
            json={
                "templateIds": ids,
            },
        )
        assert response.status_code == 422
