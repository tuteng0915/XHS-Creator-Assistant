"""Run the existing crawler while retaining only public account-level counters.

The upstream teaching export skips creator records. This adapter does not change
upstream files or retain cookies, follower identities, location, or demographics.
"""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path


def account_metrics(creator: dict) -> dict:
    interactions = creator.get("interactions") or []
    counters = {
        item.get("type"): item.get("count")
        for item in interactions
        if isinstance(item, dict)
    }
    basic = creator.get("basicInfo") or creator.get("basic_info") or {}
    return {
        "displayName": basic.get("nickname") or creator.get("nickname") or "",
        "followers": counters.get("fans"),
        # "interaction" is likes AND collections, never label it as pure likes.
        "totalLikes": counters.get("likes"),
        "likesAndCollections": counters.get("interaction"),
    }


def main():
    output = Path(sys.argv[1])
    sys.path.insert(0, str(Path.cwd()))
    import store.xhs as xhs_store

    original = xhs_store.save_creator

    async def save_creator(user_id, creator):
        await original(user_id, creator)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(account_metrics(creator), ensure_ascii=False), encoding="utf-8"
        )

    xhs_store.save_creator = save_creator
    sys.argv = ["main.py", *sys.argv[2:]]
    runpy.run_path("main.py", run_name="__main__")


if __name__ == "__main__":
    main()
