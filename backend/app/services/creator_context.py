"""Exact, bounded references explicitly selected by the creator.

Never build a workspace overview here. The selected completed result is the
whole readable boundary; its original notes, comments and related runs stay out.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from app.errors import NotFoundError, ValidationError
from app.models import CreatorContextSelection

MAX_CREATOR_REFERENCE_CHARS = 48_000


def canonical_selection(selection: CreatorContextSelection) -> dict[str, Any]:
    references = sorted({(item.kind, item.id) for item in selection.references})
    return {
        "schemaVersion": "creator-context-selection/v1",
        "references": [{"kind": kind, "id": item_id} for kind, item_id in references],
    }


def resolve_creator_context(connection, *, workspace_id: str, selection: dict) -> dict:
    frozen: list[dict[str, Any]] = []
    for reference in selection["references"]:
        kind, item_id = reference["kind"], reference["id"]
        if kind == "account_analysis":
            row = connection.execute(
                "SELECT id,status,workflow_type,stage_results_json,input_snapshot_json,"
                "model_metadata_json,"
                "created_at,completed_at "
                "FROM analysis_runs WHERE id=? AND workspace_id=?",
                (item_id, workspace_id),
            ).fetchone()
        else:
            row = connection.execute(
                "SELECT id,status,result_json,input_snapshot_json,model_metadata_json,"
                "created_at,completed_at "
                "FROM audience_analyses WHERE id=? AND workspace_id=?",
                (item_id, workspace_id),
            ).fetchone()
        if row is None:
            raise NotFoundError("所选参考记录不存在，请重新选择")
        if row["status"] != "completed":
            raise ValidationError("请选择已完整完成的分析记录作为参考")
        if kind == "account_analysis" and row["workflow_type"] != "account_diagnosis":
            raise ValidationError("所选记录不是账号分析")
        try:
            result = json.loads(
                row["stage_results_json"] if kind == "account_analysis" else row["result_json"]
            )
        except (ValueError, TypeError) as error:
            raise ValidationError("所选分析结果无法读取，请换一份参考") from error
        if not isinstance(result, dict) or not result:
            raise ValidationError("所选分析记录没有可用结果")
        if kind == "account_analysis":
            # Account diagnosis outputs, not suggested topics/drafts or raw inputs.
            result = {key: result[key] for key in ("profile", "pain_points") if key in result}
            if not result:
                raise ValidationError("所选账号分析没有可用的账号认识或读者需求")
        # Only range metadata is read from this exact record's frozen input.
        # Do not forward the input snapshot, its context pack or raw materials.
        try:
            original = json.loads(row["input_snapshot_json"])
        except (ValueError, TypeError) as error:
            raise ValidationError("所选分析的范围记录无法读取，请换一份参考") from error
        if not isinstance(original, dict):
            raise ValidationError("所选分析的范围记录无法读取，请换一份参考")
        try:
            metadata = json.loads(row["model_metadata_json"])
        except (ValueError, TypeError):
            metadata = {}
        if not isinstance(metadata, dict):
            metadata = {}
        # Preserve provenance, not provider receipts or raw input. In particular,
        # authored showcases must not masquerade as live analysis evidence.
        source_origin = next(
            (
                value
                for value in (
                    original.get("origin"),
                    metadata.get("origin"),
                    result.get("origin"),
                )
                if isinstance(value, str) and value.strip() and len(value) <= 120
            ),
            None,
        )
        if source_origin is None:
            source_origin = (
                "demo"
                if original.get("mode") == "demo"
                else "model_analysis"
                if metadata.get("provider")
                in {
                    "qwen",
                    "dashscope",
                    "anthropic",
                }
                else "unknown"
            )
        raw_scope = original.get("analysisRange" if kind == "account_analysis" else "scope", {})
        scope = (
            {
                key: raw_scope[key]
                for key in (
                    "scope",
                    "asOf",
                    "since",
                    "availableNoteCount",
                    "selectedNoteIds",
                    "selectedNoteCount",
                )
                if key in raw_scope
            }
            if isinstance(raw_scope, dict)
            else {}
        )
        text = json.dumps(
            {"content": result, "scope": scope, "sourceOrigin": source_origin},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        frozen.append(
            {
                **reference,
                "sourceVersion": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                "createdAt": row["created_at"],
                "completedAt": row["completed_at"],
                "content": result,
                "scope": scope,
                "sourceOrigin": source_origin,
            }
        )
    if len(json.dumps(frozen, ensure_ascii=False)) > MAX_CREATOR_REFERENCE_CHARS:
        raise ValidationError("参考材料过多，请减少所选记录后发送（最多 48000 字符）")
    return {"schemaVersion": "creator-context-snapshot/v1", "references": frozen}
