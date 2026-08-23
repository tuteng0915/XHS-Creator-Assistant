#!/usr/bin/env python3
"""Export a fixed local XHS fixture as a frontend-uploadable import package."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from xhs_mediacrawler_fixture import (  # noqa: E402
    build_xhs_creator_profile_payload,
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

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    profile_payload = build_xhs_creator_profile_payload(export)
    (output_dir / "xhs_creator_profile.json").write_text(
        json.dumps(profile_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    copied_covers = 0
    for note in export.notes:
        if note.cover_path is None:
            continue
        note_image_dir = images_dir / note.note_id
        note_image_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(note.cover_path, note_image_dir / note.cover_path.name)
        copied_covers += 1

    print(f"package_dir: {output_dir}")
    print(f"profile: {output_dir / 'xhs_creator_profile.json'}")
    print(f"covers: {copied_covers}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
