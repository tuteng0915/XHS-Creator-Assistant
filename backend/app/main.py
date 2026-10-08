from contextlib import asynccontextmanager
from dataclasses import replace

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import create_api_router
from app.config import Settings
from app.db.database import SQLiteDatabase
from app.errors import ApplicationError, ConflictError, NotFoundError, ValidationError
from app.models import HealthResponse
from app.panel_interview_api import panel_interview_router
from app.reader_selection_api import reader_selection_router
from app.repositories import (
    AgentConversationRepository,
    AgentRepository,
    AnalysisRunRepository,
    AssetProposalRepository,
    ContentCollaborationRepository,
    DraftRepository,
    GraphCheckpointRepository,
    MediaAssetRepository,
    SimulationRunRepository,
    SkillRepository,
    SourceMaterialRepository,
    TopicRepository,
    WorkflowAssetRepository,
    WorkspaceRepository,
    XhsCaptureJobRepository,
)
from app.services import (
    AgentConversationService,
    AgentService,
    AnalysisRunService,
    AssetProposalService,
    ContentCollaborationSessionService,
    ContextAccessService,
    DraftGenerationService,
    DraftService,
    FakeAgentConversationModelProvider,
    FakeStructureModelProvider,
    InputAssetService,
    MediaAssetService,
    MediaCrawlerXhsCaptureRunner,
    ModelCallService,
    QwenMediaService,
    RealAgentConversationModelProvider,
    RealContentCollaborationProvider,
    RealStructureModelProvider,
    SimulationRunService,
    SkillService,
    TopicService,
    WorkflowAssetService,
    WorkflowWorkerService,
    WorkspaceService,
    XhsCaptureJobService,
    XhsOfflineImportService,
)
from app.services.audience_analyses import (
    AudienceAnalysisCreate,
    AudienceAnalysisResponse,
    AudienceAnalysisService,
)
from app.services.fan_voice_templates import FanVoiceTemplateResponse, list_fan_voice_templates
from app.services.panel_interviews import PanelInterviewService, RealPanelInterviewProvider
from app.services.reader_selection_model import RealReaderSelectionProvider
from app.services.reader_selection_requests import ReaderSelectionRequestService
from app.services.reader_selection_worker import ReaderSelectionProvider, ReaderSelectionWorker
from app.services.reader_selections import ReaderSelectionService
from app.services.simulated_fans import (
    FanCreate,
    FanResponse,
    FanUpdate,
    FanVariantsCreate,
    SimulatedFanService,
)
from app.services.simulation_topic_ideas import SimulationTopicIdeaService
from app.simulation_review_api import simulation_review_router
from app.workflows import (
    AccountDiagnosisWorkflowService,
    AudienceSimulationWorkflowService,
    FakeAccountDiagnosisModelProvider,
    FakeAudienceSimulationModelProvider,
    FakeTrendAnalysisModelProvider,
    FakeVideoCreatorQualityModelProvider,
    RealAccountDiagnosisModelProvider,
    RealAudienceSimulationModelProvider,
    RealTrendAnalysisModelProvider,
    RealVideoCreatorQualityModelProvider,
    TrendAnalysisWorkflowService,
    VideoCreatorQualityWorkflowService,
)


def create_app(
    settings: Settings | None = None,
    *, reader_selection_provider: ReaderSelectionProvider | None = None,
) -> FastAPI:
    active_settings = settings or Settings.from_environment()
    database = SQLiteDatabase(active_settings.database_path)
    database.migrate()

    workspace_repository = WorkspaceRepository()
    source_repository = SourceMaterialRepository()
    media_asset_repository = MediaAssetRepository()
    analysis_repository = AnalysisRunRepository()
    draft_repository = DraftRepository()
    topic_repository = TopicRepository()
    simulation_repository = SimulationRunRepository()
    skill_repository = SkillRepository()
    agent_repository = AgentRepository()
    agent_conversation_repository = AgentConversationRepository()
    asset_proposal_repository = AssetProposalRepository()
    content_collaboration_repository = ContentCollaborationRepository()
    workflow_asset_repository = WorkflowAssetRepository()
    checkpoint_repository = GraphCheckpointRepository()
    xhs_capture_repository = XhsCaptureJobRepository()
    context_access_service = ContextAccessService(
        source_repository=source_repository,
        media_asset_repository=media_asset_repository,
        analysis_repository=analysis_repository,
        topic_repository=topic_repository,
        draft_repository=draft_repository,
        simulation_repository=simulation_repository,
        skill_repository=skill_repository,
        agent_repository=agent_repository,
        workflow_repository=workflow_asset_repository,
    )
    workspace_service = WorkspaceService(
        database,
        workspace_repository,
        default_user_id=active_settings.default_user_id,
    )
    input_asset_service = InputAssetService(
        database,
        source_repository,
        workspace_repository,
        active_settings,
    )
    media_asset_service = MediaAssetService(
        database,
        media_asset_repository,
        workspace_repository,
        active_settings,
    )
    qwen_media_service = QwenMediaService(active_settings, media_asset_service)
    xhs_import_service = XhsOfflineImportService(input_asset_service, media_asset_service)
    xhs_capture_service = XhsCaptureJobService(
        database=database,
        repository=xhs_capture_repository,
        workspace_repository=workspace_repository,
        workspace_service=workspace_service,
        runner=MediaCrawlerXhsCaptureRunner(active_settings, xhs_import_service),
    )
    analysis_service = AnalysisRunService(
        database,
        analysis_repository,
        workspace_repository,
        source_repository,
        media_asset_repository,
        topic_repository,
        active_settings,
        context_access_service,
    )
    topic_service = TopicService(
        database,
        topic_repository,
        workspace_repository,
        analysis_repository,
    )
    model_call_service = ModelCallService(active_settings)
    draft_service = DraftService(
        database,
        draft_repository,
        workspace_repository,
    )
    draft_generation_service = DraftGenerationService(
        database,
        draft_repository,
        draft_service,
        workspace_repository,
        topic_repository,
        analysis_repository,
        fake_provider=FakeStructureModelProvider(),
        live_provider=RealStructureModelProvider(model_call_service),
    )
    simulation_service = SimulationRunService(
        database,
        simulation_repository,
        workspace_repository,
        topic_repository,
        draft_repository,
    )
    skill_service = SkillService(
        database,
        skill_repository,
        workspace_repository,
        qwen_media_service,
    )
    agent_service = AgentService(
        database,
        agent_repository,
        workspace_repository,
        skill_service,
    )
    workflow_asset_service = WorkflowAssetService(
        database,
        workflow_asset_repository,
        workspace_repository,
        agent_service,
    )
    agent_conversation_service = AgentConversationService(
        database,
        agent_conversation_repository,
        asset_proposal_repository,
        workspace_repository,
        agent_repository,
        context_access_service,
        fake_provider=FakeAgentConversationModelProvider(),
        live_provider=RealAgentConversationModelProvider(model_call_service),
        capability_catalog_ensurers=[
            skill_service.list,
            agent_service.list,
            workflow_asset_service.list,
        ],
    )
    asset_proposal_service = AssetProposalService(
        database=database,
        repository=asset_proposal_repository,
        workspace_repository=workspace_repository,
        topic_repository=topic_repository,
        skill_repository=skill_repository,
        agent_repository=agent_repository,
        workflow_repository=workflow_asset_repository,
    )
    # Collaboration live turns are an explicit Qwen-only feature.  Keep this
    # separate from the application's general model provider so a demo request
    # never starts using a different configured provider accidentally.
    content_collaboration_live_provider = (
        RealContentCollaborationProvider(
            ModelCallService(replace(active_settings, model_provider="qwen"))
        )
        if active_settings.qwen_api_key
        else None
    )
    content_collaboration_service = ContentCollaborationSessionService(
        database=database,
        repository=content_collaboration_repository,
        workspace_repository=workspace_repository,
        topic_repository=topic_repository,
        context_access_service=context_access_service,
        live_provider=content_collaboration_live_provider,
    )
    account_workflow_service = AccountDiagnosisWorkflowService(
        database=database,
        analysis_repository=analysis_repository,
        checkpoint_repository=checkpoint_repository,
        analysis_service=analysis_service,
        fake_provider=FakeAccountDiagnosisModelProvider(),
        live_provider=RealAccountDiagnosisModelProvider(model_call_service),
    )
    trend_workflow_service = TrendAnalysisWorkflowService(
        database=database,
        checkpoint_repository=checkpoint_repository,
        analysis_service=analysis_service,
        fake_provider=FakeTrendAnalysisModelProvider(),
        live_provider=RealTrendAnalysisModelProvider(model_call_service),
    )
    video_workflow_service = VideoCreatorQualityWorkflowService(
        database=database,
        checkpoint_repository=checkpoint_repository,
        analysis_service=analysis_service,
        fake_provider=FakeVideoCreatorQualityModelProvider(),
        live_provider=RealVideoCreatorQualityModelProvider(model_call_service),
        skill_service=skill_service,
    )
    simulation_workflow_service = AudienceSimulationWorkflowService(
        database=database,
        checkpoint_repository=checkpoint_repository,
        simulation_service=simulation_service,
        fake_provider=FakeAudienceSimulationModelProvider(),
        live_provider=RealAudienceSimulationModelProvider(model_call_service),
    )
    workflow_worker = WorkflowWorkerService(
        database=database,
        analysis_repository=analysis_repository,
        simulation_repository=simulation_repository,
        account_workflow_service=account_workflow_service,
        trend_workflow_service=trend_workflow_service,
        video_workflow_service=video_workflow_service,
        simulation_workflow_service=simulation_workflow_service,
    )
    reader_selection_service = ReaderSelectionService(database)
    reader_selection_requests = ReaderSelectionRequestService(reader_selection_service)
    if (reader_selection_provider is None
            and active_settings.model_provider.strip().lower() in {"qwen", "dashscope"}
            and active_settings.qwen_api_key):
        reader_selection_provider = RealReaderSelectionProvider(model_call_service)
    reader_selection_worker = ReaderSelectionWorker(
        reader_selection_service, reader_selection_provider,
    )
    panel_interview_service = PanelInterviewService(
        database,
        live_provider=RealPanelInterviewProvider(
            ModelCallService(replace(active_settings, model_provider="qwen"))
        ) if active_settings.qwen_api_key else None,
    )

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        audience_analysis_service.resume()
        xhs_capture_service.recover_interrupted()
        agent_conversation_service.resume_unfinished()
        content_collaboration_service.resume_unfinished()
        await workflow_worker.resume_unfinished()
        reader_selection_worker.start()
        panel_interview_service.start()
        try:
            yield
        finally:
            await panel_interview_service.shutdown()
            await reader_selection_worker.shutdown()
            await audience_analysis_service.shutdown()
            await agent_conversation_service.shutdown()
            await content_collaboration_service.shutdown()
            await workflow_worker.shutdown()
            xhs_capture_service.shutdown()

    audience_analysis_service = AudienceAnalysisService(database, model_call_service)
    simulated_fan_service = SimulatedFanService(database)
    application = FastAPI(
        title="Creator Workspace API",
        version="0.1.0",
        description="Workspace and input-asset persistence for the creator prototype.",
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.database = database
    application.state.workspace_service = workspace_service
    application.state.input_asset_service = input_asset_service
    application.state.media_asset_service = media_asset_service
    application.state.qwen_media_service = qwen_media_service
    application.state.source_service = input_asset_service
    application.state.analysis_service = analysis_service
    application.state.topic_service = topic_service
    application.state.draft_service = draft_service
    application.state.draft_generation_service = draft_generation_service
    application.state.simulation_service = simulation_service
    application.state.skill_service = skill_service
    application.state.agent_service = agent_service
    application.state.agent_conversation_service = agent_conversation_service
    application.state.asset_proposal_service = asset_proposal_service
    application.state.content_collaboration_service = content_collaboration_service
    application.state.workflow_asset_service = workflow_asset_service
    application.state.model_call_service = model_call_service
    application.state.context_access_service = context_access_service
    application.state.account_workflow_service = account_workflow_service
    application.state.trend_workflow_service = trend_workflow_service
    application.state.video_workflow_service = video_workflow_service
    application.state.simulation_workflow_service = simulation_workflow_service
    application.state.workflow_worker = workflow_worker
    application.state.reader_selection_service = reader_selection_service
    application.state.reader_selection_requests = reader_selection_requests
    application.state.reader_selection_worker = reader_selection_worker
    application.state.panel_interview_service = panel_interview_service
    application.include_router(panel_interview_router(panel_interview_service))
    application.include_router(simulation_review_router(SimulationTopicIdeaService(database)))
    application.include_router(reader_selection_router(
        reader_selection_requests, reader_selection_worker,
    ))
    application.state.xhs_capture_service = xhs_capture_service

    @application.exception_handler(ApplicationError)
    async def handle_application_error(_request: Request, error: ApplicationError) -> JSONResponse:
        status_code = 400
        if isinstance(error, NotFoundError):
            status_code = 404
        elif isinstance(error, ConflictError):
            status_code = 409
        elif isinstance(error, ValidationError):
            status_code = 422
        return JSONResponse(
            status_code=status_code,
            content={"detail": str(error)},
        )

    @application.get("/api/health", response_model=HealthResponse, tags=["health"])
    async def health() -> HealthResponse:
        return HealthResponse(status="ok", service="creator-workspace-backend")

    application.state.audience_analysis_service = audience_analysis_service
    application.state.simulated_fan_service = simulated_fan_service

    @application.get(
        "/api/workspaces/{workspace_id}/simulated-fans", response_model=list[FanResponse]
    )
    def list_simulated_fans(workspace_id: str):
        return simulated_fan_service.list(workspace_id)

    @application.post(
        "/api/workspaces/{workspace_id}/simulated-fans", response_model=FanResponse, status_code=201
    )
    def create_simulated_fan(workspace_id: str, payload: FanCreate):
        return simulated_fan_service.create(workspace_id, payload)

    @application.get("/api/simulated-fan-voices", response_model=list[FanVoiceTemplateResponse])
    def list_simulated_fan_voices():
        return list_fan_voice_templates()

    @application.post(
        "/api/simulated-fans/{fan_id}/variants", response_model=list[FanResponse], status_code=201
    )
    def create_simulated_fan_variants(fan_id: str, payload: FanVariantsCreate):
        return simulated_fan_service.create_variants(fan_id, payload)

    @application.get("/api/simulated-fans/{fan_id}", response_model=FanResponse)
    def get_simulated_fan(fan_id: str):
        return simulated_fan_service.get(fan_id)

    @application.patch("/api/simulated-fans/{fan_id}", response_model=FanResponse)
    def update_simulated_fan(fan_id: str, payload: FanUpdate):
        return simulated_fan_service.update(fan_id, payload)

    @application.post(
        "/api/workspaces/{workspace_id}/audience-analyses",
        response_model=AudienceAnalysisResponse,
        status_code=202,
    )
    async def create_audience_analysis(workspace_id: str, payload: AudienceAnalysisCreate):
        return audience_analysis_service.create(workspace_id, payload)

    @application.get(
        "/api/workspaces/{workspace_id}/audience-analyses",
        response_model=list[AudienceAnalysisResponse],
    )
    def list_audience_analyses(workspace_id: str):
        return audience_analysis_service.list(workspace_id)

    @application.get("/api/audience-analyses/{run_id}", response_model=AudienceAnalysisResponse)
    def get_audience_analysis(run_id: str):
        return audience_analysis_service.get(run_id)

    application.include_router(
        create_api_router(
            workspace_service,
            input_asset_service,
            media_asset_service,
            analysis_service,
            topic_service,
            draft_service,
            draft_generation_service,
            simulation_service,
            skill_service,
            agent_service,
            agent_conversation_service,
            asset_proposal_service,
            workflow_asset_service,
            workflow_worker,
            xhs_import_service,
            xhs_capture_service,
            content_collaboration_service,
        )
    )
    return application


app = create_app()
