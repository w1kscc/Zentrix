"""Check history stored in SQLite (%APPDATA%/Zentrix/cache.db).

Every blocking-check run records one row per service. The 7-day view
aggregates availability per service: share of successful probes per day.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from .logger import get_logger

log = get_logger("history")

SCHEMA = """
CREATE TABLE IF NOT EXISTS check_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    service TEXT NOT NULL,
    status TEXT NOT NULL,
    latency_ms INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_check_results_service_ts
    ON check_results (service, ts);
"""

DAY = 86400.0
GOOD_STATUSES = {"ok"}
_LOCK = threading.Lock()


def _connect(path: Path | None = None) -> sqlite3.Connection:
    connection = sqlite3.connect(str(path or _db_path()), timeout=5.0)
    connection.executescript(SCHEMA)
    return connection


def _db_path() -> Path:
    from . import paths

    return paths.DATA_DIR / "cache.db"


def record_results(results: list, *, path: Path | None = None, now: float | None = None) -> int:
    """Persist a batch of ServiceResult-like objects. Returns rows written."""
    rows = []
    stamp = time.time() if now is None else now
    for item in results:
        service = getattr(item, "id", None) or str(getattr(item, "service", "") or "")
        status = str(getattr(item, "status", "") or "")
        if not service or not status:
            continue
        rows.append((stamp, service, status, int(getattr(item, "latency_ms", 0) or 0)))
    if not rows:
        return 0
    with _LOCK:
        connection = _connect(path)
        try:
            with connection:
                connection.executemany(
                    "INSERT INTO check_results (ts, service, status, latency_ms) "
                    "VALUES (?, ?, ?, ?)", rows,
                )
        finally:
            connection.close()
    return len(rows)


def day_availability(days: int = 7, *, path: Path | None = None, now: float | None = None
                     ) -> dict[str, dict[str, float]]:
    """Per-service availability grouped by ISO date for the last ``days`` days.

    Returns ``{service: {"2026-11-05": 100.0, ...}}``; days without probes are
    absent, the UI treats missing days as "нет данных".
    """
    stamp = time.time() if now is None else now
    since = stamp - days * DAY
    with _LOCK:
        connection = _connect(path)
        try:
            rows = connection.execute(
                "SELECT service, ts, "
                "SUM(CASE WHEN status IN ('ok') THEN 1 ELSE 0 END) AS good, "
                "COUNT(*) AS total "
                "FROM check_results WHERE ts >= ? GROUP BY service, "
                "CAST((ts - ?) / ? AS INTEGER) ORDER BY ts",
                (since, since, DAY),
            ).fetchall()
        finally:
            connection.close()
    result: dict[str, dict[str, float]] = {}
    for service, ts, good, total in rows:
        day = time.strftime("%Y-%m-%d", time.localtime(ts))
        result.setdefault(service, {})[day] = round(100.0 * good / total, 1) if total else 0.0
    return result


def latest_per_service(*, path: Path | None = None) -> dict[str, tuple[str, float]]:
    """Most recent status per service: ``{service: (status, ts)}``."""
    with _LOCK:
        connection = _connect(path)
        try:
            rows = connection.execute(
                "SELECT service, status, ts FROM check_results "
                "WHERE id IN (SELECT MAX(id) FROM check_results GROUP BY service)"
            ).fetchall()
        finally:
            connection.close()
    return {service: (status, ts) for service, status, ts in rows}


def prune(keep_days: int = 30, *, path: Path | None = None, now: float | None = None) -> int:
    """Delete rows older than ``keep_days``. Returns removed row count."""
    stamp = time.time() if now is None else now
    with _LOCK:
        connection = _connect(path)
        try:
            with connection:
                cursor = connection.execute(
                    "DELETE FROM check_results WHERE ts < ?", (stamp - keep_days * DAY,)
                )
                return cursor.rowcount
        finally:
            connection.close()
