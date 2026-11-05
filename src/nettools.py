"""Network tools: repair, DNS presets, hosts editor and diagnostics.

Every mutating function requires administrator rights on Windows and shells
out to the standard utilities (netsh/ipconfig). Pure helpers (presets, hosts
parsing) are separated so they can be unit-tested headlessly.
"""

from __future__ import annotations

import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .logger import get_logger

log = get_logger("nettools")

WINDOWS_HOSTS = Path(r"C:\Windows\System32\drivers\etc\hosts")

DNS_PRESETS: dict[str, dict] = {
    "cloudflare": {"label": "Cloudflare", "servers": ["1.1.1.1", "1.0.0.1"]},
    "google": {"label": "Google", "servers": ["8.8.8.8", "8.8.4.4"]},
    "adguard": {"label": "AdGuard", "servers": ["94.140.14.14", "94.140.15.15"]},
    "family": {"label": "AdGuard Family", "servers": ["94.140.14.15", "94.140.15.16"]},
    "dhcp": {"label": "Как у провайдера (DHCP)", "servers": []},
}

ANTI_AD_DOMAINS = [
    "ads.adfox.ru", "an.yandex.ru", "googleads.g.doubleclick.net",
    "ads.youtube.com", "ad.mail.ru", "adserv.adfox.ru",
    "top-fwz1.mail.ru", "ads.twitter.com", "ad.adriver.ru",
]

REPAIR_STEPS = (
    ("flushdns", "Очистка кэша DNS", ["ipconfig", "/flushdns"]),
    ("winsock", "Сброс Winsock", ["netsh", "winsock", "reset"]),
    ("ipreset", "Сброс IP-стека", ["netsh", "int", "ip", "reset"]),
)


def _decode(raw: bytes) -> str:
    """Windows console utilities (ping/tracert/netsh) print in OEM CP866;
    try UTF-8 first, then the OEM/ANSI codepages."""
    for codec in ("utf-8", "cp866", "cp1251"):
        try:
            return raw.decode(codec)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def _run(args: list[str], timeout: float = 30.0) -> tuple[int, str]:
    try:
        result = subprocess.run(args, capture_output=True, timeout=timeout,
                                creationflags=0x08000000)  # CREATE_NO_WINDOW
        output = _decode(result.stdout or b"") + _decode(result.stderr or b"")
        return result.returncode, output.strip()
    except FileNotFoundError:
        return -1, f"Утилита не найдена: {args[0]}"
    except subprocess.TimeoutExpired:
        return -1, "Превышено время ожидания"
    except Exception as exc:
        return -1, str(exc)


# ------------------------------------------------------------------- repair
def repair_network(clean_zentrix_cache: bool = False) -> list[tuple[str, str, bool]]:
    """Run the «Починить сеть» steps. Returns (key, title, ok) rows."""
    results: list[tuple[str, str, bool]] = []
    for key, title, args in REPAIR_STEPS:
        code, output = _run(args)
        ok = code == 0
        if not ok and key == "winsock" and "требуются права" in output.lower():
            ok = False
        results.append((key, title, ok))
        log.info("Починка сети · %s: %s %s", key, "ok" if ok else "fail", output[:120])
    if clean_zentrix_cache:
        from . import paths
        import shutil
        for cache_dir in (paths.CACHE_DIR, paths.TEMP_DIR):
            try:
                if cache_dir.exists():
                    shutil.rmtree(cache_dir, ignore_errors=True)
                    cache_dir.mkdir(parents=True, exist_ok=True)
            except Exception:
                pass
        results.append(("zentrix_cache", "Очистка кэша Zentrix", True))
    return results


# ---------------------------------------------------------------------- DNS
def set_dns(interface: str, preset_key: str) -> tuple[bool, str]:
    """Apply a DNS preset to a network interface via netsh. Admin required."""
    preset = DNS_PRESETS.get(preset_key)
    if preset is None:
        return False, f"Неизвестный пресет: {preset_key}"
    servers = preset["servers"]
    label = preset["label"]
    if not servers:
        code, output = _run(["netsh", "interface", "ip", "set", "dns",
                             f"name={interface}", "source=dhcp"])
        ok = code == 0
        return ok, (f"DNS сброшен на DHCP ({interface})" if ok
                    else f"Не удалось сбросить DNS: {output[:120]}")
    code, output = _run(["netsh", "interface", "ip", "set", "dns", f"name={interface}",
                         "static", servers[0], "primary"])
    if code != 0:
        return False, f"Не удалось задать DNS ({label}): {output[:120]}"
    for index, server in enumerate(servers[1:], start=2):
        _run(["netsh", "interface", "ip", "add", "dns", f"name={interface}",
              server, f"index={index}"])
    _run(["ipconfig", "/flushdns"])
    return True, f"DNS изменён на {label} ({', '.join(servers)})"


def active_interfaces() -> list[str]:
    """Interface names suitable for netsh (skip virtual/tunnel adapters)."""
    try:
        import psutil
    except ImportError:
        return []
    skip = ("vpn", "tap", "tun", "wintun", "wireguard", "loopback", "virtual",
            "vethernet", "bluetooth", "hm")
    names = []
    for name, stats in psutil.net_if_stats().items():
        if not stats.isup:
            continue
        lowered = name.casefold()
        if any(token in lowered for token in skip):
            continue
        names.append(name)
    return names


# -------------------------------------------------------------------- hosts
def read_hosts(path: Path | None = None) -> list[tuple[str, str, str]]:
    """Parse hosts into (enabled, ip, host) rows; comments are dropped."""
    target = path or WINDOWS_HOSTS
    rows = []
    try:
        for line in target.read_text(encoding="utf-8", errors="replace").splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            enabled = True
            if stripped.startswith("## "):  # our disabled marker
                stripped = stripped[3:]
                enabled = False
            elif stripped.startswith("#"):
                continue
            parts = stripped.split()
            if len(parts) < 2:
                continue
            rows.append((enabled, parts[0], parts[1]))
    except OSError as exc:
        log.warning("Чтение hosts: %s", exc)
    return rows


def render_hosts(rows: list[tuple[bool, str, str]]) -> str:
    lines = ["# Zentrix hosts — управляется на вкладке Инструменты"]
    for enabled, ip, host in rows:
        lines.append(f"{'## ' if not enabled else ''}{ip}\t{host}")
    return "\n".join(lines) + "\n"


def write_hosts(rows: list[tuple[bool, str, str]], path: Path | None = None) -> tuple[bool, str]:
    target = path or WINDOWS_HOSTS
    try:
        target.write_text(render_hosts(rows), encoding="utf-8")
        _run(["ipconfig", "/flushdns"])
        return True, "hosts сохранён"
    except PermissionError:
        return False, "Нет прав на запись hosts (нужен администратор)"
    except OSError as exc:
        return False, f"Не удалось записать hosts: {exc}"


def anti_ad_rows(existing: list[tuple[bool, str, str]]) -> list[tuple[bool, str, str]]:
    """Merge the anti-ad preset into current rows without duplicates."""
    rows = list(existing)
    known = {host for _enabled, _ip, host in rows}
    added = 0
    for domain in ANTI_AD_DOMAINS:
        if domain not in known:
            rows.append((True, "0.0.0.0", domain))
            added += 1
    return rows


# --------------------------------------------------------------- diagnostics
def tcp_ping(host: str, port: int = 443, timeout: float = 3.0) -> float | None:
    """TCP connect latency in ms, or None when unreachable."""
    start = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return round((time.perf_counter() - start) * 1000.0)
    except OSError:
        return None


def icmp_ping(host: str, count: int = 4) -> tuple[bool, float, str]:
    """Windows ping. Returns (alive, avg_ms, raw tail)."""
    code, output = _run(["ping", "-n", str(count), "-w", "2000", host], timeout=25)
    if code != 0:
        return False, 0.0, output[-300:]
    latencies = []
    import re
    for line in output.splitlines():
        match = re.search(r"[<|=](\d+)[ ]?(?:мс|ms)", line, re.IGNORECASE)
        if not match:
            match = re.search(r"time[=<]\s?(\d+)", line, re.IGNORECASE)
        if match:
            latencies.append(int(match.group(1)))
    alive = bool(latencies) or "TTL=" in output
    avg = round(sum(latencies) / len(latencies)) if latencies else 0.0
    return alive, float(avg), output[-300:]


def traceroute(host: str, max_hops: int = 12) -> str:
    code, output = _run(["tracert", "-d", "-h", str(max_hops), "-w", "1200", host],
                        timeout=90)
    return output if output else (f"tracert завершился с кодом {code}")


def port_scan(host: str, ports: list[int], timeout: float = 1.5) -> list[tuple[int, bool]]:
    """Concurrent TCP port probe; returns (port, open) pairs in input order."""
    def probe(port: int) -> tuple[int, bool]:
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return port, True
        except OSError:
            return port, False

    with ThreadPoolExecutor(max_workers=min(32, len(ports) or 1)) as pool:
        return list(pool.map(probe, ports))


WHOIS_SERVERS = {".ru": "whois.tcinet.ru", ".рф": "whois.tcinet.ru",
                 ".com": "whois.verisign-grs.com", ".net": "whois.verisign-grs.com",
                 ".org": "whois.pir.org", ".dev": "whois.nic.google"}


def whois_query(domain: str, timeout: float = 8.0) -> str:
    """Minimal whois via port 43 (Windows has no bundled whois)."""
    lowered = domain.casefold()
    server = "whois.iana.org"
    for suffix, candidate in WHOIS_SERVERS.items():
        if lowered.endswith(suffix):
            server = candidate
            break
    try:
        with socket.create_connection((server, 43), timeout=timeout) as sock:
            sock.sendall(f"{domain}\r\n".encode("utf-8"))
            chunks = []
            while True:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                chunks.append(chunk)
        return b"".join(chunks).decode("utf-8", errors="replace")[:4000]
    except OSError as exc:
        return f"whois недоступен: {exc}"
