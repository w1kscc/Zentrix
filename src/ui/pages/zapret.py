"""Zapret tab: strategy picker, start/stop, live winws journal."""

from __future__ import annotations

import html
import threading
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ... import winapi
from ...blocking_check import STATUS_LABELS
from ...engines.zapret import Strategy, discover_strategies
from ...strategy_check import SearchReport, StrategyReport, search_best_strategy, verify_strategy
from .. import overlays, theme
from ..widgets import (
    Badge, Divider, GlassCard, IconButton, IconOrb, LogView, PrimaryButton, ToggleRow,
    icon, make_heading,
)
from ..workers import run_task
from .base_page import STATUS_KIND, STATUS_TEXT, Page, page_heading


class StrategyDelegate(QStyledItemDelegate):
    def __init__(self, palette_obj: theme.Palette, parent=None) -> None:
        super().__init__(parent)
        self._palette = palette_obj

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self._palette = palette_obj

    def sizeHint(self, option, index) -> QSize:
        return QSize(option.rect.width(), 46)

    def paint(self, painter: QPainter, option, index) -> None:
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        p = self._palette
        rect = QRectF(option.rect).adjusted(2, 2, -2, -2)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        if selected:
            painter.setBrush(QColor(theme.rgba(p.accent, 0.18)))
            painter.setPen(QPen(QColor(theme.rgba(p.accent, 0.45)), 1))
            painter.drawRoundedRect(rect, 9, 9)
        elif hover:
            painter.setBrush(QColor(theme.rgba(p.surface, 0.05 if p.is_dark else 0.5)))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 9, 9)

        name = index.data(Qt.DisplayRole) or ""
        complexity = index.data(Qt.UserRole + 1) or ""
        font = QFont(option.font)
        font.setWeight(QFont.DemiBold if selected else QFont.Normal)
        painter.setFont(font)
        painter.setPen(QColor(p.text if selected else theme.mix(p.muted, p.text, 0.65)))
        text_rect = rect.adjusted(12, 0, -92, 0)
        metrics = QFontMetrics(font)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft,
                         metrics.elidedText(str(name), Qt.ElideRight, int(text_rect.width())))

        chip_font = QFont(option.font)
        chip_font.setPointSize(max(7, p.font_size - 2))
        painter.setFont(chip_font)
        chip_rect = QRectF(rect.right() - 84, rect.center().y() - 10, 74, 20)
        painter.setBrush(QColor(theme.rgba(p.accent, 0.12 if selected else 0.07)))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(chip_rect, 8, 8)
        painter.setPen(QColor(p.accent if selected else p.muted))
        painter.drawText(chip_rect, Qt.AlignCenter, str(complexity))
        if selected:
            painter.setBrush(QColor(p.accent2))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(QRectF(rect.left() + 5, rect.center().y() - 2, 4, 4))
        painter.restore()


class ZapretPage(Page):
    key = "zapret"

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        self.engine = context.zapret
        self._strategies: list[Strategy] = []
        self._last_folder = ""
        self._verifying = False
        self._searching = False
        self._search_cancel = threading.Event()
        self._search_index = 0
        self._search_total = 0
        self._build()
        self._connect()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        p = self.ctx.palette
        self.add(page_heading("Zapret", "GUI-обёртка над zapret-discord-youtube 1.10.4 · winws без консоли"))

        self.admin_card = GlassCard("Требуются права администратора",
                                    "Драйвер WinDivert загружается только с повышенными правами.",
                                    "alert", p)
        restart = PrimaryButton("Перезапустить от администратора", "shield", p)
        restart.clicked.connect(self._admin_help)
        self.admin_card.add(restart, 0)
        self.admin_card.hide()
        self.add(self.admin_card)

        hero = GlassCard(strong=True)
        row = QHBoxLayout()
        row.setSpacing(18)
        self.orb = IconOrb("bolt", p, 58)
        row.addWidget(self.orb, 0, Qt.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(4)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        self.status_badge = Badge("ВЫКЛЮЧЕН", "muted")
        title_row.addWidget(self.status_badge, 0, Qt.AlignLeft)
        self.status_label = QLabel("Движок не запущен")
        self.status_label.setObjectName("muted")
        title_row.addWidget(self.status_label, 1)
        column.addLayout(title_row)
        self.strategy_label = QLabel("Стратегия: —")
        self.strategy_label.setObjectName("h2")
        column.addWidget(self.strategy_label)
        self.detail_label = QLabel("Путь к движку не задан")
        self.detail_label.setObjectName("tiny")
        self.detail_label.setWordWrap(True)
        column.addWidget(self.detail_label)
        buttons = QHBoxLayout()
        buttons.setSpacing(9)
        self.toggle_button = PrimaryButton("Запустить", "play", p)
        self.toggle_button.clicked.connect(self._toggle)
        buttons.addWidget(self.toggle_button)
        self.restart_button = QPushButton("Перезапустить")
        self.restart_button.setIcon(icon("refresh", p.accent, 18))
        self.restart_button.setFixedHeight(38)
        self.restart_button.clicked.connect(self._restart)
        buttons.addWidget(self.restart_button)
        self.verify_button = QPushButton("Проверить стратегию")
        self.verify_button.setIcon(icon("target", p.accent, 18))
        self.verify_button.setFixedHeight(38)
        self.verify_button.setToolTip(
            "Запустить выбранную стратегию на несколько секунд и проверить доступность сервисов"
        )
        self.verify_button.clicked.connect(self._verify_strategy)
        buttons.addWidget(self.verify_button)
        self.command_button = QPushButton("Команда winws")
        self.command_button.setProperty("variant", "ghost")
        self.command_button.clicked.connect(self._show_command)
        buttons.addWidget(self.command_button)
        buttons.addStretch(1)
        column.addLayout(buttons)
        self.verify_label = QLabel("Проверка стратегии не запускалась")
        self.verify_label.setObjectName("tiny")
        self.verify_label.setWordWrap(True)
        column.addWidget(self.verify_label)
        row.addLayout(column, 1)
        hero.body.addLayout(row)
        self.add(hero)

        body = QHBoxLayout()
        body.setSpacing(14)
        strategies_card = GlassCard("Стратегии", "Выберите .bat-стратегию — Zentrix запустит winws напрямую",
                                    "filter", p)
        self.best_button = QPushButton("Поиск лучшей стратегии")
        self.best_button.setIcon(icon("target", p.accent, 17))
        self.best_button.setProperty("variant", "chip")
        self.best_button.setCursor(Qt.PointingHandCursor)
        self.best_button.setFixedHeight(32)
        self.best_button.setToolTip(
            "Поочерёдно проверить все стратегии и выбрать ту, которая открывает больше сервисов"
        )
        self.best_button.clicked.connect(self._search_best)
        strategies_card.add_header_widget(self.best_button)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию…")
        self.search.textChanged.connect(self._filter)
        strategies_card.add(self.search)
        self.best_label = QLabel("Поиск лучшей стратегии не запускался")
        self.best_label.setObjectName("tiny")
        self.best_label.setWordWrap(True)
        strategies_card.add(self.best_label)
        self.list = QListWidget()
        self.list.setMouseTracking(True)
        self.list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.list.setMinimumHeight(370)
        self.delegate = StrategyDelegate(p)
        self.list.setItemDelegate(self.delegate)
        self.list.currentItemChanged.connect(self._selection_changed)
        strategies_card.add(self.list, 1)
        body.addWidget(strategies_card, 3)

        side = QVBoxLayout()
        side.setSpacing(14)
        config_card = GlassCard("Расположение", "Папка zapret-discord-youtube", "folder", p)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText(r"C:\...\zapret-discord-youtube")
        config_card.add(self.path_edit)
        path_buttons = QHBoxLayout()
        path_buttons.setSpacing(8)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self._browse)
        path_buttons.addWidget(browse)
        apply_path = QPushButton("Применить")
        apply_path.setProperty("variant", "primary")
        apply_path.clicked.connect(self._apply_path)
        path_buttons.addWidget(apply_path)
        config_card.add_layout(path_buttons)
        self.autostart_row = ToggleRow("Автозапуск в Zentrix",
                                       "Стартовать стратегию при открытии приложения",
                                       bool(self.ctx.settings.get("zapret.autostart", False)), p)
        self.autostart_row.toggled.connect(self._autostart_changed)
        config_card.add(self.autostart_row)
        self.os_autostart_row = ToggleRow("Запуск при старте Windows",
                                         "Добавить Zentrix в автозагрузку пользователя",
                                         winapi.is_autostart_enabled(), p)
        self.os_autostart_row.toggled.connect(self._os_autostart_changed)
        config_card.add(self.os_autostart_row)
        side.addWidget(config_card)

        system_card = GlassCard("Состояние", "", "cpu", p)
        self.pid_label = QLabel("PID: —")
        self.pid_label.setObjectName("tiny")
        self.admin_label = QLabel("Права: пользователь" if not self.ctx.admin() else "Права: администратор")
        self.admin_label.setObjectName("tiny")
        self.folder_label = QLabel("Движок: не найден")
        self.folder_label.setObjectName("tiny")
        self.folder_label.setWordWrap(True)
        system_card.add(self.pid_label)
        system_card.add(self.admin_label)
        system_card.add(self.folder_label)
        side.addWidget(system_card)
        side.addStretch(1)
        body.addLayout(side, 2)
        self.add_layout(body)

        log_card = GlassCard("Журнал winws", "Вывод процесса в реальном времени", "activity", p)
        log_tools = QHBoxLayout()
        log_tools.addStretch(1)
        copy_button = IconButton("copy", p, "Копировать журнал")
        copy_button.clicked.connect(self._copy_log)
        clear_button = IconButton("trash", p, "Очистить журнал")
        clear_button.clicked.connect(lambda: self.log.clear())
        log_tools.addWidget(copy_button)
        log_tools.addWidget(clear_button)
        log_card.add_layout(log_tools)
        self.log = LogView(p)
        self.log.setMinimumHeight(210)
        log_card.add(self.log)
        self.add(log_card)
        self.finish()

    def _connect(self) -> None:
        self.engine.status_changed.connect(self._on_status)
        self.engine.log_line.connect(self.log.append_line)
        self.engine.error.connect(lambda title, msg: self.ctx.notify(f"{title}: {msg}", "err", "error"))

    # ------------------------------------------------------------------- show
    def on_show(self) -> None:
        folder = str(self.engine.folder())
        if folder != self._last_folder:
            self._last_folder = folder
            self.path_edit.setText(folder)
            self.reload_strategies()
        self._refresh()
        self.admin_card.setVisible(not self.ctx.admin())
        self.orb.set_icon("bolt" if self.engine.status == "running" else "bolt")

    def on_theme(self) -> None:
        p = self.ctx.palette
        self.delegate.set_palette(p)
        self.list.viewport().update()
        self.orb.set_palette(p)
        self.log.set_palette(p)
        self.verify_button.setIcon(icon("target", p.accent, 18))
        self.best_button.setIcon(icon("target", p.accent, 17))

    # -------------------------------------------------------------- strategies
    def reload_strategies(self) -> None:
        folder = Path(self.path_edit.text().strip() or str(self.engine.folder()))
        self._strategies = discover_strategies(folder)
        self.list.clear()
        current = str(self.ctx.settings.get("zapret.strategy", "general.bat"))
        selected_row = 0
        for row, strategy in enumerate(self._strategies):
            item = QListWidgetItem(strategy.name)
            item.setData(Qt.UserRole, strategy.filename)
            item.setData(Qt.UserRole + 1, strategy.complexity)
            item.setToolTip(f"{strategy.filename} · {strategy.size} Б")
            self.list.addItem(item)
            if strategy.filename == current:
                selected_row = row
        if self._strategies:
            self.list.setCurrentRow(selected_row)
        else:
            self.ctx.notify("Стратегии не найдены — проверьте папку движка", "warn")
        self._update_strategy_labels()

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.list.count()):
            item = self.list.item(row)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _selection_changed(self, current, previous) -> None:
        if current is None:
            return
        filename = current.data(Qt.UserRole)
        self.ctx.settings.set("zapret.strategy", filename)
        self._update_strategy_labels()
        if self.engine.status == "running":
            self.ctx.notify("Стратегия сохранена. Перезапустите, чтобы применить.", "info")

    def _update_strategy_labels(self) -> None:
        strategy = self.engine.strategy()
        if strategy:
            self.strategy_label.setText(f"Стратегия: {strategy.name}")
            self.detail_label.setText(
                f"{strategy.filename} · {self.engine.folder()} · "
                f"{'запущена' if self.engine.status == 'running' else 'готова к запуску'}"
            )
        else:
            self.strategy_label.setText("Стратегия не выбрана")
            self.detail_label.setText(f"Папка: {self.engine.folder()}")
        self.folder_label.setText(f"Движок: {self.engine.folder()}")

    # ----------------------------------------------------------------- actions
    def _toggle(self) -> None:
        if self._searching:
            return
        if self.engine.status == "running":
            self.toggle_button.setEnabled(False)
            run_task(self, self.engine.stop, on_done=self._on_stopped,
                     on_error=lambda msg: self._error(msg))
            return
        if not self.ctx.admin():
            self._admin_help()
            return
        if not self.engine.is_available():
            self._error("winws.exe не найден. Проверьте папку движка.")
            return
        self.toggle_button.setEnabled(False)
        self.ctx.sound.play("click")
        run_task(self, self.engine.start, on_done=self._on_started,
                 on_error=lambda msg: self._error(msg))

    def _restart(self) -> None:
        if self._searching:
            return
        if not self.ctx.admin():
            self._admin_help()
            return
        if self.engine.status != "running":
            self._toggle()
            return
        self.restart_button.setEnabled(False)
        run_task(self, self.engine.restart, on_done=lambda _: self.restart_button.setEnabled(True),
                 on_error=lambda msg: self._error(msg))

    # -------------------------------------------------------- strategy check
    def _verify_strategy(self) -> None:
        if self._searching:
            return
        strategy = self.engine.strategy()
        if strategy is None:
            self.ctx.notify("Сначала выберите стратегию", "warn")
            return
        if not self.ctx.admin():
            self._admin_help()
            return
        if not self.engine.is_available():
            self._error("winws.exe не найден. Проверьте папку движка.")
            return
        active = str(self.ctx.settings.get("zapret.strategy", "") or "")
        if self.engine.status == "running" and active and active != strategy.filename:
            overlays.confirm(
                self.ctx.overlay,
                "Проверка стратегии",
                f"Сейчас запущена стратегия <b>{html.escape(active)}</b>.<br><br>"
                f"Для проверки <b>{html.escape(strategy.filename)}</b> Zapret будет "
                "временно остановлен, а после проверки запущен снова.",
                "Проверить",
                lambda: self._start_verification(strategy),
            )
            return
        self._start_verification(strategy)

    def _start_verification(self, strategy: Strategy) -> None:
        if self._verifying:
            return
        self._verifying = True
        self.toggle_button.setEnabled(False)
        self.restart_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.verify_button.setText("Проверка…")
        self.verify_label.setText(
            f"Проверка «{strategy.name}»: запуск winws и опрос сервисов…"
        )
        self.ctx.sound.play("click")
        run_task(self, verify_strategy, self.engine, strategy.filename,
                 on_done=self._on_verified, on_error=self._on_verify_error)

    def _reset_verify_button(self) -> None:
        self._verifying = False
        self.verify_button.setEnabled(True)
        self.verify_button.setText("Проверить стратегию")
        self.verify_button.setIcon(icon("target", self.ctx.palette.accent, 18))

    def _on_verified(self, report) -> None:
        self._reset_verify_button()
        if not isinstance(report, StrategyReport):
            self._on_verify_error("Неожиданный результат проверки")
            return
        self.verify_label.setText(report.verdict)
        kind = {"ok": "ok", "warn": "warn", "err": "err"}.get(report.level, "info")
        sound = "enable" if report.level == "ok" else "disable"
        self.ctx.notify(report.verdict, kind, sound)
        self._show_verification(report)
        self._refresh()

    def _on_verify_error(self, message: str) -> None:
        self._reset_verify_button()
        self.verify_label.setText(f"Ошибка проверки: {message}")
        self.ctx.notify(message, "err", "error")
        self._refresh()

    def _show_verification(self, report: StrategyReport) -> None:
        p = self.ctx.palette
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        headline = QLabel(
            f"<b>{html.escape(report.strategy or report.filename)}</b> · "
            f"{html.escape(report.verdict)}"
        )
        headline.setWordWrap(True)
        layout.addWidget(headline)

        if report.results:
            summary = QLabel(
                f"Проверено сервисов: {report.total} · доступно: {report.ok_count} · "
                f"время: {report.duration:.1f} с"
            )
            summary.setObjectName("tiny")
            layout.addWidget(summary)

        for result in report.results:
            color = {"ok": p.success, "unstable": p.warning}.get(result.status, p.danger)
            reason = html.escape(result.reason or STATUS_LABELS.get(result.status, result.status))
            line = (f"<b>{html.escape(result.name)}</b> — "
                    f"<span style='color:{color}'>{reason}</span> · {result.latency_ms} мс")
            if result.detail:
                line += (f"<br><span style='color:{p.muted}'>{html.escape(result.detail)}</span>")
            label = QLabel(line)
            label.setWordWrap(True)
            layout.addWidget(label)

        if report.error:
            error = QLabel(
                f"<span style='color:{p.danger}'>{html.escape(report.error)}</span>"
            )
            error.setWordWrap(True)
            layout.addWidget(error)

        note = ("Предыдущее состояние Zapret восстановлено." if report.restored
                else "Не удалось восстановить предыдущее состояние Zapret.")
        footer = QLabel(note)
        footer.setObjectName("tiny")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        layout.addStretch(1)

        overlays.panel_with_actions(
            self.ctx.overlay,
            f"Проверка стратегии · {report.strategy or '—'}",
            content,
            [
                ("Повторить", "ghost", lambda: self._retry_verification(report)),
                ("Закрыть", "primary", self.ctx.overlay.close_panel),
            ],
        )

    def _retry_verification(self, report: StrategyReport) -> None:
        self.ctx.overlay.close_panel()
        strategy = self.engine.strategy(report.filename)
        if strategy is not None:
            self._start_verification(strategy)

    # ------------------------------------------------------ best strategy search
    def _search_best(self) -> None:
        if self._searching:
            self._search_cancel.set()
            self.best_button.setEnabled(False)
            self.best_button.setText("Останавливаю…")
            self.best_label.setText("Поиск остановится после текущей стратегии…")
            return
        if self._verifying:
            self.ctx.notify("Дождитесь завершения проверки стратегии", "warn")
            return
        if not self._strategies:
            self.ctx.notify("Стратегии не найдены — проверьте папку движка", "warn")
            return
        if not self.ctx.admin():
            self._admin_help()
            return
        if not self.engine.is_available():
            self._error("winws.exe не найден. Проверьте папку движка.")
            return
        total = len(self._strategies)
        if self.engine.status == "running":
            action = ("Сейчас Zapret запущен: на время поиска он будет остановлен, "
                      "а после поиска запущен с лучшей стратегией.")
        else:
            action = ("После поиска лучшая стратегия будет выбрана; Zapret останется "
                      "остановленным до нажатия «Запустить».")
        overlays.confirm(
            self.ctx.overlay,
            "Поиск лучшей стратегии",
            f"Будет поочерёдно проверено <b>{total}</b> стратегий. Это занимает "
            f"несколько минут, интернет-обход на это время недоступен.<br><br>{action}",
            "Начать поиск",
            self._start_best_search,
        )

    def _start_best_search(self) -> None:
        if self._searching or not self._strategies:
            return
        self._searching = True
        self._search_cancel.clear()
        self._search_index = 0
        self._search_total = len(self._strategies)
        self.toggle_button.setEnabled(False)
        self.restart_button.setEnabled(False)
        self.verify_button.setEnabled(False)
        self.list.setEnabled(False)
        self.search.setEnabled(False)
        self.best_button.setEnabled(True)
        self.best_button.setText("Отменить поиск")
        self.best_label.setText(f"Поиск: 0 из {self._search_total}…")
        self.ctx.sound.play("click")
        run_task(
            self, search_best_strategy, self.engine, list(self._strategies),
            with_progress=True, cancelled=self._search_cancel.is_set,
            on_progress=self._on_search_progress,
            on_progress_text=self._on_search_progress_text,
            on_done=self._on_search_done, on_error=self._on_search_error,
        )

    def _on_search_progress(self, index: int, total: int) -> None:
        if not self._searching:
            return
        self._search_index = index
        self._search_total = total
        self.best_label.setText(f"Поиск: {index} из {total} · проверяю…")

    def _on_search_progress_text(self, name: str) -> None:
        if not self._searching:
            return
        self.best_label.setText(
            f"Поиск: {self._search_index} из {self._search_total} · {name}"
        )

    def _reset_search_controls(self) -> None:
        self._searching = False
        self.best_button.setEnabled(True)
        self.best_button.setText("Поиск лучшей стратегии")
        self.best_button.setIcon(icon("target", self.ctx.palette.accent, 17))
        self.list.setEnabled(True)
        self.search.setEnabled(True)
        self.verify_button.setEnabled(True)

    def _on_search_done(self, result) -> None:
        self._reset_search_controls()
        if not isinstance(result, SearchReport):
            self._on_search_error("Неожиданный результат поиска")
            return
        if result.best is not None:
            self._select_strategy(result.best.filename)
        if result.cancelled:
            text = f"Поиск остановлен: проверено {result.tested} из {result.total}"
            kind, sound = "warn", "disable"
        elif result.best is not None:
            text = f"Лучшая: {result.best.strategy} — {result.best.verdict}"
            kind = "ok" if result.best.level == "ok" else "warn"
            sound = "enable"
        else:
            text = "Рабочая стратегия не найдена"
            kind, sound = "err", "disable"
        self.best_label.setText(text)
        self.ctx.notify(text, kind, sound)
        self._show_search_report(result)
        self._refresh()

    def _on_search_error(self, message: str) -> None:
        self._reset_search_controls()
        self.best_label.setText(f"Ошибка поиска: {message}")
        self.ctx.notify(message, "err", "error")
        self._refresh()

    def _select_strategy(self, filename: str) -> None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(Qt.UserRole) == filename:
                self.list.setCurrentRow(row)
                self.list.scrollToItem(item)
                return

    def _show_search_report(self, result: SearchReport) -> None:
        p = self.ctx.palette
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        if result.cancelled:
            headline = f"Поиск остановлен: проверено {result.tested} из {result.total}"
        elif result.best is not None:
            headline = f"Лучшая стратегия: <b>{html.escape(result.best.strategy)}</b>"
        else:
            headline = "Рабочая стратегия не найдена"
        title = QLabel(headline)
        title.setWordWrap(True)
        layout.addWidget(title)

        summary = QLabel(
            f"Проверено: {result.tested} из {result.total} · время: {result.duration:.0f} с"
        )
        summary.setObjectName("tiny")
        layout.addWidget(summary)

        if result.best is not None:
            best = result.best
            best_line = QLabel(
                f"<span style='color:{self._level_color(best.level)}'>"
                f"{html.escape(best.verdict)}</span> · доступно {best.ok_count} из {best.total}"
            )
            best_line.setWordWrap(True)
            layout.addWidget(best_line)
            for item in best.results:
                colour = {"ok": p.success, "unstable": p.warning}.get(item.status, p.danger)
                reason = html.escape(item.reason or STATUS_LABELS.get(item.status, item.status))
                details = (f"<b>{html.escape(item.name)}</b> — "
                           f"<span style='color:{colour}'>{reason}</span> · {item.latency_ms} мс")
                label = QLabel(details)
                label.setWordWrap(True)
                layout.addWidget(label)
            layout.addWidget(Divider())

        shown = result.reports[:6]
        if shown:
            caption = QLabel(
                "Рейтинг" + (f" · показаны первые {len(shown)} из {result.tested}"
                             if result.tested > len(shown) else "")
            )
            caption.setObjectName("tiny")
            layout.addWidget(caption)
            for position, item in enumerate(shown, start=1):
                colour = self._level_color(item.level)
                line = (f"{position}. <b>{html.escape(item.strategy)}</b> — "
                        f"<span style='color:{colour}'>{html.escape(item.verdict)}</span>")
                label = QLabel(line)
                label.setWordWrap(True)
                layout.addWidget(label)

        if result.error:
            error = QLabel(
                f"<span style='color:{p.danger}'>{html.escape(result.error)}</span>"
            )
            error.setWordWrap(True)
            layout.addWidget(error)

        notes = []
        if result.applied:
            notes.append("Лучшая стратегия выбрана" + (" и запущена." if result.final_running
                                                       else "; запуск — вручную."))
        elif result.cancelled:
            notes.append("Поиск отменён, прежнее состояние Zapret восстановлено."
                         if result.was_running else "Поиск отменён.")
        elif result.best is None:
            notes.append("Рабочая стратегия не найдена, прежнее состояние восстановлено."
                         if result.was_running else "Рабочая стратегия не найдена.")
        if not result.state_ok:
            notes.append("Не удалось восстановить состояние Zapret — проверьте вкладку.")
        footer = QLabel(" ".join(notes))
        footer.setObjectName("tiny")
        footer.setWordWrap(True)
        layout.addWidget(footer)
        layout.addStretch(1)

        overlays.panel_with_actions(
            self.ctx.overlay,
            "Поиск лучшей стратегии",
            content,
            [
                ("Повторить", "ghost", lambda: self._retry_search()),
                ("Закрыть", "primary", self.ctx.overlay.close_panel),
            ],
        )

    def _retry_search(self) -> None:
        self.ctx.overlay.close_panel()
        self._search_best()

    def _level_color(self, level: str) -> str:
        p = self.ctx.palette
        return {"ok": p.success, "warn": p.warning}.get(level, p.danger)

    def _on_started(self, _result=None) -> None:
        self.toggle_button.setEnabled(True)
        if self.engine.status == "running":
            self.ctx.notify("Zapret запущен", "ok", "enable")

    def _on_stopped(self, _result=None) -> None:
        self.toggle_button.setEnabled(True)
        self.ctx.notify("Zapret остановлен", "warn", "disable")

    def _error(self, message: str) -> None:
        self.toggle_button.setEnabled(True)
        self.restart_button.setEnabled(True)
        self.ctx.notify(message, "err", "error")
        self._refresh()

    def _on_status(self, status: str, message: str) -> None:
        self.status_badge.update_badge(STATUS_TEXT.get(status, status).upper(),
                                       STATUS_KIND.get(status, "muted"))
        self.status_label.setText(message or STATUS_TEXT.get(status, status))
        running = status == "running"
        self.toggle_button.setText("Остановить" if running else "Запустить")
        self.toggle_button.setProperty("variant", "danger" if running else "primary")
        self.toggle_button.style().unpolish(self.toggle_button)
        self.toggle_button.style().polish(self.toggle_button)
        self.toggle_button.setIcon(icon("stop" if running else "play", "#FFFFFF", 18))
        busy = self._verifying or self._searching
        self.toggle_button.setEnabled(not busy)
        self.restart_button.setEnabled(running and not busy)
        self.pid_label.setText(f"PID: {self.engine.supervisor.pid or '—'}")
        self.orb.set_icon("bolt")

    def _refresh(self) -> None:
        self._on_status(self.engine.status, self.engine._message)
        self.admin_label.setText("Права: администратор" if self.ctx.admin() else "Права: пользователь")
        self.admin_card.setVisible(not self.ctx.admin())
        self._update_strategy_labels()

    def _browse(self) -> None:
        if self._searching:
            return
        folder = QFileDialog.getExistingDirectory(self, "Папка zapret-discord-youtube",
                                                  str(self.engine.folder()))
        if folder:
            self.path_edit.setText(folder)
            self._apply_path()

    def _apply_path(self) -> None:
        if self._searching:
            self.ctx.notify("Дождитесь завершения поиска стратегий", "warn")
            return
        folder = self.path_edit.text().strip()
        self.ctx.settings.set("zapret.path", folder)
        self.reload_strategies()
        self._refresh()
        self.ctx.notify("Путь к движку обновлён", "ok")

    def _autostart_changed(self, value: bool) -> None:
        self.ctx.settings.set("zapret.autostart", bool(value))

    def _os_autostart_changed(self, value: bool) -> None:
        if winapi.set_autostart(bool(value)):
            self.ctx.settings.set("general.autostart", bool(value))
            self.ctx.notify("Автозагрузка обновлена", "ok")
        else:
            self.ctx.notify("Не удалось изменить автозагрузку", "err")
            self.os_autostart_row.set_checked(winapi.is_autostart_enabled())

    def _copy_log(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.log.toPlainText())
        self.ctx.notify("Журнал скопирован", "ok")

    def _show_command(self) -> None:
        strategy = self.engine.strategy()
        text = self.engine.command_preview() if strategy else "Стратегия не выбрана"
        editor = QPlainTextEdit(text)
        editor.setReadOnly(True)
        editor.setMinimumHeight(260)
        editor.setObjectName("logView")
        overlays.panel_with_actions(
            self.ctx.overlay,
            f"winws · {strategy.name if strategy else '—'}",
            editor,
            [("Закрыть", "primary", self.ctx.overlay.close_panel)],
        )

    def _admin_help(self) -> None:
        overlays.confirm(
            self.ctx.overlay,
            "Права администратора",
            "Для загрузки драйвера WinDivert приложению нужны права администратора.<br><br>"
            "Zentrix перезапустится с повышением прав, настройки сохранятся.",
            "Перезапустить",
            self.ctx.relaunch_admin,
        )
