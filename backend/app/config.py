import os
import re
from dataclasses import dataclass, replace
from pathlib import Path

ENV_LINE_RE = re.compile(
    r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$"
)


def environment_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized not in {"true", "false"}:
        raise ValueError(f"{name} must be true or false")
    return normalized == "true"


def environment_integer(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError as error:
        raise ValueError(f"{name} must be an integer") from error


def load_env_file_defaults(path: Path) -> None:
    """Load simple KEY=value lines without overriding explicit environment.

    This intentionally supports only the .env.local format used by this repo.
    It does not print values, and it ignores malformed/comment lines.
    """
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_LINE_RE.match(line)
        if not match:
            continue
        key = match.group("key")
        value = match.group("value").strip()
        if (
            (value.startswith("'") and value.endswith("'"))
            or (value.startswith('"') and value.endswith('"'))
        ):
            value = value[1:-1]
        os.environ.setdefault(key, value)


@dataclass(frozen=True)
class Settings:
    database_path: Path
    upload_directory: Path
    default_user_id: str = "local-default-user"
    xhs_capture_directory: Path | None = None
    xhs_mediacrawler_directory: Path | None = None
    max_upload_bytes: int = 5 * 1024 * 1024
    csv_preview_rows: int = 20
    # Qwen is the product default. Other supported providers remain explicit
    # opt-ins through MODEL_PROVIDER rather than becoming an accidental
    # fallback when a local env file is absent.
    model_provider: str = "qwen"
    # Account diagnosis has its own provider; other product flows keep Qwen.
    # Use qwen for rollback, or inherit/empty to follow MODEL_PROVIDER.
    account_diagnosis_provider: str = "deepseek"
    # Structured reports add isolated reading assistance by default;
    # source_led remains the explicit single-call rollback option.
    account_report_mode: str = "staged"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-4-20250514"
    anthropic_base_url: str = "https://api.anthropic.com/v1"
    anthropic_messages_url: str = ""
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-flash"
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_read_timeout_seconds: int = 180
    qwen_api_key: str = ""
    qwen_model: str = "qwen-plus"
    qwen_profile_model: str = "qwen3.8-max"
    qwen_profile_read_timeout_seconds: int = 180
    qwen_profile_enable_thinking: bool = False
    qwen_profile_thinking_budget: int = 4096
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_dashscope_base_url: str = "https://dashscope.aliyuncs.com/api/v1"
    qwen_vision_model: str = "qwen-vl-plus"
    qwen_image_model: str = "wanx-v1"
    qwen_video_model: str = "wan2.7-t2v-2026-06-12"
    qwen_task_poll_interval_seconds: float = 1.0
    qwen_task_poll_attempts: int = 30
    ffmpeg_path: str = "ffmpeg"
    video_preview_frame_count: int = 8

    def __post_init__(self) -> None:
        if (not isinstance(self.account_diagnosis_provider, str)
                or self.account_diagnosis_provider.strip().lower()
                not in {"", "inherit", "deepseek", "qwen", "dashscope", "anthropic"}):
            raise ValueError(
                "ACCOUNT_DIAGNOSIS_PROVIDER must be deepseek, qwen, dashscope, "
                "anthropic, or inherit"
            )
        if self.account_report_mode not in ("source_led", "staged"):
            raise ValueError("ACCOUNT_REPORT_MODE must be 'source_led' or 'staged'")
        value = self.deepseek_read_timeout_seconds
        if type(value) is not int or not 1 <= value <= 300:
            raise ValueError("DEEPSEEK_READ_TIMEOUT_SECONDS must be an integer from 1 to 300")
        value = self.qwen_profile_read_timeout_seconds
        if type(value) is not int or not 1 <= value <= 300:
            raise ValueError("QWEN_PROFILE_READ_TIMEOUT_SECONDS must be an integer from 1 to 300")
        if type(self.qwen_profile_enable_thinking) is not bool:
            raise ValueError("QWEN_PROFILE_ENABLE_THINKING must be true or false")
        value = self.qwen_profile_thinking_budget
        if type(value) is not int or not 1 <= value <= 8192:
            raise ValueError("QWEN_PROFILE_THINKING_BUDGET must be an integer from 1 to 8192")

    def for_account_diagnosis(self) -> "Settings":
        """Scope the account override without mutating the general model settings."""
        provider = self.account_diagnosis_provider.strip().lower()
        return replace(self, model_provider=(
            self.model_provider if provider in {"", "inherit"} else provider
        ))

    @classmethod
    def from_environment(cls) -> "Settings":
        repository_root = Path(__file__).resolve().parents[2]
        load_env_file_defaults(repository_root / ".env.local")
        load_env_file_defaults(repository_root / "backend/.env.local")
        return cls(
            database_path=Path(
                os.getenv("DATABASE_PATH", repository_root / "data/app.sqlite3")
            ),
            upload_directory=Path(
                os.getenv(
                    "UPLOAD_DIRECTORY", repository_root / "data/uploads/trends"
                )
            ),
            default_user_id=os.getenv("DEFAULT_USER_ID", "local-default-user"),
            xhs_capture_directory=Path(
                os.getenv(
                    "XHS_CAPTURE_DIRECTORY",
                    repository_root / "data/xhs-captures",
                )
            ),
            xhs_mediacrawler_directory=Path(
                os.getenv(
                    "XHS_MEDIACRAWLER_DIRECTORY",
                    repository_root / "data/external/MediaCrawler",
                )
            ),
            model_provider=os.getenv("MODEL_PROVIDER", "qwen"),
            account_diagnosis_provider=os.getenv("ACCOUNT_DIAGNOSIS_PROVIDER", "deepseek"),
            account_report_mode=os.getenv("ACCOUNT_REPORT_MODE", "staged"),
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-20250514"),
            anthropic_base_url=os.getenv(
                "ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"
            ),
            anthropic_messages_url=os.getenv("ANTHROPIC_MESSAGES_URL", ""),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            deepseek_read_timeout_seconds=environment_integer("DEEPSEEK_READ_TIMEOUT_SECONDS", 180),
            qwen_api_key=os.getenv("QWEN_API_KEY", os.getenv("DASHSCOPE_API_KEY", "")),
            qwen_model=os.getenv("QWEN_MODEL", "qwen-plus"),
            qwen_profile_model=os.getenv("QWEN_PROFILE_MODEL", "qwen3.8-max"),
            qwen_profile_read_timeout_seconds=int(
                os.getenv("QWEN_PROFILE_READ_TIMEOUT_SECONDS", "180")
            ),
            qwen_profile_enable_thinking=environment_bool("QWEN_PROFILE_ENABLE_THINKING", False),
            qwen_profile_thinking_budget=environment_integer("QWEN_PROFILE_THINKING_BUDGET", 4096),
            qwen_base_url=os.getenv(
                "QWEN_BASE_URL",
                os.getenv(
                    "DASHSCOPE_BASE_URL",
                    "https://dashscope.aliyuncs.com/compatible-mode/v1",
                ),
            ),
            qwen_dashscope_base_url=os.getenv(
                "QWEN_DASHSCOPE_BASE_URL",
                os.getenv(
                    "DASHSCOPE_API_BASE_URL",
                    "https://dashscope.aliyuncs.com/api/v1",
                ),
            ),
            qwen_vision_model=os.getenv("QWEN_VISION_MODEL", "qwen-vl-plus"),
            qwen_image_model=os.getenv("QWEN_IMAGE_MODEL", "wanx-v1"),
            qwen_video_model=os.getenv(
                "QWEN_VIDEO_MODEL", "wan2.7-t2v-2026-06-12"
            ),
            qwen_task_poll_interval_seconds=float(
                os.getenv("QWEN_TASK_POLL_INTERVAL_SECONDS", "1.0")
            ),
            qwen_task_poll_attempts=int(os.getenv("QWEN_TASK_POLL_ATTEMPTS", "30")),
            ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg"),
            video_preview_frame_count=int(
                os.getenv("VIDEO_PREVIEW_FRAME_COUNT", "8")
            ),
        )
