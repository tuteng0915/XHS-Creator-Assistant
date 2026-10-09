"""Append prewritten showcase histories to verified existing account workspaces.

Default: validate and report only. --apply first creates a SQLite online backup.
No server startup, migration, crawling, model calls or automatic reader adoption.
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.db.database import SQLiteDatabase  # noqa: E402
from app.services.workspace_showcases import seed_workspace_showcases  # noqa: E402


def backup_database(path: Path) -> Path:
    # This directory is covered by the repository's data/ ignore rule, including
    # when --database refers to a collaborator's database somewhere else.
    directory = ROOT / "data" / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    backup = directory / f"before-workspace-showcases-{stamp}-{uuid4().hex[:8]}.sqlite3"
    descriptor = os.open(backup, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(descriptor)
    source = None
    try:
        source = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        with sqlite3.connect(backup) as target:
            source.backup(target)
            if target.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("导入前备份未通过完整性校验，未写入数据库")
    except Exception:
        backup.unlink(missing_ok=True)
        raise
    finally:
        if source is not None:
            source.close()
    return backup


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database", type=Path, default=ROOT / "data" / "app.sqlite3")
    parser.add_argument("--apply", action="store_true", help="备份后追加已完成示例历史")
    args = parser.parse_args(argv)
    from app.services.workspace_showcase_content import WORKSPACE_SHOWCASES

    database = SQLiteDatabase(args.database)
    report = seed_workspace_showcases(database, WORKSPACE_SHOWCASES)
    if args.apply and report["newRecords"]:
        backup = backup_database(args.database)
        report = seed_workspace_showcases(database, WORKSPACE_SHOWCASES, apply=True)
        report["backup"] = str(backup)
    elif args.apply:
        report["mode"] = "applied"
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    try:
        main()
    except (ValueError, sqlite3.Error) as error:
        print(f"未导入：{error}", file=sys.stderr)
        raise SystemExit(1) from None
