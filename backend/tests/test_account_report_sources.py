"""Synthetic fixtures for reversible excerpt catalogs and exact v2 reference lookup."""

import json
from copy import deepcopy

import pytest

from app.services.account_report_editorial import compile_editorial_profile
from app.services.account_report_sources import (
    build_report_sources,
    prepare_source_led_context,
    resolve_editorial_refs,
)
from app.workflows.account_diagnosis import ProfileStageResult


@pytest.fixture
def snapshot():
    return {"xhsCreatorProfile": {"notes": [
        {"noteId": "a", "title": "先说明场景，再给动作",
         "desc": "先摆出两件物品。再说明摆放顺序。"},
        {"noteId": "b", "title": "另一个标题", "desc": "另一个场景。"},
    ]}}


def report_v2():
    claim = {"statement": "测试判断", "evidence": [{"noteId": "a", "excerptId": "b1"}],
             "counterexamples": [{"noteId": "b", "excerptId": "t"}]}
    portrait = {key: deepcopy(claim) for key in ("summary", "encouragement", "recentChange")}
    portrait.update({key: [deepcopy(claim)] for key in (
        "keywords", "strengths", "recurringThemes", "readerValue", "expressionPatterns",
    )})
    return {"profile": {"reportFormat": "source-led/v2", "accountPortrait": portrait,
                        "titleReadings": [{"noteId": "a", "move": "场景接动作", "parts": [
                            {"text": "先说明场景", "role": "场景"},
                            {"text": "再给动作", "role": "动作"},
                        ]}], "nextMoves": [{
                            "sourceNoteId": "a", "sourceExcerptId": "b2",
                            "basis": "原文说明了摆放顺序", "action": "写清楚一次动作的顺序",
                        }], "contrast": {"other": ["保留"]}}}


def test_catalog_is_lossless_stable_bounded_and_preserves_empty_sources(snapshot):
    body = " \r\n第一句。第二句!?\n\n" + "🙂" * 325 + "未完句  \r\n"
    snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = body
    snapshot["xhsCreatorProfile"]["notes"].append({"noteId": "empty", "title": "", "desc": ""})
    before = deepcopy(snapshot)
    catalog = build_report_sources(snapshot)
    assert catalog == build_report_sources(snapshot) and snapshot == before
    assert catalog["a"]["t"] == "先说明场景，再给动作"
    fragments = [text for key, text in catalog["a"].items() if key != "t"]
    assert "".join(fragments) == body
    assert all(0 < len(text) <= 160 and text in body for text in fragments)
    assert list(catalog["a"])[1:] == [f"b{index}" for index in range(1, len(fragments) + 1)]
    assert catalog["empty"] == {}


def test_english_boundaries_preserve_urls_decimals_and_initialisms(snapshot):
    body = "查看 https://example.test/a?x=3.5 来自 L.S.E. 下一句! 保留尾句"
    snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = body
    fragments = [text for key, text in build_report_sources(snapshot)["a"].items() if key != "t"]
    assert "".join(fragments) == body
    assert all(any(value in part for part in fragments)
               for value in ("https://example.test/a?x=3.5", "3.5", "L.S.E."))
    assert len(fragments) == 3


def test_prepare_uses_local_ids_and_only_content_fields_without_mutating_sources(snapshot):
    stable_ids = ["0123456789abcdef01234567", "fedcba9876543210fedcba98"]
    for note, note_id in zip(snapshot["xhsCreatorProfile"]["notes"], stable_ids, strict=True):
        note["noteId"] = note_id
    packet = {"schemaVersion": "account-reading-input/v2",
              "readingScope": {"selectedNoteCount": 2, "metricScope": "不要进入模型的指标说明"},
              "metricSummaries": [{"metric": "liked", "validCount": 2}],
              "statistics": {"private": 123456}, "chronology": {"earlier": {"noteIds": stable_ids}},
              "notes": [
                  {"noteId": note["noteId"], "title": note["title"], "body": note["desc"],
                   "metrics": {"liked": 0}, "metricRanksInSelection": {"liked": 1},
                   "type": "normal", "availableBodyCharacters": len(note["desc"])}
                  for note in snapshot["xhsCreatorProfile"]["notes"]
              ]}
    context = {"positioning": "本次所选材料",
               "historicalPosts": json.dumps(packet, ensure_ascii=False),
               "other": {"items": ["保留"]}}
    original = deepcopy(context)
    prepared = prepare_source_led_context(context)
    converted = json.loads(prepared["historicalPosts"])
    catalog = build_report_sources(snapshot)
    assert context == original and prepared["other"] == context["other"]
    assert converted["schemaVersion"] == "account-reading-input/v3"
    assert set(converted) == {"schemaVersion", "readingScope", "notes"}
    assert [note["noteId"] for note in converted["notes"]] == ["n1", "n2"]
    for before, after in zip(packet["notes"], converted["notes"], strict=True):
        assert set(after) == {"noteId", "title", "type", "bodyExcerpts"}
        assert after["title"] == before["title"] and after["type"] == before["type"]
        assert after["bodyExcerpts"] == [
            {"excerptId": key, "text": value} for key, value in catalog[before["noteId"]].items()
            if key != "t"
        ]
        assert "".join(item["text"] for item in after["bodyExcerpts"]) == before["body"]
    assert converted["readingScope"]["selectedNoteCount"] == 2
    assert "未读取图片内文字" in converted["readingScope"]["textScope"]
    assert set(converted["readingScope"]) == {"selectedNoteCount", "textScope"}
    for omitted in (*stable_ids, "metrics", "metricRanks", "metricScope", "metricSummaries",
                    "statistics", "chronology", "availableBodyCharacters"):
        assert omitted not in prepared["historicalPosts"]
    prepared["other"]["items"].append("独立副本")
    assert context == original
    assert prepare_source_led_context(prepared) == prepared


def test_legacy_context_and_v1_report_are_deep_copies_without_requiring_sources():
    for text in ("旧的正文", json.dumps({"schemaVersion": "unrelated", "notes": []})):
        context = {"historicalPosts": text, "other": {"nested": []}}
        result = prepare_source_led_context(context)
        assert result == context and result["other"] is not context["other"]
    output = {"profile": {"reportFormat": "source-led/v1", "nextMoves": []}}
    result = resolve_editorial_refs(output, {})
    assert result == output and result["profile"] is not output["profile"]


def test_all_portrait_claims_and_next_moves_resolve_local_ids_without_mutation(snapshot):
    output = report_v2()
    before, original_snapshot = deepcopy(output), deepcopy(snapshot)
    result = resolve_editorial_refs(output, snapshot)
    assert output == before and snapshot == original_snapshot
    assert result["profile"]["reportFormat"] == "source-led/v1"
    for value in result["profile"]["accountPortrait"].values():
        claim = value[0] if isinstance(value, list) else value
        assert claim["evidence"] == [{"noteId": "a", "quote": "先摆出两件物品。"}]
        assert claim["counterexamples"] == [{"noteId": "b", "quote": "另一个标题"}]
    assert result["profile"]["nextMoves"][0] == {
        "sourceNoteId": "a", "sourceQuote": "再说明摆放顺序。",
        "basis": "原文说明了摆放顺序", "action": "写清楚一次动作的顺序",
    }
    result["profile"]["contrast"]["other"].append("副本内容")
    assert output == before


def test_local_ids_map_all_reference_fields_back_to_real_ids_and_match_old_v2_responses(snapshot):
    stable_ids = ["0123456789abcdef01234567", "fedcba9876543210fedcba98"]
    for note, note_id in zip(snapshot["xhsCreatorProfile"]["notes"], stable_ids, strict=True):
        note["noteId"] = note_id

    def with_ids(value, replacements):
        if isinstance(value, list):
            return [with_ids(item, replacements) for item in value]
        if isinstance(value, dict):
            return {key: replacements[item] if key in {"noteId", "sourceNoteId"}
                    else with_ids(item, replacements) for key, item in value.items()}
        return value

    local = with_ids(report_v2(), {"a": "n1", "b": "n2"})
    legacy = with_ids(report_v2(), dict(zip(("a", "b"), stable_ids, strict=True)))
    before, original_snapshot = deepcopy(local), deepcopy(snapshot)
    resolved = resolve_editorial_refs(local, snapshot)
    assert resolved == resolve_editorial_refs(legacy, snapshot)
    assert resolved["profile"]["titleReadings"][0]["noteId"] == stable_ids[0]
    assert resolved["profile"]["nextMoves"][0]["sourceNoteId"] == stable_ids[0]
    assert resolved["profile"]["accountPortrait"]["summary"]["counterexamples"][0] \
        == {"noteId": stable_ids[1], "quote": "另一个标题"}
    assert compile_editorial_profile(local, snapshot) == compile_editorial_profile(legacy, snapshot)
    assert local == before and snapshot == original_snapshot


def test_unknown_local_ids_and_typos_fail_in_each_reference_location(snapshot):
    for location, field, invalid in (
        ("evidence", "noteId", "n3"), ("titleReadings", "noteId", "n01"),
        ("nextMoves", "sourceNoteId", "aa"),
    ):
        output = report_v2()
        target = (output["profile"]["accountPortrait"]["summary"]["evidence"][0]
                  if location == "evidence" else output["profile"][location][0])
        target[field] = invalid
        with pytest.raises(ValueError, match="noteId 未知"):
            resolve_editorial_refs(output, snapshot)


def test_local_id_that_collides_with_another_stable_id_is_rejected_without_guessing(snapshot):
    snapshot["xhsCreatorProfile"]["notes"][0]["noteId"] = "n2"
    output = {"profile": {"reportFormat": "source-led/v2", "accountPortrait": {
        "summary": {"evidence": [{"noteId": "n2", "excerptId": "t"}]},
    }}}
    with pytest.raises(ValueError, match="歧义"):
        resolve_editorial_refs(output, snapshot)
    packet = {"schemaVersion": "account-reading-input/v2", "notes": [
        {"noteId": note["noteId"], "title": note["title"], "body": note["desc"]}
        for note in snapshot["xhsCreatorProfile"]["notes"]
    ]}
    with pytest.raises(ValueError, match="含义冲突"):
        prepare_source_led_context({"historicalPosts": json.dumps(packet)})
    # A genuine stable ID outside the collision remains valid for an older response.
    output["profile"]["accountPortrait"]["summary"]["evidence"][0]["noteId"] = "b"
    assert resolve_editorial_refs(output, snapshot)["profile"]["accountPortrait"]["summary"][
        "evidence"
    ] == [{"noteId": "b", "quote": "另一个标题"}]


def test_compiler_accepts_v2_end_to_end_and_normalizes_known_claim_locations(snapshot):
    output = report_v2()
    output["profile"]["strengths"] = output["profile"]["accountPortrait"].pop("strengths")
    result = compile_editorial_profile(output, snapshot)["profile"]
    assert result["titleFormulas"] == [{
        "formula": "原标题拆解：先说明场景（场景）→再给动作（动作）",
        "examples": ["先说明场景，再给动作"],
    }]
    assert result["contrast"] == {"other": ["保留"], "takeaways": [
        "参考《先说明场景，再给动作》：原文说明了摆放顺序。下一篇可尝试：写清楚一次动作的顺序。",
    ]}
    assert result["accountPortrait"]["strengths"][0]["evidence"] \
        == [{"noteId": "a", "quote": "先摆出两件物品。"}]
    assert not {"reportFormat", "titleReadings", "nextMoves"} & result.keys()


def test_v2_ignores_umbrella_move_and_accepts_its_omission_while_v1_preserves_it(snapshot):
    snapshot["xhsCreatorProfile"]["notes"][0]["title"] = "《远行》第三章，结尾留下什么？"
    reading = {"noteId": "n1", "move": "悬念前置", "parts": [
        {"text": "《远行》第三章", "role": "作品对象"},
        {"text": "结尾留下什么？", "role": "提出悬念"},
    ]}
    output = {"profile": {"reportFormat": "source-led/v2", "titleReadings": [reading]}}
    before = deepcopy(output)
    formula = compile_editorial_profile(output, snapshot)["profile"]["titleFormulas"][0]["formula"]
    assert formula == "原标题拆解：《远行》第三章（作品对象）→结尾留下什么？（提出悬念）"
    assert "悬念前置" not in formula and output == before
    del output["profile"]["titleReadings"][0]["move"]
    assert compile_editorial_profile(output, snapshot)["profile"]["titleFormulas"][0]["formula"] \
        == formula
    legacy = {"profile": {"reportFormat": "source-led/v1", "titleReadings": [
        {**reading, "noteId": "a", "move": "旧记录中的原说明"},
    ]}}
    assert compile_editorial_profile(legacy, snapshot)["profile"]["titleFormulas"][0]["formula"] \
        .startswith("旧记录中的原说明：")


def test_root_structure_and_two_next_moves_are_relocated_before_id_and_quote_resolution(snapshot):
    # Synthetic reconstruction of a response that split profile fields across the root.
    output = report_v2()
    output["viralStructure"] = {
        "name": "《先说明场景，再给动作》", "steps": ["摆出物品", "说明顺序"],
    }
    output["nextMoves"] = [
        {"sourceNoteId": "n1", "sourceExcerptId": "b2", "basis": "原文写清顺序",
         "action": "把一次动作按真实顺序整理"},
        {"sourceNoteId": "n2", "sourceExcerptId": "b1", "basis": "原文呈现一个场景",
         "action": "说明自己在场景中注意到什么"},
    ]
    del output["profile"]["nextMoves"]
    before = deepcopy(output)
    result = compile_editorial_profile(output, snapshot)
    assert result["profile"]["viralStructure"] == before["viralStructure"]
    assert result["profile"]["contrast"]["takeaways"] == [
        "参考《先说明场景，再给动作》：原文写清顺序。下一篇可尝试：把一次动作按真实顺序整理。",
        "参考《另一个标题》：原文呈现一个场景。下一篇可尝试：说明自己在场景中注意到什么。",
    ]
    assert "viralStructure" not in result and "nextMoves" not in result
    validated = ProfileStageResult.model_validate(result).model_dump(mode="json")
    assert validated["profile"]["viralStructure"] == before["viralStructure"]
    assert validated["profile"]["contrast"]["takeaways"] \
        == result["profile"]["contrast"]["takeaways"]
    assert output == before
    # Relocation must not allow an invalid root reference to escape validation.
    output["nextMoves"][1]["sourceExcerptId"] = "b999"
    with pytest.raises(ValueError, match="冻结目录"):
        compile_editorial_profile(output, snapshot)


def test_root_portrait_and_title_readings_are_restored_and_exact_duplicates_merge(snapshot):
    output = report_v2()
    output["accountPortrait"] = output["profile"].pop("accountPortrait")
    output["accountPortrait"]["summary"]["evidence"][0]["noteId"] = "n1"
    output["titleReadings"] = output["profile"].pop("titleReadings")
    output["titleReadings"][0]["noteId"] = "n1"
    output["profile"]["titleReadings"] = deepcopy(output["titleReadings"])
    before = deepcopy(output)
    result = compile_editorial_profile(output, snapshot)
    assert "accountPortrait" not in result and "titleReadings" not in result
    assert result["profile"]["accountPortrait"]["summary"]["evidence"] \
        == [{"noteId": "a", "quote": "先摆出两件物品。"}]
    assert len(result["profile"]["titleFormulas"]) == 1
    assert output == before


@pytest.mark.parametrize("field", [
    "viralStructure", "nextMoves", "titleReadings", "accountPortrait",
])
def test_conflicting_root_and_profile_fields_fail_without_overwriting_either(snapshot, field):
    output = report_v2()
    output[field] = {"conflicting": "different"}
    output["profile"].setdefault(field, {"name": "existing", "steps": ["先"]})
    before = deepcopy(output)
    with pytest.raises(ValueError, match="内容冲突"):
        compile_editorial_profile(output, snapshot)
    assert output == before


def test_root_known_fields_on_legacy_output_are_not_relocated():
    output = {"profile": {"summary": "旧内容"}, "viralStructure": {"name": "旧根层", "steps": []},
              "nextMoves": [{"sourceNoteId": "历史值"}], "unknownRoot": {"keep": True}}
    result = compile_editorial_profile(output, {})
    assert result == output and result is not output
    result["viralStructure"]["steps"].append("仅副本")
    assert output["viralStructure"]["steps"] == []


@pytest.mark.parametrize("ref", [
    {"noteId": "missing", "excerptId": "b1"},
    {"noteId": "a", "excerptId": "b999"},
    {"noteId": "b", "excerptId": "b2"},  # b2 exists only in another note.
    {"noteId": "a", "excerptId": "b1", "quote": "不得覆盖的引文"},
])
def test_unknown_cross_note_or_dual_written_refs_fail_without_partial_changes(snapshot, ref):
    output = report_v2()
    output["profile"]["accountPortrait"]["summary"]["counterexamples"] = [ref]
    before = deepcopy(output)
    with pytest.raises(ValueError):
        compile_editorial_profile(output, snapshot)
    assert output == before


def test_next_move_bad_ref_old_quote_and_duplicate_source_ids_fail(snapshot):
    for change in ({"sourceExcerptId": "missing"}, {"sourceQuote": "不要静默覆盖"}):
        output = report_v2()
        output["profile"]["nextMoves"][0].update(change)
        with pytest.raises(ValueError):
            resolve_editorial_refs(output, snapshot)
    snapshot["xhsCreatorProfile"]["notes"].append(
        deepcopy(snapshot["xhsCreatorProfile"]["notes"][0]),
    )
    with pytest.raises(ValueError, match="唯一"):
        build_report_sources(snapshot)


def test_empty_body_conversion_and_whitespace_only_reference_rejection(snapshot):
    context = {"historicalPosts": json.dumps({"schemaVersion": "account-reading-input/v2",
                                               "notes": [{"noteId": "empty", "body": ""}]})}
    prepared = json.loads(prepare_source_led_context(context)["historicalPosts"])
    assert prepared["notes"][0]["bodyExcerpts"] == []
    snapshot["xhsCreatorProfile"]["notes"][0]["desc"] = " \n"
    with pytest.raises(ValueError, match="空白"):
        resolve_editorial_refs(report_v2(), snapshot)
