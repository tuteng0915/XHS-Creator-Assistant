"""Back up SQLite, then remove only accidental empty 新账号档案 records."""

import argparse
import sqlite3
from datetime import datetime
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("database", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    c = sqlite3.connect(args.database)
    c.execute("PRAGMA foreign_keys=ON")
    tables = [
        r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")
    ]
    owned = [
        t
        for t in tables
        if "workspace_id" in [r[1] for r in c.execute(f'PRAGMA table_info("{t}")')]
    ]
    metadata = {
        "positioning_versions",
        "app_user_workspaces",
        "workspace_skills",
        "workspace_agents",
        "workspace_workflows",
    }
    candidates = []
    for wid, name in c.execute(
        "SELECT id,name FROM creator_workspaces WHERE name='新账号档案'"
    ):
        counts = {
            t: c.execute(
                f'SELECT count(*) FROM "{t}" WHERE workspace_id=?', (wid,)
            ).fetchone()[0]
            for t in owned
        }
        if any(n for t, n in counts.items() if t not in metadata):
            continue
        if c.execute(
            "SELECT count(*) FROM positioning_versions WHERE workspace_id=? AND trim(positioning_text) != ''",
            (wid,),
        ).fetchone()[0]:
            continue
        if any(
            c.execute(
                f'SELECT count(*) FROM "{t}" WHERE workspace_id=? '
                "AND (source != 'builtin' OR user_notes != '')",
                (wid,),
            ).fetchone()[0]
            for t in ["workspace_skills", "workspace_agents", "workspace_workflows"]
            if t in tables
        ):
            continue
        candidates.append(wid)
        print(name, wid)
    if args.apply and candidates:
        backup = (
            args.database.parent
            / "backups"
            / f"pre-empty-account-cleanup-{datetime.now():%Y%m%d-%H%M%S}.sqlite3"
        )
        backup.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(backup) as dest:
            c.backup(dest)
        print("Backup:", backup)
        with c:
            for wid in candidates:
                c.execute(
                    "UPDATE creator_workspaces SET current_positioning_version_id=NULL WHERE id=?",
                    (wid,),
                )
                for table in [
                    "workspace_workflows",
                    "workspace_agents",
                    "workspace_skills",
                    "positioning_versions",
                    "app_user_workspaces",
                ]:
                    if table in tables:
                        c.execute(f'DELETE FROM "{table}" WHERE workspace_id=?', (wid,))
                c.execute("DELETE FROM creator_workspaces WHERE id=?", (wid,))
        print("Removed:", len(candidates))
    c.close()


if __name__ == "__main__":
    main()
