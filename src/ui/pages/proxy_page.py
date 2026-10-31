"""Shared UI for the headless Happ (Xray) and Hiddify (sing-box) engines."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QListWidgetItem, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox, QVBoxLayout,
    QWidget,
)

from ...engines.base import EngineError
from ...logger import get_logger
from ... import net
from .. import flags, overlays, theme
from ..widgets import (
    Badge, Divider, GlassCard, IconButton, IconOrb, LogView, PrimaryButton, StatTile,
    ToggleRow, human_bytes, human_speed, icon,
)
from ..workers import run_task
from .base_page import STATUS_KIND, STATUS_TEXT, Page, page_heading

log = get_logger("proxy-page")


class ProxyPage(Page):
    """Concrete pages subclass this and provide titles/ports."""

    icon_name = "globe"

    def __init__(self, context, engine, title: str, subtitle: str, source_line: str,
                 core_label: str, parent=None) -> None:
        super().__init__(context, parent)
        self.engine = engine
        self.title = title
        self.subtitle = subtitle
        self.source_line = source_line
        self.core_label = core_label
        self._build()
        self._connect()
        self._refresh_ports()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        p = self.ctx.palette
        self.add(page_heading(self.title, self.subtitle))

        self.hero = GlassCard(strong=True)
        hero_row = QHBoxLayout()
        hero_row.setSpacing(18)
        self.orb = IconOrb(self.icon_name, p, 58)
        hero_row.addWidget(self.orb, 0, Qt.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(4)
        status_row = QHBoxLayout()
        status_row.setSpacing(10)
        self.status_badge = Badge("ВЫКЛЮЧЕНО", "muted")
        status_row.addWidget(self.status_badge, 0, Qt.AlignLeft)
        self.latency_badge = Badge("—", "muted")
        status_row.addWidget(self.latency_badge, 0, Qt.AlignLeft)
        status_row.addStretch(1)
        column.addLayout(status_row)
        self.node_label = QLabel("Сервер не выбран")
        self.node_label.setObjectName("h2")
        self.node_label.setWordWrap(True)
        column.addWidget(self.node_label)
        self.detail_label = QLabel(self.source_line)
        self.detail_label.setObjectName("tiny")
        self.detail_label.setWordWrap(True)
        column.addWidget(self.detail_label)
        actions = QHBoxLayout()
        actions.setSpacing(9)
        self.connect_button = PrimaryButton("Подключиться", "power", p)
        self.connect_button.clicked.connect(self._toggle)
        actions.addWidget(self.connect_button)
        self.sysproxy_row = ToggleRow(
            "Системный прокси",
            "Направить трафик Windows через локальный порт",
            bool(self.ctx.settings.get(f"{self.engine.ns}.sysproxy", False)), p,
        )
        self.sysproxy_row.setMinimumWidth(330)
        self.sysproxy_row.toggled.connect(self._sysproxy_changed)
        actions.addWidget(self.sysproxy_row, 1)
        column.addLayout(actions)
        hero_row.addLayout(column, 1)
        self.hero.body.addLayout(hero_row)
        self.add(self.hero)

        self.sysproxy_card = GlassCard(
            "Трафик Windows идёт напрямую",
            "Системный прокси выключен: браузер и другие программы обходят туннель, "
            "поэтому обычные приложения Windows могут идти напрямую. Включите системный прокси.",
            "alert", p,
        )
        self.sysproxy_card.add_header_widget(Badge("ВНИМАНИЕ", "warn"))
        fix_row = QHBoxLayout()
        fix_row.addStretch(1)
        self.enable_sysproxy_button = PrimaryButton("Включить системный прокси", "power", p)
        self.enable_sysproxy_button.clicked.connect(lambda: self._apply_sysproxy(True))
        fix_row.addWidget(self.enable_sysproxy_button)
        self.sysproxy_card.add_layout(fix_row)
        self.sysproxy_card.setVisible(
            not bool(self.ctx.settings.get(f"{self.engine.ns}.sysproxy", False))
        )
        self.add(self.sysproxy_card)

        self.core_card = GlassCard("Ядро не установлено",
                                   f"Установите {self.core_label} — Zentrix запустит его скрыто.",
                                   "alert", p)
        core_row = QHBoxLayout()
        core_row.addStretch(1)
        self.install_button = PrimaryButton("Скачать ядро", "download", p)
        self.install_button.clicked.connect(self._install_core)
        core_row.addWidget(self.install_button)
        self.core_progress = QProgressBar()
        self.core_progress.setRange(0, 100)
        self.core_progress.setValue(0)
        self.core_progress.hide()
        self.core_card.add(self.core_progress)
        self.core_card.add_layout(core_row)
        self.core_card.hide()
        self.add(self.core_card)

        tiles = QGridLayout()
        tiles.setSpacing(14)
        self.tile_down = StatTile("Скорость ↓", "download", p, "0 Б/с")
        self.tile_up = StatTile("Скорость ↑", "activity", p, "0 Б/с")
        self.tile_conn = StatTile("Соединения", "wifi", p, "0")
        tiles.addWidget(self.tile_down, 0, 0)
        tiles.addWidget(self.tile_up, 0, 1)
        tiles.addWidget(self.tile_conn, 0, 2)
        self.add_layout(tiles)

        body = QHBoxLayout()
        body.setSpacing(14)
        servers = GlassCard("Серверы", "Ссылки vless / vmess / trojan / ss или base64-подписка",
                            "globe", p)
        self.nodes = QListWidget()
        self.nodes.setMinimumHeight(170)
        self.nodes.setIconSize(QSize(26, 18))
        self.nodes.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.nodes.currentRowChanged.connect(self._node_selected)
        servers.add(self.nodes)
        self.node_hint = QLabel("")
        self.node_hint.setObjectName("tiny")
        self.node_hint.setWordWrap(True)
        self.node_hint.hide()
        servers.add(self.node_hint)
        subscription_row = QHBoxLayout()
        subscription_row.setSpacing(8)
        self.subscription_edit = QLineEdit()
        self.subscription_edit.setPlaceholderText("https://… подписка")
        subscription_row.addWidget(self.subscription_edit, 1)
        self.fetch_button = QPushButton("Загрузить")
        self.fetch_button.clicked.connect(self._fetch_subscription)
        subscription_row.addWidget(self.fetch_button)
        servers.add_layout(subscription_row)
        self.links_edit = QPlainTextEdit()
        self.links_edit.setPlaceholderText("vless://…\nvmess://…\n(по одной ссылке на строку)")
        self.links_edit.setFixedHeight(92)
        servers.add(self.links_edit)
        links_row = QHBoxLayout()
        links_row.setSpacing(8)
        save_links = QPushButton("Сохранить ссылки")
        save_links.setProperty("variant", "primary")
        save_links.clicked.connect(self._save_links)
        links_row.addWidget(save_links)
        import_button = QPushButton("Импорт JSON…")
        import_button.clicked.connect(self._import_json)
        links_row.addWidget(import_button)
        clear_button = QPushButton("Очистить")
        clear_button.setProperty("variant", "ghost")
        clear_button.clicked.connect(self._clear_links)
        links_row.addWidget(clear_button)
        links_row.addStretch(1)
        servers.add_layout(links_row)
        body.addWidget(servers, 3)

        params = GlassCard("Параметры подключения", "", "settings", p)
        self.core_state = QLabel("Ядро: не найдено")
        self.core_state.setObjectName("tiny")
        self.core_state.setWordWrap(True)
        params.add(self.core_state)
        ports = QHBoxLayout()
        ports.setSpacing(8)
        self.port_a_label = QLabel("SOCKS")
        self.port_a = QSpinBox()
        self.port_a.setRange(1024, 65535)
        self.port_b_label = QLabel("HTTP")
        self.port_b = QSpinBox()
        self.port_b.setRange(1024, 65535)
        for label, spin in ((self.port_a_label, self.port_a), (self.port_b_label, self.port_b)):
            label.setObjectName("tiny")
            spin.setFixedWidth(88)
        ports.addWidget(self.port_a_label)
        ports.addWidget(self.port_a)
        ports.addSpacing(6)
        ports.addWidget(self.port_b_label)
        ports.addWidget(self.port_b)
        ports.addStretch(1)
        params.add_layout(ports)
        save_ports = QPushButton("Применить порты")
        save_ports.setProperty("variant", "chip")
        save_ports.setFixedHeight(30)
        save_ports.clicked.connect(self._save_ports)
        params.add(save_ports, 0)
        params.add(Divider())
        self.port_hint = QLabel("")
        self.port_hint.setObjectName("tiny")
        self.port_hint.setWordWrap(True)
        params.add(self.port_hint)
        self.auto_row = ToggleRow("Автозапуск в Zentrix",
                                  "Подключаться при старте приложения",
                                  bool(self.ctx.settings.get(f"{self.engine.ns}.autostart", False)), p)
        self.auto_row.toggled.connect(
            lambda value: self.ctx.settings.set(f"{self.engine.ns}.autostart", bool(value))
        )
        params.add(self.auto_row)
        latency_button = QPushButton("Проверить задержку")
        latency_button.setIcon(icon("activity", p.accent, 18))
        latency_button.clicked.connect(self._measure_latency)
        params.add(latency_button)
        params.addStretch(1)
        body.addWidget(params, 2)
        self.add_layout(body)

        log_card = GlassCard("Журнал ядра", "stdout/stderr процесса", "activity", p)
        tools = QHBoxLayout()
        tools.addStretch(1)
        copy_button = IconButton("copy", p, "Копировать журнал")
        copy_button.clicked.connect(self._copy_log)
        clear_button = IconButton("trash", p, "Очистить")
        clear_button.clicked.connect(lambda: self.log.clear())
        tools.addWidget(copy_button)
        tools.addWidget(clear_button)
        log_card.add_layout(tools)
        self.log = LogView(p)
        self.log.setMinimumHeight(180)
        log_card.add(self.log)
        self.add(log_card)
        self.finish()

    def _connect(self) -> None:
        self.engine.status_changed.connect(self._on_status)
        self.engine.stats_changed.connect(self._on_stats)
        self.engine.log_line.connect(self.log.append_line)
        self.engine.error.connect(lambda title, msg: self.ctx.notify(f"{title}: {msg}", "err", "error"))

    # ------------------------------------------------------------------- show
    def on_show(self) -> None:
        self.engine.ensure_profile_from_settings()
        self._reload_nodes()
        self._refresh()
        if not self.engine.core_installed():
            self.core_card.show()
        self.hero.setVisible(True)

    def on_theme(self) -> None:
        p = self.ctx.palette
        self.orb.set_palette(p)
        self.log.set_palette(p)

    # -------------------------------------------------------------- node list
    def _reload_nodes(self, select: int | None = None) -> None:
        nodes = self.engine.nodes()
        self.nodes.blockSignals(True)
        self.nodes.clear()
        for node in nodes:
            label = flags.strip_flag_emoji(node.label)
            item = QListWidgetItem(f"{label}   ·   {node.summary()}")
            item.setData(Qt.UserRole, node.summary())
            node_icon = flags.flag_icon(flags.detect_country(node.label), 16)
            if node_icon is None:
                node_icon = icon("globe", self.ctx.palette.muted, 16)
            item.setIcon(node_icon)
            self.nodes.addItem(item)
        index = self.engine.selected_index() if select is None else select
        if nodes:
            self.nodes.setCurrentRow(max(0, min(index, len(nodes) - 1)))
        self.nodes.blockSignals(False)
        self._node_selected(self.nodes.currentRow())
        if not nodes:
            self.links_edit.setPlainText(self.engine.profile_text())

    def _node_selected(self, row: int) -> None:
        if row < 0:
            self.node_label.setText("Сервер не выбран")
            self.node_hint.hide()
            return
        nodes = self.engine.nodes()
        if row >= len(nodes):
            self.node_hint.hide()
            return
        self.engine.select_node(row)
        node = nodes[row]
        self.node_label.setText(f"{flags.strip_flag_emoji(node.label)} · {node.summary()}")
        self.detail_label.setText(
            f"{node.protocol.upper()} · {node.transport_label}"
            + (f" · SNI {node.sni}" if node.sni else "")
        )
        self._update_node_hint(node)
        if self.engine.status == "running":
            self.ctx.notify("Сервер выбран. Перезапустите подключение, чтобы применить.", "info")

    def _update_node_hint(self, node) -> None:
        hints: list[str] = []
        if self.engine.core_kind == "singbox":
            if node.network in {"xhttp", "splithttp"}:
                hints.append(
                    "XHTTP не поддерживается sing-box. Выберите Xray "
                    "или узел WS/TCP."
                )
            elif node.security == "reality":
                hints.append(
                    "Reality может не работать в sing-box. Если подключение не "
                    "устанавливается, выберите узел Резерв (WS/TLS) или движок Xray."
                )
        self.node_hint.setText(" ".join(hints))
        self.node_hint.setVisible(bool(hints))

    # ------------------------------------------------------------------ links
    def _save_links(self) -> None:
        text = self.links_edit.toPlainText().strip()
        if not text:
            self.ctx.notify("Вставьте хотя бы одну ссылку", "warn")
            return
        try:
            count = self.engine.set_profile_text(text)
        except Exception as exc:
            self.ctx.notify(f"Не удалось сохранить: {exc}", "err")
            return
        self._reload_nodes(select=0)
        if count:
            self.ctx.notify(f"Добавлено серверов: {count}", "ok")
            self.links_edit.clear()
        else:
            self.ctx.notify("Ссылки не распознаны. Поддержка: vless, vmess, trojan, ss.", "warn")

    def _clear_links(self) -> None:
        self.engine.set_profile_text("")
        self.links_edit.clear()
        self._reload_nodes()
        self.ctx.notify("Профиль очищен", "info")

    def _fetch_subscription(self) -> None:
        url = self.subscription_edit.text().strip()
        if not url.lower().startswith(("http://", "https://")):
            self.ctx.notify("Укажите http(s)-ссылку на подписку", "warn")
            return
        self.fetch_button.setEnabled(False)
        run_task(
            self, self.engine.fetch_subscription, url,
            on_done=self._subscription_loaded,
            on_error=lambda msg: self._subscription_failed(msg),
        )

    def _subscription_loaded(self, count: int) -> None:
        self.fetch_button.setEnabled(True)
        self._reload_nodes()
        self.ctx.notify(f"Подписка загружена · серверов: {count}", "ok")

    def _subscription_failed(self, message: str) -> None:
        self.fetch_button.setEnabled(True)
        self.ctx.notify(f"Подписка: {message}", "err", "error")

    def _import_json(self) -> None:
        path, _ = QFileDialog.getOpenFileName(self, "Импорт профиля", "", "JSON (*.json);;Все файлы (*.*)")
        if not path:
            return
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            count = self.engine.set_profile_text(text)
        except Exception as exc:
            self.ctx.notify(str(exc), "err")
            return
        self.links_edit.clear()
        self._reload_nodes(0)
        self.ctx.notify(f"Импортировано серверов: {count}", "ok" if count else "warn")

    # ------------------------------------------------------------------ cores
    def _install_core(self) -> None:
        if getattr(self, "_installing", False):
            return
        self._installing = True
        self.install_button.setEnabled(False)
        self.core_progress.show()
        self.core_progress.setValue(0)
        self.ctx.notify(f"Скачивание {self.core_label}…", "info")
        run_task(
            self, self.engine.install_core, with_progress=True,
            on_done=self._core_installed, on_error=self._core_failed,
            on_progress=self._core_progress,
        )

    def _core_progress(self, done: int, total: int) -> None:
        if total:
            self.core_progress.setValue(int(done * 100 / total))
        else:
            self.core_progress.setValue(min(90, self.core_progress.value() + 2))

    def _core_installed(self, path) -> None:
        self._installing = False
        self.install_button.setEnabled(True)
        self.core_progress.hide()
        self.core_card.hide()
        self._refresh()
        self.ctx.notify("Ядро установлено", "ok", "update")

    def _core_failed(self, message: str) -> None:
        self._installing = False
        self.install_button.setEnabled(True)
        self.core_progress.hide()
        self.ctx.notify(f"Не удалось скачать ядро: {message}", "err", "error")

    # ------------------------------------------------------------------ ports
    def _refresh_ports(self) -> None:
        primary, secondary = self.engine.ports()
        self.port_a.setValue(primary)
        self.port_b.setValue(secondary)
        host = "127.0.0.1"
        if self.ctx.settings.get("vpn.share", False):
            addresses = net.lan_ipv4_addresses()
            host = addresses[0] if addresses else "IP LAN не найден"
        self.port_hint.setText(
            f"Локальный прокси: {host}:{primary}" if self.engine.core_kind == "singbox"
            else f"SOCKS {host}:{primary} · HTTP {host}:{secondary}"
        )

    def _save_ports(self) -> None:
        primary, secondary = self.port_a.value(), self.port_b.value()
        if primary == secondary:
            self.ctx.notify("Порты должны различаться", "warn")
            return
        if self.engine.core_kind == "xray":
            self.ctx.settings.update("happ", {"socks_port": primary, "http_port": secondary})
        else:
            self.ctx.settings.update("hiddify", {"mixed_port": primary, "api_port": secondary})
        self._refresh_ports()
        hint = "Перезапустите подключение" if self.engine.status == "running" else "Порты сохранены"
        self.ctx.notify(hint, "info")

    # ---------------------------------------------------------------- connect
    def _toggle(self) -> None:
        if self.engine.status == "running":
            self.connect_button.setEnabled(False)
            run_task(self, self.engine.stop,
                     on_done=lambda _: self._after_toggle(False),
                     on_error=lambda msg: self._error(msg))
            return
        if not self.engine.core_installed():
            self.core_card.show()
            self.ctx.notify("Сначала скачайте ядро", "warn")
            return
        if not self.engine.nodes():
            self.ctx.notify("Добавьте сервер или загрузите подписку", "warn")
            return
        self.connect_button.setEnabled(False)
        run_task(self, self.engine.start,
                 on_done=lambda _: self._after_toggle(True),
                 on_error=lambda msg: self._error(msg))

    def _after_toggle(self, connected: bool) -> None:
        self.connect_button.setEnabled(True)
        self._refresh()
        if connected and self.engine.status == "running":
            if self.ctx.settings.get(f"{self.engine.ns}.sysproxy", False):
                self.ctx.notify(f"{self.title}: подключено", "ok", "enable")
            else:
                self.ctx.notify(
                    f"{self.title}: подключено, но системный прокси выключен — "
                    "2ip.io покажет прежний IP.",
                    "warn", "enable",
                )
            self.ctx.sound.play("enable")
        elif not connected:
            self.ctx.sound.play("disable")

    def _error(self, message: str) -> None:
        self.connect_button.setEnabled(True)
        self._refresh()
        self.ctx.notify(message, "err", "error")

    def _sysproxy_changed(self, value: bool) -> None:
        self._apply_sysproxy(bool(value))

    def _apply_sysproxy(self, value: bool) -> None:
        self.ctx.settings.set(f"{self.engine.ns}.sysproxy", bool(value))
        self.sysproxy_row.set_checked(bool(value))
        if self.engine.status == "running":
            self.engine.set_system_proxy(bool(value))
            self.ctx.notify("Системный прокси " + ("включён" if value else "выключен"),
                            "ok" if value else "info")
        else:
            self.ctx.notify(
                "Системный прокси будет включён при подключении" if value
                else "Системный прокси выключен",
                "info",
            )
        self._refresh()

    def _measure_latency(self) -> None:
        if self.engine.status != "running":
            self.ctx.notify("Сначала подключитесь", "warn")
            return
        self.latency_badge.update_badge("…", "info")
        run_task(self, self.engine.latency, on_done=self._latency_done,
                 on_error=lambda msg: self.latency_badge.update_badge("ошибка", "err"))

    def _latency_done(self, value) -> None:
        if value is None:
            self.latency_badge.update_badge("нет ответа", "err")
        else:
            kind = "ok" if value < 800 else ("warn" if value < 2000 else "err")
            self.latency_badge.update_badge(f"{value} мс", kind)

    # ----------------------------------------------------------------- status
    def _on_status(self, status: str, message: str) -> None:
        self.status_badge.update_badge(STATUS_TEXT.get(status, status).upper(),
                                       STATUS_KIND.get(status, "muted"))
        self.detail_label.setText(message or self.source_line)
        running = status == "running"
        self.connect_button.setText("Отключиться" if running else "Подключиться")
        self.connect_button.setProperty("variant", "danger" if running else "primary")
        self.connect_button.style().unpolish(self.connect_button)
        self.connect_button.style().polish(self.connect_button)
        self.connect_button.setIcon(icon("stop" if running else "power", "#FFFFFF", 18))
        self.connect_button.setEnabled(True)

    def _on_stats(self, data: dict) -> None:
        self.tile_down.set_value(human_speed(data.get("down", 0)),
                                 f"{human_bytes(data.get('total_down', 0))} всего")
        self.tile_up.set_value(human_speed(data.get("up", 0)),
                               f"{human_bytes(data.get('total_up', 0))} всего")
        self.tile_conn.set_value(str(data.get("connections", 0)), f"PID {data.get('pid', '—')}")

    def _refresh(self) -> None:
        core = self.engine.core_path()
        if core:
            self.core_state.setText(f"Ядро: {core}\n{self.engine.info().get('core_version', '')}")
            self.core_card.hide()
        else:
            self.core_state.setText("Ядро: не найдено")
            self.core_card.show()
        self._on_status(self.engine.status, self.engine._message)
        self._refresh_ports()
        if not self.engine.nodes():
            self.node_label.setText("Сервер не выбран")
            self.node_hint.hide()
        sysproxy_on = bool(self.ctx.settings.get(f"{self.engine.ns}.sysproxy", False))
        self.sysproxy_row.set_checked(sysproxy_on)
        self.sysproxy_card.setVisible(not sysproxy_on)
        self.auto_row.set_checked(bool(self.ctx.settings.get(f"{self.engine.ns}.autostart", False)))

    def _copy_log(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.log.toPlainText())
        self.ctx.notify("Журнал скопирован", "ok")
