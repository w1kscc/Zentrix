"""History store (SQLite cache.db) tests."""

from __future__ import annotations

from dataclasses import dataclass

from src import history


@dataclass
class FakeResult:
    id: str
    name: str
    host: str = ""
    status: str = "ok"
    latency_ms: int = 10


def _write(path, service: str, status: str, ts: float, latency: int = 20):
    history.record_results([FakeResult(id=service, name=service.title(), status=status,
                                       latency_ms=latency)], path=path, now=ts)


def test_record_and_availability(tmp_path):
    now = 1_800_000_000.0
    _write(tmp_path / "cache.db", "youtube", "ok", now - 3600)
    _write(tmp_path / "cache.db", "youtube", "blocked", now - 1800)
    _write(tmp_path / "cache.db", "youtube", "ok", now - 900, latency=40)
    _write(tmp_path / "cache.db", "discord", "ok", now - 900)

    data = history.day_availability(days=7, path=tmp_path / "cache.db", now=now)
    assert data["youtube"]["2027-01-15"] == 66.7  # 2 of 3 probes ok
    assert data["discord"]["2027-01-15"] == 100.0


def test_latest_and_prune(tmp_path):
    now = 1_800_000_000.0
    db = tmp_path / "cache.db"
    _write(db, "youtube", "blocked", now - 100)
    _write(db, "youtube", "ok", now - 10)
    latest = history.latest_per_service(path=db)
    assert latest["youtube"][0] == "ok"

    removed = history.prune(keep_days=1, path=db, now=now)
    assert removed == 0
    removed = history.prune(keep_days=0, path=db, now=now + 20)
    assert removed == 2
    assert history.latest_per_service(path=db) == {}


def test_record_skips_empty(tmp_path):
    db = tmp_path / "cache.db"
    assert history.record_results([], path=db) == 0
    assert history.record_results([FakeResult(id="", name="x")], path=db) == 0
