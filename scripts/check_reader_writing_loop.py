"""Opt-in four-account reader → local revision → same-reader check; no product writes."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings  # noqa: E402
from app.models import ContentWritingFocus, ModelOperation, PanelTask  # noqa: E402
from app.services.content_collaboration import CollaborationMessage  # noqa: E402
from app.services.content_collaboration_provider import (  # noqa: E402
    RealContentCollaborationProvider,
)
from app.services.model_calls import ModelCallService  # noqa: E402
from app.services.panel_interviews import InterviewReply, RealPanelInterviewProvider  # noqa: E402
from app.services.panel_reading import compact_reader, resolve_reaction_anchor  # noqa: E402
from app.workflows.audience_simulation import (  # noqa: E402
    PersonaDefinition,
    PersonaReactionResult,
    validate_trigger_quote,
)

DEFAULT_MANIFEST = ROOT / "data/evals/four-accounts-20261006/manifest.json"
DEFAULT_PRIOR = ROOT / "data/evals/four-accounts-20261006/recovered/report.json"
MAX_REQUESTS = 16
MAX_ACCOUNT_REQUESTS = 4
PLAN = {
    "QSheep 的工作区": (
        ("d112f0e3-9475-4c4e-996e-a04063217d78", "9902e36d-079d-49de-84af-edaaad3b7a08"),
        "经历共鸣与课程兴趣，不强改为教程",
    ),
    "秀才加点冰 的工作区": (
        ("18eb9c07-2c94-40a2-9bcb-228761c8954f", "19c20876-f987-465b-908d-d5441fd10192"),
        "文化理解入口；检查既有近义人物是否重复",
    ),
    "Ag 的工作区": (("4", "3"), "平台限制与技术路径判断，不替作者补技术事实"),
    "一粒鱼 的工作区": (
        ("ab84ad5d-fdb0-4809-9784-10fdbea90287", "600421f6-bf1a-4604-a3ab-d3e244167e8b"),
        "跨专业依据与选校对照，不自拟招生条件",
    ),
}
QUALITY_RUBRIC = {
    "readerPerspective": "两人的判断是否各自符合人物和作品；是否有真实不同角度，而非同义复述。",
    "historyParroting": "是否机械复述旧评论；本轮不向模型提供历史原评论。",
    "authorVoice": "是否保留原稿的观点、口气和分享目的，而非统一变成教程。",
    "unsupportedFacts": "是否新增原稿不存在的事实、经历、数字、承诺或功能。",
    "readerUpdate": "复看是否针对实际改动更新判断；允许仍不同意或表示没有解决。",
    "usefulness": "修改是否确实改善原关切，而非仅换同义词或改成更长的解释。",
}


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def select_plan(account_names, plan=PLAN):
    """An explicit subset never resumes or silently re-runs an earlier report."""
    if account_names is None:
        return plan
    if not account_names or len(account_names) != len(set(account_names)):
        raise ValueError("账号名单不能为空或重复")
    if any(name not in plan for name in account_names):
        raise ValueError("账号名称不在冻结计划中，请使用完整名称")
    return {name: plan[name] for name in account_names}


def prepare_cases(manifest, prior, plan=PLAN):
    """Use frozen readers only; never silently pick or generate replacement people."""
    prior_ids = {a["workspaceId"] for a in prior.get("accounts", [])}
    subset_manifest = {
        **manifest,
        "accounts": [a for a in manifest["accounts"] if a["workspaceId"] in prior_ids],
    }
    if prior.get("manifestHash") not in {fingerprint(manifest), fingerprint(subset_manifest)}:
        raise ValueError("旧报告不属于这份冻结清单")
    accounts = {a["name"]: a for a in manifest["accounts"]}
    previous = {a["workspaceId"]: a for a in prior.get("accounts", [])}
    result = []
    if len(plan) > 4:
        raise ValueError("本批最多四个账号")
    for name, (reader_ids, rationale) in plan.items():
        if len(reader_ids) != 2 or len(set(reader_ids)) != 2:
            raise ValueError("每账号需固定两位不同的既有读者")
        account = accounts[name]
        readers = account.get("readers") or previous.get(account["workspaceId"], {}).get(
            "readers", []
        )
        selected = []
        for reader_id in reader_ids:
            reader = next((p for p in readers if p.get("id") == reader_id), None)
            if reader is None:
                raise ValueError("冻结读者缺失，不自动生成人物")
            selected.append(PersonaDefinition.model_validate(reader).model_dump(by_alias=True))
        case = next(c for c in account["cases"] if c["role"] == "primary")
        if not case.get("body", "").strip():
            raise ValueError("冻结笔记缺少正文")
        if case.get("sourceHash") != fingerprint({"title": case["title"], "body": case["body"]}):
            raise ValueError("冻结笔记指纹不符")
        result.append(
            {
                "name": name,
                "workspaceId": account["workspaceId"],
                "case": deepcopy(case),
                "readers": [compact_reader(reader, include_history=False) for reader in selected],
                "readerOrigin": "saved_asset" if account.get("readers") else "prior_check_only",
                "readerSnapshotHash": fingerprint(selected),
                "selectionRationale": rationale,
                "historicalCommentsForLocalAudit": {
                    reader["id"]: [
                        e.get("observedComment") or e.get("evidenceQuote") or ""
                        for e in reader.get("observedEpisodes", [])
                    ]
                    for reader in selected
                },
            }
        )
    return result


def choose_selection(body, trigger_quote):
    """Select a literal sentence at the reader anchor (Python/codepoint offsets)."""
    anchor = body.find(trigger_quote) if trigger_quote else -1
    anchor = max(anchor, 0)
    end_anchor = anchor + len(trigger_quote) if trigger_quote and trigger_quote in body else anchor
    boundaries = list(re.finditer(r"[。！？\n]", body))
    start = max((m.end() for m in boundaries if m.end() <= anchor), default=0)
    end = next(
        (m.end() for m in boundaries if m.end() >= end_anchor and m.end() > start), len(body)
    )
    # Short public anchors can still point into very long paragraphs.
    if end - start > 800:
        start, end = anchor, min(len(body), max(end_anchor, anchor + 400))
    return {"start": start, "end": end, "text": body[start:end]}


def splice(body, selection, replacement):
    start, end = selection["start"], selection["end"]
    if not (0 <= start < end <= len(body)) or body[start:end] != selection["text"]:
        raise ValueError("所选文字与冻结正文不一致")
    revised = body[:start] + replacement + body[end:]
    return revised, {
        "nonTargetCharactersUnchanged": (
            revised[:start] == body[:start] and revised[start + len(replacement) :] == body[end:]
        ),
        "replacementIsDifferent": replacement != selection["text"],
        "offsetUnit": "unicode_codepoint",
    }


class RecordingCalls:
    """Audit the actual provider packet and count HTTP attempts before dispatch."""

    def __init__(self, service, report, save):
        self.service, self.report, self.save = service, report, save
        self.settings = service.settings
        self.account = None
        self.stage = ""
        self.entry = None
        self.real_service = isinstance(service, ModelCallService)
        if self.real_service:
            service.before_request = self.before_request

    def before_request(self):
        if (
            self.report["requestAttempts"] >= self.report["maxRequests"]
            or self.account["requestAttempts"] >= MAX_ACCOUNT_REQUESTS
        ):
            raise ValueError("实际 HTTP 请求达到本批或本账号预算")
        self.report["requestAttempts"] += 1
        self.account["requestAttempts"] += 1
        self.entry["requestCount"] += 1
        self.save(self.report)

    async def call_operation(self, operation, context):
        entry = {
            "stage": self.stage,
            "operation": operation.value,
            "context": deepcopy(context),
            "contextHash": fingerprint(context),
            "requestCount": 0,
            "status": "running",
        }
        self.entry = entry
        self.account["calls"].append(entry)
        if hasattr(self.service, "_build_prompt"):
            system, user = self.service._build_prompt(operation, context)
            entry.update(
                systemPromptHash=hashlib.sha256(system.encode()).hexdigest(),
                userPromptHash=hashlib.sha256(user.encode()).hexdigest(),
            )
        self.save(self.report)
        start = time.monotonic()
        try:
            if not self.real_service:
                self.before_request()
            response = await self.service.call_operation(operation, context)
            entry.update(
                status="completed",
                output=response.output,
                metadata={
                    k: v
                    for k, v in response.model_metadata.items()
                    if k in {"provider", "model", "usage", "systemPromptHash", "requestCount"}
                },
            )
            return response
        except Exception as error:
            entry.update(status="failed", errorType=type(error).__name__)
            raise
        finally:
            entry["elapsedSeconds"] = round(time.monotonic() - start, 3)
            self.save(self.report)


async def check(cases, service, save=lambda report: None):
    """One pass only. Any failure stops this batch; no retries or semantic retries."""
    if len(cases) > 4:
        raise ValueError("本批最多四个账号")
    report = {
        "version": "reader-writing-loop/v1",
        "casesHash": fingerprint(cases),
        "maxRequests": min(MAX_REQUESTS, len(cases) * MAX_ACCOUNT_REQUESTS),
        "maxRequestsPerAccount": MAX_ACCOUNT_REQUESTS,
        "requestAttempts": 0,
        "accounts": [],
        "status": "running",
        "semanticStatus": "not_reviewed",
        "qualityRubric": QUALITY_RUBRIC,
        "limitations": [
            "每账号仅两位固定旧读者，不能代表完整受众或验收 retrieval。",
            "非盲测；只看文字，没有图片。",
            "已发布笔记仅复制为临时草稿做改写实验，正式笔记不变。",
            "既有人物可能有旧版话题化偏差，本批不生成人物。",
        ],
    }
    calls = RecordingCalls(service, report, save)
    writer = RealContentCollaborationProvider(calls)
    interviewer = RealPanelInterviewProvider(calls)
    for case in cases:
        row = {
            "name": case["name"],
            "workspaceId": case["workspaceId"],
            "sourceNoteId": case["case"]["noteId"],
            "readers": deepcopy(case["readers"]),
            "readerOrigin": case["readerOrigin"],
            "readerSnapshotHash": case["readerSnapshotHash"],
            "selectionRationale": case["selectionRationale"],
            "requestAttempts": 0,
            "status": "running",
            "calls": [],
            "qualityReview": {
                key: {"status": "not_reviewed", "notes": ""} for key in QUALITY_RUBRIC
            },
        }
        report["accounts"].append(row)
        calls.account = row
        original = case["case"]
        target = {
            "targetType": "topic",
            "simulationCategory": "creation",
            "previewLevel": "text_draft",
            "title": original["title"],
            "body": original["body"],
            "panelTask": PanelTask(discussion_enabled=False).model_dump(by_alias=True),
            "limitations": "只给已保存文字的临时草稿；未看图片，不代表原图文全部内容。",
        }
        row["original"] = deepcopy(target)
        try:
            reactions = []
            row["reactions"] = reactions
            for index, reader in enumerate(case["readers"]):
                calls.stage = f"independent_reading:{index + 1}"
                response = await calls.call_operation(
                    ModelOperation.SIMULATION_REACTION, {"persona": reader, "topic": target}
                )
                reaction = PersonaReactionResult.model_validate(
                    resolve_reaction_anchor(response.output, target)
                ).reaction.model_dump()
                if reaction["personaId"] != reader["id"]:
                    raise ValueError("独立试读人物错配")
                validate_trigger_quote(reaction["triggerQuote"], target)
                reactions.append(reaction)
            reaction = next(
                (r for r in reactions if r["action"] == "comment" and r["quote"].strip()), None
            )
            if reaction is None:
                row["status"] = "no_public_feedback"
                save(report)
                continue  # Never turn a private concern into a public reader message.
            reader = next(r for r in case["readers"] if r["id"] == reaction["personaId"])
            row["selectedReaderId"] = reader["id"]
            quote = reaction["quote"].strip()
            row["localHistoryAudit"] = {
                "exactPriorCommentReuse": any(
                    text.strip() and text.strip() in quote
                    for text in case.get("historicalCommentsForLocalAudit", {}).get(
                        reader["id"], []
                    )
                ),
                "semanticStatus": "not_reviewed",
            }
            selection = choose_selection(original["body"], reaction["triggerQuote"])
            reference = {
                "simulationId": f"eval:{original['noteId']}",
                "stage": "initial",
                "messageId": f"initial:{reader['id']}",
            }
            focus = {
                "baseTopicId": f"eval:{original['noteId']}",
                "baseTitle": original["title"],
                "baseBody": original["body"],
                "baseUpdatedAt": "2026-10-06T00:00:00Z",
                "selection": selection,
                "readerReference": reference,
                "readerMessage": {
                    "personaId": reader["id"],
                    "senderName": reader["name"],
                    "content": quote,
                    "sourceTarget": deepcopy(target),
                    "sourceUpdatedAt": "2026-10-06T00:00:00Z",
                    "sourceKind": "simulated_reader_opinion",
                },
            }
            row["writingFocus"] = focus
            row["writingFocusRequest"] = {
                "expectedUpdatedAt": focus["baseUpdatedAt"],
                "selection": selection,
                "readerReference": reference,
            }
            ContentWritingFocus.model_validate(row["writingFocusRequest"])
            message = CollaborationMessage(
                id=f"eval-writing:{original['noteId']}",
                sender="creator",
                to="writing",
                content="请基于所附读者公开意见，只改 writingFocus.selection 的选中文字。"
                "保留原稿观点、个人口气和事实，不补编经历、产品功能、数据、剧情或招生条件。"
                "确实值得改时给一条 copy_option，body 只含可替换所选片段的正文。"
                "读者仅认可原文时可以保留不改；不够事实时请给 open_question。"
                "缺少事实时保留真实的不确定性，不把追问当成已获答案。",
            )
            writer_context = {
                "target": {
                    "assetType": "topic",
                    "assetId": focus["baseTopicId"],
                    "title": original["title"],
                    "body": original["body"],
                },
                "writingFocus": focus,
                "transcript": [message.model_dump()],
                "transcriptTruncated": False,
            }
            calls.stage = "focused_revision"
            turn = await writer.run(role="writing", message=message, context=writer_context)
            candidates = [
                c
                for c in turn.model_metadata.get("candidateSuggestions", [])
                if c.get("kind") == "copy_option"
            ]
            if not candidates:
                suggestions = turn.model_metadata.get("candidateSuggestions", [])
                row["writingTurn"] = {
                    **turn.model_dump(exclude={"model_metadata"}),
                    "candidateSuggestions": suggestions,
                }
                row["status"] = (
                    "needs_creator"
                    if any(c.get("kind") == "open_question" for c in suggestions)
                    else "no_rewrite"
                )
                continue
            if len(candidates) > 1:
                raise ValueError("预期恰好一条 copy_option，不自动重写或挑选多方案")
            replacement = candidates[0]["body"]
            revised, structural = splice(original["body"], selection, replacement)
            row.update(
                replacement=replacement,
                revised={**target, "body": revised},
                structuralChecks=structural,
                writingTurn={
                    **turn.model_dump(exclude={"model_metadata"}),
                    "candidateSuggestions": candidates,
                },
            )
            calls.stage = "same_reader_revisit"
            response = await interviewer.reply(
                {
                    "reader": reader,
                    "participants": [{"id": reader["id"], "name": reader["name"]}],
                    "target": {**target, "body": revised},
                    "publicHistory": [
                        {"role": "reader", "senderName": reader["name"], "content": quote}
                    ],
                    "authorQuestion": "我调整了刚才的稿子。请再读当前版本：你上一条留言在意的点"
                    "是否改变了？直接说变在哪里或仍没解决什么，不必为了鼓励我改口。",
                }
            )
            row["revisit"] = InterviewReply.model_validate(response.output).reply
            row["status"] = "completed_unreviewed"
        except Exception as error:
            row.update(status="failed", errorType=type(error).__name__)
            report["status"] = "stopped_on_failure"
            break
        finally:
            save(report)
    if report["status"] == "running":
        report["status"] = "completed_unreviewed"
    save(report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--prior-report", type=Path, default=DEFAULT_PRIOR)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--accounts", nargs="+", help="只检查列出的完整账号名称，不重复已运行账号")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    prior = json.loads(args.prior_report.read_text())
    try:
        cases = prepare_cases(manifest, prior, select_plan(args.accounts))
    except ValueError as error:
        parser.error(str(error))
    preview = {
        "mode": "dry_run",
        "maxRequests": min(MAX_REQUESTS, len(cases) * MAX_ACCOUNT_REQUESTS),
        "accounts": [
            {
                "name": c["name"],
                "noteId": c["case"]["noteId"],
                "readerNames": [reader["name"] for reader in c["readers"]],
                "bodyCharacters": len(c["case"]["body"]),
                "readerOrigin": c["readerOrigin"],
            }
            for c in cases
        ],
    }
    if not args.live:
        print(json.dumps(preview, ensure_ascii=False))
        return
    if not args.output or args.output.exists():
        parser.error("真实验证需要全新的 --output 目录，不覆盖或恢复旧报告")
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / "data/evals").resolve()):
        parser.error("报告只能写入忽略的 data/evals 子目录")
    settings = Settings.from_environment()
    if not settings.has_text_model_credentials:
        parser.error("未配置所选文字模型的密钥，不切换其他模型提供商")
    output.mkdir(parents=True, exist_ok=False)
    destination = output / "report.json"

    def save(report):
        destination.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    report = asyncio.run(check(cases, ModelCallService(settings), save))
    print(
        json.dumps(
            {
                "report": str(destination),
                "status": report["status"],
                "requestAttempts": report["requestAttempts"],
                "accounts": [
                    {"name": a["name"], "status": a["status"]} for a in report["accounts"]
                ],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
