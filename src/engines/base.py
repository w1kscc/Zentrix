"""Shared plumbing for every engine wrapper.

All child processes are started with CREATE_NO_WINDOW so the user never sees
a console window. Output is streamed to the UI through Qt signals.
"""

from __future__ import annotations

import os
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from .. import paths, winapi
from ..logger import get_logger

log = get_logger("engine")
ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


class EngineError(RuntimeError):
    def __init__(self, message: str, code: str = "error") -> None:
        super().__init__(message)
        self.code = code


def decode_line(raw: bytes) -> str:
    raw = ANSI_RE.sub("", raw.decode("utf-8", errors="replace")).rstrip("\r\n\x00")
    if "\ufffd" in raw:
        for encoding in ("cp866", "cp1251"):
            try:
                candidate = raw.encode("utf-8", errors="ignore").decode(encoding)
                if "\ufffd" not in candidate:
                    return candidate
            except Exception:
                continue
    return raw


class ProcessSupervisor(QObject):
    """Owns one hidden child process, its reader thread and its exit watcher."""

    line_received = Signal(str)
    exited = Signal(int)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._process: subprocess.Popen | None = None
        self._reader: threading.Thread | None = None
        self._watcher: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

    @property
    def pid(self) -> int:
        process = self._process
        return process.pid if process and process.poll() is None else 0

    @property
    def running(self) -> bool:
        process = self._process
        return bool(process and process.poll() is None)

    def start(self, argv: list[str], cwd: Path, env: dict[str, str] | None = None,
              pid_file: Path | None = None) -> int:
        if self.running:
            raise EngineError("Процесс уже запущен", "already_running")
        creation = winapi.CREATE_NO_WINDOW | winapi.CREATE_NEW_PROCESS_GROUP
        environment = os.environ.copy()
        environment.setdefault("PYTHONIOENCODING", "utf-8")
        if env:
            environment.update(env)
        try:
            process = subprocess.Popen(
                argv,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=creation,
                env=environment,
                bufsize=0,
            )
        except FileNotFoundError as exc:
            raise EngineError(f"Исполняемый файл не найден: {argv[0]}", "missing_binary") from exc
        except OSError as exc:
            raise EngineError(f"Не удалось запустить процесс: {exc}", "spawn_failed") from exc
        with self._lock:
            self._process = process
            self._stop_event.clear()
        if pid_file:
            try:
                pid_file.parent.mkdir(parents=True, exist_ok=True)
                pid_file.write_text(str(process.pid), encoding="utf-8")
            except OSError:
                pass
        self._reader = threading.Thread(target=self._pump, args=(process,), daemon=True,
                                        name=f"reader-{process.pid}")
        self._reader.start()
        self._watcher = threading.Thread(target=self._watch, args=(process,), daemon=True,
                                         name=f"watch-{process.pid}")
        self._watcher.start()
        log.info("Запущен %s (PID %s)", Path(argv[0]).name, process.pid)
        return process.pid

    def _pump(self, process: subprocess.Popen) -> None:
        stream = process.stdout
        if stream is None:
            return
        pending = b""
        try:
            while not self._stop_event.is_set():
                chunk = stream.read(4096)
                if not chunk:
                    break
                pending += chunk
                while b"\n" in pending:
                    raw, pending = pending.split(b"\n", 1)
                    text = decode_line(raw)
                    if text:
                        self.line_received.emit(text)
            if pending:
                text = decode_line(pending)
                if text:
                    self.line_received.emit(text)
        except Exception:
            pass

    def _watch(self, process: subprocess.Popen) -> None:
        code = process.wait()
        with self._lock:
            if self._process is process:
                self._process = None
        for handle in (process.stdout,):
            try:
                if handle:
                    handle.close()
            except Exception:
                pass
        log.info("Процесс PID %s завершился с кодом %s", process.pid, code)
        self.exited.emit(code)

    def stop(self, timeout: float = 6.0) -> None:
        process = self._process
        self._stop_event.set()
        if not process:
            return
        pid = process.pid
        try:
            if process.poll() is None:
                winapi.kill_tree(pid, timeout=timeout)
        finally:
            try:
                process.wait(timeout=timeout)
            except Exception:
                pass
            with self._lock:
                if self._process is process:
                    self._process = None
        log.info("Процесс PID %s остановлен", pid)


@dataclass
class EngineState:
    status: str = "stopped"  # stopped | starting | running | stopping | error | missing
    message: str = ""
    pid: int = 0


class BaseEngine(QObject):
    """Common signal surface used by all engine pages."""

    status_changed = Signal(str, str)  # status, message
    log_line = Signal(str)
    stats_changed = Signal(dict)
    error = Signal(str, str)

    key: str = "base"
    title: str = "Engine"

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self.supervisor = ProcessSupervisor(self)
        self.supervisor.line_received.connect(self.log_line.emit)
        self.supervisor.exited.connect(self._on_exit)
        self._status = "stopped"
        self._message = ""
        self._intentional_stop = False

    # ------------------------------------------------------------------ state
    @property
    def status(self) -> str:
        return self._status

    @property
    def running(self) -> bool:
        return self.supervisor.running

    def _set_status(self, status: str, message: str = "") -> None:
        self._status = status
        self._message = message
        self.status_changed.emit(status, message)

    def _on_exit(self, code: int) -> None:
        if self._intentional_stop:
            self._intentional_stop = False
            self._set_status("stopped", "Остановлено")
            return
        if code == 0:
            self._set_status("stopped", "Процесс завершился")
        else:
            self._set_status("error", f"Процесс завершился с кодом {code}")
            self.error.emit("Процесс завершился", f"Код выхода: {code}")

    # ------------------------------------------------------------- interface
    def start(self) -> None:  # pragma: no cover - overridden
        raise NotImplementedError

    def stop(self) -> None:
        self._intentional_stop = True
        self._set_status("stopping", "Остановка…")
        self.supervisor.stop()
        self._set_status("stopped", "Остановлено")

    def restart(self) -> None:
        threading.Thread(target=self._restart_worker, daemon=True, name="restart").start()

    def _restart_worker(self) -> None:
        self.stop()
        time.sleep(0.6)
        self.start()

    def cleanup(self) -> None:
        try:
            if self.supervisor.running:
                self.supervisor.stop(timeout=3.0)
        except Exception:
            pass

    def state(self) -> EngineState:
        return EngineState(self._status, self._message, self.supervisor.pid)

    def _pid_file(self) -> Path:
        return paths.DATA_DIR / "run" / f"{self.key}.pid"

    def adopt_stale_pid(self) -> None:
        """Kill a process left over from a previous crashed session."""
        pid_file = self._pid_file()
        try:
            if not pid_file.exists():
                return
            pid = int(pid_file.read_text(encoding="utf-8").strip() or 0)
            pid_file.unlink(missing_ok=True)
            if pid and winapi.is_pid_alive(pid):
                log.warning("Найден зависший процесс %s (PID %s), останавливаю", self.key, pid)
                winapi.kill_tree(pid)
        except Exception:
            pass
