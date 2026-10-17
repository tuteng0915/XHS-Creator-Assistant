import asyncio
import json
from copy import deepcopy
from dataclasses import replace

import pytest

from app.errors import ValidationError
from app.models import ModelCallResponse, ModelOperation
from app.services.creator_fact_edit import (
    apply_fact_edits,
    draft_units,
    fact_edit_sources,
    parse_creator_statements,
    prepare_creator_statements,
    prepare_fact_edit,
)
from app.services.model_calls import ModelCallService


def draft(body="她做了模板。这不在她的职责内。小事也能看出主动性。"):
    return {"turn": {"summary": "从小事切入", "nextRecipient": "creator",
                     "candidateSuggestions": [{"kind": "copy_option", "title": "小改进",
                                               "body": body, "confidence": "inference",
                                               "evidenceRefs": []}]}}


def context():
    return {"assistantMode": "single_writer", "conversation": [
        {"role": "assistant", "content": "作者曾招过人"},
        {"role": "user", "content": "写一个开头"},
    ], "evidence": {"allowedSources": [
        {"id": "note", "text": "她做了模板，错误率下降。", "sourceRole": "source_document"},
        {"id": "analysis", "text": "突破职责边界", "sourceRole": "editorial_analysis"},
        {"id": "comment", "text": "我很焦虑", "sourceRole": "historical_reader_feedback"},
    ]}}


def edit(id="0:body:1", after=""):
    return {"id": id, "action": "replace", "claimType": "event", "text": after,
            "reason": "原文只写做模板，没有岗位职责范围"}


def test_editor_gets_originals_and_real_creator_not_writer_rationale_or_other_people():
    value = context()
    output = draft()
    frozen = deepcopy((value, output))
    _, user = prepare_fact_edit(value, output, creator_statements=[])
    packet = json.loads(user)
    assert [source["id"] for source in packet["sources"]] == ["note"]
    assert "写一个开头" not in user and "creatorDialogue" not in user
    assert "confidence" not in user and "summary" not in user
    assert "作者曾招过人" not in user and "突破职责边界" not in user
    assert (value, output) == frozen


def test_statement_preparation_cannot_see_draft_or_old_assistant_and_keeps_mixed_author_facts():
    value = context()
    value["conversation"][1]["content"] = (
        "开头回应应届生。请保留我上周与两位同学长聊的经历，但我没接触过其他人。"
    )
    _, packet = prepare_creator_statements(value)
    assert "作者曾招过人" not in packet and "职责" not in packet
    assert json.loads(packet)["creatorMessages"][0]["dialogueIndex"] == 1
    facts = parse_creator_statements(value, {"facts": [
        {"dialogueIndex": 1, "quote": "我上周与两位同学长聊"},
        {"dialogueIndex": 1, "quote": "我没接触过其他人"},
    ]})
    _, final = prepare_fact_edit(value, draft(), creator_statements=facts)
    assert "开头回应应届生" not in final
    assert "我上周与两位同学长聊" in final and "我没接触过其他人" in final


@pytest.mark.parametrize("fact", [
    {"dialogueIndex": 0, "quote": "作者曾招过人"},
    {"dialogueIndex": 1, "quote": "很多应届生跟我说"},
    {"dialogueIndex": True, "quote": "写一个开头"},
    {"dialogueIndex": 1, "quote": ""},
])
def test_statement_quote_cannot_be_invented_or_taken_from_assistant(fact):
    with pytest.raises(ValueError):
        parse_creator_statements(context(), {"facts": [fact]})


def test_raw_task_cannot_silently_enter_editor_as_evidence():
    with pytest.raises(ValueError, match="prepared"):
        prepare_fact_edit(context(), draft())
    assert prepare_creator_statements({"conversation": []}) is None


@pytest.mark.parametrize("ref", [None, {"sourceId": "note", "quote": "很多人跟我说"},
                                  {"sourceId": "analysis", "quote": "突破职责边界"},
                                  {"sourceId": "dialogue:1", "quote": "写一个开头"}])
def test_event_keep_cannot_use_task_editorial_or_invented_quote(ref):
    original = draft()
    with pytest.raises(ValueError):
        apply_fact_edits(original, {"checks": [{
            "id": "0:body:0", "action": "keep", "claimType": "event", "evidenceRef": ref,
        }]}, sources=fact_edit_sources(context(), []))
    assert original == draft()


def test_true_events_can_keep_original_or_author_statement_without_forcing_opinion_citations():
    value = context()
    value["conversation"][1]["content"] = "保留我上周与家人长聊的经历"
    facts = parse_creator_statements(value, {"facts": [
        {"dialogueIndex": 1, "quote": "我上周与家人长聊"},
    ]})
    original = draft("她做了模板。我上周与家人长聊。小事也能看出主动性。")
    result, edits = apply_fact_edits(original, {"checks": [
        {"id": "0:body:0", "action": "keep", "claimType": "event",
         "evidenceRef": {"sourceId": "note", "quote": "她做了模板"}},
        {"id": "0:body:1", "action": "keep", "claimType": "event",
         "evidenceRef": {"sourceId": "statement:0", "quote": "我上周与家人长聊"}},
        {"id": "0:body:2", "action": "keep", "claimType": "opinion"},
    ]}, sources=fact_edit_sources(value, facts))
    assert result == original and edits == []


def test_fact_edit_changes_only_exact_span_and_keeps_opinion_and_quote_metadata():
    output = draft()
    frozen = deepcopy(output)
    result, receipt = apply_fact_edits(output, {"checks": [edit()]})
    assert output == frozen
    assert result["turn"]["candidateSuggestions"][0]["body"] == "她做了模板。小事也能看出主动性。"
    assert len(receipt) == 1 and receipt[0]["before"] == "这不在她的职责内。"
    assert result["turn"]["summary"] == output["turn"]["summary"]
    assert apply_fact_edits(output, {"checks": []}) == (output, [])


@pytest.mark.parametrize("edits", [
    [edit(id="missing")], [edit(), edit()], [{**edit(), "id": True}],
    [{**edit(), "action": "unknown"}], [{**edit(), "id": []}],
    [edit(after="新" * 1_201)], [edit(id="0:title:0")],
])
def test_ambiguous_overlapping_or_invalid_edits_never_partially_modify_draft(edits):
    output = draft()
    frozen = deepcopy(output)
    with pytest.raises(ValueError):
        apply_fact_edits(output, {"checks": edits})
    assert output == frozen


def test_repeated_sentences_have_distinct_ids_and_multiple_spans_apply_backwards():
    repeated = draft("小事。小事。🤔保留。\n\n后文")
    result, _ = apply_fact_edits(repeated, {"checks": [edit(id="0:body:1")]})
    assert result["turn"]["candidateSuggestions"][0]["body"] == "小事。🤔保留。\n\n后文"
    output = draft("她做了模板。她独立开发三天。错误率降了80%。小事也能看出主动性。")
    result, _ = apply_fact_edits(output, {"checks": [
        edit(id="0:body:1"), edit(id="0:body:2", after="错误率下降。"),
    ]})
    assert result["turn"]["candidateSuggestions"][0]["body"] == (
        "她做了模板。错误率下降。小事也能看出主动性。"
    )


def test_lossless_outer_candidate_mirror_follows_the_local_edit_without_mutating_receipt():
    output = draft()
    output["candidateSuggestions"] = deepcopy(output["turn"]["candidateSuggestions"])
    frozen = deepcopy(output)
    result, _ = apply_fact_edits(output, {"checks": [edit()]})
    assert output == frozen
    assert result["candidateSuggestions"] == result["turn"]["candidateSuggestions"]


def test_sentence_units_cover_all_literal_characters_except_whitespace():
    output = draft('重复！重复！\n\n🤔“原话？”另一个问题?最后一行')
    units = [row for row in draft_units(output) if row["field"] == "body"]
    body = output["turn"]["candidateSuggestions"][0]["body"]
    assert "".join(row["text"] for row in units) == body.replace("\n", "")
    assert all(body[row["start"]:row["end"]] == row["text"] for row in units)


def test_legacy_discussion_and_questions_do_not_add_a_call():
    assert prepare_fact_edit({}, draft()) is None
    output = draft()
    output["turn"]["candidateSuggestions"][0]["kind"] = "outline"
    assert prepare_fact_edit(context(), output) is None


@pytest.mark.parametrize("review", [
    {"checks": [edit()]},
    {"checks": [{"id": u["id"], "action": "keep", "claimType": "opinion"}
                for u in draft_units(draft())]},
    {"checks": [edit(id="missing")]}, None,
])
def test_explicit_statement_preparation_and_edit_preserve_availability_and_receipts(
    settings, review,
):
    service = ModelCallService(replace(settings, model_provider="deepseek"))
    calls = []

    async def call_once(operation, packet, **kwargs):
        calls.append((operation, packet, kwargs))
        if len(calls) == 1:
            return ModelCallResponse(output=draft(), model_metadata={
                "model": "test", "usage": {"total_tokens": 10},
            })
        assert packet == {}  # Do not append original assistant messages to editor.
        if len(calls) == 2:
            assert "creatorMessages" in kwargs["review_prompt"][1]
            return ModelCallResponse(output={"facts": []}, model_metadata={
                "model": "test", "usage": {"total_tokens": 3},
            })
        assert "写一个开头" not in kwargs["review_prompt"][1]
        if review is None:
            raise ValidationError("editor unavailable")
        return ModelCallResponse(output=review, model_metadata={
            "model": "test", "usage": {"total_tokens": 5},
        })

    service._call_deepseek = call_once
    async def explicit_edit():
        original = await call_once(ModelOperation.CONTENT_COLLABORATION_TURN, context())
        return await service.edit_creator_facts(context(), original, call_once=call_once)

    result = asyncio.run(explicit_edit())
    assert len(calls) == 3
    assert result.model_metadata["requestCount"] == 3
    assert result.model_metadata["factEdit"]["originalOutput"] == draft()
    status = result.model_metadata["factEdit"]["status"]
    if review is None or review["checks"][0]["id"] == "missing":
        assert status == "unavailable"
        assert result.output == draft()
    else:
        assert status == ("partial" if len(review["checks"]) == 1 else "completed")
        assert result.model_metadata["usage"]["total_tokens"] == 18


@pytest.mark.parametrize("response", [None, {"facts": [{"dialogueIndex": 1, "quote": "编造"}]}])
def test_failed_statement_preparation_skips_editor_instead_of_erasing_real_experience(
    settings, response,
):
    service = ModelCallService(settings)
    calls = []

    async def call_once(operation, packet, **kwargs):
        calls.append(kwargs)
        if response is None:
            raise ValidationError("unavailable")
        return ModelCallResponse(output=response, model_metadata={"usage": {"total_tokens": 3}})

    original = draft("我上周与两位同学长聊。这次交流让我重新思考。")
    result = asyncio.run(service.edit_creator_facts(context(), ModelCallResponse(
        output=original, model_metadata={"requestCount": 0},
    ), call_once=call_once))
    assert result.output == original
    assert len(calls) == 1 and result.model_metadata["requestCount"] == 1
    assert result.model_metadata["factEdit"]["status"] == "unavailable"
    assert result.model_metadata["factEdit"]["failedStage"] == "creator_statements"


def test_no_author_dialogue_needs_only_editor_and_preserves_original_source(settings):
    value = context()
    value["conversation"] = []
    calls = []

    async def call_once(operation, packet, **kwargs):
        calls.append(kwargs)
        assert "她做了模板" in kwargs["review_prompt"][1]
        return ModelCallResponse(output={"checks": []}, model_metadata={})

    result = asyncio.run(ModelCallService(settings).edit_creator_facts(value, ModelCallResponse(
        output=draft(), model_metadata={"requestCount": 0},
    ), call_once=call_once))
    assert len(calls) == 1 and result.model_metadata["requestCount"] == 1
    assert result.model_metadata["factEdit"]["creatorStatements"]["status"] == "not_needed"
