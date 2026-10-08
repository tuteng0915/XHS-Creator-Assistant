"""Explicit, idempotent promotion of a frozen review idea into the topic library."""
import json

from app.db.database import SQLiteDatabase
from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import TopicResponse
from app.repositories.simulation_runs import SimulationRunRepository
from app.repositories.topics import TopicRepository
from app.services.common import utc_now
from app.services.simulation_review import simulation_category
from app.services.topics import TopicService


class SimulationTopicIdeaService:
    def __init__(self, database: SQLiteDatabase):
        self.database = database
        self.simulations = SimulationRunRepository()
        self.topics = TopicRepository()

    def adopt(self, workspace_id: str, simulation_id: str, idea_id: str) -> TopicResponse:
        with self.database.transaction() as connection:
            run = self.simulations.get(connection, simulation_id)
            if run["workspace_id"] != workspace_id:
                raise NotFoundError("未找到当前账号的模拟记录")
            snapshot = json.loads(run["input_snapshot_json"])
            category = simulation_category(snapshot)
            if category == "creation":
                raise ValidationError("仅账号访谈和已发布笔记复盘可收录后续选题")
            if run["status"] not in {"completed", "partially_completed"}:
                raise ConflictError("请等待本次复盘完成后再收录选题")
            synthesis = json.loads(run["synthesis_json"])
            ideas = (synthesis.get("review") or {}).get("topicIdeas") or []
            idea = next((item for item in ideas if item.get("id") == idea_id), None)
            if idea is None:
                raise NotFoundError("未找到本次复盘的候选选题")
            # BEGIN IMMEDIATE serializes concurrent clicks; no auto-adoption or analysis record.
            for row in self.topics.list(connection, workspace_id=workspace_id):
                origin = json.loads(row.get("generated_snapshot_json") or "{}")
                if (origin.get("sourceSimulationId") == simulation_id
                        and origin.get("sourceTopicIdeaId") == idea_id):
                    return TopicService._to_response(row)
            title = str(idea.get("title") or "").strip()
            if not title:
                raise ValidationError("候选选题标题不能为空")
            origin = {
                "title": title,
                "angle": str(idea.get("angle") or ""),
                "whyItFits": str(idea.get("whyItFits") or ""),
                "sourceSimulationId": simulation_id,
                "sourceTopicIdeaId": idea_id,
                "sourceSimulationCategory": category,
            }
            row = self.topics.create(
                connection, workspace_id=workspace_id, title=title, angle=origin["angle"],
                associated_pain_point="", why_it_fits=origin["whyItFits"],
                generated_snapshot_json=json.dumps(origin, ensure_ascii=False),
                source_analysis_run_id=None, source_workflow="manual", now=utc_now(),
            )
        return TopicService._to_response(row)
