from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.config import Settings
from app.main import create_app


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "test.sqlite3",
        upload_directory=tmp_path / "uploads",
        max_upload_bytes=1024 * 1024,
        csv_preview_rows=2,
    )


@pytest.fixture
def app(settings: Settings) -> Iterator[FastAPI]:
    yield create_app(settings)

