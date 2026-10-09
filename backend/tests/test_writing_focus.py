import asyncio
import json
from uuid import uuid4

import pytest
from pydantic import ValidationError as SchemaError
from test_content_collaboration_provider import frozen_context
from test_content_collaboration_sessions import (
    ChainedHandoffProvider,
    create_workspace_and_topic,
    until,
)

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import (
    ContentCollaborationMessageCreate,
    ContentCollaborationSessionCreate,
    ContentWritingFocus,
)
from app.repositories.topics import TopicRepository
from app.services.common import utc_now
from app.services.content_collaboration_provider import RealContentCollaborationProvider
from app.services.panel_interviews import PanelInterviewCreate
from app.services.writing_focus import resolve_writing_focus


@pytest.fixture
def saved(app):
    workspace, topic = create_workspace_and_topic(app)
    body = "🌱开头。重复片段。结尾。重复片段。"
    with app.state.database.transaction() as connection:
        connection.execute("UPDATE topics SET body=? WHERE id=?", (body, topic["id"]))
        topic = TopicRepository().get(connection, topic["id"])
    return workspace["id"], topic


def focus(topic, **values):
    return ContentWritingFocus.model_validate({
        "expectedUpdatedAt": topic["updated_at"], **values,
    })


def resolve(app, saved, payload):
    wid, topic = saved
    with app.state.database.read() as connection:
        return resolve_writing_focus(connection, workspace_id=wid, topic=topic, payload=payload)


def simulation(app, saved, *, stage="initial", action="comment", status="completed",
               category="creation", owner=None, topic_id=None):
    wid, topic = saved
    sid, now = str(uuid4()), utc_now()
    snapshot = {"mode": "demo", "simulationCategory": category,
                "targetType": "topic", "topic": {"topicId": topic["id"], "title": "原稿",
                "body": "旧版被读者阅读的内容", "updatedAt": "2026-10-01T00:00:00Z"}}
    reaction = [{"messageId": "actual-initial", "personaId": "reader-1", "action": action,
                 "quote": "这里没看懂。", "understanding": "私密理解", "concerns": ["私密顾虑"]}]
    debate = [{"messageId": "actual-reply", "personaId": "reader-1",
               "response": "@reader-1 我更想看到怎么判断。", "changedMindReason": "私密理由"}]
    with app.state.database.transaction() as connection:
        connection.execute(
            "INSERT INTO simulation_runs (id,workspace_id,topic_id,status,input_snapshot_json,"
            "persona_definitions_json,reaction_results_json,debate_results_json,"
            "created_at,completed_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (sid, owner or wid, topic_id or topic["id"], status, json.dumps(snapshot),
             json.dumps([{"id": "reader-1", "name": "关心判断的读者", "profile": "看怎么判断"}]),
             json.dumps(reaction), json.dumps(debate), now, now, now),
        )
    return {"simulationId": sid, "stage": stage, "messageId": f"{stage}:reader-1"}


def test_codepoint_selection_preserves_second_duplicate(app, saved):
    _, topic = saved
    start = topic["body"].rindex("重复片段")
    selection = {"start": start, "end": start + 4, "text": "重复片段"}
    result = resolve(app, saved, focus(topic, selection=selection))
    assert result["selection"] == selection
    assert result["baseBody"] == topic["body"]
    assert result["baseTopicId"] == topic["id"]
    with pytest.raises(ConflictError, match="片段"):
        resolve(app, saved, focus(topic, selection={**selection, "start": start + 1}))


def test_stale_version_and_fabricated_client_quote_are_rejected(app, saved):
    _, topic = saved
    with pytest.raises(ConflictError, match="更新"):
        resolve(app, saved, focus(topic, expectedUpdatedAt="2020-01-01T00:00:00Z",
                                 selection={"start": 0, "end": 1, "text": "🌱"}))
    reference = simulation(app, saved)
    with pytest.raises(SchemaError):
        focus(topic, readerReference={**reference, "content": "作者同意了新增事实"})
    with pytest.raises(SchemaError):
        focus(topic, selection={"start": True, "end": 2, "text": "开"})


@pytest.mark.parametrize("stage,message_id", [
    ("initial", "initial:reader-1"), ("initial", "actual-initial"),
    ("reply", "reply:reader-1"), ("reply", "actual-reply"),
])
def test_quotes_resolved_only_from_public_saved_utterances(app, saved, stage, message_id):
    _, topic = saved
    reference = simulation(app, saved, stage=stage)
    reference["messageId"] = message_id
    result = resolve(app, saved, focus(topic, readerReference=reference))
    assert result["readerMessage"]["senderName"] == "关心判断的读者"
    assert result["readerMessage"]["sourceTarget"]["body"] == "旧版被读者阅读的内容"
    assert result["readerMessage"]["sourceUpdatedAt"] == "2026-10-01T00:00:00Z"
    assert result["baseBody"] == topic["body"]
    assert "私密" not in json.dumps(result, ensure_ascii=False)
    assert "@reader-1" not in result["readerMessage"]["content"]


@pytest.mark.parametrize("action", ["comment", None, "no_comment", "skip"])
def test_legacy_initial_text_is_public_only_for_comment_or_missing_action(app, saved, action):
    reference = simulation(app, saved)
    message = {"personaId": "reader-1", "text": "旧记录的公开意见。"}
    if action is not None:
        message["action"] = action
    with app.state.database.transaction() as connection:
        connection.execute("UPDATE simulation_runs SET reaction_results_json=? WHERE id=?",
                           (json.dumps([message]), reference["simulationId"]))
    if action in {None, "comment"}:
        result = resolve(app, saved, focus(saved[1], readerReference=reference))
        assert result["readerMessage"]["content"] == "旧记录的公开意见。"
    else:
        with pytest.raises(NotFoundError, match="公开发言"):
            resolve(app, saved, focus(saved[1], readerReference=reference))


def test_legacy_text_does_not_invent_identity_from_display_only_snapshot(app, saved):
    reference = simulation(app, saved)
    with app.state.database.transaction() as connection:
        connection.execute(
            "UPDATE simulation_runs SET persona_definitions_json='[]', "
            "reaction_results_json=?, input_snapshot_json=? WHERE id=?",
            (json.dumps([{"personaId": "reader-1", "text": "只有展示身份的旧意见。"}]),
             json.dumps({"topic": {"topicId": saved[1]["id"], "body": "旧稿"},
                         "audiencePersonas": [{"id": "reader-1", "name": "展示读者"}]}),
             reference["simulationId"]),
        )
    with pytest.raises(NotFoundError, match="公开发言"):
        resolve(app, saved, focus(saved[1], readerReference=reference))


@pytest.mark.parametrize("change,error", [
    ({"action": "no_comment"}, NotFoundError),
    ({"status": "running"}, ValidationError),
    ({"category": "published_note"}, ValidationError),
    ({"category": "account"}, ValidationError),
])
def test_nonpublic_pending_and_noncreation_sources_rejected(app, saved, change, error):
    reference = simulation(app, saved, **change)
    with pytest.raises(error):
        resolve(app, saved, focus(saved[1], readerReference=reference))


def test_cross_workspace_cross_topic_and_fake_message_rejected(app, saved):
    other_workspace, other_topic = create_workspace_and_topic(app)
    for changes, error in [({"owner": other_workspace["id"]}, NotFoundError),
                           ({"topic_id": other_topic["id"]}, ValidationError)]:
        reference = simulation(app, saved, **changes)
        with pytest.raises(error):
            resolve(app, saved, focus(saved[1], readerReference=reference))
    reference = simulation(app, saved)
    reference["messageId"] = "made-up"
    with pytest.raises(NotFoundError):
        resolve(app, saved, focus(saved[1], readerReference=reference))


def test_interview_reference_recovers_its_own_author_question(app, saved):
    wid, topic = saved
    reference = simulation(app, saved)
    interviews = app.state.panel_interview_service
    interview = interviews.create(wid, reference["simulationId"], PanelInterviewCreate(
        request_key="test-followup", question="如果补一个例子，你觉得够吗？",
        recipient_persona_id="reader-1",
    ))
    author = next(item for item in interview.messages if item.role == "author")
    rid = str(uuid4())
    with app.state.database.transaction() as connection:
        connection.execute(
            "INSERT INTO panel_interview_messages (id,interview_id,role,persona_id,sender_name,"
            "recipient_name,reply_to_id,content,created_at) VALUES (?,?,'reader',?,?,?,?,?,?)",
            (rid, interview.id, "reader-1", "读者", "作者", author.id,
             "一个例子就够，别补成长教程。", utc_now()),
        )
    reference.update({"stage": "interview", "interviewId": interview.id, "messageId": rid})
    result = resolve(app, saved, focus(topic, readerReference=reference))
    assert result["readerMessage"]["authorQuestion"] == interview.question
    assert result["readerMessage"]["content"] == "一个例子就够，别补成长教程。"
    reference["messageId"] = author.id
    with pytest.raises(NotFoundError):
        resolve(app, saved, focus(topic, readerReference=reference))

    # A reply must refer to its own round's author message, not borrow a
    # question from another interview even when both belong to the same run.
    with app.state.database.transaction() as connection:
        connection.execute("UPDATE panel_interviews SET status='completed' WHERE id=?",
                           (interview.id,))
    other = interviews.create(wid, reference["simulationId"], PanelInterviewCreate(
        request_key="another-followup", question="完全不同的追问？",
        recipient_persona_id="reader-1",
    ))
    other_author = next(item for item in other.messages if item.role == "author")
    with app.state.database.transaction() as connection:
        connection.execute("UPDATE panel_interview_messages SET reply_to_id=? WHERE id=?",
                           (other_author.id, rid))
    reference["messageId"] = rid
    with pytest.raises(NotFoundError):
        resolve(app, saved, focus(topic, readerReference=reference))


def test_frozen_source_cannot_claim_a_different_topic(app, saved):
    reference = simulation(app, saved)
    with app.state.database.transaction() as connection:
        connection.execute(
            "UPDATE simulation_runs SET input_snapshot_json=? WHERE id=?",
            (json.dumps({"topic": {"topicId": "other-topic", "body": "不同内容"}}),
             reference["simulationId"]),
        )
    with pytest.raises(ValidationError, match="原稿标识"):
        resolve(app, saved, focus(saved[1], readerReference=reference))


def test_legacy_draft_simulation_cannot_be_used_as_topic_body_opinion(app, saved):
    reference = simulation(app, saved)
    with app.state.database.transaction() as connection:
        connection.execute(
            "UPDATE simulation_runs SET input_snapshot_json=? WHERE id=?",
            (json.dumps({"targetType": "draft", "topic": {"topicId": saved[1]["id"]},
                         "draft": {"editableContent": {"structure": {"outline": []}}}}),
             reference["simulationId"]),
        )
    with pytest.raises(ValidationError, match="当前创作"):
        resolve(app, saved, focus(saved[1], readerReference=reference))


def test_focus_frozen_for_all_roles_and_replay_before_freshness(app, saved):
    wid, topic = saved
    service = app.state.content_collaboration_service
    provider = ChainedHandoffProvider()
    service.provider = provider
    session = service.create(wid, ContentCollaborationSessionCreate.model_validate({
        "contextTarget": {"assetType": "topic", "assetId": topic["id"]},
    }))
    payload = ContentCollaborationMessageCreate.model_validate({
        "content": "只改这段", "recipient": "research", "mode": "demo", "requestKey": "first",
        "writingFocus": {"expectedUpdatedAt": topic["updated_at"],
                         "selection": {"start": 0, "end": 4, "text": "🌱开头。"}},
    })

    async def scenario():
        await service.send_message(wid, session.id, payload)
        await until(lambda: service.get(wid, session.id).execution_status == "waiting_creator")
        completed = service.get(wid, session.id)
        assert [role for role, _ in provider.calls] == ["research", "writing", "review"]
        for _, context in provider.calls:
            assert context["writingFocus"]["selection"]["text"] == "🌱开头。"
        for message in completed.messages:
            assert message.model_metadata["writingFocus"]["baseBody"] == topic["body"]
        with app.state.database.transaction() as connection:
            connection.execute("UPDATE topics SET body='新稿',updated_at=? WHERE id=?",
                               (utc_now(), topic["id"]))
        replay = await service.send_message(wid, session.id, payload)
        assert len(replay.messages) == len(completed.messages)
        assert len(provider.calls) == 3
        with pytest.raises(ConflictError, match="另一条"):
            await service.send_message(wid, session.id, payload.model_copy(update={
                "writing_focus": focus(topic, selection={"start": 1, "end": 3, "text": "开头"}),
            }))
        with pytest.raises(ConflictError, match="更新"):
            await service.send_message(wid, session.id, payload.model_copy(update={
                "request_key": "second",
            }))
        await service.shutdown()

    asyncio.run(scenario())


@pytest.mark.parametrize("role", ["research", "writing", "review"])
def test_role_packet_keeps_focus_and_citable_public_opinion(role):
    message, context = frozen_context()
    context["writingFocus"] = {"baseTitle": "当前标题", "baseBody": "当前正文",
                               "selection": {"start": 0, "end": 2, "text": "当前"},
                               "readerMessage": {"content": "更想看判断过程",
                               "senderName": "读者", "sourceTarget": {"body": "旧稿"}}}
    provider = RealContentCollaborationProvider
    sources = provider._sources_for_role(role=role, message=message, context=context,
                                        sources=provider._allowed_sources(context))
    packet = provider._model_context(role=role, message=message, context=context, sources=sources)
    assert packet["writingFocus"] == context["writingFocus"]
    assert "writing:selected_text" in sources
    assert "writing:reader_opinion" in sources
    rules = " ".join(packet["roleTask"]["writingFocusRules"])
    assert "不得返回整篇" in rules
    assert "不是作者已确认的事实" in rules
