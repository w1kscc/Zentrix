"""Filesystem layout used by Zentrix.

Everything writable lives under %APPDATA%\\Zentrix. Engine binaries live next
to the application (``engines/``) and are never shipped in the source tree.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Directory containing the executable (packaged) or the repository root."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def resource_dir() -> Path:
    """Directory that holds bundled read-only resources (assets/)."""
    if is_frozen():
        return Path(getattr(sys, "_MEIPASS", app_dir()))
    return Path(__file__).resolve().parent.parent


DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "Zentrix"
CACHE_DIR = DATA_DIR / "cache"
SOUNDS_CACHE_DIR = CACHE_DIR / "sounds"
LOGS_DIR = DATA_DIR / "logs"
PRESETS_DIR = DATA_DIR / "presets"
DOWNLOADS_DIR = DATA_DIR / "downloads"
TEMP_DIR = DATA_DIR / "temp"
PROFILES_DIR = DATA_DIR / "profiles"
CONFIG_DIR = DATA_DIR / "configs"

SETTINGS_FILE = DATA_DIR / "settings.json"
STATE_FILE = DATA_DIR / "state.json"
LOG_FILE = LOGS_DIR / "zentrix.log"

ASSETS_DIR = resource_dir() / "assets"
ICONS_DIR = ASSETS_DIR / "icons"
BRAND_DIR = ASSETS_DIR / "brand"
ENGINES_DIR = app_dir() / "engines"

# Optional, git-ignored developer overrides (local source paths, etc.).
LOCAL_DEFAULTS_FILE = app_dir() / "settings.local.json"

_created = False


def ensure_dirs() -> None:
    """Create the writable directory tree exactly once per process."""
    global _created
    if _created:
        return
    for directory in (
        DATA_DIR,
        CACHE_DIR,
        SOUNDS_CACHE_DIR,
        LOGS_DIR,
        PRESETS_DIR,
        DOWNLOADS_DIR,
        TEMP_DIR,
        PROFILES_DIR,
        CONFIG_DIR,
        ENGINES_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)
    _created = True


def human_size(num_bytes: float) -> str:
    if num_bytes < 1024:
        return f"{num_bytes:.0f} Б"
    for unit in ("КБ", "МБ", "ГБ", "ТБ"):
        num_bytes /= 1024.0
        if num_bytes < 1024 or unit == "ТБ":
            return f"{num_bytes:.1f} {unit}".replace(".0 ", " ")
    return f"{num_bytes:.1f} ТБ"
