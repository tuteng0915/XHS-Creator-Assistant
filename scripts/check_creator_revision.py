"""Continue the two unchanged enhanced first drafts and saved reader comments.

First-turn/reader receipts are explicitly replayed without a model. Only the
two actual revision turns are sent to DeepSeek, through production sessions.
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import tempfile
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import httpx
from check_creator_end_to_end import MAIN, PLAN, SOURCE, Trace, clone_database, evaluate
from compare_creator_models import digest, load_frozen_cases

from app.config import Settings, load_env_file_defaults
from app.models import ModelCallResponse, ModelOperation


def saved_cases(path):
    report = json.loads(path.read_text(encoding="utf-8"))
    selected = []
    for spec in PLAN:
        matches = [a for a in report["arms"]
                   if a["account"] == spec[0] and a["arm"] == "enhanced"]
        if len(matches) != 1 or not matches[0].get("initial", {}).get("body", "").strip():
            raise ValueError("Expected exactly one actual enhanced first draft per account")
        row = matches[0]
        if row.get("readerIds") != spec[3] or not row.get("chosenFeedback"):
            raise ValueError("Saved reader selection/feedback does not match the frozen plan")
        selected.append(deepcopy(row))
    return selected, digest(report)


async def run(args):
    if args.output.exists():
        raise ValueError("Refusing to overwrite receipts")
    cases, source_hash = saved_cases(args.source_report)
    if not args.live:
        print(json.dumps({"maxRequests": 2, "live": False, "sourceHash": source_hash,
                          "firstDraftHashes": [digest(c["initial"]) for c in cases]}))
        return
    load_env_file_defaults(MAIN / "backend/.env.local")
    settings = Settings.from_environment()
    assert settings.model_provider == settings.for_creator_writing().model_provider == "deepseek"
    assert settings.deepseek_api_key
    args.output.mkdir(parents=True)
    report = {"maxRequests": 2, "requests": [], "arms": [], "sourceReportHash": source_hash,
              "scope": "Two saved enhanced drafts/comments replayed; only revisions are live",
              "limitations": ["API not browser QA", "One live revision per account, no retry"]}
    trace = Trace(report, args.output, settings)
    with tempfile.TemporaryDirectory(prefix="sqs-revision-check-") as temp:
        database = Path(temp) / "app.sqlite3"
        clone_database(SOURCE, database)
        with patch.dict(os.environ, {"DATABASE_PATH": str(database)}):
            module = importlib.import_module("app.main")
        app = module.create_app(replace(settings, database_path=database,
                                       upload_directory=Path(temp) / "uploads"))
        writer = app.state.content_collaboration_service.live_provider.writing_model_call_service
        live_call = writer.call_operation
        trace.install(writer)
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://evaluation.local") as client:
                for spec, saved in zip(PLAN, cases, strict=True):
                    replay_count = 0

                    async def first_then_live(operation, context, *, saved=saved):
                        nonlocal replay_count
                        assert operation == ModelOperation.CONTENT_COLLABORATION_TURN
                        replay_count += 1
                        if replay_count == 1:
                            # Adopt the exact post-edit first draft that the user reviewed.
                            summary = saved["stages"]["initial"]["session"]["messages"][-1][
                                "content"].split("\n\n【", 1)[0]
                            return ModelCallResponse(output={"turn": {
                                "summary": summary, "nextRecipient": "creator",
                                "usedCandidateIds": [], "candidateSuggestions": [saved["initial"]],
                            }}, model_metadata={"provider": "saved_receipt_replay",
                                                "requestCount": 0,
                                                "savedDraftHash": digest(saved["initial"])})
                        if replay_count != 2:
                            raise RuntimeError("One actual revision per account, no retry")
                        return await live_call(operation, context)

                    async def saved_reading(operation, context, *, saved=saved):
                        assert operation == ModelOperation.SIMULATION_REACTION
                        persona_id = context["persona"]["id"]
                        reaction = next(r for r in saved["stages"]["readers"]["reactions"]
                                        if r["personaId"] == persona_id)
                        return ModelCallResponse(output={"reaction": reaction}, model_metadata={
                            "provider": "saved_receipt_replay", "requestCount": 0})

                    writer.call_operation = first_then_live
                    app.state.model_call_service.call_operation = saved_reading
                    frozen = load_frozen_cases(
                        MAIN / "data/evals" / spec[2] / "manifest.json")[0][0]
                    await evaluate(app, client, trace, spec, "continued_saved_initial", frozen)
                    result = report["arms"][-1]
                    result["firstTurnAndReadersReplayed"] = True
                    result["initialExact"] = result.get("initial") == saved["initial"]
                    result["feedbackExact"] = (
                        result.get("chosenFeedback") == saved["chosenFeedback"])
                    assert result["initialExact"] and result["feedbackExact"]
                    trace.save()
        finally:
            await app.state.content_collaboration_service.shutdown()
            trace.save()
    print(json.dumps({"actualRequests": len(report["requests"]), "results": [
        {k: a.get(k) for k in ("account", "status", "initialExact", "feedbackExact",
                               "reopenExact", "staleSaveRejected")} for a in report["arms"]
    ]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    asyncio.run(run(parser.parse_args()))
