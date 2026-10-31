"""JSON settings store with atomic writes and debounced persistence."""

from __future__ import annotations

import copy
import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

from . import constants, paths


DEFAULTS: dict[str, Any] = {
    "version": 1,
    "general": {
        "language": "ru",
        "start_minimized": False,
        "autostart": False,
        "auto_clean": False,
        "auto_clean_days": 7,
        "check_updates_on_start": False,
        "close_to_tray": True,
        "first_tray_hint": True,
    },
    "appearance": {
        "theme": "dark",
        "accent": "#7C5CFF",
        "accent2": "#22D3EE",
        "bg": "#080B12",
        "bg2": "#101726",
        "text": "#EAF0FF",
        "muted": "#8B93A7",
        "radius": 18,
        "card_opacity": 0.62,
        "border_opacity": 0.10,
        "font_family": "Segoe UI",
        "font_size": 10,
        "animations": True,
        "video_enabled": True,
        "video_path": "",
        "video_dim": 0.58,
        "video_muted": True,
        "video_blur": False,
        "preset": constants.DEFAULT_PRESET_NAME,
    },
    "sounds": {
        "enabled": True,
        "volume": 40,
        "tone": "soft",
        "regenerate": 1,
    },
    "zapret": {
        "path": "",
        "strategy": "general.bat",
        "autostart": False,
        "extra_args": "",
        "auto_scroll": True,
        "search_exhaustive": False,
        "gamefilter_mode": "disabled",
        "gamefilter_games": [],
    },
    "happ": {
        "path": "",
        "core": "",
        "config": "",
        "subscription": "",
        "socks_port": 10808,
        "http_port": 10809,
        "sysproxy": True,
        "autostart": False,
    },
    "hiddify": {
        "path": "",
        "core": "",
        "config": "",
        "subscription": "",
        "mixed_port": 2080,
        "api_port": 9091,
        "sysproxy": True,
        "autostart": False,
    },
    "vpn": {
        "core": "xray",
        "multiproxy": False,
        "share": False,
        "share_route": "vpn",
    },
    "monitor": {
        "interval": 1.0,
        "show_connections": True,
    },
    "updates": {
        "zentrix_repo": constants.ZENTRIX_REPO,
        "check_on_start": False,
        "last_check": 0,
    },
    "ui": {
        "window_width": 1320,
        "window_height": 860,
        "maximized": False,
        "nav_collapsed": False,
        "last_page": "home",
    },
    "maintenance": {
        "keep_presets": True,
        "last_clean": 0,
        "cleaned_total": 0,
    },
}


def _deep_merge(base: dict, incoming: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


class Settings:
    """Thread-safe settings accessor.

    Reads are cheap (in-memory dict). Writes are persisted through a small
    debounce timer so dragging a colour picker cannot hammer the disk.
    """

    def __init__(self, path: Path | None = None) -> None:
        self._path = path or paths.SETTINGS_FILE
        self._lock = threading.RLock()
        self._save_timer: threading.Timer | None = None
        self._listeners: list[Callable[[str], None]] = []
        self._data = self._load()
        self._changed_keys: set[str] = set()

    # ------------------------------------------------------------------ load
    def _load(self) -> dict[str, Any]:
        data = copy.deepcopy(DEFAULTS)
        # Local developer defaults (git-ignored) only fill empty values.
        if paths.LOCAL_DEFAULTS_FILE.exists():
            try:
                local = json.loads(paths.LOCAL_DEFAULTS_FILE.read_text(encoding="utf-8"))
                if isinstance(local, dict):
                    data = _deep_merge(data, local)
            except Exception:
                pass
        if self._path.exists():
            try:
                stored = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(stored, dict):
                    data = _deep_merge(data, stored)
            except Exception:
                # Corrupt settings must never prevent the app from starting.
                try:
                    self._path.replace(self._path.with_suffix(".broken.json"))
                except OSError:
                    pass
        return data

    # ------------------------------------------------------------------ read
    def get(self, dotted: str, default: Any = None) -> Any:
        with self._lock:
            node: Any = self._data
            for part in dotted.split("."):
                if not isinstance(node, dict) or part not in node:
                    return default
                node = node[part]
            return copy.deepcopy(node) if isinstance(node, (dict, list)) else node

    def section(self, name: str) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data.get(name, {}))

    def as_dict(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._data)

    # ----------------------------------------------------------------- write
    def set(self, dotted: str, value: Any, *, save: bool = True) -> None:
        with self._lock:
            parts = dotted.split(".")
            node = self._data
            for part in parts[:-1]:
                node = node.setdefault(part, {})
            if node.get(parts[-1]) == value:
                return
            node[parts[-1]] = value
            self._changed_keys.add(parts[0])
        if save:
            self.schedule_save()
        self._notify(parts[0])

    def update(self, section: str, values: dict[str, Any], *, save: bool = True) -> None:
        with self._lock:
            node = self._data.setdefault(section, {})
            changed = {k: v for k, v in values.items() if node.get(k) != v}
            if not changed:
                return
            node.update(copy.deepcopy(changed))
            self._changed_keys.add(section)
        if save:
            self.schedule_save()
        self._notify(section)

    def replace_section(self, section: str, values: dict[str, Any]) -> None:
        with self._lock:
            self._data[section] = copy.deepcopy(values)
        self.save()
        self._notify(section)

    # ---------------------------------------------------------------- events
    def subscribe(self, callback: Callable[[str], None]) -> None:
        self._listeners.append(callback)

    def _notify(self, section: str) -> None:
        for callback in list(self._listeners):
            try:
                callback(section)
            except Exception:
                pass

    # ------------------------------------------------------------------ save
    def schedule_save(self, delay: float = 0.35) -> None:
        with self._lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
            self._save_timer = threading.Timer(delay, self.save)
            self._save_timer.daemon = True
            self._save_timer.start()

    def save(self) -> None:
        with self._lock:
            if self._save_timer is not None:
                self._save_timer.cancel()
                self._save_timer = None
            payload = json.dumps(self._data, ensure_ascii=False, indent=2)
            self._changed_keys.clear()
        self._atomic_write(payload)

    def _atomic_write(self, payload: str) -> None:
        paths.ensure_dirs()
        target = self._path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(
                prefix=".settings-", suffix=".tmp", dir=str(target.parent)
            )
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, target)
        except Exception:
            try:
                target.write_text(payload, encoding="utf-8")
            except OSError:
                pass


settings = Settings()
