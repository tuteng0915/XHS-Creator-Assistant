import asyncio
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.models import ModelCallResponse, ModelOperation


def load_check():
    path = Path(__file__).resolve().parents[2] / "scripts/check_audience_analysis.py"
    spec = importlib.util.spec_from_file_location("analysis_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def raw_export(tmp_path):
    base = tmp_path / "raw" / "xhs" / "jsonl"
    base.mkdir(parents=True)
    notes = [
        {
            "note_id": str(i),
            "title": "真实标题",
            "desc": "先准备材料",
            "creator_hash": "1234567890abcdef",
            "time": 1700000000000 + i * 1000,
        }
        for i in range(12)
    ]
    comments = [
        {
            "note_id": "11",
            "comment_id": "author",
            "content": "请发到我的邮箱",
            "creator_hash": "1234567890abcdef",
        },
        {
            "note_id": "11",
            "comment_id": "reader",
            "content": "想知道第一步",
            "creator_hash": "fedcba0987654321",
        },
    ]
    for name, rows in [("contents", notes), ("comments", comments)]:
        (base / f"creator_{name}_test.jsonl").write_text(
            "\n".join(json.dumps(row, ensure_ascii=False) for row in rows), encoding="utf-8"
        )
    return tmp_path / "raw"


def test_preview_uses_import_scope_and_role_logic_without_network(tmp_path):
    source = raw_export(tmp_path)
    check = load_check()
    context = check.prepare_context(source)
    assert [n["noteId"] for n in context["notes"]] == [str(i) for i in range(11, 1, -1)]
    assert context["sampling"]["sentAuthorComments"] == 1
    assert context["sampling"]["sentCandidateComments"] == 1
    assert context["sampling"]["sentComments"] == 2
    assert context["notes"][0]["comments"][0]["commentId"] == "reader"
    assert context["notes"][0]["authorReplies"][0]["commentId"] == "author"
    assert context["sampling"]["commentLayout"] == "reader_comments_author_background_v1"
    assert "authorHash" not in json.dumps(context)
    result = subprocess.run(
        [sys.executable, check.__file__, str(source)], capture_output=True, text=True, check=True
    )
    assert json.loads(result.stdout)["requestAttempts"] == 0


def test_one_call_preserves_rejected_output_and_reader_result(tmp_path):
    check = load_check()
    context = check.prepare_context(raw_export(tmp_path))

    class Model:
        calls = 0

        async def call_operation(self, operation, received):
            self.calls += 1
            assert operation == ModelOperation.AUDIENCE_ANALYSIS
            assert received is context
            return ModelCallResponse(
                output={
                    "summary": "模拟人物",
                    "limitations": "样本有限",
                    "groups": [
                        {
                            "id": cid,
                            "name": cid,
                            "profile": "先看条件再行动",
                            "evidenceRefs": [
                                {
                                    "noteId": "11",
                                    "commentId": cid,
                                    "sourceType": "comment",
                                    "quote": quote,
                                }
                            ],
                        }
                        for cid, quote in [("author", "我的邮箱"), ("reader", "第一步")]
                    ],
                },
                model_metadata={"model": "fake"},
            )

    model = Model()
    report = asyncio.run(check.run_check(model, context))
    assert model.calls == 1
    assert report["status"] == "partially_completed"
    assert len(report["output"]["groups"]) == 2
    assert len(report["result"]["groups"]) == 1
    assert report["requiresSemanticReview"] is True
    assert report["reviewSummary"]["semanticStatus"] == "not_reviewed"
    assert report["reviewSummary"]["acceptedGroups"] == 1
    assert report["reviewSummary"]["rejectedGroups"] == 1
    assert report["reviewSummary"]["rejectionCodes"] == {
        "author_comment_not_reader_evidence": 1,
    }


def test_failure_is_not_retried_or_dumped_with_sensitive_details():
    class Model:
        calls = 0

        async def call_operation(self, *args):
            self.calls += 1
            raise RuntimeError("secret-header-value")

    model = Model()
    report = asyncio.run(load_check().run_check(model, {"notes": []}))
    assert model.calls == 1
    assert report["status"] == "failed"
    assert report["error"] == {"phase": "model_call", "type": "RuntimeError"}
    assert "secret-header-value" not in json.dumps(report)
    assert report["reviewSummary"]["acceptedGroups"] is None
    assert report["reviewSummary"]["rejectedGroups"] is None


def test_validation_failure_keeps_model_output_for_review():
    class Model:
        async def call_operation(self, *args):
            return ModelCallResponse(
                output={"groups": "bad-schema"}, model_metadata={"model": "fake"}
            )

    report = asyncio.run(load_check().run_check(Model(), {"notes": []}))
    assert report["status"] == "failed"
    assert report["error"]["phase"] == "validation"
    assert report["output"] == {"groups": "bad-schema"}
    assert report["reviewSummary"]["generatedGroups"] is None


def test_review_summary_never_promotes_quote_validation_to_semantic_success():
    report = {
        "status": "completed", "output": {"groups": [{"name": "角色"}]},
        "diagnostics": {"acceptedGroups": 1, "rejectedGroups": []},
    }
    summary = load_check().review_summary(report)
    assert summary["automatedStatus"] == "completed"
    assert summary["generatedGroups"] == summary["acceptedGroups"] == 1
    assert summary["semanticStatus"] == "not_reviewed"
    assert len(summary["manualChecks"]) == 5
    assert "reviewSummary" not in report


def test_semantically_unrelated_exact_quote_remains_an_explicit_manual_review(tmp_path):
    check = load_check()
    context = check.prepare_context(raw_export(tmp_path))

    class Model:
        async def call_operation(self, *args):
            return ModelCallResponse(output={
                "summary": "测试机械校验的边界", "limitations": "需人工复核",
                "groups": [{
                    "id": "a", "name": "审美派", "profile": "关心配色",
                    "coreConcern": "寻找合适的颜色组合",
                    "evidenceRefs": [{"noteId": "11", "commentId": "reader",
                                      "sourceType": "comment", "quote": "想知道第一步"}],
                }],
            }, model_metadata={"model": "fake"})

    report = asyncio.run(check.run_check(Model(), context))
    # Exact source matching is intentionally not a semantic entailment detector.
    assert report["status"] == "completed"
    assert report["reviewSummary"]["acceptedGroups"] == 1
    assert report["reviewSummary"]["semanticStatus"] == "not_reviewed"
    assert report["requiresSemanticReview"] is True


def test_existing_report_directory_refuses_live_call(tmp_path, monkeypatch, settings):
    check = load_check()
    source = raw_export(tmp_path)
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "report.json"
    sentinel.write_text("untouched", encoding="utf-8")
    from dataclasses import replace

    monkeypatch.setattr(
        check.Settings, "from_environment", lambda: replace(settings, qwen_api_key="test")
    )
    monkeypatch.setattr(
        sys, "argv", [check.__file__, str(source), "--live", "--output", str(output)]
    )

    def forbidden(*args):
        pytest.fail("No model service should be created for an existing report directory")

    monkeypatch.setattr(check, "ModelCallService", forbidden)
    with pytest.raises(FileExistsError):
        check.main()
    assert sentinel.read_text() == "untouched"


def test_replay_preserves_exact_context_and_never_changes_baseline(tmp_path):
    check = load_check()
    context = check.prepare_context(raw_export(tmp_path))
    path = tmp_path / "baseline.json"
    original = json.dumps({"context": context}, ensure_ascii=False)
    path.write_text(original, encoding="utf-8")
    assert check.context_from_report(path) == context
    result = subprocess.run(
        [sys.executable, check.__file__, "--context-from", str(path)],
        capture_output=True,
        text=True,
        check=True,
    )
    preview = json.loads(result.stdout)
    assert preview["requestAttempts"] == 0
    assert preview["scope"] == context["scope"]
    assert preview["sampling"] == context["sampling"]
    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("report", [[], {}, {"context": {"notes": []}}])
def test_incomplete_replay_input_is_rejected_before_call(tmp_path, report):
    path = tmp_path / "bad-report.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    with pytest.raises(ValueError, match="完整 context"):
        load_check().context_from_report(path)
