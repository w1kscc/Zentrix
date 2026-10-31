"""Country flags for server lists and IP cards.

Windows does not paint emoji flag sequences (regional-indicator pairs fall
back to plain letters like "DE"), so flags are rendered from bundled SVG
assets instead. Country detection works off the server remark text that
subscription providers generate.
"""

from __future__ import annotations

import re

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtSvg import QSvgRenderer

from .. import paths

FLAGS_DIR = paths.ASSETS_DIR / "flags"

# Regional-indicator emoji pairs ("🇩🇪"), plus stray single indicators.
FLAG_EMOJI_RE = re.compile("[\U0001F1E6-\U0001F1FF]{2}")
ANY_EMOJI_FLAG_RE = re.compile("[\U0001F1E6-\U0001F1FF]")

# Full country names (RU/EN) -> ISO code. Matched on word boundaries, longest
# first so "romania" wins over "oman".
COUNTRY_NAMES: dict[str, str] = {
    "россия": "ru", "russia": "ru",
    "украина": "ua", "ukraine": "ua",
    "беларусь": "by", "белоруссия": "by", "belarus": "by",
    "молдова": "md", "moldova": "md",
    "литва": "lt", "lithuania": "lt",
    "латвия": "lv", "latvia": "lv",
    "эстония": "ee", "estonia": "ee",
    "польша": "pl", "poland": "pl",
    "германия": "de", "germany": "de",
    "нидерланды": "nl", "голландия": "nl", "netherlands": "nl", "holland": "nl",
    "франция": "fr", "france": "fr",
    "великобритания": "gb", "британия": "gb", "англия": "gb", "united kingdom": "gb", "uk": "gb",
    "ирландия": "ie", "ireland": "ie",
    "испания": "es", "spain": "es",
    "португалия": "pt", "portugal": "pt",
    "италия": "it", "italy": "it",
    "австрия": "at", "austria": "at",
    "швейцария": "ch", "switzerland": "ch",
    "чехия": "cz", "czech": "cz", "czechia": "cz",
    "словакия": "sk", "slovakia": "sk",
    "словения": "si", "slovenia": "si",
    "хорватия": "hr", "croatia": "hr",
    "сербия": "rs", "serbia": "rs",
    "босния": "ba", "bosnia": "ba",
    "македония": "mk", "macedonia": "mk",
    "черногория": "me", "montenegro": "me",
    "албания": "al", "albania": "al",
    "греция": "gr", "greece": "gr",
    "болгария": "bg", "bulgaria": "bg",
    "румыния": "ro", "romania": "ro",
    "венгрия": "hu", "hungary": "hu",
    "финляндия": "fi", "finland": "fi",
    "швеция": "se", "sweden": "se",
    "норвегия": "no", "norway": "no",
    "дания": "dk", "denmark": "dk",
    "исландия": "is", "iceland": "is",
    "люксембург": "lu", "luxembourg": "lu",
    "бельгия": "be", "belgium": "be",
    "кипр": "cy", "cyprus": "cy",
    "мальта": "mt", "malta": "mt",
    "армения": "am", "armenia": "am",
    "грузия": "ge", "georgia": "ge",
    "азербайджан": "az", "azerbaijan": "az",
    "турция": "tr", "turkey": "tr", "türkiye": "tr",
    "сша": "us", "америка": "us", "united states": "us", "usa": "us", "america": "us",
    "канада": "ca", "canada": "ca",
    "мексика": "mx", "mexico": "mx",
    "бразилия": "br", "brazil": "br",
    "аргентина": "ar", "argentina": "ar",
    "чили": "cl", "chile": "cl",
    "колумбия": "co", "colombia": "co",
    "перу": "pe", "peru": "pe",
    "уругвай": "uy", "uruguay": "uy",
    "венесуэла": "ve", "venezuela": "ve",
    "эквадор": "ec", "ecuador": "ec",
    "китай": "cn", "china": "cn",
    "гонконг": "hk", "hong kong": "hk",
    "макао": "mo", "макау": "mo", "macau": "mo", "macao": "mo",
    "япония": "jp", "japan": "jp",
    "корея": "kr", "korea": "kr",
    "тайвань": "tw", "taiwan": "tw",
    "сингапур": "sg", "singapore": "sg",
    "малайзия": "my", "malaysia": "my",
    "таиланд": "th", "thailand": "th",
    "вьетнам": "vn", "vietnam": "vn",
    "филиппины": "ph", "philippines": "ph",
    "индонезия": "id", "indonesia": "id",
    "индия": "in", "india": "in",
    "пакистан": "pk", "pakistan": "pk",
    "бангладеш": "bd", "bangladesh": "bd",
    "казахстан": "kz", "kazakhstan": "kz",
    "узбекистан": "uz", "uzbekistan": "uz",
    "киргизия": "kg", "кыргызстан": "kg", "kyrgyzstan": "kg",
    "таджикистан": "tj", "tajikistan": "tj",
    "туркменистан": "tm", "turkmenistan": "tm",
    "оаэ": "ae", "объединённые арабские эмираты": "ae", "эмираты": "ae",
    "united arab emirates": "ae", "uae": "ae",
    "саудовская аравия": "sa", "saudi arabia": "sa",
    "катар": "qa", "qatar": "qa",
    "израиль": "il", "israel": "il",
    "иран": "ir", "iran": "ir",
    "египет": "eg", "egypt": "eg",
    "юар": "za", "южная африка": "za", "south africa": "za",
    "марокко": "ma", "morocco": "ma",
    "нигерия": "ng", "nigeria": "ng",
    "кения": "ke", "kenya": "ke",
    "австралия": "au", "australia": "au",
    "новая зеландия": "nz", "new zealand": "nz",
    "косово": "xk", "kosovo": "xk",
}

_NAME_RE = {
    name: re.compile(rf"(?<![A-Za-zА-Яа-яЁё]){re.escape(name)}(?![A-Za-zА-Яа-яЁё])")
    for name in COUNTRY_NAMES
}

# Lowercase two-letter words that must not be read as country codes
# (uppercase tokens like "US-1" or "DE" are still accepted).
_LOWER_WORDS = {"is", "it", "at", "be", "as", "do", "go", "or", "and", "so",
                "no", "me", "my", "on", "in", "an", "if", "of", "to", "by"}
_CODE_RE = re.compile(r"(?<![A-Za-z])([A-Za-z]{2})(?![A-Za-z])")

_AVAILABLE: set[str] | None = None
_PIXMAPS: dict[tuple[str, int], QPixmap] = {}


def _available() -> set[str]:
    global _AVAILABLE
    if _AVAILABLE is None:
        try:
            _AVAILABLE = {path.stem.lower() for path in FLAGS_DIR.glob("*.svg")}
        except Exception:
            _AVAILABLE = set()
    return _AVAILABLE


def strip_flag_emoji(text: str) -> str:
    """Drop emoji flags that Windows renders as plain letters."""
    return " ".join(ANY_EMOJI_FLAG_RE.sub(" ", text or "").split())


def _normalize(code: str) -> str:
    code = (code or "").strip().lower()
    return code if len(code) == 2 and code.isalpha() else ""


def flag_pixmap(code: str, height: int = 18) -> QPixmap | None:
    """Render a bundled flag SVG at the requested pixel height, rounded corners."""
    code = _normalize(code)
    if not code or code not in _available():
        return None
    key = (code, height)
    if key in _PIXMAPS:
        return _PIXMAPS[key]
    renderer = QSvgRenderer(str(FLAGS_DIR / f"{code}.svg"))
    if not renderer.isValid():
        return None
    default = renderer.defaultSize()
    width = max(height, round(height * default.width() / max(1, default.height())))
    dpr = QGuiApplication.primaryScreen().devicePixelRatio() if QGuiApplication.primaryScreen() else 1.0
    pixmap = QPixmap(int(width * dpr), int(height * dpr))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setRenderHint(QPainter.SmoothPixmapTransform)
    clip = QPainterPath()
    clip.addRoundedRect(QRectF(0.5, 0.5, width - 1, height - 1), 2.5, 2.5)
    painter.setClipPath(clip)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    pixmap.setDevicePixelRatio(dpr)
    _PIXMAPS[key] = pixmap
    return pixmap


def flag_icon(code: str, height: int = 18) -> QIcon | None:
    pixmap = flag_pixmap(code, height)
    return QIcon(pixmap) if pixmap is not None else None


def detect_country(text: str) -> str:
    """Best-effort ISO-3166 code from a server label ("🇩🇪 Frankfurt 1" → "de")."""
    text = text or ""
    match = FLAG_EMOJI_RE.search(text)
    if match:
        code = "".join(chr(ord(char) - 127397) for char in match.group(0))
        code = _normalize(code)
        if code and code in _available():
            return code
    lowered = text.lower()
    for name, code in sorted(COUNTRY_NAMES.items(), key=lambda item: -len(item[0])):
        if _NAME_RE[name].search(lowered):
            return code
    for token in _CODE_RE.findall(text):
        low = token.lower()
        if token.islower() and low in _LOWER_WORDS:
            continue
        if low in _available():
            return low
    return ""
