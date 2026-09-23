from __future__ import annotations

import json
import mimetypes
import os
import selectors
import signal
import subprocess
import sys
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from urllib.parse import urlparse

from app.config import Settings
from app.db.database import SQLiteDatabase
from app.errors import ValidationError
from app.models import (
    WorkspaceUpdate,
    XhsCaptureJobCreate,
    XhsCaptureJobResponse,
    XhsCaptureJobStatus,
    XhsOfflineImportPackageResponse,
)
from app.repositories.workspaces import WorkspaceRepository
from app.repositories.xhs_capture_jobs import XhsCaptureJobRepository
from app.services.common import utc_now
from app.services.workspaces import WorkspaceService
from app.services.xhs_imports import XhsOfflineImportService, XhsPackageFile

ProgressCallback = Callable[[XhsCaptureJobStatus, str, str], None]


@dataclass(frozen=True)
class XhsCaptureResult:
    resolved_url: str
    imported: XhsOfflineImportPackageResponse
    display_name: str


class MediaCrawlerXhsCaptureRunner:
    def __init__(
        self,
        settings: Settings,
        import_service: XhsOfflineImportService,
    ) -> None:
        self.settings = settings
        self.import_service = import_service
        self.repository_root = Path(__file__).resolve().parents[3]
        self.stopping = Event()

    def shutdown(self) -> None:
        self.stopping.set()

    def _capture(
        self, command: list[str], profile_url: str, progress: ProgressCallback
    ) -> str:
        """Read real crawler progress; keep browser descendants within the job lifetime."""
        lines: list[str] = []
        resolved_line = ""
        process = subprocess.Popen(
            command, cwd=self.repository_root, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        deadline = time.monotonic() + 20 * 60
        pending = b""
        try:
            assert process.stdout is not None
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while True:
                    if self.stopping.is_set():
                        raise RuntimeError("导入因后端关闭而中断，请重新开始。")
                    if time.monotonic() > deadline:
                        raise RuntimeError("本次读取超过 20 分钟，请减少读取数量后重试。")
                    ready = selector.select(timeout=0.5)
                    if not ready:
                        if process.poll() is not None:
                            break
                        continue
                    chunk = os.read(process.stdout.fileno(), 8192)
                    if not chunk:
                        break
                    pending += chunk
                    while b"\n" in pending:
                        raw, pending = pending.split(b"\n", 1)
                        line = raw.decode("utf-8", errors="replace")
                        if line.startswith(("短链已解析：", "使用主页 URL：")):
                            resolved_line = line
                        lines.append(line)
                        lines = lines[-300:]
                        if "waiting for scan code" in line or "CAPTCHA appeared" in line:
                            progress(
                                XhsCaptureJobStatus.WAITING_FOR_LOGIN,
                                "请在本机打开的小红书窗口扫码登录，或完成页面验证。",
                                profile_url,
                            )
                        elif "Begin get Xiaohongshu creators" in line:
                            progress(
                                XhsCaptureJobStatus.RUNNING,
                                "正在读取笔记和评论。", profile_url,
                            )
            code = process.wait(timeout=5)
            if code != 0:
                # Raw crawler logs may include session tokens. Keep those off the API.
                raise RuntimeError("未能读取主页，请确认链接有效、登录已完成后重试。")
            return "\n".join([resolved_line, *lines])
        finally:
            # The command starts browser/MediaCrawler descendants. Stop the entire
            # group on timeout, shutdown, or exit, rather than leaving them running.
            with suppress(ProcessLookupError):
                os.killpg(process.pid, signal.SIGTERM)
            if process.poll() is None:
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)
            if process.stdout:
                process.stdout.close()

    def run(
        self,
        *,
        job_id: str,
        workspace_id: str,
        profile_url: str,
        note_limit: int,
        include_comments: bool,
        progress: ProgressCallback,
    ) -> XhsCaptureResult:
        mediacrawler_directory = self.settings.xhs_mediacrawler_directory
        capture_root = self.settings.xhs_capture_directory
        if mediacrawler_directory is None or not (mediacrawler_directory / "main.py").is_file():
            raise ValidationError(
                "本机尚未配置 MediaCrawler，暂时不能从主页 URL 自动导入。"
            )
        if capture_root is None:
            raise ValidationError("XHS capture directory is not configured")

        job_directory = capture_root / job_id
        raw_directory = job_directory / "raw"
        package_directory = job_directory / "package"
        job_directory.mkdir(parents=True, exist_ok=True)

        progress(
            XhsCaptureJobStatus.RUNNING,
            "正在打开浏览器；如需登录，请按页面提示扫码。",
            profile_url,
        )
        capture_command = [
            sys.executable,
            str(self.repository_root / "scripts/xhs_mediacrawler_profile_importer.py"),
            profile_url,
            "--limit",
            str(note_limit),
            "--save-data-path",
            str(raw_directory),
            "--mediacrawler-dir",
            str(mediacrawler_directory),
        ]
        if include_comments:
            capture_command.append("--comments")

        capture_output = self._capture(capture_command, profile_url, progress)
        resolved_url = self._resolved_url(capture_output, profile_url)
        progress(
            XhsCaptureJobStatus.PROCESSING,
            "抓取完成，正在整理账号档案、正文、评论和封面。",
            resolved_url,
        )
        export = subprocess.run(
            [
                sys.executable,
                str(self.repository_root / "scripts/export_xhs_import_package.py"),
                "--input",
                str(raw_directory),
                "--output",
                str(package_directory),
                "--code",
                job_id,
            ],
            cwd=self.repository_root,
            capture_output=True,
            text=True,
            timeout=5 * 60,
            check=False,
        )
        if export.returncode != 0:
            detail = (export.stderr or export.stdout or "账号档案整理失败").strip()
            raise RuntimeError(detail[-2_000:])

        profile_path = package_directory / "xhs_creator_profile.json"
        if not profile_path.is_file():
            raise RuntimeError("抓取结果中缺少 xhs_creator_profile.json")
        profile_payload = json.loads(profile_path.read_text(encoding="utf-8"))
        creator = profile_payload.get("creator", {})
        display_name = str(creator.get("displayName") or "小红书账号").strip()
        profile_payload.setdefault("source", {})["profileUrl"] = resolved_url
        profile_payload["source"]["captureNoteLimit"] = note_limit
        self._check_account_identity(workspace_id, profile_payload)
        package_files = [
            XhsPackageFile(
                relative_path=str(path.relative_to(package_directory)),
                filename=path.name,
                media_type=mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                content=path.read_bytes(),
            )
            for path in sorted((package_directory / "images").rglob("*"))
            if path.is_file()
        ]
        imported = self.import_service.import_package(
            workspace_id,
            profile_filename=profile_path.name,
            profile_content=json.dumps(profile_payload, ensure_ascii=False).encode("utf-8"),
            files=package_files,
            name="",
            save_as_new=False,
        )
        return XhsCaptureResult(
            resolved_url=resolved_url,
            imported=imported,
            display_name=display_name,
        )

    def _check_account_identity(self, workspace_id: str, incoming: dict) -> None:
        with self.import_service.input_asset_service.database.read() as connection:
            rows = connection.execute(
                "SELECT text_content FROM source_materials "
                "WHERE workspace_id = ? AND type = 'xhs_creator_profile'",
                (workspace_id,),
            ).fetchall()
        incoming_name = incoming.get("creator", {}).get("displayName")
        incoming_path = urlparse(incoming.get("source", {}).get("profileUrl", "")).path
        for row in rows:
            previous = json.loads(row["text_content"])
            previous_url = previous.get("source", {}).get("profileUrl", "")
            same = (
                urlparse(previous_url).path == incoming_path if previous_url
                else previous.get("creator", {}).get("displayName") == incoming_name
            )
            if not same:
                raise ValidationError("链接属于另一个账号，请先点击“添加账号”再导入。")
            known_ids = {note.get("noteId") for note in incoming.get("notes", [])}
            incoming["notes"].extend(
                note for note in previous.get("notes", [])
                if isinstance(note, dict) and note.get("noteId") not in known_ids
            )

    @staticmethod
    def _resolved_url(output: str, fallback: str) -> str:
        for line in output.splitlines():
            if line.startswith("短链已解析：") or line.startswith("使用主页 URL："):
                return line.split("：", 1)[1].strip()
        return fallback


class XhsCaptureJobService:
    def __init__(
        self,
        database: SQLiteDatabase,
        repository: XhsCaptureJobRepository,
        workspace_repository: WorkspaceRepository,
        workspace_service: WorkspaceService,
        runner: MediaCrawlerXhsCaptureRunner,
    ) -> None:
        self.database = database
        self.repository = repository
        self.workspace_repository = workspace_repository
        self.workspace_service = workspace_service
        self.runner = runner
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="xhs-capture")
        self.futures: dict[str, Future[None]] = {}

    def create(
        self, workspace_id: str, payload: XhsCaptureJobCreate
    ) -> XhsCaptureJobResponse:
        profile_url = self._validate_profile_url(payload.profile_url)
        with self.database.transaction() as connection:
            self.workspace_repository.get(connection, workspace_id)
            active = self.repository.find_active(connection, workspace_id)
            if active is not None:
                return XhsCaptureJobResponse.model_validate(active)
            row = self.repository.create(
                connection,
                workspace_id=workspace_id,
                profile_url=profile_url,
                note_limit=payload.note_limit,
                include_comments=payload.include_comments,
                now=utc_now(),
            )
        future = self.executor.submit(self._execute, row["id"])
        self.futures[row["id"]] = future
        future.add_done_callback(lambda _: self.futures.pop(row["id"], None))
        return XhsCaptureJobResponse.model_validate(row)

    def get(self, job_id: str) -> XhsCaptureJobResponse:
        with self.database.read() as connection:
            row = self.repository.get(connection, job_id)
        return XhsCaptureJobResponse.model_validate(row)

    def list(self, workspace_id: str) -> list[XhsCaptureJobResponse]:
        with self.database.read() as connection:
            self.workspace_repository.get(connection, workspace_id)
            rows = self.repository.list_for_workspace(connection, workspace_id)
        return [XhsCaptureJobResponse.model_validate(row) for row in rows]

    def recover_interrupted(self) -> None:
        with self.database.transaction() as connection:
            self.repository.fail_interrupted(connection, now=utc_now())

    def shutdown(self) -> None:
        if hasattr(self.runner, "shutdown"):
            self.runner.shutdown()
        self.executor.shutdown(wait=False, cancel_futures=True)

    def _execute(self, job_id: str) -> None:
        try:
            job = self.get(job_id)

            def progress(
                status: XhsCaptureJobStatus, message: str, resolved_url: str
            ) -> None:
                with self.database.transaction() as connection:
                    self.repository.transition(
                        connection,
                        job_id=job_id,
                        status=status.value,
                        status_message=message,
                        resolved_url=resolved_url,
                        started=True,
                        now=utc_now(),
                    )

            result = self.runner.run(
                job_id=job.id,
                workspace_id=job.workspace_id,
                profile_url=job.profile_url,
                note_limit=job.note_limit,
                include_comments=job.include_comments,
                progress=progress,
            )
            self._rename_workspace(job.workspace_id, result.display_name)
            with self.database.transaction() as connection:
                self.repository.transition(
                    connection,
                    job_id=job_id,
                    status=XhsCaptureJobStatus.COMPLETED.value,
                    status_message="账号导入完成，可以开始账号诊断。",
                    resolved_url=result.resolved_url,
                    result_input_asset_id=result.imported.input_asset.id,
                    completed=True,
                    now=utc_now(),
                )
        except Exception as error:  # noqa: BLE001 - persisted product failure boundary
            with self.database.transaction() as connection:
                self.repository.transition(
                    connection,
                    job_id=job_id,
                    status=XhsCaptureJobStatus.FAILED.value,
                    status_message="账号导入失败，请根据提示检查后重试。",
                    error=str(error)[:10_000],
                    completed=True,
                    now=utc_now(),
                )
        finally:
            self.futures.pop(job_id, None)

    def _rename_workspace(self, workspace_id: str, display_name: str) -> None:
        if not display_name:
            return
        workspace = self.workspace_service.get(workspace_id)
        self.workspace_service.update(
            workspace_id,
            WorkspaceUpdate(
                name=display_name[:120],
                expected_updated_at=workspace.updated_at,
            ),
        )

    @staticmethod
    def _validate_profile_url(value: str) -> str:
        url = value.strip()
        parsed = urlparse(url)
        host = (parsed.hostname or "").lower()
        is_short_link = host == "xhslink.cn" or host.endswith(".xhslink.cn")
        is_profile = (
            host == "www.xiaohongshu.com"
            and parsed.path.startswith("/user/profile/")
            and len(parsed.path.rstrip("/").split("/")[-1]) > 4
        )
        if parsed.scheme != "https" or not (is_short_link or is_profile):
            raise ValidationError(
                "请输入小红书 https://www.xiaohongshu.com/user/profile/... 主页链接，"
                "或 xhslink.cn 用户主页短链。"
            )
        return url
