"""Preview or explicitly evaluate the staged account report on frozen inputs.

The default preview makes no model calls and writes no files. Live diagnostics
contain private source text; save them only to an appropriate private eval folder.
No database access, source refresh, or provider fallback is performed. Output
recovery uses the same bounded stage-local policy as the product.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from account_profile_diagnostics import DiagnosticProfileCalls, safe_usage  # noqa: E402
from check_account_profile import case_from_report, claim_counts  # noqa: E402

from app.config import Settings  # noqa: E402
from app.services.account_diagnosis_evidence import verified_portrait  # noqa: E402
from app.services.account_report_contract import AccountReportOutputError  # noqa: E402
from app.services.account_report_delivery import compile_usable_account_report  # noqa: E402
from app.services.account_report_pipeline import (  # noqa: E402
    MAX_EXTRA_REQUESTS,
    PIPELINE_VERSION,
    _material,
    run_staged_account_report,
)
from app.services.account_report_prompt import READING_OBSERVATIONS_MARKER  # noqa: E402
from app.workflows.account_diagnosis import ProfileStageResult  # noqa: E402


def preview_scope(case: dict, read_note_ids: list[str] | None = None) -> dict:
    _, notes = _material(case["context"])
    available = {item["noteId"] for item in notes}
    if read_note_ids is not None and (
        not 1 <= len(read_note_ids) <= 3
        or any(not isinstance(item, str) or item not in available for item in read_note_ids)
        or len(set(read_note_ids)) != len(read_note_ids)
    ):
        raise ValueError("--read-note-ids 必须是冻结输入中1～3个不同的 n 编号")
    normal_requests = 2 + (
        len(read_note_ids) if read_note_ids is not None else min(3, len(notes))
    )
    return {
        "inputNoteCount": len(notes),
        "inputBodyCharacters": sum(len(item["body"]) for item in notes),
        "readSelection": "explicit" if read_note_ids is not None else "overview_selected",
        "readNoteIds": list(read_note_ids) if read_note_ids is not None else None,
        "readNoteCount": len(read_note_ids) if read_note_ids is not None else None,
        "maxReadNoteCount": len(read_note_ids) if read_note_ids is not None else min(3, len(notes)),
        "normalModelRequests": normal_requests,
        "maxRecoveryRequests": MAX_EXTRA_REQUESTS,
        "maxModelRequests": normal_requests + MAX_EXTRA_REQUESTS,
    }


def _input_scope(stage: str, payload: dict) -> dict:
    if stage == "read":
        note = payload["note"]
        return {"kind": "single_note", "noteCount": 1, "title": note["title"],
                "bodyCharacters": sum(len(item["text"]) for item in note["bodyExcerpts"])}
    return {
        "kind": "all_source_notes" if stage == "overview" else "all_source_notes_and_readings",
        "noteCount": len(payload["notes"]),
        "noteIds": [item["noteId"] for item in payload["notes"]],
        **({"readingCount": len(payload["readings"]), "bodyCharacters": sum(
            len(fragment["text"]) for note in payload["notes"]
            for fragment in note["bodyExcerpts"]
        )} if stage == "synthesis" else {}),
    }


def stage_input(stage: str, user: str) -> dict:
    """Capture the default report prompt without changing the actual request."""
    if stage != "synthesis":
        return json.loads(user)
    _, marker, tail = user.partition("\n\n历史笔记：\n")
    if not marker:
        # Read older JSON-shaped diagnostic inputs without rewriting them.
        return json.loads(user)
    packet, _ = json.JSONDecoder().raw_decode(tail)
    _, observations_marker, observations = user.partition(READING_OBSERVATIONS_MARKER)
    return {**packet, "readings": json.loads(observations) if observations_marker else []}


def validate_product_result(
    output: dict, snapshot: dict, observations: dict | None,
) -> tuple[dict, dict]:
    """Apply the product's final checks offline without changing compiled output."""
    prepared = compile_usable_account_report(output, snapshot)
    validated = ProfileStageResult.model_validate(prepared).model_dump(mode="json")
    raw = validated["profile"].get("accountPortrait")
    kept = verified_portrait(raw, snapshot, (observations or {}).get("chronology"))
    validated["profile"]["accountPortrait"] = kept
    if observations is not None:
        validated["observations"] = deepcopy(observations)
    raw_counts, kept_counts = claim_counts(raw), claim_counts(kept)
    verification = {
        "rawClaimCounts": raw_counts,
        "keptClaimCounts": kept_counts,
        "droppedClaimCounts": {
            key: count - kept_counts.get(key, 0) for key, count in raw_counts.items()
            if count > kept_counts.get(key, 0)
        },
        "hasVerifiedPortrait": kept is not None,
        "scope": "source_identity_and_literal_quotes_not_semantic_entailment",
    }
    return validated, verification


async def run_check(service_factory, case: dict, *, read_note_ids=None, on_progress=None) -> dict:
    """Capture one fresh diagnostic service per call; injectable for offline tests."""
    started = time.monotonic()
    frozen = deepcopy(case)
    report = {
        **frozen, "status": "failed", "semanticStatus": "not_reviewed",
        "promptVersion": PIPELINE_VERSION, "requestAttempts": 0,
        "stages": [], "progress": [],
    }
    services = []

    async def progress(update):
        event = {key: update[key] for key in ("phase", "status", "completed", "total")}
        if isinstance(update.get("recovery"), dict):
            event["recovery"] = deepcopy(update["recovery"])
        event["elapsedSeconds"] = round(time.monotonic() - started, 3)
        report["progress"].append(event)
        if on_progress is not None:
            on_progress(deepcopy(event))

    async def call_step(stage, system, user):
        payload = stage_input(stage, user)
        capture = {
            "sequence": len(report["stages"]) + 1, "stage": stage, "status": "failed",
            "input": payload, "inputScope": _input_scope(stage, payload),
            "userPrompt": user,
            "systemPromptHash": hashlib.sha256(system.encode("utf-8")).hexdigest(),
            "inputHash": hashlib.sha256(user.encode("utf-8")).hexdigest(),
        }
        if stage == "read":
            capture["taskTitle"] = payload["note"]["title"]
        # Append before awaiting: parallel readers keep invocation/task order.
        report["stages"].append(capture)
        call_started = time.monotonic()
        service = None
        try:
            service = service_factory()
            services.append(service)
            response = await service.call_account_report_step(stage, system, user)
            capture.update(status="completed", output=deepcopy(response.output),
                           modelMetadata=deepcopy(response.model_metadata))
            return response
        except asyncio.CancelledError:
            capture.update(status="cancelled", error={"type": "CancelledError"})
            raise
        except Exception as error:
            capture["error"] = {"type": type(error).__name__}
            raise
        finally:
            capture["elapsedSeconds"] = round(time.monotonic() - call_started, 3)
            capture["requestAttempts"] = getattr(service, "request_attempts", 0)
            capture["responseDiagnostic"] = deepcopy(getattr(service, "diagnostic", {}))
            capture["requestDiagnostics"] = deepcopy(
                getattr(service, "request_diagnostics", []),
            )
            if service is not None:
                redacted = service.redact(capture)
                capture.clear()
                capture.update(redacted)

    validation_phase = None
    try:
        report["scope"] = preview_scope(frozen, read_note_ids)
        result = await run_staged_account_report(
            frozen["context"], call_step, on_update=progress,
            representative_note_ids=deepcopy(read_note_ids),
        )
        report["result"] = {
            "output": result.output, "modelMetadata": result.model_metadata,
        }
        validation_phase = "product_validation"
        validated, verification = validate_product_result(
            result.output, frozen["snapshot"], frozen.get("observations"),
        )
        report.update(status="completed", validatedResult=validated,
                      portraitVerification=verification)
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "phase": validation_phase or (
            report["progress"][-1]["phase"] if report["progress"] else "input_validation"
        )}
        if isinstance(error, AccountReportOutputError):
            report["error"]["code"] = error.code
            report["recoveryMetadata"] = deepcopy(getattr(error, "pipeline_metadata", {}))
    report["requestAttempts"] = sum(item["requestAttempts"] for item in report["stages"])
    total_usage = {}
    for capture in report["stages"]:
        usage = safe_usage(capture["responseDiagnostic"].get("usage")) or safe_usage(
            capture.get("modelMetadata", {}).get("usage"),
        )
        for key, value in usage.items():
            total_usage[key] = total_usage.get(key, 0) + value
    report["totalUsage"] = total_usage
    report["elapsedSeconds"] = round(time.monotonic() - started, 3)
    for service in services:
        report = service.redact(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-from", type=Path, required=True,
                        help="已有检查报告中的完整冻结输入；不读取当前数据库")
    parser.add_argument("--read-note-ids", help="可选：逗号分隔的1～3个 n 编号，例如 n1,n3,n17")
    parser.add_argument("--live", action="store_true", help="明确执行整体阅读、并行精读和汇总")
    parser.add_argument("--provider", choices=("qwen", "deepseek"), default="qwen",
                        help="仅本次诊断使用的服务；默认 qwen，DeepSeek 需显式选择")
    parser.add_argument("--output", type=Path, help="新的诊断报告目录，拒绝覆盖")
    parser.add_argument("--read-timeout-seconds", type=int,
                        help="仅本次每个请求的读取等待上限，1～300秒；默认使用画像配置")
    parser.add_argument("--thinking", choices=("on", "off"),
                        help="仅本次账号模型是否思考；不修改正式配置")
    parser.add_argument("--thinking-budget", type=int,
                        help="仅本次思考预算，1～8192；不是最终答案长度")
    args = parser.parse_args()
    if args.live and args.output is None:
        parser.error("--live 必须指定新的 --output 目录")
    if args.read_timeout_seconds is not None and not 1 <= args.read_timeout_seconds <= 300:
        parser.error("--read-timeout-seconds 必须为1～300的整数")
    if args.thinking_budget is not None and not 1 <= args.thinking_budget <= 8192:
        parser.error("--thinking-budget 必须为1～8192的整数")
    if args.provider == "deepseek" and (args.thinking is not None or args.thinking_budget is not None):
        parser.error("--thinking 和 --thinking-budget 仅用于 Qwen；DeepSeek 固定关闭思考")
    if args.output is not None and args.output.exists():
        parser.error("--output 已存在，拒绝覆盖")
    try:
        case = case_from_report(args.input_from)
        source_hash = hashlib.sha256(args.input_from.read_bytes()).hexdigest()
        ids = ([item.strip() for item in args.read_note_ids.split(",")]
               if args.read_note_ids is not None else None)
        scope = preview_scope(case, ids)
        settings = replace(Settings.from_environment(),
                           account_diagnosis_provider=args.provider).for_account_diagnosis()
        if args.thinking is not None:
            settings = replace(settings, qwen_profile_enable_thinking=args.thinking == "on")
        if args.thinking_budget is not None:
            settings = replace(settings, qwen_profile_thinking_budget=args.thinking_budget)
        is_deepseek = args.provider == "deepseek"
        model = (settings.deepseek_model.strip() if is_deepseek
                 else settings.qwen_profile_model.strip() or settings.qwen_model)
        model_details = {
            "provider": args.provider, "configuredModel": model,
            "enableThinking": False if is_deepseek else settings.qwen_profile_enable_thinking,
            "thinkingBudget": (settings.qwen_profile_thinking_budget
                               if not is_deepseek and settings.qwen_profile_enable_thinking else None),
        }
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(f"输入预检失败：{type(error).__name__}")
    if not args.live:
        print(json.dumps({"mode": "preview", **model_details,
                          "requestAttempts": 0, "scope": scope}, ensure_ascii=False))
        return 0
    if not (settings.deepseek_api_key.strip() if is_deepseek else settings.qwen_api_key):
        parser.error("未配置 DeepSeek 密钥" if is_deepseek else "未配置 Qwen 密钥")
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        parser.error(f"无法创建新输出目录：{type(error).__name__}")

    def service_factory():
        return DiagnosticProfileCalls(
            settings,
            read_timeout_seconds=(args.read_timeout_seconds
                                  or (settings.deepseek_read_timeout_seconds if is_deepseek
                                      else settings.qwen_profile_read_timeout_seconds)),
        )

    report = asyncio.run(run_check(service_factory, case, read_note_ids=ids,
                                  on_progress=lambda event: print(json.dumps({
                                      "event": "progress", **event,
                                  }, ensure_ascii=False), flush=True)))
    report.update(**model_details, inputSource={
        "type": "previous_profile_report",
        "sha256": source_hash,
    })
    destination = args.output / "report.json"
    with destination.open("x", encoding="utf-8") as handle:
        json.dump(report, handle, ensure_ascii=False, indent=2)
    print(json.dumps({"report": str(destination), "status": report["status"],
                      "requestAttempts": report["requestAttempts"],
                      "elapsedSeconds": report["elapsedSeconds"],
                      "totalUsage": report["totalUsage"],
                      "semanticStatus": "not_reviewed"}, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
