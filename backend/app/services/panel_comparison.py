"""Read-only, ID-paired evidence from two frozen runs; no model interpretation."""

from app.errors import ValidationError
from app.services.audience_target import reader_visible_target
from app.services.panel_retests import digest, validate_parent


def _record(rows, persona_id):
    matches = [r for r in rows if isinstance(r, dict) and r.get("personaId") == persona_id]
    if len(matches) > 1:
        raise ValidationError("同一读者存在重复结果，暂不能逐人对照")
    return matches[0] if matches else None


def _texts(value):
    return [s for s in value if isinstance(s, str) and s.strip()] if isinstance(value, list) else []


def _validate_text_fields(record, text_fields, list_fields):
    if record is None:
        return
    if any(key in record and not isinstance(record[key], str) for key in text_fields):
        raise ValidationError("旧读者结果包含无法展示的文字字段，暂不能逐人对照")
    if any(key in record and (not isinstance(record[key], list)
           or any(not isinstance(item, str) for item in record[key])) for key in list_fields):
        raise ValidationError("旧读者结果包含无法展示的列表字段，暂不能逐人对照")


def _side(run, persona_id):
    reaction = _record(run.reaction_results, persona_id)
    reply = _record(run.debate_results, persona_id)
    _validate_text_fields(reaction, ("understanding", "stance", "quote", "text", "action"),
                          ("concerns", "opportunities"))
    _validate_text_fields(reply, ("response", "text", "changeReason"),
                          ("newConcerns", "strongerSignals"))
    initial_error = run.stage_errors.get(f"initial_reactions.{persona_id}")
    reply_error = run.stage_errors.get(f"debate_responses.{persona_id}")
    if reaction is not None and initial_error or reply is not None and reply_error:
        raise ValidationError("读者结果和失败状态冲突，暂不能逐人对照")
    initial_status = "failed" if initial_error else "missing"
    if reaction is not None:
        initial_status = reaction.get("action") or "unknown"
    enabled = run.input_snapshot["panelTask"]["discussionEnabled"]
    reply_status = "disabled" if not enabled else "failed" if reply_error else "not_recorded"
    if reply is not None:
        if not enabled:
            raise ValidationError("关闭讨论的记录包含回应，暂不能逐人对照")
        reply_text = reply.get("response") or reply.get("text") or ""
        reply_status = "replied" if reply_text.strip() else "silent"
    return {
        "initialStatus": initial_status,
        "understanding": (reaction or {}).get("understanding", ""),
        "stance": (reaction or {}).get("stance", ""),
        "quote": ((reaction or {}).get("quote") or (reaction or {}).get("text") or "")
        if initial_status == "comment" else "",
        "concerns": _texts((reaction or {}).get("concerns")),
        "opportunities": _texts((reaction or {}).get("opportunities")),
        "replyStatus": reply_status,
        "reply": reply_text if reply_status == "replied" else "",
        "newConcerns": _texts((reply or {}).get("newConcerns")),
        "strongerSignals": _texts((reply or {}).get("strongerSignals")),
        "changeReason": (reply or {}).get("changeReason", ""),
    }


def _summary(run):
    calls = run.model_metadata.get("responseCalls", [])
    signatures = []
    for call in calls if isinstance(calls, list) else []:
        if not isinstance(call, dict):
            continue
        item = {key: call[key] for key in
                ("operation", "provider", "model", "modelSource", "systemPromptHash")
                if isinstance(call.get(key), str)}
        if item and item not in signatures:
            signatures.append(item)
    return {"id": run.id, "status": run.status, "createdAt": run.created_at,
            "title": run.input_snapshot["topic"]["title"],
            "body": run.input_snapshot["topic"]["body"],
            "mode": run.input_snapshot["mode"], "recordedModels": signatures}


def compare_panel_runs(parent, child):
    validate_parent(parent)
    if child.status not in {"completed", "partially_completed", "failed"}:
        raise ValidationError("请等待本次复测结束后再对照")
    source = child.input_snapshot
    try:
        if (child.workspace_id != parent.workspace_id or child.topic_id != parent.topic_id
                or child.parent_simulation_id != parent.id
                or source["parentSimulationId"] != parent.id
                or source["workspaceId"] != parent.workspace_id
                or source["targetType"] != "topic" or source["draft"] is not None
                or source["topic"]["topicId"] != parent.topic_id
                or not isinstance(source["topic"]["title"], str)
                or not isinstance(source["topic"]["body"], str)
                or source["simulatedFanIds"] != parent.input_snapshot["simulatedFanIds"]
                or source["accountPositioning"] != parent.input_snapshot["accountPositioning"]
                or source["simulationMethod"] != parent.input_snapshot["simulationMethod"]
                or source["retest"]["version"] != "fixed-panel/v1"
                or source["retest"]["personaSnapshotHash"] != digest(parent.persona_definitions)
                or source["retest"]["parentTargetContentHash"]
                != parent.input_snapshot["targetContentHash"]
                or source["retest"]["parentTopicUpdatedAt"]
                != parent.input_snapshot["topic"]["updatedAt"]
                or source["audiencePersonas"] != parent.persona_definitions
                or (child.persona_definitions
                    and child.persona_definitions != parent.persona_definitions)
                or source["panelTask"] != parent.input_snapshot["panelTask"]
                or source["mode"] != parent.input_snapshot["mode"]
                or source["targetContentHash"] != digest(reader_visible_target(source))):
            raise ValueError("snapshot mismatch")
    except (KeyError, TypeError, ValueError) as error:
        raise ValidationError("两次试读的来源或固定人物任务无法核对，不能标为同组对照") from error
    ids = {p["id"] for p in parent.persona_definitions}
    for run in (parent, child):
        for rows in (run.reaction_results, run.debate_results):
            if any(not isinstance(r, dict) or r.get("personaId") not in ids for r in rows):
                raise ValidationError("结果包含未在当时名单中的读者，暂不能逐人对照")
    return {
        "workspaceId": child.workspace_id, "simulationId": child.id,
        "parentSimulationId": parent.id, "before": _summary(parent), "after": _summary(child),
        "readers": [{"id": p["id"], "name": p["name"], "profile": p["profile"],
                     "before": _side(parent, p["id"]), "after": _side(child, p["id"])}
                    for p in parent.persona_definitions],
        "limitations": [
            "并排展示当时记录；新版未提及某个顾虑，不等于已经解决。",
            "固定人物与任务，但模型输出仍可能变化；不能把差异全归因于改稿。",
            "模型信息只覆盖已成功返回的调用，不代表全部尝试或费用；旧记录不补造。",
            "系统提示指纹不覆盖用户提示拼装逻辑，尚不构成完整提示版本配对。",
        ],
    }
