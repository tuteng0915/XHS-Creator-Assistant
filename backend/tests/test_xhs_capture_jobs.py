import asyncio
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from threading import Event

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.models import (
    SourceMaterialType,
    TextSourceMaterialCreate,
    XhsCaptureJobCreate,
    XhsCaptureJobStatus,
    XhsOfflineImportPackageResponse,
)
from app.repositories.workspaces import WorkspaceRepository
from app.services.xhs_capture_jobs import MediaCrawlerXhsCaptureRunner, XhsCaptureResult


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
        json={"name": "新账号档案", "accountPositioning": ""},
    )
    assert response.status_code == 201
    return response.json()


class BlockingCaptureRunner:
    def __init__(self, app: FastAPI) -> None:
        self.app = app
        self.started = Event()
        self.release = Event()
        self.calls = 0

    def run(self, **kwargs) -> XhsCaptureResult:
        self.calls += 1
        progress = kwargs["progress"]
        profile_url = kwargs["profile_url"]
        progress(
            XhsCaptureJobStatus.WAITING_FOR_LOGIN,
            "请扫码登录",
            profile_url,
        )
        self.started.set()
        assert self.release.wait(timeout=3)
        progress(XhsCaptureJobStatus.PROCESSING, "正在整理", profile_url)
        material = self.app.state.input_asset_service.create_text(
            kwargs["workspace_id"],
            TextSourceMaterialCreate(
                type=SourceMaterialType.XHS_CREATOR_PROFILE,
                name="QSheep 创作者主页",
                content=(
                    '{"schemaVersion":"xhs-creator-profile/v1",'
                    '"creator":{"displayName":"QSheep"},'
                    '"notes":[{"noteId":"n1","title":"测试笔记"}]}'
                ),
            ),
        )
        return XhsCaptureResult(
            resolved_url=profile_url,
            imported=XhsOfflineImportPackageResponse(
                input_asset=material,
                parsed_note_count=1,
                source_url=profile_url,
                warnings=[],
                media_assets=[],
            ),
            display_name="QSheep",
        )


def test_xhs_capture_rejects_non_profile_url(app: FastAPI) -> None:
    workspace = create_workspace(app)
    response = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/xhs-capture-jobs",
        json={"profileUrl": "https://example.com/not-xhs"},
    )
    assert response.status_code == 422
    assert "小红书" in response.json()["detail"]


def test_xhs_capture_is_single_flight_and_persists_result(app: FastAPI) -> None:
    workspace = create_workspace(app)
    runner = BlockingCaptureRunner(app)
    service = app.state.xhs_capture_service
    service.runner = runner
    url = "https://www.xiaohongshu.com/user/profile/5d2aefea0000000010004907"

    first = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/xhs-capture-jobs",
        json={"profileUrl": url, "noteLimit": 20, "includeComments": True},
    )
    assert first.status_code == 202
    assert runner.started.wait(timeout=2)

    duplicate = send(
        app,
        "POST",
        f"/api/workspaces/{workspace['id']}/xhs-capture-jobs",
        json={"profileUrl": url, "noteLimit": 20, "includeComments": True},
    )
    assert duplicate.status_code == 202
    assert duplicate.json()["id"] == first.json()["id"]
    assert runner.calls == 1

    runner.release.set()
    completed = None
    for _ in range(40):
        response = send(app, "GET", f"/api/xhs-capture-jobs/{first.json()['id']}")
        completed = response.json()
        if completed["status"] == "completed":
            break
        time.sleep(0.05)

    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["resultInputAssetId"]
    renamed = send(app, "GET", f"/api/workspaces/{workspace['id']}")
    assert renamed.json()["name"] == "QSheep"


def test_workspace_list_is_scoped_to_default_user(app: FastAPI) -> None:
    workspace = create_workspace(app)
    database = app.state.database
    with database.transaction() as connection:
        connection.execute(
            """
            INSERT INTO app_users(id, display_name, created_at, updated_at)
            VALUES ('other-user', '另一个用户', '2026-09-23T10:00:00Z', '2026-09-23T10:00:00Z')
            """
        )
        WorkspaceRepository().create(
            connection,
            owner_user_id="other-user",
            name="不应出现在默认用户列表",
            account_positioning="隔离数据",
            now="2026-09-23T10:00:00Z",
        )
    listed = send(app, "GET", "/api/workspaces")
    assert [item["id"] for item in listed.json()] == [workspace["id"]]


def test_capture_defaults_and_explicit_all():
    url = "https://xhslink.cn/m/test"
    assert XhsCaptureJobCreate(profile_url=url).note_limit == 10
    assert XhsCaptureJobCreate(profile_url=url, note_limit=0).note_limit == 0


def test_runner_reports_observed_login_and_reading_states(app, settings):
    runner = MediaCrawlerXhsCaptureRunner(
        settings, app.state.xhs_capture_service.runner.import_service
    )
    events = []
    output = runner._capture(
        [sys.executable, "-c", "print('waiting for scan code'); "
         "print('Begin get Xiaohongshu creators')"],
        "https://xhslink.cn/m/test",
        lambda state, message, url: events.append(state),
    )
    assert events == [XhsCaptureJobStatus.WAITING_FOR_LOGIN, XhsCaptureJobStatus.RUNNING]
    assert "Begin get Xiaohongshu creators" in output


def test_capture_restart_marks_job_failed_without_reexecuting(app: FastAPI):
    workspace = create_workspace(app)
    service = app.state.xhs_capture_service
    with service.database.transaction() as connection:
        row = service.repository.create(
            connection, workspace_id=workspace["id"], profile_url="https://xhslink.cn/m/test",
            note_limit=10, include_comments=True, now="2026-09-23T10:00:00Z",
        )
    service.recover_interrupted()
    result = service.get(row["id"])
    assert result.status == XhsCaptureJobStatus.FAILED
    assert result.completed_at is not None
    assert not service.futures


def test_runner_imports_package_and_reuses_profile_on_refresh(app, settings, tmp_path, monkeypatch):
    workspace = create_workspace(app)
    crawler = tmp_path / "crawler"
    crawler.mkdir()
    (crawler / "main.py").touch()
    settings = replace(settings, xhs_capture_directory=tmp_path / "captures",
                       xhs_mediacrawler_directory=crawler)
    runner = MediaCrawlerXhsCaptureRunner(
        settings, app.state.xhs_capture_service.runner.import_service
    )
    url = "https://www.xiaohongshu.com/user/profile/test-account"
    monkeypatch.setattr(runner, "_capture", lambda *args: f"使用主页 URL：{url}")

    def export(command, **kwargs):
        output = Path(command[command.index("--output") + 1])
        output.mkdir(parents=True)
        (output / "xhs_creator_profile.json").write_text(json.dumps({
            "schemaVersion": "xhs-creator-profile/v1", "source": {},
            "creator": {"displayName": "测试账号"},
            "notes": [{"noteId": "n1", "title": "笔记", "desc": "中文正文", "comments": []}],
        }), encoding="utf-8")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", export)
    result = runner.run(job_id="job1", workspace_id=workspace["id"], profile_url=url,
                        note_limit=10, include_comments=True, progress=lambda *args: None)
    repeated = runner.run(job_id="job2", workspace_id=workspace["id"], profile_url=url,
                          note_limit=20, include_comments=True, progress=lambda *args: None)
    assert result.imported.input_asset.id == repeated.imported.input_asset.id
    assert "中文正文" in repeated.imported.input_asset.content
    assert json.loads(repeated.imported.input_asset.content)["source"]["profileUrl"] == url
