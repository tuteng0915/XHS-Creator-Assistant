"""Install handwritten results beneath verified existing profiles, without any model runtime.

This module never creates accounts, source materials, reader assets or topics. All
records are validated before one transaction appends terminal, immutable histories.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse
from uuid import NAMESPACE_URL, uuid5

from app.db.database import SQLiteDatabase
from app.services.account_diagnosis_evidence import build_account_observations, verified_portrait
from app.services.audience_analyses import validate_audience_output
from app.services.audience_evidence import audience_context
from app.services.audience_target import reader_visible_target
from app.services.common import utc_now
from app.services.saved_note_target import saved_note_target

ORIGIN = "oracle_showcase"
BUNDLE_VERSION = "workspace-oracle/v1"
# Stable platform IDs, not share tokens, workspace names or machine-specific DB IDs.
PROFILE_IDENTITIES = {
    "qsheep": ("54bf8e7bb4c4d64c5ece14cd", "QSheep"),
    "xiucai": ("5d2aefea0000000010004907", "秀才加点冰"),
    "ag": ("5c45cfc9000000001203c1b4", "Ag"),
    "yiliyu": ("67ed2399000000000e01e16b", "一粒鱼"),
}
TABLES = {"analysis": "analysis_runs", "audience": "audience_analyses",
          "simulation": "simulation_runs"}


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def _require(condition: object, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _text(value: object, field: str) -> str:
    _require(isinstance(value, str) and value.strip(), f"{field} 不能为空")
    return value.strip()


def _profile_id(url: object) -> str | None:
    if not isinstance(url, str):
        return None
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or parsed.hostname not in {
        "xiaohongshu.com", "www.xiaohongshu.com",
    }:
        return None
    parts = parsed.path.strip("/").split("/")
    return parts[2] if len(parts) == 3 and parts[:2] == ["user", "profile"] else None


def _resolve_source(connection: sqlite3.Connection, case: dict) -> tuple[dict, dict, dict]:
    key = case["key"]
    _require(key in PROFILE_IDENTITIES, f"未知示例 {key}")
    anchor = _text(case["anchor_note_id"], f"{key} anchor_note_id")
    matches = []
    for row in connection.execute("SELECT * FROM source_materials "
                                  "WHERE type='xhs_creator_profile'"):
        try:
            profile = json.loads(row["text_content"])
        except (TypeError, ValueError):
            continue
        if not isinstance(profile, dict) or not isinstance(profile.get("notes"), list):
            continue
        if any(isinstance(note, dict) and note.get("noteId") == anchor
               for note in profile["notes"]):
            matches.append((dict(row), profile))
    _require(len(matches) == 1, f"{key} 的锚点笔记缺失或出现在多个档案中，未导入")
    source, profile = matches[0]
    expected_id, expected_name = PROFILE_IDENTITIES[key]
    _require(profile.get("schemaVersion") == "xhs-creator-profile/v1",
             f"{key} 档案格式不支持")
    _require(_profile_id((profile.get("source") or {}).get("profileUrl")) == expected_id,
             f"{key} 平台账号身份不匹配，未导入")
    _require((profile.get("creator") or {}).get("displayName") == expected_name,
             f"{key} 材料创作者身份不一致，未导入")
    workspace = connection.execute("SELECT * FROM creator_workspaces WHERE id=?",
                                   (source["workspace_id"],)).fetchone()
    _require(workspace is not None, f"{key} 原档案不存在")
    return source, profile, dict(workspace)


def _record_ids(case: dict, source_id: str) -> dict[str, str]:
    return {kind: str(uuid5(NAMESPACE_URL, f"{BUNDLE_VERSION}:{source_id}:{case['key']}:{kind}"))
            for kind in TABLES}


def _build_case(connection: sqlite3.Connection, case: dict, now: str) -> dict:
    source, profile, workspace = _resolve_source(connection, case)
    key, workspace_id = case["key"], workspace["id"]
    note_ids = case["note_ids"]
    _require(isinstance(note_ids, list) and note_ids and len(set(note_ids)) == len(note_ids),
             f"{key} 笔记选择为空或重复")
    _require(case["anchor_note_id"] in note_ids, f"{key} 锚点不在选定材料中")
    notes = []
    for note_id in note_ids:
        matches = [note for note in profile["notes"]
                   if isinstance(note, dict) and note.get("noteId") == note_id]
        _require(len(matches) == 1, f"{key} 所需笔记 {note_id} 缺失或重复，未导入")
        _text(matches[0].get("desc"), f"{key} 笔记正文")
        notes.append(deepcopy(matches[0]))
    by_id = {note["noteId"]: note for note in notes}
    target_id = case["panel"]["target_note_id"]
    _require(target_id in by_id, f"{key} 模拟目标不属于本次材料")
    ids = _record_ids(case, source["id"])
    metadata = {"origin": ORIGIN, "provider": "handwritten_oracle", "modelCalled": False,
                "oracle": {"bundleVersion": BUNDLE_VERSION, "caseKey": key,
                           "label": "预写示例"}}
    scope = {"scope": "selected", "selectedNoteCount": len(notes),
             "availableNoteCount": len(profile["notes"]), "selectedNoteIds": note_ids}
    source_ref = {"inputAssetId": source["id"], "materialId": source["id"],
                  "name": source["name"], "updatedAt": source["updated_at"]}
    snapshot = {"origin": ORIGIN, "mode": "demo", "workspaceId": workspace_id,
                "workspaceName": workspace["name"], "analysisRange": scope,
                "accountPositioning": "预写示例：基于本次所选的已保存笔记。",
                "accountProfile": {**source_ref, "source": "xhs_creator_profile"},
                "xhsCreatorProfile": {**source_ref, "schemaVersion": profile["schemaVersion"],
                                      "creator": deepcopy(profile["creator"]), "notes": notes,
                                      "noteCount": len(notes)},
                "oracleShowcase": metadata["oracle"]}

    def evidence(item: dict) -> dict:
        note_id = item["noteId"]
        _require(note_id in by_id, f"{key} 画像依据不在本次材料中")
        note = by_id[note_id]
        quote = _text(item.get("quote"), f"{key} 画像明确引用")
        _require(len(quote) <= 240 and (quote in note["desc"]
                 or quote in str(note.get("title") or "")), f"{key} 画像引文与原文不符")
        return {"noteId": note_id, "quote": quote}

    raw_portrait = case["portrait"]
    portrait = {}
    for field in ("keywords", "strengths"):
        portrait[field] = [{"statement": _text(item["statement"], field),
                            "evidence": [evidence(item)]}
                           for item in raw_portrait[field]]
    summary_evidence = [claim["evidence"][0] for claim in portrait["strengths"]]
    _require(summary_evidence, f"{key} 画像总结需要明确的优势依据")
    portrait["summary"] = {"statement": _text(raw_portrait["summary"], "账号总结"),
                           "evidence": summary_evidence}
    verified = verified_portrait(portrait, snapshot)
    _require(verified and verified.get("summary")
             and all(len(verified.get(field, [])) == len(portrait[field])
                     for field in ("keywords", "strengths")), f"{key} 画像校验失败")
    observations = build_account_observations(snapshot, now)
    stage_results = {"profile": {"profile": {"accountPortrait": verified},
                                  "observations": observations}}
    audience_snapshot = {"origin": ORIGIN, "scope": scope,
                         "creator": deepcopy(profile["creator"]), "notes": notes}
    groups = []
    for reader in case["readers"]:
        ref = reader["evidence"]
        _require(ref["noteId"] in by_id, f"{key} 读者引文不在本次材料中")
        quote = _text(ref["quote"], "读者依据")
        note = by_id[ref["noteId"]]
        _require(quote in note["desc"] or quote in str(note.get("title") or ""),
                 f"{key} 读者引文与本次笔记原文不符")
        groups.append({**{field: reader[field] for field in
                          ("id", "name", "profile", "coreConcern", "interests",
                           "expressionStyle")},
                       "contentPreference": reader.get("contentPreference", ""),
                       "evidenceRefs": [{**ref, "sourceType": "note"}],
                       "unknowns": []})
    result, diagnostics = validate_audience_output({
        "summary": f"为 {profile['creator']['displayName']} 整理的 {len(groups)} 位候选读者。",
        "groups": groups, "limitations": "人物和发言是预写示例，不是实际粉丝调查。",
    }, audience_context(audience_snapshot))
    _require(result and not diagnostics["rejectedGroups"], f"{key} 候选读者依据校验失败")
    result.update(origin=ORIGIN, summary=f"{len(groups)} 位可供收录的示例读者。")
    readers = {group["id"]: group for group in result["groups"]}
    panel = case["panel"]
    participants = panel["participant_ids"]
    _require(participants and len(set(participants)) == len(participants)
             and set(participants).issubset(readers), f"{key} 参与者名单无效")
    _require(len(panel["reactions"]) == len(participants)
             and {item["readerId"] for item in panel["reactions"]} == set(participants),
             f"{key} 初始发言与参与者不一致")
    reactions = [{"personaId": item["readerId"], "messageId": f"initial:{item['readerId']}",
                  "action": "comment", "quote": _text(item["quote"], "读者发言"),
                  "understanding": _text(item["understanding"], "读者理解"),
                  "concerns": item["concerns"]} for item in panel["reactions"]]
    replies = []
    for index, item in enumerate(panel["replies"]):
        _require(item["readerId"] in participants and item["to"] in participants,
                 f"{key} 回应包含未参与的读者")
        replies.append({"personaId": item["readerId"],
                        "messageId": f"reply:{item['readerId']}:{index}",
                        "replyToId": f"initial:{item['to']}",
                        "response": _text(item["quote"], "读者回应")})
    _require(len(panel["answers"]) == len(participants)
             and {item["readerId"] for item in panel["answers"]} == set(participants),
             f"{key} 预写访谈回复与参与者不一致")
    personas = [{**readers[reader_id], "origin": ORIGIN, "evidenceStatus": "hypothesis",
                 "sourceAnalysisId": ids["audience"], "sourceGroupId": reader_id}
                for reader_id in participants]
    source_note = saved_note_target(connection, workspace_id, source["id"], target_id)
    simulation_snapshot = {
        "origin": ORIGIN, "mode": "demo", "workspaceId": workspace_id,
        "workspaceName": workspace["name"], "simulationCategory": "published_note",
        "targetType": "note", "sourceNote": source_note,
        "topic": {"title": source_note["title"], "body": source_note["body"],
                  "sourceWorkflow": "saved_note"},
        "audienceAnalysisId": ids["audience"], "audiencePersonas": personas,
        "readerSelection": {"source": ORIGIN, "proposedReaders": [],
                            "actualFanIds": participants},
        "panelTask": {"protocolVersion": "panel/v1", "readingMode": "natural",
                      "discussionEnabled": True, "focusQuestions": []},
        "oracleShowcase": metadata["oracle"],
        "oracleInterview": {"question": _text(panel["question"], "预写访谈问题"),
                            "answers": [{"personaId": item["readerId"],
                                         "quote": _text(item["quote"], "预写访谈回复")}
                                        for item in panel["answers"]]},
    }
    simulation_snapshot["targetContentHash"] = hashlib.sha256(
        _json(reader_visible_target(simulation_snapshot)).encode("utf-8")).hexdigest()
    outcome = panel["outcome"]
    ideas = outcome["topicIdeas"]
    _require(len({idea["id"] for idea in ideas}) == len(ideas), f"{key} 候选选题 ID 重复")
    review = {"summary": _text(outcome["summary"], "复盘总结"), "readerNeeds": [],
              "keepDoing": [], "nextTimeSuggestions": outcome["directions"],
              "topicIdeas": [{"id": _text(idea["id"], "选题 ID"),
                              "title": _text(idea["title"], "选题标题"),
                              "angle": _text(idea["angle"], "选题切口")}
                             for idea in ideas]}
    records = {
        "analysis": {"workflow_type": "account_diagnosis", "input_snapshot_json": _json(snapshot),
                     "stage_results_json": _json(stage_results), "stage_errors_json": "{}",
                     "idempotency_key": f"{BUNDLE_VERSION}:{key}:{source['id']}"},
        "audience": {"source_material_id": source["id"],
                     "input_snapshot_json": _json(audience_snapshot), "result_json": _json(result),
                     "model_output_json": "{}", "diagnostics_json": _json(diagnostics),
                     "error": ""},
        "simulation": {"topic_id": None, "draft_id": None,
                       "input_snapshot_json": _json(simulation_snapshot),
                       "persona_definitions_json": _json(personas),
                       "reaction_results_json": _json(reactions),
                       "debate_results_json": _json(replies),
                       "synthesis_json": _json({"origin": ORIGIN, "review": review}),
                       "stage_errors_json": "{}"},
    }
    existing = []
    for kind, record in records.items():
        record.update(id=ids[kind], workspace_id=workspace_id, status="completed",
                      model_metadata_json=_json(metadata), created_at=now, completed_at=now)
        if kind != "audience":
            record.update(started_at=now, updated_at=now)
        row = connection.execute(f"SELECT * FROM {TABLES[kind]} WHERE id=?",
                                 (ids[kind],)).fetchone()
        existing.append(row is not None)
        if row is not None:
            stored = json.loads(row["model_metadata_json"])
            _require(row["workspace_id"] == workspace_id and row["status"] == "completed"
                     and stored.get("origin") == ORIGIN
                     and stored.get("oracle") == metadata["oracle"],
                     f"{key} 固定记录 ID 已被其他内容使用，未导入")
    _require(not any(existing) or all(existing), f"{key} 已有示例记录不完整，未覆盖或补写")
    return {"key": key, "workspaceId": workspace_id, "workspaceName": workspace["name"],
            "sourceMaterialId": source["id"], "noteCount": len(notes),
            "targetTitle": source_note["title"], "recordIds": ids,
            "alreadyInstalled": all(existing), "records": records}


def _prepare(connection: sqlite3.Connection, cases: list[dict]) -> list[dict]:
    _require(cases and len({case["key"] for case in cases}) == len(cases),
             "示例为空或 case key 重复")
    plans = [_build_case(connection, case, utc_now()) for case in cases]
    _require(len({plan["workspaceId"] for plan in plans}) == len(plans),
             "不同示例不能绑定同一账号档案")
    return plans


def _report(plans: list[dict], apply: bool) -> dict:
    count = sum(not plan["alreadyInstalled"] for plan in plans) * len(TABLES)
    return {"mode": "applied" if apply else "dry_run", "origin": ORIGIN,
            "bundleVersion": BUNDLE_VERSION, "newRecords": count,
            "cases": [{key: value for key, value in plan.items() if key != "records"}
                      for plan in plans]}


def seed_workspace_showcases(database: SQLiteDatabase, cases: list[dict], *, apply=False) -> dict:
    """Dry-run is read-only. Apply revalidates the entire bundle inside one transaction."""
    path = Path(database.path).resolve()
    _require(path.is_file(), "数据库不存在；不会新建数据库或档案")
    if not apply:
        connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
        connection.row_factory = sqlite3.Row
        try:
            return _report(_prepare(connection, cases), False)
        finally:
            connection.close()
    with database.transaction() as connection:
        plans = _prepare(connection, cases)
        for plan in plans:
            if plan["alreadyInstalled"]:
                continue
            for kind, record in plan["records"].items():
                fields = list(record)
                connection.execute(
                    f"INSERT INTO {TABLES[kind]} ({','.join(fields)}) "
                    f"VALUES ({','.join('?' for _ in fields)})",
                    tuple(record[field] for field in fields),
                )
        return _report(plans, True)
