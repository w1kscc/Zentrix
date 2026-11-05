"""Unified VPN page for the shared Xray and sing-box profile list."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget, QListWidgetItem as QtListWidgetItem
from PySide6.QtWidgets import (
    QCheckBox,
    QButtonGroup, QComboBox, QFrame, QHBoxLayout, QLabel, QPushButton, QStackedWidget,
    QVBoxLayout, QWidget,
)

from ... import net, free_keys, nettools
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

        self.engine_card = GlassCard("Движок и режим", "Ядро, мульти‑прокси и переключение соединений", "settings",
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
        self.engine_card.add_layout(selector_row)
        self.engine_card.add(self.multi_hint)

        # Sub-tab chips: every section fits one screen, nothing to scroll.
        chips = QHBoxLayout()
        chips.setSpacing(8)
        self.section_group = QButtonGroup(self)
        self.section_group.setExclusive(True)
        self.section_buttons: dict[str, QPushButton] = {}
        for key, label in (("connect", "Подключение"),
                           ("servers", "Серверы и подписки"),
                           ("keys", "Ключи · BETA")):
            button = QPushButton(label)
            button.setProperty("variant", "chip")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            self.section_group.addButton(button)
            button.clicked.connect(lambda _=False, k=key: self.show_section(k))
            chips.addWidget(button)
            self.section_buttons[key] = button
        chips.addStretch(1)
        layout.addLayout(chips)

        self.sections = QStackedWidget()
        self.sections.setObjectName("pageStack")

        # --- section: Подключение (IP + движок + список серверов ядра)
        connect_view = QWidget()
        connect_layout = QVBoxLayout(connect_view)
        connect_layout.setContentsMargins(0, 0, 0, 0)
        connect_layout.setSpacing(14)
        connect_layout.addWidget(self.ip_card)
        connect_layout.addWidget(self.engine_card)
        self.xray_page = HappPage(context)
        self.singbox_page = HiddifyPage(context)
        # Single-scroll unification: pull the plain content containers out of
        # the proxy pages' own scroll areas so only ONE scrollbar exists —
        # the outer one wrapping the whole VPN section.
        self.stack = QStackedWidget()
        for page_object in (self.xray_page, self.singbox_page):
            page_object.column.setContentsMargins(0, 0, 0, 0)
            content = page_object.widget()
            content.setParent(None)
            self.stack.addWidget(content)
        connect_layout.addWidget(self.stack, 1)
        self.sections.addWidget(connect_view)

        # --- section: Серверы и подписки
        servers_view = QWidget()
        servers_layout = QVBoxLayout(servers_view)
        servers_layout.setContentsMargins(0, 0, 0, 0)
        servers_layout.setSpacing(14)
        self._build_servers_card(servers_layout, context)
        servers_layout.addStretch(1)
        self.sections.addWidget(servers_view)

        # --- section: Ключи · BETA
        keys_view = QWidget()
        keys_layout = QVBoxLayout(keys_view)
        keys_layout.setContentsMargins(0, 0, 0, 0)
        keys_layout.setSpacing(14)
        self._build_beta_card(keys_layout, context)
        keys_layout.addStretch(1)
        self.sections.addWidget(keys_view)

        from PySide6.QtWidgets import QScrollArea

        body_scroll = QScrollArea()
        body_scroll.setWidgetResizable(True)
        body_scroll.setFrameShape(QScrollArea.NoFrame)
        body_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        body_scroll.setWidget(self.sections)
        layout.addWidget(body_scroll, 1)
        self.section_buttons["connect"].setChecked(True)
        for engine in (context.happ, context.hiddify):
            engine.status_changed.connect(self._engine_status_changed)
        self._core_changed(self.core_selector.currentIndex())
        self._multi_state_changed(bool(context.settings.get("vpn.multiproxy", False)))

    @property
    def active_page(self):
        return (self.singbox_page if self.core_selector.currentData() == "singbox"
                else self.xray_page)

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
            self.stack.setCurrentIndex(1 if core == "singbox" else 0)
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

    # ---------------------------------------------------------------- servers
    def _build_servers_card(self, layout, context) -> None:
        """Ping / pick-best, subscription auto-update."""
        p = context.palette
        card = GlassCard("Серверы и подписки", "Замер задержки и авто-обновление подписок",
                         "activity", p)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.ping_button = QPushButton("Ping серверов")
        self.ping_button.setToolTip("TCP-замер задержки каждого сервера списка")
        self.ping_button.clicked.connect(self._ping_servers)
        row.addWidget(self.ping_button)
        self.best_server_button = QPushButton("Выбрать лучший")
        self.best_server_button.setToolTip("Переключиться на сервер с минимальной задержкой")
        self.best_server_button.clicked.connect(self._pick_best_server)
        row.addWidget(self.best_server_button)
        self.ping_hint = QLabel("Замер по TCP-подключению к каждому серверу")
        self.ping_hint.setObjectName("tiny")
        self.ping_hint.setWordWrap(True)
        row.addWidget(self.ping_hint, 1)
        card.add_layout(row)

        subs_row = QHBoxLayout()
        subs_row.setSpacing(8)
        self.subs_auto = QPushButton("Авто-обновление подписок")
        self.subs_auto.setProperty("variant", "chip")
        self.subs_auto.setCheckable(True)
        self.subs_auto.setChecked(bool(context.settings.get("subscriptions.auto_update", False)))
        self.subs_auto.clicked.connect(self._toggle_subs_auto)
        subs_row.addWidget(self.subs_auto)
        self.subs_now = QPushButton("Обновить сейчас")
        self.subs_now.clicked.connect(self._update_subscriptions)
        subs_row.addWidget(self.subs_now)
        self.subs_hint = QLabel("URL подписок задаются в списках серверов ниже")
        self.subs_hint.setObjectName("tiny")
        self.subs_hint.setWordWrap(True)
        subs_row.addWidget(self.subs_hint, 1)
        card.add_layout(subs_row)
        layout.addWidget(card)

    # ------------------------------------------------------------------- BETA
    def _build_beta_card(self, layout, context) -> None:
        """BETA: free public keys. Off by default, manual add only."""
        p = context.palette
        card = GlassCard("Поиск бесплатных ключей", "Публичные репозитории · BETA — на свой страх и риск",
                         "link", p)
        self.beta_badge = Badge("BETA", "warn")
        card.add_header_widget(self.beta_badge)
        self.beta_enabled = QPushButton("Включить поиск ключей")
        self.beta_enabled.setCheckable(True)
        self.beta_enabled.setChecked(bool(context.settings.get("freekeys.enabled", False)))
        self.beta_enabled.clicked.connect(self._toggle_beta)
        card.add(self.beta_enabled)
        self.beta_label = QLabel(
            "BETA — НА СВОЙ СТРАХ И РИСК. Бесплатные узлы не гарантируют безопасность: "
            "возможен сбор данных и MITM. Ничего не применяется автоматически — "
            "добавляйте узлы вручную кнопкой ниже.")
        self.beta_label.setObjectName("tiny")
        self.beta_label.setWordWrap(True)
        card.add(self.beta_label)

        # Category picker: igareck/vpn-configs-for-russia groups configs into
        # black/white list files; let the user choose which to fetch.
        cat_caption = QLabel("Что искать (источник: igareck/vpn-configs-for-russia, "
                             "обновляется автором каждые 1–2 часа):")
        cat_caption.setObjectName("tiny")
        card.add(cat_caption)
        from PySide6.QtWidgets import QGridLayout

        self.category_checks: dict[str, QCheckBox] = {}
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(4)
        for index, item_def in enumerate(free_keys.CATEGORIES):
            box = QCheckBox(item_def["label"])
            box.setToolTip(" · ".join(item_def["schemes"]))
            self.category_checks[item_def["key"]] = box
            grid.addWidget(box, index // 2, index % 2)
        container = QWidget()
        container.setLayout(grid)
        card.add(container)

        scheme_row = QHBoxLayout()
        scheme_caption = QLabel("Протоколы:")
        scheme_caption.setObjectName("tiny")
        scheme_row.addWidget(scheme_caption)
        self.scheme_checks: dict[str, QCheckBox] = {}
        for scheme, label in (("vless", "VLESS"), ("vmess", "VMess"),
                              ("trojan", "Trojan"), ("ss", "Shadowsocks")):
            box = QCheckBox(label)
            box.setChecked(scheme == "vless")
            self.scheme_checks[scheme] = box
            scheme_row.addWidget(box)
        scheme_row.addStretch(1)
        card.add_layout(scheme_row)

        beta_row = QHBoxLayout()
        self.beta_search = QPushButton("Найти ключи")
        self.beta_search.clicked.connect(self._search_keys)
        beta_row.addWidget(self.beta_search)
        self.beta_add = QPushButton("Добавить выбранный в мой список")
        self.beta_add.setEnabled(False)
        self.beta_add.clicked.connect(self._add_key)
        beta_row.addWidget(self.beta_add)
        beta_row.addStretch(1)
        card.add_layout(beta_row)
        self.beta_results = QListWidget()
        self.beta_results.setMinimumHeight(220)
        self.beta_results.setVisible(bool(context.settings.get("freekeys.enabled", False)))
        card.add(self.beta_results)
        layout.addWidget(card)

    def _toggle_beta(self, checked: bool) -> None:
        self.ctx.settings.set("freekeys.enabled", bool(checked))
        for box in self.category_checks.values():
            box.setVisible(bool(checked))
        self.beta_results.setVisible(bool(checked))
        if checked:
            self.ctx.notify("Поиск ключей включён: авто-обновление раз в час, "
                            "добавление только вручную. BETA — на ваш риск.", "warn")
            self.ctx.start_freekeys_refresh()
        else:
            self.beta_results.clear()
            self.ctx.stop_freekeys_refresh()

    def _search_keys(self) -> None:
        if not bool(self.ctx.settings.get("freekeys.enabled", False)):
            self.ctx.notify("Сначала включите поиск ключей (BETA)", "warn")
            return
        self.beta_search.setEnabled(False)
        self.beta_label.setText("Ищу в известных публичных источниках…")

        def _progress(index, total, name):
            self.beta_label.setText(f"Источник {index}/{total}: {name}")

        categories = self._selected_categories()
        schemes = [key for key, box in self.scheme_checks.items() if box.isChecked()]
        if not categories:
            self.beta_label.setText("Отметьте хотя бы одну категорию")
            return
        if not schemes:
            self.beta_label.setText("Отметьте хотя бы один протокол")
            return
        self.ctx.settings.set("freekeys.categories", categories)
        self.ctx.settings.set("freekeys.schemes", schemes)

        def _search():
            nodes = free_keys.search(progress=_progress, categories=categories,
                                     schemes=schemes)
            free_keys.probe_nodes(nodes)
            return nodes

        run_task(self, _search, on_done=self._keys_found,
                 on_error=self._keys_failed)

    def _selected_categories(self) -> list[str]:
        return [key for key, box in self.category_checks.items() if box.isChecked()]

    def _keys_found(self, nodes) -> None:
        import time

        self.beta_search.setEnabled(True)
        self._free_nodes = nodes
        self.ctx.free_keys_cache = nodes
        self.beta_results.clear()
        for node in nodes:
            ping = f" · {node.ping_ms:.0f} мс" if node.ping_ms is not None else ""
            alive = "" if node.usable is None else (" · доступен" if node.usable else " · недоступен")
            item = QtListWidgetItem(f"{node.name} [{node.scheme}]{ping}{alive}")
            item.setData(Qt.UserRole, node)
            self.beta_results.addItem(item)
        self.beta_add.setEnabled(bool(nodes))
        self.beta_label.setText(free_keys.summarize(nodes))
        self.ctx.settings.set("freekeys.last_search", time.time())

    def _keys_failed(self, message: str) -> None:
        self.beta_search.setEnabled(True)
        self.beta_label.setText(f"Поиск не удался: {message}")

    def _add_key(self) -> None:
        item = self.beta_results.currentItem()
        if item is None:
            self.ctx.notify("Выберите узел в списке", "warn")
            return
        node = item.data(Qt.UserRole)
        engine = self.active_engine
        existing = "\n".join(n.raw_link for n in engine.nodes() if n.raw_link)
        engine.set_profile_text("\n".join(filter(None, [existing, node.raw_link])))
        self.ctx.notify(f"Узел «{node.name}» добавлен с пометкой BETA/не проверено", "ok")
        self.active_page._reload_nodes()

    def _ping_servers(self) -> None:
        engine = self.active_engine
        nodes = engine.nodes()
        if not nodes:
            self.ping_hint.setText("Список серверов пуст — добавьте серверы или подписку")
            return
        self.ping_button.setEnabled(False)
        self.ping_hint.setText(f"Проверяю {len(nodes)} серверов…")

        def _probe():
            rows = []
            for node in nodes:
                latency = (nettools.tcp_ping(node.host, node.port, timeout=3.0)
                           if node.host and node.port else None)
                rows.append((node, latency))
            return rows

        run_task(self, _probe, on_done=self._ping_done,
                 on_error=lambda _message: self._ping_done([]))

    def _ping_done(self, rows) -> None:
        self.ping_button.setEnabled(True)
        self._latencies = rows
        good = [(node, ms) for node, ms in rows if ms is not None]
        if good:
            best = min(good, key=lambda item: item[1])
            self.ping_hint.setText(
                " · ".join(f"{node.name[:24]}: {ms} мс" for node, ms in good[:5])
                + f"   →  лучший: {best[0].name} ({best[1]} мс)")
        else:
            self.ping_hint.setText("Ни один сервер не ответил (TCP)")

    def _pick_best_server(self) -> None:
        rows = getattr(self, "_latencies", [])
        if not rows:
            self._ping_servers()
            return
        good = [(node, ms) for node, ms in rows if ms is not None]
        if not good:
            self.ctx.notify("Нет ответивших серверов — выбрать лучший нельзя", "warn")
            return
        best = min(good, key=lambda item: item[1])
        nodes = self.active_engine.nodes()
        index = next((i for i, n in enumerate(nodes) if n.raw_link == best[0].raw_link), None)
        if index is None:
            self.ctx.notify("Не удалось сопоставить сервер со списком", "err", "error")
            return
        self.active_engine.select_node(index)
        self.active_page._reload_nodes(index)
        self.ctx.notify(f"Выбран лучший сервер: {best[0].name} ({best[1]} мс)", "ok")

    def _toggle_subs_auto(self, checked: bool) -> None:
        self.ctx.settings.set("subscriptions.auto_update", bool(checked))
        self.ctx.notify("Авто-обновление подписок " + ("включено" if checked else "выключено"),
                        "info")
        self.ctx.reschedule_subscriptions()

    def _update_subscriptions(self) -> None:
        urls = []
        for engine in (self.ctx.happ, self.ctx.hiddify):
            url = str(self.ctx.settings.get(f"{engine.ns}.subscription", "") or "").strip()
            if url:
                urls.append((engine, url))
        if not urls:
            self.subs_hint.setText("URL подписки не задан — вставьте его в строке «подписка» ниже")
            return
        self.subs_now.setEnabled(False)

        def _refresh():
            counts = []
            for engine, url in urls:
                counts.append(f"{engine.title}: +{engine.fetch_subscription(url)}")
            return ", ".join(counts)

        run_task(self, _refresh,
                 on_done=lambda message: (self.subs_now.setEnabled(True),
                                          self.subs_hint.setText(message),
                                          self.ctx.notify("Подписки обновлены: " + message, "ok")),
                 on_error=lambda message: (self.subs_now.setEnabled(True),
                                           self.ctx.notify(f"Подписки: {message}", "err", "error")))

    def show_section(self, key: str) -> None:
        """Switch the VPN sub-tab; proxy pages refresh only when visible."""
        for name, button in self.section_buttons.items():
            button.setChecked(name == key)
        leaving = self.sections.currentWidget()
        self.sections.setCurrentIndex(
            list(self.section_buttons).index(key))
        if key == "keys":
            self._restore_beta_settings()
            self._render_free_nodes(getattr(self.ctx, "free_keys_cache", []))
        if key == "connect":
            if leaving is not self.sections.widget(0):
                self.active_page.on_show()
            self._update_ip_state()

    def on_show(self) -> None:
        self._restore_beta_settings()
        self._render_free_nodes(getattr(self.ctx, "free_keys_cache", []))
        if self.sections.currentIndex() == 0:
            self.active_page.on_show()
            self._update_ip_state()

    def _restore_beta_settings(self) -> None:
        saved = set(self.ctx.settings.get("freekeys.categories", []) or [])
        for key, box in self.category_checks.items():
            box.setChecked(bool(not saved or key in saved))
        saved_schemes = set(self.ctx.settings.get("freekeys.schemes", ["vless"]) or ["vless"])
        for key, box in self.scheme_checks.items():
            box.setChecked(key in saved_schemes)

    def _render_free_nodes(self, nodes) -> None:
        self.beta_results.clear()
        for node in nodes:
            ping = f" · {node.ping_ms:.0f} мс" if node.ping_ms is not None else ""
            alive = "" if node.usable is None else (" · доступен" if node.usable else " · недоступен")
            item = QtListWidgetItem(f"{node.name} [{node.scheme}]{ping}{alive}")
            item.setData(Qt.UserRole, node)
            self.beta_results.addItem(item)
        self.beta_add.setEnabled(bool(nodes))

    def on_hide(self) -> None:
        self.active_page.on_hide()

    def on_theme(self) -> None:
        self.active_page.on_theme()
