from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_import_script():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "import_xhs_fixture_to_workspace.py"
    spec = importlib.util.spec_from_file_location(
        "import_xhs_fixture_to_workspace", module_path
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_xhs_fixture_to_workspace"] = module
    spec.loader.exec_module(module)
    return module


def test_cover_media_asset_name_uses_note_title_and_cover_suffix():
    module = load_import_script()

    assert (
        module.cover_media_asset_name("中传大三/专业第一，我为什么放弃保研")
        == "中传大三 专业第一，我为什么放弃保研_封面"
    )


def test_cover_media_asset_caption_uses_note_text_then_title():
    module = load_import_script()

    assert module.cover_media_asset_caption("正文内容", "标题") == "正文内容"
    assert module.cover_media_asset_caption("", "标题") == "标题"
