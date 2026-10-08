"""Shared, in-memory event contract for long-running product workflows.

This module deliberately has no database dependency.  A workflow can use it while it
is running, while a polling/SSE endpoint can reconstruct equivalent events from a
persisted run later.  Keeping the contract here prevents the graph implementation
from becoming the public event schema.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypedDict
from uuid import uuid4

from app.services.common import utc_now

RunEventType = Literal[
    "run.created",
    "run.started",
    "run.succeeded",
    "run.partial",
    "run.failed",
    "stage.started",
    "stage.succeeded",
    "stage.failed",
]

RUN_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "run.created",
        "run.started",
        "run.succeeded",
        "run.partial",
        "run.failed",
        "stage.started",
        "stage.succeeded",
        "stage.failed",
    }
)


class RunEvent(TypedDict):
    """Stable event envelope shared by graph execution and product transports."""

    eventId: str
    runId: str
    runType: str
    stageKey: str | None
    status: str
    sequence: int
    occurredAt: str
    data: dict[str, Any]


def _new_event_id() -> str:
    return str(uuid4())


@dataclass(slots=True)
class RunEventEmitter:
    """Create ordered lifecycle events for one in-memory execution.

    It owns only a local sequence counter; durable history remains owned by the
    relevant business repository.  This lets existing workflow-specific schemas
    adopt the envelope without being forced into a shared run table.
    """

    run_id: str
    run_type: str
    sequence: int = 0
    event_id_factory: Callable[[], str] = _new_event_id
    clock: Callable[[], str] = utc_now

    def event(
        self,
        event_type: RunEventType,
        *,
        status: str,
        stage_key: str | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> RunEvent:
        """Build the next event without mutating a caller-owned payload."""
        if event_type not in RUN_EVENT_TYPES:
            raise ValueError(f"Unsupported run event type: {event_type}")
        self.sequence += 1
        payload = dict(data or {})
        # The envelope owns eventType, so model or stage payloads cannot shadow it.
        payload["eventType"] = event_type
        return RunEvent(
            eventId=self.event_id_factory(),
            runId=self.run_id,
            runType=self.run_type,
            stageKey=stage_key,
            status=str(status),
            sequence=self.sequence,
            occurredAt=self.clock(),
            data=payload,
        )

    def run_created(
        self, *, status: str, data: Mapping[str, Any] | None = None
    ) -> RunEvent:
        return self.event("run.created", status=status, data=data)

    def run_started(self, *, data: Mapping[str, Any] | None = None) -> RunEvent:
        return self.event("run.started", status="running", data=data)

    def stage_started(
        self, stage_key: str, *, data: Mapping[str, Any] | None = None
    ) -> RunEvent:
        return self.event(
            "stage.started", status="running", stage_key=stage_key, data=data
        )

    def stage_succeeded(
        self, stage_key: str, *, data: Mapping[str, Any] | None = None
    ) -> RunEvent:
        return self.event(
            "stage.succeeded", status="completed", stage_key=stage_key, data=data
        )

    def stage_failed(
        self, stage_key: str, *, data: Mapping[str, Any] | None = None
    ) -> RunEvent:
        return self.event("stage.failed", status="failed", stage_key=stage_key, data=data)

    def run_terminal(
        self, *, status: str, data: Mapping[str, Any] | None = None
    ) -> RunEvent:
        return self.event(terminal_event_type(status), status=status, data=data)


def terminal_event_type(status: str) -> RunEventType:
    """Map durable run status to the terminal event name used by the UI."""
    if status == "completed":
        return "run.succeeded"
    if status == "partially_completed":
        return "run.partial"
    return "run.failed"
