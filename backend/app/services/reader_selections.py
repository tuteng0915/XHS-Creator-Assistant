"""Persistence boundary only. No scheduling, model invocation or HTTP endpoints yet."""
import json
from typing import Any, Literal

from pydantic import Field, field_validator

from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import APIModel
from app.repositories.reader_selections import ReaderSelectionRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.common import utc_now
from app.services.reader_selection import (
    ReaderSelectionInput,
    ValidatedReaderSelection,
    selection_input_hash,
    validate_reader_selection,
)

FailureCode = Literal["model_error", "invalid_output", "interrupted", "input_too_large"]


class ReaderSelectionCreate(APIModel):
    # Internal input: prepare_reader_selection must build this from account-scoped assets.
    request_key: str = Field(min_length=1, max_length=200)
    input_snapshot: ReaderSelectionInput

    @field_validator("request_key")
    @classmethod
    def nonblank_key(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("请求标识不能为空")
        return value


class ReaderSelectionResponse(APIModel):
    id: str
    workspace_id: str
    request_key: str
    input_hash: str
    input_snapshot: ReaderSelectionInput
    status: Literal["pending", "running", "completed", "partially_completed", "failed"]
    result: ValidatedReaderSelection | None
    error_code: FailureCode | None
    model_metadata: dict[str, Any]
    created_at: str
    started_at: str | None
    completed_at: str | None


class ReaderSelectionClaim(APIModel):
    """Internal worker receipt. Token must not become part of the product response."""
    selection: ReaderSelectionResponse
    token: str


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(",", ":"))


class ReaderSelectionService:
    def __init__(self, database: SQLiteDatabase):
        self.database = database
        self.repository = ReaderSelectionRepository()

    @staticmethod
    def response(row: dict) -> ReaderSelectionResponse:
        data = dict(row)
        data.pop("claim_token", None)
        data["input_snapshot"] = json.loads(data.pop("input_snapshot_json"))
        result = data.pop("result_json")
        data["result"] = json.loads(result) if result is not None else None
        data["model_metadata"] = json.loads(data.pop("model_metadata_json"))
        return ReaderSelectionResponse.model_validate(data)

    def create(self, workspace_id: str, payload: ReaderSelectionCreate) -> ReaderSelectionResponse:
        inputs = payload.input_snapshot.model_copy(deep=True)
        if inputs.workspace_id != workspace_id:
            raise ValidationError("选人输入不属于当前账号")
        with self.database.transaction() as c:
            WorkspaceRepository().get(c, workspace_id)
            return self.response(self.repository.create(
                c, workspace_id=workspace_id, request_key=payload.request_key,
                input_hash=selection_input_hash(inputs),
                snapshot_json=_json(inputs.model_dump(mode="json", by_alias=True)), now=utc_now(),
            ))

    def get(self, workspace_id: str, selection_id: str) -> ReaderSelectionResponse:
        with self.database.read() as c:
            return self.response(self.repository.get(c, workspace_id, selection_id))

    def pending(self) -> list[ReaderSelectionResponse]:
        """Worker discovery, not a public cross-account listing."""
        with self.database.read() as c:
            return [self.response(row) for row in self.repository.pending(c)]

    def claim(self, workspace_id: str, selection_id: str) -> ReaderSelectionClaim | None:
        with self.database.transaction() as c:
            row = self.repository.claim(c, workspace_id, selection_id, utc_now())
            if row is None:
                return None
            return ReaderSelectionClaim(selection=self.response(row), token=row["claim_token"])

    def complete(
        self, workspace_id: str, selection_id: str, token: str, output: Any,
        *, model_metadata: dict[str, Any] | None = None,
    ) -> ReaderSelectionResponse:
        # Validate against the stored snapshot, never against mutable current assets or a receipt.
        with self.database.transaction() as c:
            saved = self.response(self.repository.get(c, workspace_id, selection_id))
            try:
                result = validate_reader_selection(output, saved.input_snapshot)
                status = result.status
                result_json = _json(result.model_dump(mode="json", by_alias=True))
                error_code = "invalid_output" if status == "failed" else None
            except ValidationError:
                status, result_json, error_code = "failed", None, "invalid_output"
            return self.response(self.repository.finish(
                c, workspace_id=workspace_id, selection_id=selection_id, claim_token=token,
                status=status, result_json=result_json, error_code=error_code,
                metadata_json=_json(model_metadata or {}), now=utc_now(),
            ))

    def fail(
        self, workspace_id: str, selection_id: str, token: str,
        *, code: FailureCode = "model_error", model_metadata: dict[str, Any] | None = None,
    ) -> ReaderSelectionResponse:
        if code not in {"model_error", "invalid_output", "interrupted", "input_too_large"}:
            raise ValidationError("不支持的推荐失败类型")
        with self.database.transaction() as c:
            return self.response(self.repository.finish(
                c, workspace_id=workspace_id, selection_id=selection_id, claim_token=token,
                status="failed", result_json=None, error_code=code,
                metadata_json=_json(model_metadata or {}), now=utc_now(),
            ))

    def interrupt_running(self) -> int:
        """Call only during exclusive startup, not whenever a service instance is constructed."""
        with self.database.transaction() as c:
            return self.repository.interrupt_running(c, utc_now())
