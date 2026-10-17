"""Bounded replay: same bad draft, sourced communication, mixed author request.

No new article generation, product database or scraping. Preview: zero calls.
Live: three fixtures, at most six DeepSeek requests, no retries. Positive drafts
are diagnostic fixtures built from a real selected note, not historical outputs.
"""

import argparse
import asyncio
import json
import time
from copy import deepcopy
from dataclasses import replace
from pathlib import Path

from compare_creator_models import digest, scrub

from app.config import Settings, load_env_file_defaults
from app.models import ModelCallResponse
from app.services.content_collaboration_provider import RealContentCollaborationProvider
from app.services.model_calls import ModelCallService


def fixtures(bad, positive):
    original = bad["modelMetadata"]["factEdit"]["originalOutput"]
    packet = deepcopy(positive["packet"])
    note = next(row for row in packet["evidence"]["allowedSources"]
                if row.get("sourceRole") == "source_document")
    quote = "在去年这个阶段，我和家人长聊了几番"
    body = json.loads(note["text"])["result"]["body"]
    if quote not in body:
        raise ValueError("Positive must contain the real saved communication experience")
    candidate = {"turn": {"summary": "诊断样本，不是重新生成文章", "nextRecipient": "creator",
                           "candidateSuggestions": [{"kind": "copy_option",
                               "title": "先把选择想具体", "confidence": "inference",
                               "evidenceRefs": [], "body": (
                                   quote + "。想清楚路径，不能只靠一时的冲动。"
                               )}]}}
    mixed = deepcopy(packet)
    # A diagnostic relocation of an actually sourced statement, not a claim
    # that the real creator sent this message in the product.
    mixed["conversation"] = [{"sourceId": "diagnostic:mixed-author-request", "role": "user",
        "content": "开头回应犹豫的读者。保留这段真实经历：“" + quote +
                   "”。写得直接些，不要只剩抽象建议。"}]
    mixed["evidence"]["allowedSources"] = []
    return [
        {"id": "same_bad_draft", "origin": "unchanged_saved_generation",
         "packet": bad["packet"], "originalOutput": original},
        {"id": "source_communication", "origin": "diagnostic_draft_from_real_note",
         "packet": packet, "originalOutput": candidate, "sourceQuote": quote},
        {"id": "mixed_request_communication", "origin": "diagnostic_relocation_of_real_note_fact",
         "packet": mixed, "originalOutput": deepcopy(candidate), "sourceQuote": quote},
    ]


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bad-receipt", type=Path, required=True)
    parser.add_argument("--positive-receipt", type=Path, required=True)
    parser.add_argument("--env-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    bad = json.loads(args.bad_receipt.read_text())
    positive = json.loads(args.positive_receipt.read_text())
    rows = fixtures(bad, positive)
    if not args.live:
        print(json.dumps({"requestCount": 0, "maxRequestsPlanned": 6,
                          "cases": [{"id": row["id"], "origin": row["origin"],
                                     "draftHash": digest(row["originalOutput"])} for row in rows]},
                         ensure_ascii=False, indent=2))
        return
    if args.output is None or args.output.exists():
        parser.error("Choose a new output directory")
    load_env_file_defaults(args.env_root / ".env.local")
    load_env_file_defaults(args.env_root / "backend/.env.local")
    settings = replace(Settings.from_environment(), model_provider="deepseek")
    if not settings.deepseek_api_key.strip():
        parser.error("Configure DeepSeek")
    args.output.mkdir(parents=True)
    count = 0

    def before_request():
        nonlocal count
        count += 1
        if count > 6:
            raise RuntimeError("At most six requests, no retries")

    service = ModelCallService(settings, before_request=before_request)
    for row in rows:
        stages = []

        async def captured_call(operation, context, *, review_prompt, _stages=stages):
            stage = {"messages": [{"role": "system", "content": review_prompt[0]},
                                  {"role": "user", "content": review_prompt[1]}]}
            _stages.append(stage)
            start = time.monotonic()
            try:
                response = await service._call_deepseek(operation, context,
                                                       review_prompt=review_prompt)
                stage.update(output=response.output, modelMetadata=response.model_metadata)
                return response
            finally:
                stage["seconds"] = round(time.monotonic() - start, 3)

        start = time.monotonic()
        before = count
        result = await service.edit_creator_facts(row["packet"], ModelCallResponse(
            output=deepcopy(row["originalOutput"]),
            model_metadata={"requestCount": 0, "model": settings.deepseek_model},
        ), call_once=captured_call)
        contract = "passed"
        try:
            wire, _ = RealContentCollaborationProvider._parse_output(
                result.output, single_writer=True,
            )
            sources = {item["id"]: item for item in row["packet"]["evidence"]["allowedSources"]}
            RealContentCollaborationProvider._validate_turn(
                role="writing", turn=wire.turn, sources=sources,
                upstream_candidates=[], single_writer=True,
            )
        except Exception:
            contract = "failed"
        record = {**row, "inputDraftHash": digest(row["originalOutput"]),
                  "generationReused": row["origin"] == "unchanged_saved_generation",
                  "newArticleGeneration": False, "stages": stages, "output": result.output,
                  "modelMetadata": result.model_metadata,
                  "seconds": round(time.monotonic() - start, 3), "requestCount": count - before,
                  "contractStatus": contract, "semanticStatus": "not_reviewed",
                  "badReceiptHash": digest(bad), "positiveReceiptHash": digest(positive)}
        args.output.joinpath(row["id"] + ".json").write_text(
            scrub(json.dumps(record, ensure_ascii=False, indent=2), settings), encoding="utf-8",
        )
        print(json.dumps({"case": row["id"], "seconds": record["seconds"],
                          "requestCount": record["requestCount"], "contractStatus": contract,
                          "factEdit": result.model_metadata["factEdit"]["status"],
                          "tokens": result.model_metadata.get("usage", {}).get("total_tokens")},
                         ensure_ascii=False), flush=True)


if __name__ == "__main__":
    asyncio.run(main())
