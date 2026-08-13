import asyncio
from pathlib import Path
from typing import Any

import httpx
import pytest

from app.config import Settings
from app.errors import ValidationError
from app.models import ModelOperation
from app.services.model_calls import ModelCallService


class FakeAsyncClient:
    requests: list[dict[str, Any]] = []
    response_body: dict[str, Any] = {}
    response_status_code = 200

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> "FakeAsyncClient":
        return self

    async def __aexit__(self, *args: Any) -> None:
        return None

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> httpx.Response:
        self.requests.append({"url": url, "headers": headers, "json": json})
        return httpx.Response(self.response_status_code, json=self.response_body)


def settings(**overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "database_path": Path(":memory:"),
        "upload_directory": Path(":memory:"),
    }
    values.update(overrides)
    return Settings(**values)


def test_qwen_provider_uses_openai_compatible_chat_completions(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [{"message": {"content": '{"painPoints":[]}'}}],
        "usage": {"total_tokens": 12},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="dashscope-key",
            qwen_model="qwen-plus",
        )
    )
    response = asyncio.run(
        service.call_operation(ModelOperation.PAIN_POINTS, {"comments": "中文评论"})
    )

    assert response.output == {"painPoints": []}
    assert response.model_metadata == {
        "provider": "qwen",
        "model": "qwen-plus",
        "usage": {"total_tokens": 12},
        "operation": "pain_points",
    }
    request = FakeAsyncClient.requests[0]
    assert request["url"] == (
        "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    )
    assert request["headers"]["authorization"] == "Bearer dashscope-key"
    assert request["json"]["model"] == "qwen-plus"
    assert request["json"]["response_format"] == {"type": "json_object"}
    assert request["json"]["messages"][0]["role"] == "system"
    assert request["json"]["messages"][1] == {
        "role": "user",
        "content": "中文评论",
    }


def test_qwen_provider_uses_configured_compatible_base_url_and_parses_fenced_json(
    monkeypatch,
) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [
            {
                "message": {
                    "content": (
                        "```json\n"
                        '{"painPoints":[{"theme":"预算焦虑","intensity":"高","count":2,"evidence":["太贵了"]}]}'
                        "\n```"
                    )
                }
            }
        ],
        "usage": {"input_tokens": 30, "output_tokens": 20, "total_tokens": 50},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="qwen-plus",
            qwen_base_url=(
                "https://workspace-id.cn-beijing.maas.aliyuncs.com"
                "/compatible-mode/v1"
            ),
        )
    )

    response = asyncio.run(
        service.call_operation(ModelOperation.PAIN_POINTS, {"sourceText": "太贵了\n预算不够"})
    )

    assert response.output == {
        "painPoints": [
            {
                "theme": "预算焦虑",
                "intensity": "高",
                "count": 2,
                "evidence": ["太贵了"],
            }
        ]
    }
    assert response.model_metadata["provider"] == "qwen"
    assert response.model_metadata["model"] == "qwen-plus"
    request = FakeAsyncClient.requests[0]
    assert request["url"] == (
        "https://workspace-id.cn-beijing.maas.aliyuncs.com"
        "/compatible-mode/v1/chat/completions"
    )
    assert request["json"]["model"] == "qwen-plus"
    assert request["json"]["response_format"] == {"type": "json_object"}
    assert request["json"]["messages"][1] == {
        "role": "user",
        "content": "太贵了\n预算不够",
    }


def test_qwen_provider_repairs_json_wrapped_in_prose(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [
            {
                "message": {
                    "content": (
                        "下面是 JSON 结果：\n"
                        '{"painPoints":[{"theme":"选校焦虑","intensity":"高","count":3,"evidence":["冲不冲"]}]}'
                        "\n以上供参考。"
                    )
                }
            }
        ],
        "usage": {"total_tokens": 42},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="qwen-plus",
        )
    )

    response = asyncio.run(
        service.call_operation(ModelOperation.PAIN_POINTS, {"sourceText": "冲不冲"})
    )

    assert response.output["painPoints"][0]["theme"] == "选校焦虑"


def test_agent_chat_accepts_plain_text_model_reply(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-plus",
        "choices": [{"message": {"content": "我已读取当前 workspace context。"}}],
        "usage": {"total_tokens": 16},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="qwen-plus",
        )
    )

    response = asyncio.run(
        service.call_operation(
            ModelOperation.AGENT_CHAT,
            {
                "agent": {"displayName": "测试 Agent"},
                "contextPack": {"items": []},
                "messages": [],
                "userMessage": "请确认。",
            },
        )
    )

    assert response.output == {
        "reply": "我已读取当前 workspace context。",
        "proposedActions": [],
    }
    assert response.model_metadata["operation"] == "agent_chat"


def test_qwen_provider_reports_http_errors(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 400
    FakeAsyncClient.response_body = {"error": {"message": "model not found"}}
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="qwen",
            qwen_api_key="placeholder-key",
            qwen_model="bad-model",
        )
    )

    with pytest.raises(ValidationError, match=r"Model call failed \(400\)"):
        asyncio.run(
            service.call_operation(ModelOperation.PAIN_POINTS, {"comments": "中文评论"})
        )


def test_qwen_provider_requires_api_key() -> None:
    service = ModelCallService(settings(model_provider="qwen"))

    with pytest.raises(ValidationError, match="QWEN_API_KEY or DASHSCOPE_API_KEY"):
        asyncio.run(service.call_operation(ModelOperation.PAIN_POINTS, {"comments": ""}))


def test_anthropic_provider_remains_supported(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "claude-sonnet-4-20250514",
        "content": [{"type": "text", "text": '{"painPoints":[]}'}],
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="anthropic",
            anthropic_api_key="anthropic-key",
            anthropic_model="claude-sonnet-4-20250514",
        )
    )
    response = asyncio.run(
        service.call_operation(ModelOperation.PAIN_POINTS, {"comments": "中文评论"})
    )

    assert response.output == {"painPoints": []}
    assert response.model_metadata["provider"] == "anthropic"
    request = FakeAsyncClient.requests[0]
    assert request["url"] == "https://api.anthropic.com/v1/messages"
    assert request["headers"]["x-api-key"] == "anthropic-key"


def test_anthropic_provider_can_use_compatible_base_url(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-anthropic-compatible",
        "content": [{"type": "text", "text": '{"painPoints":[]}'}],
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="anthropic",
            anthropic_api_key="compatible-key",
            anthropic_model="qwen-compatible",
            anthropic_base_url="https://example.test/apps/anthropic",
        )
    )

    asyncio.run(service.call_operation(ModelOperation.PAIN_POINTS, {"comments": "中文评论"}))

    request = FakeAsyncClient.requests[0]
    assert request["url"] == "https://example.test/apps/anthropic/v1/messages"
    assert request["headers"]["x-api-key"] == "compatible-key"
    assert request["json"]["model"] == "qwen-compatible"


def test_anthropic_provider_can_use_exact_messages_url(monkeypatch) -> None:
    FakeAsyncClient.requests = []
    FakeAsyncClient.response_status_code = 200
    FakeAsyncClient.response_body = {
        "model": "qwen-anthropic-compatible",
        "content": [{"type": "text", "text": '{"painPoints":[]}'}],
        "usage": {"input_tokens": 10, "output_tokens": 2},
    }
    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    service = ModelCallService(
        settings(
            model_provider="anthropic",
            anthropic_api_key="compatible-key",
            anthropic_model="qwen-compatible",
            anthropic_messages_url="https://example.test/apps/anthropic/v1/messages",
        )
    )

    asyncio.run(service.call_operation(ModelOperation.PAIN_POINTS, {"comments": "中文评论"}))

    request = FakeAsyncClient.requests[0]
    assert request["url"] == "https://example.test/apps/anthropic/v1/messages"
