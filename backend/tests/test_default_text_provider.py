import asyncio
import json

import httpx
import pytest

from app.config import Settings
from app.errors import ValidationError
from app.main import create_app
from app.models import ModelOperation
from app.services.model_calls import ModelCallService
from app.services.reader_selection import prepare_reader_selection


def defaults(tmp_path, **overrides):
    return Settings(database_path=tmp_path / "default.sqlite3", upload_directory=tmp_path,
                    **overrides)


def test_every_default_text_entry_uses_deepseek_with_no_qwen_key(tmp_path):
    configured = defaults(tmp_path, deepseek_api_key="test-only")
    app = create_app(configured)
    shared = app.state.model_call_service
    assert configured.model_provider == "deepseek"
    assert shared.settings.has_text_model_credentials
    assert shared.settings.qwen_api_key == ""
    assert shared.settings.text_model_name == "deepseek-flash"
    for workflow in (app.state.trend_workflow_service, app.state.video_workflow_service,
                     app.state.simulation_workflow_service, app.state.draft_generation_service,
                     app.state.agent_conversation_service):
        assert workflow.live_provider.model_call_service is shared
    assert app.state.audience_analysis_service.model_call_service is shared
    assert app.state.reader_selection_worker.provider.model_calls is shared
    assert app.state.panel_interview_service.live_provider.model_calls is shared
    team = app.state.content_collaboration_service.live_provider
    assert team.model_call_service is shared
    assert team.writing_model_call_service.settings.model_provider == "deepseek"
    account = app.state.account_workflow_service.live_provider.model_call_service
    assert account.settings.model_provider == "deepseek"


@pytest.mark.parametrize("provider,key,expected", [
    ("deepseek", "deepseek_api_key", True), ("deepseek", "qwen_api_key", False),
    ("qwen", "qwen_api_key", True), ("qwen", "deepseek_api_key", False),
    ("dashscope", "qwen_api_key", True), ("unknown", "deepseek_api_key", False),
])
def test_credentials_never_enable_a_different_provider(tmp_path, provider, key, expected):
    configured = defaults(tmp_path, model_provider=provider, **{key: "test"})
    assert configured.has_text_model_credentials is expected


@pytest.mark.parametrize("operation,output", [
    (ModelOperation.AUDIENCE_ANALYSIS, {"summary": "观察", "groups": [], "limitations": ""}),
    (ModelOperation.READER_SELECTION, {"proposedReaders": []}),
    (ModelOperation.SIMULATION_REACTION, {"reaction": {}}),
    (ModelOperation.SIMULATION_DEBATE, {"debateResponse": {}}),
    (ModelOperation.SIMULATION_SYNTHESIS, {"synthesis": {}}),
    (ModelOperation.PANEL_INTERVIEW, {"reply": "先看内容再回答。"}),
    (ModelOperation.CREATOR_EDIT, {"reply": "仅供采用", "update": None}),
    (ModelOperation.AGENT_CHAT, {"reply": "一起讨论", "proposedActions": []}),
])
def test_default_operations_send_only_deepseek_non_thinking_requests(
    tmp_path, monkeypatch, operation, output,
):
    service = ModelCallService(defaults(tmp_path, deepseek_api_key="test-only"))
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={
            "model": "deepseek-flash", "choices": [{"finish_reason": "stop", "message": {
                "content": json.dumps(output),
            }}],
        })

    def forbidden(*args, **kwargs):
        pytest.fail("Default text call must not use Qwen or Anthropic")

    monkeypatch.setattr(service, "_deepseek_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    monkeypatch.setattr(service, "_call_qwen", forbidden)
    monkeypatch.setattr(service, "_call_anthropic", forbidden)
    context = {}
    if operation == ModelOperation.READER_SELECTION:
        from test_reader_selection import snapshot

        context = prepare_reader_selection("w", snapshot(), []).model_dump(
            by_alias=True, mode="json",
        )
    result = asyncio.run(service.call_operation(operation, context))
    assert result.output == output
    assert result.model_metadata["provider"] == "deepseek"
    assert result.model_metadata["enableThinking"] is False
    assert len(requests) == 1
    assert requests[0].url.host == "api.deepseek.com"
    assert json.loads(requests[0].content)["thinking"] == {"type": "disabled"}


def test_missing_deepseek_does_not_enable_reader_or_interview_using_qwen(tmp_path, monkeypatch):
    app = create_app(defaults(tmp_path, qwen_api_key="not-a-fallback"))
    assert app.state.reader_selection_worker.provider is None
    assert app.state.panel_interview_service.live_provider is None
    service = app.state.model_call_service

    def forbidden(*args, **kwargs):
        pytest.fail("Missing key must fail before any HTTP request")

    monkeypatch.setattr(httpx, "AsyncClient", forbidden)
    with pytest.raises(ValidationError, match="DEEPSEEK_API_KEY"):
        asyncio.run(service.call_operation(ModelOperation.TOPICS, {}))
