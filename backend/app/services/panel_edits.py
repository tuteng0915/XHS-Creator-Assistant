"""Explicit, version-checked edits from one saved Panel feedback card. No model calls."""

import hashlib
import json
from datetime import datetime
from typing import Literal
from uuid import uuid4

from pydantic import ConfigDict, Field, field_validator
from pydantic import ValidationError as SchemaError

from app.db.database import SQLiteDatabase
from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import APIModel, TopicUpdate
from app.repositories.simulation_runs import SimulationRunRepository
from app.repositories.topics import TopicRepository
from app.services.audience_target import reader_visible_target
from app.services.common import as_iso, utc_now
from app.services.proposal_lifecycle import APPLY, REJECT, UNDO, should_execute_transition


class PanelEditCreate(APIModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=1, max_length=120, strict=True)
    feedback_id: str = Field(min_length=1, max_length=120, strict=True)
    expected_updated_at: datetime
    operation: Literal["replace", "insert_before", "insert_after"]
    text: str = Field(max_length=50_000, strict=True)
    author_material: str | None = Field(default=None, max_length=50_000, strict=True)

    @field_validator("request_key", "feedback_id")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("标识不能为空")
        return value

    @field_validator("expected_updated_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("版本时间需要包含时区")
        return value


class PanelEditConfirm(APIModel):
    model_config = ConfigDict(extra="forbid")
    confirmed: bool = Field(strict=True)

    @field_validator("confirmed")
    @classmethod
    def explicit_confirmation(cls, value):
        if value is not True:
            raise ValueError("请明确确认本次操作")
        return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def topic_snapshot(topic):
    return {"title": topic["title"], "body": topic["body"], "updatedAt": topic["updated_at"]}


class PanelEditService:
    def __init__(self, database: SQLiteDatabase):
        self.database = database
        self.topics = TopicRepository()
        self.runs = SimulationRunRepository()

    def _get(self, connection, workspace_id, proposal_id):
        row = connection.execute(
            "SELECT * FROM panel_edit_proposals WHERE id=? AND workspace_id=?",
            (proposal_id, workspace_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("改稿提案不存在")
        return dict(row)

    def _response(self, connection, row):
        snapshot = json.loads(row["snapshot_json"])
        current = self.topics.get(connection, row["topic_id"])
        receipt = json.loads(row["receipt_json"])
        undo_receipt = json.loads(row["undo_receipt_json"])
        compared = receipt.get("after") if row["status"] == "applied" else snapshot["before"]
        if row["status"] == "undone":
            compared = undo_receipt.get("after")
        return {
            "id": row["id"],
            "workspaceId": row["workspace_id"],
            "simulationId": row["simulation_id"],
            "topicId": row["topic_id"],
            "status": row["status"],
            "snapshot": snapshot,
            "receipt": receipt,
            "undoReceipt": undo_receipt,
            "freshness": "current"
            if topic_snapshot(current) == compared and current["status"] != "archived"
            else "stale",
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
        }

    def get(self, workspace_id, proposal_id):
        with self.database.read() as connection:
            return self._response(connection, self._get(connection, workspace_id, proposal_id))

    def list_for_run(self, workspace_id, simulation_id):
        with self.database.read() as connection:
            run = self.runs.get(connection, simulation_id)
            if run["workspace_id"] != workspace_id:
                raise NotFoundError("模拟记录不存在")
            rows = connection.execute(
                "SELECT * FROM panel_edit_proposals WHERE workspace_id=? AND simulation_id=? "
                "ORDER BY created_at DESC, id DESC",
                (workspace_id, simulation_id),
            ).fetchall()
            return [self._response(connection, dict(row)) for row in rows]

    def create(self, workspace_id: str, simulation_id: str, payload: PanelEditCreate):
        request_json = encoded(
            {"simulationId": simulation_id,
             **payload.model_dump(mode="json", by_alias=True, exclude_none=True)}
        )
        with self.database.transaction() as connection:
            prior = connection.execute(
                "SELECT * FROM panel_edit_proposals WHERE workspace_id=? AND request_key=?",
                (workspace_id, payload.request_key),
            ).fetchone()
            if prior is not None:
                if prior["request_json"] != request_json:
                    raise ConflictError("请求标识已用于另一份改稿提案")
                return self._response(connection, dict(prior))
            run = self.runs.get(connection, simulation_id)
            if run["workspace_id"] != workspace_id:
                raise NotFoundError("模拟记录不存在")
            if json.loads(run["model_metadata_json"]).get("recovery", {}).get("summaryStale"):
                raise ConflictError("请先更新汇总，再根据新发言准备改稿")
            frozen = json.loads(run["input_snapshot_json"])
            if (
                run["status"] not in {"completed", "partially_completed"}
                or not run["topic_id"]
                or run["draft_id"]
                or not frozen.get("panelTask")
            ):
                raise ValidationError("请选择已完成的新版选题试读，暂不支持大纲或手动标题改稿")
            current = self.topics.get(connection, run["topic_id"])
            original = frozen.get("topic", {})
            if original.get("topicId") != run["topic_id"]:
                raise ValidationError("冻结稿件与选题不匹配")
            before = {
                "title": original.get("title"),
                "body": original.get("body"),
                "updatedAt": original.get("updatedAt"),
            }
            if (
                current["workspace_id"] != workspace_id
                or current["status"] == "archived"
                or topic_snapshot(current) != before
                or current["updated_at"] != as_iso(payload.expected_updated_at)
            ):
                raise ConflictError("稿件已变化，请基于当前版本重新试读后创建提案")
            synthesis = json.loads(run["synthesis_json"])
            if synthesis.get("editorFeedbackValidation", {}).get("status") not in {
                "validated",
                "partial",
            }:
                raise ValidationError("该次试读没有已核对的反馈卡")
            matches = [
                c
                for c in synthesis.get("editorFeedback", [])
                if isinstance(c, dict) and c.get("id") == payload.feedback_id
            ]
            if len(matches) != 1 or matches[0].get("kind") not in {
                "clarify",
                "rewrite",
                "add_material",
                "explore",
            }:
                raise ValidationError("请选择一条已保存的修改建议")
            card = matches[0]
            needs_material = (
                card.get("kind") == "add_material" or bool(card.get("materialRequests"))
            )
            if needs_material and (
                not payload.author_material or not payload.author_material.strip()
                or payload.author_material != payload.text
            ):
                raise ValidationError("请先填写准备加入稿件的作者素材，不能直接采用模型补写的事实")
            if not needs_material and payload.author_material is not None:
                raise ValidationError("这条建议不是补素材，请按普通改写预览")
            target = card.get("target", {})
            visible = reader_visible_target(frozen)
            content_hash = hashlib.sha256(encoded(visible).encode()).hexdigest()
            if (
                target.get("contentHash") != content_hash
                or frozen.get("targetContentHash") != content_hash
            ):
                raise ValidationError("建议与冻结稿件不匹配")
            field = target.get("field")
            if field not in {"title", "body"}:
                raise ValidationError("全文建议需要先确定具体修改位置")
            start, end, occurrence = (target.get(k) for k in ("start", "end", "occurrence"))
            quote, source = target.get("quote"), before[field]
            if (
                target.get("coordinateSystem") != "unicode_code_points"
                or any(type(n) is not int for n in (start, end, occurrence))
                or not isinstance(quote, str)
                or not quote
                or not isinstance(source, str)
                or not 0 <= start < end <= len(source)
                or occurrence < 1
                or source[start:end] != quote
            ):
                raise ValidationError("原文位置无法核对")
            # Occurrence counts overlapping matches, as in feedback validation and UI.
            position = -1
            for _ in range(occurrence):
                position = source.find(quote, position + 1)
                if position < 0:
                    raise ValidationError("原文出现序号无法核对")
            if position != start:
                raise ValidationError("原文出现序号无法核对")
            left = end if payload.operation == "insert_after" else start
            right = start if payload.operation == "insert_before" else end
            proposed = {"title": before["title"], "body": before["body"]}
            proposed[field] = source[:left] + payload.text + source[right:]
            if proposed == {k: before[k] for k in ("title", "body")}:
                raise ValidationError("这份提案没有修改内容")
            try:
                TopicUpdate(
                    title=proposed["title"],
                    body=proposed["body"],
                    expected_updated_at=payload.expected_updated_at,
                )
            except SchemaError as error:
                raise ValidationError("修改后的标题或正文超出长度限制，或标题为空") from error
            if not proposed["title"].strip():
                raise ValidationError("标题不能为空")
            snapshot = {
                "version": "panel-edit/v1",
                "feedback": card,
                "before": before,
                "proposed": proposed,
                "edit": {
                    "field": field,
                    "start": left,
                    "end": right,
                    "operation": payload.operation,
                    "text": payload.text,
                },
            }
            if needs_material:
                snapshot["authorMaterial"] = payload.author_material
            proposal_id, now = str(uuid4()), utc_now()
            connection.execute(
                "INSERT INTO panel_edit_proposals(id,workspace_id,simulation_id,topic_id,"
                "request_key,request_json,snapshot_json,created_at,updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    proposal_id,
                    workspace_id,
                    simulation_id,
                    run["topic_id"],
                    payload.request_key,
                    request_json,
                    encoded(snapshot),
                    now,
                    now,
                ),
            )
            return self._response(connection, self._get(connection, workspace_id, proposal_id))

    def apply(self, workspace_id, proposal_id):
        with self.database.transaction() as connection:
            row = self._get(connection, workspace_id, proposal_id)
            if not should_execute_transition(
                row["status"],
                APPLY,
                conflict_message="该提案已拒绝或撤销，不能再次采用",
            ):
                return self._response(
                    connection, row
                )  # Immutable original receipt, no second write.
            snapshot = json.loads(row["snapshot_json"])
            feedback = snapshot.get("feedback", {})
            if (feedback.get("kind") == "add_material" or feedback.get("materialRequests")) and (
                not str(snapshot.get("authorMaterial") or "").strip()
                or snapshot.get("authorMaterial") != snapshot.get("edit", {}).get("text")
            ):
                raise ValidationError(
                    "这份旧提案尚未记录作者素材，请重新补充素材并预览；原记录仍保留"
                )
            current = self.topics.get(connection, row["topic_id"])
            if (
                current["workspace_id"] != workspace_id
                or current["status"] == "archived"
                or topic_snapshot(current) != snapshot["before"]
            ):
                raise ConflictError("稿件已有新编辑，未应用这份旧提案")
            now = utc_now()
            updated = self.topics.update(
                connection,
                topic_id=row["topic_id"],
                angle=None,
                title=snapshot["proposed"]["title"],
                body=snapshot["proposed"]["body"],
                expected_updated_at=current["updated_at"],
                now=now,
            )
            receipt = {
                "before": snapshot["before"],
                "after": topic_snapshot(updated),
                "appliedAt": now,
            }
            connection.execute(
                "UPDATE panel_edit_proposals SET status='applied',receipt_json=?,updated_at=? "
                "WHERE id=?",
                (encoded(receipt), now, proposal_id),
            )
            return self._response(connection, self._get(connection, workspace_id, proposal_id))

    def undo(self, workspace_id, proposal_id):
        with self.database.transaction() as connection:
            row = self._get(connection, workspace_id, proposal_id)
            if not should_execute_transition(
                row["status"],
                UNDO,
                conflict_message="只有已采用的提案可以撤销",
            ):
                return self._response(connection, row)
            receipt = json.loads(row["receipt_json"])
            current = self.topics.get(connection, row["topic_id"])
            if (
                current["workspace_id"] != workspace_id
                or current["status"] == "archived"
                or topic_snapshot(current) != receipt.get("after")
            ):
                raise ConflictError("稿件在采用后已有变化，不能撤销覆盖新版本")
            before = receipt.get("before", {})
            if not isinstance(before.get("title"), str) or not isinstance(before.get("body"), str):
                raise ValidationError("原采用回执不完整，不能自动恢复")
            now = utc_now()
            restored = self.topics.update(
                connection,
                topic_id=row["topic_id"],
                angle=None,
                title=before["title"],
                body=before["body"],
                expected_updated_at=current["updated_at"],
                now=now,
            )
            undo_receipt = {
                "before": receipt["after"],
                "after": topic_snapshot(restored),
                "undoneAt": now,
            }
            connection.execute(
                "UPDATE panel_edit_proposals SET status='undone',undo_receipt_json=?,updated_at=? "
                "WHERE id=?",
                (encoded(undo_receipt), now, proposal_id),
            )
            return self._response(connection, self._get(connection, workspace_id, proposal_id))

    def reject(self, workspace_id, proposal_id):
        with self.database.transaction() as connection:
            row = self._get(connection, workspace_id, proposal_id)
            if not should_execute_transition(
                row["status"],
                REJECT,
                conflict_message="已采用或撤销的提案不能标记为拒绝",
            ):
                return self._response(connection, row)
            connection.execute(
                "UPDATE panel_edit_proposals SET status='rejected',updated_at=? WHERE id=?",
                (utc_now(), proposal_id),
            )
            return self._response(connection, self._get(connection, workspace_id, proposal_id))
