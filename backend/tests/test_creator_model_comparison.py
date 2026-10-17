import asyncio
import importlib.util
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.models import ModelCallResponse, ModelOperation


@pytest.fixture
def comparison():
    spec = importlib.util.spec_from_file_location(
        "creator_comparison",
        Path(__file__).resolve().parents[2] / "scripts/compare_creator_models.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def receipts():
    first_message = {"id": "first", "sender": "creator", "to": "writing", "content": "写初稿"}
    second_message = {"id": "second", "sender": "creator", "to": "writing", "content": "再写"}
    context = {
        "assistantMode": "single_writer", "target": {"title": "初始标题", "body": ""},
        "receivedMessage": first_message, "transcript": [first_message],
        "sessionContext": {"creatorContextSnapshot": {"references": [
            {"kind": "imported_note", "id": "m", "noteId": "n",
             "content": {"body": "爸爸的MBA毕业于MIT；毕业后第一步是就业。", "title": "原笔记"}},
        ]}},
    }
    followup = deepcopy(context)
    followup["receivedMessage"] = second_message
    followup["transcript"] = [first_message, {"id": "old-ai", "sender": "writing",
                                            "content": "未经确认的下周截止。"}, second_message]
    return {"sessions": [{
        "topic": {"title": "已保存标题", "body": "还没想好🤔，先查证。\n\n后文不能改。"},
        "messages": [
            {"sender_role": "writing", "context_snapshot": {"specialistInput": context}},
            {"sender_role": "writing", "context_snapshot": {"specialistInput": followup}},
        ],
    }]}


def test_cases_are_frozen_and_paired_input_is_identical(comparison, receipts, tmp_path):
    before = deepcopy(receipts)
    settings = Settings(database_path=tmp_path / "unused.sqlite", upload_directory=tmp_path)
    cases = comparison.make_cases(receipts)
    assert [case["id"] for case in cases] == ["initial", "revision", "confirmed", "local"]
    for case in cases:
        messages = []
        for provider in ("qwen", "deepseek"):
            service = comparison.ModelCallService(replace(settings, model_provider=provider))
            packet, _ = comparison.packet_for(case, service)
            system, user = service._build_prompt(ModelOperation.CONTENT_COLLABORATION_TURN, packet)
            messages.append(service._compatible_messages(ModelOperation.CONTENT_COLLABORATION_TURN,
                                                          packet, system, user))
        assert comparison.digest(messages[0]) == comparison.digest(messages[1])
    assert receipts == before
    assert not (tmp_path / "unused.sqlite").exists()


def test_error_history_and_local_scope_are_kept_without_invented_author_facts(comparison, receipts):
    cases = comparison.make_cases(receipts)
    assert all(item["sender"] == "creator" for item in cases[0]["context"]["transcript"])
    prior = [item for item in cases[1]["context"]["transcript"] if item["sender"] == "writing"]
    assert prior == [{"id": "old-ai", "sender": "writing", "content": "未经确认的下周截止。"}]
    local = cases[3]["context"]
    assert local["target"]["body"].endswith("后文不能改。")
    selection = local["writingFocus"]["selection"]
    assert selection["text"] == "还没想好🤔，先查证。"
    assert selection["end"] == len(selection["text"]) + 1
    assert "爸爸的MBA毕业于MIT" in cases[2]["context"]["receivedMessage"]["content"]


def test_frozen_cases_are_explicit_bounded_and_do_not_rewrite_input(comparison, receipts, tmp_path):
    path = tmp_path / "cases.json"
    cases = comparison.make_cases(receipts)
    document = {"cases": cases, "origin": "offline constructed; not product history"}
    original = json.dumps(document, ensure_ascii=False)
    path.write_text(original)
    loaded, source_hash = comparison.load_frozen_cases(path)
    assert loaded == cases
    assert source_hash == comparison.digest(document)
    assert path.read_text() == original
    for invalid in (cases[:3], cases + [cases[0]], [dict(cases[0], id="../outside"), *cases[1:]]):
        path.write_text(json.dumps({"cases": invalid}))
        with pytest.raises(ValueError, match="four ordered"):
            comparison.load_frozen_cases(path)
    cases[0]["context"]["assistantMode"] = "legacy_team"
    path.write_text(json.dumps({"cases": cases}))
    with pytest.raises(ValueError, match="single-writer"):
        comparison.load_frozen_cases(path)


def test_failure_is_recorded_without_retry_or_product_write(
    comparison, receipts, monkeypatch, tmp_path,
):
    class FailedService(comparison.ModelCallService):
        async def call_operation(self, operation, context):
            self.before_request()
            raise RuntimeError("private endpoint or credential must not be saved")

    monkeypatch.setattr(comparison, "ModelCallService", FailedService)
    settings = Settings(database_path=tmp_path / "unused.sqlite", upload_directory=tmp_path)
    result = asyncio.run(comparison.generate(comparison.make_cases(receipts)[0], "qwen",
                                            settings, tmp_path))
    record = json.loads((tmp_path / "initial-qwen.json").read_text())
    assert result["status"] == "failed"
    assert result["requestCount"] == 1
    assert record["errorType"] == "RuntimeError"
    assert "private endpoint" not in json.dumps(record)
    assert not (tmp_path / "unused.sqlite").exists()


def test_comparison_uses_production_parser_and_preserves_redundant_raw_output(
    comparison, receipts, monkeypatch, tmp_path,
):
    output = {"turn": {"summary": "给一版开头", "nextRecipient": "creator",
                       "candidateSuggestions": [{
                           "kind": "copy_option", "title": "先确认目标",
                           "body": "先写下你能查证的事。", "confidence": "inference",
                           "evidenceRefs": [],
                       }]}, "evidenceRefs": []}

    class RecordedService(comparison.ModelCallService):
        async def call_operation(self, operation, context):
            self.before_request()
            return ModelCallResponse(output=deepcopy(output), model_metadata={})

    monkeypatch.setattr(comparison, "ModelCallService", RecordedService)
    settings = Settings(database_path=tmp_path / "unused.sqlite", upload_directory=tmp_path)
    result = asyncio.run(comparison.generate(comparison.make_cases(receipts)[0], "deepseek",
                                            settings, tmp_path))
    record = json.loads((tmp_path / "initial-deepseek.json").read_text())
    assert result["requestCount"] == 1
    assert result["contractStatus"] == "passed"
    assert record["output"] == output
    assert record["outputNormalization"]["ignoredOuterFields"] == ["evidenceRefs"]
    assert not (tmp_path / "unused.sqlite").exists()


def test_preview_defaults_to_deepseek_without_calls(
    comparison, receipts, monkeypatch, tmp_path, capsys,
):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": comparison.make_cases(receipts)}))
    monkeypatch.setattr("sys.argv", ["compare", "--cases", str(path),
                                     "--case", "initial", "--case", "revision"])
    monkeypatch.setattr(comparison.Settings, "from_environment", lambda: Settings(
        database_path=tmp_path / "unused.sqlite", upload_directory=tmp_path,
    ))

    async def forbidden(*args, **kwargs):
        pytest.fail("Preview must not call a model")

    monkeypatch.setattr(comparison, "generate", forbidden)
    asyncio.run(comparison.main())
    preview = json.loads(capsys.readouterr().out)
    assert preview["providers"] == ["deepseek"]
    assert preview["requestsPlanned"] == 2
    assert preview["requestCount"] == 0
    assert [case["id"] for case in preview["cases"]] == ["initial", "revision"]
    assert not (tmp_path / "unused.sqlite").exists()


def test_three_stage_receipts_keep_generation_statement_and_editor_outputs_separate(
    comparison, receipts, monkeypatch, tmp_path,
):
    original = {"turn": {"summary": "给一版", "nextRecipient": "creator",
                         "candidateSuggestions": [{"kind": "copy_option", "title": "文章标题",
                             "body": "这是一个观点。", "confidence": "inference",
                             "evidenceRefs": []}]}}
    outputs = [original, {"facts": []}, {"checks": [
        {"id": "0:title:0", "action": "keep", "claimType": "opinion"},
        {"id": "0:body:0", "action": "keep", "claimType": "opinion"},
    ]}]
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={"model": "deepseek-flash", "choices": [
            {"finish_reason": "stop", "message": {"content": json.dumps(
                outputs[len(requests) - 1], ensure_ascii=False,
            )}},
        ]})

    monkeypatch.setattr(comparison.ModelCallService, "_deepseek_client",
                        lambda *_: httpx.AsyncClient(transport=httpx.MockTransport(respond)))
    settings = Settings(database_path=tmp_path / "unused.sqlite", upload_directory=tmp_path,
                        deepseek_api_key="test-key")
    result = asyncio.run(comparison.generate(comparison.make_cases(receipts)[0], "deepseek",
                                            settings, tmp_path, edit_facts=True))
    record = json.loads((tmp_path / "initial-deepseek.json").read_text())
    assert result["contractStatus"] == "passed" and result["requestCount"] == 3
    assert json.loads(record["rawContent"]) == outputs[0]
    assert json.loads(record["creatorStatementsRawContent"]) == outputs[1]
    assert json.loads(record["factEditRawContent"]) == outputs[2]
    assert not (tmp_path / "unused.sqlite").exists()


@pytest.mark.parametrize("provider,expected", [
    (None, ["deepseek"]), ("qwen", ["qwen"]), ("both", ["qwen", "deepseek"]),
])
def test_live_cli_only_calls_explicit_providers(
    comparison, receipts, monkeypatch, tmp_path, provider, expected,
):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": comparison.make_cases(receipts)}))
    output = tmp_path / "output"
    argv = ["compare", "--cases", str(path), "--live", "--output", str(output),
            "--case", "initial"]
    if provider:
        argv += ["--provider", provider]
    monkeypatch.setattr("sys.argv", argv)
    monkeypatch.setattr(comparison.Settings, "from_environment", lambda: Settings(
        database_path=tmp_path / "unused.sqlite", upload_directory=tmp_path,
        deepseek_api_key="test-deepseek" if "deepseek" in expected else "",
        qwen_api_key="test-qwen" if "qwen" in expected else "",
    ))
    calls = []

    async def generate(case, provider_name, settings, directory):
        calls.append((case["id"], provider_name))
        return {"inputHash": "same", "case": case["id"], "provider": provider_name}

    monkeypatch.setattr(comparison, "generate", generate)
    asyncio.run(comparison.main())
    manifest = json.loads((output / "manifest.json").read_text())
    assert manifest["providers"] == expected
    assert manifest["requestsPlanned"] == len(expected)
    assert calls == [("initial", name) for name in expected]
    assert not (tmp_path / "unused.sqlite").exists()


def test_cli_rejects_duplicate_cases_before_calls(comparison, receipts, monkeypatch, tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"cases": comparison.make_cases(receipts)}))
    monkeypatch.setattr("sys.argv", ["compare", "--cases", str(path),
                                     "--case", "initial", "--case", "initial", "--live"])
    monkeypatch.setattr(comparison.Settings, "from_environment", lambda: Settings(
        database_path=tmp_path / "unused.sqlite", upload_directory=tmp_path,
    ))
    with pytest.raises(SystemExit) as error:
        asyncio.run(comparison.main())
    assert error.value.code == 2
