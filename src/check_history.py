"""Persistent history of blocking-check results.

Stores one row per service result produced by ``src/blocking_check.py``
(``ServiceResult.as_dict()`` payloads or plain dicts) in a SQLite database so
the "Проверки" page can render availability over time.

Design notes:

* Default storage location follows the ``paths`` module: ``DATA_DIR /
  cache.db`` (the same file the app already uses as its SQLite cache).
* Every public call opens its own short-lived connection with
  ``timeout=5`` so the module is safe to use from multiple threads and never
  keeps a handle open against the rest of the application.
* ``availability()`` semantics: ``ratio = ok / (ok + blocked)`` computed over
  the requested time window. ``unstable`` and ``error`` rows feed ``total``
  but are excluded from the ratio denominator (they are neither an OK nor a
  proven block).
* ``service_timeline()`` returns fixed-size time buckets including empty ones
  as zeros, so a chart can draw gaps.
* No Qt imports here: this module may be used from worker threads and tests.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from . import paths

# Kept in this module (not added to paths.py) per repo ownership rules.
CACHE_DB = paths.DATA_DIR / "cache.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS check_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id TEXT,
    service_name TEXT,
    status TEXT,
    latency_ms INTEGER,
    checked_at REAL
)
"""

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS idx_check_results_service_time "
    "ON check_results (service_id, checked_at)",
    "CREATE INDEX IF NOT EXISTS idx_check_results_time "
    "ON check_results (checked_at)",
)

_SECONDS_PER_DAY = 86400.0


class CheckHistory:
    """Thread-safe persistent store of blocking-check results."""

    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = Path(db_path) if db_path is not None else CACHE_DB
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------
    # Connection helpers
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=5)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
        except sqlite3.DatabaseError:
            # Not every filesystem/backend supports WAL; fall back silently.
            pass
        return conn

    def _init_schema(self) -> None:
        conn = self._connect()
        try:
            with conn:
                conn.execute(_SCHEMA)
                for statement in _INDEXES:
                    conn.execute(statement)
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Writing
    # ------------------------------------------------------------------

    @staticmethod
    def _row_from(item: Any) -> dict[str, Any] | None:
        """Normalise one incoming result (ServiceResult-like or dict)."""
        as_dict = getattr(item, "as_dict", None)
        data = as_dict() if callable(as_dict) else item
        if not isinstance(data, dict):
            return None
        service_id = data.get("id", data.get("service_id"))
        if service_id is None:
            return None
        try:
            latency = int(data.get("latency_ms") or 0)
        except (TypeError, ValueError):
            latency = 0
        checked_at = data.get("checked_at")
        if not isinstance(checked_at, (int, float)) or checked_at <= 0:
            checked_at = time.time()
        return {
            "service_id": str(service_id),
            "service_name": str(data.get("name") or data.get("service_name") or ""),
            "status": str(data.get("status") or "error"),
            "latency_ms": latency,
            "checked_at": float(checked_at),
        }

    def record_batch(self, results: Iterable[Any]) -> int:
        """Store a batch of results in a single transaction.

        Accepts ``ServiceResult`` objects (anything exposing ``as_dict()``)
        or plain dicts. Items without an ``id`` are skipped. Returns the
        number of rows actually stored.
        """
        rows = [row for row in (self._row_from(item) for item in results) if row]
        if not rows:
            return 0
        conn = self._connect()
        try:
            with conn:
                conn.executemany(
                    "INSERT INTO check_results "
                    "(service_id, service_name, status, latency_ms, checked_at) "
                    "VALUES (:service_id, :service_name, :status, :latency_ms, :checked_at)",
                    rows,
                )
        finally:
            conn.close()
        return len(rows)

    # ------------------------------------------------------------------
    # Reading / aggregation
    # ------------------------------------------------------------------

    def availability(
        self,
        service_id: str | None = None,
        days: int = 7,
    ) -> dict[str, dict[str, float]]:
        """Per-service availability over the last ``days`` days.

        Returns ``{service_id: {"ok", "total", "ratio"}}`` (or a single-entry
        mapping when ``service_id`` is given). ``total`` counts every stored
        result (ok, blocked, unstable, error); ``ratio = ok / (ok + blocked)``
        so ``unstable``/``error`` rows neither inflate nor tank the ratio
        when status is merely noise, but still reduce nothing. When
        ``ok + blocked == 0``, ratio is ``0.0``.
        """
        since = time.time() - days * _SECONDS_PER_DAY
        query = (
            "SELECT service_id, status, COUNT(*) AS n FROM check_results "
            "WHERE checked_at >= ?"
        )
        params: list[Any] = [since]
        if service_id is not None:
            query += " AND service_id = ?"
            params.append(service_id)
        query += " GROUP BY service_id, status"

        conn = self._connect()
        try:
            rows = conn.execute(query, params).fetchall()
        finally:
            conn.close()

        # Internal counters keep ok and blocked separate so that unstable and
        # error rows count toward "total" but never enter the ratio denominator.
        counts: dict[str, dict[str, int]] = {}
        for row_service_id, status, count in rows:
            bucket = counts.setdefault(row_service_id, {"ok": 0, "blocked": 0, "other": 0})
            if status == "ok":
                bucket["ok"] += count
            elif status == "blocked":
                bucket["blocked"] += count
            else:
                bucket["other"] += count

        out: dict[str, dict[str, float]] = {}
        for row_service_id, bucket in counts.items():
            ok = bucket["ok"]
            blocked = bucket["blocked"]
            denominator = ok + blocked
            out[row_service_id] = {
                "ok": ok,
                "total": ok + blocked + bucket["other"],
                "ratio": ok / denominator if denominator > 0 else 0.0,
            }
        return out

    def service_timeline(
        self,
        service_id: str,
        days: int = 7,
        buckets: int = 28,
    ) -> list[dict[str, float]]:
        """Aggregate one service's results into ``buckets`` equal time slots.

        Returns ``[{"start", "ok", "blocked", "other"}, ...]`` in chronological
        order. Empty buckets are present as zeros so a chart renders gaps.
        Statuses other than ok/blocked (unstable, error) land in ``other``.
        """
        buckets = max(1, int(buckets))
        now = time.time()
        window = max(1, int(days)) * _SECONDS_PER_DAY
        start = now - window
        span = window / buckets

        counters = [
            {"start": start + index * span, "ok": 0, "blocked": 0, "other": 0}
            for index in range(buckets)
        ]
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT status, checked_at FROM check_results "
                "WHERE service_id = ? AND checked_at >= ? AND checked_at <= ?",
                (service_id, start, now),
            ).fetchall()
        finally:
            conn.close()

        last_index = buckets - 1
        for status, checked_at in rows:
            offset = checked_at - start
            index = int(offset // span)
            index = min(max(index, 0), last_index)
            key = status if status in ("ok", "blocked") else "other"
            counters[index][key] += 1
        return counters

    def last_run(self) -> float | None:
        """Timestamp of the most recent stored check, or ``None`` if empty."""
        conn = self._connect()
        try:
            row = conn.execute("SELECT MAX(checked_at) FROM check_results").fetchone()
        finally:
            conn.close()
        if row is None or row[0] is None:
            return None
        return float(row[0])

    # ------------------------------------------------------------------
    # Maintenance
    # ------------------------------------------------------------------

    def purge(self, keep_days: int = 90) -> int:
        """Delete rows older than ``keep_days``; returns deleted row count.

        Cheap thanks to the ``(checked_at)`` index; call opportunistically
        (e.g. on app start).
        """
        cutoff = time.time() - keep_days * _SECONDS_PER_DAY
        conn = self._connect()
        try:
            with conn:
                cursor = conn.execute(
                    "DELETE FROM check_results WHERE checked_at < ?", (cutoff,)
                )
                deleted = cursor.rowcount
        finally:
            conn.close()
        return max(0, deleted)
