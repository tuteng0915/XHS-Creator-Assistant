"""The model supplies editorial judgments; code supplies source identities/UI shape."""

import json
from copy import deepcopy

import pytest

from app.models import ModelOperation
from app.services.account_report_editorial import compile_editorial_profile
from app.services.account_report_lean import LEAN_PROFILE_PROMPT, lean_profile_messages
from app.services.account_report_prompt import SOURCE_LED_PROFILE_PROMPT
from app.services.model_calls import ModelCallService
from app.workflows.account_diagnosis import ProfileStageResult


@pytest.fixture
def snapshot():
    return {"xhsCreatorProfile": {"notes": [
        {"noteId": "stable-a", "title": "整理杂物", "desc": "第一段。\n\n第二段…… 保留空格。"},
        {"noteId": "stable-b", "title": "一张路线图", "desc": "不同方向分别展开。"},
    ]}}


@pytest.fixture
def output():
    def item(text, ids=None):
        return {"text": text, "noteIds": ids or ["n1"]}
    return {"profile": {
        "reportFormat": "editorial/v1", "summary": item("两个独立的日常主题", ["n1", "n2"]),
        "keywords": [item("整理杂物")], "directions": [item("整理时如何选择保留什么")],
        "strengths": [item("具体指出一次选择")],
        "writing": [item("不同方向分别展开", ["n2"])],
        "nextSteps": [item("下次写整理时，讲一次改变保留标准的选择")],
    }, "metadata": {"keep": [1]}}


def test_input_preserves_whole_original_bodies_without_metrics_or_excerpt_catalog(snapshot):
    notes = [{**note, "body": note["desc"], "metrics": {"likes": 99}}
             for note in snapshot["xhsCreatorProfile"]["notes"]]
    context = {"positioning": "合成账号", "historicalPosts": json.dumps({
        "schemaVersion": "account-reading-input/v2", "notes": notes,
        "readingScope": {"metricSummaries": {"likes": 99}},
    })}
    before = deepcopy(context)
    system, user = lean_profile_messages(context)
    material = json.loads(user.split("所选笔记：\n", 1)[1])
    assert material == {"notes": [
        {"noteId": f"n{i}", "title": note["title"], "body": note["desc"]}
        for i, note in enumerate(snapshot["xhsCreatorProfile"]["notes"], 1)
    ]}
    assert context == before
    assert system == LEAN_PROFILE_PROMPT and "JSON" in system
    assert all(term not in system for term in ("structureReading", "excerptId", "repeated_blocks"))
    assert len(system) < 1600


def test_uniform_items_map_to_existing_sections_and_new_next_steps(snapshot, output):
    original, source = deepcopy(output), deepcopy(snapshot)
    compiled = compile_editorial_profile(output, snapshot)
    portrait = ProfileStageResult.model_validate(compiled).profile.accountPortrait
    assert portrait["readerValue"][0]["statement"] == output["profile"]["directions"][0]["text"]
    assert portrait["expressionPatterns"][0]["evidence"] == [
        {"noteId": "stable-b", "scope": "note"},
    ]
    assert portrait["nextSteps"][0]["evidence"] == [{"noteId": "stable-a", "scope": "note"}]
    assert "quote" not in portrait["summary"]["evidence"][0]
    assert compiled["metadata"] == original["metadata"]
    compiled["metadata"]["keep"].clear()
    assert output == original and snapshot == source


@pytest.mark.parametrize("ids", [["n3"], ["stable-a"], [], [1]])
def test_unknown_stable_and_malformed_source_ids_are_not_guessed(snapshot, output, ids):
    output["profile"]["summary"]["noteIds"] = ids
    with pytest.raises(ValueError):
        compile_editorial_profile(output, snapshot)


def test_local_ids_only_have_request_order_meaning_even_if_stable_id_looks_local(snapshot, output):
    snapshot["xhsCreatorProfile"]["notes"][1]["noteId"] = "n1"
    portrait = compile_editorial_profile(output, snapshot)["profile"]["accountPortrait"]
    assert portrait["summary"]["evidence"] == [
        {"noteId": "stable-a", "scope": "note"}, {"noteId": "n1", "scope": "note"},
    ]


def test_duplicate_refs_deduplicate_without_rewriting_judgment(snapshot, output):
    output["profile"]["summary"]["noteIds"] = ["n1", "n1"]
    result = compile_editorial_profile(output, snapshot)
    assert result["profile"]["accountPortrait"]["summary"] == {
        "statement": "两个独立的日常主题", "evidence": [{"noteId": "stable-a", "scope": "note"}],
    }


@pytest.mark.parametrize("field,value", [
    ("summary", {"text": "", "noteIds": ["n1"]}),
    ("summary", {"text": "字" * 201, "noteIds": ["n1"]}),
    ("keywords", [{"text": "字" * 13, "noteIds": ["n1"]}]),
    ("titleReadings", []),
    ("accountPortrait", {"summary": "冲突旧字段"}),
])
def test_bad_or_dual_contract_output_is_rejected_not_silently_dropped(
    snapshot, output, field, value,
):
    output["profile"][field] = value
    with pytest.raises(ValueError):
        compile_editorial_profile(output, snapshot)


def test_duplicate_frozen_identity_is_rejected(snapshot, output):
    snapshot["xhsCreatorProfile"]["notes"].append(snapshot["xhsCreatorProfile"]["notes"][0])
    with pytest.raises(ValueError):
        compile_editorial_profile(output, snapshot)


def test_candidate_does_not_replace_default_without_quality_acceptance(settings):
    context = {"historicalPosts": json.dumps({
        "schemaVersion": "account-reading-input/v2", "notes": [],
    })}
    system, _ = ModelCallService(settings)._build_prompt(ModelOperation.PROFILE, context)
    assert system == SOURCE_LED_PROFILE_PROMPT
    assert system != LEAN_PROFILE_PROMPT


def test_editorial_task_invites_generalization_without_requiring_identical_articles():
    assert "跨篇归纳是这份报告的主要价值" in LEAN_PROFILE_PROMPT
    assert "不必每篇都用相同的措辞、步骤或结构" in LEAN_PROFILE_PROMPT
    assert "举例中的人、经历、措辞和顺序则按原作" in LEAN_PROFILE_PROMPT
    assert "不从一个局部推出大家都适用的模式" not in LEAN_PROFILE_PROMPT
    for name in ("QSheep", "一粒鱼", "FinTech", "Hassan"):
        assert name not in LEAN_PROFILE_PROMPT


def test_sections_separate_account_synthesis_examples_and_future_actions():
    tasks = dict(
        line.removeprefix("- ").split("：", 1)
        for line in LEAN_PROFILE_PROMPT.splitlines()
        if line.startswith("- ")
    )
    assert set(tasks) == {"summary", "keywords", "directions", "strengths", "writing", "nextSteps"}
    assert "不展开例子" in tasks["summary"]
    assert "不排列作品或复述人物与事件" in tasks["directions"]
    assert "预告介绍打算展开的问题，不当成已给出的答案" in tasks["directions"]
    assert "每个例子的具体表现各归其文" in tasks["strengths"]
    assert "不重讲内容方向与优势" in tasks["writing"]
    assert "下一篇可以【方向】；试着【编辑动作】，让读者【阅读价值】" in tasks["nextSteps"]
    assert "text不复述旧经历" in tasks["nextSteps"]
    assert "noteIds仍指向启发建议的作品" in tasks["nextSteps"]
    assert "同一作品可以支撑不同判断" in LEAN_PROFILE_PROMPT


def test_future_action_keeps_source_links_without_requiring_past_story_recap(snapshot, output):
    action = "下一篇比较两种保留标准怎样改变选择，让读者找到适合自己的取舍。"
    output["profile"]["nextSteps"] = [{"text": action, "noteIds": ["n1", "n2"]}]
    portrait = compile_editorial_profile(output, snapshot)["profile"]["accountPortrait"]
    assert portrait["nextSteps"] == [{
        "statement": action,
        "evidence": [{"noteId": "stable-a", "scope": "note"},
                     {"noteId": "stable-b", "scope": "note"}],
    }]


def test_report_can_omit_next_steps_without_inventing_an_omission(snapshot, output):
    output["profile"]["nextSteps"] = []
    result = compile_editorial_profile(output, snapshot)
    assert result["profile"]["accountPortrait"]["nextSteps"] == []
    assert result["profile"]["accountPortrait"]["strengths"]


def test_compiler_preserves_account_level_interpretation_with_distinct_note_references(
    snapshot, output,
):
    output["profile"]["strengths"] = [{
        "text": "你善于用身边的生活条件解释选择，不照搬一套标准答案。",
        "noteIds": ["n1", "n2"],
    }]
    result = compile_editorial_profile(output, snapshot)
    claim = result["profile"]["accountPortrait"]["strengths"][0]
    assert claim["statement"] == output["profile"]["strengths"][0]["text"]
    assert claim["evidence"] == [
        {"noteId": "stable-a", "scope": "note"}, {"noteId": "stable-b", "scope": "note"},
    ]
