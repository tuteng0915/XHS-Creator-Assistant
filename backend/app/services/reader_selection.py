"""Pure contracts for choosing existing readers. No model, repository or API calls."""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from typing import Any, Literal

from pydantic import ConfigDict, Field, field_validator
from pydantic import ValidationError as PydanticValidationError

from app.errors import ValidationError
from app.models import APIModel, PanelTask
from app.services.audience_target import reader_visible_target
from app.services.simulated_fans import FanDefinition, FanResponse

SELECTOR_VERSION = "saved_readers_v1"


class ReaderCandidate(FanDefinition):
    id: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)


class ReaderSelectionInput(APIModel):
    panel_task: PanelTask | None = None
    workspace_id: str = Field(min_length=1)
    account_positioning: str
    target: dict[str, Any]
    candidates: list[ReaderCandidate]
    desired_count: int = Field(default=3, ge=1, strict=True)
    selector_version: Literal["saved_readers_v1"] = SELECTOR_VERSION


class ProposedReader(APIModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    fan_id: str = Field(min_length=1)
    fit_reason: str = Field(min_length=1, max_length=200)
    contribution: str = Field(min_length=1, max_length=200)
    relation: Literal["direct", "adjacent"]

    @field_validator("fan_id", "fit_reason", "contribution")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("推荐字段不能为空")
        return value


class ReaderSelectionOutput(APIModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    proposed_readers: list[Any]
    unmatched_reason: str = Field(default="", max_length=400)


class SelectionWarning(APIModel):
    index: int
    code: Literal["invalid_item", "unknown_reader", "duplicate_reader"]


class ValidatedReaderSelection(APIModel):
    status: Literal["completed", "partially_completed", "failed"]
    proposed_readers: list[ProposedReader]
    unmatched_reason: str
    validation_warnings: list[SelectionWarning]


def prepare_reader_selection(
    workspace_id: str, snapshot: dict[str, Any], fans: Sequence[FanResponse],
    *, desired_count: int = 3, panel_task: PanelTask | None = None,
) -> ReaderSelectionInput:
    if not workspace_id or snapshot.get("workspaceId") != workspace_id:
        raise ValidationError("选题快照不属于当前账号")
    candidates = []
    seen = set()
    for fan in fans:
        if fan.workspace_id != workspace_id:
            raise ValidationError("读者池包含其他账号的角色")
        if fan.status != "active":
            continue
        if not fan.id.strip() or not fan.updated_at.strip() or fan.id in seen:
            raise ValidationError("读者池包含缺少身份、版本或重复的角色")
        seen.add(fan.id)
        candidates.append(ReaderCandidate(
            **fan.editable.model_dump(), id=fan.id, updated_at=fan.updated_at,
        ))
    return ReaderSelectionInput(
        workspace_id=workspace_id, account_positioning=snapshot.get("accountPositioning", ""),
        target=reader_visible_target(snapshot), candidates=candidates, desired_count=desired_count,
        panel_task=panel_task,
    ).model_copy(deep=True)


def selection_input_hash(inputs: ReaderSelectionInput) -> str:
    # Do not invalidate persisted v1 hashes by injecting a new null/default task.
    exclude = {"panel_task"} if inputs.panel_task is None else set()
    encoded = json.dumps(inputs.model_dump(mode="json", by_alias=True, exclude=exclude),
                         ensure_ascii=False,
                         sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_reader_selection(
    output: Any, inputs: ReaderSelectionInput,
) -> ValidatedReaderSelection:
    try:
        envelope = ReaderSelectionOutput.model_validate(output)
    except PydanticValidationError as error:
        raise ValidationError("读者推荐结果结构无效") from error
    if len(envelope.proposed_readers) > inputs.desired_count:
        raise ValidationError("推荐人数超过本次请求，未自动裁剪")
    if not envelope.proposed_readers and not envelope.unmatched_reason.strip():
        raise ValidationError("无匹配时需要说明原因")
    allowed = {candidate.id for candidate in inputs.candidates}
    # Reject every occurrence of ambiguous duplicate IDs, rather than picking a reason arbitrarily.
    ids = [row.get("fanId", row.get("fan_id")) for row in envelope.proposed_readers
           if isinstance(row, dict)]
    counts = Counter(value for value in ids if isinstance(value, str))
    accepted, warnings = [], []
    for index, row in enumerate(envelope.proposed_readers):
        try:
            proposed = ProposedReader.model_validate(row)
        except PydanticValidationError:
            warnings.append(SelectionWarning(index=index, code="invalid_item"))
            continue
        code = ("unknown_reader" if proposed.fan_id not in allowed
                else "duplicate_reader" if counts[proposed.fan_id] > 1 else None)
        if code:
            warnings.append(SelectionWarning(index=index, code=code))
        else:
            accepted.append(proposed.model_copy(deep=True))
    return ValidatedReaderSelection(
        status=("partially_completed" if accepted else "failed") if warnings else "completed",
        proposed_readers=accepted, unmatched_reason=envelope.unmatched_reason,
        validation_warnings=warnings,
    )
