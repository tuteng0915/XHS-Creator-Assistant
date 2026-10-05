"""Two-topic saved-reader check. Read-only SQLite; --live makes at most two Qwen calls."""
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

from pydantic import ValidationError as SchemaError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from app.config import Settings  # noqa: E402
from app.models import PanelTask  # noqa: E402
from app.services.model_calls import ModelCallService  # noqa: E402
from app.services.reader_selection import (  # noqa: E402
    prepare_reader_selection,
    selection_input_hash,
    validate_reader_selection,
)
from app.services.reader_selection_model import RealReaderSelectionProvider  # noqa: E402
from app.services.reader_selection_prompt import selection_prompt  # noqa: E402
from app.services.simulated_fans import SimulatedFanService  # noqa: E402

CASES = [
    {"title": "免费的口语练习，先用十分钟看看适不适合自己",
     "body": "这是一个自助口语小练习，不是培训班推荐。先录一分钟自我介绍，用免费工具转成文字，"
             "检查一处卡顿并重录。今天只比较这两次录音，不承诺十分钟提分。"
             "愿意继续的话，一周后再看自己能否更顺畅地说清经历。"},
    {"title": "放弃保研之后，我怎样重新理解选择的代价",
     "body": "这不是劝所有人放弃保研。对我而言，申请海外意味着准备成本和未知生活，"
             "留下也有稳定的研究路径。我把真正想学的内容、能接受的投入和不愿放弃的生活"
             "分别写下来，再查课程要求和申请时间线。结果不保证更成功，但让我能说清自己为何选择。"},
]


def load_inputs(database: Path, workspace_id: str, panel_task: PanelTask | None = None):
    from app.repositories.simulated_fans import SimulatedFanRepository
    from app.repositories.workspaces import WorkspaceRepository

    connection = sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        workspace = WorkspaceRepository().get(connection, workspace_id)
        fans = [SimulatedFanService.response(row)
                for row in SimulatedFanRepository().list(connection, workspace_id)]
        return [prepare_reader_selection(workspace_id, {
            "workspaceId": workspace_id, "accountPositioning": workspace["account_positioning"],
            "targetType": "topic", "topic": case,
        }, fans, panel_task=panel_task) for case in CASES]
    finally:
        connection.close()


async def check(provider, inputs):
    reports = []
    for item in inputs:
        started = time.monotonic()
        report = {"inputSnapshot": item.model_dump(by_alias=True),
                  "inputHash": selection_input_hash(item),
                  "candidateCount": len(item.candidates),
                  "requestAttempted": bool(item.candidates),
                  "promptHash": hashlib.sha256(
                      selection_prompt(item)[0].encode("utf-8"),
                  ).hexdigest(),
                  "semanticReview": {
                      "status": "not_reviewed",
                      "questions": [
                          "每位推荐理由能否同时对应本篇正文和已有的人物需求？",
                          "组合是否提供不同判断，而不只是换语气？",
                          "有没有预写人物一定会追问或补正文未提到的具体环节？",
                          "两题的名单或排序即使相同，理由是否真实适配各自内容？",
                      ],
                  }}
        try:
            response = await provider.select(item)
            result = validate_reader_selection(response.output, item)
            report.update(status=result.status, rawOutput=response.output,
                          result=result.model_dump(by_alias=True),
                          modelMetadata=response.model_metadata)
        except Exception as error:
            # Keep error types, not raw URLs, headers, credentials or provider exceptions.
            report.update(status="failed", errorType=type(error).__name__)
        report["elapsedSeconds"] = round(time.monotonic() - started, 2)
        reports.append(report)
        if report["status"] == "failed":
            break  # No blind second request when connectivity/response handling is broken.
    return reports


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--workspace-id", required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--reading-mode", choices=["natural", "guided"],
                        help="显式测试新试读协议；不传则保持旧协议")
    parser.add_argument("--focus-question", action="append", default=[])
    parser.add_argument("--no-discussion", action="store_true")
    args = parser.parse_args()
    if args.reading_mode is None and (args.focus_question or args.no_discussion):
        parser.error("问题或讨论开关需要配合 --reading-mode")
    try:
        task = PanelTask(
            reading_mode=args.reading_mode, focus_questions=args.focus_question,
            discussion_enabled=not args.no_discussion,
        ) if args.reading_mode else None
    except SchemaError:
        parser.error("试读任务无效：定向模式需一到两个非空问题，每条最多300字；自然模式不带问题")
    inputs = load_inputs(args.database, args.workspace_id, panel_task=task)
    sizes = [len("".join(selection_prompt(item)).encode("utf-8")) for item in inputs]
    if not args.live:
        print(json.dumps({"candidateCount": len(inputs[0].candidates), "inputBytes": sizes,
                          "topics": CASES, "modelCalls": 0,
                          "panelTask": task.model_dump(by_alias=True) if task else None,
                          "inputHashes": [selection_input_hash(item) for item in inputs]},
                         ensure_ascii=False, indent=2))
        return 0
    if args.output is None:
        parser.error("--live 必须指定新的 --output 目录")
    settings = replace(Settings.from_environment(), model_provider="qwen")
    if not settings.qwen_api_key:
        parser.error("未配置 Qwen 密钥")
    args.output.mkdir(parents=True, exist_ok=False)
    reports = asyncio.run(check(RealReaderSelectionProvider(ModelCallService(settings)), inputs))
    report = {"provider": "qwen", "configuredModel": settings.qwen_model,
              "authoredTestTopics": True, "requiresSemanticReview": True, "cases": reports}
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    print(json.dumps({"report": str(args.output / "report.json"),
                      "statuses": [row["status"] for row in reports],
                      "requestAttempts": sum(row["requestAttempted"] for row in reports),
                      "configuredModel": settings.qwen_model}, ensure_ascii=False))
    return 1 if any(row["status"] == "failed" for row in reports) else 0


if __name__ == "__main__":
    raise SystemExit(main())
