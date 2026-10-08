from __future__ import annotations

import json
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.errors import ValidationError
from app.models import APIModel
from app.repositories.simulated_fans import SimulatedFanRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.audience_evidence import InterestLabel, select_audience_personas
from app.services.common import as_iso
from app.services.fan_voice_templates import fan_voice_template


class FanDefinition(APIModel):
    name: str = Field(min_length=1, max_length=200)
    profile: str = Field(min_length=1, max_length=4000)
    interests: list[InterestLabel] = Field(default_factory=list, max_length=6)
    core_concern: str = Field(default="", max_length=2000)
    content_preference: str = Field(default="", max_length=2000)
    expression_style: str = Field(default="", max_length=2000)

    @field_validator("name", "profile")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("名称和阅读视角不能为空")
        return value


class FanCreate(APIModel):
    source_analysis_id: str
    source_group_id: str


class FanVariantsCreate(APIModel):
    template_ids: list[str] = Field(min_length=1)


class FanUpdate(FanDefinition):
    status: Literal["active", "archived"] = "active"
    expected_updated_at: datetime


class FanResponse(APIModel):
    id: str
    workspace_id: str
    source_analysis_id: str
    source_group_id: str
    original: dict
    editable: FanDefinition
    status: Literal["active", "archived"]
    created_at: str
    updated_at: str


class SimulatedFanService:
    def __init__(self, database):
        self.database = database
        self.repository = SimulatedFanRepository()

    @staticmethod
    def response(row):
        data = dict(row)
        data["original"] = json.loads(data.pop("original_json"))
        data["editable"] = json.loads(data.pop("editable_json"))
        return FanResponse.model_validate(data)

    def list(self, workspace_id):
        with self.database.read() as c:
            WorkspaceRepository().get(c, workspace_id)
            return [self.response(r) for r in self.repository.list(c, workspace_id)]

    def get(self, fan_id):
        with self.database.read() as c:
            return self.response(self.repository.get(c, fan_id))

    def _save_group(self, c, workspace_id, analysis_id, group, result, snapshot):
        # Reuse evidence enrichment, not model-generated or simulated comments.
        original = select_audience_personas({**result, "groups": [group]}, snapshot)[0]
        editable = FanDefinition.model_validate(original).model_dump(by_alias=True)
        return self.repository.create(c, workspace_id, analysis_id, group["id"], original, editable)

    def save_generated(self, c, workspace_id, analysis_id, result, snapshot):
        # Each analysis contributes its own roles; repository keys preserve edits on replay.
        for group in select_audience_personas(result, snapshot, limit=None):
            self._save_group(c, workspace_id, analysis_id, group, result, snapshot)

    def create(self, workspace_id, payload):
        with self.database.transaction() as c:
            row = c.execute(
                "SELECT * FROM audience_analyses WHERE id=? AND workspace_id=? "
                "AND status IN ('completed','partially_completed')",
                (payload.source_analysis_id, workspace_id),
            ).fetchone()
            if row is None:
                raise ValidationError("请选择当前账号已完成的受众分析")
            result = json.loads(row["result_json"])
            group = next(
                (g for g in result.get("groups", []) if g["id"] == payload.source_group_id), None
            )
            if group is None:
                raise ValidationError("该受众视角不存在")
            return self.response(
                self._save_group(
                    c,
                    workspace_id,
                    row["id"],
                    group,
                    result,
                    json.loads(row["input_snapshot_json"]),
                )
            )

    def create_variants(self, fan_id: str, payload: FanVariantsCreate) -> list[FanResponse]:
        if len(set(payload.template_ids)) != len(payload.template_ids):
            raise ValidationError("请勿重复选择同一种人物声音")
        templates = [fan_voice_template(template_id) for template_id in payload.template_ids]
        if any(template is None for template in templates):
            raise ValidationError("人物声音模板不存在")
        with self.database.transaction() as c:
            selected = self.response(self.repository.get(c, fan_id))
            root_id = selected.original.get("variantOfFanId")
            root = self.response(self.repository.get(c, root_id)) if root_id else selected
            if root.workspace_id != selected.workspace_id:
                raise ValidationError("人物来源不属于当前账号")
            results = []
            for template in templates:
                assert template is not None
                original = {
                    **root.original,
                    "origin": "voice_template",
                    "sourceOrigin": root.original.get("origin", "audience_analysis"),
                    "variantOfFanId": root.id,
                    "voiceTemplateId": template.id,
                    "name": f"{template.name} · {root.editable.name}"[:200],
                    "profile": (
                        f"{root.editable.profile[:2500]}\n人物设定：{template.outlook} "
                        f"判断方式：{template.decision_style} "
                        f"参与方式：{template.participation_style}"
                    )[:4000],
                    "coreConcern": root.editable.core_concern,
                    "interests": root.editable.interests,
                    "contentPreference": (
                        f"{root.editable.content_preference[:1400]} {template.decision_style}"
                    ).strip()[:2000],
                    "expressionStyle": (
                        f"{template.expression_style} {template.participation_style}"
                    )[:2000],
                    "evidenceStatus": "hypothesis",
                }
                editable = FanDefinition.model_validate(original).model_dump(by_alias=True)
                row = self.repository.create(
                    c,
                    root.workspace_id,
                    root.source_analysis_id,
                    f"{root.source_group_id}::voice:{template.id}",
                    original,
                    editable,
                )
                results.append(self.response(row))
            return results

    def update(self, fan_id, payload):
        if not payload.name.strip() or not payload.profile.strip():
            raise ValidationError("名称和阅读视角不能为空")
        editable = FanDefinition.model_validate(payload.model_dump()).model_dump(by_alias=True)
        with self.database.transaction() as c:
            current = self.response(self.repository.get(c, fan_id))
            # Older clients cannot edit interests and must not erase the saved labels.
            if "interests" not in payload.model_fields_set:
                editable["interests"] = current.editable.interests
            return self.response(
                self.repository.update(
                    c,
                    fan_id,
                    editable,
                    payload.status,
                    as_iso(payload.expected_updated_at),
                )
            )

    def snapshots(self, c, workspace_id, fan_ids):
        if not fan_ids or len(set(fan_ids)) != len(fan_ids):
            raise ValidationError("请至少选择一位模拟粉丝，且不要重复选择")
        results = []
        for fan_id in fan_ids:
            fan = self.response(self.repository.get(c, fan_id))
            if fan.workspace_id != workspace_id or fan.status != "active":
                raise ValidationError("请选择当前账号未归档的模拟粉丝")
            editable = fan.editable.model_dump(by_alias=True)
            original_editable = FanDefinition.model_validate(fan.original).model_dump(by_alias=True)
            adjusted = editable != original_editable
            results.append(
                {
                    **fan.original,
                    **editable,
                    "id": fan.id,
                    "fanAssetId": fan.id,
                    "sourceAnalysisId": fan.source_analysis_id,
                    "sourceGroupId": fan.source_group_id,
                    "updatedAt": fan.updated_at,
                    "userAdjusted": adjusted,
                    "originalDefinition": fan.original,
                    "evidenceStatus": "hypothesis" if adjusted else fan.original["evidenceStatus"],
                    "limitations": fan.original.get("limitations", "")
                    + ("；含人工设定，设定不等于真实受众证据。" if adjusted else ""),
                }
            )
        return results
