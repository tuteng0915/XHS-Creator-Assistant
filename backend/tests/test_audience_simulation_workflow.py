import asyncio
import json

import pytest
from fastapi import FastAPI
from test_workspace_api import create_workspace, send

from app.models import ModelCallResponse, ModelOperation
from app.workflows.audience_simulation import (
    AUDIENCE_SIMULATION_NODE_ORDER,
    MAX_CONCURRENT_PERSONA_CALLS,
    FakeAudienceSimulationModelProvider,
    RealAudienceSimulationModelProvider,
)


def create_topic(app: FastAPI, workspace_id: str) -> dict:
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace_id}/topics",
        json={
            "title": "非技术背景如何开始数字游民",
            "angle": "拆成六条可验证路径",
            "associatedPainPoint": "不知道靠什么远程赚钱",
            "whyItFits": "符合真实记录和可操作指南定位",
            "sourceWorkflow": "manual",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_simulation_run(app: FastAPI, *, saved_topic: bool = True) -> dict:
    workspace = create_workspace(app)
    payload: dict
    if saved_topic:
        topic = create_topic(app, workspace["id"])
        payload = {"topicId": topic["id"], "mode": "demo"}
    else:
        payload = {"manualTopic": "手动输入的受众模拟选题", "mode": "demo"}
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/simulation-runs",
        json=payload,
    )
    assert response.status_code == 201
    return response.json()


def collect(
    app: FastAPI, simulation_id: str, stop_after_node: str | None = None
) -> list[dict]:
    return asyncio.run(
        app.state.simulation_workflow_service.collect_events(
            simulation_id, stop_after_node=stop_after_node
        )
    )


def test_simulation_graph_from_saved_topic_persists_full_result(app: FastAPI) -> None:
    run = create_simulation_run(app)

    assert AUDIENCE_SIMULATION_NODE_ORDER == [
        "derive_personas",
        "parallel_initial_reactions",
        "parallel_debate_responses",
        "synthesis",
        "finalize",
    ]

    events = collect(app, run["id"])

    assert events[-1]["data"]["eventType"] == "run.succeeded"
    completed = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert completed["personaDefinitions"][0]["archetype"] == "想转型的传统职场人"
    assert len(completed["reactionResults"]) == 3
    assert len(completed["debateResults"]) == 3
    assert completed["synthesis"]["verdict"]
    assert completed["synthesis"]["topResonance"]["persona"] == "想转型的传统职场人"


def test_simulation_can_start_from_manual_topic(app: FastAPI) -> None:
    run = create_simulation_run(app, saved_topic=False)

    assert run["topicId"] is None
    assert run["inputSnapshot"]["topic"]["title"] == "手动输入的受众模拟选题"

    collect(app, run["id"])
    completed = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert completed["status"] == "completed"


def test_failed_persona_reaction_is_preserved_as_partial(app: FastAPI) -> None:
    run = create_simulation_run(app)
    app.state.simulation_workflow_service.fake_provider = (
        FakeAudienceSimulationModelProvider(failures={"reaction:nomad"})
    )

    events = collect(app, run["id"])

    assert events[-1]["data"]["eventType"] == "run.partial"
    partial = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert partial["status"] == "partially_completed"
    assert len(partial["reactionResults"]) == 2
    assert "initial_reactions.nomad" in partial["stageErrors"]
    assert partial["synthesis"]["verdict"]


def test_persona_calls_use_bounded_retry(app: FastAPI) -> None:
    class FlakyProvider(FakeAudienceSimulationModelProvider):
        def __init__(self) -> None:
            super().__init__()
            self.reaction_attempts = 0

        async def initial_reaction(self, **kwargs):
            persona = kwargs["persona"]
            if persona["id"] == "wannabe" and self.reaction_attempts == 0:
                self.reaction_attempts += 1
                raise RuntimeError("transient failure")
            return await super().initial_reaction(**kwargs)

    run = create_simulation_run(app)
    provider = FlakyProvider()
    app.state.simulation_workflow_service.fake_provider = provider

    collect(app, run["id"])

    completed = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert len(completed["reactionResults"]) == 3
    assert provider.reaction_attempts == 1


def test_simulation_history_and_reopen(app: FastAPI) -> None:
    run = create_simulation_run(app)
    workspace_id = run["workspaceId"]
    collect(app, run["id"])

    history = send(
        app, "GET", f"/api/workspaces/{workspace_id}/simulation-runs"
    ).json()
    assert history[0]["id"] == run["id"]
    assert history[0]["status"] == "completed"

    reopened = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert reopened["id"] == run["id"]
    assert reopened["synthesis"]["strongestAngle"]


def test_live_evidence_survives_and_silence_skips_discussion_after_restart(app):
    run = create_simulation_run(app)
    snapshot = run["inputSnapshot"]
    snapshot.update(mode="live", audiencePersonas=[{
        "id": "reader", "name": "费用视角", "profile": "关心费用",
        "evidenceStatus": "verified", "limitations": "小样本",
        "evidenceRefs": [{"noteId": "n", "commentId": "c", "sourceType": "comment",
                          "quote": "多少钱"}],
    }])
    with app.state.simulation_service.database.transaction() as c:
        c.execute("UPDATE simulation_runs SET input_snapshot_json=? WHERE id=?",
                  (json.dumps(snapshot, ensure_ascii=False), run["id"]))

    class Model:
        calls = []

        async def call_operation(self, operation, context):
            self.calls.append(operation)
            assert "whyItFits" not in context["topic"]
            assert "associatedPainPoint" not in context["topic"]
            if operation == ModelOperation.SIMULATION_REACTION:
                assert context["persona"]["evidenceRefs"][0]["commentId"] == "c"
                output = {"reaction": {"personaId": "reader", "stance": "无感",
                                       "action": "no_comment", "quote": "不应成为评论"}}
            else:
                assert operation == ModelOperation.SIMULATION_SYNTHESIS
                assert context["personas"][0]["limitations"] == "小样本"
                assert context["reactions"][0]["quote"] == ""
                assert context["debateResponses"] == []
                output = {"synthesis": {"verdict": "先补充内容", "limitations": "仅概念预演"}}
            return ModelCallResponse(output=output, model_metadata={"model": "injected"})

    model = Model()
    app.state.simulation_workflow_service.live_provider = RealAudienceSimulationModelProvider(model)
    collect(app, run["id"], stop_after_node="parallel_initial_reactions")
    assert model.calls == [ModelOperation.SIMULATION_REACTION]
    events = collect(app, run["id"])
    assert any(e["data"].get("skippedReason") for e in events)
    completed = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert completed["personaDefinitions"][0]["evidenceRefs"][0]["noteId"] == "n"
    assert completed["debateResults"] == []
    assert model.calls == [ModelOperation.SIMULATION_REACTION, ModelOperation.SIMULATION_SYNTHESIS]
    replay = send(app, "GET", f"/api/simulation-runs/{run['id']}/events")
    assert "没有可供其他读者回应的公开评论" in replay.text


def test_many_saved_personas_run_without_unbounded_provider_burst(app):
    run = create_simulation_run(app)
    snapshot = run["inputSnapshot"]
    snapshot.update(mode="live", audiencePersonas=[
        {"id": f"reader-{index}", "name": f"人物 {index}", "profile": "不同阅读方式"}
        for index in range(8)
    ])
    with app.state.simulation_service.database.transaction() as c:
        c.execute("UPDATE simulation_runs SET input_snapshot_json=? WHERE id=?",
                  (json.dumps(snapshot, ensure_ascii=False), run["id"]))

    class Model:
        active = 0
        peak = 0

        async def call_operation(self, operation, context):
            if operation == ModelOperation.SIMULATION_REACTION:
                self.active += 1
                self.peak = max(self.peak, self.active)
                await asyncio.sleep(0.01)
                self.active -= 1
                output = {"reaction": {"personaId": context["persona"]["id"],
                                       "stance": "无感", "action": "no_comment"}}
            else:
                assert operation == ModelOperation.SIMULATION_SYNTHESIS
                output = {"synthesis": {"verdict": "仅模拟参考"}}
            return ModelCallResponse(output=output, model_metadata={})

    model = Model()
    app.state.simulation_workflow_service.live_provider = RealAudienceSimulationModelProvider(model)
    collect(app, run["id"])
    completed = app.state.simulation_service.get(run["id"])
    assert completed.status.value == "completed", completed.stage_errors
    assert len(completed.reaction_results) == 8
    assert model.peak == MAX_CONCURRENT_PERSONA_CALLS


def test_debate_only_receives_public_comments_not_private_reasoning(app):
    class Provider(FakeAudienceSimulationModelProvider):
        async def initial_reaction(self, **kwargs):
            result = await super().initial_reaction(**kwargs)
            result["reaction"]["understanding"] = "私人推理"
            return result

        async def debate_response(self, **kwargs):
            assert all(set(r) == {"messageId", "personaId", "quote", "round"}
                       for r in kwargs["other_reactions"])
            assert all(r["personaId"] != kwargs["persona"]["id"] for r in kwargs["other_reactions"])
            assert kwargs["prior_reaction"]["personaId"] == kwargs["persona"]["id"]
            assert kwargs["prior_reaction"]["understanding"] == "私人推理"
            return await super().debate_response(**kwargs)

    run = create_simulation_run(app)
    app.state.simulation_workflow_service.fake_provider = Provider()
    collect(app, run["id"])
    assert send(app, "GET", f"/api/simulation-runs/{run['id']}").json()["status"] == "completed"


def test_silent_readers_join_one_public_comment_after_restart(app):
    class Provider(FakeAudienceSimulationModelProvider):
        async def initial_reaction(self, **kwargs):
            result = await super().initial_reaction(**kwargs)
            if kwargs["persona"]["id"] != "wannabe":
                result["reaction"].update(action="no_comment", quote="不公开")
            return result

        async def debate_response(self, **kwargs):
            assert kwargs["prior_reaction"]["action"] == "no_comment"
            assert kwargs["prior_reaction"]["quote"] == ""
            assert [r["messageId"] for r in kwargs["other_reactions"]] == ["initial:wannabe"]
            return await super().debate_response(**kwargs)

    run = create_simulation_run(app)
    provider = Provider()
    app.state.simulation_workflow_service.fake_provider = provider
    collect(app, run["id"], stop_after_node="parallel_initial_reactions")
    initial_calls = list(provider.calls)
    collect(app, run["id"])
    completed = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert len(completed["debateResults"]) == 2
    assert provider.calls[:len(initial_calls)] == initial_calls
    assert sum(c.startswith("reaction:") for c in provider.calls) == 3
    assert "debate:wannabe" not in provider.calls
    for response in completed["debateResults"]:
        assert response["replyToId"] == "initial:wannabe"
        assert response["visibleMessageIds"] == ["initial:wannabe"]
        assert response["round"] == 2
    replay = send(app, "GET", f"/api/simulation-runs/{run['id']}/events")
    assert "skippedReason" not in replay.text


@pytest.mark.parametrize("invalid", ["self", "future", "no_reason"])
def test_invalid_reply_is_partial_and_other_readers_survive(app, invalid):
    class Provider(FakeAudienceSimulationModelProvider):
        async def debate_response(self, **kwargs):
            result = await super().debate_response(**kwargs)
            if kwargs["persona"]["id"] == "wannabe":
                reply = result["debateResponse"]
                if invalid == "no_reason":
                    reply.update(changedMind=True, changeReason="")
                else:
                    reply["replyToId"] = "initial:wannabe" if invalid == "self" else "reply:future"
            return result

    run = create_simulation_run(app)
    app.state.simulation_workflow_service.fake_provider = Provider()
    collect(app, run["id"])
    completed = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert completed["status"] == "partially_completed"
    assert len(completed["reactionResults"]) == 3
    assert len(completed["debateResults"]) == 2
    assert "debate_responses.wannabe" in completed["stageErrors"]


def test_live_provider_gets_paired_history_and_own_previous_state(app):
    run = create_simulation_run(app)
    snapshot = run["inputSnapshot"]
    episode = {"noteId": "n", "commentId": "c", "noteTitle": "历史笔记",
               "noteExcerpt": "历史正文", "observedComment": "费用怎么算",
               "evidenceQuote": "费用怎么算"}
    snapshot.update(mode="live", audiencePersonas=[{
        "id": pid, "name": pid, "profile": "费用视角", "unknowns": ["收入未知"],
        "observedEpisodes": [episode],
    } for pid in ("a", "b")])
    with app.state.simulation_service.database.transaction() as c:
        c.execute("UPDATE simulation_runs SET input_snapshot_json=? WHERE id=?",
                  (json.dumps(snapshot, ensure_ascii=False), run["id"]))

    class Model:
        async def call_operation(self, operation, context):
            if operation == ModelOperation.SIMULATION_REACTION:
                assert context["persona"]["observedEpisodes"][0]["noteExcerpt"] == "历史正文"
                assert context["persona"]["unknowns"] == ["收入未知"]
                pid = context["persona"]["id"]
                output = {"reaction": {"personaId": pid, "stance": "不确定",
                                       "action": "comment" if pid == "a" else "no_comment",
                                       "quote": "是否含住宿？" if pid == "a" else "",
                                       "understanding": "独立理解"}}
            elif operation == ModelOperation.SIMULATION_DEBATE:
                assert context["persona"]["id"] == "b"
                assert context["priorReaction"]["understanding"] == "独立理解"
                assert set(context["otherReactions"][0]) == {
                    "messageId", "personaId", "quote", "round",
                }
                output = {"debateResponse": {
                    "personaId": "b", "response": "我也想知道保险是否包含在内",
                    "replyToId": "initial:a", "changedMind": False,
                }}
            else:
                assert operation == ModelOperation.SIMULATION_SYNTHESIS
                assert context["debateResponses"][0]["replyToId"] == "initial:a"
                output = {"synthesis": {"verdict": "补充费用口径"}}
            return ModelCallResponse(output=output, model_metadata={"model": "injected"})

    app.state.simulation_workflow_service.live_provider = RealAudienceSimulationModelProvider(
        Model()
    )
    collect(app, run["id"])
    completed = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert completed["status"] == "completed"
    assert completed["personaDefinitions"][0]["observedEpisodes"][0]["noteId"] == "n"
    assert completed["debateResults"][0]["targetedAt"] == "a"


def test_simulation_run_review_metadata_is_editable_without_mutating_result(
    app: FastAPI,
) -> None:
    run = create_simulation_run(app)
    collect(app, run["id"])
    completed = send(app, "GET", f"/api/simulation-runs/{run['id']}").json()
    assert completed["userNotes"] == ""
    assert completed["reviewStatus"] == "unreviewed"

    updated = send(
        app,
        "PATCH",
        f"/api/simulation-runs/{run['id']}/review",
        json={
            "userNotes": "反对意见有用，可用于改标题。",
            "reviewStatus": "useful",
            "expectedUpdatedAt": completed["updatedAt"],
        },
    )
    assert updated.status_code == 200
    updated_json = updated.json()
    assert updated_json["userNotes"] == "反对意见有用，可用于改标题。"
    assert updated_json["reviewStatus"] == "useful"
    assert updated_json["synthesis"] == completed["synthesis"]
    assert updated_json["reactionResults"] == completed["reactionResults"]

    stale = send(
        app,
        "PATCH",
        f"/api/simulation-runs/{run['id']}/review",
        json={
            "reviewStatus": "rejected",
            "expectedUpdatedAt": completed["updatedAt"],
        },
    )
    assert stale.status_code == 409
