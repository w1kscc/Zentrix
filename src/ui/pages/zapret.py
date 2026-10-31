"""Zapret tab: strategy picker, start/stop, live winws journal."""

from __future__ import annotations

import html
import threading
from pathlib import Path

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QComboBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPlainTextEdit, QPushButton, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget,
)

from ... import winapi
from ...blocking_check import STATUS_LABELS
from ...engines.game_scan import GameEntry, scan_games
from ...engines.zapret import Strategy, discover_strategies, game_filter_settings, validate_port_ranges
from ...strategy_check import SearchReport, StrategyReport, search_best_strategy, verify_strategy
from ... import zapret_lists
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
            painter.setBrush(theme.qcolor(p.accent, 0.18))
            painter.setPen(QPen(theme.qcolor(p.accent, 0.45), 1))
            painter.drawRoundedRect(rect, 9, 9)
        elif hover:
            painter.setBrush(theme.qcolor("#FFFFFF", 0.11 if p.is_dark else 0.42))
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
        painter.setBrush(theme.qcolor(p.accent, 0.12 if selected else 0.07))
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
        self._games: list[GameEntry] = []
        self._scanned = False
        self._build()
        self._connect()
        self._load_saved_games()

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
        self.exhaustive_button = QPushButton("Полный перебор")
        self.exhaustive_button.setProperty("variant", "chip")
        self.exhaustive_button.setCheckable(True)
        self.exhaustive_button.setCursor(Qt.PointingHandCursor)
        self.exhaustive_button.setFixedHeight(32)
        self.exhaustive_button.setToolTip(
            "Включено: проверяются все стратегии и строится полный рейтинг.\n"
            "Выключено: поиск останавливается на первой полностью рабочей стратегии (быстро)."
        )
        self.exhaustive_button.setChecked(
            bool(self.ctx.settings.get("zapret.search_exhaustive", False)))
        strategies_card.add_header_widget(self.exhaustive_button)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск по названию…")
        self.search.textChanged.connect(self._filter)
        strategies_card.add(self.search)
        self.best_label = QLabel("Поиск лучшей стратегии не запускался")
        self.best_label.setObjectName("tiny")
        self.best_label.setWordWrap(True)
        strategies_card.add(self.best_label)
        self.list = QListWidget()
        self.list.setObjectName("strategyList")
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

        bypass_card = GlassCard("Обход", "Обновление списков из репозитория zapret-discord-youtube",
                                "download", p)
        bypass_row = QHBoxLayout()
        bypass_row.setSpacing(8)
        self.ipset_button = QPushButton("Обновить IPSet")
        self.ipset_button.setToolTip(
            "Скачать свежий список подсетей (ipset-all.txt) из репозитория Flowseal.\n"
            "Предыдущая версия сохраняется как ipset-all.txt.backup"
        )
        self.ipset_button.clicked.connect(self._update_ipset)
        bypass_row.addWidget(self.ipset_button, 1)
        self.hosts_button = QPushButton("Обновить hosts")
        self.hosts_button.setToolTip(
            "Синхронизировать файл hosts Windows с upstream-списком.\n"
            "Изменения вносятся отдельным блоком, оригинал сохраняется в hosts.zentrix.bak"
        )
        self.hosts_button.clicked.connect(self._update_hosts)
        bypass_row.addWidget(self.hosts_button, 1)
        bypass_card.add_layout(bypass_row)
        self.bypass_label = QLabel("")
        self.bypass_label.setObjectName("tiny")
        self.bypass_label.setWordWrap(True)
        bypass_card.add(self.bypass_label)
        side.addWidget(bypass_card)

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

        game_card = GlassCard("Игровой фильтр",
                              "Как Zapret работает с трафиком игр — без джиттера и скачков пинга",
                              "filter", p)
        mode_row = QHBoxLayout()
        mode_caption = QLabel("Режим")
        mode_row.addWidget(mode_caption)
        self.gamefilter_mode = QComboBox()
        for label, mode in (("Выключен", "disabled"),
                            ("Изоляция: Zapret только для выбранных игр", "isolate"),
                            ("Исключения: Zapret не применять к выбранным играм", "exclude")):
            self.gamefilter_mode.addItem(label, mode)
        saved_mode = str(self.ctx.settings.get("zapret.gamefilter.mode", "disabled") or "disabled")
        self.gamefilter_mode.setCurrentIndex(max(0, self.gamefilter_mode.findData(saved_mode)))
        self.gamefilter_mode.currentIndexChanged.connect(self._save_gamefilter_mode)
        mode_row.addWidget(self.gamefilter_mode, 1)
        game_card.add_layout(mode_row)

        games_controls = QHBoxLayout()
        games_controls.setSpacing(8)
        self.scan_button = QPushButton("Найти игры")
        self.scan_button.setProperty("variant", "chip")
        self.scan_button.setFixedHeight(32)
        self.scan_button.setCursor(Qt.PointingHandCursor)
        self.scan_button.setToolTip(
            "Сканировать библиотеки Steam, Epic Games, EA, GOG и реестр Windows"
        )
        self.scan_button.clicked.connect(self._scan_games)
        games_controls.addWidget(self.scan_button)
        self.add_game_button = QPushButton("Добавить вручную…")
        self.add_game_button.setProperty("variant", "chip")
        self.add_game_button.setFixedHeight(32)
        self.add_game_button.setCursor(Qt.PointingHandCursor)
        self.add_game_button.setToolTip("Указать путь к .exe игры в кастомной директории")
        self.add_game_button.clicked.connect(self._add_game_manual)
        games_controls.addWidget(self.add_game_button)
        games_controls.addStretch(1)
        game_card.add_layout(games_controls)

        self.games_search = QLineEdit()
        self.games_search.setPlaceholderText("Поиск по названию или имени процесса…")
        self.games_search.textChanged.connect(self._filter_games)
        game_card.add(self.games_search)

        self.games_list = QListWidget()
        self.games_list.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.games_list.setMinimumHeight(190)
        self.games_list.itemChanged.connect(self._on_game_item_changed)
        game_card.add(self.games_list, 1)

        self.gamefilter_status = QLabel("")
        self.gamefilter_status.setObjectName("tiny")
        self.gamefilter_status.setWordWrap(True)
        self.gamefilter_status.hide()
        game_card.add(self.gamefilter_status)

        game_card.add(Divider())
        ports_caption = QLabel("Фильтр портов upstream (глобальный, применяется к всему трафику)")
        ports_caption.setObjectName("tiny")
        game_card.add(ports_caption)
        self.game_mode = QComboBox()
        for label, mode in (("Порты: выключено", "disabled"), ("Порты: TCP + UDP", "all"),
                            ("Порты: только TCP", "tcp"), ("Порты: только UDP", "udp")):
            self.game_mode.addItem(label, mode)
        ranges = game_filter_settings(self.engine.folder())
        self.game_mode.setCurrentIndex(max(0, self.game_mode.findData(ranges["mode"])))
        game_card.add(self.game_mode)
        range_row = QHBoxLayout()
        self.game_tcp = QLineEdit(ranges["tcp"])
        self.game_tcp.setPlaceholderText("TCP: 1024-65535")
        self.game_udp = QLineEdit(ranges["udp"])
        self.game_udp.setPlaceholderText("UDP: 1024-65535")
        range_row.addWidget(self.game_tcp)
        range_row.addWidget(self.game_udp)
        game_card.add_layout(range_row)
        save_game = QPushButton("Сохранить фильтр портов")
        save_game.setProperty("variant", "chip")
        save_game.clicked.connect(self._save_game_filter)
        game_card.add(save_game)
        self.add(game_card)

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
        self.engine.gamefilter_state.connect(self._on_gamefilter_state)

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
        # Auto-scan game libraries once per session, per the game filter spec.
        if not self._scanned:
            self._scan_games()

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
            if self.engine.status == "running":
                active = self.engine.strategy(self.engine.active_strategy)
                state = (f"запущена: {active.filename}" if active
                         else "процесс работает; выбранная стратегия применится после перезапуска")
            else:
                state = "готова к запуску"
            self.detail_label.setText(
                f"{strategy.filename} · {self.engine.folder()} · "
                f"{state}"
            )
        else:
            self.strategy_label.setText("Стратегия не выбрана")
            self.detail_label.setText(f"Папка: {self.engine.folder()}")
        self.folder_label.setText(f"Движок: {self.engine.folder()}")

    def _save_game_filter(self) -> None:
        tcp = validate_port_ranges(self.game_tcp.text())
        udp = validate_port_ranges(self.game_udp.text())
        if tcp != self.game_tcp.text().replace(" ", ""):
            self.ctx.notify("Некорректный диапазон TCP‑портов", "warn")
            return
        if udp != self.game_udp.text().replace(" ", ""):
            self.ctx.notify("Некорректный диапазон UDP‑портов", "warn")
            return
        mode = self.game_mode.currentData()
        flag = self.engine.folder() / "utils" / "game_filter.enabled"
        try:
            flag.parent.mkdir(parents=True, exist_ok=True)
            flag.write_text(f"mode={mode}\ntcp={tcp}\nudp={udp}\n", encoding="utf-8")
        except OSError as exc:
            self.ctx.notify(f"Не удалось сохранить игровой фильтр: {exc}", "err", "error")
            return
        if self.engine.status == "running":
            self.ctx.notify("Игровой фильтр сохранён. Перезапустите Zapret для применения.", "info")
        else:
            self.ctx.notify("Игровой фильтр сохранён", "ok")

    # ------------------------------------------------------------ game filter
    def _checked_game_paths(self) -> list[str]:
        return [self.games_list.item(row).data(Qt.UserRole)
                for row in range(self.games_list.count())
                if self.games_list.item(row).checkState() == Qt.Checked]

    def _load_saved_games(self) -> None:
        saved = [str(item) for item in (self.ctx.settings.get("zapret.gamefilter.games") or [])]
        known = {entry.exe.lower() for entry in self._games}
        for path in saved:
            if path.lower() not in known:
                self._games.append(GameEntry(Path(path).stem, path, "manual"))
        self._populate_games()

    def _populate_games(self) -> None:
        checked = {item.lower() for item in (self.ctx.settings.get("zapret.gamefilter.games") or [])}
        self.games_list.blockSignals(True)
        self.games_list.clear()
        for game in self._games:
            item = QListWidgetItem(f"{game.name}   ·   {Path(game.exe).name}")
            item.setData(Qt.UserRole, game.exe)
            item.setToolTip(game.exe)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Checked if game.exe.lower() in checked else Qt.Unchecked)
            self.games_list.addItem(item)
        self.games_list.blockSignals(False)
        self._filter_games(self.games_search.text())

    def _merge_games(self, entries: list[GameEntry]) -> int:
        known = {entry.exe.lower() for entry in self._games}
        added = 0
        for entry in entries:
            if entry.exe.lower() not in known:
                self._games.append(entry)
                known.add(entry.exe.lower())
                added += 1
        return added

    def _on_game_item_changed(self, _item) -> None:
        self.ctx.settings.set("zapret.gamefilter.games", self._checked_game_paths())

    def _filter_games(self, text: str) -> None:
        needle = text.strip().lower()
        for row in range(self.games_list.count()):
            item = self.games_list.item(row)
            item.setHidden(bool(needle) and needle not in item.text().lower())

    def _scan_games(self) -> None:
        if getattr(self, "_scanning", False):
            return
        self._scanning = True
        self.scan_button.setEnabled(False)
        self.scan_button.setText("Сканирую…")
        run_task(self, scan_games, on_done=self._games_scanned,
                 on_error=self._games_scan_failed)

    def _games_scanned(self, entries) -> None:
        self._scanning = False
        self._scanned = True
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Найти игры")
        added = self._merge_games(list(entries))
        self._populate_games()
        if added:
            self.ctx.notify(f"Найдено игр: {len(entries)} (новых: {added})", "ok")
        elif entries:
            self.ctx.notify(f"Найдено игр: {len(entries)} — список уже актуален", "info")
        else:
            self.ctx.notify("Игры не найдены — добавьте .exe вручную", "warn")

    def _games_scan_failed(self, message: str) -> None:
        self._scanning = False
        self._scanned = True
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Найти игры")
        self.ctx.notify(f"Сканирование игр: {message}", "err", "error")

    def _add_game_manual(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Выберите .exe игры", "",
                                              "Приложения (*.exe);;Все файлы (*.*)")
        if not path:
            return
        self._merge_games([GameEntry(Path(path).stem, path, "manual")])
        self._populate_games()
        # Check the newly added game and persist it.
        for row in range(self.games_list.count()):
            item = self.games_list.item(row)
            if item.data(Qt.UserRole) == path:
                item.setCheckState(Qt.Checked)
                break
        self.ctx.settings.set("zapret.gamefilter.games", self._checked_game_paths())
        self.ctx.notify("Игра добавлена в игровой фильтр", "ok")

    def _save_gamefilter_mode(self, _index: int) -> None:
        mode = self.gamefilter_mode.currentData()
        self.ctx.settings.set("zapret.gamefilter.mode", mode)
        if mode == "disabled":
            self.ctx.notify("Игровой фильтр выключен", "info")
            return
        if not self._checked_game_paths():
            self.ctx.notify("Отметьте игры в списке — иначе фильтр не сработает", "warn")
        elif mode == "isolate":
            self.ctx.notify(
                "Режим изоляции: Zapret будет запускаться только пока идёт выбранная игра",
                "info")
        else:
            self.ctx.notify(
                "Режим исключений: Zapret будет останавливаться на время выбранной игры",
                "info")

    def _on_gamefilter_state(self, text: str) -> None:
        self.gamefilter_status.setText(text)
        self.gamefilter_status.setVisible(bool(text))

    # --------------------------------------------------------- bypass updates
    def _update_ipset(self) -> None:
        if getattr(self, "_updating_lists", False):
            return
        self._updating_lists = True
        self.ipset_button.setEnabled(False)
        self.bypass_label.setText("Скачиваю ipset…")
        run_task(self, zapret_lists.update_ipset, self.engine.folder(),
                 on_done=self._ipset_updated, on_error=self._lists_failed)

    def _ipset_updated(self, count: int) -> None:
        self._updating_lists = False
        self.ipset_button.setEnabled(True)
        self.bypass_label.setText(f"ipset обновлён: {count} подсетей")
        if self.engine.status == "running":
            self.ctx.notify("IPSet обновлён — перезапустите Zapret для применения", "info")
        else:
            self.ctx.notify(f"IPSet обновлён ({count} подсетей)", "ok")

    def _update_hosts(self) -> None:
        if getattr(self, "_updating_lists", False):
            return
        self._updating_lists = True
        self.hosts_button.setEnabled(False)
        self.bypass_label.setText("Проверяю hosts…")
        run_task(self, zapret_lists.fetch_hosts,
                 on_done=self._hosts_fetched, on_error=self._lists_failed)

    def _hosts_fetched(self, content: str) -> None:
        self._updating_lists = False
        self.hosts_button.setEnabled(True)
        if zapret_lists.hosts_is_up_to_date(content):
            self.bypass_label.setText("hosts уже актуален")
            self.ctx.notify("Файл hosts уже соответствует upstream-списку", "ok")
            return
        if self.ctx.admin():
            if zapret_lists.write_hosts_block(content):
                self.bypass_label.setText("hosts обновлён")
                self.ctx.notify(
                    "Файл hosts обновлён. Изменения могут примениться после "
                    "очистки кэша DNS (ipconfig /flushdns) или перезапуска сети.",
                    "ok")
            else:
                self.bypass_label.setText("Не удалось записать hosts")
                self.ctx.notify("Не удалось записать файл hosts", "err", "error")
            return
        # No admin rights: show the content and instructions, like upstream does.
        self.bypass_label.setText("hosts отличается — нужны права администратора")
        from PySide6.QtWidgets import QApplication, QPlainTextEdit

        editor = QPlainTextEdit(
            zapret_lists.HOSTS_BEGIN + "\n" + content + "\n" + zapret_lists.HOSTS_END)
        editor.setReadOnly(True)
        editor.setMinimumHeight(260)
        editor.setObjectName("logView")
        overlays.panel_with_actions(
            self.ctx.overlay,
            "Обновление hosts",
            editor,
            [
                ("Скопировать", "ghost", lambda: (
                    QApplication.clipboard().setText(
                        zapret_lists.HOSTS_BEGIN + "\n" + content + "\n" + zapret_lists.HOSTS_END),
                    self.ctx.notify("Скопировано — вставьте в C:\\Windows\\System32\\drivers\\etc\\hosts",
                                    "info"))),
                ("Перезапустить от администратора", "primary", self.ctx.relaunch_admin),
            ],
        )

    def _lists_failed(self, message: str) -> None:
        self._updating_lists = False
        self.ipset_button.setEnabled(True)
        self.hosts_button.setEnabled(True)
        self.bypass_label.setText(f"Ошибка обновления: {message}")
        self.ctx.notify(f"Обновление списков: {message}", "err", "error")

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
        exhaustive = self.exhaustive_button.isChecked()
        self.ctx.settings.set("zapret.search_exhaustive", exhaustive)
        if exhaustive:
            action = ("Будут проверены все стратегии и построен полный рейтинг. "
                      "Это занимает несколько минут.")
        else:
            action = ("Поиск остановится на первой стратегии, которая открывает все "
                      "проверяемые сервисы — это самый быстрый режим.")
        if self.engine.status == "running":
            action += (" Сейчас Zapret запущен: на время поиска он будет остановлен, "
                       "а после поиска запущен с лучшей стратегией.")
        else:
            action += (" После поиска лучшая стратегия будет выбрана; Zapret останется "
                       "остановленным до нажатия «Запустить».")
        overlays.confirm(
            self.ctx.overlay,
            "Поиск лучшей стратегии",
            f"Будет поочерёдно проверено <b>{total}</b> стратегий, интернет-обход "
            f"на это время недоступен.<br><br>{action}",
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
        self.exhaustive_button.setEnabled(False)
        self.best_button.setEnabled(True)
        self.best_button.setText("Отменить поиск")
        self.best_label.setText(f"Поиск: 0 из {self._search_total}…")
        self.ctx.sound.play("click")
        run_task(
            self, search_best_strategy, self.engine, list(self._strategies),
            with_progress=True, cancelled=self._search_cancel.is_set,
            stop_on_ok=not self.exhaustive_button.isChecked(),
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
        self.exhaustive_button.setEnabled(True)
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
        if result.early_stop:
            notes.append("Быстрый режим: остановлено на первой полностью рабочей "
                         "стратегии (включите «Полный перебор» для рейтинга всех).")
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
