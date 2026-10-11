"""Preview or explicitly evaluate the staged account report on frozen inputs.

The default preview makes no model calls and writes no files. Live diagnostics
contain private source text; save them only to an appropriate private eval folder.
No database access, source refresh, retries, or provider fallback is performed.
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
from check_account_profile import case_from_report  # noqa: E402

from app.config import Settings  # noqa: E402
from app.services.account_report_pipeline import (  # noqa: E402
    PIPELINE_VERSION,
    _material,
    run_staged_account_report,
)


def preview_scope(case: dict, read_note_ids: list[str] | None = None) -> dict:
    _, notes = _material(case["context"])
    available = {item["noteId"] for item in notes}
    if read_note_ids is not None and (
        not 1 <= len(read_note_ids) <= 3
        or any(not isinstance(item, str) or item not in available for item in read_note_ids)
        or len(set(read_note_ids)) != len(read_note_ids)
    ):
        raise ValueError("--read-note-ids 必须是冻结输入中1～3个不同的 n 编号")
    return {
        "inputNoteCount": len(notes),
        "inputBodyCharacters": sum(len(item["body"]) for item in notes),
        "readSelection": "explicit" if read_note_ids is not None else "overview_selected",
        "readNoteIds": list(read_note_ids) if read_note_ids is not None else None,
        "readNoteCount": len(read_note_ids) if read_note_ids is not None else None,
        "maxReadNoteCount": len(read_note_ids) if read_note_ids is not None else min(3, len(notes)),
        "maxModelRequests": 2 + (
            len(read_note_ids) if read_note_ids is not None else min(3, len(notes))
        ),
    }


def _input_scope(stage: str, payload: dict) -> dict:
    if stage == "read":
        note = payload["note"]
        return {"kind": "single_note", "noteCount": 1, "title": note["title"],
                "bodyCharacters": sum(len(item["text"]) for item in note["bodyExcerpts"])}
    return {
        "kind": "all_source_notes" if stage == "overview" else "conclusions_only",
        "noteCount": len(payload["notes"]),
        "noteIds": [item["noteId"] for item in payload["notes"]],
        **({"readingCount": len(payload["readings"])} if stage == "synthesis" else {}),
    }


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
        event["elapsedSeconds"] = round(time.monotonic() - started, 3)
        report["progress"].append(event)
        if on_progress is not None:
            on_progress(deepcopy(event))

    async def call_step(stage, system, user):
        payload = json.loads(user)
        capture = {
            "sequence": len(report["stages"]) + 1, "stage": stage, "status": "failed",
            "input": payload, "inputScope": _input_scope(stage, payload),
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

    try:
        report["scope"] = preview_scope(frozen, read_note_ids)
        result = await run_staged_account_report(
            frozen["context"], call_step, on_update=progress,
            representative_note_ids=deepcopy(read_note_ids),
        )
        report.update(status="completed", result={
            "output": result.output, "modelMetadata": result.model_metadata,
        })
    except Exception as error:
        report["error"] = {"type": type(error).__name__, "phase": (
            report["progress"][-1]["phase"] if report["progress"] else "input_validation"
        )}
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
    parser.add_argument("--output", type=Path, help="新的诊断报告目录，拒绝覆盖")
    parser.add_argument("--read-timeout-seconds", type=int,
                        help="仅本次每个请求的读取等待上限，1～300秒；默认使用画像配置")
    args = parser.parse_args()
    if args.live and args.output is None:
        parser.error("--live 必须指定新的 --output 目录")
    if args.read_timeout_seconds is not None and not 1 <= args.read_timeout_seconds <= 300:
        parser.error("--read-timeout-seconds 必须为1～300的整数")
    if args.output is not None and args.output.exists():
        parser.error("--output 已存在，拒绝覆盖")
    try:
        case = case_from_report(args.input_from)
        source_hash = hashlib.sha256(args.input_from.read_bytes()).hexdigest()
        ids = ([item.strip() for item in args.read_note_ids.split(",")]
               if args.read_note_ids is not None else None)
        scope = preview_scope(case, ids)
        settings = replace(Settings.from_environment(), model_provider="qwen")
        model = settings.qwen_profile_model.strip() or settings.qwen_model
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(f"输入预检失败：{type(error).__name__}")
    if not args.live:
        print(json.dumps({"mode": "preview", "provider": "qwen", "configuredModel": model,
                          "requestAttempts": 0, "scope": scope}, ensure_ascii=False))
        return 0
    if not settings.qwen_api_key:
        parser.error("未配置 Qwen 密钥")
    try:
        args.output.mkdir(parents=True, exist_ok=False)
    except OSError as error:
        parser.error(f"无法创建新输出目录：{type(error).__name__}")

    def service_factory():
        return DiagnosticProfileCalls(
            settings,
            read_timeout_seconds=(args.read_timeout_seconds
                                  or settings.qwen_profile_read_timeout_seconds),
        )

    report = asyncio.run(run_check(service_factory, case, read_note_ids=ids,
                                  on_progress=lambda event: print(json.dumps({
                                      "event": "progress", **event,
                                  }, ensure_ascii=False), flush=True)))
    report.update(provider="qwen", configuredModel=model, inputSource={
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
