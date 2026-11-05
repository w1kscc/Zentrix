"""TG WS Proxy engine and updater component tests (no network)."""

from __future__ import annotations

import json
import zipfile

import pytest

from src.engines import tgws
from src import updater


def test_core_available_false_without_engine(tmp_path, monkeypatch):
    monkeypatch.setattr(tgws.paths, "ENGINES_DIR", tmp_path / "none")
    assert not tgws.core_available()
    assert tgws.vendored_version() == ""


def test_vendored_version(tmp_path, monkeypatch):
    root = tmp_path / "engines" / "tgwsproxy"
    (root / "proxy").mkdir(parents=True)
    (root / "proxy" / "tg_ws_proxy.py").write_text("# core", encoding="utf-8")
    (root / "version.json").write_text(json.dumps({"version": "1.11.4"}), encoding="utf-8")
    monkeypatch.setattr(tgws.paths, "ENGINES_DIR", tmp_path / "engines")
    assert tgws.core_available()
    assert tgws.vendored_version() == "1.11.4"


def test_runtime_config_generates_secret(monkeypatch):
    from src.settings_store import settings

    settings.set("tgws.secret", "")
    settings.set("tgws.port", 1500)
    engine = tgws.TgWsProxyEngine.__new__(tgws.TgWsProxyEngine)
    cfg = engine._build_runtime_config()
    assert cfg["port"] == 1500
    assert len(cfg["secret"]) == 32
    assert cfg["dc_ip"] == tgws.DEFAULT_DC_IP
    # second call reuses the stored secret
    assert engine._build_runtime_config()["secret"] == cfg["secret"]


def test_proxy_url_format(monkeypatch):
    from src.settings_store import settings

    settings.set("tgws.secret", "a" * 32)
    settings.set("tgws.port", 1443)
    engine = tgws.TgWsProxyEngine.__new__(tgws.TgWsProxyEngine)
    url = engine.proxy_url()
    assert url.startswith("tg://proxy?server=127.0.0.1&port=1443&secret=dd")
    assert "a" * 32 in url


class _Status:
    latest = "1.11.5"
    tag = "v1.11.5"
    version = "1.11.5"
    name = "TG WS Proxy 1.11.5"
    html_url = "https://example.test"
    error = ""
    assets = []


def test_check_tgws_uses_source_archive(monkeypatch):
    monkeypatch.setattr(updater.paths, "ENGINES_DIR", updater.paths.TEMP_DIR)  # not installed
    monkeypatch.setattr(updater.net, "github_latest", lambda repo: _Status())
    status = updater.check("tgwsproxy")
    assert status.latest == "1.11.5"
    assert status.asset_url.endswith("/archive/refs/tags/v1.11.5.zip")
    assert status.has_update  # nothing installed


def test_install_tgwsproxy_replaces_and_rolls_back(tmp_path, monkeypatch):
    engine_dir = tmp_path / "engines" / "tgwsproxy"
    old_core = engine_dir / "proxy"
    old_core.mkdir(parents=True)
    (old_core / "tg_ws_proxy.py").write_text("old", encoding="utf-8")
    (engine_dir / "version.json").write_text(json.dumps({"version": "1.11.4"}), encoding="utf-8")

    archive = tmp_path / "src.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("tg-ws-proxy-1.11.5/proxy/tg_ws_proxy.py", b"new")
        bundle.writestr("tg-ws-proxy-1.11.5/README.md", b"readme")

    monkeypatch.setattr(updater.paths, "ENGINES_DIR", tmp_path / "engines")
    monkeypatch.setattr(updater.paths, "TEMP_DIR", tmp_path / "temp")
    monkeypatch.setattr(updater, "download", lambda key, progress=None, cancel=None: archive)
    monkeypatch.setattr(updater, "installed_version", lambda key: "1.11.4")
    monkeypatch.setattr(updater, "_cleanup_archive", lambda archive: None)

    result = updater._install_tgwsproxy(archive, updater.COMPONENTS["tgwsproxy"],
                                        "1.11.5", "stamp")
    assert (engine_dir / "proxy" / "tg_ws_proxy.py").read_bytes() == b"new"
    meta = json.loads((engine_dir / "version.json").read_text(encoding="utf-8"))
    assert meta["version"] == "1.11.5"
    assert "1.11.5" in result["message"]
    assert not list(tmp_path.glob("**/tgwsproxy.old-*"))


def test_install_tgwsproxy_rollback_on_bad_archive(tmp_path, monkeypatch):
    engine_dir = tmp_path / "engines" / "tgwsproxy"
    (engine_dir / "proxy").mkdir(parents=True)
    (engine_dir / "proxy" / "tg_ws_proxy.py").write_text("old", encoding="utf-8")

    archive = tmp_path / "src.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("readme.txt", b"no core here")

    monkeypatch.setattr(updater.paths, "ENGINES_DIR", tmp_path / "engines")
    monkeypatch.setattr(updater.paths, "TEMP_DIR", tmp_path / "temp")
    monkeypatch.setattr(updater, "installed_version", lambda key: "1.11.4")

    with pytest.raises(RuntimeError):
        updater._install_tgwsproxy(archive, updater.COMPONENTS["tgwsproxy"],
                                   "1.11.5", "stamp")
    assert (engine_dir / "proxy" / "tg_ws_proxy.py").read_bytes() == b"old"
