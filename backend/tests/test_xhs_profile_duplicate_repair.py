from __future__ import annotations

import importlib.util
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "repair_xhs_profile_duplicates.py"


def load_repair_module():
    spec = importlib.util.spec_from_file_location("repair_xhs_profile_duplicates", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def duplicate_profile() -> dict:
    note = {
        "noteId": "n1", "title": "原始笔记", "desc": "中文正文",
        "comments": [
            {"commentId": "c1", "content": "这是什么意思？"},
            {"commentId": "c1", "content": "这是什么意思？"},
        ],
    }
    return {
        "schemaVersion": "xhs-creator-profile/v1",
        "creator": {"displayName": "测试账号"},
        "notes": [note, {**note, "comments": list(note["comments"])}],
    }


def test_repair_removes_only_exact_duplicates_and_preserves_chinese():
    module = load_repair_module()
    original = duplicate_profile()

    cleaned, removed_notes, removed_comments = module.deduplicate_profile(original)

    assert (removed_notes, removed_comments) == (1, 3)
    assert len(cleaned["notes"]) == 1
    assert cleaned["notes"][0]["desc"] == "中文正文"
    assert cleaned["notes"][0]["comments"] == [
        {"commentId": "c1", "content": "这是什么意思？"}
    ]
    assert len(original["notes"]) == 2


def test_repair_refuses_divergent_duplicate_content():
    module = load_repair_module()
    original = duplicate_profile()
    original["notes"][1]["desc"] = "另一段正文"
    with pytest.raises(ValueError, match="需要人工检查"):
        module.deduplicate_profile(original)


def test_repair_cli_is_dry_run_by_default_and_backs_up_before_apply(tmp_path: Path):
    database = tmp_path / "app.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            "CREATE TABLE source_materials ("
            "id TEXT PRIMARY KEY, type TEXT, text_content TEXT, updated_at TEXT)"
        )
        connection.execute(
            "INSERT INTO source_materials VALUES (?,?,?,?)",
            ("asset-1", "xhs_creator_profile",
             json.dumps(duplicate_profile(), ensure_ascii=False), "original"),
        )
    command = [sys.executable, str(SCRIPT), "--database", str(database),
               "--asset-id", "asset-1"]

    dry_run = subprocess.run(command, capture_output=True, text=True, check=True)
    assert "未修改数据库" in dry_run.stdout
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT updated_at FROM source_materials WHERE id='asset-1'"
        ).fetchone()[0] == "original"

    subprocess.run([*command, "--apply"], capture_output=True, text=True, check=True)
    backups = list((tmp_path / "backups").glob("xhs-profile-dedup-*.sqlite3"))
    assert len(backups) == 1
    with sqlite3.connect(backups[0]) as connection:
        previous = json.loads(connection.execute(
            "SELECT text_content FROM source_materials WHERE id='asset-1'"
        ).fetchone()[0])
    with sqlite3.connect(database) as connection:
        current = json.loads(connection.execute(
            "SELECT text_content FROM source_materials WHERE id='asset-1'"
        ).fetchone()[0])
    assert len(previous["notes"]) == 2
    assert len(current["notes"]) == 1
    assert len(current["notes"][0]["comments"]) == 1

    repeat = subprocess.run([*command, "--apply"], capture_output=True, text=True,
                            check=True)
    assert "未修改数据库" in repeat.stdout
    assert len(list((tmp_path / "backups").glob("*.sqlite3"))) == 1
