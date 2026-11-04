"""Application runtime: IP watch, scenario rules, subscription refresh.

Lives beside the UI (QObject + QTimer) but all network and rule work happens
in background threads via ``run_task``.
"""

from __future__ import annotations

import threading
import time

from PySide6.QtCore import QObject, QTimer, Signal

from .. import ipwatch, rules as rules_lib
from ..check_history import CheckHistory
from ..logger import get_logger
from .workers import run_task

log = get_logger("runtime")

IP_INTERVAL_MS = 5 * 60 * 1000          # exit-IP poll
SUB_CHECK_INTERVAL_MS = 20 * 60 * 1000  # subscription due-date check


class RuntimeMonitor(QObject):
    """Owns the timers that make Zentrix feel alive without user attention."""

    ip_alert = Signal(str)
    rule_fired = Signal(str)  # rule title

    def __init__(self, context: QObject, parent=None) -> None:
        super().__init__(parent or context)
        self.ctx = context
        self._tasks: list = []
        self._last_ip: str | None = None
        self._last_rules_matched: set[str] = set()
        self.history = CheckHistory()

        self._ip_timer = QTimer(self)
        self._ip_timer.setInterval(IP_INTERVAL_MS)
        self._ip_timer.timeout.connect(self.check_ip)

        self._sub_timer = QTimer(self)
        self._sub_timer.setInterval(SUB_CHECK_INTERVAL_MS)
        self._sub_timer.timeout.connect(self.update_subscriptions)

        for engine in (context.zapret, context.happ, context.hiddify):
            engine.status_changed.connect(lambda *_, e=engine: self.run_rules(engine))

    # ------------------------------------------------------------------ start
    def start(self) -> None:
        self._ip_timer.start()
        self._sub_timer.start()
        QTimer.singleShot(40_000, self.check_ip)

    def stop(self) -> None:
        self._ip_timer.stop()
        self._sub_timer.stop()

    # -------------------------------------------------------------- ip police
    def check_ip(self) -> None:
        if not bool(self.ctx.settings.get("network.ip_alert", True)):
            return
        engine = self._active_proxy_engine()
        proxy_url = engine.proxy_url() if engine is not None else None
        run_task(self, ipwatch.fetch_ip, proxy_url, on_done=self._ip_result,
                 on_error=lambda _message: None)

    def _ip_result(self, info) -> None:
        if not info:
            return
        previous = self._last_ip
        if previous is None:
            previous = str(self.ctx.settings.get("network.last_exit_ip", "") or "") or None
        self._last_ip = str(info.get("ip", "")) if isinstance(info, dict) else str(info)
        self.ctx.settings.set("network.last_exit_ip", self._last_ip, save=False)
        self.ctx.settings.schedule_save()
        if ipwatch.ip_changed(previous, self._last_ip):
            message = ipwatch.format_change(previous, self._last_ip)
            self.ip_alert.emit(message)
            self.ctx.notify(message, "warn", None)
            self.run_rules(self._active_proxy_engine(), reason="ip_change")

    def _active_proxy_engine(self):
        for engine in (self.ctx.happ, self.ctx.hiddify):
            if engine.status == "running":
                return engine
        return None

    # ------------------------------------------------------ blockcheck history
    def register_service_results(self, results: list) -> None:
        """Persist check results and evaluate service-conditions rules."""
        try:
            count = self.history.record_batch(results)
            if count:
                last = float(self.history.last_run() or time.time())
                self.ctx.settings.set("network.last_check_run", last, save=False)
                self.ctx.settings.schedule_save()
        except Exception:
            log.exception("Не удалось сохранить историю проверок")
        self.run_rules(None, reason="blockcheck")

    # ------------------------------------------------------- subscription sync
    def update_subscriptions(self) -> None:
        interval_hours = float(self.ctx.settings.get("network.sub_interval_hours", 12) or 12)
        if interval_hours <= 0:
            return
        for engine in (self.ctx.happ, self.ctx.hiddify):
            self._maybe_update(engine, interval_hours, time.time())

    def _maybe_update(self, engine, interval_hours: float, now: float) -> None:
        url = str(self.ctx.settings.get(f"{engine.ns}.subscription", "") or "").strip()
        if not url or not bool(self.ctx.settings.get(f"{engine.ns}.sub_auto", False)):
            return
        if engine.status in {"running", "starting", "stopping"}:
            return  # do not rewrite the profile under a live connection
        last = float(self.ctx.settings.get(f"{engine.ns}.sub_last", 0) or 0)
        if last and now - last < interval_hours * 3600:
            return
        run_task(self, engine.fetch_subscription, url,
                 on_done=lambda count: self._subscription_done(engine, count),
                 on_error=lambda message: log.warning(
                     "Подписка %s: %s", engine.title, message))

    def _subscription_done(self, engine, count: int) -> None:
        self.ctx.settings.set(f"{engine.ns}.sub_last", time.time(), save=False)
        self.ctx.settings.schedule_save()
        self.ctx.notify(f"{engine.title}: подписка обновлена "
                        f"(серверов в профиле: {count})", "ok", "update")

    # ------------------------------------------------------------ scenario rules
    def run_rules(self, _engine=None, reason: str = "") -> None:
        """Evaluate user rules and act on the newly matched ones."""
        try:
            user_rules = rules_lib.rules_from_json(self.ctx.settings.get("network.rules", []))
        except Exception:
            log.exception("Не удалось прочитать правила")
            return
        if not user_rules:
            return
        state = self._state()
        matched = rules_lib.filter_rules(user_rules, state)
        fresh = [rule for rule in matched if rule.id not in self._last_rules_matched]
        self._last_rules_matched = {rule.id for rule in matched}
        for rule in fresh:
            error = rules_lib.validate(rule)
            if error:
                log.warning("Сценарий %s неполон: %s", rule.title, error)
                continue
            self._execute(rule)

    def _state(self) -> dict:
        services: dict[str, str] = {}
        for result in self.ctx.block_results:
            service_id = getattr(result, "id", None)
            service_status = getattr(result, "status", "")
            if service_id and service_status:
                services[service_id] = service_status
        proxy = self._active_proxy_engine()
        return {
            "service_status": services,
            "zapret_status": self.ctx.zapret.status,
            "proxy_status": proxy.status if proxy is not None else "stopped",
        }

    def _execute(self, rule) -> None:
        engine = self.ctx.zapret
        log.info("Сценарий сработал: %s (%s)", rule.title, rule.condition)
        self.rule_fired.emit(rule.title)
        if rule.action == "notify":
            message = rule.value.strip() or f"Сценарий: {rule.title}"
            self.ctx.notify(message, "info", None)
        elif rule.action == "start_zapret":
            if engine.status == "stopped" and self.ctx.admin() and engine.is_available():
                threading.Thread(target=self._safe_engine_call, args=(engine, "start"),
                                 daemon=True, name="rule-zapret-start").start()
        elif rule.action == "stop_zapret":
            if engine.status == "running":
                threading.Thread(target=self._safe_engine_call, args=(engine, "stop"),
                                 daemon=True, name="rule-zapret-stop").start()
        elif rule.action == "set_strategy":
            current = str(self.ctx.settings.get("zapret.strategy", "") or "")
            if current != rule.value:
                self.ctx.settings.set("zapret.strategy", rule.value)
                if engine.status == "stopped":
                    threading.Thread(target=self._safe_engine_call, args=(engine, "start"),
                                     daemon=True, name="rule-zapret-strategy").start()
                else:
                    self.ctx.notify(
                        f"Сценарий выбрал стратегию {rule.value} — перезапустите Zapret",
                        "info", None)

    def _safe_engine_call(self, engine, method: str) -> None:
        try:
            getattr(engine, method)()
            self.ctx.notify(f"Сценарий: Zapret {'запущен' if method == 'start' else 'остановлен'}",
                            "ok" if method == "start" else "warn", None)
        except Exception as exc:
            log.warning("Сценарий не смог %s Zapret: %s", method, exc)
            self.ctx.notify(f"Сценарий: не удалось управлять Zapret ({exc})", "err", None)
