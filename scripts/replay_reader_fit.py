"""Freeze a saved selection and replay only its existing reader-fit check once."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.services.panel_quality import apply_review, prepare_review  # noqa: E402
from app.services.reader_selection import ReaderSelectionInput, validate_reader_selection  # noqa: E402


def prepare(saved: dict):
    primary = json.loads(saved["requests"][0]["rawContent"])
    context = saved["inputSnapshot"]
    inputs = ReaderSelectionInput.model_validate(context)
    plan = prepare_review("reader_selection", context, primary)
    if plan is None:
        raise ValueError("No saved recommendation to check")
    old_packet = saved["requests"][1]["packet"]
    original_context = json.loads(old_packet["messages"][-1]["content"])
    source_context = {k: v for k, v in plan.context.items() if k != "recommendationClaims"}
    if source_context != original_context:
        raise ValueError("Replay would change the frozen checker input")
    return inputs, primary, plan


async def replay(args):
    source = args.source_report.read_bytes()
    saved = json.loads(source)
    inputs, primary, plan = prepare(saved)
    report = {
        "mode": "saved_primary_replay_fit_check_only", "maxRequests": 1, "requests": [],
        "sourceSha256": hashlib.sha256(source).hexdigest(),
        "checkerInputExact": plan.prompt[1] == saved["requests"][1]["packet"]["messages"][-1]["content"],
        "checkerSourceInputExact": True, "savedPrimaryOutput": primary,
        "recommendationClaims": plan.context.get("recommendationClaims", []),
        "inputSnapshot": saved["inputSnapshot"], "before": saved["result"],
        "oldDecisions": json.loads(saved["requests"][1]["rawContent"]),
        "newPromptHash": hashlib.sha256(plan.system.encode()).hexdigest(),
        "oldPromptHash": hashlib.sha256(
            saved["requests"][1]["packet"]["messages"][0]["content"].encode()).hexdigest(),
        "expected": {"includeGroups": args.expect_include, "excludeGroups": args.expect_exclude},
        "personasRegenerated": False, "selectionRegenerated": False,
        "discussionRun": False, "databaseOpened": False,
    }
    if not args.live:
        print(json.dumps({"modelRequests": 0, "reviewedIds": plan.ids,
                          "checkerSourceInputExact": True,
                          "claimsFromSavedPrimary": bool(plan.context.get("recommendationClaims")),
                          "expected": report["expected"]},
                         ensure_ascii=False))
        return
    if args.output.exists():
        raise ValueError("Refusing to overwrite an evaluation")
    from app.config import Settings, load_env_file_defaults
    from app.models import ModelOperation
    from app.services.model_calls import ModelCallService

    if args.env_file:
        load_env_file_defaults(args.env_file)
    settings = Settings.from_environment()
    if settings.model_provider != "deepseek" or not settings.deepseek_api_key:
        raise ValueError("Configured DeepSeek credentials required")
    args.output.mkdir(parents=True, exist_ok=False)

    def save():
        text = json.dumps(report, ensure_ascii=False, indent=2)
        for key in (settings.deepseek_api_key, settings.qwen_api_key, settings.anthropic_api_key):
            if key:
                text = text.replace(key, "[redacted]")
        (args.output / "report.json").write_text(text + "\n", encoding="utf-8")

    async def request_hook(request):
        if report["requests"]:
            raise RuntimeError("Single-request replay budget exhausted")
        report["requests"].append({"packet": json.loads(request.content), "status": "running"})
        save()

    async def response_hook(response):
        await response.aread()
        row = report["requests"][0]
        row["httpStatus"] = response.status_code
        raw = response.json()
        choice = raw["choices"][0]
        row.update(status="returned", rawContent=choice["message"].get("content"),
                   finishReason=choice.get("finish_reason"), model=raw.get("model"),
                   usage=raw.get("usage"))
        save()

    service = ModelCallService(settings)
    factory = service._deepseek_client

    def client(operation):
        result = factory(operation)
        result.event_hooks["request"].append(request_hook)
        result.event_hooks["response"].append(response_hook)
        return result

    service._deepseek_client = client
    started = time.monotonic()
    try:
        # Existing check only: never call call_operation or the selection provider.
        checked = await service._call_deepseek(
            ModelOperation.READER_SELECTION, saved["inputSnapshot"], review_prompt=plan.prompt,
        )
        output, receipt = apply_review(plan, primary, checked.output)
        result = validate_reader_selection(output, inputs)
        mapping = saved["fanToGroup"]
        selected = {mapping[r.fan_id] for r in result.proposed_readers}
        report.update(status=result.status, result=result.model_dump(by_alias=True),
                      reviewReceipt=receipt, modelMetadata=checked.model_metadata,
                      selectedGroups=sorted(selected), semanticExpectedMatches=(
                          set(report["expected"]["includeGroups"]) <= selected
                          and not set(report["expected"]["excludeGroups"]) & selected))
    except Exception as error:
        report.update(status="failed", errorType=type(error).__name__)
    finally:
        report.update(elapsedSeconds=round(time.monotonic() - started, 3),
                      sourceUnchanged=args.source_report.read_bytes() == source,
                      actualModelRequests=len(report["requests"]))
        save()
    print(json.dumps({k: report.get(k) for k in ["status", "errorType", "selectedGroups",
                    "semanticExpectedMatches", "actualModelRequests", "elapsedSeconds",
                    "sourceUnchanged"]}, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--expect-include", action="append", default=[])
    parser.add_argument("--expect-exclude", action="append", default=[])
    parser.add_argument("--live", action="store_true")
    asyncio.run(replay(parser.parse_args()))
