from copy import deepcopy

import pytest

from app.services import account_report_delivery
from app.services.account_diagnosis_evidence import verified_portrait
from app.services.account_report_delivery import compile_usable_account_report
from app.services.account_report_editorial import compile_editorial_profile


@pytest.fixture
def snapshot():
    return {"xhsCreatorProfile": {"notes": [
        {"noteId": "stable-a", "title": "先开盒子，再摆木块",
         "desc": "先打开盒子。再摆出木块。比较两种摆法。"},
        {"noteId": "stable-b", "title": "走廊里的一次停步",
         "desc": "我先看见门边的纸片。接着停下来想了一会。"},
    ]}}


def claim(statement="你用具体动作记录日常观察。", *note_ids):
    return {"statement": statement, "evidence": [
        {"noteId": note_id, "excerptId": "b1"} for note_id in note_ids or ("n1",)
    ]}


def report():
    return {"profile": {"reportFormat": "source-led/v3", "accountPortrait": {
        "summary": claim(),
    }}}


def title():
    return {"noteId": "n1", "parts": [
        {"text": "先开盒子", "role": "起始动作"}, {"text": "再摆木块", "role": "后续动作"},
    ]}


def expression():
    return {"kind": "opening", "technique": "先写一个可见动作。", "application": "用动作进入现场。",
            "examples": [{"noteId": "n1", "fromExcerptId": "b1", "toExcerptId": "b1"}]}


def structure():
    return {"noteId": "n1", "kind": "narrative", "scope": "whole_note", "scopeLabel": "",
            "overview": "沿动作推进。", "units": [
                {"excerptIds": ["b1"], "label": "打开", "reading": "呈现盒子。"},
                {"excerptIds": ["b2"], "label": "摆放", "reading": "说明摆法。"},
            ]}


def move():
    return {"sourceNoteId": "n1", "sourceExcerptId": "b2", "basis": "原文写出摆放动作。",
            "action": "下次写一次动作的先后顺序。"}


def test_missing_optional_keys_compile_locally_without_model_or_empty_placeholders(snapshot):
    omissions = []
    result = compile_usable_account_report(report(), snapshot, omissions=omissions)["profile"]
    assert result["titleFormulas"] == result["hookStyles"] == result["voiceFingerprint"] == []
    assert result["viralStructure"] == {"name": "", "steps": []}
    assert result["contrast"]["takeaways"] == []
    for field in ("keywords", "recurringThemes", "strengths"):
        assert result["accountPortrait"][field] == []
    assert result["accountPortrait"]["summary"]["evidence"] == [
        {"noteId": "stable-a", "quote": "先打开盒子。"},
    ]
    assert omissions == []


def test_bad_title_and_suggestion_do_not_destroy_valid_items_or_report(snapshot):
    raw = report()
    raw["profile"].update({
        "titleReadings": [{**title(), "noteId": "wrong"}, title()],
        "nextMoves": [{**move(), "sourceExcerptId": "b99"}, move()],
    })
    omissions = []
    result = compile_usable_account_report(raw, snapshot, omissions=omissions)["profile"]
    assert len(result["titleFormulas"]) == len(result["contrast"]["takeaways"]) == 1
    assert "先开盒子" in result["titleFormulas"][0]["formula"]
    assert "下次写一次动作" in result["contrast"]["takeaways"][0]
    assert result["accountPortrait"]["summary"]
    assert omissions == ["titleReadings[0]:invalid", "nextMoves[0]:invalid"]


def test_bad_optional_column_shapes_are_omitted_without_fabricating_content(snapshot):
    raw = report()
    raw["profile"].update({"titleReadings": {}, "expressionReadings": "not a list",
                           "nextMoves": False, "structureReading": []})
    raw["profile"]["accountPortrait"]["keywords"] = "not a list"
    omissions = []
    result = compile_usable_account_report(raw, snapshot, omissions=omissions)["profile"]
    assert result["accountPortrait"]["keywords"] == []
    assert result["titleFormulas"] == result["hookStyles"] == []
    assert result["viralStructure"] == {"name": "", "steps": []}
    assert omissions == ["accountPortrait.keywords:invalid", "titleReadings:invalid",
                         "expressionReadings:invalid", "nextMoves:invalid",
                         "structureReading:invalid"]


def test_bad_expression_does_not_destroy_good_structure_and_other_expression(snapshot):
    raw = report()
    invalid = expression()
    invalid["examples"][0]["toExcerptId"] = "b99"
    raw["profile"].update({"expressionReadings": [invalid, expression()],
                           "structureReading": structure()})
    omissions = []
    result = compile_usable_account_report(raw, snapshot, omissions=omissions)["profile"]
    assert len(result["hookStyles"]) == 1
    assert result["viralStructure"]["steps"] == ["打开：呈现盒子。", "摆放：说明摆法。"]
    assert omissions == ["expressionReadings[0]:invalid"]


def test_optional_portrait_claims_are_independent_and_still_use_verified_sources(snapshot):
    raw = report()
    raw["profile"]["accountPortrait"].update({
        "keywords": [claim("日常观察"), claim("不存在", "wrong")],
        "strengths": [claim("可见的动作", "n1"), {"statement": "没有来源"}],
        "recurringThemes": [claim("具体动作观察", "n1", "n2")],
    })
    result = compile_usable_account_report(raw, snapshot)["profile"]["accountPortrait"]
    assert [item["statement"] for item in result["keywords"]] == ["日常观察"]
    assert [item["statement"] for item in result["strengths"]] == ["可见的动作"]
    assert result == verified_portrait(result, snapshot)


def test_bad_summary_reference_is_dropped_only_when_a_real_one_remains(snapshot):
    raw = report()
    raw["profile"]["accountPortrait"]["summary"]["evidence"].append(
        {"noteId": "wrong", "excerptId": "b1"},
    )
    omissions = []
    summary = compile_usable_account_report(raw, snapshot, omissions=omissions)["profile"][
        "accountPortrait"]["summary"]
    assert summary["evidence"] == [{"noteId": "stable-a", "quote": "先打开盒子。"}]
    assert omissions == ["accountPortrait.summary.evidence[1]:invalid"]


@pytest.mark.parametrize("reference", [
    {"noteId": "wrong", "excerptId": "b1"},
    {"noteId": "n1", "excerptId": "b99"},
    {"noteId": "n1", "excerptId": "b1", "quote": "伪造原句"},
    {"noteId": "n1", "quote": "先打开盒子。"},
])
def test_summary_cannot_guess_sources_or_mixed_quote_formats(snapshot, reference):
    raw = report()
    raw["profile"]["accountPortrait"]["summary"]["evidence"] = [reference]
    with pytest.raises(ValueError, match="带原文来源的有效分析"):
        compile_usable_account_report(raw, snapshot)


@pytest.mark.parametrize("summary", [None, {}, {"statement": " "}, claim(""),
                                     claim("字" * 201), {"statement": "无来源", "evidence": []}])
def test_empty_or_unverifiable_summary_alone_cannot_be_a_successful_report(snapshot, summary):
    raw = report()
    raw["profile"]["accountPortrait"]["summary"] = summary
    with pytest.raises(ValueError, match="带原文来源的有效分析"):
        compile_usable_account_report(raw, snapshot)


def test_summary_is_optional_when_report_has_the_default_chains_good_structure(snapshot):
    raw = {"profile": {"reportFormat": "source-led/v3", "structureReading": structure(),
                       "expressionReadings": [expression()]}}
    result = compile_usable_account_report(raw, snapshot)["profile"]
    assert result["accountPortrait"] is None
    assert result["viralStructure"]["steps"] == ["打开：呈现盒子。", "摆放：说明摆法。"]
    assert len(result["hookStyles"]) == 1
    raw["profile"]["accountPortrait"] = {"summary": claim("", "wrong")}
    assert compile_usable_account_report(raw, snapshot)["profile"] == result


@pytest.mark.parametrize("field,value", [
    ("titleReadings", [title()]), ("expressionReadings", [expression()]),
    ("nextMoves", [move()]), ("structureReading", structure()),
    ("accountPortrait", {"strengths": [claim("动作具体")]}),
])
def test_any_one_substantive_sourced_section_can_be_delivered(snapshot, field, value):
    raw = {"profile": {"reportFormat": "source-led/v3", field: value}}
    assert compile_usable_account_report(raw, snapshot)["profile"]


def test_keywords_alone_do_not_turn_an_empty_report_into_success(snapshot):
    raw = {"profile": {"reportFormat": "source-led/v3", "accountPortrait": {
        "keywords": [claim("日常")],
    }}}
    with pytest.raises(ValueError, match="带原文来源的有效分析"):
        compile_usable_account_report(raw, snapshot)


def test_extra_display_fields_are_ignored_without_modifying_original_text(snapshot):
    raw = report()
    raw["profile"]["extra"] = "说明"
    raw["profile"]["accountPortrait"]["summary"]["explanation"] = "附加说明"
    title_reading, expression_reading, structure_reading = title(), expression(), structure()
    for reading in (title_reading, expression_reading, structure_reading):
        reading["explanation"] = "附加说明"
    title_reading["parts"][0]["color"] = "red"
    structure_reading["units"][0]["display"] = "extra"
    del structure_reading["scopeLabel"]
    raw["profile"].update({"titleReadings": [title_reading],
                           "expressionReadings": [expression_reading],
                           "structureReading": structure_reading,
                           "nextMoves": [{**move(), "priority": "high"}]})
    before, frozen = deepcopy(raw), deepcopy(snapshot)
    omissions = []
    result = compile_usable_account_report(raw, snapshot, omissions=omissions)
    assert raw == before and snapshot == frozen
    assert len(result["profile"]["titleFormulas"]) == len(result["profile"]["hookStyles"]) == 1
    assert result["profile"]["viralStructure"]["scopeLabel"] == ""
    assert len(result["profile"]["contrast"]["takeaways"]) == 1
    assert omissions == []


def test_more_optional_items_do_not_trigger_an_all_or_nothing_maximum(snapshot):
    raw = report()
    raw["profile"]["titleReadings"] = [title()] * 4
    assert len(compile_usable_account_report(raw, snapshot)["profile"]["titleFormulas"]) == 4


def test_complete_report_matches_existing_compilation_with_existing_portrait_verification(snapshot):
    raw = report()
    raw["profile"]["accountPortrait"].update({
        "keywords": [claim("日常")], "strengths": [claim("动作具体")],
        "recurringThemes": [claim("日常观察", "n1", "n2")],
    })
    raw["profile"].update({"titleReadings": [title()], "expressionReadings": [expression()],
                           "structureReading": structure(), "nextMoves": [move()]})
    expected = compile_editorial_profile(raw, snapshot)
    expected["profile"]["accountPortrait"] = verified_portrait(
        expected["profile"]["accountPortrait"], snapshot,
    )
    assert compile_usable_account_report(raw, snapshot) == expected


def test_existing_flattened_summary_and_portrait_field_aliases_still_work(snapshot):
    raw = {"profile": {"reportFormat": "source-led/v3", "accountPortrait": {
        "summary": "你用具体动作记录日常观察。",
        "evidence": [{"noteId": "n1", "excerptId": "b1"}],
    }, "strengths": [claim("动作具体")]}}
    expected = compile_editorial_profile(raw, snapshot)
    expected["profile"]["accountPortrait"].update({"keywords": [], "recurringThemes": []})
    expected["profile"]["accountPortrait"] = verified_portrait(
        expected["profile"]["accountPortrait"], snapshot,
    )
    assert compile_usable_account_report(raw, snapshot) == expected


@pytest.mark.parametrize("duplicate", [False, True])
def test_existing_nested_next_moves_repair_matches_original_compiler(snapshot, duplicate):
    raw = report()
    raw["profile"]["accountPortrait"].update({
        "keywords": [], "strengths": [], "recurringThemes": [],
    })
    raw["profile"]["structureReading"] = {**structure(), "nextMoves": [move()]}
    if duplicate:
        raw["profile"]["nextMoves"] = [move()]
    before = deepcopy(raw)
    expected = compile_editorial_profile(raw, snapshot)
    expected["profile"]["accountPortrait"] = verified_portrait(
        expected["profile"]["accountPortrait"], snapshot,
    )
    omissions = []
    assert compile_usable_account_report(raw, snapshot, omissions=omissions) == expected
    assert expected["profile"]["contrast"]["takeaways"]
    assert raw == before and omissions == []


@pytest.mark.parametrize("top_location", ["profile", "root"])
def test_conflicting_nested_next_moves_only_drop_the_ambiguous_suggestions(snapshot, top_location):
    raw = report()
    raw["profile"]["structureReading"] = {**structure(), "nextMoves": [move()]}
    top = raw["profile"] if top_location == "profile" else raw
    top["nextMoves"] = [{**move(), "action": "这是另一条建议。"}]
    before = deepcopy(raw)
    omissions = []
    result = compile_usable_account_report(raw, snapshot, omissions=omissions)["profile"]
    assert result["contrast"]["takeaways"] == []
    assert result["viralStructure"]["steps"]
    assert result["accountPortrait"]["summary"]
    assert omissions == ["nextMoves:conflict"]
    assert raw == before


@pytest.mark.parametrize("field,other", [
    ("accountPortrait", {"summary": claim("另一份账号概括。")}),
    ("titleReadings", [{**title(), "noteId": "n2"}]),
    ("expressionReadings", [{**expression(), "technique": "另一种说明。"}]),
    ("structureReading", {**structure(), "overview": "另一种结构概括。"}),
    ("nextMoves", [{**move(), "action": "另一条建议。"}]),
])
def test_conflicting_root_and_profile_fields_are_not_silently_selected(snapshot, field, other):
    raw = report()
    raw["profile"].update({"titleReadings": [title()], "expressionReadings": [expression()],
                           "structureReading": structure(), "nextMoves": [move()]})
    raw[field] = other
    before = deepcopy(raw)
    omissions = []
    result = compile_usable_account_report(raw, snapshot, omissions=omissions)["profile"]
    assert omissions == [f"{field}:conflict"]
    if field == "accountPortrait":
        assert result["accountPortrait"] is None
    elif field == "titleReadings":
        assert result["titleFormulas"] == []
    elif field == "expressionReadings":
        assert result["hookStyles"] == result["voiceFingerprint"] == []
    elif field == "structureReading":
        assert result["viralStructure"] == {"name": "", "steps": []}
    else:
        assert result["contrast"]["takeaways"] == []
    assert raw == before


def test_conflicting_top_level_next_moves_cannot_be_salvaged_by_picking_a_nested_copy(snapshot):
    raw = report()
    raw["profile"].update({"nextMoves": [move()],
                           "structureReading": {**structure(), "nextMoves": [move()]}})
    raw["nextMoves"] = [{**move(), "action": "不同的建议。"}]
    omissions = []
    result = compile_usable_account_report(raw, snapshot, omissions=omissions)["profile"]
    assert result["contrast"]["takeaways"] == []
    assert result["viralStructure"]["steps"]
    assert omissions == ["nextMoves:conflict"]


def test_legacy_and_already_compiled_outputs_keep_old_behavior_and_are_idempotent(snapshot):
    legacy = {"profile": {"titleFormulas": [{"formula": "旧标题", "examples": []}],
                           "accountPortrait": {"summary": {"statement": "旧历史"}}}}
    assert compile_usable_account_report(legacy, {}) == compile_editorial_profile(legacy, {})
    result = compile_usable_account_report(report(), snapshot)
    before = deepcopy(result)
    assert compile_usable_account_report(result, snapshot) == result == before
    assert compile_usable_account_report(result, snapshot)["profile"] is not result["profile"]
    # The unchanged historical compiler can still read saved source-backed data
    # without the original snapshot; only new generation uses this boundary check.
    assert compile_editorial_profile(result, {}) == result


def test_obvious_current_source_fields_without_version_are_compiled_not_left_unresolved(snapshot):
    raw = report()
    del raw["profile"]["reportFormat"]
    assert compile_usable_account_report(raw, snapshot) == compile_usable_account_report(
        report(), snapshot,
    )
    only_structure = {"profile": {"structureReading": structure()}}
    assert compile_usable_account_report(only_structure, snapshot)["profile"][
        "viralStructure"]["steps"]
    only_move = {"profile": {"nextMoves": [move()]}}
    assert compile_usable_account_report(only_move, snapshot)["profile"]["contrast"]["takeaways"]


@pytest.mark.parametrize("profile", [
    {}, {"invalid": True}, {"accountPortrait": None}, {"titleFormulas": []},
    {"accountPortrait": {"summary": {"statement": "结论", "evidence": []}}},
    {"accountPortrait": {"summary": {"statement": "结论", "evidence": [
        {"noteId": "missing", "quote": "不存在的原句"},
    ]}}},
    {"titleFormulas": [{"formula": " ", "examples": []}]},
    {"pillars": [], "hookStyles": [], "voiceFingerprint": [" "],
     "viralStructure": {"name": "", "steps": []}, "contrast": {"takeaways": []}},
    {"accountPortrait": {"keywords": [
        {"statement": "日常", "evidence": [{"noteId": "stable-a", "quote": "先打开盒子。"}]},
    ]}},
])
def test_empty_or_unknown_profile_does_not_bypass_final_recovery(snapshot, profile):
    with pytest.raises(ValueError, match="尚无可用的分析内容"):
        compile_usable_account_report({"profile": profile}, snapshot)


@pytest.mark.parametrize("profile", [
    {"pillars": ["具体经历分享"]},
    {"hookStyles": ["先描述具体动作"]},
    {"voiceFingerprint": ["短句串起动作"]},
    {"titleFormulas": [{"formula": "", "examples": ["先开盒子，再摆木块"]}]},
    {"viralStructure": {"name": "按动作顺序展开", "steps": []}},
    {"contrast": {"takeaways": ["下次保留动作细节"]}},
    {"accountPortrait": {"summary": {
        "statement": "从具体动作进入现场。",
        "evidence": [{"noteId": "stable-a", "quote": "先打开盒子。"}],
    }}},
    {"accountPortrait": {"hookStyles": ["先描述具体动作"]}},
])
def test_nonempty_legacy_report_keeps_existing_compiler_output_exactly(snapshot, profile):
    raw = {"profile": profile}
    assert compile_usable_account_report(raw, snapshot) == compile_editorial_profile(raw, snapshot)


def test_known_old_version_validation_is_not_silently_rewritten(snapshot):
    raw = report()
    raw["profile"]["reportFormat"] = "source-led/v2"
    raw["profile"]["nextMoves"] = [{**move(), "sourceNoteId": "wrong"}]
    with pytest.raises(ValueError):
        compile_usable_account_report(raw, snapshot)


@pytest.mark.parametrize("output", [None, [], {}, {"profile": []}, {"invalid": True}])
def test_missing_profile_keeps_the_existing_transport_contract(snapshot, output):
    with pytest.raises(ValueError, match="profile 对象"):
        compile_usable_account_report(output, snapshot)


def test_omissions_never_contain_generated_content_or_invented_ids(snapshot):
    raw = report()
    raw["profile"]["nextMoves"] = [{**move(), "sourceNoteId": "PRIVATE_FAKE_ID",
                                     "action": "PRIVATE_CONTENT"}]
    omissions = []
    compile_usable_account_report(raw, snapshot, omissions=omissions)
    assert omissions == ["nextMoves[0]:invalid"]


def test_unknown_compiler_errors_escape_instead_of_becoming_silent_omissions(snapshot, monkeypatch):
    original = account_report_delivery.compile_editorial_profile

    def broken(output, snapshot):
        if "nextMoves" in output["profile"]:
            raise RuntimeError("Unexpected compiler bug")
        return original(output, snapshot)

    monkeypatch.setattr(account_report_delivery, "compile_editorial_profile", broken)
    raw = report()
    raw["profile"]["nextMoves"] = [move()]
    with pytest.raises(RuntimeError, match="Unexpected compiler bug"):
        compile_usable_account_report(raw, snapshot)
