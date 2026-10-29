"""In-window overlay helpers (confirmations, info panels)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from . import theme


def rich_text(html: str) -> QLabel:
    label = QLabel(html)
    label.setWordWrap(True)
    label.setTextFormat(Qt.RichText)
    label.setOpenExternalLinks(True)
    return label


def confirm(overlay, title: str, message: str, confirm_text: str,
            on_confirm, *, cancel_text: str = "Отмена", danger: bool = False) -> None:
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(rich_text(message))

    def _confirm() -> None:
        overlay.close_panel()
        on_confirm()

    overlay.open_panel(
        title,
        content,
        [
            (cancel_text, "ghost", overlay.close_panel),
            (confirm_text, "danger" if danger else "primary", _confirm),
        ],
    )


def info(overlay, title: str, message: str, *, ok_text: str = "Понятно") -> None:
    content = QWidget()
    layout = QVBoxLayout(content)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.addWidget(rich_text(message))
    overlay.open_panel(title, content, [(ok_text, "primary", overlay.close_panel)])


def panel_with_actions(overlay, title: str, content: QWidget, actions: list[tuple]) -> None:
    overlay.open_panel(title, content, actions)
