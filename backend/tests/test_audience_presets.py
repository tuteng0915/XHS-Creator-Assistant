import importlib.util
import json
from pathlib import Path

import pytest
from test_creator_experience import audience_output, profile
from test_workspace_api import create_workspace, send

from app.errors import ValidationError
from app.models import SimulationRunCreate
from app.services.audience_presets import save_curated_fans


def test_curated_presets_are_attributed_persistent_and_idempotent(app):
    wid = create_workspace(app)["id"]
    source = profile(app, wid)
    service = app.state.audience_analysis_service
    groups = audience_output()["groups"]
    groups[0]["expressionStyle"] = "简短追问，不虚构经历"
    fans = save_curated_fans(service.database, source["id"], "test-v1", groups)
    assert len(fans) == 4  # Saved assets are not limited to the three selected for simulation.
    fan = fans[0]
    assert fan.original["origin"] == "curated_preset"
    assert fan.original["evidenceStatus"] == "hypothesis"
    assert fan.original["observedEpisodes"]
    analysis = service.get(fan.source_analysis_id)
    assert analysis.status == "completed"
    assert analysis.model_metadata["modelCalled"] is False
    assert analysis.result["origin"] == "curated_preset"
    assert len(service.list(wid)) == 1
    updated = send(app, "PATCH", f"/api/simulated-fans/{fan.id}", json={
        **fan.editable.model_dump(by_alias=True), "name": "我的角色🌱", "status": "archived",
        "expectedUpdatedAt": fan.updated_at,
    }).json()
    again = save_curated_fans(service.database, source["id"], "test-v1", [])
    assert len(again) == 4
    saved = next(f for f in again if f.id == fan.id)
    assert saved.editable.name == updated["editable"]["name"]
    assert saved.status == "archived"
    assert service.get(analysis.id).input_snapshot == analysis.input_snapshot
    simulation = app.state.simulation_service.create(wid, SimulationRunCreate(
        manual_topic="测试选题", audience_analysis_id=analysis.id,
    ))
    assert all(g["evidenceStatus"] == "hypothesis"
               for g in simulation.input_snapshot["audiencePersonas"])
    active = next(f for f in again if f.status == "active")
    simulation = app.state.simulation_service.create(wid, SimulationRunCreate(
        manual_topic="测试选题", simulated_fan_ids=[active.id],
    ))
    assert simulation.input_snapshot["audiencePersonas"][0]["evidenceStatus"] == "hypothesis"
    other = create_workspace(app)["id"]
    assert not send(app, "GET", f"/api/workspaces/{other}/simulated-fans").json()


def test_invalid_preset_aborts_without_partial_writes(app):
    wid = create_workspace(app)["id"]
    source = profile(app, wid)
    groups = audience_output()["groups"]
    groups[0]["evidenceRefs"][0]["quote"] = "不存在的内容"
    service = app.state.audience_analysis_service
    with pytest.raises(ValidationError, match="未写入"):
        save_curated_fans(service.database, source["id"], "bad", groups)
    assert not service.list(wid)
    assert not send(app, "GET", f"/api/workspaces/{wid}/simulated-fans").json()


def test_qsheep_manifest_requires_real_matching_comments():
    path = Path(__file__).resolve().parents[2] / "scripts/seed_qsheep_audience_presets.py"
    spec = importlib.util.spec_from_file_location("seed_presets", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(ValueError, match="缺少"):
        module.build_groups({"notes": []})
    comments = [{"commentId": cid, "content": "原始评论🌱"}
                for preset in module.PRESETS for cid in preset["commentIds"]]
    groups = module.build_groups({"notes": [{"noteId": "note", "comments": comments}]})
    assert len(groups) == 5
    assert len({g["id"] for g in groups}) == 5
    assert "commentIds" not in json.dumps(groups)
    assert all(g["evidenceRefs"][0]["quote"] == "原始评论🌱" for g in groups)
