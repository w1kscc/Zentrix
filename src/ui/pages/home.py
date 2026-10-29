"""Dashboard: live status, quick controls and service snapshot."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QRectF, Qt, QVariantAnimation
from PySide6.QtGui import QColor, QFont, QLinearGradient, QPainter, QPen, QRadialGradient
from PySide6.QtWidgets import (
    QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget,
)

from ... import constants
from ...blocking_check import STATUS_LABELS
from .. import overlays, theme
from ..widgets import (
    Badge, GlassCard, IconOrb, PrimaryButton, StatTile, TrafficChart, human_bytes, human_speed,
    make_heading, svg_pixmap,
)
from .base_page import Page, page_heading

STATUS_TEXT = {
    "running": "Работает",
    "starting": "Запуск…",
    "stopping": "Остановка…",
    "stopped": "Выключен",
    "error": "Ошибка",
    "missing": "Не настроен",
}


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


class HomePage(Page):
    key = "home"

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        self._engine_cards: dict[str, tuple[QLabel, Badge, QPushButton]] = {}
        self._last_sample = {}
        self._build()
        self._connect()
        self.on_theme()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        p = self.ctx.palette
        self.add(page_heading("Главная", "Zapret, Happ и Hiddify — под одним стеклом"))

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
        check_button.clicked.connect(lambda: self.ctx.navigate("blockcheck"))
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

        stats = QGridLayout()
        stats.setSpacing(14)
        self.tile_down = StatTile("Входящая скорость", "download", p, "0 Б/с")
        self.tile_up = StatTile("Исходящая скорость", "activity", p, "0 Б/с")
        self.tile_total = StatTile("Трафик за сессию", "wifi", p, "0 Б")
        stats.addWidget(self.tile_down, 0, 0)
        stats.addWidget(self.tile_up, 0, 1)
        stats.addWidget(self.tile_total, 0, 2)
        self.add_layout(stats)

        chart_card = GlassCard("Скорость во времени", "Обновление раз в секунду · системный интерфейс",
                               "activity", p)
        self.chart = TrafficChart(p)
        self.chart.setMinimumHeight(150)
        chart_card.add(self.chart)
        self.add(chart_card)

        engines_row = QHBoxLayout()
        engines_row.setSpacing(14)
        for key, title, icon_name, description in (
            ("zapret", "Zapret", "bolt", "DPI-обход через winws"),
            ("happ", "Happ", "globe", "Xray · VLESS / VMess"),
            ("hiddify", "Hiddify", "shield", "sing-box · мультипротокол"),
        ):
            card = GlassCard(title, description, icon_name, p)
            card.setMinimumHeight(150)
            badge = Badge("Проверка…", "muted")
            card.add_header_widget(badge)
            detail = QLabel("—")
            detail.setObjectName("tiny")
            detail.setWordWrap(True)
            card.add(detail)
            card.body.addStretch(1)
            button = QPushButton("Управление")
            button.setProperty("variant", "chip")
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(32)
            button.clicked.connect(lambda _=False, k=key: self.ctx.navigate(k))
            card.add(button)
            engines_row.addWidget(card, 1)
            self._engine_cards[key] = (detail, badge, button)
        self.add_layout(engines_row)

        bottom = QHBoxLayout()
        bottom.setSpacing(14)
        services = GlassCard("Проверка сервисов", "Последний результат на этой сессии", "target", p)
        self.services_box = QVBoxLayout()
        self.services_box.setSpacing(6)
        services.add_layout(self.services_box)
        self.services_placeholder = QLabel("Проверка ещё не запускалась")
        self.services_placeholder.setObjectName("tiny")
        self.services_box.addWidget(self.services_placeholder)
        services_button = QPushButton("Проверить сейчас")
        services_button.setProperty("variant", "chip")
        services_button.setCursor(Qt.PointingHandCursor)
        services_button.setFixedHeight(32)
        services_button.clicked.connect(lambda: self.ctx.navigate("blockcheck"))
        services.add(services_button)
        bottom.addWidget(services, 3)

        quick = GlassCard("Быстрые действия", "", "settings", p)
        for text, icon_name, target in (
            ("Обновления компонентов", "download", "updates"),
            ("Очистка от лишних файлов", "trash", "settings"),
            ("Мониторинг трафика", "activity", "monitor"),
            ("Оформление и звук", "palette", "settings"),
        ):
            button = QPushButton(text)
            button.setIcon(self._icon(icon_name))
            button.setProperty("variant", "ghost")
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(34)
            button.setStyleSheet("text-align:left; padding-left:10px;")
            button.clicked.connect(lambda _=False, t=target: self.ctx.navigate(t))
            quick.add(button)
        bottom.addWidget(quick, 2)
        self.add_layout(bottom)
        self.finish()

    def _icon(self, name: str):
        from ..widgets import icon

        return icon(name, self.ctx.palette.accent, 18)

    def _connect(self) -> None:
        self.ctx.monitor.sampled.connect(self._on_sample)
        for key, engine in (("zapret", self.ctx.zapret), ("happ", self.ctx.happ),
                            ("hiddify", self.ctx.hiddify)):
            engine.status_changed.connect(lambda *_, k=key: self._refresh_engine(k))
            engine.log_line.connect(lambda *_: None)

    # ------------------------------------------------------------------- live
    def on_show(self) -> None:
        self.ctx.start_monitor(show_connections=False)
        self._refresh_all()

    def on_hide(self) -> None:
        # The dashboard owns the sampler only while it is visible. This also
        # guarantees the Monitor tab opens in the stopped state.
        self.ctx.stop_monitor()

    def _refresh_all(self) -> None:
        for key in ("zapret", "happ", "hiddify"):
            self._refresh_engine(key)
        self._refresh_hero()
        self._refresh_services()

    def _refresh_hero(self) -> None:
        engine = self.ctx.zapret
        running = engine.status == "running"
        self.orb.set_active(running)
        self.hero_badge.update_badge("АКТИВНО" if running else "ВЫКЛЮЧЕНО",
                                     "ok" if running else "muted")
        if running:
            strategy = self.ctx.settings.get("zapret.strategy", "")
            self.hero_subtitle.setText(f"Zapret работает · {strategy} · {engine._message}")
            self.toggle_button.setText("Остановить обход")
        else:
            strategy = self.ctx.settings.get("zapret.strategy", "general.bat")
            self.hero_subtitle.setText(f"Zapret выключен · выбрана стратегия {strategy}")
            self.toggle_button.setText("Включить обход")
        self.admin_notice.setVisible(not self.ctx.admin())

    def _refresh_engine(self, key: str) -> None:
        engine = getattr(self.ctx, key)
        detail, badge, _button = self._engine_cards[key]
        status = engine.status
        if key in {"happ", "hiddify"} and not engine.core_installed() and status == "stopped":
            badge.update_badge("НЕТ ЯДРА", "warn")
            detail.setText("Ядро не установлено — откройте вкладку")
        elif status == "running":
            badge.update_badge("РАБОТАЕТ", "ok")
            # Only proxy engines expose a selected node; Zapret has none.
            node = engine.selected_node() if hasattr(engine, "selected_node") else None
            detail.setText(f"{node.summary() if node else 'Подключено'} · {engine._message}")
        elif status == "error":
            badge.update_badge("ОШИБКА", "err")
            detail.setText(engine._message or "Смотрите журнал")
        elif status in {"starting", "stopping"}:
            badge.update_badge(STATUS_TEXT.get(status, status).upper(), "info")
            detail.setText(engine._message)
        else:
            badge.update_badge("ВЫКЛЮЧЕН", "muted")
            detail.setText("Готов к подключению" if key == "zapret" or engine.core_installed()
                           else "Требуется установка ядра")
        if key == "zapret":
            self._refresh_hero()

    def _on_sample(self, data: dict) -> None:
        self._last_sample = data
        self.tile_down.set_value(human_speed(data.get("down", 0)),
                                 f"{human_bytes(data.get('total_down', 0))} получено")
        self.tile_up.set_value(human_speed(data.get("up", 0)),
                               f"{human_bytes(data.get('total_up', 0))} отправлено")
        self.tile_total.set_value(
            human_bytes(data.get("total_down", 0) + data.get("total_up", 0)),
            f"{data.get('connections', 0)} активных соединений",
        )
        self.chart.push(data.get("down", 0), data.get("up", 0))

    def _refresh_services(self) -> None:
        while self.services_box.count():
            item = self.services_box.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        results = self.ctx.block_results
        if not results:
            label = QLabel("Проверка ещё не запускалась. Нажмите «Проверить сейчас».")
            label.setObjectName("tiny")
            label.setWordWrap(True)
            self.services_box.addWidget(label)
            return
        for result in results[:6]:
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(0, 0, 0, 0)
            layout.setSpacing(8)
            layout.addWidget(QLabel(result.name), 1)
            kind = {"ok": "ok", "blocked": "err", "unstable": "warn"}.get(result.status, "muted")
            layout.addWidget(Badge(STATUS_LABELS.get(result.status, result.status), kind), 0)
            self.services_box.addWidget(row)

    # --------------------------------------------------------------- actions
    def _toggle_obfuscation(self) -> None:
        engine = self.ctx.zapret
        if engine.status == "running":
            from ..workers import run_task

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
        from ..workers import run_task

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
        overlays.confirm(
            self.ctx.overlay,
            "Требуются права администратора",
            "Zapret использует драйвер WinDivert, поэтому <b>winws.exe</b> запускается только "
            "от имени администратора.<br><br>Zentrix перезапустится с повышенными правами. "
            "Текущее окно закроется, настройки сохранятся.",
            "Перезапустить от администратора",
            self.ctx.relaunch_admin,
        )

    def on_theme(self) -> None:
        p = self.ctx.palette
        self.orb.set_palette(p)
        self.chart.set_palette(p)
        for key in ("zapret", "happ", "hiddify"):
            _detail, _badge, button = self._engine_cards[key]
            button.setIcon(self._icon("chevron"))
        self._refresh_hero()
