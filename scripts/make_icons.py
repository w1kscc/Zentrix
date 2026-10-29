"""Generate SVG/PNG/ICO/ICNS assets for Zentrix (no binaries in git).

Run:  python scripts/make_icons.py
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "assets" / "icons"
BRAND = ROOT / "assets" / "brand"
for folder in (ICONS, BRAND, BRAND / "png", ROOT / "docs" / "screenshots"):
    folder.mkdir(parents=True, exist_ok=True)

W = 'stroke="currentColor" stroke-width="1.8" fill="none" stroke-linecap="round" stroke-linejoin="round"'

ICON_PATHS: dict[str, str] = {
    "home": '<path d="M3 10.7 12 3l9 7.7" /><path d="M5.5 9.3V21h13V9.3" /><path d="M9.7 21v-5.7h4.6V21" />',
    "bolt": '<path d="M13.2 2.5 4.6 13.9h6.1L9.9 21.5l8.6-11.4h-6.1l0.8-7.6Z" />',
    "globe": '<circle cx="12" cy="12" r="9" /><path d="M3.2 12h17.6" /><path d="M12 3c2.6 2.5 4 5.6 4 9s-1.4 6.5-4 9c-2.6-2.5-4-5.6-4-9s1.4-6.5 4-9Z" />',
    "shield": '<path d="M12 3.2 19 6v6c0 4.3-2.9 7.4-7 8.8C7.9 19.4 5 16.3 5 12V6l7-2.8Z" /><path d="m9 12 2.2 2.2L15.5 10" />',
    "download": '<path d="M12 3.5v11.2" /><path d="m7.4 10.6 4.6 4.6 4.6-4.6" /><path d="M4.5 20h15" />',
    "activity": '<path d="M3 12.2h3.7l2.6-7.4 4 14.4 2.6-7h5.1" />',
    "target": '<circle cx="12" cy="12" r="8.7" /><circle cx="12" cy="12" r="4.7" /><circle cx="12" cy="12" r="1" fill="currentColor" />',
    "settings": '<path d="M4 7h9" /><path d="M18 7h2" /><path d="M4 17h3" /><path d="M12 17h8" /><circle cx="15.5" cy="7" r="2.4" /><circle cx="9.5" cy="17" r="2.4" />',
    "play": '<path d="M8 5.2 19 12 8 18.8V5.2Z" fill="currentColor" stroke="none" />',
    "stop": '<rect x="6.5" y="6.5" width="11" height="11" rx="2.4" fill="currentColor" stroke="none" />',
    "refresh": '<path d="M20 12a8 8 0 1 1-2.5-5.8" /><path d="M20 4.5V10h-5.5" />',
    "trash": '<path d="M4 7h16" /><path d="M9.5 7V4.8h5V7" /><path d="M6.4 7l.8 13.2h9.6L17.6 7" /><path d="M10.2 10.7v6.4M13.8 10.7v6.4" />',
    "folder": '<path d="M3.5 7.2A2 2 0 0 1 5.5 5.2h3.4l2 2.2h7.6a2 2 0 0 1 2 2v7.4a2 2 0 0 1-2 2H5.5a2 2 0 0 1-2-2V7.2Z" />',
    "volume": '<path d="M4.5 9.2h3.4L12.5 5.5v13L7.9 14.8H4.5V9.2Z" /><path d="M16 9a4.2 4.2 0 0 1 0 6" /><path d="M18.6 6.6a7.6 7.6 0 0 1 0 10.8" />',
    "palette": '<path d="M12 3.2a8.8 8.8 0 0 0 0 17.6c1.5 0 2.2-.9 2.2-2 0-1.4-1.1-1.7-1.1-2.9 0-1 .8-1.8 1.9-1.8h2.1c2 0 3.5-1.5 3.5-3.6C20.6 6.4 16.7 3.2 12 3.2Z" /><circle cx="8" cy="9" r="1.2" fill="currentColor" /><circle cx="12" cy="7.2" r="1.2" fill="currentColor" /><circle cx="15.8" cy="8.6" r="1.2" fill="currentColor" />',
    "cpu": '<rect x="6.5" y="6.5" width="11" height="11" rx="2.4" /><rect x="10" y="10" width="4" height="4" rx="1" /><path d="M9 3v3.2M15 3v3.2M9 17.8V21M15 17.8V21M3 9h3.2M3 15h3.2M17.8 9H21M17.8 15H21" />',
    "close": '<path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />',
    "minimize": '<path d="M6 12h12" />',
    "maximize": '<rect x="6.2" y="6.2" width="11.6" height="11.6" rx="2" />',
    "restore": '<rect x="8" y="8" width="10" height="10" rx="1.8" /><path d="M6 15.5V6.8A1.8 1.8 0 0 1 7.8 5H16" />',
    "external": '<path d="M14 4h6v6" /><path d="M20 4 11 13" /><path d="M18 14.5V19a1.8 1.8 0 0 1-1.8 1.8H5A1.8 1.8 0 0 1 3.2 19V7.8A1.8 1.8 0 0 1 5 6h4.5" />',
    "plus": '<path d="M12 5v14M5 12h14" />',
    "link": '<path d="M10 13.8a4.2 4.2 0 0 0 6 0l2.3-2.3a4.2 4.2 0 1 0-6-6L11 6.8" /><path d="M14 10.2a4.2 4.2 0 0 0-6 0l-2.3 2.3a4.2 4.2 0 1 0 6 6L13 17.2" />',
    "check": '<path d="m5 12.6 4.2 4.2L19 6" />',
    "alert": '<path d="M12 4.4 21 19.6H3L12 4.4Z" /><path d="M12 9.6v4.6" /><circle cx="12" cy="17" r="1" fill="currentColor" />',
    "info": '<circle cx="12" cy="12" r="8.6" /><path d="M12 11v5" /><circle cx="12" cy="8" r="1" fill="currentColor" />',
    "clock": '<circle cx="12" cy="12" r="8.6" /><path d="M12 7v5.4l3.2 2" />',
    "chevron": '<path d="m9 5.5 6.5 6.5L9 18.5" />',
    "power": '<path d="M12 3.5v8" /><path d="M6.4 6.9a8 8 0 1 0 11.2 0" />',
    "wifi": '<path d="M4 9.5a12 12 0 0 1 16 0" /><path d="M7 12.8a8 8 0 0 1 10 0" /><path d="M9.8 16a4 4 0 0 1 4.4 0" /><circle cx="12" cy="19" r="1.1" fill="currentColor" />',
    "edit": '<path d="M4 20h4.2L20 8.2a2 2 0 0 0 0-2.8L18.6 4a2 2 0 0 0-2.8 0L4 15.8V20Z" /><path d="m14.5 5.5 4 4" />',
    "copy": '<rect x="8.5" y="8.5" width="11" height="11" rx="2.2" /><path d="M15.5 5.5h-9a2 2 0 0 0-2 2v9" />',
    "filter": '<path d="M4 5.5h16l-6.2 7.4v5.4l-3.6 2v-7.4L4 5.5Z" />',
    "shield-off": '<path d="M12 3.2 19 6v6c0 4.3-2.9 7.4-7 8.8C7.9 19.4 5 16.3 5 12V6l7-2.8Z" /><path d="m5 5 14 14" />',
}


def svg_icon(name: str, size: int = 24) -> str:
    body = ICON_PATHS[name]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" '
        f'viewBox="0 0 24 24" color="#EAF0FF" {W}>{body}</svg>'
    )


def write_icons() -> None:
    for name, body in ICON_PATHS.items():
        path = ICONS / f"{name}.svg"
        path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
            f'viewBox="0 0 24 24" color="#EAF0FF" {W}>{body}\n</svg>\n',
            encoding="utf-8",
        )


def brand_svg(primary: str = "#7C5CFF", secondary: str = "#22D3EE", muted: bool = False) -> str:
    if muted:
        primary, secondary = "#5B6478", "#8792A8"
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#111a2f"/>
      <stop offset="1" stop-color="#070a12"/>
    </linearGradient>
    <linearGradient id="accent" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{primary}"/>
      <stop offset="1" stop-color="{secondary}"/>
    </linearGradient>
    <radialGradient id="glow" cx="0.5" cy="0.35" r="0.65">
      <stop offset="0" stop-color="{primary}" stop-opacity="0.42"/>
      <stop offset="1" stop-color="{primary}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="512" height="512" rx="116" fill="url(#bg)"/>
  <rect width="512" height="512" rx="116" fill="url(#glow)"/>
  <path d="M256 74 392 124v112c0 82-55 142-136 172-81-30-136-90-136-172V124L256 74Z"
        fill="none" stroke="url(#accent)" stroke-width="18" stroke-linejoin="round" opacity="0.95"/>
  <path d="M256 98 370 139v96c0 69-45 120-114 147-69-27-114-78-114-147v-96L256 98Z"
        fill="{primary}" opacity="0.07"/>
  <g fill="none" stroke="url(#accent)" stroke-width="24" stroke-linecap="round" stroke-linejoin="round">
    <path d="M196 196h120L196 316h120"/>
  </g>
  <g fill="{secondary}">
    <circle cx="316" cy="196" r="10"/>
    <circle cx="196" cy="316" r="10"/>
    <circle cx="256" cy="256" r="7" opacity="0.85"/>
  </g>
  <g stroke="{primary}" stroke-width="3" opacity="0.55">
    <path d="M256 74v-26M163 108 143 88M349 108l20-20M120 236H92M392 236h28"/>
  </g>
  <g fill="{primary}" opacity="0.8">
    <circle cx="256" cy="45" r="7"/><circle cx="140" cy="85" r="7"/><circle cx="372" cy="85" r="7"/>
    <circle cx="89" cy="236" r="7"/><circle cx="423" cy="236" r="7"/>
  </g>
</svg>
'''


def write_brand() -> None:
    (BRAND / "logo.svg").write_text(brand_svg(), encoding="utf-8")
    (BRAND / "logo-mark.svg").write_text(brand_svg(), encoding="utf-8")
    (BRAND / "tray-active.svg").write_text(brand_svg("#7C5CFF", "#22D3EE"), encoding="utf-8")
    (BRAND / "tray-inactive.svg").write_text(brand_svg(muted=True), encoding="utf-8")


def render_assets() -> None:
    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QGuiApplication, QImage, QPainter
    from PySide6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication(sys.argv[:1])

    def render(svg_text: str, size: int, destination: Path) -> None:
        renderer = QSvgRenderer(svg_text.encode("utf-8"))
        image = QImage(size, size, QImage.Format_ARGB32)
        image.fill(Qt.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        renderer.render(painter, QRectF(0, 0, size, size))
        painter.end()
        image.save(str(destination))

    logo = (BRAND / "logo.svg").read_text(encoding="utf-8")
    for size in (16, 24, 32, 48, 64, 128, 256, 512, 1024):
        render(logo, size, BRAND / "png" / f"zentrix-{size}.png")
    render(logo, 1024, ROOT / "docs" / "logo.png")

    # Tray icons keep a transparent margin so Windows renders them crisply.
    for state in ("active", "inactive"):
        text = (BRAND / f"tray-{state}.svg").read_text(encoding="utf-8")
        for size in (16, 24, 32, 48):
            render(text, size, BRAND / "png" / f"tray-{state}-{size}.png")

    # Multi-resolution ICO.
    from PIL import Image

    base = Image.open(BRAND / "png" / "zentrix-256.png").convert("RGBA")
    base.save(BRAND / "zentrix.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48),
                                           (64, 64), (128, 128), (256, 256)])
    base_1024 = Image.open(BRAND / "png" / "zentrix-1024.png").convert("RGBA")
    base_1024.save(BRAND / "zentrix.png")

    # ICNS container with PNG entries.
    entries = [("ic07", 128), ("ic08", 256), ("ic09", 512), ("ic10", 1024)]
    chunks = b""
    for kind, size in entries:
        data = (BRAND / "png" / f"zentrix-{size}.png").read_bytes()
        chunks += kind.encode("ascii") + struct.pack(">I", len(data) + 8) + data
    (BRAND / "zentrix.icns").write_bytes(b"icns" + struct.pack(">I", len(chunks) + 8) + chunks)
    app.quit()


if __name__ == "__main__":
    write_icons()
    write_brand()
    render_assets()
    print("icons:", len(list(ICONS.glob("*.svg"))), "png:", len(list((BRAND / 'png').glob('*.png'))))
