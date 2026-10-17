import asyncio
import json
from dataclasses import replace

import httpx
import pytest
from test_content_collaboration_sessions import create_workspace_and_topic, until

from app.config import Settings
from app.errors import ValidationError
from app.main import create_app
from app.models import ContentCollaborationMessageCreate, ContentCollaborationSessionCreate
from app.repositories.topics import TopicRepository
from app.services.content_collaboration import CollaborationMessage


def forbid_call(*args, **kwargs):
    pytest.fail("Writer must not use legacy Qwen or another provider as fallback")


def test_writer_default_and_environment_override_are_scoped(settings, monkeypatch):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.delenv("CREATOR_WRITING_PROVIDER", raising=False)
    monkeypatch.setenv("MODEL_PROVIDER", "qwen")
    default = Settings.from_environment()
    assert default.creator_writing_provider == "deepseek"
    assert default.for_creator_writing().model_provider == "deepseek"
    assert default.for_creator_writing().deepseek_model == "deepseek-flash"
    for provider in ("qwen", "dashscope", " DEEPSEEK "):
        monkeypatch.setenv("CREATOR_WRITING_PROVIDER", provider)
        configured = Settings.from_environment()
        assert configured.for_creator_writing().model_provider == provider.strip().lower()
        assert configured.model_provider == "qwen"
        assert configured.for_account_diagnosis().model_provider == "deepseek"
    general = replace(settings, model_provider="anthropic", account_diagnosis_provider="qwen")
    assert general.for_creator_writing().model_provider == "deepseek"
    assert general.model_provider == "anthropic"
    assert general.for_account_diagnosis().model_provider == "qwen"


@pytest.mark.parametrize("value", ["", "inherit", "anthropic", "unknown", None, True])
def test_writer_rejects_unsupported_provider(settings, value):
    with pytest.raises(ValueError, match="CREATOR_WRITING_PROVIDER"):
        replace(settings, creator_writing_provider=value)


@pytest.mark.parametrize("writer_provider", ["deepseek", "qwen"])
def test_app_keeps_writer_legacy_and_global_services_separate(settings, writer_provider):
    application = create_app(replace(
        settings, model_provider="anthropic", qwen_api_key="test-qwen",
        deepseek_api_key="test-deepseek", creator_writing_provider=writer_provider,
    ))
    provider = application.state.content_collaboration_service.live_provider
    assert application.state.model_call_service.settings.model_provider == "anthropic"
    assert provider.model_call_service.settings.model_provider == "anthropic"
    assert provider.writing_model_call_service.settings.model_provider == writer_provider
    assert provider.model_call_service is not provider.writing_model_call_service


@pytest.mark.parametrize("outer_fields", [
    {}, {"usedCandidateIds": []}, {"evidenceRefs": []},
    {"nextRecipient": "creator", "usedCandidateIds": []},
])
def test_deepseek_only_writer_persists_receipt_without_adopting_draft(
    settings, monkeypatch, outer_fields,
):
    application = create_app(replace(
        settings, deepseek_api_key="test-deepseek", qwen_api_key="",
        qwen_profile_enable_thinking=True,
    ))
    workspace, topic = create_workspace_and_topic(application)
    service = application.state.content_collaboration_service
    provider = service.live_provider
    writer = provider.writing_model_call_service
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        assert len(requests) == 1  # No mandatory statement extraction or fact editor.
        return httpx.Response(200, json={
            "model": "deepseek-flash",
            "choices": [{"finish_reason": "stop", "message": {"content": json.dumps({
                "turn": {
                    "summary": "先给一个可以编辑的开头。",
                    "nextRecipient": "creator",
                    "candidateSuggestions": [{
                        "kind": "copy_option", "title": "从一个小问题开始",
                        "body": "这里是等待作者采用的新稿。", "confidence": "inference",
                        "evidenceRefs": [],
                    }],
                },
                **outer_fields,
            }, ensure_ascii=False), "reasoning_content": "not-for-storage"}}],
        })

    monkeypatch.setattr(writer, "_deepseek_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    monkeypatch.setattr(writer, "_call_qwen", forbid_call)
    monkeypatch.setattr(writer, "_call_anthropic", forbid_call)
    monkeypatch.setattr(provider.model_call_service, "call_operation", forbid_call)
    session = service.create(workspace["id"], ContentCollaborationSessionCreate(
        assistant_mode="single_writer",
        context_target={"assetType": "topic", "assetId": topic["id"]},
    ))

    async def run():
        await service.send_message(workspace["id"], session.id,
                                   ContentCollaborationMessageCreate(
                                       content="帮我起草", recipient="writing",
                                       request_key="deepseek-writer", mode="live",
                                       creator_context_selection={"references": []},
                                   ))
        await until(lambda: service.get(workspace["id"], session.id).execution_status
                    in {"waiting_creator", "failed"})

    asyncio.run(run())
    persisted = service.get(workspace["id"], session.id)
    assert persisted.execution_status == "waiting_creator"
    assert [m.sender.value for m in persisted.messages] == ["creator", "writing"]
    receipt = persisted.messages[-1].model_metadata
    assert receipt["provider"] == "deepseek"
    assert receipt["model"] == "deepseek-flash"
    assert receipt["enableThinking"] is False
    assert receipt["contract"] == "creator-writing-turn/v1"
    assert receipt["candidateSuggestions"][0]["title"] == "从一个小问题开始"
    if outer_fields:
        assert receipt["outputNormalization"]["ignoredOuterFields"] == sorted(outer_fields)
        assert len(receipt["outputNormalization"]["originalOutputHash"]) == 64
    else:
        assert "outputNormalization" not in receipt
    assert "not-for-storage" not in persisted.model_dump_json()
    assert len(requests) == 1
    assert "factEdit" not in receipt
    assert receipt["candidateSuggestions"][0]["body"] == "这里是等待作者采用的新稿。"
    assert requests[0]["thinking"] == {"type": "disabled"}
    assert requests[0]["model"] == "deepseek-flash"
    assert requests[0]["max_tokens"] == 1800
    assert requests[0]["messages"][-1]["role"] == "user"
    with application.state.database.read() as connection:
        unchanged = TopicRepository().get(connection, topic["id"])
    assert unchanged["title"] == topic["title"]
    assert unchanged["body"] == topic["body"]
    assert unchanged["updated_at"] == topic["updated_at"]


@pytest.mark.parametrize("failure", ["missing_key", "http_error"])
def test_writer_failure_does_not_retry_or_fall_back(settings, monkeypatch, failure):
    application = create_app(replace(
        settings, qwen_api_key="available-but-not-fallback",
        deepseek_api_key="" if failure == "missing_key" else "test-deepseek",
    ))
    provider = application.state.content_collaboration_service.live_provider
    writer = provider.writing_model_call_service
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(503, json={"error": "temporary failure"})

    monkeypatch.setattr(writer, "_deepseek_client", lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(respond),
    ))
    monkeypatch.setattr(writer, "_call_qwen", forbid_call)
    monkeypatch.setattr(writer, "_call_anthropic", forbid_call)
    monkeypatch.setattr(provider.model_call_service, "call_operation", forbid_call)
    with pytest.raises(ValidationError):
        asyncio.run(provider.run(
            role="writing",
            message=CollaborationMessage(sender="creator", to="writing", content="起草"),
            context={"assistantMode": "single_writer", "target": {}, "sessionContext": {}},
        ))
    assert len(requests) == (0 if failure == "missing_key" else 1)


def test_legacy_team_does_not_use_writer_service(settings, monkeypatch):
    application = create_app(replace(settings, qwen_api_key="test-qwen"))
    provider = application.state.content_collaboration_service.live_provider
    monkeypatch.setattr(provider.writing_model_call_service, "call_operation", forbid_call)
    calls = []

    async def stop_legacy(operation, context):
        calls.append(operation)
        raise ValidationError("legacy-qwen-only")

    monkeypatch.setattr(provider.model_call_service, "call_operation", stop_legacy)
    with pytest.raises(ValidationError, match="legacy-qwen-only"):
        asyncio.run(provider.run(
            role="research",
            message=CollaborationMessage(sender="creator", to="research", content="研究"),
            context={"target": {}, "sessionContext": {}},
        ))
    assert len(calls) == 1
