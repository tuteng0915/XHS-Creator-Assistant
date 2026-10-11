"""Fictional sources exercise v3 literal/order checks, not semantic judgments."""

from copy import deepcopy

import pytest

from app.services.account_report_editorial import compile_editorial_profile
from app.services.account_report_sources import build_report_sources, resolve_editorial_refs
from app.workflows.account_diagnosis import ProfileStageResult, ViralStructure


@pytest.fixture
def snapshot():
    return {"xhsCreatorProfile": {"notes": [
        {"noteId": "stable-a", "title": "先开盒子，再摆木块",
         "desc": "先打开盒子。再摆出木块。比较两种摆法。留下一处空位。记下变化。"},
        {"noteId": "stable-b", "title": "走廊里的一次停步",
         "desc": "我先看见门边的纸片。接着停下来想了一会。"},
    ]}}


def structure(kind="narrative", scope="whole_note"):
    return {"noteId": "n1", "kind": kind, "scope": scope,
            "scopeLabel": "摆放部分" if scope == "section" else "", "overview": "观察一次摆放过程",
            "units": [{"label": "打开", "excerptIds": ["b1"], "reading": "先呈现盒子"},
                      {"label": "摆放", "excerptIds": ["b2", "b3"], "reading": "再描述摆法"}]}


def expression(kind="wording", examples=None):
    return {"kind": kind, "technique": "用具体动作引入", "application": "先交代一次可见动作",
            "examples": examples or [{"noteId": "n1", "excerptId": "b1", "quote": "打开盒子"}]}


def output(reading=None, expressions=None):
    return {"profile": {"reportFormat": "source-led/v3", "structureReading": reading,
                        "expressionReadings": expressions or [], "titleReadings": [],
                        "nextMoves": []}}


def span(first="b1", last="b2", note_id="n1"):
    return {"noteId": note_id, "fromExcerptId": first, "toExcerptId": last}


@pytest.mark.parametrize("kind", ["narrative", "comparison", "repeated_blocks"])
def test_three_structure_kinds_compile_and_survive_final_model_without_mutating_inputs(
    snapshot, kind,
):
    raw = output(structure(kind, "section"))
    before, frozen = deepcopy(raw), deepcopy(snapshot)
    result = compile_editorial_profile(raw, snapshot)
    expected = {"name": "先开盒子，再摆木块", "kind": kind, "scope": "section",
                "scopeLabel": "摆放部分", "overview": "观察一次摆放过程",
                "steps": ["打开：先呈现盒子", "摆放：再描述摆法"]}
    assert result["profile"]["viralStructure"] == expected
    assert ProfileStageResult.model_validate(result).model_dump()["profile"]["viralStructure"] \
        == expected
    assert "structureReading" not in result["profile"]
    assert "expressionReadings" not in result["profile"]
    assert raw == before and snapshot == frozen


@pytest.mark.parametrize("units", [
    [["b2", "b1"], ["b3"]], [["b1", "b1"], ["b2"]],
    [["b1", "b3"], ["b2", "b4"]], [["b1", "b2"], ["b2", "b3"]],
    [["t"], ["b2"]], [["b99"], ["b2"]],
])
def test_structure_order_duplicate_crossing_and_nonbody_references_fail(snapshot, units):
    reading = structure()
    for unit, ids in zip(reading["units"], units, strict=True):
        unit["excerptIds"] = ids
    with pytest.raises(ValueError):
        compile_editorial_profile(output(reading), snapshot)


def test_structure_order_uses_catalog_positions_instead_of_string_sort(snapshot):
    snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = "".join(
        f"第{index}段。" for index in range(1, 13)
    )
    reading = structure()
    reading["units"][0]["excerptIds"] = ["b2"]
    reading["units"][1]["excerptIds"] = ["b10"]
    result = compile_editorial_profile(output(reading), snapshot)
    assert result["profile"]["viralStructure"]["scopeLabel"] == ""


def test_structure_schema_limits_unknown_ids_and_section_label_are_strict(snapshot):
    for field, value in (
        ("noteId", "unknown"), ("kind", "invented"), ("scope", "whole"),
        ("overview", " "), ("units", []), ("units", structure()["units"] * 3),
    ):
        reading = structure()
        reading[field] = value
        with pytest.raises(ValueError):
            compile_editorial_profile(output(reading), snapshot)
    reading = structure(scope="section")
    reading["scopeLabel"] = " "
    with pytest.raises(ValueError, match="scopeLabel"):
        compile_editorial_profile(output(reading), snapshot)
    for ids in ([], ["b1"] * 6):
        reading = structure()
        reading["units"][0]["excerptIds"] = ids
        with pytest.raises(ValueError):
            compile_editorial_profile(output(reading), snapshot)


def test_structure_units_may_reference_more_than_four_real_segments_without_clipping(snapshot):
    snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = "".join(
        f"第{index}段的实际内容。" for index in range(1, 25)
    )
    reading = structure()
    reading["units"][0]["excerptIds"] = [f"b{index}" for index in range(1, 10)]
    reading["units"][1]["excerptIds"] = [f"b{index}" for index in range(10, 25)]
    original = deepcopy(reading)
    result = compile_editorial_profile(output(reading), snapshot)
    assert result["profile"]["viralStructure"]["steps"] == ["打开：先呈现盒子", "摆放：再描述摆法"]
    assert reading == original
    # Check the final reference too: accepting a long unit must not silently slice it.
    reading["units"][1]["excerptIds"][-1] = "b99"
    with pytest.raises(ValueError, match="正文 b 片段"):
        compile_editorial_profile(output(reading), snapshot)
    reading["units"][1]["excerptIds"][-1] = "b23"
    with pytest.raises(ValueError, match="不重复"):
        compile_editorial_profile(output(reading), snapshot)
    reading["units"][0]["excerptIds"] = [f"b{index}" for index in range(1, 26)]
    with pytest.raises(ValueError, match="1 至 24"):
        compile_editorial_profile(output(reading), snapshot)


def test_null_structure_and_empty_body_do_not_invent_analysis_or_new_dump_fields(snapshot):
    snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = ""
    raw = output()
    raw["profile"].update({"viralStructure": {"name": "", "steps": []},
                           "hookStyles": [], "voiceFingerprint": []})
    result = compile_editorial_profile(raw, snapshot)
    parsed = ProfileStageResult.model_validate(result).model_dump()["profile"]
    assert parsed["viralStructure"] == {"name": "", "steps": []}
    assert parsed["hookStyles"] == parsed["voiceFingerprint"] == []
    with pytest.raises(ValueError):
        compile_editorial_profile(output(structure()), snapshot)
    snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = None
    with pytest.raises(ValueError, match="正文必须是文字"):
        compile_editorial_profile(output(), snapshot)


def test_expression_style_is_scoped_to_one_or_multiple_distinct_source_notes(snapshot):
    one = expression("opening", [{"noteId": "n1", "excerptId": "b1", "quote": "打开盒子"},
                                 {"noteId": "stable-a", "excerptId": "b2", "quote": "摆出木块"}])
    many = expression("transition", [
        {"noteId": "n1", "excerptId": "b1", "quote": "打开盒子"},
        {"noteId": "n2", "excerptId": "b1", "quote": "看见门边的纸片"},
    ])
    raw = output(expressions=[one, many])
    before = deepcopy(raw)
    result = compile_editorial_profile(raw, snapshot)["profile"]
    single = result["hookStyles"][0]
    multiple = result["voiceFingerprint"][0]
    assert single.startswith("《先开盒子，再摆木块》的写法：")
    assert single.count("《先开盒子，再摆木块》") == 1
    assert multiple.startswith("《先开盒子，再摆木块》《走廊里的一次停步》中都能看到的写法：")
    for item, quote in ((single, "打开盒子"), (single, "摆出木块"), (multiple, "看见门边的纸片")):
        assert f"“{quote}”" in item and "先交代一次可见动作" in item
        assert "习惯" not in item and "经常" not in item and "频率" not in item
    assert raw == before


@pytest.mark.parametrize("kind", ["wording", "rhythm", "address", "transition"])
def test_nonopening_expression_kinds_compile_only_to_voice(snapshot, kind):
    result = compile_editorial_profile(output(expressions=[expression(kind)]), snapshot)["profile"]
    assert result["hookStyles"] == [] and len(result["voiceFingerprint"]) == 1


def test_expression_quotes_must_match_the_correct_body_fragment_exactly(snapshot):
    for change in (
        {"quote": "没有这句原文"}, {"quote": "打开 盒子"}, {"quote": " "},
        {"excerptId": "t", "quote": "先开盒子"}, {"noteId": "n2"}, {"noteId": "unknown"},
        {"excerptId": "b2", "quote": "打开盒子"},
    ):
        reading = expression()
        reading["examples"][0].update(change)
        with pytest.raises(ValueError):
            compile_editorial_profile(output(expressions=[reading]), snapshot)
    snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = "字" * 150 + "。"
    reading = expression(examples=[{"noteId": "n1", "excerptId": "b1", "quote": "字" * 100}])
    assert compile_editorial_profile(output(expressions=[reading]), snapshot)
    reading["examples"][0]["quote"] += "字"
    with pytest.raises(ValueError, match="不超过100字"):
        compile_editorial_profile(output(expressions=[reading]), snapshot)


def test_expression_duplicate_refs_use_stable_identity_and_limits_are_not_silently_clipped(
    snapshot,
):
    reading = expression(examples=[{"noteId": "n1", "excerptId": "b1", "quote": "打开盒子"},
                                   {"noteId": "stable-a", "excerptId": "b1", "quote": "先打开"}])
    with pytest.raises(ValueError, match="不能重复引用"):
        compile_editorial_profile(output(expressions=[reading]), snapshot)
    for examples in ([], [expression()["examples"][0]] * 4):
        reading = expression()
        reading["examples"] = examples
        with pytest.raises(ValueError):
            compile_editorial_profile(output(expressions=[reading]), snapshot)
    with pytest.raises(ValueError, match="0 至 3"):
        compile_editorial_profile(output(expressions=[expression()] * 4), snapshot)
    for field, value in (("kind", "unknown"), ("technique", " "), ("application", [])):
        reading = expression()
        reading[field] = value
        with pytest.raises(ValueError):
            compile_editorial_profile(output(expressions=[reading]), snapshot)


def test_expression_spans_restore_whole_source_and_use_stable_note_identity(snapshot):
    one = expression("rhythm", [span(), span("b3", "b3", "stable-a")])
    many = expression("opening", [span(), span(note_id="n2")])
    raw = output(expressions=[one, many])
    before, frozen = deepcopy(raw), deepcopy(snapshot)
    result = compile_editorial_profile(raw, snapshot)["profile"]
    single, multiple = result["voiceFingerprint"][0], result["hookStyles"][0]
    assert "“先打开盒子。再摆出木块。”" in single
    assert "“比较两种摆法。”" in single
    assert single.count("《先开盒子，再摆木块》") == 1
    assert "中都能看到的写法" not in single
    assert "《先开盒子，再摆木块》《走廊里的一次停步》中都能看到的写法" in multiple
    assert "“我先看见门边的纸片。接着停下来想了一会。”" in multiple
    assert raw == before and snapshot == frozen


def test_expression_span_preserves_interior_blank_layout_but_requires_text_endpoints(snapshot):
    body = "第一句。 \n第二句。"
    snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = body
    assert build_report_sources(snapshot)["stable-a"]["b2"] == " \n"
    raw = output(expressions=[expression("rhythm", [span("b1", "b3")])])
    result = compile_editorial_profile(raw, snapshot)["profile"]["voiceFingerprint"][0]
    assert f"“{body}”" in result
    for first, last in (("b2", "b3"), ("b1", "b2"), ("b2", "b2")):
        with pytest.raises(ValueError, match="空白"):
            compile_editorial_profile(
                output(expressions=[expression(examples=[span(first, last)])]), snapshot,
            )
    for body in ("", " \n"):
        snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = body
        with pytest.raises(ValueError):
            compile_editorial_profile(
                output(expressions=[expression(examples=[span("b1", "b1")])]), snapshot,
            )


def test_expression_span_budgets_include_layout_and_never_clip(snapshot):
    note = snapshot["xhsCreatorProfile"]["notes"][0]
    note["desc"] = ("字" * 99 + "。") * 6
    raw = output(expressions=[expression("rhythm", [span("b1", "b6")])])
    assert f"“{note['desc']}”" in compile_editorial_profile(raw, snapshot)["profile"][
        "voiceFingerprint"
    ][0]
    note["desc"] = "字" + note["desc"]
    with pytest.raises(ValueError, match="600字"):
        compile_editorial_profile(raw, snapshot)
    note["desc"] = "字。" * 7
    raw["profile"]["expressionReadings"][0]["examples"] = [span("b1", "b7")]
    with pytest.raises(ValueError, match="6个"):
        compile_editorial_profile(raw, snapshot)
    note["desc"] = "字。" + " \n" * 5 + "末句。"
    with pytest.raises(ValueError, match="6个"):
        compile_editorial_profile(raw, snapshot)
    note["desc"] = "字" * 99 + "。" + " " * 401 + "\n" + "字" * 99 + "。"
    raw["profile"]["expressionReadings"][0]["examples"] = [span("b1", "b5")]
    with pytest.raises(ValueError, match="600字"):
        compile_editorial_profile(raw, snapshot)


def test_expression_span_order_uses_numeric_catalog_positions(snapshot):
    snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = "".join(
        f"第{index}段。" for index in range(1, 12)
    )
    raw = output(expressions=[expression(examples=[span("b9", "b10")])])
    voice = compile_editorial_profile(raw, snapshot)["profile"]["voiceFingerprint"][0]
    assert "“第9段。第10段。”" in voice


@pytest.mark.parametrize("example", [
    span("b2", "b1"), span("t", "b2"), span("b1", "t"), span("b1", "b99"),
    span(note_id="unknown"), span("b1", "b3", "n2"), span(last=[]),
    {"noteId": "n1", "fromExcerptId": "b1"},
    {**span(), "quote": "先打开盒子"}, {**span(), "excerptId": "b1"},
])
def test_expression_span_invalid_ranges_and_mixed_schemas_fail(snapshot, example):
    raw = output(expressions=[expression(examples=[example])])
    before = deepcopy(raw)
    with pytest.raises(ValueError):
        compile_editorial_profile(raw, snapshot)
    assert raw == before


def test_expression_spans_reject_overlaps_with_ranges_and_legacy_quotes_after_id_mapping(snapshot):
    for second in (
        span("b2", "b3", "stable-a"), span("b1", "b2", "stable-a"),
        {"noteId": "stable-a", "excerptId": "b2", "quote": "摆出木块"},
    ):
        for examples in ([span(), second], [second, span()]):
            with pytest.raises(ValueError, match="重叠引用"):
                compile_editorial_profile(
                    output(expressions=[expression(examples=examples)]), snapshot,
                )


@pytest.mark.parametrize("ending", ["", "。", "！", "？", ".", "!", "?"])
def test_expression_technique_gets_only_missing_terminal_punctuation(snapshot, ending):
    reading = expression()
    reading.update(technique="具体动作" + ending, application="先写动作。")
    raw = output(expressions=[reading])
    before = deepcopy(raw)
    voice = compile_editorial_profile(raw, snapshot)["profile"]["voiceFingerprint"][0]
    assert f"：具体动作{ending or '。'}原句：" in voice
    assert voice.endswith("借鉴方式：先写动作。")
    assert raw == before
    reading["application"] = "先写动作"
    voice = compile_editorial_profile(raw, snapshot)["profile"]["voiceFingerprint"][0]
    assert voice.endswith("借鉴方式：先写动作")


def test_known_structure_next_moves_misnest_is_relocated_before_source_resolution(snapshot):
    raw = output(structure())
    moves = [{"sourceNoteId": "n1", "sourceExcerptId": "b2",
              "basis": "原文交代摆放", "action": "说明动作的顺序"}]
    raw["profile"].pop("nextMoves")
    raw["profile"]["structureReading"]["nextMoves"] = moves
    # Root structure relocation and this one known nested key compose correctly.
    raw["structureReading"] = raw["profile"].pop("structureReading")
    before = deepcopy(raw)
    result = compile_editorial_profile(raw, snapshot)["profile"]
    assert result["viralStructure"]["kind"] == "narrative"
    assert result["contrast"]["takeaways"] == [
        "参考《先开盒子，再摆木块》：原文交代摆放。下一篇可尝试：说明动作的顺序。",
    ]
    assert raw == before
    raw["profile"]["nextMoves"] = deepcopy(moves)
    assert compile_editorial_profile(raw, snapshot)["profile"] == result
    for conflict in ([], [{**moves[0], "action": "不同建议"}]):
        raw["profile"]["nextMoves"] = conflict
        with pytest.raises(ValueError, match="内容冲突"):
            compile_editorial_profile(raw, snapshot)


def test_structure_misnest_repair_never_moves_unknown_fields_or_hides_invalid_next_moves(snapshot):
    for invalid in (None, "建议", [{"sourceNoteId": "unknown", "sourceExcerptId": "b1"}]):
        raw = output(structure())
        raw["profile"].pop("nextMoves")
        raw["profile"]["structureReading"]["nextMoves"] = invalid
        before = deepcopy(raw)
        with pytest.raises(ValueError):
            compile_editorial_profile(raw, snapshot)
        assert raw == before
    raw = output(structure())
    raw["profile"]["structureReading"]["unknown"] = "不可猜测"
    with pytest.raises(ValueError, match="structureReading"):
        compile_editorial_profile(raw, snapshot)
    for version in (None, "source-led/v1", "source-led/v2"):
        raw = {"profile": {"structureReading": {"nextMoves": []}}}
        if version:
            raw["profile"]["reportFormat"] = version
        result = resolve_editorial_refs(raw, snapshot)
        assert result["profile"]["structureReading"] == {"nextMoves": []}
        assert "nextMoves" not in result["profile"]


def test_root_new_fields_are_relocated_without_changing_input_and_conflicts_fail(snapshot):
    raw = output(structure(), [expression()])
    raw["structureReading"] = raw["profile"].pop("structureReading")
    raw["expressionReadings"] = raw["profile"].pop("expressionReadings")
    before = deepcopy(raw)
    assert compile_editorial_profile(raw, snapshot)["profile"]["viralStructure"]["kind"] \
        == "narrative"
    assert raw == before
    raw["profile"]["structureReading"] = None
    with pytest.raises(ValueError, match="内容冲突"):
        compile_editorial_profile(raw, snapshot)
    misplaced = output()
    misplaced["profile"]["accountPortrait"] = {"expressionReadings": [expression()]}
    with pytest.raises(ValueError, match="不能错嵌"):
        compile_editorial_profile(misplaced, snapshot)


@pytest.mark.parametrize("field,value", [
    ("viralStructure", {"name": "旧结构", "steps": ["旧步骤"]}),
    ("hookStyles", ["旧开头"]), ("voiceFingerprint", ["旧声音"]),
    ("viralStructure", None), ("viralStructure", {"steps": False}), ("hookStyles", ""),
])
def test_v3_rejects_nonempty_old_pattern_fields_and_invalid_empty_types(snapshot, field, value):
    raw = output(structure(), [expression()])
    raw["profile"][field] = value
    with pytest.raises(ValueError):
        compile_editorial_profile(raw, snapshot)


def test_v3_preserves_the_existing_portrait_title_and_next_move_protocols(snapshot):
    raw = output(structure())
    raw["profile"].update({
        "accountPortrait": {"summary": {"statement": "具体动作", "evidence": [
            {"noteId": "n1", "excerptId": "b1"},
        ]}},
        "titleReadings": [{"noteId": "n1", "parts": [
            {"text": "先开盒子", "role": "前项"}, {"text": "再摆木块", "role": "后项"},
        ]}],
        "nextMoves": [{"sourceNoteId": "n1", "sourceExcerptId": "b2",
                       "basis": "原文交代摆放", "action": "说明动作的顺序"}],
    })
    result = compile_editorial_profile(raw, snapshot)["profile"]
    assert result["accountPortrait"]["summary"]["evidence"][0]["noteId"] == "stable-a"
    assert result["titleFormulas"][0]["formula"].startswith("原标题拆解：")
    assert result["contrast"]["takeaways"][0].startswith("参考《先开盒子，再摆木块》：")


def test_old_shapes_and_versions_keep_their_exact_field_sets(snapshot):
    assert ViralStructure().model_dump() == {"name": "", "steps": []}
    assert ViralStructure(name="旧结构", steps=["第一步"]).model_dump() \
        == {"name": "旧结构", "steps": ["第一步"]}
    for version in (None, "source-led/v1", "source-led/v2"):
        raw = {"profile": {"viralStructure": {"name": "旧结构", "steps": ["旧步骤"]},
                            "hookStyles": ["旧开头"], "voiceFingerprint": ["旧声音"]}}
        if version:
            raw["profile"]["reportFormat"] = version
        result = compile_editorial_profile(raw, snapshot)
        assert ProfileStageResult.model_validate(result).model_dump()["profile"]["viralStructure"] \
            == {"name": "旧结构", "steps": ["旧步骤"]}
        if version != "source-led/v2":
            assert resolve_editorial_refs(raw, {}) == raw
