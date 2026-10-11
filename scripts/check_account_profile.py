"""Preview saved notes or check the profile stage with one Qwen call.

Optionally read saved workspace notes through read-only SQLite; no database writes,
crawling, topic generation or retries. Reports include private source text; keep
them under ignored data/evals. Default mode does not call any model.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from account_profile_diagnostics import DiagnosticProfileCalls  # noqa: E402
from xhs_mediacrawler_fixture import (  # noqa: E402
    build_xhs_creator_profile_payload,
    load_mediacrawler_export,
)

from app.config import Settings  # noqa: E402
from app.errors import ValidationError  # noqa: E402
from app.models import ModelOperation  # noqa: E402
from app.services.account_diagnosis_evidence import (  # noqa: E402
    profile_stage_input,
    verified_portrait,
)
from app.services.account_report_delivery import compile_usable_account_report  # noqa: E402
from app.services.account_report_prompt import profile_prompt_version  # noqa: E402
from app.services.analysis_runs import AnalysisRunService  # noqa: E402
from app.services.creator_analysis_scope import ordered_notes, scope_creator_profile  # noqa: E402
from app.services.model_calls import PROFILE_PROMPT_VERSION as PROFILE_PROMPT_VERSION  # noqa: E402
from app.services.xhs_imports import XhsOfflineImportService  # noqa: E402
from app.workflows.account_diagnosis import ProfileStageResult  # noqa: E402


def prepare_case(source: Path) -> dict:
    exported = build_xhs_creator_profile_payload(load_mediacrawler_export(source, code="check"))
    parsed = XhsOfflineImportService(None)._parse_creator_profile_export(exported)
    scoped, scope = scope_creator_profile(parsed, "recent_10")
    return _prepare_scoped_case(scoped, scope)


def _prepare_scoped_case(scoped: dict, scope: dict) -> dict:
    # Only pure derivation helpers are used. No repository/database is constructed.
    service = AnalysisRunService(None, None, None, None, None, None, None, None)
    snapshot = {
        "accountPositioning": service._derive_xhs_account_positioning(scoped),
        "historicalPosts": {"content": service._derive_xhs_historical_posts_text(scoped)},
        "xhsCreatorProfile": scoped,
        "analysisRange": scope,
    }
    context, observations = profile_stage_input(snapshot, scope["asOf"])
    return {"snapshot": snapshot, "context": context, "observations": observations}


def prepare_workspace_case(
    database: Path, workspace_id: str, *, limit: int = 5, note_ids: list[str] | None = None,
) -> dict:
    """Freeze an exact saved subset; never bootstrap/migrate the product database."""
    if not isinstance(workspace_id, str) or not workspace_id.strip():
        raise ValueError("账号档案标识不能为空")
    if type(limit) is not int or not 1 <= limit <= 50:
        raise ValueError("笔记数量必须为 1～50")
    if note_ids is not None and (
        not note_ids or len(note_ids) > 50 or len(set(note_ids)) != len(note_ids)
        or any(not isinstance(item, str) or not item.strip() or item != item.strip()
               for item in note_ids)
    ):
        raise ValueError("笔记标识必须为 1～50 个不同的非空标识")
    connection = sqlite3.connect(database.resolve(strict=True).as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        workspace = connection.execute(
            "SELECT id FROM creator_workspaces WHERE id=?", (workspace_id,),
        ).fetchone()
        if workspace is None:
            raise ValueError("账号档案不存在")
        row = connection.execute(
            "SELECT id,text_content FROM source_materials "
            "WHERE workspace_id=? AND type='xhs_creator_profile' "
            "ORDER BY updated_at DESC,id LIMIT 1", (workspace_id,),
        ).fetchone()
        if row is None:
            raise ValueError("当前账号没有已保存笔记资料")
        profile = json.loads(row["text_content"])
        if not isinstance(profile, dict) or not isinstance(profile.get("notes"), list):
            raise ValueError("账号笔记资料格式无效")
        notes = [item for item in profile["notes"] if isinstance(item, dict)]
        selected = note_ids if note_ids is not None else [
            item.get("noteId") for item in ordered_notes(notes)[:limit]
        ]
        available = [item.get("noteId") for item in notes]
        # Do not inherit the legacy scope helper's positional fallback IDs.
        if (not selected or any(not isinstance(item, str) or not item.strip()
                                or item != item.strip() for item in selected)
                or len(set(selected)) != len(selected)
                or any(available.count(item) != 1 for item in selected)):
            raise ValueError("所选笔记不在当前资料中或标识不唯一")
        scoped, scope = scope_creator_profile(profile, "custom", selected_note_ids=selected)
        by_id = {item["noteId"]: item for item in scoped["notes"]}
        scoped["notes"] = [by_id[item] for item in selected]
        scope["selectedNoteIds"] = list(selected)
        scope["selectionMethod"] = "explicit_ids" if note_ids is not None else "recent_limit"
        if note_ids is None:
            scope["requestedLimit"] = limit
        case = _prepare_scoped_case(scoped, scope)
        case["inputSource"] = {
            "type": "saved_workspace_notes", "workspaceId": workspace_id,
            "sourceMaterialId": row["id"], "selectedNoteIds": scope["selectedNoteIds"],
        }
        return case
    finally:
        connection.close()


def prepare_analysis_run_case(database: Path, run_id: str) -> dict:
    """Use one historical input snapshot with today's profile prompt/input shape."""
    if not isinstance(run_id, str) or not run_id.strip():
        raise ValueError("分析记录标识不能为空")
    connection = sqlite3.connect(database.resolve(strict=True).as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        row = connection.execute(
            "SELECT id,workspace_id,workflow_type,input_snapshot_json,created_at "
            "FROM analysis_runs WHERE id=?", (run_id,),
        ).fetchone()
        if row is None or row["workflow_type"] != "account_diagnosis":
            raise ValueError("账号分析记录不存在或类型不符")
        snapshot = json.loads(row["input_snapshot_json"])
        profile = snapshot.get("xhsCreatorProfile") if isinstance(snapshot, dict) else None
        notes = profile.get("notes") if isinstance(profile, dict) else None
        if (not isinstance(notes, list) or not notes
                or any(not isinstance(note, dict) for note in notes)):
            raise ValueError("历史输入没有可用的结构化笔记快照")
        if not any(isinstance(note.get(key), str) and note[key].strip()
                   for note in notes for key in ("title", "desc")):
            raise ValueError("历史笔记快照没有已保存的标题或正文")
        selected = [note.get("noteId") for note in notes]
        if (any(not isinstance(item, str) or not item.strip() or item != item.strip()
                for item in selected) or len(set(selected)) != len(selected)):
            raise ValueError("历史笔记标识缺失或不唯一")
        scope = snapshot.get("analysisRange")
        if isinstance(scope, dict):
            recorded_ids = scope.get("selectedNoteIds")
            if recorded_ids is not None and (
                not isinstance(recorded_ids, list)
                or any(not isinstance(item, str) for item in recorded_ids)
                or len(recorded_ids) != len(selected) or set(recorded_ids) != set(selected)
            ):
                raise ValueError("历史范围与冻结笔记不一致")
            if ("selectedNoteCount" in scope and scope["selectedNoteCount"] != len(selected)):
                raise ValueError("历史范围与冻结笔记数量不一致")
        context, observations = profile_stage_input(snapshot, row["created_at"])
        return {
            "snapshot": snapshot, "context": context, "observations": observations,
            "inputSource": {
                "type": "analysis_run_snapshot", "runId": row["id"],
                "workspaceId": row["workspace_id"], "selectedNoteIds": selected,
            },
        }
    finally:
        connection.close()


def claim_counts(portrait) -> dict:
    portrait = portrait if isinstance(portrait, dict) else {}
    result = {key: int(isinstance(portrait.get(key), dict))
              for key in ("summary", "encouragement", "recentChange")}
    for key in ("keywords", "strengths", "recurringThemes", "readerValue", "expressionPatterns"):
        values = portrait.get(key)
        result[key] = len(values) if isinstance(values, list) else 0
    if "nextSteps" in portrait:
        result["nextSteps"] = (len(portrait["nextSteps"])
                               if isinstance(portrait["nextSteps"], list) else 0)
    return result


def case_from_report(path: Path) -> dict:
    """Replay the actual frozen model input, not today's changed source material."""
    previous = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(previous, dict):
        raise ValueError("检查报告必须是对象")
    case = {key: previous.get(key) for key in ("snapshot", "context", "observations")}
    if not all(isinstance(value, dict) for value in case.values()):
        raise ValueError("检查报告缺少 snapshot、context 或 observations")
    if not all(isinstance(case["context"].get(key), str) and case["context"][key].strip()
               for key in ("positioning", "historicalPosts")):
        raise ValueError("检查报告缺少完整画像输入")
    profile = case["snapshot"].get("xhsCreatorProfile")
    if not isinstance(profile, dict) or not isinstance(profile.get("notes"), list):
        raise ValueError("检查报告缺少笔记快照")
    return case


async def run_check(service, case: dict) -> dict:
    report = {"status": "failed", "requestAttempts": 1, **case,
              "semanticStatus": "not_reviewed", "manualChecks": [
                  "解释力：是否认出跨篇的观察、判断或表达特点，而非仅列题材；允许例外和不同表现，不要求每篇同一结构？",
                  "事实落点：代表作中的人物、经历、措辞和顺序是否准确；积极的编辑评价不能变成补造事实或已验证的传播效果？",
                  "创作回报：是否指出值得延续的本领与可用的下一步，而非拔高使命、挑不存在的缺点或强套模板？",
              ]}
    phase = "model_call"
    started = time.monotonic()
    try:
        response = await service.call_operation(ModelOperation.PROFILE, case["context"])
        report.update(output=response.output, modelMetadata=response.model_metadata)
        phase = "validation"
        omissions: list[str] = []
        prepared = compile_usable_account_report(
            response.output, case["snapshot"], omissions=omissions,
        )
        report["omittedReportItems"] = omissions
        result = ProfileStageResult.model_validate(prepared).model_dump(mode="json")
        raw = result["profile"].get("accountPortrait")
        observations = case["observations"]
        kept = verified_portrait(raw, case["snapshot"], (observations or {}).get("chronology"))
        result["profile"]["accountPortrait"] = kept
        if observations is not None:
            result["observations"] = observations
        report.update(status="completed", result=result, portraitVerification={
            "rawClaimCounts": claim_counts(raw), "keptClaimCounts": claim_counts(kept),
            "hasVerifiedPortrait": kept is not None,
            "scope": "source_identity_and_literal_quotes_not_semantic_entailment",
        })
    except Exception as error:
        report["error"] = {"phase": phase, "type": type(error).__name__}
    report["elapsedSeconds"] = round(time.monotonic() - started, 2)
    if isinstance(service, DiagnosticProfileCalls):
        report["requestAttempts"] = service.request_attempts
        report["responseDiagnostic"] = service.diagnostic.copy()
        # Also cover a credential echoed inside otherwise valid structured output.
        report = service.redact(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, help="已保存的 MediaCrawler 原始数据目录")
    parser.add_argument("--input-from", type=Path, help="复用已有画像检查报告的完整冻结输入")
    parser.add_argument("--workspace-id", help="只读检查当前账号档案已保存的笔记")
    parser.add_argument("--analysis-run-id",
                        help="只读历史账号分析的冻结笔记，用当前画像输入重新检查")
    parser.add_argument("--database", type=Path,
                        help="账号或历史分析模式使用；默认读取配置路径")
    parser.add_argument("--note-ids", help="与 --workspace-id 一起使用；逗号分隔的精确笔记 ID")
    parser.add_argument("--limit", type=int, help="账号模式下选择最近 N 篇，默认 5，范围 1～50")
    parser.add_argument("--live", action="store_true", help="运行一次 Qwen 画像检查，不重试")
    parser.add_argument("--output", type=Path, help="新的报告目录，拒绝覆盖")
    parser.add_argument("--read-timeout-seconds", type=int, default=90,
                        help="仅本次检查的读取等待上限，1～300 秒；默认 90，不改变生产设置")
    args = parser.parse_args()
    if not 1 <= args.read_timeout_seconds <= 300:
        parser.error("--read-timeout-seconds 必须为 1～300 的整数")
    if args.live and args.output is None:
        parser.error("--live 必须指定新的 --output 目录")
    if sum(value is not None for value in (
        args.source, args.input_from, args.workspace_id, args.analysis_run_id,
    )) != 1:
        parser.error("提供原始数据目录、--input-from、--workspace-id 或 --analysis-run-id，四选一")
    database_input = args.workspace_id is not None or args.analysis_run_id is not None
    if not database_input and args.database is not None:
        parser.error("--database 仅用于 --workspace-id 或 --analysis-run-id")
    if args.workspace_id is None and any(
        value is not None for value in (args.note_ids, args.limit)
    ):
        parser.error("--note-ids 和 --limit 仅用于 --workspace-id，不改变历史冻结范围")
    if args.limit is not None and not 1 <= args.limit <= 50:
        parser.error("--limit 必须为 1～50 的整数")
    if args.limit is not None and args.note_ids is not None:
        parser.error("--note-ids 已指定精确笔记，不与 --limit 同时使用")
    if database_input and args.live and not args.output.resolve().is_relative_to(
        (ROOT / "data/evals").resolve(),
    ):
        parser.error("账号笔记报告请保存到仓库 data/evals 下的新目录")
    try:
        if args.analysis_run_id is not None:
            database = args.database or Settings.from_environment().database_path
            case = prepare_analysis_run_case(database, args.analysis_run_id)
        elif args.workspace_id is not None:
            database = args.database or Settings.from_environment().database_path
            ids = ([item.strip() for item in args.note_ids.split(",")]
                   if args.note_ids is not None else None)
            case = prepare_workspace_case(
                database, args.workspace_id, limit=args.limit or 5, note_ids=ids,
            )
        else:
            case = (case_from_report(args.input_from)
                    if args.input_from else prepare_case(args.source))
    except (OSError, ValueError, sqlite3.Error, ValidationError) as error:
        parser.error(f"输入预检失败：{type(error).__name__}")
    if not args.live:
        print(json.dumps({
            "mode": "preview", "requestAttempts": 0,
            "coverage": case["observations"].get("coverage"),
            "chronology": case["observations"].get("chronology"),
            **({"selection": case["inputSource"]} if database_input else {}),
        }, ensure_ascii=False))
        return 0
    settings = replace(Settings.from_environment(), model_provider="qwen")
    if not settings.qwen_api_key:
        parser.error("未配置 Qwen 密钥")
    args.output.mkdir(parents=True, exist_ok=False)
    service = DiagnosticProfileCalls(settings, read_timeout_seconds=args.read_timeout_seconds)
    system, user = service._build_prompt(ModelOperation.PROFILE, case["context"])
    report = asyncio.run(run_check(service, case))
    report.update(provider="qwen", configuredModel=service.qwen_model_for(ModelOperation.PROFILE),
                  promptVersion=profile_prompt_version(case["context"]),
                  promptHash=hashlib.sha256(system.encode()).hexdigest(),
                  inputHash=hashlib.sha256(user.encode()).hexdigest())
    if args.input_from:
        report["inputSource"] = {"type": "previous_profile_report",
                                 "sha256": hashlib.sha256(args.input_from.read_bytes()).hexdigest()}
    report = service.redact(report)
    destination = args.output / "report.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(destination), "status": report["status"],
                      "requestAttempts": report["requestAttempts"],
                      "semanticStatus": "not_reviewed"}, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
