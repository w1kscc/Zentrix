"""Tools page: network repair, DNS switching, hosts editor, diagnostics, Game Mode."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QFrame, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from ... import nettools
from ...logger import get_logger
from ...engines import game_scan
from .. import overlays, theme
from ..game_mode import GameModeMonitor
from ..widgets import Badge, Divider, GlassCard, PrimaryButton, ToggleRow, icon
from ..workers import run_task
from .base_page import Page, page_heading

log = get_logger("tools-page")

SECTIONS = (
    ("repair", "Починить сеть", "wrench"),
    ("dns", "Смена DNS", "globe"),
    ("hosts", "Hosts-файл", "file"),
    ("diag", "Диагностика", "activity"),
    ("games", "Game Mode", "bolt"),
)

AD_PROMO_LIST = [
    "ads.adfox.ru", "an.yandex.ru", "ads.pubmatic.com", "ad.2030.pl",
    "ads.xnet.ru", "ctbucket.net", "tnkexchange.com", "adriver.ru",
    "awaps.yandex.net", "ads.sape.ru", "yandexadexchange.net",
]

DNS_PRESET_ROWS = (
    ("auto", "DHCP (автоматически)"),
    ("cloudflare", "Cloudflare"),
    ("google", "Google"),
    ("adguard", "AdGuard (реклама в.strip)"),
)


class ToolsPage(Page):
    key = "tools"

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        self._section_buttons: list[QPushButton] = []
        self._sections: list[QWidget] = []
        self._build()
        self.on_theme()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        p = self.ctx.palette
        self.add(page_heading("Инструменты", "Уход за сетью: DNS, hosts, диагностика, игры"))

        nav = QWidget()
        nav_layout = QHBoxLayout(nav)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(6)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for index, (_key, label, icon_name) in enumerate(SECTIONS):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setProperty("variant", "chip")
            button.setFixedHeight(34)
            button.setCursor(Qt.PointingHandCursor)
            button.setIcon(icon(icon_name, p.accent, 17))
            button.setIconSize(QSize(17, 17))
            self._group.addButton(button, index)
            self._section_buttons.append(button)
            nav_layout.addWidget(button)
        nav_layout.addStretch(1)
        self._group.idClicked.connect(self._switch_section)
        self.add(nav)
        self._section_buttons[0].setChecked(True)

        self.section_host = QWidget()
        self.section_layout = QVBoxLayout(self.section_host)
        self.section_layout.setContentsMargins(0, 0, 0, 0)
        self.section_layout.setSpacing(0)
        self._sections = [
            self._build_repair(),
            self._build_dns(),
            self._build_hosts(),
            self._build_diag(),
            self._build_games(),
        ]
        self._attach_section(0)
        self.finish()

    def _attach_section(self, index: int) -> None:
        while self.section_layout.count():
            item = self.section_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        self.section_layout.addWidget(self._sections[index])

    def _switch_section(self, index: int) -> None:
        self._attach_section(index)

    def _card(self, title: str, subtitle: str, icon_name: str) -> GlassCard:
        return GlassCard(title, subtitle, icon_name, self.ctx.palette)

    # ----------------------------------------------------------------- repair
    def _build_repair(self) -> QWidget:
        p = self.ctx.palette
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        adapter_card = self._card("Адаптер", "Выберите интерфейс или оставьте авто", "globe", )
        row = QHBoxLayout()
        row.setSpacing(8)
        self.adapter_combo = QLineEdit()
        self.adapter_combo.setPlaceholderText("Определяется автоматически…")
        row.addWidget(self.adapter_combo, 1)
        refresh = QPushButton("Найти адаптеры")
        refresh.setProperty("variant", "chip")
        refresh.clicked.connect(self._refresh_adapters)
        row.addWidget(refresh)
        adapter_card.add_layout(row)
        layout.addWidget(adapter_card)

        actions_card = self._card("Ремонт сети",
                                  "Очистка кэша DNS, сброс Winsock и IP-стека", "wrench", p)
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(8)
        flush = PrimaryButton("Очистить DNS-кэш", "trash", p)
        flush.clicked.connect(self._flush_dns)
        buttons_row.addWidget(flush)
        winsock = QPushButton("Сбросить Winsock")
        winsock.setProperty("variant", "chip")
        winsock.clicked.connect(self._reset_winsock)
        buttons_row.addWidget(winsock)
        full = QPushButton("Полный ремонт")
        full.setProperty("variant", "chip")
        full.clicked.connect(self._full_repair)
        buttons_row.addWidget(full)
        buttons_row.addStretch(1)
        actions_card.add_layout(buttons_row)
        self.repair_note = QLabel("Заметка: сброс Winsock требует перезагрузки Windows.")
        self.repair_note.setObjectName("tiny")
        self.repair_note.setWordWrap(True)
        actions_card.add(self.repair_note)
        layout.addWidget(actions_card)
        layout.addStretch(1)
        return body

    def _refresh_adapters(self) -> None:
        def load() -> list[dict]:
            return nettools.adapter_list()

        def done(adapters: list[dict]) -> None:
            if not adapters:
                self.adapter_combo.setText("")
                self.ctx.notify("Активные адаптеры не найдены", "warn")
                return
            first = adapters[0]
            self.adapter_combo.setText(str(first.get("name", "")))

        self._search_adapters = run_task(self, load, on_done=done,
                                         on_error=lambda _m: None)

    def _flush_dns(self) -> None:
        run_task(self, nettools.flush_dns_cache, on_done=self._report_step,
                 on_error=lambda message: self.ctx.notify(f"DNS: {message}", "err", "error"))

    def _reset_winsock(self) -> None:
        if not self.ctx.admin():
            self._admin_first("Сброс Winsock")
            return
        run_task(self, nettools.reset_winsock, on_done=self._report_step,
                 on_error=lambda message: self.ctx.notify(f"Winsock: {message}", "err", "error"))

    def _full_repair(self) -> None:
        if not self.ctx.admin():
            self._admin_first("Полный ремонт сети")
            return

        def worker(progress=None) -> dict:
            return nettools.network_repair(
                adapter=str(self.adapter_combo.text()).strip() or None,
                progress=progress, cycle_adapter=False, )

        run_task(self, worker, with_progress=True, on_done=self._report_step,
                 on_error=lambda message: self.ctx.notify(f"Ремонт: {message}", "err", "error"))

    def _report_step(self, report: dict) -> None:
        text = report.get("message") or report.get("error") or "Готово"
        ok = bool(report.get("ok", True))
        self.ctx.notify(str(text), "ok" if ok else "err", None)

    def _admin_first(self, title: str) -> None:
        overlays.confirm(
            self.ctx.overlay, "Требуются права администратора",
            f"«{title}» меняет сетевые настройки Windows.<br><br>"
            "Zentrix перезапустится с повышенными правами, настройки сохранятся.",
            "Перезапустить от администратора", self.ctx.relaunch_admin,
        )

    # -------------------------------------------------------------------- dns
    def _build_dns(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        current = self._card("Текущий DNS", "Системный DNS выбранного адаптера", "globe")
        self.dns_current = QLabel("Определяется…")
        self.dns_current.setObjectName("h2")
        current.add(self.dns_current)
        layout.addWidget(current)

        presets = self._card("Готовые профили", "Один клик — и DNS заменён", "target")
        grp = QButtonGroup(self)
        grp.setExclusive(False)
        grid = QHBoxLayout()
        grid.setSpacing(8)
        self._dns_chips: list[QPushButton] = []
        for key, label in DNS_PRESET_ROWS:
            chip = QPushButton(label)
            chip.setCheckable(True)
            chip.setProperty("variant", "chip")
            chip.setCursor(Qt.PointingHandCursor)
            chip.clicked.connect(lambda _=False, k=key: self._apply_dns_preset(k))
            grid.addWidget(chip)
        grid.addStretch(1)
        presets.add_layout(grid)
        presets_row = QHBoxLayout()
        presets_row.addStretch(1)
        hint = QLabel("Смена DNS требует прав администратора…")
        hint.setObjectName("tiny")
        presets_row.addWidget(hint)
        presets.add_layout(presets_row)
        layout.addWidget(presets)
        layout.addStretch(1)
        self.on_theme()
        return body

    def _apply_dns_preset(self, key: str) -> None:
        if not self.ctx.admin():
            for chip in self._dns_chips:
                chip.setChecked(False)
            self._admin_first("Смена DNS")
            return

        def worker() -> dict:
            return nettools.set_dns(key)

        run_task(self, worker, on_done=self._dns_done,
                 on_error=lambda message: self.ctx.notify(f"DNS: {message}", "err", "error"))

    def _dns_done(self, report: dict) -> None:
        if report.get("ok"):
            self.ctx.notify(f"DNS изменён: {', '.join(report.get('applied') or [])}",
                            "ok", "update")
            self._refresh_dns_current()
        else:
            self.ctx.notify(f"DNS не изменён: {report.get('error', '?')}", "err", "error")

    def _refresh_dns_current(self) -> None:
        def load() -> dict:
            return nettools.current_dns()

        def done(info: dict) -> None:
            servers = ", ".join(info.get("servers") or []) or "DHCP (не задан статически)"
            self.dns_current.setText(f"{info.get('adapter', '?')} · {servers}")

        run_task(self, load, on_done=done, on_error=lambda _m: None)

    # ------------------------------------------------------------------ hosts
    def _build_hosts(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        info = self._card("Hosts-файл Windows", "%WINDIR%\\System32\\drivers\\etc\\hosts", "file")
        self.hosts_info = QLabel("—")
        self.hosts_info.setObjectName("tiny")
        info.add(self.hosts_info)
        layout.addWidget(info)

        group_card = self._card("Группы Zentrix",
                                "Блокировка доменов через hosts одним тумблером", "shield")
        self.hosts_rows: list[QWidget] = []
        self.groups_box = QVBoxLayout()
        self.groups_box.setSpacing(6)
        group_card.add_layout(self.groups_box)
        new_row = QHBoxLayout()
        new_row.setSpacing(8)
        add_pb = PrimaryButton("Добавить группу", "file", self.ctx.palette)
        add_pb.clicked.connect(self._add_hosts_group)
        new_row.addWidget(add_pb)
        promo = QPushButton("Заблокировать рекламу")
        promo.setProperty("variant", "chip")
        promo.clicked.connect(self._add_promo_group)
        new_row.addWidget(promo)
        new_row.addStretch(1)
        group_card.add_layout(new_row)
        hint = QLabel("Изменения выполняются если запись помечена маркером Zentrix")
        hint.setObjectName("tiny")
        group_card.add(hint)
        layout.addWidget(group_card)
        layout.addStretch(1)
        return body

    def _reload_hosts(self) -> None:
        def load() -> list[dict]:
            return nettools.read_hosts()

        def done(entries: list[dict]) -> None:
            while self.groups_box.count():
                item = self.groups_box.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            hosts_file = nettools.hosts_path()
            self.hosts_info.setText(str(hosts_file))
            groups = [e for e in entries if e.get("type") == "zentrix"]
            if not groups:
                label = QLabel("Своих групп нет — hosts не изменялся")
                label.setObjectName("tiny")
                self.groups_box.addWidget(label)
                return
            for group in groups:
                row = QWidget()
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(8)
                total = len(group.get("entries") or [])
                toggle = QCheckBox(group.get("group_title", group.get("group_id", "Группа")))
                toggle.setChecked(bool(group.get("enabled", True)))
                toggle.setToolTip(str(group.get("group_id", "")))
                row_layout.addWidget(toggle)
                count = QLabel(f"доменов: {total}")
                count.setObjectName("tiny")
                row_layout.addWidget(count)
                row_layout.addStretch(1)
                delete = QPushButton("Удалить")
                delete.setProperty("variant", "chip")
                delete.setFixedHeight(28)
                gid = group.get("group_id")
                delete.clicked.connect(lambda _=False, g=gid: self._remove_hosts_group(g))
                toggle.clicked.connect(
                    lambda checked=False, g=gid, enabled=toggle.isChecked():
                        self._toggle_hosts_group(g, not enabled))
                row_layout.addWidget(delete)
                self.groups_box.addWidget(row)

        run_task(self, load, on_done=done, on_error=lambda _message: None)

    def _add_promo_group(self) -> None:
        self._apply_group("promo", "Реклама и трекеры (Zentrix)",
                          [("0.0.0.0", host) for host in AD_PROMO_LIST], True)

    def _add_hosts_group(self) -> None:
        title, ok = QInputDialog.getText(self, "Новая группа hosts",
                                         "Название группы:")
        if not ok or not title.strip():
            return
        text, ok = QInputDialog.getMultiLineText(
            self, "Домены группы", "По одному домену в строке:")
        if not ok or not text.strip():
            return
        entries = []
        for line in text.splitlines():
            domain = line.strip().remove_prefix("0.0.0.0 ").strip()
            host = domain.remove_prefix("http://").remove_prefix("https://").strip("/\\")
            if host:
                entries.append(("0.0.0.0", host))
        if not entries:
            self.ctx.notify("Введите хотя бы один домен", "warn")
            return
        group_id = f"custom-{abs(hash(title.strip())) % 100000}"
        self._apply_group(group_id, title.strip(), entries, True)

    def _apply_group(self, group_id: str, title: str, entries: list, enabled: bool) -> None:
        if not self.ctx.admin():
            self._admin_first("Редактирование hosts")
            return

        def worker() -> dict:
            return nettools.apply_hosts_group(group_id, title, entries, enabled)

        def done(report: dict) -> None:
            if report.get("ok"):
                self.ctx.notify("Hosts обновлён", "ok", "update")
                self._reload_hosts()
            else:
                self.ctx.notify(f"Hosts: {report.get('error', 'ошибка')}", "err", "error")

        run_task(self, worker, on_done=done,
                 on_error=lambda message: self.ctx.notify(f"Hosts: {message}", "err", "error"))

    def _toggle_hosts_group(self, group_id: str, enabled: bool) -> None:
        def load() -> list[dict]:
            return nettools.read_hosts()

        def toggle(entries: list[dict]) -> None:
            for group in entries:
                if group.get("type") == "zentrix" and group.get("group_id") == group_id:
                    self._apply_group(group_id, str(group.get("group_title", group_id)),
                                      group.get("entries") or [], enabled)
                    return
            self.ctx.notify("Группа уже удалена", "warn")

        run_task(self, load, on_done=toggle, on_error=lambda _m: None)

    def _remove_hosts_group(self, group_id: str | None) -> None:
        if not group_id:
            return

        def worker() -> dict:
            return nettools.apply_hosts_group(group_id, "", [], False, remove=True)

        def done(report: dict) -> None:
            if report.get("ok"):
                self.ctx.notify("Группа удалена", "ok", None)
                self._reload_hosts()
            else:
                self.ctx.notify(f"Hosts: {report.get('error', 'ошибка')}", "err", "error")

        run_task(self, worker, on_done=done, on_error=lambda _message: None)

    # ------------------------------------------------------------------- diag
    def _build_diag(self) -> QWidget:
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = self._card("Диагностика узла", "ping · traceroute · whois · порт-скан", "target")
        row = QHBoxLayout()
        row.setSpacing(8)
        self.diag_host = QLineEdit()
        self.diag_host.setPlaceholderText("youtube.com или 1.1.1.1")
        row.addWidget(self.diag_host, 1)
        self.diag_ports = QLineEdit()
        self.diag_ports.setPlaceholderText("порты: 80, 443, 1233-1240")
        self.diag_ports.setFixedWidth(210)
        row.addWidget(self.diag_ports)
        card.add_layout(row)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        ping = PrimaryButton("Ping", "activity", self.ctx.palette)
        ping.clicked.connect(self._diag_ping)
        buttons.addWidget(ping)
        trace = QPushButton("Traceroute")
        trace.setProperty("variant", "chip")
        trace.clicked.connect(self._diag_trace)
        buttons.addWidget(trace)
        whois = QPushButton("Whois")
        whois.setProperty("variant", "chip")
        whois.clicked.connect(self._diag_whois)
        buttons.addWidget(whois)
        scan = QPushButton("Порт-скан")
        scan.setProperty("variant", "chip")
        scan.clicked.connect(self._diag_scan)
        buttons.addWidget(scan)
        buttons.addStretch(1)
        card.add_layout(buttons)

        self.diag_output = QPlainTextEdit()
        self.diag_output.setObjectName("logView")
        self.diag_output.setReadOnly(True)
        self.diag_output.setMinimumHeight(220)
        card.add(self.diag_output)
        layout.addWidget(card)
        return body

    def _diag_target(self) -> str | None:
        host = self.diag_host.text().strip()
        if not host:
            self.ctx.notify("Укажите домен или IP-адрес", "warn")
            return None
        return host

    def _diag_ping(self) -> None:
        target = self._diag_target()
        if not target:
            return
        self.diag_output.setPlainText("Выполняется ping…")
        run_task(self, nettools.ping, target, 4, on_done=self._diag_result,
                 on_error=lambda message: self._diag_error(message))

    def _diag_trace(self) -> None:
        target = self._diag_target()
        if not target:
            return
        self.diag_output.setPlainText("Выполняется traceroute (может занять минуту)…")
        run_task(self, nettools.traceroute, target, on_done=self._diag_result,
                 on_error=lambda message: self._diag_error(message))

    def _diag_whois(self) -> None:
        target = self._diag_target()
        if not target:
            return
        self.diag_output.setPlainText("Запрос RDAP/whois…")
        run_task(self, nettools.whois, target, on_done=self._diag_result,
                 on_error=lambda message: self._diag_error(message))

    def _parse_ports(self, text: str) -> list[int]:
        ports: list[int] = []
        for part in text.replace(",", " ").split():
            if "-" in part:
                low, _, high = part.partition("-")
                if low.isdigit() and high.isdigit():
                    ports.extend(range(int(low), int(high) + 1))
            elif part.isdigit():
                ports.append(int(part))
        return sorted({p for p in ports if 1 <= p <= 65535})[:2048]

    def _diag_scan(self) -> None:
        target = self._diag_target()
        if not target:
            return
        ports = self._parse_ports(self.diag_ports.text())
        if not ports:
            self.ctx.notify("Укажите порты, например: 80, 443", "warn")
            return
        self.diag_output.setPlainText(f"Сканируем {len(ports)} портов…")
        run_task(self, nettools.port_scan, target, ports, on_done=self._diag_result,
                 on_error=lambda message: self._diag_error(message))

    def _diag_result(self, payload) -> None:
        def render(value, indent: int = 0) -> str:
            pad = "  " * indent
            if isinstance(value, dict):
                lines = []
                for key, item in value.items():
                    if isinstance(item, (dict, list)):
                        lines.append(f"{pad}{key}:")
                        lines.append(render(item, indent + 1))
                    else:
                        lines.append(f"{pad}{key}: {item}")
                return "\n".join(lines)
            if isinstance(value, list):
                return "\n".join(f"{pad}- {render(item, indent)}" if isinstance(item, (dict, list))
                                 else f"{pad}- {item}" for item in value)
            return f"{pad}{value}"

        self.diag_output.setPlainText(render(payload))

    def _diag_error(self, message: str) -> None:
        self.diag_output.setPlainText(f"Ошибка: {message}")

    # ------------------------------------------------------------------ games
    def _build_games(self) -> QWidget:
        p = self.ctx.palette
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        card = self._card("Game Mode", "Приоритет играм и план питания — на максимум", "bolt")
        self.game_state_label = QLabel("Следим за процессами игр…")
        self.game_state_label.setObjectName("tiny")
        toggle = ToggleRow("Включать Game Mode автоматически", "",
                           bool(self.ctx.settings.get("games.mode", False)), p)
        toggle.toggled.connect(self._toggle_game_mode)
        card.add(toggle)
        self.game_state = self.ctx.game_mode.state_changed
        self.game_badge = Badge("ВЫКЛЮЧЕН", "muted")
        card.add_header_widget(self.game_badge)

        scan_row = QHBoxLayout()
        scan_row.setSpacing(8)
        scan = PrimaryButton("Найти игры", "search", p)
        scan.clicked.connect(self._scan_games)
        scan_row.addWidget(scan)
        manual = QPushButton("Добавить exe вручную")
        manual.setProperty("variant", "chip")
        manual.clicked.connect(self._add_manual_game)
        scan_row.addWidget(manual)
        scan_row.addStretch(1)
        card.add_layout(scan_row)

        self.games_box = QVBoxLayout()
        self.games_box.setSpacing(4)
        card.add_layout(self.games_box)
        note = QLabel("Zapret можно совместить: на вкладке Zapret есть игровой фильтр портов.")
        note.setObjectName("tiny")
        card.add(note)
        layout.addWidget(card)
        layout.addStretch(1)
        self.ctx.game_mode.state_changed.connect(self._game_mode_state)
        self.game_mode_state()
        return body

    # -------------------------------------------------------------- actions
    def _toggle_game_mode(self, checked: bool) -> None:
        self.ctx.settings.set("games.mode", bool(checked))
        self.ctx.notify("Game Mode " + ("включён" if checked else "выключен"),
                        "ok" if checked else "info", None)
        self.game_mode_state()

    def _game_mode_state(self, active: bool = False, message: str = "") -> None:
        mode = bool(self.ctx.settings.get("games.mode", False))
        kind = "ok" if (mode and active) else ("warn" if mode else "muted")
        text = "ИГРАЕТ" if (mode and active) else ("ОЖИДАНИЕ" if mode else "ВЫКЛЮЧЕН")
        self.game_badge.update_badge(text, kind)
        if message:
            self.game_state_label.setText(message)
            self.game_state_label.setToolTip(message)

    def _scan_games(self) -> None:
        def load() -> list:
            return game_scan.scan_games()

        def done(games: list) -> None:
            while self.games_box.count():
                item = self.games_box.takeAt(0)
                widget = item.widget()
                if widget:
                    widget.deleteLater()
            selected = [str(i).lower() for i in (self.ctx.settings.get("games.exes") or [])]
            if not games:
                label = QLabel("Игры не найдены на диске")
                label.setObjectName("tiny")
                self.games_box.addWidget(label)
            for game in games[:40]:
                exe_name = str(game.exe).rsplit("\\", 1)[-1]
                row_widget = QWidget()
                row_layout = QHBoxLayout(row_widget)
                row_layout.setContentsMargins(0, 0, 0, 0)
                row_layout.setSpacing(8)
                box = QCheckBox(f"{game.name} ({exe_name})")
                box.setChecked(exe_name.lower() in selected)
                box.toggled.connect(
                    lambda checked, p=str(game.exe): self._toggle_game(p, checked))
                row_layout.addWidget(box, 1)
                self.games_box.addWidget(row_widget)
            if games:
                self.ctx.notify(f"Найдено игр: {len(games)}", "ok", None)

        run_task(self, load, on_done=done, on_error=lambda _m: None)

    def _add_manual_game(self) -> None:
        from PySide6.QtWidgets import QFileDialog

        path, _filter = QFileDialog.getOpenFileName(self, "Выберите exe игры", "",
                                                    "Приложения (*.exe)")
        if not path:
            return
        selected = [str(i) for i in (self.ctx.settings.get("games.exes") or [])]
        if path not in selected:
            selected.append(path)
            self.ctx.settings.set("games.exes", selected)
        self.ctx.notify("Игра добавлена в Game Mode", "ok", None)

    def _toggle_game(self, exe_path: str, checked: bool) -> None:
        selected = [str(i) for i in (self.ctx.settings.get("games.exes") or [])]
        if checked and exe_path not in selected:
            selected.append(exe_path)
        elif not checked and exe_path in selected:
            selected.remove(exe_path)
        self.ctx.settings.set("games.exes", selected)

    # ------------------------------------------------------------------ theme
    def on_show(self) -> None:
        self._refresh_dns_current()
        self._reload_hosts()
        self._restore_selected_games()
        self.game_mode_state()

    def _restore_selected_games(self) -> None:
        """Show the checkbox list without rediscovering every time."""
        selected = [str(i) for i in (self.ctx.settings.get("games.exes") or [])]
        if not selected or self.games_box.count() > 1:
            return
        for exe in selected:
            shown = QWidget()
            shown_layout = QHBoxLayout(shown)
            shown_layout.setContentsMargins(0, 0, 0, 0)
            shown_layout.setSpacing(8)
            label = QLabel(f"Выбрано вручную: {exe.rsplit(chr(92), 1)[-1]}")
            label.setObjectName("tiny")
            shown_layout.addWidget(label, 1)
            self.games_box.addWidget(shown)

    def on_theme(self) -> None:
        for button in self._section_buttons:
            button.setIcon(icon(("wrench", "globe", "file", "activity", "bolt")[
                self._section_buttons.index(button)], self.ctx.palette.accent, 17))
