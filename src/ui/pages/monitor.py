"""Traffic monitor: live speed chart and a sortable connection table."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)

from .. import theme
from ..widgets import (
    Badge, GlassCard, PrimaryButton, StatTile, TrafficChart, human_bytes, human_speed, icon,
)
from .base_page import Page, page_heading


class SortItem(QTableWidgetItem):
    """Table cell that sorts by its numeric value, not by formatted text."""

    def __init__(self, text: str, value) -> None:
        super().__init__(text)
        self._sort_value = value
        self.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)

    def __lt__(self, other) -> bool:  # noqa: D105 - Qt hook
        if isinstance(other, SortItem):
            return self._sort_value < other._sort_value
        return super().__lt__(other)


class MonitorPage(Page):
    key = "monitor"

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        self._last = {}
        self._rows = 0
        self._build()
        self._connect()
        self.on_theme()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        p = self.ctx.palette
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(12)
        header_layout.addWidget(
            page_heading("Мониторинг", "Скорость интерфейсов и активные TCP-соединения"), 1
        )
        self.status_badge = Badge("ОСТАНОВЛЕН", "muted")
        header_layout.addWidget(self.status_badge, 0, Qt.AlignBottom)
        self.add(header)

        controls = GlassCard("Параметры мониторинга", "Обновление не чаще одного раза в секунду",
                            "activity", p)
        row = QHBoxLayout()
        row.setSpacing(10)
        self.start_button = PrimaryButton("Запустить", "play", p)
        self.start_button.clicked.connect(self._toggle)
        row.addWidget(self.start_button)
        self.reset_button = QPushButton("Сбросить счётчики")
        self.reset_button.setIcon(icon("refresh", p.accent, 18))
        self.reset_button.clicked.connect(self._reset)
        row.addWidget(self.reset_button)
        row.addSpacing(8)
        row.addWidget(QLabel("Интервал"))
        self.interval = QComboBox()
        for label, value in (("0,5 с", 0.5), ("1 с", 1.0), ("2 с", 2.0), ("5 с", 5.0)):
            self.interval.addItem(label, value)
        current = float(self.ctx.settings.get("monitor.interval", 1.0) or 1.0)
        index = self.interval.findData(current)
        self.interval.setCurrentIndex(max(0, index))
        self.interval.currentIndexChanged.connect(self._interval_changed)
        row.addWidget(self.interval)
        row.addStretch(1)
        self.updated_label = QLabel("Данных ещё нет")
        self.updated_label.setObjectName("tiny")
        row.addWidget(self.updated_label)
        controls.add_layout(row)
        self.add(controls)

        tiles = QGridLayout()
        tiles.setSpacing(14)
        self.tile_down = StatTile("Входящая скорость", "download", p, "0 Б/с")
        self.tile_up = StatTile("Исходящая скорость", "activity", p, "0 Б/с")
        self.tile_total = StatTile("Трафик за сессию", "wifi", p, "0 Б")
        self.tile_conn = StatTile("Соединения", "globe", p, "0")
        tiles.addWidget(self.tile_down, 0, 0)
        tiles.addWidget(self.tile_up, 0, 1)
        tiles.addWidget(self.tile_total, 0, 2)
        tiles.addWidget(self.tile_conn, 0, 3)
        self.add_layout(tiles)

        chart_card = GlassCard("Скорость во времени", "↓ входящая · ↑ исходящая", "activity", p)
        self.chart = TrafficChart(p, points=90)
        self.chart.setMinimumHeight(200)
        chart_card.add(self.chart)
        self.add(chart_card)

        table_card = GlassCard("Активные соединения",
                               "TCP ESTABLISHED · сортировка по клику на заголовок", "wifi", p)
        self.table_hint = QLabel("Ожидание данных…")
        self.table_hint.setObjectName("tiny")
        table_card.add(self.table_hint)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Процесс", "PID", "Удалённый адрес", "Состояние", "↓ скорость", "↑ скорость"]
        )
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(32)
        self.table.setMinimumHeight(320)
        header_view = self.table.horizontalHeader()
        header_view.setSectionResizeMode(0, QHeaderView.Stretch)
        header_view.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(2, QHeaderView.Stretch)
        header_view.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        header_view.setSectionResizeMode(5, QHeaderView.ResizeToContents)
        header_view.setSortIndicator(4, Qt.DescendingOrder)
        self.table.setSortingEnabled(True)
        table_card.add(self.table)
        self.add(table_card)
        self.finish()

    def _connect(self) -> None:
        monitor = self.ctx.monitor
        monitor.sampled.connect(self._on_sample)
        monitor.connections_ready.connect(self._on_connections)

    # ------------------------------------------------------------------- show
    def on_show(self) -> None:
        # Monitoring is opt-in: opening the tab must never start sampling.
        self._refresh_state()
        self._apply_series()
        if self._rows:
            self.table_hint.setText(f"Соединений: {self._rows}")
        elif not self._is_running():
            self.table_hint.setText("Мониторинг остановлен — нажмите «Запустить»")

    def on_hide(self) -> None:
        # Do not keep a background sampler alive after leaving the page.
        self.ctx.stop_monitor()
        self._refresh_state()

    def on_theme(self) -> None:
        p = self.ctx.palette
        self.chart.set_palette(p)
        for tile in (self.tile_down, self.tile_up, self.tile_total, self.tile_conn):
            tile.orb.set_palette(p)
        self.reset_button.setIcon(icon("refresh", p.accent, 18))
        self.start_button.setIcon(icon("pause" if self._is_running() else "play", "#FFFFFF", 18))
        self.table.viewport().update()

    # ------------------------------------------------------------------ state
    def _interval(self) -> float:
        value = self.interval.currentData()
        return float(value) if value else 1.0

    def _is_running(self) -> bool:
        return bool(self.ctx.monitor.isRunning())

    def _refresh_state(self) -> None:
        running = self._is_running()
        self.status_badge.update_badge("АКТИВЕН" if running else "ОСТАНОВЛЕН",
                                       "ok" if running else "muted")
        self.start_button.setText("Пауза" if running else "Запустить")
        self.start_button.setIcon(icon("pause" if running else "play", "#FFFFFF", 18))
        self.reset_button.setEnabled(True)

    def _toggle(self) -> None:
        if self._is_running():
            self.ctx.monitor.stop()
            self.ctx.monitor.wait(1500)
            self.updated_label.setText("Мониторинг приостановлен")
        else:
            self.ctx.start_monitor(show_connections=True)
            self.ctx.monitor.configure(interval=self._interval(), show_connections=True)
            self.updated_label.setText("Мониторинг запущен")
        self._refresh_state()

    def _reset(self) -> None:
        self.ctx.reset_monitor()
        self.chart.clear()
        self.table.setRowCount(0)
        self._rows = 0
        self._last = {}
        for tile in (self.tile_down, self.tile_up, self.tile_total, self.tile_conn):
            tile.set_value("0" if tile is self.tile_conn else "0 Б/с", "")
        self.tile_total.set_value("0 Б", "счётчики сброшены")
        self.tile_conn.set_value("0", "TCP ESTABLISHED")
        self.table_hint.setText("Счётчики сброшены — ожидание данных…")
        self.updated_label.setText("Счётчики сброшены")
        self.ctx.notify("Счётчики трафика сброшены", "ok")

    def _interval_changed(self) -> None:
        value = self._interval()
        self.ctx.settings.set("monitor.interval", value)
        self.ctx.monitor.configure(interval=value, show_connections=self.isVisible())

    # ------------------------------------------------------------------- live
    def _on_sample(self, data: dict) -> None:
        if not self.isVisible():
            return
        self._last = data
        down = float(data.get("down", 0) or 0)
        up = float(data.get("up", 0) or 0)
        total_down = float(data.get("total_down", 0) or 0)
        total_up = float(data.get("total_up", 0) or 0)
        self.tile_down.set_value(human_speed(down), f"{human_bytes(total_down)} получено")
        self.tile_up.set_value(human_speed(up), f"{human_bytes(total_up)} отправлено")
        self.tile_total.set_value(human_bytes(total_down + total_up),
                                  f"↓ {human_bytes(total_down)} · ↑ {human_bytes(total_up)}")
        self.tile_conn.set_value(str(data.get("connections", 0)), "TCP ESTABLISHED")
        self.chart.push(down, up)
        self.updated_label.setText("Обновлено только что")
        if not self._is_running():
            self._refresh_state()

    def _apply_series(self) -> None:
        # The monitor restarts with an empty chart; keep the current series.
        pass

    def _on_connections(self, rows: list) -> None:
        if not self.isVisible():
            return
        self._rows = len(rows)
        if not rows:
            self.table.setRowCount(0)
            self.table_hint.setText("Активных соединений нет")
            return
        header = self.table.horizontalHeader()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row, item in enumerate(rows):
            process = str(item.get("process") or "—")
            pid = int(item.get("pid") or 0)
            remote = str(item.get("remote") or "—")
            state = str(item.get("state") or "—")
            down = float(item.get("down") or 0)
            up = float(item.get("up") or 0)
            cells = [
                SortItem(process, process.lower()),
                SortItem(str(pid or "—"), pid),
                SortItem(remote, remote),
                SortItem(state, state),
                SortItem(human_speed(down), down),
                SortItem(human_speed(up), up),
            ]
            for column, cell in enumerate(cells):
                if column in (4, 5) and cell._sort_value > 0:  # noqa: SLF001
                    cell.setForeground(QColor(self.ctx.palette.accent2))
                self.table.setItem(row, column, cell)
        self.table.setSortingEnabled(True)
        self.table.sortItems(sort_column, sort_order)
        self.table.setUpdatesEnabled(True)
        self.table_hint.setText(
            f"Соединений: {len(rows)} · показаны первые {min(len(rows), 80)}"
        )
