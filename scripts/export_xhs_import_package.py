#!/usr/bin/env python3
"""Export any MediaCrawler XHS output directory as a frontend-uploadable package."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from xhs_mediacrawler_fixture import (  # noqa: E402
    export_xhs_import_package,
    infer_creator_display_name,
    load_mediacrawler_export,
)

DEFAULT_OUTPUT_ROOT = ROOT / "data" / "xhs-import-packages"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "将任意 MediaCrawler 小红书输出目录导出为前端可选择的 XHS 导入包。"
        )
    )
    parser.add_argument(
        "--input",
        required=True,
        type=Path,
        help="MediaCrawler 输出目录；可以是 .../xhs，也可以是包含 xhs/ 的上级目录。",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="导入包输出目录；默认写入 data/xhs-import-packages/<账号名或输入目录名>。",
    )
    parser.add_argument(
        "--code",
        default="",
        help="写入 profile source.fixtureCode 的内部代号；默认使用输入目录名。",
    )
    parser.add_argument(
        "--no-overwrite",
        action="store_true",
        help="如果输出目录已存在且非空，则直接失败。",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_dir = args.input.expanduser().resolve()
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory does not exist: {input_dir}")

    code = args.code.strip() or _default_code(input_dir)
    export = load_mediacrawler_export(input_dir, code=code)
    output_dir = (
        args.output.expanduser().resolve()
        if args.output is not None
        else DEFAULT_OUTPUT_ROOT / _safe_output_name(infer_creator_display_name(export))
    )
    summary = export_xhs_import_package(
        export,
        output_dir,
        overwrite=not args.no_overwrite,
    )

    print(f"package_dir: {summary.output_dir}")
    print(f"profile: {summary.profile_path}")
    print(f"display_name: {summary.display_name}")
    print(f"notes: {summary.note_count}")
    print(f"comments: {summary.comment_count}")
    print(f"covers: {summary.copied_cover_count}")
    print(f"missing_covers: {summary.missing_cover_count}")
    if summary.warnings:
        print("warnings:")
        for warning in summary.warnings:
            print(f"- {warning}")
    return 0


def _default_code(input_dir: Path) -> str:
    if input_dir.name == "xhs":
        return input_dir.parent.name
    return input_dir.name


def _safe_output_name(value: str) -> str:
    cleaned = re.sub(r"[\\/:*?\"<>|\n\r\t]+", "_", value).strip(" _.")
    return cleaned or "xhs-import-package"


if __name__ == "__main__":
    raise SystemExit(main())
