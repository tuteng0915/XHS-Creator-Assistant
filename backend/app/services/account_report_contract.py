"""Small parsing helpers for optional account-report reading assistance.

These are not a provider JSON Schema or a final-report admission checklist.
Source membership and literal evidence remain compiler responsibilities.
"""

from __future__ import annotations

import re
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
OptionalText = Annotated[str, StringConstraints(strip_whitespace=True)]


class _AssistantOutput(BaseModel):
    model_config = ConfigDict(extra="ignore", strict=True)


class ReadingTask(_AssistantOutput):
    noteId: Text
    question: Text


class OverviewClaim(_AssistantOutput):
    text: Text
    noteIds: list[Text] = Field(min_length=1)


class OverviewSummaryClaim(OverviewClaim):
    pass


class OverviewOutput(_AssistantOutput):
    summary: OverviewSummaryClaim | None = None
    directions: list[OverviewClaim] = Field(default_factory=list)
    hypotheses: list[Text] = Field(default_factory=list)
    readings: list[ReadingTask] = Field(default_factory=list)


class ReadingExample(_AssistantOutput):
    excerptIds: list[Text] = Field(min_length=1)
    interpretation: Text


class ReadingOutput(_AssistantOutput):
    assessment: Text
    correction: OptionalText = ""
    examples: list[ReadingExample] = Field(default_factory=list)


_TOKEN_USAGE_KEYS = (
    "prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens",
    "reasoning_tokens",
)
_ERROR_MESSAGES = {
    "output_truncated": "账号报告分步输出达到长度上限，未取得完整结果。",
    "empty_output": "账号报告分步未返回可用内容。",
    "invalid_json": "账号报告分步未返回有效的 JSON 对象。",
    "invalid_response": "账号报告分步返回内容不完整。",
    "schema_validation": "账号报告分步输出不符合报告结构。",
    "source_validation": "账号报告分步输出未通过原文引用校验。",
}


def _safe_error_metadata(metadata: Any, usage: Any) -> dict[str, Any]:
    source = metadata if isinstance(metadata, dict) else {}
    result: dict[str, Any] = {}
    for key in ("provider", "operation", "stage", "model", "profileModel", "modelSource",
                "responseFormat", "responseSchema", "systemPromptHash"):
        value = source.get(key)
        if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_./:-]{1,160}", value):
            result[key] = value
    if type(source.get("enableThinking")) is bool:
        result["enableThinking"] = source["enableThinking"]
    if type(source.get("thinkingBudget")) is int and source["thinkingBudget"] >= 0:
        result["thinkingBudget"] = source["thinkingBudget"]
    counters = usage if isinstance(usage, dict) else source.get("usage")
    if isinstance(counters, dict):
        result["usage"] = {key: counters[key] for key in _TOKEN_USAGE_KEYS
                           if type(counters.get(key)) is int and counters[key] >= 0}
        for key in ("completion_tokens_details", "output_tokens_details"):
            details = counters.get(key)
            count = details.get("reasoning_tokens") if isinstance(details, dict) else None
            if "reasoning_tokens" not in result["usage"] and type(count) is int and count >= 0:
                result["usage"]["reasoning_tokens"] = count
    return result


class AccountReportOutputError(ValueError):
    """A generated-output failure eligible for bounded, stage-local recovery.

HTTP/configuration failures must never be wrapped in this exception. Only safe
identifiers and numeric counters survive; raw provider text is not retained.
"""

    def __init__(self, code: str, *, usage: dict | None = None, metadata: dict | None = None):
        self.code = code if code in _ERROR_MESSAGES else "invalid_response"
        self.metadata = _safe_error_metadata(metadata, usage)
        self.model_metadata = self.metadata
        super().__init__(_ERROR_MESSAGES[self.code])
