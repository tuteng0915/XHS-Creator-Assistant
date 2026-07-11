from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api import create_api_router
from app.config import Settings
from app.db.database import SQLiteDatabase
from app.errors import ApplicationError, ConflictError, NotFoundError, ValidationError
from app.models import HealthResponse
from app.repositories import (
    AgentRepository,
    AnalysisRunRepository,
    DraftRepository,
    GraphCheckpointRepository,
    SimulationRunRepository,
    SkillRepository,
    SourceMaterialRepository,
    TopicRepository,
    WorkflowAssetRepository,
    WorkspaceRepository,
)
from app.services import (
    AgentService,
    AnalysisRunService,
    DraftGenerationService,
    DraftService,
    FakeStructureModelProvider,
    ModelCallService,
    RealStructureModelProvider,
    SimulationRunService,
    SkillService,
    SourceMaterialService,
    TopicService,
    WorkflowAssetService,
    WorkflowWorkerService,
    WorkspaceService,
)
from app.workflows import (
    AccountDiagnosisWorkflowService,
    AudienceSimulationWorkflowService,
    FakeAccountDiagnosisModelProvider,
    FakeAudienceSimulationModelProvider,
    FakeTrendAnalysisModelProvider,
    RealAccountDiagnosisModelProvider,
    RealAudienceSimulationModelProvider,
    RealTrendAnalysisModelProvider,
    TrendAnalysisWorkflowService,
)


def create_app(settings: Settings | None = None) -> FastAPI:
    active_settings = settings or Settings.from_environment()
    database = SQLiteDatabase(active_settings.database_path)
    database.migrate()

    workspace_repository = WorkspaceRepository()
    source_repository = SourceMaterialRepository()
    analysis_repository = AnalysisRunRepository()
    draft_repository = DraftRepository()
    topic_repository = TopicRepository()
    simulation_repository = SimulationRunRepository()
    skill_repository = SkillRepository()
    agent_repository = AgentRepository()
    workflow_asset_repository = WorkflowAssetRepository()
    checkpoint_repository = GraphCheckpointRepository()
    workspace_service = WorkspaceService(database, workspace_repository)
    source_service = SourceMaterialService(
        database,
        source_repository,
        workspace_repository,
        active_settings,
    )
    analysis_service = AnalysisRunService(
        database,
        analysis_repository,
        workspace_repository,
        source_repository,
        active_settings,
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
        simulation_workflow_service=simulation_workflow_service,
    )

    @asynccontextmanager
    async def lifespan(_application: FastAPI):
        await workflow_worker.resume_unfinished()
        try:
            yield
        finally:
            await workflow_worker.shutdown()

    application = FastAPI(
        title="Creator Workspace API",
        version="0.1.0",
        description="Workspace and source-material persistence for the creator prototype.",
        lifespan=lifespan,
    )
    application.state.settings = active_settings
    application.state.database = database
    application.state.workspace_service = workspace_service
    application.state.source_service = source_service
    application.state.analysis_service = analysis_service
    application.state.topic_service = topic_service
    application.state.draft_service = draft_service
    application.state.draft_generation_service = draft_generation_service
    application.state.simulation_service = simulation_service
    application.state.skill_service = skill_service
    application.state.agent_service = agent_service
    application.state.workflow_asset_service = workflow_asset_service
    application.state.model_call_service = model_call_service
    application.state.account_workflow_service = account_workflow_service
    application.state.trend_workflow_service = trend_workflow_service
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
            source_service,
            analysis_service,
            topic_service,
            draft_service,
            draft_generation_service,
            simulation_service,
            skill_service,
            agent_service,
            workflow_asset_service,
            model_call_service,
            account_workflow_service,
            trend_workflow_service,
            simulation_workflow_service,
            workflow_worker,
        )
    )
    return application


app = create_app()
