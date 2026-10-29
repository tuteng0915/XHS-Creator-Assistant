import asyncio
import hashlib
import json
from copy import deepcopy
from unittest.mock import AsyncMock

import httpx
import pytest

from app.services import account_image_text as images
from app.services.account_diagnosis_evidence import profile_stage_input
from app.services.account_report_sources import build_report_sources


def image_snapshot(settings, *, workspace="w"):
    settings.upload_directory.mkdir(parents=True, exist_ok=True)
    data = b"saved image bytes"
    path = settings.upload_directory / "one.png"
    path.write_bytes(data)
    return {
        "workspaceId": workspace,
        "xhsCreatorProfile": {
            "notes": [
                {"noteId": "n1", "title": "图片里的正文", "desc": "引言", "metrics": {}},
            ]
        },
        "diagnosisImages": [
            {
                "assetId": "a",
                "noteId": "n1",
                "page": 1,
                "sha256": hashlib.sha256(data).hexdigest(),
                "storedKey": "one.png",
                "mediaType": "image/png",
            }
        ],
    }


def test_image_cache_projection_and_original_snapshot_preservation(app, settings, monkeypatch):
    snapshot = image_snapshot(settings)
    before = deepcopy(snapshot)
    extract = AsyncMock(return_value={"text": "真正的内容。", "model": "deepseek-flash"})
    monkeypatch.setattr(images, "extract_image", extract)
    progress = AsyncMock()
    rows = asyncio.run(images.read_note_images(app.state.analysis_service, snapshot, [], progress))
    assert rows[0]["status"] == "completed"
    cached = asyncio.run(
        images.read_note_images(app.state.analysis_service, snapshot, [], progress)
    )
    assert cached[0]["cached"]
    assert extract.await_count == 1
    projected = images.snapshot_with_image_text(snapshot, rows)
    assert snapshot == before
    assert (
        projected["xhsCreatorProfile"]["notes"][0]["desc"]
        == "引言\n\n【图片1识别文字】\n真正的内容。"
    )
    packet, _ = profile_stage_input(projected, "2026-10-29T00:00:00Z")
    assert "真正的内容" in packet["historicalPosts"]
    assert "真正的内容。" in build_report_sources(projected)["n1"].values()
    another = deepcopy(snapshot)
    another["workspaceId"] = "another"
    asyncio.run(images.read_note_images(app.state.analysis_service, another, [], progress))
    assert extract.await_count == 2


def test_image_failure_does_not_drop_text_and_retry_preserves_success(app, settings, monkeypatch):
    snapshot = image_snapshot(settings)
    snapshot["diagnosisImages"].append(
        {**snapshot["diagnosisImages"][0], "assetId": "b", "storedKey": "missing.png", "page": 2}
    )
    extract = AsyncMock(return_value={"text": "正文", "model": "deepseek-flash"})
    monkeypatch.setattr(images, "extract_image", extract)
    rows = asyncio.run(
        images.read_note_images(app.state.analysis_service, snapshot, [], AsyncMock())
    )
    assert [row["status"] for row in rows] == ["completed", "failed"]
    assert images.snapshot_with_image_text(snapshot, rows)["xhsCreatorProfile"]["notes"][0][
        "desc"
    ].startswith("引言")
    asyncio.run(images.read_note_images(app.state.analysis_service, snapshot, rows, AsyncMock()))
    assert extract.await_count == 1


def test_identical_images_in_one_run_share_one_request(app, settings, monkeypatch):
    snapshot = image_snapshot(settings)
    snapshot["diagnosisImages"].append(
        {**snapshot["diagnosisImages"][0], "assetId": "b", "page": 2},
    )
    extract = AsyncMock(return_value={"text": "正文", "model": "deepseek-flash"})
    monkeypatch.setattr(images, "extract_image", extract)
    rows = asyncio.run(images.read_note_images(
        app.state.analysis_service, snapshot, [], AsyncMock(),
    ))
    assert len(rows) == 2
    assert extract.await_count == 1


@pytest.mark.parametrize("key", ["../secret.png", "", "missing.png"])
def test_missing_or_outside_image_never_reaches_provider(app, settings, monkeypatch, key):
    snapshot = image_snapshot(settings)
    snapshot["diagnosisImages"][0]["storedKey"] = key
    extract = AsyncMock()
    monkeypatch.setattr(images, "extract_image", extract)
    rows = asyncio.run(
        images.read_note_images(app.state.analysis_service, snapshot, [], AsyncMock())
    )
    assert rows[0]["status"] == "failed"
    extract.assert_not_called()


def test_deepseek_vision_transport_uses_images_non_thinking_and_no_fallback(settings, monkeypatch):
    from dataclasses import replace

    settings = replace(settings, deepseek_api_key="test-key")
    requests = []

    def handle(request):
        payload = json.loads(request.content)
        requests.append(payload)
        assert payload["model"] == "deepseek-flash"
        assert payload["thinking"] == {"type": "disabled"}
        image = payload["messages"][1]["content"][1]
        assert image["image_url"]["url"].startswith("data:image/png;base64,")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"text":"识别文字"}'}}
                ]
            },
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        images.httpx,
        "AsyncClient",
        lambda **kw: client(
            transport=httpx.MockTransport(handle),
            **kw,
        ),
    )
    result = asyncio.run(images.extract_image(settings, b"image", "image/png"))
    assert result["text"] == "识别文字"
    assert len(requests) == 1
