"""Explicit, idempotent recovery of one failed unit, preserving terminal history."""

import json

from pydantic import ConfigDict, Field, field_validator

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import APIModel, SimulationRunStatus
from app.services.audience_evidence import public_reactions
from app.services.common import utc_now
from app.services.panel_protocol import panel_discussion_enabled


class PanelRecoveryCreate(APIModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(strict=True, min_length=1, max_length=120)
    stage_key: str = Field(strict=True, min_length=1, max_length=200)

    @field_validator("request_key", "stage_key")
    @classmethod
    def nonblank(cls, value):
        if not value.strip():
            raise ValueError("请求标识和重试环节不能为空")
        return value


def create_recovery(service, workspace_id, source_id, payload: PanelRecoveryCreate):
    with service.database.transaction() as connection:
        source = service._to_response(service.repository.get(connection, source_id))
        if source.workspace_id != workspace_id:
            raise NotFoundError("试读记录不存在")
        existing = connection.execute(
            "SELECT * FROM simulation_recoveries WHERE workspace_id=? AND request_key=?",
            (workspace_id, payload.request_key),
        ).fetchone()
        if existing:
            if (existing["source_run_id"], existing["stage_key"]) != (source_id, payload.stage_key):
                raise ConflictError("同一重试请求不能更换环节")
            row = service.repository.get(connection, existing["recovery_run_id"])
            return service._to_response(row)
        if source.status not in {"completed", "partially_completed", "failed"}:
            raise ConflictError("请等待本轮完成后，仅重试未完成环节")
        if "oracle_showcase" in (source.input_snapshot.get("origin"),
                                 source.model_metadata.get("origin")):
            raise ValidationError("示例记录不能重试")
        # A reload can lose the browser receipt. The immutable source/unit still
        # identifies the same attempt; retrying a failed child uses that child's ID.
        previous = connection.execute(
            "SELECT recovery_run_id FROM simulation_recoveries "
            "WHERE source_run_id=? AND stage_key=? LIMIT 1",
            (source_id, payload.stage_key),
        ).fetchone()
        if previous:
            connection.execute("INSERT INTO simulation_recoveries VALUES (?, ?, ?, ?, ?)",
                               (workspace_id, payload.request_key, source_id, payload.stage_key,
                                previous["recovery_run_id"]))
            return service._to_response(service.repository.get(connection,
                                                               previous["recovery_run_id"]))
        active = connection.execute(
            "SELECT 1 FROM simulation_recoveries r JOIN simulation_runs s "
            "ON s.id=r.recovery_run_id WHERE r.source_run_id=? "
            "AND s.status IN ('pending','running')",
            (source_id,),
        ).fetchone()
        if active:
            raise ConflictError("已有一项正在重试，请先查看该结果")
        key = payload.stage_key
        stage, _, persona_id = key.partition(".")
        stale = source.model_metadata.get("recovery", {}).get("summaryStale", False)
        summary_refresh = key == "synthesis" and bool(source.reaction_results) and (
            stale or not source.synthesis
        )
        if key not in source.stage_errors and not summary_refresh:
            raise ValidationError("只能重试失败环节或更新尚未包含新发言的汇总")
        if stage in {"initial_reactions", "debate_responses"}:
            if not persona_id or not any(p["id"] == persona_id for p in source.persona_definitions):
                raise ValidationError("重试读者不在当时名单中")
            results = (source.reaction_results if stage == "initial_reactions"
                       else source.debate_results)
            if any(r["personaId"] == persona_id for r in results):
                raise ValidationError("已完成的发言不会重新生成")
            if stage == "debate_responses" and (
                not panel_discussion_enabled(source.input_snapshot)
                or not any(r["personaId"] == persona_id for r in source.reaction_results)
                or not any(r["personaId"] != persona_id
                           for r in public_reactions(source.reaction_results))
            ):
                raise ValidationError("该读者当时没有可回应的公开发言，请先恢复试读")
        elif key not in {"personas", "synthesis"}:
            raise ValidationError("该环节不支持局部重试")
        if key == "personas" and source.persona_definitions:
            raise ValidationError("已有读者名单，不会重新生成人物")
        if key == "synthesis" and not source.reaction_results:
            raise ValidationError("请先恢复至少一位读者的试读")
        now = utc_now()
        row = service.repository.create(
            connection, workspace_id=workspace_id,
            topic_id=source.topic_id, draft_id=source.draft_id,
            input_snapshot_json=json.dumps(source.input_snapshot, ensure_ascii=False), now=now,
        )
        if source.parent_simulation_id:
            connection.execute("UPDATE simulation_runs SET parent_simulation_id=? WHERE id=?",
                               (source.parent_simulation_id, row["id"]))
        metadata = {**source.model_metadata, "recovery": {
            "sourceRunId": source_id, "stageKey": key,
            "summaryStale": bool(stale),
            "requestedAt": now,
        }}
        # The old run stays immutable, including its errors and feedback. Only
        # this new recovery record receives the selected replacement result.
        row = service.repository.update(
            connection, simulation_id=row["id"], status=SimulationRunStatus.PENDING,
            persona_definitions_json=json.dumps(source.persona_definitions, ensure_ascii=False),
            reaction_results_json=json.dumps(source.reaction_results, ensure_ascii=False),
            debate_results_json=json.dumps(source.debate_results, ensure_ascii=False),
            synthesis_json=json.dumps(source.synthesis, ensure_ascii=False),
            stage_errors_json=json.dumps({k: v for k, v in source.stage_errors.items() if k != key},
                                        ensure_ascii=False),
            model_metadata_json=json.dumps(metadata, ensure_ascii=False), now=now,
        )
        row = service.repository.update_review(
            connection, simulation_id=row["id"], user_notes=source.user_notes,
            review_status=source.review_status, expected_updated_at=row["updated_at"], now=now,
        )
        connection.execute("INSERT INTO simulation_recoveries VALUES (?, ?, ?, ?, ?)",
                           (workspace_id, payload.request_key, source_id, key, row["id"]))
        return service._to_response(row)
