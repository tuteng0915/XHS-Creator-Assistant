import asyncio
from dataclasses import replace

import pytest
from test_audience_simulation_workflow import collect
from test_creator_experience import audience_output, profile, topic
from test_workspace_api import create_workspace, send

from app.models import ModelCallResponse, ModelOperation, SimulationRunCreate
from app.services.audience_analyses import AudienceAnalysisCreate
from app.services.fan_voice_templates import fan_voice_template
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


def adopt_candidates(app, wid, analysis_id, group_ids=None):
    groups = app.state.audience_analysis_service.get(analysis_id).result["groups"]
    for group in groups:
        if group_ids is None or group["id"] in group_ids:
            response = send(app, "POST", f"/api/workspaces/{wid}/simulated-fans", json={
                "sourceAnalysisId": analysis_id, "sourceGroupId": group["id"],
            })
            assert response.status_code == 201, response.text
    return send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()


@pytest.fixture
def seeded(app):
    wid = create_workspace(app)["id"]
    source = profile(app, wid)
    analysis = analyze(app, wid, source["id"])
    assert send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json() == []
    fans = adopt_candidates(app, wid, analysis)
    assert len(fans) == 4
    assert {f["sourceGroupId"] for f in fans} == {"3", "2", "1", "0"}
    fans.sort(key=lambda f: f["sourceGroupId"], reverse=True)
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
    new_analysis = analyze(app, wid, source["id"])
    assert len(send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()) == 4
    adopt_candidates(app, wid, new_analysis, ["0"])
    assert len(send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()) == 5
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


def test_eight_compact_personas_are_candidates_until_explicitly_adopted(app):
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
    assert send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json() == []
    fans = adopt_candidates(app, wid, analysis_id)
    assert len(fans) == 8
    assert {fan["editable"]["expressionStyle"] for fan in fans} == set(styles)
    service = app.state.audience_analysis_service
    analysis = service.get(analysis_id)
    assert len(analysis.result["groups"]) == 8
    adopt_candidates(app, wid, analysis_id)
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
    assert before["audiencePersonas"][0]["sourceAnalysisId"] == fan["sourceAnalysisId"]
    assert before["audiencePersonas"][0]["sourceGroupId"] == fan["sourceGroupId"]
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
    assert completed.persona_definitions[0]["sourceAnalysisId"] == fan["sourceAnalysisId"]
    assert completed.persona_definitions[0]["sourceGroupId"] == fan["sourceGroupId"]
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


def test_action_voice_update_keeps_old_assets_and_frozen_simulation(app, seeded, monkeypatch):
    wid, _, _, fans = seeded
    source = fans[0]
    current = fan_voice_template("action_first")
    legacy = replace(current, decision_style="先找下一步、步骤和具体入口。",
                     expression_style="短句、直接，会追问怎么做。",
                     participation_style="容易公开提问。")
    route = f"/api/simulated-fans/{source['id']}/variants"
    with monkeypatch.context() as patch:
        patch.setattr("app.services.simulated_fans.fan_voice_template", lambda _: legacy)
        old = send(app, "POST", route, json={"templateIds": ["action_first"]}).json()[0]
    run = send(app, "POST", f"/api/workspaces/{wid}/simulation-runs", json={
        "manualTopic": "自行开始的练习", "simulatedFanIds": [old["id"]], "mode": "live",
    }).json()
    repeated = send(app, "POST", route, json={"templateIds": ["action_first"]}).json()
    assert repeated == [old]
    assert send(app, "GET", f"/api/simulation-runs/{run['id']}").json()["inputSnapshot"] == (
        run["inputSnapshot"]
    )
    assert send(app, "GET", f"/api/simulated-fans/{source['id']}").json() == source

    new = send(app, "POST", f"/api/simulated-fans/{fans[1]['id']}/variants",
               json={"templateIds": ["action_first"]}).json()[0]
    assert current.decision_style in new["editable"]["profile"]
    assert current.participation_style in new["editable"]["expressionStyle"]
    assert new["editable"]["interests"] == fans[1]["editable"]["interests"]
    assert new["editable"]["coreConcern"] == fans[1]["editable"]["coreConcern"]
    assert new["original"]["evidenceRefs"] == fans[1]["original"]["evidenceRefs"]
    new_run = send(app, "POST", f"/api/workspaces/{wid}/simulation-runs", json={
        "manualTopic": "新练习", "simulatedFanIds": [new["id"]], "mode": "live",
    }).json()
    person = new_run["inputSnapshot"]["audiencePersonas"][0]
    assert person["profile"] == new["editable"]["profile"]
    assert person["expressionStyle"] == new["editable"]["expressionStyle"]


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
