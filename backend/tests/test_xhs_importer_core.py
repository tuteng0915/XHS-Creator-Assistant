import importlib.util
import sys
from pathlib import Path


def load_core_module():
    root = Path(__file__).resolve().parents[2]
    module_path = root / "scripts" / "xhs_importer_core.py"
    spec = importlib.util.spec_from_file_location("xhs_importer_core", module_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["xhs_importer_core"] = module
    spec.loader.exec_module(module)
    return module


def test_normalize_note_candidates_dedupes_and_filters_non_notes():
    core = load_core_module()

    notes, warnings = core.normalize_note_candidates(
        [
            {
                "title": " 留学申请复盘 ",
                "noteUrl": "https://www.xiaohongshu.com/explore/abc?xsec_token=1",
                "text": " 留学申请复盘   赞 12 ",
            },
            {
                "title": "留学申请复盘",
                "noteUrl": "https://www.xiaohongshu.com/explore/abc?xsec_token=1",
                "text": "duplicate",
            },
            {
                "title": "用户主页",
                "noteUrl": "https://www.xiaohongshu.com/user/profile/abc",
                "text": "not a note",
            },
        ],
        limit=10,
    )

    assert len(notes) == 1
    assert notes[0].title == "留学申请复盘"
    assert notes[0].card_text == "留学申请复盘 赞 12"
    assert warnings == []


def test_build_profile_import_and_markdown_preserve_chinese_content():
    core = load_core_module()

    profile_import = core.build_profile_import(
        source_url="https://www.xiaohongshu.com/user/profile/u1",
        profile_text="账号：QSheep 留学账号\n定位：文科留学申请",
        candidates=[
            {
                "title": "不要盲目冲前 30",
                "noteUrl": "https://www.xiaohongshu.com/explore/n1",
                "detailText": "这篇讲选校策略，以及如何判断项目是否适合自己。",
                "coverUrl": "https://img.example/cover.jpg",
                "engagementText": "赞 88 / 评论 12",
            }
        ],
        limit=5,
    )

    markdown = core.format_historical_posts_markdown(profile_import)

    assert profile_import.platform == "xiaohongshu"
    assert profile_import.notes[0].title == "不要盲目冲前 30"
    assert "账号：QSheep 留学账号 定位：文科留学申请" in markdown
    assert "这篇讲选校策略，以及如何判断项目是否适合自己。" in markdown
    assert "赞 88 / 评论 12" in markdown


def test_json_export_uses_versioned_camel_case_schema():
    core = load_core_module()

    profile_import = core.build_profile_import(
        source_url="https://www.xiaohongshu.com/user/profile/u1",
        profile_text="账号：QSheep 留学账号",
        candidates=[
            {
                "title": "留学申请复盘",
                "noteUrl": "https://www.xiaohongshu.com/explore/n1",
                "text": "申请节奏复盘",
            }
        ],
        limit=1,
    )

    payload = core.to_jsonable(profile_import)

    assert payload["schemaVersion"] == "xhs-profile-import/v1"
    assert payload["sourceUrl"] == "https://www.xiaohongshu.com/user/profile/u1"
    assert payload["creator"]["profileText"] == "账号：QSheep 留学账号"
    assert payload["notes"] == [
        {
            "title": "留学申请复盘",
            "url": "https://www.xiaohongshu.com/explore/n1",
            "cardText": "申请节奏复盘",
            "detailText": "",
            "coverUrl": "",
            "engagementText": "",
        }
    ]


def test_profile_text_trims_xhs_footer_and_note_grid_noise():
    core = load_core_module()

    profile = core.trim_profile_text(
        "首页 点点 ai RED 电话：9501-3888 秀才加点冰 "
        "小红书号：927269230 IP属地：新加坡 THU - NUS ｜ AI PhD 在读 "
        "78 关注 83 粉丝 2022 获赞与收藏 笔记 收藏 点赞 木马，非礼也 13"
    )

    assert profile == (
        "秀才加点冰 小红书号：927269230 IP属地：新加坡 "
        "THU - NUS ｜ AI PhD 在读 78 关注 83 粉丝 2022 获赞与收藏"
    )
