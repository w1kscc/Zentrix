"""System tray integration with a compact control menu."""

from __future__ import annotations

from PySide6.QtCore import QObject
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from .. import constants, paths
from ..logger import get_logger

log = get_logger("tray")


class TrayController(QObject):
    def __init__(self, window, context) -> None:
        super().__init__(window)
        self.window = window
        self.ctx = context
        self.icon = QSystemTrayIcon(self)
        self.menu = QMenu(window)
        self.icon.setContextMenu(self.menu)
        self.icon.activated.connect(self._activated)
        self._build_menu()
        self.refresh()

    # ------------------------------------------------------------------ state
    def is_available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def is_visible(self) -> bool:
        return self.icon.isVisible()

    def show(self) -> None:
        if self.is_available():
            self.icon.show()
        else:
            log.info("Системный трей недоступен")

    def hide(self) -> None:
        self.icon.hide()

    # ------------------------------------------------------------------ menu
    def _build_menu(self) -> None:
        self.menu.clear()
        self.status_action = self.menu.addAction("Обход выключен")
        self.status_action.setEnabled(False)
        self.menu.addSeparator()

        show_action = self.menu.addAction("Показать Zentrix")
        show_action.triggered.connect(self.window.show_window)
        hide_action = self.menu.addAction("Свернуть в трей")
        hide_action.triggered.connect(self.window.hide_to_tray)
        self.engine_action = self.menu.addAction("Включить Zapret")
        self.engine_action.triggered.connect(self.window.toggle_zapret)
        self.menu.addSeparator()

        check_action = self.menu.addAction("Проверить блокировки")
        check_action.triggered.connect(lambda: self.window.show_page("blockcheck"))
        monitor_action = self.menu.addAction("Мониторинг трафика")
        monitor_action.triggered.connect(lambda: self.window.show_page("monitor"))
        updates_action = self.menu.addAction("Обновления")
        updates_action.triggered.connect(lambda: self.window.show_page("updates"))
        settings_action = self.menu.addAction("Настройки")
        settings_action.triggered.connect(lambda: self.window.show_page("settings"))
        self.menu.addSeparator()

        quit_action = self.menu.addAction("Выход")
        quit_action.triggered.connect(self.window.request_quit)

    def _activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.window.show_window()

    # ---------------------------------------------------------------- refresh
    def refresh(self) -> None:
        engines = (self.ctx.zapret, self.ctx.happ, self.ctx.hiddify)
        active = any(engine.status == "running" for engine in engines)
        name = "tray-active" if active else "tray-inactive"
        icon_path = paths.BRAND_DIR / "png" / f"{name}-32.png"
        if icon_path.exists():
            self.icon.setIcon(QIcon(str(icon_path)))
        else:
            self.icon.setIcon(QIcon(str(paths.BRAND_DIR / "zentrix.ico")))
        self.icon.setToolTip(
            f"Zentrix {constants.APP_VERSION} · "
            + ("обход активен" if active else "обход выключен")
        )
        if active:
            names = ", ".join(engine.title for engine in engines if engine.status == "running")
            self.status_action.setText(f"Активно: {names}")
        else:
            self.status_action.setText("Обход выключен")
        if self.ctx.zapret.status == "running":
            self.engine_action.setText("Остановить Zapret")
        elif self.ctx.zapret.status in {"starting", "stopping"}:
            self.engine_action.setText("Zapret: подождите…")
        else:
            self.engine_action.setText("Включить Zapret")

    def notify(self, message: str, kind: str = "info") -> None:
        if not self.icon.isVisible():
            return
        icon_type = {
            "ok": QSystemTrayIcon.Information,
            "err": QSystemTrayIcon.Critical,
            "warn": QSystemTrayIcon.Warning,
        }.get(kind, QSystemTrayIcon.Information)
        try:
            self.icon.showMessage("Zentrix", message, icon_type, 3500)
        except Exception:
            pass
