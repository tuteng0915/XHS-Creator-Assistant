import asyncio
from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from test_account_langgraph_workflow import (
    collect,
    create_account_run,
    create_source_led_account_run,
)

from app.models import AnalysisRunStatus
from app.services.xhs_comment_roles import reader_comments_text
from app.workflows.account_diagnosis import (
    FakeAccountDiagnosisModelProvider,
    RealAccountDiagnosisModelProvider,
)

RETRIEVAL = {
    "phase": "feedback_retrieval", "status": "running", "completed": 0, "total": 2,
    "preview": "读者希望了解 DIY 的具体步骤。",
}
RANKING = {
    "phase": "feedback_ranking", "status": "running", "completed": 1, "total": 2,
}
OUTPUT = {"painPoints": [{
    "theme": "想了解 DIY 步骤", "intensity": "中", "count": 1,
    "evidence": ["我现在就纠结要不要DIY。"],
}]}


@pytest.mark.parametrize("failure", [None, "model", "validation"])
def test_feedback_progress_is_persisted_and_cleared_for_every_terminal_outcome(app, failure):
    run = create_account_run(app)

    class Provider(FakeAccountDiagnosisModelProvider):
        async def pain_points_with_updates(self, *, comments, source_profile, on_update):
            self.calls.append("pain_points_with_updates")
            assert comments == run["inputSnapshot"]["comments"]["content"]
            assert source_profile is None
            await on_update(RETRIEVAL)
            stored = app.state.analysis_service.get(run["id"])
            assert stored.status == AnalysisRunStatus.RUNNING
            assert "pain_points" not in stored.stage_results
            assert stored.model_metadata["pain_points"]["progress"] == RETRIEVAL
            await on_update(RANKING)
            stored = app.state.analysis_service.get(run["id"])
            assert stored.model_metadata["pain_points"]["progress"] == {
                **RANKING, "preview": RETRIEVAL["preview"],
            }
            if failure == "model":
                raise ValueError("重要反馈筛选未完成")
            return SimpleNamespace(
                output={"painPoints": [{}]} if failure == "validation" else deepcopy(OUTPUT),
                model_metadata={
                    "readerFeedbackMode": "two_stage", "requestCount": 2,
                    "calls": [{"stage": "retrieval"}, {"stage": "ranking"}],
                    "progress": RANKING,
                },
            )

    provider = Provider()
    app.state.account_workflow_service.fake_provider = provider
    events = collect(app, run["id"])
    progress = [event for event in events if event["stageKey"] == "pain_points"
                and event["data"]["eventType"] == "stage.progress"]
    assert len(progress) == 2
    assert progress[0]["data"] == {**RETRIEVAL, "eventType": "stage.progress"}
    assert progress[1]["data"] == {
        **RANKING, "preview": RETRIEVAL["preview"], "eventType": "stage.progress",
    }
    assert "eventType" not in RETRIEVAL
    assert "preview" not in RANKING
    assert "pain_points" not in provider.calls
    stored = app.state.analysis_service.get(run["id"])
    assert "progress" not in stored.model_metadata["pain_points"]
    if failure:
        assert "pain_points" not in stored.stage_results
        assert "pain_points" in stored.stage_errors
    else:
        assert stored.stage_results["pain_points"] == OUTPUT
        assert stored.model_metadata["pain_points"]["requestCount"] == 2
        assert [call["stage"] for call in stored.model_metadata["pain_points"]["calls"]] == [
            "retrieval", "ranking",
        ]
    previous_calls = list(provider.calls)
    replay = collect(app, run["id"])
    assert provider.calls == previous_calls
    assert all(event["data"]["eventType"] != "stage.progress" for event in replay)


def test_feedback_provider_receives_only_the_frozen_selected_source_profile(app):
    run = create_source_led_account_run(app)
    expected = deepcopy(run["inputSnapshot"]["xhsCreatorProfile"])

    class Provider(FakeAccountDiagnosisModelProvider):
        async def pain_points_with_updates(self, *, comments, source_profile, on_update):
            self.calls.append("pain_points_with_updates")
            assert source_profile == expected
            assert [note["noteId"] for note in source_profile["notes"]] == ["11"]
            assert comments == reader_comments_text(expected)
            return SimpleNamespace(output={"painPoints": []}, model_metadata={})

    provider = Provider()
    app.state.account_workflow_service.live_provider = provider
    collect(app, run["id"])
    stored = app.state.analysis_service.get(run["id"])
    assert provider.calls.count("pain_points_with_updates") == 1
    assert stored.input_snapshot["xhsCreatorProfile"] == expected
    assert stored.stage_results["pain_points"] == {"painPoints": []}


def test_completed_empty_feedback_is_not_retrieved_again_after_restart(app):
    run = create_account_run(app)

    class EmptyProvider(FakeAccountDiagnosisModelProvider):
        async def pain_points(self, *, comments):
            self.calls.append("pain_points")
            return {"painPoints": []}

    provider = EmptyProvider()
    app.state.account_workflow_service.fake_provider = provider
    collect(app, run["id"], stop_after_node="profile_analysis")
    interrupted = app.state.analysis_service.get(run["id"])
    assert interrupted.status == AnalysisRunStatus.RUNNING
    assert interrupted.stage_results["pain_points"] == {"painPoints": []}
    assert provider.calls.count("pain_points") == 1
    restarted = FakeAccountDiagnosisModelProvider()
    app.state.account_workflow_service.fake_provider = restarted
    collect(app, run["id"])
    assert restarted.calls == ["topics"]
    stored = app.state.analysis_service.get(run["id"])
    assert stored.stage_results["pain_points"] == {"painPoints": []}


def test_real_feedback_provider_wires_pipeline_and_retains_output_only_wrapper(monkeypatch):
    from app.services import reader_feedback_pipeline

    response = SimpleNamespace(output=deepcopy(OUTPUT), model_metadata={"requestCount": 2})
    pipeline = AsyncMock(return_value=response)
    monkeypatch.setattr(reader_feedback_pipeline, "run_reader_feedback", pipeline)
    model = SimpleNamespace(call_reader_feedback_step=AsyncMock(), call_operation=AsyncMock())
    provider = RealAccountDiagnosisModelProvider(model)
    callback = AsyncMock()
    source = {"notes": []}
    result = asyncio.run(provider.pain_points_with_updates(
        comments="评论原文", source_profile=source, on_update=callback,
    ))
    assert result is response
    pipeline.assert_awaited_once_with(
        "评论原文", source, model.call_reader_feedback_step, on_update=callback,
    )
    pipeline.reset_mock()
    assert asyncio.run(provider.pain_points(comments="旧版评论")) == OUTPUT
    pipeline.assert_awaited_once_with(
        "旧版评论", None, model.call_reader_feedback_step, on_update=None,
    )
    model.call_operation.assert_not_called()
