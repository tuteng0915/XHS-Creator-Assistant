import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, File, Form, Query, Request, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.errors import ValidationError
from app.models import (
    AccountProfileCsvImportResponse,
    AgentConversationCreate,
    AgentConversationResponse,
    AgentConversationSummary,
    AgentConversationUpdate,
    AgentDefinitionUpdate,
    AgentMessageCreate,
    AgentResponse,
    AgentSummary,
    AgentUpdate,
    AnalysisRunBatchCreate,
    AnalysisRunCreate,
    AnalysisRunResponse,
    AnalysisRunSummary,
    AssetProposalPreviewResponse,
    AssetProposalResponse,
    AssetProposalUpdate,
    CapabilityDefinitionDiffResponse,
    CapabilityDefinitionRevert,
    DraftGenerateRequest,
    DraftResponse,
    DraftSummary,
    DraftUpdate,
    InputAssetResponse,
    InputAssetType,
    InputAssetUpdate,
    MediaAssetResponse,
    MediaAssetType,
    MediaAssetUpdate,
    RunReviewUpdate,
    SimulationRunCreate,
    SimulationRunResponse,
    SimulationRunSummary,
    SkillDefinitionUpdate,
    SkillDryRunRequest,
    SkillDryRunResponse,
    SkillInvokeRequest,
    SkillInvokeResponse,
    SkillResponse,
    SkillSummary,
    SkillUpdate,
    SourceMaterialResponse,
    SourceMaterialType,
    SourceMaterialUpdate,
    TextInputAssetCreate,
    TextInputAssetCsvImportResponse,
    TextSourceMaterialCreate,
    TopicCreate,
    TopicResponse,
    TopicSourceWorkflow,
    TopicStatus,
    TopicUpdate,
    VideoPreviewDeriveRequest,
    VideoPreviewDeriveResponse,
    WorkflowAssetDefinitionUpdate,
    WorkflowAssetResponse,
    WorkflowAssetSummary,
    WorkflowAssetUpdate,
    WorkflowCallBindingUpdate,
    WorkflowType,
    WorkspaceCreate,
    WorkspaceResponse,
    WorkspaceUpdate,
    XhsCaptureJobCreate,
    XhsCaptureJobResponse,
    XhsOfflineImportPackageResponse,
    XhsOfflineImportResponse,
)
from app.services import (
    AgentConversationService,
    AgentService,
    AnalysisRunService,
    AssetProposalService,
    DraftGenerationService,
    DraftService,
    InputAssetService,
    MediaAssetService,
    SimulationRunService,
    SkillService,
    TopicService,
    WorkflowAssetService,
    WorkflowWorkerService,
    WorkspaceService,
    XhsCaptureJobService,
    XhsOfflineImportService,
)
from app.services.common import utc_now
from app.services.xhs_imports import XhsPackageFile
from app.workflows import (
    ACCOUNT_STAGE_ORDER,
    SIMULATION_STAGE_ORDER,
    TREND_STAGE_ORDER,
    VIDEO_CREATOR_QUALITY_STAGE_ORDER,
)


def _terminal_event_type(status: str) -> str:
    if status == "completed":
        return "run.succeeded"
    if status == "partially_completed":
        return "run.partial"
    return "run.failed"


def _sse_event(
    *,
    run_id: str,
    run_type: str,
    stage_key: str | None,
    status: str,
    sequence: int,
    event_type: str,
    data: dict,
) -> str:
    event = {
        "eventId": str(sequence),
        "runId": run_id,
        "runType": run_type,
        "stageKey": stage_key,
        "status": status,
        "sequence": sequence,
        "occurredAt": utc_now(),
        "data": {"eventType": event_type, **data},
    }
    return (
        f"id: {event['eventId']}\n"
        f"event: {event_type}\n"
        f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
    )


def create_api_router(
    workspace_service: WorkspaceService,
    input_asset_service: InputAssetService,
    media_asset_service: MediaAssetService,
    analysis_service: AnalysisRunService,
    topic_service: TopicService,
    draft_service: DraftService,
    draft_generation_service: DraftGenerationService,
    simulation_service: SimulationRunService,
    skill_service: SkillService,
    agent_service: AgentService,
    agent_conversation_service: AgentConversationService,
    asset_proposal_service: AssetProposalService,
    workflow_asset_service: WorkflowAssetService,
    workflow_worker: WorkflowWorkerService,
    xhs_import_service: XhsOfflineImportService,
    xhs_capture_service: XhsCaptureJobService,
) -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.post(
        "/workspaces",
        response_model=WorkspaceResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_workspace(payload: WorkspaceCreate) -> WorkspaceResponse:
        return workspace_service.create(payload)

    @router.get("/workspaces", response_model=list[WorkspaceResponse])
    def list_workspaces() -> list[WorkspaceResponse]:
        return workspace_service.list()

    @router.get("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
    def get_workspace(workspace_id: str) -> WorkspaceResponse:
        return workspace_service.get(workspace_id)

    @router.patch("/workspaces/{workspace_id}", response_model=WorkspaceResponse)
    def update_workspace(
        workspace_id: str, payload: WorkspaceUpdate
    ) -> WorkspaceResponse:
        return workspace_service.update(workspace_id, payload)

    @router.post(
        "/workspaces/{workspace_id}/xhs-capture-jobs",
        response_model=XhsCaptureJobResponse,
        status_code=status.HTTP_202_ACCEPTED,
    )
    def create_xhs_capture_job(
        workspace_id: str, payload: XhsCaptureJobCreate
    ) -> XhsCaptureJobResponse:
        return xhs_capture_service.create(workspace_id, payload)

    @router.get(
        "/workspaces/{workspace_id}/xhs-capture-jobs",
        response_model=list[XhsCaptureJobResponse],
    )
    def list_xhs_capture_jobs(workspace_id: str) -> list[XhsCaptureJobResponse]:
        return xhs_capture_service.list(workspace_id)

    @router.post("/creator-accounts/import", response_model=XhsCaptureJobResponse, status_code=201)
    def import_creator_account(payload: XhsCaptureJobCreate) -> XhsCaptureJobResponse:
        return xhs_capture_service.create_account(payload)

    @router.get(
        "/xhs-capture-jobs/{job_id}", response_model=XhsCaptureJobResponse
    )
    def get_xhs_capture_job(job_id: str) -> XhsCaptureJobResponse:
        return xhs_capture_service.get(job_id)

    @router.post(
        "/workspaces/{workspace_id}/source-materials",
        response_model=SourceMaterialResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_text_source_material(
        workspace_id: str, payload: TextSourceMaterialCreate
    ) -> SourceMaterialResponse:
        return input_asset_service.create_text(workspace_id, payload)

    @router.post(
        "/workspaces/{workspace_id}/input-assets",
        response_model=InputAssetResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_text_input_asset(
        workspace_id: str, payload: TextInputAssetCreate
    ) -> InputAssetResponse:
        return input_asset_service.create_text(workspace_id, payload)

    @router.post(
        "/workspaces/{workspace_id}/source-materials/trend-csv",
        response_model=SourceMaterialResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_trend_csv(
        workspace_id: str,
        name: Annotated[str, Form()],
        keyword: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
    ) -> SourceMaterialResponse:
        return input_asset_service.create_csv(
            workspace_id,
            name=name,
            keyword=keyword,
            filename=file.filename or "upload.csv",
            content=await file.read(),
        )

    @router.post(
        "/workspaces/{workspace_id}/input-assets/trend-csv",
        response_model=InputAssetResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_input_asset_trend_csv(
        workspace_id: str,
        name: Annotated[str, Form()],
        keyword: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
    ) -> InputAssetResponse:
        return input_asset_service.create_csv(
            workspace_id,
            name=name,
            keyword=keyword,
            filename=file.filename or "upload.csv",
            content=await file.read(),
        )

    @router.post(
        "/workspaces/{workspace_id}/source-materials/account-profiles-csv",
        response_model=AccountProfileCsvImportResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_account_profiles_csv(
        workspace_id: str,
        file: Annotated[UploadFile, File()],
    ) -> AccountProfileCsvImportResponse:
        return input_asset_service.import_account_profiles_csv(
            workspace_id,
            filename=file.filename or "account-profiles.csv",
            content=await file.read(),
        )

    @router.post(
        "/workspaces/{workspace_id}/input-assets/account-profiles-csv",
        response_model=AccountProfileCsvImportResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_input_asset_account_profiles_csv(
        workspace_id: str,
        file: Annotated[UploadFile, File()],
    ) -> AccountProfileCsvImportResponse:
        return input_asset_service.import_account_profiles_csv(
            workspace_id,
            filename=file.filename or "account-profiles.csv",
            content=await file.read(),
        )

    @router.post(
        "/workspaces/{workspace_id}/input-assets/text-csv",
        response_model=TextInputAssetCsvImportResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_input_asset_text_csv(
        workspace_id: str,
        type: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
    ) -> TextInputAssetCsvImportResponse:
        try:
            material_type = SourceMaterialType(type)
        except ValueError:
            material_type = SourceMaterialType.TREND_CSV
        return input_asset_service.import_text_assets_csv(
            workspace_id,
            material_type=material_type,
            filename=file.filename or "input-assets.csv",
            content=await file.read(),
        )

    @router.post(
        "/workspaces/{workspace_id}/input-assets/xhs-import",
        response_model=XhsOfflineImportResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_xhs_offline_import(
        workspace_id: str,
        file: Annotated[UploadFile, File()],
        type: Annotated[str, Form()] = SourceMaterialType.HISTORICAL_POSTS.value,
        name: Annotated[str, Form()] = "",
    ) -> XhsOfflineImportResponse:
        try:
            asset_type = SourceMaterialType(type)
        except ValueError:
            asset_type = SourceMaterialType.TREND_CSV
        return xhs_import_service.import_file(
            workspace_id,
            asset_type=asset_type,
            name=name,
            filename=file.filename or "xhs-import.json",
            content=await file.read(),
        )

    @router.post(
        "/workspaces/{workspace_id}/input-assets/xhs-import-package",
        response_model=XhsOfflineImportPackageResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_xhs_offline_import_package(
        workspace_id: str,
        profile: Annotated[UploadFile, File()],
        files: Annotated[list[UploadFile] | None, File()] = None,
        relative_paths: Annotated[
            list[str] | None, Form(alias="relativePaths")
        ] = None,
        name: Annotated[str, Form()] = "",
        save_as_new: Annotated[bool, Form(alias="saveAsNew")] = False,
    ) -> XhsOfflineImportPackageResponse:
        uploaded_files = files or []
        uploaded_relative_paths = relative_paths or []
        if len(uploaded_files) != len(uploaded_relative_paths):
            raise ValidationError(
                "XHS package files and relativePaths must have the same length"
            )
        return xhs_import_service.import_package(
            workspace_id,
            profile_filename=profile.filename or "xhs_creator_profile.json",
            profile_content=await profile.read(),
            files=[
                XhsPackageFile(
                    relative_path=relative_path,
                    filename=file.filename or relative_path,
                    media_type=file.content_type or "",
                    content=await file.read(),
                )
                for file, relative_path in zip(
                    uploaded_files, uploaded_relative_paths, strict=True
                )
            ],
            name=name,
            save_as_new=save_as_new,
        )

    @router.get(
        "/workspaces/{workspace_id}/source-materials",
        response_model=list[SourceMaterialResponse],
    )
    def list_source_materials(
        workspace_id: str,
        material_type: Annotated[
            SourceMaterialType | None, Query(alias="type")
        ] = None,
    ) -> list[SourceMaterialResponse]:
        return input_asset_service.list(workspace_id, material_type)

    @router.get(
        "/workspaces/{workspace_id}/input-assets",
        response_model=list[InputAssetResponse],
    )
    def list_input_assets(
        workspace_id: str,
        asset_type: Annotated[InputAssetType | None, Query(alias="type")] = None,
    ) -> list[InputAssetResponse]:
        return input_asset_service.list(workspace_id, asset_type)

    @router.get(
        "/source-materials/{material_id}", response_model=SourceMaterialResponse
    )
    def get_source_material(material_id: str) -> SourceMaterialResponse:
        return input_asset_service.get(material_id)

    @router.get("/input-assets/{asset_id}", response_model=InputAssetResponse)
    def get_input_asset(asset_id: str) -> InputAssetResponse:
        return input_asset_service.get(asset_id)

    @router.patch(
        "/source-materials/{material_id}", response_model=SourceMaterialResponse
    )
    def update_source_material(
        material_id: str, payload: SourceMaterialUpdate
    ) -> SourceMaterialResponse:
        return input_asset_service.update(material_id, payload)

    @router.patch("/input-assets/{asset_id}", response_model=InputAssetResponse)
    def update_input_asset(
        asset_id: str, payload: InputAssetUpdate
    ) -> InputAssetResponse:
        return input_asset_service.update(asset_id, payload)

    @router.post(
        "/workspaces/{workspace_id}/media-assets/upload",
        response_model=MediaAssetResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def upload_media_asset(
        workspace_id: str,
        type: Annotated[MediaAssetType, Form()],
        name: Annotated[str, Form()],
        file: Annotated[UploadFile, File()],
        purpose: Annotated[str, Form()] = "",
    ) -> MediaAssetResponse:
        return media_asset_service.create_upload(
            workspace_id,
            asset_type=type,
            name=name,
            purpose=purpose,
            filename=file.filename or "upload",
            media_type=file.content_type or "",
            content=await file.read(),
        )

    @router.get(
        "/workspaces/{workspace_id}/media-assets",
        response_model=list[MediaAssetResponse],
    )
    def list_media_assets(
        workspace_id: str,
        asset_type: Annotated[MediaAssetType | None, Query(alias="type")] = None,
    ) -> list[MediaAssetResponse]:
        return media_asset_service.list(workspace_id, asset_type)

    @router.get("/media-assets/{asset_id}", response_model=MediaAssetResponse)
    def get_media_asset(asset_id: str) -> MediaAssetResponse:
        return media_asset_service.get(asset_id)

    @router.patch("/media-assets/{asset_id}", response_model=MediaAssetResponse)
    def update_media_asset(
        asset_id: str, payload: MediaAssetUpdate
    ) -> MediaAssetResponse:
        return media_asset_service.update(asset_id, payload)

    @router.post(
        "/media-assets/{asset_id}/derive-video-preview",
        response_model=VideoPreviewDeriveResponse,
    )
    def derive_video_preview(
        asset_id: str, payload: VideoPreviewDeriveRequest | None = None
    ) -> VideoPreviewDeriveResponse:
        request_payload = payload or VideoPreviewDeriveRequest()
        return media_asset_service.derive_video_preview(
            asset_id,
            frame_count=request_payload.frame_count,
            force=request_payload.force,
        )

    @router.get("/media-assets/{asset_id}/file")
    def get_media_asset_file(asset_id: str) -> FileResponse:
        path, media_type, filename = media_asset_service.get_file(asset_id)
        return FileResponse(path, media_type=media_type, filename=filename)

    @router.get(
        "/workspaces/{workspace_id}/skills",
        response_model=list[SkillSummary],
    )
    def list_skills(workspace_id: str) -> list[SkillSummary]:
        return skill_service.list(workspace_id)

    @router.get("/skills/{skill_asset_id}", response_model=SkillResponse)
    def get_skill(skill_asset_id: str) -> SkillResponse:
        return skill_service.get(skill_asset_id)

    @router.patch("/skills/{skill_asset_id}", response_model=SkillResponse)
    def update_skill(
        skill_asset_id: str, payload: SkillUpdate
    ) -> SkillResponse:
        return skill_service.update(skill_asset_id, payload)

    @router.patch(
        "/skills/{skill_asset_id}/definition",
        response_model=SkillResponse,
    )
    def update_skill_definition(
        skill_asset_id: str, payload: SkillDefinitionUpdate
    ) -> SkillResponse:
        return skill_service.update_definition(skill_asset_id, payload)

    @router.get(
        "/skills/{skill_asset_id}/definition-diff",
        response_model=CapabilityDefinitionDiffResponse,
    )
    def get_skill_definition_diff(
        skill_asset_id: str,
    ) -> CapabilityDefinitionDiffResponse:
        return skill_service.definition_diff(skill_asset_id)

    @router.post(
        "/skills/{skill_asset_id}/revert-definition",
        response_model=SkillResponse,
    )
    def revert_skill_definition(
        skill_asset_id: str, payload: CapabilityDefinitionRevert
    ) -> SkillResponse:
        return skill_service.revert_definition(skill_asset_id, payload)

    @router.post(
        "/skills/{skill_asset_id}/invoke",
        response_model=SkillInvokeResponse,
    )
    def invoke_skill(
        skill_asset_id: str, payload: SkillInvokeRequest
    ) -> SkillInvokeResponse:
        return skill_service.invoke(skill_asset_id, payload)

    @router.post(
        "/skills/{skill_asset_id}/dry-run",
        response_model=SkillDryRunResponse,
    )
    def dry_run_skill(
        skill_asset_id: str, payload: SkillDryRunRequest
    ) -> SkillDryRunResponse:
        return skill_service.dry_run(skill_asset_id, payload)

    @router.get(
        "/workspaces/{workspace_id}/agents",
        response_model=list[AgentSummary],
    )
    def list_agents(workspace_id: str) -> list[AgentSummary]:
        return agent_service.list(workspace_id)

    @router.get("/agents/{agent_asset_id}", response_model=AgentResponse)
    def get_agent(agent_asset_id: str) -> AgentResponse:
        return agent_service.get(agent_asset_id)

    @router.patch("/agents/{agent_asset_id}", response_model=AgentResponse)
    def update_agent(
        agent_asset_id: str, payload: AgentUpdate
    ) -> AgentResponse:
        return agent_service.update(agent_asset_id, payload)

    @router.patch(
        "/agents/{agent_asset_id}/definition",
        response_model=AgentResponse,
    )
    def update_agent_definition(
        agent_asset_id: str, payload: AgentDefinitionUpdate
    ) -> AgentResponse:
        return agent_service.update_definition(agent_asset_id, payload)

    @router.get(
        "/agents/{agent_asset_id}/definition-diff",
        response_model=CapabilityDefinitionDiffResponse,
    )
    def get_agent_definition_diff(
        agent_asset_id: str,
    ) -> CapabilityDefinitionDiffResponse:
        return agent_service.definition_diff(agent_asset_id)

    @router.post(
        "/agents/{agent_asset_id}/revert-definition",
        response_model=AgentResponse,
    )
    def revert_agent_definition(
        agent_asset_id: str, payload: CapabilityDefinitionRevert
    ) -> AgentResponse:
        return agent_service.revert_definition(agent_asset_id, payload)

    @router.post(
        "/workspaces/{workspace_id}/agent-conversations",
        response_model=AgentConversationResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_agent_conversation(
        workspace_id: str, payload: AgentConversationCreate
    ) -> AgentConversationResponse:
        return agent_conversation_service.create(workspace_id, payload)

    @router.get(
        "/workspaces/{workspace_id}/agent-conversations",
        response_model=list[AgentConversationSummary],
    )
    def list_agent_conversations(
        workspace_id: str,
    ) -> list[AgentConversationSummary]:
        return agent_conversation_service.list(workspace_id)

    @router.get(
        "/agent-conversations/{conversation_id}",
        response_model=AgentConversationResponse,
    )
    def get_agent_conversation(conversation_id: str) -> AgentConversationResponse:
        return agent_conversation_service.get(conversation_id)

    @router.patch(
        "/agent-conversations/{conversation_id}",
        response_model=AgentConversationResponse,
    )
    def update_agent_conversation(
        conversation_id: str, payload: AgentConversationUpdate
    ) -> AgentConversationResponse:
        return agent_conversation_service.update(conversation_id, payload)

    @router.post(
        "/agent-conversations/{conversation_id}/messages",
        response_model=AgentConversationResponse,
    )
    async def send_agent_message(
        conversation_id: str, payload: AgentMessageCreate
    ) -> AgentConversationResponse:
        return await agent_conversation_service.send_message(conversation_id, payload)

    @router.get(
        "/workspaces/{workspace_id}/asset-proposals",
        response_model=list[AssetProposalResponse],
    )
    def list_workspace_asset_proposals(
        workspace_id: str,
    ) -> list[AssetProposalResponse]:
        return asset_proposal_service.list(workspace_id=workspace_id)

    @router.get(
        "/agent-conversations/{conversation_id}/asset-proposals",
        response_model=list[AssetProposalResponse],
    )
    def list_conversation_asset_proposals(
        conversation_id: str,
    ) -> list[AssetProposalResponse]:
        return asset_proposal_service.list(conversation_id=conversation_id)

    @router.get(
        "/asset-proposals/{proposal_id}/preview",
        response_model=AssetProposalPreviewResponse,
    )
    def preview_asset_proposal(proposal_id: str) -> AssetProposalPreviewResponse:
        return asset_proposal_service.preview(proposal_id)

    @router.post(
        "/asset-proposals/{proposal_id}/apply",
        response_model=AssetProposalResponse,
    )
    def apply_asset_proposal(proposal_id: str) -> AssetProposalResponse:
        return asset_proposal_service.apply(proposal_id)

    @router.patch(
        "/asset-proposals/{proposal_id}",
        response_model=AssetProposalResponse,
    )
    def update_asset_proposal(
        proposal_id: str, payload: AssetProposalUpdate
    ) -> AssetProposalResponse:
        return asset_proposal_service.update(proposal_id, payload)

    @router.post(
        "/asset-proposals/{proposal_id}/reject",
        response_model=AssetProposalResponse,
    )
    def reject_asset_proposal(proposal_id: str) -> AssetProposalResponse:
        return asset_proposal_service.reject(proposal_id)

    @router.get(
        "/workspaces/{workspace_id}/workflows",
        response_model=list[WorkflowAssetSummary],
    )
    def list_workflow_assets(workspace_id: str) -> list[WorkflowAssetSummary]:
        return workflow_asset_service.list(workspace_id)

    @router.get(
        "/workflows/{workflow_asset_id}", response_model=WorkflowAssetResponse
    )
    def get_workflow_asset(workflow_asset_id: str) -> WorkflowAssetResponse:
        return workflow_asset_service.get(workflow_asset_id)

    @router.patch(
        "/workflows/{workflow_asset_id}", response_model=WorkflowAssetResponse
    )
    def update_workflow_asset(
        workflow_asset_id: str, payload: WorkflowAssetUpdate
    ) -> WorkflowAssetResponse:
        return workflow_asset_service.update(workflow_asset_id, payload)

    @router.patch(
        "/workflows/{workflow_asset_id}/definition",
        response_model=WorkflowAssetResponse,
    )
    def update_workflow_asset_definition(
        workflow_asset_id: str, payload: WorkflowAssetDefinitionUpdate
    ) -> WorkflowAssetResponse:
        return workflow_asset_service.update_definition(workflow_asset_id, payload)

    @router.get(
        "/workflows/{workflow_asset_id}/definition-diff",
        response_model=CapabilityDefinitionDiffResponse,
    )
    def get_workflow_asset_definition_diff(
        workflow_asset_id: str,
    ) -> CapabilityDefinitionDiffResponse:
        return workflow_asset_service.definition_diff(workflow_asset_id)

    @router.post(
        "/workflows/{workflow_asset_id}/revert-definition",
        response_model=WorkflowAssetResponse,
    )
    def revert_workflow_asset_definition(
        workflow_asset_id: str, payload: CapabilityDefinitionRevert
    ) -> WorkflowAssetResponse:
        return workflow_asset_service.revert_definition(workflow_asset_id, payload)

    @router.patch(
        "/workflows/{workflow_asset_id}/call-binding",
        response_model=WorkflowAssetResponse,
    )
    def update_workflow_call_binding(
        workflow_asset_id: str, payload: WorkflowCallBindingUpdate
    ) -> WorkflowAssetResponse:
        return workflow_asset_service.update_call_binding(workflow_asset_id, payload)

    @router.post(
        "/workspaces/{workspace_id}/analysis-runs",
        response_model=AnalysisRunResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_analysis_run(
        workspace_id: str, payload: AnalysisRunCreate
    ) -> AnalysisRunResponse:
        run = analysis_service.create(workspace_id, payload)
        await workflow_worker.enqueue_analysis_run(run.id)
        return run

    @router.post(
        "/workspaces/{workspace_id}/analysis-runs/batch",
        response_model=list[AnalysisRunResponse],
        status_code=status.HTTP_201_CREATED,
    )
    async def create_analysis_runs_batch(
        workspace_id: str, payload: AnalysisRunBatchCreate
    ) -> list[AnalysisRunResponse]:
        runs = analysis_service.create_batch(workspace_id, payload)
        for run in runs:
            await workflow_worker.enqueue_analysis_run(run.id)
        return runs

    @router.get(
        "/workspaces/{workspace_id}/analysis-runs",
        response_model=list[AnalysisRunSummary],
    )
    def list_analysis_runs(workspace_id: str) -> list[AnalysisRunSummary]:
        return analysis_service.list(workspace_id)

    @router.get("/workspaces/{workspace_id}/analysis-runs/export.csv")
    def export_analysis_runs_csv(
        workspace_id: str,
        workflow_type: Annotated[
            WorkflowType | None, Query(alias="workflowType")
        ] = None,
        ids: Annotated[str | None, Query()] = None,
    ) -> Response:
        run_ids = [item.strip() for item in ids.split(",") if item.strip()] if ids else None
        csv_text = analysis_service.export_csv(
            workspace_id,
            workflow_type=workflow_type,
            run_ids=run_ids,
        )
        return Response(
            content=csv_text,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="analysis-runs.csv"'
            },
        )

    @router.get("/analysis-runs/{run_id}", response_model=AnalysisRunResponse)
    def get_analysis_run(run_id: str) -> AnalysisRunResponse:
        return analysis_service.get(run_id)

    @router.patch("/analysis-runs/{run_id}/review", response_model=AnalysisRunResponse)
    def update_analysis_run_review(
        run_id: str, payload: RunReviewUpdate
    ) -> AnalysisRunResponse:
        return analysis_service.update_review(run_id, payload)

    @router.get("/analysis-runs/{run_id}/events")
    async def stream_analysis_run_events(
        run_id: str,
        request: Request,
        after: Annotated[int | None, Query()] = None,
    ) -> StreamingResponse:
        last_event_id = request.headers.get("last-event-id")
        min_sequence = after or (
            int(last_event_id)
            if last_event_id and last_event_id.isdigit()
            else 0
        )

        async def event_stream():
            emitted_stages: set[tuple[str, str]] = set()
            emitted_terminal = False
            sequence = 0
            while True:
                run = analysis_service.get(run_id)
                stage_order = (
                    ACCOUNT_STAGE_ORDER
                    if run.workflow_type.value == "account_diagnosis"
                    else VIDEO_CREATOR_QUALITY_STAGE_ORDER
                    if run.workflow_type.value == "video_creator_quality"
                    else TREND_STAGE_ORDER
                )
                if sequence == 0:
                    sequence += 1
                    event = _sse_event(
                        run_id=run.id,
                        run_type=run.workflow_type.value,
                        stage_key=None,
                        status=run.status.value,
                        sequence=sequence,
                        event_type="run.created",
                        data={},
                    )
                    if sequence > min_sequence:
                        yield event
                for stage_key in stage_order:
                    if (
                        run.status.value == "running"
                        and stage_key not in run.stage_results
                        and stage_key not in run.stage_errors
                        and ("started", stage_key) not in emitted_stages
                    ):
                        emitted_stages.add(("started", stage_key))
                        sequence += 1
                        event = _sse_event(
                            run_id=run.id,
                            run_type=run.workflow_type.value,
                            stage_key=stage_key,
                            status="running",
                            sequence=sequence,
                            event_type="stage.started",
                            data={},
                        )
                        if sequence > min_sequence:
                            yield event
                    if stage_key in run.stage_results and ("ok", stage_key) not in emitted_stages:
                        emitted_stages.add(("ok", stage_key))
                        sequence += 1
                        event = _sse_event(
                            run_id=run.id,
                            run_type=run.workflow_type.value,
                            stage_key=stage_key,
                            status="completed",
                            sequence=sequence,
                            event_type="stage.succeeded",
                            data=run.stage_results[stage_key],
                        )
                        if sequence > min_sequence:
                            yield event
                    if stage_key in run.stage_errors and ("err", stage_key) not in emitted_stages:
                        emitted_stages.add(("err", stage_key))
                        sequence += 1
                        event = _sse_event(
                            run_id=run.id,
                            run_type=run.workflow_type.value,
                            stage_key=stage_key,
                            status="failed",
                            sequence=sequence,
                            event_type="stage.failed",
                            data={"error": run.stage_errors[stage_key]},
                        )
                        if sequence > min_sequence:
                            yield event
                if run.status.value in {"completed", "partially_completed", "failed"}:
                    if not emitted_terminal:
                        emitted_terminal = True
                        sequence += 1
                        event = _sse_event(
                            run_id=run.id,
                            run_type=run.workflow_type.value,
                            stage_key=None,
                            status=run.status.value,
                            sequence=sequence,
                            event_type=_terminal_event_type(run.status.value),
                            data={
                                "stageResults": run.stage_results,
                                "stageErrors": run.stage_errors,
                            },
                        )
                        if sequence > min_sequence:
                            yield event
                    break
                await asyncio.sleep(0.2)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.post(
        "/workspaces/{workspace_id}/simulation-runs",
        response_model=SimulationRunResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def create_simulation_run(
        workspace_id: str, payload: SimulationRunCreate
    ) -> SimulationRunResponse:
        run = simulation_service.create(workspace_id, payload)
        await workflow_worker.enqueue_simulation_run(run.id)
        return run

    @router.get(
        "/workspaces/{workspace_id}/simulation-runs",
        response_model=list[SimulationRunSummary],
    )
    def list_simulation_runs(workspace_id: str) -> list[SimulationRunSummary]:
        return simulation_service.list(workspace_id)

    @router.get("/simulation-runs/{simulation_id}", response_model=SimulationRunResponse)
    def get_simulation_run(simulation_id: str) -> SimulationRunResponse:
        return simulation_service.get(simulation_id)

    @router.patch(
        "/simulation-runs/{simulation_id}/review",
        response_model=SimulationRunResponse,
    )
    def update_simulation_run_review(
        simulation_id: str, payload: RunReviewUpdate
    ) -> SimulationRunResponse:
        return simulation_service.update_review(simulation_id, payload)

    @router.get("/simulation-runs/{simulation_id}/events")
    async def stream_simulation_run_events(
        simulation_id: str,
        request: Request,
        after: Annotated[int | None, Query()] = None,
    ) -> StreamingResponse:
        last_event_id = request.headers.get("last-event-id")
        min_sequence = after or (
            int(last_event_id)
            if last_event_id and last_event_id.isdigit()
            else 0
        )

        async def event_stream():
            emitted_stages: set[tuple[str, str]] = set()
            emitted_terminal = False
            sequence = 0
            while True:
                run = simulation_service.get(simulation_id)
                if sequence == 0:
                    sequence += 1
                    event = _sse_event(
                        run_id=run.id,
                        run_type="audience_simulation",
                        stage_key=None,
                        status=run.status.value,
                        sequence=sequence,
                        event_type="run.created",
                        data={},
                    )
                    if sequence > min_sequence:
                        yield event
                stage_data = {
                    "personas": {"personas": run.persona_definitions},
                    "initial_reactions": {"reactions": run.reaction_results},
                    "debate_responses": {"debateResponses": run.debate_results},
                    "synthesis": {"synthesis": run.synthesis},
                }
                discussion_skipped = bool(run.reaction_results) and sum(
                    r.get("action", "comment") == "comment"
                    and bool(r.get("quote") or r.get("text"))
                    for r in run.reaction_results
                ) < 2 and (bool(run.synthesis) or run.status.value in {
                    "completed", "partially_completed", "failed",
                })
                if discussion_skipped:
                    stage_data["debate_responses"]["skippedReason"] = (
                        "不足两条模拟公开评论，无需交叉回应。"
                    )
                stage_has_result = {
                    "personas": bool(run.persona_definitions),
                    "initial_reactions": bool(run.reaction_results),
                    "debate_responses": bool(run.debate_results) or discussion_skipped,
                    "synthesis": bool(run.synthesis),
                }
                for stage_key in SIMULATION_STAGE_ORDER:
                    if (
                        run.status.value == "running"
                        and not stage_has_result[stage_key]
                        and not any(
                            key == stage_key or key.startswith(f"{stage_key}.")
                            for key in run.stage_errors
                        )
                        and ("started", stage_key) not in emitted_stages
                    ):
                        emitted_stages.add(("started", stage_key))
                        sequence += 1
                        event = _sse_event(
                            run_id=run.id,
                            run_type="audience_simulation",
                            stage_key=stage_key,
                            status="running",
                            sequence=sequence,
                            event_type="stage.started",
                            data={},
                        )
                        if sequence > min_sequence:
                            yield event
                    if stage_has_result[stage_key] and ("ok", stage_key) not in emitted_stages:
                        emitted_stages.add(("ok", stage_key))
                        sequence += 1
                        event = _sse_event(
                            run_id=run.id,
                            run_type="audience_simulation",
                            stage_key=stage_key,
                            status="completed",
                            sequence=sequence,
                            event_type="stage.succeeded",
                            data=stage_data[stage_key],
                        )
                        if sequence > min_sequence:
                            yield event
                    stage_errors = [
                        (key, message)
                        for key, message in run.stage_errors.items()
                        if key == stage_key or key.startswith(f"{stage_key}.")
                    ]
                    if stage_errors and ("err", stage_key) not in emitted_stages:
                        emitted_stages.add(("err", stage_key))
                        sequence += 1
                        event = _sse_event(
                            run_id=run.id,
                            run_type="audience_simulation",
                            stage_key=stage_key,
                            status="failed",
                            sequence=sequence,
                            event_type="stage.failed",
                            data={"error": "; ".join(message for _, message in stage_errors)},
                        )
                        if sequence > min_sequence:
                            yield event
                if run.status.value in {"completed", "partially_completed", "failed"}:
                    if not emitted_terminal:
                        emitted_terminal = True
                        sequence += 1
                        event = _sse_event(
                            run_id=run.id,
                            run_type="audience_simulation",
                            stage_key=None,
                            status=run.status.value,
                            sequence=sequence,
                            event_type=_terminal_event_type(run.status.value),
                            data={
                                "personaDefinitions": run.persona_definitions,
                                "reactionResults": run.reaction_results,
                                "debateResults": run.debate_results,
                                "synthesis": run.synthesis,
                                "stageErrors": run.stage_errors,
                            },
                        )
                        if sequence > min_sequence:
                            yield event
                    break
                await asyncio.sleep(0.2)

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get(
        "/workspaces/{workspace_id}/drafts",
        response_model=list[DraftSummary],
    )
    def list_drafts(workspace_id: str) -> list[DraftSummary]:
        return draft_service.list(workspace_id)

    @router.get("/drafts/{draft_id}", response_model=DraftResponse)
    def get_draft(draft_id: str) -> DraftResponse:
        return draft_service.get(draft_id)

    @router.patch("/drafts/{draft_id}", response_model=DraftResponse)
    def update_draft(draft_id: str, payload: DraftUpdate) -> DraftResponse:
        return draft_service.update(draft_id, payload)

    @router.post(
        "/workspaces/{workspace_id}/topics",
        response_model=TopicResponse,
        status_code=status.HTTP_201_CREATED,
    )
    def create_topic(workspace_id: str, payload: TopicCreate) -> TopicResponse:
        return topic_service.create(workspace_id, payload)

    @router.get(
        "/workspaces/{workspace_id}/topics",
        response_model=list[TopicResponse],
    )
    def list_topics(
        workspace_id: str,
        source_workflow: Annotated[
            TopicSourceWorkflow | None, Query(alias="sourceWorkflow")
        ] = None,
        topic_status: Annotated[TopicStatus | None, Query(alias="status")] = None,
    ) -> list[TopicResponse]:
        return topic_service.list(
            workspace_id,
            source_workflow=source_workflow,
            status=topic_status,
        )

    @router.get("/topics/{topic_id}", response_model=TopicResponse)
    def get_topic(topic_id: str) -> TopicResponse:
        return topic_service.get(topic_id)

    @router.patch("/topics/{topic_id}", response_model=TopicResponse)
    def update_topic(topic_id: str, payload: TopicUpdate) -> TopicResponse:
        return topic_service.update(topic_id, payload)

    @router.post("/topics/{topic_id}/select", response_model=TopicResponse)
    def select_topic(topic_id: str) -> TopicResponse:
        return topic_service.select(topic_id)

    @router.post("/topics/{topic_id}/archive", response_model=TopicResponse)
    def archive_topic(topic_id: str) -> TopicResponse:
        return topic_service.archive(topic_id)

    @router.post(
        "/topics/{topic_id}/briefs/generate",
        response_model=DraftResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def generate_content_brief(
        topic_id: str, payload: DraftGenerateRequest
    ) -> DraftResponse:
        return await draft_generation_service.generate_brief_from_topic(topic_id, payload)

    @router.post(
        "/topics/{topic_id}/drafts/generate",
        response_model=DraftResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def generate_draft(
        topic_id: str, payload: DraftGenerateRequest
    ) -> DraftResponse:
        return await draft_generation_service.generate_from_topic(topic_id, payload)

    @router.post(
        "/drafts/{draft_id}/structure/generate",
        response_model=DraftResponse,
        status_code=status.HTTP_201_CREATED,
    )
    async def generate_structure_from_brief(
        draft_id: str, payload: DraftGenerateRequest
    ) -> DraftResponse:
        return await draft_generation_service.generate_structure_from_brief(
            draft_id, payload
        )

    return router
