import asyncio
import json
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError as SchemaError
from test_workspace_api import create_workspace, send

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import ModelCallResponse
from app.services.common import utc_now
from app.services.panel_interviews import (
    MAX_CONCURRENT_REPLIES,
    PanelInterviewCreate,
    PanelInterviewService,
    build_interview_prompt,
)


@pytest.fixture
def panel(app):
    wid = create_workspace(app)["id"]
    sid = str(uuid4())
    personas = [{"id": f"reader-{i}", "name": f"读者 {i}", "profile": "希望看清第一步"}
                for i in range(5)]
    snapshot = {"mode": "demo", "topic": {"title": "写下第一句话", "body": "先写一句话，再读出来。",
                                           "angle": "作者的内部创作策略"}}
    reactions = [
        {"personaId": "reader-0", "action": "comment", "quote": "我愿意试一下。",
         "understanding": "绝不能公开的内部理解", "concerns": ["内部顾虑也不公开"]},
        {"personaId": "reader-1", "action": "no_comment", "quote": "并未公开说出的留言"},
    ]
    debate = [{"personaId": "reader-2", "response": "@reader-0 我也想试试。",
               "targetedAt": "reader-0", "replyToId": "initial:reader-0",
               "changedMindReason": "其他内部记录"}]
    now = utc_now()
    with app.state.database.transaction() as connection:
        connection.execute(
            "INSERT INTO simulation_runs (id,workspace_id,status,input_snapshot_json,"
            "persona_definitions_json,reaction_results_json,debate_results_json,"
            "created_at,completed_at,updated_at) VALUES (?,?,'completed',?,?,?,?,?,?,?)",
            (sid, wid, json.dumps(snapshot), json.dumps(personas), json.dumps(reactions),
             json.dumps(debate), now, now, now),
        )
    return wid, sid, personas


def question(key="first", recipient=None, content="哪句话让你愿意试一下？"):
    return PanelInterviewCreate(request_key=key, question=content, recipient_persona_id=recipient)


def path(wid, sid):
    return f"/api/workspaces/{wid}/simulation-runs/{sid}/interviews"


async def until(check):
    async with asyncio.timeout(3):
        while not check():
            await asyncio.sleep(0.003)


class ControlledProvider:
    def __init__(self, gates=None, failures=()):
        self.calls = []
        self.gates = gates or {}
        self.failures = failures
        self.active = self.maximum_active = 0

    async def reply(self, context):
        self.calls.append(deepcopy(context))
        identity = context["reader"]["id"]
        self.active += 1
        self.maximum_active = max(self.maximum_active, self.active)
        try:
            if identity in self.gates:
                await self.gates[identity].wait()
            if identity in self.failures:
                raise RuntimeError("provider-secret-token-must-not-leak")
            return ModelCallResponse(output={"reply": f"{identity}：第一句话让我觉得可以开始。"},
                                     model_metadata={"provider": "test", "modelCalled": False})
        finally:
            self.active -= 1


def test_bounded_parallel_replies_appear_before_last_reply_and_never_drop_fifth(app, panel):
    wid, sid, personas = panel
    service = app.state.panel_interview_service
    original = app.state.simulation_service.get(sid).model_dump(mode="json")

    async def run():
        gates = {p["id"]: asyncio.Event() for p in personas}
        provider = ControlledProvider(gates)
        service.demo_provider = provider
        created = service.create(wid, sid, question())
        task = asyncio.create_task(service.execute(wid, sid, created.id))
        await until(lambda: len(provider.calls) == MAX_CONCURRENT_REPLIES)
        assert service.get(wid, sid, created.id).completed_replies == 0
        gates["reader-0"].set()
        await until(lambda: service.get(wid, sid, created.id).completed_replies == 1)
        interim = service.get(wid, sid, created.id)
        assert interim.status == "running"
        assert interim.total_replies == 5
        assert len(interim.pending_participant_ids) == 4
        assert interim.messages[0].role == "author"
        assert interim.messages[1].sender_name == "读者 0"
        assert interim.messages[1].recipient_name == "作者"
        assert interim.messages[1].reply_to_id == interim.messages[0].id
        for gate in gates.values():
            gate.set()
        await task
        result = service.get(wid, sid, created.id)
        assert result.status == "completed"
        assert result.completed_replies == result.total_replies == 5
        assert result.pending_participant_ids == []
        assert provider.maximum_active == MAX_CONCURRENT_REPLIES
        assert len(provider.calls) == 5

    asyncio.run(run())
    assert app.state.simulation_service.get(sid).model_dump(mode="json") == original


def test_frozen_target_roster_and_only_public_history_reach_reader(app, panel):
    wid, sid, _ = panel
    service = app.state.panel_interview_service
    provider = ControlledProvider()
    service.demo_provider = provider
    first = service.create(wid, sid, question(recipient="reader-0"))
    asyncio.run(service.execute(wid, sid, first.id))
    second = service.create(wid, sid, question(
        "followup", "reader-2", "补充：每天一句，够具体吗？",
    ))
    with app.state.database.transaction() as connection:
        connection.execute(
            "UPDATE simulation_runs SET input_snapshot_json=?,persona_definitions_json=? "
            "WHERE id=?",
            (json.dumps({"mode": "demo", "topic": {"title": "后来被修改的作品",
                                                 "body": "其他材料"}}),
             json.dumps([{"id": "new-reader", "name": "后来的人物"}]), sid),
        )
    asyncio.run(service.execute(wid, sid, second.id))
    captured = provider.calls[-1]
    assert captured["reader"]["id"] == "reader-2"
    assert captured["target"]["title"] == "写下第一句话"
    assert captured["authorQuestion"] == "补充：每天一句，够具体吗？"
    history = captured["publicHistory"]
    assert [m["senderName"] for m in history] == ["读者 0", "读者 2", "作者", "读者 0"]
    assert history[1]["content"] == "@读者 0 我也想试试。"
    system, prompt = build_interview_prompt(captured)
    projected = json.loads(prompt)
    assert projected["publicHistory"] == history
    assert projected["authorQuestion"] == captured["authorQuestion"]
    assert projected["publicHistory"][0]["content"] == "我愿意试一下。"
    assert "内部推理" in system
    for private in ("绝不能公开", "内部顾虑", "其他内部记录", "并未公开", "内部创作策略"):
        assert private not in prompt
    assert '"id"' not in prompt
    assert len(service.list(wid, sid)) == 2
    assert service.get(wid, sid, second.id).recipient_name == "读者 2"


def test_revisit_uses_only_public_words_as_prior_concerns_and_preserves_intent():
    public_history = [{"senderName": "先试一步的读者", "content": "这一句让我想试试。"}]
    context = {
        "reader": {"id": "reader-a", "name": "先试一步的读者",
                   "coreConcern": "遇到阻力时如何继续行动", "expressionStyle": "直接说感受"},
        "participants": [{"id": "reader-a", "name": "先试一步的读者"}],
        "target": {"targetType": "topic", "title": "从今天开始", "body": "此刻就触手可及。"},
        "publicHistory": public_history,
        "authorQuestion": "我改了那句话，你现在怎么看？",
        "independentReaction": {"concerns": ["未公开的疑问"], "understanding": "内部理解"},
        "synthesis": {"recommendation": "不是聊天的编辑判断"},
    }
    before = deepcopy(context)
    system, prompt = build_interview_prompt(context)
    projected = json.loads(prompt)
    assert set(projected) == {"reader", "participants", "target", "publicHistory", "authorQuestion"}
    assert projected["publicHistory"] == public_history
    assert projected["reader"]["coreConcern"] == "遇到阻力时如何继续行动"
    encoded_history = json.dumps(projected["publicHistory"], ensure_ascii=False)
    assert "遇到阻力时如何继续行动" not in encoded_history
    assert "未公开的疑问" not in prompt
    assert "内部理解" not in prompt
    assert "不是聊天的编辑判断" not in prompt
    assert context == before
    assert "只有 publicHistory 中你本人实际说过的话" in system
    assert "不是既有聊天记录" in system
    assert "不能追认成上次的疑问" in system
    assert "上次只有认可时，可以继续认可" in system
    assert "行动重点或作者表达意图" in system
    assert "更喜欢原句" in system
    assert "不将新增的制度、事件、处境或个人经历安到作者或自己身上" in system


def test_same_request_key_is_idempotent_even_after_shutdown_and_changes_conflict(app, panel):
    wid, sid, _ = panel
    service = app.state.panel_interview_service
    payload = question()
    with ThreadPoolExecutor(max_workers=4) as pool:
        values = list(pool.map(lambda _: service.create(wid, sid, payload).id, range(4)))
    assert len(set(values)) == 1
    assert len(service.list(wid, sid)) == 1
    response = send(app, "POST", path(wid, sid), json=payload.model_dump(by_alias=True))
    assert response.status_code == 202  # Replay needs no active worker or paid call.
    assert response.json()["id"] == values[0]
    with pytest.raises(ConflictError):
        service.create(wid, sid, question(content="changed"))
    with pytest.raises(ConflictError):
        service.create(wid, sid, question("different-key"))


@pytest.mark.parametrize(("target", "expected", "absent"), [
    ({"targetType": "account"}, "本次是账号级访谈", "本次是创作级试读"),
    ({"targetType": "note"}, "本次是已发布笔记复盘", "本次是账号级访谈"),
    ({"targetType": "topic"}, "本次是创作级试读", "原笔记保持原样"),
])
def test_interview_preserves_target_purpose(target, expected, absent):
    system, _ = build_interview_prompt({"target": target})
    assert expected in system
    assert absent not in system


def test_recipient_and_workspace_are_checked_before_any_record_or_call(app, panel):
    wid, sid, _ = panel
    service = app.state.panel_interview_service
    other = create_workspace(app)["id"]
    with pytest.raises(ValidationError, match="实际参与"):
        service.create(wid, sid, question(recipient="not-a-participant"))
    with pytest.raises(NotFoundError):
        service.create(other, sid, question())
    assert service.list(wid, sid) == []
    created = service.create(wid, sid, question())
    for action in (service.get, service.cancel):
        with pytest.raises(NotFoundError):
            action(other, sid, created.id)
    with pytest.raises(NotFoundError):
        service.list(other, sid)


def test_failed_or_unfinished_initial_simulation_is_not_interviewable(app, panel):
    wid, sid, _ = panel
    service = app.state.panel_interview_service
    for status in ("pending", "running", "failed"):
        with app.state.database.transaction() as connection:
            connection.execute("UPDATE simulation_runs SET status=? WHERE id=?", (status, sid))
        with pytest.raises(ValidationError, match="结束"):
            service.create(wid, sid, question())
    with app.state.database.transaction() as connection:
        connection.execute("UPDATE simulation_runs SET status='partially_completed' WHERE id=?",
                           (sid,))
    assert service.create(wid, sid, question()).status == "pending"


def test_failures_preserve_other_replies_and_never_expose_provider_secrets(app, panel):
    wid, sid, _ = panel
    service = app.state.panel_interview_service
    provider = ControlledProvider(failures={"reader-0", "reader-1"})
    service.demo_provider = provider
    created = service.create(wid, sid, question())
    asyncio.run(service.execute(wid, sid, created.id))
    result = service.get(wid, sid, created.id)
    assert result.status == "partially_completed"
    assert result.completed_replies == 3
    assert len(result.failures) == 2
    assert "2 位" in result.error
    assert "secret" not in result.model_dump_json()
    assert len(provider.calls) == 5
    assert result.pending_participant_ids == []
    assert service.create(wid, sid, question("new-question")).status == "pending"


def test_http_disconnect_does_not_stop_work_and_cancellation_keeps_ready_reply(app, panel):
    wid, sid, personas = panel
    service = app.state.panel_interview_service
    service.poll_interval = 0.003

    async def run():
        gates = {p["id"]: asyncio.Event() for p in personas}
        provider = ControlledProvider(gates)
        service.demo_provider = provider
        assert service.start()
        competitor = PanelInterviewService(app.state.database)
        assert not competitor.start()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                response = await client.post(path(wid, sid), json={
                    "requestKey": "http", "question": "你们看明白了吗？",
                    "recipientPersonaId": None,
                })
                assert response.status_code == 202, response.text
                iid = response.json()["id"]
            await until(lambda: len(provider.calls) == 4)
            gates["reader-0"].set()
            await until(lambda: service.get(wid, sid, iid).completed_replies == 1)
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test",
            ) as client:
                result = await client.post(f"{path(wid, sid)}/{iid}/cancel")
                assert result.status_code == 200
                assert result.json()["status"] == "cancelled"
                assert result.json()["completedReplies"] == 1
                assert (await client.get(path(wid, sid))).json()[0]["id"] == iid
            for gate in gates.values():
                gate.set()
            await until(lambda: provider.active == 0)
            final = service.get(wid, sid, iid)
            assert final.status == "cancelled"
            assert final.completed_replies == 1
            assert final.pending_participant_ids == []
        finally:
            await competitor.shutdown()
            await service.shutdown()

    asyncio.run(run())


def test_shutdown_and_restart_preserve_partial_and_do_not_retry_paid_work(app, panel):
    wid, sid, personas = panel
    service = app.state.panel_interview_service
    service.poll_interval = 0.003

    async def run():
        gates = {p["id"]: asyncio.Event() for p in personas}
        provider = ControlledProvider(gates)
        service.demo_provider = provider
        service.start()
        created = service.create(wid, sid, question())
        await until(lambda: len(provider.calls) == 4)
        gates["reader-0"].set()
        await until(lambda: service.get(wid, sid, created.id).completed_replies == 1)
        await service.shutdown()
        after = service.get(wid, sid, created.id)
        assert after.status == "partially_completed"
        assert "中断" in after.error
        count = len(provider.calls)
        pending = service.create(wid, sid, question("offline-question"))
        assert service.start()
        assert service.get(wid, sid, pending.id).status == "failed"
        await asyncio.sleep(0.015)
        assert len(provider.calls) == count
        assert service.get(wid, sid, created.id).completed_replies == 1
        await service.shutdown()

    asyncio.run(run())


def test_invalid_model_reply_fails_without_automatic_retry(app, panel):
    wid, sid, _ = panel
    service = app.state.panel_interview_service

    class InvalidProvider:
        calls = 0

        async def reply(self, context):
            self.calls += 1
            return ModelCallResponse(output={"reply": "", "internalReasoning": "private"},
                                     model_metadata={})

    provider = InvalidProvider()
    service.demo_provider = provider
    created = service.create(wid, sid, question(recipient="reader-0"))
    asyncio.run(service.execute(wid, sid, created.id))
    asyncio.run(service.execute(wid, sid, created.id))
    result = service.get(wid, sid, created.id)
    assert result.status == "failed"
    assert result.completed_replies == 0
    assert len(result.messages) == 1
    assert provider.calls == 1


def test_live_interview_needs_live_provider_and_names_replace_id_mentions(app, panel):
    wid, sid, _ = panel
    service = app.state.panel_interview_service
    with app.state.database.transaction() as connection:
        snapshot = json.loads(connection.execute(
            "SELECT input_snapshot_json FROM simulation_runs WHERE id=?", (sid,),
        ).fetchone()[0])
        snapshot["mode"] = "live"
        connection.execute("UPDATE simulation_runs SET input_snapshot_json=? WHERE id=?",
                           (json.dumps(snapshot), sid))
    with pytest.raises(ValidationError, match="连接模型"):
        service.create(wid, sid, question())

    class MentionProvider:
        async def reply(self, context):
            return ModelCallResponse(output={"reply": "@initial:reader-1 这一步我也看懂了。"},
                                     model_metadata={"provider": "test"})

    service.live_provider = MentionProvider()
    created = service.create(wid, sid, question(recipient="reader-2"))
    asyncio.run(service.execute(wid, sid, created.id))
    final = service.get(wid, sid, created.id)
    assert final.mode == "live"
    assert final.messages[-1].content == "@读者 1 这一步我也看懂了。"


@pytest.mark.parametrize("fields", [
    {"question": " "}, {"question": "x" * 2001}, {"requestKey": " "},
    {"recipientPersonaId": " "}, {"participants": []}, {"context": {}},
])
def test_input_contract_rejects_blanks_long_questions_and_forged_context(fields):
    with pytest.raises(SchemaError):
        PanelInterviewCreate.model_validate({"requestKey": "r", "question": "为什么？", **fields})
