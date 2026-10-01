from __future__ import annotations

import ast
import json
import mimetypes
import os
import re
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
    XhsCaptureProgress,
    XhsOfflineImportPackageResponse,
)
from app.repositories.workspaces import WorkspaceRepository
from app.repositories.xhs_capture_jobs import XhsCaptureJobRepository
from app.services.common import utc_now
from app.services.workspaces import WorkspaceService
from app.services.xhs_imports import XhsOfflineImportService, XhsPackageFile

ProgressCallback = Callable[
    [XhsCaptureJobStatus, str, str, XhsCaptureProgress | None], None
]


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
        self,
        command: list[str],
        profile_url: str,
        progress: ProgressCallback,
        raw_directory: Path | None = None,
    ) -> str:
        """Read real crawler progress; keep browser descendants within the job lifetime."""
        lines: list[str] = []
        resolved_line = ""
        process = subprocess.Popen(
            command,
            cwd=self.repository_root,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        deadline = time.monotonic() + 20 * 60
        pending = b""
        details = XhsCaptureProgress()
        status = XhsCaptureJobStatus.RUNNING
        message = "正在打开浏览器；如需登录，请按页面提示扫码。"
        last_sample = 0.0
        last_reported: tuple | None = None

        def report() -> None:
            nonlocal last_reported
            current = (status, message, details.model_dump(mode="json"))
            if current == last_reported:
                return
            progress(status, message, profile_url, details.model_copy())
            last_reported = current

        def sample_counts() -> None:
            nonlocal last_sample
            if raw_directory is None or time.monotonic() - last_sample < 1:
                return
            last_sample = time.monotonic()
            notes, comments = self._capture_counts(raw_directory)
            if notes != details.captured_notes or comments != details.captured_comments:
                details.captured_notes = notes
                details.captured_comments = comments
                report()

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
                        sample_counts()
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
                            status = XhsCaptureJobStatus.WAITING_FOR_LOGIN
                            message = "请在本机打开的小红书窗口扫码登录，或完成页面验证。"
                            details.phase = "login"
                            report()
                        elif "Begin get Xiaohongshu creators" in line:
                            status = XhsCaptureJobStatus.RUNNING
                            message = "正在读取笔记。"
                            details.phase = "notes"
                            report()
                        elif "Begin batch get note comments, note list:" in line:
                            sample_counts()
                            details.phase = "comments"
                            details.comment_notes_total = self._comment_note_total(line)
                            message = "笔记读取完成，正在读取评论。"
                            report()
                        elif "after fetching comments for note" in line:
                            details.comment_notes_completed += 1
                            report()
                    sample_counts()
            # The final write may happen just before the child exits.
            if raw_directory is not None:
                details.captured_notes, details.captured_comments = self._capture_counts(
                    raw_directory
                )
                report()
            code = process.wait(timeout=5)
            if code != 0:
                # Raw crawler logs may include session tokens. Only expose known,
                # token-free failure categories to the API.
                raise RuntimeError(self._capture_failure_detail(lines))
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

    @staticmethod
    def _capture_counts(raw_directory: Path) -> tuple[int, int]:
        jsonl = raw_directory / "xhs" / "jsonl"
        counts = []
        for pattern, id_field in (
            ("creator_contents_*.jsonl", "note_id"),
            ("creator_comments_*.jsonl", "comment_id"),
        ):
            seen: set[str] = set()
            for path in jsonl.glob(pattern):
                with path.open("rb") as handle:
                    for raw_line in handle:
                        try:
                            value = json.loads(raw_line.decode("utf-8", errors="replace"))
                        except json.JSONDecodeError:
                            continue  # A writer may still be appending this line.
                        if isinstance(value, dict) and value.get(id_field):
                            seen.add(str(value[id_field]))
            counts.append(len(seen))
        return counts[0], counts[1]

    @staticmethod
    def _comment_note_total(line: str) -> int | None:
        try:
            note_list = ast.literal_eval(line.split("note list:", 1)[1].strip())
        except (ValueError, SyntaxError, IndexError):
            return None
        if not isinstance(note_list, list) or len(note_list) > 1000:
            return None
        return len(note_list) if all(isinstance(item, str) for item in note_list) else None

    @staticmethod
    def _capture_failure_detail(lines: list[str]) -> str:
        output = "\n".join(lines)
        if "Creator homepage state parse failed" in output:
            return (
                "主页已打开，但页面数据格式暂无法解析；本次没有导入笔记。"
                "请保留任务记录供排查，不要连续重试。"
            )
        if "Page.goto" in output and "Timeout" in output:
            return (
                "抓取浏览器打开小红书页面超时。请检查弹出的专用 Chrome 是否能访问网站；"
                "它不复用普通 Chrome 的扩展和登录状态。"
            )
        network_error = re.search(r"net::(ERR_[A-Z_]+)", output)
        if network_error:
            return f"抓取浏览器网络错误（{network_error.group(1)}）；请检查专用 Chrome 的网络连接。"
        return "未能读取主页，请确认链接有效、登录已完成后重试。"

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
            raise ValidationError("本机尚未配置 MediaCrawler，暂时不能从主页 URL 自动导入。")
        if capture_root is None:
            raise ValidationError("XHS capture directory is not configured")

        job_directory = capture_root / job_id
        raw_directory = job_directory / "raw"
        package_directory = job_directory / "package"
        job_directory.mkdir(parents=True, exist_ok=True)

        latest_progress = XhsCaptureProgress()

        def report(
            status: XhsCaptureJobStatus,
            message: str,
            resolved_url: str,
            details: XhsCaptureProgress | None = None,
        ) -> None:
            nonlocal latest_progress
            if details is not None:
                latest_progress = details
            progress(status, message, resolved_url, details)

        report(
            XhsCaptureJobStatus.RUNNING,
            "正在打开浏览器；如需登录，请按页面提示扫码。",
            profile_url,
            latest_progress,
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

        capture_output = self._capture(
            capture_command, profile_url, report, raw_directory
        )
        resolved_url = self._resolved_url(capture_output, profile_url)
        report(
            XhsCaptureJobStatus.PROCESSING,
            "抓取完成，正在整理账号档案、正文、评论和封面。",
            resolved_url,
            latest_progress.model_copy(update={"phase": "processing"}),
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
                urlparse(previous_url).path == incoming_path
                if previous_url
                else previous.get("creator", {}).get("displayName") == incoming_name
            )
            if not same:
                raise ValidationError("链接属于另一个账号，请先点击“添加账号”再导入。")
            known_ids = {note.get("noteId") for note in incoming.get("notes", [])}
            incoming["notes"].extend(
                note
                for note in previous.get("notes", [])
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

    def create(self, workspace_id: str, payload: XhsCaptureJobCreate) -> XhsCaptureJobResponse:
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
        self._schedule(row["id"])
        return XhsCaptureJobResponse.model_validate(row)

    def create_account(self, payload: XhsCaptureJobCreate) -> XhsCaptureJobResponse:
        profile_url = self._validate_profile_url(payload.profile_url)
        with self.database.transaction() as connection:
            # Repeated submission of the same URL reopens its existing import.
            existing = connection.execute(
                "SELECT * FROM xhs_capture_jobs WHERE profile_url = ? "
                "ORDER BY created_at DESC LIMIT 1",
                (profile_url,),
            ).fetchone()
            if existing and existing["status"] != "failed":
                return XhsCaptureJobResponse.model_validate(dict(existing))
            workspace = (
                self.workspace_repository.get(connection, existing["workspace_id"])
                if existing
                else self.workspace_repository.create(
                    connection,
                    name="正在导入的账号",
                    account_positioning="",
                    now=utc_now(),
                )
            )
            row = self.repository.create(
                connection,
                workspace_id=workspace["id"],
                profile_url=profile_url,
                note_limit=payload.note_limit,
                include_comments=payload.include_comments,
                now=utc_now(),
            )
        self._schedule(row["id"])
        return XhsCaptureJobResponse.model_validate(row)

    def _schedule(self, job_id: str) -> None:
        future = self.executor.submit(self._execute, job_id)
        self.futures[job_id] = future
        future.add_done_callback(lambda _: self.futures.pop(job_id, None))

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
                status: XhsCaptureJobStatus,
                message: str,
                resolved_url: str,
                details: XhsCaptureProgress | None = None,
            ) -> None:
                with self.database.transaction() as connection:
                    self.repository.transition(
                        connection,
                        job_id=job_id,
                        status=status.value,
                        status_message=message,
                        resolved_url=resolved_url,
                        progress=(
                            details.model_dump(mode="json", by_alias=True)
                            if details is not None else None
                        ),
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
                previous = self.repository.get(connection, job_id)
                completed_progress = XhsCaptureProgress.model_validate(
                    previous["progress"]
                ).model_copy(update={"phase": "completed"})
                self.repository.transition(
                    connection,
                    job_id=job_id,
                    status=XhsCaptureJobStatus.COMPLETED.value,
                    status_message="账号导入完成，可以开始账号诊断。",
                    resolved_url=result.resolved_url,
                    result_input_asset_id=result.imported.input_asset.id,
                    progress=completed_progress.model_dump(mode="json", by_alias=True),
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
        nickname = display_name.strip()
        if not nickname:
            return
        workspace = self.workspace_service.get(workspace_id)
        # A capture supplies the default name, but must not overwrite a name
        # that the creator has chosen explicitly.
        if workspace.name not in {
            "正在导入的账号",
            "新账号档案",
            nickname,
            f"XHS {nickname} 工作区",
            f"{nickname} 的工作区",
        }:
            return
        name = f"{nickname[: 120 - len(' 的工作区')]} 的工作区"
        if workspace.name == name:
            return
        self.workspace_service.update(
            workspace_id,
            WorkspaceUpdate(
                name=name,
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
