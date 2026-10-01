import re

import pytest
from pydantic import ValidationError

from app.services.audience_prototypes import (
    READING_NEED_PROTOTYPES,
    catalog_for_matching,
    matching_input_from_snapshot,
    validate_reading_need_candidates,
)


def test_reading_need_catalog_is_stable_and_composable():
    catalog = catalog_for_matching()
    ids = [item["id"] for item in catalog]

    assert len(catalog) >= 10
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"[a-z][a-z0-9_]*", value) for value in ids)
    assert catalog == [
        {
            "id": item.id,
            "name": item.name,
            "readingTask": item.reading_task,
            "matchQuestion": item.match_question,
        }
        for item in READING_NEED_PROTOTYPES
    ]
    assert all(item.name and item.reading_task and item.match_question
               for item in READING_NEED_PROTOTYPES)


def test_catalog_does_not_claim_observed_personas_or_population_traits():
    catalog = catalog_for_matching()
    assert all(set(item) == {"id", "name", "readingTask", "matchQuestion"}
               for item in catalog)
    text = " ".join(str(value) for item in catalog for value in item.values())
    for forbidden in ("MBTI", "阶层", "粉丝比例", "占比", "已确认粉丝", "评论者身份"):
        assert forbidden not in text


def _context():
    return {"notes": [{
        "noteId": "n1", "title": "申请步骤", "content": "先准备材料，再核对费用。",
        "comments": [{"commentId": "c1", "content": "费用包含签证费吗？"}],
    }]}


def _candidate(prototype_id="cost_scope"):
    return {
        "prototypeId": prototype_id,
        "matchReason": "评论询问费用包含范围。",
        "evidenceRefs": [{"noteId": "n1", "commentId": "c1",
                          "sourceType": "comment", "quote": "费用包含签证费吗"}],
        "counterEvidenceRefs": [{"noteId": "n1", "sourceType": "note",
                                 "quote": "先准备材料"}],
        "uncertainty": "只见到一条评论，不能推广到全部读者。",
    }


def test_matching_input_contains_only_scoped_citable_text_and_catalog():
    snapshot = {
        "creator": {"displayName": "作者", "profileText": "不属于本次阅读需求匹配"},
        "workspace": {"privateNotes": "不应传递"},
        "scope": {"mode": "selected", "noteIds": ["n1"]},
        "notes": [{
            "noteId": "n1", "title": "申请步骤", "desc": "先准备材料，再核对费用。",
            "images": ["private-cover-url"],
            "comments": [{"commentId": "c1", "content": "费用包含签证费吗？"}],
        }],
    }
    prepared = matching_input_from_snapshot(snapshot)

    assert set(prepared) == {"scope", "notes", "sampling", "catalog"}
    assert prepared["scope"] == snapshot["scope"]
    assert prepared["catalog"] == catalog_for_matching()
    assert prepared["notes"] == [{
        "noteId": "n1", "title": "申请步骤", "content": "先准备材料，再核对费用。",
        "comments": [{"commentId": "c1", "content": "费用包含签证费吗？",
                      "createTime": None}],
    }]
    assert prepared["sampling"]["sentNotes"] == 1
    assert prepared["sampling"]["sentComments"] == 1
    assert "作者" not in str(prepared)
    assert "private-cover-url" not in str(prepared)
    assert validate_reading_need_candidates([_candidate()], prepared)[0][
        "prototypeId"
    ] == "cost_scope"


def test_matching_input_rejects_quotes_outside_sent_text():
    prepared = matching_input_from_snapshot({
        "notes": [{
            "noteId": "n1", "title": "标题", "desc": "正文" + "字" * 4000 + "未发送尾句",
            "comments": [{"commentId": "c1", "content": "问" * 1000 + "未发送评论"}],
        }],
    })

    for source_type, quote, comment_id in [
        ("note", "未发送尾句", None),
        ("comment", "未发送评论", "c1"),
    ]:
        candidate = _candidate()
        candidate["evidenceRefs"] = [{
            "noteId": "n1", "commentId": comment_id,
            "sourceType": source_type, "quote": quote,
        }]
        candidate["counterEvidenceRefs"] = []
        with pytest.raises(ValueError, match="引用与本次输入不符"):
            validate_reading_need_candidates([candidate], prepared)


def test_candidate_matching_can_return_no_match_or_multiple_task_matches():
    assert validate_reading_need_candidates([], _context()) == []
    candidates = validate_reading_need_candidates(
        [_candidate(), {**_candidate("step_by_step"), "counterEvidenceRefs": []}],
        _context(),
    )
    assert [item["prototypeId"] for item in candidates] == ["cost_scope", "step_by_step"]
    assert all(item["status"] == "unconfirmed_proposal"
               and item["semanticReviewNeeded"] for item in candidates)
    assert candidates[0]["evidenceRefs"][0]["quote"] == "费用包含签证费吗"
    assert candidates[0]["citationBasis"] == "comment_only"
    assert "profile" not in candidates[0] and "estimatedPercent" not in candidates[0]


def test_candidate_citation_basis_uses_supporting_refs_not_counterevidence():
    note_ref = {"noteId": "n1", "sourceType": "note", "quote": "先准备材料"}
    comment_ref = {"noteId": "n1", "commentId": "c1",
                   "sourceType": "comment", "quote": "费用包含签证费吗"}
    note_only = {**_candidate(), "evidenceRefs": [note_ref],
                 "counterEvidenceRefs": [comment_ref]}
    comment_only = {**_candidate("step_by_step"), "evidenceRefs": [comment_ref],
                    "counterEvidenceRefs": [note_ref]}
    mixed = {**_candidate("claim_check"),
             "evidenceRefs": [note_ref, comment_ref], "counterEvidenceRefs": []}

    proposals = validate_reading_need_candidates(
        [note_only, comment_only, mixed], _context()
    )
    assert [item["citationBasis"] for item in proposals] == [
        "note_only", "comment_only", "mixed"
    ]
    assert all(item["status"] == "unconfirmed_proposal" and item["semanticReviewNeeded"]
               for item in proposals)


def test_model_cannot_self_report_citation_basis():
    with pytest.raises(ValidationError):
        validate_reading_need_candidates(
            [{**_candidate(), "citationBasis": "mixed"}], _context()
        )


def test_candidate_rejects_duplicate_or_contradictory_citations():
    candidate = _candidate()
    candidate["evidenceRefs"] *= 2
    with pytest.raises(ValueError, match="同一引文不可重复"):
        validate_reading_need_candidates([candidate], _context())

    candidate = _candidate()
    candidate["counterEvidenceRefs"] *= 2
    with pytest.raises(ValueError, match="同一引文不可重复"):
        validate_reading_need_candidates([candidate], _context())

    candidate = _candidate()
    candidate["counterEvidenceRefs"] = list(candidate["evidenceRefs"])
    with pytest.raises(ValueError, match="同时作为支持和反证"):
        validate_reading_need_candidates([candidate], _context())


def test_candidate_accepts_distinct_passages_from_the_same_note():
    candidate = _candidate()
    candidate["evidenceRefs"] = [
        {"noteId": "n1", "sourceType": "note", "quote": "先准备材料"},
        {"noteId": "n1", "sourceType": "note", "quote": "再核对费用"},
    ]
    candidate["counterEvidenceRefs"] = []
    assert len(validate_reading_need_candidates([candidate], _context())[0]["evidenceRefs"]) == 2


@pytest.mark.parametrize("items, error", [
    ([_candidate("made_up")], "未知阅读需求原型"),
    ([_candidate(), _candidate()], "阅读需求原型不可重复"),
    ([_candidate("scope_check"), _candidate("cost_scope"),
      _candidate("claim_check"), _candidate("step_by_step")], "最多三项"),
    ([{**_candidate(), "evidenceRefs": [{"noteId": "n1", "sourceType": "note",
                                        "quote": "原文里没有"}]}], "引用与本次输入不符"),
    ([{**_candidate(), "counterEvidenceRefs": [{"noteId": "n1", "sourceType": "note",
                                               "quote": "原文里没有"}]}], "引用与本次输入不符"),
])
def test_candidate_matching_rejects_unbounded_or_unverifiable_proposals(items, error):
    with pytest.raises(ValueError, match=error):
        validate_reading_need_candidates(items, _context())


def test_candidate_matching_rejects_empty_evidence_and_persona_fields():
    with pytest.raises(ValidationError):
        validate_reading_need_candidates([{**_candidate(), "evidenceRefs": []}], _context())
    with pytest.raises(ValidationError):
        validate_reading_need_candidates([{**_candidate(), "MBTI": "INFP"}], _context())
