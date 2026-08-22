from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def load_fixture_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "xhs_mediacrawler_fixture.py"
    spec = importlib.util.spec_from_file_location("xhs_mediacrawler_fixture", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["xhs_mediacrawler_fixture"] = module
    spec.loader.exec_module(module)
    return module


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )


def test_load_mediacrawler_export_preserves_notes_comments_and_cover(tmp_path: Path):
    module = load_fixture_module()
    base = tmp_path / "QSheep" / "xhs"
    write_jsonl(
        base / "jsonl" / "creator_contents_2026-08-22.jsonl",
        [
            {
                "note_id": "n1",
                "type": "normal",
                "title": "中传大三|专业第一，我为什么放弃保研",
                "desc": "中文正文完整保留。",
                "note_url": "https://www.xiaohongshu.com/explore/n1",
                "tag_list": "留学,申请",
                "liked_count": "1454",
                "collected_count": "349",
                "comment_count": "66",
                "share_count": "253",
            }
        ],
    )
    write_jsonl(
        base / "jsonl" / "creator_comments_2026-08-22.jsonl",
        [
            {
                "comment_id": "c1",
                "note_id": "n1",
                "content": "真诚有勇气。",
                "like_count": "24",
                "sub_comment_count": "2",
                "create_time": 1720571622000,
            }
        ],
    )
    cover = base / "images" / "n1" / "0.jpg"
    cover.parent.mkdir(parents=True)
    cover.write_bytes(b"jpg")

    export = module.load_mediacrawler_export(tmp_path / "QSheep", code="QSheep")

    assert export.code == "QSheep"
    assert len(export.notes) == 1
    assert export.notes[0].title == "中传大三|专业第一，我为什么放弃保研"
    assert export.notes[0].desc == "中文正文完整保留。"
    assert export.notes[0].tag_list == ["留学", "申请"]
    assert export.notes[0].liked_count == 1454
    assert export.notes[0].cover_path == cover
    assert len(export.comments) == 1
    assert export.comments[0].content == "真诚有勇气。"


def test_fixture_markdown_outputs_agent_readable_context(tmp_path: Path):
    module = load_fixture_module()
    base = tmp_path / "_tt" / "xhs"
    write_jsonl(
        base / "jsonl" / "creator_contents_2026-08-22.jsonl",
        [
            {
                "note_id": "n1",
                "type": "normal",
                "title": "阿凡达3 看懂这一点，就再也回不去了",
                "desc": "Eywa 真的是信仰吗？",
                "tag_list": "科幻电影,影评",
                "liked_count": "1370",
            }
        ],
    )
    write_jsonl(
        base / "jsonl" / "creator_comments_2026-08-22.jsonl",
        [{"comment_id": "c1", "note_id": "n1", "content": "很有启发。"}],
    )
    export = module.load_mediacrawler_export(tmp_path / "_tt", code="_tt")

    profile = module.build_account_profile_markdown(export)
    posts = module.build_historical_posts_markdown(
        export, media_asset_ids_by_note={"n1": "media-1"}
    )
    comments = module.build_comments_markdown(export)

    assert "确定性摘要，不是 LLM 诊断结论" in profile
    assert "高频标签：科幻电影、影评" in profile
    assert "封面 MediaAsset：media-1" in posts
    assert "Eywa 真的是信仰吗？" in posts
    assert "很有启发。" in comments


def test_build_xhs_creator_profile_payload_keeps_note_comment_media_relationships(
    tmp_path: Path,
):
    module = load_fixture_module()
    base = tmp_path / "QSheep" / "xhs"
    write_jsonl(
        base / "jsonl" / "creator_contents_2026-08-22.jsonl",
        [
            {
                "note_id": "n1",
                "type": "normal",
                "title": "中传大三|专业第一，我为什么放弃保研",
                "desc": "正文",
                "note_url": "https://www.xiaohongshu.com/explore/n1",
                "tag_list": "留学,申请",
                "liked_count": "1454",
                "collected_count": "349",
                "comment_count": "66",
                "share_count": "253",
            }
        ],
    )
    write_jsonl(
        base / "jsonl" / "creator_comments_2026-08-22.jsonl",
        [{"comment_id": "c1", "note_id": "n1", "content": "真诚有勇气。"}],
    )
    export = module.load_mediacrawler_export(tmp_path / "QSheep", code="QSheep")

    payload = module.build_xhs_creator_profile_payload(
        export, media_asset_ids_by_note={"n1": "media-1"}
    )

    assert payload["schemaVersion"] == "xhs-creator-profile/v1"
    assert payload["source"]["fixtureCode"] == "QSheep"
    assert payload["notes"][0]["noteId"] == "n1"
    assert payload["notes"][0]["coverMediaAssetId"] == "media-1"
    assert payload["notes"][0]["metrics"]["liked"] == 1454
    assert payload["notes"][0]["comments"][0]["commentId"] == "c1"
