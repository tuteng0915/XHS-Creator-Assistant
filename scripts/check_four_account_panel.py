"""Freeze four saved accounts; opt-in 17-request first-pass panel check, no DB writes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.models import ModelOperation, PanelTask  # noqa: E402
from app.services.audience_analyses import validate_audience_output  # noqa: E402
from app.services.audience_evidence import (  # noqa: E402
    audience_context,
    discussion_coverage,
    reader_persona_context,
    select_audience_personas,
)
from app.services.creator_analysis_scope import scope_creator_profile  # noqa: E402
from app.services.editor_feedback import validate_editor_feedback  # noqa: E402
from app.services.model_calls import ModelCallService  # noqa: E402
from app.services.panel_quality import prepare_review  # noqa: E402
from app.services.panel_reading import resolve_reaction_anchor  # noqa: E402
from app.services.reader_selection import (  # noqa: E402
    ReaderCandidate,
    ReaderSelectionInput,
    validate_reader_selection,
)
from app.services.simulated_fans import FanDefinition, SimulatedFanService  # noqa: E402
from app.workflows.audience_simulation import (  # noqa: E402
    PersonaDefinition,
    PersonaReactionResult,
    SimulationSynthesisResult,
    validate_trigger_quote,
)

PLAN = {
    "QSheep 的工作区": ("6a6e309f000000002500fd86", "6a9c346a000000002601a8c7"),
    "秀才加点冰 的工作区": ("6a7c1b5e000000002500676a", "6ab0e8540000000033033fee"),
    "Ag 的工作区": ("6aba9d6e000000001b01dad6", "69c533b5000000001e00d19b"),
    "一粒鱼 的工作区": ("69f2a75f00000000220254f9", "6a6b8df2000000003300eeda"),
}


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def freeze(database: Path, plan=PLAN):
    connection = sqlite3.connect(database.resolve(strict=True).as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("BEGIN")
        accounts = []
        for name, note_ids in plan.items():
            rows = connection.execute(
                "SELECT * FROM creator_workspaces WHERE name=?", (name,)
            ).fetchall()
            if len(rows) != 1:
                raise ValueError("档案名称不存在或不唯一")
            workspace_id = rows[0]["id"]
            material = connection.execute(
                "SELECT text_content FROM source_materials WHERE workspace_id=? "
                "AND type='xhs_creator_profile' ORDER BY updated_at DESC LIMIT 1",
                (workspace_id,),
            ).fetchone()
            profile = json.loads(material[0])
            notes = {n["noteId"]: n for n in profile["notes"]}
            cases = []
            for index, note_id in enumerate(note_ids):
                note = notes[note_id]
                if not str(note.get("desc") or "").strip():
                    raise ValueError("测试笔记没有文字正文")
                cases.append(
                    {
                        "noteId": note_id,
                        "role": "primary" if index == 0 else "reserved",
                        "title": note["title"],
                        "body": note["desc"],
                        "sourceHash": fingerprint({"title": note["title"], "body": note["desc"]}),
                    }
                )
            ids = [
                r[0]
                for r in connection.execute(
                    "SELECT id FROM simulated_fans WHERE workspace_id=? AND status='active' "
                    "ORDER BY created_at,id",
                    (workspace_id,),
                )
            ]
            readers = (
                SimulatedFanService(None).snapshots(connection, workspace_id, ids) if ids else []
            )
            readers = [
                PersonaDefinition.model_validate(p).model_dump(by_alias=True) for p in readers
            ]
            account = {
                "name": name,
                "workspaceId": workspace_id,
                "cases": cases,
                "readerOrigin": "saved_assets",
                "readers": readers,
                "sourceNoteCount": len(notes),
                "limitation": "仅保存文字；不含图片。既有人物可能源自测试笔记，非盲测。",
            }
            if not readers:
                training = {
                    **profile,
                    "notes": [n for n in profile["notes"] if n["noteId"] not in note_ids],
                }
                scoped, scope = scope_creator_profile(training, "recent_10")
                account.update(
                    readerOrigin="generated_for_check_only",
                    audienceContext=audience_context({**scoped, "scope": scope}),
                )
            accounts.append(account)
        return {
            "version": "four-accounts/v1",
            "accounts": accounts,
            "sourceDatabaseHash": hashlib.sha256(database.read_bytes()).hexdigest(),
            "maxRequests": 17,
            "discussionEnabled": False,
        }
    finally:
        connection.close()


async def check(manifest, service, save=lambda report: None, previous=None, case_role="primary"):
    if case_role not in {"primary", "reserved"}:
        raise ValueError("未知样本组")
    if previous and previous.get("caseRole", "primary") != case_role:
        raise ValueError("恢复报告属于另一组样本")
    report = {
        "manifestHash": fingerprint(manifest),
        "caseRole": case_role,
        "calls": [],
        "accounts": [],
        "semanticStatus": "not_reviewed",
        "maxRequests": 17,
    }
    cached = {
        (c["operation"], fingerprint(c["context"])): c for c in (previous or {}).get("calls", [])
    }
    previous_attempts = (previous or {}).get("requestAttempts", len(cached))
    report["previousRequestAttempts"] = previous_attempts
    if previous:
        report["reusedReportHash"] = fingerprint(previous)

    def attempts():
        return sum(c.get("requestCount", int(c.get("requestAttempted", False)))
                   for c in report["calls"])

    def before_request():
        if previous_attempts + attempts() >= 17:
            raise ValueError("含独立核对在内的实际请求预算已用完")
        entry = report["calls"][-1]
        entry["requestCount"] = entry.get("requestCount", 0) + 1
        entry["requestAttempted"] = True
        save(report)

    if isinstance(service, ModelCallService):
        service.before_request = before_request

    async def call(operation, context, label):
        if len(report["calls"]) >= 17:
            raise ValueError("验证请求预算已用完")
        entry = {"label": label, "operation": operation.value, "context": context}
        report["calls"].append(entry)
        save(report)
        start = time.monotonic()
        try:
            prior = cached.get((operation.value, fingerprint(context)))
            if prior is not None:
                entry["reused"] = True
                if "output" not in prior:
                    raise ValueError("上轮未返回成功响应，不自动重试")
                if hasattr(service, "_build_prompt"):
                    system, _ = service._build_prompt(operation, context)
                    if (
                        prior.get("metadata", {}).get("systemPromptHash")
                        != hashlib.sha256(system.encode("utf-8")).hexdigest()
                    ):
                        raise ValueError("模型提示已变化，不混用旧响应或自动重发")
                if isinstance(service, ModelCallService):
                    plan = prepare_review(operation.value, context, prior["output"])
                    if plan and prior.get("metadata", {}).get("panelReview", {}).get(
                        "systemPromptHash"
                    ) != hashlib.sha256(plan.system.encode()).hexdigest():
                        raise ValueError("缓存缺少当前独立核对，不作为新版已验收响应复用")
                entry.update(output=prior["output"], metadata=prior.get("metadata", {}))
                return prior["output"]
            sent = attempts()
            if previous_attempts + sent >= 17:
                raise ValueError("含上轮在内的请求预算已用完")
            if not isinstance(service, ModelCallService):
                entry["requestAttempted"] = True
            response = await service.call_operation(operation, context)
            entry["output"] = response.output
            entry["metadata"] = {
                k: v
                for k, v in response.model_metadata.items()
                if k in {"model", "provider", "usage", "systemPromptHash", "requestCount",
                         "panelReview", "generationUsage"}
            }
            return response.output
        except Exception as error:
            entry["errorType"] = type(error).__name__
            raise
        finally:
            entry["elapsedSeconds"] = round(time.monotonic() - start, 2)
            save(report)

    for account in manifest["accounts"]:
        row = {
            "name": account["name"],
            "workspaceId": account["workspaceId"],
            "readerOrigin": account["readerOrigin"],
            "status": "running",
        }
        report["accounts"].append(row)
        try:
            readers = [
                PersonaDefinition.model_validate(p).model_dump(by_alias=True)
                for p in account["readers"]
            ]
            if not readers:
                raw = await call(
                    ModelOperation.AUDIENCE_ANALYSIS,
                    account["audienceContext"],
                    account["name"] + "/readers",
                )
                result, diagnostics = validate_audience_output(raw, account["audienceContext"])
                row["audienceDiagnostics"] = diagnostics
                readers = [
                    PersonaDefinition.model_validate(p).model_dump(by_alias=True)
                    for p in select_audience_personas(result or {}, limit=None)
                ]
                if not readers:
                    raise ValueError("未生成有效读者，本档案不补造替身")
            row["readers"] = readers
            case = next(c for c in account["cases"] if c["role"] == case_role)
            task = PanelTask(discussion_enabled=False)
            target = {
                "targetType": "topic",
                "previewLevel": "text_draft",
                "title": case["title"],
                "body": case["body"],
                "limitations": account["limitation"],
                "panelTask": task.model_dump(by_alias=True),
            }
            row["topic"] = target
            inputs = ReaderSelectionInput(
                workspace_id=account["workspaceId"],
                account_positioning="",
                target=target,
                candidates=[
                    ReaderCandidate(
                        **FanDefinition.model_validate(p).model_dump(),
                        id=p["id"],
                        updated_at=p.get("updatedAt") or "frozen",
                    )
                    for p in readers
                ],
                desired_count=2,
                panel_task=task,
            )
            raw = await call(
                ModelOperation.READER_SELECTION,
                inputs.model_dump(by_alias=True),
                account["name"] + "/selection",
            )
            selection = validate_reader_selection(raw, inputs)
            row["selection"] = selection.model_dump(by_alias=True)
            if selection.status == "failed":
                raise ValueError("读者推荐无效")
            ids = [r.fan_id for r in selection.proposed_readers]
            row["selectedReaderIds"] = ids
            if not ids:
                row["status"] = "unmatched"
                continue
            # Do not hand the model the tested note's actual comments as its answer.
            excluded = {c["noteId"] for c in account["cases"]}
            personas = []
            for id in ids:
                persona = next(p for p in readers if p["id"] == id)
                persona = {
                    **persona,
                    "observedEpisodes": [
                        e
                        for e in persona.get("observedEpisodes", [])
                        if e["noteId"] not in excluded
                    ],
                }
                personas.append(reader_persona_context(persona, target))
            reactions = []
            row["reactions"] = reactions
            for persona in personas:
                raw = await call(
                    ModelOperation.SIMULATION_REACTION,
                    {"persona": persona, "topic": target},
                    account["name"] + "/reaction/" + persona["id"],
                )
                reaction = PersonaReactionResult.model_validate(
                    resolve_reaction_anchor(raw, target)
                ).reaction.model_dump()
                if reaction["personaId"] != persona["id"]:
                    raise ValueError("人物错配")
                validate_trigger_quote(reaction["triggerQuote"], target)
                reaction.update(messageId=f"initial:{persona['id']}", round=1)
                reactions.append(reaction)
            raw = await call(
                ModelOperation.SIMULATION_SYNTHESIS,
                {
                    "topic": target,
                    "personas": personas,
                    "reactions": reactions,
                    "debateResponses": [],
                    "discussionCoverage": discussion_coverage(
                        personas, reactions, [], enabled=False
                    ),
                },
                account["name"] + "/synthesis",
            )
            row["synthesis"] = SimulationSynthesisResult.model_validate(raw).synthesis.model_dump()
            row["synthesis"].update(
                validate_editor_feedback(
                    raw["synthesis"].get("editorFeedback"),
                    topic=target,
                    personas=personas,
                    reactions=reactions,
                    replies=[],
                )
            )
            row["status"] = "completed"
        except Exception as error:
            row.update(status="failed", errorType=type(error).__name__)
            # A failed account stops locally; another account is a different test, not a retry.
        finally:
            save(report)
    report["requestAttempts"] = attempts()
    save(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data/app.sqlite3")
    parser.add_argument("--freeze", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case-role", choices=["primary", "reserved"], default="primary")
    parser.add_argument(
        "--resume-report",
        type=Path,
        help="仅恢复本地 KeyError 中断账号，复用已返回响应，不重复模型请求",
    )
    args = parser.parse_args()
    if args.freeze:
        if args.live or args.manifest or args.freeze.exists():
            parser.error("冻结清单需新路径，不能同时调用模型")
        manifest = freeze(args.database)
        args.freeze.parent.mkdir(parents=True, exist_ok=True)
        args.freeze.write_text(json.dumps(manifest, ensure_ascii=False, indent=2))
    elif args.manifest:
        manifest = json.loads(args.manifest.read_text())
    else:
        parser.error("请先 --freeze，再用 --manifest 选择冻结清单")
    if not args.live:
        print(
            json.dumps(
                [
                    {
                        "name": a["name"],
                        "readerCount": len(a["readers"]),
                        "cases": [c["title"] for c in a["cases"]],
                    }
                    for a in manifest["accounts"]
                ],
                ensure_ascii=False,
            )
        )
        return
    if not args.output or args.output.exists():
        parser.error("需要新的报告目录")
    settings = Settings.from_environment()
    if not settings.has_text_model_credentials:
        parser.error("未配置所选文字模型的密钥")
    args.output.mkdir(parents=True, exist_ok=False)
    destination = args.output / "report.json"

    def save(report):
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    previous = None
    if args.resume_report:
        previous = json.loads(args.resume_report.read_text())
        if previous["manifestHash"] != fingerprint(manifest):
            parser.error("恢复需使用完全相同的冻结清单")
        failed = {
            a["workspaceId"]
            for a in previous["accounts"]
            if a["status"] == "failed" and a.get("errorType") == "KeyError"
        }
        manifest = {
            **manifest,
            "accounts": [a for a in manifest["accounts"] if a["workspaceId"] in failed],
        }
        if not manifest["accounts"]:
            parser.error("没有可恢复的本地字段错误，不重试模型失败")
    report = asyncio.run(check(manifest, ModelCallService(settings), save, previous=previous,
                               case_role=args.case_role))
    print(
        json.dumps(
            {
                "report": str(destination),
                "requestAttempts": report["requestAttempts"],
                "statuses": [(a["name"], a["status"]) for a in report["accounts"]],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
