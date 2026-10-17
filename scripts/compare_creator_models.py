"""Read-only writer regression using frozen review receipts.

Preview is free; DeepSeek alone is the default. --provider both explicitly
opts into paired comparison. --live runs each selected provider/case once.
--fact-edit explicitly adds the diagnostic statement/editor experiment (up to 24 calls).
Does not create sessions or change defaults.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import sys
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.config import Settings, load_env_file_defaults  # noqa: E402
from app.models import ModelOperation  # noqa: E402
from app.services.content_collaboration import CollaborationMessage  # noqa: E402
from app.services.content_collaboration_provider import (  # noqa: E402
    RealContentCollaborationProvider,
)
from app.services.model_calls import ModelCallService  # noqa: E402

OPERATION = ModelOperation.CONTENT_COLLABORATION_TURN


def digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


def load_frozen_cases(path: Path) -> tuple[list[dict], str]:
    """Accept four explicit offline cases, never an unbounded batch."""
    document = json.loads(path.read_text(encoding="utf-8"))
    cases = document.get("cases") if isinstance(document, dict) else None
    expected = ["initial", "revision", "confirmed", "local"]
    if not isinstance(cases, list) or [case.get("id") for case in cases
                                       if isinstance(case, dict)] != expected or len(cases) != 4:
        raise ValueError("Expected exactly four ordered comparison cases")
    for case in cases:
        context = case.get("context", {})
        if not isinstance(context, dict) or context.get("assistantMode") != "single_writer":
            raise ValueError("Only frozen single-writer contexts are supported")
        message = CollaborationMessage.model_validate(context.get("receivedMessage"))
        if message.sender != "creator" or message.to != "writing":
            raise ValueError("Each case must be an explicit creator request to writing")
    return cases, digest(document)


def make_cases(receipts: dict) -> list[dict]:
    sessions = [s for s in receipts["sessions"] if any(
        m.get("context_snapshot", {}).get("specialistInput", {}).get("assistantMode")
        == "single_writer" for m in s["messages"]
    ) and len(s["topic"]["body"]) > 0]
    if len(sessions) != 1:
        raise ValueError("Choose receipts containing one manually saved review session")
    session = sessions[0]
    responses = [m for m in session["messages"] if m["sender_role"] == "writing"]
    first = deepcopy(responses[0]["context_snapshot"]["specialistInput"])
    followup = deepcopy(responses[-1]["context_snapshot"]["specialistInput"])

    def current(context: dict, case_id: str, request: str, *, keep_history=False) -> dict:
        context = deepcopy(context)
        old_id = context["receivedMessage"]["id"]
        message = CollaborationMessage(id=f"eval-qsfacts-{case_id}", sender="creator",
                                       to="writing", content=request).model_dump()
        context["receivedMessage"] = message
        context["transcript"] = ([item for item in context["transcript"]
                                  if item["id"] != old_id] if keep_history else []) + [message]
        context["upstreamCandidates"] = []
        context.pop("writingFocus", None)
        context["sessionContext"].pop("writingFocus", None)
        return context

    initial = current(first, "initial", first["receivedMessage"]["content"])
    revision = current(followup, "revision", (
        "上一版的大方向可以：还是围绕三件能查证的事。请重写成约500字，开头更自然，"
        "保留自问但不替人决定的口吻。只使用原笔记和我明确提供的事实，旧稿里的具体日期、"
        "读者条件、学校要求都不算我确认过的材料。"
    ), keep_history=True)
    confirmed = current(first, "confirmed", (
        "这一轮只写约250字的开头，不写整篇。请保留原笔记明确写过的两点：爸爸的MBA毕业于MIT，"
        "因此支持我换环境读书；我明确毕业后的第一步是就业。把这两点放回‘先看资源和目标，"
        "再比较保研和出国’的判断里。不要写成靠家庭背景就该出国，也不要把爸爸经历写成我的录取结果；"
        "其他没有提供的经历和日期不要补。"
    ))
    confirmed["target"] = {**confirmed["target"], "title": "先看资源和目标，再比较路径", "body": ""}
    local = current(first, "local", (
        "只精修我选中的开头这一段，让自问口吻更自然、少一点说明书感。保留原来的意思和事实，"
        "不要改后面三件事，也不要加新的时间、经历或学校条件。只给可替换的这一段。"
    ))
    target = {**local["target"], "title": session["topic"]["title"],
              "body": session["topic"]["body"]}
    local["target"] = target
    opening = target["body"].split("\n\n")[0]
    local["writingFocus"] = {"baseTitle": target["title"], "baseBody": target["body"],
                             "selection": {"start": 0, "end": len(opening.encode("utf-16-le")) // 2,
                                           "text": opening}}
    return [
        {"id": "initial", "label": "无旧稿首稿", "context": initial,
         "focus": "没有日期不能补日期；三件查证动作与自然口吻兼顾"},
        {"id": "revision", "label": "错误旧稿续写", "context": revision,
         "focus": "沿用行动思路不等于确认旧稿中的日期、经历或读者条件"},
        {"id": "confirmed", "label": "明确事实保留", "context": confirmed,
         "focus": "保留爸爸MIT MBA、作者先就业；不串主体，不因保守而删光真实素材"},
        {"id": "local", "label": "局部精修", "context": local,
         "focus": "只返回选段，改善语感但不补故事、不重写整篇"},
    ]


def packet_for(case: dict, service: ModelCallService) -> tuple[dict, dict]:
    provider = RealContentCollaborationProvider(service)
    context = case["context"]
    message = CollaborationMessage.model_validate(context["receivedMessage"])
    sources = provider._allowed_sources(context)
    sources = provider._sources_for_role(role="writing", message=message,
                                        context=context, sources=sources)
    return provider._model_context(role="writing", message=message, context=context,
                                   sources=sources), sources


def scrub(value: str, settings: Settings) -> str:
    for secret in (settings.qwen_api_key, settings.deepseek_api_key, settings.anthropic_api_key):
        if secret:
            value = value.replace(secret, "[REDACTED]")
    return value


async def generate(case: dict, provider_name: str, settings: Settings, output: Path,
                   *, edit_facts: bool = False) -> dict:
    settings = replace(settings, model_provider=provider_name)
    count = 0

    def before_request():
        nonlocal count
        count += 1
        if count > (3 if edit_facts else 1):
            raise RuntimeError("Comparison request budget exceeded")

    service = ModelCallService(settings, before_request=before_request)
    packet, sources = packet_for(case, service)
    system, user = service._build_prompt(OPERATION, packet)
    messages = service._compatible_messages(OPERATION, packet, system, user)
    record = {"case": case["id"], "provider": provider_name, "label": case["label"],
              "messages": messages, "inputHash": digest(messages), "packet": packet,
              "semanticStatus": "not_reviewed", "rawContent": None}

    async def capture(response):
        await response.aread()
        try:
            body = response.json()
            choice = body.get("choices", [])[0]
            prefix = ""
            if count > 1:
                payload = json.loads(response.request.content)
                last_message = json.loads(payload["messages"][-1]["content"])
                prefix = "creatorStatements" if "creatorMessages" in last_message else "factEdit"
            record[f"{prefix}RawContent" if prefix else "rawContent"] = (
                choice.get("message", {}).get("content")
            )
            record[f"{prefix}FinishReason" if prefix else "finishReason"] = (
                choice.get("finish_reason")
            )
        except (ValueError, IndexError, AttributeError, TypeError):
            # Do not save arbitrary HTTP errors, headers, or reasoning blocks.
            pass

    factory_name = "_qwen_client" if provider_name == "qwen" else "_deepseek_client"
    original_factory = getattr(service, factory_name)

    def recorded_client(operation):
        client = original_factory(operation)
        client.event_hooks["response"].append(capture)
        return client

    setattr(service, factory_name, recorded_client)
    start = time.monotonic()
    try:
        result = await service.call_operation(OPERATION, packet)
        if edit_facts:
            call_once = (service._call_deepseek if provider_name == "deepseek"
                         else service._call_qwen)
            result = await service.edit_creator_facts(packet, result, call_once=call_once)
        record.update(output=result.output, modelMetadata=result.model_metadata,
                      status="returned")
        try:
            wire, ignored_outer_fields = RealContentCollaborationProvider._parse_output(
                result.output, single_writer=True,
            )
            if wire.turn.next_recipient != "creator":
                raise ValueError("Single writer must reply to the creator")
            RealContentCollaborationProvider._validate_turn(
                role="writing", turn=wire.turn, sources=sources,
                upstream_candidates=[], single_writer=True,
            )
            record["contractStatus"] = "passed"
            if ignored_outer_fields:
                record["outputNormalization"] = {"ignoredOuterFields": ignored_outer_fields}
        except Exception as error:
            record["contractStatus"] = "failed"
            record["contractErrorType"] = type(error).__name__
    except Exception as error:
        record.update(status="failed", errorType=type(error).__name__)
    record["seconds"] = round(time.monotonic() - start, 3)
    record["requestCount"] = count
    output.joinpath(f"{case['id']}-{provider_name}.json").write_text(
        scrub(json.dumps(record, ensure_ascii=False, indent=2), settings), encoding="utf-8",
    )
    summary = {key: record.get(key) for key in ("case", "provider", "status", "contractStatus",
                                               "inputHash", "seconds", "requestCount")}
    summary["model"] = record.get("modelMetadata", {}).get("model")
    summary["tokens"] = record.get("modelMetadata", {}).get("usage", {}).get("total_tokens")
    print(json.dumps(summary, ensure_ascii=False), flush=True)
    return summary


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--receipts", type=Path)
    inputs.add_argument("--cases", type=Path,
                        help="Four frozen offline contexts; no product writes")
    parser.add_argument("--env-root", type=Path,
                        help="Existing env location; never copied to outputs")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--fact-edit", action="store_true",
                        help="Explicit diagnostic editing, not the product default")
    parser.add_argument("--provider", choices=("deepseek", "qwen", "both"), default="deepseek")
    parser.add_argument("--case", action="append", dest="selected_cases",
                        choices=("initial", "revision", "confirmed", "local"))
    args = parser.parse_args()
    if args.env_root:
        load_env_file_defaults(args.env_root / ".env.local")
        load_env_file_defaults(args.env_root / "backend/.env.local")
    settings = Settings.from_environment()
    if args.cases:
        cases, input_hash = load_frozen_cases(args.cases)
    else:
        receipts = json.loads(args.receipts.read_text(encoding="utf-8"))
        cases, input_hash = make_cases(receipts), digest(receipts)
    if args.selected_cases:
        if len(set(args.selected_cases)) != len(args.selected_cases):
            parser.error("Duplicate cases are not allowed")
        cases = [case for case in cases if case["id"] in args.selected_cases]
    providers = ("qwen", "deepseek") if args.provider == "both" else (args.provider,)
    manifest = {"schemaVersion": "creator-model-comparison/v1", "cases": cases,
                "inputReceiptHash": input_hash, "providers": list(providers),
                "requestsPlanned": len(cases) * len(providers),
                "maxRequestsIncludingFactEdit": (3 if args.fact_edit else 1)
                * len(cases) * len(providers), "diagnosticFactEdit": args.fact_edit,
                "parameters": {"temperature": 0.3, "maxTokens": 1800,
                               "deepseekThinking": "disabled", "qwenThinking": "existing config"}}
    if not args.live:
        print(json.dumps({"requestCount": 0, "requestsPlanned": manifest["requestsPlanned"],
                          "maxRequestsIncludingFactEdit": manifest["maxRequestsIncludingFactEdit"],
                          "providers": list(providers), "cases": [
            {"id": c["id"], "focus": c["focus"],
             "request": c["context"]["receivedMessage"]["content"]} for c in cases
        ]}, ensure_ascii=False, indent=2))
        return
    keys = {"qwen": settings.qwen_api_key, "deepseek": settings.deepseek_api_key}
    if any(not keys[provider].strip() for provider in providers):
        raise SystemExit("Selected providers must be configured; no request made")
    if args.output is None or args.output.exists():
        raise SystemExit("Choose a new output directory; existing experiments are not overwritten")
    args.output.mkdir(parents=True)
    args.output.joinpath("manifest.json").write_text(
        scrub(json.dumps(manifest, ensure_ascii=False, indent=2), settings), encoding="utf-8",
    )
    summaries = []
    for case in cases:
        extra = {"edit_facts": True} if args.fact_edit else {}
        pair = await asyncio.gather(*(generate(case, provider, settings, args.output, **extra)
                                      for provider in providers))
        if len({item["inputHash"] for item in pair}) != 1:
            raise RuntimeError("Paired inputs differ; stopping remaining calls")
        summaries.extend(pair)
    args.output.joinpath("summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, indent=2),
    )


if __name__ == "__main__":
    asyncio.run(main())
