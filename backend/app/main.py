from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import create_api_router
from app.config import Settings
from app.db.database import SQLiteDatabase
from app.errors import ApplicationError, ConflictError, NotFoundError, ValidationError
from app.models import HealthResponse
from app.repositories import (
    AgentConversationRepository,
    AgentRepository,
    AnalysisRunRepository,
    AssetProposalRepository,
    DraftRepository,
    GraphCheckpointRepository,
    MediaAssetRepository,
    SimulationRunRepository,
    SkillRepository,
    SourceMaterialRepository,
    TopicRepository,
    WorkflowAssetRepository,
    WorkspaceRepository,
)
from app.services import (
    AgentConversationService,
    AgentService,
    AnalysisRunService,
    AssetProposalService,
    ContextAccessService,
    DraftGenerationService,
    DraftService,
    FakeAgentConversationModelProvider,
    FakeStructureModelProvider,
    InputAssetService,
    MediaAssetService,
    ModelCallService,
    QwenMediaService,
    RealAgentConversationModelProvider,
    RealStructureModelProvider,
    SimulationRunService,
    SkillService,
    TopicService,
    WorkflowAssetService,
    WorkflowWorkerService,
    WorkspaceService,
    XhsOfflineImportService,
)
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


def create_app(settings: Settings | None = None) -> FastAPI:
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
    workflow_asset_repository = WorkflowAssetRepository()
    checkpoint_repository = GraphCheckpointRepository()
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
    workspace_service = WorkspaceService(database, workspace_repository)
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
    xhs_import_service = XhsOfflineImportService(input_asset_service)
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

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        agent_conversation_service.resume_unfinished()
        await workflow_worker.resume_unfinished()
        try:
            yield
        finally:
            await agent_conversation_service.shutdown()
            await workflow_worker.shutdown()

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
    application.state.workflow_asset_service = workflow_asset_service
    application.state.model_call_service = model_call_service
    application.state.context_access_service = context_access_service
    application.state.account_workflow_service = account_workflow_service
    application.state.trend_workflow_service = trend_workflow_service
    application.state.video_workflow_service = video_workflow_service
    application.state.simulation_workflow_service = simulation_workflow_service
    application.state.workflow_worker = workflow_worker

    @application.exception_handler(ApplicationError)
    async def handle_application_error(
        _request: Request, error: ApplicationError
    ) -> JSONResponse:
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
        )
    )
    return application


app = create_app()
