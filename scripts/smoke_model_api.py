#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Smoke test the configured live model API through the backend model adapter.

This script intentionally reads API keys only from environment variables and
never prints them. It exercises the same ModelCallService used by workflows and
agent conversations, so a pass here means the backend provider configuration is
usable without opening the frontend.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402
from app.errors import ApplicationError  # noqa: E402
from app.models import ModelOperation  # noqa: E402
from app.services.model_calls import ModelCallService  # noqa: E402


ENV_LINE_RE = re.compile(
    r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$"
)


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_LINE_RE.match(line)
        if not match:
            continue
        key = match.group("key")
        value = match.group("value").strip()
        if (
            (value.startswith("'") and value.endswith("'"))
            or (value.startswith('"') and value.endswith('"'))
        ):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def _mask(value: str) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return "set"
    return f"{value[:4]}...{value[-4:]}"


def _settings_summary(settings: Settings) -> dict[str, Any]:
    provider = settings.model_provider.strip().lower()
    summary: dict[str, Any] = {"provider": provider}
    if provider == "anthropic":
        summary.update(
            {
                "apiKey": _mask(settings.anthropic_api_key),
                "model": settings.anthropic_model,
                "baseUrl": settings.anthropic_base_url,
                "messagesUrl": settings.anthropic_messages_url or "(derived)",
            }
        )
    elif provider in {"qwen", "dashscope"}:
        summary.update(
            {
                "apiKey": _mask(settings.qwen_api_key),
                "model": settings.qwen_model,
                "baseUrl": settings.qwen_base_url,
            }
        )
    return summary


def _operation_from_name(name: str) -> ModelOperation:
    try:
        return ModelOperation(name)
    except ValueError as error:
        allowed = ", ".join(item.value for item in ModelOperation)
        raise SystemExit(f"Unsupported operation: {name}. Allowed: {allowed}") from error


def _default_context(operation: ModelOperation) -> dict[str, Any]:
    if operation == ModelOperation.PAIN_POINTS:
        return {"comments": "预算太高了\n不知道怎么选校\n怕中介坑我"}
    if operation == ModelOperation.AGENT_CHAT:
        return {
            "agent": {
                "agentId": "smoke_test_agent",
                "displayName": "Smoke Test Agent",
                "purpose": "验证模型接口是否可用。",
                "systemPrompt": "你只负责返回结构化 JSON。",
                "skillIds": [],
                "defaultContextPolicy": {},
            },
            "contextPack": {
                "mode": "workspace_pack",
                "scope": "smoke_test",
                "items": [],
            },
            "messages": [],
            "userMessage": "请用一句中文确认模型 API 可用。",
        }
    raise SystemExit(
        "This smoke script currently supports pain_points and agent_chat only."
    )


async def _run(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file)
    _load_env_file(env_file)
    if env_file == REPO_ROOT / ".env.local":
        _load_env_file(BACKEND_ROOT / ".env.local")
    settings = Settings.from_environment()
    operation = _operation_from_name(args.operation)
    service = ModelCallService(settings)

    print("Model API smoke test configuration:")
    print(json.dumps(_settings_summary(settings), ensure_ascii=False, indent=2))
    print(f"Operation: {operation.value}")

    try:
        response = await service.call_operation(operation, _default_context(operation))
    except ApplicationError as error:
        print(f"FAILED: {error}", file=sys.stderr)
        return 1
    except Exception as error:  # noqa: BLE001
        print(f"FAILED: {type(error).__name__}: {error}", file=sys.stderr)
        return 1

    print("Output:")
    print(json.dumps(response.output, ensure_ascii=False, indent=2))
    print("Model metadata:")
    print(json.dumps(response.model_metadata, ensure_ascii=False, indent=2))
    print("PASSED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--env-file",
        default=str(REPO_ROOT / ".env.local"),
        help=(
            "Optional env file. Default: .env.local. Values do not override "
            "existing environment variables."
        ),
    )
    parser.add_argument(
        "--operation",
        default=ModelOperation.PAIN_POINTS.value,
        help="Model operation to smoke test. Default: pain_points.",
    )
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
