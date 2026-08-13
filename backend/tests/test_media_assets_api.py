import asyncio
import subprocess
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
            "name": "媒体素材工作区",
            "accountPositioning": "分析 AIGC 视频创作者。",
        },
    )
    assert response.status_code == 201
    return response.json()


def upload_media(
    app: FastAPI,
    workspace_id: str,
    *,
    asset_type: str,
    name: str,
    filename: str,
    content: bytes,
    media_type: str,
) -> dict:
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace_id}/media-assets/upload",
        data={"type": asset_type, "name": name},
        files={"file": (filename, content, media_type)},
    )
    assert response.status_code == 201
    return response.json()


def test_image_media_asset_upload_update_list_and_file(app: FastAPI) -> None:
    workspace = create_workspace(app)
    image_bytes = b"\x89PNG\r\n\x1a\nfake-image"

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/media-assets/upload",
        data={
            "type": "image",
            "name": "主页截图",
            "purpose": "账号主页视觉定位参考",
        },
        files={"file": ("../unsafe/home.png", image_bytes, "image/png")},
    )

    assert created.status_code == 201
    asset = created.json()
    assert asset["type"] == "image"
    assert asset["name"] == "主页截图"
    assert asset["purpose"] == "账号主页视觉定位参考"
    assert asset["originalFilename"] == "home.png"
    assert asset["mediaType"] == "image/png"
    assert asset["metadata"] == {"width": None, "height": None}
    assert asset["derived"]["visualSummary"] == ""
    assert asset["fileUrl"] == f"/api/media-assets/{asset['id']}/file"
    assert "storedKey" not in asset

    listed = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/media-assets?type=image",
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [asset["id"]]

    updated = send(
        app,
        "PATCH",
        f"/api/media-assets/{asset['id']}",
        json={
            "name": "主页截图 v2",
            "derived": {
                "extractedText": "关注留学申请",
                "visualSummary": "主页强调留学申请路径。",
                "tags": ["主页", "截图"],
            },
            "userNotes": "用户手动补充：截图来自小红书主页。",
            "expectedUpdatedAt": asset["updatedAt"],
        },
    )
    assert updated.status_code == 200
    updated_asset = updated.json()
    assert updated_asset["name"] == "主页截图 v2"
    assert updated_asset["derived"]["extractedText"] == "关注留学申请"
    assert updated_asset["userNotes"] == "用户手动补充：截图来自小红书主页。"

    stale = send(
        app,
        "PATCH",
        f"/api/media-assets/{asset['id']}",
        json={
            "name": "不应覆盖",
            "expectedUpdatedAt": asset["updatedAt"],
        },
    )
    assert stale.status_code == 409

    file_response = send(app, "GET", f"/api/media-assets/{asset['id']}/file")
    assert file_response.status_code == 200
    assert file_response.content == image_bytes
    assert file_response.headers["content-type"].startswith("image/png")


def test_video_media_asset_upload_preserves_editable_derived_fields(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    video_bytes = b"fake-video"

    created = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/media-assets/upload",
        data={
            "type": "video",
            "name": "AI短剧样本",
            "purpose": "视频质量诊断样本",
        },
        files={"file": ("sample.mp4", video_bytes, "video/mp4")},
    )

    assert created.status_code == 201
    asset = created.json()
    assert asset["type"] == "video"
    assert asset["metadata"]["durationSeconds"] is None
    assert asset["derived"]["transcript"] == ""
    assert asset["derived"]["metrics"] == {}

    updated = send(
        app,
        "PATCH",
        f"/api/media-assets/{asset['id']}",
        json={
            "metadata": {
                "durationSeconds": 42,
                "width": 1080,
                "height": 1920,
                "fps": 30,
            },
            "derived": {
                "transcript": "第一幕：AI短剧开场。",
                "sceneSummary": "三段式短剧结构。",
                "visualSummary": "竖屏快节奏剪辑。",
                "audioSummary": "旁白驱动。",
                "tags": ["AI短剧"],
                "metrics": {"likes": 1200, "comments": 80},
            },
            "expectedUpdatedAt": asset["updatedAt"],
        },
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["metadata"]["durationSeconds"] == 42
    assert body["derived"]["metrics"]["likes"] == 1200


def test_media_asset_upload_rejects_mismatched_type(app: FastAPI) -> None:
    workspace = create_workspace(app)

    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/media-assets/upload",
        data={"type": "image", "name": "错误素材"},
        files={"file": ("sample.mp4", b"fake-video", "video/mp4")},
    )

    assert response.status_code == 422


def test_media_asset_upload_validates_blank_name_empty_content_and_extension(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)

    blank_name = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/media-assets/upload",
        data={"type": "image", "name": "   "},
        files={"file": ("home.png", b"fake-image", "image/png")},
    )
    assert blank_name.status_code == 422
    assert blank_name.json()["detail"] == "Media asset name cannot be blank"

    empty_file = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/media-assets/upload",
        data={"type": "image", "name": "空文件"},
        files={"file": ("home.png", b"", "image/png")},
    )
    assert empty_file.status_code == 422
    assert empty_file.json()["detail"] == "Media file cannot be empty"

    unsupported_extension = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/media-assets/upload",
        data={"type": "image", "name": "文本文件"},
        files={"file": ("home.txt", b"not-an-image", "image/png")},
    )
    assert unsupported_extension.status_code == 422
    assert unsupported_extension.json()["detail"] == "Only image files are supported"


def test_media_assets_can_be_listed_across_image_and_video_types(
    app: FastAPI,
) -> None:
    workspace = create_workspace(app)
    image = upload_media(
        app,
        workspace["id"],
        asset_type="image",
        name="主页截图",
        filename="home.png",
        content=b"fake-image",
        media_type="image/png",
    )
    video = upload_media(
        app,
        workspace["id"],
        asset_type="video",
        name="AI短剧样本",
        filename="sample.mp4",
        content=b"fake-video",
        media_type="video/mp4",
    )

    listed = send(app, "GET", f"/api/workspaces/{workspace['id']}/media-assets")

    assert listed.status_code == 200
    items = listed.json()
    assert {item["id"] for item in items} == {image["id"], video["id"]}
    assert {item["type"] for item in items} == {"image", "video"}


def test_video_preview_derivation_extracts_persistent_frame_assets(
    app: FastAPI,
    monkeypatch,
) -> None:
    workspace = create_workspace(app)
    video = upload_media(
        app,
        workspace["id"],
        asset_type="video",
        name="AI短剧样本",
        filename="sample.mp4",
        content=b"fake-video",
        media_type="video/mp4",
    )

    def fake_run(command, **_kwargs):
        output_pattern = Path(command[-1])
        output_pattern.parent.mkdir(parents=True, exist_ok=True)
        (output_pattern.parent / "frame_001.jpg").write_bytes(b"frame-one")
        (output_pattern.parent / "frame_002.jpg").write_bytes(b"frame-two")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)

    response = send(
        app,
        "POST",
        f"/api/media-assets/{video['id']}/derive-video-preview",
        json={"frameCount": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["videoAsset"]["id"] == video["id"]
    preview = body["videoAsset"]["derived"]["videoPreview"]
    assert preview["frameCount"] == 2
    assert len(preview["frames"]) == 2
    assert [frame["type"] for frame in body["frames"]] == ["image", "image"]
    assert {frame["sourceType"] for frame in body["frames"]} == {"extracted_frame"}
    assert body["frames"][0]["metadata"]["sourceVideoAssetId"] == video["id"]

    frame_file = send(app, "GET", body["frames"][0]["fileUrl"])
    assert frame_file.status_code == 200
    assert frame_file.content == b"frame-one"

    reused = send(
        app,
        "POST",
        f"/api/media-assets/{video['id']}/derive-video-preview",
        json={"frameCount": 2},
    )
    assert reused.status_code == 200
    assert [frame["id"] for frame in reused.json()["frames"]] == [
        frame["id"] for frame in body["frames"]
    ]


def test_video_preview_derivation_rejects_image_assets(app: FastAPI) -> None:
    workspace = create_workspace(app)
    image = upload_media(
        app,
        workspace["id"],
        asset_type="image",
        name="主页截图",
        filename="home.png",
        content=b"fake-image",
        media_type="image/png",
    )

    response = send(
        app,
        "POST",
        f"/api/media-assets/{image['id']}/derive-video-preview",
        json={"frameCount": 2},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "Video preview can only be derived from video assets"


def test_media_asset_get_and_update_validation_errors(app: FastAPI) -> None:
    workspace = create_workspace(app)
    asset = upload_media(
        app,
        workspace["id"],
        asset_type="image",
        name="主页截图",
        filename="home.png",
        content=b"fake-image",
        media_type="image/png",
    )

    missing = send(app, "GET", "/api/media-assets/not-found")
    assert missing.status_code == 404

    no_editable_fields = send(
        app,
        "PATCH",
        f"/api/media-assets/{asset['id']}",
        json={"expectedUpdatedAt": asset["updatedAt"]},
    )
    assert no_editable_fields.status_code == 422
    assert no_editable_fields.json()["detail"] == "At least one editable field is required"

    blank_name = send(
        app,
        "PATCH",
        f"/api/media-assets/{asset['id']}",
        json={"name": "  ", "expectedUpdatedAt": asset["updatedAt"]},
    )
    assert blank_name.status_code == 422
    assert blank_name.json()["detail"] == "Media asset name cannot be blank"
