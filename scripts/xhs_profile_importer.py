#!/usr/bin/env python3
"""Browser-assisted Xiaohongshu profile importer for local demos.

The script opens a local Chromium browser with a persistent profile. The user is
expected to complete Xiaohongshu login manually. The importer only reads content
rendered in that browser session and writes local JSON/Markdown files.

It deliberately does not bypass captcha, reverse signed APIs, inject cookies, or
perform high-frequency crawling.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from contextlib import suppress
from pathlib import Path
from typing import Any

from xhs_importer_core import (
    build_profile_import,
    format_historical_posts_markdown,
    to_jsonable,
)

DEFAULT_PROFILE_DIR = Path("data/browser-profiles/xhs-importer")
DEFAULT_OUTPUT_DIR = Path("data/xhs-imports")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="本地浏览器辅助导入小红书用户主页可见笔记。"
    )
    parser.add_argument("url", help="小红书用户主页 URL")
    parser.add_argument("--limit", type=int, default=12, help="最多导入多少条笔记")
    parser.add_argument("--scrolls", type=int, default=4, help="主页向下滚动次数")
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=DEFAULT_PROFILE_DIR,
        help="Playwright 持久浏览器 profile 目录",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="JSON 输出路径；默认写入 data/xhs-imports/",
    )
    parser.add_argument(
        "--markdown-out",
        type=Path,
        default=None,
        help="Markdown 输出路径；默认与 JSON 同名 .md",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="无头模式；不推荐，首次登录必须使用可见浏览器",
    )
    parser.add_argument(
        "--skip-login-prompt",
        action="store_true",
        help="不等待用户按 Enter，适合已登录 profile",
    )
    parser.add_argument(
        "--open-details",
        action=argparse.BooleanOptionalAction,
        default=False,
        help="尝试逐条打开详情页读取更多可见正文；默认关闭，因为详情页更容易受推荐流/弹窗影响",
    )
    parser.add_argument(
        "--detail-wait",
        type=float,
        default=1.5,
        help="打开详情页后的等待秒数",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.limit < 1:
        raise SystemExit("--limit 必须大于 0")
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError:
        print(
            "缺少 Playwright。请先安装：\n\n"
            "  cd backend\n"
            "  source .venv/bin/activate\n"
            "  python -m pip install '.[xhs]'\n"
            "  python -m playwright install chromium\n",
            file=sys.stderr,
        )
        return 2

    output_path = args.out or default_output_path(args.url)
    markdown_path = args.markdown_out or output_path.with_suffix(".md")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    args.profile_dir.mkdir(parents=True, exist_ok=True)

    extra_warnings: list[str] = []
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(args.profile_dir),
            headless=args.headless,
            viewport={"width": 1440, "height": 1100},
            locale="zh-CN",
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(12_000)
        try:
            print(f"打开主页：{args.url}")
            page.goto(args.url, wait_until="domcontentloaded")
            wait_for_user_login(args.skip_login_prompt)
            settle(page)
            scroll_profile(page, args.scrolls)
            snapshot = extract_profile_snapshot(page)
            candidates = snapshot.get("candidates", [])
            if args.open_details:
                enrich_candidates_with_details(
                    source_page=page,
                    context=context,
                    candidates=candidates,
                    limit=args.limit,
                    detail_wait=args.detail_wait,
                    timeout_error=PlaywrightTimeoutError,
                    browser_error=PlaywrightError,
                    warnings=extra_warnings,
                )
            profile_import = build_profile_import(
                source_url=args.url,
                profile_text=str(snapshot.get("profileText") or ""),
                candidates=candidates,
                limit=args.limit,
                extra_warnings=extra_warnings,
            )
            output_path.write_text(
                json.dumps(to_jsonable(profile_import), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            markdown_path.write_text(
                format_historical_posts_markdown(profile_import),
                encoding="utf-8",
            )
            print(f"已导出 JSON：{output_path}")
            print(f"已导出 Markdown：{markdown_path}")
            print(f"识别笔记数：{len(profile_import.notes)}")
            if profile_import.warnings:
                print("提示：")
                for warning in profile_import.warnings:
                    print(f"- {warning}")
        finally:
            context.close()
    return 0


def wait_for_user_login(skip_login_prompt: bool) -> None:
    if skip_login_prompt:
        return
    print(
        "\n如果浏览器未登录，请在打开的窗口中手动完成登录/验证。"
        "\n确认目标主页已经正常显示后，回到终端按 Enter 继续。"
    )
    input()


def settle(page: Any) -> None:
    with suppress(Exception):
        page.wait_for_load_state("networkidle", timeout=8_000)
    time.sleep(1)


def scroll_profile(page: Any, scrolls: int) -> None:
    for index in range(max(scrolls, 0)):
        print(f"滚动主页 {index + 1}/{scrolls}")
        page.mouse.wheel(0, 1600)
        time.sleep(1.2)


def extract_profile_snapshot(page: Any) -> dict[str, Any]:
    return page.evaluate(
        """
        () => {
          const clean = (value, max = 4000) => {
            const text = String(value || '').replace(/\\u200b/g, '').replace(/\\s+/g, ' ').trim();
            return text.length > max ? text.slice(0, max - 1).trim() + '…' : text;
          };
          const noteHref = (href) => {
            if (!href || !href.includes('xiaohongshu.com')) return false;
            return href.includes('/explore/')
              || href.includes('/discovery/item/')
              || href.includes('/search_result/');
          };
          const pickTitle = (anchor, cardText) => {
            const aria = anchor.getAttribute('aria-label');
            const ownText = anchor.innerText;
            const titleNode = anchor.closest('section, article, div')
              ?.querySelector('[class*=title], [class*=name], [class*=desc]');
            return clean(
              aria || ownText || titleNode?.innerText || cardText.split(' ').slice(0, 16).join(' '),
              160
            );
          };
          const anchors = Array.from(document.querySelectorAll('a[href]'));
          const candidates = [];
          for (const anchor of anchors) {
            const href = anchor.href;
            if (!noteHref(href)) continue;
            const card = anchor.closest('section, article, li, div') || anchor;
            const cardText = clean(card.innerText || anchor.innerText, 1500);
            const image = card.querySelector('img');
            const engagementParts = Array.from(card.querySelectorAll('span, div'))
              .map((node) => clean(node.innerText, 60))
              .filter((text) => /赞|收藏|评论|\\d/.test(text))
              .slice(0, 8);
            candidates.push({
              title: pickTitle(anchor, cardText),
              noteUrl: href,
              text: cardText,
              coverUrl: image?.src || '',
              engagementText: engagementParts.join(' / ')
            });
          }
          return {
            pageTitle: document.title,
            profileText: clean(document.body?.innerText || '', 4000),
            candidates
          };
        }
        """
    )


def enrich_candidates_with_details(
    *,
    source_page: Any,
    context: Any,
    candidates: list[dict[str, Any]],
    limit: int,
    detail_wait: float,
    timeout_error: type[Exception],
    browser_error: type[Exception],
    warnings: list[str],
) -> None:
    seen: set[str] = set()
    selected: list[dict[str, Any]] = []
    for candidate in candidates:
        note_url = str(candidate.get("noteUrl") or "")
        if not note_url or note_url in seen:
            continue
        seen.add(note_url)
        selected.append(candidate)
        if len(selected) >= limit:
            break

    detail_page = context.new_page()
    detail_page.set_default_timeout(10_000)
    try:
        for index, candidate in enumerate(selected, start=1):
            note_url = str(candidate.get("noteUrl") or "")
            title = str(candidate.get("title") or "").strip()
            print(f"打开详情 {index}/{len(selected)}：{title or note_url}")
            try:
                detail_text = ""
                try:
                    if not source_page.is_closed():
                        detail_text = extract_detail_text_by_clicking_profile_card(
                            page=source_page,
                            note_url=note_url,
                            title=title,
                            detail_wait=detail_wait,
                        )
                except Exception as click_error:
                    warnings.append(
                        f"主页点击读取失败，改用直链详情：{title or note_url} "
                        f"({type(click_error).__name__})"
                    )
                if not detail_text:
                    detail_page.goto(note_url, wait_until="domcontentloaded")
                    settle(detail_page)
                    time.sleep(max(detail_wait, 0))
                    detail_text = extract_detail_text(detail_page, title)
                if not detail_contains_title(detail_text, title):
                    warnings.append(f"详情页内容未通过标题校验，已保留卡片快照：{title}")
                    continue
                candidate["detailText"] = detail_text
            except (timeout_error, browser_error, Exception) as exc:
                title_or_url = candidate.get("title") or note_url
                warnings.append(
                    f"详情页读取失败，已保留卡片快照：{title_or_url} "
                    f"({type(exc).__name__})"
                )
    finally:
        detail_page.close()


def extract_detail_text_by_clicking_profile_card(
    *,
    page: Any,
    note_url: str,
    title: str,
    detail_wait: float,
) -> str:
    original_url = page.url
    clicked = page.evaluate(
        """
        ({ noteUrl }) => {
          const normalize = (url) => String(url || '').split('#')[0].split('?')[0];
          const target = normalize(noteUrl);
          const anchors = Array.from(document.querySelectorAll('a[href]'));
          const anchor = anchors.find((item) => normalize(item.href) === target);
          if (!anchor) return false;
          anchor.scrollIntoView({ block: 'center', inline: 'center' });
          anchor.click();
          return true;
        }
        """,
        {"noteUrl": note_url},
    )
    if not clicked:
        return ""
    try:
        time.sleep(max(detail_wait, 0))
        settle(page)
        text = extract_detail_text(page, title)
        return text if detail_contains_title(text, title) else ""
    finally:
        close_detail_view(page, original_url)


def close_detail_view(page: Any, original_url: str) -> None:
    if page.url != original_url:
        try:
            page.go_back(wait_until="domcontentloaded", timeout=8_000)
            settle(page)
            return
        except Exception:
            pass
    page.keyboard.press("Escape")
    time.sleep(0.5)


def detail_contains_title(detail_text: str, title: str) -> bool:
    return not title or title in detail_text


def extract_detail_text(page: Any, expected_title: str = "") -> str:
    return page.evaluate(
        """
        ({ expectedTitle }) => {
          const clean = (value, max = 6000) => {
            const text = String(value || '').replace(/\\u200b/g, '').replace(/\\s+/g, ' ').trim();
            return text.length > max ? text.slice(0, max - 1).trim() + '…' : text;
          };
          const visible = (node) => {
            if (!node) return false;
            const style = window.getComputedStyle(node);
            const rect = node.getBoundingClientRect();
            return style.visibility !== 'hidden'
              && style.display !== 'none'
              && rect.width > 0
              && rect.height > 0;
          };
          const selectors = [
            '[role=dialog]',
            '[class*=note-detail]',
            '[class*=noteDetail]',
            '[class*=detail]',
            '[class*=interaction]',
            '[class*=comments]',
            '[class*=content]',
            '[id*=note]',
            '[class*=note]',
            'main',
            'body'
          ];
          const candidates = [];
          for (const selector of selectors) {
            for (const node of Array.from(document.querySelectorAll(selector))) {
              if (!visible(node)) continue;
              const text = clean(node.innerText || '');
              if (text.length < 30) continue;
              const containsTitle = expectedTitle && text.includes(expectedTitle);
              candidates.push({
                text,
                score: (containsTitle ? 100000 : 0) + Math.min(text.length, 6000)
              });
            }
          }
          candidates.sort((a, b) => b.score - a.score);
          return candidates[0]?.text || clean(document.body?.innerText || '');
        }
        """,
        {"expectedTitle": expected_title},
    )


def default_output_path(url: str) -> Path:
    safe = "".join(ch if ch.isalnum() else "-" for ch in url)[-80:].strip("-")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    return DEFAULT_OUTPUT_DIR / f"xhs-profile-{stamp}-{safe or 'import'}.json"


if __name__ == "__main__":
    raise SystemExit(main())
