"""Summarize wait times and failures from saved run records (read-only).

Sources:
  * product SQLite databases, opened with ``mode=ro`` and deduplicated by record id;
  * saved experiment reports under ``data/evals/**.json``.

No model is called and nothing is written except the optional ``--output`` directory.

Examples (repository root):
  backend/.venv/bin/python -I scripts/report_wait_failure_stats.py
  backend/.venv/bin/python -I scripts/report_wait_failure_stats.py --output /private/tmp/wait-stats
"""
from __future__ import annotations

import argparse
import glob
import json
import math
import re
import sqlite3
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATABASES = [
    "data/development-runtime/20261016-f767f21/data/app.sqlite3",
    "data/app.sqlite3",
    "data/submission-demo/20261012-002859/data/app.sqlite3",
    "data/releases/SqsAgent-Submission-20261012-db875d8/data/app.sqlite3",
    "data/handoffs/SqsAgent-creator-data-20261001/data/app.sqlite3",
]
SUCCESS = {"completed", "returned", "passed", "waiting_creator", "succeeded", "ok"}
SKIP_STATUS = {"running", "queued", "pending"}
SKIP_KEYS = {"networkEvents", "timings", "progress", "requestDiagnostics", "events", "checks", "initialSave"}
# Review/summary files restate timings already present in the raw reports.
SKIP_FILES = re.compile(r"(^|/)(review|summary|automated-summary|review-summary|manifest)[^/]*\.json$")
CONTAINER_KEYS = {"statuses", "stages", "calls", "requests", "events", "cases", "reports", "accounts", "arms"}
# Product defaults switched from Qwen to DeepSeek on 2026-10-12 (text, diagnosis) and 2026-10-16 (writing).
DEEPSEEK_SINCE = {"diagnosis": "2026-10-12", "audience_simulation": "2026-10-12", "writing": "2026-10-16"}

# ---------------------------------------------------------------- helpers


def ts(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def seconds_between(start, end):
    a, b = ts(start), ts(end)
    return (b - a).total_seconds() if a and b else None


def loads(text):
    try:
        return json.loads(text) if text else {}
    except (TypeError, ValueError):
        return {}


def provider_of(*values):
    for value in values:
        text = str(value or "").lower()
        if "deepseek" in text:
            return "deepseek"
        if "qwen" in text or "dashscope" in text:
            return "qwen"
        if "fake" in text:
            return "fake"
        if "handwritten" in text or "oracle" in text:
            return "oracle"
    return "unknown"


def failure_type(record: dict) -> str | None:
    """Return a delivery-failure category, or None when the item was delivered."""
    error = [e for e in (record.get("error"), record.get("errorType")) if e not in (None, "", {}, [])] or None
    diag = record.get("responseDiagnostic") if isinstance(record.get("responseDiagnostic"), dict) else {}
    status = str(record.get("status") or "")
    text = json.dumps(error, ensure_ascii=False) if error not in (None, "", {}, []) else ""
    text += " " + str(diag.get("phase") or "") + " " + str(diag.get("waitingFor") or "")
    failed = bool(error not in (None, "", {}, [])) or (status and status not in SUCCESS)
    if record.get("contractStatus") == "failed":
        failed = True
    if not failed:
        return None
    if "Cancelled" in text or status == "cancelled":
        return "cancelled"
    if "Timeout" in text or "response_headers" in text or "timeout" in text.lower():
        return "timeout"
    if "ConnectError" in text or "transport" in text:
        return "connection"
    if "output_length" in text or record.get("finishReason") == "length":
        return "truncated"
    if "http_status" in text:
        return "http_error"
    if "RuntimeError" in text:
        return "turn_failed"
    if "ValidationError" in text or "ValueError" in text or "model_json" in text or record.get("contractStatus") == "failed":
        return "format_or_validation"
    if status == "partially_completed":
        return "partial"
    return "failed_unspecified"


# ------------------------------------------------------------- stage names

STAGE_ALIASES = {
    "overview": "profile.overview", "read": "profile.reading", "reading": "profile.reading",
    "synthesis": "profile.synthesis", "profile": "profile", "pain_points": "feedback",
    "retrieve": "feedback.retrieve", "rank": "feedback.rank", "topics": "topics",
    "profile_analysis": "profile+feedback", "topic_generation": "topics", "finalize": "finalize",
    "audience_analysis": "audience_analysis", "reader_selection": "reader_selection",
    "simulation_personas": "personas", "simulation_reaction": "reaction",
    "simulation_debate": "debate", "simulation_synthesis": "synthesis",
    "panel_interview": "interview", "creator_edit": "editor_feedback",
    "content_collaboration_turn": "writing_turn", "initial": "writing.initial",
    "revision": "writing.revision", "readers": "readers",
}


def chain_of(family: str) -> str:
    if family.startswith(("account-",)):
        return "diagnosis"
    if family.startswith(("creator-", "deepseek-title")):
        return "writing"
    return "audience_simulation"


def stage_of(record: dict, path: str) -> str:
    meta = record.get("modelMetadata") if isinstance(record.get("modelMetadata"), dict) else {}
    raw = record.get("stage") or record.get("operation") or record.get("label") or meta.get("stage")
    if not raw:
        keys = [k for k in re.findall(r"\.([A-Za-z_]+)", path) if k not in CONTAINER_KEYS]
        raw = keys[-1] if keys else "run"
    raw = str(raw)
    key = raw.split(":")[0].split("/")[0].strip()
    return STAGE_ALIASES.get(key, key[:40])


# ------------------------------------------------------------ eval reports

def eval_records(evals_dir: Path):
    for file in sorted(glob.glob(str(evals_dir / "**" / "*.json"), recursive=True)):
        rel = Path(file).relative_to(evals_dir)
        family = rel.parts[0]
        date = re.search(r"(2026\d{4})", family)
        date = f"{date.group(1)[:4]}-{date.group(1)[4:6]}-{date.group(1)[6:]}" if date else None
        if SKIP_FILES.search(str(rel)):
            continue
        try:
            data = json.loads(Path(file).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        top = data if isinstance(data, dict) else {}
        file_provider = provider_of(top.get("provider"), top.get("model"), top.get("configuredModel"),
                                    family if "deepseek" in family else "", rel.name)
        chain = chain_of(family)
        if file_provider == "unknown" and date:
            file_provider = "qwen*" if date < DEEPSEEK_SINCE[chain] else "deepseek*"

        def walk(obj, path=""):
            if isinstance(obj, dict):
                secs = obj.get("elapsedSeconds", obj.get("seconds", obj.get("totalSeconds")))
                status = str(obj.get("status") or "")
                if isinstance(secs, (int, float)) and status not in SKIP_STATUS:
                    nested = any(isinstance(obj.get(k), list) and obj.get(k) for k in ("stages", "calls", "requests"))
                    meta = obj.get("modelMetadata") if isinstance(obj.get("modelMetadata"), dict) else {}
                    diag = obj.get("responseDiagnostic") if isinstance(obj.get("responseDiagnostic"), dict) else {}
                    prov = provider_of(obj.get("provider"), meta.get("provider"), obj.get("model"),
                                       meta.get("model"), diag.get("model"))
                    if prov == "unknown":
                        prov = file_provider
                    stage = stage_of(obj, path)
                    if stage == "run" and family.startswith("audience-") and not path:
                        stage = "audience_analysis"
                    elif stage == "run" and chain == "writing":
                        stage = "fact_edit" if re.search(r"(claim|fact|sentence)-edit", family) else (
                            "writing.probe" if "statement" in family else ("arm_total" if "totalSeconds" in obj else stage))
                    yield {
                        "source": "evals", "chain": chain, "family": family,
                        "file": str(rel), "path": path or "/", "date": date,
                        "level": "run" if nested or not path else "call",
                        "stage": stage, "provider": prov, "seconds": float(secs),
                        "attempts": obj.get("requestAttempts"), "failure": failure_type(obj),
                    }
                for key, value in obj.items():
                    if key not in SKIP_KEYS:
                        yield from walk(value, f"{path}.{key}")
            elif isinstance(obj, list):
                for item in obj:
                    yield from walk(item, f"{path}[]")

        yield from walk(data)


# ------------------------------------------------------- product databases

def db_records(databases):
    seen: dict[tuple, dict] = {}

    def keep(key, record):
        old = seen.get(key)
        if old is None or (old.get("failure") == "unfinished" and record.get("failure") != "unfinished"):
            seen[key] = record

    for db in databases:
        path = ROOT / db
        if not path.exists():
            continue
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        con.row_factory = sqlite3.Row
        tables = {r[0] for r in con.execute("select name from sqlite_master where type='table'")}

        if "analysis_runs" in tables:
            checkpoints = defaultdict(list)
            if "graph_checkpoints" in tables:
                for row in con.execute("select analysis_run_id, node_key, created_at from graph_checkpoints order by created_at"):
                    checkpoints[row["analysis_run_id"]].append((row["node_key"], row["created_at"]))
            for row in con.execute("select * from analysis_runs where workflow_type='account_diagnosis'"):
                meta = loads(row["model_metadata_json"])
                if meta.get("modelCalled") is False or meta.get("origin") == "oracle_showcase":
                    continue
                total = seconds_between(row["started_at"], row["completed_at"])
                if total is None or total <= 0:
                    continue
                profile = meta.get("profile") or {}
                calls = profile.get("calls") or []
                prov = provider_of(*(c.get("metadata", {}).get("provider") for c in calls),
                                   (meta.get("topics") or {}).get("provider"), meta.get("provider"))
                if prov == "unknown" and str(row["created_at"])[:10] < DEEPSEEK_SINCE["diagnosis"]:
                    prov = "qwen*"
                errors = loads(row["stage_errors_json"])
                failure = None if row["status"] == "completed" and not errors else (
                    "partial" if row["status"] == "completed" else "failed_run")
                base = {"source": "db", "chain": "diagnosis", "family": "analysis_runs", "file": db,
                        "date": str(row["created_at"])[:10], "provider": prov}
                keep(("analysis", row["id"], "run"), {**base, "level": "run", "stage": "run", "seconds": total,
                     "failure": failure, "retries": profile.get("retryCount"),
                     "degraded": sorted((profile.get("degradedStages") or {}).keys())})
                prev = row["started_at"]
                for node, created in checkpoints.get(row["id"], []):
                    delta = seconds_between(prev, created)
                    prev = created
                    if delta is not None and delta >= 0:
                        keep(("analysis", row["id"], node), {**base, "level": "stage",
                             "stage": STAGE_ALIASES.get(node, node), "seconds": delta, "failure": None})

        if "simulation_runs" in tables:
            for row in con.execute("select * from simulation_runs"):
                meta = loads(row["model_metadata_json"])
                if meta.get("modelCalled") is False or meta.get("origin") == "oracle_showcase":
                    continue
                total = seconds_between(row["started_at"], row["completed_at"])
                if total is None or total <= 0:
                    continue
                calls = meta.get("responseCalls") or []
                errors = loads(row["stage_errors_json"])
                keep(("simulation", row["id"]), {
                    "source": "db", "chain": "audience_simulation", "family": "simulation_runs", "file": db,
                    "date": str(row["created_at"])[:10], "level": "run", "stage": "simulation_run",
                    "provider": provider_of(*(c.get("provider") for c in calls)), "seconds": total,
                    "failure": None if row["status"] == "completed" and not errors else "partial"})

        if "audience_analyses" in tables:
            for row in con.execute("select * from audience_analyses"):
                meta = loads(row["model_metadata_json"])
                total = seconds_between(row["created_at"], row["completed_at"])
                if meta.get("modelCalled") is False or total is None or total <= 0:
                    continue
                keep(("audience", row["id"]), {
                    "source": "db", "chain": "audience_simulation", "family": "audience_analyses", "file": db,
                    "date": str(row["created_at"])[:10], "level": "run", "stage": "audience_analysis",
                    "provider": provider_of(meta.get("provider"), meta.get("model")), "seconds": total,
                    "failure": None if row["status"] == "completed" else (
                        "partial" if row["status"] == "partially_completed" else (row["status"] or "failed"))})

        if "reader_selections" in tables:
            for row in con.execute("select * from reader_selections"):
                total = seconds_between(row["started_at"], row["completed_at"])
                if total is None:
                    continue
                meta = loads(row["model_metadata_json"])
                keep(("selection", row["id"]), {
                    "source": "db", "chain": "audience_simulation", "family": "reader_selections", "file": db,
                    "date": str(row["created_at"])[:10], "level": "run", "stage": "reader_selection",
                    "provider": provider_of(meta.get("provider"), meta.get("model")), "seconds": total,
                    "failure": None if row["status"] == "completed" else (row["error_code"] or row["status"])})

        if {"content_collaboration_runs", "content_collaboration_messages"} <= tables:
            for row in con.execute("select * from content_collaboration_runs"):
                reply = con.execute(
                    "select created_at, model_metadata_json from content_collaboration_messages "
                    "where session_id=? and sender_role!='creator' and created_at>=? order by created_at limit 1",
                    (row["session_id"], row["started_at"] or row["created_at"])).fetchone()
                end = row["completed_at"] or (reply["created_at"] if reply else None)
                total = seconds_between(row["started_at"], end)
                if total is None:
                    continue
                meta = loads(reply["model_metadata_json"]) if reply else {}
                keep(("collab", row["id"]), {
                    "source": "db", "chain": "writing", "family": "content_collaboration_runs", "file": db,
                    "date": str(row["created_at"])[:10], "level": "run", "stage": "writing_turn",
                    "provider": provider_of(meta.get("provider"), meta.get("model")), "seconds": total,
                    "failure": None if not row["error_code"] else row["error_code"]})

        if "xhs_capture_jobs" in tables:
            for row in con.execute("select * from xhs_capture_jobs"):
                total = seconds_between(row["started_at"], row["completed_at"])
                if total is None:
                    continue
                keep(("capture", row["id"]), {
                    "source": "db", "chain": "import", "family": "xhs_capture_jobs", "file": db,
                    "date": str(row["created_at"])[:10], "level": "run", "stage": "capture_job",
                    "provider": "mediacrawler", "seconds": total,
                    "failure": None if row["status"] == "completed" else (row["status"] or "failed"),
                    "error": (row["error"] or "")[:120]})
        con.close()
    return list(seen.values())


def dedupe(records):
    """Drop repeats of one call recorded in several places of an experiment directory.

    Reports often keep the same call under ``requests`` and ``calls`` or in a second file; a call is
    identified by experiment family, stage, provider, failure and elapsed time to the millisecond.
    """
    seen, out = set(), []
    for r in records:
        key = (r["family"], r["level"], r["stage"], r["provider"], r["failure"], round(r["seconds"], 3))
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


# --------------------------------------------------------------- summarize

def pct(values, q):
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def summarize(records):
    groups = defaultdict(list)
    for r in records:
        groups[(r["chain"], r["source"], r["level"], r["stage"], r["provider"])].append(r)
    rows = []
    for (chain, source, level, stage, prov), items in sorted(groups.items()):
        ok = [i["seconds"] for i in items if not i["failure"]]
        failures = defaultdict(int)
        for i in items:
            if i["failure"]:
                failures[i["failure"]] += 1
        retried = sum(1 for i in items if isinstance(i.get("attempts"), int) and i["attempts"] > 1)
        dates = sorted(d for d in (i.get("date") for i in items) if d)
        rows.append({
            "chain": chain, "source": source, "level": level, "stage": stage, "provider": prov,
            "n": len(items), "n_ok": len(ok), "failures": dict(failures), "retried": retried,
            "median": pct(ok, .5), "p90": pct(ok, .9), "max": max(ok) if ok else None,
            "from": dates[0] if dates else None, "to": dates[-1] if dates else None,
        })
    return rows


def fmt(v):
    return "—" if v is None else (f"{v:.1f}" if v < 100 else f"{v:.0f}")


def markdown(rows, min_n):
    out = ["| 链路 | 来源 | 层级 | 阶段 | provider | n | 成功 | 中位数(s) | P90(s) | 最大(s) | 失败 | 重试 | 时间范围 |",
           "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["n"] < min_n:
            continue
        fails = ", ".join(f"{k}×{v}" for k, v in sorted(r["failures"].items())) or "—"
        span = f"{r['from']}～{r['to']}" if r["from"] != r["to"] else (r["from"] or "—")
        out.append(f"| {r['chain']} | {r['source']} | {r['level']} | {r['stage']} | {r['provider']} | {r['n']} | "
                   f"{r['n_ok']} | {fmt(r['median'])} | {fmt(r['p90'])} | {fmt(r['max'])} | {fails} | "
                   f"{r['retried'] or '—'} | {span} |")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--evals", default=str(ROOT / "data/evals"))
    parser.add_argument("--database", action="append", help="database path relative to repo root (repeatable)")
    parser.add_argument("--min-n", type=int, default=1, help="hide groups with fewer records")
    parser.add_argument("--output", help="directory for records.json, summary.json and summary.md")
    args = parser.parse_args()
    records = db_records(args.database or DEFAULT_DATABASES) + dedupe(eval_records(Path(args.evals)))
    rows = summarize(records)
    table = markdown(rows, args.min_n)
    if args.output:
        out = Path(args.output)
        out.mkdir(parents=True, exist_ok=True)
        (out / "records.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "summary.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
        (out / "summary.md").write_text(table + "\n", encoding="utf-8")
    print(table)
    print(f"\nrecords={len(records)} groups={len(rows)}")


if __name__ == "__main__":
    main()
