"""Country detection and flag rendering for the VPN UI."""

from __future__ import annotations

import pytest

from src.ui import flags


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("🇩🇪 Frankfurt-1 · VLESS", "de"),
        ("🇷🇺 Москва", "ru"),
        ("Нидерланды #2", "nl"),
        ("Netherlands WS-443", "nl"),
        ("US West Reality", "us"),
        ("UK-1", "gb"),
        ("Германия", "de"),
        ("США скорость", "us"),
        ("Japan Tokyo 01", "jp"),
        ("Казахстан-2", "kz"),
        ("XHTTP node is fast", ""),
        ("reserve node no country", ""),
    ],
)
def test_detect_country(text: str, expected: str) -> None:
    assert flags.detect_country(text) == expected


def test_detect_country_lowercase_words_not_codes() -> None:
    assert flags.detect_country("node no 1") == ""
    assert flags.detect_country("NODE NO 1") == "no"


def test_strip_flag_emoji() -> None:
    assert flags.strip_flag_emoji("🇩🇪 DE-Frankfurt ⚡") == "DE-Frankfurt ⚡"
    assert flags.strip_flag_emoji("plain") == "plain"


def test_flag_pixmap_renders_bundled_svg(qapp) -> None:
    pixmap = flags.flag_pixmap("de", 20)
    assert pixmap is not None and not pixmap.isNull()
    assert pixmap.height() == 20
    assert flags.flag_pixmap("zz", 20) is None
    assert flags.flag_icon("us", 18) is not None
