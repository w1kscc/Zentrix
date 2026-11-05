"""Game Mode: raise the priority of game processes and switch the Windows
power plan to maximum performance. Everything is restored automatically."""

from __future__ import annotations

import ctypes
import re
import subprocess
import threading

from .logger import get_logger

log = get_logger("game-mode")

HIGH_PERFORMANCE_SCHEME = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
PRIORITY_HIGH = 0x00000080


def parse_active_scheme(output: str) -> str:
    """Extract the current power scheme GUID from ``powercfg /getactivescheme``."""
    match = re.search(r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                      r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12})", output)
    return match.group(1).lower() if match else ""


def _run(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(args, capture_output=True, text=True, timeout=20)


def set_process_priority(process, priority: int = PRIORITY_HIGH) -> bool:
    try:
        handle = ctypes.windll.kernel32.OpenProcess(
            0x0200 | 0x0400, False, process.pid)  # PROCESS_SET_INFORMATION | QUERY
        if not handle:
            return False
        try:
            return bool(ctypes.windll.kernel32.SetPriorityClass(handle, priority))
        finally:
            ctypes.windll.kernel32.CloseHandle(handle)
    except Exception:
        return False


class GameMode:
    """Apply/restore the power scheme and game process priorities.

    ``games`` is a list of substrings matched case-insensitively against
    process names (``game_scan`` supplies sensible defaults).
    """

    def __init__(self) -> None:
        self._previous_scheme = ""
        self._touched_pids: list[int] = []
        self._lock = threading.Lock()
        self.active = False

    # ----------------------------------------------------------------- power
    def _switch_power_scheme(self, scheme: str) -> bool:
        try:
            result = _run(["powercfg", "/setactive", scheme])
            return result.returncode == 0
        except Exception as exc:
            log.warning("powercfg /setactive: %s", exc)
            return False

    def _current_scheme(self) -> str:
        try:
            result = _run(["powercfg", "/getactivescheme"])
            return parse_active_scheme(result.stdout or "")
        except Exception:
            return ""

    # -------------------------------------------------------------- priority
    def _boost_processes(self, games: list[str]) -> int:
        try:
            import psutil
        except ImportError:
            return 0
        lowered = [name.casefold() for name in games if name.strip()]
        if not lowered:
            return 0
        boosted = 0
        for process in psutil.process_iter(["pid", "name"]):
            name = str(process.info.get("name", "") or "").casefold()
            if not any(token in name for token in lowered):
                continue
            if set_process_priority(process):
                self._touched_pids.append(process.info["pid"])
                boosted += 1
        return boosted

    def _restore_processes(self) -> None:
        try:
            import psutil
        except ImportError:
            return
        for pid in self._touched_pids:
            try:
                process = psutil.Process(pid)
                process.nice(psutil.NORMAL_PRIORITY_CLASS)
            except Exception:
                pass
        self._touched_pids.clear()

    # ------------------------------------------------------------------- api
    def enable(self, games: list[str]) -> str:
        """Apply Game Mode. Returns a human summary of what was applied."""
        with self._lock:
            if self.active:
                return "Игровой режим уже включён"
            applied = []
            if not self._previous_scheme:
                self._previous_scheme = self._current_scheme()
            if self._switch_power_scheme(HIGH_PERFORMANCE_SCHEME):
                applied.append("план питания «Максимальная производительность»")
            boosted = self._boost_processes(games)
            if boosted:
                applied.append(f"высокий приоритет для {boosted} процесс(ов)")
            self.active = True
            message = "Игровой режим включён: " + (", ".join(applied) if applied
                                                   else "игровые процессы не найдены")
            log.info(message)
            return message

    def disable(self) -> str:
        """Restore the previous power plan and process priorities."""
        with self._lock:
            if not self.active:
                return "Игровой режим не был включён"
            self._restore_processes()
            message = "Игровой режим выключен"
            if self._previous_scheme and self._previous_scheme != HIGH_PERFORMANCE_SCHEME:
                if self._switch_power_scheme(self._previous_scheme):
                    message += ", план питания восстановлен"
            elif self._previous_scheme == HIGH_PERFORMANCE_SCHEME:
                # The user already ran the high-performance plan; fall back to
                # the balanced scheme so "restore" actually changes something.
                self._switch_power_scheme("381b4222-f694-41f0-9685-ff5bb260df2e")
                message += ", план питания сбалансирован"
            self._previous_scheme = ""
            self.active = False
            log.info(message)
            return message


_instance = GameMode()


def instance() -> GameMode:
    return _instance
