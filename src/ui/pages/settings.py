"""Settings page: appearance, sounds, engines, maintenance and about."""

from __future__ import annotations

import time
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFileDialog, QFontComboBox, QGridLayout,
    QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QProgressBar, QPushButton,
    QVBoxLayout, QWidget,
)

from ... import constants, paths, winapi
from ...cleaner import CATEGORY_LABELS, CleanReport, Cleaner
from ...logger import get_logger
from ...presets import DEFAULT_NAME, presets as preset_store
from ...sound_generator import TONE_PROFILES
from .. import overlays, theme
from ..widgets import (
    Badge, ColorRow, Divider, GlassCard, PrimaryButton, SliderRow, ToggleRow, human_bytes, icon,
)
from ..workers import run_task
from .base_page import Page, page_heading

log = get_logger("settings-page")

TONE_LABELS = {
    "soft": "Мягкий (колокольчик)",
    "standard": "Стандартный",
    "bright": "Яркий",
}

MIT_TEXT = """MIT License

Copyright (c) 2026 Zentrix Project

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

SECTIONS = (
    ("appearance", "Оформление", "palette"),
    ("sounds", "Звук", "volume"),
    ("engines", "Движки", "cpu"),
    ("maintenance", "Обслуживание", "trash"),
    ("about", "О программе", "info"),
)


class SettingsPage(Page):
    key = "settings"

    def __init__(self, context, parent=None) -> None:
        super().__init__(context, parent)
        self.cleaner = Cleaner()
        self._toggles: list[ToggleRow] = []
        self._section_buttons: list[QPushButton] = []
        self._scan_report: CleanReport | None = None
        self._build()
        self._sync_controls()
        self.on_theme()

    # ------------------------------------------------------------------ build
    def _build(self) -> None:
        p = self.ctx.palette
        self.add(page_heading("Настройки", "Оформление, звук, движки и обслуживание Zentrix"))

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

        # A QStackedWidget reports the largest page height to the outer scroll
        # area, which left a large gap above shorter sections. Only the active
        # section is attached to this host instead.
        self.section_host = QWidget()
        self.section_layout = QVBoxLayout(self.section_host)
        self.section_layout.setContentsMargins(0, 0, 0, 0)
        self.section_layout.setSpacing(0)
        self._sections = [
            self._build_appearance(),
            self._build_sounds(),
            self._build_engines(),
            self._build_maintenance(),
            self._build_about(),
        ]
        for section in self._sections:
            section.hide()
        self.section_layout.addWidget(self._sections[0])
        self._sections[0].show()
        self.add(self.section_host)
        self.finish()

    def _page(self) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 2, 0)
        layout.setSpacing(14)
        return page, layout

    # ------------------------------------------------------------ appearance
    def _build_appearance(self) -> QWidget:
        p = self.ctx.palette
        page, layout = self._page()

        theme_card = GlassCard("Тема оформления", "Светлая и тёмная палитры", "palette", p)
        row = QHBoxLayout()
        row.setSpacing(8)
        row.addWidget(QLabel("Тема"))
        self.dark_button = QPushButton("Тёмная")
        self.light_button = QPushButton("Светлая")
        theme_group = QButtonGroup(self)
        theme_group.setExclusive(True)
        for index, button in enumerate((self.dark_button, self.light_button)):
            button.setCheckable(True)
            button.setProperty("variant", "chip")
            button.setCursor(Qt.PointingHandCursor)
            theme_group.addButton(button, index)
            row.addWidget(button)
        theme_group.idClicked.connect(lambda index: self._set_theme("dark" if index == 0 else "light"))
        row.addStretch(1)
        reset = QPushButton("Сбросить оформление")
        reset.setProperty("variant", "ghost")
        reset.clicked.connect(self._reset_appearance)
        row.addWidget(reset)
        theme_card.add_layout(row)
        self.theme_group = theme_group
        layout.addWidget(theme_card)

        color_card = GlassCard("Акценты", "Цвета кнопок, графиков и подсветки", "palette", p)
        appearance = self.ctx.settings.section("appearance")
        self.accent_row = ColorRow("Основной акцент", str(appearance.get("accent", "#7C5CFF")), p)
        self.accent_row.changed.connect(lambda value: self._set_appearance(accent=value))
        color_card.add(self.accent_row)
        self.accent2_row = ColorRow("Второй акцент", str(appearance.get("accent2", "#22D3EE")), p)
        self.accent2_row.changed.connect(lambda value: self._set_appearance(accent2=value))
        color_card.add(self.accent2_row)
        layout.addWidget(color_card)

        shape_card = GlassCard("Форма и контраст", "Скругления, прозрачность и размер шрифта",
                               "filter", p)
        self.radius_row = SliderRow("Скругление карточек", 0, 30,
                                    float(appearance.get("radius", 18) or 18), " px", p)
        self.radius_row.value_changed.connect(
            lambda value: self._set_appearance(radius=int(round(value)))
        )
        shape_card.add(self.radius_row)
        self.opacity_row = SliderRow("Плотность карточек", 0.15, 0.95,
                                     float(appearance.get("card_opacity", 0.62) or 0.62), "", p)
        self.opacity_row.value_changed.connect(
            lambda value: self._set_appearance(card_opacity=round(float(value), 2))
        )
        shape_card.add(self.opacity_row)
        self.border_row = SliderRow("Контраст границ", 0.02, 0.40,
                                    float(appearance.get("border_opacity", 0.10) or 0.10), "", p)
        self.border_row.value_changed.connect(
            lambda value: self._set_appearance(border_opacity=round(float(value), 2))
        )
        shape_card.add(self.border_row)
        self.font_size_row = SliderRow("Размер шрифта", 8, 14,
                                       float(appearance.get("font_size", 10) or 10), " pt", p)
        self.font_size_row.value_changed.connect(
            lambda value: self._set_appearance(font_size=int(round(value)))
        )
        shape_card.add(self.font_size_row)

        font_row = QHBoxLayout()
        font_row.setSpacing(8)
        font_row.addWidget(QLabel("Шрифт"))
        self.font_combo = QFontComboBox()
        self.font_combo.setMinimumWidth(240)
        self.font_combo.currentFontChanged.connect(self._font_changed)
        font_row.addWidget(self.font_combo, 1)
        import_font = QPushButton("Загрузить файл…")
        import_font.clicked.connect(self._load_font)
        font_row.addWidget(import_font)
        shape_card.add_layout(font_row)
        layout.addWidget(shape_card)

        presets_card = GlassCard("Пресеты оформления", "Сохраняйте и переносите настройки между ПК",
                                 "copy", p)
        preset_row = QHBoxLayout()
        preset_row.setSpacing(8)
        preset_row.addWidget(QLabel("Пресет"))
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumWidth(220)
        preset_row.addWidget(self.preset_combo, 1)
        apply_button = QPushButton("Применить")
        apply_button.setProperty("variant", "primary")
        apply_button.clicked.connect(self._apply_preset)
        preset_row.addWidget(apply_button)
        presets_card.add_layout(preset_row)
        preset_actions = QHBoxLayout()
        preset_actions.setSpacing(8)
        for text, callback in (
            ("Сохранить как…", self._save_preset),
            ("Удалить", self._delete_preset),
            ("Экспорт…", self._export_preset),
            ("Импорт…", self._import_preset),
        ):
            button = QPushButton(text)
            button.setProperty("variant", "chip")
            button.setFixedHeight(32)
            button.clicked.connect(callback)
            preset_actions.addWidget(button)
        preset_actions.addStretch(1)
        presets_card.add_layout(preset_actions)
        layout.addWidget(presets_card)

        video_card = GlassCard("Видео-фон", "Необязательный ролик за интерфейсом (без звука)",
                               "play", p)
        video = self.ctx.settings.section("appearance")
        self.video_toggle = ToggleRow(
            "Включить видео-фон",
            "Декодирование идёт через GPU; при слабом ПК лучше оставить градиент",
            bool(video.get("video_enabled", True)), p,
        )
        self.video_toggle.toggled.connect(self._video_enabled_changed)
        video_card.add(self.video_toggle)
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        self.video_path = QLineEdit(str(video.get("video_path", "") or ""))
        self.video_path.setPlaceholderText(r"C:\Videos\background.mp4")
        path_row.addWidget(self.video_path, 1)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self._browse_video)
        path_row.addWidget(browse)
        apply_video = QPushButton("Применить")
        apply_video.setProperty("variant", "primary")
        apply_video.clicked.connect(self._apply_video_path)
        path_row.addWidget(apply_video)
        video_card.add_layout(path_row)
        self.video_dim_row = SliderRow("Затемнение", 0.0, 0.9,
                                       float(video.get("video_dim", 0.58) or 0.58), "", p)
        self.video_dim_row.value_changed.connect(
            lambda value: self._set_video(dim=round(float(value), 2))
        )
        video_card.add(self.video_dim_row)
        self.video_mute_row = ToggleRow("Без звука", "Рекомендуется: звук Zentrix не перекрывается",
                                        bool(video.get("video_muted", True)), p)
        self.video_mute_row.toggled.connect(lambda value: self._set_video(muted=bool(value)))
        video_card.add(self.video_mute_row)
        layout.addWidget(video_card)
        layout.addStretch(1)
        return page

    # ---------------------------------------------------------------- sounds
    def _build_sounds(self) -> QWidget:
        p = self.ctx.palette
        page, layout = self._page()
        sounds = self.ctx.settings.section("sounds")

        main_card = GlassCard("Звуковая схема", "Все звуки синтезируются программно — аудиофайлов нет",
                              "volume", p)
        self.sound_toggle = ToggleRow("Звуки интерфейса", "Короткие отклики на действия",
                                      bool(sounds.get("enabled", True)), p)
        self.sound_toggle.toggled.connect(lambda value: self._set_sound(enabled=bool(value)))
        main_card.add(self.sound_toggle)
        self.volume_row = SliderRow("Громкость", 0, 100, float(sounds.get("volume", 40) or 0), " %", p)
        self.volume_row.value_changed.connect(
            lambda value: self._set_sound(volume=int(round(value)))
        )
        main_card.add(self.volume_row)
        tone_row = QHBoxLayout()
        tone_row.setSpacing(8)
        tone_row.addWidget(QLabel("Тембр"))
        self.tone_combo = QComboBox()
        for key in TONE_PROFILES:
            self.tone_combo.addItem(TONE_LABELS.get(key, key), key)
        tone_row.addWidget(self.tone_combo, 1)
        preview = QPushButton("Прослушать")
        preview.setIcon(icon("play", p.accent, 17))
        preview.clicked.connect(lambda: self.ctx.sound.preview("notify"))
        tone_row.addWidget(preview)
        main_card.add_layout(tone_row)
        self.tone_combo.currentIndexChanged.connect(self._tone_changed)
        self.sound_info = QLabel("")
        self.sound_info.setObjectName("tiny")
        main_card.add(self.sound_info)
        layout.addWidget(main_card)

        events_card = GlassCard("События", "Нажмите, чтобы прослушать конкретный звук", "activity", p)
        grid = QGridLayout()
        grid.setSpacing(8)
        for index, (event, label) in enumerate(constants.SOUND_EVENTS):
            button = QPushButton(label)
            button.setProperty("variant", "chip")
            button.setFixedHeight(34)
            button.setIcon(icon("volume", p.accent, 16))
            button.clicked.connect(lambda _=False, e=event: self.ctx.sound.preview(e))
            grid.addWidget(button, index // 3, index % 3)
        events_card.add_layout(grid)
        actions = QHBoxLayout()
        actions.setSpacing(8)
        regenerate = QPushButton("Перегенерировать все")
        regenerate.setIcon(icon("refresh", p.accent, 17))
        regenerate.clicked.connect(self._regenerate_sounds)
        actions.addWidget(regenerate)
        clear = QPushButton("Очистить кэш")
        clear.setProperty("variant", "ghost")
        clear.clicked.connect(self._clear_sound_cache)
        actions.addWidget(clear)
        actions.addStretch(1)
        events_card.add_layout(actions)
        layout.addWidget(events_card)
        layout.addStretch(1)
        return page

    # --------------------------------------------------------------- engines
    def _build_engines(self) -> QWidget:
        p = self.ctx.palette
        page, layout = self._page()

        zapret_card = GlassCard("Zapret", "Папка zapret-discord-youtube и выбранная стратегия",
                                "bolt", p)
        zapret_row = QHBoxLayout()
        zapret_row.setSpacing(8)
        self.zapret_path = QLineEdit()
        self.zapret_path.setPlaceholderText(r"C:\...\zapret-discord-youtube-1.10.4")
        zapret_row.addWidget(self.zapret_path, 1)
        browse = QPushButton("Обзор…")
        browse.clicked.connect(self._browse_zapret)
        zapret_row.addWidget(browse)
        apply = QPushButton("Применить")
        apply.setProperty("variant", "primary")
        apply.clicked.connect(self._apply_zapret_path)
        zapret_row.addWidget(apply)
        zapret_card.add_layout(zapret_row)
        strategy_row = QHBoxLayout()
        strategy_row.setSpacing(8)
        strategy_row.addWidget(QLabel("Стратегия"))
        self.strategy_combo = QComboBox()
        self.strategy_combo.setMinimumWidth(260)
        self.strategy_combo.currentIndexChanged.connect(self._strategy_changed)
        strategy_row.addWidget(self.strategy_combo, 1)
        open_zapret = QPushButton("Открыть вкладку")
        open_zapret.setProperty("variant", "chip")
        open_zapret.clicked.connect(lambda: self.ctx.navigate("zapret"))
        strategy_row.addWidget(open_zapret)
        zapret_card.add_layout(strategy_row)
        self.zapret_state = QLabel("")
        self.zapret_state.setObjectName("tiny")
        self.zapret_state.setWordWrap(True)
        zapret_card.add(self.zapret_state)
        if not self.ctx.admin():
            admin_button = QPushButton("Перезапустить от администратора")
            admin_button.setIcon(icon("shield", p.accent, 17))
            admin_button.clicked.connect(self._admin_help)
            zapret_card.add(admin_button, 0)
        layout.addWidget(zapret_card)

        for engine, title, description in (
            (self.ctx.happ, "Happ · Xray", "Ядро Xray-core и ссылки vless / vmess"),
            (self.ctx.hiddify, "Hiddify · sing-box", "Ядро sing-box и мультипротокольные ссылки"),
        ):
            card = GlassCard(title, description, "globe" if engine.key == "happ" else "shield", p)
            state = QLabel("")
            state.setObjectName("tiny")
            state.setWordWrap(True)
            card.add(state)
            setattr(self, f"_{engine.key}_state", state)
            row = QHBoxLayout()
            row.setSpacing(8)
            open_button = QPushButton("Открыть вкладку")
            open_button.setProperty("variant", "chip")
            open_button.clicked.connect(lambda _=False, k=engine.key: self.ctx.navigate(k))
            row.addWidget(open_button)
            row.addStretch(1)
            card.add_layout(row)
            auto = ToggleRow("Автозапуск в Zentrix", "Подключаться при старте приложения",
                             bool(self.ctx.settings.get(f"{engine.key}.autostart", False)), p)
            auto.toggled.connect(
                lambda value, e=engine: self.ctx.settings.set(f"{e.key}.autostart", bool(value))
            )
            self._toggles.append(auto)
            card.add(auto)
            layout.addWidget(card)

        system_card = GlassCard("Система", "Запуск Zentrix и поведение окна", "settings", p)
        self.os_autostart = ToggleRow("Запускать при входе в Windows",
                                      "Добавить Zentrix в автозагрузку пользователя",
                                      winapi.is_autostart_enabled(), p)
        self.os_autostart.toggled.connect(self._os_autostart_changed)
        self._toggles.append(self.os_autostart)
        system_card.add(self.os_autostart)
        self.start_minimized = ToggleRow(
            "Стартовать свёрнутым", "Сразу в системный трей, без показа окна",
            bool(self.ctx.settings.get("general.start_minimized", False)), p,
        )
        self.start_minimized.toggled.connect(
            lambda value: self.ctx.settings.set("general.start_minimized", bool(value))
        )
        self._toggles.append(self.start_minimized)
        system_card.add(self.start_minimized)
        self.close_to_tray = ToggleRow(
            "Закрывать в трей", "Кнопка ✕ сворачивает Zentrix, а не завершает работу",
            bool(self.ctx.settings.get("general.close_to_tray", True)), p,
        )
        self.close_to_tray.toggled.connect(
            lambda value: self.ctx.settings.set("general.close_to_tray", bool(value))
        )
        self._toggles.append(self.close_to_tray)
        system_card.add(self.close_to_tray)
        layout.addWidget(system_card)
        layout.addStretch(1)
        return page

    # ----------------------------------------------------------- maintenance
    def _build_maintenance(self) -> QWidget:
        p = self.ctx.palette
        page, layout = self._page()

        clean_card = GlassCard(
            "Очистка лишних файлов",
            "Перед удалением Zentrix показывает список и объём. Движки в работе не затрагиваются.",
            "trash", p,
        )
        self.auto_clean = ToggleRow(
            "Автоочистка при запуске", "Только безопасные категории: логи, temp, старые архивы",
            bool(self.ctx.settings.get("general.auto_clean", False)), p,
        )
        self.auto_clean.toggled.connect(
            lambda value: self.ctx.settings.set("general.auto_clean", bool(value))
        )
        self._toggles.append(self.auto_clean)
        clean_card.add(self.auto_clean)
        self.clean_days = SliderRow(
            "Хранить файлы обновлений", 1, 30,
            float(self.ctx.settings.get("general.auto_clean_days", 7) or 7), " дн.", p,
        )
        self.clean_days.value_changed.connect(
            lambda value: self.ctx.settings.set("general.auto_clean_days", int(round(value)))
        )
        clean_card.add(self.clean_days)
        self.include_presets = ToggleRow(
            "Учитывать неиспользуемые пресеты", "Пресет, выбранный в оформлении, защищён",
            False, p,
        )
        self._toggles.append(self.include_presets)
        clean_card.add(self.include_presets)
        scan_row = QHBoxLayout()
        scan_row.setSpacing(8)
        self.scan_button = PrimaryButton("Сканировать и показать отчёт", "refresh", p)
        self.scan_button.clicked.connect(self._scan_cleaner)
        scan_row.addWidget(self.scan_button)
        scan_row.addStretch(1)
        clean_card.add_layout(scan_row)
        self.clean_progress = QProgressBar()
        self.clean_progress.setRange(0, 100)
        self.clean_progress.hide()
        clean_card.add(self.clean_progress)
        self.clean_result = QLabel("")
        self.clean_result.setObjectName("tiny")
        self.clean_result.setWordWrap(True)
        clean_card.add(self.clean_result)
        layout.addWidget(clean_card)

        stats_card = GlassCard("Обслуживание", "Пути данных и журналов", "folder", p)
        self.maintenance_stats = QLabel("")
        self.maintenance_stats.setObjectName("tiny")
        self.maintenance_stats.setWordWrap(True)
        stats_card.add(self.maintenance_stats)
        row = QHBoxLayout()
        row.setSpacing(8)
        for text, path in (
            ("Папка данных", paths.DATA_DIR),
            ("Журналы", paths.LOGS_DIR),
            ("Пресеты", paths.PRESETS_DIR),
        ):
            button = QPushButton(text)
            button.setProperty("variant", "chip")
            button.setFixedHeight(32)
            button.clicked.connect(lambda _=False, target=path: winapi.open_in_explorer(target))
            row.addWidget(button)
        row.addStretch(1)
        stats_card.add_layout(row)
        layout.addWidget(stats_card)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------ about
    def _build_about(self) -> QWidget:
        p = self.ctx.palette
        page, layout = self._page()

        hero = GlassCard(strong=True)
        row = QHBoxLayout()
        row.setSpacing(18)
        logo = QLabel()
        from ..widgets import brand_pixmap

        pixmap = brand_pixmap(96)
        if not pixmap.isNull():
            logo.setPixmap(pixmap)
        logo.setFixedSize(96, 96)
        row.addWidget(logo, 0, Qt.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(5)
        title = QLabel("Zentrix")
        title.setObjectName("h1")
        column.addWidget(title)
        version = QLabel(f"Версия {constants.APP_VERSION} · {constants.APP_LICENSE}")
        version.setObjectName("muted")
        column.addWidget(version)
        description = QLabel(
            "Единое окно для Zapret, Happ и Hiddify: обход блокировок, прокси, "
            "мониторинг трафика и диагностика — без консолей и лишних процессов."
        )
        description.setObjectName("tiny")
        description.setWordWrap(True)
        column.addWidget(description)
        links = QLabel(
            f"<a href='{constants.APP_HOMEPAGE}'>Сайт проекта</a> · "
            "<a href='https://github.com/Flowseal/zapret-discord-youtube'>Zapret</a> · "
            "<a href='https://github.com/Happ-proxy/happ-desktop'>Happ</a> · "
            "<a href='https://github.com/hiddify/hiddify-app'>Hiddify</a>"
        )
        links.setOpenExternalLinks(True)
        links.setTextFormat(Qt.RichText)
        links.setObjectName("tiny")
        column.addWidget(links)
        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        updates = PrimaryButton("Проверить обновления", "download", p)
        updates.clicked.connect(lambda: self.ctx.navigate("updates"))
        buttons.addWidget(updates)
        license_button = QPushButton("Лицензия MIT")
        license_button.setProperty("variant", "chip")
        license_button.clicked.connect(self._show_license)
        buttons.addWidget(license_button)
        buttons.addStretch(1)
        column.addLayout(buttons)
        row.addLayout(column, 1)
        hero.body.addLayout(row)
        layout.addWidget(hero)

        sources = GlassCard("Источники и лицензии", "Zentrix не изменяет лицензии upstream-проектов",
                            "link", p)
        text = QLabel(
            "• <b>zapret-discord-youtube 1.10.4</b> — Flowseal, лицензия MIT. "
            "Zentrix разбирает .bat-стратегии и запускает winws.exe напрямую.<br>"
            "• <b>Happ Desktop 4.6.1</b> — Happ-proxy, проприетарная лицензия Happ. "
            "Используется только идея headless-подключения; ядро — Xray-core (MPL-2.0).<br>"
            "• <b>Hiddify 4.1.1</b> — Hiddify, CC BY-NC-SA 4.0. Ядро — sing-box (GPL-3.0).<br>"
            "• <b>PySide6 / Qt 6</b> — LGPL-3.0. <b>psutil</b> — BSD-3-Clause.<br><br>"
            "Бинарники движков не входят в репозиторий и не поставляются с исходниками: "
            "Zentrix скачивает их с официальных GitHub-релизов по запросу пользователя и "
            "распаковывает в папку <code>engines/</code>."
        )
        text.setObjectName("tiny")
        text.setWordWrap(True)
        text.setTextFormat(Qt.RichText)
        text.setOpenExternalLinks(True)
        sources.add(text)
        layout.addWidget(sources)

        tech = GlassCard("Технологии и приватность", "", "cpu", p)
        tech_text = QLabel(
            "Python 3.12 · PySide6 6.12 · psutil · Pillow (сборка иконок).<br>"
            "Zentrix не собирает телеметрию и не отправляет данные на серверы, кроме запросов "
            "к GitHub API для проверки обновлений и DNS-over-HTTPS при диагностике.<br>"
            "Звуки синтезируются из синусоидальных партиал на лету и кэшируются в "
            "<code>%APPDATA%\\Zentrix\\cache\\sounds</code>."
        )
        tech_text.setObjectName("tiny")
        tech_text.setWordWrap(True)
        tech.add(tech_text)
        layout.addWidget(tech)
        layout.addStretch(1)
        return page

    # ------------------------------------------------------------------ theme
    def on_theme(self) -> None:
        p = self.ctx.palette
        for toggle in self._toggles:
            toggle.set_colors(p)
        self.sound_toggle.set_colors(p)
        self.video_toggle.set_colors(p)
        self.video_mute_row.set_colors(p)
        self.auto_clean.set_colors(p)
        for button, (_key, _label, icon_name) in zip(self._section_buttons, SECTIONS):
            button.setIcon(icon(icon_name, p.accent, 17))

    def _switch_section(self, index: int) -> None:
        if 0 <= index < len(self._sections):
            for position, section in enumerate(self._sections):
                if position == index:
                    if self.section_layout.indexOf(section) < 0:
                        self.section_layout.addWidget(section)
                    section.show()
                else:
                    section.hide()
                    if self.section_layout.indexOf(section) >= 0:
                        self.section_layout.removeWidget(section)
            self.section_host.updateGeometry()
            self._section_buttons[index].setChecked(True)
            self._sync_controls()

    # -------------------------------------------------------------- general
    def _set_appearance(self, **values) -> None:
        self.ctx.settings.update("appearance", values)

    def _set_video(self, **values) -> None:
        self.ctx.settings.update("appearance", values)
        self._apply_background()

    def _set_sound(self, **values) -> None:
        self.ctx.settings.update("sounds", values)
        self._refresh_sound_info()

    def _apply_background(self) -> None:
        window = self.ctx.window
        if window is not None and hasattr(window, "apply_background"):
            try:
                window.apply_background()
            except Exception:
                log.exception("Не удалось применить видео-фон")

    def _set_theme(self, name: str) -> None:
        defaults = theme.THEMES.get(name, theme.THEMES["dark"])
        self.ctx.settings.update("appearance", {
            "theme": name,
            "bg": defaults["bg"],
            "bg2": defaults["bg2"],
            "text": defaults["text"],
            "muted": defaults["muted"],
        })
        self.ctx.apply_theme()
        self._refresh_theme_buttons()
        self._apply_background()

    def _refresh_theme_buttons(self) -> None:
        is_dark = str(self.ctx.settings.get("appearance.theme", "dark")) != "light"
        self.dark_button.setChecked(is_dark)
        self.light_button.setChecked(not is_dark)

    def _reset_appearance(self) -> None:
        def _reset() -> None:
            from ...presets import default_preset

            self.ctx.settings.replace_section("appearance", default_preset()["appearance"])
            self.ctx.apply_theme()
            self._sync_controls()
            self._apply_background()
            self.ctx.notify("Оформление сброшено", "ok")

        overlays.confirm(
            self.ctx.overlay, "Сбросить оформление?",
            "Тема, цвета, шрифт, видео-фон и прозрачность вернутся к значениям по умолчанию. "
            "Пресеты и настройки движков не изменятся.",
            "Сбросить", _reset,
        )

    def _font_changed(self, font) -> None:
        family = font.family()
        if family:
            self._set_appearance(font_family=family)

    def _load_font(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Загрузить шрифт", str(Path.home()), "Шрифты (*.ttf *.otf);;Все файлы (*.*)"
        )
        if not path:
            return
        family = theme.load_custom_font(path)
        if not family:
            self.ctx.notify("Не удалось загрузить шрифт", "err")
            return
        self.font_combo.blockSignals(True)
        self.font_combo.setCurrentFont(QFont(family))
        self.font_combo.blockSignals(False)
        self._set_appearance(font_family=family)
        self.ctx.notify(f"Шрифт «{family}» применён", "ok")

    # ---------------------------------------------------------------- presets
    def _refresh_presets(self, select: str | None = None) -> None:
        names = preset_store.names()
        current = select or self.preset_combo.currentText() or str(
            self.ctx.settings.get("appearance.preset", DEFAULT_NAME) or DEFAULT_NAME
        )
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItems(names)
        index = self.preset_combo.findText(current)
        self.preset_combo.setCurrentIndex(max(0, index))
        self.preset_combo.blockSignals(False)

    def _apply_preset(self) -> None:
        name = self.preset_combo.currentText()
        if not name:
            return
        try:
            preset_store.apply(name)
        except Exception as exc:
            self.ctx.notify(f"Не удалось применить пресет: {exc}", "err")
            return
        self.ctx.apply_theme()
        self._sync_controls()
        self._apply_background()
        self.ctx.notify(f"Пресет «{name}» применён", "ok", "update")

    def _save_preset(self) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        label = QLabel("Имя пресета")
        layout.addWidget(label)
        edit = QLineEdit()
        edit.setPlaceholderText("Например, «Ночная тема»")
        edit.setMaxLength(48)
        layout.addWidget(edit)

        def _save() -> None:
            name = edit.text().strip()
            if not name:
                self.ctx.notify("Введите имя пресета", "warn")
                return
            try:
                preset_store.save(name)
            except Exception as exc:
                self.ctx.notify(str(exc), "err")
                return
            self.ctx.overlay.close_panel()
            self._refresh_presets(name)
            self.ctx.notify(f"Пресет «{name}» сохранён", "ok")

        overlays.panel_with_actions(
            self.ctx.overlay, "Сохранить пресет", content,
            [("Отмена", "ghost", self.ctx.overlay.close_panel), ("Сохранить", "primary", _save)],
        )
        edit.setFocus()

    def _delete_preset(self) -> None:
        name = self.preset_combo.currentText()
        if not name or name == DEFAULT_NAME:
            self.ctx.notify("Встроенный пресет удалить нельзя", "warn")
            return

        def _delete() -> None:
            if preset_store.delete(name):
                self._refresh_presets(DEFAULT_NAME)
                self.ctx.notify(f"Пресет «{name}» удалён", "info")
            else:
                self.ctx.notify("Пресет не найден", "err")

        overlays.confirm(self.ctx.overlay, "Удалить пресет?",
                         f"Файл пресета <b>{name}</b> будет удалён без возможности восстановления.",
                         "Удалить", _delete, danger=True)

    def _export_preset(self) -> None:
        name = self.preset_combo.currentText()
        if not name:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Экспорт пресета", str(Path.home() / f"{name}.json"), "JSON (*.json)"
        )
        if not path:
            return
        try:
            preset_store.export(name, path)
        except Exception as exc:
            self.ctx.notify(f"Экспорт: {exc}", "err")
            return
        self.ctx.notify(f"Пресет экспортирован: {Path(path).name}", "ok")

    def _import_preset(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Импорт пресета", str(Path.home()), "JSON (*.json);;Все файлы (*.*)"
        )
        if not path:
            return
        try:
            name = preset_store.import_file(path)
        except Exception as exc:
            self.ctx.notify(f"Импорт: {exc}", "err")
            return
        self._refresh_presets(name)
        self.ctx.notify(f"Пресет «{name}» импортирован", "ok")

    # ------------------------------------------------------------------ video
    def _video_enabled_changed(self, value: bool) -> None:
        self._set_video(video_enabled=bool(value))

    def _browse_video(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Видео-фон", str(Path.home()),
            "Видео (*.mp4 *.webm *.mov *.mkv);;Все файлы (*.*)",
        )
        if path:
            self.video_path.setText(path)
            self._apply_video_path()

    def _apply_video_path(self) -> None:
        path = self.video_path.text().strip()
        if path and not Path(path).exists():
            self.ctx.notify("Файл видео не найден", "err")
            return
        self._set_video(path=path, video_enabled=bool(path) if path else False)
        self.video_toggle.set_checked(bool(path))
        self.ctx.notify("Видео-фон обновлён" if path else "Видео-фон отключён", "ok")

    # ----------------------------------------------------------------- sounds
    def _tone_changed(self) -> None:
        tone = self.tone_combo.currentData()
        if not tone:
            return
        self._set_sound(tone=str(tone))
        self.ctx.sound.preview("notify")
        self._refresh_sound_info()

    def _regenerate_sounds(self) -> None:
        self.ctx.notify("Генерация звуков…", "info")
        run_task(
            self, self.ctx.sound.regenerate_all,
            on_done=lambda count: self._sounds_regenerated(count),
            on_error=lambda message: self.ctx.notify(f"Звуки: {message}", "err", "error"),
        )

    def _sounds_regenerated(self, count: int) -> None:
        self._refresh_sound_info()
        self.ctx.notify(f"Сгенерировано звуков: {count}", "ok", "update")

    def _clear_sound_cache(self) -> None:
        removed = self.ctx.sound.clear_cache()
        self._refresh_sound_info()
        self.ctx.notify(f"Удалено файлов: {removed}", "info")

    def _refresh_sound_info(self) -> None:
        files = list(paths.SOUNDS_CACHE_DIR.glob("*.wav"))
        total = 0
        for file in files:
            try:
                total += file.stat().st_size
            except OSError:
                continue
        self.sound_info.setText(
            f"Тембр: {TONE_LABELS.get(self.ctx.sound.tone, self.ctx.sound.tone)} · "
            f"кэш: {len(files)} файлов · {human_bytes(total)}"
        )

    # ----------------------------------------------------------------- engines
    def _reload_strategies(self) -> None:
        self.strategy_combo.blockSignals(True)
        self.strategy_combo.clear()
        current = str(self.ctx.settings.get("zapret.strategy", "general.bat"))
        index = 0
        for row, strategy in enumerate(self.ctx.zapret.strategies()):
            self.strategy_combo.addItem(f"{strategy.name} · {strategy.filename}", strategy.filename)
            if strategy.filename.lower() == current.lower():
                index = row
        if self.strategy_combo.count():
            self.strategy_combo.setCurrentIndex(index)
        self.strategy_combo.blockSignals(False)

    def _strategy_changed(self) -> None:
        filename = self.strategy_combo.currentData()
        if filename:
            self.ctx.settings.set("zapret.strategy", str(filename))

    def _browse_zapret(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Папка zapret-discord-youtube",
                                                  str(self.ctx.zapret.folder()))
        if folder:
            self.zapret_path.setText(folder)
            self._apply_zapret_path()

    def _apply_zapret_path(self) -> None:
        folder = self.zapret_path.text().strip()
        self.ctx.settings.set("zapret.path", folder)
        self._reload_strategies()
        self._refresh_engine_labels()
        self.ctx.notify("Путь к Zapret обновлён", "ok")

    def _os_autostart_changed(self, value: bool) -> None:
        if winapi.set_autostart(bool(value)):
            self.ctx.settings.set("general.autostart", bool(value))
            self.ctx.notify("Автозагрузка обновлена", "ok")
        else:
            self.os_autostart.set_checked(winapi.is_autostart_enabled())
            self.ctx.notify("Не удалось изменить автозагрузку", "err")

    def _admin_help(self) -> None:
        overlays.confirm(
            self.ctx.overlay, "Права администратора",
            "Для WinDivert, смены DNS и некоторых настроек нужны повышенные права.<br><br>"
            "Zentrix перезапустится от имени администратора. Настройки сохранятся.",
            "Перезапустить", self.ctx.relaunch_admin,
        )

    def _refresh_engine_labels(self) -> None:
        zapret = self.ctx.zapret
        self.zapret_path.setText(str(zapret.folder()))
        self.zapret_state.setText(
            f"winws.exe: {'найден' if zapret.is_available() else 'не найден'} · "
            f"{'администратор' if self.ctx.admin() else 'обычные права'} · "
            f"стратегий: {len(zapret.strategies())}"
        )
        for engine in (self.ctx.happ, self.ctx.hiddify):
            label = getattr(self, f"_{engine.key}_state", None)
            if label is None:
                continue
            core = engine.core_path()
            label.setText(
                f"Ядро: {core if core else 'не установлено'}\n"
                f"Порты: {engine.ports()[0]} / {engine.ports()[1]} · "
                f"серверов: {len(engine.nodes())}"
            )

    # ------------------------------------------------------------ maintenance
    def _scan_cleaner(self) -> None:
        self.scan_button.setEnabled(False)
        self.scan_button.setText("Сканирование…")
        self.clean_result.setText("Сканирование…")
        run_task(
            self, self.cleaner.scan,
            include_presets=self.include_presets.is_checked(),
            include_sound_cache=True,
            older_than_days=int(round(self.clean_days.value())),
            on_done=self._scan_done,
            on_error=self._scan_failed,
        )

    def _scan_failed(self, message: str) -> None:
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Сканировать и показать отчёт")
        self.clean_result.setText("")
        self.ctx.notify(f"Сканирование: {message}", "err", "error")

    def _scan_done(self, report: CleanReport) -> None:
        self.scan_button.setEnabled(True)
        self.scan_button.setText("Сканировать и показать отчёт")
        self._scan_report = report
        self.clean_result.setText(
            f"Найдено объектов: {len(report.items)} · {human_bytes(report.total_size)}"
            if report.items else "Лишних файлов не найдено."
        )
        if not report.items:
            overlays.info(
                self.ctx.overlay, "Очистка не требуется",
                f"Zentrix не нашёл лишних файлов.<br><br>Проверено в: "
                f"<code>{paths.DATA_DIR}</code> и <code>{paths.ENGINES_DIR}</code>.",
            )
            return
        self._show_clean_preview(report)

    def _show_clean_preview(self, report: CleanReport) -> None:
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        summary = QLabel(
            f"Найдено <b>{len(report.items)}</b> объектов на <b>{human_bytes(report.total_size)}</b>. "
            "Снимите галочки с категорий, которые нужно сохранить."
        )
        summary.setWordWrap(True)
        summary.setTextFormat(Qt.RichText)
        layout.addWidget(summary)

        checks: dict[str, QCheckBox] = {}
        grid = QGridLayout()
        grid.setSpacing(6)
        grouped = report.by_category()
        for row, (category, items) in enumerate(sorted(grouped.items())):
            size = sum(item.size for item in items)
            box = QCheckBox(
                f"{CATEGORY_LABELS.get(category, category)} · {len(items)} · {human_bytes(size)}"
            )
            box.setChecked(True)
            checks[category] = box
            grid.addWidget(box, row // 2, row % 2)
        layout.addLayout(grid)

        preview = QPlainTextEdit()
        preview.setReadOnly(True)
        preview.setObjectName("logView")
        preview.setMinimumHeight(220)
        lines = []
        for item in report.items[:200]:
            marker = "папка" if item.is_dir else "файл"
            lines.append(f"[{marker}] {item.path}  ·  {human_bytes(item.size)}  ·  {item.reason}")
        if len(report.items) > 200:
            lines.append(f"… и ещё {len(report.items) - 200} объектов")
        preview.setPlainText("\n".join(lines))
        layout.addWidget(preview)

        def _clean() -> None:
            selected = [category for category, box in checks.items() if box.isChecked()]
            if not selected:
                self.ctx.notify("Выберите хотя бы одну категорию", "warn")
                return
            items = [item for item in report.items if item.category in selected]
            self.ctx.overlay.close_panel()
            self._run_clean(items, selected)

        overlays.panel_with_actions(
            self.ctx.overlay, "Предпросмотр очистки", content,
            [("Отмена", "ghost", self.ctx.overlay.close_panel),
             ("Очистить выбранное", "danger", _clean)],
        )

    def _run_clean(self, items: list, categories: list[str]) -> None:
        self.clean_progress.show()
        self.clean_progress.setValue(0)
        self.clean_result.setText(f"Очистка: {len(items)} объектов…")
        run_task(
            self, self.cleaner.delete, items, with_progress=True,
            on_done=lambda outcome: self._clean_done(outcome, categories),
            on_error=self._clean_failed,
            on_progress=self._clean_progress_changed,
        )

    def _clean_progress_changed(self, done: int, total: int, name: str) -> None:
        self.clean_progress.setValue(int(done * 100 / total) if total else 0)
        self.clean_result.setText(f"Очистка: {done} из {total} · {name}")

    def _clean_done(self, outcome, categories: list[str]) -> None:
        self.clean_progress.hide()
        removed, freed, errors = outcome if isinstance(outcome, tuple) else (0, 0, [])
        self.ctx.sound.invalidate()
        if "sounds" in categories:
            self._refresh_sound_info()
        self._refresh_maintenance_stats()
        self.clean_result.setText(
            f"Удалено объектов: {removed} · освобождено {human_bytes(freed)}"
        )
        self.ctx.sound.play("update")
        if errors:
            body = "<br>".join(error.replace("<", "&lt;") for error in errors[:6])
            overlays.info(
                self.ctx.overlay, "Очистка завершена с замечаниями",
                f"Удалено: <b>{removed}</b> · освобождено <b>{human_bytes(freed)}</b>.<br><br>"
                f"Не удалось удалить:<br>{body}{'<br>…' if len(errors) > 6 else ''}",
            )
        else:
            self.ctx.notify(f"Очистка завершена · освобождено {human_bytes(freed)}", "ok", "update")

    def _clean_failed(self, message: str) -> None:
        self.clean_progress.hide()
        self.clean_result.setText("")
        self.ctx.notify(f"Очистка: {message}", "err", "error")

    def _refresh_maintenance_stats(self) -> None:
        last = int(self.ctx.settings.get("maintenance.last_clean", 0) or 0)
        total = int(self.ctx.settings.get("maintenance.cleaned_total", 0) or 0)
        last_text = time.strftime("%d.%m.%Y %H:%M", time.localtime(last)) if last else "ещё не выполнялась"
        self.maintenance_stats.setText(
            f"Последняя очистка: {last_text}<br>"
            f"Всего освобождено: {human_bytes(total)}<br>"
            f"Настройки: <code>{paths.SETTINGS_FILE}</code><br>"
            f"Журнал: <code>{paths.LOG_FILE}</code>"
        )

    # ------------------------------------------------------------------- about
    def _show_license(self) -> None:
        editor = QPlainTextEdit(MIT_TEXT)
        editor.setReadOnly(True)
        editor.setObjectName("logView")
        editor.setMinimumHeight(300)
        overlays.panel_with_actions(
            self.ctx.overlay, "Лицензия Zentrix", editor,
            [("Закрыть", "primary", self.ctx.overlay.close_panel)],
        )

    # ------------------------------------------------------------------- sync
    def _sync_controls(self) -> None:
        appearance = self.ctx.settings.section("appearance")
        sounds = self.ctx.settings.section("sounds")
        self._refresh_theme_buttons()
        self.accent_row.set_color(str(appearance.get("accent", "#7C5CFF")))
        self.accent2_row.set_color(str(appearance.get("accent2", "#22D3EE")))
        self.radius_row.set_value(float(appearance.get("radius", 18) or 18))
        self.opacity_row.set_value(float(appearance.get("card_opacity", 0.62) or 0.62))
        self.border_row.set_value(float(appearance.get("border_opacity", 0.10) or 0.10))
        self.font_size_row.set_value(float(appearance.get("font_size", 10) or 10))
        family = str(appearance.get("font_family", "Segoe UI") or "Segoe UI")
        self.font_combo.blockSignals(True)
        self.font_combo.setCurrentFont(QFont(family))
        self.font_combo.blockSignals(False)
        self.video_toggle.set_checked(bool(appearance.get("video_enabled", True)))
        self.video_path.setText(str(appearance.get("video_path", "") or ""))
        self.video_dim_row.set_value(float(appearance.get("video_dim", 0.58) or 0.58))
        self.video_mute_row.set_checked(bool(appearance.get("video_muted", True)))
        self._refresh_presets()

        self.sound_toggle.set_checked(bool(sounds.get("enabled", True)))
        self.volume_row.set_value(float(sounds.get("volume", 40) or 0))
        tone = str(sounds.get("tone", "soft") or "soft")
        index = self.tone_combo.findData(tone)
        self.tone_combo.blockSignals(True)
        self.tone_combo.setCurrentIndex(max(0, index))
        self.tone_combo.blockSignals(False)
        self._refresh_sound_info()

        self.zapret_path.setText(str(self.ctx.zapret.folder()))
        self._reload_strategies()
        self._refresh_engine_labels()

        self.os_autostart.set_checked(winapi.is_autostart_enabled())
        self.start_minimized.set_checked(bool(self.ctx.settings.get("general.start_minimized", False)))
        self.close_to_tray.set_checked(bool(self.ctx.settings.get("general.close_to_tray", True)))
        self.auto_clean.set_checked(bool(self.ctx.settings.get("general.auto_clean", False)))
        self.clean_days.set_value(float(self.ctx.settings.get("general.auto_clean_days", 7) or 7))
        self._refresh_maintenance_stats()

    def on_show(self) -> None:
        self._sync_controls()
