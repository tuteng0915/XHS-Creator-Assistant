import asyncio
import json
from dataclasses import replace

import httpx
import pytest

from app.config import Settings
from app.errors import ValidationError
from app.models import ModelOperation
from app.services.account_report_contract import AccountReportOutputError
from app.services.model_calls import ModelCallService


def forbid_call(*args, **kwargs):
    pytest.fail("DeepSeek must not fall back to another model provider")


def test_account_provider_defaults_are_scoped_and_environment_is_independent(monkeypatch):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    for key in ("MODEL_PROVIDER", "ACCOUNT_DIAGNOSIS_PROVIDER", "DEEPSEEK_API_KEY",
                "DEEPSEEK_MODEL", "DEEPSEEK_BASE_URL", "DEEPSEEK_READ_TIMEOUT_SECONDS"):
        monkeypatch.delenv(key, raising=False)
    general = Settings.from_environment()
    account = general.for_account_diagnosis()
    assert general.model_provider == "deepseek"
    assert account.model_provider == general.account_diagnosis_provider == "deepseek"
    assert account.deepseek_api_key == ""
    assert account.deepseek_model == "deepseek-flash"
    assert account.deepseek_base_url == "https://api.deepseek.com"
    assert account.deepseek_read_timeout_seconds == 180
    assert account.qwen_model == general.qwen_model
    monkeypatch.setenv("DEEPSEEK_API_KEY", "placeholder-secret")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-flash-pinned")
    monkeypatch.setenv("DEEPSEEK_BASE_URL", "https://deepseek.example.test/v1")
    monkeypatch.setenv("DEEPSEEK_READ_TIMEOUT_SECONDS", "240")
    custom = Settings.from_environment()
    assert custom.model_provider == "deepseek"
    assert custom.deepseek_api_key == "placeholder-secret"
    assert custom.deepseek_model == "deepseek-flash-pinned"
    assert custom.deepseek_base_url == "https://deepseek.example.test/v1"
    assert custom.deepseek_read_timeout_seconds == 240


@pytest.mark.parametrize("override,expected", [
    ("qwen", "qwen"), (" QWEN ", "qwen"), ("dashscope", "dashscope"),
    ("anthropic", "anthropic"), ("deepseek", "deepseek"),
    ("inherit", "anthropic"), (" INHERIT ", "anthropic"), ("", "anthropic"),
])
def test_account_provider_override_and_explicit_rollback(settings, monkeypatch, override, expected):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
    monkeypatch.setenv("ACCOUNT_DIAGNOSIS_PROVIDER", override)
    configured = Settings.from_environment()
    assert configured.for_account_diagnosis().model_provider == expected
    direct = replace(settings, model_provider="anthropic", account_diagnosis_provider=override)
    assert direct.for_account_diagnosis().model_provider == expected
    assert direct.model_provider == "anthropic"


@pytest.mark.parametrize("value", ["unknown", "deepseek-chat", None, True])
def test_account_provider_rejects_unknown_direct_values(settings, value):
    with pytest.raises(ValueError, match="ACCOUNT_DIAGNOSIS_PROVIDER"):
        replace(settings, account_diagnosis_provider=value)


@pytest.mark.parametrize("value", [0, 301, True, 1.5, None, "180"])
def test_deepseek_timeout_is_bounded(settings, value):
    with pytest.raises(ValueError, match="DEEPSEEK_READ_TIMEOUT_SECONDS"):
        replace(settings, deepseek_read_timeout_seconds=value)


@pytest.mark.parametrize("value", ["", "invalid", "0", "301", "1.5"])
def test_deepseek_timeout_rejects_invalid_environment(monkeypatch, value):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.setenv("DEEPSEEK_READ_TIMEOUT_SECONDS", value)
    with pytest.raises(ValueError, match="DEEPSEEK_READ_TIMEOUT_SECONDS"):
        Settings.from_environment()


@pytest.mark.parametrize("kind,stage,budget,output", [
    ("profile", "overview", 1600, {"overview": "阅读观察"}),
    ("profile", "read", 1600, {"assessment": "独立阅读"}),
    ("profile", "synthesis", 6000, {"stageResult": {"observation": "汇总观察"}}),
    ("feedback", "retrieve", 2200, {"candidates": []}),
    ("feedback", "rank", 500, {"selectedIds": []}),
])
def test_deepseek_steps_share_json_transport_and_keep_stage_budgets(
    settings, monkeypatch, kind, stage, budget, output,
):
    requests = []
    before_requests = []

    def respond(request):
        assert before_requests == [True]
        requests.append(request)
        return httpx.Response(200, json={
            "model": "deepseek-flash-2026-version",
            "usage": {
                "prompt_tokens": 80, "completion_tokens": 35, "total_tokens": 115,
                "prompt_cache_hit_tokens": 60, "prompt_cache_miss_tokens": 20,
                "input_tokens": -1, "output_tokens": True,
                "reasoning_content": "never-retain-this",
                "api_key": "placeholder-secret",
                "completion_tokens_details": {
                    "reasoning_tokens": 0, "reasoning_content": "never-retain-this",
                },
            },
            "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(output, ensure_ascii=False),
                "reasoning_content": "never-retain-this",
            }}],
        })

    service = ModelCallService(replace(
        settings, model_provider="deepseek", deepseek_api_key="placeholder-secret",
        deepseek_base_url="https://deepseek.example.test/v1/",
        qwen_profile_enable_thinking=True,
    ), before_request=lambda: before_requests.append(True))
    operations = []

    def client(operation):
        operations.append(operation)
        return httpx.AsyncClient(transport=httpx.MockTransport(respond))

    monkeypatch.setattr(service, "_deepseek_client", client)
    monkeypatch.setattr(service, "_call_qwen", forbid_call)
    monkeypatch.setattr(service, "_call_anthropic", forbid_call)
    monkeypatch.setattr(service, "_build_prompt", forbid_call)
    monkeypatch.setattr(service, "review_panel_output", forbid_call)
    method = (service.call_account_report_step if kind == "profile"
              else service.call_reader_feedback_step)
    result = asyncio.run(method(stage, "只输出阶段 JSON。", "这一阶段的原文。"))

    expected_operation = ModelOperation.PROFILE if kind == "profile" else ModelOperation.PAIN_POINTS
    assert operations == [expected_operation]
    assert len(requests) == 1
    assert str(requests[0].url) == "https://deepseek.example.test/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer placeholder-secret"
    assert json.loads(requests[0].content) == {
        "model": "deepseek-flash", "max_tokens": budget, "temperature": 0.3,
        "response_format": {"type": "json_object"}, "thinking": {"type": "disabled"},
        "messages": [{"role": "system", "content": "只输出阶段 JSON。"},
                     {"role": "user", "content": "这一阶段的原文。"}],
    }
    assert result.output == output
    assert result.model_metadata["provider"] == "deepseek"
    assert result.model_metadata["stage"] == stage
    assert result.model_metadata["modelSource"] == "response"
    assert result.model_metadata["enableThinking"] is False
    assert result.model_metadata["thinkingBudget"] is None
    assert result.model_metadata["responseFormat"] == "json_object"
    assert result.model_metadata["usage"] == {
        "prompt_tokens": 80, "completion_tokens": 35, "total_tokens": 115,
        "prompt_cache_hit_tokens": 60, "prompt_cache_miss_tokens": 20, "reasoning_tokens": 0,
    }
    if kind == "profile":
        assert result.model_metadata["profileModel"] == "deepseek-flash"
    assert "never-retain-this" not in result.model_dump_json()
    assert "placeholder-secret" not in result.model_dump_json()


@pytest.mark.parametrize("operation,output,budget", [
    (ModelOperation.PROFILE, {"data": {"profile": {}}}, 6000),
    (ModelOperation.PAIN_POINTS, {"pain_points": []}, 1000),
    (ModelOperation.TOPICS, {"topics": [], "titles": []}, 2000),
])
def test_deepseek_regular_operations_keep_shared_parser_and_budgets(
    settings, monkeypatch, operation, output, budget,
):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "choices": [{"finish_reason": "stop", "message": {
                "content": "```json\n" + json.dumps(output) + "\n```",
                "reasoning_content": "not-for-client",
            }}],
            "usage": {"completion_tokens": 5, "raw_content": "not-for-client"},
        })

    service = ModelCallService(replace(
        settings, model_provider="deepseek", deepseek_api_key="placeholder-secret",
    ))
    monkeypatch.setattr(service, "_deepseek_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    result = asyncio.run(service.call_operation(operation, {}))
    expected = service._parse_model_output(operation, json.dumps(output))
    assert result.output == expected
    assert result.model_metadata["model"] == "deepseek-flash"
    assert result.model_metadata["modelSource"] == "configured"
    assert result.model_metadata["usage"] == {"completion_tokens": 5}
    assert "not-for-client" not in result.model_dump_json()
    assert len(requests) == 1
    assert requests[0]["max_tokens"] == budget
    assert requests[0]["thinking"] == {"type": "disabled"}


@pytest.mark.parametrize("kind", ["regular", "profile", "feedback"])
@pytest.mark.parametrize("key", ["", "   "])
def test_missing_deepseek_key_fails_without_request_or_fallback(settings, monkeypatch, kind, key):
    service = ModelCallService(replace(
        settings, model_provider="deepseek", deepseek_api_key=key,
        qwen_api_key="available-but-not-a-fallback",
    ), before_request=forbid_call)
    monkeypatch.setattr(service, "_deepseek_client", forbid_call)
    monkeypatch.setattr(service, "_call_qwen", forbid_call)
    monkeypatch.setattr(service, "_call_anthropic", forbid_call)
    with pytest.raises(ValidationError, match="DEEPSEEK_API_KEY is required"):
        asyncio.run(_invoke(service, kind))


async def _invoke(service, kind):
    if kind == "profile":
        return await service.call_account_report_step("read", "输出 JSON", "原文")
    if kind == "feedback":
        return await service.call_reader_feedback_step("retrieve", "输出 JSON", "评论")
    return await service.call_operation(ModelOperation.TOPICS, {})


@pytest.mark.parametrize("body,code", [
    ([], "invalid_response"),
    ({"choices": []}, "invalid_response"),
    ({"choices": [{"message": "not-an-object"}]}, "invalid_response"),
    ({"choices": [{"finish_reason": "length", "message": {"content": "{}"}}]}, "output_truncated"),
    ({"choices": [{"message": {"content": "not JSON"}}]}, "invalid_json"),
    ({"choices": [{"message": {"content": "[]"}}]}, "invalid_json"),
    ({"choices": [{"message": {"content": ""}}]}, "empty_output"),
    ({"choices": [{"message": {"content": "{}"}}]}, "empty_output"),
])
def test_deepseek_staged_failures_keep_safe_classification(settings, monkeypatch, body, code):
    requests = []
    if isinstance(body, dict):
        body["usage"] = {"completion_tokens": 10, "reasoning_content": "private-provider-text"}
        body["model"] = {"reasoning_content": "private-provider-text"}

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=body)

    service = ModelCallService(replace(
        settings, model_provider="deepseek", deepseek_api_key="placeholder-secret",
    ))
    monkeypatch.setattr(service, "_deepseek_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    monkeypatch.setattr(service, "_call_qwen", forbid_call)
    with pytest.raises(AccountReportOutputError) as error:
        asyncio.run(_invoke(service, "profile"))
    assert len(requests) == 1
    assert error.value.code == code
    assert error.value.model_metadata["provider"] == "deepseek"
    assert error.value.model_metadata["model"] == "deepseek-flash"
    assert "private-provider-text" not in json.dumps(error.value.model_metadata)
    assert "placeholder-secret" not in str(error.value)


@pytest.mark.parametrize("kind", ["regular", "profile", "feedback"])
@pytest.mark.parametrize("failure", ["http", "network", "invalid_json"])
def test_deepseek_external_errors_never_include_raw_response_or_secret(
    settings, monkeypatch, kind, failure,
):
    requests = []

    def respond(request):
        requests.append(request)
        if failure == "network":
            raise httpx.ReadTimeout("private-provider-text placeholder-secret", request=request)
        return httpx.Response(503 if failure == "http" else 200,
                              text="private-provider-text placeholder-secret")

    service = ModelCallService(replace(
        settings, model_provider="deepseek", deepseek_api_key="placeholder-secret",
    ))
    monkeypatch.setattr(service, "_deepseek_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    monkeypatch.setattr(service, "_call_qwen", forbid_call)
    expected_error = (AccountReportOutputError if kind == "profile" and failure == "invalid_json"
                      else ValidationError)
    with pytest.raises(expected_error) as error:
        asyncio.run(_invoke(service, kind))
    assert len(requests) == 1
    assert "private-provider-text" not in str(error.value)
    assert "placeholder-secret" not in str(error.value)
    if failure in {"http", "network"}:
        assert not isinstance(error.value, AccountReportOutputError)
    elif kind == "profile":
        assert error.value.code == "invalid_response"


def test_deepseek_read_timeout_applies_to_account_feedback_and_topics(settings):
    service = ModelCallService(replace(settings, deepseek_read_timeout_seconds=123))
    for operation in (ModelOperation.PROFILE, ModelOperation.PAIN_POINTS, ModelOperation.TOPICS):
        client = service._deepseek_client(operation)
        assert client.timeout.read == 123
        assert client.timeout.connect == 90
        asyncio.run(client.aclose())


@pytest.mark.parametrize("kind", ["regular", "profile", "feedback"])
def test_deepseek_invalid_url_never_exposes_configured_values(settings, monkeypatch, kind):
    service = ModelCallService(replace(
        settings, model_provider="deepseek", deepseek_api_key="placeholder-api-secret",
        deepseek_base_url="https://api.example:placeholder-url-secret",
    ))
    monkeypatch.setattr(service, "_deepseek_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(forbid_call),
    ))
    monkeypatch.setattr(service, "_call_qwen", forbid_call)
    with pytest.raises(ValidationError) as error:
        asyncio.run(_invoke(service, kind))
    assert not isinstance(error.value, AccountReportOutputError)
    assert str(error.value) == "DeepSeek model call failed (transport error)"
    assert error.value.__suppress_context__ is True
    assert "placeholder" not in str(error.value)
    assert "api.example" not in str(error.value)
