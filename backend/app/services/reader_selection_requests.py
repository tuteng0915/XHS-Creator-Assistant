"""Resolve a product request once, with all assets read in the same SQLite transaction."""
import json
from typing import Literal

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic import ValidationError as PydanticValidationError

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import AccountNoteSelection, APIModel, PanelTask
from app.repositories.drafts import DraftRepository
from app.repositories.simulated_fans import SimulatedFanRepository
from app.repositories.topics import TopicRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.account_simulation_target import account_reader_topic, account_simulation_target
from app.services.common import utc_now
from app.services.reader_selection import (
    ReaderSelectionInput,
    prepare_reader_selection,
    selection_input_hash,
)
from app.services.reader_selections import ReaderSelectionResponse, ReaderSelectionService
from app.services.saved_note_target import saved_note_target
from app.services.simulated_fans import SimulatedFanService


class ReaderSelectionRequest(APIModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1, max_length=200)
    topic_id: str | None = Field(default=None, min_length=1)
    draft_id: str | None = Field(default=None, min_length=1)
    manual_topic: str | None = Field(default=None, min_length=1, max_length=10000)
    source_material_id: str | None = Field(default=None, min_length=1)
    note_id: str | None = Field(default=None, min_length=1)
    account_profile_id: str | None = Field(default=None, min_length=1)
    account_note_selection: AccountNoteSelection | None = None
    desired_count: int = Field(default=3, ge=1, strict=True)
    panel_task: PanelTask | None = None

    @field_validator(
        "request_key", "topic_id", "draft_id", "manual_topic", "source_material_id", "note_id",
        "account_profile_id",
    )
    @classmethod
    def nonblank(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("请求标识或目标不能为空")
        return value

    @model_validator(mode="after")
    def one_target(self):
        if bool(self.source_material_id) != bool(self.note_id):
            raise ValueError("请选择完整的笔记来源")
        targets = (self.topic_id, self.draft_id, self.manual_topic, self.note_id,
                   self.account_profile_id, self.account_note_selection)
        if sum(value is not None for value in targets) != 1:
            raise ValueError("请选择一个账号、选题、草稿、历史笔记或手动标题")
        return self

    def identity(self) -> str:
        exclude = {"request_key"}
        if self.panel_task is None:
            exclude.add("panel_task")
        if self.note_id is None:
            exclude.update({"note_id", "source_material_id"})
        if self.account_profile_id is None:
            exclude.add("account_profile_id")
        if self.account_note_selection is None:
            exclude.add("account_note_selection")
        return json.dumps(self.model_dump(by_alias=True, exclude=exclude),
                          ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ReaderSelectionRequestService:
    def __init__(self, selections: ReaderSelectionService):
        self.selections = selections
        self.database = selections.database

    def _existing(self, c, workspace_id, payload) -> ReaderSelectionResponse | None:
        row = self.selections.repository.find_request(c, workspace_id, payload.request_key)
        if row is None:
            return None
        if row["request_json"] != payload.identity():
            raise ConflictError("这次推荐请求已使用不同目标、人数或试读任务，请发起新的推荐")
        return self.selections.response(row)

    def existing(self, workspace_id, payload) -> ReaderSelectionResponse | None:
        with self.database.read() as c:
            WorkspaceRepository().get(c, workspace_id)
            return self._existing(c, workspace_id, payload)

    def create(self, workspace_id, payload: ReaderSelectionRequest) -> ReaderSelectionResponse:
        with self.database.transaction() as c:
            WorkspaceRepository().get(c, workspace_id)
            existing = self._existing(c, workspace_id, payload)
            if existing is not None:
                return existing  # Do not re-read changed/deleted source assets on network replay.
            inputs = self.resolve_input(c, workspace_id, payload)
            row = self.selections.repository.create(
                c, workspace_id=workspace_id, request_key=payload.request_key,
                input_hash=selection_input_hash(inputs),
                snapshot_json=inputs.model_dump_json(by_alias=True),
                request_json=payload.identity(), now=utc_now(),
            )
            return self.selections.response(row)

    @staticmethod
    def resolve_input(
        c, workspace_id: str, payload: ReaderSelectionRequest,
    ) -> ReaderSelectionInput:
        workspace = WorkspaceRepository().get(c, workspace_id)
        draft = None
        topic_id = payload.topic_id
        if payload.draft_id:
            row = DraftRepository().get(c, payload.draft_id)
            if row["workspace_id"] != workspace_id:
                raise ValidationError("草稿不属于当前账号")
            topic_id = row["topic_id"]
            draft = {"editableContent": json.loads(row["editable_content_json"])}
        topic = {"title": payload.manual_topic or "", "body": ""}
        account = None
        if payload.account_profile_id:
            account = account_simulation_target(c, workspace_id, payload.account_profile_id)
            topic = account_reader_topic(account)
        if payload.account_note_selection is not None:
            selection = payload.account_note_selection
            account = account_simulation_target(
                c, workspace_id, selection.source_material_id,
                selected_note_ids=selection.selected_note_ids,
            )
            topic = account_reader_topic(account)
        if payload.note_id:
            note = saved_note_target(c, workspace_id, payload.source_material_id, payload.note_id)
            topic = {"title": note["title"], "body": note["body"]}
        if topic_id:
            row = TopicRepository().get(c, topic_id)
            if row["workspace_id"] != workspace_id:
                raise ValidationError("选题不属于当前账号")
            topic = {"title": row["title"], "body": row.get("body", "")}
        fans = [SimulatedFanService.response(row)
                for row in SimulatedFanRepository().list(c, workspace_id)]
        return prepare_reader_selection(workspace_id, {
            "workspaceId": workspace_id, "accountPositioning": workspace["account_positioning"],
            "targetType": ("account" if account else "note" if payload.note_id else "draft" if draft
                           else "topic" if topic_id else "manual"),
            "topic": topic, "draft": draft, "sourceAccount": account,
        }, fans, desired_count=payload.desired_count, panel_task=payload.panel_task)

    @staticmethod
    def stored_request(row: dict) -> ReaderSelectionRequest | None:
        if row.get("request_json") is None:
            return None
        try:
            return ReaderSelectionRequest.model_validate({
                **json.loads(row["request_json"]), "requestKey": row["request_key"],
            })
        except (ValueError, TypeError, PydanticValidationError):
            return None

    def freshness(self, c, row: dict) -> "ReaderSelectionFreshness":
        payload = self.stored_request(row)
        if payload is None:
            return ReaderSelectionFreshness(status="unavailable", reasons=["missing_source"])
        saved = self.selections.response(row).input_snapshot
        try:
            current = self.resolve_input(c, row["workspace_id"], payload)
        except (NotFoundError, ValidationError, PydanticValidationError, ValueError, TypeError):
            return ReaderSelectionFreshness(status="unavailable", reasons=["source_unavailable"])
        current_hash = selection_input_hash(current)
        reasons = []
        if current.target != saved.target:
            reasons.append("target_changed")
        if current.account_positioning != saved.account_positioning:
            reasons.append("positioning_changed")
        if current.candidates != saved.candidates:
            reasons.append("readers_changed")
        if current_hash != row["input_hash"] and not reasons:
            reasons.append("inputs_changed")
        return ReaderSelectionFreshness(
            status="stale" if reasons else "current", reasons=reasons,
            current_input_hash=current_hash,
        )

    def observe(self, workspace_id: str, selection_id: str) -> "ReaderSelectionObservation":
        with self.database.read() as c:
            c.execute("BEGIN")  # One consistent read snapshot; never writes or invokes the worker.
            row = self.selections.repository.get(c, workspace_id, selection_id)
            return ReaderSelectionObservation(
                **self.selections.response(row).model_dump(), freshness=self.freshness(c, row),
            )


class ReaderSelectionFreshness(APIModel):
    status: Literal["current", "stale", "unavailable"]
    reasons: list[Literal[
        "target_changed", "positioning_changed", "readers_changed", "inputs_changed",
        "missing_source", "source_unavailable",
    ]] = Field(default_factory=list)
    current_input_hash: str | None = None


class ReaderSelectionObservation(ReaderSelectionResponse):
    freshness: ReaderSelectionFreshness
