"""Resolve editing scope and public reader quotes before freezing a writing turn.

Browser references are identifiers only. All quoted content and source versions
come from saved product records; nothing in this module mutates those records.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from app.errors import ConflictError, NotFoundError, ValidationError
from app.models import ContentWritingFocus
from app.services.audience_target import reader_visible_target
from app.services.panel_interviews import _named_mentions, _names
from app.services.simulation_review import simulation_category


def _decode(value: str, expected: type):
    try:
        result = json.loads(value)
    except (ValueError, TypeError) as error:
        raise ValidationError("读者意见记录无法读取") from error
    if not isinstance(result, expected):
        raise ValidationError("读者意见记录无法读取")
    return result


def resolve_writing_focus(connection, *, workspace_id: str, topic: dict,
                          payload: ContentWritingFocus) -> dict[str, Any]:
    if datetime.fromisoformat(topic["updated_at"].replace("Z", "+00:00")) != (
        payload.expected_updated_at
    ):
        raise ConflictError("正文已更新，请重新选择片段后再改写")
    result: dict[str, Any] = {
        "schemaVersion": "writing-focus/v1",
        "baseTopicId": topic["id"],
        "baseTitle": topic["title"],
        "baseBody": topic["body"],
        "baseUpdatedAt": topic["updated_at"],
    }
    if payload.selection is not None:
        selection = payload.selection
        body = topic["body"]
        if selection.end > len(body) or body[selection.start:selection.end] != selection.text:
            raise ConflictError("选中的片段与已保存正文不一致，请重新选择")
        result["selection"] = selection.model_dump(by_alias=True)
    if payload.reader_reference is not None:
        reference = payload.reader_reference
        row = connection.execute(
            "SELECT * FROM simulation_runs WHERE id=? AND workspace_id=?",
            (reference.simulation_id, workspace_id),
        ).fetchone()
        if row is None:
            raise NotFoundError("读者意见来源不存在")
        snapshot = _decode(row["input_snapshot_json"], dict)
        if (row["topic_id"] != topic["id"] or row["draft_id"] is not None
            or snapshot.get("targetType") == "draft" or snapshot.get("draft")
            or simulation_category(snapshot) != "creation"):
            raise ValidationError("请选用当前创作对应的读者意见")
        source_topic = snapshot.get("topic") or {}
        source_draft = snapshot.get("draft") or {}
        if (not isinstance(source_topic, dict) or not isinstance(source_draft, dict)
            or any(source.get("topicId") not in {None, topic["id"]}
                   for source in (source_topic, source_draft))):
            raise ValidationError("读者意见的原稿标识与当前创作不一致")
        if row["status"] not in {"completed", "partially_completed"}:
            raise ValidationError("请等本轮试读结束后，再使用读者意见改稿")
        personas = _decode(row["persona_definitions_json"], list)
        names = _names(personas)
        if reference.stage == "interview":
            message = connection.execute(
                "SELECT m.*, a.content AS author_question FROM panel_interview_messages m "
                "JOIN panel_interviews i ON i.id=m.interview_id "
                "JOIN panel_interview_messages a ON a.id=m.reply_to_id "
                "AND a.interview_id=m.interview_id AND a.role='author' "
                "WHERE m.id=? AND m.interview_id=? AND m.role='reader' "
                "AND i.workspace_id=? AND i.simulation_id=?",
                (reference.message_id, reference.interview_id,
                 workspace_id, reference.simulation_id),
            ).fetchone()
            if message is None or message["persona_id"] not in names:
                raise NotFoundError("这条公开访谈回复不存在")
            public = {"personaId": message["persona_id"],
                      "senderName": names[message["persona_id"]],
                      "content": message["content"],
                      "authorQuestion": message["author_question"]}
        else:
            field = ("reaction_results_json" if reference.stage == "initial"
                     else "debate_results_json")
            messages = _decode(row[field], list)
            matches = [item for item in messages if isinstance(item, dict)
                       and reference.message_id in {
                           item.get("messageId"),
                           f"{reference.stage}:{item.get('personaId')}",
                       }]
            if len(matches) != 1:
                raise NotFoundError("这条公开读者发言不存在")
            message = matches[0]
            persona_id = message.get("personaId")
            content = ((message.get("quote") or message.get("text")) if reference.stage == "initial"
                       else message.get("response") or message.get("text"))
            if (persona_id not in names or not isinstance(content, str) or not content.strip()
                or reference.stage == "initial" and message.get("action", "comment") != "comment"):
                raise NotFoundError("这条记录没有可引用的公开发言")
            public = {"personaId": persona_id, "senderName": names[persona_id],
                      "content": _named_mentions(content.strip(), names)}
        try:
            source_target = reader_visible_target(snapshot)
        except (KeyError, TypeError, AttributeError) as error:
            raise ValidationError("读者意见缺少可读的原稿版本") from error
        public["sourceTarget"] = source_target
        public["sourceUpdatedAt"] = source_draft.get("updatedAt") or source_topic.get("updatedAt")
        public["sourceKind"] = "simulated_reader_opinion"
        result["readerReference"] = reference.model_dump(by_alias=True, exclude_none=True)
        result["readerMessage"] = public
    return result
