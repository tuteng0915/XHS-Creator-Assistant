import asyncio
import hashlib
import json
from copy import deepcopy
from dataclasses import replace

import httpx
import pytest
from test_account_profile_check import load_check
from test_audience_analysis_check import raw_export

from app.models import ModelOperation
from app.services.account_report_prompt import SOURCE_LED_PROFILE_PROMPT


def response_body(output, *, usage=None, finish="stop"):
    text = output if isinstance(output, str) else json.dumps(output, ensure_ascii=False)
    return {
        "model": "qwen-returned-model",
        "usage": usage if usage is not None else {
            "prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
        },
        "choices": [{"finish_reason": finish, "message": {"content": text}}],
    }


@pytest.mark.parametrize("thinking", [False, True])
def test_profile_check_tracks_actual_request_and_preserves_frozen_input(
    tmp_path, settings, thinking,
):
    check = load_check()
    case = check.prepare_case(raw_export(tmp_path))
    original = deepcopy(case)
    requests = []
    output = {"profile": {"pillars": ["private-api-key", "具体做法"]}}
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
             "private": "private-api-key",
             "completion_tokens_details": {"reasoning_tokens": 3 if thinking else 0,
                                           "reasoning_content": "private-reasoning-text"}}

    def respond(request):
        requests.append(json.loads(request.content))
        assert len(requests) == 1  # No hidden editorial call or retry.
        body = response_body(output, usage=usage)
        body["choices"][0]["message"]["reasoning_content"] = "private-reasoning-text"
        return httpx.Response(200, json=body)

    service = check.DiagnosticProfileCalls(
        replace(settings, model_provider="qwen", qwen_api_key="private-api-key",
                qwen_profile_enable_thinking=thinking),
        transport=httpx.MockTransport(respond),
    )
    report = asyncio.run(check.run_check(service, case))
    assert report["status"] == "completed"
    assert case == original
    assert report["context"] == original["context"]
    assert report["snapshot"] == original["snapshot"]
    assert report["requestAttempts"] == service.request_attempts == len(requests) == 1
    diagnostic = report["responseDiagnostic"]
    request_diagnostic, = diagnostic["requests"]
    assert request_diagnostic["requestNumber"] == 1
    assert request_diagnostic["phase"] == diagnostic["phase"] == "parsed"
    assert diagnostic["rawText"] == request_diagnostic["rawText"]
    assert request_diagnostic["timings"]["requestPreparedMs"] <= (
        request_diagnostic["timings"]["finishedMs"]
    )
    assert len(request_diagnostic["systemPromptHash"]) == len(request_diagnostic["inputHash"]) == 64
    assert requests[0]["messages"][0]["content"] == SOURCE_LED_PROFILE_PROMPT
    assert "先准备材料" in requests[0]["messages"][1]["content"]
    totals = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
              "reasoning_tokens": 3 if thinking else 0}
    assert diagnostic["totalUsage"] == request_diagnostic["usage"] == totals
    metadata = report["modelMetadata"]
    assert metadata["requestCount"] == 1
    assert metadata["usage"] == totals
    for record in (metadata, diagnostic, request_diagnostic):
        assert record["enableThinking"] is thinking
        assert record["thinkingBudget"] == (4096 if thinking else None)
    assert requests[0]["max_tokens"] == request_diagnostic["requestedMaxTokens"] == 6000
    assert request_diagnostic["responseFormat"] == "json_object"
    assert request_diagnostic.get("responseSchema") is None
    assert request_diagnostic.get("schemaHash") is None
    assert requests[0]["enable_thinking"] is thinking
    if thinking:
        assert requests[0]["thinking_budget"] == 4096
    else:
        assert "thinking_budget" not in requests[0]
    assert metadata["systemPromptHash"] == hashlib.sha256(
        SOURCE_LED_PROFILE_PROMPT.encode(),
    ).hexdigest()
    assert metadata["model"] == "qwen-returned-model" and metadata["modelSource"] == "response"
    assert "private-api-key" not in json.dumps(report)
    assert "private-reasoning-text" not in json.dumps(report)
    assert "reasoning_content" not in json.dumps(report)
    assert "[REDACTED]" in request_diagnostic["rawText"]
    assert "private" not in json.dumps(metadata)


@pytest.mark.parametrize("failure,attempts,phase", [
    ("configuration", 0, "configuration"),
    ("http", 1, "http_status"),
    ("transport", 1, "transport"),
    ("json", 1, "model_json"),
    ("length", 1, "output_length"),
    ("schema", 1, "output_schema"),
])
@pytest.mark.parametrize("thinking", [False, True])
def test_failed_check_reports_actual_attempts_without_retry_or_partial_success(
    tmp_path, settings, failure, attempts, phase, thinking,
):
    check = load_check()
    case = check.prepare_case(raw_export(tmp_path))
    original = deepcopy(case)
    requests = []

    def respond(request):
        requests.append(request)
        assert len(requests) <= attempts
        if failure == "http":
            return httpx.Response(503, json={"error": "private-error-key"})
        if failure == "transport":
            raise httpx.ReadTimeout("private-error-key", request=request)
        output = ("not valid json" if failure == "json" else
                  {"invalid": "result"} if failure == "schema" else {"profile": {}})
        body = response_body(
            output, finish="length" if failure == "length" else "stop",
        )
        body["choices"][0]["message"]["reasoning_content"] = "never-retain-reasoning"
        return httpx.Response(200, json=body)

    service = check.DiagnosticProfileCalls(
        replace(settings, model_provider="qwen",
                qwen_api_key="" if failure == "configuration" else "private-error-key",
                qwen_profile_enable_thinking=thinking),
        transport=httpx.MockTransport(respond),
    )
    report = asyncio.run(check.run_check(service, case))
    assert report["status"] == "failed"
    assert report["error"]["phase"] == "model_call"
    assert "result" not in report and "output" not in report and "modelMetadata" not in report
    assert report["requestAttempts"] == service.request_attempts == len(requests) == attempts
    assert case == original
    diagnostic = report["responseDiagnostic"]
    assert diagnostic["phase"] == phase
    assert diagnostic["requestAttempts"] == len(diagnostic["requests"]) == attempts
    assert "private-error-key" not in json.dumps(report)
    assert "never-retain-reasoning" not in json.dumps(report)
    assert diagnostic["enableThinking"] is thinking
    assert diagnostic["thinkingBudget"] == (4096 if thinking else None)


def test_diagnostics_reset_between_operations_and_keep_safe_metadata_only(tmp_path, settings):
    check = load_check()
    case = check.prepare_case(raw_export(tmp_path))
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json=response_body({
            "profile": {"hookStyles": ["从具体动作切入，再展开说明。"]},
        }))

    service = check.DiagnosticProfileCalls(
        replace(settings, model_provider="qwen", qwen_api_key="private-key"),
        transport=httpx.MockTransport(respond),
    )
    for _ in range(2):
        report = asyncio.run(check.run_check(service, case))
        assert report["status"] == "completed"
        assert report["requestAttempts"] == len(report["responseDiagnostic"]["requests"]) == 1
        assert report["modelMetadata"]["usage"]["total_tokens"] == 15
    assert len(requests) == 2
    metadata = service._safe_metadata({
        "model": "private-key", "headers": {"Authorization": "should-not-copy"},
        "usage": {"prompt_tokens": 8, "completion_tokens": True, "total_tokens": -2,
                  "output_tokens": 1.5, "private": "should-not-copy"},
    }, ModelOperation.PROFILE)
    assert metadata["usage"] == {"prompt_tokens": 8}
    assert "should-not-copy" not in json.dumps(metadata)
    assert "private-key" not in json.dumps(metadata)


@pytest.mark.parametrize("usage,expected", [
    ({"completion_tokens_details": {"reasoning_tokens": 12, "private": "never-retain"}},
     {"reasoning_tokens": 12}),
    ({"output_tokens_details": {"reasoning_tokens": 8}}, {"reasoning_tokens": 8}),
    ({"reasoning_tokens": 5, "completion_tokens_details": {"reasoning_tokens": 5}},
     {"reasoning_tokens": 5}),
    ({"completion_tokens_details": {"reasoning_tokens": True}}, {}),
    ({"completion_tokens_details": {"reasoning_tokens": -1}}, {}),
    ({"completion_tokens_details": {"reasoning_tokens": 1.5}}, {}),
    ({"completion_tokens_details": {"reasoning_tokens": "12"}}, {}),
    ({"completion_tokens_details": "never-retain"}, {}),
    (None, {}),
])
def test_diagnostics_retain_only_safe_reasoning_token_counts(settings, usage, expected):
    check = load_check()
    service = check.DiagnosticProfileCalls(settings)
    metadata = service._safe_metadata({"usage": usage}, ModelOperation.PROFILE)
    assert metadata["usage"] == expected


def test_diagnostics_sum_reasoning_as_a_subset_without_inflating_total_usage(settings):
    check = load_check()
    service = check.DiagnosticProfileCalls(settings)
    service.request_diagnostics = [
        {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                   "reasoning_tokens": 3}},
        {"usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15,
                   "completion_tokens_details": {"reasoning_tokens": 4}}},
    ]
    assert service._total_usage() == {
        "prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30, "reasoning_tokens": 7,
    }


@pytest.mark.parametrize("invalid_source", [False, True])
def test_source_led_result_never_triggers_editorial_call_or_validation_retry(
    tmp_path, settings, invalid_source,
):
    check = load_check()
    case = check.prepare_case(raw_export(tmp_path))
    output = {"profile": {
        "reportFormat": "source-led/v2",
        "titleReadings": [{"noteId": "n1", "move": "两部分分别指认标题内容", "parts": [
            {"text": "不存在的片段" if invalid_source else "真实", "role": "前半句"},
            {"text": "标题", "role": "后半句"},
        ]}],
        "nextMoves": [],
    }}
    original = deepcopy(output)
    requests = []

    def respond(request):
        requests.append(request)
        assert len(requests) == 1
        return httpx.Response(200, json=response_body(output))

    service = check.DiagnosticProfileCalls(
        replace(settings, model_provider="qwen", qwen_api_key="placeholder"),
        transport=httpx.MockTransport(respond),
    )
    report = asyncio.run(check.run_check(service, case))
    assert report["requestAttempts"] == len(requests) == 1
    assert report["output"] == output == original
    assert report["responseDiagnostic"]["phase"] == "parsed"
    assert "accountReportEdit" not in report["modelMetadata"]
    if invalid_source:
        assert report["status"] == "failed" and report["error"]["phase"] == "validation"
        assert "result" not in report
    else:
        assert report["status"] == "completed"
        assert report["result"]["profile"]["titleFormulas"][0]["examples"] == ["真实标题"]


def test_deepseek_profile_diagnostics_use_own_transport_and_safe_metadata(tmp_path, settings):
    check = load_check()
    case = check.prepare_case(raw_export(tmp_path))
    original = deepcopy(case)
    requests = []

    def respond(request):
        requests.append(request)
        assert str(request.url) == "https://deepseek.invalid/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer private-deepseek-key"
        payload = json.loads(request.content)
        assert payload["model"] == "deepseek-flash-test"
        assert payload["thinking"] == {"type": "disabled"}
        assert "enable_thinking" not in payload and "thinking_budget" not in payload
        assert request.extensions["timeout"]["read"] == 179
        body = response_body({"profile": {"pillars": ["private-deepseek-key"]}}, usage={
            "prompt_tokens": 12, "completion_tokens": 6, "total_tokens": 18,
            "completion_tokens_details": {"reasoning_tokens": 2,
                                           "reasoning_content": "private-reasoning"},
            "headers": {"authorization": "never-retain-header"},
        })
        body["model"] = "deepseek-returned-model"
        body["choices"][0]["message"]["reasoning_content"] = "private-reasoning"
        return httpx.Response(200, json=body, headers={"x-private": "never-retain-header"})

    service = check.DiagnosticProfileCalls(
        replace(settings, model_provider="deepseek", deepseek_api_key="private-deepseek-key",
                deepseek_model="deepseek-flash-test", deepseek_base_url="https://deepseek.invalid/v1",
                deepseek_read_timeout_seconds=179, qwen_profile_enable_thinking=True),
        transport=httpx.MockTransport(respond),
    )
    report = asyncio.run(check.run_check(service, case))
    assert report["status"] == "completed"
    assert case == original
    assert report["requestAttempts"] == len(requests) == 1
    metadata = report["modelMetadata"]
    assert metadata["provider"] == "deepseek"
    assert metadata["model"] == "deepseek-returned-model"
    assert metadata["modelSource"] == "response"
    assert metadata["requestCount"] == 1
    assert metadata["usage"] == {"prompt_tokens": 12, "completion_tokens": 6,
                                 "total_tokens": 18, "reasoning_tokens": 2}
    diagnostic = report["responseDiagnostic"]
    request_diagnostic, = diagnostic["requests"]
    assert request_diagnostic["timeoutsSeconds"]["read"] == 179
    assert request_diagnostic["requestedMaxTokens"] == 6000
    assert request_diagnostic["responseFormat"] == "json_object"
    for record in (metadata, diagnostic, request_diagnostic):
        assert record["enableThinking"] is False
        assert record["thinkingBudget"] is None
    serialized = json.dumps(report)
    for private in ("private-deepseek-key", "private-reasoning", "reasoning_content",
                    "never-retain-header", "https://deepseek.invalid"):
        assert private not in serialized
    assert "[REDACTED]" in diagnostic["rawText"]


@pytest.mark.parametrize("failure,attempts,phase", [
    ("configuration", 0, "configuration"), ("http", 1, "http_status"),
    ("transport", 1, "transport"), ("json", 1, "model_json"),
    ("length", 1, "output_length"),
])
def test_deepseek_profile_failures_have_no_retry_or_qwen_fallback(
    tmp_path, settings, failure, attempts, phase,
):
    check = load_check()
    requests = []

    def respond(request):
        requests.append(request)
        assert request.url.host == "deepseek.invalid"
        if failure == "http":
            return httpx.Response(429, json={"error": "private-deepseek-error"})
        if failure == "transport":
            raise httpx.ReadTimeout("private-deepseek-error", request=request)
        return httpx.Response(200, json=response_body(
            "invalid json" if failure == "json" else {"profile": {}},
            finish="length" if failure == "length" else "stop",
        ))

    service = check.DiagnosticProfileCalls(
        replace(settings, model_provider="deepseek", deepseek_base_url="https://deepseek.invalid",
                deepseek_api_key="" if failure == "configuration" else "private-deepseek-error",
                qwen_api_key="qwen-key-must-not-be-used"),
        transport=httpx.MockTransport(respond),
    )
    report = asyncio.run(check.run_check(service, check.prepare_case(raw_export(tmp_path))))
    assert report["status"] == "failed"
    assert report["requestAttempts"] == len(requests) == attempts
    assert report["responseDiagnostic"]["phase"] == phase
    assert report["responseDiagnostic"]["enableThinking"] is False
    assert len(report["responseDiagnostic"]["requests"]) == attempts
    assert "private-deepseek-error" not in json.dumps(report)
    assert "qwen-key-must-not-be-used" not in json.dumps(report)
