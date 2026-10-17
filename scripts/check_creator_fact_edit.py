"""Replay one saved draft through the production local factual editor.

Zero calls without --live. Two DeepSeek requests maximum, no new generation,
product database, retries, replacement fixtures or silent receipt overwrites.
"""

import argparse
import asyncio
import json
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from compare_creator_models import digest, load_frozen_cases, packet_for, scrub

from app.config import Settings, load_env_file_defaults
from app.models import ModelCallResponse
from app.services.content_collaboration_provider import RealContentCollaborationProvider
from app.services.creator_fact_edit import draft_units
from app.services.model_calls import ModelCallService


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--case", choices=("initial", "revision", "confirmed", "local"),
                        required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--env-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    cases, _ = load_frozen_cases(args.cases)
    case = next(row for row in cases if row["id"] == args.case)
    frozen = json.loads(args.receipt.read_text())
    if frozen.get("case") != args.case or frozen.get("provider") != "deepseek":
        parser.error("Choose a DeepSeek receipt of the same case")
    old_sources = frozen.get("packet", {}).get("evidence", {}).get("allowedSources")
    original = frozen.get("modelMetadata", {}).get("factEdit", {}).get(
        "originalOutput", frozen.get("output"),
    )
    if not isinstance(original, dict):
        parser.error("Receipt has no complete saved generation")
    load_env_file_defaults(args.env_root / ".env.local")
    load_env_file_defaults(args.env_root / "backend/.env.local")
    settings = replace(Settings.from_environment(), model_provider="deepseek")
    count = 0

    def before_request():
        nonlocal count
        count += 1
        if count > 2:
            raise RuntimeError("Replay permits author statements plus one fact edit")

    service = ModelCallService(settings, before_request=before_request)
    packet, sources = packet_for(case, service)
    if (packet["evidence"]["allowedSources"] != old_sources
            or packet["conversation"] != frozen.get("packet", {}).get("conversation")):
        parser.error("Receipt sources or dialogue differ from this frozen case")
    if not draft_units(original):
        parser.error("Receipt contains no editable copy candidate")
    if not args.live:
        print(json.dumps({"case": args.case, "requestCount": 0, "requestsPlanned": 2,
                          "savedDraftHash": digest(original)}, ensure_ascii=False))
        return
    if not settings.deepseek_api_key.strip() or args.output is None or args.output.exists():
        parser.error("Configure DeepSeek and choose a new output file")
    start = time.monotonic()
    stages = []

    async def captured_call(operation, context, *, review_prompt):
        stage = {"messages": [{"role": "system", "content": review_prompt[0]},
                              {"role": "user", "content": review_prompt[1]}]}
        stages.append(stage)
        stage_start = time.monotonic()
        try:
            response = await service._call_deepseek(operation, context, review_prompt=review_prompt)
            stage.update(output=response.output, modelMetadata=response.model_metadata)
            return response
        finally:
            stage["seconds"] = round(time.monotonic() - stage_start, 3)

    result = await service.edit_creator_facts(packet, ModelCallResponse(
        output=deepcopy(original), model_metadata={"requestCount": 0, "usage": {},
                                                 "model": settings.deepseek_model},
    ), call_once=captured_call)
    contract = "passed"
    try:
        wire, _ = RealContentCollaborationProvider._parse_output(result.output, single_writer=True)
        if wire.turn.next_recipient != "creator":
            raise ValueError("Single writer must reply to creator")
        RealContentCollaborationProvider._validate_turn(
            role="writing", turn=wire.turn, sources=sources,
            upstream_candidates=[], single_writer=True,
        )
    except Exception:
        contract = "failed"
    record = {"case": args.case, "generationReused": True, "generationReceipt": str(args.receipt),
              "generationReceiptHash": digest(frozen), "originalOutput": original,
              "stages": stages,
              "output": result.output, "modelMetadata": result.model_metadata,
              "seconds": round(time.monotonic() - start, 3), "requestCount": count,
              "contractStatus": contract}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(scrub(json.dumps(record, ensure_ascii=False, indent=2), settings))
    print(json.dumps({"case": args.case, "requestCount": count, "seconds": record["seconds"],
                      "contractStatus": contract,
                      "factEdit": result.model_metadata["factEdit"]["status"],
                      "tokens": result.model_metadata.get("usage", {}).get("total_tokens")},
                     ensure_ascii=False))


if __name__ == "__main__":
    asyncio.run(main())
