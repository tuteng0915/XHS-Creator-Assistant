"""Preview scoped MediaCrawler input, or make one Qwen audience-analysis request.

No database access, crawling, retries, or asset writes. Reports contain source
text: keep them in ignored data/evals, not in Git. Default is a free preview.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from collections import Counter
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "backend"), str(ROOT / "scripts")]

from app.config import Settings  # noqa: E402
from app.models import ModelOperation  # noqa: E402
from app.services.audience_analyses import validate_audience_output  # noqa: E402
from app.services.audience_evidence import audience_context  # noqa: E402
from app.services.creator_analysis_scope import scope_creator_profile  # noqa: E402
from app.services.model_calls import ModelCallService  # noqa: E402
from app.services.xhs_imports import XhsOfflineImportService  # noqa: E402
from xhs_mediacrawler_fixture import (  # noqa: E402
    build_xhs_creator_profile_payload,
    load_mediacrawler_export,
)


def prepare_context(source: Path) -> dict:
    exported = build_xhs_creator_profile_payload(
        load_mediacrawler_export(source, code="check")
    )
    # Use the production import normalizer and scope rules; never create an asset.
    parsed = XhsOfflineImportService(None)._parse_creator_profile_export(exported)
    scoped, scope = scope_creator_profile(parsed, "recent_10")
    return audience_context({**scoped, "scope": scope})


def context_from_report(path: Path) -> dict:
    report = json.loads(path.read_text(encoding="utf-8"))
    context = report.get("context") if isinstance(report, dict) else None
    if (
        not isinstance(context, dict)
        or not isinstance(context.get("notes"), list)
        or not isinstance(context.get("scope"), dict)
        or not isinstance(context.get("sampling"), dict)
    ):
        raise ValueError("报告缺少完整 context，不能重放")
    return context


def review_summary(report: dict) -> dict:
    """Keep execution/quotation checks distinct from manual character review."""
    output = report.get("output", {})
    groups = output.get("groups") if isinstance(output, dict) else None
    diagnostics = report.get("diagnostics")
    rejected = diagnostics.get("rejectedGroups", []) if diagnostics else []
    codes = Counter(issue["code"] for group in rejected for issue in group["issues"])
    return {
        "automatedStatus": report["status"],
        "generatedGroups": len(groups) if isinstance(groups, list) else None,
        "acceptedGroups": diagnostics["acceptedGroups"] if diagnostics else None,
        "rejectedGroups": len(rejected) if diagnostics else None,
        "rejectionCodes": dict(codes),
        "semanticStatus": "not_reviewed",
        "manualChecks": [
            "兴趣能否跨笔记复用，而不是单篇话题或一次问题？",
            "需求是否具体，引文是否在语义上支持该需求？",
            "共享兴趣的人物是否有不同判断和行动，而非只换语气？",
            "性格是否是自洽的模拟设定，而非虚构已发生经历或行为频率？",
            "作者背景是否被误用为读者需求（含换引文或改称正文来源）？",
        ],
    }


async def run_check(service, context: dict) -> dict:
    report = {
        "status": "failed",
        "requestAttempts": 1,
        "context": context,
        "requiresSemanticReview": True,
    }
    started = time.monotonic()
    phase = "model_call"
    try:
        response = await service.call_operation(
            ModelOperation.AUDIENCE_ANALYSIS, context
        )
        report.update(output=response.output, modelMetadata=response.model_metadata)
        phase = "validation"
        result, diagnostics = validate_audience_output(response.output, context)
        report.update(result=result, diagnostics=diagnostics)
        report["status"] = (
            "partially_completed"
            if result and diagnostics["rejectedGroups"]
            else "completed"
            if result
            else "failed"
        )
    except Exception as error:
        # Arbitrary provider error messages can contain request headers or URLs.
        report["error"] = {"phase": phase, "type": type(error).__name__}
    report["elapsedSeconds"] = round(time.monotonic() - started, 2)
    report["reviewSummary"] = review_summary(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "source", type=Path, nargs="?", help="已保存的 MediaCrawler 原始数据目录"
    )
    parser.add_argument(
        "--context-from", type=Path, help="复用已有报告的完整输入，不重新选取范围"
    )
    parser.add_argument(
        "--live", action="store_true", help="仅一次 Qwen 调用，不自动重试"
    )
    parser.add_argument("--output", type=Path, help="新的报告目录，不覆盖现有内容")
    args = parser.parse_args()
    if bool(args.source) == bool(args.context_from):
        parser.error("提供 source 或 --context-from，且只能二选一")
    if args.live and args.output is None:
        parser.error("--live 必须指定新的 --output 目录")
    context = (
        context_from_report(args.context_from)
        if args.context_from
        else prepare_context(args.source)
    )
    if not args.live:
        print(
            json.dumps(
                {
                    "mode": "preview",
                    "requestAttempts": 0,
                    "scope": context["scope"],
                    "sampling": context["sampling"],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    settings = replace(Settings.from_environment(), model_provider="qwen")
    if not settings.qwen_api_key:
        parser.error("未配置 Qwen 密钥")
    args.output.mkdir(parents=True, exist_ok=False)
    service = ModelCallService(settings)
    report = asyncio.run(run_check(service, context))
    if args.context_from:
        report["baselineReport"] = str(args.context_from)
    system, user = service._build_prompt(ModelOperation.AUDIENCE_ANALYSIS, context)
    report.update(
        configuredModel=settings.qwen_model,
        provider="qwen",
        promptHash=hashlib.sha256(system.encode()).hexdigest(),
        inputHash=hashlib.sha256(user.encode()).hexdigest(),
    )
    destination = args.output / "report.json"
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "report": str(destination),
                "status": report["status"],
                "requestAttempts": 1,
                "requiresSemanticReview": True,
                "reviewSummary": report["reviewSummary"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
