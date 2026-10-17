"""Two saved readers, two authored drafts, at most six model attempts in an isolated DB."""

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
from tempfile import TemporaryDirectory

from fastapi.encoders import jsonable_encoder

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))

from check_audience_reactions import create_app  # noqa: E402

from app.config import Settings  # noqa: E402
from app.models import (  # noqa: E402
    ModelOperation,
    PanelTask,
    SimulationRunCreate,
    TopicCreate,
    TopicUpdate,
)
from app.services.common import utc_now  # noqa: E402
from app.services.model_calls import ModelCallService  # noqa: E402
from app.services.panel_reading import resolve_reaction_anchor  # noqa: E402
from app.services.panel_retests import PanelRetestCreate  # noqa: E402
from app.services.simulated_fans import SimulatedFanService  # noqa: E402
from app.workflows.audience_simulation import (  # noqa: E402
    PersonaReactionResult,
    RealAudienceSimulationModelProvider,
    SimulationSynthesisResult,
    validate_trigger_quote,
)

TITLE = "免费的十分钟口语练习，先从一分钟自我介绍开始"
BODY = (
    "这不是培训班推荐，而是一个可以自己完成的小练习。用手机录一分钟自我介绍，"
    "重听一遍，挑一处卡顿的句子改写，再录一次。两段录音都留在自己手机上，不需要报名或上传。"
    "今天只花十分钟，不追求一次说得完美；做完比较两次录音，决定要不要继续练。"
)
BEFORE = "做完比较两次录音，决定要不要继续练。"
AFTER = (
    "比较时只数两次超过三秒的停顿次数：第二次更少，就记下这句表达；"
    "这只是本次练习的观察方法，不是口语能力评分，也不承诺提分。"
)


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_readers(database, workspace_id, ids):
    if len(ids) != 2 or len(set(ids)) != 2:
        raise ValueError("本检查只接受两位不同的已保存读者")
    connection = sqlite3.connect(database.resolve(strict=True).as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        return SimulatedFanService(None).snapshots(connection, workspace_id, ids)
    finally:
        connection.close()


class BoundedCalls:
    def __init__(self, service):
        self.service, self.phase = service, "baseline"
        self.calls, self.seen = [], set()
        self.failures = {}
        self.halted = False
        self.lock = asyncio.Lock()
        self.request_attempts = 0
        if isinstance(service, ModelCallService):
            service.before_request = self.before_request

    def before_request(self):
        if self.request_attempts >= 6:
            raise RuntimeError("含独立核对在内的六次请求预算已用完")
        self.request_attempts += 1
        self.calls[-1]["requestCount"] = self.calls[-1].get("requestCount", 0) + 1

    async def call_operation(self, operation, context):
        async with self.lock:
            key = (self.phase, operation.value, context.get("persona", {}).get("id"))
            if key in self.failures:
                raise RuntimeError(self.failures[key])
            if self.halted:
                raise RuntimeError("因先前请求失败停止验证，本步骤未发送模型请求")
            if (
                key in self.seen
                or len(self.calls) >= 6
                or operation
                not in {
                    ModelOperation.SIMULATION_REACTION,
                    ModelOperation.SIMULATION_SYNTHESIS,
                }
            ):
                raise RuntimeError("验证已停止或到达预算，不重复请求")
            self.seen.add(key)
            entry = {
                "phase": self.phase,
                "operation": operation.value,
                "personaId": key[2],
                "context": context,
            }
            if isinstance(self.service, ModelCallService):
                entry["requestCount"] = 0
            self.calls.append(entry)
            start = time.monotonic()
            failure_code = "model_request_failed"
            try:
                response = await self.service.call_operation(operation, context)
                entry["output"] = response.output
                entry["metadata"] = {
                    k: response.model_metadata[k]
                    for k in (
                        "provider",
                        "model",
                        "modelSource",
                        "systemPromptHash",
                        "usage",
                        "requestCount",
                        "panelReview",
                        "generationUsage",
                    )
                    if k in response.model_metadata
                }
                failure_code = "response_schema_invalid"
                if operation == ModelOperation.SIMULATION_REACTION:
                    normalized = resolve_reaction_anchor(response.output, context["topic"])
                    reaction = PersonaReactionResult.model_validate(normalized).reaction
                    if reaction.personaId != key[2]:
                        failure_code = "persona_id_mismatch"
                        raise ValueError("wrong persona")
                    failure_code = "trigger_quote_not_in_frozen_text"
                    validate_trigger_quote(reaction.triggerQuote, context["topic"])
                else:
                    SimulationSynthesisResult.model_validate(response.output)
                return response
            except Exception as error:
                self.halted = True
                entry["errorType"] = type(error).__name__
                entry["failureCode"] = failure_code
                message = f"本次验证请求失败：{failure_code}（未自动重试）"
                self.failures[key] = message
                raise RuntimeError(message) from None
            finally:
                entry["elapsedSeconds"] = round(time.monotonic() - start, 2)


async def check(database, workspace_id, ids, settings, service):
    load_readers(database, workspace_id, ids)  # Fail before creating anything or calling a model.
    original_hash = file_hash(database)
    calls = BoundedCalls(service)
    report = {
        "createdAt": utc_now(),
        "origin": "saved_readers_with_authored_test_text",
        "sourceDatabaseHash": original_hash,
        "sourceWorkspaceId": workspace_id,
        "selectedReaderIds": ids,
        "semanticStatus": "not_reviewed",
        "intervention": {"before": BEFORE, "after": AFTER},
        "runs": [],
        "calls": calls.calls,
    }
    with TemporaryDirectory(prefix="sqs-panel-pair-") as temporary:
        root = Path(temporary)
        source = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
        target_db = sqlite3.connect(root / "pair.sqlite3")
        try:
            source.backup(target_db)
        finally:
            target_db.close()
            source.close()
        app = create_app(
            replace(
                settings,
                database_path=root / "pair.sqlite3",
                upload_directory=root / "uploads",
            )
        )
        simulation, topics = app.state.simulation_service, app.state.topic_service
        workflow = app.state.simulation_workflow_service
        workflow.live_provider = RealAudienceSimulationModelProvider(calls)
        target = topics.create(workspace_id, TopicCreate(title=TITLE))
        target = topics.update(
            target.id, TopicUpdate(body=BODY, expected_updated_at=target.updated_at)
        )
        baseline = simulation.create(
            workspace_id,
            SimulationRunCreate(
                topic_id=target.id,
                simulated_fan_ids=ids,
                mode="live",
                panel_task=PanelTask(reading_mode="natural", discussion_enabled=False),
            ),
        )
        await workflow.collect_events(baseline.id)
        first = simulation.get(baseline.id)
        report["runs"].append(first.model_dump(mode="json", by_alias=True))
        if first.status == "completed" and not calls.halted:
            revised = topics.update(
                target.id,
                TopicUpdate(
                    body=BODY.replace(BEFORE, AFTER),
                    expected_updated_at=target.updated_at,
                ),
            )
            preview = simulation.preview_retest(workspace_id, first.id)
            calls.phase = "retest"
            second = simulation.create_retest(
                workspace_id,
                first.id,
                PanelRetestCreate(
                    request_key="isolated-pair",
                    expected_updated_at=revised.updated_at,
                    confirmed=True,
                ),
            )
            await workflow.collect_events(second.id)
            second = simulation.get(second.id)
            report["runs"].append(second.model_dump(mode="json", by_alias=True))
            report["comparison"] = simulation.compare_retest(workspace_id, second.id)
            report["previewReaderIds"] = [r["id"] for r in preview["readers"]]
        report["status"] = (
            "completed"
            if len(report["runs"]) == 2 and all(r["status"] == "completed" for r in report["runs"])
            else "incomplete"
        )
    report.update(
        requestAttempts=sum(c.get("requestCount", 1) for c in calls.calls),
        billingStatus="not_verified",
        sourceDatabaseUnchanged=file_hash(database) == original_hash,
    )
    return jsonable_encoder(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/app.sqlite3")
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--reader-ids", nargs=2, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    readers = load_readers(args.database, args.workspace_id, args.reader_ids)
    if not args.live:
        print(
            json.dumps(
                {
                    "title": TITLE,
                    "baselineBody": BODY,
                    "revisedBody": BODY.replace(BEFORE, AFTER),
                    "readers": [{"id": p["id"], "name": p["name"]} for p in readers],
                    "requestAttempts": 0,
                    "maxLiveAttempts": 6,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.output is None or args.output.exists():
        parser.error("真实验证需要新的 --output 目录，不覆盖旧报告")
    settings = Settings.from_environment()
    if not settings.has_text_model_credentials:
        parser.error("未配置所选文字模型的密钥")
    args.output.mkdir(parents=True, exist_ok=False)
    report = asyncio.run(
        check(
            args.database,
            args.workspace_id,
            args.reader_ids,
            settings,
            ModelCallService(settings),
        )
    )
    report.update(provider=settings.model_provider, configuredModel=settings.text_model_name)
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "report": str(args.output / "report.json"),
                "status": report["status"],
                "model": settings.text_model_name,
                "requestAttempts": report["requestAttempts"],
                "sourceDatabaseUnchanged": report["sourceDatabaseUnchanged"],
            },
            ensure_ascii=False,
        )
    )
    return 0 if report["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
