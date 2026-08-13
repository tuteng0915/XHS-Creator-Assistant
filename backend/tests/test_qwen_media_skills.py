from __future__ import annotations

import json as jsonlib
import subprocess
from pathlib import Path
from typing import Any

import httpx
from test_workspace_api import create_workspace, send

from app.config import Settings
from app.main import create_app


class FakeQwenClient:
    requests: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    def __enter__(self) -> FakeQwenClient:
        return self

    def __exit__(self, *args: Any) -> None:
        return None

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> httpx.Response:
        self.requests.append(
            {"method": "POST", "url": url, "headers": headers, "json": json}
        )
        if url.endswith("/chat/completions"):
            content = json["messages"][0]["content"]
            text_parts = [
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            if any("videoUnderstanding" in text for text in text_parts):
                return httpx.Response(
                    200,
                    json={
                        "model": "qwen-vl-plus",
                        "choices": [
                            {
                                "message": {
                                    "content": jsonlib.dumps(
                                        {
                                            "videoUnderstanding": {
                                                "sceneSummary": "两帧显示 AI 短剧冲突开场。",
                                                "transcript": "",
                                                "visualSummary": "竖屏人物对话。",
                                                "audioSummary": "",
                                                "qualitySignals": ["剧情驱动"],
                                                "creatorSignals": ["系列化"],
                                                "incentiveFitSignals": ["适合激励"],
                                                "risks": [],
                                                "uncertainties": [],
                                            }
                                        },
                                        ensure_ascii=False,
                                    )
                                }
                            }
                        ],
                        "usage": {"total_tokens": 32},
                    },
                )
            return httpx.Response(
                200,
                json={
                    "model": "qwen-vl-plus",
                    "choices": [
                        {
                            "message": {
                                "content": jsonlib.dumps(
                                    {
                                        "imageUnderstanding": {
                                            "visualSummary": "画面包含留学账号主页截图。",
                                            "extractedText": "留学申请",
                                            "styleTags": ["清爽"],
                                            "creatorSignals": ["专业可信"],
                                            "risks": [],
                                            "uncertainties": [],
                                        }
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ],
                    "usage": {"total_tokens": 24},
                },
            )
        if url.endswith("/text2image/image-synthesis"):
            return httpx.Response(
                200,
                json={"output": {"task_id": "image-task-1", "task_status": "PENDING"}},
            )
        if url.endswith("/video-generation/video-synthesis"):
            return httpx.Response(
                200,
                json={"output": {"task_id": "video-task-1", "task_status": "PENDING"}},
            )
        raise AssertionError(f"unexpected POST {url}")

    def get(self, url: str, *, headers: dict[str, str]) -> httpx.Response:
        self.requests.append({"method": "GET", "url": url, "headers": headers})
        if url == "https://cdn.example.test/qwen-image.png":
            return httpx.Response(
                200,
                content=b"generated-image",
                headers={"content-type": "image/png"},
            )
        if url == "https://cdn.example.test/qwen-video.mp4":
            return httpx.Response(
                200,
                content=b"generated-video",
                headers={"content-type": "video/mp4"},
            )
        if url.endswith("/tasks/image-task-1"):
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_id": "image-task-1",
                        "task_status": "SUCCEEDED",
                        "results": [{"url": "https://cdn.example.test/qwen-image.png"}],
                    },
                    "usage": {"image_count": 1},
                },
            )
        if url.endswith("/tasks/video-task-1"):
            return httpx.Response(
                200,
                json={
                    "output": {
                        "task_id": "video-task-1",
                        "task_status": "SUCCEEDED",
                        "results": [{"video_url": "https://cdn.example.test/qwen-video.mp4"}],
                    },
                    "usage": {"video_count": 1},
                },
            )
        raise AssertionError(f"unexpected GET {url}")


def qwen_app(tmp_path: Path):
    return create_app(
        Settings(
            database_path=tmp_path / "qwen-media.sqlite3",
            upload_directory=tmp_path / "uploads",
            qwen_api_key="dashscope-key",
            qwen_base_url="https://workspace.cn-beijing.maas.aliyuncs.com/compatible-mode/v1",
            qwen_dashscope_base_url="https://workspace.cn-beijing.maas.aliyuncs.com/api/v1",
            qwen_task_poll_interval_seconds=0,
            qwen_task_poll_attempts=2,
        )
    )


def skill_by_id(app, workspace_id: str, skill_id: str) -> dict[str, Any]:
    skills = send(app, "GET", f"/api/workspaces/{workspace_id}/skills").json()
    return next(skill for skill in skills if skill["skillId"] == skill_id)


def test_qwen_image_understanding_skill_uses_saved_image_as_data_url(
    monkeypatch,
    tmp_path,
) -> None:
    FakeQwenClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeQwenClient)
    app = qwen_app(tmp_path)
    workspace = create_workspace(app)
    image = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/media-assets/upload",
        data={"type": "image", "name": "主页截图"},
        files={"file": ("home.png", b"\x89PNG\r\n\x1a\nfake", "image/png")},
    ).json()
    skill = skill_by_id(app, workspace["id"], "media.understand_image")

    response = send(
        app,
        "POST",
        f"/api/skills/{skill['id']}/invoke",
        json={
            "mode": "live",
            "input": {
                "mediaAssetId": image["id"],
                "prompt": "请描述画面，并提取可用于账号诊断的视觉线索。",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["skillId"] == "media.understand_image"
    assert body["output"]["text"] == "画面包含留学账号主页截图。"
    assert body["output"]["imageUnderstanding"]["creatorSignals"] == ["专业可信"]
    request = FakeQwenClient.requests[0]
    assert request["url"] == (
        "https://workspace.cn-beijing.maas.aliyuncs.com"
        "/compatible-mode/v1/chat/completions"
    )
    content = request["json"]["messages"][0]["content"]
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[1]["text"].startswith("请描述画面，并提取可用于账号诊断的视觉线索。")
    assert "imageUnderstanding" in content[1]["text"]


def test_qwen_video_understanding_skill_derives_frames_for_local_video(
    monkeypatch,
    tmp_path,
) -> None:
    FakeQwenClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeQwenClient)

    def fake_run(command, **_kwargs):
        output_pattern = Path(command[-1])
        output_pattern.parent.mkdir(parents=True, exist_ok=True)
        (output_pattern.parent / "frame_001.jpg").write_bytes(b"frame-one")
        (output_pattern.parent / "frame_002.jpg").write_bytes(b"frame-two")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", fake_run)
    app = qwen_app(tmp_path)
    workspace = create_workspace(app)
    video = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/media-assets/upload",
        data={"type": "video", "name": "AI短剧样本"},
        files={"file": ("sample.mp4", b"fake-video", "video/mp4")},
    ).json()
    skill = skill_by_id(app, workspace["id"], "media.understand_video")

    response = send(
        app,
        "POST",
        f"/api/skills/{skill['id']}/invoke",
        json={
            "mode": "live",
            "input": {
                "mediaAssetId": video["id"],
                "prompt": "请分析这个视频样本的质量。",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["output"]["text"] == "两帧显示 AI 短剧冲突开场。"
    assert body["output"]["frameCount"] == 2
    assert body["output"]["sourceAsset"]["mediaAssetId"] == video["id"]
    assert body["output"]["videoAsset"]["id"] == video["id"]
    assert len(body["output"]["derivedFrameAssets"]) == 2
    request = FakeQwenClient.requests[0]
    content = request["json"]["messages"][0]["content"]
    image_parts = [item for item in content if item.get("type") == "image_url"]
    assert len(image_parts) == 2
    assert image_parts[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")
    assert "videoUnderstanding" in content[-1]["text"]

    updated_video = send(app, "GET", f"/api/media-assets/{video['id']}").json()
    assert updated_video["derived"]["videoPreview"]["frameCount"] == 2


def test_qwen_image_generation_skill_persists_generated_media_asset(
    monkeypatch,
    tmp_path,
) -> None:
    FakeQwenClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeQwenClient)
    app = qwen_app(tmp_path)
    workspace = create_workspace(app)
    skill = skill_by_id(app, workspace["id"], "media.generate_image")

    response = send(
        app,
        "POST",
        f"/api/skills/{skill['id']}/invoke",
        json={
            "mode": "live",
            "input": {
                "prompt": "生成一张留学账号主页视觉参考图",
                "name": "留学主页视觉参考",
                "purpose": "主页视觉定位",
                "size": "1024*1024",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    asset = body["output"]["mediaAsset"]
    assert asset["type"] == "image"
    assert asset["sourceType"] == "generated"
    assert asset["externalUrl"] == "https://cdn.example.test/qwen-image.png"
    assert asset["fileUrl"] == f"/api/media-assets/{asset['id']}/file"
    assert asset["metadata"]["prompt"] == "生成一张留学账号主页视觉参考图"

    listed = send(
        app,
        "GET",
        f"/api/workspaces/{workspace['id']}/media-assets?type=image",
    ).json()
    assert [item["id"] for item in listed] == [asset["id"]]
    submit_request = FakeQwenClient.requests[0]
    assert submit_request["url"].endswith("/text2image/image-synthesis")
    assert submit_request["headers"]["x-dashscope-async"] == "enable"
    assert submit_request["json"]["model"] == "wanx-v1"
    file_response = send(app, "GET", f"/api/media-assets/{asset['id']}/file")
    assert file_response.status_code == 200
    assert file_response.content == b"generated-image"


def test_qwen_video_generation_skill_persists_generated_media_asset(
    monkeypatch,
    tmp_path,
) -> None:
    FakeQwenClient.requests = []
    monkeypatch.setattr(httpx, "Client", FakeQwenClient)
    app = qwen_app(tmp_path)
    workspace = create_workspace(app)
    skill = skill_by_id(app, workspace["id"], "media.generate_video")

    response = send(
        app,
        "POST",
        f"/api/skills/{skill['id']}/invoke",
        json={
            "mode": "live",
            "input": {
                "prompt": "生成一个 AIGC 短剧开场镜头",
                "name": "AI短剧开场参考",
                "duration": 5,
            },
        },
    )

    assert response.status_code == 200
    asset = response.json()["output"]["mediaAsset"]
    assert asset["type"] == "video"
    assert asset["sourceType"] == "generated"
    assert asset["externalUrl"] == "https://cdn.example.test/qwen-video.mp4"
    submit_request = FakeQwenClient.requests[0]
    assert submit_request["url"].endswith("/video-generation/video-synthesis")
    assert submit_request["json"]["model"] == "wan2.7-t2v-2026-06-12"
    assert submit_request["json"]["parameters"]["resolution"] == "720P"
    assert submit_request["json"]["parameters"]["ratio"] == "16:9"
    file_response = send(app, "GET", f"/api/media-assets/{asset['id']}/file")
    assert file_response.status_code == 200
    assert file_response.content == b"generated-video"
