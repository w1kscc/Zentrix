"""Zapret watchdog: keep winws.exe alive, restart up to 3 times."""

from __future__ import annotations

import time

from .logger import get_logger

log = get_logger("watchdog")

MAX_ATTEMPTS = 3
CHECK_INTERVAL = 10  # seconds


def should_restart(should_run: bool, running: bool, failures: int) -> bool:
    """Pure decision: restart if the engine should run but does not, and the
    retry budget (MAX_ATTEMPTS) is not exhausted."""
    return bool(should_run and not running and failures < MAX_ATTEMPTS)


def attempts_left(failures: int) -> int:
    return max(0, MAX_ATTEMPTS - failures)


class WatchdogState:
    """Track consecutive restart attempts with a cool-down between checks."""

    def __init__(self, interval: float = CHECK_INTERVAL) -> None:
        self.failures = 0
        self.interval = interval
        self.last_restart = 0.0

    def register_restart(self, running: bool, now: float | None = None) -> None:
        self.last_restart = time.time() if now is None else now
        if running:
            self.failures = 0
            log.info("Watchdog: Zapret восстановлен")
        else:
            self.failures += 1
            log.warning("Watchdog: перезапуск Zapret не удался (%d/%d)",
                        self.failures, MAX_ATTEMPTS)

    def reset(self) -> None:
        self.failures = 0
