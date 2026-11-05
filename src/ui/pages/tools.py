"""Level-2 page: network repair, DNS presets, hosts editor, diagnostics,
Game Mode. Actions first, settings next, logs last."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ... import nettools
from ..widgets import Badge, GlassCard
from ..workers import run_task
from .base_page import Page, page_heading


class ToolsPage(Page):
    key = "tools"

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        self._build()
        self.on_theme()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        p = self.ctx.palette
        self.add(page_heading("Инструменты", "Ремонт сети, DNS, hosts и диагностика"))

        # ---------------------------------------------------------- actions
        repair_card = GlassCard("Починить сеть", "flushdns → Winsock → сброс IP-стека → кэш Zentrix",
                                "wrench", p)
        self.repair_button = QPushButton("Починить сеть")
        self.repair_button.setIcon(self._icon("wrench"))
        self.repair_button.clicked.connect(self._repair)
        repair_card.add(self.repair_button)
        self.repair_label = QLabel("Требуются права администратора")
        self.repair_label.setObjectName("tiny")
        self.repair_label.setWordWrap(True)
        repair_card.add(self.repair_label)
        self.add(repair_card)

        # ------------------------------------------------------ DNS presets
        dns_card = GlassCard("Смена DNS", "Пресеты в один клик; сброс на DHCP", "globe", p)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.interface_combo = QComboBox()
        self.interface_combo.setMinimumWidth(220)
        row.addWidget(self.interface_combo, 1)
        self.dns_combo = QComboBox()
        for key, preset in nettools.DNS_PRESETS.items():
            self.dns_combo.addItem(preset["label"], key)
        row.addWidget(self.dns_combo, 1)
        apply_dns = QPushButton("Применить")
        apply_dns.clicked.connect(self._apply_dns)
        row.addWidget(apply_dns, 0)
        dns_card.add_layout(row)
        self.dns_label = QLabel("Выберите интерфейс и пресет")
        self.dns_label.setObjectName("tiny")
        dns_card.add(self.dns_label)
        self.add(dns_card)

        # ------------------------------------------------------------- hosts
        hosts_card = GlassCard("Редактор hosts", "Анти-рекламный пресет и групповое выключение",
                               "edit", p)
        self.hosts_list = QListWidget()
        self.hosts_list.setMinimumHeight(160)
        self.hosts_list.setAlternatingRowColors(True)
        hosts_card.add(self.hosts_list, 1)
        hosts_row = QHBoxLayout()
        self.hosts_ip = QLineEdit()
        self.hosts_ip.setPlaceholderText("0.0.0.0")
        self.hosts_ip.setFixedWidth(110)
        self.hosts_host = QLineEdit()
        self.hosts_host.setPlaceholderText("домен для блокировки")
        add_button = QPushButton("Добавить")
        add_button.clicked.connect(self._host_add)
        anti_ad = QPushButton("Анти-реклама")
        anti_ad.setToolTip("Добавить стандартный набор рекламных доменов → 0.0.0.0")
        anti_ad.clicked.connect(self._host_anti_ad)
        toggle = QPushButton("Вкл/выкл")
        toggle.clicked.connect(self._host_toggle)
        remove = QPushButton("Удалить")
        remove.clicked.connect(self._host_remove)
        for button in (add_button, anti_ad, toggle, remove):
            button.setProperty("variant", "chip")
            button.setCursor(Qt.PointingHandCursor)
        hosts_row.addWidget(self.hosts_ip)
        hosts_row.addWidget(self.hosts_host, 1)
        hosts_row.addWidget(add_button)
        hosts_row.addWidget(anti_ad)
        hosts_row.addWidget(toggle)
        hosts_row.addWidget(remove)
        hosts_card.add_layout(hosts_row)
        hosts_bottom = QHBoxLayout()
        self.hosts_save = QPushButton("Сохранить hosts")
        self.hosts_save.clicked.connect(self._host_save)
        hosts_bottom.addWidget(self.hosts_save)
        self.hosts_label = QLabel("Чтение требует прав администратора")
        self.hosts_label.setObjectName("tiny")
        hosts_bottom.addWidget(self.hosts_label, 1)
        hosts_card.add_layout(hosts_bottom)
        self.add(hosts_card)

        # -------------------------------------------------------- diagnostics
        diag_card = GlassCard("Диагностика", "ping · traceroute · whois · скан портов",
                              "cpu", p)
        diag_row = QHBoxLayout()
        self.diag_host = QLineEdit()
        self.diag_host.setPlaceholderText("example.com или IP")
        diag_row.addWidget(self.diag_host, 1)
        self.diag_mode = QComboBox()
        self.diag_mode.addItem("ping", "ping")
        self.diag_mode.addItem("traceroute", "traceroute")
        self.diag_mode.addItem("whois", "whois")
        self.diag_mode.addItem("порты 80/443/53", "ports")
        diag_row.addWidget(self.diag_mode, 0)
        run_diag = QPushButton("Запустить")
        run_diag.clicked.connect(self._run_diag)
        diag_row.addWidget(run_diag, 0)
        diag_card.add_layout(diag_row)
        self.diag_output = QLabel("")
        self.diag_output.setObjectName("tiny")
        self.diag_output.setWordWrap(True)
        self.diag_output.setMinimumHeight(90)
        diag_card.add(self.diag_output, 1)
        self.add(diag_card)

        self.finish()

    def _icon(self, name: str):
        from ..widgets import icon

        return icon(name, self.ctx.palette.accent, 18)

    # ------------------------------------------------------------------ show
    def on_show(self) -> None:
        self.interface_combo.clear()
        for name in nettools.active_interfaces():
            self.interface_combo.addItem(name)
        self._load_hosts()

    def on_hide(self) -> None:
        pass

    # ---------------------------------------------------------------- repair
    def _repair(self) -> None:
        if not self.ctx.admin():
            self._admin_help()
            return
        self.repair_button.setEnabled(False)
        self.repair_label.setText("Выполняю: flushdns → Winsock → сброс IP…")
        run_task(self, lambda: nettools.repair_network(clean_zentrix_cache=True),
                 on_done=self._repair_done, on_error=self._repair_failed)

    def _repair_done(self, rows) -> None:
        self.repair_button.setEnabled(True)
        ok = [title for _k, title, good in rows if good]
        bad = [title for _k, title, good in rows if not good]
        if bad:
            self.repair_label.setText("Не удалось: " + ", ".join(bad))
            self.ctx.notify("Ремонт сети: часть шагов не выполнена", "warn", "error")
        else:
            self.repair_label.setText("Готово: " + ", ".join(ok))
            self.ctx.notify("Сеть починена", "ok")

    def _repair_failed(self, message: str) -> None:
        self.repair_button.setEnabled(True)
        self.repair_label.setText(f"Ошибка: {message}")

    # ------------------------------------------------------------------- dns
    def _apply_dns(self) -> None:
        if not self.ctx.admin():
            self._admin_help()
            return
        interface = self.interface_combo.currentText()
        preset = self.dns_combo.currentData()
        if not interface:
            self.dns_label.setText("Активный интерфейс не найден")
            return
        self.dns_label.setText("Применяю…")

        def _apply():
            return nettools.set_dns(interface, preset)

        run_task(self, _apply, on_done=lambda result: self._dns_done(result),
                 on_error=lambda message: self.dns_label.setText(f"Ошибка: {message}"))

    def _dns_done(self, result) -> None:
        ok, message = result
        self.dns_label.setText(message)
        self.ctx.notify(message, "ok" if ok else "warn")

    # ----------------------------------------------------------------- hosts
    def _load_hosts(self) -> None:
        self._host_rows = nettools.read_hosts()
        self.hosts_list.clear()
        if not self._host_rows:
            self.hosts_label.setText("hosts пуст или недоступен (нужен администратор)")
            return
        self.hosts_label.setText(f"Записей: {len(self._host_rows)}")
        for enabled, ip, host in self._host_rows:
            item = QListWidgetItem(("✓ " if enabled else "✗ ") + f"{ip}\t{host}")
            item.setData(Qt.UserRole, (enabled, ip, host))
            if not enabled:
                item.setForeground(self.ctx.palette.muted)
            self.hosts_list.addItem(item)

    def _host_add(self) -> None:
        ip = self.hosts_ip.text().strip() or "0.0.0.0"
        host = self.hosts_host.text().strip()
        if not host:
            return
        self._host_rows.append((True, ip, host))
        self.hosts_host.clear()
        self._host_render()

    def _host_anti_ad(self) -> None:
        self._host_rows = nettools.anti_ad_rows(self._host_rows)
        self._host_render()

    def _host_toggle(self) -> None:
        row = self.hosts_list.currentRow()
        if 0 <= row < len(self._host_rows):
            enabled, ip, host = self._host_rows[row]
            self._host_rows[row] = (not enabled, ip, host)
            self._host_render()

    def _host_remove(self) -> None:
        row = self.hosts_list.currentRow()
        if 0 <= row < len(self._host_rows):
            del self._host_rows[row]
            self._host_render()

    def _host_render(self) -> None:
        self.hosts_list.clear()
        for enabled, ip, host in self._host_rows:
            item = QListWidgetItem(("✓ " if enabled else "✗ ") + f"{ip}\t{host}")
            item.setData(Qt.UserRole, (enabled, ip, host))
            if not enabled:
                item.setForeground(self.ctx.palette.muted)
            self.hosts_list.addItem(item)

    def _host_save(self) -> None:
        if not self.ctx.admin():
            self._admin_help()
            return

        def _save():
            return nettools.write_hosts(self._host_rows)

        run_task(self, _save,
                 on_done=lambda result: (self.hosts_label.setText(result[1]),
                                         self.ctx.notify(result[1], "ok" if result[0] else "warn")),
                 on_error=lambda message: self.hosts_label.setText(f"Ошибка: {message}"))

    # ------------------------------------------------------------ diagnostics
    def _run_diag(self) -> None:
        host = self.diag_host.text().strip()
        mode = self.diag_mode.currentData()
        if not host:
            self.diag_output.setText("Введите домен или IP")
            return
        self.diag_output.setText("Выполняю…")
        functions = {
            "ping": lambda: self._fmt_ping(nettools.icmp_ping(host)),
            "traceroute": lambda: nettools.traceroute(host)[:1200] or "Маршрут не построился",
            "whois": lambda: (nettools.whois_query(host)[:900] or "Нет данных"),
            "ports": lambda: self._fmt_ports(nettools.port_scan(host, [80, 443, 53])),
        }
        run_task(self, functions[mode],
                 on_done=lambda text: self.diag_output.setText(text),
                 on_error=lambda message: self.diag_output.setText(f"Ошибка: {message}"))

    @staticmethod
    def _fmt_ping(result) -> str:
        alive, avg, _tail = result
        return f"ping: {'жив, средняя ' + str(avg) + ' мс' if alive else 'не отвечает'}"

    @staticmethod
    def _fmt_ports(rows) -> str:
        if not rows:
            return "Порты не проверены"
        return " · ".join(f"{port}: {'открыт' if ok else 'закрыт'}" for port, ok in rows)

    # ------------------------------------------------------------------ misc
    def _admin_help(self) -> None:
        from .. import overlays

        overlays.confirm(
            self.ctx.overlay, "Права администратора",
            "Инструменты меняют настройки Windows (DNS, hosts, сетевой стек) и требуют "
            "повышенных прав.<br><br>Zentrix перезапустится от имени администратора.",
            "Перезапустить", self.ctx.relaunch_admin,
        )

    def on_theme(self) -> None:
        pass
