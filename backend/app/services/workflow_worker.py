from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress

from app.db.database import SQLiteDatabase
from app.models import WorkflowType
from app.repositories.analysis_runs import TERMINAL_STATUSES, AnalysisRunRepository
from app.repositories.simulation_runs import (
    SIMULATION_TERMINAL_STATUSES,
    SimulationRunRepository,
)
from app.workflows import (
    AccountDiagnosisWorkflowService,
    AudienceSimulationWorkflowService,
    TrendAnalysisWorkflowService,
    VideoCreatorQualityWorkflowService,
)


class WorkflowWorkerService:
    def __init__(
        self,
        *,
        database: SQLiteDatabase,
        analysis_repository: AnalysisRunRepository,
        simulation_repository: SimulationRunRepository,
        account_workflow_service: AccountDiagnosisWorkflowService,
        trend_workflow_service: TrendAnalysisWorkflowService,
        video_workflow_service: VideoCreatorQualityWorkflowService,
        simulation_workflow_service: AudienceSimulationWorkflowService,
    ) -> None:
        self.database = database
        self.analysis_repository = analysis_repository
        self.simulation_repository = simulation_repository
        self.account_workflow_service = account_workflow_service
        self.trend_workflow_service = trend_workflow_service
        self.video_workflow_service = video_workflow_service
        self.simulation_workflow_service = simulation_workflow_service
        self._tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()

    async def enqueue_analysis_run(self, run_id: str) -> bool:
        with self.database.read() as connection:
            row = self.analysis_repository.get(connection, run_id)
        if row["status"] in TERMINAL_STATUSES:
            return False
        workflow_type = WorkflowType(row["workflow_type"])
        if workflow_type == WorkflowType.ACCOUNT_DIAGNOSIS:
            execute = self.account_workflow_service.collect_events
        elif workflow_type == WorkflowType.TREND_ANALYSIS:
            execute = self.trend_workflow_service.collect_events
        else:
            execute = self.video_workflow_service.collect_events
        return await self._enqueue(("analysis", run_id), lambda: execute(run_id))

    async def enqueue_simulation_run(self, simulation_id: str) -> bool:
        with self.database.read() as connection:
            row = self.simulation_repository.get(connection, simulation_id)
        if row["status"] in SIMULATION_TERMINAL_STATUSES:
            return False
        return await self._enqueue(
            ("simulation", simulation_id),
            lambda: self.simulation_workflow_service.collect_events(simulation_id),
        )

    async def resume_unfinished(self) -> int:
        queued = 0
        with self.database.read() as connection:
            analysis_rows = self.analysis_repository.list_unfinished(connection)
            simulation_rows = self.simulation_repository.list_unfinished(connection)
        for row in analysis_rows:
            if await self.enqueue_analysis_run(row["id"]):
                queued += 1
        for row in simulation_rows:
            if await self.enqueue_simulation_run(row["id"]):
                queued += 1
        return queued

    async def wait_for_idle(self, timeout: float = 5.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            tasks = [task for task in self._tasks.values() if not task.done()]
            if not tasks:
                return
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError("Workflow worker did not become idle")
            await asyncio.wait(tasks, timeout=min(remaining, 0.1))

    async def shutdown(self) -> None:
        tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        self._tasks.clear()

    async def _enqueue(
        self,
        key: tuple[str, str],
        execute: Callable[[], Awaitable[object]],
    ) -> bool:
        async with self._lock:
            existing = self._tasks.get(key)
            if existing is not None and not existing.done():
                return False
            task = asyncio.create_task(self._run(key, execute))
            self._tasks[key] = task
            return True

    async def _run(
        self,
        key: tuple[str, str],
        execute: Callable[[], Awaitable[object]],
    ) -> None:
        try:
            await execute()
        finally:
            async with self._lock:
                if self._tasks.get(key) is asyncio.current_task():
                    self._tasks.pop(key, None)
