"""Synthetic, snapshot-local examples for the source-led report display adapter."""

from copy import deepcopy

import pytest

from app.services.account_report_editorial import compile_editorial_profile


@pytest.fixture
def snapshot():
    return {"xhsCreatorProfile": {"notes": [
        {"noteId": "note-a", "title": "清晨五分钟，把桌面收好",
         "desc": "先把常用物品放回固定位置。再清出一块空白。"},
        {"noteId": "note-b", "title": "一张路线图，周末少绕路",
         "desc": "出门前标出两个停靠点，再决定先后顺序。"},
    ]}}


@pytest.fixture
def report():
    return {"profile": {
        "reportFormat": "source-led/v1",
        "titleReadings": [
            {"noteId": "note-a", "move": "先限定投入，再说明动作", "parts": [
                {"text": "清晨五分钟", "role": "具体时段和投入"},
                {"text": "把桌面收好", "role": "明确动作"},
            ]},
            {"noteId": "note-b", "move": "先给工具，再说明用途", "parts": [
                {"text": "一张路线图", "role": "具体工具"},
                {"text": "周末少绕路", "role": "使用场景"},
            ]},
        ],
        "nextMoves": [
            {"sourceNoteId": "note-a", "sourceQuote": "把常用物品放回固定位置",
             "basis": "原文先写放回物品的具体动作", "action": "沿用具体动作开头，写一次收纳尝试"},
            {"sourceNoteId": "note-b", "sourceQuote": "一张路线图",
             "basis": "标题点出一件可使用的工具。", "action": "说明实际使用路线图的一次选择。"},
        ],
        "contrast": {"highPerformers": [{"noteId": "note-a"}], "other": {"items": ["保留"]}},
        "accountPortrait": {"summary": "合成测试内容", "keywords": ["具体动作"]},
    }, "untouched": {"metadata": ["保留"]}}


def test_distinct_title_readings_compile_separately_with_exact_original_titles(snapshot, report):
    result = compile_editorial_profile(report, snapshot)
    assert result["profile"]["titleFormulas"] == [
        {"formula": "先限定投入，再说明动作：清晨五分钟（具体时段和投入）→把桌面收好（明确动作）",
         "examples": ["清晨五分钟，把桌面收好"]},
        {"formula": "先给工具，再说明用途：一张路线图（具体工具）→周末少绕路（使用场景）",
         "examples": ["一张路线图，周末少绕路"]},
    ]
    assert result["profile"]["contrast"]["takeaways"] == [
        "参考《清晨五分钟，把桌面收好》：原文先写放回物品的具体动作。"
        "下一篇可尝试：沿用具体动作开头，写一次收纳尝试。",
        "参考《一张路线图，周末少绕路》：标题点出一件可使用的工具。"
        "下一篇可尝试：说明实际使用路线图的一次选择。",
    ]
    assert result["profile"]["contrast"]["highPerformers"] == [{"noteId": "note-a"}]
    assert result["profile"]["contrast"]["other"] == {"items": ["保留"]}
    assert result["profile"]["accountPortrait"] == report["profile"]["accountPortrait"]
    assert not {"reportFormat", "titleReadings", "nextMoves"} & result["profile"].keys()


def test_compilation_does_not_mutate_or_share_nested_inputs(snapshot, report):
    before_output, before_snapshot = deepcopy(report), deepcopy(snapshot)
    result = compile_editorial_profile(report, snapshot)
    assert report == before_output and snapshot == before_snapshot
    result["profile"]["contrast"]["other"]["items"].append("新项")
    result["profile"]["accountPortrait"]["keywords"].append("另一项")
    result["untouched"]["metadata"].clear()
    assert report == before_output and snapshot == before_snapshot


@pytest.mark.parametrize("profile", [
    {"titleFormulas": [{"formula": "旧公式", "examples": ["旧标题"]}],
     "contrast": {"takeaways": ["旧建议"], "metadata": {"value": [1]}}},
    {"accountPortrait": {"summary": "旧报告"}},
    None,
])
def test_unversioned_legacy_outputs_are_unchanged_deep_copies_without_source_snapshot(profile):
    output = {"profile": profile, "other": [1]}
    result = compile_editorial_profile(output, {})
    assert result == output and result is not output
    result["other"].append(2)
    assert output["other"] == [1]
    if isinstance(profile, dict):
        assert result["profile"] is not profile


def test_empty_new_lists_compile_to_empty_legacy_fields(snapshot):
    output = {"profile": {"reportFormat": "source-led/v1", "titleReadings": [], "nextMoves": [],
                          "titleFormulas": [], "contrast": {"takeaways": [], "other": "保留"}}}
    result = compile_editorial_profile(output, snapshot)
    assert result == {"profile": {"titleFormulas": [], "contrast": {
        "takeaways": [], "other": "保留",
    }}}
    assert compile_editorial_profile({"profile": {"reportFormat": "source-led/v1"}}, snapshot) \
        == {"profile": {"titleFormulas": [], "contrast": {"takeaways": []}}}


@pytest.mark.parametrize("version", ["source-led/v99", "", None, 0, True, [], {}])
def test_unknown_or_malformed_versions_are_rejected(snapshot, report, version):
    report["profile"]["reportFormat"] = version
    with pytest.raises(ValueError, match="reportFormat"):
        compile_editorial_profile(report, snapshot)


@pytest.mark.parametrize("field", ["titleReadings", "nextMoves"])
def test_new_fields_without_version_fail_instead_of_being_silently_ignored(snapshot, field):
    with pytest.raises(ValueError, match="缺少 reportFormat"):
        compile_editorial_profile({"profile": {field: []}}, snapshot)


@pytest.mark.parametrize("field,value", [
    ("reportFormat", "source-led/v1"), ("titleReadings", []), ("nextMoves", []),
])
def test_new_fields_misnested_in_portrait_fail_instead_of_looking_like_legacy(
    snapshot, field, value,
):
    with pytest.raises(ValueError, match="不能错嵌画像"):
        compile_editorial_profile({"profile": {"accountPortrait": {field: value}}}, snapshot)


@pytest.mark.parametrize("field", ["titleFormulas", "takeaways"])
def test_nonempty_legacy_fields_conflict_even_when_new_lists_are_empty(snapshot, field):
    profile = {"reportFormat": "source-led/v1", "titleReadings": [], "nextMoves": []}
    if field == "titleFormulas":
        profile[field] = [{"formula": "旧公式", "examples": ["旧标题"]}]
    else:
        profile["contrast"] = {field: ["旧建议"]}
    with pytest.raises(ValueError, match="冲突"):
        compile_editorial_profile({"profile": profile}, snapshot)


@pytest.mark.parametrize("field,value", [
    ("titleFormulas", [{"formula": "错嵌旧公式", "examples": ["旧标题"]}]),
    ("contrast", {"takeaways": ["错嵌旧建议"]}),
])
def test_misnested_legacy_fields_cannot_bypass_source_led_conflict_check(
    snapshot, report, field, value,
):
    report["profile"].pop(field, None)
    report["profile"]["accountPortrait"][field] = value
    before = deepcopy(report)
    with pytest.raises(ValueError, match="冲突"):
        compile_editorial_profile(report, snapshot)
    assert report == before


def test_new_compilation_normalizes_known_nesting_before_replacing_empty_fields(snapshot, report):
    profile = report["profile"]
    profile["accountPortrait"]["contrast"] = profile.pop("contrast")
    profile["accountPortrait"]["titleFormulas"] = []
    profile["accountPortrait"]["hookStyles"] = ["从具体动作开始"]
    result = compile_editorial_profile(report, snapshot)["profile"]
    assert result["hookStyles"] == ["从具体动作开始"]
    assert result["contrast"]["other"] == {"items": ["保留"]}
    assert len(result["titleFormulas"]) == len(result["contrast"]["takeaways"]) == 2
    assert not {"titleFormulas", "contrast", "hookStyles"} & result["accountPortrait"].keys()


def test_legacy_misnesting_is_still_returned_unchanged_without_new_contract():
    output = {"profile": {"accountPortrait": {"titleFormulas": [
        {"formula": "旧公式", "examples": ["旧标题"]},
    ], "contrast": {"takeaways": ["旧建议"]}}}}
    assert compile_editorial_profile(output, {}) == output


@pytest.mark.parametrize("field,value", [
    ("titleFormulas", None), ("titleFormulas", 0), ("titleFormulas", {}),
    ("contrast", []), ("contrast", None),
    ("contrast", {"takeaways": None}), ("contrast", {"takeaways": ""}),
])
def test_malformed_legacy_fields_are_not_hidden_by_falsey_checks(snapshot, report, field, value):
    report["profile"][field] = value
    with pytest.raises(ValueError):
        compile_editorial_profile(report, snapshot)


@pytest.mark.parametrize("field,value", [
    ("titleReadings", None), ("titleReadings", ""), ("titleReadings", {}),
    ("titleReadings", ()), ("titleReadings", [None]), ("titleReadings", [False]),
    ("nextMoves", None), ("nextMoves", ""), ("nextMoves", {}), ("nextMoves", ()),
    ("nextMoves", [0]),
])
def test_new_collections_and_rows_have_strict_types(snapshot, report, field, value):
    report["profile"][field] = value
    with pytest.raises(ValueError):
        compile_editorial_profile(report, snapshot)


@pytest.mark.parametrize("field", ["titleReadings", "nextMoves"])
def test_more_than_three_items_rejected_without_truncation(snapshot, report, field):
    report["profile"][field] = [deepcopy(report["profile"][field][0]) for _ in range(4)]
    with pytest.raises(ValueError, match="0 至 3"):
        compile_editorial_profile(report, snapshot)


@pytest.mark.parametrize("parts", [
    [{"text": "清晨五分钟", "role": "投入"}],
    [{"text": "清", "role": "片段"}] * 5,
    [{"text": "把桌面收好", "role": "动作"}, {"text": "清晨五分钟", "role": "投入"}],
    [{"text": "清晨五分钟", "role": "投入"}, {"text": "分钟，把桌面", "role": "重叠"}],
    [{"text": "清晨五分钟", "role": "投入"}, {"text": "周末少绕路", "role": "来自另一标题"}],
    [{"text": " 清晨五分钟", "role": "不是精确原文"}, {"text": "把桌面收好", "role": "动作"}],
    [{"text": "清晨五分钟", "role": "投入"}, {"text": "先把常用物品", "role": "来自正文"}],
    [{"text": "", "role": "空"}, {"text": "把桌面收好", "role": "动作"}],
    [{"text": "清晨五分钟", "role": " "}, {"text": "把桌面收好", "role": "动作"}],
    [{"text": False, "role": "坏类型"}, {"text": "把桌面收好", "role": "动作"}],
    [{"text": "清晨五分钟", "role": 1}, {"text": "把桌面收好", "role": "动作"}],
    [None, {}], None, {}, (),
])
def test_invalid_title_fragments_never_form_a_formula(snapshot, report, parts):
    report["profile"]["titleReadings"][0]["parts"] = parts
    before = deepcopy(report)
    with pytest.raises(ValueError):
        compile_editorial_profile(report, snapshot)
    assert report == before


def test_repeated_words_are_valid_when_they_occur_at_separate_positions(snapshot, report):
    snapshot["xhsCreatorProfile"]["notes"][0]["title"] = "试一试，再试一试"
    report["profile"]["titleReadings"] = [{
        "noteId": "note-a", "move": "重复动作", "parts": [
            {"text": "试一试", "role": "起点"}, {"text": "试一试", "role": "重复"},
        ],
    }]
    result = compile_editorial_profile(report, snapshot)
    assert result["profile"]["titleFormulas"] == [{
        "formula": "重复动作：试一试（起点）→试一试（重复）", "examples": ["试一试，再试一试"],
    }]


def test_v3_single_whole_title_is_a_reading_without_forcing_a_split(snapshot, report):
    snapshot["xhsCreatorProfile"]["notes"][0]["title"] = "盒子也会休息。"
    report["profile"]["reportFormat"] = "source-led/v3"
    report["profile"]["nextMoves"] = []
    report["profile"]["titleReadings"][0] = {
        "noteId": "n1", "parts": [{"text": "盒子也会休息。", "role": "把物品写成行动者"}],
    }
    before, frozen = deepcopy(report), deepcopy(snapshot)
    result = compile_editorial_profile(report, snapshot)["profile"]["titleFormulas"]
    assert result[0] == {"formula": "原标题解读：盒子也会休息。（把物品写成行动者）",
                         "examples": ["盒子也会休息。"]}
    assert result[1]["formula"].startswith("原标题拆解：")
    assert report == before and snapshot == frozen


@pytest.mark.parametrize("text", ["盒子也会休息", "盒子", " 盒子也会休息。", "", None])
def test_v3_single_title_part_must_equal_the_entire_original(snapshot, text):
    snapshot["xhsCreatorProfile"]["notes"][0]["title"] = "盒子也会休息。"
    raw = {"profile": {"reportFormat": "source-led/v3", "titleReadings": [
        {"noteId": "n1", "parts": [{"text": text, "role": "完整判断"}]},
    ]}}
    before = deepcopy(raw)
    with pytest.raises(ValueError):
        compile_editorial_profile(raw, snapshot)
    assert raw == before


@pytest.mark.parametrize("version", ["source-led/v1", "source-led/v2"])
def test_older_protocols_cannot_enable_single_title_part_with_the_new_display_label(
    snapshot, version,
):
    title = snapshot["xhsCreatorProfile"]["notes"][0]["title"]
    raw = {"profile": {"reportFormat": version, "titleReadings": [
        {"noteId": "note-a", "move": "原标题解读", "parts": [{"text": title, "role": "整句"}]},
    ]}}
    with pytest.raises(ValueError, match="2 至 4"):
        compile_editorial_profile(raw, snapshot)


@pytest.mark.parametrize("field,value", [
    ("noteId", "unknown"), ("noteId", ""), ("noteId", 1),
    ("move", " "), ("move", None), ("move", []),
])
def test_invalid_title_reading_identity_and_move_are_rejected(snapshot, report, field, value):
    report["profile"]["titleReadings"][0][field] = value
    with pytest.raises(ValueError):
        compile_editorial_profile(report, snapshot)


@pytest.mark.parametrize("field,value", [
    ("sourceNoteId", "unknown"), ("sourceNoteId", ""), ("sourceNoteId", 1),
    ("sourceQuote", "出门前标出两个停靠点"),
    ("sourceQuote", "清晨五分钟，把桌面收好\n先把常用物品"),
    ("sourceQuote", "不存在的拼接内容"), ("sourceQuote", " "), ("sourceQuote", True),
    ("basis", ""), ("basis", None), ("action", " "), ("action", {}),
])
def test_next_moves_require_a_local_exact_quote_and_text_fields(snapshot, report, field, value):
    report["profile"]["nextMoves"][0][field] = value
    with pytest.raises(ValueError):
        compile_editorial_profile(report, snapshot)


def test_duplicate_source_ids_are_ambiguous_even_if_titles_match(snapshot, report):
    snapshot["xhsCreatorProfile"]["notes"].append(
        deepcopy(snapshot["xhsCreatorProfile"]["notes"][0]),
    )
    with pytest.raises(ValueError, match="noteId 重复"):
        compile_editorial_profile(report, snapshot)


def test_same_title_on_distinct_note_ids_does_not_merge_sources(snapshot, report):
    notes = snapshot["xhsCreatorProfile"]["notes"]
    notes[1]["title"] = notes[0]["title"]
    report["profile"]["titleReadings"][1] = {
        **deepcopy(report["profile"]["titleReadings"][0]), "noteId": "note-b", "move": "第二条拆解",
    }
    report["profile"]["nextMoves"][1]["sourceQuote"] = "出门前标出两个停靠点"
    result = compile_editorial_profile(report, snapshot)
    assert len(result["profile"]["titleFormulas"]) == 2
    assert result["profile"]["titleFormulas"][1]["formula"].startswith("第二条拆解：")


@pytest.mark.parametrize("source", [
    None, {}, {"notes": None}, {"notes": {}}, {"notes": [None]},
    {"notes": [{"noteId": "note-a", "title": 7}]},
    {"notes": [{"noteId": "note-a", "desc": []}]},
    {"notes": [{"noteId": "", "title": "标题"}]},
])
def test_malformed_snapshot_data_is_rejected_for_new_reports(report, source):
    with pytest.raises(ValueError):
        compile_editorial_profile(report, {"xhsCreatorProfile": source})


def test_late_invalid_item_does_not_leave_a_partially_compiled_input(snapshot, report):
    report["profile"]["nextMoves"][1]["sourceQuote"] = "另一篇的固定位置"
    original_output, original_snapshot = deepcopy(report), deepcopy(snapshot)
    with pytest.raises(ValueError):
        compile_editorial_profile(report, snapshot)
    assert report == original_output and snapshot == original_snapshot


@pytest.mark.parametrize("output", [None, [], "", True])
def test_top_level_output_must_be_a_dictionary(snapshot, output):
    with pytest.raises(ValueError):
        compile_editorial_profile(output, snapshot)
