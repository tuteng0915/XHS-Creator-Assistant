import asyncio
import importlib.util
import json
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from app.services.account_report_pipeline import DEFAULT_READING_QUESTION


def load_check():
    path = Path(__file__).resolve().parents[2] / "scripts/check_staged_account_report.py"
    spec = importlib.util.spec_from_file_location("staged_account_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def frozen_case():
    notes = [
        {"noteId": "stable-a", "title": "甲篇", "body": "先确认费用。\n再决定。"},
        {"noteId": "stable-b", "title": "乙篇", "body": "这里是下一篇的预告。"},
        {"noteId": "stable-c", "title": "丙篇", "body": "另一种内容方向。"},
    ]
    return {
        "snapshot": {"xhsCreatorProfile": {"notes": [
            {"noteId": note["noteId"], "title": note["title"], "desc": note["body"]}
            for note in notes
        ]}},
        "context": {"positioning": "冻结的账号介绍", "historicalPosts": json.dumps({
            "schemaVersion": "account-reading-input/v2", "notes": notes,
        }, ensure_ascii=False)},
        "observations": {"coverage": {"selectedCount": len(notes)}},
    }


def stage_output(payload):
    if "account" in payload:
        return {
            "summary": {"text": "这些作品关心具体条件下如何作出判断。", "noteIds": ["n1"]},
            "directions": [{"text": "从日常经验中整理具体判断", "noteIds": ["n1", "n2"]}],
            "hypotheses": ["确认不同条件如何影响判断"],
            "readings": [{"noteId": note_id, "question": f"这篇如何说明判断？（{note_id}）"}
                         for note_id in payload.get("representativeNoteIds", ["n2", "n1"])],
        }
    if "note" in payload:
        return {"assessment": payload["note"]["title"] + "的实际表达。",
                "correction": "", "examples": [{
                    "excerptIds": [item["excerptId"]
                                   for item in payload["note"]["bodyExcerpts"][:2]] or ["t"],
                    "interpretation": "按原文次序组织文字，让表达有清楚的落点。",
                }]}
    return {"profile": {
        "reportFormat": "source-led/v3",
        "accountPortrait": {"summary": {
            "statement": "从具体问题出发。",
            "evidence": [{"noteId": "n1", "excerptId": "b1"}],
        }, "keywords": [], "recurringThemes": [], "strengths": []},
        "titleReadings": [{"noteId": "n1", "parts": [
            {"text": "甲篇", "role": "点明题材"},
        ]}],
        "expressionReadings": [{
            "kind": "wording", "technique": "先交代条件再行动", "application": "用于决策经验",
            "examples": [{"noteId": "n1", "fromExcerptId": "b1", "toExcerptId": "b2"}],
        }],
        "structureReading": {"noteId": "n1", "kind": "narrative", "scope": "whole_note",
            "scopeLabel": "", "overview": "从条件走向决定", "units": [
                {"label": "条件", "reading": "确认费用", "excerptIds": ["b1"]},
                {"label": "行动", "reading": "作出决定", "excerptIds": ["b2"]},
            ]},
        "nextMoves": [],
    }}


def diagnostic_factory(check, settings, *, responder=None, provider="qwen"):
    services = []
    requests = []
    diagnostic_class = check.DiagnosticProfileCalls
    configured = replace(settings, model_provider=provider, qwen_api_key="test-secret-only",
                         deepseek_api_key="deepseek-test-secret", deepseek_model="deepseek-flash-test")

    def respond(request):
        user = json.loads(request.content)["messages"][1]["content"]
        payload = (check.stage_input("synthesis", user)
                   if user.startswith("账号定位：") else json.loads(user))
        requests.append(payload)
        content = stage_output(payload) if responder is None else responder(payload)
        return httpx.Response(200, json={
            "model": "deepseek-flash-test" if provider == "deepseek" else "qwen3.8-max-test", "usage": {
                "prompt_tokens": 10, "completion_tokens": 3, "total_tokens": 13,
            },
            "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(content, ensure_ascii=False),
            }}],
        })

    def factory():
        service = diagnostic_class(configured, transport=httpx.MockTransport(respond))
        services.append(service)
        return service

    return factory, services, requests


def test_free_preview_reports_model_and_scope_without_constructing_model_or_writing(
    settings, tmp_path, monkeypatch, capsys,
):
    check = load_check()
    source = tmp_path / "frozen.json"
    source.write_text(json.dumps(frozen_case()), encoding="utf-8")
    destination = tmp_path / "not-created"
    monkeypatch.setattr(check.Settings, "from_environment", lambda: settings)
    monkeypatch.setattr(check, "DiagnosticProfileCalls", lambda *a, **k: pytest.fail("no calls"))
    monkeypatch.setattr(check, "run_staged_account_report", lambda *a, **k: pytest.fail("no graph"))
    monkeypatch.setattr(sys, "argv", [
        check.__file__, "--input-from", str(source), "--read-note-ids", "n1,n3",
        "--output", str(destination),
    ])
    before = set(tmp_path.iterdir())
    assert check.main() == 0
    assert set(tmp_path.iterdir()) == before
    preview = json.loads(capsys.readouterr().out)
    assert preview["requestAttempts"] == 0
    assert preview["configuredModel"] == settings.qwen_profile_model
    assert preview["scope"]["inputNoteCount"] == 3
    assert preview["scope"]["readNoteIds"] == ["n1", "n3"]
    assert preview["scope"]["normalModelRequests"] == 4
    assert preview["scope"]["maxRecoveryRequests"] == 1
    assert preview["scope"]["maxModelRequests"] == 5
    assert not destination.exists()


def test_deepseek_preview_is_explicit_and_keeps_qwen_default(
    settings, tmp_path, monkeypatch, capsys,
):
    check = load_check()
    source = tmp_path / "frozen.json"
    source.write_text(json.dumps(frozen_case()), encoding="utf-8")
    configured = replace(settings, account_diagnosis_provider="deepseek",
                         deepseek_model="deepseek-flash-test", qwen_profile_enable_thinking=True)
    monkeypatch.setattr(check.Settings, "from_environment", lambda: configured)
    monkeypatch.setattr(check, "DiagnosticProfileCalls", lambda *a, **k: pytest.fail("no calls"))
    for arguments, expected in (([], "qwen"), (["--provider", "deepseek"], "deepseek")):
        monkeypatch.setattr(sys, "argv", [check.__file__, "--input-from", str(source), *arguments])
        assert check.main() == 0
        preview = json.loads(capsys.readouterr().out)
        assert preview["provider"] == expected
        assert preview["configuredModel"] == (
            "deepseek-flash-test" if expected == "deepseek" else configured.qwen_profile_model
        )
        assert preview["enableThinking"] is (expected == "qwen")
        assert preview["thinkingBudget"] == (4096 if expected == "qwen" else None)
        assert preview["requestAttempts"] == 0
    assert configured.model_provider == "qwen"


@pytest.mark.parametrize("options", [["--thinking", "off"], ["--thinking-budget", "2048"]])
def test_deepseek_rejects_qwen_thinking_flags_before_configuration(monkeypatch, options):
    check = load_check()
    monkeypatch.setattr(check.Settings, "from_environment", lambda: pytest.fail("preflight first"))
    monkeypatch.setattr(sys, "argv", [check.__file__, "--input-from", "frozen.json",
                                    "--provider", "deepseek", *options])
    with pytest.raises(SystemExit, match="2"):
        check.main()


@pytest.mark.parametrize("thinking,expected", [("on", True), ("off", False)])
def test_preview_thinking_override_is_local_and_does_not_call_model(
    settings, tmp_path, monkeypatch, capsys, thinking, expected,
):
    check = load_check()
    source = tmp_path / "frozen.json"
    source.write_text(json.dumps(frozen_case()), encoding="utf-8")
    monkeypatch.setattr(check.Settings, "from_environment", lambda: settings)
    monkeypatch.setattr(check, "DiagnosticProfileCalls", lambda *a, **k: pytest.fail("no calls"))
    monkeypatch.setattr(sys, "argv", [check.__file__, "--input-from", str(source),
        "--thinking", thinking, "--thinking-budget", "2048"])
    assert check.main() == 0
    preview = json.loads(capsys.readouterr().out)
    assert preview["enableThinking"] is expected
    assert preview["thinkingBudget"] == (2048 if expected else None)
    assert settings.qwen_profile_enable_thinking is False
    assert settings.qwen_profile_thinking_budget == 4096


@pytest.mark.parametrize("budget", ["0", "8193", "1.5", "invalid"])
def test_invalid_thinking_budget_is_rejected_before_configuration(monkeypatch, budget):
    check = load_check()
    monkeypatch.setattr(check.Settings, "from_environment", lambda: pytest.fail("preflight first"))
    monkeypatch.setattr(sys, "argv", [check.__file__, "--input-from", "frozen.json",
        "--thinking-budget", budget])
    with pytest.raises(SystemExit, match="2"):
        check.main()


def test_staged_report_keeps_frozen_input_diagnostics_progress_and_total_usage(settings):
    check = load_check()
    case = frozen_case()
    before = deepcopy(case)
    factory, services, requests = diagnostic_factory(check, settings)
    updates = []
    report = asyncio.run(check.run_check(factory, case, on_progress=updates.append))
    assert case == before
    assert report["status"] == "completed"
    assert report["semanticStatus"] == "not_reviewed"
    assert report["context"] == case["context"]
    assert report["snapshot"] == case["snapshot"]
    assert report["requestAttempts"] == 4
    assert len(services) == len({id(service) for service in services}) == 4
    assert report["totalUsage"] == {
        "prompt_tokens": 40, "completion_tokens": 12, "total_tokens": 52,
    }
    assert report["result"]["modelMetadata"]["representativeNoteIds"] == ["stable-b", "stable-a"]
    expected_questions = [DEFAULT_READING_QUESTION, DEFAULT_READING_QUESTION]
    assert [stage["input"]["question"] for stage in report["stages"]
            if stage["stage"] == "read"] == expected_questions
    assert all("question" not in item
               for item in report["result"]["modelMetadata"]["readingAssessments"])
    assert report["result"]["output"]["profile"]["accountPortrait"]["summary"]["statement"] \
        == "从具体问题出发。"
    assert report["validatedResult"]["profile"]["accountPortrait"]["summary"]["statement"] \
        == "从具体问题出发。"
    assert report["validatedResult"]["observations"] == case["observations"]
    verification = report["portraitVerification"]
    assert verification["rawClaimCounts"] == verification["keptClaimCounts"]
    assert verification["keptClaimCounts"]["summary"] == 1
    assert verification["droppedClaimCounts"] == {}
    assert verification["hasVerifiedPortrait"] is True
    assert [capture["stage"] for capture in report["stages"]] == [
        "overview", "read", "read", "synthesis",
    ]
    assert [capture["taskTitle"] for capture in report["stages"] if capture["stage"] == "read"] \
        == ["乙篇", "甲篇"]
    assert all("noteId" not in capture for capture in report["stages"])
    for capture, payload in zip(report["stages"], requests, strict=True):
        assert capture["input"] == payload
        assert len(capture["systemPromptHash"]) == len(capture["inputHash"]) == 64
        assert capture["responseDiagnostic"]["phase"] == "parsed"
        assert capture["responseDiagnostic"]["rawText"]
        assert capture["requestAttempts"] == 1
        assert capture["elapsedSeconds"] >= 0
        assert len(capture["requestDiagnostics"]) == 1
    assert [item["responseDiagnostic"]["requestedMaxTokens"] for item in report["stages"]] \
        == [1600, 1600, 1600, 6000]
    bodies = {item["title"]: item["body"]
              for item in json.loads(case["context"]["historicalPosts"])["notes"]}
    for capture in report["stages"][1:3]:
        note = capture["input"]["note"]
        assert set(note) == {"title", "bodyExcerpts"}
        assert "".join(item["text"] for item in note["bodyExcerpts"]) == bodies[note["title"]]
        assert capture["inputScope"]["bodyCharacters"] == len(bodies[note["title"]])
        example = capture["output"]["examples"][0]
        assert set(example) == {"excerptIds", "interpretation"}
        assert example["excerptIds"] == [item["excerptId"] for item in note["bodyExcerpts"][:2]]
    profile = report["result"]["output"]["profile"]
    assert bodies["甲篇"] in profile["voiceFingerprint"][0]
    assert profile["titleFormulas"][0]["examples"] == ["甲篇"]
    assert profile["viralStructure"]["steps"] == ["条件：确认费用", "行动：作出决定"]
    synthesis = report["stages"][-1]["input"]
    assert "initialView" not in synthesis
    assert all("question" not in item for item in synthesis["readings"])
    assert report["stages"][-1]["userPrompt"].startswith("账号定位：")
    assert {note["title"]: "".join(fragment["text"] for fragment in note["bodyExcerpts"])
            for note in synthesis["notes"]} == bodies
    assert report["stages"][-1]["inputScope"] == {
        "kind": "all_source_notes_and_readings", "noteCount": 3,
        "noteIds": ["n1", "n2", "n3"], "readingCount": 2,
        "bodyCharacters": sum(map(len, bodies.values())),
    }
    assert report["progress"] == updates
    assert all(set(item) == {"phase", "status", "completed", "total", "elapsedSeconds"}
               for item in updates)
    assert report["elapsedSeconds"] >= 0


def test_deepseek_staged_diagnostics_preserve_provider_counts_and_redaction(settings):
    check = load_check()
    case = frozen_case()
    case["context"]["positioning"] = "deepseek-test-secret Bearer other-secret"
    before = deepcopy(case)
    factory, services, requests = diagnostic_factory(check, settings, provider="deepseek")
    report = asyncio.run(check.run_check(factory, case))
    assert report["status"] == "completed"
    assert case == before
    assert report["requestAttempts"] == len(services) == len(requests) == 4
    assert report["totalUsage"] == {
        "prompt_tokens": 40, "completion_tokens": 12, "total_tokens": 52,
    }
    assert [capture["stage"] for capture in report["stages"]] == [
        "overview", "read", "read", "synthesis",
    ]
    for capture in report["stages"]:
        assert capture["modelMetadata"]["provider"] == "deepseek"
        assert capture["modelMetadata"]["model"] == "deepseek-flash-test"
        assert capture["modelMetadata"]["profileModel"] == "deepseek-flash-test"
        assert capture["requestAttempts"] == len(capture["requestDiagnostics"]) == 1
        diagnostic = capture["responseDiagnostic"]
        assert diagnostic["phase"] == "parsed"
        assert diagnostic["enableThinking"] is False
        assert diagnostic["thinkingBudget"] is None
        assert diagnostic["timeoutsSeconds"]["read"] == settings.deepseek_read_timeout_seconds
    assert all(call["metadata"]["provider"] == "deepseek"
               for call in report["result"]["modelMetadata"]["calls"])
    serialized = json.dumps(report)
    assert "deepseek-test-secret" not in serialized and "other-secret" not in serialized
    assert "[REDACTED]" in serialized


def test_invalid_forced_scope_makes_zero_calls(settings):
    check = load_check()
    for ids in ([], ["n1", "n1"], ["n4"], ["stable-a"], ["n1", "n2", "n3", "n4"]):
        report = asyncio.run(check.run_check(
            lambda: pytest.fail("must preflight"), frozen_case(), read_note_ids=ids,
        ))
        assert report["status"] == "failed"
        assert report["requestAttempts"] == 0
        assert report["error"]["phase"] == "input_validation"


def test_read_scope_counts_all_body_excerpt_text_without_counting_title_or_ids():
    check = load_check()
    scope = check._input_scope("read", {"note": {"title": "标题", "bodyExcerpts": [
        {"excerptId": "b1", "text": "第一句。\n"},
        {"excerptId": "b2", "text": "😀 第二句。"},
        {"excerptId": "b3", "text": "\n"},
    ]}})
    assert scope == {"kind": "single_note", "noteCount": 1, "title": "标题",
                     "bodyCharacters": len("第一句。\n😀 第二句。\n")}
    assert check._input_scope("read", {"note": {"title": "只有标题", "bodyExcerpts": []}})[
        "bodyCharacters"
    ] == 0


def test_unusable_final_output_is_captured_after_optional_overview_and_one_retry(settings):
    check = load_check()
    factory, services, _ = diagnostic_factory(
        check, settings, responder=lambda _: {"invalid": True},
    )
    report = asyncio.run(check.run_check(factory, frozen_case()))
    assert report["status"] == "failed"
    assert report["requestAttempts"] == len(services) == 3
    assert report["error"]["phase"] == "synthesis"
    assert report["totalUsage"]["total_tokens"] == 39
    assert report["stages"][0]["output"] == {"invalid": True}
    assert "result" not in report


def test_missing_selection_uses_default_report_without_repeating_overview(settings):
    check = load_check()
    overview_attempts = 0

    def respond(payload):
        nonlocal overview_attempts
        output = stage_output(payload)
        if "account" in payload:
            overview_attempts += 1
            if overview_attempts == 1:
                output.pop("readings")
        return output

    case = frozen_case()
    before = deepcopy(case)
    factory, services, requests = diagnostic_factory(check, settings, responder=respond)
    report = asyncio.run(check.run_check(factory, case))
    assert report["status"] == "completed"
    assert case == before
    assert report["requestAttempts"] == len(services) == 2
    assert [stage["stage"] for stage in report["stages"]] == [
        "overview", "synthesis",
    ]
    assert "readings" not in report["stages"][0]["output"]
    assert "profile" in report["stages"][1]["output"]
    assert report["totalUsage"]["total_tokens"] == 26
    assert report["result"]["modelMetadata"]["retryCount"] == 0
    assert report["result"]["modelMetadata"]["requestCount"] == 2
    assert report["validatedResult"]["profile"]["titleFormulas"]


def test_product_validation_keeps_compiled_output_and_records_filtered_claims(
    settings, monkeypatch,
):
    check = load_check()
    case = frozen_case()
    before = deepcopy(case)
    monkeypatch.setattr("sqlite3.connect", lambda *a, **k: pytest.fail("no database access"))

    def respond(payload):
        output = stage_output(payload)
        if "readings" in payload:
            output["profile"]["accountPortrait"]["recurringThemes"] = [{
                "statement": "具体选择：确认条件再决定。",
                "evidence": [
                    {"noteId": "n1", "excerptId": "t"},
                    {"noteId": "n1", "excerptId": "b1"},
                    {"noteId": "n1", "excerptId": "b2"},
                    {"noteId": "n2", "excerptId": "b1"},
                ],
            }]
        return output

    factory, services, requests = diagnostic_factory(check, settings, responder=respond)
    report = asyncio.run(check.run_check(factory, case))
    assert report["status"] == "completed"
    assert report["semanticStatus"] == "not_reviewed"
    assert report["requestAttempts"] == len(services) == len(requests) == 4
    assert case == before
    compiled = report["result"]["output"]["profile"]["accountPortrait"]
    raw = report["stages"][-1]["output"]["profile"]["accountPortrait"]
    assert len(raw["recurringThemes"]) == 1
    assert len(raw["recurringThemes"][0]["evidence"]) == 4
    assert compiled["recurringThemes"] == []
    assert report["result"]["modelMetadata"]["degradedStages"] == {"synthesis": 1}
    assert report["result"]["modelMetadata"]["calls"][-1]["omittedItemCount"] >= 1
    assert report["validatedResult"]["profile"]["accountPortrait"]["recurringThemes"] == []
    verification = report["portraitVerification"]
    assert verification["rawClaimCounts"]["recurringThemes"] == 0
    assert verification["keptClaimCounts"]["recurringThemes"] == 0
    assert verification["droppedClaimCounts"] == {}
    assert verification["hasVerifiedPortrait"] is True
    assert verification["scope"] == "source_identity_and_literal_quotes_not_semantic_entailment"


@pytest.mark.parametrize("failure", ["schema", "portrait"])
def test_product_validation_failure_cannot_mark_report_completed(settings, monkeypatch, failure):
    check = load_check()

    if failure == "portrait":
        def fail_verification(*args):
            raise RuntimeError("test-secret-only")
        monkeypatch.setattr(check, "verified_portrait", fail_verification)
    else:
        product_contract = check.ProfileStageResult

        class FailingProductContract:
            @staticmethod
            def model_validate(_output):
                return product_contract.model_validate({
                    "profile": {"pillars": [{"invalid": "not a string"}]},
                })

        monkeypatch.setattr(check, "ProfileStageResult", FailingProductContract)
    factory, services, requests = diagnostic_factory(check, settings)
    report = asyncio.run(check.run_check(factory, frozen_case()))
    assert report["status"] == "failed"
    assert report["requestAttempts"] == len(services) == len(requests) == 4
    assert report["error"] == {
        "type": "ValidationError" if failure == "schema" else "RuntimeError",
        "phase": "product_validation",
    }
    assert "result" in report  # Keep the compiled output for diagnosing the failure.
    assert "validatedResult" not in report
    assert "portraitVerification" not in report
    assert report["stages"][-1]["status"] == "completed"  # Model call itself succeeded.
    assert report["totalUsage"]["total_tokens"] == 52
    assert "test-secret-only" not in json.dumps(report)


def test_product_validation_helper_is_offline_and_preserves_all_inputs(monkeypatch):
    check = load_check()
    case = frozen_case()
    compiled = check.compile_usable_account_report(stage_output({}), case["snapshot"])
    before = deepcopy((compiled, case))
    monkeypatch.setattr(check, "DiagnosticProfileCalls", lambda *a, **k: pytest.fail("no calls"))
    monkeypatch.setattr("sqlite3.connect", lambda *a, **k: pytest.fail("no database access"))
    validated, verification = check.validate_product_result(
        compiled, case["snapshot"], case["observations"],
    )
    assert (compiled, case) == before
    assert verification["droppedClaimCounts"] == {}
    assert validated["profile"]["titleFormulas"] == compiled["profile"]["titleFormulas"]
    assert validated["profile"]["voiceFingerprint"] == compiled["profile"]["voiceFingerprint"]
    validated["observations"]["coverage"]["selectedCount"] = 999
    assert case == before[1]


def test_diagnostics_redact_raw_text_outputs_metadata_and_frozen_context(settings):
    check = load_check()
    case = frozen_case()
    case["context"]["positioning"] = "test-secret-only Bearer other-secret"

    def respond(payload):
        output = stage_output(payload)
        if "account" in payload:
            output["summary"]["text"] = "test-secret-only Bearer echoed-secret"
        if "readings" in payload:
            output["profile"]["accountPortrait"]["summary"]["statement"] = (
                "test-secret-only Bearer echoed-secret"
            )
        return output

    factory, _, _ = diagnostic_factory(check, settings, responder=respond)
    report = asyncio.run(check.run_check(factory, case))
    assert report["status"] == "completed"
    serialized = json.dumps(report)
    for secret in ("test-secret-only", "other-secret", "echoed-secret"):
        assert secret not in serialized
    assert "[REDACTED]" in serialized
    assert "[REDACTED]" in report["validatedResult"]["profile"]["accountPortrait"][
        "summary"
    ]["statement"]
    assert report["semanticStatus"] == "not_reviewed"


@pytest.mark.parametrize("success", [True, False])
def test_live_cli_saves_one_report_for_success_or_failure_without_console_raw_content(
    settings, tmp_path, monkeypatch, capsys, success,
):
    check = load_check()
    case = frozen_case()
    source = tmp_path / "frozen.json"
    source.write_text(json.dumps(case), encoding="utf-8")
    destination = tmp_path / "new-report"
    factory, services, _ = diagnostic_factory(
        check, settings, responder=None if success else lambda _: {"invalid": True},
    )
    monkeypatch.setattr(check.Settings, "from_environment", lambda: replace(
        settings, model_provider="anthropic", qwen_api_key="test-secret-only",
    ))
    monkeypatch.setattr(check, "DiagnosticProfileCalls", lambda *a, **k: factory())
    monkeypatch.setattr(sys, "argv", [check.__file__, "--input-from", str(source),
                                    "--live", "--output", str(destination)])
    assert check.main() == (0 if success else 1)
    report = json.loads((destination / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == ("completed" if success else "failed")
    assert report["semanticStatus"] == "not_reviewed"
    assert len(list(destination.iterdir())) == 1
    assert report["requestAttempts"] == len(services) == (4 if success else 3)
    console = capsys.readouterr().out
    assert "test-secret-only" not in console
    assert "rawText" not in console
    assert "先确认费用" not in console
    assert "冻结的账号介绍" not in console
    assert json.loads(console.splitlines()[-1])["semanticStatus"] == "not_reviewed"


@pytest.mark.parametrize("timeout_override", [None, 144])
def test_deepseek_live_cli_uses_explicit_provider_model_key_and_timeout(
    settings, tmp_path, monkeypatch, capsys, timeout_override,
):
    check = load_check()
    source = tmp_path / "frozen.json"
    source.write_text(json.dumps(frozen_case()), encoding="utf-8")
    destination = tmp_path / "deepseek-report"
    configured = replace(settings, model_provider="qwen", account_diagnosis_provider="qwen",
                         deepseek_api_key="deepseek-test-secret", deepseek_model="deepseek-flash-test",
                         deepseek_read_timeout_seconds=188, qwen_api_key="")
    factory, services, _ = diagnostic_factory(check, configured, provider="deepseek")
    captured = []

    def construct(active, **kwargs):
        captured.append((active, kwargs))
        return factory()

    monkeypatch.setattr(check.Settings, "from_environment", lambda: configured)
    monkeypatch.setattr(check, "DiagnosticProfileCalls", construct)
    monkeypatch.setattr(sys, "argv", [check.__file__, "--input-from", str(source),
        "--provider", "deepseek", "--live", "--output", str(destination),
        *(["--read-timeout-seconds", str(timeout_override)] if timeout_override else [])])
    assert check.main() == 0
    assert len(captured) == len(services) == 4
    for active, kwargs in captured:
        assert active.model_provider == "deepseek"
        assert active.deepseek_api_key == "deepseek-test-secret"
        assert kwargs["read_timeout_seconds"] == (timeout_override or 188)
    report = json.loads((destination / "report.json").read_text())
    assert report["provider"] == "deepseek" and report["configuredModel"] == "deepseek-flash-test"
    assert report["enableThinking"] is False and report["thinkingBudget"] is None
    assert report["requestAttempts"] == 4
    console = capsys.readouterr().out
    for private in ("deepseek-test-secret", "rawText", "先确认费用", "冻结的账号介绍"):
        assert private not in console
    assert configured.model_provider == "qwen"


def test_deepseek_live_cli_requires_own_key_before_creating_output(
    settings, tmp_path, monkeypatch,
):
    check = load_check()
    source = tmp_path / "frozen.json"
    source.write_text(json.dumps(frozen_case()), encoding="utf-8")
    destination = tmp_path / "not-created"
    monkeypatch.setattr(check.Settings, "from_environment", lambda: replace(
        settings, qwen_api_key="qwen-key-must-not-be-used", deepseek_api_key="",
    ))
    monkeypatch.setattr(check, "DiagnosticProfileCalls", lambda *a, **k: pytest.fail("no calls"))
    monkeypatch.setattr(sys, "argv", [check.__file__, "--input-from", str(source),
                                    "--provider", "deepseek", "--live", "--output", str(destination)])
    with pytest.raises(SystemExit, match="2"):
        check.main()
    assert not destination.exists()


def test_existing_destination_is_rejected_without_calls_or_overwrite(
    settings, tmp_path, monkeypatch,
):
    check = load_check()
    destination = tmp_path / "existing"
    destination.mkdir()
    marker = destination / "report.json"
    marker.write_text("untouched", encoding="utf-8")
    monkeypatch.setattr(check.Settings, "from_environment", lambda: pytest.fail("preflight first"))
    monkeypatch.setattr(sys, "argv", [check.__file__, "--input-from", "not-even-read.json",
                                    "--live", "--output", str(destination)])
    with pytest.raises(SystemExit, match="2"):
        check.main()
    assert marker.read_text(encoding="utf-8") == "untouched"


def test_live_requires_explicit_new_output_before_loading_configuration(monkeypatch):
    check = load_check()
    monkeypatch.setattr(check.Settings, "from_environment", lambda: pytest.fail("preflight first"))
    monkeypatch.setattr(sys, "argv", [check.__file__, "--input-from", "frozen.json", "--live"])
    with pytest.raises(SystemExit, match="2"):
        check.main()


@pytest.mark.parametrize("fail_reader", [False, True])
def test_parallel_captures_keep_start_order_and_count_cancelled_actual_attempts(
    settings, fail_reader,
):
    check = load_check()

    async def scenario():
        other_started = asyncio.Event()
        never = asyncio.Event()
        finished = []
        services = []

        async def respond(request):
            user = json.loads(request.content)["messages"][1]["content"]
            payload = (check.stage_input("synthesis", user) if user.startswith("账号定位：")
                       else json.loads(user))
            if "note" in payload:
                title = payload["note"]["title"]
                if title == "乙篇":
                    await other_started.wait()
                    if fail_reader:
                        return httpx.Response(503, json={"private": "test-secret-only"})
                else:
                    other_started.set()
                    if fail_reader:
                        await never.wait()
                finished.append(title)
            return httpx.Response(200, json={
                "usage": {"total_tokens": 13},
                "choices": [{"finish_reason": "stop", "message": {
                    "content": json.dumps(stage_output(payload), ensure_ascii=False),
                }}],
            })

        def factory():
            service = check.DiagnosticProfileCalls(
                replace(settings, qwen_api_key="test-secret-only"),
                transport=httpx.MockTransport(respond),
            )
            services.append(service)
            return service

        report = await asyncio.wait_for(check.run_check(factory, frozen_case()), timeout=2)
        readers = [item for item in report["stages"] if item["stage"] == "read"]
        assert [item["taskTitle"] for item in readers] == ["乙篇", "甲篇"]
        assert all(item["requestAttempts"] == 1 for item in report["stages"])
        assert report["requestAttempts"] == len(services) == (3 if fail_reader else 4)
        if fail_reader:
            assert report["status"] == "failed"
            assert [item["status"] for item in readers] == ["failed", "cancelled"]
            assert readers[0]["responseDiagnostic"]["httpStatus"] == 503
            assert report["totalUsage"] == {"total_tokens": 13}
            assert all(item["stage"] != "synthesis" for item in report["stages"])
        else:
            assert report["status"] == "completed"
            assert finished == ["甲篇", "乙篇"]
            for capture in readers:
                assert capture["taskTitle"] in capture["responseDiagnostic"]["rawText"]
                assert capture["output"]["assessment"].startswith(capture["taskTitle"])

    asyncio.run(scenario())
