from fastapi import APIRouter

from app.services.comment_preview import (
    CommentPreviewCreate,
    CommentPreviewResponse,
    CommentPreviewService,
)


def comment_preview_router(service: CommentPreviewService) -> APIRouter:
    router = APIRouter(prefix="/api/workspaces/{workspace_id}/comment-previews",
                       tags=["comment-previews"])

    @router.post("", response_model=CommentPreviewResponse)
    async def create(workspace_id: str, payload: CommentPreviewCreate):
        return await service.create(workspace_id, payload)

    return router
