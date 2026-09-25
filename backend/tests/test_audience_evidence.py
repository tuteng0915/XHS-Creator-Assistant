import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.services.audience_analyses import AudienceResult
from app.services.audience_evidence import (
    AudienceEvidence,
    audience_context,
    select_audience_personas,
    validate_evidence,
)
from app.workflows.audience_simulation import (
    AudienceSimulationWorkflowService,
    PersonaDefinition,
    PersonaDefinitionsResult,
    PersonaReaction,
    validate_trigger_quote,
)


def context():
    return audience_context({
        "creator": {"displayName": "甲", "profileText": "范围外的全局摘要"},
        "notes": [{"noteId": "n", "title": "申请经历", "desc": "真实正文",
                   "comments": [{"commentId": "c", "content": "具体费用多少？"}]}],
    })


def ref(**changes):
    return AudienceEvidence.model_validate({
        "noteId": "n", "commentId": "c", "sourceType": "comment",
        "quote": "费用多少", **changes,
    })


def test_context_keeps_ids_and_sampling_not_unscoped_summary():
    data = context()
    assert "profileText" not in data["creator"]
    assert data["notes"][0]["comments"][0]["commentId"] == "c"
    assert data["sampling"]["sentComments"] == 1
    validate_evidence([ref()], data)


@pytest.mark.parametrize("changes", [
    {"noteId": "other"}, {"commentId": "other"}, {"quote": "不存在"},
    {"quote": " "}, {"sourceType": "note"},
])
def test_evidence_rejects_invented_or_mismatched_source(changes):
    with pytest.raises(ValueError):
        validate_evidence([ref(**changes)], context())


def test_missing_evidence_rejected():
    with pytest.raises(ValueError):
        validate_evidence([], context())


def test_content_inference_without_comments_is_explicit():
    data = context()
    data["notes"][0]["comments"] = []
    validate_evidence([ref(commentId=None, sourceType="note", quote="真实正文")], data)


def test_grounded_result_clears_estimates_and_preserves_verified_refs():
    result = AudienceResult.model_validate({
        "summary": "费用视角", "limitations": "样本少", "groups": [{
            "id": "g", "name": "申请者", "profile": "关注费用",
            "estimatedPercent": 80, "evidence": ["模型的改写不作引文"],
            "evidenceRefs": [ref().model_dump(by_alias=True)],
        }],
    }).grounded_result(context())
    assert result["method"] == "evidence_grounded_v1"
    assert result["groups"][0]["estimatedPercent"] is None
    assert result["groups"][0]["evidence"] == ["费用多少"]
    selected = select_audience_personas(result)[0]
    persona = PersonaDefinition.model_validate(selected).model_dump(by_alias=True)
    assert persona["evidenceRefs"][0]["commentId"] == "c"
    assert persona["limitations"] == "样本少"


def test_legacy_audience_is_readable_but_not_verified():
    selected = select_audience_personas({"groups": [
        {"id": "a", "estimatedPercent": 20}, {"id": "b", "estimatedPercent": 80},
    ]})
    assert selected[0]["id"] == "b"
    assert selected[0]["evidenceStatus"] == "legacy_unverified"


@pytest.mark.parametrize("action", ["no_comment", "skip"])
def test_silence_cannot_leak_generated_public_comment(action):
    reaction = PersonaReaction(personaId="p", stance="无感", action=action,
                               quote="不应公开", text="旧字段也不能泄露")
    assert reaction.quote == reaction.text == ""


def test_reader_does_not_receive_strategy_fields():
    target = AudienceSimulationWorkflowService._simulation_target_context({
        "topic": {"title": "标题", "body": "正文", "whyItFits": "你一定会喜欢",
                  "angle": "内部切角", "associatedPainPoint": "内部痛点"},
        "draft": {"editableContent": {"brief": {"targetReader": "身份推测",
                    "readerPain": "让人相信", "openingHook": "开场白"}}},
    })
    assert "whyItFits" not in target and "angle" not in target
    assert target["draft"]["editableContent"]["brief"] == {"openingHook": "开场白"}


def test_trigger_quote_must_be_in_reader_visible_text():
    target = {"title": "费用明细", "body": "第一步准备申请费", "limitations": "不是正文"}
    validate_trigger_quote("申请费", target)
    with pytest.raises(ValueError):
        validate_trigger_quote("不是正文", target)
    with pytest.raises(ValueError):
        validate_trigger_quote("编造的数字", target)


def test_duplicate_personas_are_rejected():
    with pytest.raises(ValueError):
        PersonaDefinitionsResult.model_validate({"personas": [
            {"id": "p", "name": "甲", "profile": "需要资料"},
            {"id": "p", "name": "乙", "profile": "需要资料"},
        ]})


def load_research():
    path = Path(__file__).resolve().parents[2] / "scripts/audience_research_cases.py"
    spec = importlib.util.spec_from_file_location("audience_cases", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def research_profile():
    return {"creator": {"profileText": "含测试答案的摘要"}, "notes": [
        {"noteId": "past", "publishedAt": 1000, "title": "旧帖", "desc": "旧正文",
         "comments": [
             {"content": "可用证据", "createTime": 1100},
             {"content": "未来评论", "createTime": 3000},
             {"content": "未知日期"},
             {"content": "答案文本", "createTime": 1200},
         ]},
        {"noteId": "target", "publishedAt": 2000, "title": "新帖", "desc": "新正文",
         "comments": [{"content": "答案文本", "createTime": 2100}], "likes": 9999},
        {"noteId": "future", "publishedAt": 3000, "title": "未来信息"},
    ]}


def test_research_temporal_split_removes_future_and_answer_leakage():
    inputs, answers = load_research().prepare_case(research_profile(), "target")
    assert len(inputs["history"]["notes"]) == 1
    comments = inputs["history"]["notes"][0]["comments"]
    assert [c["content"] for c in comments] == ["可用证据"]
    assert inputs["stimulus"] == {"title": "新帖", "body": "新正文"}
    assert "答案文本" not in str(inputs)
    assert "profileText" not in str(inputs) and "9999" not in str(inputs)
    assert answers["observedComments"][0]["content"] == "答案文本"
    assert inputs["omittedComments"] == 3


@pytest.mark.parametrize("change", ["missing_date", "duplicate_id", "no_history"])
def test_research_refuses_invalid_temporal_cases(change):
    data = research_profile()
    if change == "missing_date":
        del data["notes"][1]["publishedAt"]
    elif change == "duplicate_id":
        data["notes"][0]["noteId"] = "target"
    else:
        data["notes"] = data["notes"][1:]
    with pytest.raises(ValueError):
        load_research().prepare_case(data, "target")


def test_research_cli_separates_utf8_answers_and_refuses_overwrite(tmp_path):
    script = Path(__file__).resolve().parents[2] / "scripts/audience_research_cases.py"
    source = tmp_path / "profile.json"
    source.write_text(json.dumps(research_profile(), ensure_ascii=False), encoding="utf-8")
    output = tmp_path / "research"
    command = [sys.executable, str(script), str(source), "--target-id", "target",
               "--output", str(output)]
    subprocess.run(command, check=True, capture_output=True)
    inputs = (output / "inputs.json").read_text(encoding="utf-8")
    answers = (output / "heldout-answers.json").read_text(encoding="utf-8")
    assert "可用证据" in inputs and "答案文本" not in inputs
    assert "答案文本" in answers
    repeated = subprocess.run(command, check=False, capture_output=True)
    assert repeated.returncode != 0
    assert (output / "inputs.json").read_text(encoding="utf-8") == inputs
