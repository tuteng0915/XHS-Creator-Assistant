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


def test_smoke_preserves_deepseek_and_scoped_credentials_without_model_calls(
    settings, tmp_path, monkeypatch,
):
    path = Path(__file__).resolve().parents[2] / "scripts/smoke_live_workflows.py"
    spec = importlib.util.spec_from_file_location("smoke_deepseek_settings", path)
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    base = replace(settings, model_provider="deepseek", deepseek_api_key="test-only",
                   deepseek_model="deepseek-test", deepseek_read_timeout_seconds=120,
                   deepseek_base_url="https://deepseek.test/v1")
    monkeypatch.setattr(smoke, "load_env_file", lambda _: None)
    monkeypatch.setattr(smoke.Settings, "from_environment", lambda: base)
    captured = []

    class Captured(Exception):
        pass

    def capture(configured):
        captured.append(configured)
        raise Captured

    monkeypatch.setattr(smoke, "create_app", capture)
    with pytest.raises(Captured):
        asyncio.run(smoke.run_smoke(Namespace(env_file=str(tmp_path / "unused.env"))))
    isolated, = captured
    assert isolated.model_provider == "deepseek"
    assert isolated.deepseek_api_key == base.deepseek_api_key
    assert isolated.deepseek_model == base.deepseek_model
    assert isolated.deepseek_base_url == base.deepseek_base_url
    assert isolated.deepseek_read_timeout_seconds == 120
    assert isolated.creator_writing_provider == base.creator_writing_provider
    assert isolated.account_diagnosis_provider == base.account_diagnosis_provider
    assert not isolated.database_path.parent.exists()
