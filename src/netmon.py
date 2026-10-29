"""Background traffic monitor built on psutil + Win32 TCP table."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from PySide6.QtCore import QThread, Signal

from . import winapi
from .logger import get_logger
from .settings_store import settings

log = get_logger("netmon")


@dataclass
class SpeedSample:
    down: float = 0.0
    up: float = 0.0
    total_down: int = 0
    total_up: int = 0
    connections: int = 0

    def as_dict(self) -> dict:
        return {
            "down": self.down,
            "up": self.up,
            "total_down": self.total_down,
            "total_up": self.total_up,
            "connections": self.connections,
        }


def read_interfaces() -> tuple[int, int]:
    received = sent = 0
    for item in winapi.interface_stats():
        received += item.received
        sent += item.sent
    return received, sent


class TrafficMonitor(QThread):
    sampled = Signal(dict)
    connections_ready = Signal(list)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._stop = threading.Event()
        self._interval = 1.0
        self._names: dict[int, tuple[str, float]] = {}
        self._prev_process: dict[int, tuple[int, float]] = {}
        self._total_down = 0
        self._total_up = 0

    def configure(self, interval: float = 1.0, show_connections: bool = True) -> None:
        self._interval = max(0.5, float(interval))
        self._show_connections = show_connections

    _show_connections = True

    def start(self, *args, **kwargs) -> None:  # noqa: D102 - QThread override
        # A stopped monitor keeps its stop flag; clear it so pause/resume works.
        self._stop.clear()
        super().start(*args, **kwargs)

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:  # noqa: D401 - QThread entry point
        last_received, last_sent = read_interfaces()
        last_time = time.monotonic()
        while not self._stop.is_set():
            # Wait on the event so stop() wakes the thread immediately, even
            # when the sampling interval is several seconds.
            if self._stop.wait(max(0.2, self._interval)):
                break
            received, sent = read_interfaces()
            now = time.monotonic()
            elapsed = max(0.2, now - last_time)
            down = max(0, received - last_received) / elapsed
            up = max(0, sent - last_sent) / elapsed
            if received < last_received or sent < last_sent:  # counter reset / adapter change
                down = up = 0
            self._total_down += max(0, received - last_received)
            self._total_up += max(0, sent - last_sent)
            last_received, last_sent, last_time = received, sent, now

            try:
                connections = winapi.tcp_connections()
            except Exception:
                connections = []
            self.sampled.emit(SpeedSample(down, up, self._total_down, self._total_up,
                                          len(connections)).as_dict())
            if self._show_connections:
                try:
                    self.connections_ready.emit(self._build_rows(connections, elapsed))
                except Exception as exc:
                    log.debug("Список соединений: %s", exc)

    def _process_name(self, pid: int) -> str:
        cached = self._names.get(pid)
        if cached and time.monotonic() - cached[1] < 30:
            return cached[0]
        name = winapi.process_name(pid) if pid else "System"
        if len(self._names) > 600:
            self._names.clear()
        self._names[pid] = (name, time.monotonic())
        return name

    def _build_rows(self, connections, elapsed: float) -> list[dict]:
        pids = {connection.pid for connection in connections if connection.pid}
        rates: dict[int, tuple[float, float]] = {}
        for pid in pids:
            counters = winapi.process_io(pid)
            if counters is None:
                continue
            previous = self._prev_process.get(pid)
            down = up = 0.0
            if previous:
                down = max(0, counters.read_bytes - previous[0]) / elapsed
                up = max(0, counters.write_bytes - previous[1]) / elapsed
            rates[pid] = (down, up)
            self._prev_process[pid] = (counters.read_bytes, counters.write_bytes)
        # Drop IO bookkeeping for processes that disconnected.
        for stale in set(self._prev_process) - pids:
            self._prev_process.pop(stale, None)

        rows = []
        for connection in connections:
            down, up = rates.get(connection.pid, (0.0, 0.0))
            rows.append({
                "process": self._process_name(connection.pid),
                "pid": connection.pid,
                "remote": connection.remote,
                "state": connection.state,
                "down": down,
                "up": up,
                "speed": down + up,
            })
        rows.sort(key=lambda row: (-row["speed"], row["process"]))
        return rows[:80]
