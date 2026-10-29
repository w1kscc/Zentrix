"""Background task helpers so no blocking work ever touches the UI thread."""

from __future__ import annotations

import traceback
from typing import Any, Callable

from PySide6.QtCore import QThread, Signal

from ..logger import get_logger

log = get_logger("worker")


class Task(QThread):
    """Run ``fn`` in a thread and deliver its result through signals."""

    done = Signal(object)
    failed = Signal(str)
    progress = Signal(int, int)
    progress_text = Signal(str)

    def __init__(self, fn: Callable[..., Any], *args, with_progress: bool = False,
                 parent=None, **kwargs) -> None:
        super().__init__(parent)
        self._fn = fn
        self._args = args
        self._kwargs = kwargs
        self._with_progress = with_progress

    def _report_progress(self, done, total, text: str = "") -> None:
        self.progress.emit(int(done), int(total))
        if text:
            self.progress_text.emit(str(text))

    def run(self) -> None:
        try:
            if self._with_progress:
                result = self._fn(*self._args, progress=self._report_progress, **self._kwargs)
            else:
                result = self._fn(*self._args, **self._kwargs)
            self.done.emit(result)
        except Exception as exc:
            log.exception("Фоновая задача завершилась ошибкой")
            self.failed.emit(str(exc) or exc.__class__.__name__)


def run_task(owner, fn, *args, on_done=None, on_error=None, with_progress=False,
             on_progress=None, on_progress_text=None, **kwargs) -> Task:
    """Start a Task and keep a reference on ``owner`` until it finishes."""
    task = Task(fn, *args, with_progress=with_progress, parent=owner, **kwargs)
    bucket = getattr(owner, "_tasks", None)
    if bucket is None:
        bucket = owner._tasks = []
    bucket.append(task)
    if on_done:
        task.done.connect(on_done)
    if on_error:
        task.failed.connect(on_error)
    if on_progress:
        task.progress.connect(on_progress)
    if on_progress_text:
        task.progress_text.connect(on_progress_text)

    def _cleanup() -> None:
        if task in bucket:
            bucket.remove(task)
        task.deleteLater()

    task.finished.connect(_cleanup)
    task.start()
    return task
