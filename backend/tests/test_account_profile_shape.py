import asyncio
import json
from copy import deepcopy

import pytest
from pydantic import ValidationError as PydanticValidationError
from test_account_diagnosis_evidence import selected_snapshot
from test_account_profile_check import load_check
from test_analysis_topics_api import create_text_material
from test_workspace_api import create_workspace, send

from app.models import ModelCallResponse
from app.services.account_diagnosis_evidence import profile_stage_input, verified_portrait
from app.services.account_profile_shape import normalize_profile_stage_result
from app.workflows.account_diagnosis import FakeAccountDiagnosisModelProvider, ProfileStageResult


def claim(statement="把经验写具体"):
    return {"statement": statement, "evidence": [{"noteId": "n1", "quote": "中文正文甲"}],
            "counterexamples": []}


def writing_fields():
    return {
        "pillars": ["经验分享"],
        "titleFormulas": [{"formula": "场景＋判断", "examples": ["先判断再行动"]}],
        "hookStyles": ["从具体动作切入"],
        "viralStructure": {"name": "判断过程", "steps": ["问题", "动作", "结果"]},
        "voiceFingerprint": ["短句，具体动词"],
        "contrast": {"takeaways": ["保留动作细节"]},
    }


def misplaced_portrait():
    return {"profile": {
        "accountPortrait": {"summary": "把经验写具体", "evidence": claim()["evidence"],
                            "counterexamples": []},
        "keywords": [claim("经验分享")], "strengths": [claim()],
        "recurringThemes": [], "readerValue": [claim("提供行动参照")],
        "expressionPatterns": [claim("具体动作")], "recentChange": None,
        "encouragement": None,
        **writing_fields(),
    }}


def misplaced_writing():
    return {"profile": {"accountPortrait": {"summary": claim(), **writing_fields()}}}


def test_standard_shape_is_unchanged_and_unknown_keys_are_not_guessed():
    standard = {"profile": {"accountPortrait": {"summary": claim(), "unknown": ["原样"]},
                            "unrecognized": {"hooks": ["不猜别名"]}, **writing_fields()}}
    before = deepcopy(standard)
    normalized = normalize_profile_stage_result(standard)
    assert normalized == standard == before
    assert normalized is not standard
    normalized["profile"]["accountPortrait"]["summary"]["evidence"].clear()
    assert standard == before


def test_qsheep_shaped_response_relocates_portrait_fields_and_wraps_existing_evidence():
    raw = misplaced_portrait()
    before = deepcopy(raw)
    normalized = normalize_profile_stage_result(raw)
    portrait = normalized["profile"]["accountPortrait"]
    assert portrait["summary"] == claim()
    for key in ("keywords", "strengths", "recurringThemes", "readerValue",
                "expressionPatterns", "recentChange", "encouragement"):
        assert portrait[key] == raw["profile"][key]
        assert key not in normalized["profile"]
    assert "evidence" not in portrait and "counterexamples" not in portrait
    assert ProfileStageResult.model_validate(raw).profile.accountPortrait == portrait
    assert raw == before


def test_ag_shaped_response_relocates_writing_fields_without_rewriting_values():
    raw = misplaced_writing()
    before = deepcopy(raw)
    normalized = normalize_profile_stage_result(raw)
    assert normalized["profile"] == {"accountPortrait": {"summary": claim()}, **writing_fields()}
    result = ProfileStageResult.model_validate(raw).model_dump(mode="json")
    assert result == normalized
    assert raw == before


@pytest.mark.parametrize("raw", [
    {"profile": {"keywords": [claim("另一个")], "accountPortrait": {"keywords": [claim()]}}},
    {"profile": {"pillars": [], "accountPortrait": {"pillars": ["有值"]}}},
    {"profile": {"accountPortrait": None, "strengths": [claim()] }},
    {"profile": {"accountPortrait": {"summary": claim()}, "summary": "不同值"}},
])
def test_conflicting_locations_fail_validation_and_preserve_raw_response(raw):
    before = deepcopy(raw)
    with pytest.raises(PydanticValidationError, match="冲突"):
        ProfileStageResult.model_validate(raw)
    assert raw == before


def test_identical_duplicate_is_deduplicated_without_overwriting_canonical_content():
    raw = {"profile": {"strengths": [claim()], "pillars": ["经验分享"],
                       "accountPortrait": {"strengths": [claim()], "pillars": ["经验分享"]}}}
    normalized = normalize_profile_stage_result(raw)
    assert normalized == {"profile": {"pillars": ["经验分享"],
                                       "accountPortrait": {"strengths": [claim()]}}}


@pytest.mark.parametrize("extra", [{}, {"evidence": None}, {"evidence": "不是引用数组"},
                                    {"evidence": []}])
def test_summary_without_usable_evidence_never_gets_invented_support(extra):
    raw = {"profile": {"accountPortrait": {"summary": "无依据总结", **extra}}}
    before = deepcopy(raw)
    portrait = ProfileStageResult.model_validate(raw).profile.accountPortrait
    if extra == {"evidence": []}:
        assert portrait["summary"] == {
            "statement": "无依据总结", "evidence": [], "counterexamples": [],
        }
    else:
        assert portrait["summary"] == "无依据总结"
    assert verified_portrait(portrait, selected_snapshot()) is None
    assert raw == before


def test_missing_portrait_container_can_be_created_only_from_known_fields():
    raw = {"profile": {"strengths": [claim()], "unknownAlias": ["不移动"]}}
    assert normalize_profile_stage_result(raw) == {"profile": {
        "accountPortrait": {"strengths": [claim()]}, "unknownAlias": ["不移动"],
    }}


@pytest.mark.parametrize("factory", [misplaced_portrait, misplaced_writing])
def test_check_report_keeps_raw_output_and_uses_same_validation_entry(factory):
    check = load_check()
    snapshot = selected_snapshot()
    context, observations = profile_stage_input(snapshot, "2026-10-10")
    raw = factory()
    before = deepcopy(raw)

    class Model:
        calls = 0

        async def call_operation(self, *args):
            self.calls += 1
            return ModelCallResponse(output=raw, model_metadata={"model": "fake"})

    model = Model()
    report = asyncio.run(check.run_check(model, {
        "snapshot": snapshot, "context": context, "observations": observations,
    }))
    assert model.calls == 1 and report["status"] == "completed"
    assert report["output"] == before == raw
    assert report["result"]["profile"]["accountPortrait"]["summary"] == claim()
    assert report["result"]["profile"]["hookStyles"] == writing_fields()["hookStyles"]


@pytest.mark.parametrize("factory", [misplaced_portrait, misplaced_writing])
def test_production_workflow_uses_same_normalization_without_mutating_provider_output(app, factory):
    workspace = create_workspace(app)
    snapshot = selected_snapshot()
    source = create_text_material(app, workspace["id"], "xhs_creator_profile", json.dumps({
        "schemaVersion": "xhs-creator-profile/v1", "creator": {"displayName": "测试账号"},
        **snapshot["xhsCreatorProfile"],
    }, ensure_ascii=False))
    response = send(app, "POST", f"/api/workspaces/{workspace['id']}/analysis-runs", json={
        "workflowType": "account_diagnosis", "xhsCreatorProfileInputAssetId": source["id"],
        "selectedNoteIds": ["n1"], "mode": "live",
    })
    assert response.status_code == 201
    raw = factory()
    before = deepcopy(raw)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile(self, **kwargs):
            return raw

    app.state.account_workflow_service.live_provider = Provider()
    run_id = response.json()["id"]
    asyncio.run(app.state.account_workflow_service.collect_events(run_id))
    result = send(app, "GET", f"/api/analysis-runs/{run_id}").json()["stageResults"]["profile"]
    assert result["profile"]["accountPortrait"]["summary"] == claim()
    assert result["profile"]["hookStyles"] == writing_fields()["hookStyles"]
    assert raw == before
