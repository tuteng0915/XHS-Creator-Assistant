import asyncio
import json
import subprocess
import sys
import time
from dataclasses import replace
from pathlib import Path
from threading import Event

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.models import (
    SourceMaterialType,
    TextSourceMaterialCreate,
    XhsCaptureJobCreate,
    XhsCaptureJobStatus,
    XhsCaptureProgress,
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
            XhsCaptureProgress(phase="login"),
        )
        self.started.set()
        assert self.release.wait(timeout=3)
        progress(
            XhsCaptureJobStatus.PROCESSING, "正在整理", profile_url,
            XhsCaptureProgress(phase="processing", captured_notes=1),
        )
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
    active = send(app, "GET", f"/api/xhs-capture-jobs/{first.json()['id']}")
    assert active.json()["progress"]["phase"] == "login"

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
    assert completed["progress"] == {
        "phase": "completed", "capturedNotes": 1, "capturedComments": 0,
        "commentNotesCompleted": 0, "commentNotesTotal": None,
    }
    assert completed["resultInputAssetId"]
    renamed = send(app, "GET", f"/api/workspaces/{workspace['id']}")
    assert renamed.json()["name"] == "QSheep 的工作区"


def test_capture_default_name_does_not_replace_custom_workspace_name(app: FastAPI) -> None:
    workspace = create_workspace(app)
    service = app.state.xhs_capture_service
    with app.state.database.transaction() as connection:
        connection.execute(
            "UPDATE creator_workspaces SET name = ? WHERE id = ?",
            ("自定义名称", workspace["id"]),
        )
    service._rename_workspace(workspace["id"], "Ag")
    assert send(app, "GET", f"/api/workspaces/{workspace['id']}").json()["name"] == "自定义名称"

    with app.state.database.transaction() as connection:
        connection.execute(
            "UPDATE creator_workspaces SET name = ? WHERE id = ?",
            ("正在导入的账号", workspace["id"]),
        )
    service._rename_workspace(workspace["id"], "Ag")
    assert send(app, "GET", f"/api/workspaces/{workspace['id']}").json()["name"] == "Ag 的工作区"


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
        lambda state, message, url, details: events.append(state),
    )
    assert events == [XhsCaptureJobStatus.WAITING_FOR_LOGIN, XhsCaptureJobStatus.RUNNING]
    assert "Begin get Xiaohongshu creators" in output


def test_runner_counts_unique_saved_rows_and_comment_note_progress(
    app, settings, tmp_path: Path,
):
    runner = MediaCrawlerXhsCaptureRunner(
        settings, app.state.xhs_capture_service.runner.import_service
    )
    jsonl = tmp_path / "xhs" / "jsonl"
    jsonl.mkdir(parents=True)
    (jsonl / "creator_contents_2026-10-01.jsonl").write_text(
        '\n'.join([json.dumps({"note_id": "n1"}), json.dumps({"note_id": "n1"}),
                   json.dumps({"note_id": "n2"}), '{']) + '\n', encoding="utf-8"
    )
    (jsonl / "creator_comments_2026-10-01.jsonl").write_text(
        '\n'.join([json.dumps({"comment_id": "c1"}), json.dumps({"comment_id": "c1"}),
                   json.dumps({"comment_id": "c2"})]) + '\n', encoding="utf-8"
    )
    events = []
    runner._capture(
        [sys.executable, "-c", "print('Begin get Xiaohongshu creators'); "
         "print(\"Begin batch get note comments, note list: ['n1', 'n2']\"); "
         "print('Sleeping for 1 seconds after fetching comments for note n1')"],
        "https://xhslink.cn/m/test",
        lambda state, message, url, details: events.append(details.model_dump()),
        tmp_path,
    )
    assert events[-1] == {
        "phase": "comments", "captured_notes": 2, "captured_comments": 2,
        "comment_notes_completed": 1, "comment_notes_total": 2,
    }


def test_runner_reports_sanitized_browser_timeout(app, settings):
    runner = MediaCrawlerXhsCaptureRunner(
        settings, app.state.xhs_capture_service.runner.import_service
    )
    secret = "xsec_token=private-session-value"
    with pytest.raises(RuntimeError, match="抓取浏览器打开小红书页面超时") as error:
        runner._capture(
            [sys.executable, "-c", "import sys; "
             f"print('Page.goto: Timeout 30000ms exceeded {secret}'); sys.exit(1)"],
            "https://www.xiaohongshu.com/user/profile/test-account",
            lambda *_: None,
        )
    assert secret not in str(error.value)


def test_runner_reports_sanitized_browser_network_error(app, settings):
    runner = MediaCrawlerXhsCaptureRunner(
        settings, app.state.xhs_capture_service.runner.import_service
    )
    with pytest.raises(RuntimeError, match="ERR_CONNECTION_TIMED_OUT") as error:
        runner._capture(
            [sys.executable, "-c", "import sys; "
             "print('Page.goto: net::ERR_CONNECTION_TIMED_OUT "
             "xsec_token=private-session-value'); sys.exit(1)"],
            "https://www.xiaohongshu.com/user/profile/test-account",
            lambda *_: None,
        )
    assert "private-session-value" not in str(error.value)


def test_runner_reports_sanitized_creator_state_parse_failure(app, settings):
    runner = MediaCrawlerXhsCaptureRunner(
        settings, app.state.xhs_capture_service.runner.import_service
    )
    with pytest.raises(RuntimeError, match="主页已打开，但页面数据格式暂无法解析") as error:
        runner._capture(
            [sys.executable, "-c", "import sys; "
             "print('Creator homepage state parse failed: position 62376 "
             "xsec_token=private-session-value'); sys.exit(1)"],
            "https://www.xiaohongshu.com/user/profile/test-account",
            lambda *_: None,
        )
    assert "private-session-value" not in str(error.value)


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
