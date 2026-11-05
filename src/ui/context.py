"""Application context shared by every page."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal

from .. import paths, scenarios as scenarios_mod, watchdog as watchdog_mod, winapi
from ..engines import HappEngine, HiddifyEngine, ZapretEngine
from ..engines.tgws import TgWsProxyEngine
from ..logger import get_logger
from ..settings_store import settings as global_settings
from ..sound_generator import SoundManager
from ..netmon import TrafficMonitor
from . import theme

if TYPE_CHECKING:  # pragma: no cover
    from .main_window import MainWindow

log = get_logger("context")


class AppContext(QObject):
    theme_changed = Signal()
    engines_changed = Signal()

    def __init__(self, app, sound: SoundManager, parent=None) -> None:
        super().__init__(parent)
        if winapi.restore_stale_system_proxy():
            log.warning("Восстановлены системные настройки прокси после аварийного выхода")
        self.app = app
        self.settings = global_settings
        self.sound = sound
        self.window: "MainWindow | None" = None
        self.toast = None
        self.overlay = None
        self.tray = None
        self.block_results = []
        self.current_page = "home"
        self.pages: dict[str, object] = {}
        self._shutdown_done = False
        self._palette = theme.Palette.from_settings(self.settings)
        self._monitor: TrafficMonitor | None = None
        self._theme_timer = QTimer(self)
        self._theme_timer.setSingleShot(True)
        self._theme_timer.setInterval(120)
        self._theme_timer.timeout.connect(self._apply_theme)

        # Level-1 runtime services (watchdog, IP alerts, scenarios, theme).
        self._watchdog_failures = 0
        self._zapret_desired = False
        self._engine_prev_status: dict[str, str] = {}
        self._ipwatch = None
        self._watchdog_timer = QTimer(self)
        self._watchdog_timer.setInterval(watchdog_mod.CHECK_INTERVAL * 1000)
        self._watchdog_timer.timeout.connect(self._watchdog_tick)
        self._scenario_timer = QTimer(self)
        self._scenario_timer.setInterval(15 * 60 * 1000)
        self._scenario_timer.timeout.connect(self._scenario_tick)
        self._scenario_busy = False
        self._subscription_timer = QTimer(self)
        self._subscription_timer.timeout.connect(self._subscriptions_tick)
        self._theme_watch_timer = QTimer(self)
        self._theme_watch_timer.setInterval(3000)
        self._theme_watch_timer.timeout.connect(self._theme_watch_tick)
        self._last_windows_light: bool | None = None
        # BETA free keys: upstream repo refreshes every 1-2 hours; we poll hourly.
        self.free_keys_cache: list = []
        self._freekeys_timer = QTimer(self)
        self._freekeys_timer.setInterval(60 * 60 * 1000)
        self._freekeys_timer.timeout.connect(self._freekeys_tick)
        self._freekeys_busy = False

        self.zapret = ZapretEngine(self)
        self.happ = HappEngine(self)
        self.hiddify = HiddifyEngine(self)
        self.tgws = TgWsProxyEngine(self)
        for engine in (self.zapret, self.happ, self.hiddify):
            threading.Thread(target=engine.adopt_stale_pid, daemon=True,
                             name=f"stale-{engine.key}").start()

        self.settings.subscribe(self._on_setting_changed)
        for engine in (self.zapret, self.happ, self.hiddify):
            engine.status_changed.connect(lambda status, _msg, e=engine:
                                          self._on_engine_transition(e, status))

    # ------------------------------------------------- background services
    def start_services(self) -> None:
        """Start the runtime watchers once the window exists."""
        if bool(self.settings.get("ipwatch.enabled", True)):
            self._start_ipwatch()
        if bool(self.settings.get("watchdog.enabled", True)):
            self._watchdog_timer.start()
        if self.settings.get("scenarios.rules"):
            self._scenario_timer.start()
        self._subscription_timer.start()
        self._reschedule_subscriptions()
        self._theme_watch_timer.start()
        if bool(self.settings.get("freekeys.enabled", False)):
            self._freekeys_timer.start()

    # ------------------------------------------------------------ free keys
    def start_freekeys_refresh(self) -> None:
        """Hourly background refresh of the BETA key list while enabled."""
        self._freekeys_timer.start()

    def stop_freekeys_refresh(self) -> None:
        self._freekeys_timer.stop()

    def _freekeys_tick(self) -> None:
        """Refresh cached free nodes from the curated repo (background)."""
        from .workers import run_task

        if self._freekeys_busy or not bool(self.settings.get("freekeys.enabled", False)):
            return
        self._freekeys_busy = True
        categories = self.settings.get("freekeys.categories", []) or ["black_vless"]
        schemes = self.settings.get("freekeys.schemes", ["vless"]) or ["vless"]

        def _search():
            from .. import free_keys
            nodes = free_keys.search(categories=categories, schemes=schemes)
            free_keys.probe_nodes(nodes)
            return nodes

        def _done(nodes):
            self._freekeys_busy = False
            old_count = len(self.free_keys_cache)
            self.free_keys_cache = nodes
            if nodes:
                self.notify(f"Бесплатные ключи обновлены: найдено {len(nodes)} "
                            f"(было {old_count}). Добавление — вручную на вкладке VPN.",
                            "info")
            else:
                self.notify("Обновление бесплатных ключей: ничего не найдено", "warn")

        run_task(self, _search, on_done=_done,
                 on_error=lambda _message: setattr(self, "_freekeys_busy", False))

    def _start_ipwatch(self) -> None:
        from .. import ipwatch

        if self._ipwatch is None:
            self._ipwatch = ipwatch.IpWatcher(self._on_ip_event)
            self._ipwatch.start()

    def _stop_ipwatch(self) -> None:
        if self._ipwatch is not None:
            self._ipwatch.stop()
            self._ipwatch = None

    def _on_ip_event(self, kind: str, message: str) -> None:
        if kind == "changed":
            self.notify(message, "warn")
            self._dispatch_scenario("ip_changed", zapret_running=self.zapret.status == "running")
        elif kind == "error":
            log.debug("ipwatch: %s", message)

    def _on_engine_transition(self, engine, status: str) -> None:
        previous = self._engine_prev_status.get(engine.key, "")
        self._engine_prev_status[engine.key] = status
        if engine.key == "zapret":
            self._zapret_desired = status in {"running", "starting"}
            if status == "running":
                self._watchdog_failures = 0
        if previous == "running" and status == "stopped" and engine.key in {"happ", "hiddify"}:
            self._dispatch_scenario("vpn_lost", zapret_running=self.zapret.status == "running")

    # ------------------------------------------------------------- watchdog
    def _watchdog_tick(self) -> None:
        """Restart winws.exe if it died while the user wanted it running."""
        engine = self.zapret
        if not watchdog_mod.should_restart(self._zapret_desired, engine.status == "running",
                                           self._watchdog_failures):
            return
        strategy = str(self.settings.get("zapret.strategy", "") or "")
        log.warning("Watchdog: winws.exe пропал, перезапуск (%d/%d)",
                    self._watchdog_failures + 1, watchdog_mod.MAX_ATTEMPTS)

        def _restart() -> bool:
            engine.start_with(strategy)
            return engine.status == "running"

        from .workers import run_task
        run_task(self, _restart,
                 on_done=self._watchdog_restarted,
                 on_error=lambda _message: self._watchdog_restarted(False))

    def _watchdog_restarted(self, running: bool) -> None:
        if running:
            self._watchdog_failures = 0
            self.notify("Watchdog: Zapret перезапущен автоматически", "warn")
        else:
            self._watchdog_failures += 1
            if self._watchdog_failures >= watchdog_mod.MAX_ATTEMPTS:
                self.notify(
                    f"Watchdog: Zapret не удалось перезапустить за {watchdog_mod.MAX_ATTEMPTS} "
                    "попытки — запустите вручную", "err", "error")

    # ------------------------------------------------------------ scenarios
    def _scenario_enabled(self) -> bool:
        return bool(self.settings.get("scenarios.rules"))

    def _dispatch_scenario(self, event: str, zapret_running: bool) -> None:
        if not self._scenario_enabled():
            return
        actions = scenarios_mod.plan_actions(
            event, self.settings.get("scenarios.rules"),
            zapret_running=zapret_running,
            strategy=str(self.settings.get("zapret.strategy", "") or ""),
        )
        for action in actions:
            if action.kind == "notify":
                self.notify(action.message or
                            f"Сценарий: {scenarios_mod.event_label(event)}", "warn")
            elif action.kind == "enable_zapret":
                if winapi.is_admin() and self.zapret.is_available():
                    log.info("Сценарий %s: включаю Zapret", event)
                    import threading
                    threading.Thread(target=self._safe_start, args=(self.zapret,),
                                     daemon=True, name="scenario-zapret").start()
                    self.notify("Сценарий: Zapret включён", "warn")
                else:
                    self.notify("Сценарий: не могу включить Zapret (нет прав или движка)", "err")
            elif action.kind == "switch_strategy":
                if event == "ip_changed":
                    continue  # IP change alone is not a signal to re-probe
                self.notify("Сценарий: подбираю лучшую стратегию…", "warn")
                self.run_best_strategy_async()

    def run_best_strategy_async(self) -> None:
        """Background search_best_strategy; used by scenarios and palette."""
        from ..strategy_check import search_best_strategy
        from .workers import run_task

        def _search():
            return search_best_strategy(self.zapret)

        run_task(self, _search,
                 on_done=lambda report: self._scenario_best_done(report),
                 on_error=lambda message: self.notify(f"Сценарий: {message}", "err"))

    def _scenario_best_done(self, report) -> None:
        if report.best is not None:
            self.notify(f"Сценарий: применена стратегия {report.best.strategy}", "ok")
        else:
            self.notify("Сценарий: рабочую стратегию не нашли", "warn")

    def _scenario_tick(self) -> None:
        """Periodic light probe: youtube + discord, then scenario dispatch."""
        if self._scenario_busy or not self._scenario_enabled():
            return
        self._scenario_busy = True
        from .. import constants, strategy_check

        def _probe():
            services = [s for s in constants.SERVICES if s["id"] in {"youtube", "discord"}]
            return strategy_check.probe_services(services)

        from .workers import run_task

        def _done(results):
            self._scenario_busy = False
            event = scenarios_mod.blocked_event(results)
            if event:
                self._dispatch_scenario(event, zapret_running=self.zapret.status == "running")

        run_task(self, _probe, on_done=_done,
                 on_error=lambda _message: setattr(self, "_scenario_busy", False))

    # --------------------------------------------------------- subscriptions
    def reschedule_subscriptions(self) -> None:
        self._reschedule_subscriptions()

    def _reschedule_subscriptions(self) -> None:
        interval_hours = float(self.settings.get("subscriptions.interval_hours", 12) or 12)
        enabled = bool(self.settings.get("subscriptions.auto_update", False))
        self._subscription_timer.stop()
        if enabled:
            self._subscription_timer.start(max(1, int(interval_hours * 3600 * 1000)))

    def _subscriptions_tick(self) -> None:
        urls = []
        for engine in (self.happ, self.hiddify):
            url = str(self.settings.get(f"{engine.ns}.subscription", "") or "").strip()
            if url:
                urls.append((engine, url))
        if not urls:
            return

        def _refresh():
            import time
            counts = []
            for engine, url in urls:
                counts.append(f"{engine.title}: +{engine.fetch_subscription(url)}")
            self.settings.update("subscriptions", {"last_update": time.time()}, save=True)
            return ", ".join(counts)

        from .workers import run_task
        run_task(self, _refresh,
                 on_done=lambda message: self.notify("Подписки обновлены: " + message, "ok"),
                 on_error=lambda message: self.notify(f"Авто-обновление подписок: {message}",
                                                      "err"))

    # --------------------------------------------------------------- theme
    def _theme_watch_tick(self) -> None:
        if not bool(self.settings.section("appearance").get("auto_theme", False)):
            self._last_windows_light = None
            return
        from . import theme

        current = theme.windows_theme_changed_since(None)
        if current is None:
            return
        if self._last_windows_light is not None and current != self._last_windows_light:
            log.info("Тема Windows изменилась — применяю авто-тему")
            self._apply_theme()
        self._last_windows_light = current

    # ------------------------------------------------------------------ theme
    @property
    def palette(self) -> theme.Palette:
        return self._palette

    def _on_setting_changed(self, section: str) -> None:
        if section == "appearance":
            self._theme_timer.start()
        elif section == "sounds":
            data = self.settings.section("sounds")
            self.sound.configure(
                tone=str(data.get("tone", "soft")),
                volume=int(data.get("volume", 40) or 0),
                enabled=bool(data.get("enabled", True)),
            )

    def apply_theme(self) -> None:
        self._apply_theme()

    def _apply_theme(self) -> None:
        self._palette = theme.Palette.from_settings(self.settings)
        self.app.setStyleSheet(theme.qss(self._palette))
        self.theme_changed.emit()
        for page in self.pages.values():
            handler = getattr(page, "on_theme", None)
            if callable(handler):
                try:
                    handler()
                except Exception:
                    log.exception("on_theme упал")

    # ------------------------------------------------------------------- misc
    def navigate(self, key: str) -> None:
        if self.window:
            self.window.navigate(key)

    def notify(self, message: str, kind: str = "info", sound: str | None = None) -> None:
        if self.toast:
            self.toast.show_message(message, kind)
        # When Zentrix lives in the tray, mirror the message as a system balloon.
        if self.tray and self.window and not self.window.isVisible():
            try:
                self.tray.notify(message, kind)
            except Exception:
                pass
        if sound:
            self.sound.play(sound)

    def admin(self) -> bool:
        return winapi.is_admin()

    def relaunch_admin(self) -> None:
        if winapi.relaunch_as_admin(["--keep-running"]):
            self.notify("Перезапуск с правами администратора…", "info")
            QTimer.singleShot(400, self.shutdown)

    @property
    def monitor(self) -> TrafficMonitor:
        if self._monitor is None:
            self._monitor = TrafficMonitor(self)
        return self._monitor

    def start_monitor(self, show_connections: bool = True) -> TrafficMonitor:
        monitor = self.monitor
        monitor.configure(
            interval=float(self.settings.get("monitor.interval", 1.0) or 1.0),
            show_connections=show_connections,
        )
        if not monitor.isRunning():
            monitor.start()
        return monitor

    def stop_monitor(self) -> None:
        if self._monitor and self._monitor.isRunning():
            self._monitor.stop()
            self._monitor.wait(1500)

    def reset_monitor(self) -> None:
        if self._monitor:
            self._monitor._total_down = 0  # noqa: SLF001 - intentional reset
            self._monitor._total_up = 0
            self._monitor._prev_process.clear()

    # ---------------------------------------------------------------- startup
    def autostart_engines(self) -> None:
        """Start engines flagged for autostart, in the background."""
        if self.settings.get("zapret.autostart", False):
            if winapi.is_admin() and self.zapret.is_available():
                threading.Thread(target=self._safe_start, args=(self.zapret,), daemon=True).start()
            else:
                log.info("Автозапуск Zapret пропущен: нет прав или движка")
        engine = self.hiddify if self.settings.get("vpn.core", "xray") == "singbox" else self.happ
        if self.settings.get(f"{engine.ns}.autostart", False) and engine.core_installed():
            threading.Thread(target=self._safe_start, args=(engine,), daemon=True).start()
        if (self.settings.get("tgws.autostart", False)
                and self.settings.get("tgws.enabled", False) and self.tgws.is_available()):
            threading.Thread(target=self._safe_start, args=(self.tgws,), daemon=True).start()

    @staticmethod
    def _safe_start(engine) -> None:
        try:
            engine.start()
        except Exception as exc:
            log.warning("Автозапуск %s: %s", engine.key, exc)

    # --------------------------------------------------------------- shutdown
    def shutdown(self) -> None:
        if self._shutdown_done:
            return
        self._shutdown_done = True
        log.info("Завершение работы Zentrix")
        self._stop_ipwatch()
        for timer in (self._watchdog_timer, self._scenario_timer,
                      self._subscription_timer, self._theme_watch_timer,
                      self._freekeys_timer):
            timer.stop()
        try:
            self.stop_monitor()
        except Exception:
            pass
        for engine in (self.zapret, self.happ, self.hiddify, self.tgws):
            try:
                engine.cleanup()
            except Exception:
                pass
        self.settings.save()
