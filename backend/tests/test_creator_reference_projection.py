import asyncio
import json
from copy import deepcopy
from pathlib import Path

from test_content_collaboration_provider import FakeModelCallService

from app.config import Settings
from app.models import ModelOperation
from app.services.content_collaboration import CollaborationMessage
from app.services.content_collaboration_provider import RealContentCollaborationProvider
from app.services.creator_reference_projection import account_writing_views
from app.services.model_calls import PROMPT_SINGLE_CREATOR_WRITING, ModelCallService


def report():
    return {
        "profile": {
            "observations": {"coverage": {"selectedCount": 10}},
            "profile": {"voiceFingerprint": ["反问后给出具体比较方法"],
                        "example": {"quote": "朋友在交材料当天决定放弃。"}},
        },
        "pain_points": {"painPoints": [
            {"theme": "如何做选择", "count": 1,
             "evidence": ["我是机械专业，老师给我两天考虑。"]},
        ]},
    }


def test_editorial_and_comment_views_preserve_content_and_owners_without_mutation():
    content = report()
    frozen = deepcopy(content)
    editorial, feedback = account_writing_views(content)
    assert content == frozen
    assert editorial == {"profile": content["profile"]["profile"]}
    assert feedback[0]["analysis"] == {"theme": "如何做选择", "count": 1}
    assert feedback[0]["historicalComments"] == [
        {"speaker": "历史评论者，身份未核实", "text": "我是机械专业，老师给我两天考虑。"},
    ]
    assert "未知" in feedback[0]["currentReaderCircumstances"]


def test_legacy_and_unrecognized_reference_shapes_are_not_silently_discarded():
    for content in ("旧版文本", {"summary": "旧报告"},
                    {"pain_points": {"painPoints": [{"evidence": [None]}]}},
                    {"pain_points": {"painPoints": "旧版文本"}}):
        assert account_writing_views(content) == (content, [])
    content = report()
    content["profile"]["custom"] = "旧扩展字段"
    content["pain_points"]["custom"] = "旧反馈说明"
    editorial, _ = account_writing_views(content)
    assert editorial["profile"] == content["profile"]
    assert editorial["pain_points"] == {"custom": "旧反馈说明"}


def test_provider_separates_feedback_sources_and_keeps_original_note_intact():
    original = "推免材料上交当天，朋友决定放弃。原文的主体与时间不能改。"
    context = {
        "assistantMode": "single_writer", "target": {"title": "选题", "body": ""},
        "sessionContext": {"creatorContextSnapshot": {"references": [
            {"kind": "account_analysis", "id": "a", "content": report()},
            {"kind": "imported_note", "id": "m", "noteId": "n",
             "content": {"title": "原标题", "body": original}},
        ]}},
        "transcript": [],
    }
    sources = RealContentCollaborationProvider._allowed_sources(context)
    editorial = sources["reference:account_analysis:a"]["text"]
    comment = sources["reference:account_analysis:a:feedback:1"]
    assert "机械专业" not in editorial
    assert "selectedCount" not in editorial
    assert "朋友在交材料当天决定放弃。" in editorial
    assert "机械专业" in comment["text"]
    assert comment["purpose"] == "historical_feedback"
    note = next(source for key, source in sources.items()
                if key.startswith("reference:imported_note:"))
    assert original in note["text"]


def dialogue_packet():
    previous = CollaborationMessage(
        id="prior-user", sender="creator", to="writing", content="我上次做了一份检查清单。",
    )
    old_ai = CollaborationMessage(
        id="prior-ai", sender="writing", to="creator", content="未经确认的读者找过作者。",
    )
    message = CollaborationMessage(
        id="current", sender="creator", to="writing",
        content="写给觉得自己没做过大项目的应届生。保留我做过检查清单的事实。",
    )
    context = {
        "assistantMode": "single_writer", "target": {"title": "小改进", "body": "已有稿件"},
        "receivedMessage": message.model_dump(),
        "sessionContext": {"creatorContextSnapshot": {"references": [
            {"kind": "account_analysis", "id": "a", "content": report()},
            {"kind": "imported_note", "id": "m", "noteId": "n", "content": {
                "title": "原笔记", "body": "这篇来自朋友。她做了配置模板，降低错误率。",
            }},
        ]}},
        "transcript": [previous.model_dump(), old_ai.model_dump(), message.model_dump()],
    }
    return message, context


def test_writer_request_is_once_in_real_dialogue_not_repeated_as_factual_material():
    message, context = dialogue_packet()
    frozen = deepcopy(context)
    sources = RealContentCollaborationProvider._allowed_sources(context)
    packet = RealContentCollaborationProvider._model_context(
        role="writing", message=message, context=context, sources=sources,
    )
    service = ModelCallService(Settings(
        database_path=Path("/tmp/unused-projection.sqlite"),
        upload_directory=Path("/tmp/unused-projection-uploads"),
    ))
    system, user = service._build_prompt(ModelOperation.CONTENT_COLLABORATION_TURN, packet)
    messages = service._compatible_messages(ModelOperation.CONTENT_COLLABORATION_TURN,
                                            packet, system, user)
    assert context == frozen
    assert packet["schemaVersion"] == "creator-writing-packet/v2"
    assert system == PROMPT_SINGLE_CREATOR_WRITING  # Context change, no additional prompt layer.
    assert "creatorRequest" not in packet["creativeBrief"]
    assert message.content not in user
    assert sum(item["content"].count(message.content) for item in messages) == 1
    assert [item["role"] for item in messages] == ["system", "user", "user", "assistant", "user"]
    assert messages[2]["content"] == "我上次做了一份检查清单。"
    assert json.loads(messages[3]["content"])["turn"]["summary"] == "未经确认的读者找过作者。"
    assert messages[-1]["content"] == message.content
    views = {source["id"]: source for source in packet["evidence"]["allowedSources"]}
    assert views["message:prior-user"]["sourceRole"] == "creator_dialogue"
    assert views["message:prior-user"]["dialogueIndex"] == 0
    assert views["message:current"]["dialogueIndex"] == 2
    assert "text" not in views["message:current"]
    assert "message:prior-ai" not in views  # Prior AI remains discussion, not evidence.
    assert views["reference:account_analysis:a"]["sourceRole"] == "editorial_analysis"
    assert views["reference:account_analysis:a:feedback:1"]["sourceRole"] == (
        "historical_reader_feedback"
    )
    original = next(v for v in views.values() if v["sourceRole"] == "source_document")
    assert "这篇来自朋友。她做了配置模板，降低错误率。" in original["text"]
    assert original["narration"] == {
        "speakerScope": original["id"], "creatorBinding": "not_established_by_selection",
    }
    assert views["target:topic"]["sourceRole"] == "manuscript"
    # Exact author statements remain in the server-side source map for citation
    # checks; removing duplicate instructions must not remove true author facts.
    assert sources["message:prior-user"]["text"] == messages[2]["content"]
    assert "authorMessages" not in json.dumps(packet["evidence"]["sourceGroups"])


def test_explicit_author_fact_still_can_be_quoted_from_dialogue_index():
    message, context = dialogue_packet()
    model = FakeModelCallService({"turn": {
        "summary": "保留作者明确补充的事实。", "nextRecipient": "creator",
        "candidateSuggestions": [{
            "kind": "copy_option", "title": "从检查清单开始",
            "body": "我上次做了一份检查清单。", "confidence": "supported",
            "evidenceRefs": [{
                "sourceId": "message:prior-user", "quote": "我上次做了一份检查清单。",
            }],
        }],
    }}, provider="deepseek")
    result = asyncio.run(RealContentCollaborationProvider(model).run(
        role="writing", message=message, context=context,
    ))
    assert result.model_metadata["candidateSuggestions"][0]["body"] == "我上次做了一份检查清单。"
    assert len(model.calls) == 1


def test_dialogue_indexes_match_transmitted_messages_even_with_empty_legacy_turns():
    message, context = dialogue_packet()
    context["transcript"].insert(0, {
        "id": "empty-legacy", "sender": "creator", "content": "  ",
    })
    sources = RealContentCollaborationProvider._allowed_sources(context)
    packet = RealContentCollaborationProvider._model_context(
        role="writing", message=message, context=context, sources=sources,
    )
    views = {item["id"]: item for item in packet["evidence"]["allowedSources"]}
    assert "message:empty-legacy" not in views
    assert views["message:prior-user"]["dialogueIndex"] == 0
    assert views["message:current"]["dialogueIndex"] == 2
