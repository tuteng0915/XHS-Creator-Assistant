import asyncio
from concurrent.futures import ThreadPoolExecutor

import pytest
from httpx import ASGITransport, AsyncClient
from test_creator_experience import topic
from test_reader_selection import proposal
from test_simulated_fans import seeded as seeded
from test_workspace_api import create_workspace, send

from app.errors import ValidationError
from app.main import create_app
from app.models import ModelCallResponse
from app.repositories.drafts import DraftRepository
from app.services.common import utc_now
from app.services.reader_selection_requests import ReaderSelectionRequest
from app.services.reader_selection_worker import ReaderSelectionWorker


def path(wid):
    return f"/api/workspaces/{wid}/reader-selections"


class FakeSelector:
    def __init__(self, gate=None, error=None, output=None):
        self.calls = []
        self.gate = gate
        self.error = error
        self.output = output

    async def select(self, inputs):
        self.calls.append(inputs.model_copy(deep=True))
        if self.gate is not None:
            await self.gate.wait()
        if self.error:
            raise self.error
        output = self.output if self.output is not None else {
            "proposedReaders": [proposal(inputs.candidates[0].id)] if inputs.candidates else [],
            "unmatchedReason": "无候选人物" if not inputs.candidates else "",
        }
        return ModelCallResponse(output=output, model_metadata={"model": "fake-selector-test"})


async def until(check):
    async with asyncio.timeout(3):
        while not check():
            await asyncio.sleep(0.005)


def test_default_does_not_offer_fake_recommendations(app):
    wid = create_workspace(app)["id"]
    result = send(app, "POST", path(wid), json={"requestKey": "click", "manualTopic": "标题"})
    assert result.status_code == 503
    assert app.state.reader_selection_service.pending() == []


def test_post_survives_observer_disconnect_and_replay_after_asset_edits(app, seeded):
    wid, _, _, fans = seeded
    selected = topic(app, wid, "原选题")
    payload = {"requestKey": "same-click", "topicId": selected["id"]}
    worker = app.state.reader_selection_worker
    service = app.state.reader_selection_service

    async def run():
        gate = asyncio.Event()
        provider = FakeSelector(gate)
        worker.provider = provider
        worker.poll_interval = 0.005
        assert worker.start()
        try:
            # Closing the HTTP client does not own or cancel the background model call.
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                response = await c.post(path(wid), json=payload)
                assert response.status_code == 202
                created = response.json()
            await until(lambda: len(provider.calls) == 1)
            assert service.get(wid, created["id"]).status == "running"
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                assert (await c.patch(f"/api/topics/{selected['id']}", json={
                    "title": "人物修改后选题", "expectedUpdatedAt": selected["updatedAt"],
                })).status_code == 200
                assert (await c.patch(f"/api/simulated-fans/{fans[0]['id']}", json={
                    **fans[0]["editable"], "name": "新的读者名称",
                    "expectedUpdatedAt": fans[0]["updatedAt"],
                })).status_code == 200
                responses = await asyncio.gather(*[
                    c.post(path(wid), json=payload) for _ in range(6)
                ])
                assert all(r.json()["id"] == created["id"] for r in responses)
                for _ in range(3):
                    observed = await c.get(f"{path(wid)}/{created['id']}")
                    assert observed.json()["status"] == "running"
                    assert observed.json()["inputSnapshot"] == created["inputSnapshot"]
                    assert "claimToken" not in observed.json()
                changed = await c.post(path(wid), json={**payload, "desiredCount": 4})
                assert changed.status_code == 409
            assert len(provider.calls) == 1
            competing = ReaderSelectionWorker(service, FakeSelector())
            assert not competing.start()
            await competing.shutdown()
            assert service.get(wid, created["id"]).status == "running"
            gate.set()
            await until(lambda: service.get(wid, created["id"]).status == "completed")
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                replay = await c.post(path(wid), json=payload)
                assert replay.json()["status"] == "completed"
                fresh = await c.post(path(wid), json={**payload, "requestKey": "new-click"})
                assert fresh.json()["inputHash"] != created["inputHash"]
                assert fresh.json()["inputSnapshot"]["target"]["title"] == "人物修改后选题"
            await until(lambda: service.get(wid, fresh.json()["id"]).status == "completed")
            assert len(provider.calls) == 2
        finally:
            await worker.shutdown()
    asyncio.run(run())


@pytest.mark.parametrize("fields", [
    {}, {"manualTopic": " "}, {"manualTopic": "题", "topicId": "id"},
    {"manualTopic": "题", "desiredCount": 0}, {"manualTopic": "题", "desiredCount": True},
    {"manualTopic": "题", "inputSnapshot": {"candidates": []}},
])
def test_invalid_request_cannot_supply_its_own_asset_pool(app, fields):
    wid = create_workspace(app)["id"]
    assert send(app, "POST", path(wid), json={"requestKey": "x", **fields}).status_code == 422
    assert app.state.reader_selection_service.pending() == []


def test_workspace_scope_and_concurrent_request_resolution(app, seeded):
    wid, _, _, _ = seeded
    other = create_workspace(app)["id"]
    selected = topic(app, wid)
    service = app.state.reader_selection_requests
    payload = ReaderSelectionRequest(request_key="click", topic_id=selected["id"])
    with ThreadPoolExecutor(max_workers=6) as pool:
        rows = list(pool.map(lambda _: service.create(wid, payload), range(12)))
    assert len({row.id for row in rows}) == 1
    assert send(app, "GET", f"{path(other)}/{rows[0].id}").status_code == 404
    assert send(app, "GET", f"{path(wid)}/{rows[0].id}").status_code == 200

    async def run():
        worker = app.state.reader_selection_worker
        worker.provider = FakeSelector()
        worker.start()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                response = await c.post(path(other), json=payload.model_dump(by_alias=True))
                assert response.status_code == 422
                unknown = await c.post(path("missing"), json={
                    "requestKey": "x", "manualTopic": "标题",
                })
                assert unknown.status_code == 404
        finally:
            await worker.shutdown()
    asyncio.run(run())


@pytest.mark.parametrize(("output", "error", "status", "code"), [
    ({"proposedReaders": [], "unmatchedReason": "没有相近需求"}, None, "completed", None),
    ({"proposedReaders": []}, None, "failed", "invalid_output"),
    (None, RuntimeError("secret must never appear"), "failed", "model_error"),
])
def test_worker_persists_outcomes_without_retries(app, output, error, status, code):
    wid = create_workspace(app)["id"]
    worker = app.state.reader_selection_worker
    provider = FakeSelector(error=error, output=output)
    worker.provider = provider
    worker.poll_interval = 0.005
    service = app.state.reader_selection_service

    async def run():
        worker.start()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                payload = {"requestKey": "click", "manualTopic": "试读标题", "desiredCount": 6}
                response = await c.post(path(wid), json=payload)
                rid = response.json()["id"]
                await until(lambda: service.get(wid, rid).completed_at is not None)
                for _ in range(3):
                    replay = await c.post(path(wid), json=payload)
                    assert replay.json()["status"] == status
                    assert replay.json()["errorCode"] == code
                    assert "secret" not in replay.text
                assert len(provider.calls) == 1
        finally:
            await worker.shutdown()
    asyncio.run(run())


def test_lifespan_restart_pending_recovery_and_exclusive_worker(app, settings):
    wid = create_workspace(app)["id"]
    requests = app.state.reader_selection_requests
    service = app.state.reader_selection_service
    pending = requests.create(
        wid, ReaderSelectionRequest(request_key="pending", manual_topic="标题"),
    )
    running = requests.create(
        wid, ReaderSelectionRequest(request_key="running", manual_topic="标题"),
    )
    abandoned = service.claim(wid, running.id)
    provider = FakeSelector()
    restarted = create_app(settings, reader_selection_provider=provider)

    async def run():
        async with restarted.router.lifespan_context(restarted):
            worker = restarted.state.reader_selection_worker
            assert worker.available
            assert service.get(wid, running.id).error_code == "interrupted"
            await until(lambda: service.get(wid, pending.id).status == "completed")
            assert len(provider.calls) == 1
            competing = ReaderSelectionWorker(service, FakeSelector())
            assert not competing.start()  # Cannot recover or claim the first process's work.
            await competing.shutdown()
            assert service.get(wid, pending.id).status == "completed"
        assert not restarted.state.reader_selection_worker.available
        # Repeated startup neither repeats completed work nor retries interrupted calls.
        async with restarted.router.lifespan_context(restarted):
            assert restarted.state.reader_selection_worker.available
            assert len(provider.calls) == 1
            assert service.get(wid, running.id).error_code == "interrupted"
    asyncio.run(run())
    assert abandoned is not None


def test_shutdown_interrupts_inflight_and_timeout_fails_once(app):
    wid = create_workspace(app)["id"]
    service = app.state.reader_selection_service
    requests = app.state.reader_selection_requests

    async def run():
        gate = asyncio.Event()
        provider = FakeSelector(gate)
        worker = ReaderSelectionWorker(service, provider, poll_interval=0.005)
        created = requests.create(
            wid, ReaderSelectionRequest(request_key="cancel", manual_topic="题"),
        )
        worker.start()
        await until(lambda: len(provider.calls) == 1)
        await worker.shutdown()
        assert service.get(wid, created.id).error_code == "interrupted"
        timed = requests.create(
            wid, ReaderSelectionRequest(request_key="timeout", manual_topic="题"),
        )
        worker = ReaderSelectionWorker(service, provider, poll_interval=0.005, call_timeout=0.01)
        worker.start()
        try:
            await until(lambda: service.get(wid, timed.id).status == "failed")
            assert service.get(wid, timed.id).error_code == "model_error"
            assert len(provider.calls) == 2
        finally:
            await worker.shutdown()
    asyncio.run(run())


def test_lost_post_response_replayed_without_another_execution(app):
    wid = create_workspace(app)["id"]
    worker = app.state.reader_selection_worker
    provider = FakeSelector()
    worker.provider = provider
    worker.poll_interval = 0.005
    payload = {"requestKey": "lost-response", "manualTopic": "标题"}

    async def disconnected(scope, receive, send_response):
        async def drop_response(message):
            if message["type"] == "http.response.start":
                raise asyncio.CancelledError("client disconnected after commit")
            await send_response(message)
        await app(scope, receive, drop_response)

    async def run():
        worker.start()
        try:
            async with AsyncClient(
                transport=ASGITransport(app=disconnected), base_url="http://test",
            ) as client:
                with pytest.raises(asyncio.CancelledError):
                    await client.post(path(wid), json=payload)
            existing = app.state.reader_selection_requests.existing(
                wid, ReaderSelectionRequest.model_validate(payload),
            )
            assert existing is not None
            await until(lambda: app.state.reader_selection_service.get(
                wid, existing.id,
            ).status == "completed")
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                response = await c.post(path(wid), json=payload)
                assert response.json()["id"] == existing.id
                assert response.json()["status"] == "completed"
            assert len(provider.calls) == 1
        finally:
            await worker.shutdown()
    asyncio.run(run())


def test_partial_selection_keeps_valid_reader_and_default_server_can_observe(app, seeded, settings):
    wid, _, _, fans = seeded
    worker = app.state.reader_selection_worker
    provider = FakeSelector(output={
        "proposedReaders": [proposal(fans[0]["id"]), proposal("missing")],
    })
    worker.provider = provider
    worker.poll_interval = 0.005
    payload = {"requestKey": "partial", "manualTopic": "标题"}

    async def run():
        worker.start()
        try:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                rid = (await c.post(path(wid), json=payload)).json()["id"]
                await until(lambda: app.state.reader_selection_service.get(
                    wid, rid,
                ).status == "partially_completed")
                result = (await c.get(f"{path(wid)}/{rid}")).json()
                assert result["result"]["proposedReaders"][0]["fanId"] == fans[0]["id"]
                assert result["result"]["validationWarnings"][0]["code"] == "unknown_reader"
                return result
        finally:
            await worker.shutdown()
    completed = asyncio.run(run())
    default_server = create_app(settings)  # No fake provider leaks into the default path.
    assert send(default_server, "GET", f"{path(wid)}/{completed['id']}").json() == completed
    assert completed["freshness"]["status"] == "current"
    assert send(default_server, "POST", path(wid), json=payload).json() == {
        key: value for key, value in completed.items() if key != "freshness"
    }
    assert len(provider.calls) == 1


def test_draft_target_uses_editable_visible_content_and_same_account(app, seeded):
    wid, _, _, _ = seeded
    selected = topic(app, wid)
    other = create_workspace(app)["id"]
    with app.state.database.transaction() as c:
        draft = DraftRepository().create(
            c, workspace_id=wid, topic_id=selected["id"], kind="content_structure",
            source_analysis_run_id=None, source_workflow="manual", status="completed",
            generated_snapshot_json='{"structure":{"outline":[]}}',
            editable_content_json='{"structure":{"outline":[{"sec":"开篇","ct":"新正文"}],'
                                  '"audience":"内部说服策略"}}',
            input_snapshot_json="{}", stage_errors_json="{}", model_metadata_json="{}",
            now=utc_now(), completed_at=utc_now(),
        )
    requests = app.state.reader_selection_requests
    payload = ReaderSelectionRequest(request_key="draft", draft_id=draft["id"])
    created = requests.create(wid, payload)
    target = created.input_snapshot.target
    assert target["targetType"] == "draft" and target["previewLevel"] == "outline"
    assert target["draft"]["editableContent"]["structure"]["outline"] == [
        {"sec": "开篇", "ct": "新正文"},
    ]
    assert "内部说服策略" not in str(target)
    with pytest.raises(ValidationError, match="草稿不属于当前账号"):
        requests.create(other, payload)


def test_default_application_bootstrap_is_also_isolated(pytestconfig):
    from pathlib import Path

    from app.main import app as default_application

    expected = Path(pytestconfig._bootstrap_runtime.name) / "bootstrap.sqlite3"
    assert default_application.state.database.path == expected
    assert expected.is_file()
