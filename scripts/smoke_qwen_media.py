#!/usr/bin/env python3
# ruff: noqa: E402, I001
"""Smoke test Qwen media skills through the backend skill invocation path.

This script reads credentials from `.env.local` / `backend/.env.local` or the
current environment. It never prints API keys. By default it uses a temporary
SQLite database and upload directory, so generated files are only for smoke
testing unless explicit paths are provided.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402
from app.errors import ApplicationError  # noqa: E402
from app.main import create_app  # noqa: E402
from app.models import SkillInvokeRequest, WorkspaceCreate  # noqa: E402


ENV_LINE_RE = re.compile(
    r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$"
)


def _load_env_file(path: Path) -> None:
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


def _mask(value: str) -> str:
    if not value:
        return "missing"
    if len(value) <= 8:
        return "set"
    return f"{value[:4]}...{value[-4:]}"


def _skill_input(args: argparse.Namespace) -> tuple[str, dict[str, Any]]:
    if args.operation == "image-understand":
        if not args.image_url:
            raise SystemExit("--image-url is required for image-understand")
        return (
            "media.understand_image",
            {
                "imageUrl": args.image_url,
                "prompt": args.prompt or "请描述图片，并提取创作者内容判断线索。",
            },
        )
    if args.operation == "video-understand":
        frame_urls = [item for item in args.frame_url if item]
        if not args.video_url and not frame_urls:
            raise SystemExit("--video-url or --frame-url is required for video-understand")
        payload: dict[str, Any] = {
            "prompt": args.prompt or "请分析视频内容、画面质量和创作者运营线索。"
        }
        if frame_urls:
            payload["videoFrameUrls"] = frame_urls
        else:
            payload["videoUrl"] = args.video_url
        return "media.understand_video", payload
    if args.operation == "image-generate":
        return (
            "media.generate_image",
            {
                "prompt": args.prompt or "生成一张创作者账号主页视觉参考图。",
                "name": args.name or "Qwen smoke 生成图片",
                "purpose": "Qwen media smoke test",
                "size": args.size,
            },
        )
    if args.operation == "video-generate":
        return (
            "media.generate_video",
            {
                "prompt": args.prompt or "生成一个 AIGC 短剧开场镜头。",
                "name": args.name or "Qwen smoke 生成视频",
                "purpose": "Qwen media smoke test",
                "resolution": args.resolution,
                "ratio": args.ratio,
                "duration": args.duration,
            },
        )
    raise SystemExit(f"Unsupported operation: {args.operation}")


def _settings(args: argparse.Namespace, temp_dir: Path) -> Settings:
    _load_env_file(Path(args.env_file))
    if Path(args.env_file) == REPO_ROOT / ".env.local":
        _load_env_file(BACKEND_ROOT / ".env.local")
    settings = Settings.from_environment()
    return replace(
        settings,
        database_path=(
            Path(args.database_path)
            if args.database_path
            else temp_dir / "smoke.sqlite3"
        ),
        upload_directory=(
            Path(args.upload_directory)
            if args.upload_directory
            else temp_dir / "uploads"
        ),
        qwen_task_poll_interval_seconds=args.poll_interval,
        qwen_task_poll_attempts=args.poll_attempts,
    )


def _run(args: argparse.Namespace) -> int:
    with tempfile.TemporaryDirectory(prefix="sqs-qwen-media-") as tmp:
        temp_dir = Path(tmp)
        settings = _settings(args, temp_dir)
        skill_id, input_payload = _skill_input(args)
        app = create_app(settings)
        workspace = app.state.workspace_service.create(
            WorkspaceCreate(
                name="Qwen media smoke workspace",
                accountPositioning="用于验证 Qwen 多模态 API。",
            )
        )
        skills = app.state.skill_service.list(workspace.id)
        skill = next(item for item in skills if item.skill_id == skill_id)

        print("Qwen media smoke configuration:")
        print(
            json.dumps(
                {
                    "apiKey": _mask(settings.qwen_api_key),
                    "baseUrl": settings.qwen_base_url,
                    "dashscopeBaseUrl": settings.qwen_dashscope_base_url,
                    "visionModel": settings.qwen_vision_model,
                    "imageModel": settings.qwen_image_model,
                    "videoModel": settings.qwen_video_model,
                    "operation": args.operation,
                    "workspaceId": workspace.id,
                    "skillId": skill_id,
                    "databasePath": str(settings.database_path),
                    "uploadDirectory": str(settings.upload_directory),
                },
                ensure_ascii=False,
                indent=2,
            )
        )

        try:
            response = app.state.skill_service.invoke(
                skill.id,
                SkillInvokeRequest(mode="live", input=input_payload),
            )
        except ApplicationError as error:
            print(f"FAILED: {error}", file=sys.stderr)
            return 1
        except Exception as error:  # noqa: BLE001
            print(f"FAILED: {type(error).__name__}: {error}", file=sys.stderr)
            return 1

        print("Output:")
        print(json.dumps(response.output, ensure_ascii=False, indent=2))
        print("Model metadata:")
        print(json.dumps(response.model_metadata, ensure_ascii=False, indent=2))
        print("PASSED")
        return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "operation",
        choices=[
            "image-understand",
            "video-understand",
            "image-generate",
            "video-generate",
        ],
    )
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env.local"))
    parser.add_argument("--database-path", default="")
    parser.add_argument("--upload-directory", default="")
    parser.add_argument("--image-url", default="")
    parser.add_argument("--video-url", default="")
    parser.add_argument("--frame-url", action="append", default=[])
    parser.add_argument("--prompt", default="")
    parser.add_argument("--name", default="")
    parser.add_argument("--size", default="1024*1024")
    parser.add_argument("--resolution", default="720P")
    parser.add_argument("--ratio", default="16:9")
    parser.add_argument("--duration", type=int, default=5)
    parser.add_argument("--poll-interval", type=float, default=1.0)
    parser.add_argument("--poll-attempts", type=int, default=30)
    return _run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
