"""Theme palette and stylesheet generation for Zentrix."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = (value or "").strip().lstrip("#")
    if len(value) == 3:
        value = "".join(char * 2 for char in value)
    if len(value) != 6:
        return (124, 92, 255)
    try:
        return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)
    except ValueError:
        return (124, 92, 255)


def rgba(value: str, alpha: float) -> str:
    red, green, blue = hex_to_rgb(value)
    return f"rgba({red}, {green}, {blue}, {_clamp(alpha):.3f})"


def qcolor(value: str, alpha: float = 1.0) -> QColor:
    """Return a QColor with the requested opacity.

    ``QColor`` does not understand CSS ``rgba(...)`` strings, so painting code
    must use this helper instead of ``QColor(rgba(...))`` (which is black).
    """
    colour = QColor(value)
    if not colour.isValid():
        colour = QColor("#7C5CFF")
    colour.setAlphaF(_clamp(alpha))
    return colour


def mix(first: str, second: str, ratio: float) -> str:
    ratio = _clamp(ratio)
    r1, g1, b1 = hex_to_rgb(first)
    r2, g2, b2 = hex_to_rgb(second)
    return "#{:02x}{:02x}{:02x}".format(
        int(r1 + (r2 - r1) * ratio),
        int(g1 + (g2 - g1) * ratio),
        int(b1 + (b2 - b1) * ratio),
    )


def luminance(value: str) -> float:
    red, green, blue = hex_to_rgb(value)
    return (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255.0


@dataclass
class Palette:
    theme: str = "dark"
    bg: str = "#080B12"
    bg2: str = "#101726"
    text: str = "#EAF0FF"
    muted: str = "#93A0B8"
    accent: str = "#7C5CFF"
    accent2: str = "#22D3EE"
    surface: str = "#FFFFFF"
    border: str = "#FFFFFF"
    card_opacity: float = 0.62
    border_opacity: float = 0.10
    radius: int = 18
    danger: str = "#FF5C7A"
    success: str = "#3DDC97"
    warning: str = "#FFC46B"
    font_family: str = "Segoe UI"
    font_size: int = 10

    @property
    def is_dark(self) -> bool:
        return luminance(self.bg) < 0.45

    @property
    def card(self) -> str:
        return rgba(self.surface, self.card_opacity * (0.09 if self.is_dark else 0.85))

    @property
    def card_strong(self) -> str:
        return rgba(self.surface, self.card_opacity * (0.14 if self.is_dark else 1.0))

    @property
    def line(self) -> str:
        return rgba(self.surface if self.is_dark else "#0F172A", self.border_opacity)

    @property
    def hover(self) -> str:
        return rgba(self.surface if self.is_dark else "#0F172A", 0.07)

    @property
    def navigation(self) -> str:
        return rgba(self.bg, 0.55 if self.is_dark else 0.45)

    @classmethod
    def from_settings(cls, settings) -> "Palette":
        data = settings.section("appearance")
        theme = str(data.get("theme", "dark"))
        defaults = THEMES.get(theme, THEMES["dark"])
        return cls(
            theme=theme,
            bg=str(data.get("bg") or defaults["bg"]),
            bg2=str(data.get("bg2") or defaults["bg2"]),
            text=str(data.get("text") or defaults["text"]),
            muted=str(data.get("muted") or defaults["muted"]),
            accent=str(data.get("accent") or "#7C5CFF"),
            accent2=str(data.get("accent2") or "#22D3EE"),
            surface="#FFFFFF" if theme == "dark" else "#FFFFFF",
            border="#FFFFFF" if theme == "dark" else "#0F172A",
            card_opacity=float(data.get("card_opacity", 0.62) or 0.62),
            border_opacity=float(data.get("border_opacity", 0.10) or 0.10),
            radius=int(data.get("radius", 18) or 18),
            font_family=str(data.get("font_family", "Segoe UI") or "Segoe UI"),
            font_size=int(data.get("font_size", 10) or 10),
        )


THEMES = {
    "dark": {
        "bg": "#080B12", "bg2": "#101726", "text": "#EAF0FF", "muted": "#93A0B8",
        "accent": "#7C5CFF", "accent2": "#22D3EE",
    },
    "light": {
        "bg": "#EDF1F9", "bg2": "#FFFFFF", "text": "#0F172A", "muted": "#5B6B85",
        "accent": "#6D4AFF", "accent2": "#0EA5C6",
    },
}

ACCENT_PRESETS = [
    "#7C5CFF", "#22D3EE", "#3DDC97", "#FFC46B",
    "#FF5C7A", "#FF8A4C", "#4C9AFF", "#C084FC",
]


def load_custom_font(path: str | Path) -> str:
    """Register a user font and return its family (or an empty string)."""
    path = Path(path)
    if not path.exists():
        return ""
    font_id = QFontDatabase.addApplicationFont(str(path))
    if font_id < 0:
        return ""
    families = QFontDatabase.applicationFontFamilies(font_id)
    return families[0] if families else ""


def qss(palette: Palette) -> str:
    dark = palette.is_dark
    text = palette.text
    muted = palette.muted
    accent = palette.accent
    accent2 = palette.accent2
    card = palette.card
    strong = palette.card_strong
    line = palette.line
    radius = palette.radius
    input_bg = rgba("#FFFFFF" if dark else "#FFFFFF", 0.05 if dark else 0.9)
    scroll = rgba(palette.surface if dark else "#0F172A", 0.18)
    scroll_hover = rgba(accent, 0.55)
    menu_bg = mix(palette.bg, palette.bg2, 0.55)

    return f"""
    * {{
        font-family: "{palette.font_family}";
        font-size: {palette.font_size}pt;
        outline: none;
    }}
    QWidget {{
        color: {text};
        background: transparent;
    }}
    QMainWindow, #root {{
        background: {rgba(palette.bg, 0.0)};
    }}
    QToolTip {{
        background: {menu_bg};
        color: {text};
        border: 1px solid {line};
        padding: 6px 9px;
        border-radius: 8px;
    }}
    #card {{
        background: {card};
        border: 1px solid {line};
        border-radius: {radius}px;
    }}
    #cardStrong {{
        background: {strong};
        border: 1px solid {line};
        border-radius: {radius}px;
    }}
    #hero {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {rgba(accent, 0.24 if dark else 0.16)},
            stop:0.55 {rgba(accent2, 0.10 if dark else 0.10)},
            stop:1 {rgba(palette.bg2, 0.55 if dark else 0.9)});
        border: 1px solid {rgba(accent, 0.28)};
        border-radius: {radius + 6}px;
    }}
    #title {{ font-size: {palette.font_size + 7}pt; font-weight: 700; }}
    #h1 {{ font-size: {palette.font_size + 13}pt; font-weight: 700; }}
    #h2 {{ font-size: {palette.font_size + 4}pt; font-weight: 600; }}
    #muted {{ color: {muted}; }}
    #tiny {{ color: {muted}; font-size: {max(8, palette.font_size - 1)}pt; }}
    #value {{ font-size: {palette.font_size + 11}pt; font-weight: 700; }}
    #mono {{ font-family: "Cascadia Mono", "Consolas", monospace;
             font-size: {max(8, palette.font_size - 1)}pt; }}

    QLabel#badge {{
        padding: 3px 10px;
        border-radius: 10px;
        font-size: {max(8, palette.font_size - 1)}pt;
        font-weight: 600;
    }}
    QLabel#badge[kind="ok"] {{ color: {palette.success}; background: {rgba(palette.success, 0.14)}; }}
    QLabel#badge[kind="warn"] {{ color: {palette.warning}; background: {rgba(palette.warning, 0.14)}; }}
    QLabel#badge[kind="err"] {{ color: {palette.danger}; background: {rgba(palette.danger, 0.14)}; }}
    QLabel#badge[kind="info"] {{ color: {accent2}; background: {rgba(accent2, 0.12)}; }}
    QLabel#badge[kind="accent"] {{ color: {accent}; background: {rgba(accent, 0.16)}; }}
    QLabel#badge[kind="muted"] {{ color: {muted}; background: {rgba(muted, 0.10)}; }}

    QPushButton {{
        background: {rgba(palette.surface, 0.06 if dark else 0.7)};
        border: 1px solid {line};
        border-radius: {max(8, radius - 6)}px;
        padding: 8px 16px;
        color: {text};
        font-weight: 600;
    }}
    QPushButton:hover {{ background: {rgba(palette.surface, 0.11 if dark else 0.95)}; }}
    QPushButton:pressed {{ background: {rgba(accent, 0.18)}; }}
    QPushButton:disabled {{ color: {rgba(muted, 0.6)}; background: {rgba(palette.surface, 0.03)}; }}

    QPushButton[variant="primary"] {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {accent}, stop:1 {mix(accent, accent2, 0.55)});
        border: none; color: white; padding: 9px 18px;
    }}
    QPushButton[variant="primary"]:hover {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {mix(accent, "#FFFFFF", 0.10)}, stop:1 {mix(accent2, accent, 0.35)});
    }}
    QPushButton[variant="danger"] {{
        background: {rgba(palette.danger, 0.16)}; border: 1px solid {rgba(palette.danger, 0.35)};
        color: {palette.danger};
    }}
    QPushButton[variant="danger"]:hover {{ background: {rgba(palette.danger, 0.24)}; }}
    QPushButton[variant="ghost"] {{
        background: transparent; border: 1px solid transparent; color: {muted}; padding: 6px 10px;
    }}
    QPushButton[variant="ghost"]:hover {{ color: {text}; background: {palette.hover}; }}
    QPushButton[variant="chip"] {{
        background: {rgba(palette.surface, 0.05)}; border: 1px solid {line};
        border-radius: {radius - 4}px; padding: 6px 12px; font-weight: 500;
    }}
    QPushButton[variant="chip"]:checked {{
        background: {rgba(accent, 0.20)}; border-color: {rgba(accent, 0.55)}; color: {text};
    }}
    QToolButton {{
        background: transparent; border: none; border-radius: 9px; padding: 6px;
    }}
    QToolButton:hover {{ background: {palette.hover}; }}
    QToolButton:pressed {{ background: {rgba(accent, 0.20)}; }}
    QToolButton#windowButton {{ border-radius: 0px; padding: 0px; }}
    QToolButton#windowButton:hover {{ background: {rgba(palette.surface, 0.10)}; }}
    QToolButton#windowButton[role="close"]:hover {{ background: #E81123; }}

    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {input_bg};
        border: 1px solid {line};
        border-radius: {max(8, radius - 8)}px;
        padding: 7px 10px;
        color: {text};
        selection-background-color: {rgba(accent, 0.45)};
        selection-color: white;
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
    QDoubleSpinBox:focus, QComboBox:focus {{ border-color: {rgba(accent, 0.65)}; }}
    QLineEdit:disabled, QTextEdit:disabled {{ color: {rgba(muted, 0.7)}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{
        background: {menu_bg}; border: 1px solid {line}; border-radius: 10px;
        selection-background-color: {rgba(accent, 0.30)}; padding: 4px;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}

    QCheckBox {{ spacing: 8px; color: {text}; }}
    QCheckBox::indicator {{
        width: 18px; height: 18px; border-radius: 5px;
        border: 1px solid {rgba(palette.surface if dark else "#0F172A", 0.22)};
        background: {rgba(palette.surface, 0.04 if dark else 0.7)};
    }}
    QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
    QCheckBox::indicator:hover {{ border-color: {rgba(accent, 0.7)}; }}

    QSlider::groove:horizontal {{
        height: 6px; border-radius: 3px;
        background: {rgba(palette.surface if dark else "#0F172A", 0.14)};
    }}
    QSlider::sub-page:horizontal {{
        height: 6px; border-radius: 3px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 {accent2});
    }}
    QSlider::handle:horizontal {{
        width: 16px; height: 16px; margin: -6px 0; border-radius: 8px;
        background: {text}; border: 2px solid {accent};
    }}
    QSlider::handle:horizontal:hover {{ background: white; }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {scroll}; min-height: 28px; border-radius: 4px; }}
    QScrollBar::handle:vertical:hover {{ background: {scroll_hover}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0px; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{ background: transparent; height: 9px; }}
    QScrollBar::handle:horizontal {{ background: {scroll}; min-width: 28px; border-radius: 4px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0px; }}

    QTabWidget::pane {{ border: none; background: transparent; }}
    QTabBar::tab {{
        background: transparent; color: {muted}; padding: 8px 16px; margin-right: 4px;
        border-radius: {max(7, radius - 9)}px; font-weight: 600;
    }}
    QTabBar::tab:hover {{ color: {text}; background: {palette.hover}; }}
    QTabBar::tab:selected {{
        color: {text}; background: {rgba(accent, 0.18)};
        border: 1px solid {rgba(accent, 0.30)};
    }}

    QTableWidget, QTableView {{
        background: transparent; border: none; gridline-color: transparent;
        selection-background-color: {rgba(accent, 0.18)}; selection-color: {text};
        alternate-background-color: transparent;
    }}
    QHeaderView::section {{
        background: transparent; color: {muted}; border: none;
        border-bottom: 1px solid {line}; padding: 8px 10px;
        font-weight: 600; font-size: {max(8, palette.font_size - 1)}pt;
    }}
    QTableWidget::item {{ padding: 7px 10px; border-bottom: 1px solid {rgba(palette.surface if dark else "#0F172A", 0.04)}; }}

    QProgressBar {{
        background: {rgba(palette.surface if dark else "#0F172A", 0.10)};
        border: none; border-radius: 5px; height: 8px; text-align: center; color: transparent;
    }}
    QProgressBar::chunk {{
        border-radius: 5px;
        background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {accent}, stop:1 {accent2});
    }}

    QMenu {{
        background: {menu_bg}; border: 1px solid {line}; border-radius: 12px; padding: 6px;
    }}
    QMenu::item {{ padding: 8px 26px 8px 14px; border-radius: 8px; color: {text}; }}
    QMenu::item:selected {{ background: {rgba(accent, 0.22)}; }}
    QMenu::separator {{ height: 1px; background: {line}; margin: 5px 8px; }}

    QListWidget {{ background: transparent; border: none; }}
    QListWidget::item {{ padding: 8px 10px; border-radius: 9px; color: {text}; }}
    QListWidget::item:selected {{ background: {rgba(accent, 0.20)}; }}
    QListWidget::item:hover {{ background: {palette.hover}; }}

    QSplitter::handle {{ background: transparent; width: 8px; }}

    #separator {{ background: {line}; max-height: 1px; min-height: 1px; border: none; }}
    #navArea {{ background: {palette.navigation}; border-right: 1px solid {line}; }}
    #titleBar {{ background: {rgba(palette.bg, 0.35 if dark else 0.5)}; border-bottom: 1px solid {line}; }}
    #brandName {{ color: {text}; font-weight: 700; letter-spacing: 2px; }}
    #statusPill {{
        background: {rgba(palette.surface if dark else "#0F172A", 0.05 if dark else 0.04)};
        border: 1px solid {line}; border-radius: 12px; min-height: 24px; max-height: 24px;
    }}
    #pageStack {{ background: transparent; }}
    #sidebarFooter {{ border-top: 1px solid {line}; }}
    #logView {{
        background: {rgba("#000000" if dark else "#FFFFFF", 0.28 if dark else 0.55)};
        border: 1px solid {line}; border-radius: {max(8, radius - 8)}px;
        font-family: "Cascadia Mono", "Consolas", monospace;
        font-size: {max(8, palette.font_size - 1)}pt; color: {muted};
        padding: 8px;
    }}
    #overlayBackdrop {{ background: rgba(4, 6, 12, 0.55); }}
    #overlayCard {{
        background: {mix(palette.bg, palette.bg2, 0.35)};
        border: 1px solid {rgba(accent, 0.25)};
        border-radius: {radius + 4}px;
    }}
    #toast {{
        background: {mix(palette.bg, palette.bg2, 0.5)};
        border: 1px solid {rgba(accent, 0.35)};
        border-radius: {max(10, radius - 4)}px;
    }}
    """
