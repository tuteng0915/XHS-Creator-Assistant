"""Preview saved notes or check the profile stage with one Qwen call.

No database, crawling, topic generation or retries. Reports include private source
text; keep them under ignored data/evals. Default mode does not call any model.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
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
from app.models import ModelOperation  # noqa: E402
from app.services.account_diagnosis_evidence import (  # noqa: E402
    profile_stage_input,
    verified_portrait,
)
from app.services.analysis_runs import AnalysisRunService  # noqa: E402
from app.services.creator_analysis_scope import scope_creator_profile  # noqa: E402
from app.services.xhs_imports import XhsOfflineImportService  # noqa: E402
from app.workflows.account_diagnosis import ProfileStageResult  # noqa: E402


def prepare_case(source: Path) -> dict:
    exported = build_xhs_creator_profile_payload(load_mediacrawler_export(source, code="check"))
    parsed = XhsOfflineImportService(None)._parse_creator_profile_export(exported)
    scoped, scope = scope_creator_profile(parsed, "recent_10")
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


def claim_counts(portrait) -> dict:
    portrait = portrait if isinstance(portrait, dict) else {}
    result = {key: int(isinstance(portrait.get(key), dict))
              for key in ("summary", "encouragement", "recentChange")}
    for key in ("keywords", "strengths", "recurringThemes", "readerValue", "expressionPatterns"):
        values = portrait.get(key)
        result[key] = len(values) if isinstance(values, list) else 0
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
                  "关键词是否同时体现主题、价值和表达，而非仅复述标题？",
                  "优势是否具体指出已经做对的事情，且引用真正支持它？",
                  "鼓励是否自然、贴合本人，而非承诺流量或泛泛夸奖？",
                  "改进建议与优势是否自洽，是否把相关性写成原因？",
                  "是否分开理解赞、收藏、评论、分享，而非只按点赞判断所有表现？",
                  "复盘经验是否指出来源写法、适用场景和一个可执行调整？",
                  "风格描述是否可以模仿，而非空泛人格标签或固定爆款模板？",
                  "示例是否被误写为账号事实，是否保留不同类型内容的表达差异？",
              ]}
    phase = "model_call"
    started = time.monotonic()
    try:
        response = await service.call_operation(ModelOperation.PROFILE, case["context"])
        report.update(output=response.output, modelMetadata=response.model_metadata)
        phase = "validation"
        result = ProfileStageResult.model_validate(response.output).model_dump(mode="json")
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
        report["responseDiagnostic"] = service.diagnostic.copy()
        # Also cover a credential echoed inside otherwise valid structured output.
        report = service.redact(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, help="已保存的 MediaCrawler 原始数据目录")
    parser.add_argument("--input-from", type=Path, help="复用已有画像检查报告的完整冻结输入")
    parser.add_argument("--live", action="store_true", help="只调用一次 Qwen 账号画像")
    parser.add_argument("--output", type=Path, help="新的报告目录，拒绝覆盖")
    args = parser.parse_args()
    if args.live and args.output is None:
        parser.error("--live 必须指定新的 --output 目录")
    if (args.source is None) == (args.input_from is None):
        parser.error("提供原始数据目录或 --input-from，二选一")
    try:
        case = case_from_report(args.input_from) if args.input_from else prepare_case(args.source)
    except (OSError, ValueError) as error:
        parser.error(f"输入预检失败：{type(error).__name__}")
    if not args.live:
        print(json.dumps({
            "mode": "preview", "requestAttempts": 0,
            "coverage": case["observations"].get("coverage"),
            "chronology": case["observations"].get("chronology"),
        }, ensure_ascii=False))
        return 0
    settings = replace(Settings.from_environment(), model_provider="qwen")
    if not settings.qwen_api_key:
        parser.error("未配置 Qwen 密钥")
    args.output.mkdir(parents=True, exist_ok=False)
    service = DiagnosticProfileCalls(settings)
    system, user = service._build_prompt(ModelOperation.PROFILE, case["context"])
    report = asyncio.run(run_check(service, case))
    report.update(provider="qwen", configuredModel=settings.qwen_model,
                  promptHash=hashlib.sha256(system.encode()).hexdigest(),
                  inputHash=hashlib.sha256(user.encode()).hexdigest())
    if args.input_from:
        report["inputSource"] = {"type": "previous_profile_report",
                                 "sha256": hashlib.sha256(args.input_from.read_bytes()).hexdigest()}
    report = service.redact(report)
    destination = args.output / "report.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(destination), "status": report["status"],
                      "requestAttempts": 1, "semanticStatus": "not_reviewed"}, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
