"""Bounded, message-driven content collaboration on top of LangGraph.

This module intentionally owns no product writes. A caller persists creator
messages and candidate artifacts, then gives the graph one pending message to
process. The graph decides only which fixed specialist gets that message next.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Literal, Protocol, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.errors import ValidationError

Role = Literal["creator", "research", "writing", "review"]
SpecialistRole = Literal["research", "writing", "review"]
Text = StringConstraints(strip_whitespace=True, min_length=1, max_length=8_000)

SPECIALISTS: set[str] = {"research", "writing", "review"}
ALL_RECIPIENTS: set[str] = {"creator", *SPECIALISTS}
ALLOWED_NEXT_RECIPIENTS: dict[SpecialistRole, set[Role]] = {
    "research": {"writing", "creator"},
    "writing": {"research", "review", "creator"},
    "review": {"research", "writing", "creator"},
}


class CollaborationMessage(BaseModel):
    """Product message envelope; backend supplies identity and timestamps."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(default_factory=lambda: str(uuid4()))
    sender: Role
    to: Role
    content: str = Field(min_length=1, max_length=8_000)
    reply_to: str | None = Field(default=None, min_length=1)
    artifact_refs: list[dict[str, str]] = Field(default_factory=list, max_length=12)


class SpecialistTurn(BaseModel):
    """The only model result accepted from a specialist node."""

    model_config = ConfigDict(extra="forbid")

    content: str = Field(min_length=1, max_length=8_000)
    to: Role | None = None
    artifact_refs: list[dict[str, str]] = Field(default_factory=list, max_length=12)
    # This is server-supplied provider receipt data, never text returned by a
    # model as part of its wire schema.  The durable session service stores it
    # next to the resulting specialist message for auditability.
    model_metadata: dict[str, Any] = Field(default_factory=dict)


class CollaborationState(TypedDict, total=False):
    thread_id: str
    pending: dict[str, Any] | None
    transcript: list[dict[str, Any]]
    remaining_turns: int
    status: Literal["running", "waiting_creator", "idle", "failed"]
    error: str
    turn_metadata: dict[str, Any]


class SpecialistProvider(Protocol):
    async def run(
        self,
        *,
        role: SpecialistRole,
        message: CollaborationMessage,
        context: dict[str, Any],
    ) -> SpecialistTurn: ...


ContextBuilder = Callable[
    [SpecialistRole, CollaborationMessage, list[dict[str, Any]]], dict[str, Any]
]


class ContentCollaborationGraph:
    """One-at-a-time message routing with no model-driven dispatcher."""

    def __init__(self, provider: SpecialistProvider, context_builder: ContextBuilder) -> None:
        self.provider = provider
        self.context_builder = context_builder
        self.graph = self._build_graph()
        self.step_graph = self._build_graph(stop_after_specialist=True)

    async def run(
        self,
        *,
        thread_id: str,
        initial_message: CollaborationMessage,
        max_turns: int = 3,
        prior_transcript: list[CollaborationMessage] | None = None,
    ) -> CollaborationState:
        if initial_message.to not in ALL_RECIPIENTS:
            raise ValidationError("协作消息的收件人不受支持")
        if max_turns < 1 or max_turns > 8:
            raise ValidationError("协作回合预算必须在 1 到 8 之间")
        transcript = self._hydrate_transcript(
            initial_message=initial_message,
            prior_transcript=prior_transcript,
        )
        state = await self.graph.ainvoke(
            {
                "thread_id": thread_id,
                "pending": initial_message.model_dump(),
                "transcript": transcript,
                "remaining_turns": max_turns,
                "status": "running",
                "error": "",
            },
            config={"configurable": {"thread_id": thread_id}},
        )
        return CollaborationState(**state)

    async def advance_one(
        self,
        *,
        thread_id: str,
        pending_message: CollaborationMessage,
        transcript: list[CollaborationMessage],
        remaining_turns: int,
    ) -> CollaborationState:
        """Advance exactly one addressed specialist or resolve a wait state.

        Durable product services use this boundary to append every outbound
        message atomically before another role is invoked.  The existing
        ``run`` convenience method remains useful for in-memory unit tests.
        """
        if pending_message.to not in ALL_RECIPIENTS:
            raise ValidationError("协作消息的收件人不受支持")
        if remaining_turns < 0 or remaining_turns > 8:
            raise ValidationError("协作回合余额必须在 0 到 8 之间")
        hydrated = self._hydrate_transcript(
            initial_message=pending_message,
            prior_transcript=transcript,
        )
        state = await self.step_graph.ainvoke(
            {
                "thread_id": thread_id,
                "pending": pending_message.model_dump(),
                "transcript": hydrated,
                "remaining_turns": remaining_turns,
                "status": "running",
                "error": "",
            },
            config={"configurable": {"thread_id": thread_id}},
        )
        return CollaborationState(**state)

    @staticmethod
    def _hydrate_transcript(
        *,
        initial_message: CollaborationMessage,
        prior_transcript: list[CollaborationMessage] | None,
    ) -> list[dict[str, Any]]:
        # Product storage is append-only; avoid duplicating the pending message
        # when it is already present in the caller's rehydrated transcript.
        transcript = [
            message.model_dump()
            for message in (prior_transcript or [])
            if message.id != initial_message.id
        ]
        transcript.append(initial_message.model_dump())
        return transcript

    def _build_graph(self, *, stop_after_specialist: bool = False):
        builder = StateGraph(CollaborationState)
        builder.add_node("dispatch", self._dispatch)
        for role in sorted(SPECIALISTS):
            builder.add_node(role, self._specialist(role))
        builder.add_edge(START, "dispatch")
        builder.add_conditional_edges(
            "dispatch",
            self._next_node,
            {"research": "research", "writing": "writing", "review": "review", "end": END},
        )
        for role in SPECIALISTS:
            builder.add_edge(role, END if stop_after_specialist else "dispatch")
        return builder.compile()

    async def _dispatch(self, state: CollaborationState) -> dict[str, Any]:
        pending = state.get("pending")
        if pending is None:
            return {"status": "idle"}
        message = CollaborationMessage.model_validate(pending)
        if message.to == "creator":
            return {"status": "waiting_creator"}
        if message.to not in SPECIALISTS:
            return {"status": "failed", "error": "协作消息收件人非法", "pending": None}
        if state.get("remaining_turns", 0) <= 0:
            budget_message = CollaborationMessage(
                sender="review",
                to="creator",
                content="本轮协作已达到回合上限，请确认下一步要继续追问还是采用当前结论。",
                reply_to=message.id,
            ).model_dump()
            return {
                "status": "waiting_creator",
                "pending": budget_message,
                "transcript": [*state.get("transcript", []), budget_message],
            }
        return {"status": "running"}

    @staticmethod
    def _next_node(state: CollaborationState) -> str:
        pending = state.get("pending")
        if pending is None or state.get("status") in {"idle", "waiting_creator", "failed"}:
            return "end"
        recipient = pending.get("to")
        return recipient if recipient in SPECIALISTS else "end"

    def _specialist(self, role: SpecialistRole):
        async def invoke(state: CollaborationState) -> dict[str, Any]:
            message = CollaborationMessage.model_validate(state["pending"])
            transcript = list(state.get("transcript", []))
            context = self.context_builder(role, message, transcript)
            try:
                turn = await self.provider.run(role=role, message=message, context=context)
            except Exception as error:
                return {
                    "status": "failed",
                    "error": str(error) or error.__class__.__name__,
                    "pending": None,
                }
            recipient = turn.to or "creator"
            if recipient not in ALLOWED_NEXT_RECIPIENTS[role]:
                return {
                    "status": "failed",
                    "error": f"{role} 的协作交接目标不受支持",
                    "pending": None,
                }
            output = CollaborationMessage(
                sender=role,
                to=recipient,
                content=turn.content,
                reply_to=message.id,
                artifact_refs=turn.artifact_refs,
            )
            return {
                "pending": output.model_dump(),
                "transcript": [*transcript, output.model_dump()],
                "remaining_turns": state["remaining_turns"] - 1,
                "status": "running",
                "turn_metadata": turn.model_metadata,
            }

        return invoke
