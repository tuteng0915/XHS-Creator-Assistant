import asyncio
import hashlib
import json
from dataclasses import replace

import httpx
import pytest

from app.config import Settings
from app.errors import ValidationError
from app.models import ModelOperation
from app.services.account_report_contract import AccountReportOutputError
from app.services.model_calls import MAX_TOKENS, ModelCallService


def forbid_call(*args, **kwargs):
    pytest.fail("This staged transport must not invoke another model path")


@pytest.mark.parametrize("value,expected", [
    (None, "staged"), ("source_led", "source_led"), ("staged", "staged"),
])
def test_account_report_defaults_to_staged_with_an_explicit_single_call_rollback(
    settings, monkeypatch, value, expected,
):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.delenv("ACCOUNT_REPORT_MODE", raising=False)
    if value is not None:
        monkeypatch.setenv("ACCOUNT_REPORT_MODE", value)
    assert settings.account_report_mode == "staged"
    assert settings.qwen_profile_enable_thinking is False
    assert Settings.from_environment().account_report_mode == expected


@pytest.mark.parametrize("value", ["", "other", "STAGED", " staged "])
def test_account_report_mode_rejects_invalid_environment_and_direct_values(
    settings, monkeypatch, value,
):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.setenv("ACCOUNT_REPORT_MODE", value)
    with pytest.raises(ValueError, match="ACCOUNT_REPORT_MODE"):
        Settings.from_environment()
    with pytest.raises(ValueError, match="ACCOUNT_REPORT_MODE"):
        replace(settings, account_report_mode=value)


@pytest.mark.parametrize("provider", ["qwen", "dashscope"])
@pytest.mark.parametrize("thinking", [False, True])
@pytest.mark.parametrize("stage,budget", [
    ("overview", 1600), ("read", 1600), ("synthesis", 6000),
])
def test_staged_report_uses_one_profile_routed_qwen_request(
    settings, monkeypatch, provider, stage, budget, thinking,
):
    requests = []
    before_requests = []
    output = {
        "overview": {
            "summary": {"text": "一条有来源且完整的整体阅读观察", "noteIds": ["n1"]},
            "directions": [{"text": "有来源的内容方向", "noteIds": ["n1", "n3"]}],
            "hypotheses": ["待精读核对的判断"],
            "readings": [{"noteId": "n1", "question": "这篇如何组织真实经验？"}],
        },
        "read": {"assessment": "一条阅读观察", "correction": "", "examples": [
            {"excerptIds": ["b1", "b2"], "interpretation": "两个片段共同体现的写法。"},
            {"excerptIds": ["t"], "interpretation": "原标题的表达特点。"},
        ]},
        "synthesis": {"stageResult": {"observation": "一条汇总观察"}},
    }[stage]

    def respond(request):
        assert before_requests == [True]
        requests.append(request)
        return httpx.Response(200, json={
            "model": "qwen3.8-max-response-version",
            "usage": {"prompt_tokens": 80, "completion_tokens": 35, "total_tokens": 115,
                      "completion_tokens_details": {"reasoning_tokens": 10 if thinking else 0,
                                                    "reasoning_content": "never-retain-this"}},
            "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(output, ensure_ascii=False),
                "reasoning_content": "never-retain-this",
            }}],
        })

    service = ModelCallService(replace(
        settings, model_provider=provider, qwen_api_key="test-placeholder",
        qwen_base_url="https://qwen.example.test/v1/",
        qwen_model="qwen-plus", qwen_profile_model=" qwen3.8-max ",
        qwen_profile_enable_thinking=thinking, qwen_profile_thinking_budget=4096,
    ), before_request=lambda: before_requests.append(True))
    operations = []

    def client(operation):
        operations.append(operation)
        return httpx.AsyncClient(transport=httpx.MockTransport(respond))

    monkeypatch.setattr(service, "_qwen_client", client)
    monkeypatch.setattr(service, "_call_anthropic", forbid_call)
    monkeypatch.setattr(service, "_build_prompt", forbid_call)
    monkeypatch.setattr(service, "review_panel_output", forbid_call)
    system, user = "只输出这一阶段的 JSON。", "这一阶段提供的原始资料。"
    if stage == "read":
        user = json.dumps({"question": "这篇怎样展开？", "note": {
            "title": "真实标题", "bodyExcerpts": [
                {"excerptId": "b1", "text": "第一句。\n"},
                {"excerptId": "b2", "text": "第二句。"},
            ],
        }}, ensure_ascii=False)
    result = asyncio.run(service.call_account_report_step(stage, system, user))

    assert len(requests) == 1
    assert operations == [ModelOperation.PROFILE]
    assert str(requests[0].url) == "https://qwen.example.test/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer test-placeholder"
    assert json.loads(requests[0].content) == {
        "model": "qwen3.8-max", "max_tokens": budget, "temperature": 0.3,
        "response_format": {"type": "json_object"}, "enable_thinking": thinking,
        **({"thinking_budget": 4096} if thinking else {}),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
    }
    assert result.output == output  # Stage contracts need not contain PROFILE's profile envelope.
    assert result.model_metadata == {
        "provider": "qwen", "operation": "profile", "stage": stage,
        "profileModel": "qwen3.8-max", "model": "qwen3.8-max-response-version",
        "modelSource": "response",
        "responseFormat": "json_object",
        "responseSchema": None,
        "enableThinking": thinking, "thinkingBudget": 4096 if thinking else None,
        "systemPromptHash": hashlib.sha256(system.encode("utf-8")).hexdigest(),
        "usage": {"prompt_tokens": 80, "completion_tokens": 35, "total_tokens": 115,
                  "reasoning_tokens": 10 if thinking else 0},
    }
    assert "never-retain-this" not in result.model_dump_json()


def test_staged_report_calls_are_independent_without_history(settings, monkeypatch):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": '{"result":[]}'}}],
        })

    service = ModelCallService(replace(
        settings, qwen_api_key="test-placeholder", qwen_profile_model="", qwen_model="qwen-plus",
    ))
    monkeypatch.setattr(service, "_qwen_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))

    async def run():
        first = await service.call_account_report_step("read", "第一阶段规则", "第一篇资料")
        second = await service.call_account_report_step("read", "第二阶段规则", "第二篇资料")
        return first, second

    results = asyncio.run(run())
    assert len(requests) == 2
    for request, system, user in zip(
        requests, ("第一阶段规则", "第二阶段规则"), ("第一篇资料", "第二篇资料"), strict=True,
    ):
        assert request["messages"] == [
            {"role": "system", "content": system}, {"role": "user", "content": user},
        ]
        assert request["model"] == "qwen-plus"
        assert "enable_thinking" not in request
        assert "thinking_budget" not in request
    for result in results:
        assert result.model_metadata["model"] == "qwen-plus"
        assert result.model_metadata["profileModel"] == "qwen-plus"
        assert result.model_metadata["modelSource"] == "configured"


@pytest.mark.parametrize("stage", ["", "profile", "Read", None, []])
def test_invalid_stage_is_rejected_before_request(settings, monkeypatch, stage):
    service = ModelCallService(settings, before_request=forbid_call)
    monkeypatch.setattr(service, "_call_qwen", forbid_call)
    with pytest.raises(ValidationError, match="Unsupported account report stage"):
        asyncio.run(service.call_account_report_step(stage, "system", "user"))


@pytest.mark.parametrize("provider", ["anthropic", "", "unsupported"])
def test_staged_report_rejects_other_providers_without_fallback(settings, monkeypatch, provider):
    service = ModelCallService(
        replace(settings, model_provider=provider), before_request=forbid_call,
    )
    monkeypatch.setattr(service, "_call_qwen", forbid_call)
    monkeypatch.setattr(service, "_call_anthropic", forbid_call)
    with pytest.raises(ValidationError, match="require MODEL_PROVIDER=qwen or dashscope"):
        asyncio.run(service.call_account_report_step("overview", "system", "user"))


def test_staged_report_missing_qwen_key_does_not_fallback(settings, monkeypatch):
    service = ModelCallService(replace(settings, qwen_api_key=""), before_request=forbid_call)
    monkeypatch.setattr(service, "_call_anthropic", forbid_call)
    monkeypatch.setattr(service, "_qwen_client", forbid_call)
    with pytest.raises(ValidationError, match="QWEN_API_KEY or DASHSCOPE_API_KEY"):
        asyncio.run(service.call_account_report_step("overview", "system", "user"))


@pytest.mark.parametrize("status,finish_reason,content,code", [
    (200, "length", '{"result":[]}', "output_truncated"),
    (200, "stop", "not JSON", "invalid_json"),
    (200, "stop", "[]", "invalid_json"),
    (200, "stop", "", "empty_output"),
    (200, "stop", "{}", "empty_output"),
    (400, "stop", '{"result":[]}', None),
    (401, "stop", '{"result":[]}', None),
    (503, "stop", '{"result":[]}', None),
])
@pytest.mark.parametrize("thinking", [False, True])
def test_staged_report_failure_is_not_reviewed_retried_or_fallback(
    settings, monkeypatch, status, finish_reason, content, code, thinking,
):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(status, json={
            "usage": {"completion_tokens": 10, "reasoning_content": "never-retain-this",
                      "completion_tokens_details": {"reasoning_tokens": 3}},
            "choices": [{"finish_reason": finish_reason, "message": {
                "content": content, "reasoning_content": "never-retain-this",
            }}],
        })

    service = ModelCallService(replace(
        settings, qwen_api_key="test-placeholder", qwen_profile_enable_thinking=thinking,
    ))
    monkeypatch.setattr(service, "_qwen_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    monkeypatch.setattr(service, "_call_anthropic", forbid_call)
    monkeypatch.setattr(service, "review_panel_output", forbid_call)
    with pytest.raises(AccountReportOutputError if code else ValidationError) as error:
        asyncio.run(service.call_account_report_step("read", "system", "user"))
    assert len(requests) == 1
    if code:
        assert error.value.code == code
        assert error.value.metadata is error.value.model_metadata
        assert error.value.metadata["usage"] == {"completion_tokens": 10, "reasoning_tokens": 3}
        assert error.value.metadata["responseFormat"] == "json_object"
        assert error.value.metadata.get("responseSchema") is None
        assert "never-retain-this" not in json.dumps(error.value.metadata)
    else:
        assert not isinstance(error.value, AccountReportOutputError)
        assert str(status) in str(error.value)


@pytest.mark.parametrize("mode", ["source_led", "staged"])
@pytest.mark.parametrize("thinking", [False, True])
def test_default_profile_path_keeps_its_prompt_budget_and_json_object_transport(
    settings, monkeypatch, mode, thinking,
):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {"content": '{"profile":{}}'}}],
        })

    service = ModelCallService(replace(
        settings, account_report_mode=mode, qwen_api_key="test-placeholder",
        qwen_profile_enable_thinking=thinking,
    ))
    monkeypatch.setattr(service, "_qwen_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    context = {"historicalPosts": "原有完整正文"}
    expected_system, expected_user = service._build_prompt(ModelOperation.PROFILE, context)
    result = asyncio.run(service.call_operation(ModelOperation.PROFILE, context))
    assert len(requests) == 1
    assert requests[0]["max_tokens"] == 6000
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert requests[0]["enable_thinking"] is thinking
    if thinking:
        assert requests[0]["thinking_budget"] == 4096
    else:
        assert "thinking_budget" not in requests[0]
    assert requests[0]["messages"] == [
        {"role": "system", "content": expected_system},
        {"role": "user", "content": expected_user},
    ]
    assert result.output == {"profile": {}}
    assert "stage" not in result.model_metadata
    assert "profileModel" not in result.model_metadata
    with pytest.raises(ValidationError, match="missing profile"):
        service._parse_model_output(ModelOperation.PROFILE, '{"result":[]}')


@pytest.mark.parametrize("operation", list(ModelOperation))
def test_stage_budget_key_does_not_change_other_operations(operation):
    baseline = ModelCallService._output_budget(operation, {})
    for stage in ("overview", "read", "synthesis"):
        budget = ModelCallService._output_budget(operation, {"_accountReportStage": stage})
        if operation != ModelOperation.PROFILE:
            assert budget == baseline
    assert ModelCallService._output_budget(ModelOperation.PROFILE, {}) == MAX_TOKENS[
        ModelOperation.PROFILE
    ]


@pytest.mark.parametrize("body", [
    None, [], {}, {"choices": []}, {"choices": [None]},
    {"choices": [{"finish_reason": "stop"}]},
    {"choices": [{"message": {"content": 42}}]},
    {"choices": [{"message": {"content": [{"type": "text", "text": None}]}}]},
])
def test_staged_malformed_response_is_a_safe_output_error(settings, monkeypatch, body):
    service = ModelCallService(replace(settings, qwen_api_key="test-placeholder"))
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, content=json.dumps(body), headers={
            "content-type": "application/json",
        })

    monkeypatch.setattr(service, "_qwen_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    with pytest.raises(AccountReportOutputError) as error:
        asyncio.run(service.call_account_report_step("read", "system", "user"))
    assert error.value.code == "invalid_response"
    assert len(requests) == 1


def test_staged_invalid_response_json_is_a_safe_output_error(settings, monkeypatch):
    service = ModelCallService(replace(settings, qwen_api_key="test-placeholder"))
    monkeypatch.setattr(service, "_qwen_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, text="provider secret")),
    ))
    with pytest.raises(AccountReportOutputError) as error:
        asyncio.run(service.call_account_report_step("read", "system", "user"))
    assert error.value.code == "invalid_response"
    assert error.value.metadata.get("responseSchema") is None
    assert "provider secret" not in str(error.value)
    assert "provider secret" not in json.dumps(error.value.metadata)


def test_staged_network_failure_is_not_a_recoverable_output_error(settings, monkeypatch):
    service = ModelCallService(replace(settings, qwen_api_key="test-placeholder"))

    def respond(request):
        raise httpx.ReadTimeout("network failure", request=request)

    monkeypatch.setattr(service, "_qwen_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    with pytest.raises(httpx.ReadTimeout):
        asyncio.run(service.call_account_report_step("read", "system", "user"))


@pytest.mark.parametrize("model", [
    "qwen3.8-max",
    "qwen-plus",
    "qwen3.8-plus",
    "qwen3.8-max-unverified-version",
    "not-qwen3.8-max",
])
def test_staged_transport_does_not_add_model_specific_schema_requirements(
    settings, monkeypatch, model,
):
    requests = []
    service = ModelCallService(replace(
        settings, qwen_api_key="test-placeholder", qwen_profile_model=model,
    ))

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {
            "content": '{"assessment":"观察"}',
        }}]})

    monkeypatch.setattr(service, "_qwen_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    response = asyncio.run(service.call_account_report_step("read", "system", "user"))
    assert len(requests) == 1
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert response.model_metadata["responseFormat"] == "json_object"
    assert response.model_metadata["responseSchema"] is None
    assert response.output == {"assessment": "观察"}
