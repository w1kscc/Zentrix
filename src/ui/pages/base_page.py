"""Shared page helpers."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from ..widgets import Page

STATUS_TEXT = {
    "running": "Работает",
    "starting": "Запуск…",
    "stopping": "Остановка…",
    "stopped": "Выключен",
    "error": "Ошибка",
    "missing": "Не настроен",
}

STATUS_KIND = {
    "running": "ok",
    "starting": "info",
    "stopping": "info",
    "stopped": "muted",
    "error": "err",
    "missing": "warn",
}


def page_heading(title: str, subtitle: str = "") -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(2, 0, 2, 0)
    layout.setSpacing(3)
    label = QLabel(title)
    label.setObjectName("h1")
    layout.addWidget(label)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        layout.addWidget(sub)
    return widget


__all__ = ["Page", "page_heading", "STATUS_TEXT", "STATUS_KIND"]
