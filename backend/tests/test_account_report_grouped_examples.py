"""Grouped source passages stay separate and retain their exact catalog locations."""

from copy import deepcopy

import pytest

from app.services.account_diagnosis_evidence import verified_portrait
from app.services.account_report_passages import reading_fragments


def snapshot():
    return {"xhsCreatorProfile": {"notes": [{
        "noteId": "stable-1", "title": "两处重复的短句",
        "desc": "共同短句。中间不摘。共同短句。尾句。",
    }, {
        "noteId": "stable-2", "title": "另一篇的相同文字", "desc": "共同短句。",
    }]}}


def example_for(source, keys=("b1", "b3"), note_index=0):
    note = source["xhsCreatorProfile"]["notes"][note_index]
    catalog = reading_fragments(note["title"], note["desc"])
    return {
        "noteId": note["noteId"], "title": note["title"],
        "fragments": [deepcopy(catalog[key]) for key in keys],
        "interpretation": "在不同位置重提同一句话，形成前后的呼应。",
    }


def portrait_for(examples):
    ids = list(dict.fromkeys(example["noteId"] for example in examples))
    return {
        "summary": {"statement": "说明观察过程", "evidence": [
            {"noteId": "stable-1", "scope": "note"},
        ]},
        "strengths": [{"statement": "具体文字之间有呼应", "evidence": [
            {"noteId": note_id, "scope": "note"} for note_id in ids
        ], "examples": examples}],
    }


def test_grouped_passages_accept_equal_text_at_distinct_original_positions():
    source = snapshot()
    example = example_for(source)
    before = deepcopy(example)
    assert example["fragments"][0]["quote"] == example["fragments"][1]["quote"]
    assert example["fragments"][0]["start"] != example["fragments"][1]["start"]
    portrait = portrait_for([example])
    saved = verified_portrait(portrait, source)
    assert saved["strengths"][0]["examples"] == [example]
    assert saved["strengths"][0]["evidence"] == [{"noteId": "stable-1", "scope": "note"}]
    assert example == before
    saved["strengths"][0]["examples"][0]["fragments"][0]["quote"] = "修改副本"
    assert example == before


def test_three_groups_of_six_fragments_do_not_hit_the_three_reference_limit():
    source = snapshot()
    source["xhsCreatorProfile"]["notes"][0]["desc"] = "".join(f"第{n}段。" for n in range(1, 19))
    groups = [example_for(source, tuple(f"b{n}" for n in range(start, start + 6)))
              for start in (1, 7, 13)]
    saved = verified_portrait(portrait_for(groups), source)
    assert saved["strengths"][0]["examples"] == groups
    assert len(saved["strengths"][0]["evidence"]) == 1
    assert sum(len(item["fragments"]) for item in saved["strengths"][0]["examples"]) == 18


def test_long_complete_title_and_ordered_body_fragments_survive_unchanged():
    source = snapshot()
    source["xhsCreatorProfile"]["notes"][0]["title"] = "完整标题" * 45
    example = example_for(source, ("t", "b1", "b3"))
    saved = verified_portrait(portrait_for([example]), source)
    assert len(example["fragments"][0]["quote"]) > 160
    assert saved["strengths"][0]["examples"] == [example]


@pytest.mark.parametrize("change", [
    {"excerptId": "unknown"}, {"excerptId": "b2"}, {"excerptId": []},
    {"source": "title"}, {"source": []}, {"quote": "伪造原句"},
    {"quote": "共同短句"}, {"start": 1}, {"end": 1000},
    {"start": False}, {"start": 0.0}, {"extra": "不能保留"},
])
def test_grouped_passages_reject_changed_or_unknown_fragment_fields(change):
    source = snapshot()
    example = example_for(source)
    example["fragments"][0].update(change)
    portrait = portrait_for([example])
    before = deepcopy(portrait)
    assert verified_portrait(portrait, source)["strengths"] == []
    assert portrait == before


@pytest.mark.parametrize("change", [
    {"title": "改写原标题"}, {"noteId": "outside-selection"}, {"noteId": []},
    {"interpretation": ""}, {"interpretation": "释" * 201},
    {"fragments": []}, {"fragments": None}, {"fragments": [None]},
    {"quote": "不能混入旧格式"}, {"extra": "不支持的字段"},
])
def test_grouped_passages_reject_malformed_group_without_crashing(change):
    source = snapshot()
    portrait = portrait_for([example_for(source)])
    portrait["strengths"][0]["examples"][0].update(change)
    assert verified_portrait(portrait, source)["strengths"] == []


@pytest.mark.parametrize("keys", [("b1", "b1"), ("b3", "b1"), ("b1", "t")])
def test_grouped_passages_reject_duplicate_or_reversed_fragments(keys):
    source = snapshot()
    assert verified_portrait(portrait_for([example_for(source, keys)]), source)["strengths"] == []


def test_grouped_passages_accept_reused_fragment_between_different_interpretations():
    source = snapshot()
    examples = [example_for(source, ("b1", "b3")), example_for(source, ("b3", "b4"))]
    examples[1]["interpretation"] = "同一个片段在另一组中也可以说明收束方式。"
    saved = verified_portrait(portrait_for(examples), source)
    assert saved["strengths"][0]["examples"] == examples


def test_grouped_passages_reject_more_than_six_fragments():
    source = snapshot()
    source["xhsCreatorProfile"]["notes"][0]["desc"] = "".join(f"第{n}段。" for n in range(1, 8))
    example = example_for(source, tuple(f"b{n}" for n in range(1, 8)))
    assert verified_portrait(portrait_for([example]), source)["strengths"] == []


def test_grouped_passages_scope_reuse_to_the_source_note_and_order_within_each_group():
    source = snapshot()
    examples = [example_for(source, ("b3",)), example_for(source, ("b1",)),
                example_for(source, ("b1",), note_index=1)]
    saved = verified_portrait(portrait_for(examples), source)
    assert saved["strengths"][0]["examples"] == examples


def test_grouped_passages_require_their_own_note_level_evidence():
    source = snapshot()
    for evidence in ([{"noteId": "stable-1", "quote": "共同短句。"}],
                     [{"noteId": "stable-2", "scope": "note"}]):
        portrait = portrait_for([example_for(source)])
        portrait["strengths"][0]["evidence"] = evidence
        assert verified_portrait(portrait, source)["strengths"] == []


def test_grouped_passages_reject_more_than_three_example_groups():
    source = snapshot()
    examples = [example_for(source, (key,)) for key in ("t", "b1", "b2", "b3")]
    assert verified_portrait(portrait_for(examples), source)["strengths"] == []


def test_legacy_single_quote_example_shape_is_preserved_alongside_grouped_example():
    source = snapshot()
    note = source["xhsCreatorProfile"]["notes"][0]
    start = note["desc"].index("尾句。")
    legacy = {"noteId": "stable-1", "title": note["title"], "source": "body",
              "quote": "尾句。", "interpretation": "在结尾收束。", "start": start, "end": start + 3}
    grouped = example_for(source)
    portrait = portrait_for([legacy, grouped])
    portrait["strengths"][0]["evidence"].append({"noteId": "stable-1", "quote": "尾句。"})
    saved = verified_portrait(portrait, source)
    assert saved["strengths"][0]["examples"] == [legacy, grouped]
    assert "fragments" not in saved["strengths"][0]["examples"][0]
