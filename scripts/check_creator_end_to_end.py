"""Bounded DeepSeek creation evaluation on an ephemeral clone, never product storage.

Two accounts × single generation / explicit experimental editing, one reader-feedback
revision each. Preview is free. Raw model content and API receipts are retained.
No application lifespan (and thus no resumption of existing background jobs).
"""
from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import os
import sqlite3
import sys
import tempfile
import time
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import httpx  # noqa: E402
from compare_creator_models import digest, load_frozen_cases, scrub  # noqa: E402

from app.config import Settings, load_env_file_defaults  # noqa: E402
from app.models import ModelOperation, PanelTask, SimulationRunCreate  # noqa: E402
from app.services.audience_target import reader_visible_target  # noqa: E402
from app.services.common import utc_now  # noqa: E402
from app.services.panel_reading import compact_reader, resolve_reaction_anchor  # noqa: E402
from app.workflows.audience_simulation import (  # noqa: E402
    PersonaReactionResult,
    validate_trigger_quote,
)

MAIN = Path("/Users/tut/ForFun/AI PM/SqsAgent")
SOURCE = MAIN / "data/development-runtime/20261016-f767f21/data/app.sqlite3"
PLAN = [
    ("QSheep", "a81ff1af-8b0d-4999-a9a2-d73f48a53c0d",
     "creator-model-compare-20261016",
     ["831bbae3-eb5e-40ce-8f7e-5ccdb1e99f5c", "d112f0e3-9475-4c4e-996e-a04063217d78"]),
    ("一粒鱼", "e1d04043-f3bc-4887-a42b-2e1db8f5006d",
     "creator-model-compare-yiliyu-20261016", ["e5cbda52-2f03-46b4-820b-d1c93a409dac"]),
]
REVISION = (
    "请结合这条试读意见，再给一版完整的约500字正文和自然的标题。先判断意见是否值得采纳，"
    "只吸收能让读者更清楚、更容易行动的部分；保留原稿的立场和口气，"
    "不要为了回应意见补出材料没有的经历或结果。已经讲清楚的地方可以保留。"
)


def format_only(body):
    """Exercise manual editing without introducing another writing intervention."""
    return body.rstrip() + "\n\n"


def clone_database(source, destination):
    with (
        sqlite3.connect(f"file:{source}?mode=ro", uri=True) as original,
        sqlite3.connect(destination) as target,
    ):
        original.backup(target)


class Trace:
    def __init__(self, report, output, settings):
        self.report, self.output, self.settings = report, output, settings
        self.arm = None
        self.stage = ""

    def save(self):
        self.output.joinpath("report.json").write_text(
            scrub(json.dumps(self.report, ensure_ascii=False, indent=2, default=str),
                  self.settings),
            encoding="utf-8",
        )

    def install(self, service):
        factory = service._deepseek_client

        async def request_hook(request):
            limit = self.report.get("maxRequests", 22)
            if len(self.report["requests"]) >= limit:
                raise RuntimeError(f"Hard limit: {limit} actual model requests")
            packet = json.loads(request.content)
            entry = {"account": self.arm["account"], "arm": self.arm["arm"],
                     "stage": self.stage, "packet": packet, "status": "running"}
            self.report["requests"].append(entry)
            request.extensions["eval_entry"] = (entry, time.monotonic())
            self.save()

        async def response_hook(response):
            entry, started = response.request.extensions["eval_entry"]
            await response.aread()
            entry.update(seconds=round(time.monotonic() - started, 3),
                         httpStatus=response.status_code)
            try:
                raw = response.json()
                choice = raw.get("choices", [{}])[0]
                entry.update(rawContent=choice.get("message", {}).get("content"),
                             finishReason=choice.get("finish_reason"),
                             model=raw.get("model"), usage=raw.get("usage"), status="returned")
            except (ValueError, IndexError):
                entry["status"] = "invalid_response"
            self.save()

        def client(operation):
            result = factory(operation)
            result.event_hooks["request"].append(request_hook)
            result.event_hooks["response"].append(response_hook)
            return result

        service._deepseek_client = client


async def evaluate(app, client, trace, spec, arm_name, frozen):
    name, wid, _, reader_ids = spec
    row = {"account": name, "arm": arm_name, "status": "running", "stages": {}}
    trace.report["arms"].append(row)
    trace.arm = row
    started_all = time.monotonic()

    async def api(method, path, **kwargs):
        response = await client.request(method, "/api" + path, **kwargs)
        if response.status_code >= 400:
            row.setdefault("apiErrors", []).append({"status": response.status_code,
                                                   "body": response.json()})
        response.raise_for_status()
        return response.json()

    try:
        selection = frozen["context"]["sessionContext"]["creatorContextSelection"]
        request = frozen["context"]["receivedMessage"]["content"]
        row.update(request=request, selection=selection, readerIds=reader_ids,
                   referenceHash=digest(frozen["context"]["sessionContext"]
                                        ["creatorContextSnapshot"]))
        topic = await api("POST", f"/workspaces/{wid}/topics", json={"title": (
            "还不知道以后想做什么，先怎么比较保研和出国" if name == "QSheep"
            else "只有普通实习经历，怎么做出一件能讲清楚的小改进")})
        tid = topic["id"]
        base = f"/workspaces/{wid}/content-collaboration-sessions"
        session = await api("POST", base, json={"assistantMode": "single_writer",
                            "contextTarget": {"assetType": "topic", "assetId": tid},
                            "requestKey": str(uuid4())})
        path = base + "/" + session["id"]
        row.update(topicId=tid, sessionId=session["id"])

        async def turn(stage, content, focus=None):
            trace.stage = stage
            began = time.monotonic()
            payload = {"content": content, "recipient": "writing", "mode": "live",
                       "requestKey": str(uuid4()), "creatorContextSelection": selection}
            if focus:
                payload["writingFocus"] = focus
            await api("POST", path + "/messages", json=payload)
            statuses = []
            while True:
                current = await api("GET", path)
                status = current["executionStatus"]
                if not statuses or statuses[-1]["status"] != status:
                    statuses.append({"status": status,
                                     "seconds": round(time.monotonic() - began, 3)})
                if status not in {"queued", "running"}:
                    break
                if time.monotonic() - began > 240:
                    raise TimeoutError("Writer did not settle within 240 seconds; no retry")
                await asyncio.sleep(0.1)
            seconds = round(time.monotonic() - began, 3)
            row["stages"][stage] = {"seconds": seconds, "statuses": statuses,
                                     "session": current}
            trace.save()
            print(json.dumps({"account": name, "arm": arm_name, "stage": stage,
                              "seconds": seconds, "status": status},
                             ensure_ascii=False), flush=True)
            if current.get("failureCode"):
                raise RuntimeError(current.get("failureDetail") or current["failureCode"])
            messages = [m for m in current["messages"] if m["sender"] == "writing"]
            candidates = messages[-1]["modelMetadata"].get("candidateSuggestions", [])
            copies = [c for c in candidates if c.get("kind") == "copy_option"]
            if not copies:
                raise ValueError("No adoptable full draft; not retrying")
            row[stage + "CandidateCount"] = len(copies)
            return copies[0]

        async def adopt(candidate, before, key):
            mark = time.monotonic()
            unchanged = await api("GET", f"/topics/{tid}")
            assert unchanged["body"] == before["body"]  # Generation never silently adopts.
            result = await api("PATCH", f"/topics/{tid}", json={
                "title": candidate["title"], "body": candidate["body"],
                "expectedUpdatedAt": before["updatedAt"]})
            row[key] = {"seconds": round(time.monotonic() - mark, 3), "topic": result,
                        "noAutomaticAdoption": True}
            return result

        initial = await turn("initial", request)
        topic = await adopt(initial, topic, "initialSave")
        row["initial"] = initial
        trace.stage = "readers"
        begin_read = time.monotonic()
        service = app.state.simulation_service
        simulation = service.create(wid, SimulationRunCreate(
            topic_id=tid, simulated_fan_ids=reader_ids, mode="live",
            panel_task=PanelTask(reading_mode="guided", discussion_enabled=False,
                                 focus_questions=["读完你知道怎么开始了吗？哪里仍阻碍你行动？"])))
        target = reader_visible_target(simulation.input_snapshot)
        target.update(simulationCategory="creation",
                      panelTask=simulation.input_snapshot["panelTask"])
        with app.state.database.read() as connection:
            readers = app.state.simulated_fan_service.snapshots(connection, wid, reader_ids)
        row["readers"] = readers

        async def read(reader):
            response = await app.state.model_call_service.call_operation(
                ModelOperation.SIMULATION_REACTION,
                {"persona": compact_reader(reader, include_history=False), "topic": target})
            reaction = PersonaReactionResult.model_validate(
                resolve_reaction_anchor(response.output, target)).reaction.model_dump()
            assert reaction["personaId"] == reader["id"]
            validate_trigger_quote(reaction["triggerQuote"], target)
            return reaction

        reactions = await asyncio.gather(*(read(r) for r in readers))
        row["stages"]["readers"] = {"seconds": round(time.monotonic() - begin_read, 3),
                                        "reactions": reactions}
        # No debate/synthesis was requested: retain this explicitly partial history.
        now = utc_now()
        with app.state.database.transaction() as connection:
            service.repository.update(
                connection, simulation_id=simulation.id, status="partially_completed",
                persona_definitions_json=json.dumps(readers, ensure_ascii=False, default=str),
                reaction_results_json=json.dumps(reactions, ensure_ascii=False),
                debate_results_json="[]", synthesis_json="{}",
                stage_errors_json=json.dumps({"synthesis": "Evaluation: independent reading only"}),
                model_metadata_json='{"evaluation":"independent_reading_only"}',
                now=now, completed_at=now)
        row["simulationId"] = simulation.id
        print(json.dumps({"account": name, "arm": arm_name, "stage": "readers",
                          "seconds": row["stages"]["readers"]["seconds"]},
                         ensure_ascii=False), flush=True)
        chosen = next((r for r in reactions
                       if r["action"] == "comment" and r["quote"].strip()), None)
        if chosen is None:
            raise ValueError("No public feedback; private concerns not used as public comments")
        row["chosenFeedback"] = chosen
        final = await turn("revision", REVISION, {
            "expectedUpdatedAt": topic["updatedAt"], "readerReference": {
                "simulationId": simulation.id, "stage": "initial",
                "messageId": "initial:" + chosen["personaId"]}})
        topic = await adopt(final, topic, "finalAdoption")
        row["final"] = final
        manual = {**final, "body": format_only(final["body"])}
        previous = topic
        topic = await adopt(manual, topic, "manualSave")
        reopened = await api("GET", f"/topics/{tid}")
        assert reopened["title"] == manual["title"] and reopened["body"] == manual["body"]
        stale = await client.patch("/api/topics/" + tid, json={
            "title": previous["title"], "body": "stale edit must not overwrite",
            "expectedUpdatedAt": previous["updatedAt"]})
        assert stale.status_code == 409
        assert (await api("GET", f"/topics/{tid}"))["body"] == manual["body"]
        reopened_session = await api("GET", path)
        row.update(status="completed", reopenExact=True, staleSaveRejected=True,
                   manualEdit="Formatting-only trailing blank line, not a quality rewrite",
                   savedTopic=reopened, reopenedSession=reopened_session,
                   readerHistory=service.get(simulation.id).model_dump(by_alias=True, mode="json"))
    except Exception as error:
        row.update(status="failed", errorType=type(error).__name__, error=str(error))
        print(json.dumps({"account": name, "arm": arm_name, "status": "failed",
                          "errorType": type(error).__name__, "error": str(error)},
                         ensure_ascii=False), flush=True)
    finally:
        row["totalSeconds"] = round(time.monotonic() - started_all, 3)
        trace.save()


async def main(args):
    if args.output.exists():
        raise ValueError("Refusing to overwrite evaluation output")
    frozen = [load_frozen_cases(MAIN / "data/evals" / spec[2] / "manifest.json")[0][0]
              for spec in PLAN]
    if not args.live:
        print(json.dumps({"live": False, "maxRequests": 22, "accounts": [p[0] for p in PLAN],
                          "sourceDatabaseExists": SOURCE.is_file(), "frozenCases": len(frozen)}))
        return
    load_env_file_defaults(MAIN / "backend/.env.local")
    settings = Settings.from_environment()
    assert settings.for_creator_writing().model_provider == "deepseek"
    assert settings.model_provider == "deepseek" and settings.deepseek_api_key
    args.output.mkdir(parents=True)
    report = {"maxRequests": 22, "requests": [], "arms": [],
              "limitations": ["API flow, not browser-visible QA", "One sample per condition",
                              "Saved readers manually selected; no retrieval/debate/synthesis",
                              "Enhanced arm explicitly opts into diagnostic factual editing",
                              "No implicit retry, no production writes, no default switch"]}
    trace = Trace(report, args.output, settings)
    with tempfile.TemporaryDirectory(prefix="sqs-creation-eval-") as temp:
        database = Path(temp) / "app.sqlite3"
        clone_database(SOURCE, database)
        # main creates a module-level app: redirect even that import to this clone.
        with patch.dict(os.environ, {"DATABASE_PATH": str(database)}):
            module = importlib.import_module("app.main")
        app = module.create_app(replace(settings, database_path=database,
                                       upload_directory=Path(temp) / "uploads"))
        writer = app.state.content_collaboration_service.live_provider.writing_model_call_service
        trace.install(writer)
        trace.install(app.state.model_call_service)
        original_edit = writer.edit_creator_facts
        original_call = writer.call_operation

        async def explicit_edit(operation, context):
            response = await original_call(operation, context)
            return await original_edit(context, response, call_once=writer._call_deepseek)

        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                         base_url="http://evaluation.local") as client:
                for spec, case in zip(PLAN, frozen, strict=True):
                    for arm in ("simple", "enhanced"):
                        writer.call_operation = original_call if arm == "simple" else explicit_edit
                        await evaluate(app, client, trace, spec, arm, case)
        finally:
            await app.state.content_collaboration_service.shutdown()
            trace.save()
    print(json.dumps({"requests": len(report["requests"]), "arms": [
        {k: a[k] for k in ("account", "arm", "status", "totalSeconds")} for a in report["arms"]
    ]}, ensure_ascii=False), flush=True)


async def persistence_check(source_report, output):
    """Reuse the four actual first drafts; no models, no claim of revised finals."""
    if output.exists():
        raise ValueError("Refusing to overwrite evaluation output")
    frozen = json.loads(source_report.read_text(encoding="utf-8"))
    receipts = []
    with tempfile.TemporaryDirectory(prefix="sqs-saved-draft-check-") as temp:
        database = Path(temp) / "app.sqlite3"
        clone_database(SOURCE, database)
        with patch.dict(os.environ, {"DATABASE_PATH": str(database)}):
            module = importlib.import_module("app.main")
        app = module.create_app(Settings(database_path=database,
                                          upload_directory=Path(temp) / "uploads"))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),
                                     base_url="http://evaluation.local") as client:
            for arm in frozen["arms"]:
                wid = next(spec[1] for spec in PLAN if spec[0] == arm["account"])
                before = arm["initial"]
                began = time.monotonic()
                result = await client.post(f"/api/workspaces/{wid}/topics", json={
                    "title": before["title"]})
                result.raise_for_status()
                topic = result.json()
                path = "/api/topics/" + topic["id"]

                async def save(body, expected, *, path=path, title=before["title"]):
                    result = await client.patch(path, json={"title": title, "body": body,
                                               "expectedUpdatedAt": expected})
                    result.raise_for_status()
                    return result.json()

                saved = await save(before["body"], topic["updatedAt"])
                manual_body = format_only(before["body"])
                manual = await save(manual_body, saved["updatedAt"])
                reopened = (await client.get(path)).json()
                assert reopened["body"] == manual_body and reopened["title"] == before["title"]
                stale = await client.patch(path, json={"title": before["title"],
                    "body": "stale write", "expectedUpdatedAt": saved["updatedAt"]})
                assert stale.status_code == 409
                assert (await client.get(path)).json() == reopened
                receipts.append({"account": arm["account"], "arm": arm["arm"],
                                 "reopenExact": True, "staleSaveRejected": True,
                                 "initialBodyHash": digest(before["body"]),
                                 "manualBodyHash": digest(manual["body"]),
                                 "seconds": round(time.monotonic() - began, 3)})
        await app.state.content_collaboration_service.shutdown()
    output.mkdir(parents=True)
    result = {"modelRequests": 0, "sourceReportHash": digest(frozen), "checks": receipts,
              "scope": "Separate API save check of actual first drafts, not final revisions"}
    output.joinpath("report.json").write_text(json.dumps(result, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--persistence-from", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.persistence_from:
        if args.live:
            parser.error("Persistence replay never calls a live model")
        asyncio.run(persistence_check(args.persistence_from, args.output))
    else:
        asyncio.run(main(args))
