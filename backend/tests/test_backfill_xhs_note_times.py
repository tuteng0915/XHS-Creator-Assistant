from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


def load_backfill_module():
    path = Path(__file__).resolve().parents[2] / "scripts" / "backfill_xhs_note_times.py"
    spec = importlib.util.spec_from_file_location("backfill_xhs_note_times", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_backfill_fills_only_missing_publication_dates():
    backfill = load_backfill_module().backfill_payload
    original = {
        "creator": {"displayName": "中文账号"},
        "notes": [
            {"noteId": "n1", "title": "第一篇", "publishedAt": None},
            {"noteId": "n2", "title": "第二篇", "publishedAt": 2000},
        ],
    }
    updated, count = backfill(original, {"n1": 1000, "n2": 2000})
    assert count == 1
    assert updated["notes"][0]["publishedAt"] == 1000
    assert updated["notes"][1]["publishedAt"] == 2000
    assert updated["creator"] == original["creator"]
    assert original["notes"][0]["publishedAt"] is None
    assert backfill(updated, {"n1": 1000, "n2": 2000})[1] == 0


@pytest.mark.parametrize(
    "payload,times",
    [
        ({"notes": [{"noteId": "n1"}]}, {"n2": 1000}),
        ({"notes": [{"noteId": "n1"}, {"noteId": "n1"}]}, {"n1": 1000}),
        ({"notes": [{"noteId": "n1", "publishedAt": 2000}]}, {"n1": 1000}),
    ],
)
def test_backfill_rejects_mismatched_source(payload, times):
    with pytest.raises(ValueError):
        load_backfill_module().backfill_payload(payload, times)
