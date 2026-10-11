import asyncio
import importlib.util
from argparse import Namespace
from dataclasses import replace
from pathlib import Path

import pytest

from app.models import ModelOperation
from app.services.model_calls import ModelCallService


@pytest.mark.parametrize("profile_model,expected", [
    ("", "qwen-test-general"), ("qwen3.8-max", "qwen3.8-max"),
])
def test_smoke_preserves_profile_model_without_starting_app_or_calling_models(
    settings, tmp_path, monkeypatch, profile_model, expected,
):
    path = Path(__file__).resolve().parents[2] / "scripts/smoke_live_workflows.py"
    spec = importlib.util.spec_from_file_location("smoke_workflow_settings", path)
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    base = replace(settings, qwen_model="qwen-test-general", qwen_profile_model=profile_model)
    monkeypatch.setattr(smoke, "load_env_file", lambda _: None)
    monkeypatch.setattr(smoke.Settings, "from_environment", lambda: base)
    captured = []

    class SettingsCaptured(Exception):
        pass

    def capture_without_starting_app(configured):
        captured.append(configured)
        raise SettingsCaptured

    monkeypatch.setattr(smoke, "create_app", capture_without_starting_app)
    with pytest.raises(SettingsCaptured):
        asyncio.run(smoke.run_smoke(Namespace(env_file=str(tmp_path / "unused.env"))))
    isolated, = captured
    assert isolated.qwen_profile_model == profile_model
    assert isolated.qwen_model == "qwen-test-general"
    assert ModelCallService(isolated).qwen_model_for(ModelOperation.PROFILE) == expected
    assert isolated.database_path != base.database_path
    assert not isolated.database_path.parent.exists()
