from fastapi import APIRouter, HTTPException

from app.services.reader_selection_requests import (
    ReaderSelectionObservation,
    ReaderSelectionRequest,
    ReaderSelectionRequestService,
)
from app.services.reader_selection_worker import ReaderSelectionWorker
from app.services.reader_selections import ReaderSelectionResponse


def reader_selection_router(requests: ReaderSelectionRequestService, worker: ReaderSelectionWorker):
    router = APIRouter(prefix="/api/workspaces/{workspace_id}/reader-selections")

    @router.post("", response_model=ReaderSelectionResponse, status_code=202)
    async def create(workspace_id: str, payload: ReaderSelectionRequest):
        existing = requests.existing(workspace_id, payload)
        if existing is not None:
            return existing
        if not worker.available:
            raise HTTPException(status_code=503, detail="读者推荐暂未启用，请继续手动选择")
        # The durable worker scans pending rows, even if this response is lost/disconnected.
        return requests.create(workspace_id, payload)

    @router.get("/{selection_id}", response_model=ReaderSelectionObservation)
    async def get(workspace_id: str, selection_id: str):
        return requests.observe(workspace_id, selection_id)

    return router
