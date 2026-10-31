"""Application context shared by every page."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QTimer, Signal

from .. import paths, winapi
from ..engines import HappEngine, HiddifyEngine, ShareProxyEngine, ZapretEngine
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

        self.zapret = ZapretEngine(self)
        self.happ = HappEngine(self)
        self.hiddify = HiddifyEngine(self)
        self.share = ShareProxyEngine(self)
        for engine in (self.zapret, self.happ, self.hiddify, self.share):
            threading.Thread(target=engine.adopt_stale_pid, daemon=True,
                             name=f"stale-{engine.key}").start()

        self.settings.subscribe(self._on_setting_changed)

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
        try:
            self.stop_monitor()
        except Exception:
            pass
        for engine in (self.zapret, self.happ, self.hiddify, self.share):
            try:
                engine.cleanup()
            except Exception:
                pass
        self.settings.save()
