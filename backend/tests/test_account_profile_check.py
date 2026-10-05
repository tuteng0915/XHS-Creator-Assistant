import asyncio
import importlib.util
import json
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_audience_analysis_check import raw_export

from app.models import ModelCallResponse, ModelOperation
from app.services.account_diagnosis_evidence import build_account_observations, profile_stage_input


def load_check():
    path = Path(__file__).resolve().parents[2] / "scripts/check_account_profile.py"
    spec = importlib.util.spec_from_file_location("account_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_preview_is_free(tmp_path, monkeypatch, capsys):
    check = load_check()
    source = raw_export(tmp_path)
    case = check.prepare_case(source)
    assert len(case["snapshot"]["xhsCreatorProfile"]["notes"]) == 10
    assert case["observations"]["coverage"]["selectedCount"] == 10
    assert case["observations"]["coverage"]["availableCount"] == 12
    assert "先准备材料" in case["context"]["historicalPosts"]
    assert "发布时间" in case["context"]["historicalPosts"]
    assert "请发到我的邮箱" not in case["context"]["historicalPosts"]
    monkeypatch.setattr(sys, "argv", [check.__file__, str(source)])
    monkeypatch.setattr(
        check.Settings, "from_environment", lambda: pytest.fail("preview must be free")
    )
    assert check.main() == 0
    assert json.loads(capsys.readouterr().out)["requestAttempts"] == 0


def test_report_replay_preserves_frozen_input_without_loading_sources_or_settings(
    tmp_path, monkeypatch, capsys,
):
    check = load_check()
    case = check.prepare_case(raw_export(tmp_path))
    report = tmp_path / "previous.json"
    report.write_text(json.dumps({**case, "output": {"must_not_be_input": True}},
                                 ensure_ascii=False), encoding="utf-8")
    assert check.case_from_report(report) == case
    monkeypatch.setattr(check, "prepare_case", lambda _: pytest.fail("must reuse frozen input"))
    monkeypatch.setattr(check.Settings, "from_environment", lambda: pytest.fail("free preview"))
    monkeypatch.setattr(sys, "argv", [check.__file__, "--input-from", str(report)])
    assert check.main() == 0
    assert json.loads(capsys.readouterr().out)["requestAttempts"] == 0


@pytest.mark.parametrize("content", [[], {}, {"snapshot": {}, "context": {}, "observations": {}},
    {"snapshot": {}, "context": {"positioning": "账号", "historicalPosts": "正文"},
     "observations": {}}])
def test_report_replay_rejects_incomplete_inputs_before_model_configuration(tmp_path, content):
    check = load_check()
    report = tmp_path / "bad.json"
    report.write_text(json.dumps(content), encoding="utf-8")
    with pytest.raises(ValueError):
        check.case_from_report(report)


@pytest.mark.parametrize("comparable", [False, True])
def test_shared_input_matches_previous_controller_exactly_without_mutating_snapshot(comparable):
    notes = [{"noteId": str(i), "publishedAt": f"2026-{i+1:02d}-01T00:00:00Z"}
             for i in range(6 if comparable else 2)]
    snapshot = {"accountPositioning": "中文定位", "historicalPosts": {"content": "逐字历史\n"},
                "xhsCreatorProfile": {"notes": notes}}
    original = deepcopy(snapshot)
    observations = build_account_observations(snapshot, "2026-10-03")
    expected = "逐字历史\n"
    if comparable:
        expected += ("\n\n可比较的前后发布时间组（只比较内容方向，不比较累计互动）：\n"
                     + json.dumps(observations["chronology"], ensure_ascii=False))
    context, actual = profile_stage_input(snapshot, "2026-10-03")
    assert context == {"positioning": "中文定位", "historicalPosts": expected}
    assert actual == observations
    assert snapshot == original


def test_check_makes_one_profile_call_and_keeps_raw_and_filtered_results(tmp_path):
    check = load_check()
    case = check.prepare_case(raw_export(tmp_path))
    claim = {"statement": "准备清晰", "evidence": [{"noteId": "11", "quote": "先准备材料"}]}
    rejected = {"statement": "不存在的引用", "evidence": [{"noteId": "11", "quote": "不存在"}]}

    class Model:
        calls = 0

        async def call_operation(self, operation, context):
            self.calls += 1
            assert operation == ModelOperation.PROFILE
            assert context is case["context"]
            return ModelCallResponse(output={"profile": {"accountPortrait": {
                "keywords": [claim, rejected], "strengths": [claim], "encouragement": claim,
            }}}, model_metadata={"model": "fake"})

    model = Model()
    report = asyncio.run(check.run_check(model, case))
    assert model.calls == 1
    assert report["status"] == "completed"
    assert report["semanticStatus"] == "not_reviewed"
    assert len(report["output"]["profile"]["accountPortrait"]["keywords"]) == 2
    assert report["portraitVerification"]["keptClaimCounts"]["keywords"] == 1
    assert report["portraitVerification"]["rawClaimCounts"]["keywords"] == 2
    assert report["result"]["observations"] == case["observations"]


def test_failure_has_no_retry_or_sensitive_error_output(tmp_path):
    check = load_check()

    class Model:
        calls = 0

        async def call_operation(self, *args):
            self.calls += 1
            raise RuntimeError("secret-header")

    model = Model()
    report = asyncio.run(check.run_check(model, check.prepare_case(raw_export(tmp_path))))
    assert model.calls == 1
    assert report["error"] == {"phase": "model_call", "type": "RuntimeError"}
    assert "secret-header" not in json.dumps(report)
    assert "portraitVerification" not in report


def test_invalid_schema_retains_output_and_empty_portrait_is_not_quality_success(tmp_path):
    check = load_check()
    case = check.prepare_case(raw_export(tmp_path))

    class Model:
        output = {"invalid": "result"}

        async def call_operation(self, *args):
            return ModelCallResponse(output=self.output, model_metadata={})

    model = Model()
    report = asyncio.run(check.run_check(model, case))
    assert report["error"]["phase"] == "validation"
    assert report["output"] == model.output
    model.output = {"profile": {}}
    report = asyncio.run(check.run_check(model, case))
    assert report["status"] == "completed"
    assert report["portraitVerification"]["hasVerifiedPortrait"] is False
    assert report["semanticStatus"] == "not_reviewed"


def test_live_refuses_existing_output_before_constructing_provider(tmp_path, monkeypatch, settings):
    check = load_check()
    source = raw_export(tmp_path)
    output = tmp_path / "output"
    output.mkdir()
    marker = output / "report.json"
    marker.write_text("untouched", encoding="utf-8")
    monkeypatch.setattr(
        sys, "argv", [check.__file__, str(source), "--live", "--output", str(output)]
    )
    monkeypatch.setattr(
        check.Settings, "from_environment", lambda: replace(settings, qwen_api_key="fake")
    )
    monkeypatch.setattr(
        check, "DiagnosticProfileCalls", lambda *_: pytest.fail("must not call model")
    )
    with pytest.raises(FileExistsError):
        check.main()
    assert marker.read_text(encoding="utf-8") == "untouched"


@pytest.mark.parametrize("kind,phase,status", [
    ("valid", "parsed", "completed"),
    ("blocks", "parsed", "completed"),
    ("arguments", "parsed", "completed"),
    ("length", "output_length", "failed"),
    ("json", "model_json", "failed"),
    ("schema", "output_schema", "failed"),
    ("missing_content", "content_extraction", "failed"),
    ("non_json", "response_json", "failed"),
    ("http_error", "http_status", "failed"),
    ("transport", "transport", "failed"),
])
def test_diagnostics_use_production_request_and_safe_stage_information(
    tmp_path, settings, kind, phase, status,
):
    check = load_check()
    case = check.prepare_case(raw_export(tmp_path))
    calls = []
    text = json.dumps({"profile": {"pillars": ["中文", "test-private-key"]}})

    def respond(request):
        calls.append(request)
        payload = json.loads(request.content)
        assert payload["model"] == "qwen-plus"
        assert payload["max_tokens"] == 6000
        assert payload["temperature"] == 0.3
        assert payload["response_format"] == {"type": "json_object"}
        assert request.headers["authorization"] == "Bearer test-private-key"
        if kind == "transport":
            raise httpx.ReadTimeout("secret-header-value", request=request)
        if kind == "http_error":
            return httpx.Response(429, json={"error": "secret-header-value"},
                                  headers={"x-private": "secret-header-value"})
        if kind == "non_json":
            return httpx.Response(200, text="<html>secret-header-value</html>")
        message = {"content": text}
        if kind == "blocks":
            message = {"content": [{"type": "text", "text": text}]}
        if kind == "arguments":
            message = {"content": "", "function_call": {"arguments": text}}
        if kind in {"json", "length"}:
            message = {"content": '{"profile": {"中文": "test-private-key'}
        if kind == "schema":
            message = {"content": '{"somethingElse": "test-private-key"}'}
        body = {"model": "qwen-plus", "usage": {"prompt_tokens": 123,
                "completion_tokens": 12, "total_tokens": 135, "private": "secret-header-value"},
                "choices": [{"finish_reason": "length" if kind == "length" else "stop",
                             "message": message}], "ignored": "secret-header-value"}
        if kind == "missing_content":
            body["choices"] = []
        return httpx.Response(200, json=body)

    service = check.DiagnosticProfileCalls(
        replace(settings, model_provider="qwen", qwen_model="qwen-plus",
                qwen_api_key="test-private-key", qwen_base_url="https://example.invalid/v1"),
        transport=httpx.MockTransport(respond),
    )
    report = asyncio.run(check.run_check(service, case))
    assert len(calls) == 1
    assert report["status"] == status
    diagnostic = report["responseDiagnostic"]
    assert diagnostic["phase"] == phase
    assert diagnostic["requestedMaxTokens"] == 6000
    assert "test-private-key" not in json.dumps(report)
    assert "secret-header-value" not in json.dumps(report)
    if kind == "transport":
        assert "httpStatus" not in diagnostic
    else:
        assert diagnostic["httpStatus"] == (429 if kind == "http_error" else 200)
    if kind in {"valid", "blocks", "arguments", "length", "json", "schema"}:
        if kind in {"valid", "blocks", "arguments"}:
            assert diagnostic["rawText"] == text.replace("test-private-key", "[REDACTED]")
        else:
            assert "[REDACTED]" in diagnostic["rawText"]
        assert diagnostic["providerReportedLengthLimit"] is (kind == "length")
        assert diagnostic["usage"]["total_tokens"] == 135
    else:
        assert "rawText" not in diagnostic


@pytest.mark.parametrize("failure", [None, "headers", "body"])
def test_long_request_diagnostics_distinguish_headers_body_and_parse(tmp_path, settings, failure):
    check = load_check()
    calls = []
    response_body = json.dumps({"choices": [{"message": {"content": '{"profile":{}}'}}]}).encode()

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield response_body[:10]
            if failure == "body":
                raise httpx.ReadTimeout("secret-body-error")
            yield response_body[10:]

    def respond(request):
        calls.append(request)
        if failure == "headers":
            raise httpx.ReadTimeout("secret-headers-error", request=request)
        return httpx.Response(200, stream=Stream(), headers={"x-private": "secret-header"})

    service = check.DiagnosticProfileCalls(
        replace(settings, model_provider="qwen", qwen_api_key="secret-key"),
        transport=httpx.MockTransport(respond),
    )
    report = asyncio.run(check.run_check(service, check.prepare_case(raw_export(tmp_path))))
    diagnostic = report["responseDiagnostic"]
    assert len(calls) == 1
    assert diagnostic["sizes"]["requestBodyBytes"] == len(calls[0].content)
    payload = json.loads(calls[0].content)
    prompt = "".join(item["content"] for item in payload["messages"])
    assert diagnostic["sizes"]["promptTextUtf8Bytes"] == len(prompt.encode())
    assert diagnostic["sizes"]["promptTextCharacters"] == len(prompt)
    assert diagnostic["timeoutsSeconds"] == dict(connect=90, read=90, write=90, pool=90)
    timings = diagnostic["timings"]
    assert 0 <= timings["requestPreparedMs"] <= timings["finishedMs"]
    if failure == "headers":
        assert diagnostic["waitingFor"] == "response_headers"
        assert "responseHeadersMs" not in timings
        assert "httpStatus" not in diagnostic
    else:
        assert diagnostic["httpStatus"] == 200
        assert timings["requestPreparedMs"] <= timings["responseHeadersMs"] <= timings["finishedMs"]
        if failure == "body":
            assert diagnostic["waitingFor"] == "response_body"
            assert diagnostic["phase"] == "response_body"
            assert "responseBodyMs" not in timings
            assert "rawText" not in diagnostic
        else:
            assert diagnostic["waitingFor"] is None
            assert timings["responseHeadersMs"] <= timings["responseBodyMs"] <= timings["parsedMs"]
            assert timings["parsedMs"] <= timings["finishedMs"]
            assert diagnostic["sizes"]["responseBodyBytes"] == len(response_body)
    if failure:
        assert diagnostic["failureType"] == "ReadTimeout"
    assert "secret" not in json.dumps(diagnostic)


@pytest.mark.parametrize("failed_event", [
    "connection.connect_tcp", "connection.start_tls", "proxy.start_tls",
    "http11.send_request_body", "http11.receive_response_headers",
    "http2.receive_response_headers",
])
def test_network_trace_records_stage_without_private_details(tmp_path, settings, failed_event):
    check = load_check()
    attempts = []
    error_type = (httpx.ConnectTimeout if failed_event.startswith(("connection.", "proxy."))
                  else httpx.WriteTimeout if ".send_" in failed_event else httpx.ReadTimeout)
    preceding = (["http11.send_request_body.complete"]
                 if failed_event == "http11.receive_response_headers" else [])

    async def respond(request):
        attempts.append(request)
        trace = request.extensions["trace"]
        private = {"host": "private-host", "headers": {"Authorization": "private-key"},
                   "exception": error_type("private-error"), "return_value": object()}
        for event in preceding:
            await trace(event, private)
        await trace(f"{failed_event}.started", private)
        await trace(f"{failed_event}.failed", private)
        raise error_type("private-error", request=request)

    service = check.DiagnosticProfileCalls(
        replace(settings, model_provider="qwen", qwen_api_key="private-key"),
        transport=httpx.MockTransport(respond),
    )
    report = asyncio.run(check.run_check(service, check.prepare_case(raw_export(tmp_path))))
    diagnostic = report["responseDiagnostic"]
    assert report["status"] == "failed"
    assert len(attempts) == 1
    assert diagnostic["failureType"] == error_type.__name__
    assert [item["event"] for item in diagnostic["networkEvents"]] == preceding + [
        f"{failed_event}.started", f"{failed_event}.failed",
    ]
    assert all(set(item) == {"event", "elapsedMs"} for item in diagnostic["networkEvents"])
    assert 0 <= diagnostic["networkEvents"][0]["elapsedMs"] <= (
        diagnostic["networkEvents"][1]["elapsedMs"]
    ) <= diagnostic["timings"]["finishedMs"]
    assert "private" not in json.dumps(diagnostic)


def test_network_trace_is_allowlisted_bounded_and_reset_between_calls(settings):
    check = load_check()

    async def respond(request):
        trace = request.extensions["trace"]
        for event in ("private.secret.started", "http11.send_request_body.private",
                      "http11.private.started", "http11.send_request_body.started.extra"):
            await trace(event, {"private": object()})
        for _ in range(150):
            await trace("http11.send_request_body.complete", {"private": object()})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"profile":{}}'}}]})

    service = check.DiagnosticProfileCalls(
        replace(settings, model_provider="qwen", qwen_api_key="private-key"),
        transport=httpx.MockTransport(respond),
    )
    for _ in range(2):
        asyncio.run(service.call_operation(ModelOperation.PROFILE, {}))
        assert len(service.diagnostic["networkEvents"]) == 128
        assert service.diagnostic["networkEventsTruncated"] is True
        assert service.diagnostic["phase"] == "parsed"
        assert "private" not in json.dumps(service.diagnostic)


def test_network_trace_runs_through_real_local_http_transport(settings):
    check = load_check()

    async def exercise():
        requests = []
        handlers = set()

        async def respond(reader, writer):
            task = asyncio.current_task()
            handlers.add(task)
            try:
                headers = await reader.readuntil(b"\r\n\r\n")
                size = next(int(line.split(b":", 1)[1]) for line in headers.split(b"\r\n")
                            if line.lower().startswith(b"content-length:"))
                requests.append(await reader.readexactly(size))
                body = json.dumps({"choices": [{"message": {"content": '{"profile":{}}'}}]})
                body = body.encode()
                writer.write(b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                             + f"Content-Length: {len(body)}\r\n".encode()
                             + b"Connection: close\r\n\r\n" + body)
                await writer.drain()
            finally:
                writer.close()
                await writer.wait_closed()
                handlers.discard(task)

        server = await asyncio.start_server(respond, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        try:
            service = check.DiagnosticProfileCalls(
                replace(settings, model_provider="qwen", qwen_api_key="private-key",
                        qwen_base_url=f"http://127.0.0.1:{port}"),
                transport=httpx.AsyncHTTPTransport(retries=0),
            )
            await asyncio.wait_for(service.call_operation(ModelOperation.PROFILE, {}), 5)
            events = [item["event"] for item in service.diagnostic["networkEvents"]]
            assert events == [f"{name}.{status}" for name in (
                "connection.connect_tcp", "http11.send_request_headers",
                "http11.send_request_body", "http11.receive_response_headers",
                "http11.receive_response_body",
            ) for status in ("started", "complete")]
            assert len(requests) == 1
            assert service.diagnostic["phase"] == "parsed"
            assert "private" not in json.dumps(service.diagnostic)
        finally:
            server.close()
            await server.wait_closed()
            if handlers:
                await asyncio.gather(*handlers)

    asyncio.run(exercise())


def test_diagnostic_read_timeout_changes_only_local_read_limit(settings):
    check = load_check()
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"profile":{}}'}}]})

    service = check.DiagnosticProfileCalls(
        replace(settings, model_provider="qwen", qwen_api_key="placeholder"),
        read_timeout_seconds=180, transport=httpx.MockTransport(respond),
    )
    asyncio.run(service.call_operation(ModelOperation.PROFILE, {}))
    assert len(requests) == 1
    assert requests[0].extensions["timeout"] == dict(connect=90, read=180, write=90, pool=90)
    assert service.diagnostic["timeoutsSeconds"] == requests[0].extensions["timeout"]
    assert check.DiagnosticProfileCalls(settings).read_timeout_seconds == 90


@pytest.mark.parametrize("value", [0, -1, 301, True, 1.5, float("nan"), float("inf")])
def test_diagnostic_read_timeout_rejects_unbounded_values(settings, value):
    with pytest.raises(ValueError, match="1 to 300"):
        load_check().DiagnosticProfileCalls(settings, read_timeout_seconds=value)


@pytest.mark.parametrize("value", ["0", "301", "nan", "1.5"])
def test_cli_rejects_invalid_timeout_before_loading_settings(monkeypatch, value):
    check = load_check()
    monkeypatch.setattr(check.Settings, "from_environment", lambda: pytest.fail("no credentials"))
    monkeypatch.setattr(sys, "argv", [check.__file__, "--read-timeout-seconds", value])
    with pytest.raises(SystemExit) as error:
        check.main()
    assert error.value.code == 2


def test_diagnostics_redact_before_clipping_and_reject_non_qwen(settings):
    check = load_check()
    service = check.DiagnosticProfileCalls(replace(settings, qwen_api_key="private-api-key"))
    text = "中" * 99_997 + "private-api-key" + "尾部" * 20
    assert service._extract_openai_compatible_text({"choices": [
        {"message": {"content": text}},
    ]}) == text
    assert service.diagnostic["rawTextClipped"] is True
    assert len(service.diagnostic["rawText"]) == 100_000
    assert "pri" not in service.diagnostic["rawText"]
    assert service.redact("Bearer another-token") == "Bearer [REDACTED]"
    with pytest.raises(ValueError, match="only support"):
        asyncio.run(service.call_operation(ModelOperation.PROFILE, {}))


@pytest.mark.parametrize("replay", [False, True])
def test_diagnostic_cli_prints_only_summary(tmp_path, monkeypatch, settings, capsys, replay):
    check = load_check()
    source = raw_export(tmp_path)
    output = tmp_path / "report"
    private_text = '{"profile": {"pillars": ["private-api-key", "私有正文"]}}'
    cls = check.DiagnosticProfileCalls
    configured = replace(settings, qwen_api_key="private-api-key", model_provider="qwen")
    monkeypatch.setattr(check.Settings, "from_environment", lambda: configured)
    inputs = [str(source)]
    case = check.prepare_case(source)
    if replay:
        previous = tmp_path / "previous.json"
        previous.write_text(json.dumps(case, ensure_ascii=False), encoding="utf-8")
        inputs = ["--input-from", str(previous)]
    monkeypatch.setattr(
        sys, "argv", [check.__file__, *inputs, "--live", "--output", str(output),
                      "--read-timeout-seconds", "180"]
    )
    # Patch the client factory, not the diagnostic class (run_check uses isinstance).
    def client(self, operation):
        assert operation == ModelOperation.PROFILE
        assert self.read_timeout_seconds == 180
        return httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json={
                "model": "qwen-plus", "choices": [{"finish_reason": "stop",
                                                    "message": {"content": private_text}}],
            })), event_hooks={"response": [self._record_response]},
        )
    monkeypatch.setattr(cls, "_qwen_client", client)
    assert check.main() == 0
    stdout = capsys.readouterr().out
    assert "private-api-key" not in stdout
    assert "私有正文" not in stdout
    assert "rawText" not in stdout
    saved = (output / "report.json").read_text(encoding="utf-8")
    assert "私有正文" in saved
    assert "private-api-key" not in saved
    assert json.loads(saved)["responseDiagnostic"]["phase"] == "parsed"
    if replay:
        report = json.loads(saved)
        assert report["inputSource"]["type"] == "previous_profile_report"
        assert report["context"] == case["context"]
        assert report["snapshot"] == case["snapshot"]
        assert report["requestAttempts"] == 1
