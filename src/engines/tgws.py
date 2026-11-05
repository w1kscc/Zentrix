"""TG WS Proxy engine: local MTProto-over-WebSocket bridge for Telegram.

Runs the upstream Flowseal/tg-ws-proxy core IN-PROCESS (a worker thread, no
external GUI and no extra tray icon). The engine source lives in
``engines/tgwsproxy`` — downloaded and updated by the updater from the
upstream releases, exactly like Zapret.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path

from .. import paths
from ..logger import get_logger
from ..settings_store import settings
from .base import BaseEngine, EngineError

log = get_logger("tgws")

DEFAULT_DC_IP = ["2:149.154.167.220", "4:149.154.167.220"]
DEFAULT_PORT = 1443


def engine_root() -> Path:
    return paths.ENGINES_DIR / "tgwsproxy"


def core_available() -> bool:
    return (engine_root() / "proxy" / "tg_ws_proxy.py").exists()


def vendored_version() -> str:
    meta = engine_root() / "version.json"
    try:
        return str(json.loads(meta.read_text(encoding="utf-8")).get("version", "") or "")
    except Exception:
        return ""


def ensure_importable() -> None:
    """Make the vendored ``proxy`` package importable (idempotent)."""
    root = str(engine_root())
    if root not in sys.path:
        sys.path.insert(0, root)


class TgWsProxyEngine(BaseEngine):
    """In-process TG WS Proxy controller."""

    key = "tgwsproxy"
    title = "TG WS Proxy"

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self._thread: threading.Thread | None = None
        self._stop_event = None
        self._proxy = None  # lazily imported vendored module
        self._install_log_hook()

    # ------------------------------------------------------------- lifecycle
    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def is_available(self) -> bool:
        return core_available()

    def core_installed(self) -> bool:
        return core_available()

    def _install_log_hook(self) -> None:
        """Forward the vendored core's logging into the UI log signal."""
        import logging

        engine = self

        class _Bridge(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                try:
                    engine.log_line.emit(record.getMessage())
                except Exception:
                    pass

        bridge = _Bridge(level=logging.INFO)
        logging.getLogger("tgwsproxy").addHandler(bridge)

    # ------------------------------------------------------------------ start
    def start(self) -> None:
        if self.running:
            raise EngineError("TG WS Proxy уже запущен", "already_running")
        if not core_available():
            raise EngineError(
                "Ядро TG WS Proxy не найдено — установите его на вкладке Zapret "
                "или через Обновления.", "missing_core",
            )
        cfg = self._build_runtime_config()
        ensure_importable()
        import proxy as tg_proxy
        import proxy.tg_ws_proxy as tg_core  # vendored engine entry

        self._proxy = tg_proxy
        self._core = tg_core
        # Apply the settings to the vendored ProxyConfig singleton.
        from proxy.config import parse_dc_ip_list

        pc = tg_proxy.proxy_config
        try:
            pc.dc_redirects = parse_dc_ip_list(cfg["dc_ip"])
        except ValueError as exc:
            raise EngineError(f"Некорректный DC → IP список: {exc}", "bad_dc")
        pc.port = cfg["port"]
        pc.host = cfg["host"]
        pc.secret = cfg["secret"]
        pc.buffer_size = 256 * 1024
        pc.pool_size = 4
        pc.fallback_cfproxy = cfg["cfproxy"]
        pc.cfproxy_h2_media = cfg["h2"]
        pc.cfproxy_user_domains = []
        pc.cfproxy_worker_domains = []
        pc.force_test_dc = False
        pc.disable_secure = False

        import asyncio
        self._stop_event = asyncio.Event()
        self._loop = None
        self._intentional_stop = False
        self._set_status("starting", f"Запуск TG WS Proxy на {cfg['host']}:{cfg['port']}…")
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="tgwsproxy")
        self._thread.start()
        time.sleep(0.6)
        if self._thread.is_alive():
            self._set_status("running", f"TG WS Proxy · {cfg['host']}:{cfg['port']}")
            self.log_line.emit(
                f"[TG WS Proxy] MTProxy-мост запущен: {cfg['host']}:{cfg['port']} — "
                "подключите Telegram Desktop по ссылке")
        else:
            self._set_status("error", "TG WS Proxy завершился сразу после запуска")
            raise EngineError("Не удалось запустить TG WS Proxy (порт занят?)", "core_exited")

    def _run(self) -> None:
        import asyncio

        # Own loop so stop() can wake the core's stop_event thread-safely.
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._core._run(self._stop_event))
        except Exception as exc:
            if not self._intentional_stop:
                self._set_status("error", f"TG WS Proxy: {exc}")
                log.warning("TG WS Proxy упал: %s", exc)
                return
        if not self._intentional_stop:
            self._set_status("stopped", "TG WS Proxy остановлен")

    def cleanup(self) -> None:
        try:
            if self.running:
                self.stop()
        except Exception:
            pass

    def stop(self) -> None:
        self._intentional_stop = True
        self._set_status("stopping", "Остановка TG WS Proxy…")
        if self._stop_event is not None:
            try:
                if self._loop is not None and self._loop.is_running():
                    self._loop.call_soon_threadsafe(self._stop_event.set)
                else:
                    self._stop_event.set()
            except Exception:
                self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            if self._thread.is_alive():
                log.warning("TG WS Proxy не остановился за 5 с — порт может быть занят")
        self._thread = None
        self._stop_event = None
        self._set_status("stopped", "TG WS Proxy остановлен")

    # ---------------------------------------------------------------- config
    def _build_runtime_config(self) -> dict:
        secret = str(settings.get("tgws.secret", "") or "").strip()
        if not secret:
            import secrets as _secrets
            secret = _secrets.token_hex(16)
            settings.set("tgws.secret", secret)
        dc_ip = list(settings.get("tgws.dc_ip", DEFAULT_DC_IP) or DEFAULT_DC_IP)
        return {
            "port": int(settings.get("tgws.port", DEFAULT_PORT) or DEFAULT_PORT),
            "host": str(settings.get("tgws.host", "127.0.0.1") or "127.0.0.1"),
            "secret": secret,
            "dc_ip": dc_ip,
            "cfproxy": bool(settings.get("tgws.cfproxy", True)),
            "h2": bool(settings.get("tgws.h2", True)),
        }

    def proxy_url(self) -> str:
        """tg:// deep link that configures Telegram Desktop in one click."""
        cfg = self._build_runtime_config()
        return (f"tg://proxy?server={cfg['host']}&port={cfg['port']}"
                f"&secret=dd{cfg['secret']}")
