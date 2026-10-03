"""Application-owned saved-reader worker, independent of HTTP observers."""
import asyncio
from contextlib import suppress
from typing import Protocol

from app.errors import ConflictError, NotFoundError
from app.models import ModelCallResponse
from app.services.reader_selection import ReaderSelectionInput
from app.services.reader_selection_prompt import (
    MAX_SELECTION_PROMPT_BYTES,
    ReaderSelectionInputTooLarge,
)
from app.services.reader_selections import ReaderSelectionService


class ReaderSelectionProvider(Protocol):
    async def select(self, inputs: ReaderSelectionInput) -> ModelCallResponse: ...


class ReaderSelectionWorker:
    def __init__(
        self, service: ReaderSelectionService, provider: ReaderSelectionProvider | None = None,
        *, poll_interval: float = 0.25, call_timeout: float = 120,
    ):
        self.service = service
        self.provider = provider
        self.poll_interval = poll_interval
        self.call_timeout = call_timeout
        self._task: asyncio.Task | None = None
        self._lock_file = None

    @property
    def available(self) -> bool:
        return self.provider is not None and self._task is not None and not self._task.done()

    def start(self) -> bool:
        if self.available:
            return True
        if self.provider is None:
            return False
        # Local macOS/Linux runner. An OS-held lock releases on process exit, so startup
        # recovery cannot fail another still-running process's claimed recommendations.
        try:
            import fcntl
        except ImportError:
            return False  # No unsafe recovery on an unsupported lock platform.
        database_path = self.service.database.path.resolve()
        lock_path = database_path.with_name(database_path.name + ".reader-selection.lock")
        lock = lock_path.open("a")
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            return False
        self._lock_file = lock
        try:
            self.service.interrupt_running()
            self._task = asyncio.create_task(self._run())
        except BaseException:
            self._lock_file.close()
            self._lock_file = None
            raise
        return True

    async def _run(self):
        while True:
            pending = self.service.pending()
            if not pending:
                await asyncio.sleep(self.poll_interval)
                continue
            for selection in pending:
                await self._execute(selection.workspace_id, selection.id)

    async def _execute(self, workspace_id: str, selection_id: str):
        try:
            claim = self.service.claim(workspace_id, selection_id)
        except NotFoundError:
            return  # Account was removed while waiting.
        if claim is None:
            return
        try:
            assert self.provider is not None
            response = ModelCallResponse.model_validate(await asyncio.wait_for(
                self.provider.select(claim.selection.input_snapshot), timeout=self.call_timeout,
            ))
        except ReaderSelectionInputTooLarge as error:
            with suppress(ConflictError, NotFoundError):
                self.service.fail(
                    workspace_id, selection_id, claim.token, code="input_too_large",
                    model_metadata={"modelCalled": False, "inputBytes": error.actual_bytes,
                                    "inputByteLimit": MAX_SELECTION_PROMPT_BYTES},
                )
        except asyncio.CancelledError:
            with suppress(ConflictError, NotFoundError):
                self.service.fail(workspace_id, selection_id, claim.token, code="interrupted")
            raise
        except Exception:
            # Never persist raw provider exceptions, request headers or credentials.
            with suppress(ConflictError, NotFoundError):
                self.service.fail(workspace_id, selection_id, claim.token, code="model_error")
        else:
            with suppress(ConflictError, NotFoundError):
                self.service.complete(workspace_id, selection_id, claim.token, response.output,
                                      model_metadata=response.model_metadata)

    async def shutdown(self):
        if self._task is not None:
            self._task.cancel()
            try:
                with suppress(asyncio.CancelledError):
                    await self._task
            finally:
                self._task = None
                if self._lock_file is not None:
                    self._lock_file.close()
                    self._lock_file = None
