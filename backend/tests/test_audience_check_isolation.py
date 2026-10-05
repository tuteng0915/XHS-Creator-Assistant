"""Fresh processes: pytest's app bootstrap must not hide CLI import side effects."""

import builtins
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from test_audience_reaction_check import load_check

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/check_audience_reactions.py"


@pytest.mark.parametrize("existing", [False, True])
@pytest.mark.parametrize("mode", ["help", "preview", "invalid", "import", "graph"])
def test_fresh_process_never_initializes_configured_database(tmp_path, existing, mode):
    database = tmp_path / "user" / "database.sqlite3"
    uploads = tmp_path / "user-uploads"
    if existing:
        database.parent.mkdir()
        with sqlite3.connect(database) as connection:
            connection.execute("CREATE TABLE sentinel (value TEXT)")
            connection.execute("INSERT INTO sentinel VALUES ('keep')")
    before = database.read_bytes() if existing else None
    temporary = tmp_path / "temporary"
    temporary.mkdir()
    environment = {**os.environ, "DATABASE_PATH": str(database),
                   "UPLOAD_DIRECTORY": str(uploads), "TMPDIR": str(temporary)}
    if mode in {"import", "graph"}:
        code = """
import asyncio, os, runpy, sys
from pathlib import Path
script, mode = sys.argv[1:]
before = {key: os.environ[key] for key in ('DATABASE_PATH', 'UPLOAD_DIRECTORY')}
module = runpy.run_path(script)
assert 'app.main' not in sys.modules
if mode == 'graph':
    sys.path.insert(0, str(Path(script).parents[1] / 'backend/tests'))
    from test_audience_reaction_check import Model
    report = asyncio.run(module['run_check'](Model(), module['Settings'].from_environment()))
    assert report['status'] == 'completed'
    assert report['paidRequests'] == 6  # Injected model, no external requests.
assert all(os.environ[key] == value for key, value in before.items())
"""
        command = [sys.executable, "-c", code, str(SCRIPT), mode]
    else:
        args = {"help": ["--help"], "preview": [], "invalid": ["--task-pair"]}[mode]
        command = [sys.executable, str(SCRIPT), *args]
    result = subprocess.run(command, cwd=ROOT, env=environment, capture_output=True,
                            text=True, timeout=30)
    assert result.returncode == (2 if mode == "invalid" else 0), result.stderr
    assert not uploads.exists()
    if existing:
        assert database.read_bytes() == before
        assert sorted(path.name for path in database.parent.iterdir()) == [database.name]
    else:
        assert not database.parent.exists()
    assert list(temporary.iterdir()) == []


@pytest.mark.parametrize("configured", [False, True])
def test_failed_factory_import_restores_environment_and_cleans_bootstrap(
    monkeypatch, settings, configured,
):
    module = load_check()
    keys = ("DATABASE_PATH", "UPLOAD_DIRECTORY")
    for key in keys:
        if configured:
            monkeypatch.setenv(key, f"original-{key}")
        else:
            monkeypatch.delenv(key, raising=False)
    before = {key: os.environ.get(key) for key in keys}
    original_import = builtins.__import__
    temporary_roots = []

    def fail_import(name, *args, **kwargs):
        if name == "app.main":
            root = Path(os.environ["DATABASE_PATH"]).parent
            assert root.is_dir()
            assert Path(os.environ["UPLOAD_DIRECTORY"]).parent == root
            temporary_roots.append(root)
            raise ImportError("injected factory failure")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fail_import)
    with pytest.raises(ImportError, match="injected factory failure"):
        module.create_app(settings)
    assert {key: os.environ.get(key) for key in keys} == before
    assert len(temporary_roots) == 1
    assert not temporary_roots[0].exists()
