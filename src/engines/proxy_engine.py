"""Headless proxy core wrapper shared by the Happ (Xray) and Hiddify (sing-box) tabs.

The core runs hidden, listens on a local mixed/SOCKS port, and Zentrix talks
to the UI through Qt signals. Traffic accounting uses per-process IO counters,
which works without any admin rights.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QTimer

from .. import paths, winapi
from ..logger import get_logger
from ..settings_store import settings
from . import cores, links
from .base import BaseEngine, EngineError

log = get_logger("proxy")


def _port_free(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


class ProxyEngine(BaseEngine):
    """Common implementation; subclasses only pick the core kind and ports."""

    core_kind = "xray"
    ns = "happ"
    need_admin = False

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._nodes_cache: list[links.ProxyNode] = []
        self._nodes_mtime = 0.0
        self._stats_timer: QTimer | None = None
        self._last_io: tuple[int, int] | None = None
        self._last_sample = 0.0
        self._total_up = 0
        self._total_down = 0
        self._proxy_applied = False

    # ------------------------------------------------------------------ paths
    @property
    def profile_file(self) -> Path:
        return paths.PROFILES_DIR / f"{self.ns}.txt"

    @property
    def config_file(self) -> Path:
        return paths.CONFIG_DIR / self.ns / "config.json"

    def core_path(self) -> Path | None:
        configured = str(settings.get(f"{self.ns}.core", "") or "")
        return cores.find_core(self.core_kind, configured)

    def core_installed(self) -> bool:
        return self.core_path() is not None

    def ports(self) -> tuple[int, int]:
        raise NotImplementedError

    # ---------------------------------------------------------------- profile
    def profile_text(self) -> str:
        try:
            return self.profile_file.read_text(encoding="utf-8")
        except OSError:
            return ""

    def set_profile_text(self, text: str) -> int:
        paths.ensure_dirs()
        self.profile_file.write_text(text.strip() + "\n", encoding="utf-8")
        self._nodes_mtime = 0.0
        return len(self.nodes())

    def nodes(self) -> list[links.ProxyNode]:
        try:
            mtime = self.profile_file.stat().st_mtime
        except OSError:
            return []
        if mtime != self._nodes_mtime:
            self._nodes_cache = links.parse_links(self.profile_text())
            self._nodes_mtime = mtime
        return self._nodes_cache

    def selected_index(self) -> int:
        nodes = self.nodes()
        index = int(settings.get(f"{self.ns}.node", 0) or 0)
        return index if 0 <= index < len(nodes) else 0

    def selected_node(self) -> links.ProxyNode | None:
        nodes = self.nodes()
        return nodes[self.selected_index()] if nodes else None

    def select_node(self, index: int) -> None:
        settings.set(f"{self.ns}.node", int(index))

    def fetch_subscription(self, url: str, timeout: float = 20.0) -> int:
        """Download a subscription URL and merge it into the profile."""
        request = urllib.request.Request(url, headers={"User-Agent": "Zentrix/1.0"})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read().decode("utf-8", errors="replace")
        nodes = links.parse_links(payload)
        if not nodes:
            raise EngineError("В подписке не найдено поддерживаемых серверов", "empty_subscription")
        existing = [node for node in self.nodes()]
        text = "\n".join(node.raw_link for node in existing if node.raw_link)
        self.set_profile_text("\n".join(filter(None, [text, payload])))
        return len(self.nodes())

    # ------------------------------------------------------------------ start
    def build_config(self) -> dict:
        node = self.selected_node()
        if node is None:
            raise EngineError(
                "Добавьте сервер: вставьте ссылку (vless/vmess/trojan/ss) или подписку.",
                "no_nodes",
            )
        primary, secondary = self.ports()
        if self.core_kind == "xray":
            return links.xray_config(node, socks_port=primary, http_port=secondary)
        return links.singbox_config(node, mixed_port=primary, api_port=secondary)

    def public_proxy(self) -> str:
        primary, secondary = self.ports()
        if self.core_kind == "xray":
            return f"http=127.0.0.1:{secondary};https=127.0.0.1:{secondary};socks=127.0.0.1:{primary}"
        return f"http=127.0.0.1:{primary};https=127.0.0.1:{primary};socks=127.0.0.1:{primary}"

    def start(self) -> None:
        if self.running:
            raise EngineError("Подключение уже активно", "already_running")
        core = self.core_path()
        if core is None:
            self._set_status("missing", "Ядро не установлено")
            raise EngineError(
                "Ядро не найдено. Скачайте его на этой вкладке или укажите путь в настройках.",
                "missing_core",
            )
        primary, secondary = self.ports()
        for port in (primary, secondary):
            if not _port_free(port):
                raise EngineError(
                    f"Порт {port} уже занят другим приложением. Измените порт в настройках.",
                    "port_busy",
                )
        try:
            config = self.build_config()
        except ValueError as exc:
            self._set_status("error", str(exc))
            raise EngineError(str(exc), "unsupported_transport") from exc
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8")

        self._set_status("starting", "Запуск ядра…")
        self._intentional_stop = False
        try:
            pid = self.supervisor.start(
                [str(core), "run", "-c", str(self.config_file)],
                core.parent,
                pid_file=self._pid_file(),
            )
        except EngineError as exc:
            self._set_status("error", str(exc))
            raise
        time.sleep(0.45)
        if not self.supervisor.running:
            self._set_status("error", "Ядро завершилось сразу после запуска")
            raise EngineError(
                "Ядро не запустилось. Проверьте журнал: возможно, неверная ссылка или порт.",
                "core_exited",
            )
        self._last_io = None
        self._last_sample = time.monotonic()
        self._total_up = 0
        self._total_down = 0
        if settings.get(f"{self.ns}.sysproxy", False):
            self._proxy_applied = winapi.set_system_proxy(True, self.public_proxy())
        # QTimer must be created/started on the engine's (UI) thread.
        QTimer.singleShot(0, self._start_stats)
        self._set_status("running", f"Подключено · PID {pid}")
        self.log_line.emit(f"[Zentrix] {self.title}: {self.selected_node().summary() if self.selected_node() else ''}")
        if self._proxy_applied:
            self.log_line.emit("[Zentrix] Системный прокси включён")
        else:
            self.log_line.emit(
                "[Zentrix] Системный прокси выключен — трафик Windows идёт напрямую"
            )

    def stop(self) -> None:
        self._intentional_stop = True
        self._set_status("stopping", "Отключение…")
        self._stop_stats()
        self.supervisor.stop()
        if self._proxy_applied:
            winapi.set_system_proxy(False)
            self._proxy_applied = False
        self._pid_file().unlink(missing_ok=True)
        self._set_status("stopped", "Отключено")

    def _on_exit(self, code: int) -> None:
        self._stop_stats()
        if self._proxy_applied:
            winapi.set_system_proxy(False)
            self._proxy_applied = False
        super()._on_exit(code)

    # ------------------------------------------------------------------ stats
    def _start_stats(self) -> None:
        if self._stats_timer is None:
            self._stats_timer = QTimer(self)
            self._stats_timer.setInterval(1000)
            self._stats_timer.timeout.connect(self._sample)
        self._stats_timer.start()

    def _stop_stats(self) -> None:
        if self._stats_timer:
            self._stats_timer.stop()

    def _sample(self) -> None:
        pid = self.supervisor.pid
        if not pid:
            return
        counters = winapi.process_io(pid)
        now = time.monotonic()
        up_rate = down_rate = 0.0
        if counters and self._last_io:
            delta_read = max(0, counters.read_bytes - self._last_io[0])
            delta_write = max(0, counters.write_bytes - self._last_io[1])
            elapsed = max(0.2, now - self._last_sample)
            down_rate = delta_read / elapsed
            up_rate = delta_write / elapsed
            self._total_down += delta_read
            self._total_up += delta_write
        if counters:
            self._last_io = (counters.read_bytes, counters.write_bytes)
        self._last_sample = now
        connections = sum(1 for item in winapi.tcp_connections() if item.pid == pid)
        self.stats_changed.emit({
            "up": up_rate,
            "down": down_rate,
            "total_up": self._total_up,
            "total_down": self._total_down,
            "connections": connections,
            "pid": pid,
        })

    # ------------------------------------------------------------- diagnostics
    def latency(self, timeout: float = 8.0) -> int | None:
        """Measure end-to-end latency through the local proxy (ms)."""
        primary, secondary = self.ports()
        port = primary if self.core_kind == "singbox" else secondary
        proxy = f"http://127.0.0.1:{port}"
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(handler)
        started = time.perf_counter()
        try:
            with opener.open("https://www.gstatic.com/generate_204", timeout=timeout) as response:
                response.read(1)
            return int((time.perf_counter() - started) * 1000)
        except Exception:
            return None

    def public_ip(self, timeout: float = 12.0) -> str | None:
        """Return the external IP as seen through the local proxy."""
        primary, secondary = self.ports()
        port = secondary if self.core_kind == "xray" else primary
        proxy = f"http://127.0.0.1:{port}"
        handler = urllib.request.ProxyHandler({"http": proxy, "https": proxy})
        opener = urllib.request.build_opener(handler)
        try:
            with opener.open("https://api.ipify.org", timeout=timeout) as response:
                value = response.read(64).decode("utf-8", errors="replace").strip()
            return value or None
        except Exception:
            return None

    def install_core(self, progress=None) -> Path:
        path = cores.install_core(self.core_kind, progress=progress)
        self.log_line.emit(f"[Zentrix] Ядро установлено: {path}")
        return path

    def cleanup(self) -> None:
        if self._proxy_applied:
            winapi.set_system_proxy(False)
            self._proxy_applied = False
        super().cleanup()

    def ensure_profile_from_settings(self) -> None:
        """Seed the profile from legacy settings (``subscription``/``config``)."""
        if self.profile_file.exists() and self.profile_file.stat().st_size > 0:
            return
        seed = str(settings.get(f"{self.ns}.config", "") or "").strip()
        if seed:
            try:
                self.set_profile_text(seed)
            except OSError:
                pass
