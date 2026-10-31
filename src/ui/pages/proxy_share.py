"""Home-network proxy sharing page."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from ... import net
from ..widgets import GlassCard, PrimaryButton, icon
from ..workers import run_task
from .base_page import Page

ROUTE_HINTS = {
    "vpn": "Устройства выходят в интернет через выбранный VPN‑сервер этого ПК. "
           "Нужен добавленный сервер и установленное ядро.",
    "zapret": "Устройства выходят напрямую, а запущенная стратегия Zapret обходит "
              "блокировки для их трафика. VPN‑сервер и подписка не требуются.",
}


class QRCodeView(QLabel):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(248, 248)
        self.setAlignment(Qt.AlignCenter)
        self.setObjectName("qrCode")
        self.setText("Включите раздачу,\nчтобы создать QR‑код")
        self.setWordWrap(True)

    def set_payload(self, payload: str) -> None:
        try:
            import qrcode
            image = qrcode.make(payload).convert("RGB")
            buffer = image.tobytes("raw", "RGB")
            qimage = QImage(buffer, image.width, image.height, image.width * 3,
                            QImage.Format.Format_RGB888).copy()
            self.setPixmap(QPixmap.fromImage(qimage).scaled(
                224, 224, Qt.KeepAspectRatio, Qt.FastTransformation
            ))
            self.setToolTip(payload)
        except Exception as exc:
            self.setPixmap(QPixmap())
            self.setText(f"QR‑код недоступен\n{exc}")


class ProxySharePage(Page):
    key = "proxy_share"

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        self._share_enabled = bool(context.settings.get("vpn.share", False))
        self._started_by_share = False
        self._zapret_started_by_share = False
        route = str(context.settings.get("vpn.share_route", "vpn") or "vpn")
        self._route = route if route in {"vpn", "zapret"} else "vpn"
        self._build()
        self._connect()
        self._update_route_ui()
        self._refresh_state()

    def _build(self) -> None:
        p = self.ctx.palette
        self.add(self._heading())

        self.status_card = GlassCard("Локальный шеринг", "Доступ к прокси по Wi‑Fi или LAN", "wifi", p)
        self.toggle = PrimaryButton("Включить раздачу", "wifi", p)
        self.toggle.setCheckable(True)
        self.toggle.setChecked(self._share_enabled)
        self.toggle.setMaximumWidth(260)
        self.toggle.clicked.connect(self._toggle_share)
        self.status_card.add(self.toggle, 0)
        self.status_label = QLabel("Раздача выключена")
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        self.status_card.add(self.status_label)

        route_caption = QLabel("Через что идёт трафик устройств")
        route_caption.setObjectName("tiny")
        self.status_card.add(route_caption)
        route_row = QHBoxLayout()
        route_row.setSpacing(8)
        self.route_vpn_button = QPushButton("VPN")
        self.route_zapret_button = QPushButton("Zapret")
        for button, route in ((self.route_vpn_button, "vpn"), (self.route_zapret_button, "zapret")):
            button.setProperty("variant", "chip")
            button.setCheckable(True)
            button.setCursor(Qt.PointingHandCursor)
            button.setProperty("route", route)
            route_row.addWidget(button)
        self.route_group = QButtonGroup(self)
        self.route_group.setExclusive(True)
        self.route_group.addButton(self.route_vpn_button)
        self.route_group.addButton(self.route_zapret_button)
        self.route_group.buttonClicked.connect(
            lambda button: self._set_route(str(button.property("route")))
        )
        route_row.addStretch(1)
        self.status_card.add_layout(route_row)
        self.route_hint = QLabel("")
        self.route_hint.setObjectName("tiny")
        self.route_hint.setWordWrap(True)
        self.status_card.add(self.route_hint)
        self.add(self.status_card)

        body = QHBoxLayout()
        body.setSpacing(14)
        qr_card = GlassCard("QR‑код подключения", "Отсканируйте код устройством в той же домашней сети", "target", p)
        self.protocol = QComboBox()
        self.protocol.addItem("SOCKS5", "socks5")
        self.protocol.addItem("HTTP", "http")
        self.protocol.currentIndexChanged.connect(self._refresh_qr)
        qr_card.add(self.protocol)
        self.qr = QRCodeView()
        qr_card.add(self.qr, 0)
        body.addWidget(qr_card, 1)

        details = GlassCard("Настройки подключения", "Устройства должны быть подключены к одному роутеру", "globe", p)
        self.address_label = QLabel("IP компьютера: поиск…")
        self.address_label.setObjectName("h2")
        self.address_label.setWordWrap(True)
        details.add(self.address_label)
        self.proxy_label = QLabel("Включите раздачу — прокси запустится сам, VPN на этом ПК не обязателен")
        self.proxy_label.setObjectName("muted")
        self.proxy_label.setWordWrap(True)
        details.add(self.proxy_label)
        copy_row = QHBoxLayout()
        self.copy_socks = QPushButton("Копировать SOCKS5")
        self.copy_http = QPushButton("Копировать HTTP")
        self.copy_socks.clicked.connect(lambda: self._copy("socks5"))
        self.copy_http.clicked.connect(lambda: self._copy("http"))
        copy_row.addWidget(self.copy_socks)
        copy_row.addWidget(self.copy_http)
        details.add_layout(copy_row)
        self.refresh_button = QPushButton("Обновить IP сети")
        self.refresh_button.setIcon(icon("refresh", p.accent, 18))
        self.refresh_button.clicked.connect(self._refresh_state)
        details.add(self.refresh_button, 0)
        body.addWidget(details, 1)
        self.add_layout(body)

        self.guide_card = GlassCard("Как подключить телефон",
                                    "Телефон и компьютер должны быть в одной Wi‑Fi сети", "wifi", p)
        self.guide_step1 = self._step_label("")
        self.guide_card.add(self.guide_step1)
        self.guide_card.add(self._step_label(
            "2.  При первом запуске разрешите доступ в окне брандмауэра Windows "
            "(должны быть отмечены «Частные сети»)."
        ))
        self.guide_android = self._step_label("")
        self.guide_ios = self._step_label("")
        self.guide_card.add(self.guide_android)
        self.guide_card.add(self.guide_ios)
        self.guide_step5 = self._step_label("")
        self.guide_card.add(self.guide_step5)
        self.add(self.guide_card)

        note = QLabel(
            "Раздача работает и с подключённым VPN, и без него: устройства выходят в интернет "
            "через этот ПК. Доступ без пароля открыт только устройствам "
            "в вашей локальной сети."
        )
        note.setObjectName("tiny")
        note.setWordWrap(True)
        self.add(note)
        self.finish()

    def _heading(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(2, 0, 2, 0)
        layout.setSpacing(3)
        title_row = QHBoxLayout()
        title_row.setSpacing(10)
        title = QLabel("Прокси‑шеринг")
        title.setObjectName("h1")
        title_row.addWidget(title)
        title_row.addStretch(1)
        layout.addLayout(title_row)
        subtitle = QLabel("Подключите другие устройства в домашней сети к интернету через этот ПК")
        subtitle.setObjectName("muted")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)
        return widget

    @staticmethod
    def _step_label(text: str) -> QLabel:
        label = QLabel(text)
        label.setTextFormat(Qt.RichText)
        label.setWordWrap(True)
        return label

    def _connect(self) -> None:
        for engine in (self.ctx.happ, self.ctx.hiddify, self.ctx.share):
            engine.status_changed.connect(self._engine_status_changed)

    def _engine_status_changed(self, _status: str, _message: str) -> None:
        self._refresh_state()

    def _active_engine(self):
        if self.ctx.happ.status == "running":
            return self.ctx.happ
        if self.ctx.hiddify.status == "running":
            return self.ctx.hiddify
        return self.ctx.hiddify if self.ctx.settings.get("vpn.core", "xray") == "singbox" else self.ctx.happ

    def _proxy_engine(self):
        """Engine whose inbound serves the shared devices for the current route."""
        if self._route == "zapret":
            return self.ctx.share
        return self._active_engine()

    # ------------------------------------------------------------------ route
    def _set_route(self, route: str) -> None:
        if route not in {"vpn", "zapret"} or route == self._route:
            self._update_route_ui()
            return
        if self._share_enabled:
            # Switching routes re-binds the inbound — drop sharing first.
            self.toggle.setChecked(False)
            self._toggle_share(False)
            self.ctx.notify("Маршрут изменён — включите раздачу заново", "info")
        self._route = route
        self.ctx.settings.set("vpn.share_route", route)
        self._update_route_ui()
        self._refresh_state()

    def _update_route_ui(self) -> None:
        self.route_vpn_button.setChecked(self._route == "vpn")
        self.route_zapret_button.setChecked(self._route == "zapret")
        self.route_hint.setText(ROUTE_HINTS[self._route])
        self.guide_step1.setText(
            "1.  Включите раздачу кнопкой выше. "
            + ("Если VPN ещё не подключён, Zentrix сам запустит локальный прокси — "
               "сам компьютер при этом ходит в интернет напрямую."
               if self._route == "vpn" else
               "Zentrix запустит локальный прокси и при необходимости стратегию Zapret — "
               "трафик устройств выходит напрямую, а Zapret обходит блокировки.")
        )
        self.guide_step5.setText(
            "5.  Быстрый способ: отсканируйте QR‑код приложением v2rayNG, Happ или Streisand — "
            "адрес прокси подставится автоматически. "
            + ("Телефон получит IP тех VPN‑серверов, которые выбраны на этом ПК."
               if self._route == "vpn" else
               "Телефон получит IP этого ПК, а блокировки обойдёт запущенная стратегия Zapret.")
        )

    # ----------------------------------------------------------------- toggle
    def _toggle_share(self, checked: bool) -> None:
        if self._route == "vpn":
            self._toggle_share_vpn(checked)
        else:
            self._toggle_share_zapret(checked)

    def _toggle_share_vpn(self, checked: bool) -> None:
        engine = self._active_engine()
        if checked and not engine.nodes():
            self._reject_toggle("Добавьте хотя бы один сервер во вкладке VPN — раздавать пока нечего")
            return
        if checked and not engine.core_installed():
            self._reject_toggle("Сначала установите ядро во вкладке VPN — без него прокси не запустить")
            return
        self._share_enabled = bool(checked)
        self.ctx.settings.set("vpn.share", self._share_enabled)
        self.toggle.setEnabled(False)
        if engine.status == "running":
            restart = checked or not self._started_by_share
            self._started_by_share = False
            if restart:
                # Rebind the inbound: LAN address when sharing, localhost otherwise.
                def apply() -> None:
                    engine.stop()
                    engine.start()
                run_task(self, apply, on_done=self._share_applied, on_error=self._share_failed)
            else:
                # The core was started just for sharing — shut it down.
                run_task(self, engine.stop, on_done=self._share_applied, on_error=self._share_failed)
            return
        if checked:
            self._started_by_share = True
            self._refresh_state()
            run_task(self, engine.start, on_done=self._share_started, on_error=self._share_failed)
        else:
            self._started_by_share = False
            self._share_applied(None)

    def _toggle_share_zapret(self, checked: bool) -> None:
        self._share_enabled = bool(checked)
        self.ctx.settings.set("vpn.share", self._share_enabled)
        self.toggle.setEnabled(False)
        if checked:
            run_task(self, self._start_zapret_share,
                     on_done=self._share_applied, on_error=self._share_failed)
        else:
            run_task(self, self._stop_zapret_share,
                     on_done=self._share_applied, on_error=self._share_failed)

    def _start_zapret_share(self) -> None:
        """Background: stop any VPN tunnel, ensure Zapret, start the direct proxy."""
        share = self.ctx.share
        if not share.core_installed():
            raise RuntimeError(
                "Ядро не установлено — установите Xray или sing-box во вкладке VPN"
            )
        for peer in (self.ctx.happ, self.ctx.hiddify):
            if peer.status in {"running", "starting"}:
                peer.stop()
        zapret = self.ctx.zapret
        if zapret.status != "running":
            if not self.ctx.admin():
                raise RuntimeError(
                    "Для запуска Zapret нужны права администратора (драйвер WinDivert)"
                )
            if not zapret.is_available():
                raise RuntimeError("winws.exe не найден — проверьте папку движка на вкладке Zapret")
            zapret.start()
            self._zapret_started_by_share = True
        share.start()

    def _stop_zapret_share(self) -> None:
        share = self.ctx.share
        if share.status in {"running", "starting"}:
            share.stop()
        if self._zapret_started_by_share:
            self._zapret_started_by_share = False
            if self.ctx.zapret.status == "running":
                self.ctx.zapret.stop()

    def _reject_toggle(self, message: str) -> None:
        self._share_enabled = False
        self.ctx.settings.set("vpn.share", False)
        self.toggle.setChecked(False)
        self.ctx.notify(message, "warn")
        self._refresh_state()

    def _share_started(self, _result) -> None:
        self.toggle.setEnabled(True)
        self.ctx.notify("Локальный прокси запущен — устройства в сети могут подключаться",
                        "ok", "enable")
        self._refresh_state()

    def _share_applied(self, _result) -> None:
        self.toggle.setEnabled(True)
        self.ctx.notify("Раздача прокси включена" if self._share_enabled else "Раздача прокси выключена",
                        "ok" if self._share_enabled else "info")
        self._refresh_state()

    def _share_failed(self, message: str) -> None:
        self.toggle.setEnabled(True)
        self._share_enabled = False
        self._started_by_share = False
        self._zapret_started_by_share = False
        self.ctx.settings.set("vpn.share", False)
        self.toggle.setChecked(False)
        self.ctx.notify(f"Не удалось применить настройку шеринга: {message}", "err", "error")
        self._refresh_state()

    # ----------------------------------------------------------------- status
    def _refresh_state(self) -> None:
        addresses = net.lan_ipv4_addresses()
        if addresses:
            self.address_label.setText("IP компьютера в сети: " + " · ".join(addresses))
        else:
            self.address_label.setText("IP локальной сети не найден — подключитесь к Wi‑Fi или LAN")
        engine = self._proxy_engine()
        self._sync_protocol(engine)
        self.toggle.setChecked(self._share_enabled)
        self.toggle.setText("Выключить раздачу" if self._share_enabled else "Включить раздачу")
        running = engine.status == "running"
        if running:
            protocol = self.protocol.currentData()
            port = self._port_for(protocol, engine)
            host = addresses[0] if self._share_enabled else "127.0.0.1"
            self.proxy_label.setText(
                f"Локальный прокси активен · {protocol.upper()} слушает {host}:{port}"
            )
        elif engine.status == "starting":
            self.proxy_label.setText("Запускаем локальный прокси…")
        elif self._share_enabled:
            self.proxy_label.setText("Прокси запустится автоматически при включении раздачи")
        else:
            self.proxy_label.setText("Включите раздачу — прокси запустится сам, VPN на этом ПК не обязателен")
        if self._share_enabled and running:
            self.status_label.setText("Устройства в домашней сети могут подключаться")
        elif self._share_enabled:
            self.status_label.setText("Запускаем прокси для раздачи…")
        else:
            self.status_label.setText("Раздача выключена")
        self._update_guide(engine, addresses)
        self._refresh_qr()

    def _update_guide(self, engine, addresses: list[str]) -> None:
        host = addresses[0] if addresses else "<IP компьютера>"
        port = self._port_for("http", engine)
        self.guide_android.setText(
            "3.  <b>Android:</b> Настройки → Wi‑Fi → долгое нажатие на вашу сеть → «Изменить» → "
            "«Дополнительно» → Прокси: «Вручную» → "
            f"Имя хоста: <b>{host}</b> → Порт: <b>{port}</b> → Сохранить"
        )
        self.guide_ios.setText(
            "4.  <b>iPhone / iPad:</b> Настройки → Wi‑Fi → «ⓘ» рядом с сетью → "
            "Настройка прокси → «Вручную» → "
            f"Сервер: <b>{host}</b> → Порт: <b>{port}</b> → Готово"
        )

    def _sync_protocol(self, engine) -> None:
        multi_tcp_only = getattr(engine, "multiproxy_active", False)
        socks_index = self.protocol.findData("socks5")
        if multi_tcp_only and socks_index >= 0:
            self.protocol.removeItem(socks_index)
        elif not multi_tcp_only and socks_index < 0:
            self.protocol.insertItem(0, "SOCKS5", "socks5")
        http_index = self.protocol.findData("http")
        if multi_tcp_only and http_index >= 0 and self.protocol.currentIndex() != http_index:
            self.protocol.setCurrentIndex(http_index)
        self.copy_socks.setEnabled(not multi_tcp_only)
        self.copy_socks.setToolTip(
            "В мульти‑прокси BETA доступен только HTTP (TCP)" if multi_tcp_only else ""
        )

    @staticmethod
    def _port_for(protocol: str, engine) -> int:
        primary, secondary = engine.ports()
        return secondary if protocol == "http" and engine.core_kind == "xray" else primary

    def _payload(self, protocol: str) -> str | None:
        if not self._share_enabled:
            return None
        addresses = net.lan_ipv4_addresses()
        if not addresses:
            return None
        engine = self._proxy_engine()
        if engine.status != "running":
            return None
        port = self._port_for(protocol, engine)
        return f"{protocol}://{addresses[0]}:{port}"

    def _refresh_qr(self, *_args) -> None:
        payload = self._payload(self.protocol.currentData())
        if payload:
            self.qr.set_payload(payload)
        else:
            self.qr.setPixmap(QPixmap())
            self.qr.setText("Включите раздачу,\nчтобы создать QR‑код")

    def _copy(self, protocol: str) -> None:
        engine = self._proxy_engine()
        if protocol == "socks5" and getattr(engine, "multiproxy_active", False):
            self.ctx.notify("В мульти‑прокси доступен только HTTP (TCP)", "warn")
            return
        payload = self._payload(protocol)
        if not payload:
            self.ctx.notify("Включите раздачу и дождитесь запуска прокси", "warn")
            return
        self.ctx.app.clipboard().setText(payload)
        self.ctx.notify(f"{protocol.upper()}‑адрес скопирован", "ok")

    def on_show(self) -> None:
        self._refresh_state()

    def on_theme(self) -> None:
        self._refresh_state()
