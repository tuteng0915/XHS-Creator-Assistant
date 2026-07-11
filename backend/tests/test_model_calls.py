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
    assert request["json"]["messages"][0]["role"] == "system"
    assert request["json"]["messages"][1] == {
        "role": "user",
        "content": "中文评论",
    }


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
