"""Controlled same-text persona check; no production database access.

Default is a free case preview. --live performs at most seven Qwen requests in
the real graph using a temporary database; no network retries. These authored
roles test behavior differences, not audience inference or prediction accuracy.
--audience-from with explicit --group-ids instead reuses accepted analysis roles
for at most three initial reactions, without a graph, database, or synthesis.
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
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import ModelOperation, WorkspaceCreate  # noqa: E402
from app.services.audience_evidence import (  # noqa: E402
    AUDIENCE_METHOD_VERSION,
    reader_persona_context,
    select_audience_personas,
)
from app.services.common import utc_now  # noqa: E402
from app.services.model_calls import ModelCallService  # noqa: E402
from app.services.simulated_fans import FanDefinition  # noqa: E402
from app.workflows.audience_simulation import (  # noqa: E402
    AudienceSimulationWorkflowService,
    PersonaDefinitionsResult,
    PersonaReactionResult,
    RealAudienceSimulationModelProvider,
    SimulationSynthesisResult,
    validate_trigger_quote,
)


def authored_case() -> dict:
    return {
        "caseId": "same-text-three-readers-v1",
        "origin": "authored_test_not_real_followers",
        "topic": {
            "title": "不转码，也能用半小时做一次 AI 产品小练习",
            "body": (
                "先选一个你熟悉的小任务，例如把一段公开的活动介绍改成报名提醒。"
                "今天先用十分钟写清谁会看、要知道什么，再用任意免费文字模型生成两个版本，"
                "花十分钟对照原文检查日期、地点和报名条件，最后用十分钟写下你会改哪三处以及理由。"
                "这里不需要写代码、买课或找导师，也不要上传公司文件或他人的私人信息。"
                "练习不要求公开发布，先保存在自己的文档里即可。"
                "这只是一种练习产品判断的方法，不是招聘入口，不保证实习或录用；"
                "做完可以停下来，不必今天就把它做成作品集。"
            ),
        },
        "personas": [
            {
                "id": "action", "name": "先试一步派",
                "interests": ["职业发展", "AI应用", "个人成长"],
                "profile": "看到新办法就想先试一小步，有明确入口时不等完整计划。",
                "coreConcern": "想找到今天就能完成的第一步",
                "contentPreference": "短步骤和可照做的例子",
                "expressionStyle": "直说最想试的部分，不必为了互动硬提问。",
            },
            {
                "id": "check", "name": "仔细核对派",
                "interests": ["职业发展", "AI应用", "个人成长"],
                "profile": "先看条件与投入，内容已经交代清楚时会认可，不为反对而反对。",
                "coreConcern": "想判断练习的投入和适用条件是否清楚",
                "contentPreference": "条件说明和检验方法",
                "expressionStyle": "冷静简短，只追问真正没解释的关键条件。",
            },
            {
                "id": "quiet", "name": "安静回看派",
                "interests": ["职业发展", "AI应用", "个人成长"],
                "profile": "遇到完整清单通常自己留着回看，只有缺关键步骤才公开提问。",
                "coreConcern": "想在需要时方便地找到完整步骤",
                "contentPreference": "可保存、可回查的清单",
                "expressionStyle": "通常不留言，没有具体疑问时保持沉默。",
            },
        ],
        "reviewQuestions": [
            "是否只改变说话语气，还是需求与判断在反应里产生了差异？",
            "是否重复追问正文已给出的步骤、费用、代码门槛或是否必须公开？",
            "是否把设定编成已经发生的个人经历或已执行的动作？",
            "没有关键缺口时，安静角色能否不公开评论？",
            "讨论是否只使用可见公开评论，而不读取别人的私下感受？",
        ],
    }


def analysis_case(path: Path, group_ids: list[str]) -> dict:
    """Use accepted roles as-is, including imperfect traits; never reinterpret them."""
    if not 1 <= len(group_ids) <= 3 or len(set(group_ids)) != len(group_ids):
        raise ValueError("本次检查请明确选择一至三位不同角色")
    raw = path.read_bytes()
    report = json.loads(raw)
    result = report.get("result", {})
    if report.get("status") not in {"completed", "partially_completed"} or not result:
        raise ValueError("只接受包含有效受众结果的检查报告")
    groups = result.get("groups", [])
    if len({group["id"] for group in groups}) != len(groups):
        raise ValueError("报告的受众 ID 重复")
    by_id = {p["id"]: p for p in select_audience_personas(result, limit=None)}
    if any(group_id not in by_id for group_id in group_ids):
        raise ValueError("选择的受众不在报告有效结果中")
    personas = []
    for group_id in group_ids:
        original = by_id[group_id]
        editable = FanDefinition.model_validate(original).model_dump(by_alias=True)
        personas.append({**original, **editable})
    case = authored_case()
    return {
        **case, "caseId": "analysis-roles-same-text-v1",
        "origin": "analysis_report_not_saved_fan_assets",
        "sourceReport": str(path), "sourceReportHash": hashlib.sha256(raw).hexdigest(),
        "sourceInputHash": report.get("inputHash"), "selectedGroupIds": group_ids,
        "personas": personas,
        "reviewQuestions": [*case["reviewQuestions"],
                            "原人物设定或历史评论是否把新反应锁在旧帖子的话题里？"],
    }


class SingleAttemptCalls:
    """Cap real billing even when the product graph retries a failed persona."""

    def __init__(self, service, max_requests=7):
        self.service = service
        self.max_requests = max_requests
        self.seen = set()
        self.calls = []

    async def call_operation(self, operation, context):
        key = (operation.value, context.get("persona", {}).get("id", ""))
        if key in self.seen or len(self.seen) >= self.max_requests:
            raise RuntimeError("本次验证不重复调用失败的角色或超过请求预算")
        if operation not in {
            ModelOperation.SIMULATION_REACTION, ModelOperation.SIMULATION_DEBATE,
            ModelOperation.SIMULATION_SYNTHESIS,
        }:
            raise RuntimeError("本次验证只使用指定测试人物，不生成新人物")
        self.seen.add(key)
        entry = {"operation": key[0], "personaId": key[1], "context": context}
        self.calls.append(entry)
        started = time.monotonic()
        try:
            response = await self.service.call_operation(operation, context)
            entry.update(output=response.output, metadata=response.model_metadata)
            return response
        except Exception as error:
            entry["errorType"] = type(error).__name__
            raise RuntimeError(f"模型验证请求失败：{type(error).__name__}") from None
        finally:
            entry["elapsedSeconds"] = round(time.monotonic() - started, 2)


def initial_context(case: dict) -> tuple[dict, list[dict]]:
    """Use the graph's nested field aliases and episode-selection rules."""
    if not 1 <= len(case["personas"]) <= 3:
        raise ValueError("独立反应检查最多三位角色")
    target = AudienceSimulationWorkflowService._simulation_target_context({
        "topic": case["topic"], "targetType": "topic",
    })
    validated = PersonaDefinitionsResult.model_validate({"personas": case["personas"]})
    personas = [reader_persona_context(p, target) for p in
                validated.model_dump(mode="json", by_alias=True)["personas"]]
    return target, personas


async def run_initial_check(service, case: dict) -> dict:
    """Mirror product input/validation, but call no graph, retry, debate or database."""
    target, personas = initial_context(case)
    calls = SingleAttemptCalls(service, max_requests=3)
    provider = RealAudienceSimulationModelProvider(calls)
    errors = {}

    async def react(persona):
        persona_id = persona["id"]
        try:
            output = await provider.initial_reaction(persona=persona, topic=target)
            result = PersonaReactionResult.model_validate(output).model_dump(mode="json")["reaction"]
            if result["personaId"] != persona_id:
                raise ValueError("反应角色与请求不一致")
            validate_trigger_quote(result["triggerQuote"], target)
            return {**result, "messageId": f"initial:{persona_id}", "round": 1}
        except Exception as error:
            errors[f"initial_reactions.{persona_id}"] = type(error).__name__
            return None

    results = await asyncio.gather(*(react(p) for p in personas))
    reactions = [result for result in results if result is not None]
    return {
        "createdAt": utc_now(), "case": case, "personas": personas, "target": target,
        "status": "completed" if not errors else "partially_completed" if reactions else "failed",
        "stageErrors": errors, "reactions": reactions, "calls": calls.calls,
        "paidRequests": len(calls.calls), "requiresSemanticReview": True,
        "requestAttempts": len(calls.calls),
        "receivedStructuredResponses": sum("output" in call for call in calls.calls),
        "billingStatus": "not_verified",
        "executedStages": ["initial_reactions"], "semanticStatus": "not_reviewed",
    }


async def run_check(service, settings: Settings) -> dict:
    case = authored_case()
    calls = SingleAttemptCalls(service)
    with TemporaryDirectory(prefix="audience-reactions-") as temporary:
        root = Path(temporary)
        app = create_app(replace(settings, database_path=root / "test.sqlite3",
                                 upload_directory=root / "uploads"))
        workspace = app.state.workspace_service.create(WorkspaceCreate(name="隔离验证"))
        snapshot = {
            "simulationMethod": AUDIENCE_METHOD_VERSION,
            "mode": "live", "workspaceId": workspace.id, "workspaceName": workspace.name,
            "accountPositioning": "", "targetType": "topic", "topic": case["topic"],
            "audiencePersonas": [{**p, "evidenceStatus": "hypothesis",
                                  "limitations": "人工编写的测试角色，不是真实粉丝。"}
                                 for p in case["personas"]],
        }
        simulation = app.state.simulation_service
        with app.state.database.transaction() as connection:
            row = simulation.repository.create(
                connection, workspace_id=workspace.id, topic_id=None, draft_id=None,
                input_snapshot_json=json.dumps(snapshot, ensure_ascii=False), now=utc_now(),
            )
        workflow = app.state.simulation_workflow_service
        workflow.live_provider = RealAudienceSimulationModelProvider(calls)
        await workflow.collect_events(row["id"])
        result = simulation.get(row["id"])
        report = {
            "createdAt": utc_now(), "case": case,
            "status": result.status.value, "stageErrors": result.stage_errors,
            "personas": result.persona_definitions, "reactions": result.reaction_results,
            "debateResponses": result.debate_results, "synthesis": result.synthesis,
            "calls": calls.calls, "paidRequests": len(calls.calls),
            "requiresSemanticReview": True,
        }
    return report


async def recheck_synthesis(service, baseline: dict) -> dict:
    """Keep the exact earlier discussion and spend only one call on its summary."""
    if baseline["case"]["origin"] != "authored_test_not_real_followers":
        raise ValueError("仅接受本脚本生成的独立测试报告")
    calls = SingleAttemptCalls(service)
    target = AudienceSimulationWorkflowService._simulation_target_context({
        "topic": baseline["case"]["topic"], "targetType": "topic",
    })
    errors = dict(baseline.get("stageErrors", {}))
    synthesis = {}
    try:
        output = await RealAudienceSimulationModelProvider(calls).synthesis(
            topic=target, personas=baseline["personas"], reactions=baseline["reactions"],
            debate_responses=baseline["debateResponses"],
        )
        synthesis = SimulationSynthesisResult.model_validate(output).model_dump()["synthesis"]
        errors.pop("synthesis", None)
    except Exception as error:
        errors["synthesis"] = type(error).__name__
    return {
        **baseline, "createdAt": utc_now(), "synthesis": synthesis,
        "status": "partially_completed" if errors else "completed", "stageErrors": errors,
        "calls": calls.calls, "paidRequests": len(calls.calls),
        "replayedStages": ["personas", "initial_reactions", "debate_responses"],
        "requiresSemanticReview": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="执行有限次数真实 Qwen 调用")
    parser.add_argument("--output", type=Path, help="新的独立结果目录，不覆盖已有目录")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--synthesis-from", type=Path, help="复用先前报告，只付费复测一次汇总")
    source.add_argument("--audience-from", type=Path, help="复用受众检查报告，只检查独立反应")
    parser.add_argument("--group-ids", nargs="+", help="明确选择一至三位有效受众 ID")
    args = parser.parse_args()
    if bool(args.audience_from) != bool(args.group_ids):
        parser.error("--audience-from 和 --group-ids 必须同时提供")
    case = analysis_case(args.audience_from, args.group_ids) if args.audience_from else None
    if case:
        initial_context(case)  # Validate nested episodes before settings, output or billing.
    if args.synthesis_from and not args.live:
        parser.error("--synthesis-from 需要显式提供 --live")
    if not args.live:
        print(json.dumps(case or authored_case(), ensure_ascii=False, indent=2))
        return 0
    if args.output is None:
        parser.error("真实验证必须指定 --output，例如 data/evals/reactions-20261003")
    settings = replace(Settings.from_environment(), model_provider="qwen")
    if not settings.qwen_api_key:
        parser.error("未配置 Qwen 密钥")
    args.output.mkdir(parents=True, exist_ok=False)
    service = ModelCallService(settings)
    if case:
        report = asyncio.run(run_initial_check(service, case))
    elif args.synthesis_from:
        baseline = json.loads(args.synthesis_from.read_text(encoding="utf-8"))
        report = asyncio.run(recheck_synthesis(service, baseline))
        report["baselineReport"] = str(args.synthesis_from)
    else:
        report = asyncio.run(run_check(service, settings))
    operations = ([ModelOperation.SIMULATION_REACTION] if case else
                  [ModelOperation.SIMULATION_SYNTHESIS] if args.synthesis_from else [
        ModelOperation.SIMULATION_REACTION, ModelOperation.SIMULATION_DEBATE,
        ModelOperation.SIMULATION_SYNTHESIS,
    ])
    report["promptHashes"] = {**report.get("promptHashes", {}), **{
        operation.value: hashlib.sha256(service._build_prompt(operation, {})[0].encode()).hexdigest()
        for operation in operations
    }}
    report.update(provider="qwen", configuredModel=settings.qwen_model)
    destination = args.output / "report.json"
    destination.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(destination), "status": report["status"],
                      "requestAttempts": report["paidRequests"],
                      "billingStatus": "not_verified",
                      "requiresSemanticReview": True}, ensure_ascii=False))
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
