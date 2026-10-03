"""Local-only response diagnostics for the single-call profile check.

No request headers, URLs, error bodies or arbitrary provider metadata are retained.
Raw model text is private source-derived content and belongs in ignored reports.
"""
from __future__ import annotations

import re

import httpx

from app.models import ModelOperation
from app.services.model_calls import MAX_TOKENS, ModelCallService


class DiagnosticProfileCalls(ModelCallService):
    def __init__(self, settings, *, transport=None):
        super().__init__(settings)
        self.transport = transport
        self.diagnostic: dict = {}
        self._secrets = [value for value in (settings.qwen_api_key, settings.anthropic_api_key)
                         if value]

    def redact(self, value):
        if isinstance(value, str):
            for secret in sorted(self._secrets, key=len, reverse=True):
                value = value.replace(secret, "[REDACTED]")
            return re.sub(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]+=*", "Bearer [REDACTED]", value)
        if isinstance(value, list):
            return [self.redact(item) for item in value]
        if isinstance(value, dict):
            return {self.redact(key): self.redact(item) for key, item in value.items()}
        return value

    async def call_operation(self, operation, context):
        self.diagnostic = {"phase": "configuration"}
        if operation != ModelOperation.PROFILE or self.settings.model_provider != "qwen":
            raise ValueError("Profile diagnostics only support the Qwen profile operation")
        response = await super().call_operation(operation, context)
        return response.model_copy(update={"model_metadata": {
            "provider": "qwen", "model": self.diagnostic.get("model", self.settings.qwen_model),
            "usage": self.diagnostic.get("usage", {}), "operation": operation.value,
        }})

    def _qwen_client(self):
        self.diagnostic.update(phase="transport", requestedMaxTokens=MAX_TOKENS[ModelOperation.PROFILE])
        return httpx.AsyncClient(timeout=90, transport=self.transport,
                                 event_hooks={"response": [self._record_response]})

    async def _record_response(self, response: httpx.Response):
        self.diagnostic.update(httpStatus=response.status_code, phase="http_status")
        if response.status_code >= 400:
            return  # Error payloads may echo credentials; status alone is retained.
        await response.aread()
        self.diagnostic["phase"] = "response_json"
        try:
            body = response.json()
        except ValueError:
            return
        if not isinstance(body, dict):
            return
        model = body.get("model")
        if isinstance(model, str):
            self.diagnostic["model"] = self.redact(model)[:200]
        usage = body.get("usage")
        if isinstance(usage, dict):
            self.diagnostic["usage"] = {
                key: usage[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                if type(usage.get(key)) is int and usage[key] >= 0
            }
        choices = body.get("choices")
        first = choices[0] if isinstance(choices, list) and choices else None
        reason = first.get("finish_reason") if isinstance(first, dict) else None
        if isinstance(reason, str):
            self.diagnostic["finishReason"] = self.redact(reason)[:64]
            self.diagnostic["providerReportedLengthLimit"] = reason == "length"

    def _extract_openai_compatible_text(self, body):
        self.diagnostic["phase"] = "content_extraction"
        text = super()._extract_openai_compatible_text(body)
        # Redact before clipping so a key crossing the boundary cannot be exposed.
        safe_text = self.redact(text)
        self.diagnostic.update(rawText=safe_text[:100_000],
                               rawTextClipped=len(safe_text) > 100_000)
        if self.diagnostic.get("providerReportedLengthLimit"):
            self.diagnostic["phase"] = "output_length"
        return text

    def _parse_model_output(self, operation, text):
        # PROFILE has no agent-chat free-text fallback. Use the same two parsers.
        self.diagnostic["phase"] = "model_json"
        value = self._parse_json(text)
        self.diagnostic["phase"] = "output_schema"
        value = self._validate_model_output(operation, value)
        self.diagnostic["phase"] = "parsed"
        return value
