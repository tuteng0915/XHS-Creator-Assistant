"""Account-only provider migration must not reroute unrelated product workflows."""

from dataclasses import replace

import httpx
import pytest
from test_account_langgraph_workflow import collect, create_account_run

from app.main import create_app
from app.models import ModelCallResponse, ModelOperation
from app.workflows.account_diagnosis import SAMPLE_ACCOUNT_RESULT


@pytest.mark.parametrize("override,expected", [
    ("deepseek", "deepseek"), ("qwen", "qwen"), ("inherit", "qwen"),
])
def test_account_scope_does_not_mutate_general_settings(settings, override, expected):
    original = replace(settings, account_diagnosis_provider=override)
    app = create_app(original)
    shared = app.state.model_call_service
    account = app.state.account_workflow_service.live_provider.model_call_service
    assert account is not shared
    assert account.settings.model_provider == expected
    assert shared.settings is original
    assert original.model_provider == "qwen"
    for service in (app.state.trend_workflow_service, app.state.video_workflow_service,
                    app.state.simulation_workflow_service, app.state.draft_generation_service,
                    app.state.agent_conversation_service):
        assert service.live_provider.model_call_service is shared
    assert app.state.audience_analysis_service.model_call_service is shared


def test_real_account_stages_keep_provider_receipts_and_replay_without_new_calls(
    settings, monkeypatch,
):
    app = create_app(replace(settings, deepseek_api_key="test-only"))
    model = app.state.account_workflow_service.live_provider.model_call_service
    calls = []

    async def operation(operation, context):
        calls.append(operation.value)
        assert model.settings.model_provider == "deepseek"
        output = ({"profile": SAMPLE_ACCOUNT_RESULT["profile"]}
                  if operation == ModelOperation.PROFILE else {
                      "topics": SAMPLE_ACCOUNT_RESULT["topics"],
                      "titles": SAMPLE_ACCOUNT_RESULT["titles"],
                  })
        return ModelCallResponse(output=output, model_metadata={
            "provider": "deepseek", "model": "deepseek-flash", "operation": operation.value,
            "usage": {"total_tokens": 10, "private_detail": "must-not-persist"},
            "reasoning_content": "must-not-persist",
        })

    async def feedback(stage, system, user):
        calls.append(stage)
        output = ({"candidates": [{"theme": "DIY 选择", "commentIds": ["c1"]}]}
                  if stage == "retrieve" else {"selectedIds": ["f1"]})
        return ModelCallResponse(output=output, model_metadata={
            "provider": "deepseek", "model": "deepseek-flash", "stage": stage,
        })

    monkeypatch.setattr(model, "call_operation", operation)
    monkeypatch.setattr(model, "call_reader_feedback_step", feedback)
    run = create_account_run(app, mode="live")
    collect(app, run["id"])
    saved = app.state.analysis_service.get(run["id"])
    assert saved.status.value == "completed"
    assert sorted(calls) == sorted(["profile", "retrieve", "rank", "topics"])
    assert saved.model_metadata["profile"]["provider"] == "deepseek"
    assert saved.model_metadata["topics"]["model"] == "deepseek-flash"
    assert "must-not-persist" not in str(saved.model_metadata)
    assert all(call["provider"] == "deepseek"
               for call in saved.model_metadata["pain_points"]["calls"])
    before = saved.model_dump()
    model.settings = replace(model.settings, model_provider="qwen")
    collect(app, run["id"])
    assert app.state.analysis_service.get(run["id"]).model_dump() == before
    assert len(calls) == 4


def test_missing_account_key_never_calls_other_provider_or_network(settings, monkeypatch):
    app = create_app(replace(settings, qwen_api_key="available-but-not-a-fallback"))
    def forbidden(*args, **kwargs):
        pytest.fail("Missing DeepSeek key must not make any network call")
    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    run = create_account_run(app, mode="live")
    collect(app, run["id"])
    saved = app.state.analysis_service.get(run["id"])
    assert saved.status.value == "failed"
    assert all("DEEPSEEK_API_KEY" in message for message in saved.stage_errors.values())
    assert not saved.stage_results
