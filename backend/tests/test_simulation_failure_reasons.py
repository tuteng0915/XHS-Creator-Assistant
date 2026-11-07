"""Failed reader units end with their real reason and keep delivered replies."""

import asyncio

from test_panel_recovery import Readers
from test_workspace_api import create_workspace

from app.errors import ModelTransportError, ValidationError
from app.models import SimulationRunCreate
from app.workflows.audience_simulation import (
    SIMULATION_STEP_TIMEOUT_SECONDS,
    SIMULATION_SYNTHESIS_TIMEOUT_SECONDS,
)


def run_panel(app, provider, *, step=None, synthesis=None):
    workflow = app.state.simulation_workflow_service
    workflow.fake_provider = provider
    if step is not None:
        workflow.step_timeout_seconds = step
    if synthesis is not None:
        workflow.synthesis_timeout_seconds = synthesis
    wid = create_workspace(app)["id"]
    run = app.state.simulation_service.create(wid, SimulationRunCreate(manual_topic="先写一句话"))
    asyncio.run(workflow.collect_events(run.id))
    return app.state.simulation_service.get(run.id)


def records(run, key):
    entries = run.model_metadata.get("stepRecords", [])
    return [entry for entry in entries if entry["stageKey"] == key]


def test_summary_gets_a_longer_limit_than_reader_steps():
    assert SIMULATION_STEP_TIMEOUT_SECONDS == 30
    assert SIMULATION_SYNTHESIS_TIMEOUT_SECONDS == 90


def test_no_reply_is_reported_as_no_reply_and_other_reader_is_kept(app):
    class NoReply(Readers):
        async def initial_reaction(self, *, persona, topic):
            if persona["id"] == "b":
                self.calls.append("reaction:b")
                raise ModelTransportError("RemoteProtocolError", provider="deepseek")
            return await super().initial_reaction(persona=persona, topic=topic)

    run = run_panel(app, NoReply())
    message = run.stage_errors["initial_reactions.b"]
    assert message == "没有收到模型回复（模型服务中断了连接），已保留其他结果，可单独重试。"
    assert [r["personaId"] for r in run.reaction_results] == ["a"]
    [failed] = records(run, "initial_reactions.b")
    assert failed["status"] == "failed" and failed["failure"] == "no_response"
    assert failed["detail"] == "RemoteProtocolError" and failed["seconds"] >= 0
    [done] = records(run, "initial_reactions.a")
    assert done["status"] == "completed" and "failure" not in done


def test_slow_summary_uses_its_own_limit_while_reader_steps_stay_short(app):
    class Slow(Readers):
        async def initial_reaction(self, *, persona, topic):
            if persona["id"] == "b":
                self.calls.append("reaction:b")
                await asyncio.sleep(0.3)
            return await super().initial_reaction(persona=persona, topic=topic)

        async def synthesis(self, **kwargs):
            await asyncio.sleep(0.15)
            return await super().synthesis(**kwargs)

    run = run_panel(app, Slow(), step=0.05, synthesis=1.0)
    assert run.stage_errors["initial_reactions.b"] == (
        "本环节等待超时（超过0.05秒未收到回复），已保留其他结果，可单独重试。")
    assert "synthesis" not in run.stage_errors and run.synthesis
    [timed_out] = records(run, "initial_reactions.b")
    assert timed_out["failure"] == "timeout" and timed_out["seconds"] < 0.3
    [summary] = records(run, "synthesis")
    assert summary["status"] == "completed" and summary["seconds"] >= 0.15


def test_bad_output_and_http_errors_get_readable_reasons(app):
    class Broken(Readers):
        async def initial_reaction(self, *, persona, topic):
            self.calls.append(f"reaction:{persona['id']}")
            if persona["id"] == "a":
                raise ValidationError("Model response was not valid JSON")
            raise ValidationError("Model call failed (503)")

    run = run_panel(app, Broken())
    kept = "，已保留其他结果，可单独重试。"
    assert run.stage_errors["initial_reactions.a"] == "模型回复格式不符合要求" + kept
    assert run.stage_errors["initial_reactions.b"] == "模型服务返回错误（HTTP 503）" + kept
    assert records(run, "initial_reactions.a")[0]["failure"] == "invalid_output"
    assert records(run, "initial_reactions.b")[0] | {"seconds": 0} == {
        "stageKey": "initial_reactions.b", "status": "failed", "seconds": 0,
        "failure": "http_error", "detail": "503"}


def test_output_check_failure_after_a_returned_call_is_recorded(app):
    class WrongReader(Readers):
        async def initial_reaction(self, *, persona, topic):
            result = await super().initial_reaction(persona=persona, topic=topic)
            if persona["id"] == "b":
                result["reaction"]["personaId"] = "someone-else"
            return result

    run = run_panel(app, WrongReader())
    assert run.stage_errors["initial_reactions.b"] == "反应角色与请求不一致"
    [entry] = records(run, "initial_reactions.b")
    assert entry["status"] == "failed" and entry["failure"] == "failed"
    assert entry["detail"] == "ValueError" and entry["seconds"] is not None
