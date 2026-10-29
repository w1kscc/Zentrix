"""Cleaner safety: previews, root confinement and active-engine protection."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import cleaner, paths
from src.settings_store import Settings


@pytest.fixture()
def sandbox(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "data"
    engines = tmp_path / "engines"
    cache = data / "cache"
    sounds = cache / "sounds"
    logs = data / "logs"
    presets = data / "presets"
    downloads = data / "downloads"
    temp = data / "temp"
    for folder in (cache, sounds, logs, presets, downloads, temp, engines):
        folder.mkdir(parents=True)

    monkeypatch.setattr(paths, "CACHE_DIR", cache)
    monkeypatch.setattr(paths, "SOUNDS_CACHE_DIR", sounds)
    monkeypatch.setattr(paths, "LOGS_DIR", logs)
    monkeypatch.setattr(paths, "PRESETS_DIR", presets)
    monkeypatch.setattr(paths, "DOWNLOADS_DIR", downloads)
    monkeypatch.setattr(paths, "TEMP_DIR", temp)
    monkeypatch.setattr(paths, "DATA_DIR", data)
    monkeypatch.setattr(paths, "ENGINES_DIR", engines)

    store = Settings(tmp_path / "settings.json")
    monkeypatch.setattr(cleaner, "settings", store)
    return {
        "data": data, "engines": engines, "cache": cache, "sounds": sounds,
        "logs": logs, "presets": presets, "downloads": downloads, "temp": temp,
    }


def test_scan_previews_only_safe_categories(sandbox) -> None:
    (sandbox["logs"] / "old.log").write_text("old", encoding="utf-8")
    (sandbox["logs"] / "zentrix.log").write_text("active", encoding="utf-8")
    (sandbox["sounds"] / "click.wav").write_bytes(b"RIFF")
    (sandbox["downloads"] / "old.zip").write_bytes(b"PK")
    (sandbox["temp"] / "staging").mkdir()

    report = cleaner.Cleaner().scan(include_presets=False, include_sound_cache=True,
                                    older_than_days=0)
    names = {item.path.name for item in report.items}

    assert "old.log" in names
    assert "zentrix.log" not in names  # active log is never offered
    assert "click.wav" in names
    assert "staging" in names
    assert report.total_size > 0


def test_active_engine_is_protected_but_snapshot_is_not(sandbox) -> None:
    current = sandbox["engines"] / "zapret"
    old = sandbox["engines"] / "zapret.old-20260101"
    for folder in (current, old):
        (folder / "bin").mkdir(parents=True)
        (folder / "bin" / "winws.exe").write_bytes(b"MZ")

    report = cleaner.Cleaner().scan(include_presets=False, include_sound_cache=False)
    paths_found = {item.path.name for item in report.items}

    assert "zapret.old-20260101" in paths_found
    assert "zapret" not in paths_found

    removed, _freed, errors = cleaner.Cleaner().delete(report.items)
    assert removed == 1
    assert errors == []
    assert current.exists()
    assert not old.exists()


def test_delete_refuses_paths_outside_sandbox(sandbox, tmp_path: Path) -> None:
    victim = tmp_path / "important.txt"
    victim.write_text("keep me", encoding="utf-8")
    item = cleaner.CleanItem(victim, victim.stat().st_size, "temp", "test")

    removed, _freed, errors = cleaner.Cleaner().delete([item])

    assert removed == 0
    assert errors
    assert victim.exists()


def test_scan_never_returns_unused_presets_by_default(sandbox) -> None:
    (sandbox["presets"] / "custom.json").write_text("{}", encoding="utf-8")

    default_report = cleaner.Cleaner().scan(include_presets=False)
    assert not any(item.category == "presets" for item in default_report.items)

    opt_in = cleaner.Cleaner().scan(include_presets=True)
    assert any(item.path.name == "custom.json" for item in opt_in.items)
