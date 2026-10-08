import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from test_model_calls import FakeAsyncClient, settings

from app.errors import ValidationError
from app.models import ModelCallResponse, ModelOperation
from app.services.editor_feedback import validate_editor_feedback
from app.services.model_calls import ModelCallService
from app.services.panel_quality import apply_review, prepare_review
from app.services.reader_selection import ReaderSelectionInput, validate_reader_selection

TASK = {"protocolVersion": "panel/v1"}
TOPIC = {
    "title": "读书随想",
    "body": "我读了一篇论文，想分享自己的看法。",
    "panelTask": TASK,
    "limitations": "INTERNAL_NOT_AUTHOR_TEXT",
}


def selection():
    context = {
        "panelTask": TASK,
        "workspaceId": "w",
        "accountPositioning": "ACCOUNT_NOT_EVIDENCE",
        "target": TOPIC,
        "desiredCount": 2,
        "candidates": [
            {"id": id, "updatedAt": "frozen", "name": name, "profile": profile}
            for id, name, profile in [
                ("a", "愿意理解新观点", "想知道论文提出什么新看法"),
                ("b", "旅行规划者", "准备出门旅行，先确认住宿预算"),
            ]
        ],
    }
    output = {
        "proposedReaders": [
            {
                "fanId": id,
                "fitReason": "PERSUASIVE_GENERATOR_REASON",
                "contribution": "阅读角度",
                "relation": "direct",
            }
            for id in ("a", "b")
        ],
        "unmatchedReason": "",
    }
    return context, output


def editing():
    context = {
        "topic": TOPIC,
        "personas": [{"id": "p", "profile": "PERSONA_NOT_FACT"}],
        "reactions": [
            {
                "messageId": "initial:p",
                "personaId": "p",
                "understanding": "READER_GUESSED_FIVE_EXPERIMENTS",
            }
        ],
        "debateResponses": [],
    }
    cards = [
        {
            "id": id,
            "kind": "clarify",
            "sourceType": "editor_optional",
            "sourceMessageIds": [],
            "readerConcernIds": [],
            "priority": "optional",
            "target": {"field": "body", "quote": TOPIC["body"]},
            "observation": "有价值的表达",
            "reason": "PERSUASIVE_GENERATOR_REASON",
            "suggestedText": text,
        }
        for id, text in [
            ("new_fact", "基于五次复现实验，我总结了结果。"),
            ("wording", "读完一篇论文，我想分享自己的看法。"),
        ]
    ]
    return context, {
        "synthesis": {
            "verdict": "读书感想",
            "editorFeedback": cards,
            "contentAdjustments": ["另一套未经核对的建议"],
        }
    }


def edit_decisions():
    return {
        "decisions": [
            {
                "id": "new_fact",
                "decision": "needs_material",
                "reason": "原文未提到复现实验",
                "questions": ["你实际做过哪些复现？如未做，可只保留阅读感想。"],
            },
            {
                "id": "wording",
                "decision": "retain",
                "reason": "只调整已有信息顺序",
                "questions": [],
            },
        ]
    }


def test_context_separates_manuscript_from_internal_metadata_and_model_guesses():
    context, output = editing()
    original = deepcopy((context, output))
    plan = prepare_review("simulation_synthesis", context, output)
    serialized = json.dumps(plan.context)
    for forbidden in [
        "INTERNAL_NOT_AUTHOR_TEXT",
        "PERSONA_NOT_FACT",
        "READER_GUESSED_FIVE_EXPERIMENTS",
        "PERSUASIVE_GENERATOR_REASON",
    ]:
        assert forbidden not in serialized
    assert (
        plan.context["edits"][0]["proposedText"]
        == output["synthesis"]["editorFeedback"][0]["suggestedText"]
    )
    assert (context, output) == original


def test_review_rejects_unrelated_reader_without_replacement_or_asset_changes():
    context, output = selection()
    original = deepcopy((context, output))
    plan = prepare_review("reader_selection", context, output)
    assert "PERSUASIVE_GENERATOR_REASON" not in json.dumps(plan.context)
    assert "ACCOUNT_NOT_EVIDENCE" not in json.dumps(plan.context)
    result, receipt = apply_review(
        plan,
        output,
        {
            "decisions": [
                {"id": "b", "decision": "exclude", "reason": "本文不涉及住宿规划"},
                {"id": "a", "decision": "include", "reason": "可以读到论文的新观点"},
            ]
        },
    )
    assert [r["fanId"] for r in result["proposedReaders"]] == ["a"]
    assert result["proposedReaders"][0]["fitReason"] == "可以读到论文的新观点"
    assert receipt["status"] == "checked"
    assert (context, output) == original
    assert (
        validate_reader_selection(result, ReaderSelectionInput.model_validate(context)).status
        == "completed"
    )


def test_all_unrelated_returns_explicit_no_match_not_replacement_personas():
    context, output = selection()
    result, _ = apply_review(
        prepare_review("reader_selection", context, output),
        output,
        {
            "decisions": [
                {"id": id, "decision": "exclude", "reason": "无具体联系"} for id in ("a", "b")
            ]
        },
    )
    assert result["proposedReaders"] == [] and result["unmatchedReason"]


def test_new_fact_becomes_blank_material_request_but_wording_survives():
    context, output = editing()
    original = deepcopy(output)
    result, _ = apply_review(
        prepare_review("simulation_synthesis", context, output), output, edit_decisions()
    )
    cards = result["synthesis"]["editorFeedback"]
    assert cards[0]["kind"] == "add_material" and cards[0]["suggestedText"] == ""
    assert cards[0]["materialRequests"] and "五次" not in json.dumps(cards[0], ensure_ascii=False)
    assert cards[1] == output["synthesis"]["editorFeedback"][1]
    assert result["synthesis"]["contentAdjustments"] == []
    assert (
        validate_editor_feedback(
            cards,
            topic=TOPIC,
            personas=context["personas"],
            reactions=context["reactions"],
            replies=[],
        )["editorFeedbackValidation"]["status"]
        == "validated"
    )
    assert output == original


def test_reviewer_questions_cannot_smuggle_invented_answers_into_material_input():
    context, output = editing()
    raw = edit_decisions()
    raw["decisions"][0]["questions"] = ["您提到保留率达到75%，五次实验的配置是什么？"]
    result, _ = apply_review(
        prepare_review("simulation_synthesis", context, output), output, raw
    )
    card = result["synthesis"]["editorFeedback"][0]
    assert card["suggestedText"] == ""
    assert card["target"]["quote"] == TOPIC["body"]
    assert card["reason"] == "原文未提到复现实验"
    assert "75%" not in str(card["materialRequests"])
    assert "五次" not in str(card["materialRequests"])
    assert "保留原文" in card["materialRequests"][0]


@pytest.mark.parametrize("change", ["missing", "duplicate", "extra", "bad_decision", "no_question"])
def test_incomplete_or_invalid_reviews_never_release_the_original(change):
    context, output = editing()
    raw = edit_decisions()
    if change == "missing":
        raw["decisions"].pop()
    elif change == "duplicate":
        raw["decisions"][1] = raw["decisions"][0]
    elif change == "extra":
        raw["decisions"][1]["id"] = "another_run"
    elif change == "bad_decision":
        raw["decisions"][0]["decision"] = "rewrite"
    else:
        raw["decisions"][0]["questions"] = []
    with pytest.raises((ValidationError, ValueError)):
        apply_review(prepare_review("simulation_synthesis", context, output), output, raw)


def test_legacy_and_no_cards_skip_extra_call():
    context, output = editing()
    context["topic"] = {"title": "旧稿", "body": "正文"}
    assert prepare_review("simulation_synthesis", context, output) is None
    context["topic"] = TOPIC
    output["synthesis"]["editorFeedback"] = []
    assert prepare_review("simulation_synthesis", context, output) is None


def test_service_performs_one_independent_review_and_aggregates_provenance(monkeypatch):
    context, output = editing()
    service = ModelCallService(settings(model_provider="qwen", qwen_api_key="fake"))
    calls = []

    async def once(op, ctx, *, review_prompt=None):
        calls.append(review_prompt)
        return ModelCallResponse(
            output=edit_decisions() if review_prompt else output,
            model_metadata={
                "model": "fake",
                "systemPromptHash": str(len(calls)),
                "usage": {"total_tokens": 10},
            },
        )

    monkeypatch.setattr(service, "_call_qwen", once)
    response = asyncio.run(service.call_operation(ModelOperation.SIMULATION_SYNTHESIS, context))
    assert len(calls) == 2 and calls[0] is None and calls[1] is not None
    assert response.model_metadata["requestCount"] == 2
    assert response.model_metadata["usage"]["total_tokens"] == 20
    assert response.model_metadata["panelReview"]["systemPromptHash"] == "2"
    assert response.output["synthesis"]["editorFeedback"][0]["kind"] == "add_material"


def test_review_failure_does_not_retry_or_return_unchecked_copy(monkeypatch):
    context, output = selection()
    service = ModelCallService(settings(model_provider="qwen", qwen_api_key="fake"))
    calls = []

    async def once(op, ctx, *, review_prompt=None):
        calls.append(review_prompt)
        if review_prompt:
            raise ValidationError("核对失败")
        return ModelCallResponse(output=output, model_metadata={})

    monkeypatch.setattr(service, "_call_qwen", once)
    with pytest.raises(ValidationError, match="核对失败"):
        asyncio.run(service.call_operation(ModelOperation.READER_SELECTION, context))
    assert len(calls) == 2


@pytest.mark.parametrize("budget,finish", [(2, "stop"), (1, "stop"), (2, "length")])
def test_real_transport_uses_json_contract_and_counts_both_http_requests(
    monkeypatch, budget, finish
):
    context, output = editing()
    requests = []

    class Transport(FakeAsyncClient):
        async def post(self, url, *, headers, json):
            requests.append(json)
            assert "json" in json["messages"][0]["content"].lower()
            value = output if len(requests) == 1 else edit_decisions()
            import json as serializer

            return httpx.Response(
                200,
                json={
                    "model": "mock-qwen",
                    "usage": {"total_tokens": 3},
                    "choices": [
                        {
                            "finish_reason": finish if len(requests) > 1 else "stop",
                            "message": {"content": serializer.dumps(value)},
                        }
                    ],
                },
            )

    def before_request():
        if len(requests) >= budget:
            raise RuntimeError("network budget exhausted")

    monkeypatch.setattr(httpx, "AsyncClient", Transport)
    service = ModelCallService(
        settings(model_provider="qwen", qwen_api_key="fake"), before_request=before_request
    )
    if budget == 1:
        with pytest.raises(RuntimeError, match="budget"):
            asyncio.run(service.call_operation(ModelOperation.SIMULATION_SYNTHESIS, context))
        assert len(requests) == 1
    elif finish == "length":
        with pytest.raises(ValidationError, match="核对输出不完整"):
            asyncio.run(service.call_operation(ModelOperation.SIMULATION_SYNTHESIS, context))
        assert len(requests) == 2
    else:
        result = asyncio.run(service.call_operation(ModelOperation.SIMULATION_SYNTHESIS, context))
        assert len(requests) == result.model_metadata["requestCount"] == 2
        assert result.model_metadata["usage"]["total_tokens"] == 6
        assert result.output["synthesis"]["editorFeedback"][0]["kind"] == "add_material"
