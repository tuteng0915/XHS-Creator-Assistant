"""Local-only response diagnostics for the single-call profile check.

No request headers, URLs, error bodies or arbitrary provider metadata are retained.
Raw model text is private source-derived content and belongs in ignored reports.
"""
from __future__ import annotations

import json
import re
import time

import httpx

from app.models import ModelOperation
from app.services.model_calls import MAX_TOKENS, ModelCallService

TRACE_OPERATIONS = {
    "connection": {"connect_tcp", "start_tls"},
    "proxy": {"start_tls"},
    "http11": {"send_request_headers", "send_request_body",
               "receive_response_headers", "receive_response_body"},
    "http2": {"send_request_headers", "send_request_body",
              "receive_response_headers", "receive_response_body"},
}
MAX_TRACE_EVENTS = 128


class DiagnosticProfileCalls(ModelCallService):
    def __init__(self, settings, *, transport=None, read_timeout_seconds=90):
        if type(read_timeout_seconds) is not int or not 1 <= read_timeout_seconds <= 300:
            raise ValueError("read_timeout_seconds must be an integer from 1 to 300")
        super().__init__(settings)
        self.transport = transport
        self.read_timeout_seconds = read_timeout_seconds
        self.diagnostic: dict = {}
        self._started: float | None = None
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
        self._started = time.monotonic()
        try:
            response = await super().call_operation(operation, context)
        except Exception as error:
            self.diagnostic["failureType"] = type(error).__name__
            raise
        finally:
            self._mark("finishedMs")
        return response.model_copy(update={"model_metadata": {
            "provider": "qwen", "model": self.diagnostic.get("model", self.settings.qwen_model),
            "usage": self.diagnostic.get("usage", {}), "operation": operation.value,
        }})

    def _qwen_client(self, operation):
        self.diagnostic.update(
            phase="transport", requestedMaxTokens=MAX_TOKENS[ModelOperation.PROFILE],
        )
        self.diagnostic["timeoutsSeconds"] = {
            "connect": 90, "read": self.read_timeout_seconds, "write": 90, "pool": 90,
        }  # These are per-operation limits, not a total request deadline.
        return httpx.AsyncClient(timeout=httpx.Timeout(90, read=self.read_timeout_seconds),
                                 transport=self.transport,
                                 event_hooks={"request": [self._record_request],
                                              "response": [self._record_response]})

    def _mark(self, name):
        if self._started is not None:
            self.diagnostic.setdefault("timings", {})[name] = round(
                (time.monotonic() - self._started) * 1000, 3,
            )

    async def _record_request(self, request: httpx.Request):
        self._mark("requestPreparedMs")
        request.extensions["trace"] = self._record_network_event
        payload = json.loads(request.content)
        text = "".join(message.get("content", "") for message in payload.get("messages", [])
                       if isinstance(message.get("content"), str))
        self.diagnostic["sizes"] = {
            "requestBodyBytes": len(request.content),
            "promptTextCharacters": len(text),
            "promptTextUtf8Bytes": len(text.encode("utf-8")),
        }
        # The request hook runs before network I/O; this does not prove it was sent.
        self.diagnostic["waitingFor"] = "response_headers"

    async def _record_network_event(self, name: str, info: dict):
        # Never serialize info: it contains hosts, headers, streams and exceptions.
        # Repeated events may describe a proxy CONNECT, not the model request.
        parts = name.split(".")
        if (len(parts) != 3 or parts[1] not in TRACE_OPERATIONS.get(parts[0], set())
                or parts[2] not in {"started", "complete", "failed"}
                or self._started is None):
            return
        events = self.diagnostic.setdefault("networkEvents", [])
        if len(events) >= MAX_TRACE_EVENTS:
            self.diagnostic["networkEventsTruncated"] = True
            return
        events.append({"event": name, "elapsedMs": round(
            (time.monotonic() - self._started) * 1000, 3,
        )})

    async def _record_response(self, response: httpx.Response):
        self._mark("responseHeadersMs")
        self.diagnostic.update(httpStatus=response.status_code, phase="http_status")
        self.diagnostic["waitingFor"] = "response_body"
        if response.status_code < 400:
            self.diagnostic["phase"] = "response_body"
        await response.aread()
        self._mark("responseBodyMs")
        self.diagnostic["waitingFor"] = None
        self.diagnostic.setdefault("sizes", {})["responseBodyBytes"] = len(response.content)
        if response.status_code >= 400:
            return  # Error payloads may echo credentials; status alone is retained.
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
        self._mark("parsedMs")
        return value
