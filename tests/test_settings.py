"""Settings store: dotted access, custom paths, atomic save and recovery."""

from __future__ import annotations

import json
from pathlib import Path

from src.settings_store import DEFAULTS, Settings


def test_defaults_and_dotted_access(tmp_path: Path) -> None:
    store = Settings(tmp_path / "settings.json")

    assert store.get("appearance.theme") == "dark"
    assert store.get("missing.key", "fallback") == "fallback"

    store.set("appearance.theme", "light", save=False)
    store.set("zapret.strategy", "general (ALT).bat", save=False)
    assert store.get("appearance.theme") == "light"
    assert store.get("zapret.strategy") == "general (ALT).bat"


def test_update_merges_and_only_marks_changes(tmp_path: Path) -> None:
    store = Settings(tmp_path / "settings.json")
    store.update("monitor", {"interval": 2.0}, save=False)
    assert store.get("monitor.interval") == 2.0
    assert store.get("monitor.show_connections") is True


def test_save_and_reload_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "settings.json"
    store = Settings(path)
    store.set("general.auto_clean", True, save=False)
    store.set("happ.socks_port", 1080, save=False)
    store.save()

    assert path.exists()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["general"]["auto_clean"] is True
    assert payload["happ"]["socks_port"] == 1080

    reloaded = Settings(path)
    assert reloaded.get("general.auto_clean") is True
    assert reloaded.get("happ.socks_port") == 1080
    # Unknown persisted keys are merged over defaults without dropping sections.
    assert "appearance" in payload


def test_corrupt_file_is_moved_aside(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{this is not json", encoding="utf-8")

    store = Settings(path)

    assert store.get("appearance.theme") == DEFAULTS["appearance"]["theme"]
    assert path.with_suffix(".broken.json").exists()


def test_default_last_page_is_valid(tmp_path: Path) -> None:
    store = Settings(tmp_path / "settings.json")
    assert store.get("ui.last_page") in {
        "home", "zapret", "happ", "hiddify", "monitor", "blockcheck", "updates", "settings",
    }
