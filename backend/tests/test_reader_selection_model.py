import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from test_model_calls import FakeAsyncClient
from test_reader_selection import fan, proposal, snapshot
from test_reader_selection_persistence import payload
from test_reader_selection_persistence import store as store

from app.errors import ValidationError
from app.main import create_app
from app.models import ModelCallResponse, ModelOperation
from app.services.model_calls import ModelCallService
from app.services.reader_selection import prepare_reader_selection, validate_reader_selection
from app.services.reader_selection_model import RealReaderSelectionProvider
from app.services.reader_selection_prompt import (
    MAX_SELECTION_PROMPT_BYTES,
    ReaderSelectionInputTooLarge,
    selection_prompt,
)
from app.services.reader_selection_worker import ReaderSelectionWorker


class Calls:
    def __init__(self, output=None):
        self.received = []
        self.output = output

    async def call_operation(self, operation, context):
        self.received.append((operation, context))
        return ModelCallResponse(output=self.output or {"proposedReaders": [proposal()]},
                                 model_metadata={"model": "injected-test"})


def test_eight_complete_cards_and_six_requested_reach_model_without_strategy(settings):
    inputs = prepare_reader_selection("w", snapshot(), [fan(str(i)) for i in range(8)],
                                      desired_count=6)
    calls = Calls({"proposedReaders": [proposal(str(i)) for i in range(6)]})
    response = asyncio.run(RealReaderSelectionProvider(calls).select(inputs))
    assert len(calls.received) == 1
    operation, context = calls.received[0]
    assert operation == ModelOperation.READER_SELECTION
    system, user = ModelCallService(settings)._build_prompt(operation, context)
    sent = json.loads(user)
    assert len(sent["candidates"]) == 8 and sent["desiredCount"] == 6
    assert sent["candidates"][7]["profile"] == inputs.candidates[7].profile
    assert "updatedAt" not in sent["candidates"][0]
    assert "workspaceId" not in sent and "selectorVersion" not in sent
    assert "内部策略" not in user and "original" not in user
    assert "不只挑会喜欢的人" in system and "不创造、改写人物" in system
    assert "可从行动门槛与投入角度试读" in system and "不预写人物会说什么" in system
    assert len(validate_reader_selection(response.output, inputs).proposed_readers) == 6
    assert response.model_metadata["inputBytes"] < MAX_SELECTION_PROMPT_BYTES


def test_empty_pool_does_not_call_model():
    inputs = prepare_reader_selection("w", snapshot(), [])
    calls = Calls()
    result = asyncio.run(RealReaderSelectionProvider(calls).select(inputs))
    assert calls.received == []
    assert result.model_metadata["modelCalled"] is False
    assert validate_reader_selection(result.output, inputs).status == "completed"


def test_large_input_rejected_before_call_without_truncating_pool(settings):
    inputs = prepare_reader_selection("w", snapshot(), [fan(str(i)) for i in range(8)])
    inputs.account_positioning = "中" * MAX_SELECTION_PROMPT_BYTES
    calls = Calls()
    with pytest.raises(ReaderSelectionInputTooLarge) as failure:
        asyncio.run(RealReaderSelectionProvider(calls).select(inputs))
    assert failure.value.actual_bytes > MAX_SELECTION_PROMPT_BYTES
    assert calls.received == [] and len(inputs.candidates) == 8
    # The generic model endpoint cannot bypass the same input-size check.
    with pytest.raises(ReaderSelectionInputTooLarge):
        ModelCallService(settings)._build_prompt(ModelOperation.READER_SELECTION,
                                                inputs.model_dump(by_alias=True))


def test_budget_is_utf8_size_not_english_character_count():
    inputs = prepare_reader_selection("w", snapshot(), [fan()])
    _, user = selection_prompt(inputs)
    assert len(user.encode("utf-8")) > len(user)


def test_worker_persists_budget_failure_and_continues_next_job(store):
    service, wid = store
    request = payload(wid)
    request.input_snapshot.target["body"] = "中" * MAX_SELECTION_PROMPT_BYTES
    oversized = service.create(wid, request)
    valid = service.create(wid, payload(wid, "normal"))
    calls = Calls()
    worker = ReaderSelectionWorker(service, RealReaderSelectionProvider(calls), poll_interval=0.005)

    async def run():
        worker.start()
        try:
            async with asyncio.timeout(3):
                while service.get(wid, valid.id).completed_at is None:
                    await asyncio.sleep(0.005)
        finally:
            await worker.shutdown()
    asyncio.run(run())
    failed = service.get(wid, oversized.id)
    assert failed.error_code == "input_too_large"
    assert failed.model_metadata["modelCalled"] is False
    assert failed.model_metadata["inputBytes"] > MAX_SELECTION_PROMPT_BYTES
    assert service.get(wid, valid.id).status == "completed"
    assert len(calls.received) == 1


@pytest.mark.parametrize("finish", ["stop", "length"])
def test_qwen_wire_request_is_single_structured_call(settings, monkeypatch, finish):
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-test", "usage": {"prompt_tokens": 10, "completion_tokens": 20},
        "choices": [{"finish_reason": finish, "message": {"content": json.dumps({
            "proposedReaders": [proposal()],
        })}}],
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)
    calls = ModelCallService(replace(settings, model_provider="qwen", qwen_api_key="fake"))
    inputs = prepare_reader_selection("w", snapshot(), [fan()])
    if finish == "length":
        with pytest.raises(ValidationError, match="长度上限"):
            asyncio.run(RealReaderSelectionProvider(calls).select(inputs))
    else:
        result = asyncio.run(RealReaderSelectionProvider(calls).select(inputs))
        assert result.model_metadata["usage"]["completion_tokens"] == 20
        assert validate_reader_selection(result.output, inputs).status == "completed"
    assert len(FakeAsyncClient.requests) == 1
    sent = FakeAsyncClient.requests[0]["json"]
    assert sent["response_format"] == {"type": "json_object"}
    assert sent["max_tokens"] == 4000
    assert len(json.loads(sent["messages"][1]["content"])["candidates"]) == 1


def test_partial_result_is_not_repaired_by_an_extra_model_call():
    inputs = prepare_reader_selection("w", snapshot(), [fan()])
    calls = Calls({"proposedReaders": [proposal(), proposal("other-account")]})
    output = asyncio.run(RealReaderSelectionProvider(calls).select(inputs)).output
    result = validate_reader_selection(output, inputs)
    assert result.status == "partially_completed"
    assert len(result.proposed_readers) == 1 and len(calls.received) == 1


def test_default_wiring_requires_configured_qwen_not_anthropic(settings):
    configured = create_app(replace(settings, model_provider="qwen", qwen_api_key="fake"))
    assert isinstance(
        configured.state.reader_selection_worker.provider, RealReaderSelectionProvider,
    )
    assert not configured.state.reader_selection_worker.available  # No import-time execution.
    other = create_app(replace(settings, model_provider="anthropic", anthropic_api_key="fake"))
    assert other.state.reader_selection_worker.provider is None
