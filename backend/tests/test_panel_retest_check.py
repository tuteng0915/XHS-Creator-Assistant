import asyncio
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
from test_simulated_fans import seeded as seeded

from app.models import ModelCallResponse, ModelOperation


def load_check():
    path = Path(__file__).resolve().parents[2] / "scripts/check_panel_retest.py"
    spec = importlib.util.spec_from_file_location("panel_retest_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Model:
    def __init__(self, fail_at=None, invalid=False):
        self.contexts = []
        self.fail_at, self.invalid = fail_at, invalid

    async def call_operation(self, operation, context):
        self.contexts.append(context)
        if self.fail_at == len(self.contexts):
            raise RuntimeError("secret-must-not-be-logged")
        if operation == ModelOperation.SIMULATION_REACTION:
            output = {
                "reaction": {
                    "personaId": "wrong" if self.invalid else context["persona"]["id"],
                    "stance": "理解",
                    "action": "comment",
                    "quote": "只在首轮出现的留言" if len(self.contexts) < 3 else "新版留言",
                }
            }
        else:
            output = {"synthesis": {"verdict": "测试完成", "editorFeedback": []}}
        return ModelCallResponse(
            output=output,
            model_metadata={"provider": "test", "model": "fake", "apiKey": "never-save"},
        )


def test_pair_uses_real_services_and_only_mutates_temporary_copy(app, seeded, settings):
    module = load_check()
    wid, _, _, fans = seeded
    ids = [f["id"] for f in fans[:2]]
    source = app.state.database.path
    before = module.file_hash(source)
    model = Model()
    report = asyncio.run(module.check(source, wid, ids, settings, model))
    assert report["status"] == "completed"
    assert report["semanticStatus"] == "not_reviewed"
    assert report["requestAttempts"] == 6 == len(model.contexts)
    first, second = report["runs"]
    assert second["parentSimulationId"] == first["id"]
    assert first["personaDefinitions"] == second["personaDefinitions"]
    assert first["inputSnapshot"]["panelTask"] == second["inputSnapshot"]["panelTask"]
    assert not first["inputSnapshot"]["panelTask"]["discussionEnabled"]
    assert second["inputSnapshot"]["topic"]["body"] == module.BODY.replace(
        module.BEFORE, module.AFTER
    )
    assert "只在首轮出现的留言" not in json.dumps(model.contexts[3:5], ensure_ascii=False)
    assert module.file_hash(source) == before
    assert report["sourceDatabaseUnchanged"]
    assert len(report["comparison"]["readers"]) == 2
    assert "never-save" not in json.dumps(report)
    json.dumps(report)  # All records, including comparison timestamps, are serializable.


@pytest.mark.parametrize(
    "fail_at,invalid,attempts", [(1, False, 1), (None, True, 1), (4, False, 4)]
)
def test_failure_stops_paid_attempts_without_graph_retry(
    app, seeded, settings, fail_at, invalid, attempts
):
    module = load_check()
    wid, _, _, fans = seeded
    model = Model(fail_at, invalid)
    report = asyncio.run(
        module.check(app.state.database.path, wid, [f["id"] for f in fans[:2]], settings, model)
    )
    assert report["status"] == "incomplete"
    assert report["requestAttempts"] == attempts == len(model.contexts)
    code = "persona_id_mismatch" if invalid else "model_request_failed"
    assert report["calls"][-1]["failureCode"] == code
    assert any(code in error for error in report["runs"][-1]["stageErrors"].values())
    assert "secret-must-not-be-logged" not in json.dumps(report)
    assert report["sourceDatabaseUnchanged"]


@pytest.mark.parametrize("schema_error", [False, True])
def test_invalid_response_keeps_first_diagnostic_without_paid_retry(schema_error):
    module = load_check()

    class InvalidQuote(Model):
        async def call_operation(self, operation, context):
            response = await super().call_operation(operation, context)
            if schema_error:
                response.output = {"reaction": "invalid"}
            else:
                response.output["reaction"]["triggerQuote"] = "自己练习……无需报名"
            return response

    model = InvalidQuote()
    code = "response_schema_invalid" if schema_error else "trigger_quote_not_in_frozen_text"

    async def run():
        calls = module.BoundedCalls(model)
        context = {"persona": {"id": "reader"}, "topic": {"body": "自己练习，无需报名"}}
        for _ in range(2):
            with pytest.raises(RuntimeError, match=code):
                await calls.call_operation(ModelOperation.SIMULATION_REACTION, context)
        with pytest.raises(RuntimeError, match="本步骤未发送模型请求"):
            await calls.call_operation(ModelOperation.SIMULATION_SYNTHESIS, {})
        assert calls.calls[0]["failureCode"] == code
        assert len(calls.calls) == 1

    asyncio.run(run())
    assert len(model.contexts) == 1


def test_budget_and_disabled_operations_do_not_call_service():
    module = load_check()
    model = Model()

    async def run():
        calls = module.BoundedCalls(model)
        with pytest.raises(RuntimeError):
            await calls.call_operation(ModelOperation.SIMULATION_DEBATE, {})
        for index in range(6):
            calls.phase = str(index)
            await calls.call_operation(ModelOperation.SIMULATION_SYNTHESIS, {})
        with pytest.raises(RuntimeError):
            await calls.call_operation(ModelOperation.SIMULATION_SYNTHESIS, {})
        calls.phase = "extra"
        with pytest.raises(RuntimeError):
            await calls.call_operation(ModelOperation.SIMULATION_SYNTHESIS, {})

    asyncio.run(run())
    assert len(model.contexts) == 6


def test_invalid_reader_selection_refused_before_call(app, seeded, settings):
    module = load_check()
    wid, _, _, fans = seeded
    model = Model()
    with pytest.raises(ValueError):
        asyncio.run(
            module.check(app.state.database.path, wid, [fans[0]["id"]] * 2, settings, model)
        )
    assert model.contexts == []


def test_free_preview_does_not_bootstrap_database_or_call_model(app, seeded, tmp_path):
    module = load_check()
    wid, _, _, fans = seeded
    source = app.state.database.path
    before = module.file_hash(source)
    unwanted = tmp_path / "must-not-create.sqlite3"
    result = subprocess.run(
        [
            sys.executable,
            str(Path(module.__file__)),
            "--database",
            str(source),
            "--workspace-id",
            wid,
            "--reader-ids",
            *[f["id"] for f in fans[:2]],
        ],
        env={**os.environ, "DATABASE_PATH": str(unwanted)},
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["requestAttempts"] == 0
    assert not unwanted.exists()
    assert module.file_hash(source) == before


def test_existing_report_directory_is_not_overwritten(app, seeded, tmp_path, monkeypatch):
    module = load_check()
    wid, _, _, fans = seeded
    output = tmp_path / "existing-report"
    output.mkdir()
    marker = output / "report.json"
    marker.write_text("existing")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "check",
            "--database",
            str(app.state.database.path),
            "--workspace-id",
            wid,
            "--reader-ids",
            *[f["id"] for f in fans[:2]],
            "--live",
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as error:
        module.main()
    assert error.value.code == 2
    assert marker.read_text() == "existing"
