"""Command palette (Ctrl+K): quick fuzzy access to pages and actions."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QVBoxLayout, QWidget,
)

from .. import commands
from .widgets import icon


class CommandPalette(QFrame):
    """Modal-style floating palette owned by the main window."""

    command_chosen = Signal(object)  # commands.Command

    def __init__(self, palette_obj, window, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("commandPalette")
        self._palette = palette_obj
        self._window = window
        self._commands: list[commands.Command] = []
        self.setFixedWidth(520)
        self.hide()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Команда или страница…  (Enter — выполнить, Esc — закрыть)")
        self.input.textChanged.connect(self._refill)
        self.input.returnPressed.connect(self._run_current)
        layout.addWidget(self.input)

        self.list = QListWidget()
        self.list.itemActivated.connect(lambda _item: self._run_current())
        self.list.currentRowChanged.connect(self._on_row)
        layout.addWidget(self.list, 1)

        self.hint = QLabel("")
        self.hint.setObjectName("tiny")
        layout.addWidget(self.hint)

        close_shortcut = QShortcut(QKeySequence(Qt.Key_Escape), self)
        close_shortcut.activated.connect(self.close)
        self._shortcut = QShortcut(QKeySequence("Ctrl+K"), window)
        self._shortcut.activated.connect(self.open_palette)

    # ------------------------------------------------------------------- api
    def set_palette(self, palette_obj) -> None:
        self._palette = palette_obj
        for index in range(self.list.count()):
            item = self.list.item(index)
            widget = self.list.itemWidget(item)
            if widget:
                self._paint_row(widget, item)

    def open_palette(self) -> None:
        parent = self.parentWidget()
        if parent:
            geometry = parent.geometry()
            self.move((geometry.width() - self.width()) // 2, 90)
            self.resize(self.width(), min(420, geometry.height() - 160))
        self.raise_()
        self.show()
        self.input.clear()
        self.input.setFocus()
        self._refill("")

    def closeEvent(self, event) -> None:
        parent = self.parentWidget()
        if parent:
            parent.setFocus()
        super().closeEvent(event)

    # ---------------------------------------------------------------- internals
    def _paint_row(self, widget: QWidget, item: QListWidgetItem) -> None:
        command = item.data(Qt.UserRole)
        colour = self._palette.text
        muted = self._palette.muted
        widget.title.setStyleSheet(f"color: {colour}; font-weight: 600;")
        widget.hint.setStyleSheet(f"color: {muted};")
        if command:
            widget.icon_label.setPixmap(icon(
                "chevron" if command.key.startswith("go:") else "play",
                self._palette.accent, 14).pixmap(14, 14))

    def _on_row(self, row: int) -> None:
        item = self.list.item(row)
        if item is not None:
            self.hint.setText(str(item.data(Qt.UserRole + 1) or ""))

    def _refill(self, query: str) -> None:
        self._commands = commands.filter_commands(commands.all_commands(), query)
        self.list.clear()
        for command in self._commands:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, command)
            item.setData(Qt.UserRole + 1, command.hint)
            self.list.addItem(item)
            row = QWidget()
            layout = QHBoxLayout(row)
            layout.setContentsMargins(6, 4, 6, 4)
            layout.setSpacing(9)
            icon_label = QLabel()
            icon_label.setFixedSize(16, 16)
            title = QLabel(command.title)
            hint = QLabel(command.hint)
            hint.setObjectName("tiny")
            layout.addWidget(icon_label)
            layout.addWidget(title, 0)
            layout.addStretch(1)
            layout.addWidget(hint, 0)
            row.icon_label = icon_label  # type: ignore[attr-defined]
            row.title = title            # type: ignore[attr-defined]
            row.hint = hint              # type: ignore[attr-defined]
            self.list.setItemWidget(item, row)
            self._paint_row(row, item)
        if self._commands:
            self.list.setCurrentRow(0)
        else:
            self.hint.setText("Ничего не найдено")

    def _run_current(self) -> None:
        row = self.list.currentRow()
        if 0 <= row < len(self._commands):
            command = self._commands[row]
            self.close()
            self.command_chosen.emit(command)
