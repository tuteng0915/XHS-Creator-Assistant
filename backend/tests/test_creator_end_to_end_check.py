import asyncio
import importlib.util
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from app.config import Settings
from app.models import ModelOperation


@pytest.fixture
def check(monkeypatch):
    scripts = Path(__file__).resolve().parents[2] / "scripts"
    monkeypatch.syspath_prepend(str(scripts))
    spec = importlib.util.spec_from_file_location(
        "creation_eval", scripts / "check_creator_end_to_end.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_clone_is_independent(check, tmp_path):
    source, clone = tmp_path / "original.db", tmp_path / "clone.db"
    with sqlite3.connect(source) as c:
        c.execute("CREATE TABLE items(value TEXT)")
        c.execute("INSERT INTO items VALUES ('original')")
    check.clone_database(source, clone)
    with sqlite3.connect(clone) as c:
        c.execute("UPDATE items SET value='changed'")
    with sqlite3.connect(source) as c:
        assert c.execute("SELECT value FROM items").fetchone()[0] == "original"


def test_preview_never_loads_credentials_or_creates_app(check, monkeypatch, tmp_path):
    def forbidden(*args):
        pytest.fail("Preview must not load credentials or instantiate the application")

    monkeypatch.setattr(check, "load_env_file_defaults", forbidden)
    monkeypatch.setattr(check, "load_frozen_cases", lambda _: ([{}], "hash"))
    monkeypatch.setattr(check.importlib, "import_module", forbidden)
    target = tmp_path / "output"
    asyncio.run(check.main(SimpleNamespace(live=False, output=target)))
    assert not target.exists()


@pytest.mark.parametrize("limit", [2, 22])
def test_capture_redacts_secrets_omits_reasoning_and_enforces_budget(check, tmp_path, limit):
    settings = Settings(database_path=tmp_path / "db", upload_directory=tmp_path,
                        deepseek_api_key="private-test-key")
    report = {"requests": [], "maxRequests": limit}
    trace = check.Trace(report, tmp_path, settings)
    trace.arm = {"account": "test", "arm": "simple"}

    def response(request):
        return httpx.Response(200, json={"model": "fake", "choices": [{
            "message": {"content": "private-test-key", "reasoning_content": "not retained"},
            "finish_reason": "stop"}]})

    service = SimpleNamespace(_deepseek_client=lambda _: httpx.AsyncClient(
        transport=httpx.MockTransport(response)))
    trace.install(service)

    async def run():
        async with service._deepseek_client(ModelOperation.SIMULATION_REACTION) as client:
            for _ in range(limit):
                await client.post("https://example.test", json={"messages": []})
            with pytest.raises(RuntimeError, match="Hard limit"):
                await client.post("https://example.test", json={"messages": []})

    asyncio.run(run())
    saved = (tmp_path / "report.json").read_text()
    assert "private-test-key" not in saved and "not retained" not in saved
    assert len(report["requests"]) == limit


def test_manual_edit_is_formatting_not_another_writing_pass(check):
    assert check.format_only("原有观点。\n") == "原有观点。\n\n"


def test_actual_api_save_check_uses_clone_no_model_and_rejects_stale_edit(
    check, app, monkeypatch, tmp_path,
):
    from test_content_collaboration_sessions import create_workspace_and_topic

    workspace, _ = create_workspace_and_topic(app)
    monkeypatch.setattr(check, "SOURCE", app.state.settings.database_path)
    monkeypatch.setattr(check, "PLAN", [("test", workspace["id"], "unused", [])])
    report = tmp_path / "source.json"
    report.write_text(json.dumps({"arms": [{"account": "test", "arm": "simple",
                                            "initial": {"title": "标题", "body": "真实首稿。"}}]}))
    output = tmp_path / "check"
    asyncio.run(check.persistence_check(report, output))
    result = json.loads((output / "report.json").read_text())
    assert result["modelRequests"] == 0
    assert result["checks"][0]["reopenExact"]
    assert result["checks"][0]["staleSaveRejected"]
    with app.state.database.read() as connection:
        assert not connection.execute("SELECT id FROM topics WHERE title='标题'").fetchall()
