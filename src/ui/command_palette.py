"""Command palette (Ctrl+K): fuzzy jump to pages and quick actions."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from .widgets import icon

ENTRY_PAGES = "page"
ENTRY_ACTION = "action"
ENTRY_SETTING = "setting"


class CommandPalette(QWidget):
    """Searchable list of commands. Executes the selected entry on Enter."""

    def __init__(self, context, entries: list[dict], parent=None) -> None:
        super().__init__(parent)
        self.ctx = context
        self._entries = entries
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Введите команду или раздел…")
        self.search.textChanged.connect(self._filter)
        self.search.returnPressed.connect(self._execute_current)
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.setWordWrap(False)
        self.list.itemActivated.connect(lambda _item: self._execute_current())
        self.list.clicked.connect(lambda _index: self._execute_current())
        layout.addWidget(self.list, 1)

        self._filter("")
        self.search.setFocus()

    def _entry_label(self, entry: dict) -> str:
        suffix = f"   ·   {entry['hint']}" if entry.get("hint") else ""
        return f"{entry['label']}{suffix}"

    def _filter(self, text: str) -> None:
        needle = text.strip().lower()
        self.list.clear()
        for entry in self._entries:
            haystack = f"{entry['label']} {entry.get('hint', '')} {entry.get('keywords', '')}"
            if needle and not any(part in haystack.lower() for part in needle.split()):
                continue
            item = QListWidgetItem(self._entry_label(entry))
            item.setData(Qt.UserRole, entry["label"])
            item.setIcon(icon(entry.get("icon_name", "chevron"),
                              self.ctx.palette.accent, 18))
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def keyPressEvent(self, event) -> None:  # arrow keys inside the list
        if event.key() in (Qt.Key_Down, Qt.Key_Up) and not self.list.hasFocus():
            row = self.list.currentRow() + (1 if event.key() == Qt.Key_Down else -1)
            row = max(0, min(self.list.count() - 1, row))
            self.list.setCurrentRow(row)
            self.list.setFocus()
            event.accept()
            return
        super().keyPressEvent(event)

    def _execute_current(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        label = str(item.data(Qt.UserRole) or item.text())
        entry = next((e for e in self._entries if e["label"] == label), None)
        if entry is None:
            return
        self.ctx.overlay.close_panel()
        try:
            entry["run"]()
        except Exception:
            from ..logger import get_logger

            get_logger("palette").exception("Не удалось выполнить команду")


def default_entries(context) -> list[dict]:
    """Entries every user sees: navigation and primary toggles."""

    def navigate(key: str, label: str, hint: str, name: str, keywords: str = "") -> dict:
        return {"label": label, "hint": hint, "icon_name": name, "keywords": keywords,
                "run": (lambda k=key: context.navigate(k))}

    entries: list[dict] = [
        navigate("home", "Открыть главную", "", "home", "start главная"),
        navigate("zapret", "Открыть Zapret", "", "bolt", "обход стратегии"),
        navigate("vpn", "Открыть VPN", "", "globe", "прокси сервер"),
        navigate("blockcheck", "Открыть проверки", "", "target", "блокировки диагностика"),
        navigate("tools", "Открыть инструменты", "", "wrench", "dns hosts починить"),
        navigate("monitor", "Открыть мониторинг", "", "activity", "трафик скорость"),
        navigate("updates", "Открыть обновления", "", "download", "версия ядро"),
        navigate("settings", "Открыть настройки", "", "settings", "опции оформление"),
    ]

    window = context.window
    if window is not None:
        entries.append({
            "label": "Включить / выключить Zapret", "hint": "переключение", "icon_name": "power",
            "keywords": "обход включить выключить zapret toggle",
            "run": window.toggle_zapret,
        })
        entries.append({
            "label": "Свернуть в трей", "hint": "Ctrl+Shift+Z", "icon_name": "close",
            "keywords": "трей скрыть hide tray", "run": window.hide_to_tray,
        })
    entries.append({
        "label": "Проверить блокировки", "hint": "сервисы", "icon_name": "target",
        "keywords": "diagnostics ютуб дискорд", "run": lambda: context.navigate("blockcheck"),
    })
    return entries
