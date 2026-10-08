"""Replay frozen failures through independent checks, with an HTTP-level budget."""

import argparse
import asyncio
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.errors import ApplicationError  # noqa: E402
from app.models import ModelCallResponse, ModelOperation  # noqa: E402
from app.services.editor_feedback import validate_editor_feedback  # noqa: E402
from app.services.model_calls import ModelCallService  # noqa: E402
from app.services.reader_selection import (  # noqa: E402
    ReaderSelectionInput,
    validate_reader_selection,
)


async def check(cases, settings, destination, *, fresh_selection_label=None):
    if len(cases) > 8 or destination.exists():
        raise ValueError("只接受最多八项核对，报告不得覆盖")
    fresh = next(
        (
            c
            for c in cases
            if c["label"] == fresh_selection_label and c["operation"] == "reader_selection"
        ),
        None,
    )
    if fresh_selection_label and fresh is None:
        raise ValueError("新生成验证必须选择清单内的一次选人")
    destination.parent.mkdir(parents=True, exist_ok=True)
    report = {"maxRequests": 10 if fresh else 8, "requestAttempts": 0, "calls": []}

    def save():
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    def before_request():
        if report["requestAttempts"] >= report["maxRequests"]:
            raise ValueError("实际模型请求预算已用完")
        report["requestAttempts"] += 1
        entry = report["calls"][-1]
        entry["requestAttempts"] += 1
        save()

    service = ModelCallService(settings, before_request=before_request)
    for case, reuse in [(c, True) for c in cases] + ([(fresh, False)] if fresh else []):
        context, operation = case["context"], ModelOperation(case["operation"])
        entry = {
            "label": case["label"],
            "reusedGeneration": reuse,
            "requestAttempts": 0,
            "context": context,
            "originalOutput": case["output"],
            "sourceHash": hashlib.sha256(json.dumps(case, sort_keys=True).encode()).hexdigest(),
        }
        report["calls"].append(entry)
        save()
        try:
            if reuse:
                response = await service.review_panel_output(
                    operation,
                    context,
                    ModelCallResponse(
                        output=case["output"], model_metadata=case.get("metadata", {})
                    ),
                )
            else:
                response = await service.call_operation(operation, context)
            entry.update(
                output=response.output, metadata=response.model_metadata, status="completed"
            )
            if operation == ModelOperation.READER_SELECTION:
                entry["validated"] = validate_reader_selection(
                    response.output, ReaderSelectionInput.model_validate(context)
                ).model_dump(by_alias=True)
            else:
                entry["validated"] = validate_editor_feedback(
                    response.output["synthesis"].get("editorFeedback"),
                    topic=context["topic"],
                    personas=context["personas"],
                    reactions=context["reactions"],
                    replies=context["debateResponses"],
                )
        except Exception as error:
            entry.update(status="failed", errorType=type(error).__name__)
            if isinstance(error, ApplicationError):
                entry["diagnostic"] = str(error)
            save()
            break  # A systemic transport/schema error must not spend the rest of the batch.
        save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--editor-report", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--fresh-selection-label")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    original = json.loads(args.report.read_text())
    replacements = (
        {c["label"]: c for c in json.loads(args.editor_report.read_text())["calls"]}
        if args.editor_report
        else {}
    )
    cases = []
    for c in original["calls"]:
        if c.get("output") and c["operation"] in {"reader_selection", "simulation_synthesis"}:
            newer = replacements.get(c["label"], c)
            cases.append({**newer, "operation": c["operation"]})
    if not args.live:
        print(json.dumps([c["label"] for c in cases], ensure_ascii=False))
        return
    if args.output is None:
        parser.error("需要新的报告路径")
    settings = replace(Settings.from_environment(), model_provider="qwen")
    report = asyncio.run(
        check(cases, settings, args.output, fresh_selection_label=args.fresh_selection_label)
    )
    print(
        json.dumps(
            {
                "requestAttempts": report["requestAttempts"],
                "statuses": [(c["label"], c["status"]) for c in report["calls"]],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
