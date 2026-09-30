from __future__ import annotations

import asyncio
import json
from typing import Any, Literal
from uuid import uuid4

from pydantic import Field, model_validator
from pydantic import ValidationError as SchemaError

from app.errors import NotFoundError, ValidationError
from app.models import APIModel, ModelOperation
from app.services.audience_evidence import (
    AUDIENCE_METHOD_VERSION,
    AudienceEvidence,
    ObservedEpisode,
    audience_context,
    evidence_issues,
    observed_episodes,
    validate_evidence,
)
from app.services.common import utc_now
from app.services.creator_analysis_scope import scope_creator_profile
from app.services.simulated_fans import FanDefinition, SimulatedFanService


class AudienceAnalysisCreate(APIModel):
    source_material_id: str
    scope: Literal["recent_10", "last_7_days", "last_30_days", "last_90_days", "all"] = "recent_10"


class AudienceGroup(FanDefinition):
    id: str = Field(min_length=1)
    estimated_percent: float | None = Field(default=None, ge=0, le=100)
    evidence: list[str] = Field(default_factory=list)
    evidence_refs: list[AudienceEvidence] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    observed_episodes: list[ObservedEpisode] = Field(default_factory=list)


class AudienceResult(APIModel):
    summary: str
    groups: list[AudienceGroup] = Field(min_length=1, max_length=12)
    limitations: str = Field(min_length=1)

    @model_validator(mode="after")
    def valid_distribution(self):
        if len({g.id for g in self.groups}) != len(self.groups):
            raise ValueError("受众分群 ID 不可重复")
        return self

    def grounded_result(self, context: dict) -> dict:
        for group in self.groups:
            validate_evidence(group.evidence_refs, context)
            group.evidence = list(dict.fromkeys(ref.quote for ref in group.evidence_refs))
            # Never accept model-authored historical examples, even when well formed.
            group.observed_episodes = [ObservedEpisode.model_validate(e)
                                       for e in observed_episodes(group.evidence_refs, context)]
            # Never expose uncalibrated model-generated population estimates in new runs.
            group.estimated_percent = None
        self.groups.sort(key=lambda g: (
            len({(r.note_id, r.comment_id) for r in g.evidence_refs if r.source_type == "comment"}),
            len({r.note_id for r in g.evidence_refs}),
        ), reverse=True)
        result = self.model_dump(mode="json", by_alias=True)
        result.update(method="evidence_grounded_v1", sampling=context["sampling"],
                      methodVersion=AUDIENCE_METHOD_VERSION)
        return result


class AudienceAnalysisResponse(APIModel):
    id: str
    workspace_id: str
    source_material_id: str
    status: str
    input_snapshot: dict
    result: dict
    model_metadata: dict
    diagnostics: dict = Field(default_factory=dict)
    error: str
    created_at: str
    completed_at: str | None


class AudienceEnvelope(APIModel):
    summary: str
    limitations: str = Field(min_length=1)
    groups: list[Any] = Field(min_length=1, max_length=12)


def validate_audience_output(output: dict, context: dict) -> tuple[dict, dict]:
    """Reject whole ungrounded groups, retaining independently valid groups only."""
    envelope = AudienceEnvelope.model_validate(output)
    accepted, rejected = [], []
    ids = [group.get("id") for group in envelope.groups if isinstance(group, dict)]
    for index, raw in enumerate(envelope.groups):
        try:
            group = AudienceGroup.model_validate(raw)
            issues = evidence_issues(group.evidence_refs, context)
            if ids.count(group.id) > 1:
                issues.append({"code": "duplicate_group_id", "message": "分组 ID 重复"})
        except SchemaError as error:
            issues = [{"code": "invalid_group_schema", "message": "分组格式不正确",
                       "fields": [".".join(map(str, e["loc"])) for e in error.errors()]}]
        if issues:
            raw = raw if isinstance(raw, dict) else {}
            rejected.append({
                "groupIndex": index,
                "groupId": raw.get("id") if isinstance(raw.get("id"), str) else None,
                "groupName": raw.get("name") if isinstance(raw.get("name"), str) else None,
                "issues": issues,
            })
        else:
            accepted.append(group)
    diagnostics = {"phase": "evidence_validation", "acceptedGroups": len(accepted),
                   "rejectedGroups": rejected}
    if not accepted:
        return {}, diagnostics
    summary = (envelope.summary if not rejected
               else f"已保留 {len(accepted)} 个通过原文核验的阅读视角。")
    limitations = envelope.limitations
    if rejected:
        limitations += f" 另有 {len(rejected)} 个分组未通过核验，未用于模拟粉丝或模拟。"
    result = AudienceResult(summary=summary, groups=accepted, limitations=limitations)
    return result.grounded_result(context), diagnostics


class AudienceAnalysisService:
    """Product-specific persistent analysis; requests observe an independent task."""

    def __init__(self, database, model_call_service):
        self.database = database
        self.model_call_service = model_call_service
        self.tasks: dict[str, asyncio.Task] = {}

    def create(self, workspace_id: str, payload: AudienceAnalysisCreate):
        with self.database.transaction() as c:
            source = c.execute(
                "SELECT * FROM source_materials WHERE id=? AND workspace_id=? "
                "AND type='xhs_creator_profile'",
                (payload.source_material_id, workspace_id),
            ).fetchone()
            if not source:
                raise ValidationError("请先选择当前账号的创作者档案")
            active = c.execute(
                "SELECT id FROM audience_analyses WHERE workspace_id=? "
                "AND status IN ('pending','running')",
                (workspace_id,),
            ).fetchone()
            if active:
                return self.get(active["id"])
            profile, scope = scope_creator_profile(
                json.loads(source["text_content"]), payload.scope
            )
            snapshot = {
                "scope": scope,
                "creator": profile.get("creator", {}),
                "notes": profile["notes"],
            }
            run_id = str(uuid4())
            c.execute(
                "INSERT INTO audience_analyses(id,workspace_id,source_material_id,"
                "input_snapshot_json,created_at) "
                "VALUES(?,?,?,?,?)",
                (
                    run_id,
                    workspace_id,
                    source["id"],
                    json.dumps(snapshot, ensure_ascii=False),
                    utc_now(),
                ),
            )
        self._enqueue(run_id)
        return self.get(run_id)

    def _enqueue(self, run_id):
        if run_id not in self.tasks:
            task = asyncio.create_task(self.execute(run_id))
            self.tasks[run_id] = task
            task.add_done_callback(lambda _: self.tasks.pop(run_id, None))

    def resume(self):
        with self.database.transaction() as c:
            # An interrupted call may have reached the provider. Never silently bill twice.
            c.execute(
                "UPDATE audience_analyses SET status='failed', "
                "error='服务重启中断了分析，请重新发起。', completed_at=? WHERE status='running'",
                (utc_now(),),
            )
            pending = [
                r["id"]
                for r in c.execute("SELECT id FROM audience_analyses WHERE status='pending'")
            ]
        for run_id in pending:
            self._enqueue(run_id)

    async def shutdown(self):
        tasks = list(self.tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    def get(self, run_id):
        with self.database.read() as c:
            row = c.execute("SELECT * FROM audience_analyses WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise NotFoundError("受众分析不存在")
        data = dict(row)
        data.pop("model_output_json")  # Raw provider output stays in local execution history.
        for field in ["input_snapshot", "result", "model_metadata", "diagnostics"]:
            data[field] = json.loads(data.pop(field + "_json"))
        return AudienceAnalysisResponse.model_validate(data)

    def list(self, workspace_id):
        with self.database.read() as c:
            ids = [
                r["id"]
                for r in c.execute(
                    "SELECT id FROM audience_analyses "
                    "WHERE workspace_id=? ORDER BY created_at DESC",
                    (workspace_id,),
                )
            ]
        summaries = []
        for run_id in ids:
            run = self.get(run_id)
            summaries.append(
                run.model_copy(
                    update={
                        "input_snapshot": {"scope": run.input_snapshot.get("scope", {})},
                    }
                )
            )
        return summaries

    async def execute(self, run_id):
        with self.database.transaction() as c:
            claimed = c.execute(
                "UPDATE audience_analyses SET status='running' WHERE id=? AND status='pending'",
                (run_id,),
            ).rowcount
        if not claimed:
            return
        run = self.get(run_id)
        phase = "model_call"
        try:
            context = audience_context(run.input_snapshot)
            response = await self.model_call_service.call_operation(
                ModelOperation.AUDIENCE_ANALYSIS,
                context,
            )
            # Save the response before validation so rejected output remains debuggable.
            with self.database.transaction() as c:
                c.execute(
                    "UPDATE audience_analyses SET model_output_json=?,model_metadata_json=? "
                    "WHERE id=?",
                    (json.dumps(response.output, ensure_ascii=False),
                     json.dumps(response.model_metadata), run_id),
                )
            phase = "structured_validation"
            result, diagnostics = validate_audience_output(response.output, context)
            rejected = len(diagnostics["rejectedGroups"])
            status = "partially_completed" if rejected else "completed"
            error_message = ""
            if not result:
                status = "failed"
                error_message = "所有分组的受众证据引用均未通过核验；具体原因已保存。"
            phase = "saving_result"
            with self.database.transaction() as c:
                if result:
                    SimulatedFanService(self.database).seed_initial(
                        c, run.workspace_id, run.id, result, run.input_snapshot,
                    )
                c.execute(
                    "UPDATE audience_analyses SET status=?,result_json=?,"
                    "diagnostics_json=?,error=?,completed_at=? WHERE id=?",
                    (
                        status,
                        json.dumps(result, ensure_ascii=False),
                        json.dumps(diagnostics, ensure_ascii=False),
                        error_message,
                        utc_now(),
                        run_id,
                    ),
                )
        except asyncio.CancelledError:
            raise
        except Exception as error:
            with self.database.transaction() as c:
                c.execute(
                    "UPDATE audience_analyses SET status='failed',error=?,diagnostics_json=?,"
                    "completed_at=? WHERE id=?",
                    (str(error), json.dumps({"phase": phase, "errorType": type(error).__name__}),
                     utc_now(), run_id),
                )
