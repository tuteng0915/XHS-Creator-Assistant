"""Contract and lifecycle checks, not a claim of measured LLM persona quality."""

import json

import pytest
from test_audience_simulation_workflow import collect
from test_creator_experience import audience_output, profile
from test_simulated_fans import analyze
from test_workspace_api import create_workspace, send

from app.main import create_app
from app.models import ModelCallResponse, ModelOperation, SimulationRunCreate
from app.services.audience_analyses import validate_audience_output
from app.services.audience_evidence import audience_context
from app.services.model_calls import ModelCallService
from app.services.simulated_fans import FanDefinition
from app.workflows.audience_simulation import PersonaDefinition, RealAudienceSimulationModelProvider


@pytest.mark.parametrize("model", [FanDefinition, PersonaDefinition])
def test_interest_labels_are_optional_and_utf8_safe(model):
    legacy = {"id": "legacy", "name": "行动派", "profile": "先找可以马上做的一步"}
    assert model.model_validate(legacy).interests == []
    saved = model.model_validate({**legacy, "interests": [" 留学 ", "个人成长🌱"]})
    assert saved.interests == ["留学", "个人成长🌱"]


@pytest.mark.parametrize("interests", [None, "留学", [""], ["  "], ["字" * 31],
                                      ["留学"] * 7, [42]])
@pytest.mark.parametrize("model", [FanDefinition, PersonaDefinition])
def test_interest_labels_reject_malformed_data(model, interests):
    with pytest.raises(ValueError):
        model.model_validate({"id": "p", "name": "行动派", "profile": "先做一步",
                              "interests": interests})


def test_invalid_interests_only_reject_the_affected_group():
    output = audience_output()
    output["groups"][0]["interests"] = "留学"
    output["groups"][1]["interests"] = ["留学", "个人成长"]
    context = audience_context({"notes": [
        {"noteId": str(i), "comments": [{"content": "想了解申请费用"}]}
        for i in range(4)
    ]})
    result, diagnostics = validate_audience_output(output, context)
    assert len(result["groups"]) == 3
    assert len(diagnostics["rejectedGroups"]) == 1
    assert diagnostics["rejectedGroups"][0]["issues"][0]["code"] == "invalid_group_schema"
    assert next(g for g in result["groups"] if g["id"] == "1")["interests"] == ["留学", "个人成长"]


def test_prompt_separates_broad_interests_from_concrete_needs_and_behaviors(settings):
    service = ModelCallService(settings)
    context = {"notes": [{"noteId": "n", "title": "当前笔记"}]}
    system, user = service._build_prompt(ModelOperation.AUDIENCE_ANALYSIS, context)
    assert json.loads(user) == context
    assert '"interests":[]' in system
    assert "多个角色可以共享完全相同的 interests" in system
    assert "不能只换名称和语气" in system
    assert "coreConcern 写读完想得到的具体帮助" in system
    assert "profile 用一句话刻画遇到什么信息时如何判断、如何行动" in system
    assert "同一条模糊线索下的两种模拟可能" in system
    assert "先在心中把账号题材归并成少量上位领域" in system
    assert "区分供给信息与读者反应" in system
    assert "询问指导不等于愿意付费" in system
    assert "具体需求不等于照抄一次咨询" in system
    assert "住宿和保险" not in user  # Authored examples never enter account evidence.
    for operation in [ModelOperation.SIMULATION_REACTION, ModelOperation.SIMULATION_DEBATE]:
        system, user = service._build_prompt(operation, {
            "persona": {"interests": ["个人成长"], "coreConcern": "想找到第一步",
                        "profile": "看到新办法会先试一小步"},
            "topic": {"title": "新选题"},
        })
        assert all(key in system for key in ("interests", "coreConcern", "profile"))
        assert "个人成长" in user and "看到新办法会先试一小步" in user


def test_persona_dimensions_survive_save_edit_variants_restart_and_simulation(app, settings):
    workspace_id = create_workspace(app)["id"]
    source = profile(app, workspace_id)
    output = audience_output()
    common = output["groups"][0]
    output["groups"] = [
        {**common, "id": "action", "name": "先试一步派", "interests": ["留学", "个人成长"],
         "profile": "看到机会先试一小步，太复杂就问从哪里开始",
         "coreConcern": "想拿到今天能做的第一步", "expressionStyle": "直接问怎么做"},
        {**common, "id": "check", "name": "仔细核算派", "interests": ["留学", "个人成长"],
         "profile": "总成本没说清就先不决定，会逐项追问遗漏",
         "coreConcern": "想判断付出是否值得", "expressionStyle": "简短追问遗漏"},
    ]
    analysis_id = analyze(app, workspace_id, source["id"], output)
    fans = send(app, "GET", f"/api/workspaces/{workspace_id}/simulated-fans").json()
    assert len(fans) == 2  # Same interests/evidence do not collapse distinct roles.
    fan = next(f for f in fans if f["sourceGroupId"] == "action")
    original = fan["original"]
    analysis_before = app.state.audience_analysis_service.get(analysis_id).result
    for row in fans:
        assert row["original"]["interests"] == row["editable"]["interests"] == ["留学", "个人成长"]

    updated_response = send(app, "PATCH", f"/api/simulated-fans/{fan['id']}", json={
        **fan["editable"], "interests": ["留学", "职业发展"],
        "expectedUpdatedAt": fan["updatedAt"],
    })
    assert updated_response.status_code == 200
    updated = updated_response.json()
    assert updated["original"] == original
    assert app.state.audience_analysis_service.get(analysis_id).result == analysis_before

    # An older client omitting the newly introduced field cannot clear user edits.
    legacy_payload = {k: v for k, v in updated["editable"].items() if k != "interests"}
    old_client_response = send(app, "PATCH", f"/api/simulated-fans/{fan['id']}", json={
        **legacy_payload, "expectedUpdatedAt": updated["updatedAt"],
    })
    assert old_client_response.status_code == 200
    updated = old_client_response.json()
    assert updated["editable"]["interests"] == ["留学", "职业发展"]

    variant_response = send(app, "POST", f"/api/simulated-fans/{fan['id']}/variants", json={
        "templateIds": ["action_first"],
    })
    assert variant_response.status_code == 201
    assert variant_response.json()[0]["editable"]["interests"] == ["留学", "职业发展"]

    run = app.state.simulation_service.create(workspace_id, SimulationRunCreate(
        manual_topic="选择一条适合自己的路", mode="live",
        simulated_fan_ids=[row["id"] for row in fans],
    ))
    snapshot = run.input_snapshot
    expected = {p["id"]: p for p in snapshot["audiencePersonas"]}
    assert expected[fan["id"]]["userAdjusted"] is True
    assert expected[fan["id"]]["interests"] == ["留学", "职业发展"]
    cleared = send(app, "PATCH", f"/api/simulated-fans/{fan['id']}", json={
        **updated["editable"], "interests": [], "expectedUpdatedAt": updated["updatedAt"],
    })
    assert cleared.status_code == 200
    assert cleared.json()["editable"]["interests"] == []  # Explicit clearing stays possible.

    restored = create_app(settings)
    seen = []

    class Model:
        async def call_operation(self, operation, context):
            if operation in {ModelOperation.SIMULATION_REACTION, ModelOperation.SIMULATION_DEBATE}:
                persona = context["persona"]
                saved = expected[persona["id"]]
                for key in ("interests", "coreConcern", "profile", "expressionStyle"):
                    assert persona[key] == saved[key]
                seen.append((operation, persona["id"]))
                if operation == ModelOperation.SIMULATION_REACTION:
                    result = {"reaction": {"personaId": persona["id"], "stance": "犹豫",
                                           "action": "comment", "quote": saved["coreConcern"]}}
                else:
                    assert all(r["personaId"] != persona["id"] for r in context["otherReactions"])
                    result = {"debateResponse": {"personaId": persona["id"], "response": ""}}
            else:
                assert operation == ModelOperation.SIMULATION_SYNTHESIS
                assert {p["id"] for p in context["personas"]} == set(expected)
                result = {"synthesis": {"verdict": "不同需求已保留"}}
            return ModelCallResponse(output=result, model_metadata={"model": "injected"})

    restored.state.simulation_workflow_service.live_provider = RealAudienceSimulationModelProvider(
        Model(),
    )
    collect(restored, run.id)
    completed = restored.state.simulation_service.get(run.id)
    assert completed.status.value == "completed", completed.stage_errors
    assert completed.input_snapshot == snapshot
    assert set(seen) == {(op, persona_id) for op in (
        ModelOperation.SIMULATION_REACTION, ModelOperation.SIMULATION_DEBATE,
    ) for persona_id in expected}
    assert {p["id"]: p["interests"] for p in completed.persona_definitions} == {
        key: value["interests"] for key, value in expected.items()
    }
