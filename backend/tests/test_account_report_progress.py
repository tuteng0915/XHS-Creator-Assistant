import asyncio
import json
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_account_langgraph_workflow import collect, create_source_led_account_run
from test_workflow_lifecycle import create_pending_account_run
from test_workspace_api import send

from app.models import AnalysisRunStatus
from app.services.run_events import RunEventEmitter
from app.workflows.account_diagnosis import (
    SAMPLE_ACCOUNT_RESULT,
    FakeAccountDiagnosisModelProvider,
    RealAccountDiagnosisModelProvider,
)

PROGRESS = {
    "phase": "reading", "status": "running", "completed": 1, "total": 2,
    "preview": "《真实标题》：先准备，再逐项核对。",
}


@pytest.mark.parametrize("fail", [False, True])
def test_account_progress_is_durable_before_completion_and_cleared_terminally(app, fail):
    run = create_pending_account_run(app)

    class ProgressProvider(FakeAccountDiagnosisModelProvider):
        async def profile_with_updates(self, *, positioning, historical_posts, on_update):
            await on_update(PROGRESS)
            stored = app.state.analysis_service.get(run["id"])
            assert stored.status == AnalysisRunStatus.RUNNING
            assert "profile" not in stored.stage_results
            assert stored.model_metadata["profile"]["progress"] == PROGRESS
            await on_update({
                "phase": "synthesis", "status": "running", "completed": 0, "total": 1,
            })
            stored = app.state.analysis_service.get(run["id"])
            assert stored.model_metadata["profile"]["progress"]["preview"] == PROGRESS["preview"]
            if fail:
                raise ValueError("细读未能完成")
            return SimpleNamespace(
                output={"profile": deepcopy(SAMPLE_ACCOUNT_RESULT["profile"])},
                model_metadata={"accountReportMode": "staged", "calls": [{"stage": "overview"}]},
            )

    app.state.account_workflow_service.fake_provider = ProgressProvider()
    events = collect(app, run["id"])
    progress = [event for event in events if event["data"]["eventType"] == "stage.progress"]
    assert len(progress) == 2
    assert progress[0]["stageKey"] == "profile"
    assert progress[0]["status"] == "running"
    assert progress[0]["data"] == {**PROGRESS, "eventType": "stage.progress"}
    assert progress[1]["data"]["phase"] == "synthesis"
    assert progress[1]["data"]["preview"] == PROGRESS["preview"]
    assert "eventType" not in PROGRESS
    stored = app.state.analysis_service.get(run["id"])
    assert "progress" not in stored.model_metadata["profile"]
    if fail:
        assert "profile" not in stored.stage_results
        assert stored.stage_errors["profile"] == "细读未能完成"
    else:
        assert stored.model_metadata["profile"]["calls"] == [{"stage": "overview"}]
        assert stored.stage_results["profile"]["profile"]["pillars"]
        # History replays only finalized stages and never calls the provider again.
        replay = collect(app, run["id"])
        assert all(event["data"]["eventType"] != "stage.progress" for event in replay)


def test_account_sse_emits_only_changed_progress_and_no_terminal_preview(app, monkeypatch):
    run = create_pending_account_run(app)
    base = app.state.analysis_service.get(run["id"])
    first = base.model_copy(update={
        "status": AnalysisRunStatus.RUNNING,
        "model_metadata": {"profile": {"progress": deepcopy(PROGRESS)}},
    })
    next_progress = {**PROGRESS, "completed": 2, "status": "completed"}
    second = first.model_copy(update={"model_metadata": {"profile": {"progress": next_progress}}})
    # Even a stale stored preview must not be emitted after the profile finishes.
    final = second.model_copy(update={
        "status": AnalysisRunStatus.COMPLETED,
        "stage_results": {"profile": {"profile": {"pillars": ["已完成"]}}},
    })
    snapshots = iter([first, first, second, second, final])
    monkeypatch.setattr(app.state.analysis_service, "get", lambda _: next(snapshots))
    response = send(app, "GET", f"/api/analysis-runs/{run['id']}/events")
    assert response.status_code == 200
    events = [json.loads(line[6:]) for line in response.text.splitlines()
              if line.startswith("data: ")]
    progress = [event for event in events if event["data"]["eventType"] == "stage.progress"]
    assert [event["data"]["completed"] for event in progress] == [1, 2]
    assert len({event["sequence"] for event in events}) == len(events)
    assert events[-1]["data"]["eventType"] == "run.succeeded"
    assert events[-2]["data"]["eventType"] == "stage.succeeded"


def test_progress_event_contract_preserves_callback_payload():
    before = deepcopy(PROGRESS)
    event = RunEventEmitter("run", "account_diagnosis").event(
        "stage.progress", status="running", stage_key="profile", data=PROGRESS,
    )
    assert event["data"]["eventType"] == "stage.progress"
    assert before == PROGRESS


@pytest.mark.parametrize("cursor_source", ["header", "query"])
def test_progress_reconnect_replays_final_snapshot_above_old_cursor(app, cursor_source):
    run = create_pending_account_run(app)
    collect(app, run["id"])
    # A prior connection may have received many transient progress updates. Only
    # the final snapshot is available now; it must not disappear behind that cursor.
    url = f"/api/analysis-runs/{run['id']}/events"
    kwargs = {}
    if cursor_source == "header":
        kwargs["headers"] = {"Last-Event-ID": "88"}
    else:
        url += "?after=88"
    response = send(app, "GET", url, **kwargs)
    events = [json.loads(line[6:]) for line in response.text.splitlines()
              if line.startswith("data: ")]
    assert events
    assert all(event["sequence"] > 88 for event in events)
    assert events[-1]["data"]["eventType"] == "run.succeeded"
    assert events[-1]["data"]["stageResults"]["profile"]
    assert all(event["data"]["eventType"] != "stage.progress" for event in events)


@pytest.mark.parametrize("mode,structured,model_provider", [
    ("source_led", True, "qwen"),
    ("staged", False, "qwen"),
    ("staged", True, "anthropic"),
])
def test_real_provider_preserves_single_call_rollback_legacy_text_and_other_providers(
    mode, structured, model_provider,
):
    model = SimpleNamespace(settings=SimpleNamespace(
        account_report_mode=mode, model_provider=model_provider,
    ))
    provider = RealAccountDiagnosisModelProvider(model)
    provider.profile = AsyncMock(return_value={"profile": {"pillars": ["旧路径"]}})
    callback = AsyncMock()
    body = (json.dumps({"schemaVersion": "account-reading-input/v2", "notes": []})
            if structured else "旧版纯文本")
    result = asyncio.run(provider.profile_with_updates(
        positioning="账号", historical_posts=body, on_update=callback,
    ))
    assert result.output == {"profile": {"pillars": ["旧路径"]}}
    provider.profile.assert_awaited_once_with(positioning="账号", historical_posts=body)
    callback.assert_not_called()


@pytest.mark.parametrize("model_provider", ["qwen", "dashscope"])
def test_real_provider_selects_staged_pipeline_by_default_for_qwen(
    app, settings, monkeypatch, model_provider,
):
    from app.services import account_report_pipeline

    run = create_source_led_account_run(app)
    pipeline = AsyncMock(return_value=SimpleNamespace(
        output={"profile": deepcopy(SAMPLE_ACCOUNT_RESULT["profile"])},
        model_metadata={"accountReportMode": "staged", "calls": []},
    ))
    monkeypatch.setattr(account_report_pipeline, "run_staged_account_report", pipeline)
    assert settings.account_report_mode == "staged"
    model = SimpleNamespace(
        settings=SimpleNamespace(account_report_mode=settings.account_report_mode,
                                 model_provider=model_provider),
        call_account_report_step=AsyncMock(),
        call_operation=AsyncMock(),
    )
    provider = RealAccountDiagnosisModelProvider(model)
    provider.pain_points_with_updates = AsyncMock(return_value=SimpleNamespace(
        output={"painPoints": []}, model_metadata={},
    ))
    provider.topics = AsyncMock(return_value={"topics": [], "titles": []})
    app.state.account_workflow_service.live_provider = provider
    collect(app, run["id"])
    assert pipeline.await_count == 1
    context, call_step = pipeline.await_args.args
    assert call_step is model.call_account_report_step
    assert json.loads(context["historicalPosts"])["notes"][0]["noteId"] == "11"
    assert "outside-selection" not in context["historicalPosts"]
    assert callable(pipeline.await_args.kwargs["on_update"])
    model.call_operation.assert_not_called()
    stored = app.state.analysis_service.get(run["id"])
    assert stored.model_metadata["profile"]["accountReportMode"] == "staged"
