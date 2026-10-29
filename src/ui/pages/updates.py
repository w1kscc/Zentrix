"""Updates tab: Zapret, Happ, Hiddify and Zentrix itself."""

from __future__ import annotations

import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout, QWidget,
)

from ... import net, updater
from ...logger import get_logger
from .. import overlays, theme
from ..widgets import Badge, GlassCard, IconOrb, PrimaryButton, human_bytes, icon
from ..workers import run_task
from .base_page import Page, page_heading

log = get_logger("updates-page")

META = {
    "zapret": ("Zapret", "bolt", "zapret-discord-youtube-1.10.4", "Flowseal/zapret-discord-youtube", "MIT"),
    "happ": ("Happ", "globe", "happ-desktop-4.6.1", "Happ-proxy/happ-desktop", "Proprietary"),
    "hiddify": ("Hiddify", "shield", "hiddify-app-4.1.1", "hiddify/hiddify-app", "CC BY-NC-SA 4.0"),
    "zentrix": ("Zentrix", "download", "Самообновление приложения", "", "MIT"),
}


class ComponentCard(GlassCard):
    def __init__(self, key: str, palette_obj: theme.Palette, parent=None) -> None:
        name, icon_name, source, repo, license_name = META[key]
        subtitle = f"{source} · {repo}" if repo else source
        super().__init__(name, subtitle, icon_name, palette_obj, parent=parent)
        self.key = key
        self.status: updater.ComponentStatus | None = None
        current = updater.installed_version(key)
        self.badge = Badge("УСТАНОВЛЕНО" if current else "НЕ ПРОВЕРЯЛОСЬ",
                           "ok" if current else "muted")
        self.add_header_widget(self.badge)
        self.version_label = QLabel(f"Установлено: {current or '—'}")
        self.version_label.setObjectName("h2")
        self.body.addWidget(self.version_label)
        self.meta_label = QLabel(f"Лицензия: {license_name}")
        self.meta_label.setObjectName("tiny")
        self.body.addWidget(self.meta_label)
        self.notes_label = QLabel("")
        self.notes_label.setObjectName("tiny")
        self.notes_label.setWordWrap(True)
        self.notes_label.setMinimumHeight(32)
        self.body.addWidget(self.notes_label)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.hide()
        self.body.addWidget(self.progress)
        self.body.addStretch(1)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        self.check_button = QPushButton("Проверить")
        self.check_button.setProperty("variant", "chip")
        self.check_button.setFixedHeight(32)
        actions.addWidget(self.check_button)
        self.download_button = PrimaryButton("Скачать", "download", palette_obj)
        self.download_button.setFixedHeight(32)
        self.download_button.setEnabled(False)
        actions.addWidget(self.download_button)
        self.details_button = QPushButton("Детали")
        self.details_button.setProperty("variant", "ghost")
        self.details_button.setFixedHeight(32)
        self.details_button.setEnabled(False)
        actions.addWidget(self.details_button)
        actions.addStretch(1)
        self.body.addLayout(actions)

    def set_status(self, status: updater.ComponentStatus) -> None:
        self.status = status
        current = status.current or "не установлено"
        latest = status.latest or "—"
        self.version_label.setText(f"{current}  →  {latest}")
        if status.error:
            self.badge.update_badge("ОШИБКА", "err")
            self.notes_label.setText(status.error)
        elif not status.latest:
            self.badge.update_badge("НЕ ПРОВЕРЯЛОСЬ", "muted")
        elif status.has_update:
            self.badge.update_badge("ОБНОВЛЕНИЕ", "warn")
            self.notes_label.setText(status.notes or f"Доступна версия {status.latest}")
        else:
            self.badge.update_badge("АКТУАЛЬНО", "ok")
            self.notes_label.setText(status.notes or "Установлена последняя версия")
        self.download_button.setEnabled(bool(status.has_update and not status.error))
        self.details_button.setEnabled(bool(status.latest or status.error))
        self.check_button.setEnabled(True)

    def set_checking(self) -> None:
        self.badge.update_badge("ПРОВЕРКА…", "info")
        self.check_button.setEnabled(False)
        self.download_button.setEnabled(False)

    def set_progress(self, done: int, total: int) -> None:
        self.progress.show()
        self.progress.setValue(int(done * 100 / total) if total else min(95, self.progress.value() + 2))


class UpdatesPage(Page):
    key = "updates"

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        self.cards: dict[str, ComponentCard] = {}
        self._build()

    def _build(self) -> None:
        p = self.ctx.palette
        header = QWidget()
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(page_heading("Обновления",
                                             "GitHub API releases/latest · скачивание и установка"), 1)
        self.check_all_button = PrimaryButton("Проверить всё", "refresh", p)
        self.check_all_button.clicked.connect(self.check_all)
        header_layout.addWidget(self.check_all_button, 0, Qt.AlignBottom)
        self.add(header)

        self.summary = QLabel("Проверки ещё не запускались")
        self.summary.setObjectName("tiny")
        self.add(self.summary)

        grid = QGridLayout()
        grid.setSpacing(14)
        for index, key in enumerate(("zapret", "happ", "hiddify", "zentrix")):
            card = ComponentCard(key, p)
            card.check_button.clicked.connect(lambda _=False, k=key: self.check(k))
            card.download_button.clicked.connect(lambda _=False, k=key: self._install(k))
            card.details_button.clicked.connect(lambda _=False, k=key: self._details(k))
            self.cards[key] = card
            grid.addWidget(card, index // 2, index % 2)
        self.add_layout(grid)

        info = GlassCard("Источники и лицензии", "", "info", p)
        info_text = QLabel(
            "• <b>Zapret</b> — <a href='https://github.com/Flowseal/zapret-discord-youtube'>Flowseal/zapret-discord-youtube</a> "
            "(MIT), стратегии 1.10.4.<br>"
            "• <b>Happ</b> — <a href='https://github.com/Happ-proxy/happ-desktop'>Happ-proxy/happ-desktop</a> "
            "(4.6.1, проприетарная лицензия Happ); Zentrix использует собственное ядро Xray.<br>"
            "• <b>Hiddify</b> — <a href='https://github.com/hiddify/hiddify-app'>hiddify/hiddify-app</a> "
            "(4.1.1, CC BY-NC-SA 4.0); Zentrix использует ядро sing-box.<br>"
            "• Обновления движков скачиваются с GitHub и распаковываются в <code>engines/</code>. "
            "Установщики Happ/Hiddify сохраняются в <code>engines/&lt;движок&gt;/vendor</code> и не запускаются."
        )
        info_text.setObjectName("tiny")
        info_text.setWordWrap(True)
        info_text.setOpenExternalLinks(True)
        info_text.setTextFormat(Qt.RichText)
        info.add(info_text)
        self.add(info)
        self.finish()

    def on_show(self) -> None:
        last = int(self.ctx.settings.get("updates.last_check", 0) or 0)
        if last:
            self.summary.setText(f"Последняя проверка: {time.strftime('%d.%m.%Y %H:%M', time.localtime(last))}")
        else:
            self.check_all()

    # ----------------------------------------------------------------- checks
    def check_all(self) -> None:
        for key in self.cards:
            self.check(key)

    def check(self, key: str) -> None:
        card = self.cards[key]
        card.set_checking()
        run_task(self, updater.check, key,
                 on_done=lambda status, k=key: self._checked(k, status),
                 on_error=lambda message, k=key: self._check_failed(k, message))

    def _checked(self, key: str, status: updater.ComponentStatus) -> None:
        self.cards[key].set_status(status)
        self.ctx.settings.set("updates.last_check", int(time.time()), save=True)
        self.summary.setText(f"Проверка завершена: {time.strftime('%H:%M:%S')}")
        if key == "zentrix" and status.error:
            self.notes_hint(status.error)

    def _check_failed(self, key: str, message: str) -> None:
        card = self.cards[key]
        card.set_status(updater.ComponentStatus(
            key=key, name=META[key][0], error=message or "Не удалось проверить",
        ))
        self.summary.setText("Ошибка проверки")

    def notes_hint(self, text: str) -> None:
        self.summary.setText(text)

    # ------------------------------------------------------------------ install
    def _install(self, key: str) -> None:
        card = self.cards[key]
        card.progress.show()
        card.progress.setValue(0)
        card.download_button.setEnabled(False)
        self.ctx.notify(f"Скачивание обновления {META[key][0]}…", "info")
        run_task(self, updater.install, key, with_progress=True,
                 on_done=lambda result, k=key: self._installed(k, result),
                 on_error=lambda message, k=key: self._install_failed(k, message),
                 on_progress=card.set_progress)

    def _installed(self, key: str, result: dict) -> None:
        card = self.cards[key]
        card.progress.hide()
        card.download_button.setEnabled(True)
        message = result.get("message", "Готово")
        self.ctx.sound.play("update")
        if key == "zentrix":
            path = result.get("path")
            overlays.confirm(
                self.ctx.overlay,
                "Установщик Zentrix загружен",
                f"Файл: <code>{path}</code><br><br>Запустить установку сейчас? "
                "Приложение будет закрыто.",
                "Запустить установщик",
                lambda: self._run_installer(path),
            )
        else:
            self.ctx.notify(message, "ok", "update")
            if key == "zapret":
                self.ctx.zapret.log_line.emit("[Zentrix] Движок обновлён — перезапустите стратегию.")
        self.check(key)

    def _run_installer(self, path) -> None:
        if updater.launch_installer(path):
            self.ctx.notify("Установщик запущен", "info")
            self.ctx.window.request_quit()
        else:
            self.ctx.notify("Не удалось запустить установщик", "err")

    def _install_failed(self, key: str, message: str) -> None:
        card = self.cards[key]
        card.progress.hide()
        card.download_button.setEnabled(True)
        self.ctx.notify(f"Обновление {META[key][0]}: {message}", "err", "error")

    # ------------------------------------------------------------------ details
    def _details(self, key: str) -> None:
        card = self.cards[key]
        status = card.status
        if not status:
            return
        if status.error:
            body = f"<b>Ошибка:</b> {status.error}"
            if key != "zentrix":
                body += f"<br><br>Репозиторий: <code>{updater.component_repo(key)}</code>"
        else:
            notes = (status.notes or "").replace("<", "&lt;")
            body = (
                f"Установлено: <b>{status.current or '—'}</b><br>"
                f"Доступно: <b>{status.latest or '—'}</b><br>"
                f"Файл: <code>{status.asset_name or '—'}</code><br>"
                f"Лицензия: {status.license}<br><br>"
                f"<div style='white-space:pre-wrap'>{notes}</div>"
            )
        content = QLabel(body)
        content.setWordWrap(True)
        content.setTextFormat(Qt.RichText)
        content.setObjectName("tiny")
        overlays.panel_with_actions(
            self.ctx.overlay,
            f"{META[key][0]} · детали обновления",
            content,
            [("Закрыть", "primary", self.ctx.overlay.close_panel)],
        )
