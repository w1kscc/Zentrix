"""Frameless main window: custom title bar, sidebar navigation and lazy pages."""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wintypes
import sys

from PySide6.QtCore import QEvent, QPoint, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFrame, QHBoxLayout, QLabel, QMainWindow, QPushButton,
    QStackedWidget, QToolButton, QVBoxLayout, QWidget,
)

from .. import constants, paths, winapi
from ..logger import get_logger
from . import overlays, theme
from .context import AppContext
from .tray import TrayController
from .widgets import (
    BackgroundWidget, Badge, NavButton, Overlay, Toast, brand_pixmap, icon, repolish,
)
from .workers import run_task

log = get_logger("window")

NAV = (
    ("home", "Главная", "home"),
    ("zapret", "Zapret", "bolt"),
    ("happ", "Happ", "globe"),
    ("hiddify", "Hiddify", "shield"),
    ("monitor", "Мониторинг", "activity"),
    ("blockcheck", "Проверки", "target"),
    ("updates", "Обновления", "download"),
    ("settings", "Настройки", "settings"),
)

PAGE_MODULES = {
    "home": ("home", "HomePage"),
    "zapret": ("zapret", "ZapretPage"),
    "happ": ("happ", "HappPage"),
    "hiddify": ("hiddify", "HiddifyPage"),
    "monitor": ("monitor", "MonitorPage"),
    "blockcheck": ("blockcheck", "BlockCheckPage"),
    "updates": ("updates", "UpdatesPage"),
    "settings": ("settings", "SettingsPage"),
}

NAV_GROUPS = ((0, 1, 2, 3), (4, 5), (6, 7))


class StatusDot(QWidget):
    """Small painted activity dot (QLabel glyphs render inconsistently)."""

    def __init__(self, colour: str, parent=None) -> None:
        super().__init__(parent)
        self._colour = colour
        self.setFixedSize(8, 8)

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self._colour))
        painter.drawEllipse(self.rect())
        painter.end()


class TitleBar(QWidget):
    """Draggable caption with brand, live status and window buttons."""

    def __init__(self, palette_obj: theme.Palette, window: "MainWindow", parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("titleBar")
        self.setFixedHeight(46)
        self._palette = palette_obj
        self._window = window
        self._dragging = False
        self._press = QPoint()
        self._origin = QPoint()

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 0, 0)
        layout.setSpacing(10)

        self.logo = QLabel()
        self.logo.setFixedSize(24, 24)
        pixmap = brand_pixmap(24)
        if not pixmap.isNull():
            self.logo.setPixmap(pixmap)
        layout.addWidget(self.logo, 0, Qt.AlignVCenter)

        self.brand = QLabel("ZENTRIX")
        self.brand.setObjectName("brandName")
        layout.addWidget(self.brand, 0, Qt.AlignVCenter)
        self.version = QLabel(f"v{constants.APP_VERSION}")
        self.version.setObjectName("tiny")
        layout.addWidget(self.version, 0, Qt.AlignVCenter)
        layout.addStretch(1)

        self.status_pill = QFrame()
        self.status_pill.setObjectName("statusPill")
        pill_layout = QHBoxLayout(self.status_pill)
        pill_layout.setContentsMargins(10, 0, 12, 0)
        pill_layout.setSpacing(6)
        self.status_dot = StatusDot(palette_obj.muted)
        pill_layout.addWidget(self.status_dot)
        self.status_text = QLabel("Обход выключен")
        self.status_text.setObjectName("tiny")
        pill_layout.addWidget(self.status_text)
        layout.addWidget(self.status_pill, 0, Qt.AlignVCenter)

        self.min_button = self._window_button("minimize", "min")
        self.max_button = self._window_button("maximize", "max")
        self.close_button = self._window_button("close", "close")
        self.min_button.clicked.connect(window.showMinimized)
        self.max_button.clicked.connect(window.toggle_maximize)
        self.close_button.clicked.connect(window.close)
        self.min_button.setToolTip("Свернуть")
        self.max_button.setToolTip("Развернуть")
        self.close_button.setToolTip("Закрыть")
        for button in (self.min_button, self.max_button, self.close_button):
            layout.addWidget(button)
        layout.addSpacing(0)

        self._status_kind = "muted"
        self.set_palette(palette_obj)

    @staticmethod
    def _window_button(icon_name: str, role: str) -> QToolButton:
        button = QToolButton()
        button.setObjectName("windowButton")
        button.setProperty("role", role)
        button.setFixedSize(46, 46)
        button.setIconSize(QSize(14, 14))
        button.setCursor(Qt.PointingHandCursor)
        return button

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self._palette = palette_obj
        self.min_button.setIcon(icon("minimize", palette_obj.muted, 14))
        self.max_button.setIcon(icon("restore" if self._window.isMaximized() else "maximize",
                                     palette_obj.muted, 14))
        self.close_button.setIcon(icon("close", palette_obj.muted, 14))
        self.brand.setStyleSheet(
            f"color: {palette_obj.text}; font-weight: 700; letter-spacing: 2px;"
        )
        self.status_text.setStyleSheet(
            f"color: {palette_obj.text if self._status_kind == 'ok' else palette_obj.muted};"
        )
        self._paint_status_dot()

    def set_status(self, text: str, kind: str) -> None:
        self._status_kind = kind
        self.status_text.setText(text)
        self.status_text.setStyleSheet(
            f"color: {self._palette.text if kind == 'ok' else self._palette.muted};"
        )
        self._paint_status_dot()

    def _paint_status_dot(self) -> None:
        colour = {
            "ok": self._palette.success,
            "info": self._palette.accent2,
            "warn": self._palette.warning,
        }.get(self._status_kind, self._palette.muted)
        self.status_dot.set_colour(colour)

    def set_maximized(self, value: bool) -> None:
        self.max_button.setIcon(icon("restore" if value else "maximize", self._palette.muted, 14))
        self.max_button.setToolTip("Восстановить" if value else "Развернуть")

    # ------------------------------------------------------------------ drag
    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and not self._window.isMaximized():
            self._dragging = True
            self._press = event.globalPosition().toPoint()
            self._origin = self._window.pos()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._dragging and event.buttons() & Qt.LeftButton:
            delta = event.globalPosition().toPoint() - self._press
            self._window.move(self._origin + delta)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._dragging = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.LeftButton:
            self._window.toggle_maximize()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class MainWindow(QMainWindow):
    def __init__(self, context: AppContext) -> None:
        super().__init__()
        self.ctx = context
        self.ctx.window = self
        self._quitting = False
        self._pages: dict[str, QWidget] = {}
        self._nav_buttons: dict[str, NavButton] = {}
        self._shortcuts: list[QShortcut] = []

        self.setWindowTitle(f"{constants.APP_NAME} {constants.APP_VERSION}")
        self.setWindowIcon(QIcon(str(paths.BRAND_DIR / "zentrix.ico")))
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setMinimumSize(1080, 700)
        self.setMouseTracking(True)

        p = self.ctx.palette
        self.background = BackgroundWidget(p)
        self.setCentralWidget(self.background)
        root = QVBoxLayout(self.background)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.titlebar = TitleBar(p, self)
        root.addWidget(self.titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)

        self.sidebar = QFrame()
        self.sidebar.setObjectName("navArea")
        self.sidebar.setFixedWidth(232)
        side = QVBoxLayout(self.sidebar)
        side.setContentsMargins(12, 14, 12, 12)
        side.setSpacing(4)
        self._nav_group = QButtonGroup(self)
        self._nav_group.setExclusive(True)
        for index, (key, label, icon_name) in enumerate(NAV):
            button = NavButton(label, icon_name, p)
            self._nav_group.addButton(button)
            button.clicked.connect(lambda _=False, k=key: self.navigate(k))
            self._nav_buttons[key] = button
            side.addWidget(button)
            if index in (3, 5):
                side.addSpacing(10)
        side.addStretch(1)

        footer = QFrame()
        footer.setObjectName("sidebarFooter")
        footer_layout = QVBoxLayout(footer)
        footer_layout.setContentsMargins(4, 10, 4, 2)
        footer_layout.setSpacing(6)
        self.footer_badge = Badge("ПОЛЬЗОВАТЕЛЬ", "muted")
        footer_layout.addWidget(self.footer_badge, 0, Qt.AlignLeft)
        self.footer_button = QPushButton("Повысить права")
        self.footer_button.setProperty("variant", "ghost")
        self.footer_button.setCursor(Qt.PointingHandCursor)
        self.footer_button.clicked.connect(self._admin_help)
        footer_layout.addWidget(self.footer_button)
        footer_version = QLabel(f"{constants.APP_VERSION} · {constants.APP_LICENSE}")
        footer_version.setObjectName("tiny")
        footer_layout.addWidget(footer_version)
        side.addWidget(footer)
        body.addWidget(self.sidebar)

        self.stack = QStackedWidget()
        self.stack.setObjectName("pageStack")
        body.addWidget(self.stack, 1)
        root.addLayout(body, 1)

        central = self.background
        self.overlay = Overlay(central)
        self.ctx.overlay = self.overlay
        self.toast = Toast(central)
        self.ctx.toast = self.toast

        self.tray = TrayController(self, self.ctx)
        self.ctx.tray = self.tray

        self.ctx.theme_changed.connect(self._apply_theme)
        for engine in (self.ctx.zapret, self.ctx.happ, self.ctx.hiddify):
            engine.status_changed.connect(self._on_engine_status)

        self._restore_geometry()
        self._install_shortcuts()
        self.ctx.apply_theme()
        self._refresh_footer()
        self._refresh_status()

        last_page = str(self.ctx.settings.get("ui.last_page", "home") or "home")
        if last_page not in self._nav_buttons:
            last_page = "home"
        self.navigate(last_page)
        self.tray.show()

    # --------------------------------------------------------------- geometry
    def _restore_geometry(self) -> None:
        width = int(self.ctx.settings.get("ui.window_width", 1320) or 1320)
        height = int(self.ctx.settings.get("ui.window_height", 860) or 860)
        screen = QApplication.primaryScreen()
        available = screen.availableGeometry() if screen else None
        if available:
            width = min(max(1080, width), available.width())
            height = min(max(700, height), available.height())
        self.resize(width, height)
        if available:
            frame = self.frameGeometry()
            frame.moveCenter(available.center())
            self.move(frame.topLeft())
        if bool(self.ctx.settings.get("ui.maximized", False)):
            self.showMaximized()

    def _save_state(self) -> None:
        geometry = self.normalGeometry() if self.isMaximized() else self.geometry()
        self.ctx.settings.update("ui", {
            "window_width": max(1080, geometry.width()),
            "window_height": max(700, geometry.height()),
            "maximized": self.isMaximized(),
            "last_page": self.ctx.current_page,
        }, save=True)

    # ------------------------------------------------------------- navigation
    def navigate(self, key: str) -> None:
        if key not in self._nav_buttons:
            return
        page = self._pages.get(key)
        if page is None:
            try:
                page = self._create_page(key)
            except Exception as exc:
                log.exception("Не удалось открыть страницу %s", key)
                self.ctx.notify(f"Не удалось открыть страницу: {exc}", "err", "error")
                return
            self._pages[key] = page
            self.ctx.pages[key] = page
            self.stack.addWidget(page)
        previous = self._pages.get(self.ctx.current_page)
        if previous is not None and previous is not page:
            try:
                previous.on_hide()  # type: ignore[attr-defined]
            except Exception:
                log.exception("on_hide страницы %s", self.ctx.current_page)
        self.stack.setCurrentWidget(page)
        self.ctx.current_page = key
        self.ctx.settings.set("ui.last_page", key)
        for name, button in self._nav_buttons.items():
            button.setChecked(name == key)
        try:
            page.on_show()  # type: ignore[attr-defined]
        except Exception:
            log.exception("on_show страницы %s", key)
        self._refresh_status()

    def _create_page(self, key: str) -> QWidget:
        from importlib import import_module

        module_name, class_name = PAGE_MODULES[key]
        package = __package__ or "src.ui"
        module = import_module(f"{package}.pages.{module_name}")
        return getattr(module, class_name)(self.ctx)

    # ------------------------------------------------------------------ window
    def show_window(self) -> None:
        if self.isMinimized():
            self.showNormal()
        else:
            self.show()
        self.raise_()
        self.activateWindow()
        self.background.resume()
        self.tray.refresh()

    def hide_to_tray(self) -> None:
        if not self.tray.is_visible():
            self.request_quit()
            return
        self.hide()
        if bool(self.ctx.settings.get("general.first_tray_hint", True)):
            self.ctx.settings.set("general.first_tray_hint", False)
            self.ctx.notify(
                "Zentrix свёрнут в трей. Двойной клик по иконке вернёт окно.", "info", "tray"
            )
        else:
            self.ctx.notify("Zentrix свёрнут в трей", "info", "tray")

    def show_page(self, key: str) -> None:
        self.show_window()
        self.navigate(key)

    def toggle_maximize(self) -> None:
        if self.isMaximized():
            self.showNormal()
        else:
            self.showMaximized()
        self.titlebar.set_maximized(self.isMaximized())

    def request_quit(self) -> None:
        if self._quitting:
            return
        self._quitting = True
        log.info("Выход из Zentrix")
        self._save_state()
        try:
            self.ctx.shutdown()
        except Exception:
            log.exception("Ошибка при завершении")
        self.tray.hide()
        application = QApplication.instance()
        if application is not None:
            application.quit()

    # --------------------------------------------------------------- shortcuts
    def _install_shortcuts(self) -> None:
        for index, (key, _label, _icon) in enumerate(NAV):
            shortcut = QShortcut(QKeySequence(f"Ctrl+{index + 1}"), self)
            shortcut.activated.connect(lambda k=key: self.navigate(k))
            self._shortcuts.append(shortcut)
        quit_shortcut = QShortcut(QKeySequence("Ctrl+Q"), self)
        quit_shortcut.activated.connect(self.request_quit)
        self._shortcuts.append(quit_shortcut)
        settings_shortcut = QShortcut(QKeySequence("Ctrl+,"), self)
        settings_shortcut.activated.connect(lambda: self.navigate("settings"))
        self._shortcuts.append(settings_shortcut)
        hide_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Z"), self)
        hide_shortcut.activated.connect(self.hide_to_tray)
        self._shortcuts.append(hide_shortcut)

    # ------------------------------------------------------------------- theme
    def _apply_theme(self) -> None:
        p = self.ctx.palette
        self.background.set_palette(p)
        self.titlebar.set_palette(p)
        self.toast.set_palette(p)
        for button in self._nav_buttons.values():
            button.set_palette(p)
        repolish(self.sidebar)
        repolish(self.titlebar)
        self.overlay.card.style().unpolish(self.overlay.card)
        self.overlay.card.style().polish(self.overlay.card)
        self.apply_background()
        self._refresh_footer()
        self._refresh_status()
        self.tray.refresh()

    def apply_background(self) -> None:
        appearance = self.ctx.settings.section("appearance")
        path = str(appearance.get("video_path", "") or "")
        enabled = bool(appearance.get("video_enabled", False)) and bool(path)
        dim = float(appearance.get("video_dim", 0.58) or 0.58)
        muted = bool(appearance.get("video_muted", True))
        self.background.apply_video(enabled, path, dim, muted)

    # ------------------------------------------------------------------ status
    def _on_engine_status(self, _status: str, _message: str) -> None:
        self._refresh_status()

    def _refresh_status(self) -> None:
        zapret = self.ctx.zapret.status == "running"
        proxy = any(engine.status == "running" for engine in (self.ctx.happ, self.ctx.hiddify))
        if zapret and proxy:
            self.titlebar.set_status("Обход и прокси активны", "ok")
        elif zapret:
            self.titlebar.set_status("Zapret активен", "ok")
        elif proxy:
            self.titlebar.set_status("Прокси активен", "info")
        elif any(engine.status in {"starting", "stopping"}
                 for engine in (self.ctx.zapret, self.ctx.happ, self.ctx.hiddify)):
            self.titlebar.set_status("Подключение…", "info")
        else:
            self.titlebar.set_status("Обход выключен", "muted")
        self._refresh_footer()
        if hasattr(self, "tray"):
            self.tray.refresh()

    def _refresh_footer(self) -> None:
        admin = self.ctx.admin()
        self.footer_badge.update_badge("АДМИНИСТРАТОР" if admin else "ПОЛЬЗОВАТЕЛЬ",
                                       "ok" if admin else "muted")
        self.footer_button.setVisible(not admin)

    # ------------------------------------------------------------------ events
    def changeEvent(self, event) -> None:
        if event.type() == QEvent.WindowStateChange:
            self.titlebar.set_maximized(self.isMaximized())
            if self.isMinimized():
                self.background.pause()
            elif self.isVisible():
                self.background.resume()
        super().changeEvent(event)

    def hideEvent(self, event) -> None:
        self.background.pause()
        super().hideEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self.background.resume()
        if self.ctx.palette.is_dark:
            try:
                winapi.set_dark_titlebar(int(self.winId()), True)
            except Exception:
                pass

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, "overlay") and self.overlay.isVisible():
            self.overlay.resize(self.background.size())

    def closeEvent(self, event) -> None:
        if self._quitting:
            self._save_state()
            event.accept()
            return
        if bool(self.ctx.settings.get("general.close_to_tray", True)) and self.tray.is_visible():
            event.ignore()
            self.hide_to_tray()
            return
        event.ignore()
        self.request_quit()

    # ----------------------------------------------------------------- resize
    def nativeEvent(self, event_type, message):
        if sys.platform == "win32" and not self.isMaximized():
            try:
                msg = wintypes.MSG.from_address(int(message))
                if msg.message == 0x0084:  # WM_NCHITTEST
                    x = ctypes.c_short(msg.lParam & 0xFFFF).value
                    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                    pos = self.mapFromGlobal(QPoint(x, y))
                    border = 6
                    left = pos.x() < border
                    right = pos.x() > self.width() - border
                    top = pos.y() < border
                    bottom = pos.y() > self.height() - border
                    if top and left:
                        return True, 13  # HTTOPLEFT
                    if top and right:
                        return True, 14  # HTTOPRIGHT
                    if bottom and left:
                        return True, 16  # HTBOTTOMLEFT
                    if bottom and right:
                        return True, 17  # HTBOTTOMRIGHT
                    if left:
                        return True, 10  # HTLEFT
                    if right:
                        return True, 11  # HTRIGHT
                    if top:
                        return True, 12  # HTTOP
                    if bottom:
                        return True, 15  # HTBOTTOM
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    # ------------------------------------------------------------------ zapret
    def toggle_zapret(self) -> None:
        engine = self.ctx.zapret
        if engine.status == "running":
            run_task(self, engine.stop, on_done=lambda _: self._zapret_done(False),
                     on_error=lambda message: self.ctx.notify(message, "err", "error"))
            return
        if not self.ctx.admin():
            self.show_window()
            self._admin_help()
            return
        if not engine.is_available():
            self.ctx.notify("winws.exe не найден — проверьте папку движка", "err", "error")
            return
        run_task(self, engine.start, on_done=lambda _: self._zapret_done(True),
                 on_error=lambda message: self.ctx.notify(f"Zapret: {message}", "err", "error"))

    def _zapret_done(self, started: bool) -> None:
        self._refresh_status()
        if started and self.ctx.zapret.status == "running":
            self.ctx.notify("Zapret запущен", "ok", "enable")
        elif not started:
            self.ctx.notify("Zapret остановлен", "warn", "disable")

    def _admin_help(self) -> None:
        overlays.confirm(
            self.ctx.overlay, "Права администратора",
            "Zapret использует драйвер WinDivert, а смена DNS изменяет настройки Windows. "
            "Обе операции требуют повышенных прав.<br><br>"
            "Zentrix перезапустится от имени администратора, настройки сохранятся.",
            "Перезапустить", self.ctx.relaunch_admin,
        )
