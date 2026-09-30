import json
from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from app.errors import ValidationError
from app.models import APIModel
from app.repositories.simulated_fans import SimulatedFanRepository
from app.repositories.workspaces import WorkspaceRepository
from app.services.audience_evidence import select_audience_personas
from app.services.common import as_iso


class FanDefinition(APIModel):
    name: str = Field(min_length=1, max_length=200)
    profile: str = Field(min_length=1, max_length=4000)
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

    def seed_initial(self, c, workspace_id, analysis_id, result, snapshot):
        # Archived or manually adjusted profiles still count: never silently reseed/overwrite.
        if self.repository.list(c, workspace_id):
            return
        for group in select_audience_personas(result, snapshot):
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
            group = next((g for g in result.get("groups", [])
                          if g["id"] == payload.source_group_id), None)
            if group is None:
                raise ValidationError("该受众视角不存在")
            return self.response(self._save_group(
                c, workspace_id, row["id"], group, result, json.loads(row["input_snapshot_json"]),
            ))

    def update(self, fan_id, payload):
        if not payload.name.strip() or not payload.profile.strip():
            raise ValidationError("名称和阅读视角不能为空")
        editable = FanDefinition.model_validate(payload.model_dump()).model_dump(by_alias=True)
        with self.database.transaction() as c:
            self.repository.get(c, fan_id)
            return self.response(self.repository.update(
                c, fan_id, editable, payload.status, as_iso(payload.expected_updated_at),
            ))

    def snapshots(self, c, workspace_id, fan_ids):
        if not fan_ids or len(fan_ids) > 3 or len(set(fan_ids)) != len(fan_ids):
            raise ValidationError("请选择 1 至 3 位不同的模拟粉丝")
        results = []
        for fan_id in fan_ids:
            fan = self.response(self.repository.get(c, fan_id))
            if fan.workspace_id != workspace_id or fan.status != "active":
                raise ValidationError("请选择当前账号未归档的模拟粉丝")
            editable = fan.editable.model_dump(by_alias=True)
            original_editable = FanDefinition.model_validate(fan.original).model_dump(by_alias=True)
            adjusted = editable != original_editable
            results.append({
                **fan.original, **editable, "id": fan.id, "fanAssetId": fan.id,
                "sourceAnalysisId": fan.source_analysis_id, "updatedAt": fan.updated_at,
                "userAdjusted": adjusted, "originalDefinition": fan.original,
                "evidenceStatus": "hypothesis" if adjusted else fan.original["evidenceStatus"],
                "limitations": fan.original.get("limitations", "")
                + ("；含人工设定，设定不等于真实受众证据。" if adjusted else ""),
            })
        return results
