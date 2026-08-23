import asyncio
import json
from pathlib import Path

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient


async def request(app: FastAPI, method: str, path: str, **kwargs):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def send(app: FastAPI, method: str, path: str, **kwargs):
    return asyncio.run(request(app, method, path, **kwargs))


def create_workspace(app: FastAPI) -> dict:
    response = send(
        app,
        "POST",
        "/api/workspaces",
        json={
            "name": "留学内容工作区",
            "accountPositioning": "服务正在准备出国读研的文科生。",
        },
    )
    assert response.status_code == 201
    return response.json()


def create_xhs_creator_profile_asset(
    app: FastAPI, workspace_id: str, *, name: str, note_id: str
) -> dict:
    xhs_payload = {
        "schemaVersion": "xhs-creator-profile/v1",
        "source": {
            "platform": "xiaohongshu",
            "fixtureCode": name,
            "crawler": "MediaCrawler",
        },
        "creator": {
            "displayName": name,
            "profileText": f"小红书创作者主页：{name}",
        },
        "notes": [
            {
                "noteId": note_id,
                "type": "normal",
                "title": "中传大三|专业第一，我为什么放弃保研",
                "desc": "申请季前梳理自己的履历发现写不下了。",
                "noteUrl": f"https://www.xiaohongshu.com/explore/{note_id}",
                "tags": ["留学", "申请"],
                "metrics": {
                    "liked": 1454,
                    "collected": 349,
                    "comments": 66,
                    "shares": 253,
                },
                "coverMediaAssetId": f"media-{note_id}",
                "comments": [
                    {
                        "commentId": f"comment-{note_id}",
                        "content": "真诚有勇气。",
                        "likeCount": 24,
                        "subCommentCount": 2,
                    }
                ],
            }
        ],
    }
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace_id}/input-assets",
        json={
            "type": "xhs_creator_profile",
            "name": f"XHS {name} 创作者主页",
            "content": json.dumps(xhs_payload, ensure_ascii=False),
        },
    )
    assert response.status_code == 201
    return response.json()


def test_workspace_crud_and_optimistic_update(app: FastAPI) -> None:
    workspace = create_workspace(app)

    listed = send(app, "GET", "/api/workspaces")
    assert listed.status_code == 200
    assert listed.json() == [workspace]

    retrieved = send(app, "GET", f"/api/workspaces/{workspace['id']}")
    assert retrieved.json()["accountPositioning"] == "服务正在准备出国读研的文科生。"

    updated = send(
        app,
        "PATCH",
        f"/api/workspaces/{workspace['id']}",
        json={
            "name": "QSheep 留学工作区",
            "accountPositioning": "真实反思、决策方法，不贩卖焦虑。",
            "expectedUpdatedAt": workspace["updatedAt"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "QSheep 留学工作区"
    assert updated.json()["accountPositioning"] == "真实反思、决策方法，不贩卖焦虑。"
    assert updated.json()["positioningVersion"] == 2

    stale = send(
        app,
        "PATCH",
        f"/api/workspaces/{workspace['id']}",
        json={
            "name": "静默覆盖不应成功",
            "expectedUpdatedAt": workspace["updatedAt"],
        },
    )
    assert stale.status_code == 409


def test_workspace_list_prefers_workspace_with_creator_assets(app: FastAPI) -> None:
    workspace_with_assets = create_workspace(app)
    newer_empty_workspace = send(
        app,
        "POST",
        "/api/workspaces",
        json={
            "name": "空白工作区",
            "accountPositioning": "暂时没有输入资产。",
        },
    ).json()
    assert newer_empty_workspace["id"] != workspace_with_assets["id"]

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace_with_assets['id']}/input-assets",
        json={
            "type": "historical_posts",
            "name": "留学帖子数据合集",
            "content": "留学中介到底值不值｜赞1.1k｜爆",
        },
    )
    assert created.status_code == 201

    listed = send(app, "GET", "/api/workspaces")

    assert listed.status_code == 200
    workspaces = listed.json()
    assert workspaces[0]["id"] == workspace_with_assets["id"]
    assert workspaces[1]["id"] == newer_empty_workspace["id"]


def test_text_source_material_lifecycle_preserves_utf8(app: FastAPI) -> None:
    workspace = create_workspace(app)
    content = "二本逆袭G5？别再被这种标题骗了｜赞1.4k 藏980｜爆\n留学中介值不值？"
    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials",
        json={
            "type": "historical_posts",
            "name": "历史笔记（中文）",
            "content": content,
        },
    )
    assert created.status_code == 201
    material = created.json()
    assert material["content"] == content

    listed = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/source-materials?type=historical_posts",
    )
    assert listed.status_code == 200
    assert listed.json()[0]["content"] == content

    retrieved = send(app, "GET", f"/api/source-materials/{material['id']}")
    assert retrieved.json() == material

    updated_content = "想问双非背景冲英国前30有戏吗，真的好焦虑。"
    updated = send(
        app,
        "PATCH",
        f"/api/source-materials/{material['id']}",
        json={
            "content": updated_content,
            "expectedUpdatedAt": material["updatedAt"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == updated_content

    stale = send(
        app,
        "PATCH",
        f"/api/source-materials/{material['id']}",
        json={
            "content": "不应覆盖",
            "expectedUpdatedAt": material["updatedAt"],
        },
    )
    assert stale.status_code == 409


def test_input_asset_alias_lifecycle_preserves_utf8(app: FastAPI) -> None:
    workspace = create_workspace(app)
    content = "评论样本：这个选题解决了我的真实焦虑。"

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets",
        json={
            "type": "comments",
            "name": "评论样本资产",
            "content": content,
        },
    )
    assert created.status_code == 201
    asset = created.json()
    assert asset["type"] == "comments"
    assert asset["content"] == content

    listed = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/input-assets?type=comments",
    )
    assert listed.status_code == 200
    assert listed.json()[0]["id"] == asset["id"]

    retrieved = send(app, "GET", f"/api/input-assets/{asset['id']}")
    assert retrieved.status_code == 200
    assert retrieved.json() == asset

    updated = send(
        app,
        "PATCH",
        f"/api/input-assets/{asset['id']}",
        json={
            "content": "评论样本：希望有更具体的步骤。",
            "expectedUpdatedAt": asset["updatedAt"],
        },
    )
    assert updated.status_code == 200
    assert updated.json()["content"] == "评论样本：希望有更具体的步骤。"


def test_video_creator_samples_material_lifecycle_preserves_utf8(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    content = "创作者：@AI短剧研究所\n样本：AIGC短剧｜赞2.3w｜评论区催更。"

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials",
        json={
            "type": "video_creator_samples",
            "name": "视频创作样本",
            "content": content,
        },
    )

    assert created.status_code == 201
    material = created.json()
    assert material["type"] == "video_creator_samples"
    assert material["content"] == content

    listed = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/source-materials?type=video_creator_samples",
    )
    assert listed.status_code == 200
    assert listed.json()[0]["content"] == content


def test_trend_csv_upload_uses_server_path_and_returns_preview(
    app: FastAPI, settings
) -> None:
    workspace = create_workspace(app)
    csv_content = (
        "标题,点赞,收藏,标签\n"
        "普通人如何开始数字游民,45,57,#远程工作\n"
        "不会英语如何在泰国生活,286,221,#泰国\n"
        "第三条只计数不进预览,3,2,#测试\n"
    ).encode()
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials/trend-csv",
        data={"name": "数字游民热帖", "keyword": "数字游民"},
        files={"file": ("../../秘密.csv", csv_content, "text/csv")},
    )
    assert response.status_code == 201
    material = response.json()
    assert material["type"] == "trend_csv"
    assert material["originalFilename"] == "秘密.csv"
    assert material["rowCount"] == 3
    assert material["preview"] == [
        {"标题": "普通人如何开始数字游民", "点赞": "45", "收藏": "57", "标签": "#远程工作"},
        {"标题": "不会英语如何在泰国生活", "点赞": "286", "收藏": "221", "标签": "#泰国"},
    ]

    stored_files = list(Path(settings.upload_directory).rglob("source.csv"))
    assert len(stored_files) == 1
    assert stored_files[0].read_bytes() == csv_content
    assert "秘密.csv" not in str(stored_files[0])

    listed = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/source-materials",
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [material["id"]]


def test_account_profiles_csv_import_preserves_utf8(app: FastAPI) -> None:
    workspace = create_workspace(app)
    csv_content = (
        "name,profile\n"
        "剧本型创作者,账号定位：AIGC 短剧，剧情连续更新。\n"
        "技术探索型,账号定位：AI 工具链拆解，教程与实验混合。\n"
    ).encode()

    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials/account-profiles-csv",
        files={"file": ("profiles.csv", csv_content, "text/csv")},
    )

    assert response.status_code == 201
    materials = response.json()["materials"]
    assert [item["type"] for item in materials] == [
        "account_profile",
        "account_profile",
    ]
    assert materials[0]["name"] == "剧本型创作者"
    assert materials[0]["content"] == "账号定位：AIGC 短剧，剧情连续更新。"

    listed = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/source-materials?type=account_profile",
    )
    assert listed.status_code == 200
    assert sorted(item["content"] for item in listed.json()) == sorted(
        [
        "账号定位：AIGC 短剧，剧情连续更新。",
        "账号定位：AI 工具链拆解，教程与实验混合。",
        ]
    )


def test_text_input_assets_csv_import_supports_peer_asset_types(app: FastAPI) -> None:
    workspace = create_workspace(app)
    comments_csv = (
        "name,content\n"
        "留学评论区合集,太焦虑了，不知道怎么选校\\n求时间线\n"
        "预算评论,预算有限，中介和DIY的钱到底该花在哪一步\n"
    ).encode()

    imported = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/text-csv",
        data={"type": "comments"},
        files={"file": ("comments.csv", comments_csv, "text/csv")},
    )

    assert imported.status_code == 201
    materials = imported.json()["materials"]
    assert [item["type"] for item in materials] == ["comments", "comments"]
    assert materials[0]["name"] == "留学评论区合集"
    assert materials[0]["content"] == "太焦虑了，不知道怎么选校\\n求时间线"

    listed = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/input-assets?type=comments",
    )
    assert listed.status_code == 200
    assert sorted(item["name"] for item in listed.json()) == [
        "留学评论区合集",
        "预算评论",
    ]


def test_text_input_assets_csv_import_rejects_non_text_asset_types(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)

    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/text-csv",
        data={"type": "trend_csv"},
        files={"file": ("trend.csv", b"name,content\nx,y\n", "text/csv")},
    )

    assert response.status_code == 422
    assert "Only text input asset types" in response.text


def test_xhs_offline_json_import_creates_historical_posts_asset(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    payload = {
        "schemaVersion": "xhs-profile-import/v1",
        "platform": "xiaohongshu",
        "sourceUrl": "https://www.xiaohongshu.com/user/profile/u1",
        "importedAt": "2026-08-22T00:00:00Z",
        "importMethod": "browser_assisted_visible_page",
        "creator": {"profileText": "账号：QSheep 留学账号"},
        "notes": [
            {
                "title": "不要盲目冲前 30",
                "url": "https://www.xiaohongshu.com/explore/n1",
                "detailText": "这篇讲选校策略，以及如何判断项目是否适合自己。",
                "coverUrl": "https://img.example/cover.jpg",
                "engagementText": "赞 88 / 评论 12",
            }
        ],
        "warnings": ["只导入了可见页面。"],
    }

    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import",
        data={"type": "historical_posts", "name": "XHS 留学主页导入"},
        files={
            "file": (
                "xhs.json",
                json.dumps(payload, ensure_ascii=False).encode(),
                "application/json",
            )
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["parsedNoteCount"] == 1
    assert body["sourceUrl"] == "https://www.xiaohongshu.com/user/profile/u1"
    assert body["inputAsset"]["type"] == "historical_posts"
    assert body["inputAsset"]["name"] == "XHS 留学主页导入"
    assert "账号：QSheep 留学账号" in body["inputAsset"]["content"]
    assert "不要盲目冲前 30" in body["inputAsset"]["content"]
    assert "这篇讲选校策略" in body["inputAsset"]["content"]


def test_xhs_offline_json_import_creates_workflow_ready_creator_profile_asset(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    payload = {
        "schemaVersion": "xhs-profile-import/v1",
        "platform": "xiaohongshu",
        "sourceUrl": "https://www.xiaohongshu.com/user/profile/u1",
        "importedAt": "2026-08-22T00:00:00Z",
        "importMethod": "browser_assisted_visible_page",
        "creator": {"profileText": "账号：QSheep 留学账号"},
        "notes": [
            {
                "title": "不要盲目冲前 30",
                "url": "https://www.xiaohongshu.com/explore/n1",
                "detailText": "这篇讲选校策略，以及如何判断项目是否适合自己。",
                "coverUrl": "https://img.example/cover.jpg",
                "engagementText": "赞 88 / 评论 12",
            }
        ],
        "warnings": ["只导入了可见页面。"],
    }

    imported = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import",
        data={"type": "xhs_creator_profile", "name": "XHS 留学主页结构化导入"},
        files={
            "file": (
                "xhs.json",
                json.dumps(payload, ensure_ascii=False).encode(),
                "application/json",
            )
        },
    )

    assert imported.status_code == 201
    body = imported.json()
    assert body["inputAsset"]["type"] == "xhs_creator_profile"
    stored = json.loads(body["inputAsset"]["content"])
    assert stored["schemaVersion"] == "xhs-creator-profile/v1"
    assert stored["notes"][0]["desc"] == "这篇讲选校策略，以及如何判断项目是否适合自己。"
    assert stored["notes"][0]["metrics"]["engagementText"] == "赞 88 / 评论 12"

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "account_diagnosis",
            "xhsCreatorProfileInputAssetId": body["inputAsset"]["id"],
            "mode": "demo",
        },
    )
    assert created.status_code == 201
    snapshot = created.json()["inputSnapshot"]
    assert snapshot["xhsCreatorProfile"]["schemaVersion"] == "xhs-creator-profile/v1"
    assert "不要盲目冲前 30" in snapshot["historicalPosts"]["content"]


def test_xhs_offline_json_import_accepts_creator_profile_schema(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    payload = {
        "schemaVersion": "xhs-creator-profile/v1",
        "source": {
            "platform": "xiaohongshu",
            "sourceUrl": "https://www.xiaohongshu.com/user/profile/u2",
            "crawler": "MediaCrawler",
            "importedAt": "2026-08-22T00:00:00Z",
        },
        "creator": {
            "displayName": "QSheep",
            "profileText": "小红书创作者主页：QSheep",
        },
        "notes": [
            {
                "noteId": "n2",
                "type": "normal",
                "title": "申请季复盘",
                "desc": "复盘申请过程中的真实判断。",
                "noteUrl": "https://www.xiaohongshu.com/explore/n2",
                "tags": ["留学"],
                "metrics": {"liked": 88, "collected": 12},
                "coverMediaAssetId": "media-n2",
                "comments": [{"commentId": "c2", "content": "很有帮助"}],
            }
        ],
    }

    imported = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import",
        data={"type": "xhs_creator_profile"},
        files={
            "file": (
                "creator-profile.json",
                json.dumps(payload, ensure_ascii=False).encode(),
                "application/json",
            )
        },
    )

    assert imported.status_code == 201
    body = imported.json()
    assert body["parsedNoteCount"] == 1
    assert body["sourceUrl"] == "https://www.xiaohongshu.com/user/profile/u2"
    stored = json.loads(body["inputAsset"]["content"])
    assert stored["schemaVersion"] == "xhs-creator-profile/v1"
    assert stored["notes"][0]["comments"][0]["content"] == "很有帮助"


def test_xhs_offline_package_import_creates_profile_and_cover_media(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    payload = {
        "schemaVersion": "xhs-creator-profile/v1",
        "source": {
            "platform": "xiaohongshu",
            "sourceUrl": "https://www.xiaohongshu.com/user/profile/u2",
            "crawler": "MediaCrawler",
        },
        "creator": {
            "displayName": "QSheep",
            "profileText": "小红书创作者主页：QSheep",
        },
        "notes": [
            {
                "noteId": "n2",
                "type": "normal",
                "title": "申请季复盘",
                "desc": "复盘申请过程中的真实判断。",
                "noteUrl": "https://www.xiaohongshu.com/explore/n2",
                "tags": ["留学"],
                "metrics": {"liked": 88, "collected": 12},
                "cover": {
                    "relativePath": "images/n2/0.jpg",
                    "caption": "复盘申请过程中的真实判断。",
                },
                "comments": [{"commentId": "c2", "content": "很有帮助"}],
            }
        ],
    }

    imported = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import-package",
        data={"relativePaths": "images/n2/0.jpg"},
        files=[
            (
                "profile",
                (
                    "xhs_creator_profile.json",
                    json.dumps(payload, ensure_ascii=False).encode(),
                    "application/json",
                ),
            ),
            ("files", ("images/n2/0.jpg", b"fake-jpeg", "image/jpeg")),
        ],
    )

    assert imported.status_code == 201
    body = imported.json()
    assert body["inputAsset"]["type"] == "xhs_creator_profile"
    assert body["inputAsset"]["name"] == "XHS QSheep 创作者主页"
    assert len(body["mediaAssets"]) == 1
    media_asset = body["mediaAssets"][0]
    assert media_asset["name"] == "申请季复盘_封面"
    assert media_asset["purpose"] == "小红书笔记封面"
    assert media_asset["metadata"]["caption"] == "复盘申请过程中的真实判断。"
    assert media_asset["metadata"]["relativePath"] == "images/n2/0.jpg"
    assert media_asset["userNotes"] == "复盘申请过程中的真实判断。"

    stored = json.loads(body["inputAsset"]["content"])
    assert stored["notes"][0]["coverMediaAssetId"] == media_asset["id"]
    assert stored["notes"][0]["cover"]["relativePath"] == "images/n2/0.jpg"


def test_xhs_offline_package_import_updates_existing_profile_by_default(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    payload = {
        "schemaVersion": "xhs-creator-profile/v1",
        "source": {"platform": "xiaohongshu"},
        "creator": {"displayName": "QSheep", "profileText": "旧主页"},
        "notes": [
            {
                "noteId": "n2",
                "title": "申请季复盘",
                "desc": "旧正文",
                "cover": {"relativePath": "images/n2/0.jpg"},
            }
        ],
    }

    first = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import-package",
        data={"relativePaths": "images/n2/0.jpg"},
        files=[
            (
                "profile",
                (
                    "xhs_creator_profile.json",
                    json.dumps(payload, ensure_ascii=False).encode(),
                    "application/json",
                ),
            ),
            ("files", ("images/n2/0.jpg", b"old-jpeg", "image/jpeg")),
        ],
    )
    assert first.status_code == 201
    first_body = first.json()
    payload["notes"][0]["desc"] = "更新后的正文"
    payload["notes"][0]["cover"]["caption"] = "更新后的正文"

    second = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import-package",
        data={"relativePaths": "images/n2/0.jpg"},
        files=[
            (
                "profile",
                (
                    "xhs_creator_profile.json",
                    json.dumps(payload, ensure_ascii=False).encode(),
                    "application/json",
                ),
            ),
            ("files", ("images/n2/0.jpg", b"new-jpeg", "image/jpeg")),
        ],
    )

    assert second.status_code == 201
    second_body = second.json()
    assert second_body["inputAsset"]["id"] == first_body["inputAsset"]["id"]
    assert "更新后的正文" in second_body["inputAsset"]["content"]
    listed = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/input-assets?type=xhs_creator_profile",
    ).json()
    assert len(listed) == 1


def test_xhs_offline_package_import_can_save_as_new(app: FastAPI) -> None:
    workspace = create_workspace(app)
    payload = {
        "schemaVersion": "xhs-creator-profile/v1",
        "source": {"platform": "xiaohongshu"},
        "creator": {"displayName": "QSheep", "profileText": "主页"},
        "notes": [{"noteId": "n2", "title": "申请季复盘", "desc": "正文"}],
    }
    files = [
        (
            "profile",
            (
                "xhs_creator_profile.json",
                json.dumps(payload, ensure_ascii=False).encode(),
                "application/json",
            ),
        )
    ]

    first = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import-package",
        files=files,
    )
    second = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import-package",
        data={"saveAsNew": "true"},
        files=files,
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["inputAsset"]["id"] != second.json()["inputAsset"]["id"]
    listed = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/input-assets?type=xhs_creator_profile",
    ).json()
    assert len(listed) == 2


def test_xhs_offline_package_import_rejects_path_escape(app: FastAPI) -> None:
    workspace = create_workspace(app)
    payload = {
        "schemaVersion": "xhs-creator-profile/v1",
        "source": {"platform": "xiaohongshu"},
        "creator": {"displayName": "QSheep", "profileText": ""},
        "notes": [
            {
                "noteId": "n2",
                "title": "申请季复盘",
                "desc": "正文",
                "cover": {"relativePath": "../0.jpg"},
            }
        ],
    }

    imported = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import-package",
        data={"relativePaths": "../0.jpg"},
        files=[
            (
                "profile",
                (
                    "xhs_creator_profile.json",
                    json.dumps(payload, ensure_ascii=False).encode(),
                    "application/json",
                ),
            ),
            ("files", ("0.jpg", b"fake-jpeg", "image/jpeg")),
        ],
    )

    assert imported.status_code == 422
    assert "inside the package" in imported.text


def test_xhs_offline_markdown_import_can_create_video_creator_samples(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    markdown = (
        "# 小红书主页导入\n\n"
        "- 来源：https://www.xiaohongshu.com/user/profile/video1\n\n"
        "### 1. AI短剧第一集\n\n"
        "脚本驱动明显，评论区催更。\n"
    ).encode()

    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import",
        data={"type": "video_creator_samples"},
        files={"file": ("video.md", markdown, "text/markdown")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["parsedNoteCount"] == 1
    assert body["sourceUrl"] == "https://www.xiaohongshu.com/user/profile/video1"
    assert body["inputAsset"]["type"] == "video_creator_samples"
    assert body["inputAsset"]["name"] == "小红书主页导入 - video"
    assert "脚本驱动明显" in body["inputAsset"]["content"]


def test_xhs_offline_import_rejects_unsupported_asset_type(app: FastAPI) -> None:
    workspace = create_workspace(app)

    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/input-assets/xhs-import",
        data={"type": "comments"},
        files={"file": ("xhs.md", b"# ok", "text/markdown")},
    )

    assert response.status_code == 422
    assert "historical_posts or video_creator_samples" in response.text


def test_analysis_run_can_use_saved_or_manual_account_profile(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    profile = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials",
        json={
            "type": "account_profile",
            "name": "商单驱动型创作者",
            "content": "账号定位：商单驱动，内容围绕品牌brief。",
        },
    ).json()
    historical = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials",
        json={"type": "historical_posts", "name": "历史", "content": "爆款短剧｜赞2w"},
    ).json()
    comments = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials",
        json={"type": "comments", "name": "评论", "content": "想继续看下一集。"},
    ).json()

    saved_profile_run = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "account_diagnosis",
            "accountProfileMaterialId": profile["id"],
            "historicalPostsMaterialId": historical["id"],
            "commentsMaterialId": comments["id"],
            "mode": "demo",
        },
    )
    assert saved_profile_run.status_code == 201
    snapshot = saved_profile_run.json()["inputSnapshot"]
    assert snapshot["accountPositioning"] == "账号定位：商单驱动，内容围绕品牌brief。"
    assert snapshot["accountProfile"]["source"] == "input_asset"
    assert snapshot["accountProfile"]["inputAssetId"] == profile["id"]
    assert snapshot["accountProfile"]["materialId"] == profile["id"]

    manual_profile_run = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "account_diagnosis",
            "manualAccountProfile": "账号定位：手动临时输入，不覆盖 workspace。",
            "historicalPostsMaterialId": historical["id"],
            "commentsMaterialId": comments["id"],
            "mode": "demo",
        },
    )
    assert manual_profile_run.status_code == 201
    manual_snapshot = manual_profile_run.json()["inputSnapshot"]
    assert manual_snapshot["accountProfile"]["source"] == "manual"
    assert manual_snapshot["accountPositioning"] == "账号定位：手动临时输入，不覆盖 workspace。"


def test_account_diagnosis_can_use_xhs_creator_profile_input_asset(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    xhs_asset = create_xhs_creator_profile_asset(
        app, workspace["id"], name="QSheep", note_id="n1"
    )

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs",
        json={
            "workflowType": "account_diagnosis",
            "xhsCreatorProfileInputAssetId": xhs_asset["id"],
            "mode": "demo",
        },
    )

    assert created.status_code == 201
    snapshot = created.json()["inputSnapshot"]
    assert snapshot["accountProfile"]["source"] == "xhs_creator_profile"
    assert snapshot["xhsCreatorProfile"]["inputAssetId"] == xhs_asset["id"]
    assert snapshot["xhsCreatorProfile"]["noteCount"] == 1
    assert snapshot["xhsCreatorProfile"]["commentCount"] == 1
    assert "高频标签：留学、申请" in snapshot["accountPositioning"]
    assert "专业第一" in snapshot["historicalPosts"]["content"]
    assert "真诚有勇气" in snapshot["comments"]["content"]
    assert snapshot["contextPack"]["items"][-1]["key"] == "selected_xhs_creator_profile"


def test_batch_account_diagnosis_can_use_xhs_creator_profile_assets(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    xhs_a = create_xhs_creator_profile_asset(
        app, workspace["id"], name="QSheep", note_id="n1"
    )
    xhs_b = create_xhs_creator_profile_asset(
        app, workspace["id"], name="_tt", note_id="n2"
    )

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs/batch",
        json={
            "workflowType": "account_diagnosis",
            "xhsCreatorProfileInputAssetIds": [xhs_a["id"], xhs_b["id"]],
            "mode": "demo",
        },
    )

    assert created.status_code == 201
    runs = created.json()
    assert len(runs) == 2
    assert runs[0]["inputSnapshot"]["xhsCreatorProfile"]["inputAssetId"] == xhs_a["id"]
    assert runs[1]["inputSnapshot"]["xhsCreatorProfile"]["inputAssetId"] == xhs_b["id"]
    assert runs[0]["inputSnapshot"]["accountProfile"]["name"] == "XHS QSheep 创作者主页"
    assert runs[1]["inputSnapshot"]["accountProfile"]["name"] == "XHS _tt 创作者主页"

    rejected = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs/batch",
        json={
            "workflowType": "trend_analysis",
            "xhsCreatorProfileInputAssetIds": [xhs_a["id"]],
            "mode": "demo",
        },
    )
    assert rejected.status_code == 422
    assert "only supported for account diagnosis" in rejected.json()["detail"]


def test_batch_analysis_runs_and_export_csv(app: FastAPI) -> None:
    workspace = create_workspace(app)
    historical = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials",
        json={"type": "historical_posts", "name": "历史", "content": "爆款短剧｜赞2w"},
    ).json()
    comments = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials",
        json={"type": "comments", "name": "评论", "content": "想继续看下一集。"},
    ).json()
    profile_a = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials",
        json={
            "type": "account_profile",
            "name": "剧本驱动型",
            "content": "账号定位：剧本驱动型，连续剧情。",
        },
    ).json()
    profile_b = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/source-materials",
        json={
            "type": "account_profile",
            "name": "技术探索型",
            "content": "账号定位：技术探索型，教程实验。",
        },
    ).json()

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/analysis-runs/batch",
        json={
            "workflowType": "account_diagnosis",
            "accountProfileMaterialIds": [profile_a["id"], profile_b["id"]],
            "historicalPostsMaterialId": historical["id"],
            "commentsMaterialId": comments["id"],
            "mode": "demo",
        },
    )
    assert created.status_code == 201
    runs = created.json()
    assert len(runs) == 2
    assert runs[0]["inputSnapshot"]["accountProfile"]["name"] == "剧本驱动型"
    assert runs[1]["inputSnapshot"]["accountProfile"]["name"] == "技术探索型"

    exported = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/analysis-runs/export.csv?workflowType=account_diagnosis",
    )
    assert exported.status_code == 200
    assert "profile_name" in exported.text
    assert "剧本驱动型" in exported.text
    assert "技术探索型" in exported.text
