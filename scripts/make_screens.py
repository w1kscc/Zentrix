"""Render docs screenshots offscreen: launch the real app hidden (QT_QPA_PLATFORM=offscreen), open every page and save widget.grab() as PNG into docs/screenshots/.

Usage (from repo root):
    python scripts/make_screens.py [--light-only] [--out DIR]

Named real-window shots (dark, light) replace files in docs/screenshots by the same names as before.
"""

from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Must be set before QApplication and src.paths exist.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# The offscreen platform ships no font config on Windows: without QT_QPA_FONTDIR
# every non-Latin glyph renders as tofu.
windir = os.environ.get("WINDIR", r"C:\Windows")
os.environ.setdefault("QT_QPA_FONTDIR", os.path.join(windir, "Fonts"))

# Isolated profile: run against a throwaway settings folder so the user's
# real %APPDATA%\Zentrix profile (theme, video, cache.db) is never touched.
if "--use-real-profile" not in sys.argv:
    temp_root = os.environ.get("TEMP") or tempfile.gettempdir()
    profile = Path(temp_root) / "ZentrixScreensProfile"
    profile.mkdir(parents=True, exist_ok=True)
    os.environ["APPDATA"] = str(profile)

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication  # noqa: E402

from src import constants, paths  # noqa: E402
from src.logger import setup_logging  # noqa: E402
from src.settings_store import settings  # noqa: E402
from src.sound_generator import SoundManager  # noqa: E402
from src.ui.context import AppContext  # noqa: E402

SIZE = (1440, 900)
PAGE_KEYS = ("home", "zapret", "vpn", "blockcheck", "tools", "monitor", "updates", "settings")
SETTINGS_SECTIONS = {
    "settings-appearance": 0,
    "settings-sounds": 1,
    "settings-engines": 2,
    "settings-automation": 3,
    "settings-maintenance": 4,
    "settings-about": 5,
}


def settle(app: QApplication, ms: int = 350) -> None:
    """Pump the event loop for ``ms`` so lazy pages finish building."""
    deadline = QEventLoop()
    QTimer.singleShot(ms, deadline.quit)
    deadline.exec()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "docs" / "screenshots"))
    args = parser.parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    setup_logging()
    paths.ensure_dirs()

    # Never show the real tray/exit animations in the shots.
    settings.set("general.start_minimized", False, save=False)
    saved_theme = str(settings.get("appearance.theme", "dark") or "dark")

    sound = SoundManager(tone="soft", volume=0, enabled=False)
    app = QApplication(sys.argv)
    app.setApplicationName(constants.APP_NAME)
    app.setStyle("Fusion")

    from src.ui.main_window import MainWindow

    context = AppContext(app, sound)
    # No popups in the shots, and never leak the real public IP into them.
    import src.net as net_mod

    def _fake_ip(*args, **kwargs):
        return {"ip": "203.0.113.17", "city": "", "country_name": "",
                "country_code": ""}

    net_mod.external_ip_info = _fake_ip
    import src.ui.pages.vpn as vpn_page_mod

    vpn_page_mod.net.external_ip_info = _fake_ip
    context.notify = lambda *args, **kwargs: None
    window = MainWindow(context)
    window.resize(*SIZE)
    window.show()
    settle(app, 600)

    def shoot(name: str) -> None:
        pixmap = window.grab()
        target = out_dir / f"{name}.png"
        pixmap.save(str(target))
        print(f"[screens] {target.name} ({pixmap.width()}x{pixmap.height()})", flush=True)

    # Light home first (needs the theme over), then switch back to dark.
    if saved_theme != "light":
        defaults = __import__("src.ui.theme", fromlist=["THEMES"]).THEMES["light"]
        settings.update("appearance", {"theme": "light", **defaults}, save=False)
        context.apply_theme()
        settle(app, 500)
        window.show_page("home")
        settle(app, 400)
        shoot("home-light")
        defaults = __import__("src.ui.theme", fromlist=["THEMES"]).THEMES[saved_theme]
        settings.update("appearance", {"theme": saved_theme, **defaults}, save=False)
        context.apply_theme()
        settings.save()

    for key in PAGE_KEYS:
        window.show_page(key)
        settle(app, 450)
        shoot(key)

    settings_page = context.pages.get("settings")
    if settings_page is None and hasattr(window, "pages"):
        settings_page = window.pages.get("settings")
    if settings_page is not None:
        window.show_page("settings")
        settle(app, 300)
        for name, index in SETTINGS_SECTIONS.items():
            try:
                settings_page._switch_section(index)
            except Exception as exc:  # section moved — keep the old screenshot
                print(f"[screens] section {name}: {exc}", flush=True)
                continue
            settle(app, 350)
            shoot(name)

    if saved_theme != "light":
        defaults = __import__("src.ui.theme", fromlist=["THEMES"]).THEMES[saved_theme]
        settings.update("appearance", {"theme": saved_theme, **defaults}, save=False)
        settings.save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
