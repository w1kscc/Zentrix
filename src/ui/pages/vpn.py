"""Unified VPN page for the shared Xray and sing-box profile list."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ... import net
from .. import flags
from ..widgets import Badge, GlassCard
from ..workers import run_task
from .happ import HappPage
from .hiddify import HiddifyPage
from .base_page import page_heading


class IpPanel(QFrame):
    """Compact "without VPN / through VPN" tile with a flag, IP and place."""

    def __init__(self, caption: str, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("ipPanel")
        self.setMinimumHeight(92)
        column = QVBoxLayout(self)
        column.setContentsMargins(14, 11, 14, 11)
        column.setSpacing(5)
        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("tiny")
        column.addWidget(self.caption_label)
        main_row = QHBoxLayout()
        main_row.setSpacing(9)
        self.flag_label = QLabel()
        self.flag_label.setFixedHeight(20)
        self.ip_label = QLabel("—")
        self.ip_label.setObjectName("h2")
        main_row.addWidget(self.flag_label, 0, Qt.AlignVCenter)
        main_row.addWidget(self.ip_label, 0, Qt.AlignVCenter)
        main_row.addStretch(1)
        column.addLayout(main_row)
        self.place_label = QLabel("")
        self.place_label.setObjectName("tiny")
        self.place_label.setWordWrap(True)
        column.addWidget(self.place_label)

    def _clear_flag(self) -> None:
        self.flag_label.clear()
        self.flag_label.setFixedWidth(1)

    def show_lookup(self, hint: str) -> None:
        self._clear_flag()
        self.ip_label.setText("—")
        self.place_label.setText(hint)

    def show_result(self, country_code: str, ip: str, place: str) -> None:
        pixmap = flags.flag_pixmap(country_code, 20)
        if pixmap is not None:
            self.flag_label.setPixmap(pixmap)
            self.flag_label.setFixedWidth(pixmap.width())
        else:
            self._clear_flag()
        self.ip_label.setText(ip or "—")
        self.place_label.setText(place)

    def show_error(self) -> None:
        self._clear_flag()
        self.ip_label.setText("—")
        self.place_label.setText("Не удалось определить IP и местоположение")


class VpnPage(QWidget):
    key = "vpn"

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.ctx = context
        self._lookup_ids = {"direct": 0, "vpn": 0}
        # Same page grid as the Page base class so cards align with the
        # Xray / sing-box pages stacked below.
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 18, 28, 30)
        layout.setSpacing(14)

        self.heading = page_heading("VPN", "Один список серверов для Xray и sing-box")
        layout.addWidget(self.heading)

        self.ip_card = GlassCard("Ваш IP-адрес", "GeoIP: ipapi.co получает запрос с вашим публичным IP", "globe",
                                 context.palette)
        self.ip_badge = Badge("ПРОВЕРКА…", "muted")
        self.ip_card.add_header_widget(self.ip_badge)
        row = QHBoxLayout()
        row.setSpacing(14)
        self.direct_panel = IpPanel("БЕЗ VPN")
        self.vpn_panel = IpPanel("ЧЕРЕЗ VPN")
        self.direct_panel.show_lookup("Определяем прямое подключение…")
        self.vpn_panel.show_lookup("🔒  Подключитесь, чтобы проверить IP через туннель")
        row.addWidget(self.direct_panel, 1)
        row.addWidget(self.vpn_panel, 1)
        self.ip_card.add_layout(row)
        layout.addWidget(self.ip_card)

        engine_card = GlassCard("Движок и режим", "Ядро, мульти‑прокси и переключение соединений", "settings",
                                context.palette)
        selector_row = QHBoxLayout()
        selector_row.setSpacing(10)
        selector_row.addWidget(QLabel("Движок"))
        self.core_selector = QComboBox()
        self.core_selector.addItem("Xray · Happ", "xray")
        self.core_selector.addItem("sing-box · Hiddify", "singbox")
        self.core_selector.setMinimumWidth(210)
        saved_core = str(context.settings.get("vpn.core", "xray"))
        self.core_selector.setCurrentIndex(max(0, self.core_selector.findData(saved_core)))
        self.core_selector.currentIndexChanged.connect(self._core_changed)
        selector_row.addWidget(self.core_selector)
        selector_row.addSpacing(8)
        self.multi_button = QPushButton("Мульти‑прокси")
        self.multi_button.setProperty("variant", "chip")
        self.multi_button.setCheckable(True)
        self.multi_button.clicked.connect(self._toggle_multi)
        self.multi_badge = Badge("BETA", "warn")
        selector_row.addWidget(self.multi_button)
        selector_row.addWidget(self.multi_badge)
        selector_row.addStretch(1)
        self.multi_hint = QLabel("Новые TCP‑соединения распределяются между серверами.")
        self.multi_hint.setObjectName("tiny")
        self.multi_hint.setWordWrap(True)
        engine_card.add_layout(selector_row)
        engine_card.add(self.multi_hint)
        layout.addWidget(engine_card)

        self.stack = QStackedWidget()
        self.xray_page = HappPage(context)
        self.singbox_page = HiddifyPage(context)
        # The outer VpnPage provides the page margins now.
        self.xray_page.column.setContentsMargins(0, 0, 0, 0)
        self.singbox_page.column.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(self.xray_page)
        self.stack.addWidget(self.singbox_page)
        layout.addWidget(self.stack, 1)
        for engine in (context.happ, context.hiddify):
            engine.status_changed.connect(self._engine_status_changed)
        self._core_changed(self.core_selector.currentIndex())
        self._multi_state_changed(bool(context.settings.get("vpn.multiproxy", False)))

    @property
    def active_page(self):
        return self.stack.currentWidget()

    @property
    def active_engine(self):
        return self.ctx.hiddify if self.core_selector.currentData() == "singbox" else self.ctx.happ

    def _core_changed(self, index: int) -> None:
        core = self.core_selector.itemData(index) or "xray"
        previous = self.active_page
        page = self.singbox_page if core == "singbox" else self.xray_page
        old_engine = getattr(previous, "engine", None)
        if previous is not page and old_engine and old_engine.status in {"running", "starting", "stopping"}:
            self.core_selector.blockSignals(True)
            self.core_selector.setCurrentIndex(self.stack.currentIndex())
            self.core_selector.blockSignals(False)
            self.ctx.notify("Отключите текущий VPN перед сменой движка", "warn")
            return
        self.ctx.settings.set("vpn.core", core)
        if previous is not page:
            previous.on_hide()
            self.stack.setCurrentWidget(page)
            if self.ctx.current_page == self.key:
                page.on_show()
        self._update_ip_state()

    def _toggle_multi(self, enabled: bool) -> None:
        self.ctx.settings.set("vpn.multiproxy", enabled)
        self._multi_state_changed(enabled)
        if enabled and self.active_engine.core_kind != "singbox":
            self.ctx.notify("Мульти‑прокси работает только с движком sing-box.", "info")
        elif enabled and len(self.ctx.hiddify.nodes()) < 2:
            self.ctx.notify("Для балансировки добавьте минимум два сервера, поддерживаемых sing-box.", "warn")
        elif self.active_engine.status == "running":
            self.ctx.notify("Изменение применится после переподключения VPN.", "info")
        self.multi_button.setChecked(enabled)
        self.multi_button.update()

    def _multi_state_changed(self, enabled: bool) -> None:
        self.multi_button.setText(f"Мульти‑прокси · {'ВКЛ' if enabled else 'ВЫКЛ'}")
        self.multi_hint.setText(
            "Новые TCP‑соединения распределяются между серверами; одна загрузка не суммирует их скорость."
            if enabled else "Новые TCP‑соединения используют выбранный сервер."
        )

    def _engine_status_changed(self, _status: str, _message: str) -> None:
        self._update_ip_state()

    def _update_ip_state(self) -> None:
        engine = self.active_engine
        if engine.status == "running":
            self.vpn_panel.show_lookup("Получаем адрес через VPN…")
            self._lookup("vpn", lambda: net.external_ip_info(engine.proxy_url()))
        else:
            self.vpn_panel.show_lookup("🔒  Подключитесь, чтобы проверить IP через туннель")
            if engine.status in {"stopped", "error", "missing"}:
                self._lookup("direct", net.external_ip_info)

    def _lookup(self, kind: str, fn) -> None:
        self._lookup_ids[kind] += 1
        lookup_id = self._lookup_ids[kind]
        run_task(self, fn, on_done=lambda result: self._ip_done(kind, lookup_id, result),
                 on_error=lambda _message: self._ip_failed(kind, lookup_id))

    def _ip_done(self, kind: str, lookup_id: int, data: dict) -> None:
        if lookup_id != self._lookup_ids[kind]:
            return
        panel = self.direct_panel if kind == "direct" else self.vpn_panel
        place = ", ".join(str(part) for part in (data.get("city"), data.get("country_name")) if part)
        panel.show_result(data.get("country_code", ""), str(data.get("ip", "—")), place)
        self.ip_badge.update_badge("IP / GEOIP", "ok")

    def _ip_failed(self, kind: str, lookup_id: int) -> None:
        if lookup_id != self._lookup_ids[kind]:
            return
        panel = self.direct_panel if kind == "direct" else self.vpn_panel
        panel.show_error()

    def on_show(self) -> None:
        self.active_page.on_show()
        self._update_ip_state()

    def on_hide(self) -> None:
        self.active_page.on_hide()

    def on_theme(self) -> None:
        self.active_page.on_theme()
