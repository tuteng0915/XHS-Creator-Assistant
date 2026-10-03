"""Check one bounded creator-edit case; free preview unless --live is explicit.

Uses constructed Chinese writing samples, not production assets or a database.
Outputs contain model text: keep reports in ignored data/evals. No retries.
"""
from __future__ import annotations

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
from app.models import ModelOperation  # noqa: E402
from app.services.creator_grounding import validate_creator_edit  # noqa: E402
from app.services.model_calls import ModelCallService  # noqa: E402

TITLE = "做选择，不必把所有选项都研究完"
PARAGRAPHS = [
    "做选择之前，我们常常想把每一种可能都弄清楚。可选项越多，反而越难开始。",
    "先写下自己最在意的一件事，再看看哪些选项能满足它。暂时无法确定的，可以留待下一步。",
    "不必一次给出最终答案。先做一个可以调整的小决定，也是一种开始。",
]
REQUESTS = {
    "discussion": "先给我两个不同的表达角度，先别改标题和正文。",
    "style": "这篇像不像我？请指出具体位置并给建议，先别改正文。",
    "title": "只改标题，让它更具体自然。正文一个字都不要动。",
    "opening": "只把第一段压短到30字以内，标题和其余段落、换行都不要动。",
    "draft": "按当前选题直接写一篇简短初稿，不写个人经历，不必先给提纲。",
}


def make_case(name: str) -> dict:
    return {
        "topic": {"title": TITLE, "body": "" if name == "draft" else "\n\n".join(PARAGRAPHS)},
        "accountContext": {"accountPositioning": "分享日常选择方法，平实友好，不说教。"},
        "factSources": [{"id": "current-user-message", "text": REQUESTS[name]}],
        "messages": [],
        "userMessage": REQUESTS[name],
    }


def scope_checks(name: str, context: dict, checked: dict) -> dict[str, bool]:
    """Literal checks for these fixtures only; not an intent or quality classifier."""
    update = checked["update"]
    if name in {"discussion", "style"}:
        return {"discussionDoesNotEdit": update is None}
    result = {"updatePresent": update is not None}
    if update is None:
        return result
    if name == "title":
        result["bodyUnchanged"] = update["body"] == context["topic"]["body"]
        result["titleChanged"] = update["title"] != context["topic"]["title"]
    elif name == "opening":
        result["titleUnchanged"] = update["title"] == context["topic"]["title"]
        parts = update["body"].split("\n\n")
        result["remainingParagraphsUnchanged"] = parts[1:] == PARAGRAPHS[1:]
        result["openingShortened"] = 0 < len(parts[0]) <= 30
    elif name == "draft":
        result["nonemptyDraft"] = bool(update["body"].strip())
    return result


async def run_check(service, name: str) -> dict:
    context = make_case(name)
    report = {"case": name, "context": context, "requestAttempts": 1,
              "status": "failed", "semanticStatus": "not_reviewed"}
    phase = "model_call"
    try:
        response = await service.call_operation(ModelOperation.CREATOR_EDIT, context)
        report.update(output=response.output, modelMetadata=response.model_metadata)
        phase = "validation"
        checked = validate_creator_edit(response.output, context["factSources"])
        checks = scope_checks(name, context, checked)
        report.update(status="completed" if all(checks.values()) else "scope_failed",
                      scopeChecks=checks)
    except Exception as error:
        report["error"] = {"phase": phase, "type": type(error).__name__}
    return report


def redact(value, secrets: list[str]):
    if isinstance(value, str):
        for secret in sorted(filter(None, secrets), key=len, reverse=True):
            value = value.replace(secret, "[REDACTED]")
        return value
    if isinstance(value, list):
        return [redact(item, secrets) for item in value]
    if isinstance(value, dict):
        return {redact(key, secrets): redact(item, secrets) for key, item in value.items()}
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", choices=REQUESTS, default="opening")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path, help="新的报告目录，拒绝覆盖")
    args = parser.parse_args()
    if not args.live:
        print(json.dumps({"mode": "preview", "requestAttempts": 0,
                          "context": make_case(args.case)}, ensure_ascii=False))
        return 0
    if args.output is None:
        parser.error("--live 必须指定 --output")
    settings = replace(Settings.from_environment(), model_provider="qwen")
    if not settings.qwen_api_key:
        parser.error("未配置 Qwen 密钥")
    args.output.mkdir(parents=True, exist_ok=False)
    service = ModelCallService(settings)
    system, user = service._build_prompt(ModelOperation.CREATOR_EDIT, make_case(args.case))
    report = asyncio.run(run_check(service, args.case))
    report.update(configuredModel=settings.qwen_model,
                  promptHash=hashlib.sha256(system.encode()).hexdigest(),
                  inputHash=hashlib.sha256(user.encode()).hexdigest())
    report = redact(report, [settings.qwen_api_key, settings.anthropic_api_key])
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(json.dumps({"status": report["status"], "case": args.case,
                      "requestAttempts": 1, "report": str(args.output / "report.json")},
                     ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
