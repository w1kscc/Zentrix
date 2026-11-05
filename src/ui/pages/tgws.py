"""TG WS Proxy: dedicated navigation section (between Zapret and VPN)."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)

from ... import nettools
from ...engines.tgws import core_available, vendored_version
from ..widgets import Badge, GlassCard
from ..workers import run_task
from .base_page import Page, page_heading


class TgWsPage(Page):
    key = "tgws"

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        self._build()
        self.ctx.tgws.status_changed.connect(self._status_changed)
        self.on_theme()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        p = self.ctx.palette
        self.add(page_heading(
            "TG WS Proxy",
            "Мост Telegram Desktop через WebSocket на ядре Flowseal/tg-ws-proxy — "
            "работает внутри Zentrix, без сторонних окон и процессов",
        ))

        card = GlassCard("Мост для Telegram", "MTProto 127.0.0.1 → WebSocket → Telegram DC",
                         "link", p)
        self.badge = Badge("ВЫКЛЮЧЕН", "muted")
        card.add_header_widget(self.badge)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.toggle = QPushButton("Включить TG WS Proxy")
        self.toggle.setCheckable(True)
        self.toggle.clicked.connect(self._toggle)
        row.addWidget(self.toggle)
        self.open_tg_button = QPushButton("Открыть в Telegram")
        self.open_tg_button.setToolTip("Открыть tg://proxy-ссылку — Telegram подключится сам")
        self.open_tg_button.clicked.connect(self._open_telegram)
        row.addWidget(self.open_tg_button)
        self.copy_button = QPushButton("Копировать ссылку")
        self.copy_button.clicked.connect(self._copy_link)
        row.addWidget(self.copy_button)
        row.addStretch(1)
        card.add_layout(row)

        cfg_row = QHBoxLayout()
        cfg_row.setSpacing(8)
        cfg_row.addWidget(QLabel("Порт"))
        self.port = QSpinBox()
        self.port.setRange(1024, 65535)
        self.port.setValue(int(self.ctx.settings.get("tgws.port", 1443) or 1443))
        self.port.setFixedWidth(90)
        self.port.valueChanged.connect(
            lambda value: self._apply(lambda: self.ctx.settings.set("tgws.port", int(value))))
        cfg_row.addWidget(self.port)
        self.autostart = QPushButton("Автозапуск")
        self.autostart.setProperty("variant", "chip")
        self.autostart.setCheckable(True)
        self.autostart.setChecked(bool(self.ctx.settings.get("tgws.autostart", False)))
        self.autostart.clicked.connect(
            lambda checked: self.ctx.settings.set("tgws.autostart", bool(checked)))
        cfg_row.addWidget(self.autostart)
        self.update_button = QPushButton("Скачать / обновить ядро")
        self.update_button.clicked.connect(self._install)
        cfg_row.addWidget(self.update_button)
        cfg_row.addStretch(1)
        card.add_layout(cfg_row)

        secret_row = QHBoxLayout()
        secret_row.addWidget(QLabel("Secret"))
        self.secret = QLineEdit(str(self.ctx.settings.get("tgws.secret", "")) or "")
        self.secret.setPlaceholderText("MTProto secret (dd…)")
        self.secret.editingFinished.connect(
            lambda: self._apply(lambda: self.ctx.settings.set(
                "tgws.secret", self.secret.text().strip())))
        secret_row.addWidget(self.secret, 1)
        regen = QPushButton("Новый secret")
        regen.setProperty("variant", "chip")
        regen.clicked.connect(self._regen_secret)
        secret_row.addWidget(regen)
        card.add_layout(secret_row)

        flags_row = QHBoxLayout()
        self.cfproxy = QPushButton("CfProxy fallback")
        self.cfproxy.setProperty("variant", "chip")
        self.cfproxy.setCheckable(True)
        self.cfproxy.setChecked(bool(self.ctx.settings.get("tgws.cfproxy", True)))
        self.cfproxy.clicked.connect(
            lambda checked: self._apply(lambda: self.ctx.settings.set("tgws.cfproxy", bool(checked))))
        self.h2 = QPushButton("HTTP/2 медиа")
        self.h2.setProperty("variant", "chip")
        self.h2.setCheckable(True)
        self.h2.setChecked(bool(self.ctx.settings.get("tgws.h2", True)))
        self.h2.clicked.connect(
            lambda checked: self._apply(lambda: self.ctx.settings.set("tgws.h2", bool(checked))))
        flags_row.addWidget(self.cfproxy)
        flags_row.addWidget(self.h2)
        flags_row.addStretch(1)
        card.add_layout(flags_row)

        self.hint = QLabel(self._status_text())
        self.hint.setObjectName("tiny")
        self.hint.setWordWrap(True)
        card.add(self.hint)
        self.add(card)

        # Журнал моста
        log_card = GlassCard("Журнал моста", "События встроенного ядра TG WS Proxy", "activity", p)
        self.tgws_log = QLabel("")
        self.tgws_log.setObjectName("tiny")
        self.tgws_log.setWordWrap(True)
        self.tgws_log.setMinimumHeight(90)
        log_card.add(self.tgws_log, 1)
        self.add(log_card)

        self.finish()

    # ------------------------------------------------------------------ logic
    def _status_text(self) -> str:
        if not core_available():
            return ("Ядро не скачано: нажмите «Скачать / обновить ядро» — Zentrix заберёт "
                    "последнюю версию с GitHub (Flowseal/tg-ws-proxy) и запустит встроенно.")
        version = vendored_version() or "неизвестна"
        return (f"Ядро установлено (версия {version}). После включения подключите Telegram "
                "Desktop кнопкой «Открыть в Telegram» или ссылкой MTProto. "
                "Статус дублируется на Главной.")

    def _apply(self, setter) -> None:
        setter()
        if self.ctx.tgws.status == "running":
            self.ctx.notify("Применится после перезапуска TG WS Proxy", "info")

    def _toggle(self, checked: bool) -> None:
        self.ctx.settings.set("tgws.enabled", bool(checked))
        engine = self.ctx.tgws
        if checked:
            if not engine.is_available():
                self.ctx.notify("Сначала скачайте ядро TG WS Proxy", "warn")
                self.toggle.setChecked(False)
                return
            self.toggle.setEnabled(False)
            run_task(self, engine.start,
                     on_done=lambda _r: (self.toggle.setEnabled(True),
                                         self.ctx.notify("TG WS Proxy запущен", "ok")),
                     on_error=lambda msg: (self.toggle.setEnabled(True),
                                           self.toggle.setChecked(False),
                                           self.ctx.notify(f"TG WS Proxy: {msg}", "err", "error")))
        else:
            run_task(self, engine.stop,
                     on_done=lambda _r: self.ctx.notify("TG WS Proxy остановлен", "info"),
                     on_error=lambda msg: self.ctx.notify(msg, "err", "error"))

    def _status_changed(self, status: str, message: str) -> None:
        self.badge.update_badge(
            {"running": "РАБОТАЕТ", "starting": "ЗАПУСК…", "stopping": "ОСТАНОВКА…",
             "error": "ОШИБКА"}.get(status, "ВЫКЛЮЧЕН"),
            {"running": "ok", "starting": "info", "stopping": "info",
             "error": "err"}.get(status, "muted"))
        self.toggle.setChecked(status in {"running", "starting"})
        self.hint.setText(self._status_text())
        if message:
            self.tgws_log.setText(message)

    def _open_telegram(self) -> None:
        import webbrowser

        webbrowser.open(self.ctx.tgws.proxy_url())

    def _copy_link(self) -> None:
        from PySide6.QtWidgets import QApplication

        QApplication.clipboard().setText(self.ctx.tgws.proxy_url())
        self.ctx.notify("tg://proxy-ссылка скопирована", "ok")

    def _regen_secret(self) -> None:
        import secrets as _secrets

        new_secret = _secrets.token_hex(16)
        self.ctx.settings.set("tgws.secret", new_secret)
        self.secret.setText(new_secret)
        self.ctx.notify("Secret обновлён — переподключите Telegram", "info")

    def _install(self) -> None:
        self.update_button.setEnabled(False)
        self.ctx.notify("Скачиваю ядро TG WS Proxy с GitHub…", "info")

        def _install():
            from ... import updater
            return updater.install("tgwsproxy")

        def _done(result):
            self.update_button.setEnabled(True)
            self.ctx.notify(result["message"], "ok")
            self.hint.setText(self._status_text())

        def _failed(message):
            self.update_button.setEnabled(True)
            self.ctx.notify(f"TG WS Proxy: {message}", "err", "error")

        run_task(self, _install, on_done=_done, on_error=_failed)

    # ------------------------------------------------------------------ theme
    def on_show(self) -> None:
        pass

    def on_hide(self) -> None:
        pass

    def on_theme(self) -> None:
        pass
