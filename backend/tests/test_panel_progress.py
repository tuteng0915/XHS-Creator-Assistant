"""A polling client must see each finished reader before the whole stage finishes."""

import asyncio
import json
from collections import Counter
from unittest.mock import AsyncMock

import pytest
from test_workspace_api import create_workspace, send

from app.models import SimulationRunCreate, SimulationRunStatus
from app.workflows.audience_simulation import FakeAudienceSimulationModelProvider


class StaggeredReaders(FakeAudienceSimulationModelProvider):
    def __init__(self, failure_stage=None):
        super().__init__({f"{failure_stage}:failed"} if failure_stage else None)
        self.failure_stage = failure_stage
        self.release_reaction = asyncio.Event()
        self.release_debate = asyncio.Event()
        self.slow_reaction_started = asyncio.Event()
        self.slow_debate_started = asyncio.Event()

    async def personas(self, *, positioning, topic):
        self.calls.append("personas")
        # The first reader finishes last, so completion order differs from roster order.
        personas = [
            {"id": "slow", "name": "慢读者", "profile": "先想一会儿再回应"},
            {"id": "fast", "name": "快读者", "profile": "看到文字就能表达感受"},
        ]
        if self.failure_stage:
            personas.append({"id": "failed", "name": "失败读者", "profile": "本轮无法完成"})
        return {"personas": personas}

    async def initial_reaction(self, *, persona, topic):
        if persona["id"] == "slow":
            self.slow_reaction_started.set()
            await self.release_reaction.wait()
        return await super().initial_reaction(persona=persona, topic=topic)

    async def debate_response(self, *, persona, topic, other_reactions, prior_reaction=None):
        if persona["id"] == "slow":
            self.slow_debate_started.set()
            await self.release_debate.wait()
        return await super().debate_response(
            persona=persona, topic=topic, other_reactions=other_reactions,
            prior_reaction=prior_reaction,
        )


def test_sse_delivers_each_cumulative_result_before_parallel_stage_finishes(app, monkeypatch):
    wid = create_workspace(app)["id"]
    service = app.state.simulation_service
    run = service.create(wid, SimulationRunCreate(manual_topic="分段展示", mode="demo"))
    asyncio.run(app.state.simulation_workflow_service.collect_events(run.id))
    final = service.get(run.id)
    assert len(final.reaction_results) >= 3
    snapshots = iter([
        final.model_copy(update={"status": SimulationRunStatus.RUNNING,
                                 "reaction_results": final.reaction_results[:1],
                                 "debate_results": [], "synthesis": {}}),
        final.model_copy(update={"status": SimulationRunStatus.RUNNING,
                                 "reaction_results": final.reaction_results[:2],
                                 "debate_results": [], "synthesis": {}}),
        final,
    ])
    monkeypatch.setattr(service, "get", lambda _: next(snapshots))
    response = send(app, "GET", f"/api/simulation-runs/{run.id}/events")
    events = [json.loads(line.removeprefix("data: "))
              for line in response.text.splitlines() if line.startswith("data: ")]
    reactions = [e for e in events if e.get("stageKey") == "initial_reactions"
                 and e["data"]["eventType"] in {"stage.progress", "stage.succeeded"}]
    assert [len(e["data"]["reactions"]) for e in reactions] == [1, 2, 3]
    assert [e["data"]["eventType"] for e in reactions] == [
        "stage.progress", "stage.progress", "stage.succeeded",
    ]
    assert [e["status"] for e in reactions] == ["running", "running", "completed"]


def test_each_reaction_and_reply_is_durable_while_slower_reader_is_still_waiting(app):
    wid = create_workspace(app)["id"]
    simulations = app.state.simulation_service
    workflow = app.state.simulation_workflow_service
    run = simulations.create(wid, SimulationRunCreate(
        manual_topic="一个简单的观察练习", mode="demo",
    ))
    live = AsyncMock()
    workflow.live_provider = live

    def persisted():
        # Fresh repository reads prove this is saved progress, not an in-memory event.
        with app.state.database.read() as connection:
            return simulations.repository.get(connection, run.id)

    async def until_one_saved(field):
        async with asyncio.timeout(3):
            while len(json.loads(persisted()[field])) != 1:
                await asyncio.sleep(0.003)

    async def exercise():
        provider = StaggeredReaders()
        workflow.fake_provider = provider
        task = asyncio.create_task(workflow.collect_events(run.id))
        try:
            async with asyncio.timeout(3):
                await provider.slow_reaction_started.wait()
            await until_one_saved("reaction_results_json")
            partial = persisted()
            reactions = json.loads(partial["reaction_results_json"])
            assert partial["status"] == "running"
            assert reactions[0]["personaId"] == "fast"
            assert reactions[0]["messageId"] == "initial:fast"
            assert reactions[0]["quote"]
            assert json.loads(partial["debate_results_json"]) == []
            assert not provider.release_reaction.is_set()
            assert not task.done()

            provider.release_reaction.set()
            async with asyncio.timeout(3):
                await provider.slow_debate_started.wait()
            await until_one_saved("debate_results_json")
            partial = persisted()
            assert partial["status"] == "running"
            assert {item["personaId"] for item in json.loads(partial["reaction_results_json"])} == {
                "slow", "fast",
            }
            reply = json.loads(partial["debate_results_json"])[0]
            assert reply["personaId"] == "fast"
            assert reply["messageId"] == "reply:fast"
            assert reply["replyToId"] == "initial:slow"
            assert not provider.release_debate.is_set()
            assert not task.done()

            provider.release_debate.set()
            async with asyncio.timeout(3):
                events = await task
            final = simulations.get(run.id)
            assert final.status == "completed", final.stage_errors
            assert [p["id"] for p in final.persona_definitions] == ["slow", "fast"]
            assert [r["personaId"] for r in final.reaction_results] == ["slow", "fast"]
            assert [r["personaId"] for r in final.debate_results] == ["slow", "fast"]
            assert final.stage_errors == {}
            assert events[-1]["data"]["eventType"] == "run.succeeded"
            assert Counter(provider.calls) == Counter({
                "personas": 1, "reaction:slow": 1, "reaction:fast": 1,
                "debate:slow": 1, "debate:fast": 1, "synthesis": 1,
            })
            assert live.mock_calls == []
        finally:
            provider.release_reaction.set()
            provider.release_debate.set()
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(exercise())


@pytest.mark.parametrize("paused_stage", ["reaction", "debate"])
@pytest.mark.parametrize("settled_failure", [False, True])
def test_restart_only_resumes_missing_readers_and_never_repeats_settled_results(
    app, settings, pytestconfig, paused_stage, settled_failure,
):
    wid = create_workspace(app)["id"]
    service = app.state.simulation_service
    run = service.create(wid, SimulationRunCreate(
        manual_topic="读者逐个返回的恢复测试", mode="demo",
    ))
    stage_field = "reaction_results_json" if paused_stage == "reaction" else "debate_results_json"
    error_key = ("initial_reactions.failed" if paused_stage == "reaction"
                 else "debate_responses.failed")

    def persisted():
        with app.state.database.read() as connection:
            return service.repository.get(connection, run.id)

    async def interrupt_mid_stage():
        provider = StaggeredReaders(paused_stage if settled_failure else None)
        workflow = app.state.simulation_workflow_service
        workflow.fake_provider = provider
        workflow.live_provider = AsyncMock()
        if paused_stage == "debate":
            provider.release_reaction.set()
        task = asyncio.create_task(workflow.collect_events(run.id))
        try:
            async with asyncio.timeout(3):
                while True:
                    row = persisted()
                    replies = json.loads(row[stage_field])
                    errors = json.loads(row["stage_errors_json"])
                    if (len(replies) == 1 and replies[0]["personaId"] == "fast"
                            and (not settled_failure or error_key in errors)):
                        break
                    await asyncio.sleep(0.003)
            assert row["status"] == "running"
            assert not task.done()
            assert not (provider.release_reaction if paused_stage == "reaction"
                        else provider.release_debate).is_set()
            return replies[0], errors
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    # Exiting this event loop cancels all outstanding in-flight calls as a process exit would.
    first_reply, saved_errors = asyncio.run(interrupt_mid_stage())
    assert persisted()["status"] == "running"
    restarted = pytestconfig._create_test_app(settings)
    resumed_provider = FakeAudienceSimulationModelProvider()
    restarted.state.simulation_workflow_service.fake_provider = resumed_provider
    live = AsyncMock()
    restarted.state.simulation_workflow_service.live_provider = live

    async def resume():
        worker = restarted.state.workflow_worker
        try:
            assert await worker.resume_unfinished() == 1
            await worker.wait_for_idle()
            finished_calls = list(resumed_provider.calls)
            await restarted.state.simulation_workflow_service.collect_events(run.id)
            assert resumed_provider.calls == finished_calls
        finally:
            await worker.shutdown()

    asyncio.run(resume())
    final = restarted.state.simulation_service.get(run.id)
    assert final.status == ("partially_completed" if settled_failure else "completed")
    assert final.stage_errors == saved_errors
    reactions = {item["personaId"]: item for item in final.reaction_results}
    replies = {item["personaId"]: item for item in final.debate_results}
    assert (reactions if paused_stage == "reaction" else replies)["fast"] == first_reply
    assert {"slow", "fast"} <= reactions.keys()
    assert {"slow", "fast"} == replies.keys()
    assert len(final.persona_definitions) == (3 if settled_failure else 2)
    assert len(reactions) == (3 if settled_failure and paused_stage == "debate" else 2)
    expected = Counter({"debate:slow": 1, "synthesis": 1})
    if paused_stage == "reaction":
        expected.update({"reaction:slow": 1, "debate:fast": 1})
    assert Counter(resumed_provider.calls) == expected
    assert live.mock_calls == []
