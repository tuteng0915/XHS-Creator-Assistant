import asyncio
import importlib.util
import json
import sqlite3
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from test_audience_analysis_check import raw_export

from app.db.database import SQLiteDatabase
from app.models import ModelCallResponse, ModelOperation
from app.repositories.analysis_runs import AnalysisRunRepository
from app.services.account_diagnosis_evidence import build_account_observations, profile_stage_input
from app.services.account_report_prompt import (
    LEGACY_PROFILE_PROMPT_VERSION,
    PROFILE_PROMPT_VERSION,
    SOURCE_LED_PROFILE_PROMPT,
)
from app.services.model_calls import PROMPT_PROFILE


def load_check():
    path = Path(__file__).resolve().parents[2] / "scripts/check_account_profile.py"
    spec = importlib.util.spec_from_file_location("account_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def legacy_transport_case(check, source):
    case = check.prepare_case(source)
    case["context"] = {"positioning": "旧纯文本定位", "historicalPosts": "旧纯文本笔记输入"}
    return case


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
def test_shared_input_uses_structured_notes_and_observations_without_mutating_snapshot(comparable):
    notes = [{"noteId": str(i), "publishedAt": f"2026-{i+1:02d}-01T00:00:00Z"}
             for i in range(6 if comparable else 2)]
    snapshot = {"accountPositioning": "中文定位", "historicalPosts": {"content": "逐字历史\n"},
                "xhsCreatorProfile": {"notes": notes}}
    original = deepcopy(snapshot)
    observations = build_account_observations(snapshot, "2026-10-03")
    context, actual = profile_stage_input(snapshot, "2026-10-03")
    packet = json.loads(context["historicalPosts"])
    assert context["positioning"] == "所选笔记的账号报告"
    assert packet["schemaVersion"] == "account-reading-input/v2"
    assert [item["noteId"] for item in packet["notes"]] == [item["noteId"] for item in notes]
    assert packet["chronology"] == observations["chronology"]
    assert packet["metricSummaries"] == observations["metricSummaries"]
    assert "逐字历史" not in context["historicalPosts"]
    assert actual == observations
    assert snapshot == original


def test_shared_input_keeps_text_only_legacy_path():
    snapshot = {"accountPositioning": "中文定位", "historicalPosts": {"content": "逐字历史\n"}}
    context, observations = profile_stage_input(snapshot, "2026-10-03")
    assert context == {"positioning": "中文定位", "historicalPosts": "逐字历史\n"}
    assert observations is None


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
    assert report["status"] == "failed"
    assert report["error"]["phase"] == "validation"
    assert report["output"] == model.output
    assert "result" not in report
    assert "portraitVerification" not in report


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
    case = legacy_transport_case(check, raw_export(tmp_path))
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
        replace(settings, model_provider="qwen", qwen_model="qwen-plus", qwen_profile_model="",
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
    case = legacy_transport_case(check, raw_export(tmp_path))
    report = asyncio.run(check.run_check(service, case))
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
    service = check.DiagnosticProfileCalls(
        replace(
            settings,
            model_provider="anthropic",
            qwen_api_key="private-api-key",
        )
    )
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


@pytest.mark.parametrize("replay", [False, True, "legacy_text"])
def test_diagnostic_cli_prints_only_summary(tmp_path, monkeypatch, settings, capsys, replay):
    check = load_check()
    source = raw_export(tmp_path)
    output = tmp_path / "report"
    private_text = '{"profile": {"pillars": ["private-api-key", "私有正文"]}}'
    cls = check.DiagnosticProfileCalls
    requests = []
    configured = replace(settings, qwen_api_key="private-api-key", model_provider="qwen")
    monkeypatch.setattr(check.Settings, "from_environment", lambda: configured)
    inputs = [str(source)]
    case = check.prepare_case(source)
    if replay == "legacy_text":
        case["context"] = {"positioning": "旧纯文本定位", "historicalPosts": "旧纯文本笔记输入"}
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
        def respond(request):
            requests.append(request)
            payload = json.loads(request.content)
            assert payload["messages"][0]["content"] == (
                PROMPT_PROFILE if replay == "legacy_text" else SOURCE_LED_PROFILE_PROMPT
            )
            return httpx.Response(200, json={
                "model": "qwen-plus", "choices": [{"finish_reason": "stop",
                                                    "message": {"content": private_text}}],
            })
        return httpx.AsyncClient(
            transport=httpx.MockTransport(respond),
            event_hooks={"response": [self._record_response]},
        )
    monkeypatch.setattr(cls, "_qwen_client", client)
    assert check.main() == 0
    stdout = capsys.readouterr().out
    assert "private-api-key" not in stdout
    assert "私有正文" not in stdout
    assert "rawText" not in stdout
    expected_attempts = 1
    assert len(requests) == json.loads(stdout)["requestAttempts"] == expected_attempts
    saved = (output / "report.json").read_text(encoding="utf-8")
    assert "私有正文" in saved
    assert "private-api-key" not in saved
    parsed = json.loads(saved)
    assert parsed["responseDiagnostic"]["phase"] == "parsed"
    assert parsed["requestAttempts"] == expected_attempts
    assert parsed["promptVersion"] == (
        LEGACY_PROFILE_PROMPT_VERSION if replay == "legacy_text" else PROFILE_PROMPT_VERSION
    )
    assert parsed["promptVersion"] == check.profile_prompt_version(case["context"])
    if replay:
        report = json.loads(saved)
        assert report["inputSource"]["type"] == "previous_profile_report"
        assert report["context"] == case["context"]
        assert report["snapshot"] == case["snapshot"]
        assert report["requestAttempts"] == expected_attempts


def saved_workspace_database(tmp_path, *, notes=None):
    database = tmp_path / "saved.sqlite3"
    # Use production migrations so a fake fixture schema cannot hide SQL mistakes.
    SQLiteDatabase(database).migrate()
    profile = {
        "creator": {"nickname": "已保存账号", "profileText": "不能混入的全账号归纳"},
        "source": {"importedAt": "2026-10-09T10:00:00Z"},
        "notes": notes if notes is not None else [
            {"noteId": f"saved-{i}", "title": f"私有标题{i}", "desc": f"私有正文{i}",
             "publishedAt": f"2026-10-{i + 1:02d}T00:00:00Z",
             "metrics": {"liked": i, "collected": 0, "comments": None, "shares": 1}}
            for i in range(7)
        ],
    }
    with sqlite3.connect(database) as connection:
        connection.executemany(
            "INSERT INTO creator_workspaces(id,name,created_at,updated_at) VALUES (?,?,?,?)",
            [(item, item, "2026-10-01", "2026-10-01") for item in ("current", "other", "empty")],
        )
        for item_id, owner, kind, content, updated in [
            ("old", "current", "xhs_creator_profile", {"notes": [
                {"noteId": "old-only", "title": "不读取旧资料", "desc": "旧资料正文"},
            ]}, "2026-10-01"),
            ("current-profile", "current", "xhs_creator_profile", profile, "2026-10-09"),
            ("not-profile", "current", "historical_posts", {"private": "不读取别的资料"},
             "2026-10-10"),
            ("foreign-profile", "other", "xhs_creator_profile", {"notes": [
                {"noteId": "foreign-only", "title": "不读取别的账号", "desc": "跨账号正文"},
            ]}, "2026-10-11"),
        ]:
            connection.execute("INSERT INTO source_materials "
                               "(id,workspace_id,type,name,text_content,created_at,updated_at) "
                               "VALUES (?,?,?,?,?,?,?)", (
                item_id, owner, kind, item_id, json.dumps(content, ensure_ascii=False),
                updated, updated,
            ))
    return database, profile


def test_workspace_default_selects_recent_five_and_freezes_only_that_subset(tmp_path):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    before = database.read_bytes()
    case = check.prepare_workspace_case(database, "current")
    selected = [f"saved-{i}" for i in range(6, 1, -1)]
    assert case["snapshot"]["analysisRange"]["selectedNoteIds"] == selected
    assert case["observations"]["coverage"]["selectedNoteIds"] == selected
    assert case["observations"]["coverage"]["selectedCount"] == 5
    assert case["observations"]["coverage"]["availableCount"] == 7
    assert case["inputSource"] == {
        "type": "saved_workspace_notes", "workspaceId": "current",
        "sourceMaterialId": "current-profile", "selectedNoteIds": selected,
    }
    encoded = json.dumps(case, ensure_ascii=False)
    for absent in ("私有正文0", "私有正文1", "旧资料正文", "跨账号正文", "不能混入的全账号归纳"):
        assert absent not in encoded
    assert "私有正文6" in case["context"]["historicalPosts"]
    assert database.read_bytes() == before


def test_workspace_explicit_ids_do_not_get_clipped_by_default_limit(tmp_path):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    ids = [f"saved-{i}" for i in range(6)]
    case = check.prepare_workspace_case(database, "current", note_ids=ids)
    assert case["snapshot"]["analysisRange"]["selectedNoteIds"] == ids
    assert case["snapshot"]["analysisRange"]["selectionMethod"] == "explicit_ids"
    assert "私有正文6" not in json.dumps(case, ensure_ascii=False)
    assert len(check.prepare_workspace_case(database, "current", limit=50)[
        "snapshot"
    ]["xhsCreatorProfile"]["notes"]) == 7


@pytest.mark.parametrize("ids", [[], ["missing"], ["foreign-only"], ["old-only"],
                                     ["saved-0", "saved-0"], [""], [" saved-0"]])
def test_workspace_rejects_invalid_noncurrent_or_duplicate_requested_ids(tmp_path, ids):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    with pytest.raises(ValueError):
        check.prepare_workspace_case(database, "current", note_ids=ids)


@pytest.mark.parametrize("notes", [[], [{"title": "没有 ID", "desc": "不补索引"}],
    [{"noteId": "same", "desc": "一"}, {"noteId": "same", "desc": "二"}],
    [{"noteId": 1, "desc": "不字符串转换"}]])
def test_workspace_rejects_empty_or_ambiguous_saved_note_identities(tmp_path, notes):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path, notes=notes)
    with pytest.raises(ValueError):
        check.prepare_workspace_case(database, "current")


@pytest.mark.parametrize("workspace", ["missing", "empty", " "])
def test_workspace_requires_existing_account_with_saved_notes(tmp_path, workspace):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    with pytest.raises(ValueError):
        check.prepare_workspace_case(database, workspace)


def test_workspace_open_is_actually_readonly_and_missing_database_is_not_created(
    tmp_path, monkeypatch,
):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    original_connect = sqlite3.connect
    observed = []

    def readonly_connect(database_uri, **kwargs):
        assert database_uri.endswith("?mode=ro")
        assert kwargs == {"uri": True}
        connection = original_connect(database_uri, **kwargs)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("UPDATE creator_workspaces SET name='mutated'")
        connection.rollback()
        connection.set_trace_callback(observed.append)
        return connection

    monkeypatch.setattr(check.sqlite3, "connect", readonly_connect)
    check.prepare_workspace_case(database, "current", limit=2)
    assert all(sql.startswith(("BEGIN", "SELECT")) for sql in observed)
    missing = tmp_path / "not-created.sqlite3"
    with pytest.raises(FileNotFoundError):
        check.prepare_workspace_case(missing, "current")
    assert not missing.exists()


@pytest.mark.parametrize("explicit_database", [False, True])
def test_workspace_preview_prints_only_safe_summary_and_creates_nothing(
    tmp_path, monkeypatch, settings, capsys, explicit_database,
):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    output = tmp_path / "unused-output"
    argv = [check.__file__, "--workspace-id", "current", "--output", str(output)]
    if explicit_database:
        argv.extend(["--database", str(database)])
        monkeypatch.setattr(check.Settings, "from_environment", lambda: pytest.fail("explicit DB"))
    else:
        monkeypatch.setattr(check.Settings, "from_environment", lambda: replace(
            settings, database_path=database, qwen_api_key="must-not-print-key",
        ))
    monkeypatch.setattr(check, "DiagnosticProfileCalls", lambda *a, **kw: pytest.fail("no model"))
    monkeypatch.setattr(sys, "argv", argv)
    before = database.read_bytes()
    assert check.main() == 0
    stdout = capsys.readouterr().out
    assert "私有" not in stdout and "must-not-print-key" not in stdout
    assert json.loads(stdout)["requestAttempts"] == 0
    assert len(json.loads(stdout)["selection"]["selectedNoteIds"]) == 5
    assert not output.exists()
    assert database.read_bytes() == before


@pytest.mark.parametrize("arguments", [
    ["source", "--workspace-id", "current"],
    ["--input-from", "old.json", "--workspace-id", "current"],
    ["source", "--database", "some.sqlite3"],
    ["source", "--note-ids", "saved-0"],
    ["source", "--limit", "2"],
    ["--workspace-id", "current", "--limit", "0"],
    ["--workspace-id", "current", "--limit", "51"],
    ["--workspace-id", "current", "--limit", "2", "--note-ids", "saved-0"],
    ["--workspace-id", "current", "--live", "--output", "/tmp/not-ignored-output"],
])
def test_workspace_cli_rejects_ambiguous_or_unsafe_options_before_reading(
    monkeypatch, arguments,
):
    check = load_check()
    monkeypatch.setattr(check.Settings, "from_environment", lambda: pytest.fail("no config"))
    monkeypatch.setattr(check, "prepare_workspace_case", lambda *a, **kw: pytest.fail("no read"))
    monkeypatch.setattr(sys, "argv", [check.__file__, *arguments])
    with pytest.raises(SystemExit) as error:
        check.main()
    assert error.value.code == 2


@pytest.mark.parametrize("profile_model,expected_model", [
    (None, "qwen3.8-max"), ("", "qwen-plus"), ("qwen3.8-max", "qwen3.8-max"),
])
def test_workspace_live_uses_one_qwen_request_and_preserves_database(
    tmp_path, monkeypatch, settings, capsys, profile_model, expected_model,
):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    monkeypatch.setattr(check, "ROOT", tmp_path)
    output = tmp_path / "data/evals/workspace-check"
    requests = []
    configured = replace(settings, qwen_api_key="private-key", model_provider="qwen")
    if profile_model is not None:
        configured = replace(configured, qwen_profile_model=profile_model)
    monkeypatch.setattr(check.Settings, "from_environment", lambda: configured)
    monkeypatch.setattr(sys, "argv", [
        check.__file__, "--workspace-id", "current", "--database", str(database),
        "--note-ids", "saved-0,saved-6", "--live", "--output", str(output),
    ])

    def client(self, operation):
        def respond(request):
            requests.append(request)
            payload = json.loads(request.content)
            assert payload["model"] == expected_model
            if expected_model.startswith("qwen3.8"):
                assert payload["enable_thinking"] is False
            else:
                assert "enable_thinking" not in payload
            return httpx.Response(200, json={"model": "qwen-plus", "choices": [{
                "finish_reason": "stop", "message": {"content": json.dumps({
                    "profile": {"hookStyles": ["先给出具体场景，再展开观察。"]},
                })},
            }]})
        return httpx.AsyncClient(transport=httpx.MockTransport(respond), event_hooks={
            "request": [self._record_request], "response": [self._record_response],
        })

    monkeypatch.setattr(check.DiagnosticProfileCalls, "_qwen_client", client)
    before = database.read_bytes()
    assert check.main() == 0
    assert len(requests) == 1
    assert database.read_bytes() == before
    stdout = capsys.readouterr().out
    assert "私有" not in stdout and "private-key" not in stdout
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["inputSource"]["selectedNoteIds"] == ["saved-0", "saved-6"]
    assert report["requestAttempts"] == 1
    assert report["configuredModel"] == expected_model
    assert report["promptVersion"] == check.profile_prompt_version(report["context"])
    assert len(report["promptHash"]) == len(report["inputHash"]) == 64
    assert report["responseDiagnostic"]["phase"] == "parsed"
    encoded = json.dumps(report["context"], ensure_ascii=False)
    assert "私有正文0" in encoded and "私有正文6" in encoded and "私有正文1" not in encoded
    assert "private-key" not in json.dumps(report)


def saved_analysis_history(database, *, snapshot=None, workflow="account_diagnosis"):
    if snapshot is None:
        snapshot = {
            "accountPositioning": "旧定位不代替当前结构化输入",
            "historicalPosts": {"content": "旧版派生短文本不能代替完整正文"},
            "xhsCreatorProfile": {"creator": {"displayName": "历史账号"}, "notes": [
                {"noteId": "frozen-b", "title": "冻结标题乙", "desc": "完整正文乙" * 1_000,
                 "publishedAt": "2026-09-01T00:00:00Z", "metrics": {"liked": 5}},
                {"noteId": "frozen-a", "title": "冻结标题甲", "desc": "冻结正文甲",
                 "publishedAt": "2026-09-20T00:00:00Z", "metrics": {"liked": 2}},
            ]},
            "analysisRange": {"selectedNoteIds": ["frozen-b", "frozen-a"],
                              "selectedNoteCount": 2, "availableNoteCount": 7},
        }
    with sqlite3.connect(database) as connection:
        connection.row_factory = sqlite3.Row
        run = AnalysisRunRepository().create(
            connection, workspace_id="current", workflow_type=workflow,
            input_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
            idempotency_key=None, now="2026-09-21T00:00:00Z",
        )
        connection.execute(
            "UPDATE analysis_runs SET status='completed',stage_results_json=? WHERE id=?",
            (json.dumps({"profile": {"mustNotRead": "既往结论不能成为新输入"}}), run["id"]),
        )
    return run["id"], snapshot


def test_analysis_run_uses_exact_frozen_notes_full_text_order_and_current_input_builder(
    tmp_path, monkeypatch,
):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    run_id, original = saved_analysis_history(database)
    before = database.read_bytes()
    observed = []
    original_connect = sqlite3.connect

    def readonly_connect(database_uri, **kwargs):
        assert database_uri.endswith("?mode=ro") and kwargs == {"uri": True}
        connection = original_connect(database_uri, **kwargs)
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            connection.execute("UPDATE analysis_runs SET status='failed'")
        connection.rollback()
        connection.set_trace_callback(observed.append)
        return connection

    monkeypatch.setattr(check.sqlite3, "connect", readonly_connect)
    case = check.prepare_analysis_run_case(database, run_id)
    assert case["snapshot"] == original
    assert case["context"] == profile_stage_input(original, "2026-09-21T00:00:00Z")[0]
    packet = json.loads(case["context"]["historicalPosts"])
    assert [note["noteId"] for note in packet["notes"]] == ["frozen-b", "frozen-a"]
    assert packet["notes"][0]["body"] == "完整正文乙" * 1_000
    assert case["observations"]["coverage"]["snapshotAt"] == "2026-09-21T00:00:00Z"
    assert case["inputSource"] == {
        "type": "analysis_run_snapshot", "runId": run_id, "workspaceId": "current",
        "selectedNoteIds": ["frozen-b", "frozen-a"],
    }
    assert all(sql.startswith("SELECT") for sql in observed)
    assert all("source_materials" not in sql and "stage_results_json" not in sql
               for sql in observed)
    assert "私有正文" not in json.dumps(case, ensure_ascii=False)
    assert "既往结论不能成为新输入" not in json.dumps(case, ensure_ascii=False)
    assert database.read_bytes() == before


@pytest.mark.parametrize("snapshot", [
    {}, [], {"historicalPosts": {"content": "只有文本的旧快照"}},
    {"xhsCreatorProfile": {"notes": []}}, {"xhsCreatorProfile": {"notes": ["坏笔记"]}},
    {"xhsCreatorProfile": {"notes": [{"noteId": "n"}]}},
    {"xhsCreatorProfile": {"notes": [{"desc": "没有身份"}]}},
    {"xhsCreatorProfile": {"notes": [{"noteId": "n", "desc": "正文"}, {"noteId": "n"}]}},
    {"xhsCreatorProfile": {"notes": [{"noteId": "n", "desc": "正文"}]},
     "analysisRange": {"selectedNoteIds": ["not-n"]}},
    {"xhsCreatorProfile": {"notes": [{"noteId": "n", "desc": "正文"}]},
     "analysisRange": {"selectedNoteCount": 2}},
])
def test_analysis_run_rejects_empty_unstructured_or_inconsistent_frozen_inputs(tmp_path, snapshot):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    run_id, _ = saved_analysis_history(database, snapshot=snapshot)
    with pytest.raises(ValueError):
        check.prepare_analysis_run_case(database, run_id)


@pytest.mark.parametrize("problem", ["missing", "wrong_workflow", "blank"])
def test_analysis_run_requires_exact_account_diagnosis_record(tmp_path, problem):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    run_id, _ = saved_analysis_history(database, workflow="trend_analysis")
    requested = "missing" if problem == "missing" else " " if problem == "blank" else run_id
    with pytest.raises(ValueError):
        check.prepare_analysis_run_case(database, requested)


@pytest.mark.parametrize("explicit_database", [False, True])
def test_analysis_run_preview_is_free_safe_and_does_not_create_output(
    tmp_path, monkeypatch, settings, capsys, explicit_database,
):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    run_id, _ = saved_analysis_history(database)
    output = tmp_path / "unused-history-output"
    argv = [check.__file__, "--analysis-run-id", run_id, "--output", str(output)]
    if explicit_database:
        argv.extend(["--database", str(database)])
        monkeypatch.setattr(check.Settings, "from_environment", lambda: pytest.fail("explicit DB"))
    else:
        monkeypatch.setattr(check.Settings, "from_environment", lambda: replace(
            settings, database_path=database, qwen_api_key="must-not-print-key",
        ))
    monkeypatch.setattr(check, "DiagnosticProfileCalls", lambda *a, **kw: pytest.fail("no model"))
    monkeypatch.setattr(sys, "argv", argv)
    assert check.main() == 0
    stdout = capsys.readouterr().out
    assert all(value not in stdout for value in ("完整正文", "冻结标题", "must-not-print-key"))
    assert json.loads(stdout)["requestAttempts"] == 0
    assert json.loads(stdout)["selection"]["runId"] == run_id
    assert not output.exists()


@pytest.mark.parametrize("arguments", [
    ["source", "--analysis-run-id", "run"],
    ["--input-from", "previous.json", "--analysis-run-id", "run"],
    ["--workspace-id", "current", "--analysis-run-id", "run"],
    ["--analysis-run-id", "run", "--note-ids", "n1"],
    ["--analysis-run-id", "run", "--limit", "1"],
    ["--analysis-run-id", "run", "--live", "--output", "/tmp/not-ignored-history"],
])
def test_analysis_run_options_cannot_mix_or_change_frozen_scope(monkeypatch, arguments):
    check = load_check()
    monkeypatch.setattr(check.Settings, "from_environment", lambda: pytest.fail("no config"))
    monkeypatch.setattr(check, "prepare_analysis_run_case", lambda *a, **kw: pytest.fail("no read"))
    monkeypatch.setattr(sys, "argv", [check.__file__, *arguments])
    with pytest.raises(SystemExit) as error:
        check.main()
    assert error.value.code == 2


def test_analysis_run_live_calls_current_qwen_once_and_keeps_history_unchanged(
    tmp_path, monkeypatch, settings,
):
    check = load_check()
    database, _ = saved_workspace_database(tmp_path)
    run_id, original = saved_analysis_history(database)
    monkeypatch.setattr(check, "ROOT", tmp_path)
    monkeypatch.setattr(check.Settings, "from_environment", lambda: replace(
        settings, database_path=database, qwen_api_key="private-key",
    ))
    output = tmp_path / "data/evals/history-check"
    monkeypatch.setattr(sys, "argv", [check.__file__, "--analysis-run-id", run_id,
                                     "--live", "--output", str(output)])
    requests = []

    def client(self, operation):
        def respond(request):
            requests.append(request)
            return httpx.Response(200, json={"model": "qwen-plus", "choices": [{
                "finish_reason": "stop", "message": {"content": json.dumps({
                    "profile": {"voiceFingerprint": ["以短句交代观察，再用长句解释。"]},
                })},
            }]})
        return httpx.AsyncClient(transport=httpx.MockTransport(respond), event_hooks={
            "request": [self._record_request], "response": [self._record_response],
        })

    monkeypatch.setattr(check.DiagnosticProfileCalls, "_qwen_client", client)
    before = database.read_bytes()
    assert check.main() == 0
    assert len(requests) == 1 and database.read_bytes() == before
    report = json.loads((output / "report.json").read_text(encoding="utf-8"))
    assert report["snapshot"] == original
    assert report["inputSource"]["runId"] == run_id
    assert report["inputSource"]["workspaceId"] == "current"
    assert report["requestAttempts"] == 1
    assert report["promptVersion"] == check.profile_prompt_version(report["context"])


def source_led_model_output():
    """Shared synthetic response for check-script/production entry-point parity."""
    return {"profile": {
        "reportFormat": "source-led/v1",
        "titleReadings": [{
            "noteId": "11", "move": "两段分别指认标题内容", "parts": [
                {"text": "真实", "role": "前段"}, {"text": "标题", "role": "后段"},
            ],
        }],
        "nextMoves": [{
            "sourceNoteId": "11", "sourceQuote": "先准备材料",
            "basis": "先写准备动作", "action": "下次写操作分享时，按实际先后排列动作",
        }],
        "pillars": ["操作分享"],
    }}


def expected_source_led_display():
    return (
        [{"formula": "两段分别指认标题内容：真实（前段）→标题（后段）", "examples": ["真实标题"]}],
        ["参考《真实标题》：先写准备动作。下一篇可尝试：下次写操作分享时，按实际先后排列动作。"],
    )


@pytest.mark.parametrize("legacy", [False, True])
def test_check_compiles_new_editorial_output_but_preserves_raw_and_legacy_fields(tmp_path, legacy):
    check = load_check()
    case = check.prepare_case(raw_export(tmp_path))
    formulas, takeaways = expected_source_led_display()
    output = ({"profile": {"titleFormulas": formulas, "contrast": {"takeaways": takeaways}}}
              if legacy else source_led_model_output())
    before = deepcopy(output)

    class Model:
        calls = 0

        async def call_operation(self, operation, context):
            self.calls += 1
            assert operation == ModelOperation.PROFILE and context == case["context"]
            return ModelCallResponse(output=output, model_metadata={"model": "fake"})

    model = Model()
    report = asyncio.run(check.run_check(model, case))
    assert model.calls == 1 and report["status"] == "completed"
    assert report["output"] == output == before
    profile = report["result"]["profile"]
    assert profile["titleFormulas"] == formulas
    assert profile["contrast"]["takeaways"] == takeaways
    assert not {"reportFormat", "titleReadings", "nextMoves"} & profile.keys()


@pytest.mark.parametrize("problem", ["title_fragment", "wrong_source", "body_quote"])
def test_check_invalid_editorial_sources_fail_validation_without_completed_result(
    tmp_path, problem,
):
    check = load_check()
    case = check.prepare_case(raw_export(tmp_path))
    output = source_led_model_output()
    if problem == "title_fragment":
        output["profile"]["titleReadings"][0]["parts"][0]["text"] = "不在标题里的新增成分"
    elif problem == "wrong_source":
        output["profile"]["titleReadings"][0]["noteId"] = "outside-selection"
    else:
        output["profile"]["nextMoves"][0]["sourceQuote"] = "不在正文里的新增引用"
    before = deepcopy(output)

    class Model:
        calls = 0

        async def call_operation(self, *args):
            self.calls += 1
            return ModelCallResponse(output=output, model_metadata={"model": "fake"})

    model = Model()
    report = asyncio.run(check.run_check(model, case))
    assert model.calls == 1
    assert report["status"] == "failed" and report["error"]["phase"] == "validation"
    assert "result" not in report and "portraitVerification" not in report
    assert report["output"] == output == before
