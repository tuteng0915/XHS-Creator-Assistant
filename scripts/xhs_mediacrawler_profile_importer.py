#!/usr/bin/env python3
"""Run MediaCrawler for a Xiaohongshu creator URL with short-link resolution.

This utility can run independently or as the backend's local capture subprocess.
It requires a user-controlled browser login on the machine running the crawler.

Typical usage:

    python scripts/xhs_mediacrawler_profile_importer.py \
      "https://xhslink.cn/m/9mS715le7Ha" \
      --limit 20 \
      --comments \
      --save-data-path data/xhslink-20-comment-cover-test

The script resolves xhslink.cn short links in a visible browser first, then
passes the final Xiaohongshu profile URL to MediaCrawler.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

DEFAULT_MEDIACRAWLER_DIR = Path("data/external/MediaCrawler")
DEFAULT_RESOLVER_PROFILE_DIR = Path(
    "data/external/MediaCrawler/browser_data/cdp_xhs_user_data_dir"
)


class XhsUrlResolutionError(RuntimeError):
    """Raised when a supplied XHS URL cannot be resolved to a creator profile."""


@dataclass(frozen=True)
class ResolvedXhsUrl:
    original_url: str
    resolved_url: str

    @property
    def changed(self) -> bool:
        return self.original_url != self.resolved_url


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="解析小红书短链并调用本地 MediaCrawler 抓取创作者主页。"
    )
    parser.add_argument("url", help="小红书主页 URL 或 xhslink.cn 短链")
    parser.add_argument(
        "--limit", type=int, default=10, help="最多抓取多少条笔记；0 表示全部可见笔记"
    )
    parser.add_argument(
        "--comments",
        action="store_true",
        help="抓取一级评论；每条数量仍由 MediaCrawler config 控制",
    )
    parser.add_argument(
        "--sub-comments",
        action="store_true",
        help="抓取二级评论；默认关闭，不建议 demo 时开启",
    )
    parser.add_argument(
        "--save-data-path",
        default=None,
        help="传给 MediaCrawler 的 save_data_path；默认按时间写入 data/mediacrawler-xhs-*",
    )
    parser.add_argument(
        "--save-data-option",
        default="jsonl",
        choices=["jsonl", "json", "csv", "sqlite", "excel"],
        help="MediaCrawler 存储格式，默认 jsonl",
    )
    parser.add_argument(
        "--mediacrawler-dir",
        type=Path,
        default=DEFAULT_MEDIACRAWLER_DIR,
        help="本地 MediaCrawler 仓库目录",
    )
    parser.add_argument(
        "--mediacrawler-python",
        type=Path,
        default=None,
        help="运行 MediaCrawler 的 Python；默认自动选择 .venv313/bin/python 或当前 Python",
    )
    parser.add_argument(
        "--resolver-profile-dir",
        type=Path,
        default=DEFAULT_RESOLVER_PROFILE_DIR,
        help="解析短链时使用的 Playwright 持久浏览器 profile",
    )
    parser.add_argument(
        "--headless-resolver",
        action="store_true",
        help="解析短链时使用无头浏览器；首次登录不建议",
    )
    parser.add_argument(
        "--resolve-only",
        action="store_true",
        help="只解析 URL，不启动 MediaCrawler",
    )
    return parser.parse_args(argv)


def is_xhs_short_link(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host == "xhslink.cn" or host.endswith(".xhslink.cn")


def is_xhs_profile_url(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    return host == "www.xiaohongshu.com" and parsed.path.startswith("/user/profile/")


def resolve_xhs_profile_url(
    url: str,
    *,
    profile_dir: Path = DEFAULT_RESOLVER_PROFILE_DIR,
    headless: bool = False,
    timeout_ms: int = 45_000,
    settle_ms: int = 5_000,
) -> ResolvedXhsUrl:
    """Return a Xiaohongshu profile URL, resolving xhslink.cn in a browser.

    Direct Xiaohongshu profile URLs are returned unchanged. Short links require
    Playwright because xhslink.cn redirects are browser/app oriented and may not
    resolve through a plain HTTP client.
    """

    if is_xhs_profile_url(url):
        return ResolvedXhsUrl(original_url=url, resolved_url=url)

    if not is_xhs_short_link(url):
        raise XhsUrlResolutionError(
            "请输入小红书用户主页 URL，或 xhslink.cn 用户主页短链。"
        )

    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as exc:
        raise XhsUrlResolutionError(
            "解析 xhslink.cn 短链需要 Playwright。请先安装 backend 的 xhs 可选依赖。"
        ) from exc

    profile_dir.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=headless,
                viewport={"width": 1280, "height": 900},
                locale="zh-CN",
            )
            try:
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                page.wait_for_timeout(settle_ms)
                resolved_url = page.url
            finally:
                context.close()
    except (PlaywrightTimeoutError, PlaywrightError) as exc:
        raise XhsUrlResolutionError(f"短链解析失败：{type(exc).__name__}") from exc

    if not is_xhs_profile_url(resolved_url):
        raise XhsUrlResolutionError(f"短链没有解析到小红书用户主页：{resolved_url}")

    return ResolvedXhsUrl(original_url=url, resolved_url=resolved_url)


def default_save_data_path() -> str:
    return f"data/mediacrawler-xhs-{time.strftime('%Y%m%d-%H%M%S')}"


def pick_mediacrawler_python(
    mediacrawler_dir: Path,
    requested: Path | None,
) -> Path:
    if requested is not None:
        return requested
    local = mediacrawler_dir / ".venv313" / "bin" / "python"
    if local.exists():
        return local
    return Path(sys.executable)


def build_mediacrawler_command(
    *,
    python_bin: Path,
    creator_url: str,
    limit: int,
    comments: bool,
    sub_comments: bool,
    save_data_option: str,
    save_data_path: str,
) -> list[str]:
    if limit < 0:
        raise ValueError("--limit 不能小于 0")
    return [
        str(python_bin),
        "main.py",
        "--platform",
        "xhs",
        "--lt",
        "qrcode",
        "--type",
        "creator",
        "--creator_id",
        creator_url,
        "--crawler_max_notes_count",
        str(limit if limit else 2_147_483_647),
        "--max_concurrency_num",
        "1",
        "--get_comment",
        "yes" if comments else "no",
        "--get_sub_comment",
        "yes" if sub_comments else "no",
        "--save_data_option",
        save_data_option,
        "--save_data_path",
        save_data_path,
    ]


def run_mediacrawler(
    *,
    mediacrawler_dir: Path,
    command: list[str],
) -> int:
    if not mediacrawler_dir.exists():
        raise FileNotFoundError(
            f"找不到 MediaCrawler 目录：{mediacrawler_dir}. "
            "请先 clone 到 data/external/MediaCrawler。"
        )
    save_path = command[command.index("--save_data_path") + 1]
    output = (mediacrawler_dir / save_path / "creator_metrics.json").resolve()
    wrapped = [
        command[0],
        str(Path(__file__).with_name("xhs_capture_with_metrics.py")),
        str(output),
        *command[2:],
    ]
    process = subprocess.run(wrapped, cwd=mediacrawler_dir, check=False)
    return process.returncode


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    resolved = resolve_xhs_profile_url(
        args.url,
        profile_dir=args.resolver_profile_dir,
        headless=args.headless_resolver,
    )
    if resolved.changed:
        print(f"短链已解析：{resolved.resolved_url}")
    else:
        print(f"使用主页 URL：{resolved.resolved_url}")

    if args.resolve_only:
        return 0

    save_data_path = args.save_data_path or default_save_data_path()
    mediacrawler_dir = args.mediacrawler_dir
    python_bin = pick_mediacrawler_python(mediacrawler_dir, args.mediacrawler_python)
    command = build_mediacrawler_command(
        python_bin=python_bin,
        creator_url=resolved.resolved_url,
        limit=args.limit,
        comments=args.comments,
        sub_comments=args.sub_comments,
        save_data_option=args.save_data_option,
        save_data_path=save_data_path,
    )

    print("启动 MediaCrawler：")
    print(" ".join(command))
    print(f"输出目录：{mediacrawler_dir / save_data_path}")
    return run_mediacrawler(mediacrawler_dir=mediacrawler_dir, command=command)


if __name__ == "__main__":
    raise SystemExit(main())
