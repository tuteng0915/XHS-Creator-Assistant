import json
from copy import deepcopy

import pytest

from app.models import DraftKind
from app.services.account_report_editorial import compile_editorial_profile
from app.services.draft_generation import DraftGenerationService
from app.workflows.account_diagnosis import ProfileStageResult


def input_snapshot(app, profile):
    workspace = {
        "id": "workspace", "name": "测试账号", "account_positioning": "生活记录",
        "positioning_version": 1,
    }
    topic = {
        "id": "topic", "title": "一个新的选择", "angle": "具体处境",
        "associated_pain_point": "难以判断", "why_it_fits": "延续账号表达",
        "source_workflow": "account_diagnosis", "source_analysis_run_id": "run",
    }
    source_run = {
        "workflow_type": "account_diagnosis",
        "stage_results_json": json.dumps({"profile": {"profile": profile}}),
    }
    before = deepcopy((workspace, topic, source_run))
    result = app.state.draft_generation_service._input_snapshot(
        workspace, topic, source_run, "demo",
    )
    assert (workspace, topic, source_run) == before
    return result


@pytest.mark.parametrize("kind", [DraftKind.CONTENT_BRIEF, DraftKind.CONTENT_STRUCTURE])
def test_lean_expression_and_next_steps_reach_draft_without_inventing_structure(app, kind):
    profile = {
        "accountPortrait": {
            "expressionPatterns": [{
                "statement": "把选择前后的犹豫讲具体，再给出自己的判断。",
                "evidence": [{"noteId": "note-1", "scope": "note"}],
            }],
            "nextSteps": [{
                "statement": "下一篇可以保留一次没选的方案及其理由。",
                "evidence": [{"noteId": "note-2", "quote": "不要重复传入这段原文"}],
            }],
        },
        "voiceFingerprint": [],
        "viralStructure": {},
        "contrast": {},
    }
    original = deepcopy(profile)
    snapshot = input_snapshot(app, profile)
    snapshot_before = deepcopy(snapshot)
    context = DraftGenerationService._model_context(snapshot, kind)
    background = json.loads(context["background"])
    assert background == {
        "expressionPatterns": ["把选择前后的犹豫讲具体，再给出自己的判断。"],
        "writingSuggestions": ["下一篇可以保留一次没选的方案及其理由。"],
    }
    assert "viralStructure" not in background
    assert "不要重复传入这段原文" not in context["background"]
    assert profile == original
    assert snapshot == snapshot_before


def test_legacy_draft_context_remains_exactly_the_same(app):
    profile = {
        "voiceFingerprint": ["旧版确认的表达方式"],
        "viralStructure": {"name": "旧版结构", "steps": ["开头", "正文"]},
        "contrast": {"takeaways": ["旧版建议"]},
    }
    snapshot = input_snapshot(app, profile)
    expected = {key: profile[key] for key in ("voiceFingerprint", "viralStructure")}
    assert snapshot["analysisContext"] == expected
    result = DraftGenerationService._model_context(snapshot, DraftKind.CONTENT_STRUCTURE)
    assert result["background"] == json.dumps(expected, ensure_ascii=False)


def test_existing_voice_and_suggestions_take_priority_over_lean_fields(app):
    profile = {
        "voiceFingerprint": ["旧表达"],
        "viralStructure": {"name": "旧结构", "steps": ["旧步骤"]},
        "contrast": {"takeaways": ["旧建议"]},
        "accountPortrait": {
            "expressionPatterns": [{"statement": "新表达", "evidence": []}],
            "nextSteps": [{"statement": "新建议", "evidence": []}],
        },
    }
    snapshot = input_snapshot(app, profile)
    result = DraftGenerationService._model_context(snapshot, DraftKind.CONTENT_BRIEF)
    background = json.loads(result["background"])
    assert background == {
        "voiceFingerprint": profile["voiceFingerprint"],
        "viralStructure": profile["viralStructure"],
        "writingSuggestions": ["旧建议"],
    }


def test_voice_only_context_is_not_lost_without_a_structure(app):
    snapshot = input_snapshot(app, {"voiceFingerprint": ["保留原有口吻"]})
    result = DraftGenerationService._model_context(snapshot, DraftKind.CONTENT_BRIEF)
    assert json.loads(result["background"]) == {
        "voiceFingerprint": ["保留原有口吻"],
    }


@pytest.mark.parametrize("kind", [DraftKind.CONTENT_BRIEF, DraftKind.CONTENT_STRUCTURE])
def test_compiled_lean_report_defaults_are_not_added_to_model_context(app, kind):
    material = {"xhsCreatorProfile": {"notes": [
        {"noteId": "stable-note", "title": "一次选择", "desc": "选择前后的具体犹豫。"},
    ]}}
    output = {"profile": {
        "reportFormat": "editorial/v1",
        "summary": {"text": "关心选择背后的具体条件", "noteIds": ["n1"]},
        "keywords": [], "directions": [], "strengths": [],
        "writing": [{"text": "把选择前后的犹豫讲具体。", "noteIds": ["n1"]}],
        "nextSteps": [{"text": "下一篇延续一次选择背后的理由。", "noteIds": ["n1"]}],
    }}
    profile = ProfileStageResult.model_validate(
        compile_editorial_profile(output, material)
    ).model_dump(mode="json")["profile"]
    original = deepcopy(profile)
    assert profile["viralStructure"] == {"name": "", "steps": []}
    assert profile["voiceFingerprint"] == []
    snapshot = input_snapshot(app, profile)
    background = json.loads(DraftGenerationService._model_context(snapshot, kind)["background"])
    assert background == {
        "expressionPatterns": ["把选择前后的犹豫讲具体。"],
        "writingSuggestions": ["下一篇延续一次选择背后的理由。"],
    }
    assert profile == original


def test_structure_without_voice_preserves_only_meaningful_legacy_content(app):
    structure = {"name": "旧结构", "steps": ["旧步骤"]}
    snapshot = input_snapshot(app, {"viralStructure": structure})
    background = DraftGenerationService._model_context(snapshot, DraftKind.CONTENT_BRIEF)
    assert json.loads(background["background"]) == {"viralStructure": structure}


def test_malformed_optional_portrait_entries_do_not_enter_draft_context(app):
    profile = {"accountPortrait": {
        "expressionPatterns": [None, {"statement": 7}, {"statement": " "}],
        "nextSteps": [None, {"statement": []}, {"statement": ""}],
    }}
    snapshot = input_snapshot(app, profile)
    result = DraftGenerationService._model_context(snapshot, DraftKind.CONTENT_BRIEF)
    assert result["background"] == ""
