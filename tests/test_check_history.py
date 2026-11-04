"""Tests for src/check_history.py (no Qt involved)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.check_history import CheckHistory


@dataclass
class FakeResult:
    """Mimics blocking_check.ServiceResult just enough for the history API."""

    id: str
    name: str
    status: str = "ok"
    latency_ms: int = 100
    checked_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "status": self.status,
            "latency_ms": self.latency_ms,
            "checked_at": self.checked_at,
        }


@pytest.fixture()
def history(tmp_path: Path) -> CheckHistory:
    return CheckHistory(db_path=tmp_path / "cache.db")


def test_record_batch_with_dicts_and_objects(history: CheckHistory) -> None:
    stored = history.record_batch(
        [
            {"id": "svc1", "name": "Service 1", "status": "ok", "latency_ms": 42},
            {"id": "svc2", "name": "Service 2", "status": "blocked", "latency_ms": 0},
            FakeResult(id="svc1", name="Service 1", status="unstable"),
        ]
    )
    assert stored == 3

    conn = history._connect()
    try:
        rows = conn.execute(
            "SELECT service_id, service_name, status, latency_ms, checked_at "
            "FROM check_results ORDER BY id"
        ).fetchall()
    finally:
        conn.close()

    assert [row[0] for row in rows] == ["svc1", "svc2", "svc1"]
    assert rows[0][1:4] == ("Service 1", "ok", 42)
    assert rows[2][2] == "unstable"
    # checked_at filled in when missing
    assert all(row[4] > 0 for row in rows)


def test_record_batch_skips_invalid_items(history: CheckHistory) -> None:
    assert history.record_batch([{"name": "no id"}, "junk", None]) == 0
    assert history.record_batch([]) == 0
    assert history.last_run() is None


def test_availability_math(history: CheckHistory) -> None:
    now = time.time()
    history.record_batch(
        [
            {"id": "a", "name": "A", "status": "ok", "checked_at": now},
            {"id": "a", "name": "A", "status": "ok", "checked_at": now},
            {"id": "a", "name": "A", "status": "blocked", "checked_at": now},
            # unstable/error count in total but not in the ratio denominator
            {"id": "a", "name": "A", "status": "unstable", "checked_at": now},
            {"id": "a", "name": "A", "status": "error", "checked_at": now},
        ]
    )
    result = history.availability(days=7)
    assert result["a"]["ok"] == 2
    assert result["a"]["total"] == 5
    assert result["a"]["ratio"] == pytest.approx(2 / 3)  # ok / (ok + blocked)


def test_availability_days_window(history: CheckHistory) -> None:
    now = time.time()
    # Place the "old" row well inside the 30-day window (a full 30 days back
    # would race with the tiny drift between test and query timestamps).
    old = now - 29 * 86400.0
    history.record_batch(
        [
            {"id": "a", "name": "A", "status": "ok", "checked_at": now},
            {"id": "a", "name": "A", "status": "blocked", "checked_at": old},
        ]
    )
    # 7-day window only sees the fresh row
    fresh = history.availability(days=7)["a"]
    assert fresh["total"] == 1
    assert fresh["ratio"] == pytest.approx(1.0)
    # 30-day window sees both
    wide = history.availability(days=30)["a"]
    assert wide["total"] == 2
    assert wide["ratio"] == pytest.approx(0.5)
    # Restricting to a single service
    one = history.availability(service_id="a", days=30)
    assert one["a"]["total"] == 2


def test_availability_denominator_zero(history: CheckHistory) -> None:
    now = time.time()
    history.record_batch(
        [{"id": "b", "name": "B", "status": "unstable", "checked_at": now}]
    )
    assert history.availability(days=7)["b"] == {"ok": 0, "total": 1, "ratio": 0.0}


def test_timeline_bucket_boundaries(history: CheckHistory) -> None:
    now = time.time()
    days = 7
    buckets = 7  # one bucket per day for easy assertions
    window = days * 86400.0
    span = window / buckets
    start = now - window

    history.record_batch(
        [
            # inside bucket 0
            {"id": "a", "name": "A", "status": "ok", "checked_at": start + 0.3 * span},
            {"id": "a", "name": "A", "status": "ok", "checked_at": start + 0.7 * span},
            # inside bucket 1
            {"id": "a", "name": "A", "status": "blocked", "checked_at": start + 1.3 * span},
            # boundary crossing: bucket 2, not bucket 1
            {"id": "a", "name": "A", "status": "unstable", "checked_at": start + 2.3 * span},
        ]
    )
    timeline = history.service_timeline("a", days=days, buckets=buckets)
    counts = [{k: v for k, v in bucket.items() if k != "start"} for bucket in timeline]
    assert len(counts) == buckets
    assert counts[0] == {"ok": 2, "blocked": 0, "other": 0}
    assert counts[1] == {"ok": 0, "blocked": 1, "other": 0}
    assert counts[2] == {"ok": 0, "blocked": 0, "other": 1}
    # Empty buckets are zeros so charts draw gaps
    assert counts[3] == {"ok": 0, "blocked": 0, "other": 0}
    # Bucket starts are monotonically increasing and span the whole window
    assert counts[-1] == {"ok": 0, "blocked": 0, "other": 0}
    starts = [bucket["start"] for bucket in timeline]
    assert starts == sorted(starts)
    assert starts[0] == pytest.approx(start, abs=span)


def test_timeline_isolates_services(history: CheckHistory) -> None:
    now = time.time()
    history.record_batch(
        [
            {"id": "a", "name": "A", "status": "ok", "checked_at": now},
            {"id": "b", "name": "B", "status": "blocked", "checked_at": now},
        ]
    )
    timeline_a = history.service_timeline("a", days=7, buckets=4)
    timeline_b = history.service_timeline("b", days=7, buckets=4)
    assert sum(bucket["ok"] for bucket in timeline_a) == 1
    assert sum(bucket["blocked"] for bucket in timeline_a) == 0
    assert sum(bucket["blocked"] for bucket in timeline_b) == 1


def test_last_run(history: CheckHistory) -> None:
    assert history.last_run() is None
    t1 = time.time() - 1000
    t2 = time.time() - 10
    history.record_batch(
        [
            {"id": "a", "name": "A", "status": "ok", "checked_at": t1},
            {"id": "a", "name": "A", "status": "ok", "checked_at": t2},
        ]
    )
    assert history.last_run() == pytest.approx(t2)


def test_purge(history: CheckHistory) -> None:
    now = time.time()
    history.record_batch(
        [
            {"id": "a", "name": "A", "status": "ok", "checked_at": now},
            {"id": "a", "name": "A", "status": "ok", "checked_at": now - 200 * 86400.0},
            {"id": "a", "name": "A", "status": "ok", "checked_at": now - 10 * 86400.0},
        ]
    )
    assert history.purge(keep_days=90) == 1
    assert history.availability(days=400)["a"]["total"] == 2
    # Second purge deletes nothing
    assert history.purge(keep_days=90) == 0


def test_schema_and_reopen(tmp_path: Path) -> None:
    db = tmp_path / "cache.db"
    first = CheckHistory(db_path=db)
    first.record_batch([{"id": "a", "name": "A", "status": "ok"}])
    second = CheckHistory(db_path=db)
    # Schema survives a reopen and no rows are lost
    assert second.availability(days=7)["a"]["ratio"] == pytest.approx(1.0)


def test_no_qt_imports() -> None:
    import src.check_history as module

    assert not any(
        name.startswith("PySide") or name == " QtWidgets" or name == "QtGui"
        for name in vars(module)
        if isinstance(name, str)
    )
    assert "PySide" not in Path(module.__file__).read_text(encoding="utf-8")
