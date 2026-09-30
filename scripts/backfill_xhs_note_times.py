"""Backfill publication times in the two historical XHS fixture imports.

Run with --dry-run first. The script validates note IDs against the original
MediaCrawler export and saves an online SQLite backup before modifying data.
It never changes analysis or simulation execution snapshots.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import UTC, datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CASES = {
    "_tt": "297c0629-05ef-4274-8526-b9f161c06d42",
    "QSheep": "18892280-ceba-444b-b2e8-52b57aa17996",
}


def publication_times(raw_path: Path) -> dict[str, int]:
    times: dict[str, int] = {}
    for line in raw_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        note_id = row["note_id"]
        value = row.get("time") or row.get("publish_time")
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"Missing or invalid publication time for {note_id}")
        if note_id in times:
            raise ValueError(f"Duplicate raw note ID: {note_id}")
        times[note_id] = value
    if not times:
        raise ValueError(f"No raw notes in {raw_path}")
    return times


def backfill_payload(payload: dict, times: dict[str, int]) -> tuple[dict, int]:
    """Return a copy with only missing notes[].publishedAt fields filled."""
    result = json.loads(json.dumps(payload, ensure_ascii=False))
    notes = result.get("notes")
    if not isinstance(notes, list):
        raise ValueError("Creator profile has no notes list")
    ids = [note.get("noteId") for note in notes]
    if len(ids) != len(set(ids)) or set(ids) != set(times):
        raise ValueError("Creator profile note IDs do not match the raw export")
    changed = 0
    for note in notes:
        expected = times[note["noteId"]]
        current = note.get("publishedAt")
        if current is None:
            note["publishedAt"] = expected
            changed += 1
        elif current != expected:
            raise ValueError(f"Conflicting publication time for {note['noteId']}")
    return result, changed


def snapshot_rows(connection: sqlite3.Connection) -> dict[str, dict[str, str]]:
    snapshots = {}
    for table in ("analysis_runs", "audience_analyses", "simulation_runs"):
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        if "input_snapshot_json" not in columns:
            continue
        snapshots[table] = dict(
            connection.execute(f"SELECT id, input_snapshot_json FROM {table}")
        )
    return snapshots


def run(*, dry_run: bool) -> None:
    database_path = ROOT / "data" / "app.sqlite3"
    connection = sqlite3.connect(database_path, timeout=10)
    connection.row_factory = sqlite3.Row
    plans = []
    for code, source_id in CASES.items():
        raw_path = (
            ROOT / "data" / "xhs-fixtures" / code / "xhs" / "jsonl"
            / "creator_contents_2026-08-22.jsonl"
        )
        package_path = (
            ROOT / "data" / "xhs-import-packages" / code
            / "xhs_creator_profile.json"
        )
        times = publication_times(raw_path)
        package = json.loads(package_path.read_text(encoding="utf-8"))
        new_package, package_count = backfill_payload(package, times)
        row = connection.execute(
            "SELECT text_content, updated_at FROM source_materials WHERE id = ? ",
            (source_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Missing source material for {code}: {source_id}")
        asset = json.loads(row["text_content"])
        new_asset, asset_count = backfill_payload(asset, times)
        plans.append(
            (code, source_id, package_path, new_package, package_count,
             row["text_content"], row["updated_at"], new_asset, asset_count)
        )
        print(
            f"{code}: {len(times)} raw notes; "
            f"{package_count} package dates and {asset_count} asset dates to fill"
        )
    if dry_run:
        print("Dry run: no files or database rows changed")
        connection.close()
        return
    if all(package_count == asset_count == 0 for _, _, _, _, package_count,
           _, _, _, asset_count in plans):
        print("All publication times are already present; nothing changed")
        connection.close()
        return

    backup_dir = ROOT / "data" / "backups" / (
        "xhs-note-times-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    )
    backup_dir.mkdir(parents=True, exist_ok=False)
    with sqlite3.connect(backup_dir / "app.sqlite3") as backup:
        connection.backup(backup)
    for code, _, package_path, *_ in plans:
        shutil.copy2(package_path, backup_dir / f"{code}_xhs_creator_profile.json")
    print(f"Backup: {backup_dir}")

    staged = []
    for code, _, package_path, new_package, *_ in plans:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=package_path.parent,
            prefix=f".{code}-dates-", suffix=".json", delete=False,
        ) as tmp:
            json.dump(new_package, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            staged.append((code, package_path, Path(tmp.name)))

    originals = snapshot_rows(connection)
    replaced = []
    try:
        connection.execute("BEGIN IMMEDIATE")
        for code, source_id, _, _, _, old_text, old_updated, new_asset, count in plans:
            if count == 0:
                continue
            cursor = connection.execute(
                "UPDATE source_materials SET text_content = ?, updated_at = ? "
                "WHERE id = ? AND text_content = ? AND updated_at = ?",
                (
                    json.dumps(new_asset, ensure_ascii=False, indent=2),
                    datetime.now(UTC).isoformat(), source_id, old_text, old_updated,
                ),
            )
            if cursor.rowcount != 1:
                raise RuntimeError(f"{code} asset changed during backfill; aborting")
        for code, package_path, temporary_path in staged:
            os.replace(temporary_path, package_path)
            replaced.append((code, package_path))
        for table, original_rows in originals.items():
            current = dict(connection.execute(
                f"SELECT id, input_snapshot_json FROM {table}"
            ))
            if any(current.get(key) != value for key, value in original_rows.items()):
                raise RuntimeError(f"Execution snapshots changed unexpectedly in {table}")
        connection.commit()
        print("Backfill complete; existing execution snapshots unchanged")
    except Exception:
        connection.rollback()
        for code, package_path in replaced:
            shutil.copy2(backup_dir / f"{code}_xhs_creator_profile.json", package_path)
        raise
    finally:
        for _, _, temporary_path in staged:
            temporary_path.unlink(missing_ok=True)
        connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    run(dry_run=parser.parse_args().dry_run)
