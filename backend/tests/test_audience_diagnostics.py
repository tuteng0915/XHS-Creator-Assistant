import asyncio
import json

import pytest
from test_creator_experience import audience_output, profile
from test_workspace_api import create_workspace, send

from app.models import ModelCallResponse, SimulationRunCreate
from app.services.audience_analyses import AudienceAnalysisCreate, AudienceAnalysisService


def test_note_only_reader_view_persists_as_hypothesis_without_image_context(app):
    wid = create_workspace(app)["id"]
    source = send(app, "POST", f"/api/workspaces/{wid}/source-materials", json={
        "type": "xhs_creator_profile", "name": "图文账号",
        "content": json.dumps({
            "schemaVersion": "xhs-creator-profile/v1",
            "creator": {"displayName": "测试创作者"},
            "notes": [{"noteId": "note-1", "title": "非应届申请步骤",
                       "desc": "逐项核对材料和时间线", "coverMediaAssetId": "cover-1",
                       "comments": []}],
        }, ensure_ascii=False),
    }).json()

    class Model:
        async def call_operation(self, operation, context):
            assert context["notes"][0]["title"] == "非应届申请步骤"
            assert context["notes"][0]["content"] == "逐项核对材料和时间线"
            assert context["sampling"]["sentComments"] == 0
            assert "coverMediaAssetId" not in context["notes"][0]
            return ModelCallResponse(output={
                "summary": "潜在阅读视角", "limitations": "没有评论样本",
                "groups": [{"id": "steps", "name": "步骤需求", "profile": "可能需要申请步骤",
                            "coreConcern": "时间线", "evidenceRefs": [
                                {"noteId": "note-1", "commentId": None,
                                 "sourceType": "note", "quote": "逐项核对材料和时间线"},
                            ]}],
            }, model_metadata={"model": "fake"})

    service = app.state.audience_analysis_service
    service.model_call_service = Model()

    async def run():
        created = service.create(wid, AudienceAnalysisCreate(source_material_id=source["id"]))
        await asyncio.gather(*list(service.tasks.values()))
        return created.id

    run_id = asyncio.run(run())
    saved = AudienceAnalysisService(service.database, Model()).get(run_id)
    assert saved.status == "completed"
    assert saved.result["groups"][0]["evidenceBasis"] == "content_inferred"
    assert "尚无评论直接佐证" in saved.result["summary"]
    fans = send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()
    assert len(fans) == 1
    assert fans[0]["original"]["evidenceStatus"] == "hypothesis"
    simulation = app.state.simulation_service.create(wid, SimulationRunCreate(
        manual_topic="申请材料怎么整理", simulated_fan_ids=[fans[0]["id"]],
    ))
    assert simulation.input_snapshot["audiencePersonas"][0]["evidenceStatus"] == "hypothesis"


@pytest.mark.parametrize(
    "failure", ["quote", "source", "schema", "duplicate", "envelope", "provider"],
)
def test_audience_failures_keep_diagnostics_and_provider_output(app, failure):
    wid = create_workspace(app)["id"]
    source = profile(app, wid)
    output = audience_output()
    for group in output["groups"]:
        if failure == "quote":
            group["evidenceRefs"][0]["quote"] = "想知道申请花多少钱"  # Paraphrase, not evidence.
        elif failure == "source":
            group["evidenceRefs"][0]["commentId"] = "wrong"
        elif failure == "schema":
            group["profile"] = None
        elif failure == "duplicate":
            group["id"] = "duplicate"
    if failure == "envelope":
        output["groups"] = []

    class Model:
        calls = 0

        async def call_operation(self, operation, context):
            self.calls += 1
            if failure == "provider":
                raise RuntimeError("provider unavailable")
            return ModelCallResponse(output=output, model_metadata={"model": "test"})

    service = app.state.audience_analysis_service
    model = Model()
    service.model_call_service = model

    async def run():
        created = service.create(wid, AudienceAnalysisCreate(source_material_id=source["id"]))
        await asyncio.gather(*list(service.tasks.values()))
        await service.execute(created.id)  # Observation/retry must not execute twice.
        return created.id

    run_id = asyncio.run(run())
    restored = AudienceAnalysisService(service.database, model)
    result = restored.get(run_id)
    assert result.status == "failed"
    assert result.result == {}
    assert model.calls == 1
    assert not send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()
    with service.database.read() as c:
        row = c.execute("SELECT * FROM audience_analyses WHERE id=?", (run_id,)).fetchone()
        assert json.loads(row["model_output_json"]) == ({} if failure == "provider" else output)
    if failure in {"envelope", "provider"}:
        assert result.diagnostics["phase"] == (
            "model_call" if failure == "provider" else "structured_validation"
        )
    else:
        assert len(result.diagnostics["rejectedGroups"]) == 4
        if failure == "quote":
            issue = result.diagnostics["rejectedGroups"][0]["issues"][0]
            assert issue["code"] == "quote_not_exact"
            assert issue["reference"]["quote"] == "想知道申请花多少钱"
    assert "model_output" not in result.model_dump()


@pytest.mark.parametrize("invalid", [
    "missing_evidence", "non_object", "invalid_name", "long_name", "long_profile", "blank_name",
])
def test_partial_result_can_feed_fan_and_legacy_simulation(app, invalid):
    wid = create_workspace(app)["id"]
    source = profile(app, wid)
    output = audience_output()
    if invalid == "missing_evidence":
        output["groups"][0]["evidenceRefs"] = []
    elif invalid == "non_object":
        output["groups"][0] = "malformed"
    elif invalid == "invalid_name":
        output["groups"][0]["name"] = {"unexpected": "object"}
    elif invalid == "long_name":
        output["groups"][0]["name"] = "名" * 201
    elif invalid == "long_profile":
        output["groups"][0]["profile"] = "文" * 4001
    elif invalid == "blank_name":
        output["groups"][0]["name"] = "  "

    class Model:
        async def call_operation(self, operation, context):
            return ModelCallResponse(output=output, model_metadata={"model": "test"})

    service = app.state.audience_analysis_service
    service.model_call_service = Model()

    async def run():
        created = service.create(wid, AudienceAnalysisCreate(source_material_id=source["id"]))
        await asyncio.gather(*list(service.tasks.values()))
        return service.get(created.id)

    result = asyncio.run(run())
    assert result.status == "partially_completed"
    assert result.result["summary"] != output["summary"]
    assert result.model_metadata == {"model": "test"}
    if invalid in {"non_object", "invalid_name"}:
        assert result.diagnostics["rejectedGroups"][0]["groupName"] is None
    for group_id, expected in [("3", 201), ("0", 422)]:
        assert send(app, "POST", f"/api/workspaces/{wid}/simulated-fans", json={
            "sourceAnalysisId": result.id, "sourceGroupId": group_id,
        }).status_code == expected
    simulation = app.state.simulation_service.create(wid, SimulationRunCreate(
        manual_topic="申请计划", audience_analysis_id=result.id,
    ))
    assert {g["id"] for g in simulation.input_snapshot["audiencePersonas"]} == {"1", "2", "3"}
