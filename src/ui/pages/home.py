"""Level-1 dashboard: status, one-click fixes and the actions that matter.

Everything here is visible right after launch. Level-3 items (updates,
cleaning, appearance) are small links only — no large blocks.
"""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from .. import theme
from ..workers import run_task
from ..widgets import Badge, GlassCard, PrimaryButton, make_heading, svg_pixmap
from .base_page import Page, page_heading


class StatusOrb(QWidget):
    def __init__(self, palette_obj: theme.Palette, parent=None) -> None:
        super().__init__(parent)
        self._palette = palette_obj
        self._active = False
        self._phase = 0.0
        self.setFixedSize(176, 176)
        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(2600)
        self._anim.setLoopCount(-1)
        self._anim.setEasingCurve(QEasingCurve.Linear)
        self._anim.valueChanged.connect(self._on_phase)

    def _on_phase(self, value) -> None:
        self._phase = float(value)
        if self._active:
            self.update()

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self._palette = palette_obj
        self.update()

    def set_active(self, active: bool) -> None:
        self._active = active
        if active:
            if self._anim.state() != QVariantAnimation.Running:
                self._anim.start()
        else:
            self._anim.stop()
            self._phase = 0.0
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        p = self._palette
        centre = QRectF(0, 0, self.width(), self.height()).center()
        colour = p.accent if self._active else p.muted
        for index, radius in enumerate((82, 64, 46)):
            alpha = (0.10, 0.16, 0.24)[index]
            painter.setPen(QPen(theme.qcolor(colour, alpha), 1))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(centre, radius, radius)
        if self._active:
            pulse = 54 + 28 * self._phase
            painter.setPen(QPen(theme.qcolor(p.accent2, 0.35 * (1 - self._phase)), 1.6))
            painter.drawEllipse(centre, pulse, pulse)
        gradient = QRadialGradient(centre, 52)
        gradient.setColorAt(0.0, theme.qcolor(colour, 0.45))
        gradient.setColorAt(1.0, theme.qcolor(colour, 0.06))
        painter.setBrush(gradient)
        painter.setPen(QPen(theme.qcolor(colour, 0.5), 1.2))
        painter.drawEllipse(centre, 46, 46)
        pixmap = svg_pixmap("shield" if self._active else "shield-off",
                            p.accent if self._active else p.muted, 40)
        painter.drawPixmap(QRectF(centre.x() - 21, centre.y() - 21, 42, 42), pixmap, QRectF(pixmap.rect()))
        painter.end()


class StatusDot(QWidget):
    def __init__(self, colour: str, parent=None) -> None:
        super().__init__(parent)
        self._colour = colour
        self.setFixedSize(10, 10)

    def set_colour(self, colour: str) -> None:
        self._colour = colour
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._colour)
        painter.drawEllipse(self.rect())
        painter.end()


class StatusPill(QFrame):
    """Large on/off indicator for Zapret / VPN."""

    def __init__(self, title: str, palette_obj: theme.Palette, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("homeStatusPill")
        self._palette = palette_obj
        self._on = False
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 10, 14, 10)
        row.setSpacing(10)
        self.dot = StatusDot(palette_obj.muted, self)
        self.dot.setFixedSize(12, 12)
        row.addWidget(self.dot, 0, Qt.AlignVCenter)
        column = QVBoxLayout()
        column.setSpacing(1)
        self.title = QLabel(title)
        self.title.setStyleSheet("font-weight: 700;")
        column.addWidget(self.title)
        self.state = QLabel("Выключен")
        self.state.setObjectName("tiny")
        column.addWidget(self.state)
        row.addLayout(column, 1)

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self._palette = palette_obj
        self.set_state(self._on, self.state.text())

    def set_state(self, on: bool, text: str) -> None:
        self._on = on
        self.dot.set_colour(self._palette.success if on else self._palette.muted)
        self.state.setText(text)
        self.state.setStyleSheet(
            f"color: {self._palette.success if on else self._palette.muted};")
        self.title.setStyleSheet(f"color: {self._palette.text}; font-weight: 700;")


class HomePage(Page):
    key = "home"

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        self._build()
        self._connect()
        self.on_theme()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        p = self.ctx.palette
        self.add(page_heading("Главная", "Всё главное — сразу после запуска"))

        hero = QFrame()
        hero.setObjectName("hero")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(26, 22, 22, 22)
        hero_layout.setSpacing(18)
        left = QVBoxLayout()
        left.setSpacing(10)
        self.hero_badge = Badge("ПРОВЕРКА…", "muted")
        left.addWidget(self.hero_badge, 0, Qt.AlignLeft)
        title = QLabel("Обход блокировок\nпод контролем")
        title.setObjectName("h1")
        left.addWidget(title)
        self.hero_subtitle = QLabel("Zapret выключен · стратегия не выбрана")
        self.hero_subtitle.setObjectName("muted")
        self.hero_subtitle.setWordWrap(True)
        left.addWidget(self.hero_subtitle)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        self.toggle_button = PrimaryButton("Включить обход", "power", p)
        self.toggle_button.clicked.connect(self._toggle_obfuscation)
        buttons.addWidget(self.toggle_button, 0)
        check_button = QPushButton("Проверить блокировки")
        check_button.setIcon(self._icon("target"))
        check_button.setFixedHeight(38)
        check_button.setCursor(Qt.PointingHandCursor)
        check_button.clicked.connect(self._quick_check)
        buttons.addWidget(check_button, 0)
        buttons.addStretch(1)
        left.addLayout(buttons)
        self.admin_notice = QPushButton("Нужны права администратора  →")
        self.admin_notice.setProperty("variant", "ghost")
        self.admin_notice.setCursor(Qt.PointingHandCursor)
        self.admin_notice.clicked.connect(self._admin_help)
        self.admin_notice.hide()
        left.addWidget(self.admin_notice, 0, Qt.AlignLeft)
        left.addStretch(1)
        hero_layout.addLayout(left, 1)
        self.orb = StatusOrb(p)
        hero_layout.addWidget(self.orb, 0, Qt.AlignRight | Qt.AlignVCenter)
        self.add(hero)

        # Level 1: big status + one-click actions.
        top = QHBoxLayout()
        top.setSpacing(14)
        status_card = GlassCard("Статус подключения", "Что работает прямо сейчас", "shield", p)
        pills = QHBoxLayout()
        pills.setSpacing(12)
        self.zapret_pill = StatusPill("Zapret", p)
        self.vpn_pill = StatusPill("VPN", p)
        pills.addWidget(self.zapret_pill, 1)
        pills.addWidget(self.vpn_pill, 1)
        status_card.add_layout(pills)
        top.addWidget(status_card, 3)

        fix_card = GlassCard("Быстрые действия", "Одно нажатие — готово", "bolt", p)
        self.repair_button = QPushButton("Починить сеть")
        self.repair_button.setIcon(self._icon("wrench"))
        self.repair_button.setToolTip("flushdns, сброс Winsock и IP-стека, очистка кэша Zentrix")
        self.repair_button.clicked.connect(self._repair_network)
        fix_card.add(self.repair_button)
        self.game_button = QPushButton("Игровой режим")
        self.game_button.setIcon(self._icon("cpu"))
        self.game_button.setCheckable(True)
        self.game_button.setToolTip("Высокий приоритет игр и план питания «Максимальная производительность»")
        self.game_button.clicked.connect(self._toggle_game_mode)
        fix_card.add(self.game_button)
        top.addWidget(fix_card, 2)
        self.add_layout(top)

        middle = QHBoxLayout()
        middle.setSpacing(14)
        # Quick strategy switch with real measurement.
        strategy_card = GlassCard("Стратегия Zapret", "Быстрое переключение и подбор", "bolt", p)
        self.strategy_combo = QComboBox()
        self.strategy_combo.setMinimumHeight(34)
        self.strategy_combo.currentIndexChanged.connect(self._strategy_changed)
        strategy_card.add(self.strategy_combo)
        best_row = QHBoxLayout()
        self.best_button = QPushButton("Выбрать лучший")
        self.best_button.setIcon(self._icon("target"))
        self.best_button.setToolTip("Поочерёдно проверить стратегии и применить лучшую по реальному замеру")
        self.best_button.clicked.connect(self._pick_best)
        best_row.addWidget(self.best_button, 1)
        self.best_hint = QLabel("Замер по блокчеку сервисов")
        self.best_hint.setObjectName("tiny")
        self.best_hint.setWordWrap(True)
        best_row.addWidget(self.best_hint, 1)
        strategy_card.add_layout(best_row)
        middle.addWidget(strategy_card, 3)

        # External IP with change alerts.
        ip_card = GlassCard("Внешний IP", "Следим за сменой адреса", "globe", p)
        self.ip_badge = Badge("…", "muted")
        ip_card.add_header_widget(self.ip_badge)
        self.ip_value = QLabel("Определяем…")
        self.ip_value.setObjectName("h2")
        ip_card.add(self.ip_value)
        self.ip_place = QLabel("Тост при смене адреса включён")
        self.ip_place.setObjectName("tiny")
        self.ip_place.setWordWrap(True)
        ip_card.add(self.ip_place)
        refresh = QPushButton("Обновить")
        refresh.setProperty("variant", "chip")
        refresh.setCursor(Qt.PointingHandCursor)
        refresh.setFixedHeight(32)
        refresh.clicked.connect(self._refresh_ip)
        ip_card.add(refresh)
        middle.addWidget(ip_card, 2)
        self.add_layout(middle)

        # Level 3: small links only, no big blocks on the dashboard.
        footer = QHBoxLayout()
        footer.setSpacing(8)
        caption = QLabel("Служебное:")
        caption.setObjectName("tiny")
        footer.addWidget(caption)
        for text, target in (
            ("Обновления компонентов", "updates"),
            ("Мониторинг", "monitor"),
            ("Очистка файлов", "settings"),
            ("Сценарии и оформление", "settings"),
        ):
            link = QPushButton(text)
            link.setProperty("variant", "ghost")
            link.setCursor(Qt.PointingHandCursor)
            link.setFixedHeight(28)
            link.clicked.connect(lambda _=False, t=target: self.ctx.navigate(t))
            footer.addWidget(link)
        footer.addStretch(1)
        self.add_layout(footer)
        self.finish()

    def _icon(self, name: str):
        from ..widgets import icon

        return icon(name, self.ctx.palette.accent, 18)

    def _connect(self) -> None:
        for engine in (self.ctx.zapret, self.ctx.happ, self.ctx.hiddify):
            engine.status_changed.connect(lambda *_a: self._refresh_hero())
            engine.log_line.connect(lambda *_: None)

    # ------------------------------------------------------------------- live
    def on_show(self) -> None:
        self._refresh_hero()
        self._load_strategies()
        self._refresh_ip()

    def on_hide(self) -> None:
        pass

    def _game_mode_active(self) -> bool:
        try:
            from ... import game_mode
            return game_mode.instance().active
        except Exception:
            return False

    def _refresh_hero(self) -> None:
        zapret = self.ctx.zapret
        running = zapret.status == "running"
        self.orb.set_active(running)
        self.hero_badge.update_badge("АКТИВНО" if running else "ВЫКЛЮЧЕНО",
                                     "ok" if running else "muted")
        if running:
            strategy = zapret.active_strategy or self.ctx.settings.get("zapret.strategy", "")
            self.hero_subtitle.setText(f"Zapret работает · {strategy} · {zapret._message}")
            self.toggle_button.setText("Остановить обход")
        else:
            strategy = self.ctx.settings.get("zapret.strategy", "general.bat")
            self.hero_subtitle.setText(f"Zapret выключен · выбрана стратегия {strategy}")
            self.toggle_button.setText("Включить обход")
        self.admin_notice.setVisible(not self.ctx.admin())
        self.zapret_pill.set_state(
            running,
            ("Работает · " + (zapret.active_strategy or "стратегия")) if running else "Выключен",
        )
        vpn_engine = (self.ctx.happ if self.ctx.settings.get("vpn.core", "xray") == "xray"
                      else self.ctx.hiddify)
        vpn_running = vpn_engine.status == "running"
        node = vpn_engine.selected_node() if vpn_running else None
        self.vpn_pill.set_state(
            vpn_running,
            (node.summary() if node else "Подключено") if vpn_running else "Выключен",
        )
        self.game_button.setChecked(self._game_mode_active())

    # -------------------------------------------------------------- strategy
    def _load_strategies(self) -> None:
        strategies = self.ctx.zapret.strategies()
        self.strategy_combo.blockSignals(True)
        self.strategy_combo.clear()
        for strategy in strategies:
            self.strategy_combo.addItem(strategy.name, strategy.filename)
        current = str(self.ctx.settings.get("zapret.strategy", "") or "")
        index = self.strategy_combo.findData(current)
        if index >= 0:
            self.strategy_combo.setCurrentIndex(index)
        self.strategy_combo.blockSignals(False)

    def _strategy_changed(self, index: int) -> None:
        filename = self.strategy_combo.itemData(index)
        if not filename:
            return
        self.ctx.settings.set("zapret.strategy", filename)
        self.ctx.notify(f"Стратегия: {self.strategy_combo.itemText(index)}", "info")
        engine = self.ctx.zapret
        if engine.status == "running" and self.ctx.admin():
            run_task(self, lambda: engine.start_with(filename),
                     on_done=lambda _r: self.ctx.notify("Стратегия применена", "ok"),
                     on_error=lambda message: self.ctx.notify(f"Zapret: {message}", "err", "error"))
        self._refresh_hero()

    def _pick_best(self) -> None:
        from ...strategy_check import search_best_strategy

        if not self.ctx.admin():
            self._admin_help()
            return
        self.best_button.setEnabled(False)
        self.best_hint.setText("Проверяю стратегии…")

        def _progress(index, total, name):
            self.best_hint.setText(f"Проверяю {index}/{total}: {name}")

        run_task(self, lambda: search_best_strategy(self.ctx.zapret, progress=_progress),
                 on_done=self._best_done,
                 on_error=self._best_failed)

    def _best_done(self, report) -> None:
        self.best_button.setEnabled(True)
        if report.error:
            self.best_hint.setText(report.error)
        elif report.best is not None:
            self.best_hint.setText(f"Лучше всех: {report.best.strategy} — {report.best.verdict}")
            self.ctx.notify(f"Применена лучшая стратегия: {report.best.strategy}", "ok", "enable")
        else:
            self.best_hint.setText("Рабочую стратегию не нашли")
        self._load_strategies()
        self._refresh_hero()

    def _best_failed(self, message: str) -> None:
        self.best_button.setEnabled(True)
        self.best_hint.setText(f"Ошибка: {message}")

    # ----------------------------------------------------------------- actions
    def _quick_check(self) -> None:
        page = self.ctx.pages.get("blockcheck")
        self.ctx.navigate("blockcheck")
        if page is not None and hasattr(page, "_toggle_run"):
            page._toggle_run()

    def _repair_network(self) -> None:
        from ... import nettools

        if not self.ctx.admin():
            self._admin_help()
            return
        self.repair_button.setEnabled(False)
        self.ctx.notify("Чиню сеть: flushdns → Winsock → сброс IP-стека…", "info")

        run_task(self, lambda: nettools.repair_network(clean_zentrix_cache=True),
                 on_done=self._repair_done,
                 on_error=lambda _message: self._repair_done([]))

    def _repair_done(self, rows) -> None:
        self.repair_button.setEnabled(True)
        if rows:
            failed = [title for _key, title, ok in rows if not ok]
            if failed:
                self.ctx.notify(f"Сеть: не удалось {', '.join(failed)}", "warn", "error")
            else:
                self.ctx.notify("Сеть починена: DNS-кэш, Winsock и IP-стек сброшены", "ok")
        else:
            self.ctx.notify("Не удалось починить сеть", "err", "error")

    def _toggle_game_mode(self, checked: bool) -> None:
        from ... import game_mode

        mode = game_mode.instance()
        if checked:
            games = list(self.ctx.settings.section("gamemode").get("games", [])
                         or ["csgo", "cs2", "valorant", "dota2", "fortnite"])
            run_task(self, lambda: mode.enable(games),
                     on_done=lambda message: (self.ctx.notify(message, "ok"),
                                              self.game_button.setChecked(True)),
                     on_error=lambda message: (self.ctx.notify(message, "err", "error"),
                                               self.game_button.setChecked(False)))
        else:
            run_task(self, mode.disable,
                     on_done=lambda message: (self.ctx.notify(message, "info"),
                                              self.game_button.setChecked(False)),
                     on_error=lambda message: self.ctx.notify(message, "err", "error"))

    def _refresh_ip(self) -> None:
        from ... import ipwatch as module

        self.ip_badge.update_badge("…", "muted")

        def _probe():
            info = module.probe()
            module.store_ip(info)
            return info

        run_task(self, _probe, on_done=self._ip_done,
                 on_error=lambda _message: self.ip_badge.update_badge("НЕТ СВЯЗИ", "err"))

    def _ip_done(self, info) -> None:
        self.ip_value.setText(str(info.get("ip", "—")))
        place = ", ".join(str(part) for part in
                          (info.get("city"), info.get("country_name")) if part)
        self.ip_place.setText(place or "Тост при смене адреса включён")
        self.ip_badge.update_badge("ВНЕШНИЙ IP", "ok")

    def _toggle_obfuscation(self) -> None:
        from .. import overlays

        engine = self.ctx.zapret
        if engine.status == "running":
            run_task(self, engine.stop, on_done=self._after_stop, on_error=self._show_error)
            return
        if not engine.is_available():
            overlays.info(self.ctx.overlay, "Движок Zapret не найден",
                          "Укажите папку zapret-discord-youtube в <b>Настройки → Движки</b> "
                          "или установите его из папки <code>engines/</code>.")
            return
        if not self.ctx.admin():
            self._admin_help()
            return
        self.toggle_button.setEnabled(False)
        run_task(self, engine.start, on_done=self._after_start, on_error=self._start_failed)

    def _after_start(self, _result=None) -> None:
        self.toggle_button.setEnabled(True)
        if self.ctx.zapret.status == "running":
            self.ctx.notify("Обход включён — Zapret запущен", "ok", "enable")

    def _start_failed(self, message: str) -> None:
        self.toggle_button.setEnabled(True)
        self._refresh_hero()
        if "администратор" in message.lower() or "admin" in message.lower():
            self._admin_help()
        else:
            self.ctx.notify(f"Не удалось запустить Zapret: {message}", "err", "error")

    def _after_stop(self, _result=None) -> None:
        self.ctx.notify("Обход выключен", "warn", "disable")
        self._refresh_hero()

    def _show_error(self, message: str) -> None:
        self.ctx.notify(message, "err", "error")

    def _admin_help(self) -> None:
        from .. import overlays

        overlays.confirm(
            self.ctx.overlay,
            "Требуются права администратора",
            "Zapret использует драйвер WinDivert, а ремонт сети меняет настройки Windows. "
            "Обе операции требуют повышенных прав.<br><br>Zentrix перезапустится от имени "
            "администратора. Настройки сохранятся.",
            "Перезапустить от администратора",
            self.ctx.relaunch_admin,
        )

    def on_theme(self) -> None:
        p = self.ctx.palette
        self.orb.set_palette(p)
        for pill in (self.zapret_pill, self.vpn_pill):
            pill.set_palette(p)
        self._refresh_hero()
