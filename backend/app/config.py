import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    database_path: Path
    upload_directory: Path
    max_upload_bytes: int = 5 * 1024 * 1024
    csv_preview_rows: int = 20
    model_provider: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    qwen_api_key: str = ""
    qwen_model: str = "qwen-plus"
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    @classmethod
    def from_environment(cls) -> "Settings":
        repository_root = Path(__file__).resolve().parents[2]
        return cls(
            database_path=Path(
                os.getenv("DATABASE_PATH", repository_root / "data/app.sqlite3")
            ),
            upload_directory=Path(
                os.getenv(
                    "UPLOAD_DIRECTORY", repository_root / "data/uploads/trends"
                )
            ),
            model_provider=os.getenv("MODEL_PROVIDER", "anthropic"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            qwen_api_key=os.getenv("QWEN_API_KEY", os.getenv("DASHSCOPE_API_KEY", "")),
            qwen_model=os.getenv("QWEN_MODEL", "qwen-plus"),
            qwen_base_url=os.getenv(
                "QWEN_BASE_URL",
                os.getenv(
                    "DASHSCOPE_BASE_URL",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1",
                ),
            ),
        )
