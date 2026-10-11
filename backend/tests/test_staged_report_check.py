import asyncio
import importlib.util
import json
import sys
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import httpx
import pytest


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
            "summary": {"text": "关心具体判断。", "noteIds": ["n1"]},
            "directions": [{"text": "日常经验", "noteIds": ["n1", "n2"]}],
            "hypotheses": ["确认条件"],
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
    examples = [item["id"] for reading in payload["readings"] for item in reading["examples"]]
    return {
        "summary": {"text": "从具体问题出发。", "noteIds": ["n1"]}, "keywords": [],
        "directions": [],
        "strengths": [{"text": "交代具体问题。", "exampleIds": examples[:1]}] if examples else [],
        "writing": [{"text": "安排表达次序。", "exampleIds": examples[1:2]}]
        if len(examples) > 1 else [],
        "nextSteps": [],
    }


def diagnostic_factory(check, settings, *, responder=None):
    services = []
    requests = []
    diagnostic_class = check.DiagnosticProfileCalls
    configured = replace(settings, model_provider="qwen", qwen_api_key="test-secret-only")

    def respond(request):
        payload = json.loads(json.loads(request.content)["messages"][1]["content"])
        requests.append(payload)
        content = stage_output(payload) if responder is None else responder(payload)
        return httpx.Response(200, json={
            "model": "qwen3.8-max-test", "usage": {
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
    assert preview["scope"]["maxModelRequests"] == 4
    assert not destination.exists()


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
    expected_questions = ["这篇如何说明判断？（n2）", "这篇如何说明判断？（n1）"]
    assert [item["question"] for item in report["result"]["modelMetadata"]["readingAssessments"]] \
        == expected_questions
    assert report["result"]["output"]["profile"]["accountPortrait"]["summary"]["statement"] \
        == "从具体问题出发。"
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
        == [1600, 1600, 1600, 2000]
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
    bound = report["result"]["output"]["profile"]["accountPortrait"]["expressionPatterns"][0]
    assert [fragment["excerptId"] for fragment in bound["examples"][0]["fragments"]] \
        == ["b1", "b2"]
    assert "".join(item["quote"] for item in bound["examples"][0]["fragments"]) == bodies["甲篇"]
    synthesis = report["stages"][-1]["input"]
    assert synthesis["initialView"]["summary"] == {
        "text": "关心具体判断。", "noteIds": ["n1"],
    }
    assert synthesis["initialView"]["directions"] == [
        {"text": "日常经验", "noteIds": ["n1", "n2"]},
    ]
    assert [item["question"] for item in synthesis["readings"]] == expected_questions
    assert report["progress"] == updates
    assert all(set(item) == {"phase", "status", "completed", "total", "elapsedSeconds"}
               for item in updates)
    assert report["elapsedSeconds"] >= 0


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


def test_validation_failure_is_captured_without_retry_and_with_actual_usage(settings):
    check = load_check()
    factory, services, _ = diagnostic_factory(
        check, settings, responder=lambda _: {"invalid": True},
    )
    report = asyncio.run(check.run_check(factory, frozen_case()))
    assert report["status"] == "failed"
    assert report["requestAttempts"] == len(services) == 1
    assert report["error"]["phase"] == "overview"
    assert report["totalUsage"]["total_tokens"] == 13
    assert report["stages"][0]["output"] == {"invalid": True}
    assert "result" not in report


def test_diagnostics_redact_raw_text_outputs_metadata_and_frozen_context(settings):
    check = load_check()
    case = frozen_case()
    case["context"]["positioning"] = "test-secret-only Bearer other-secret"

    def respond(payload):
        output = stage_output(payload)
        if "account" in payload:
            output["summary"]["text"] = "test-secret-only Bearer echoed-secret"
        return output

    factory, _, _ = diagnostic_factory(check, settings, responder=respond)
    report = asyncio.run(check.run_check(factory, case))
    assert report["status"] == "completed"
    serialized = json.dumps(report)
    for secret in ("test-secret-only", "other-secret", "echoed-secret"):
        assert secret not in serialized
    assert "[REDACTED]" in serialized
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
    assert report["requestAttempts"] == len(services) == (4 if success else 1)
    console = capsys.readouterr().out
    assert "test-secret-only" not in console
    assert "rawText" not in console
    assert "先确认费用" not in console
    assert "冻结的账号介绍" not in console
    assert json.loads(console.splitlines()[-1])["semanticStatus"] == "not_reviewed"


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
            payload = json.loads(json.loads(request.content)["messages"][1]["content"])
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
