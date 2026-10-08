import asyncio
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest
from test_audience_simulation_workflow import collect
from test_creator_experience import topic
from test_panel_retests import edit
from test_simulated_fans import seeded as seeded
from test_workspace_api import send

from app.models import PanelTask, SimulationRunCreate
from app.services.panel_retests import PanelRetestCreate
from app.workflows.audience_simulation import (
    SAMPLE_SIMULATION_ACCOUNT,
    FakeAudienceSimulationModelProvider,
)


@pytest.mark.parametrize("count", [1, 2, 4])
@pytest.mark.parametrize("discussion", [False, True])
def test_saved_readers_and_retest_with_actual_demo_provider(app, seeded, count, discussion):
    wid, _, _, fans = seeded
    service = app.state.simulation_service
    provider = FakeAudienceSimulationModelProvider()
    app.state.simulation_workflow_service.fake_provider = provider
    live = AsyncMock(side_effect=AssertionError("Demo must not call a real model"))
    app.state.simulation_workflow_service.live_provider.initial_reaction = live
    target = edit(app, topic(app, wid, "今天的小练习"), body="先记录一个问题，再写一个小行动。")
    ids = [fan["id"] for fan in fans[:count]]
    run = service.create(wid, SimulationRunCreate(
        topic_id=target["id"], simulated_fan_ids=ids, mode="demo",
        panel_task=PanelTask(reading_mode="natural", discussion_enabled=discussion),
    ))
    collect(app, run.id)
    parent = service.get(run.id)
    assert parent.status == "completed", parent.stage_errors
    assert not parent.stage_errors
    assert [p["id"] for p in parent.persona_definitions] == ids
    assert [r["personaId"] for r in parent.reaction_results] == ids
    assert "personas" not in provider.calls
    assert len(parent.debate_results) == (count if discussion and count > 1 else 0)
    assert "演示" in parent.synthesis["verdict"]
    assert parent.synthesis["editorFeedback"] == []
    assert "中介" not in str(parent.synthesis)
    for reply in parent.debate_results:
        assert reply["replyToId"] in reply["visibleMessageIds"]
        assert reply["targetedAt"] != reply["personaId"]
        assert reply["changedMind"] is False

    original = parent.model_dump()
    selected = fans[0]
    response = send(app, "PATCH", f"/api/simulated-fans/{selected['id']}", json={
        **selected["editable"], "name": "后来修改的名字", "status": "archived",
        "expectedUpdatedAt": selected["updatedAt"],
    })
    assert response.status_code == 200
    revised = edit(app, target, body="先写下今天遇到的一个问题，再列出十分钟能完成的行动。")
    child = service.create_retest(wid, parent.id, PanelRetestCreate(
        request_key="demo-retest", expected_updated_at=revised["updatedAt"], confirmed=True,
    ))
    collect(app, child.id, stop_after_node="parallel_initial_reactions")
    collect(app, child.id)
    completed = service.get(child.id)
    assert completed.status == "completed", completed.stage_errors
    assert completed.persona_definitions == parent.persona_definitions
    assert [r["personaId"] for r in completed.reaction_results] == ids
    assert len(completed.debate_results) == len(parent.debate_results)
    assert service.get(parent.id).model_dump() == original
    assert len(service.compare_retest(wid, child.id)["readers"]) == count
    calls = list(provider.calls)
    collect(app, child.id)
    assert provider.calls == calls
    live.assert_not_called()


def test_arbitrary_ids_do_not_get_remapped_to_three_sample_people():
    provider = FakeAudienceSimulationModelProvider()
    personas = [{"id": f"saved-{i}", "fanAssetId": f"saved-{i}", "name": "读者",
                 "profile": "已有角色"} for i in range(8)]

    async def run():
        return await asyncio.gather(*(provider.initial_reaction(
            persona=p, topic={"title": "不同主题", "body": "任意正文"},
        ) for p in personas))

    results = asyncio.run(run())
    assert [r["reaction"]["personaId"] for r in results] == [p["id"] for p in personas]
    assert all("演示" in r["reaction"]["quote"] for r in results)


def test_saved_sample_id_collision_does_not_reuse_unrelated_sample_text():
    provider = FakeAudienceSimulationModelProvider()
    person = deepcopy(SAMPLE_SIMULATION_ACCOUNT["personas"][0])
    person["fanAssetId"] = person["id"]
    result = asyncio.run(provider.initial_reaction(persona=person, topic={"title": "做饭"}))
    assert result["reaction"]["personaId"] == person["id"]
    assert "演示" in result["reaction"]["quote"]
    summary = asyncio.run(provider.synthesis(topic={"title": "做饭"}, personas=[person],
                                            reactions=[result["reaction"]], debate_responses=[]))
    assert "留学" not in str(summary)


@pytest.mark.parametrize("others", [[], [
    {"personaId": "self", "messageId": "initial:self", "quote": "自己"},
    {"personaId": "quiet", "messageId": "initial:quiet", "action": "no_comment", "quote": "不可见"},
    {"personaId": "missing-id", "quote": "无消息编号"},
]])
def test_no_visible_peer_returns_empty_reply_without_claiming_changed_mind(others):
    provider = FakeAudienceSimulationModelProvider()
    result = asyncio.run(provider.debate_response(
        persona={"id": "self", "profile": "任意"}, topic={"title": "标题"},
        other_reactions=others,
    ))["debateResponse"]
    assert result["response"] == ""
    assert result["replyToId"] is None
    assert result["changedMind"] is False


def test_empty_content_is_skipped_without_inventing_quote():
    result = asyncio.run(FakeAudienceSimulationModelProvider().initial_reaction(
        persona={"id": "saved", "profile": "任意"}, topic={"title": "", "body": " "},
    ))["reaction"]
    assert result["action"] == "skip"
    assert result["quote"] == result["triggerQuote"] == ""


def test_saved_reader_failure_remains_partial_and_not_a_complete_demo(app, seeded):
    wid, _, _, fans = seeded
    ids = [fan["id"] for fan in fans[:2]]
    provider = FakeAudienceSimulationModelProvider(failures={f"reaction:{ids[0]}"})
    app.state.simulation_workflow_service.fake_provider = provider
    run = app.state.simulation_service.create(wid, SimulationRunCreate(
        manual_topic="一次练习", simulated_fan_ids=ids, mode="demo",
        panel_task=PanelTask(reading_mode="natural", discussion_enabled=True),
    ))
    collect(app, run.id)
    result = app.state.simulation_service.get(run.id)
    assert result.status == "partially_completed"
    assert f"initial_reactions.{ids[0]}" in result.stage_errors
    assert [r["personaId"] for r in result.reaction_results] == [ids[1]]
    assert result.debate_results == []
    assert "1 份试读记录" in result.synthesis["verdict"]
