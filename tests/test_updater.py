"""Updater asset selection: Windows must get the zip, not rar/tar.gz."""

from __future__ import annotations

from src import net, updater


def test_zapret_prefers_zip_asset() -> None:
    meta = updater.COMPONENTS["zapret"]
    release = net.Release(
        repo="Flowseal/zapret-discord-youtube",
        tag="1.10.4",
        name="1.10.4",
        assets=[
            net.Asset("zapret-discord-youtube-1.10.4.rar", "https://example/rar"),
            net.Asset("zapret-discord-youtube-1.10.4.tar.gz", "https://example/tar"),
            net.Asset("zapret-discord-youtube-1.10.4.zip", "https://example/zip"),
        ],
    )
    asset = net.pick_asset(release, meta["keywords"], exclude=meta["exclude"])
    assert asset is not None
    assert asset.name.endswith(".zip")


# ---------------------------------------------------------------------------
# Update replacement scenario: staging -> verify -> atomic replace -> rollback.

import json
import zipfile

import pytest


def _make_zip(path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w") as bundle:
        for name, data in entries.items():
            bundle.writestr(name, data)


def test_validate_zip_rejects_garbage(tmp_path):
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip at all")
    with pytest.raises(RuntimeError):
        updater._validate_zip(broken)


def test_extract_skips_traversal(tmp_path):
    archive = tmp_path / "evil.zip"
    _make_zip(archive, {"bin/winws.exe": b"MZ", "../outside.txt": b"nope"})
    destination = tmp_path / "out"
    updater._extract(archive, destination)
    assert (destination / "bin" / "winws.exe").read_bytes() == b"MZ"
    assert not (tmp_path / "outside.txt").exists()


class _Status:
    latest = "1.1.0"
    asset_name = "zapret.zip"
    asset_url = "https://example.test/zapret.zip"
    error = ""


def _mock_env(tmp_path, monkeypatch, archive, old_version="1.0.0"):
    engine_dir = tmp_path / "engines"
    old = engine_dir / "zapret"
    (old / "bin").mkdir(parents=True)
    (old / "bin" / "winws.exe").write_bytes(b"old")
    (old / "lists").mkdir()
    (old / "lists" / "user.txt").write_text("custom", encoding="utf-8")
    (old / "utils").mkdir()
    (old / "utils" / "game_filter.enabled").write_text("1", encoding="utf-8")
    (old / "version.json").write_text(json.dumps({"version": old_version}), encoding="utf-8")
    monkeypatch.setattr(updater.paths, "ENGINES_DIR", engine_dir)
    monkeypatch.setattr(updater.paths, "TEMP_DIR", tmp_path / "temp")
    monkeypatch.setattr(updater, "download", lambda key, progress=None, cancel=None: archive)
    monkeypatch.setattr(updater, "installed_version", lambda key: old_version)
    monkeypatch.setattr(updater, "check", lambda key: _Status())
    monkeypatch.setattr(updater, "_cleanup_archive", lambda archive: None)
    return engine_dir


def test_install_zapret_replaces_and_keeps_lists(tmp_path, monkeypatch):
    archive = tmp_path / "zapret.zip"
    _make_zip(archive, {"zapret/bin/winws.exe": b"new", "zapret/general.bat": b"@echo new"})
    engine_dir = _mock_env(tmp_path, monkeypatch, archive)

    result = updater.install("zapret")
    target = engine_dir / "zapret"
    assert (target / "bin" / "winws.exe").read_bytes() == b"new"
    assert (target / "lists" / "user.txt").read_text(encoding="utf-8") == "custom"
    assert (target / "utils" / "game_filter.enabled").exists()
    meta = json.loads((target / "version.json").read_text(encoding="utf-8"))
    assert meta["version"] == "1.1.0"
    assert not list(engine_dir.glob("zapret.old-*"))
    assert "1.1.0" in result["message"]


def test_install_zapret_rolls_back_on_bad_archive(tmp_path, monkeypatch):
    archive = tmp_path / "zapret.zip"
    _make_zip(archive, {"readme.txt": b"no binary"})
    engine_dir = _mock_env(tmp_path, monkeypatch, archive)

    with pytest.raises(RuntimeError):
        updater.install("zapret")
    assert (engine_dir / "zapret" / "bin" / "winws.exe").read_bytes() == b"old"
