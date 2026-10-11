#!/usr/bin/env python3
# ruff: noqa: E402
"""Smoke test product workflow APIs without opening the frontend.

The script creates an isolated temporary SQLite database and upload directory,
then exercises the same FastAPI routes used by the UI. It does not print API
keys. Use ``--mode live`` only when backend/.env.local contains a working model
provider configuration.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from typing import Any

from httpx import ASGITransport, AsyncClient


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.config import Settings  # noqa: E402
from app.main import create_app  # noqa: E402


ENV_LINE_RE = re.compile(
    r"^(?:export\s+)?(?P<key>[A-Za-z_][A-Za-z0-9_]*)=(?P<value>.*)$"
)


def load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        match = ENV_LINE_RE.match(line)
        if not match:
            continue
        value = match.group("value").strip()
        if (
            (value.startswith("'") and value.endswith("'"))
            or (value.startswith('"') and value.endswith('"'))
        ):
            value = value[1:-1]
        os.environ.setdefault(match.group("key"), value)


async def request(
    client: AsyncClient, method: str, path: str, **kwargs: Any
) -> dict[str, Any] | list[Any]:
    response = await client.request(method, path, **kwargs)
    if response.status_code >= 400:
        raise RuntimeError(f"{method} {path} failed: {response.status_code} {response.text}")
    return response.json()


async def create_text_asset(
    client: AsyncClient,
    workspace_id: str,
    asset_type: str,
    name: str,
    content: str,
) -> dict[str, Any]:
    return await request(
        client,
        "POST",
        f"/api/workspaces/{workspace_id}/input-assets",
        json={"type": asset_type, "name": name, "content": content},
    )


async def upload_trend_csv(client: AsyncClient, workspace_id: str) -> dict[str, Any]:
    csv_text = (
        "title,desc,liked,collected,comments,shares,tags\n"
        "数字游民如何选城市,远程工作生活成本对比,1200,300,80,40,数字游民\n"
        "清迈真实生活开销,租房和签证经验,800,220,55,30,远程工作\n"
        "别被数字游民滤镜骗了,自由职业风险,1600,420,120,88,自由职业\n"
    )
    response = await client.post(
        f"/api/workspaces/{workspace_id}/input-assets/trend-csv",
        data={"name": "数字游民趋势数据", "keyword": "数字游民"},
        files={"file": ("sample_trend.csv", csv_text.encode("utf-8"), "text/csv")},
    )
    if response.status_code >= 400:
        raise RuntimeError(f"trend csv upload failed: {response.status_code} {response.text}")
    return response.json()


async def create_analysis_run(
    client: AsyncClient,
    workspace_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    return await request(
        client,
        "POST",
        f"/api/workspaces/{workspace_id}/analysis-runs",
        json=payload,
    )


async def run_smoke(args: argparse.Namespace) -> int:
    env_file = Path(args.env_file)
    load_env_file(env_file)
    if env_file == REPO_ROOT / ".env.local":
        load_env_file(BACKEND_ROOT / ".env.local")

    with tempfile.TemporaryDirectory(prefix="sqsagent-workflow-smoke-") as temp_dir:
        temp_root = Path(temp_dir)
        base = Settings.from_environment()
        settings = Settings(
            database_path=temp_root / "app.sqlite3",
            upload_directory=temp_root / "uploads",
            max_upload_bytes=base.max_upload_bytes,
            csv_preview_rows=base.csv_preview_rows,
            model_provider=base.model_provider,
            anthropic_api_key=base.anthropic_api_key,
            anthropic_model=base.anthropic_model,
            anthropic_base_url=base.anthropic_base_url,
            anthropic_messages_url=base.anthropic_messages_url,
            qwen_api_key=base.qwen_api_key,
            qwen_model=base.qwen_model,
            qwen_profile_model=base.qwen_profile_model,
            qwen_base_url=base.qwen_base_url,
            qwen_dashscope_base_url=base.qwen_dashscope_base_url,
            qwen_vision_model=base.qwen_vision_model,
            qwen_image_model=base.qwen_image_model,
            qwen_video_model=base.qwen_video_model,
            qwen_task_poll_interval_seconds=base.qwen_task_poll_interval_seconds,
            qwen_task_poll_attempts=base.qwen_task_poll_attempts,
            ffmpeg_path=base.ffmpeg_path,
            video_preview_frame_count=base.video_preview_frame_count,
        )
        app = create_app(settings)
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            workspace = await request(
                client,
                "POST",
                "/api/workspaces",
                json={
                    "name": "Workflow Smoke Workspace",
                    "accountPositioning": "面向留学和数字游民内容创作者。",
                },
            )
            workspace_id = str(workspace["id"])
            profile = await create_text_asset(
                client,
                workspace_id,
                "account_profile",
                "QSheep 账号概况",
                "账号：QSheep。内容定位：留学申请、保研放弃、真实决策复盘。",
            )
            historical = await create_text_asset(
                client,
                workspace_id,
                "historical_posts",
                "留学帖子数据合集",
                "中传大三|专业第一，我为什么放弃保研｜赞1454 藏349 评66｜爆",
            )
            comments = await create_text_asset(
                client,
                workspace_id,
                "comments",
                "留学评论区合集",
                "我也不知道要不要放弃保研。\n申请季太焦虑了。\n求选校时间线。",
            )
            trend_csv = await upload_trend_csv(client, workspace_id)
            video_samples = await create_text_asset(
                client,
                workspace_id,
                "video_creator_samples",
                "AIGC 视频创作者样本",
                "作者连续发布剧本向 AIGC 短片，评论区有催更，但缺少真实视频理解。",
            )
            runs: list[dict[str, Any]] = []
            if args.workflow in {"all", "account"}:
                runs.append(
                    await create_analysis_run(
                        client,
                        workspace_id,
                        {
                            "workflowType": "account_diagnosis",
                            "accountProfileInputAssetId": profile["id"],
                            "historicalPostsInputAssetId": historical["id"],
                            "commentsInputAssetId": comments["id"],
                            "mode": args.mode,
                            "idempotencyKey": "smoke-account",
                        },
                    )
                )
            if args.workflow in {"all", "trend"}:
                runs.append(
                    await create_analysis_run(
                        client,
                        workspace_id,
                        {
                            "workflowType": "trend_analysis",
                            "accountProfileInputAssetId": profile["id"],
                            "trendCsvInputAssetId": trend_csv["id"],
                            "mode": args.mode,
                            "idempotencyKey": "smoke-trend",
                        },
                    )
                )
            if args.workflow in {"all", "video"}:
                runs.append(
                    await create_analysis_run(
                        client,
                        workspace_id,
                        {
                            "workflowType": "video_creator_quality",
                            "accountProfileInputAssetId": profile["id"],
                            "videoCreatorSamplesInputAssetId": video_samples["id"],
                            "mode": args.mode,
                            "idempotencyKey": "smoke-video",
                        },
                    )
                )
            await app.state.workflow_worker.wait_for_idle(timeout=args.timeout)
            completed = [
                await request(client, "GET", f"/api/analysis-runs/{run['id']}")
                for run in runs
            ]
            print("Workflow smoke summary:")
            print(
                json.dumps(
                    [
                        {
                            "id": run["id"],
                            "workflowType": run["workflowType"],
                            "status": run["status"],
                            "stageKeys": sorted(run["stageResults"].keys()),
                            "errorKeys": sorted(run["stageErrors"].keys()),
                        }
                        for run in completed
                    ],
                    ensure_ascii=False,
                    indent=2,
                )
            )
            failed = [
                run
                for run in completed
                if run["status"] not in {"completed", "partially_completed"}
            ]
            return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", default=str(REPO_ROOT / ".env.local"))
    parser.add_argument("--mode", choices=["demo", "live"], default="demo")
    parser.add_argument(
        "--workflow",
        choices=["all", "account", "trend", "video"],
        default="all",
    )
    parser.add_argument("--timeout", type=float, default=30.0)
    return asyncio.run(run_smoke(parser.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
