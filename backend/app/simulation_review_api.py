from fastapi import APIRouter

from app.models import TopicResponse
from app.services.simulation_topic_ideas import SimulationTopicIdeaService


def simulation_review_router(service: SimulationTopicIdeaService) -> APIRouter:
    router = APIRouter(
        prefix="/api/workspaces/{workspace_id}/simulation-runs/{simulation_id}",
        tags=["simulation-reviews"],
    )

    @router.post("/topic-ideas/{idea_id}/adopt", response_model=TopicResponse)
    def adopt(workspace_id: str, simulation_id: str, idea_id: str):
        return service.adopt(workspace_id, simulation_id, idea_id)

    return router
