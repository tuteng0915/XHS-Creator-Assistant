#!/usr/bin/env python3
"""Export a fixed local XHS fixture as a frontend-uploadable import package."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from xhs_mediacrawler_fixture import (  # noqa: E402
    export_xhs_import_package,
    load_mediacrawler_export,
)

DEFAULT_FIXTURE_ROOT = ROOT / "data" / "xhs-fixtures"
DEFAULT_OUTPUT_ROOT = ROOT / "data" / "xhs-import-packages"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将 data/xhs-fixtures/<code> 导出为前端可选择的 XHS 导入包。"
    )
    parser.add_argument("code", choices=["_tt", "QSheep"], help="固定样本代号")
    parser.add_argument(
        "--fixture-root",
        type=Path,
        default=DEFAULT_FIXTURE_ROOT,
        help="fixture 根目录，默认 data/xhs-fixtures",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=DEFAULT_OUTPUT_ROOT,
        help="导入包输出根目录，默认 data/xhs-import-packages",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture_dir = args.fixture_root / args.code
    output_dir = args.output_root / args.code
    export = load_mediacrawler_export(fixture_dir, code=args.code)
    summary = export_xhs_import_package(export, output_dir)

    print(f"package_dir: {summary.output_dir}")
    print(f"profile: {summary.profile_path}")
    print(f"display_name: {summary.display_name}")
    print(f"notes: {summary.note_count}")
    print(f"comments: {summary.comment_count}")
    print(f"covers: {summary.copied_cover_count}")
    if summary.warnings:
        print("warnings:")
        for warning in summary.warnings:
            print(f"- {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
