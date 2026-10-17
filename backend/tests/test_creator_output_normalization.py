"""Observed DeepSeek envelope variants, without private account fixtures."""

import asyncio
from copy import deepcopy

import pytest
from pydantic import ValidationError as PydanticValidationError
from test_content_collaboration_provider import FakeModelCallService

from app.errors import ValidationError
from app.services.content_collaboration import CollaborationMessage
from app.services.content_collaboration_provider import RealContentCollaborationProvider


def valid_turn():
    return {
        "summary": "把具体步骤写清楚。",
        "nextRecipient": "creator",
        "usedCandidateIds": [],
        "candidateSuggestions": [{
            "kind": "copy_option", "title": "从一次小改进开始",
            "body": "先找一个能验证的小问题。\n\n再做一次小改进。",
            "confidence": "inference", "evidenceRefs": [],
        }],
    }


def run(output, *, single_writer=True):
    model = FakeModelCallService(output, provider="deepseek")
    message = CollaborationMessage(sender="creator", to="writing", content="起草")
    context = {
        "target": {"title": "原标题", "body": "原正文"},
        "transcript": [message.model_dump()], "sessionContext": {},
    }
    if single_writer:
        context["assistantMode"] = "single_writer"
    result = asyncio.run(RealContentCollaborationProvider(model).run(
        role="writing", message=message, context=context,
    ))
    assert len(model.calls) == 1
    return result


@pytest.mark.parametrize("outer", [
    {"usedCandidateIds": []},  # QSheep initial
    {"evidenceRefs": []},  # Both revisions
    {"nextRecipient": "creator", "usedCandidateIds": []},  # 一粒鱼 initial
    {"summary": "把具体步骤写清楚。"},
    {"candidateSuggestions": valid_turn()["candidateSuggestions"]},
])
def test_redundant_outer_metadata_preserves_entire_turn_and_raw_receipt(outer):
    output = {"turn": valid_turn(), **outer}
    original = deepcopy(output)
    result = run(output)
    assert output == original
    assert result.to == "creator"
    assert result.model_metadata["candidateSuggestions"] == output["turn"]["candidateSuggestions"]
    assert result.model_metadata["outputNormalization"]["ignoredOuterFields"] == sorted(outer)
    assert len(result.model_metadata["outputNormalization"]["originalOutputHash"]) == 64


def test_defaulted_empty_list_duplicate_is_accepted_without_inventing_content():
    output = {"turn": valid_turn(), "usedCandidateIds": []}
    del output["turn"]["usedCandidateIds"]
    assert run(output).model_metadata["usedCandidateIds"] == []


@pytest.mark.parametrize("status", ["unavailable", "partial"])
def test_failed_optional_fact_edit_is_visible_without_losing_the_candidate(status):
    class EditorUnavailable(FakeModelCallService):
        async def call_operation(self, operation, context):
            response = await super().call_operation(operation, context)
            response.model_metadata["factEdit"] = {"status": status}
            return response

    model = EditorUnavailable({"turn": valid_turn()}, provider="deepseek")
    result = asyncio.run(RealContentCollaborationProvider(model).run(
        role="writing", message=CollaborationMessage(
            sender="creator", to="writing", content="起草",
        ),
        context={"assistantMode": "single_writer", "target": {}, "sessionContext": {}},
    ))
    assert "事实校订未完成，请核对后采用" in result.content
    assert result.model_metadata["candidateSuggestions"] == valid_turn()["candidateSuggestions"]


@pytest.mark.parametrize("outer", [
    {"nextRecipient": "review"},
    {"usedCandidateIds": ["unknown"]},
    {"summary": "另一份相冲突的回复"},
    {"candidateSuggestions": []},  # Would silently lose an existing draft.
    {"evidenceRefs": [{"sourceId": "outside", "quote": "未知"}]},
    {"evidenceRefs": None},
    {"topic": {"title": "不得自动更新作品"}},
    {"unknown": []},
])
def test_conflicts_and_unknown_content_are_not_silently_dropped(outer):
    with pytest.raises(ValidationError, match="返回格式"):
        run({"turn": valid_turn(), **outer})


def test_legacy_handoff_does_not_inherit_writer_envelope_tolerance():
    with pytest.raises(ValidationError, match="返回格式"):
        run({"turn": valid_turn(), "usedCandidateIds": []}, single_writer=False)


@pytest.mark.parametrize("mutation", [
    "empty_body", "missing_title", "wrong_kind", "string_ref", "supported_without_ref",
    "foreign_source", "fabricated_quote", "handoff",
])
def test_envelope_tolerance_keeps_inner_content_source_and_routing_checks(mutation):
    turn = valid_turn()
    candidate = turn["candidateSuggestions"][0]
    if mutation == "empty_body":
        candidate["body"] = ""
    elif mutation == "missing_title":
        del candidate["title"]
    elif mutation == "wrong_kind":
        candidate["kind"] = "review_note"
    elif mutation == "string_ref":
        candidate["evidenceRefs"] = ["target:topic"]
    elif mutation == "supported_without_ref":
        candidate["confidence"] = "supported"
    elif mutation == "foreign_source":
        candidate["evidenceRefs"] = [{"sourceId": "outside", "quote": "原文"}]
    elif mutation == "fabricated_quote":
        candidate["evidenceRefs"] = [{"sourceId": "target:topic", "quote": "未提供的经历"}]
    else:
        turn["nextRecipient"] = "review"
    with pytest.raises(ValidationError):
        run({"turn": turn, "evidenceRefs": []})


@pytest.mark.parametrize("output", [
    {}, {"turn": None}, {"turn": []}, {"turn": {}},
    {"summary": "内容不能凭空补齐", "nextRecipient": "creator", "evidenceRefs": []},
])
def test_missing_turn_is_not_filled_or_guessed(output):
    with pytest.raises(PydanticValidationError):
        RealContentCollaborationProvider._parse_output(output, single_writer=True)


@pytest.mark.parametrize("last_quote,valid", [("原正文", True), ("从未提供的经历", False)])
def test_extra_valid_references_do_not_discard_a_draft_but_every_quote_is_checked(
    last_quote, valid,
):
    output = {"turn": valid_turn()}
    candidate = output["turn"]["candidateSuggestions"][0]
    candidate["confidence"] = "supported"
    candidate["evidenceRefs"] = [
        {"sourceId": "target:topic", "quote": quote}
        for quote in ["原标题", "原正文", "标题", "正文", last_quote]
    ]
    if valid:
        assert len(run(output).model_metadata["candidateSuggestions"][0]["evidenceRefs"]) == 5
    else:
        with pytest.raises(ValidationError, match="逐字定位"):
            run(output)
