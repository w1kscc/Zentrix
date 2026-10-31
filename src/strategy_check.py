"""Temporary Zapret strategy validation.

A strategy is only useful if traffic actually passes through the DPI bypass.
This module starts a strategy (or reuses the running one), probes a handful of
services, and then restores the previous engine state.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from . import constants
from .blocking_check import ServiceResult, check_service
from .logger import get_logger
from .settings_store import settings

log = get_logger("strategy-check")

# A short, representative set: one QUIC, one UDP/STUN and two TLS targets.
VERIFY_SERVICE_IDS = ("youtube", "discord", "telegram", "github")
SEARCH_SERVICE_IDS = ("youtube", "discord", "telegram")
STARTUP_GRACE = 2.5
PROBE_TIMEOUT = 6.0
SEARCH_GRACE = 1.2
SEARCH_PROBE_TIMEOUT = 3.5
SEARCH_TCP_TIMEOUT = 3.0


@dataclass
class StrategyReport:
    strategy: str = ""
    filename: str = ""
    verdict: str = ""
    level: str = "warn"  # ok | warn | err
    results: list[ServiceResult] = field(default_factory=list)
    error: str = ""
    was_running: bool = False
    restored: bool = True
    duration: float = 0.0

    @property
    def ok_count(self) -> int:
        return sum(1 for item in self.results if item.status == "ok")

    @property
    def total(self) -> int:
        return len(self.results)


def services_by_ids(ids: tuple[str, ...]) -> list[dict]:
    by_id = {service["id"]: service for service in constants.SERVICES}
    return [by_id[service_id] for service_id in ids if service_id in by_id]


def verification_services() -> list[dict]:
    return services_by_ids(VERIFY_SERVICE_IDS)


def probe_services(services: list[dict] | None = None,
                   tls_timeout: float = PROBE_TIMEOUT,
                   tcp_timeout: float = 4.0) -> list[ServiceResult]:
    """Probe services concurrently and return results in the requested order."""
    items = list(services) if services is not None else verification_services()
    results: list[ServiceResult] = []
    if not items:
        return results
    with ThreadPoolExecutor(max_workers=min(4, len(items))) as pool:
        futures = {
            pool.submit(check_service, service, tls_timeout=tls_timeout,
                        tcp_timeout=tcp_timeout): service
            for service in items
        }
        for future in as_completed(futures):
            service = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # pragma: no cover - defensive
                results.append(ServiceResult(
                    id=service["id"], name=service["name"], host=service["host"],
                    status="error", reason="Ошибка проверки", detail=str(exc),
                ))
    order = {service["id"]: index for index, service in enumerate(items)}
    results.sort(key=lambda item: order.get(item.id, 99))
    return results


def summarize(results: list[ServiceResult]) -> tuple[str, str]:
    """Return a human verdict and a UI level for a set of probe results.

    A completed TLS handshake is the primary signal that the DPI bypass
    works: fake-TLS strategies intentionally slow the handshake down, so a
    slow-but-successful connection must not fail the verdict.
    """
    total = len(results)
    if not total:
        return "Проверка не дала результатов", "err"
    ok = sum(1 for item in results if item.status == "ok")
    unstable = sum(1 for item in results if item.status == "unstable")
    # A completed TLS handshake (or an outright ok status) is what proves the
    # DPI bypass works. DNS-spoofed responses "succeed" against the wrong
    # server, so they must not count.
    opened = sum(1 for item in results
                 if (item.tls_ok or item.status == "ok")
                 and not (item.status == "unstable" and item.reason == "DNS-подмена"))
    if ok == total:
        return f"Все {total} сервисов доступны — стратегия работает", "ok"
    if opened == total:
        return (f"TLS установлен для всех {total} сервисов"
                + (f" (мгновенно {ok})" if ok else "")
                + " — стратегия работает"), "ok"
    if opened and opened + unstable >= max(1, (total + 1) // 2):
        return (f"TLS установлен для {opened} из {total}, нестабильно {unstable} — "
                "стратегия работает частично"), "warn"
    return f"Доступно {ok} из {total} — стратегия не обходит блокировки", "err"


def verify_strategy(engine, filename: str | None = None, *,
                    services: list[dict] | None = None,
                    grace: float = STARTUP_GRACE,
                    restart_after: bool = True) -> StrategyReport:
    """Run ``filename`` briefly, probe services and restore the old state.

    Blocking work: always call this from a worker thread.
    """
    started = time.perf_counter()
    strategy = engine.strategy(filename)
    report = StrategyReport(was_running=engine.running)
    if strategy is None:
        report.error = "Стратегии не найдены — проверьте папку движка"
        report.verdict = report.error
        report.level = "err"
        return report

    report.strategy = strategy.name
    report.filename = strategy.filename
    previous = str(settings.get("zapret.strategy", "") or "") or strategy.filename
    switched = not engine.running or previous != strategy.filename

    try:
        if not engine.running:
            engine.start_with(strategy.filename)
        elif previous != strategy.filename:
            # start_with() refuses to run while another strategy is active.
            engine.stop()
            engine.start_with(strategy.filename)
        time.sleep(max(0.5, float(grace)))
        if not engine.running:
            raise RuntimeError("winws.exe завершился во время проверки")
        report.results = probe_services(services)
        report.verdict, report.level = summarize(report.results)
    except Exception as exc:
        report.error = str(exc) or exc.__class__.__name__
        report.verdict = f"Проверка не удалась: {report.error}"
        report.level = "err"
        log.warning("Проверка стратегии %s: %s", strategy.filename, report.error)
    finally:
        report.restored = not switched
        try:
            if switched:
                if engine.running:
                    engine.stop()
                if report.was_running and restart_after:
                    engine.start_with(previous)
                    report.restored = True
                elif not report.was_running:
                    # The check started the engine; stopping it restores the
                    # original stopped state.
                    report.restored = True
        except Exception as exc:
            log.warning("Не удалось восстановить состояние Zapret: %s", exc)
            report.restored = False
        report.duration = time.perf_counter() - started
    return report


@dataclass
class SearchReport:
    reports: list[StrategyReport] = field(default_factory=list)
    best: StrategyReport | None = None
    total: int = 0
    cancelled: bool = False
    early_stop: bool = False
    was_running: bool = False
    final_running: bool = False
    applied: str = ""
    state_ok: bool = True
    error: str = ""
    duration: float = 0.0

    @property
    def tested(self) -> int:
        return len(self.reports)

    @property
    def usable(self) -> bool:
        return self.best is not None


def _level_rank(level: str) -> int:
    return {"ok": 0, "warn": 1, "err": 2}.get(level, 3)


def _unstable_count(report: StrategyReport) -> int:
    return sum(1 for item in report.results if item.status == "unstable")


def rank_reports(reports: list[StrategyReport]) -> list[StrategyReport]:
    """Order reports from the most to the least useful strategy."""
    return sorted(
        reports,
        key=lambda item: (
            _level_rank(item.level),
            -item.ok_count,
            -_unstable_count(item),
            item.duration,
            item.filename,
        ),
    )


def _is_usable(report: StrategyReport) -> bool:
    # A completed TLS handshake for at least one service = the bypass works.
    # DNS-spoofed "success" is excluded: it talks to the wrong server.
    return (report.total > 0 and report.level in {"ok", "warn"}
            and any((item.tls_ok or item.status == "ok")
                    and not (item.status == "unstable" and item.reason == "DNS-подмена")
                    for item in report.results))


def probe_search(services: list[dict], tls_timeout: float = SEARCH_PROBE_TIMEOUT,
                 tcp_timeout: float = SEARCH_TCP_TIMEOUT) -> list[ServiceResult]:
    """Fast search-mode probe: screen with one service before the rest.

    A strategy that cannot pass the first service is dead weight during the
    search — probing the remaining services would only add seconds per
    failing strategy. Working strategies still get the full probe.
    """
    first = probe_services(services[:1], tls_timeout=tls_timeout, tcp_timeout=tcp_timeout)
    if not first or first[0].status in {"blocked", "error"}:
        return first
    if len(services) > 1:
        return first + probe_services(services[1:], tls_timeout=tls_timeout,
                                      tcp_timeout=tcp_timeout)
    return first


def search_best_strategy(engine, strategies=None, *,
                         services: list[dict] | None = None,
                         grace: float = SEARCH_GRACE,
                         progress=None, cancelled=None,
                         stop_on_ok: bool = True) -> SearchReport:
    """Try strategies, rank the results and apply the best one.

    By default the search stops as soon as a strategy opens every probed
    service (there is nothing better to find); pass ``stop_on_ok=False`` to
    always test the whole list and rank it. ``progress`` is called as
    ``progress(index, total, name)``. ``cancelled`` is a zero-argument
    callable checked before each strategy. Blocking work: always call this
    from a worker thread.
    """
    started = time.perf_counter()
    items = list(strategies) if strategies is not None else engine.strategies()
    result = SearchReport(total=len(items), was_running=engine.running)
    previous = str(settings.get("zapret.strategy", "") or "")
    if not items:
        result.error = "Стратегии не найдены — проверьте папку движка"
        result.state_ok = not engine.running
        return result

    previous = previous or items[0].filename
    probe_list = services if services is not None else services_by_ids(SEARCH_SERVICE_IDS)
    try:
        if engine.running:
            engine.stop()
        for index, strategy in enumerate(items, start=1):
            if cancelled and cancelled():
                result.cancelled = True
                break
            item = StrategyReport(strategy=strategy.name, filename=strategy.filename)
            item_started = time.perf_counter()
            try:
                engine.start_with(strategy.filename)
                time.sleep(max(0.5, float(grace)))
                if not engine.running:
                    raise RuntimeError("winws.exe завершился во время проверки")
                item.results = probe_search(probe_list)
                item.verdict, item.level = summarize(item.results)
            except Exception as exc:
                item.error = str(exc) or exc.__class__.__name__
                item.verdict = f"Проверка не удалась: {item.error}"
                item.level = "err"
                log.warning("Поиск стратегии %s: %s", strategy.filename, item.error)
            finally:
                try:
                    if engine.running:
                        engine.stop()
                except Exception as exc:  # pragma: no cover - defensive
                    log.warning("Не удалось остановить %s: %s", strategy.filename, exc)
                item.duration = time.perf_counter() - item_started
            result.reports.append(item)
            if progress:
                progress(index, len(items), strategy.name)
            if (stop_on_ok and item.level == "ok"
                    and not (cancelled and cancelled())):
                result.early_stop = True
                break
    except Exception as exc:  # pragma: no cover - defensive
        result.error = str(exc) or exc.__class__.__name__
        log.exception("Поиск лучшей стратегии упал")
    finally:
        result.reports = rank_reports(result.reports)
        result.best = next((item for item in result.reports if _is_usable(item)), None)
        try:
            if result.cancelled or result.best is None:
                if result.was_running and previous:
                    engine.start_with(previous)
                elif previous:
                    settings.set("zapret.strategy", previous)
                result.state_ok = True
            else:
                settings.set("zapret.strategy", result.best.filename)
                result.applied = result.best.filename
                if result.was_running:
                    engine.start_with(result.best.filename)
                result.state_ok = True
        except Exception as exc:
            log.warning("Не удалось применить результат поиска: %s", exc)
            result.error = result.error or str(exc)
            result.applied = ""
            result.state_ok = False
            try:
                if engine.running:
                    engine.stop()
                if result.was_running and previous:
                    engine.start_with(previous)
                settings.set("zapret.strategy", previous)
                result.state_ok = True
            except Exception as restore_exc:  # pragma: no cover - defensive
                log.warning("Не удалось восстановить Zapret: %s", restore_exc)
        result.final_running = engine.running
        result.duration = time.perf_counter() - started
    return result
