"""Reusable, hand-painted widgets that give Zentrix its look.

Everything is lightweight: no per-frame timers unless a video background is
active, and expensive imports (QtMultimedia) happen lazily.
"""

from __future__ import annotations

import time
from collections import deque
from pathlib import Path

from PySide6.QtCore import (
    QByteArray, QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRectF,
    QSize, Qt, QTimer, QUrl, QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QGuiApplication, QIcon, QImage, QLinearGradient,
    QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
)
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QAbstractButton, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPlainTextEdit,
    QPushButton, QScrollArea, QSizePolicy, QSlider, QVBoxLayout, QWidget,
)

from .. import paths
from . import theme

_PIXMAP_CACHE: dict[tuple[str, str, int, float], QPixmap] = {}
_ICON_DIR = paths.ICONS_DIR


def human_bytes(value: float) -> str:
    return paths.human_size(max(0.0, value))


def human_speed(bytes_per_second: float) -> str:
    value = max(0.0, bytes_per_second)
    if value < 1024:
        return f"{value:.0f} Б/с"
    if value < 1024 * 1024:
        return f"{value / 1024:.1f} КБ/с"
    return f"{value / (1024 * 1024):.2f} МБ/с"


def human_mbps(bytes_per_second: float) -> str:
    return f"{max(0.0, bytes_per_second) * 8 / 1_000_000:.2f} Мбит/с"


def svg_pixmap(name: str, color: str, size: int) -> QPixmap:
    dpr = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
    key = (name, color, size, dpr)
    if key in _PIXMAP_CACHE:
        return _PIXMAP_CACHE[key]
    file = _ICON_DIR / f"{name}.svg"
    if not file.exists():
        return QPixmap()
    text = file.read_text(encoding="utf-8").replace("currentColor", color)
    # Every bundled SVG uses #EAF0FF as its default paint; retint all of them
    # (fill, stroke and the informational `color` attribute).
    text = text.replace("#EAF0FF", color)
    renderer = QSvgRenderer(QByteArray(text.encode("utf-8")))
    pixmap = QPixmap(int(size * dpr), int(size * dpr))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * dpr, size * dpr))
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    _PIXMAP_CACHE[key] = pixmap
    return pixmap


def icon(name: str, color: str = "#EAF0FF", size: int = 20) -> QIcon:
    return QIcon(svg_pixmap(name, color, size))


def brand_pixmap(size: int = 64) -> QPixmap:
    file = paths.BRAND_DIR / "png" / f"zentrix-{1024 if size > 512 else 256}.png"
    pixmap = QPixmap(str(file))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)


def set_prop(widget: QWidget, name: str, value) -> None:
    widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def repolish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


# --------------------------------------------------------------------- buttons
class NavButton(QAbstractButton):
    """Sidebar entry with an animated hover state and an accent indicator."""

    def __init__(self, label: str, icon_name: str, palette_obj: theme.Palette, parent=None,
                 badge: str = "") -> None:
        super().__init__(parent)
        self.label = label
        self.icon_name = icon_name
        self.badge = badge
        self._palette = palette_obj
        self._hover = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self.setCursor(Qt.PointingHandCursor)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(44)

    def _on_anim(self, value) -> None:
        self._hover = float(value)
        self.update()

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self._palette = palette_obj
        self.update()

    def enterEvent(self, event) -> None:
        self._animate(1.0)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self._animate(0.0)
        super().leaveEvent(event)

    def _animate(self, target: float) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._hover)
        self._anim.setEndValue(target)
        self._anim.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        p = self._palette
        rect = QRectF(0, 0, self.width(), self.height())
        active = self.isChecked()
        if active:
            painter.setBrush(theme.qcolor(p.accent, 0.18))
            painter.setPen(QPen(theme.qcolor(p.accent, 0.35), 1))
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)
        elif self._hover > 0.01:
            painter.setBrush(theme.qcolor(p.surface, 0.06 * self._hover if p.is_dark else 0.5 * self._hover))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), 12, 12)

        if active:
            painter.setBrush(QColor(p.accent))
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(QRectF(0, 12, 3, self.height() - 24), 1.5, 1.5)

        colour = p.accent if active else (theme.mix(p.muted, p.text, self._hover * 0.65))
        pixmap = svg_pixmap(self.icon_name, colour, 20)
        painter.drawPixmap(QRectF(15, (self.height() - 20) / 2, 20, 20), pixmap, QRectF(pixmap.rect()))

        painter.setPen(QColor(p.text if active else theme.mix(p.muted, p.text, 0.35 + self._hover * 0.5)))
        font = QFont(self.font())
        font.setPointSize(max(9, p.font_size))
        font.setWeight(QFont.DemiBold if active else QFont.Medium)
        painter.setFont(font)
        label_width = self.width() - 56 - (56 if self.badge else 0)
        painter.drawText(QRectF(46, 0, label_width, self.height()), Qt.AlignVCenter | Qt.AlignLeft, self.label)

        if self.badge:
            chip_font = QFont(self.font())
            chip_font.setPointSize(max(7, p.font_size - 2))
            chip_font.setWeight(QFont.Bold)
            painter.setFont(chip_font)
            metrics = QFontMetrics(chip_font)
            chip_width = max(40, metrics.horizontalAdvance(self.badge) + 16)
            chip = QRectF(self.width() - 14 - chip_width, (self.height() - 18) / 2, chip_width, 18)
            painter.setPen(Qt.NoPen)
            painter.setBrush(theme.qcolor(p.warning, 0.16))
            painter.drawRoundedRect(chip, 9, 9)
            painter.setPen(QColor(p.warning))
            painter.drawText(chip, Qt.AlignCenter, self.badge)
        painter.end()


class PrimaryButton(QPushButton):
    def __init__(self, text: str, icon_name: str = "", palette_obj: theme.Palette | None = None,
                 variant: str = "primary", parent=None) -> None:
        super().__init__(text, parent)
        self.setProperty("variant", variant)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(38)
        if icon_name and palette_obj:
            colour = "#FFFFFF" if variant == "primary" else palette_obj.text
            self.setIcon(icon(icon_name, colour, 18))
        self.setIconSize(QSize(17, 17))


class IconButton(QPushButton):
    def __init__(self, icon_name: str, palette_obj: theme.Palette, tooltip: str = "",
                 size: int = 34, parent=None) -> None:
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setIcon(icon(icon_name, palette_obj.muted, 18))
        self.setIconSize(QSize(18, 18))
        self.setProperty("variant", "ghost")
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(tooltip)
        self._icon_name = icon_name
        self._palette = palette_obj

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self._palette = palette_obj
        self.setIcon(icon(self._icon_name, palette_obj.muted, 18))


class ToggleSwitch(QAbstractButton):
    def __init__(self, checked: bool = False, parent=None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setChecked(checked)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(46, 26)
        self._position = 1.0 if checked else 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_value)
        self.toggled.connect(self._animate)
        self._accent = "#7C5CFF"
        self._muted = "#5B6478"

    def set_colors(self, accent: str, muted: str) -> None:
        self._accent = accent
        self._muted = muted
        self.update()

    def _on_value(self, value) -> None:
        self._position = float(value)
        self.update()

    def _animate(self, checked: bool) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._position)
        self._anim.setEndValue(1.0 if checked else 0.0)
        self._anim.start()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        track = QRectF(0, 0, self.width(), self.height())
        off = QColor(self._muted)
        on = QColor(self._accent)
        colour = QColor(
            int(off.red() + (on.red() - off.red()) * self._position),
            int(off.green() + (on.green() - off.green()) * self._position),
            int(off.blue() + (on.blue() - off.blue()) * self._position),
            int(90 + 120 * self._position),
        )
        painter.setPen(Qt.NoPen)
        painter.setBrush(colour)
        painter.drawRoundedRect(track, self.height() / 2, self.height() / 2)
        margin = 3.0
        diameter = self.height() - margin * 2
        x = margin + (self.width() - margin * 2 - diameter) * self._position
        painter.setBrush(QColor("#FFFFFF"))
        painter.drawEllipse(QRectF(x, margin, diameter, diameter))
        painter.end()


# ----------------------------------------------------------------------- cards
class GlassCard(QFrame):
    def __init__(self, title: str = "", subtitle: str = "", icon_name: str = "",
                 palette_obj: theme.Palette | None = None, strong: bool = False,
                 parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("cardStrong" if strong else "card")
        self._header_widgets: list[QWidget] = []
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(18, 16, 18, 16)
        self.outer.setSpacing(12)
        self.header: QHBoxLayout | None = None
        self.icon_label: QLabel | None = None
        self.title_label: QLabel | None = None
        self.subtitle_label: QLabel | None = None
        if title:
            self._build_header(title, subtitle, icon_name, palette_obj)
        self.body = QVBoxLayout()
        self.body.setSpacing(10)
        self.outer.addLayout(self.body, 1)

    def _build_header(self, title: str, subtitle: str, icon_name: str,
                      palette_obj: theme.Palette | None) -> None:
        self.header = QHBoxLayout()
        self.header.setSpacing(10)
        if icon_name and palette_obj:
            self.icon_label = QLabel()
            self.icon_label.setPixmap(svg_pixmap(icon_name, palette_obj.accent, 20))
            self.icon_label.setFixedSize(22, 22)
            self.header.addWidget(self.icon_label, 0, Qt.AlignTop)
        text_column = QVBoxLayout()
        text_column.setSpacing(1)
        self.title_label = QLabel(title)
        self.title_label.setObjectName("h2")
        text_column.addWidget(self.title_label)
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setObjectName("tiny")
            self.subtitle_label.setWordWrap(True)
            text_column.addWidget(self.subtitle_label)
        self.header.addLayout(text_column, 1)
        self.outer.addLayout(self.header)

    def add_header_widget(self, widget: QWidget) -> None:
        if self.header is not None:
            self.header.addWidget(widget, 0, Qt.AlignVCenter)

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.body.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.body.addLayout(layout, stretch)

    def add_stretch(self, stretch: int = 1) -> None:
        self.body.addStretch(stretch)

    def addStretch(self, stretch: int = 1) -> None:  # noqa: N802 - Qt-style alias
        self.add_stretch(stretch)


class Badge(QLabel):
    KINDS = {"ok": "ok", "warn": "warn", "err": "err", "info": "info",
             "accent": "accent", "muted": "muted"}

    def __init__(self, text: str = "", kind: str = "muted", parent=None) -> None:
        super().__init__(text, parent)
        self.setObjectName("badge")
        self.setProperty("kind", kind)
        self.setAlignment(Qt.AlignCenter)
        self.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)

    def update_badge(self, text: str, kind: str) -> None:
        self.setText(text)
        set_prop(self, "kind", self.KINDS.get(kind, "muted"))


class StatTile(GlassCard):
    def __init__(self, caption: str, icon_name: str, palette_obj: theme.Palette,
                 value: str = "—", parent=None) -> None:
        super().__init__(palette_obj=palette_obj, parent=parent)
        row = QHBoxLayout()
        row.setSpacing(14)
        self.orb = IconOrb(icon_name, palette_obj, 44)
        row.addWidget(self.orb, 0, Qt.AlignTop)
        column = QVBoxLayout()
        column.setSpacing(2)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("value")
        self.caption_label = QLabel(caption)
        self.caption_label.setObjectName("tiny")
        self.detail_label = QLabel("")
        self.detail_label.setObjectName("tiny")
        column.addWidget(self.caption_label)
        column.addWidget(self.value_label)
        column.addWidget(self.detail_label)
        row.addLayout(column, 1)
        self.body.addLayout(row)

    def set_value(self, value: str, detail: str = "") -> None:
        self.value_label.setText(value)
        self.detail_label.setText(detail)


class IconOrb(QWidget):
    def __init__(self, icon_name: str, palette_obj: theme.Palette, size: int = 42,
                 color: str | None = None, parent=None) -> None:
        super().__init__(parent)
        self.icon_name = icon_name
        self._palette = palette_obj
        self._color = color
        self.setFixedSize(size, size)

    def set_icon(self, name: str) -> None:
        self.icon_name = name
        self.update()

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self._palette = palette_obj
        self.update()

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        p = self._palette
        rect = QRectF(0, 0, self.width(), self.height())
        colour = self._color or p.accent
        gradient = QRadialGradient(rect.center(), rect.width() * 0.7)
        gradient.setColorAt(0.0, theme.qcolor(colour, 0.35))
        gradient.setColorAt(1.0, theme.qcolor(colour, 0.08))
        painter.setBrush(gradient)
        painter.setPen(QPen(theme.qcolor(colour, 0.35), 1))
        painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), rect.width() * 0.32, rect.width() * 0.32)
        pixmap = svg_pixmap(self.icon_name, colour, int(self.width() * 0.48))
        painter.drawPixmap(
            QRectF((self.width() - self.width() * 0.48) / 2, (self.height() - self.width() * 0.48) / 2,
                   self.width() * 0.48, self.width() * 0.48),
            pixmap, QRectF(pixmap.rect()),
        )
        painter.end()


# ----------------------------------------------------------------------- chart
class TrafficChart(QWidget):
    """Smooth two-series area chart, fed at most once per second."""

    def __init__(self, palette_obj: theme.Palette, points: int = 90, parent=None) -> None:
        super().__init__(parent)
        self._palette = palette_obj
        self._points = points
        self._down: deque[float] = deque(maxlen=points)
        self._up: deque[float] = deque(maxlen=points)
        self.setMinimumHeight(170)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self._palette = palette_obj
        self.update()

    def push(self, down_bps: float, up_bps: float) -> None:
        self._down.append(max(0.0, down_bps) * 8 / 1_000_000)
        self._up.append(max(0.0, up_bps) * 8 / 1_000_000)
        self.update()

    def set_series(self, down: list[float], up: list[float]) -> None:
        self._down = deque(down[-self._points:], maxlen=self._points)
        self._up = deque(up[-self._points:], maxlen=self._points)
        self.update()

    def clear(self) -> None:
        self._down.clear()
        self._up.clear()
        self.update()

    def series(self) -> tuple[list[float], list[float]]:
        return list(self._down), list(self._up)

    def _path(self, values: list[float], maximum: float, rect: QRectF) -> QPainterPath:
        path = QPainterPath()
        if not values:
            return path
        count = len(values)
        step = rect.width() / max(1, self._points - 1)
        offset = rect.width() - (count - 1) * step
        points = [
            QPointF(rect.left() + offset + index * step,
                    rect.bottom() - (value / maximum) * rect.height())
            for index, value in enumerate(values)
        ]
        path.moveTo(points[0])
        for index in range(1, len(points)):
            previous, current = points[index - 1], points[index]
            middle = (previous.x() + current.x()) / 2
            path.cubicTo(QPointF(middle, previous.y()), QPointF(middle, current.y()), current)
        return path

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        p = self._palette
        rect = QRectF(6, 8, self.width() - 12, self.height() - 30)
        if rect.width() <= 0 or rect.height() <= 0:
            return

        grid_pen = QPen(theme.qcolor(p.surface if p.is_dark else "#0F172A", 0.075), 1, Qt.SolidLine)
        painter.setPen(grid_pen)
        for index in range(1, 4):
            y = rect.top() + rect.height() * index / 4
            painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

        values = list(self._down) + list(self._up)
        if not values:
            painter.setPen(QColor(p.muted))
            painter.drawText(self.rect(), Qt.AlignCenter, "Ожидание данных…")
            painter.end()
            return

        maximum = max(0.5, max(values) * 1.2)
        painter.setPen(QColor(p.muted))
        font = QFont(self.font())
        font.setPointSize(max(7, p.font_size - 2))
        painter.setFont(font)
        painter.drawText(QRectF(rect.left(), rect.top() - 2, 90, 16), Qt.AlignLeft,
                         f"{maximum:.1f} Мбит/с")

        for series, colour in ((list(self._down), p.accent), (list(self._up), p.accent2)):
            if not series:
                continue
            path = self._path(series, maximum, rect)
            fill = QPainterPath(path)
            fill.lineTo(rect.right(), rect.bottom())
            fill.lineTo(rect.left(), rect.bottom())
            fill.closeSubpath()
            gradient = QLinearGradient(0, rect.top(), 0, rect.bottom())
            gradient.setColorAt(0.0, theme.qcolor(colour, 0.30))
            gradient.setColorAt(1.0, theme.qcolor(colour, 0.0))
            painter.setPen(Qt.NoPen)
            painter.setBrush(gradient)
            painter.drawPath(fill)
            painter.setBrush(Qt.NoBrush)
            painter.setPen(QPen(theme.qcolor(colour, 0.12), 8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
            painter.setPen(QPen(QColor(colour), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            painter.drawPath(path)
        painter.end()


# ------------------------------------------------------------------- log view
class LogView(QPlainTextEdit):
    def __init__(self, palette_obj: theme.Palette, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("logView")
        self.setReadOnly(True)
        self.setMaximumBlockCount(1800)
        self.setLineWrapMode(QPlainTextEdit.NoWrap)
        self._buffer: list[str] = []
        self._flush_timer = QTimer(self)
        self._flush_timer.setInterval(120)
        self._flush_timer.timeout.connect(self.flush)
        self._flush_timer.start()
        self._palette = palette_obj

    def append_line(self, text: str) -> None:
        self._buffer.append(f"[{time.strftime('%H:%M:%S')}] {text}")
        if len(self._buffer) > 400:
            self.flush()

    def append_plain(self, text: str) -> None:
        self._buffer.append(text)

    def flush(self) -> None:
        if not self._buffer:
            return
        bar = self.verticalScrollBar()
        at_bottom = bar.value() >= bar.maximum() - 4
        self.appendPlainText("\n".join(self._buffer))
        self._buffer.clear()
        if at_bottom:
            bar.setValue(bar.maximum())

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self._palette = palette_obj
        repolish(self)


# ---------------------------------------------------------------------- toast
class Toast(QFrame):
    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("toast")
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._label = QLabel("")
        self._label.setWordWrap(True)
        self._dot = QLabel("●")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 10, 16, 10)
        layout.setSpacing(9)
        layout.addWidget(self._dot, 0, Qt.AlignTop)
        layout.addWidget(self._label, 1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide_animated)
        self._effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(self._effect)
        self._effect.setOpacity(0.0)
        self._anim = QPropertyAnimation(self._effect, b"opacity", self)
        self._anim.setDuration(220)
        self._palette = theme.Palette()
        self.hide()

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self._palette = palette_obj
        repolish(self)

    def show_message(self, text: str, kind: str = "info", duration: int = 3200) -> None:
        colours = {"ok": self._palette.success, "err": self._palette.danger,
                   "warn": self._palette.warning, "info": self._palette.accent2}
        self._dot.setStyleSheet(f"color: {colours.get(kind, self._palette.accent)};")
        self._label.setText(text)
        self.adjustSize()
        parent = self.parentWidget()
        if parent and parent.height() > 0:
            self.setFixedWidth(min(420, parent.width() - 60))
            self.adjustSize()
            self.move(parent.width() - self.width() - 26,
                      parent.height() - self.height() - 24)
            self.raise_()
        self.show()
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(1.0)
        self._anim.start()
        self._timer.start(duration)

    def hide_animated(self) -> None:
        self._anim.stop()
        self._anim.setStartValue(self._effect.opacity())
        self._anim.setEndValue(0.0)
        self._anim.finished.connect(self._on_hide_finished)
        self._anim.start()

    def _on_hide_finished(self) -> None:
        try:
            self._anim.finished.disconnect(self._on_hide_finished)
        except (RuntimeError, TypeError):
            pass
        self.hide()


# -------------------------------------------------------------------- overlay
class Overlay(QWidget):
    """In-window modal panel — no extra OS windows are created."""

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("overlayBackdrop")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.hide()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(40, 30, 40, 30)
        layout.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        self.card = QFrame()
        self.card.setObjectName("overlayCard")
        self.card.setMaximumWidth(820)
        card_layout = QVBoxLayout(self.card)
        card_layout.setContentsMargins(24, 20, 24, 20)
        card_layout.setSpacing(14)
        header = QHBoxLayout()
        self.title_label = QLabel("")
        self.title_label.setObjectName("title")
        header.addWidget(self.title_label, 1)
        self.close_button = QPushButton("✕")
        self.close_button.setProperty("variant", "ghost")
        self.close_button.setFixedSize(30, 30)
        self.close_button.setCursor(Qt.PointingHandCursor)
        self.close_button.clicked.connect(self.close_panel)
        header.addWidget(self.close_button, 0, Qt.AlignTop)
        card_layout.addLayout(header)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(12)
        card_layout.addWidget(self.content, 1)
        self.actions = QHBoxLayout()
        self.actions.setSpacing(8)
        self.actions.addStretch(1)
        card_layout.addLayout(self.actions)
        row.addWidget(self.card, 0)
        row.addStretch(1)
        layout.addLayout(row, 0)
        layout.addStretch(1)
        self._on_close = None
        self.setFocusPolicy(Qt.StrongFocus)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        parent.installEventFilter(self)
        self.hide()

    def eventFilter(self, watched, event) -> bool:
        if watched is self.parentWidget() and event.type() == QEvent.Resize and self.isVisible():
            self.resize(watched.size())
        return super().eventFilter(watched, event)

    def showEvent(self, event) -> None:
        if self.parentWidget():
            self.resize(self.parentWidget().size())
        super().showEvent(event)

    def open_panel(self, title: str, content: QWidget, actions: list[tuple] | None = None,
                   closable: bool = True) -> None:
        self.title_label.setText(title)
        while self.content_layout.count():
            item = self.content_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
        if content is not None:
            self.content_layout.addWidget(content)
        while self.actions.count() > 1:
            item = self.actions.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()
        self.close_button.setVisible(closable)
        for text, variant, callback in actions or []:
            button = QPushButton(text)
            button.setProperty("variant", variant)
            button.setCursor(Qt.PointingHandCursor)
            button.setFixedHeight(36)
            if callback:
                button.clicked.connect(callback)
            self.actions.insertWidget(self.actions.count() - 1, button)
        self.show()
        self.raise_()
        self.setFocus()
        self.resize(self.parentWidget().size())

    def close_panel(self) -> None:
        if self._on_close:
            callback, self._on_close = self._on_close, None
            callback()
        self.hide()

    def set_close_callback(self, callback) -> None:
        self._on_close = callback

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.close_panel()
            return
        super().keyPressEvent(event)


# ----------------------------------------------------------------- background
class BackgroundWidget(QWidget):
    """Gradient (or user video) backdrop with vignette and dim control."""

    def __init__(self, palette_obj: theme.Palette, parent=None) -> None:
        super().__init__(parent)
        self._palette = palette_obj
        self._dim = 0.55
        self._video_enabled = False
        self._video_path = ""
        self._player = None
        self._sink = None
        self._audio = None
        self._frame_image: QImage | None = None
        self._scaled: QImage | None = None
        self._last_frame_at = 0.0
        self._video_error = ""
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)

    def set_palette(self, palette_obj: theme.Palette) -> None:
        self._palette = palette_obj
        self.update()

    def apply_video(self, enabled: bool, path: str, dim: float, muted: bool = True) -> None:
        self._dim = max(0.0, min(0.92, dim))
        self._video_enabled = bool(enabled and path and Path(path).exists())
        if not self._video_enabled:
            self.stop_video()
            self.update()
            return
        if path != self._video_path:
            self._video_path = path
            self._setup_player()
        if self._player:
            from PySide6.QtCore import QUrl

            self._player.setSource(QUrl.fromLocalFile(path))
            self._player.play()
            if self._audio:
                self._audio.setMuted(muted)
        self.update()

    def _setup_player(self) -> None:
        if self._player is not None:
            return
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink
        except Exception as exc:  # pragma: no cover - missing multimedia
            self._video_error = str(exc)
            self._video_enabled = False
            return
        self._player = QMediaPlayer(self)
        self._sink = QVideoSink(self)
        self._player.setVideoSink(self._sink)
        self._audio = QAudioOutput(self)
        self._audio.setMuted(True)
        self._audio.setVolume(0.0)
        self._player.setAudioOutput(self._audio)
        self._sink.videoFrameChanged.connect(self._on_frame)
        self._player.mediaStatusChanged.connect(self._on_media_status)

    def _on_media_status(self, status) -> None:
        try:
            from PySide6.QtMultimedia import QMediaPlayer

            if status == QMediaPlayer.EndOfMedia:
                self._player.setPosition(0)
                self._player.play()
        except Exception:
            pass

    def _on_frame(self, frame) -> None:
        if not self._video_enabled:
            return
        now = time.monotonic()
        if now - self._last_frame_at < 1 / 30:
            return
        self._last_frame_at = now
        try:
            image = frame.toImage()
        except Exception:
            return
        if image.isNull():
            return
        if image.width() > 1920:
            image = image.scaledToWidth(1920, Qt.SmoothTransformation)
        self._frame_image = image
        self._scaled = None
        self.update()

    def pause(self) -> None:
        if self._player:
            self._player.pause()

    def resume(self) -> None:
        if self._player and self._video_enabled:
            self._player.play()

    def stop_video(self) -> None:
        if self._player:
            self._player.stop()
            self._player.setSource(QUrl())
        self._frame_image = None
        self._scaled = None

    def paintEvent(self, event) -> None:
        painter = QPainter(self)
        rect = self.rect()
        p = self._palette

        if self._frame_image is not None and self._video_enabled:
            if self._scaled is None or self._scaled.size() != rect.size():
                self._scaled = self._frame_image.scaled(
                    rect.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
                )
            source = self._scaled
            x = (source.width() - rect.width()) // 2
            y = (source.height() - rect.height()) // 2
            painter.drawImage(rect, source, source.rect().adjusted(x, y, -x, -y))
        else:
            base = QLinearGradient(0, 0, rect.width(), rect.height())
            base.setColorAt(0.0, QColor(p.bg))
            base.setColorAt(0.55, QColor(theme.mix(p.bg, p.bg2, 0.45)))
            base.setColorAt(1.0, QColor(p.bg2))
            painter.fillRect(rect, base)
            if p.is_dark:
                glow = QRadialGradient(QPointF(rect.width() * 0.78, rect.height() * 0.12), rect.width() * 0.55)
                glow.setColorAt(0.0, theme.qcolor(p.accent, 0.22))
                glow.setColorAt(1.0, theme.qcolor(p.accent, 0.0))
                painter.fillRect(rect, glow)
                glow2 = QRadialGradient(QPointF(rect.width() * 0.15, rect.height() * 0.85), rect.width() * 0.5)
                glow2.setColorAt(0.0, theme.qcolor(p.accent2, 0.13))
                glow2.setColorAt(1.0, theme.qcolor(p.accent2, 0.0))
                painter.fillRect(rect, glow2)

        # Dim and vignette exist to tame a busy video frame. Without one they
        # would wash out the carefully tuned gradient (and the light theme).
        if self._frame_image is not None and self._video_enabled:
            painter.fillRect(rect, QColor(3, 5, 10, int(255 * self._dim)))
            vignette = QRadialGradient(QPointF(rect.width() / 2, rect.height() / 2),
                                      rect.width() * 0.75)
            vignette.setColorAt(0.55, QColor(0, 0, 0, 0))
            vignette.setColorAt(1.0, QColor(0, 0, 0, 110))
            painter.fillRect(rect, vignette)
        painter.end()


# --------------------------------------------------------------------- rows
class ToggleRow(QWidget):
    toggled = Signal(bool)

    def __init__(self, title: str, subtitle: str = "", checked: bool = False,
                 palette_obj: theme.Palette | None = None, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(12)
        column = QVBoxLayout()
        column.setSpacing(1)
        self.title_label = QLabel(title)
        self.title_label.setWordWrap(True)
        column.addWidget(self.title_label)
        if subtitle:
            self.subtitle_label = QLabel(subtitle)
            self.subtitle_label.setObjectName("tiny")
            self.subtitle_label.setWordWrap(True)
            column.addWidget(self.subtitle_label)
        layout.addLayout(column, 1)
        self.switch = ToggleSwitch(checked)
        if palette_obj:
            self.switch.set_colors(palette_obj.accent, palette_obj.muted)
        self.switch.toggled.connect(self.toggled.emit)
        layout.addWidget(self.switch, 0, Qt.AlignVCenter)

    def is_checked(self) -> bool:
        return self.switch.isChecked()

    def set_checked(self, value: bool) -> None:
        self.switch.blockSignals(True)
        self.switch.setChecked(bool(value))
        self.switch.blockSignals(False)

    def set_colors(self, palette_obj: theme.Palette) -> None:
        self.switch.set_colors(palette_obj.accent, palette_obj.muted)


class SliderRow(QWidget):
    value_changed = Signal(float)

    def __init__(self, title: str, minimum: float, maximum: float, value: float,
                 suffix: str = "", palette_obj: theme.Palette | None = None, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(14)
        self.title_label = QLabel(title)
        self.title_label.setMinimumWidth(150)
        layout.addWidget(self.title_label, 0)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(int(minimum * 100), int(maximum * 100))
        self.slider.setValue(int(value * 100))
        # Sliders use integer steps; expose the original scale.
        self._scale = 100.0
        self.slider.valueChanged.connect(lambda raw: self._on_change(raw / self._scale))
        layout.addWidget(self.slider, 1)
        self.value_label = QLabel(f"{value:g}{suffix}")
        self.value_label.setObjectName("tiny")
        self.value_label.setMinimumWidth(64)
        self.value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.value_label, 0)
        self._suffix = suffix
        self._value = value

    def _on_change(self, value: float) -> None:
        self._value = value
        self.value_label.setText(f"{value:g}{self._suffix}")
        self.value_changed.emit(value)

    def set_value(self, value: float) -> None:
        self.slider.blockSignals(True)
        self.slider.setValue(int(value * self._scale))
        self.slider.blockSignals(False)
        self._value = value
        self.value_label.setText(f"{value:g}{self._suffix}")

    def value(self) -> float:
        return self._value


class ColorRow(QWidget):
    changed = Signal(str)

    def __init__(self, title: str, color: str, palette_obj: theme.Palette,
                 presets: list[str] | None = None, parent=None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(10)
        self.title_label = QLabel(title)
        self.title_label.setMinimumWidth(150)
        layout.addWidget(self.title_label, 0)
        self.swatches: list[QPushButton] = []
        for value in presets or theme.ACCENT_PRESETS:
            button = QPushButton()
            button.setFixedSize(22, 22)
            button.setCursor(Qt.PointingHandCursor)
            button.setStyleSheet(
                f"background:{value}; border:2px solid rgba(255,255,255,0.18); border-radius:11px;"
            )
            button.clicked.connect(lambda _=False, v=value: self._pick(v))
            self.swatches.append(button)
            layout.addWidget(button, 0)
        layout.addStretch(1)
        self.entry = QPushButton(color.upper())
        self.entry.setFixedSize(96, 30)
        self.entry.setProperty("variant", "chip")
        self.entry.clicked.connect(self._cycle)
        layout.addWidget(self.entry, 0)
        self._color = color
        self._options = list(presets or theme.ACCENT_PRESETS)
        self._index = 0

    def _cycle(self) -> None:
        self._index = (self._index + 1) % len(self._options)
        self._pick(self._options[self._index])

    def _pick(self, value: str) -> None:
        self._color = value
        self.entry.setText(value.upper())
        self.changed.emit(value)

    def set_color(self, value: str) -> None:
        self._color = value
        self.entry.setText(value.upper())

    def color(self) -> str:
        return self._color


class Divider(QFrame):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("separator")
        self.setFixedHeight(1)


class Page(QScrollArea):
    """Base page with a scrollable column of cards."""

    def __init__(self, context, parent=None) -> None:
        super().__init__(parent)
        self.ctx = context
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.NoFrame)
        container = QWidget()
        container.setAttribute(Qt.WA_TranslucentBackground)
        self.column = QVBoxLayout(container)
        self.column.setContentsMargins(28, 18, 28, 30)
        self.column.setSpacing(16)
        self.setWidget(container)

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        self.column.addWidget(widget, stretch)

    def add_layout(self, layout, stretch: int = 0) -> None:
        self.column.addLayout(layout, stretch)

    def finish(self) -> None:
        self.column.addStretch(1)

    def on_show(self) -> None:
        pass

    def on_hide(self) -> None:
        pass


def make_heading(title: str, subtitle: str = "") -> QWidget:
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(2, 2, 2, 2)
    layout.setSpacing(2)
    label = QLabel(title)
    label.setObjectName("h1")
    layout.addWidget(label)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        layout.addWidget(sub)
    return widget
