import asyncio

import pytest

from app.errors import ValidationError
from app.services.content_collaboration import (
    CollaborationMessage,
    ContentCollaborationGraph,
    SpecialistTurn,
)


class ScriptedProvider:
    def __init__(self, turns):
        self.turns = list(turns)
        self.calls = []

    async def run(self, *, role, message, context):
        self.calls.append((role, message, context))
        return self.turns.pop(0)


def context_for(role, message, transcript):
    return {"role": role, "received": message.id, "publicMessageCount": len(transcript)}


def message(to="research"):
    return CollaborationMessage(sender="creator", to=to, content="请先查证这个论点")


def test_routes_only_the_addressed_specialist_then_waits_for_creator():
    provider = ScriptedProvider(
        [
            SpecialistTurn(content="需要写作把依据改成更清楚的结构。", to="writing"),
            SpecialistTurn(content="已整理为一版候选提纲。", to=None),
        ]
    )
    graph = ContentCollaborationGraph(provider, context_for)
    state = asyncio.run(graph.run(thread_id="thread-1", initial_message=message(), max_turns=3))
    assert [call[0] for call in provider.calls] == ["research", "writing"]
    assert provider.calls[0][2]["publicMessageCount"] == 1
    assert state["status"] == "waiting_creator"
    assert state["pending"]["sender"] == "writing"
    assert state["pending"]["to"] == "creator"
    assert len(state["transcript"]) == 3


def test_budget_stops_before_an_unbounded_agent_loop():
    provider = ScriptedProvider([SpecialistTurn(content="请继续写作。", to="writing")])
    graph = ContentCollaborationGraph(provider, context_for)
    state = asyncio.run(graph.run(thread_id="thread-2", initial_message=message(), max_turns=1))
    assert [call[0] for call in provider.calls] == ["research"]
    assert state["status"] == "waiting_creator"
    assert state["pending"]["to"] == "creator"
    assert "回合上限" in state["pending"]["content"]


def test_creator_addressed_message_waits_without_model_call():
    provider = ScriptedProvider([])
    graph = ContentCollaborationGraph(provider, context_for)
    state = asyncio.run(graph.run(thread_id="thread-3", initial_message=message("creator")))
    assert provider.calls == []
    assert state["status"] == "waiting_creator"


def test_invalid_recipient_is_rejected_before_graph_execution():
    provider = ScriptedProvider([])
    graph = ContentCollaborationGraph(provider, context_for)
    invalid = {**message().model_dump(), "to": "unknown"}
    with pytest.raises((ValidationError, ValueError)):
        asyncio.run(
            graph.run(
                thread_id="thread-4",
                initial_message=CollaborationMessage.model_validate(invalid),
            )
        )


def test_rehydrated_transcript_is_visible_but_initial_message_is_not_duplicated():
    provider = ScriptedProvider([SpecialistTurn(content="继续处理", to=None)])
    graph = ContentCollaborationGraph(provider, context_for)
    earlier = CollaborationMessage(
        id="earlier",
        sender="writing",
        to="creator",
        content="此前的候选结构",
    )
    initial = message()
    state = asyncio.run(
        graph.run(
            thread_id="thread-5",
            initial_message=initial,
            max_turns=1,
            prior_transcript=[earlier, initial],
        )
    )

    assert provider.calls[0][2]["publicMessageCount"] == 2
    assert [item["id"] for item in state["transcript"]].count(initial.id) == 1


def test_advance_one_stops_after_one_specialist_for_durable_persistence():
    provider = ScriptedProvider(
        [SpecialistTurn(content="请交给写作继续。", to="writing")]
    )
    graph = ContentCollaborationGraph(provider, context_for)
    initial = message()

    state = asyncio.run(
        graph.advance_one(
            thread_id="thread-6",
            pending_message=initial,
            transcript=[initial],
            remaining_turns=3,
        )
    )

    assert [call[0] for call in provider.calls] == ["research"]
    assert state["pending"]["sender"] == "research"
    assert state["pending"]["to"] == "writing"
    assert state["remaining_turns"] == 2
    assert len(state["transcript"]) == 2


def test_role_cannot_route_to_a_specialist_outside_its_contract():
    provider = ScriptedProvider(
        [SpecialistTurn(content="研究不应直接交给评审。", to="review")]
    )
    graph = ContentCollaborationGraph(provider, context_for)

    state = asyncio.run(
        graph.advance_one(
            thread_id="thread-invalid-route",
            pending_message=message(),
            transcript=[],
            remaining_turns=3,
        )
    )

    assert state["status"] == "failed"
    assert state["pending"] is None
    assert "交接目标不受支持" in state["error"]
