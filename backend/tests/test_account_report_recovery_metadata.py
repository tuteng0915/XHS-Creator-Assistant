from copy import deepcopy
from types import SimpleNamespace

import pytest
from test_account_langgraph_workflow import collect, create_source_led_account_run
from test_workflow_lifecycle import create_pending_account_run

from app.errors import ValidationError
from app.models import AnalysisRunStatus, ModelCallResponse
from app.services.account_report_contract import AccountReportOutputError
from app.services.account_report_pipeline import run_staged_account_report
from app.workflows.account_diagnosis import (
    ACCOUNT_REPORT_INCOMPLETE_MESSAGE,
    ACCOUNT_REPORT_RETRY_EXHAUSTED_MESSAGE,
    SAMPLE_ACCOUNT_RESULT,
    FakeAccountDiagnosisModelProvider,
)

READING_PROGRESS = {
    "phase": "reading", "status": "running", "completed": 1, "total": 2,
    "preview": "《已读作品》：先列条件，再逐项核对。",
}
RECOVERY = {"stage": "read", "attempt": 2, "errorCode": "schema_validation"}
SAFE_PIPELINE_METADATA = {
    "accountReportMode": "staged",
    "promptVersion": "account-report/2026-10-11-staged-v4.1",
    "requestCount": 4, "retryCount": 1,
    "usage": {"prompt_tokens": 120, "completion_tokens": 30, "total_tokens": 150},
    "calls": [
        {"stage": "overview", "attempt": 1, "requestIndex": 1, "status": "completed",
         "metadata": {"provider": "qwen", "model": "qwen-test", "enableThinking": True,
                      "thinkingBudget": 200, "usage": {"total_tokens": 100}}},
        {"stage": "read", "noteId": "saved-note-1", "attempt": 1, "requestIndex": 2,
         "status": "completed", "metadata": {"usage": {"total_tokens": 50}}},
        {"stage": "read", "noteId": "saved-note-2", "attempt": 1, "requestIndex": 3,
         "status": "failed", "errorCode": "schema_validation", "usageUnavailable": True,
         "metadata": {"usage": {}}},
        {"stage": "read", "noteId": "saved-note-2", "attempt": 2, "requestIndex": 4,
         "status": "failed", "errorCode": "schema_validation", "usageUnavailable": True,
         "metadata": {"usage": {}}},
    ],
}


def exhausted_error():
    error = AccountReportOutputError("schema_validation")
    # Even if an upstream exception accidentally accumulates extra details, the
    # persistence boundary retains only the explicitly supported diagnostics.
    metadata = deepcopy(SAFE_PIPELINE_METADATA)
    metadata["rawResponse"] = "private provider response"
    metadata["readingAssessments"] = [{"assessment": "unfinalized analysis"}]
    metadata["usage"].update(reasoning_content="private reasoning", input_tokens=True)
    metadata["calls"][0]["metadata"].update(
        apiKey="private provider key", messages=[{"content": "raw source"}],
        responseSchema="unsafe schema body with spaces",
    )
    metadata["calls"][0]["metadata"]["usage"]["output_tokens"] = -3
    metadata["calls"][2]["rawError"] = "schema internals"
    metadata["calls"].extend([None, {"stage": [], "status": "failed"}])
    error.pipeline_metadata = metadata
    error.private_attribute = "never merge arbitrary exception attributes"
    error.args = ("private schema internals and provider key",)
    return error


@pytest.mark.parametrize("pain_fails", [False, True])
def test_exhausted_profile_saves_only_safe_metadata_and_keeps_parallel_branch(app, pain_fails):
    run = create_pending_account_run(app)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile_with_updates(self, *, positioning, historical_posts, on_update):
            await on_update(deepcopy(READING_PROGRESS))
            await on_update({
                "phase": "reading", "status": "running", "completed": 1, "total": 2,
                "preview": "", "recovery": deepcopy(RECOVERY),
            })
            stored = app.state.analysis_service.get(run["id"])
            progress = stored.model_metadata["profile"]["progress"]
            assert progress["preview"] == READING_PROGRESS["preview"]
            assert progress["completed"] == 1
            assert progress["recovery"] == RECOVERY
            assert "profile" not in stored.stage_results
            raise exhausted_error()

    provider = Provider(failures={"pain_points"} if pain_fails else set())
    app.state.account_workflow_service.fake_provider = provider
    events = collect(app, run["id"])
    stored = app.state.analysis_service.get(run["id"])
    assert stored.status == (AnalysisRunStatus.FAILED if pain_fails
                             else AnalysisRunStatus.PARTIALLY_COMPLETED)
    assert stored.stage_errors["profile"] == ACCOUNT_REPORT_RETRY_EXHAUSTED_MESSAGE
    assert "profile" not in stored.stage_results
    assert stored.model_metadata["profile"] == {
        "engine": "langgraph", **SAFE_PIPELINE_METADATA,
    }
    assert "progress" not in stored.model_metadata["profile"]
    failures = [event for event in events if event["stageKey"] == "profile"
                and event["data"]["eventType"] == "stage.failed"]
    assert len(failures) == 1
    assert failures[0]["data"]["error"] == ACCOUNT_REPORT_RETRY_EXHAUSTED_MESSAGE
    progress = [event["data"] for event in events
                if event["data"]["eventType"] == "stage.progress"]
    assert progress[-1]["recovery"] == RECOVERY
    assert progress[-1]["preview"] == READING_PROGRESS["preview"]
    assert progress[-1]["phase"] == "reading"
    assert progress[-1]["status"] == "running"
    if pain_fails:
        assert stored.stage_errors["pain_points"] == "pain points failed"
        assert "topics" not in provider.calls
        assert events[-1]["data"]["eventType"] == "run.failed"
    else:
        assert stored.stage_results["pain_points"] == {
            "painPoints": SAMPLE_ACCOUNT_RESULT["painPoints"],
        }
        assert stored.model_metadata["pain_points"] == {"engine": "langgraph"}
        assert "topics" in provider.calls
        assert events[-1]["data"]["eventType"] == "run.partial"


def test_success_after_recovery_preserves_success_metadata_and_clears_progress(app):
    run = create_pending_account_run(app)
    metadata = {**deepcopy(SAFE_PIPELINE_METADATA), "readingAssessments": [
        {"noteId": "saved-note-1", "assessment": "完整观察"},
    ]}

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile_with_updates(self, *, positioning, historical_posts, on_update):
            await on_update(deepcopy(READING_PROGRESS))
            await on_update({
                "phase": "synthesis", "status": "running", "completed": 0, "total": 1,
                "recovery": {**RECOVERY, "stage": "synthesis"},
            })
            assert (app.state.analysis_service.get(run["id"])
                    .model_metadata["profile"]["progress"]["preview"]
                    == READING_PROGRESS["preview"])
            return SimpleNamespace(
                output={"profile": deepcopy(SAMPLE_ACCOUNT_RESULT["profile"])},
                model_metadata=metadata,
            )

    app.state.account_workflow_service.fake_provider = Provider()
    events = collect(app, run["id"])
    stored = app.state.analysis_service.get(run["id"])
    assert stored.status == AnalysisRunStatus.COMPLETED
    assert stored.model_metadata["profile"] == {"engine": "langgraph", **metadata}
    assert "progress" not in stored.model_metadata["profile"]
    assert "profile" in stored.stage_results
    assert stored.stage_errors == {}
    assert events[-1]["data"]["eventType"] == "run.succeeded"


@pytest.mark.parametrize("error_code", ["schema_validation", "request_failed", "processing_failed"])
def test_generic_profile_error_imports_only_safe_pipeline_metadata(app, error_code):
    run = create_pending_account_run(app)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile(self, **kwargs):
            error = ValueError("普通错误")
            error.pipeline_metadata = exhausted_error().pipeline_metadata
            error.pipeline_metadata["calls"][2]["errorCode"] = error_code
            error.private_attribute = "do not import arbitrary attributes"
            raise error

    app.state.account_workflow_service.fake_provider = Provider()
    collect(app, run["id"])
    stored = app.state.analysis_service.get(run["id"])
    assert stored.stage_errors["profile"] == "普通错误"
    expected = deepcopy(SAFE_PIPELINE_METADATA)
    expected["calls"][2]["errorCode"] = error_code
    assert stored.model_metadata["profile"] == expected


@pytest.mark.parametrize("retry_count", [None, 0, True, "1", -1, 1])
def test_output_failure_only_claims_recovery_when_safe_retry_count_is_positive(app, retry_count):
    run = create_pending_account_run(app)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile(self, **kwargs):
            error = AccountReportOutputError("schema_validation")
            error.pipeline_metadata = {"requestCount": 1, "retryCount": retry_count}
            raise error

    app.state.account_workflow_service.fake_provider = Provider()
    events = collect(app, run["id"])
    stored = app.state.analysis_service.get(run["id"])
    expected = (ACCOUNT_REPORT_RETRY_EXHAUSTED_MESSAGE
                if type(retry_count) is int and retry_count > 0
                else ACCOUNT_REPORT_INCOMPLETE_MESSAGE)
    assert stored.stage_errors["profile"] == expected
    failed = [event for event in events if event["stageKey"] == "profile"
              and event["data"]["eventType"] == "stage.failed"]
    assert failed[0]["data"]["error"] == expected
    assert "profile" not in stored.stage_results


def test_401_after_completed_overview_is_not_retried_and_persists_prior_usage(app):
    run = create_source_led_account_run(app)
    step_calls = []
    usage = {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}

    async def step(stage, system, user):
        step_calls.append(stage)
        if stage == "overview":
            return ModelCallResponse(output={
                "summary": {"text": "通过先准备材料再逐项核对的顺序，说明实际行动的过程。",
                            "noteIds": ["n1"]},
                "directions": [], "hypotheses": [],
                "readings": [{"noteId": "n1", "question": "这篇如何呈现核对过程？"}],
            }, model_metadata={"provider": "qwen", "usage": deepcopy(usage)})
        raise ValidationError("Model call failed (401)")

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile_with_updates(self, *, positioning, historical_posts, on_update):
            return await run_staged_account_report(
                {"positioning": positioning, "historicalPosts": historical_posts},
                step, on_update=on_update,
            )

    app.state.account_workflow_service.live_provider = Provider()
    events = collect(app, run["id"])
    stored = app.state.analysis_service.get(run["id"])
    metadata = stored.model_metadata["profile"]
    assert stored.status == AnalysisRunStatus.PARTIALLY_COMPLETED
    assert stored.stage_errors["profile"] == "Model call failed (401)"
    assert step_calls == ["overview", "read"]
    assert metadata["requestCount"] == 2
    assert metadata["retryCount"] == 0
    assert metadata["usage"] == usage
    assert [call["status"] for call in metadata["calls"]] == ["completed", "failed"]
    assert metadata["calls"][0]["metadata"]["usage"] == usage
    assert metadata["calls"][1]["errorCode"] == "request_failed"
    assert metadata["calls"][1]["usageUnavailable"] is True
    assert "profile" not in stored.stage_results
    assert stored.stage_results["pain_points"]["painPoints"]
    assert "progress" not in metadata
    assert all("recovery" not in event["data"] for event in events)


def test_report_exception_in_pain_points_does_not_apply_profile_recovery_policy(app):
    run = create_pending_account_run(app)
    error = AccountReportOutputError("schema_validation")
    error.pipeline_metadata = deepcopy(SAFE_PIPELINE_METADATA)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def pain_points(self, **kwargs):
            raise error

    app.state.account_workflow_service.fake_provider = Provider()
    collect(app, run["id"])
    stored = app.state.analysis_service.get(run["id"])
    assert stored.status == AnalysisRunStatus.PARTIALLY_COMPLETED
    assert stored.stage_errors["pain_points"] == str(error)
    assert "pain_points" not in stored.model_metadata
    assert stored.model_metadata["profile"] == {"engine": "langgraph"}
    assert "profile" in stored.stage_results


def test_recovery_does_not_replace_existing_completed_stage_or_historical_result(app):
    run = create_pending_account_run(app)
    collect(app, run["id"], stop_after_node="profile_analysis")
    prior = app.state.analysis_service.get(run["id"])
    prior_results = deepcopy(prior.stage_results)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile_with_updates(self, **kwargs):
            raise AssertionError("A completed profile must not be regenerated")

        async def pain_points(self, **kwargs):
            raise AssertionError("Completed pain points must not be regenerated")

    provider = Provider()
    app.state.account_workflow_service.fake_provider = provider
    collect(app, run["id"])
    stored = app.state.analysis_service.get(run["id"])
    assert stored.status == AnalysisRunStatus.COMPLETED
    for key, value in prior_results.items():
        assert stored.stage_results[key] == value
    assert provider.calls == ["topics"]
    before_replay = stored.model_dump()
    collect(app, run["id"])
    assert app.state.analysis_service.get(run["id"]).model_dump() == before_replay
    assert provider.calls == ["topics"]


def test_default_report_preserves_valid_analysis_when_optional_items_are_missing_or_bad(app):
    run = create_source_led_account_run(app)
    raw = {"profile": {"reportFormat": "source-led/v3", "accountPortrait": {
        "summary": {"statement": "用准备与核对两个动作说明做事顺序。", "evidence": [
            {"noteId": "n1", "excerptId": "b1"},
        ]},
    }, "titleReadings": [{"noteId": "n1", "parts": [
        {"text": "这个标题不存在", "role": "错误片段"},
    ]}]}}
    before = deepcopy(raw)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile(self, **kwargs):
            self.calls.append("profile")
            return raw

    provider = Provider()
    app.state.account_workflow_service.live_provider = provider
    collect(app, run["id"])
    stored = app.state.analysis_service.get(run["id"])
    assert stored.status == AnalysisRunStatus.COMPLETED
    assert provider.calls.count("profile") == 1
    result = stored.stage_results["profile"]["profile"]
    assert result["accountPortrait"]["summary"]["statement"] == before["profile"][
        "accountPortrait"
    ]["summary"]["statement"]
    assert result["titleFormulas"] == []
    assert stored.model_metadata["profile"]["omittedReportItems"]
    assert "这个标题不存在" not in str(stored.model_metadata)
    assert raw == before


def test_optional_reading_failure_does_not_block_saved_final_report(app):
    run = create_source_led_account_run(app)
    calls = []

    async def step(stage, system, user):
        calls.append(stage)
        if stage == "overview":
            return ModelCallResponse(output={"readings": [{"noteId": "n1"}]},
                                     model_metadata={"usage": {"total_tokens": 10}})
        if stage == "read":
            raise AccountReportOutputError("invalid_json", usage={"total_tokens": 5})
        return ModelCallResponse(output={"profile": {
            "reportFormat": "source-led/v3", "accountPortrait": {"summary": {
                "statement": "这篇用两个动作呈现准备与检查的顺序。",
                "evidence": [{"noteId": "n1", "excerptId": "b1"}],
            }},
        }}, model_metadata={"usage": {"total_tokens": 15}})

    class Provider(FakeAccountDiagnosisModelProvider):
        async def profile_with_updates(self, *, positioning, historical_posts, on_update):
            return await run_staged_account_report(
                {"positioning": positioning, "historicalPosts": historical_posts},
                step, on_update=on_update,
            )

    app.state.account_workflow_service.live_provider = Provider()
    collect(app, run["id"])
    stored = app.state.analysis_service.get(run["id"])
    assert stored.status == AnalysisRunStatus.COMPLETED
    assert calls == ["overview", "read", "synthesis"]
    metadata = stored.model_metadata["profile"]
    assert metadata["retryCount"] == 0
    assert metadata["requestCount"] == 3
    assert metadata["usage"]["total_tokens"] == 30
    assert metadata["omittedStages"]["read"] == 1
    assert metadata["representativeNoteIds"] == []
    assert metadata["readingAssessments"] == []
    assert "profile" not in stored.stage_errors
