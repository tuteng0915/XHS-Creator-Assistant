from __future__ import annotations

import hashlib
import json

from app.db.database import SQLiteDatabase
from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import (
    RunReviewUpdate,
    SimulationRunCreate,
    SimulationRunResponse,
    SimulationRunStatus,
    SimulationRunSummary,
)
from app.repositories.drafts import DraftRepository
from app.repositories.simulation_runs import SimulationRunRepository
from app.repositories.topics import TopicRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.account_simulation_target import account_reader_topic, account_simulation_target
from app.services.audience_evidence import AUDIENCE_METHOD_VERSION, select_audience_personas
from app.services.audience_target import reader_visible_target
from app.services.common import as_iso, utc_now
from app.services.panel_comparison import compare_panel_runs
from app.services.panel_retests import PanelRetestCreate, retest_snapshot, validate_parent
from app.services.reader_selection_adoption import selection_adoption_snapshot
from app.services.saved_note_target import saved_note_target
from app.services.simulated_fans import SimulatedFanService


class SimulationRunService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: SimulationRunRepository,
        workspace_repository: WorkspaceRepository,
        topic_repository: TopicRepository,
        draft_repository: DraftRepository,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.topic_repository = topic_repository
        self.draft_repository = draft_repository

    def create(self, workspace_id: str, payload: SimulationRunCreate) -> SimulationRunResponse:
        target_count = sum(
            1 for value in (payload.topic_id, payload.draft_id, payload.manual_topic,
                            payload.note_id, payload.account_profile_id,
                            payload.account_note_selection) if value
        )
        if target_count != 1:
            raise ValidationError("请选择一个账号、选题、草稿、历史笔记或手动标题")
        if bool(payload.source_material_id) != bool(payload.note_id):
            raise ValidationError("请选择完整的笔记来源")
        if payload.simulated_fan_ids is not None and payload.audience_analysis_id:
            raise ValidationError("模拟粉丝与旧受众分析来源不能同时选择")
        if payload.persona_overrides and not set(payload.persona_overrides).issubset(
            payload.simulated_fan_ids or [],
        ):
            raise ValidationError("只能调整本次已选择的模拟读者")
        with self.database.transaction() as connection:
            workspace = self.workspace_repository.get(connection, workspace_id)
            selection_snapshot = selection_adoption_snapshot(
                connection, self.database, workspace_id, payload,
            )
            audience = None
            audience_snapshot = None
            if payload.audience_analysis_id:
                row = connection.execute(
                    "SELECT * FROM audience_analyses WHERE id=? "
                    "AND workspace_id=? AND status IN ('completed','partially_completed')",
                    (payload.audience_analysis_id, workspace_id),
                ).fetchone()
                if row is None:
                    raise ValidationError("请选择当前账号已完成的受众分析")
                audience = json.loads(row["result_json"])
                audience_snapshot = json.loads(row["input_snapshot_json"])
            topic_snapshot: dict | None = None
            draft_snapshot: dict | None = None
            topic_id: str | None = payload.topic_id
            note_snapshot = None
            account_snapshot = None
            if payload.account_profile_id:
                account_snapshot = account_simulation_target(
                    connection, workspace_id, payload.account_profile_id,
                )
                topic_snapshot = account_reader_topic(account_snapshot)
            if payload.account_note_selection is not None:
                selection = payload.account_note_selection
                account_snapshot = account_simulation_target(
                    connection, workspace_id, selection.source_material_id,
                    selected_note_ids=selection.selected_note_ids,
                )
                topic_snapshot = account_reader_topic(account_snapshot)
            if payload.note_id:
                note_snapshot = saved_note_target(
                    connection, workspace_id, payload.source_material_id, payload.note_id,
                )
                topic_snapshot = {"topicId": None, "title": note_snapshot["title"],
                                  "body": note_snapshot["body"],
                                  "sourceWorkflow": "saved_note"}
            if payload.draft_id:
                draft = self.draft_repository.get(connection, payload.draft_id)
                if draft["workspace_id"] != workspace_id:
                    raise ValidationError("Draft belongs to another workspace")
                topic_id = draft["topic_id"]
                topic = self.topic_repository.get(connection, draft["topic_id"])
                topic_snapshot = {
                    "topicId": topic["id"],
                    "title": topic["title"],
                    "angle": topic["angle"],
                    "body": topic.get("body", ""),
                    "associatedPainPoint": topic["associated_pain_point"],
                    "whyItFits": topic["why_it_fits"],
                    "sourceWorkflow": topic["source_workflow"],
                    "updatedAt": topic["updated_at"],
                }
                draft_snapshot = {
                    "draftId": draft["id"],
                    "topicId": draft["topic_id"],
                    "generatedSnapshot": json.loads(draft["generated_snapshot_json"]),
                    "editableContent": json.loads(draft["editable_content_json"]),
                    "sourceWorkflow": draft["source_workflow"],
                    "updatedAt": draft["updated_at"],
                }
            if payload.topic_id:
                topic = self.topic_repository.get(connection, payload.topic_id)
                if topic["workspace_id"] != workspace_id:
                    raise ValidationError("Topic belongs to another workspace")
                topic_snapshot = {
                    "topicId": topic["id"],
                    "title": topic["title"],
                    "angle": topic["angle"],
                    "body": topic.get("body", ""),
                    "associatedPainPoint": topic["associated_pain_point"],
                    "whyItFits": topic["why_it_fits"],
                    "sourceWorkflow": topic["source_workflow"],
                    "updatedAt": topic["updated_at"],
                }
            snapshot = {
                "simulationMethod": AUDIENCE_METHOD_VERSION,
                "audienceAnalysisId": payload.audience_analysis_id,
                "audienceAnalysis": audience,
                "simulatedFanIds": payload.simulated_fan_ids,
                "audiencePersonas": SimulatedFanService(self.database).snapshots(
                    connection, workspace_id, payload.simulated_fan_ids,
                ) if payload.simulated_fan_ids is not None
                else select_audience_personas(audience, audience_snapshot)
                if audience
                else [],
                "mode": payload.mode,
                "workspaceId": workspace_id,
                "workspaceName": workspace["name"],
                "accountPositioning": workspace["account_positioning"],
                "simulationCategory": "account" if account_snapshot else "published_note"
                if note_snapshot else "creation",
                "targetType": "account" if account_snapshot else "note" if note_snapshot
                else "draft"
                if draft_snapshot
                else "topic"
                if topic_snapshot
                else "manual",
                "draft": draft_snapshot,
                "topic": topic_snapshot
                or {
                    "topicId": None,
                    "title": payload.manual_topic or "",
                    "angle": "",
                    "sourceWorkflow": "manual",
                },
            }
            if note_snapshot:
                snapshot["sourceNote"] = note_snapshot
            if account_snapshot:
                snapshot["sourceAccount"] = account_snapshot
            if payload.persona_overrides:
                overrides = {
                    fan_id: change.model_dump(by_alias=True, exclude_none=True)
                    for fan_id, change in payload.persona_overrides.items()
                }
                snapshot["personaOverrides"] = overrides
                for persona in snapshot["audiencePersonas"]:
                    change = overrides.get(persona["id"])
                    if change:
                        persona.update(change)
                        persona.update({"userAdjusted": True, "sessionOverride": change,
                                        "evidenceStatus": "hypothesis"})
            if selection_snapshot is not None:
                snapshot["readerSelection"] = selection_snapshot
            if payload.panel_task is not None:
                if not payload.simulated_fan_ids:
                    raise ValidationError("新试读协议需要选择已保存的模拟读者")
                snapshot["panelTask"] = payload.panel_task.model_dump(by_alias=True)
                visible = json.dumps(reader_visible_target(snapshot), ensure_ascii=False,
                                     sort_keys=True, separators=(",", ":"), allow_nan=False)
                snapshot["targetContentHash"] = hashlib.sha256(visible.encode("utf-8")).hexdigest()
            row = self.repository.create(
                connection,
                workspace_id=workspace_id,
                topic_id=topic_id,
                draft_id=payload.draft_id,
                input_snapshot_json=json.dumps(snapshot, ensure_ascii=False),
                now=utc_now(),
            )
        return self._to_response(row)

    def create_retest(
        self, workspace_id: str, parent_id: str, payload: PanelRetestCreate,
    ) -> SimulationRunResponse:
        with self.database.transaction() as connection:
            self.workspace_repository.get(connection, workspace_id)
            parent = self._to_response(self.repository.get(connection, parent_id))
            if parent.workspace_id != workspace_id:
                raise NotFoundError("试读记录不存在")
            identity = payload.identity(parent_id)
            existing = connection.execute(
                "SELECT * FROM simulation_runs WHERE workspace_id=? AND retest_request_key=?",
                (workspace_id, payload.request_key),
            ).fetchone()
            if existing is not None:
                if existing["retest_request_hash"] != identity:
                    raise ConflictError("本次复测请求已用于另一份稿件或试读，请使用新请求标识")
                return self._to_response(dict(existing))
            topic, snapshot = self._prepare_retest(connection, workspace_id, parent)
            if topic["updated_at"] != as_iso(payload.expected_updated_at):
                raise ConflictError("稿件已变化，请重新载入已保存稿件后复测")
            row = self.repository.create(
                connection, workspace_id=workspace_id, topic_id=parent.topic_id, draft_id=None,
                input_snapshot_json=json.dumps(snapshot, ensure_ascii=False), now=utc_now(),
            )
            connection.execute(
                "UPDATE simulation_runs SET parent_simulation_id=?, retest_request_key=?, "
                "retest_request_hash=? WHERE id=?",
                (parent_id, payload.request_key, identity, row["id"]),
            )
            row = self.repository.get(connection, row["id"])
        return self._to_response(row)

    def preview_retest(self, workspace_id: str, parent_id: str) -> dict:
        with self.database.read() as connection:
            parent = self._to_response(self.repository.get(connection, parent_id))
            if parent.workspace_id != workspace_id:
                raise NotFoundError("试读记录不存在")
            topic, snapshot = self._prepare_retest(connection, workspace_id, parent)
        return {
            "parentSimulationId": parent.id, "workspaceId": workspace_id,
            "topicId": topic["id"], "expectedUpdatedAt": topic["updated_at"],
            "title": topic["title"], "body": topic["body"],
            "panelTask": snapshot["panelTask"], "mode": snapshot["mode"],
            "readers": [{"id": p["id"], "name": p["name"], "profile": p["profile"]}
                        for p in snapshot["audiencePersonas"]],
            "limitations": snapshot["retest"]["comparisonLimitations"],
        }

    def compare_retest(self, workspace_id: str, simulation_id: str) -> dict:
        with self.database.read() as connection:
            child = self._to_response(self.repository.get(connection, simulation_id))
            if child.workspace_id != workspace_id:
                raise NotFoundError("试读记录不存在")
            if not child.parent_simulation_id:
                raise ValidationError("这条记录不是同组复测")
            parent = self._to_response(self.repository.get(connection, child.parent_simulation_id))
            if parent.workspace_id != workspace_id:
                raise NotFoundError("上次试读不存在")
            return compare_panel_runs(parent, child)

    def _prepare_retest(self, connection, workspace_id, parent):
        validate_parent(parent)
        topic = self.topic_repository.get(connection, parent.topic_id)
        if topic["workspace_id"] != workspace_id:
            raise NotFoundError("选题不存在")
        if topic["status"] == "archived":
            raise ValidationError("已归档选题不能复测")
        snapshot = retest_snapshot(parent, topic)
        if snapshot["targetContentHash"] == parent.input_snapshot["targetContentHash"]:
            raise ValidationError("标题和正文尚未改变，无需创建改稿复测")
        return topic, snapshot

    def list(self, workspace_id: str) -> list[SimulationRunSummary]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list(connection, workspace_id)
        return [SimulationRunSummary.model_validate({
            **row, **self._target_summary(json.loads(row["input_snapshot_json"])),
        }) for row in rows]

    def get(self, simulation_id: str) -> SimulationRunResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, simulation_id)
        return self._to_response(row)

    def update_review(self, simulation_id: str, payload: RunReviewUpdate) -> SimulationRunResponse:
        current = self.get(simulation_id)
        user_notes = payload.user_notes if payload.user_notes is not None else current.user_notes
        review_status = (
            payload.review_status.value
            if payload.review_status is not None
            else current.review_status.value
        )
        if payload.user_notes is None and payload.review_status is None:
            raise ValidationError("No review changes provided")
        with self.database.transaction() as connection:
            row = self.repository.update_review(
                connection,
                simulation_id=simulation_id,
                user_notes=user_notes,
                review_status=review_status,
                expected_updated_at=as_iso(payload.expected_updated_at),
                now=utc_now(),
            )
        return self._to_response(row)

    def save_progress(
        self,
        simulation_id: str,
        *,
        status: SimulationRunStatus,
        persona_definitions: list[dict] | None = None,
        reaction_results: list[dict] | None = None,
        debate_results: list[dict] | None = None,
        synthesis: dict | None = None,
        stage_errors: dict[str, str] | None = None,
        model_metadata: dict | None = None,
        complete: bool = False,
    ) -> SimulationRunResponse:
        current = self.get(simulation_id)
        now = utc_now()
        with self.database.transaction() as connection:
            row = self.repository.update(
                connection,
                simulation_id=simulation_id,
                status=status.value,
                persona_definitions_json=json.dumps(
                    persona_definitions
                    if persona_definitions is not None
                    else current.persona_definitions,
                    ensure_ascii=False,
                ),
                reaction_results_json=json.dumps(
                    reaction_results if reaction_results is not None else current.reaction_results,
                    ensure_ascii=False,
                ),
                debate_results_json=json.dumps(
                    debate_results if debate_results is not None else current.debate_results,
                    ensure_ascii=False,
                ),
                synthesis_json=json.dumps(
                    synthesis if synthesis is not None else current.synthesis,
                    ensure_ascii=False,
                ),
                stage_errors_json=json.dumps(
                    stage_errors if stage_errors is not None else current.stage_errors,
                    ensure_ascii=False,
                ),
                model_metadata_json=json.dumps(
                    {**current.model_metadata, **(model_metadata or {})},
                    ensure_ascii=False,
                ),
                now=now,
                completed_at=now if complete else None,
            )
        return self._to_response(row)

    @staticmethod
    def _target_summary(snapshot: dict) -> dict:
        target_type = snapshot.get("targetType")
        category = snapshot.get("simulationCategory")
        if category not in {"account", "published_note", "creation"}:
            category = ("account" if target_type == "account" else "published_note"
                        if target_type == "note" or snapshot.get("sourceNote") else "creation")
        source = (snapshot.get("sourceAccount") if category == "account"
                  else snapshot.get("sourceNote")) or {}
        return {"origin": snapshot.get("origin"), "simulation_category": category,
                "target_title": (snapshot.get("topic") or {}).get("title", ""),
                "source_material_id": source.get("sourceMaterialId"),
                "note_id": source.get("noteId")}

    @staticmethod
    def _to_response(row: dict) -> SimulationRunResponse:
        snapshot = json.loads(row["input_snapshot_json"])
        return SimulationRunResponse.model_validate(
            {
                **row,
                **SimulationRunService._target_summary(snapshot),
                "input_snapshot": snapshot,
                "persona_definitions": json.loads(row["persona_definitions_json"]),
                "reaction_results": json.loads(row["reaction_results_json"]),
                "debate_results": json.loads(row["debate_results_json"]),
                "synthesis": json.loads(row["synthesis_json"]),
                "stage_errors": json.loads(row["stage_errors_json"]),
                "model_metadata": json.loads(row["model_metadata_json"]),
            }
        )
