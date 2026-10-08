import asyncio
import json

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.errors import NotFoundError
from app.models import (
    ContentCollaborationMessageCreate,
    ContentCollaborationSessionCreate,
    WorkspaceCreate,
)
from app.repositories.topics import TopicRepository
from app.services.common import utc_now
from app.services.content_collaboration import SpecialistTurn


class GatedProvider:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release_research = asyncio.Event()
        self.calls: list[tuple[str, dict]] = []
        self.inspect_before_writing = None
        self.persisted_before_writing: list[str] | None = None

    async def run(self, *, role, message, context):
        self.calls.append((role, context))
        if role == "research":
            self.started.set()
            await self.release_research.wait()
            return SpecialistTurn(content="研究结论交给写作。", to="writing")
        if role == "writing":
            if self.inspect_before_writing is not None:
                self.persisted_before_writing = self.inspect_before_writing()
            return SpecialistTurn(content="写作结构交给评审。", to="review")
        return SpecialistTurn(content="请创作者确认转折细节。", to="creator")


class RecordingLiveProvider:
    def __init__(self, *, next_recipient="creator") -> None:
        self.next_recipient = next_recipient
        self.calls: list[tuple[str, dict]] = []

    async def run(self, *, role, message, context):
        self.calls.append((role, context))
        return SpecialistTurn(
            content="实时研究已标出一条待创作者确认的事实边界。",
            to=self.next_recipient,
            model_metadata={
                "provider": "qwen",
                "model": "qwen-plus",
                "operation": "content_collaboration_turn",
                "systemPromptHash": "test-prompt-hash",
                "usage": {"total_tokens": 9},
                "candidateSuggestions": [
                    {
                        "kind": "open_question",
                        "title": "确认事实",
                        "body": "请确认当时最关键的判断标准。",
                        "confidence": "needs_creator",
                        "evidenceRefs": [],
                    }
                ],
            },
        )


class ChainedHandoffProvider:
    """Models a three-role run while exposing each durable handoff to tests."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def run(self, *, role, message, context):
        self.calls.append((role, context))
        if role == "research":
            return SpecialistTurn(
                content="研究确认了可写的经历顺序。",
                to="writing",
                model_metadata={
                    "provider": "qwen",
                    "candidateSuggestions": [
                        {
                            "kind": "evidence",
                            "title": "经历顺序",
                            "body": "把犹豫与决定按发生顺序写，形成可跟随的判断过程。",
                            "confidence": "supported",
                            "evidenceRefs": [
                                {"sourceId": "target:topic", "quote": "从一个选择切入"}
                            ],
                        }
                    ],
                },
            )
        if role == "writing":
            return SpecialistTurn(
                content="写作形成了从犹豫到判断的结构。",
                to="review",
                model_metadata={
                    "provider": "qwen",
                    "candidateSuggestions": [
                        {
                            "kind": "outline",
                            "title": "判断过程结构",
                            "body": (
                                "开场交代犹豫；推进展示取舍；转折写最终判断；"
                                "收束给读者可带走的判断方法。"
                            ),
                            "confidence": "supported",
                            "evidenceRefs": [
                                {"sourceId": "target:topic", "quote": "从一个选择切入"}
                            ],
                        }
                    ],
                },
            )
        return SpecialistTurn(
            content="评审建议保留犹豫，把判断标准放进转折。",
            to="creator",
            model_metadata={
                "provider": "qwen",
                "candidateSuggestions": [
                    {
                        "kind": "review_note",
                        "title": "先保留犹豫，再补判断标准",
                        "body": "保留犹豫带来的张力；优先补出最终判断所依据的标准。",
                        "confidence": "inference",
                        "evidenceRefs": [],
                    }
                ],
            },
        )


def create_topic(app: FastAPI, workspace_id: str, *, title: str = "原始选题") -> dict:
    with app.state.database.transaction() as connection:
        return TopicRepository().create(
            connection,
            workspace_id=workspace_id,
            title=title,
            angle="从一个选择切入",
            associated_pain_point="不知道如何讲清经历",
            why_it_fits="与账号风格一致",
            generated_snapshot_json="{}",
            source_analysis_run_id=None,
            source_workflow="manual",
            now=utc_now(),
        )


def create_workspace_and_topic(app: FastAPI, *, title: str = "原始选题") -> tuple[dict, dict]:
    workspace = app.state.workspace_service.create(
        WorkspaceCreate(name="协作测试工作区", account_positioning="具体、真诚地分享选择过程")
    )
    return workspace.model_dump(), create_topic(app, workspace.id, title=title)


async def until(check) -> None:
    async with asyncio.timeout(3):
        while not check():
            await asyncio.sleep(0.005)


def test_content_collaboration_defaults_to_live_qwen_mode() -> None:
    payload = ContentCollaborationMessageCreate(
        content="请研究这个选题。",
        recipient="research",
        request_key="default-live-mode",
    )
    assert payload.mode == "live"


def test_session_freezes_topic_context_and_is_workspace_scoped(app: FastAPI) -> None:
    workspace, topic = create_workspace_and_topic(app)
    service = app.state.content_collaboration_service
    created = service.create(
        workspace["id"],
        ContentCollaborationSessionCreate.model_validate(
            {
                "contextTarget": {"assetType": "topic", "assetId": topic["id"]},
                "requestKey": "create-once",
            }
        ),
    )
    replay = service.create(
        workspace["id"],
        ContentCollaborationSessionCreate.model_validate(
            {
                "contextTarget": {"assetType": "topic", "assetId": topic["id"]},
                "requestKey": "create-once",
            }
        ),
    )
    assert replay.id == created.id
    assert created.initial_context_snapshot["target"]["title"] == "原始选题"

    with app.state.database.transaction() as connection:
        connection.execute("UPDATE topics SET title = ? WHERE id = ?", ("改后的选题", topic["id"]))
    still_frozen = service.get(workspace["id"], created.id)
    assert still_frozen.initial_context_snapshot["target"]["title"] == "原始选题"

    other = app.state.workspace_service.create(
        WorkspaceCreate(name="另一账号", account_positioning="不同账号")
    )
    with pytest.raises(NotFoundError):
        service.get(other.id, created.id)


def test_message_run_persists_each_role_and_replay_does_not_duplicate(app: FastAPI) -> None:
    workspace, topic = create_workspace_and_topic(app)
    service = app.state.content_collaboration_service
    provider = GatedProvider()
    service.provider = provider
    session = service.create(
        workspace["id"],
        ContentCollaborationSessionCreate.model_validate(
            {"contextTarget": {"assetType": "topic", "assetId": topic["id"]}}
        ),
    )
    payload = ContentCollaborationMessageCreate(
        content="先核对这个经历的事实，再判断怎么写。",
        recipient="research",
        request_key="creator-turn-1",
        mode="demo",
    )
    provider.inspect_before_writing = lambda: [
        message.sender.value
        for message in service.get(workspace["id"], session.id).messages
    ]

    async def run() -> None:
        first = await service.send_message(workspace["id"], session.id, payload)
        await provider.started.wait()
        assert first.execution_status in {"queued", "running"}
        replay = await service.send_message(workspace["id"], session.id, payload)
        assert len(replay.messages) == 1
        assert len(provider.calls) == 1

        # The source asset changes after session creation; the specialist must
        # keep seeing the frozen target rather than silently rereading Topic.
        with app.state.database.transaction() as connection:
            connection.execute(
                "UPDATE topics SET title = ? WHERE id = ?",
                ("后来被改掉的标题", topic["id"]),
            )
        provider.release_research.set()
        await until(
            lambda: service.get(workspace["id"], session.id).execution_status
            == "waiting_creator"
        )

    asyncio.run(run())
    persisted = service.get(workspace["id"], session.id)
    assert [(message.sender.value, message.recipient.value) for message in persisted.messages] == [
        ("creator", "research"),
        ("research", "writing"),
        ("writing", "review"),
        ("review", "creator"),
    ]
    assert len(persisted.runs) == 1
    assert persisted.runs[0].status.value == "waiting_creator"
    assert len(provider.calls) == 3
    assert provider.persisted_before_writing == ["creator", "research"]
    assert provider.calls[0][1]["target"]["title"] == "原始选题"
    assert persisted.messages[-1].context_snapshot["sessionContextRef"]["sessionId"] == session.id
    with app.state.database.read() as connection:
        assert TopicRepository().get(connection, topic["id"])["title"] == "后来被改掉的标题"


def test_new_creator_turn_freezes_latest_saved_draft_without_rewriting_history(
    app: FastAPI,
) -> None:
    workspace, topic = create_workspace_and_topic(app)
    service = app.state.content_collaboration_service
    provider = RecordingLiveProvider()
    service.live_provider = provider
    session = service.create(
        workspace["id"],
        ContentCollaborationSessionCreate.model_validate(
            {"contextTarget": {"assetType": "topic", "assetId": topic["id"]}}
        ),
    )

    async def run() -> None:
        for number, body in enumerate(("第一轮前已保存的新稿", "第二轮人工改过的稿"), 1):
            with app.state.database.transaction() as connection:
                connection.execute("UPDATE topics SET body = ? WHERE id = ?", (body, topic["id"]))
            payload = ContentCollaborationMessageCreate(
                content="按当前稿件继续", recipient="research",
                request_key=f"fresh-{number}", mode="live"
            )
            await service.send_message(workspace["id"], session.id, payload)
            await until(
                lambda: service.get(workspace["id"], session.id).execution_status
                == "waiting_creator"
            )
        # Replaying an old network request keeps the old frozen run even after
        # later edits; it must not execute another model call with new content.
        await service.send_message(
            workspace["id"], session.id,
            ContentCollaborationMessageCreate(
                content="按当前稿件继续", recipient="research", request_key="fresh-1", mode="live"
            ),
        )

    asyncio.run(run())
    persisted = service.get(workspace["id"], session.id)
    assert len(provider.calls) == 2
    assert provider.calls[0][1]["target"]["body"] == "第一轮前已保存的新稿"
    assert provider.calls[1][1]["target"]["body"] == "第二轮人工改过的稿"
    assert persisted.initial_context_snapshot["target"]["body"] == topic["body"]
    assert [item.input_snapshot["sessionContext"]["target"]["body"] for item in persisted.runs] == [
        "第一轮前已保存的新稿", "第二轮人工改过的稿"
    ]


def test_workspace_scoped_http_session_routes(app: FastAPI) -> None:
    workspace, topic = create_workspace_and_topic(app)
    other = app.state.workspace_service.create(
        WorkspaceCreate(name="路由隔离账号", account_positioning="")
    )

    async def run() -> None:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            created = await client.post(
                f"/api/workspaces/{workspace['id']}/content-collaboration-sessions",
                json={
                    "contextTarget": {"assetType": "topic", "assetId": topic["id"]},
                    "requestKey": "route-session",
                },
            )
            assert created.status_code == 201
            session_id = created.json()["id"]
            listed = await client.get(
                f"/api/workspaces/{workspace['id']}/content-collaboration-sessions"
            )
            assert [item["id"] for item in listed.json()] == [session_id]
            sent = await client.post(
                f"/api/workspaces/{workspace['id']}/content-collaboration-sessions/{session_id}/messages",
                json={
                    "content": "请先梳理事实再给出结构。",
                    "recipient": "research",
                    "requestKey": "route-message",
                    "mode": "demo",
                },
            )
            assert sent.status_code == 200
            await until(
                lambda: app.state.content_collaboration_service.get(
                    workspace["id"], session_id
                ).execution_status
                == "waiting_creator"
            )
            completed = await client.get(
                f"/api/workspaces/{workspace['id']}/content-collaboration-sessions/{session_id}"
            )
            assert completed.json()["runs"][0]["status"] == "waiting_creator"
            assert len(completed.json()["messages"]) == 4
            inaccessible = await client.get(
                f"/api/workspaces/{other.id}/content-collaboration-sessions/{session_id}"
            )
            assert inaccessible.status_code == 404

    asyncio.run(run())


def test_live_mode_is_explicit_frozen_and_persists_provider_receipt(app: FastAPI) -> None:
    workspace, topic = create_workspace_and_topic(app)
    service = app.state.content_collaboration_service
    provider = RecordingLiveProvider()
    service.live_provider = provider
    session = service.create(
        workspace["id"],
        ContentCollaborationSessionCreate.model_validate(
            {"contextTarget": {"assetType": "topic", "assetId": topic["id"]}}
        ),
    )

    async def run() -> None:
        await service.send_message(
            workspace["id"],
            session.id,
            ContentCollaborationMessageCreate(
                content="请先研究这段经历的事实边界。",
                recipient="research",
                request_key="live-turn-1",
                mode="live",
            ),
        )
        await until(
            lambda: service.get(workspace["id"], session.id).execution_status
            == "waiting_creator"
        )

    asyncio.run(run())
    persisted = service.get(workspace["id"], session.id)
    assert [message.sender.value for message in persisted.messages] == ["creator", "research"]
    assert len(provider.calls) == 1
    assert provider.calls[0][1]["executionMode"] == "live"
    assert persisted.runs[0].input_snapshot["mode"] == "live"
    assert persisted.messages[0].model_metadata["executionMode"] == "live"
    receipt = persisted.messages[1].model_metadata
    assert receipt["provider"] == "qwen"
    assert receipt["model"] == "qwen-plus"
    assert receipt["executionMode"] == "live"
    assert receipt["candidateSuggestions"][0]["kind"] == "open_question"
    with app.state.database.read() as connection:
        unchanged = TopicRepository().get(connection, topic["id"])
    assert unchanged["title"] == "原始选题"


def test_live_roles_receive_structured_candidates_from_the_previous_persisted_turn(
    app: FastAPI,
) -> None:
    workspace, topic = create_workspace_and_topic(app)
    service = app.state.content_collaboration_service
    provider = ChainedHandoffProvider()
    service.live_provider = provider
    session = service.create(
        workspace["id"],
        ContentCollaborationSessionCreate.model_validate(
            {"contextTarget": {"assetType": "topic", "assetId": topic["id"]}}
        ),
    )

    async def run() -> None:
        await service.send_message(
            workspace["id"],
            session.id,
            ContentCollaborationMessageCreate(
                content="请把这次选择写成一条读者能跟下去的判断过程。",
                recipient="research",
                request_key="structured-handoffs",
                mode="live",
            ),
        )
        await until(
            lambda: service.get(workspace["id"], session.id).execution_status
            == "waiting_creator"
        )

    asyncio.run(run())
    persisted = service.get(workspace["id"], session.id)
    assert [role for role, _ in provider.calls] == ["research", "writing", "review"]

    research_message = persisted.messages[1]
    writing_message = persisted.messages[2]
    writing_context = provider.calls[1][1]
    review_context = provider.calls[2][1]
    assert writing_context["upstreamCandidates"] == [
        {
            "candidateId": f"{research_message.id}:0",
            "kind": "evidence",
            "title": "经历顺序",
            "body": "把犹豫与决定按发生顺序写，形成可跟随的判断过程。",
            "confidence": "supported",
            "evidenceRefs": [{"sourceId": "target:topic", "quote": "从一个选择切入"}],
        }
    ]
    assert review_context["upstreamCandidates"][0]["candidateId"] == f"{writing_message.id}:0"
    assert review_context["upstreamCandidates"][0]["kind"] == "outline"


def test_live_mode_without_provider_fails_without_running_demo_turn(app: FastAPI) -> None:
    workspace, topic = create_workspace_and_topic(app)
    service = app.state.content_collaboration_service
    service.live_provider = None
    session = service.create(
        workspace["id"],
        ContentCollaborationSessionCreate.model_validate(
            {"contextTarget": {"assetType": "topic", "assetId": topic["id"]}}
        ),
    )

    async def run() -> None:
        await service.send_message(
            workspace["id"],
            session.id,
            ContentCollaborationMessageCreate(
                content="请走实时协作。",
                recipient="research",
                request_key="live-without-provider",
                mode="live",
            ),
        )
        await until(
            lambda: service.get(workspace["id"], session.id).execution_status == "failed"
        )

    asyncio.run(run())
    failed = service.get(workspace["id"], session.id)
    assert [message.sender.value for message in failed.messages] == ["creator"]
    assert failed.runs[0].error_code == "live_provider_unavailable"


def test_startup_resumes_queued_run_from_persisted_graph_state(app: FastAPI) -> None:
    workspace, topic = create_workspace_and_topic(app)
    service = app.state.content_collaboration_service
    session = service.create(
        workspace["id"],
        ContentCollaborationSessionCreate.model_validate(
            {"contextTarget": {"assetType": "topic", "assetId": topic["id"]}}
        ),
    )
    with app.state.database.transaction() as connection:
        stored = service.repository.get_session(
            connection, workspace_id=workspace["id"], session_id=session.id
        )
        message = service.repository.append_message(
            connection,
            workspace_id=workspace["id"],
            session_id=session.id,
            sender_role="creator",
            recipient_role="research",
            content="这是重启前已经落库的指令。",
            artifact_refs_json="[]",
            context_snapshot_json="{}",
            model_metadata_json="{}",
            client_request_key="queued-before-restart",
            client_request_fingerprint="queued-before-restart/v1",
            now=utc_now(),
        )
        run = service.repository.create_run(
            connection,
            workspace_id=workspace["id"],
            session_id=session.id,
            request_key="queued-before-restart",
            request_fingerprint="queued-before-restart/v1",
            input_snapshot_json=json.dumps(
                {
                    "sessionContext": json.loads(stored["initial_context_snapshot_json"]),
                    "triggerMessage": service._message_for_graph(message),
                    "maxTurns": 3,
                },
                ensure_ascii=False,
            ),
            trigger_message_id=message["id"],
            graph_state_json=json.dumps(
                {
                    "pendingMessageId": message["id"],
                    "remainingTurns": 3,
                    "status": "queued",
                },
                ensure_ascii=False,
            ),
            now=utc_now(),
        )

    async def run_resume() -> None:
        service.resume_unfinished()
        await until(
            lambda: service.get(workspace["id"], session.id).execution_status
            == "waiting_creator"
        )

    asyncio.run(run_resume())
    resumed = service.get(workspace["id"], session.id)
    assert resumed.runs[0].id == run["id"]
    assert resumed.runs[0].status.value == "waiting_creator"
    assert [message.sender.value for message in resumed.messages] == [
        "creator",
        "research",
        "writing",
        "review",
    ]
