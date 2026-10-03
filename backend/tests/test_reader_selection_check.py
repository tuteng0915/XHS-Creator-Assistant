import asyncio
import hashlib
import json
import os
import runpy
import subprocess
import sys
from pathlib import Path

import pytest
from test_reader_selection import fan, snapshot
from test_simulated_fans import seeded as seeded

from app.services.reader_selection import prepare_reader_selection

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/check_reader_selection.py"


def test_preview_uses_saved_pool_read_only_without_bootstrapping_app(app, seeded, tmp_path):
    wid, _, _, fans = seeded
    database = app.state.database.path
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    unwanted = tmp_path / "must-not-create.sqlite3"
    result = subprocess.run([
        sys.executable, str(SCRIPT), "--database", str(database), "--workspace-id", wid,
    ], capture_output=True, text=True, check=True,
        env={**os.environ, "DATABASE_PATH": str(unwanted)})
    output = json.loads(result.stdout)
    assert output["modelCalls"] == 0 and output["candidateCount"] == len(fans)
    assert len(output["topics"]) == len(output["inputBytes"]) == 2
    assert not unwanted.exists()
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before


def test_missing_database_not_created(tmp_path):
    namespace = runpy.run_path(str(SCRIPT))
    missing = tmp_path / "missing.sqlite3"
    import sqlite3
    with pytest.raises(sqlite3.OperationalError):
        namespace["load_inputs"](missing, "workspace")
    assert not missing.exists()


def test_failed_real_check_does_not_retry_or_run_second_case():
    namespace = runpy.run_path(str(SCRIPT))
    inputs = prepare_reader_selection("w", snapshot(), [fan()])

    class Failure:
        calls = 0

        async def select(self, _inputs):
            self.calls += 1
            raise RuntimeError("Do not store this key or URL")

    provider = Failure()
    reports = asyncio.run(namespace["check"](provider, [inputs, inputs.model_copy(deep=True)]))
    assert provider.calls == len(reports) == 1
    assert reports[0]["errorType"] == "RuntimeError"
    assert "Do not store" not in str(reports)
    assert reports[0]["requestAttempted"]
