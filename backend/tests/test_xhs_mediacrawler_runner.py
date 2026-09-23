from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_runner():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "xhs_mediacrawler_profile_importer.py"
    spec = importlib.util.spec_from_file_location("xhs_mediacrawler_profile_importer", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["xhs_mediacrawler_profile_importer"] = module
    spec.loader.exec_module(module)
    return module


def test_xhs_url_classification():
    runner = load_runner()

    assert runner.is_xhs_short_link("https://xhslink.cn/m/9mS715le7Ha")
    assert runner.is_xhs_short_link("https://www.xhslink.cn/m/9mS715le7Ha")
    assert not runner.is_xhs_short_link("https://www.xiaohongshu.com/user/profile/abc")

    assert runner.is_xhs_profile_url(
        "https://www.xiaohongshu.com/user/profile/54bf8e7bb4c4d64c5ece14cd?xsec_token=abc"
    )
    assert not runner.is_xhs_profile_url("https://www.xiaohongshu.com/explore/abc")
    assert not runner.is_xhs_profile_url("https://xhslink.cn/m/9mS715le7Ha")


def test_direct_profile_url_does_not_require_browser_resolution():
    runner = load_runner()
    url = "https://www.xiaohongshu.com/user/profile/54bf8e7bb4c4d64c5ece14cd?xsec_token=abc"

    resolved = runner.resolve_xhs_profile_url(url)

    assert resolved.original_url == url
    assert resolved.resolved_url == url
    assert not resolved.changed


def test_invalid_non_profile_url_is_rejected():
    runner = load_runner()

    try:
        runner.resolve_xhs_profile_url("https://www.xiaohongshu.com/explore/abc")
    except runner.XhsUrlResolutionError as exc:
        assert "用户主页" in str(exc)
    else:
        raise AssertionError("expected XhsUrlResolutionError")


def test_build_mediacrawler_command_uses_resolved_url_and_safe_defaults():
    runner = load_runner()
    command = runner.build_mediacrawler_command(
        python_bin=Path(".venv313/bin/python"),
        creator_url="https://www.xiaohongshu.com/user/profile/abc?xsec_token=token",
        limit=20,
        comments=True,
        sub_comments=False,
        save_data_option="jsonl",
        save_data_path="data/output",
    )

    assert command[:2] == [".venv313/bin/python", "main.py"]
    assert command[command.index("--creator_id") + 1].startswith(
        "https://www.xiaohongshu.com/user/profile/abc"
    )
    assert command[command.index("--crawler_max_notes_count") + 1] == "20"
    assert command[command.index("--max_concurrency_num") + 1] == "1"
    assert command[command.index("--get_comment") + 1] == "yes"
    assert command[command.index("--get_sub_comment") + 1] == "no"
    assert command[command.index("--save_data_option") + 1] == "jsonl"
    assert command[command.index("--save_data_path") + 1] == "data/output"


def test_build_mediacrawler_command_rejects_negative_limit():
    runner = load_runner()

    try:
        runner.build_mediacrawler_command(
            python_bin=Path("python"),
            creator_url="https://www.xiaohongshu.com/user/profile/abc",
            limit=-1,
            comments=False,
            sub_comments=False,
            save_data_option="jsonl",
            save_data_path="data/output",
        )
    except ValueError as exc:
        assert "limit" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_explicit_all_removes_count_limit_but_keeps_one_worker():
    runner = load_runner()
    command = runner.build_mediacrawler_command(
        python_bin=Path("python"), creator_url="https://www.xiaohongshu.com/user/profile/abc",
        limit=0, comments=True, sub_comments=False,
        save_data_option="jsonl", save_data_path="data/output",
    )
    assert command[command.index("--crawler_max_notes_count") + 1] == "2147483647"
    assert command[command.index("--max_concurrency_num") + 1] == "1"
