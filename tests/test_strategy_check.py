"""Strategy verification: probe summarising and engine state restoration."""

from __future__ import annotations

from src import strategy_check
from src.blocking_check import ServiceResult
from src.strategy_check import (
    StrategyReport, rank_reports, search_best_strategy, summarize, verify_strategy,
)


class FakeStrategy:
    def __init__(self, filename: str) -> None:
        self.name = filename.removesuffix(".bat")
        self.filename = filename


class FakeEngine:
    def __init__(self, running: bool = False, active: str = "general.bat") -> None:
        self.running = running
        self.active = active
        self.started: list[str] = []
        self.stopped = 0

    def strategy(self, filename: str | None = None):
        return FakeStrategy(filename or self.active)

    def start_with(self, filename: str) -> None:
        self.started.append(filename)
        self.active = filename
        self.running = True

    def stop(self) -> None:
        self.stopped += 1
        self.running = False


class FakeSettings:
    def __init__(self, value: str = "general.bat") -> None:
        self.value = value
        self.saved: list[str] = []

    def get(self, _key: str, default=None):
        return self.value

    def set(self, _key: str, value, *, save: bool = True) -> None:
        self.value = value
        self.saved.append(value)


def _result(name: str, status: str = "ok") -> ServiceResult:
    return ServiceResult(id=name.lower(), name=name, host=f"{name.lower()}.example",
                         status=status)


def test_verify_strategy_starts_probes_and_stops(monkeypatch) -> None:
    engine = FakeEngine(running=False)
    monkeypatch.setattr(strategy_check, "settings", FakeSettings("general.bat"))
    monkeypatch.setattr(strategy_check, "probe_services",
                        lambda *args, **kwargs: [_result("YouTube")])

    report = verify_strategy(engine, "general.bat", grace=0.5)

    assert report.level == "ok"
    assert report.ok_count == 1
    assert engine.started == ["general.bat"]
    assert engine.stopped == 1
    assert engine.running is False
    assert report.restored is True


def test_verify_strategy_restores_previously_running_strategy(monkeypatch) -> None:
    engine = FakeEngine(running=True, active="general.bat")
    monkeypatch.setattr(strategy_check, "settings", FakeSettings("general.bat"))
    monkeypatch.setattr(strategy_check, "probe_services",
                        lambda *args, **kwargs: [_result("Discord", "blocked")])

    report = verify_strategy(engine, "general (ALT).bat", grace=0.5)

    assert engine.started == ["general (ALT).bat", "general.bat"]
    assert engine.active == "general.bat"
    assert engine.running is True
    assert report.was_running is True
    assert report.restored is True


def test_summarize_reports_partial_and_failed_strategies() -> None:
    assert summarize([])[1] == "err"
    assert summarize([_result("A"), _result("B")])[1] == "ok"
    assert summarize([_result("A"), _result("B", "blocked")])[1] == "warn"
    assert summarize([_result("A", "blocked"), _result("B", "blocked")])[1] == "err"
    assert summarize([_result("A"), _result("B", "unstable")])[1] == "warn"


def _report(filename: str, statuses: list[str], duration: float = 1.0) -> StrategyReport:
    results = [_result(f"S{index}", status) for index, status in enumerate(statuses)]
    verdict, level = summarize(results)
    return StrategyReport(strategy=filename.removesuffix(".bat"), filename=filename,
                          verdict=verdict, level=level, results=results,
                          duration=duration)


def test_rank_reports_prefers_available_then_fewer_unstable() -> None:
    broken = _report("broken.bat", ["blocked", "blocked"])
    partial = _report("partial.bat", ["ok", "blocked"])
    unstable = _report("unstable.bat", ["ok", "unstable"])
    complete = _report("complete.bat", ["ok", "ok"], duration=9.0)

    ranked = rank_reports([broken, partial, complete, unstable])

    assert [item.filename for item in ranked] == [
        "complete.bat", "unstable.bat", "partial.bat", "broken.bat",
    ]


def test_search_best_strategy_selects_and_applies_best(monkeypatch) -> None:
    engine = FakeEngine(running=False)
    fake_settings = FakeSettings("general.bat")
    monkeypatch.setattr(strategy_check, "settings", fake_settings)

    def probe(_services, **_kwargs):
        if engine.active == "best.bat":
            return [_result("YouTube"), _result("Discord")]
        return [_result("YouTube"), _result("Discord", "blocked")]

    monkeypatch.setattr(strategy_check, "probe_services", probe)
    strategies = [FakeStrategy("weak.bat"), FakeStrategy("best.bat")]

    result = search_best_strategy(engine, strategies, grace=0.5)

    assert result.best is not None
    assert result.best.filename == "best.bat"
    assert result.applied == "best.bat"
    assert fake_settings.value == "best.bat"
    assert result.final_running is False
    assert engine.running is False


def test_search_best_strategy_restores_previous_strategy_on_cancel(monkeypatch) -> None:
    engine = FakeEngine(running=True, active="general.bat")
    fake_settings = FakeSettings("general.bat")
    monkeypatch.setattr(strategy_check, "settings", fake_settings)
    monkeypatch.setattr(strategy_check, "probe_services",
                        lambda *args, **kwargs: [_result("YouTube")])
    strategies = [FakeStrategy("one.bat"), FakeStrategy("two.bat")]
    calls = {"count": 0}

    def cancelled() -> bool:
        calls["count"] += 1
        return calls["count"] > 1

    result = search_best_strategy(engine, strategies, grace=0.5, cancelled=cancelled)

    assert result.cancelled is True
    assert result.tested == 1
    assert result.applied == ""
    assert fake_settings.value == "general.bat"
    assert engine.started == ["one.bat", "general.bat"]
    assert engine.running is True


def test_search_best_strategy_restarts_winner_when_it_was_running(monkeypatch) -> None:
    engine = FakeEngine(running=True, active="general.bat")
    fake_settings = FakeSettings("general.bat")
    monkeypatch.setattr(strategy_check, "settings", fake_settings)
    monkeypatch.setattr(strategy_check, "probe_services",
                        lambda *args, **kwargs: [_result("YouTube")])

    result = search_best_strategy(engine, [FakeStrategy("winner.bat")], grace=0.5)

    assert result.best is not None
    assert result.applied == "winner.bat"
    assert result.final_running is True
    assert engine.started == ["winner.bat", "winner.bat"]
    assert engine.active == "winner.bat"
    assert engine.running is True
