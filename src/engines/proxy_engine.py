"""Headless proxy core wrapper shared by the Happ (Xray) and Hiddify (sing-box) tabs.

The core runs hidden, listens on a local mixed/SOCKS port, and Zentrix talks
to the UI through Qt signals. Traffic accounting uses per-process IO counters,
which works without any admin rights. Supports multi-proxy with Balancer for sing-box.
"""

from __future__ import annotations

import json
import socket
import threading
import time
import urllib.request
from pathlib import Path

from PySide6.QtCore import QTimer, Signal

from .. import net, paths, winapi
from ..logger import get_logger
from ..settings_store import settings
from .balancer import TCPBalancer
from . import cores, links
from .base import BaseEngine, EngineError

log = get_logger("proxy")


def _port_free(port: int, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


class ProxyEngine(BaseEngine):
    """Common implementation; subclasses only pick the core kind and ports."""

    core_kind = "xray"
    ns = "happ"
    need_admin = False
    stats_start_requested = Signal()
    stats_stop_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._nodes_cache: list[links.ProxyNode] = []
        self._nodes_mtime = -1
        self._stats_timer: QTimer | None = None
        self._last_io: tuple[int, int] | None = None
        self._last_sample = 0.0
        self._total_up = 0
        self._total_down = 0
        self._proxy_applied = False
        self._balancer = TCPBalancer() if self.core_kind == "singbox" else None
        self._backend_ports: list[int] = []
        self._using_balancer = False
        self.stats_start_requested.connect(self._start_stats)
        self.stats_stop_requested.connect(self._stop_stats)

    # ------------------------------------------------------------------ paths
    @property
    def profile_file(self) -> Path:
        return paths.PROFILES_DIR / "vpn.txt"

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
        cleaned = text.strip()
        parsed = links.parse_links(cleaned) if cleaned else []
        if cleaned and not parsed:
            return 0
        paths.ensure_dirs()
        self.profile_file.write_text(cleaned + ("\n" if cleaned else ""), encoding="utf-8")
        self._nodes_mtime = -1
        return len(self.nodes())

    def nodes(self) -> list[links.ProxyNode]:
        try:
            mtime = self.profile_file.stat().st_mtime_ns
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
        listen_host = self._share_host() if settings.get("vpn.share", False) else "127.0.0.1"
        if self.core_kind == "xray":
            return links.xray_config(node, socks_port=primary, http_port=secondary,
                                     listen_host=listen_host)
        nodes = self.nodes()
        if bool(settings.get("vpn.multiproxy", False)) and len(nodes) > 1:
            selected_nodes = nodes[:5]
            if len(selected_nodes) < 2:
                return links.singbox_config(node, mixed_port=primary, api_port=secondary,
                                            listen_host=listen_host)
            return links.singbox_config(
                selected_nodes, mixed_port=primary, api_port=secondary,
                backend_ports=self._backend_ports,
            )
        return links.singbox_config(node, mixed_port=primary, api_port=secondary,
                                    listen_host=listen_host)

    @staticmethod
    def _share_host() -> str:
        addresses = net.lan_ipv4_addresses()
        if not addresses:
            raise EngineError("Не найден активный IPv4‑адрес локальной сети", "no_lan_ip")
        return addresses[0]

    @staticmethod
    def _display_host() -> str:
        if settings.get("vpn.share", False):
            addresses = net.lan_ipv4_addresses()
            if addresses:
                return addresses[0]
        return "127.0.0.1"

    def public_proxy(self) -> str:
        primary, secondary = self.ports()
        host = self._display_host()
        if self.core_kind == "xray":
            return f"http={host}:{secondary};https={host}:{secondary};socks={host}:{primary}"
        if self._using_balancer:
            return f"http={host}:{primary};https={host}:{primary}"
        return f"http={host}:{primary};https={host}:{primary};socks={host}:{primary}"

    @property
    def multiproxy_active(self) -> bool:
        return self._using_balancer and self.status == "running"

    def proxy_url(self) -> str:
        """HTTP-compatible local proxy URL used by diagnostics and GeoIP."""
        primary, secondary = self.ports()
        host = self._display_host()
        return f"http://{host}:{secondary if self.core_kind == 'xray' else primary}"

    def set_system_proxy(self, enabled: bool) -> bool:
        applied = winapi.set_system_proxy(bool(enabled), self.public_proxy() if enabled else "")
        self._proxy_applied = bool(enabled and applied)
        return applied

    def start(self) -> None:
        if self.running:
            raise EngineError("Подключение уже активно", "already_running")
        app_context = self.parent()
        for key in ("happ", "hiddify"):
            peer = getattr(app_context, key, None)
            if peer is not None and peer is not self and peer.status == "running":
                raise EngineError("Отключите другой VPN‑движок перед запуском этого", "peer_running")
        core = self.core_path()
        if core is None:
            self._set_status("missing", "Ядро не установлено")
            raise EngineError(
                "Ядро не найдено. Скачайте его на этой вкладке или укажите путь в настройках.",
                "missing_core",
            )
        primary, secondary = self.ports()
        nodes = self.nodes()
        multiplex = (self.core_kind == "singbox"
                     and bool(settings.get("vpn.multiproxy", False)) and len(nodes) > 1)
        self._using_balancer = multiplex
        active_nodes = nodes[:5] if multiplex else []
        self._backend_ports = []
        if multiplex:
            candidate = primary + 1
            attempts = 0
            while len(self._backend_ports) < len(active_nodes) and attempts < 65536:
                if candidate > 65535:
                    candidate = 1024
                if candidate not in {primary, secondary} and _port_free(candidate):
                    self._backend_ports.append(candidate)
                candidate += 1
                attempts += 1
            if len(self._backend_ports) != len(active_nodes):
                self._using_balancer = False
                raise EngineError("Не удалось найти свободные порты для мульти‑прокси", "no_ports")
        ports_to_check = [primary, secondary, *self._backend_ports]
        bind_host = self._share_host() if settings.get("vpn.share", False) else "127.0.0.1"
        for index, port in enumerate(ports_to_check):
            host = (bind_host if index == 0 or self.core_kind == "xray"
                    else "127.0.0.1")
            if not _port_free(port, host):
                self._using_balancer = False
                raise EngineError(
                    f"Порт {port} уже занят другим приложением. Измените порт в настройках.",
                    "port_busy",
                )
        try:
            config = self.build_config()
        except ValueError as exc:
            self._using_balancer = False
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
            self._using_balancer = False
            self._set_status("error", str(exc))
            raise
        time.sleep(0.45)
        if not self.supervisor.running:
            self._using_balancer = False
            self._set_status("error", "Ядро завершилось сразу после запуска")
            raise EngineError(
                "Ядро не запустилось. Проверьте журнал: возможно, неверная ссылка или порт.",
                "core_exited",
            )
        if multiplex and self._balancer:
            try:
                self._balancer.start(
                    bind_host,
                    primary,
                    [("127.0.0.1", port) for port in self._backend_ports],
                )
            except Exception as exc:
                self.supervisor.stop()
                self._using_balancer = False
                self._set_status("error", f"Балансировщик не запустился: {exc}")
                raise EngineError(f"Балансировщик не запустился: {exc}", "balancer_start") from exc
        self._last_io = None
        self._last_sample = time.monotonic()
        self._total_up = 0
        self._total_down = 0
        if settings.get(f"{self.ns}.sysproxy", False):
            self.set_system_proxy(True)
        # The start worker emits a queued request; QTimer is owned by the UI thread.
        self.stats_start_requested.emit()
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
        self.stats_stop_requested.emit()
        if self._balancer:
            self._balancer.stop()
        self._using_balancer = False
        self.supervisor.stop()
        if self._proxy_applied:
            self.set_system_proxy(False)
        self._pid_file().unlink(missing_ok=True)
        self._set_status("stopped", "Отключено")

    def _on_exit(self, code: int) -> None:
        self.stats_stop_requested.emit()
        if self._balancer:
            self._balancer.stop()
        self._using_balancer = False
        if self._proxy_applied:
            self.set_system_proxy(False)
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
        if self._balancer:
            self._balancer.stop()
        self._using_balancer = False
        if self._proxy_applied:
            self.set_system_proxy(False)
        super().cleanup()

    def ensure_profile_from_settings(self) -> None:
        """Migrate the old separate profiles to the shared VPN profile once."""
        if self.profile_file.exists() and self.profile_file.stat().st_size > 0:
            return
        paths.ensure_dirs()
        sources = [paths.PROFILES_DIR / "happ.txt", paths.PROFILES_DIR / "hiddify.txt"]
        seeds = [str(settings.get(f"{name}.config", "") or "").strip()
                 for name in ("happ", "hiddify")]
        chunks = []
        for source in sources:
            try:
                chunks.append(source.read_text(encoding="utf-8").strip())
            except OSError:
                pass
        chunks.extend(seeds)
        unique: list[str] = []
        seen: set[str] = set()
        for line in "\n".join(item for item in chunks if item).splitlines():
            candidate = line.strip()
            if candidate and candidate not in seen:
                unique.append(candidate)
                seen.add(candidate)
        if unique:
            self.set_profile_text("\n".join(unique))


class ShareProxyEngine(BaseEngine):
    """LAN proxy that hands traffic straight to the internet (no tunnel).

    Used by "share via Zapret": the shared inbound runs on the installed
    Xray / sing-box core with a direct outbound, so device traffic leaves
    the PC as-is and the running winws.exe strategy processes it.
    """

    key = "share"
    title = "Прокси раздачи"

    @property
    def core_kind(self) -> str:
        return "singbox" if str(settings.get("vpn.core", "xray")) == "singbox" else "xray"

    @property
    def config_file(self) -> Path:
        return paths.CONFIG_DIR / "share" / "config.json"

    def _core_ns(self) -> str:
        return "hiddify" if self.core_kind == "singbox" else "happ"

    def core_path(self) -> Path | None:
        return cores.find_core(self.core_kind,
                               str(settings.get(f"{self._core_ns()}.core", "") or ""))

    def core_installed(self) -> bool:
        return self.core_path() is not None

    def ports(self) -> tuple[int, int]:
        if self.core_kind == "xray":
            return (int(settings.get("happ.socks_port", 10808) or 10808),
                    int(settings.get("happ.http_port", 10809) or 10809))
        return (int(settings.get("hiddify.mixed_port", 2080) or 2080),
                int(settings.get("hiddify.api_port", 9091) or 9091))

    def _share_host(self) -> str:
        addresses = net.lan_ipv4_addresses()
        if not addresses:
            raise EngineError("Не найден активный IPv4‑адрес локальной сети", "no_lan_ip")
        return addresses[0]

    def port_for(self, protocol: str) -> int:
        primary, secondary = self.ports()
        return secondary if protocol == "http" and self.core_kind == "xray" else primary

    def start(self) -> None:
        if self.running:
            raise EngineError("Прокси раздачи уже запущен", "already_running")
        core = self.core_path()
        if core is None:
            raise EngineError(
                "Ядро не найдено — установите Xray или sing-box во вкладке VPN.",
                "missing_core",
            )
        primary, secondary = self.ports()
        host = self._share_host()
        if self.core_kind == "xray":
            config = links.direct_xray_config(socks_port=primary, http_port=secondary,
                                              listen_host=host)
        else:
            config = links.direct_singbox_config(mixed_port=primary, listen_host=host)
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(json.dumps(config, ensure_ascii=False, indent=2),
                                    encoding="utf-8")
        self._set_status("starting", "Запуск прокси раздачи…")
        self._intentional_stop = False
        try:
            pid = self.supervisor.start([str(core), "run", "-c", str(self.config_file)],
                                        core.parent, pid_file=self._pid_file())
        except EngineError as exc:
            self._set_status("error", str(exc))
            raise
        time.sleep(0.45)
        if not self.supervisor.running:
            self._set_status("error", "Прокси раздачи завершился сразу после запуска")
            raise EngineError(
                "Прокси раздачи не запустился. Возможно, порт занят VPN‑движком.",
                "core_exited",
            )
        self._set_status("running", f"Раздача · PID {pid}")
        self.log_line.emit(f"[Zentrix] Прокси раздачи: {host}:{primary} (direct, без туннеля)")

    def stop(self) -> None:
        self._intentional_stop = True
        self._set_status("stopping", "Остановка прокси раздачи…")
        self.supervisor.stop()
        self._pid_file().unlink(missing_ok=True)
        self._set_status("stopped", "Прокси раздачи остановлен")
