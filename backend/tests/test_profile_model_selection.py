import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from app.models import ModelOperation
from app.services.model_calls import ModelCallService


def test_default_profile_model_does_not_change_any_other_operation(settings):
    service = ModelCallService(settings)
    assert settings.qwen_model == "qwen-plus"
    assert service.qwen_model_for(ModelOperation.PROFILE) == "qwen3.8-max"
    for operation in ModelOperation:
        if operation != ModelOperation.PROFILE:
            assert service.qwen_model_for(operation) == "qwen-plus"


@pytest.mark.parametrize("operation", list(ModelOperation))
def test_profile_thinking_opt_in_has_no_effect_on_other_operations(settings, operation):
    service = ModelCallService(replace(
        settings, qwen_profile_enable_thinking=True, qwen_profile_thinking_budget=8192,
    ))
    expected = {"enable_thinking": True, "thinking_budget": 8192}
    assert service.qwen_thinking_parameters(operation) == (
        expected if operation == ModelOperation.PROFILE else {}
    )


@pytest.mark.parametrize("override,general,operation,expected,thinking", [
    ("", "qwen-plus", ModelOperation.PROFILE, "qwen-plus", None),
    ("  ", "qwen-plus", ModelOperation.PROFILE, "qwen-plus", None),
    (" qwen3.8-max ", "qwen-plus", ModelOperation.PROFILE, "qwen3.8-max", False),
    ("qwen3.8-plus", "qwen-plus", ModelOperation.PROFILE, "qwen3.8-plus", False),
    ("qwen-plus", "qwen3.8-max", ModelOperation.PROFILE, "qwen-plus", None),
    ("", "qwen3.8-max", ModelOperation.PROFILE, "qwen3.8-max", False),
    ("qwen3.8-max", "qwen-plus", ModelOperation.PAIN_POINTS, "qwen-plus", None),
    ("qwen3.8-max", "qwen3.8-plus", ModelOperation.PAIN_POINTS, "qwen3.8-plus", None),
])
@pytest.mark.parametrize("provider", ["qwen", "dashscope"])
@pytest.mark.parametrize("enabled", [False, True])
def test_profile_override_only_changes_selected_qwen_request(
    settings, monkeypatch, override, general, operation, expected, thinking, provider, enabled,
):
    requests = []

    def respond(request):
        requests.append(request)
        content = '{"profile":{}}' if operation == ModelOperation.PROFILE else '{"painPoints":[]}'
        # Missing response.model must fall back to this operation's selected model.
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        })

    service = ModelCallService(replace(
        settings, model_provider=provider, qwen_api_key="test-placeholder",
        qwen_model=general, qwen_profile_model=override,
        qwen_profile_enable_thinking=enabled, qwen_profile_thinking_budget=2048,
    ))
    monkeypatch.setattr(service, "_qwen_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    response = asyncio.run(service.call_operation(operation, {"historicalPosts": "已保存正文"}))
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    assert payload["model"] == expected
    assert payload["temperature"] == 0.3
    assert payload["response_format"] == {"type": "json_object"}
    if enabled and operation == ModelOperation.PROFILE:
        thinking = True
        assert payload["thinking_budget"] == 2048
    else:
        assert "thinking_budget" not in payload
    if thinking is None:
        assert "enable_thinking" not in payload
    else:
        assert payload["enable_thinking"] is thinking
    assert response.model_metadata["model"] == expected
    assert response.model_metadata["modelSource"] == "configured"
    if operation == ModelOperation.PROFILE:
        assert response.model_metadata["enableThinking"] is thinking
        assert response.model_metadata["thinkingBudget"] == (2048 if thinking is True else None)
    else:
        assert "enableThinking" not in response.model_metadata
        assert "thinkingBudget" not in response.model_metadata


def test_anthropic_profile_does_not_receive_qwen_override_or_thinking_flag(settings, monkeypatch):
    requests = []
    real_client = httpx.AsyncClient

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"content": [{"type": "text", "text": '{"profile":{}}'}]})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: real_client(
        **kwargs, transport=httpx.MockTransport(respond),
    ))
    service = ModelCallService(replace(
        settings, model_provider="anthropic", anthropic_api_key="test-placeholder",
        anthropic_model="configured-anthropic-model", qwen_profile_model="qwen3.8-max",
        qwen_profile_enable_thinking=True,
    ))
    response = asyncio.run(service.call_operation(ModelOperation.PROFILE, {}))
    assert len(requests) == 1
    payload = json.loads(requests[0].content)
    assert payload["model"] == "configured-anthropic-model"
    assert "enable_thinking" not in payload
    assert "thinking_budget" not in payload
    assert "enableThinking" not in response.model_metadata
    assert "thinkingBudget" not in response.model_metadata
    assert response.model_metadata["provider"] == "anthropic"
    assert response.model_metadata["model"] == "configured-anthropic-model"


@pytest.mark.parametrize("thinking", [False, True])
@pytest.mark.parametrize("model", ["qwen3.8-max", "qwen-plus", "qwen3.8-max-new-version"])
def test_structured_profile_uses_the_same_json_object_transport_for_all_models(
    settings, monkeypatch, thinking, model,
):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {
            "content": '{"profile":{}}',
        }}]})

    service = ModelCallService(replace(
        settings, qwen_api_key="test-placeholder", qwen_profile_model=model,
        qwen_profile_enable_thinking=thinking,
    ))
    monkeypatch.setattr(service, "_qwen_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    response = asyncio.run(service.call_operation(ModelOperation.PROFILE, {
        "historicalPosts": json.dumps({"schemaVersion": "account-reading-input/v2", "notes": [
            {"noteId": "stable-one", "title": "原标题", "body": "原正文。"},
        ]}),
    }))
    assert len(requests) == 1
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert requests[0]["max_tokens"] == 6000
    assert response.model_metadata["responseFormat"] == "json_object"
    assert response.model_metadata["responseSchema"] is None
