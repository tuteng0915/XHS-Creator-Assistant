import json
from copy import deepcopy

import pytest

from app.config import Settings
from app.models import ModelOperation
from app.services.content_collaboration import CollaborationMessage
from app.services.content_collaboration_provider import RealContentCollaborationProvider
from app.services.creator_fact_edit import fact_edit_sources
from app.services.creator_writing_context import compact_writing_packet
from app.services.model_calls import ModelCallService


def packet_for(body, old_body, *, selection=False):
    target = {"assetId": "topic", "assetType": "topic", "title": "当前标题", "body": body,
              "updatedAt": "2026-10-17T00:00:00Z"}
    message = CollaborationMessage(id="current", sender="creator", to="writing", content="请改稿")
    context = {"assistantMode": "single_writer", "target": target,
               "transcript": [{"id": "old", "sender": "writing", "to": "creator",
                               "content": "旧回复【当前标题】" + body}],
               "writingFocus": {"baseTitle": target["title"], "baseBody": body,
                                "baseUpdatedAt": target["updatedAt"], "readerMessage": {
                                    "content": "需要一个实例", "senderName": "读者",
                                    "sourceTarget": {"title": target["title"], "body": old_body},
                                    "sourceUpdatedAt": "2026-10-16T00:00:00Z"}}}
    if selection:
        context["writingFocus"]["selection"] = {"start": 0, "end": 2, "text": body[:2]}
    frozen = deepcopy(context)
    sources = RealContentCollaborationProvider._allowed_sources(context)
    result = RealContentCollaborationProvider._model_context(
        role="writing", message=message, context=context, sources=sources)
    assert context == frozen
    return result, sources


@pytest.mark.parametrize("body", ["完整当前正文。", "重复。重复。\n换行与emoji🧶。"])
def test_same_manuscript_occurs_once_and_sources_keep_identity(body):
    packet, originals = packet_for(body, body, selection=True)
    assert packet["creativeBrief"]["target"]["body"] == body
    focus = packet["writingFocus"]
    assert "baseBody" not in focus and "baseTitle" not in focus
    assert focus["baseManuscriptRef"] == "creativeBrief.target"
    assert focus["readerMessage"]["sourceTarget"]["bodyRef"] == "creativeBrief.target.body"
    assert focus["readerMessage"]["sourceUpdatedAt"] == "2026-10-16T00:00:00Z"
    views = {s["id"]: s for s in packet["evidence"]["allowedSources"]}
    assert views["target:topic"]["contentRef"] == "creativeBrief.target"
    assert views["target:topic"]["contentHash"] == originals["target:topic"]["contentHash"]
    assert "text" not in views["target:topic"]
    assert body not in packet["conversation"][0]["content"]
    eligible = fact_edit_sources(packet, [])  # Explicit diagnostic editor can resolve the ref.
    assert json.loads(eligible[0]["text"])["body"] == body


def test_different_reader_version_is_not_silently_replaced_by_current_manuscript():
    packet, _ = packet_for("现在的稿件。", "读者当时看到的不同稿件。")
    source = packet["writingFocus"]["readerMessage"]["sourceTarget"]
    assert source["body"] == "读者当时看到的不同稿件。" and "bodyRef" not in source


def test_different_unadopted_suggestion_and_mismatched_baseline_are_kept():
    source = {"creativeBrief": {"target": {"title": "新标题", "body": "当前正文。"}},
              "roleTask": {}, "writingFocus": {"baseTitle": "旧标题", "baseBody": "旧基准。"},
              "conversation": [{"role": "assistant", "content": "尚未采用的另一份稿。"}]}
    frozen = deepcopy(source)
    result = compact_writing_packet(source)
    assert result["conversation"][0]["content"] == "尚未采用的另一份稿。"
    assert result["writingFocus"]["baseBody"] == "旧基准。"
    assert source == frozen


def test_json_history_preserves_assistant_role_and_untouched_creator_facts(tmp_path):
    packet, _ = packet_for("已有正文。", "已有正文。")
    packet["conversation"].insert(0, {"sourceId": "user-fact", "role": "user",
                                      "content": "我昨天确实和家人聊过。"})
    service = ModelCallService(Settings(database_path=tmp_path / "db", upload_directory=tmp_path))
    system, user = service._build_prompt(ModelOperation.CONTENT_COLLABORATION_TURN, packet)
    messages = service._compatible_messages(ModelOperation.CONTENT_COLLABORATION_TURN,
                                            packet, system, user)
    assert [m["role"] for m in messages] == ["system", "user", "user", "assistant", "user"]
    assert messages[2]["content"] == "我昨天确实和家人聊过。"
    previous = json.loads(messages[3]["content"])
    assert previous["turn"]["nextRecipient"] == "creator"
    assert "creativeBrief.target.body" in previous["turn"]["summary"]
    assert messages[-1]["content"] == "请改稿"
