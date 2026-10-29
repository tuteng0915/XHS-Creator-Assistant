import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_account_langgraph_workflow import collect, create_source_led_account_run
from test_account_report_pipeline import FakeCalls, context_for
from test_workflow_lifecycle import create_pending_account_run
from test_workspace_api import send

from app.errors import ConflictError, ValidationError
from app.services.account_recovery import recover_account
from app.services.account_report_pipeline import run_staged_account_report
from app.workflows.account_diagnosis import (
    FakeAccountDiagnosisModelProvider,
    RealAccountDiagnosisModelProvider,
)


def test_synthesis_retry_reuses_durable_overview_and_readings():
    checkpoints = []
    calls = FakeCalls()

    async def fail(stage, system, user):
        if stage == "synthesis":
            raise TimeoutError()
        return await calls(stage, system, user)

    async def update(progress):
        checkpoints.append(deepcopy(progress["checkpoint"]))

    with pytest.raises(TimeoutError):
        asyncio.run(run_staged_account_report(context_for(), fail, on_update=update))
    checkpoint = checkpoints[-1]
    assert len(checkpoint["readings"]) == 2
    calls.calls.clear()
    result = asyncio.run(run_staged_account_report(context_for(), calls, checkpoint=checkpoint))
    assert result.output["profile"]
    assert [c[0] for c in calls.calls] == ["synthesis"]
    assert result.model_metadata["requestCount"] == 1
    changed = context_for()
    changed["positioning"] = "新的账号定位"
    calls.calls.clear()
    asyncio.run(run_staged_account_report(changed, calls, checkpoint=checkpoint))
    assert calls.calls[0][0] == "overview"


def test_one_failed_reader_keeps_successful_sibling_checkpoint():
    checkpoints = []
    calls = FakeCalls()

    # Choose the actual second title, independent of fixture wording.
    second = calls.notes[1]["title"]

    async def second_fail(stage, system, user):
        if stage == "read" and second in user:
            await asyncio.sleep(0.02)
            raise TimeoutError()
        return await calls(stage, system, user)

    async def update(progress):
        checkpoints.append(progress["checkpoint"])

    with pytest.raises(TimeoutError):
        asyncio.run(run_staged_account_report(context_for(), second_fail, on_update=update))
    assert len(checkpoints[-1]["readings"]) == 1
    calls.calls.clear()
    asyncio.run(run_staged_account_report(context_for(), calls, checkpoint=checkpoints[-1]))
    assert [c[0] for c in calls.calls] == ["read", "synthesis"]


def test_recovery_is_immutable_idempotent_and_only_runs_selected_stage(app):
    run = create_pending_account_run(app)
    provider = FakeAccountDiagnosisModelProvider(failures={"profile"})
    app.state.account_workflow_service.fake_provider = provider
    collect(app, run["id"])
    source = app.state.analysis_service.get(run["id"])
    assert "profile" in source.stage_errors
    recovered = recover_account(app.state.analysis_service, source.id, "profile")
    assert recovered.input_snapshot == source.input_snapshot
    assert recover_account(app.state.analysis_service, source.id, "profile").id == recovered.id
    with pytest.raises(ConflictError):
        recover_account(app.state.analysis_service, source.id, "pain_points")
    provider = FakeAccountDiagnosisModelProvider()
    app.state.account_workflow_service.fake_provider = provider
    collect(app, recovered.id)
    assert provider.calls == ["profile"]
    result = app.state.analysis_service.get(recovered.id)
    assert result.stage_results["pain_points"] == source.stage_results["pain_points"]
    assert result.stage_results["topics"] == source.stage_results["topics"]
    assert result.model_metadata["topicsStale"] is True
    assert app.state.analysis_service.get(source.id) == source
    refresh = recover_account(app.state.analysis_service, result.id, "topics")
    provider.calls.clear()
    collect(app, refresh.id)
    assert provider.calls == ["topics"]
    with pytest.raises(ValidationError):
        recover_account(app.state.analysis_service, refresh.id, "profile")


def test_recovery_api_reuses_one_record_for_repeated_clicks(app, monkeypatch):
    run = create_pending_account_run(app)
    app.state.account_workflow_service.fake_provider = FakeAccountDiagnosisModelProvider(
        failures={"profile"},
    )
    collect(app, run["id"])
    enqueue = AsyncMock(return_value=True)
    monkeypatch.setattr(app.state.workflow_worker, "enqueue_analysis_run", enqueue)
    path = f"/api/analysis-runs/{run['id']}/recover/profile"
    first, second = send(app, "POST", path), send(app, "POST", path)
    assert first.status_code == second.status_code == 200
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["inputSnapshot"] == run["inputSnapshot"]


def test_database_checkpoint_survives_a_new_provider_and_recovers_synthesis_only(app):
    run = create_source_led_account_run(app)
    notes = [{"noteId": "11", "title": "真实标题", "body": "先准备材料，再逐项核对。"}]
    calls = FakeCalls(notes=notes, ids=("n1",),
                      readings={"n1": {"assessment": "先准备，再核对", "examples": []}},
                      synthesis={"profile": {"pillars": ["具体的准备与核对"]}})
    fail = True

    async def call(stage, system, user):
        if fail and stage == "synthesis":
            raise TimeoutError()
        return await calls(stage, system, user)

    class Provider(RealAccountDiagnosisModelProvider):
        async def pain_points_with_updates(self, **kwargs):
            return SimpleNamespace(output={"painPoints": []}, model_metadata={})

        async def topics(self, **kwargs):
            return {"topics": [], "titles": []}

    def provider():
        return Provider(SimpleNamespace(settings=SimpleNamespace(
            account_report_mode="staged", model_provider="deepseek",
        ), call_account_report_step=call))

    app.state.account_workflow_service.live_provider = provider()
    collect(app, run["id"])
    stored = app.state.analysis_service.get(run["id"])
    assert "profile" in stored.stage_errors
    assert stored.model_metadata["profile"]["pipelineCheckpoint"]["readings"]["n1"]
    recovered = recover_account(app.state.analysis_service, run["id"], "profile")
    calls.calls.clear()
    fail = False
    app.state.account_workflow_service.live_provider = provider()
    collect(app, recovered.id)
    assert [c[0] for c in calls.calls] == ["synthesis"]
    assert "profile" in app.state.analysis_service.get(recovered.id).stage_results
