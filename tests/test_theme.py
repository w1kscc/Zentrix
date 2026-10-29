"""Palette helpers and stylesheet generation."""

from __future__ import annotations

from PySide6.QtGui import QColor

from src.settings_store import Settings
from src.ui import theme


def test_color_helpers_are_valid() -> None:
    colour = theme.qcolor("#7C5CFF", 0.25)
    assert isinstance(colour, QColor)
    assert colour.isValid()
    assert abs(colour.alphaF() - 0.25) < 0.01

    assert theme.hex_to_rgb("#abc") == (0xAA, 0xBB, 0xCC)
    assert theme.mix("#000000", "#FFFFFF", 0.5) == "#7f7f7f"
    assert theme.luminance("#000000") == 0.0
    assert abs(theme.luminance("#FFFFFF") - 1.0) < 1e-6


def test_palette_from_custom_settings(tmp_path) -> None:
    store = Settings(tmp_path / "settings.json")
    store.update("appearance", {
        "theme": "dark", "accent": "#112233", "radius": 12, "font_size": 9,
    }, save=False)

    palette = theme.Palette.from_settings(store)

    assert palette.accent == "#112233"
    assert palette.radius == 12
    assert palette.font_size == 9
    assert palette.is_dark


def test_stylesheets_use_palette_colours() -> None:
    palette = theme.Palette(theme="dark", accent="#123456", text="#ABCDEF")
    dark = theme.qss(palette)
    assert "#123456" in dark
    assert "#ABCDEF" in dark
    assert "QPushButton" in dark

    light = theme.qss(theme.Palette(theme="light", bg="#F5F5F5", bg2="#FFFFFF",
                                    text="#111111", muted="#666666"))
    assert "QLineEdit" in light
