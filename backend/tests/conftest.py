import os
from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from fastapi import FastAPI

from app.config import Settings


def pytest_configure(config):
    # app.main creates its default app at import time, before per-test fixtures run.
    # Isolate that bootstrap too, even when the developer has a real DATABASE_PATH set.
    runtime = TemporaryDirectory(prefix="sqsagent-pytest-bootstrap-")
    config._bootstrap_runtime = runtime
    overrides = {
        "DATABASE_PATH": str(Path(runtime.name) / "bootstrap.sqlite3"),
        "UPLOAD_DIRECTORY": str(Path(runtime.name) / "uploads"),
    }
    config._bootstrap_environment = {key: os.environ.get(key) for key in overrides}
    os.environ.update(overrides)
    # Bootstrap through the normal app entry point after isolation, before collection.
    # Individual workflow/service imports otherwise depend on collection order.
    from app.main import create_app

    config._create_test_app = create_app


def pytest_unconfigure(config):
    runtime = getattr(config, "_bootstrap_runtime", None)
    if runtime is not None:
        runtime.cleanup()
        for key, value in config._bootstrap_environment.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "test.sqlite3",
        upload_directory=tmp_path / "uploads",
        max_upload_bytes=1024 * 1024,
        csv_preview_rows=2,
        # Existing adapter fixtures explicitly exercise Qwen. Production defaults
        # and DeepSeek-only app wiring are covered separately, without live calls.
        model_provider="qwen",
    )


@pytest.fixture
def app(settings: Settings, pytestconfig) -> Iterator[FastAPI]:
    yield pytestconfig._create_test_app(settings)
