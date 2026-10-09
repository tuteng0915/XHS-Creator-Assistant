"""Explicit maintenance of the original handwritten examples, never ordinary histories.

Callers must create a verified database backup before applying a prepared plan.
The plan carries full-row fingerprints; it contains no source text or new payload.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from copy import deepcopy
from pathlib import Path

from app.db.database import SQLiteDatabase
from app.services.common import utc_now
from app.services.workspace_showcases import ORIGIN, TABLES, _json, _prepare, _require

CONTENT_REVISION = "polish-1"


def _hash(value: object) -> str:
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


def _decode(row: dict, field: str):
    return json.loads(row[field])


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def _references(connection: sqlite3.Connection, records: dict[str, dict]) -> list[dict]:
    # JSON references are deliberately included: not every product relation is a FK.
    # This bounded offline maintenance check scans the existing local product tables.
    references = []
    record_ids = {record_id for rows in records.values() for record_id in rows}
    tables = connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()
    for table in tables:
        name = table["name"]
        for row in connection.execute(f"SELECT * FROM {_identifier(name)}"):
            value = dict(row)
            if value.get("id") in records.get(name, {}):
                continue
            fields = [key for key, item in value.items() if isinstance(item, str)
                      and any(record_id in item for record_id in record_ids)]
            if fields:
                references.append({"table": name, "id": str(value.get("id", "")),
                                   "fields": sorted(fields)})
    return sorted(references, key=lambda item: (item["table"], item["id"], item["fields"]))


def _same(value: object, expected: object, message: str) -> None:
    _require(value == expected, message)


def _portrait_evidence(portrait: dict) -> dict:
    return {"summary": (portrait.get("summary") or {}).get("evidence"),
            **{key: [claim.get("evidence") for claim in portrait.get(key, [])]
               for key in ("keywords", "strengths")}}


def _payload(kind: str, old: dict, generated: dict) -> dict[str, str]:
    """Only prose can change; source snapshots and all downstream identities are frozen."""
    before = _decode(old, "input_snapshot_json")
    after = _decode(generated, "input_snapshot_json")
    if kind == "analysis":
        _same(before, after, "账号分析输入已变化，不能润色旧示例")
        stages = _decode(old, "stage_results_json")
        incoming = _decode(generated, "stage_results_json")
        old_portrait = stages["profile"]["profile"]["accountPortrait"]
        new_portrait = incoming["profile"]["profile"]["accountPortrait"]
        _same(_portrait_evidence(old_portrait), _portrait_evidence(new_portrait),
              "画像原文引用不可在润色时改变")
        stages["profile"]["profile"]["accountPortrait"] = new_portrait
        return {"stage_results_json": _json(stages)}
    if kind == "audience":
        _same(before, after, "受众分析输入已变化，不能润色旧示例")
        previous = _decode(old, "result_json")["groups"]
        current = _decode(generated, "result_json")["groups"]
        _same([(group["id"], group.get("evidenceRefs")) for group in previous],
              [(group["id"], group.get("evidenceRefs")) for group in current],
              "读者身份或原文引用不可在润色时改变")
        return {field: generated[field] for field in ("result_json", "diagnostics_json")}

    for snapshot in (before, after):
        snapshot.pop("audiencePersonas", None)
        snapshot.pop("oracleInterview", None)
    _same(before, after, "模拟原文、来源或参与名单已变化，不能润色旧示例")
    previous_personas = _decode(old, "persona_definitions_json")
    current_personas = _decode(generated, "persona_definitions_json")
    identity_fields = ("id", "sourceAnalysisId", "sourceGroupId", "evidenceRefs")
    _same([[persona.get(field) for field in identity_fields] for persona in previous_personas],
          [[persona.get(field) for field in identity_fields] for persona in current_personas],
          "模拟人物身份或原文引用不可在润色时改变")
    for field, keys in (
        ("reaction_results_json", ("personaId", "messageId", "action")),
        ("debate_results_json", ("personaId", "messageId", "replyToId")),
    ):
        _same([[message.get(key) for key in keys] for message in _decode(old, field)],
              [[message.get(key) for key in keys] for message in _decode(generated, field)],
              "发言身份或回应关系不可在润色时改变")
    old_ideas = _decode(old, "synthesis_json")["review"]["topicIdeas"]
    new_ideas = _decode(generated, "synthesis_json")["review"]["topicIdeas"]
    _same([idea["id"] for idea in old_ideas], [idea["id"] for idea in new_ideas],
          "候选选题身份不可在润色时改变")
    snapshot = _decode(old, "input_snapshot_json")
    incoming = _decode(generated, "input_snapshot_json")
    _same([answer["personaId"] for answer in snapshot["oracleInterview"]["answers"]],
          [answer["personaId"] for answer in incoming["oracleInterview"]["answers"]],
          "预写访谈的回答者不可在润色时改变")
    for key in ("audiencePersonas", "oracleInterview"):
        snapshot[key] = incoming[key]
    return {"input_snapshot_json": _json(snapshot),
            **{field: generated[field] for field in (
                "persona_definitions_json", "reaction_results_json", "debate_results_json",
                "synthesis_json",
            )}}


def _plan(connection: sqlite3.Connection, cases: list[dict]) -> tuple[dict, list[dict]]:
    prepared = _prepare(connection, cases)
    _require(len(prepared) == 4 and all(plan["alreadyInstalled"] for plan in prepared),
             "只允许润色四份档案内已存在的完整十二条示例")
    expected_records, expected_sources, expected_workspaces = {}, {}, {}
    updates = []
    for case in prepared:
        for kind, generated in case["records"].items():
            table, record_id = TABLES[kind], generated["id"]
            old = dict(connection.execute(f"SELECT * FROM {table} WHERE id=?",
                                          (record_id,)).fetchone())
            metadata = _decode(old, "model_metadata_json")
            _require(metadata.get("origin") == ORIGIN
                     and metadata.get("provider") == "handwritten_oracle"
                     and metadata.get("modelCalled") is False,
                     "只能润色未经模型调用的预写示例")
            _require(not old.get("user_notes")
                     and old.get("review_status", "unreviewed") == "unreviewed",
                     "示例已有人工备注或复盘状态，未修改")
            payload = _payload(kind, old, generated)
            expected_records.setdefault(table, {})[record_id] = _hash(old)
            # JSON serialization alone is not a content change.
            changed = any(_decode(old, field) != json.loads(value)
                          for field, value in payload.items())
            if changed:
                updates.append({"table": table, "id": record_id, "old": old,
                                "payload": payload})
        for table, row_id, target in (
            ("source_materials", case["sourceMaterialId"], expected_sources),
            ("creator_workspaces", case["workspaceId"], expected_workspaces),
        ):
            row = connection.execute(f"SELECT * FROM {table} WHERE id=?", (row_id,)).fetchone()
            target[row_id] = _hash(dict(row))
    references = _references(connection, expected_records)
    _require(not references, "示例已被其他产品记录引用，不能原位润色")
    return {"contentRevision": CONTENT_REVISION, "contentHash": _hash(cases),
            "expectedRecords": expected_records, "expectedSources": expected_sources,
            "expectedWorkspaces": expected_workspaces, "expectedReferences": references,
            "changedRecords": len(updates)}, updates


def prepare_workspace_showcase_refresh(database: SQLiteDatabase, cases: list[dict]) -> dict:
    """Read-only plan; changing content, original rows or references invalidates it."""
    path = Path(database.path).resolve()
    _require(path.is_file(), "数据库不存在；不会新建数据库或档案")
    connection = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        plan, _ = _plan(connection, cases)
        return plan
    finally:
        connection.close()


def refresh_workspace_showcases(database: SQLiteDatabase, cases: list[dict], plan: dict) -> dict:
    """Apply after the caller's backup; stale plans abort the entire transaction."""
    _require(Path(database.path).is_file(), "数据库不存在；不会新建数据库或档案")
    with database.transaction() as connection:
        current, updates = _plan(connection, cases)
        _same(current, plan, "示例、材料或内容自检查后发生变化，未修改")
        now = utc_now()
        for update in updates:
            payload = deepcopy(update["payload"])
            old = update["old"]
            metadata = _decode(old, "model_metadata_json")
            metadata.update(contentRevision=CONTENT_REVISION,
                            contentHash=current["contentHash"], refreshedAt=now)
            payload["model_metadata_json"] = _json(metadata)
            if "updated_at" in old:
                payload["updated_at"] = now
            fields = list(payload)
            connection.execute(
                f"UPDATE {update['table']} SET " + ",".join(f"{field}=?" for field in fields)
                + " WHERE id=?",
                (*[payload[field] for field in fields], update["id"]),
            )
        return {"origin": ORIGIN, "contentRevision": CONTENT_REVISION,
                "contentHash": current["contentHash"], "updatedRecords": len(updates),
                "newRecords": 0}
