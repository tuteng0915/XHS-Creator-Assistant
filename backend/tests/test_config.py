import os

from app.config import load_env_file_defaults


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
