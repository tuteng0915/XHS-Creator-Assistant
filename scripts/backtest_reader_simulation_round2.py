"""Second round of the reader-simulation back-test: old versus revised reader prompts.

Tuning notes are the five notes of round one with their preset readers. Validation
notes are five comment-rich notes those readers were written from, so they get a
separate reader panel generated from the other 25 notes. All work happens on one
persistent copy of the development database inside --output; the budget counts every
HTTP request across phases and is enforced before each request.

    old     generate validation readers, run the unchanged prompts on validation notes
    new     run the revised prompts on validation and tuning notes
    label   control, themes and matching for validation notes
            (--tuning also matches the tuning notes against round-one themes)
    score   recompute metrics and write the comparison tables

Without --live, old and new use the demo provider and generate no readers: no requests.

    backend/.venv/bin/python scripts/backtest_reader_simulation_round2.py --output DIR --phase old [--live]
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib
import json
import os
import random
import re
import sqlite3
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import backtest_reader_simulation as v1  # noqa: E402

ROOT = v1.ROOT
ROUND1 = ROOT / "data/evals/reader-simulation-backtest-20261108/report.json"
PROMPT_FILES = ["backend/app/services/panel_reading.py", "backend/app/services/model_calls.py"]
MAX_REQUESTS = 202
LABEL_RESERVE = 20  # validation control, themes, match (15) + tuning match (5)
PANEL_SIZE = 5
SOURCE_MATERIAL = "18892280-ceba-444b-b2e8-52b57aa17996"
TUNING = v1.CASES[0]
VALIDATION = {**TUNING, "notes": ["68c81c64", "683c6e17", "692bbce2", "66855335", "670ea201"]}
TYPES = ["提问", "共鸣表态", "收藏打卡", "玩笑", "猜测", "对作者说话", "其他"]
ECHO = re.compile(r"^\s*(同问|同求|我也想问|我也想知道|我也好奇|一样|蹲|\+1)")

MATCH_PROMPT = f"""下面是一篇小红书笔记、从真实评论归纳出的主题（附原评论），以及一组待判断的句子（编号随机，来源不告诉你）。
对每个句子判断两件事：
1. themeId：它表达的关心或请求，是否属于某个主题（同一件事或同一类请求才算属于；只是话题相近不算）。属于就写主题 id，不属于任何主题写 null。“其他/无法判断”主题不要匹配。
2. type：这句话是哪种留言，只选一个：{"、".join(TYPES)}。提问指希望得到回答；对作者说话指祝福、关心、认识作者的寒暄；收藏打卡包括“马住”“dd”“已投”这类标记。
只输出 JSON：
{{"matches":[{{"itemId":"i1","themeId":"T1","type":"提问"}},{{"itemId":"i2","themeId":null,"type":"玩笑"}}]}}"""


def load_report(output: Path) -> dict:
    return json.loads((output / "report.json").read_text(encoding="utf-8"))


def prompt_state() -> dict:
    from app.services.model_calls import PROMPT_SIMULATION_DEBATE
    from app.services.panel_reading import PANEL_REACTION_PROMPT

    state = {"reaction": PANEL_REACTION_PROMPT, "debate": PROMPT_SIMULATION_DEBATE}
    return {**state, "hash": v1.digest(state)}


def prompts_match_head() -> bool:
    return subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *PROMPT_FILES],
                          cwd=ROOT, check=False).returncode == 0


def build_analysis_payload(app, workspace_id: str, validation_ids: set[str]):
    """Check the frozen model input excludes validation notes before any request."""
    from app.services.audience_analyses import AudienceAnalysisCreate
    from app.services.audience_evidence import audience_context, audience_model_context
    from app.services.creator_analysis_scope import scope_creator_profile

    with app.state.database.read() as c:
        text = c.execute("SELECT text_content FROM source_materials WHERE id=? AND workspace_id=?",
                         (SOURCE_MATERIAL, workspace_id)).fetchone()[0]
    full = json.loads(text)
    selected = [n["noteId"] for n in full["notes"] if n["noteId"] not in validation_ids]
    assert len(selected) == 25, len(selected)
    profile, scope = scope_creator_profile(full, "all", selected_note_ids=selected)
    context = audience_model_context(audience_context(
        {"scope": scope, "creator": profile.get("creator", {}), "notes": profile["notes"]}))
    packet = json.dumps(context, ensure_ascii=False, default=str)
    leaked = [i for i in validation_ids if i in packet]
    assert not leaked, leaked
    return (AudienceAnalysisCreate(source_material_id=SOURCE_MATERIAL, scope="selected_notes",
                                   selected_note_ids=selected, selection_scope="all"),
            len(packet), len(selected))


async def generate_panel(app, trace, payload, workspace_id: str, notes: list[dict]) -> list[str]:
    from app.services.simulated_fans import FanCreate

    trace.note_id = "audience_analysis"
    service = app.state.audience_analysis_service
    run = service.create(workspace_id, payload)
    task = service.tasks.get(run.id)
    if task is not None:
        await task
    done = service.get(run.id)
    trace.report["validationAnalysis"] = {
        "id": done.id, "status": done.status, "error": done.error,
        "diagnostics": done.diagnostics}
    if done.status not in ("completed", "partially_completed"):
        raise RuntimeError(f"Reader generation failed: {done.status} {done.error}")
    groups = done.result["groups"][:PANEL_SIZE]
    fans = [app.state.simulated_fan_service.create(
        workspace_id, FanCreate(source_analysis_id=done.id, source_group_id=g["id"]))
        for g in groups]
    # The panel must not contain the notes or comments it will be tested on.
    blob = json.dumps([f.model_dump(mode="json") for f in fans], ensure_ascii=False)
    hits = [n["noteId"] for n in notes if n["noteId"] in blob or n["title"] in blob]
    hits += [c["text"] for n in notes for c in n["readerComments"]
             if len(c["text"].strip()) >= 6 and c["text"] in blob]
    trace.report["validationLeakCheck"] = {"hits": hits, "readers": len(fans),
                                           "groupsGenerated": len(done.result["groups"])}
    trace.save()
    if hits:
        raise RuntimeError(f"Validation panel cites test material: {hits[:3]}")
    return [f.id for f in fans]


async def run_simulation(app, trace, note, fan_ids, live, set_name, variant) -> dict:
    from app.models import PanelTask, SimulationRunCreate, TopicCreate

    trace.note_id = note["noteId"]
    row = {"set": set_name, "variant": variant, "noteId": note["noteId"], "status": "running",
           "readerCount": len(fan_ids)}
    trace.report["runs"].append(row)
    before = len(trace.report["requests"])
    try:
        wid = TUNING["workspaceId"]
        topic = app.state.topic_service.create(wid, TopicCreate(title=note["title"][:300]))
        with app.state.database.transaction() as c:
            c.execute("UPDATE topics SET body=? WHERE id=?", (note["body"], topic.id))
        run = app.state.simulation_service.create(wid, SimulationRunCreate(
            topic_id=topic.id, simulated_fan_ids=fan_ids, mode="live" if live else "demo",
            panel_task=PanelTask()))
        await app.state.simulation_workflow_service.collect_events(run.id)
        result = app.state.simulation_service.get(run.id).model_dump(mode="json", by_alias=True)
        row["simulation"] = {k: result.get(k) for k in (
            "status", "reactionResults", "debateResults", "synthesis", "stageErrors")}
        row["status"] = "completed"
    except Exception as error:
        row.update(status="failed", errorType=type(error).__name__, error=str(error)[:300])
    finally:
        row["requests"] = len(trace.report["requests"]) - before
        trace.save()
        print(json.dumps({"set": set_name, "variant": variant, "note": note["noteId"][:8],
                          "status": row["status"],
                          "simulation": (row.get("simulation") or {}).get("status"),
                          "total": len(trace.report["requests"]), "error": row.get("error")},
                         ensure_ascii=False), flush=True)
    return row


def budget_left(report: dict) -> bool:
    return len(report["requests"]) < report["maxRequests"]


async def phase_simulate(app, trace, args, cases, preset_panel) -> None:
    report = trace.report
    live = args.live
    report["maxRequests"] = MAX_REQUESTS - LABEL_RESERVE
    if args.phase == "old":
        if live and not prompts_match_head():
            raise SystemExit("Old-prompt phase needs the committed prompts")
        payload, size, count = build_analysis_payload(
            app, TUNING["workspaceId"], {n["noteId"] for n in cases["validation"]})
        report["validationInput"] = {"notes": count, "packetChars": size}
        print(json.dumps(report["validationInput"]), flush=True)
        report["prompts"]["old"] = prompt_state()
        panel = (await generate_panel(app, trace, payload, TUNING["workspaceId"],
                                      cases["validation"])) if live else preset_panel
        report["validationPanel"] = panel
        trace.save()
        work = [("validation", n, panel) for n in cases["validation"]]
    else:
        state = prompt_state()
        if live and state["hash"] == report["prompts"]["old"]["hash"]:
            raise SystemExit("Revised prompts are not in place yet")
        report["prompts"]["new"] = state
        work = [("validation", n, report["validationPanel"]) for n in cases["validation"]]
        work += [("tuning", n, preset_panel) for n in cases["tuning"]]
    for set_name, note, panel in work:
        if live and not budget_left(report):
            print("budget reached", flush=True)
            break
        await run_simulation(app, trace, note, panel, live, set_name, args.phase)


def simulation_rows(report: dict, set_name: str, note_id: str) -> dict[str, dict]:
    return {r["variant"]: r for r in report["runs"]
            if r["set"] == set_name and r["noteId"] == note_id and r["status"] == "completed"}


def shuffled_items(note: dict, groups: list[tuple[str, list[dict]]]) -> list[dict]:
    items = []
    for variant, rows in groups:
        items += [{**i, "variant": variant} for i in rows]
    order = list(range(len(items)))
    random.Random(note["noteId"]).shuffle(order)
    for position, index in enumerate(order):
        items[index]["itemId"] = f"i{position + 1}"
    return items


def real_items(note: dict) -> list[dict]:
    return [{"source": "real", "kind": "comment", "text": c["text"], "commentId": c["id"]}
            for c in note["readerComments"] if c["text"].strip()]


async def match(trace, settings, note, themes, items) -> dict:
    by_id = {c["id"]: c["text"] for c in note["readerComments"]}
    return await v1.direct_call(trace, settings, "label_match", MATCH_PROMPT, {
        "title": note["title"], "body": note["body"][:600],
        "themes": [{"id": t["id"], "label": t["label"], "description": t.get("description", ""),
                    "comments": [by_id.get(i, "") for i in t.get("commentIds", [])]}
                   for t in themes.get("themes", [])],
        "items": sorted(({"itemId": i["itemId"], "text": i["text"]} for i in items),
                        key=lambda i: int(i["itemId"][1:]))})


async def phase_label(trace, settings, args, cases) -> None:
    report = trace.report
    report["maxRequests"] = MAX_REQUESTS
    labels = report.setdefault("labels", {"validation": {}, "tuning": {}})
    for note in cases["validation"]:
        if note["noteId"] in labels["validation"]:
            continue
        trace.note_id = note["noteId"]
        runs = simulation_rows(report, "validation", note["noteId"])
        visible = {"title": note["title"], "body": note["body"]}
        control = await v1.direct_call(trace, settings, "control_predict_comments",
                                       v1.CONTROL_PROMPT, visible)
        themes = await v1.direct_call(trace, settings, "label_themes", v1.THEME_PROMPT, {
            **visible, "body": note["body"][:600],
            "comments": [{"id": c["id"], "text": c["text"]} for c in note["readerComments"]]})
        items = shuffled_items(note, [
            *[(v, v1.simulation_items(r["simulation"])) for v, r in sorted(runs.items())],
            ("control", [{"source": "control", "kind": "comment", "text": t}
                         for t in control.get("comments") or [] if str(t).strip()]),
            ("real", real_items(note))])
        result = await match(trace, settings, note, themes, items)
        labels["validation"][note["noteId"]] = {
            "control": control, "themes": themes, "items": items, "match": result}
        trace.save()
    if not args.tuning:
        return
    first = {n["noteId"]: n for n in json.loads(ROUND1.read_text(encoding="utf-8"))["notes"]}
    for note in cases["tuning"]:
        if note["noteId"] in labels["tuning"]:
            continue
        trace.note_id = note["noteId"]
        runs = simulation_rows(report, "tuning", note["noteId"])
        old = first[note["noteId"]]
        keep = ("source", "kind", "text", "personaId")
        items = shuffled_items(note, [
            ("round1", [{k: i[k] for k in keep if k in i} for i in old["items"]
                        if i["source"] == "simulation"]),
            ("new", v1.simulation_items(runs["new"]["simulation"])),
            ("control", [{k: i[k] for k in keep if k in i} for i in old["items"]
                         if i["source"] == "control"]),
            ("real", real_items(note))])
        result = await match(trace, settings, note, old["themes"], items)
        labels["tuning"][note["noteId"]] = {"themes": old["themes"], "items": items,
                                            "match": result}
        trace.save()


def score_set(entries: dict) -> dict:
    per_note, pooled = {}, {}
    for note_id, label in entries.items():
        themes = [t for t in label["themes"].get("themes", [])
                  if "其他" not in t["label"] and "无法判断" not in t["label"]]
        ids = {t["id"] for t in themes}
        answers = {m["itemId"]: m for m in label["match"].get("matches", [])}
        note_scores = {}
        for variant in sorted({i["variant"] for i in label["items"]}):
            chosen = [i for i in label["items"] if i["variant"] == variant]
            public = [i for i in chosen if i["kind"] != "concern"]
            def theme(item):
                value = answers.get(item["itemId"], {}).get("themeId")
                return value if value in ids else None
            kinds = [answers.get(i["itemId"], {}).get("type", "其他") for i in public]
            replies = [i for i in public if i["kind"] == "reply"]
            row = {"items": len(public), "hits": sum(1 for i in public if theme(i)),
                   "themesCovered": len({theme(i) for i in public if theme(i)}),
                   "themes": len(themes), "types": {t: kinds.count(t) for t in TYPES},
                   "replies": len(replies),
                   "echoReplies": sum(1 for i in replies if ECHO.match(i["text"])),
                   "allItems": len(chosen), "allHits": sum(1 for i in chosen if theme(i))}
            note_scores[variant] = row
            total = pooled.setdefault(variant, {
                "items": 0, "hits": 0, "themesCovered": 0, "themes": 0,
                "types": dict.fromkeys(TYPES, 0), "replies": 0, "echoReplies": 0,
                "allItems": 0, "allHits": 0})
            for key in ("items", "hits", "themesCovered", "themes", "replies", "echoReplies",
                        "allItems", "allHits"):
                total[key] += row[key]
            for t in TYPES:
                total["types"][t] += row["types"][t]
        per_note[note_id] = note_scores
    for row in pooled.values():
        row["hitRate"] = round(row["hits"] / row["items"], 3) if row["items"] else None
        row["coverage"] = round(row["themesCovered"] / row["themes"], 3) if row["themes"] else None
        row["questionShare"] = round(row["types"]["提问"] / row["items"], 3) if row["items"] else None
    return {"perNote": per_note, "pooled": pooled}


def writing_rows(report: dict) -> list[dict]:
    """Size of the writing advice per run, for the check that it did not get weaker."""
    rows = []
    first = {n["noteId"]: n for n in json.loads(ROUND1.read_text(encoding="utf-8"))["notes"]}
    runs = list(report["runs"])
    runs += [{"set": "tuning", "variant": "round1", "noteId": n["noteId"], "status": "completed",
              "simulation": first[n["noteId"]]["simulation"]}
             for n in report["cases"]["tuning"] if n["noteId"] in first]
    for run in runs:
        if run["status"] != "completed":
            continue
        syn = run["simulation"].get("synthesis") or {}
        feedback = syn.get("editorFeedback") or []
        reactions = run["simulation"].get("reactionResults") or []
        rows.append({
            "set": run["set"], "variant": run["variant"], "noteId": run["noteId"],
            "concerns": sum(len(r.get("concerns") or []) for r in reactions),
            "commented": sum(1 for r in reactions if r.get("action") == "comment"),
            "contentAdjustments": len(syn.get("contentAdjustments") or []),
            "riskWarnings": len(syn.get("riskWarnings") or []),
            "editorFeedback": len(feedback),
            "editorKinds": {k: sum(1 for f in feedback if f.get("kind") == k)
                            for k in sorted({f.get("kind") for f in feedback})},
            "synthesisStatus": run["simulation"].get("status")})
    return rows


async def run(args) -> None:
    output = args.output
    cases = {"tuning": v1.load_notes(TUNING), "validation": v1.load_notes(VALIDATION)}
    if args.phase == "score":
        report = load_report(output)
        labels = report.get("labels", {})
        report["scores"] = {name: score_set(labels[name]) for name in labels if labels[name]}
        report["writing"] = writing_rows(report)
        text = json.dumps(report, ensure_ascii=False, indent=2, default=str)
        (output / "report.json").write_text(text, encoding="utf-8")
        print(json.dumps({k: v["pooled"] for k, v in report["scores"].items()},
                         ensure_ascii=False, indent=1))
        return
    from app.config import Settings, load_env_file_defaults

    if args.live:
        load_env_file_defaults(v1.ENV_FILE)
    os.environ.update({"MODEL_PROVIDER": "deepseek", "ACCOUNT_DIAGNOSIS_PROVIDER": "deepseek",
                       "CREATOR_WRITING_PROVIDER": "deepseek", "DEEPSEEK_MODEL": "deepseek-flash"})
    settings = Settings.from_environment()
    if args.live:
        assert settings.model_provider == "deepseek" and settings.deepseek_api_key.strip()
    work = output / "work"
    db = work / "app.sqlite3"
    if args.phase == "old":
        if (output / "report.json").exists():
            raise SystemExit("Refusing to overwrite an existing round-two report")
        work.mkdir(parents=True)
        v1.clone(v1.SOURCE_DB, db)
        report = {"version": "reader-simulation-backtest/round2", "live": args.live,
                  "approvedBudget": MAX_REQUESTS, "maxRequests": MAX_REQUESTS,
                  "model": settings.deepseek_model, "sourceDatabase": str(v1.SOURCE_DB),
                  "sourceDatabaseHash": hashlib.sha256(v1.SOURCE_DB.read_bytes()).hexdigest(),
                  "matchPrompt": MATCH_PROMPT, "cases": cases, "prompts": {}, "runs": [],
                  "calls": [], "requests": []}
    else:
        report = load_report(output)
        if report["live"] != args.live:
            raise SystemExit("Do not mix demo and live phases in one report")
    trace = v1.Trace(report, output, [settings.deepseek_api_key, settings.qwen_api_key,
                                      settings.anthropic_api_key])
    trace.note_id = ""
    os.environ.update({"DATABASE_PATH": str(db), "UPLOAD_DIRECTORY": str(work / "up")})
    module = importlib.import_module("app.main")
    app = module.create_app(replace(settings, database_path=db, upload_directory=work / "up"))
    trace.install(app.state.model_call_service)
    if args.phase == "label":
        if not args.live:
            raise SystemExit("Labelling needs --live")
        await phase_label(trace, settings, args, cases)
    else:
        with sqlite3.connect(db) as c:
            preset = [r[0] for r in c.execute(
                "SELECT id FROM simulated_fans WHERE workspace_id=? AND source_analysis_id=? "
                "AND status='active' ORDER BY created_at, id",
                (TUNING["workspaceId"], TUNING["fanAnalysis"]))]
        await phase_simulate(app, trace, args, cases, preset)
    same = hashlib.sha256(v1.SOURCE_DB.read_bytes()).hexdigest() == report["sourceDatabaseHash"]
    report["sourceDatabaseUnchanged"] = same
    trace.save()
    print(json.dumps({"phase": args.phase, "requests": len(report["requests"]),
                      "sourceDatabaseUnchanged": same}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--phase", choices=["old", "new", "label", "score"], required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--tuning", action="store_true",
                        help="with --phase label, also match tuning notes (needs the label check)")
    asyncio.run(run(parser.parse_args()))
