import os
from pathlib import Path

import pytest

from app.config import Settings, load_env_file_defaults


def test_load_env_file_defaults_preserves_existing_environment(
    monkeypatch, tmp_path
) -> None:
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "\n".join(
            [
                "# local model config",
                "MODEL_PROVIDER=qwen",
                "export ANTHROPIC_MODEL='qwen-plus'",
                'ANTHROPIC_BASE_URL="https://example.test/apps/anthropic"',
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)

    load_env_file_defaults(env_file)

    assert os.environ["MODEL_PROVIDER"] == "anthropic"
    assert os.environ["ANTHROPIC_MODEL"] == "qwen-plus"
    assert os.environ["ANTHROPIC_BASE_URL"] == "https://example.test/apps/anthropic"


def test_model_provider_defaults_to_deepseek_when_no_local_override(monkeypatch) -> None:
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.delenv("MODEL_PROVIDER", raising=False)

    assert Settings.from_environment().model_provider == "deepseek"


def test_model_provider_allows_an_explicit_compatible_override(monkeypatch) -> None:
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.setenv("MODEL_PROVIDER", "anthropic")

    assert Settings.from_environment().model_provider == "anthropic"


@pytest.mark.parametrize("override,expected", [(None, "qwen3.8-max"), ("", ""),
                                               ("qwen3.8-max", "qwen3.8-max")])
def test_profile_model_is_optional_and_does_not_replace_general_model(
    monkeypatch, override, expected,
):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.setenv("QWEN_MODEL", "qwen-plus")
    monkeypatch.delenv("QWEN_PROFILE_MODEL", raising=False)
    if override is not None:
        monkeypatch.setenv("QWEN_PROFILE_MODEL", override)
    configured = Settings.from_environment()
    assert configured.qwen_profile_model == expected
    assert configured.qwen_model == "qwen-plus"
    defaults = Settings(database_path=Path(":memory:"), upload_directory=Path("."))
    assert defaults.qwen_profile_model == "qwen3.8-max"


@pytest.mark.parametrize("value,expected", [(None, 180), ("90", 90), ("300", 300)])
def test_profile_timeout_from_environment(monkeypatch, value, expected):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.delenv("QWEN_PROFILE_READ_TIMEOUT_SECONDS", raising=False)
    if value is not None:
        monkeypatch.setenv("QWEN_PROFILE_READ_TIMEOUT_SECONDS", value)
    assert Settings.from_environment().qwen_profile_read_timeout_seconds == expected


@pytest.mark.parametrize("value", [0, 301, True, float("inf")])
def test_profile_timeout_is_bounded(value):
    with pytest.raises(ValueError, match="QWEN_PROFILE_READ_TIMEOUT_SECONDS"):
        Settings(database_path=Path(":memory:"), upload_directory=Path("."),
                 qwen_profile_read_timeout_seconds=value)


@pytest.mark.parametrize("value,expected", [
    (None, False), ("false", False), ("true", True), (" TRUE ", True), ("False", False),
])
def test_profile_thinking_requires_an_explicit_boolean_environment_opt_in(
    monkeypatch, value, expected,
):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.delenv("QWEN_PROFILE_ENABLE_THINKING", raising=False)
    if value is not None:
        monkeypatch.setenv("QWEN_PROFILE_ENABLE_THINKING", value)
    assert Settings.from_environment().qwen_profile_enable_thinking is expected
    defaults = Settings(database_path=Path(":memory:"), upload_directory=Path("."))
    assert defaults.qwen_profile_enable_thinking is False
    assert defaults.qwen_profile_thinking_budget == 4096


@pytest.mark.parametrize("value", ["", "yes", "no", "1", "0", "invalid"])
def test_profile_thinking_rejects_invalid_environment_value(monkeypatch, value):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.setenv("QWEN_PROFILE_ENABLE_THINKING", value)
    with pytest.raises(ValueError, match="QWEN_PROFILE_ENABLE_THINKING"):
        Settings.from_environment()


@pytest.mark.parametrize("value", [0, 1, "true", None])
def test_profile_thinking_rejects_non_boolean_direct_value(value):
    with pytest.raises(ValueError, match="QWEN_PROFILE_ENABLE_THINKING"):
        Settings(database_path=Path(":memory:"), upload_directory=Path("."),
                 qwen_profile_enable_thinking=value)


@pytest.mark.parametrize("value,expected", [(None, 4096), ("1", 1), ("8192", 8192)])
def test_profile_thinking_budget_from_environment(monkeypatch, value, expected):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.delenv("QWEN_PROFILE_THINKING_BUDGET", raising=False)
    if value is not None:
        monkeypatch.setenv("QWEN_PROFILE_THINKING_BUDGET", value)
    assert Settings.from_environment().qwen_profile_thinking_budget == expected


@pytest.mark.parametrize("value", ["", "not-an-integer", "1.5", "0", "8193", "-1"])
def test_profile_thinking_budget_rejects_invalid_environment_value(monkeypatch, value):
    monkeypatch.setattr("app.config.load_env_file_defaults", lambda _: None)
    monkeypatch.setenv("QWEN_PROFILE_THINKING_BUDGET", value)
    with pytest.raises(ValueError, match="QWEN_PROFILE_THINKING_BUDGET"):
        Settings.from_environment()


@pytest.mark.parametrize("value", [0, -1, 8193, True, 1.5, float("inf"), "4096", None])
def test_profile_thinking_budget_is_bounded_even_when_disabled(value):
    with pytest.raises(ValueError, match="QWEN_PROFILE_THINKING_BUDGET"):
        Settings(database_path=Path(":memory:"), upload_directory=Path("."),
                 qwen_profile_thinking_budget=value)
