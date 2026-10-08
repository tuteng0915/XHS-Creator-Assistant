"""Fixed-panel retest inputs. Only saved text changes; prior answers never enter the input."""

import hashlib
import json
from copy import deepcopy
from datetime import datetime

from pydantic import ConfigDict, Field, field_validator
from pydantic import ValidationError as SchemaError

from app.errors import ValidationError
from app.models import APIModel, PanelTask, SimulationRunResponse
from app.services.audience_evidence import AUDIENCE_METHOD_VERSION
from app.services.audience_target import reader_visible_target
from app.services.common import as_iso
from app.services.panel_personas import PersonaDefinitionsResult


def digest(value) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class PanelRetestCreate(APIModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(strict=True, min_length=1, max_length=120)
    expected_updated_at: datetime
    confirmed: bool = Field(strict=True)

    @field_validator("request_key")
    @classmethod
    def nonblank_key(cls, value):
        if not value.strip():
            raise ValueError("请求标识不能为空")
        return value

    @field_validator("expected_updated_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("版本时间需要包含时区")
        return value

    @field_validator("confirmed")
    @classmethod
    def confirmation_required(cls, value):
        if value is not True:
            raise ValueError("请确认使用当时人物和任务复测当前已保存稿件")
        return value

    def identity(self, parent_id: str) -> str:
        return digest({"parentSimulationId": parent_id,
                       "expectedUpdatedAt": as_iso(self.expected_updated_at)})


def validate_parent(parent: SimulationRunResponse) -> None:
    source = parent.input_snapshot
    if parent.status not in {"completed", "partially_completed"}:
        raise ValidationError("请选择已完成或部分完成的试读进行同组复测")
    if (source.get("targetType") != "topic" or not parent.topic_id or parent.draft_id
            or source.get("draft") is not None):
        raise ValidationError("同组复测目前只支持已保存的选题正文")
    try:
        task = PanelTask.model_validate(source.get("panelTask"))
        personas = PersonaDefinitionsResult(personas=parent.persona_definitions)
        normalized = personas.model_dump(mode="json", by_alias=True)["personas"]
        topic = source["topic"]
        source_ids = [p["id"] for p in source["audiencePersonas"]]
        if (task.model_dump(by_alias=True) != source["panelTask"]
                or normalized != parent.persona_definitions
                or not all(p.id.strip() and p.name.strip() and p.profile.strip()
                           and p.fanAssetId == p.id and p.updatedAt for p in personas.personas)
                or source_ids != [p.id for p in personas.personas]
                or source_ids != source["simulatedFanIds"]
                or topic["topicId"] != parent.topic_id
                or not isinstance(topic["title"], str) or not isinstance(topic["body"], str)
                or not topic["updatedAt"]
                or source["workspaceId"] != parent.workspace_id
                or not isinstance(source["accountPositioning"], str)
                or source["mode"] not in {"demo", "live"}
                or source["simulationMethod"] != AUDIENCE_METHOD_VERSION
                or digest(reader_visible_target(source)) != source["targetContentHash"]):
            raise ValueError("incomplete or incompatible snapshot")
    except (SchemaError, ValueError, KeyError, TypeError) as error:
        raise ValidationError(
            "当时人物、稿件或阅读任务快照不完整，不能严格同组复测；请新建试读",
        ) from error


def retest_snapshot(parent: SimulationRunResponse, topic: dict) -> dict:
    source = parent.input_snapshot
    # Allowlist inputs: no old reactions, replies, feedback or recommendation rationale.
    snapshot = {
        "simulationMethod": source["simulationMethod"],
        "audienceAnalysisId": None,
        "audienceAnalysis": None,
        "audiencePersonas": deepcopy(parent.persona_definitions),
        "simulatedFanIds": list(source["simulatedFanIds"]),
        "panelTask": deepcopy(source["panelTask"]),
        "mode": source["mode"],
        "workspaceId": parent.workspace_id,
        "workspaceName": source.get("workspaceName", ""),
        "accountPositioning": source["accountPositioning"],
        "targetType": "topic",
        "draft": None,
        "topic": {**deepcopy(source["topic"]), "title": topic["title"],
                  "body": topic["body"], "updatedAt": topic["updated_at"]},
        "parentSimulationId": parent.id,
    }
    snapshot["targetContentHash"] = digest(reader_visible_target(snapshot))
    snapshot["retest"] = {
        "version": "fixed-panel/v1",
        "parentTargetContentHash": source["targetContentHash"],
        "parentTopicUpdatedAt": source["topic"]["updatedAt"],
        "personaSnapshotHash": digest(parent.persona_definitions),
        "parentModelMetadata": deepcopy(parent.model_metadata),
        "comparisonLimitations": [
            "固定当时人物、案例顺序和阅读任务，不保证模型输出相同。",
            "模型和提示版本尚未完成配对核验，不能把反应变化全部归因于改稿。",
        ],
    }
    return snapshot
