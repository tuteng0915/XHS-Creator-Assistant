from fastapi import APIRouter, HTTPException

from app.services.panel_interviews import (
    PanelInterviewCreate,
    PanelInterviewResponse,
    PanelInterviewService,
)


def panel_interview_router(service: PanelInterviewService) -> APIRouter:
    router = APIRouter(
        prefix="/api/workspaces/{workspace_id}/simulation-runs/{simulation_id}/interviews",
        tags=["reader-interviews"],
    )

    @router.post("", response_model=PanelInterviewResponse, status_code=202)
    async def create(workspace_id: str, simulation_id: str, payload: PanelInterviewCreate):
        existing = service.existing(workspace_id, simulation_id, payload)
        if existing is not None:
            return existing
        if not service.available:
            raise HTTPException(status_code=503, detail="读者访谈暂时无法开始，请稍后再试")
        return service.create(workspace_id, simulation_id, payload)

    @router.get("", response_model=list[PanelInterviewResponse])
    def list_interviews(workspace_id: str, simulation_id: str):
        return service.list(workspace_id, simulation_id)

    @router.get("/{interview_id}", response_model=PanelInterviewResponse)
    def get(workspace_id: str, simulation_id: str, interview_id: str):
        return service.get(workspace_id, simulation_id, interview_id)

    @router.post("/{interview_id}/cancel", response_model=PanelInterviewResponse)
    async def cancel(workspace_id: str, simulation_id: str, interview_id: str):
        return service.cancel(workspace_id, simulation_id, interview_id)

    return router
