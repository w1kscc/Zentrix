"""Game Mode: boost priority of running games and switch the power plan.

Runs a 3-second tick, like the Zapret game-filter watchdog. All heavy work is
tiny (process table + two psutil calls), so it stays on the UI timer.
"""

from __future__ import annotations

import re
import subprocess

from PySide6.QtCore import QObject, QTimer, Signal

from .. import winapi
from ..logger import get_logger
from ..settings_store import settings

log = get_logger("game-mode")

HIGH_PLAN = "SCHEME_MIN"  # powercfg alias: high performance
_GETACTIVE_RE = re.compile(r"([0-9a-fA-F-]{36})")


def _run_powercfg(args: list[str]) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run(
            ["powercfg", *args],
            capture_output=True, text=True, timeout=15,
            creationflags=winapi.CREATE_NO_WINDOW if winapi.IS_WINDOWS else 0,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        log.warning("powercfg завершился ошибкой: %s", exc)
        return None


def _active_plan() -> str:
    result = _run_powercfg(["/getactivescheme"])
    if result and result.returncode == 0:
        match = _GETACTIVE_RE.search(result.stdout)
        return match.group(1) if match else ""
    return ""


def set_high_performance_plan() -> str:
    """Activate the high-performance plan; returns the previous plan GUID."""
    previous = _active_plan()
    result = _run_powercfg(["/setactive", HIGH_PLAN])
    if result is None or result.returncode != 0:
        return ""
    return previous


def restore_plan(guid: str) -> bool:
    if not guid:
        return False
    result = _run_powercfg(["/setactive", guid])
    return bool(result and result.returncode == 0)


def boost_priority(pid: int) -> bool:
    """Raise a process to the HIGH priority class (psutil)."""
    try:
        import psutil

        psutil.Process(pid).nice(psutil.HIGH_PRIORITY_CLASS)
        return True
    except Exception:
        return False


class GameModeMonitor(QObject):
    """Watches the process table for selected games."""

    state_changed = Signal(bool, str)  # active, message

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent or context)
        self.ctx = context
        self._active_pid = 0
        self._game_name = ""
        self._saved_plan = ""
        self._timer = QTimer(self)
        self._timer.setInterval(3000)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    # ------------------------------------------------------------------ state
    @property
    def enabled(self) -> bool:
        return bool(settings.get("games.mode", False))

    @property
    def active(self) -> bool:
        return self._active_pid != 0

    @property
    def saved_plan(self) -> str:
        return self._saved_plan

    def shutdown(self) -> None:
        """Called on app exit: never leave a boosted plan behind."""
        self._power_down_game()

    # -------------------------------------------------------------------- tick
    def _tick(self) -> None:
        try:
            if not self.enabled:
                self._power_down_game()
                return
            exes = {str(item).rsplit("\\", 1)[-1].lower()
                    for item in (settings.get("games.exes") or [])}
            if not exes:
                self._power_down_game()
                return
            processes = winapi.list_processes()
            playing = next((p for p in processes if p.name.lower() in exes), None)
            if playing is None:
                self._power_down_game()
                return
            if playing.pid != self._active_pid:
                self._boost(playing.pid, playing.name)
        except Exception:
            log.exception("Game Mode: сбой тика")

    def _boost(self, pid: int, name: str) -> None:
        self._power_down_game()
        self._saved_plan = set_high_performance_plan()
        ok = boost_priority(pid)
        self._active_pid = pid if ok else 0
        self._game_name = name
        message = (f"Game Mode: {name} — повышен приоритет процесса"
                   + (", план питания: максимальная производительность" if self._saved_plan else ""))
        if not ok and not self._saved_plan:
            message = "Game Mode: не удалось повысить приоритет (нужны права администратора)"
        self.state_changed.emit(ok or bool(self._saved_plan), message)

    def _power_down_game(self) -> None:
        if self._active_pid or self._saved_plan:
            if self._saved_plan:
                if not restore_plan(self._saved_plan):
                    log.warning("Game Mode: не вернуть прежний план питания")
            self._active_pid = 0
            self._game_name = ""
            self._saved_plan = ""
            self.state_changed.emit(False, "Game Mode: игра закрыта — режим выключен")
