"""One explicit recovery never regenerates a successful sibling or old history."""

import asyncio
import json
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

import pytest
from test_workspace_api import create_workspace, request

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import SimulationRunCreate
from app.services.panel_recovery import PanelRecoveryCreate, create_recovery
from app.workflows.audience_simulation import FakeAudienceSimulationModelProvider


class Readers(FakeAudienceSimulationModelProvider):
    async def personas(self, **kwargs):
        self.calls.append("personas")
        if "personas" in self.failures:
            raise RuntimeError("读者准备失败")
        return {"personas": [{"id": p, "name": f"读者{p}", "profile": "认真读原文"}
                             for p in ["a", "b"]]}


def source_run(app, failures):
    wid = create_workspace(app)["id"]
    provider = Readers(failures)
    workflow = app.state.simulation_workflow_service
    workflow.fake_provider = provider
    run = app.state.simulation_service.create(wid, SimulationRunCreate(manual_topic="先写一句话"))
    asyncio.run(workflow.collect_events(run.id))
    return app.state.simulation_service.get(run.id), provider


def recover(app, source, stage, key="one"):
    return create_recovery(app.state.simulation_service, source.workspace_id, source.id,
                           PanelRecoveryCreate(request_key=key, stage_key=stage))


@pytest.mark.parametrize("stage,fail,expected", [
    ("initial_reactions.b", "reaction:b", "reaction:b"),
    ("debate_responses.b", "debate:b", "debate:b"),
    ("synthesis", "synthesis", "synthesis"),
])
def test_recovery_calls_only_selected_unit_and_keeps_parent_exact(app, stage, fail, expected):
    source, provider = source_run(app, {fail})
    before = source.model_dump(mode="json")
    child = recover(app, source, stage)
    assert child.input_snapshot == source.input_snapshot
    assert child.persona_definitions == source.persona_definitions
    assert child.reaction_results == source.reaction_results
    assert child.debate_results == source.debate_results
    assert child.synthesis == source.synthesis
    provider.failures.clear()
    provider.calls.clear()
    asyncio.run(app.state.simulation_workflow_service.collect_events(child.id))
    result = app.state.simulation_service.get(child.id)
    assert provider.calls == [expected]
    assert stage not in result.stage_errors
    assert result.status == "completed"
    if stage != "synthesis":
        assert result.model_metadata["recovery"]["summaryStale"] is True
        assert result.synthesis == source.synthesis
    else:
        assert result.model_metadata["recovery"]["summaryStale"] is False
    assert app.state.simulation_service.get(source.id).model_dump(mode="json") == before
    assert recover(app, source, stage).id == child.id
    asyncio.run(app.state.simulation_workflow_service.collect_events(child.id))
    assert provider.calls == [expected]


def test_explicit_summary_refresh_is_separate_and_preserves_recovered_comments(app):
    source, provider = source_run(app, {"reaction:b"})
    child = recover(app, source, "initial_reactions.b")
    provider.failures.clear()
    asyncio.run(app.state.simulation_workflow_service.collect_events(child.id))
    child = app.state.simulation_service.get(child.id)
    before = child.model_dump(mode="json")
    refresh = recover(app, child, "synthesis", "refresh")
    provider.calls.clear()
    asyncio.run(app.state.simulation_workflow_service.collect_events(refresh.id))
    final = app.state.simulation_service.get(refresh.id)
    assert provider.calls == ["synthesis"]
    assert final.reaction_results == child.reaction_results
    assert final.debate_results == child.debate_results
    assert final.model_metadata["recovery"]["summaryStale"] is False
    assert app.state.simulation_service.get(child.id).model_dump(mode="json") == before


def test_failed_recovery_stays_retryable_without_losing_good_results(app):
    source, provider = source_run(app, {"reaction:b"})
    child = recover(app, source, "initial_reactions.b")
    provider.calls.clear()
    asyncio.run(app.state.simulation_workflow_service.collect_events(child.id))
    result = app.state.simulation_service.get(child.id)
    assert provider.calls == ["reaction:b"]
    assert result.status == "partially_completed"
    assert result.reaction_results == source.reaction_results
    assert result.synthesis == source.synthesis
    assert result.model_metadata["recovery"]["summaryStale"] is False
    again = recover(app, result, "initial_reactions.b", "second")
    provider.failures.clear()
    provider.calls.clear()
    asyncio.run(app.state.simulation_workflow_service.collect_events(again.id))
    assert provider.calls == ["reaction:b"]


def test_recovery_idempotency_conflict_running_and_workspace_guards(app):
    source, _ = source_run(app, {"reaction:b", "debate:a"})
    child = recover(app, source, "initial_reactions.b")
    assert recover(app, source, "initial_reactions.b").id == child.id
    with pytest.raises(ConflictError):
        recover(app, source, "synthesis")
    assert recover(app, source, "initial_reactions.b", "another-click").id == child.id
    with pytest.raises(ConflictError):
        recover(app, child, "synthesis", "active")
    with pytest.raises(NotFoundError):
        create_recovery(app.state.simulation_service, create_workspace(app)["id"], source.id,
                        PanelRecoveryCreate(request_key="wrong", stage_key="initial_reactions.b"))


@pytest.mark.parametrize("key", ["initial_reactions.a", "initial_reactions.unknown", "other"])
def test_successful_or_unknown_units_cannot_be_regenerated(app, key):
    source, _ = source_run(app, {"reaction:b"})
    with pytest.raises(ValidationError):
        recover(app, source, key)


def test_concurrent_duplicate_clicks_create_only_one_record(app):
    source, _ = source_run(app, {"reaction:b"})
    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(lambda _: recover(app, source, "initial_reactions.b").id, range(2)))
    assert len(set(ids)) == 1
    assert len(app.state.simulation_service.list(source.workspace_id)) == 2


def test_reload_with_a_new_receipt_reopens_the_same_attempt_even_after_completion(app):
    source, provider = source_run(app, {"reaction:b"})
    child = recover(app, source, "initial_reactions.b")
    provider.failures.clear()
    provider.calls.clear()
    asyncio.run(app.state.simulation_workflow_service.collect_events(child.id))
    assert recover(app, source, "initial_reactions.b", "after-reload").id == child.id
    asyncio.run(app.state.simulation_workflow_service.collect_events(child.id))
    assert provider.calls == ["reaction:b"]
    with pytest.raises(ConflictError):
        recover(app, source, "synthesis", "after-reload")


def test_timeout_returns_partial_once_and_cancels_the_hanging_sibling(app):
    source, _ = source_run(app, {"reaction:b"})
    child = recover(app, source, "initial_reactions.b")

    class Hanging(Readers):
        cancelled = False

        async def initial_reaction(self, **kwargs):
            self.calls.append("reaction:b")
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True

    provider = Hanging()
    workflow = app.state.simulation_workflow_service
    workflow.fake_provider = provider
    workflow.step_timeout_seconds = 0.02
    asyncio.run(workflow.collect_events(child.id))
    result = app.state.simulation_service.get(child.id)
    assert provider.calls == ["reaction:b"] and provider.cancelled
    assert "等待超时" in result.stage_errors["initial_reactions.b"]
    assert result.reaction_results == source.reaction_results


def test_api_recovery_enqueues_only_one_unit_and_gets_are_read_only(app):
    source, provider = source_run(app, {"debate:b"})
    provider.failures.clear()
    provider.calls.clear()

    async def exercise():
        url = f"/api/workspaces/{source.workspace_id}/simulation-runs/{source.id}/recoveries"
        payload = {"requestKey": "api-click", "stageKey": "debate_responses.b"}
        first = await request(app, "POST", url, json=payload)
        assert first.status_code == 202, first.text
        await app.state.workflow_worker.wait_for_idle()
        second = await request(app, "POST", url, json=payload)
        assert second.status_code == 202 and second.json()["id"] == first.json()["id"]
        await app.state.workflow_worker.wait_for_idle()
        result = await request(app, "GET", f"/api/simulation-runs/{first.json()['id']}")
        assert result.json()["status"] == "completed"
        assert Counter(provider.calls) == {"debate:b": 1}

    asyncio.run(exercise())


def test_recovery_preserves_saved_author_notes_and_review_state(app):
    source, _ = source_run(app, {"reaction:b"})
    with app.state.database.transaction() as connection:
        connection.execute(
            "UPDATE simulation_runs SET user_notes=?, review_status=? WHERE id=?",
            ("保留我的手动判断，不要覆盖", "useful", source.id),
        )
    source = app.state.simulation_service.get(source.id)
    child = recover(app, source, "initial_reactions.b")
    assert child.user_notes == source.user_notes
    assert child.review_status == source.review_status


def test_failed_summary_refresh_keeps_previous_summary_and_stale_marker(app):
    source, provider = source_run(app, {"reaction:b"})
    child = recover(app, source, "initial_reactions.b")
    provider.failures.clear()
    asyncio.run(app.state.simulation_workflow_service.collect_events(child.id))
    child = app.state.simulation_service.get(child.id)
    refresh = recover(app, child, "synthesis", "summary")
    provider.failures.add("synthesis")
    provider.calls.clear()
    asyncio.run(app.state.simulation_workflow_service.collect_events(refresh.id))
    final = app.state.simulation_service.get(refresh.id)
    assert provider.calls == ["synthesis"]
    assert final.synthesis == source.synthesis
    assert final.model_metadata["recovery"]["summaryStale"] is True
    assert "synthesis" in final.stage_errors
    assert recover(app, final, "synthesis", "try-summary-again").id != final.id


def test_recovery_resumes_after_worker_restart_without_repeating_successful_readers(
    app, settings, pytestconfig,
):
    source, _ = source_run(app, {"reaction:b"})
    child = recover(app, source, "initial_reactions.b")
    provider = Readers()
    restarted = pytestconfig._create_test_app(settings)
    restarted.state.simulation_workflow_service.fake_provider = provider

    async def resume():
        worker = restarted.state.workflow_worker
        try:
            assert await worker.resume_unfinished() == 1
            await worker.wait_for_idle()
            assert await worker.resume_unfinished() == 0
        finally:
            await worker.shutdown()

    asyncio.run(resume())
    final = restarted.state.simulation_service.get(child.id)
    assert provider.calls == ["reaction:b"]
    assert final.status == "completed"
    assert next(r for r in final.reaction_results if r["personaId"] == "a") == (
        source.reaction_results[0]
    )


def test_persona_recovery_continues_only_when_no_reader_has_been_created(app):
    source, provider = source_run(app, {"personas"})
    child = recover(app, source, "personas")
    provider.failures.clear()
    provider.calls.clear()
    asyncio.run(app.state.simulation_workflow_service.collect_events(child.id))
    assert provider.calls[0] == "personas"
    assert app.state.simulation_service.get(child.id).status == "completed"


@pytest.mark.parametrize("scenario", ["oracle", "existing-personas", "missing-reaction"])
def test_ineligible_recovery_never_creates_a_fake_success(app, scenario):
    source, _ = source_run(app, {"reaction:b"})
    key = "initial_reactions.b"
    changes = {}
    if scenario == "oracle":
        changes["input_snapshot_json"] = json.dumps({**source.input_snapshot,
                                                     "origin": "oracle_showcase"})
    elif scenario == "existing-personas":
        key = "personas"
        changes["stage_errors_json"] = json.dumps({key: "旧名单不能被替换"})
    else:
        key = "debate_responses.b"
        changes["stage_errors_json"] = json.dumps({key: "缺少前序试读"})
    with app.state.database.transaction() as connection:
        for column, value in changes.items():
            connection.execute(f"UPDATE simulation_runs SET {column}=? WHERE id=?",
                               (value, source.id))
    source = app.state.simulation_service.get(source.id)
    with pytest.raises(ValidationError):
        recover(app, source, key)
    assert len(app.state.simulation_service.list(source.workspace_id)) == 1
