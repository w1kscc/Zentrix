"""Windows network tooling: DNS presets, diagnostics and hosts-file management."""

from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .logger import get_logger

log = get_logger("nettools")

USER_AGENT = "Zentrix/1.0"
CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

#: DNS-пресеты: ключ → (основной, вторичный) сервер; "auto" означает DHCP.
DNS_PRESETS: dict[str, tuple[str, str]] = {
    "auto": ("DHCP", ""),
    "cloudflare": ("1.1.1.1", "1.0.0.1"),
    "google": ("8.8.8.8", "8.8.4.4"),
    "adguard": ("94.140.14.14", "94.140.15.15"),
    "family": ("1.1.1.3", "1.0.0.3"),
}

#: Маркеры псевдо-/виртуальных адаптеров, скрытых из списка активных.
_SKIP_TOKENS = (
    "vpn", "tap", "tun", "wintun", "wireguard", "loopback",
    "virtual", "vethernet", "switch", "hyper-v", "wan miniport", "bluetooth",
)

HOSTS_HOST = "127.0.0.1"
_HOSTS_GROUP_RE = re.compile(r"^\s*#\s*ZENTRIX-GROUP\s+(\S+)\s*([^#]*)$")
_HOSTS_END_RE = re.compile(r"^\s*#\s*ZENTRIX-END\s+(\S+)\s*$")
_ADAPTER_HEADER_RE = re.compile(r'(?:интерфейса|interface)\s+"([^"\r\n]+)"')
_IP_TOKEN_RE = re.compile(
    r"\b(?:\d{1,3}(?:\.\d{1,3}){3}|[A-Fa-f0-9]{4}(?::[A-Fa-f0-9]{0,4}){2,7}|::[A-Fa-f0-9]*:)\b"
)
_IPV4_RE = re.compile(r"\b\d{1,3}(?:\.\d{1,3}){3}\b")
_PING_TIME_RE = re.compile(r"(?:время|time)\s*[=:]\s*(\d+)\s*(?:мс(?:ек)?|ms)", re.IGNORECASE)
_PING_AVG_RE = re.compile(r"(?:Среднее|Average)\s*=\s*(\d+)")
_PING_SENT_RE = re.compile(r"(?:отправлено|Sent)\s*[=:]\s*(\d+)", re.IGNORECASE)
_PING_RECEIVED_RE = re.compile(r"(?:получено|Received)\s*[=:]\s*(\d+)", re.IGNORECASE)
_TRACE_HOP_RE = re.compile(r"^\s*(\d{1,3})\s+(.+)$")
_TRACE_MS_RE = re.compile(r"(\d+)\s*(?:мс(?:ек)?|ms)\b", re.IGNORECASE)


# ------------------------------------------------------------------ helpers

def _decode_output(raw: bytes) -> str:
    """Decode console output, falling back to cp866/cp1251 for Cyrillic."""
    text = raw.decode("utf-8", errors="replace").rstrip("\r\n\x00")
    if "\ufffd" in text:
        for encoding in ("cp866", "cp1251"):
            try:
                candidate = raw.decode(encoding)
                if "\ufffd" not in candidate:
                    return candidate
            except Exception:  # noqa: BLE001
                continue
    return text


def _run(command: list[str], timeout: float = 30.0) -> tuple[int, str]:
    """Run a console command hidden and return (returncode, output)."""
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=max(1.0, timeout),
            creationflags=CREATE_NO_WINDOW,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("Не удалось выполнить %s: %s", command[0], exc)
        return 1, f"Не удалось выполнить команду {command[0]}: {exc}"
    output = _decode_output(completed.stdout or b"")
    if not output.strip():
        output = _decode_output(completed.stderr or b"")
    return int(completed.returncode), output


def _default_route_rows() -> list[dict[str, str]]:
    """Parse ``route print -4`` for 0.0.0.0 rows (gateway/interface/metric)."""
    rows: list[dict[str, str]] = []
    _, output = _run(["route", "print", "-4"])
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 5 or parts[0] != "0.0.0.0" or parts[1] != "0.0.0.0":
            continue
        rows.append({
            "gateway": parts[2],
            "interface_ip": parts[3],
            "metric": parts[4] if parts[4].isdigit() else "9999",
        })
    rows.sort(key=lambda row: int(row["metric"]))
    return rows


def _route_gateway_map() -> dict[str, str]:
    """Map local interface IP → default gateway taken from the route table."""
    result: dict[str, str] = {}
    for row in _default_route_rows():
        gateway = row["gateway"]
        if _IPV4_RE.fullmatch(gateway or ""):
            result.setdefault(row["interface_ip"], gateway)
    return result


def default_adapter() -> str:
    """Name of the adapter (by PSUTIL lookup) that owns the default route."""
    rows = _default_route_rows()
    if not rows:
        return ""
    wanted_ip = rows[0]["interface_ip"]
    try:
        import psutil
    except ImportError:
        return ""
    for name, addresses in (psutil.net_if_addrs() or {}).items():
        lowered = name.casefold()
        if any(token in lowered for token in _SKIP_TOKENS):
            continue
        for address in addresses:
            if address.family == socket.AF_INET and address.address == wanted_ip:
                return name
    return ""


def _resolve_adapter(adapter: str | None) -> str:
    resolved = (adapter or "").strip()
    return resolved or default_adapter()


def _parse_dnsservers(output: str) -> list[dict[str, list[str]]]:
    """Split ``netsh interface ip show dnsservers`` output into sections."""
    sections: list[dict[str, list[str]]] = []
    for line in output.splitlines():
        header = _ADAPTER_HEADER_RE.search(line)
        if header:
            sections.append({"name": header.group(1).strip(), "servers": []})
            continue
        if not sections or not line.strip():
            continue
        for token in _IP_TOKEN_RE.findall(line):
            if token != "0.0.0.0" and token not in sections[-1]["servers"]:
                sections[-1]["servers"].append(token)
    return sections


# -------------------------------------------------------------- DNS reading

def current_dns(adapter: str | None = None) -> dict:
    """Read the DNS servers of ``adapter`` (default route adapter if None)."""
    result: dict = {"adapter": adapter or "", "servers": [], "error": ""}
    code, output = _run(["netsh", "interface", "ip", "show", "dnsservers"])
    if code != 0 or not output.strip():
        result["error"] = output.strip() or "Не удалось прочитать настройки DNS"
        result["adapter"] = _resolve_adapter(adapter)
        return result
    sections = _parse_dnsservers(output)
    if not sections:
        result["error"] = "Не удалось разобрать список адаптеров"
        result["adapter"] = _resolve_adapter(adapter)
        return result

    chosen = None
    if not adapter:
        wanted = _resolve_adapter(None).casefold()
        chosen = next((item for item in sections
                       if item["name"].casefold() == wanted), None) or sections[0]
    else:
        wanted = adapter.strip().casefold()
        chosen = next((item for item in sections
                       if item["name"].casefold() == wanted), None)
        if chosen is None:
            result["error"] = f'Адаптер "{adapter}" не найден среди активных'
            result["adapter"] = adapter
            return result
    result["adapter"] = chosen["name"]
    result["servers"] = list(chosen["servers"])
    return result


# ---------------------------------------------------------------- DNS apply

def set_dns(pref_key: str | None = None, adapter: str | None = None,
            servers: Iterable[str] | None = None) -> dict:
    """Apply a DNS preset (or explicit ``servers``) on the given adapter.

    Requires elevation; every failure is reported in ``error`` instead of
    raising. ``pref_key="auto"`` switches the adapter back to DHCP.
    """
    result: dict = {"ok": False, "applied": [], "error": ""}
    static_servers: list[str] | None = None
    if servers is not None:
        static_servers = [str(item).strip() for item in servers
                          if str(item).strip() and _IP_TOKEN_RE.fullmatch(str(item).strip())]
        if not static_servers:
            result["error"] = "Список DNS-серверов пуст или некорректен"
            return result
    elif pref_key == "auto":
        static_servers = None
    elif pref_key in DNS_PRESETS:
        primary, secondary = DNS_PRESETS[pref_key]
        static_servers = [primary] + ([secondary] if secondary and secondary != "DHCP" else [])
    else:
        result["error"] = f"Неизвестный пресет DNS: {pref_key!r}. Доступно: {', '.join(DNS_PRESETS)}"
        return result

    resolved = _resolve_adapter(adapter)
    result["adapter"] = resolved
    if not resolved:
        result["error"] = "Не удалось определить сетевой адаптер"
        return result

    commands: list[str]
    if static_servers is None:
        commands = [f"source=dhcp name={resolved}"]
    else:
        commands = [f"source=static addr={static_servers[0]} name={resolved}"]
        for index, server in enumerate(static_servers[1:], start=2):
            commands.append(f"addr={server} index={index} name={resolved}")

    applied: list[str] = []
    for index, tail in enumerate(commands):
        argv = ["netsh", "interface", "ip", "set", "dns"] if index == 0 else \
            ["netsh", "interface", "ip", "add", "dns"]
        code, output = _run(argv + [tail], timeout=20.0)
        key = "auto" if static_servers is None else static_servers[min(index, len(static_servers) - 1)]
        if code != 0:
            result["error"] = (f"Команда netsh завершилась с ошибкой (код {code}): "
                               + output.strip().splitlines()[-1])
            log.warning("set_dns(%s) на %s не выполнен: %s", pref_key, resolved, result["error"])
            break
        if key not in applied:
            applied.append(key)
    result["applied"] = applied
    result["ok"] = not result["error"] and bool(applied)
    return result


# -------------------------------------------------------------- diagnostics

def adapter_list() -> list[dict]:
    """Active physical IPv4 adapters with their address and default gateway."""
    entries: list[dict] = []
    try:
        import psutil
    except ImportError:
        return entries
    gateways = _route_gateway_map()
    for name, stats in (psutil.net_if_stats() or {}).items():
        lowered = name.casefold()
        if not stats.isup or any(token in lowered for token in _SKIP_TOKENS):
            continue
        for address in (psutil.net_if_addrs() or {}).get(name, []):
            if address.family != socket.AF_INET:
                continue
            try:
                ip_value = ipaddress.ip_address(address.address)
            except ValueError:
                continue
            if ip_value.is_loopback or ip_value.is_link_local:
                continue
            entries.append({
                "name": name,
                "ip": str(ip_value),
                "gateway": gateways.get(str(ip_value), ""),
            })
            break
    return entries


def flush_dns_cache() -> dict:
    """Clear the Windows DNS resolver cache (needs elevation)."""
    code, output = _run(["ipconfig", "/flushdns"], timeout=15.0)
    text = output.strip()
    ok = code == 0
    return {"ok": ok, "error": "" if ok else (text or f"ipconfig завершился с кодом {code}")}


def reset_winsock() -> dict:
    """Reset the Winsock catalog; takes effect after a reboot."""
    code, output = _run(["netsh", "winsock", "reset"], timeout=20.0)
    ok = code == 0
    return {
        "ok": ok,
        "error": "" if ok else (output.strip() or f"netsh завершился с кодом {code}"),
        "message": ("Winsock сброшен. Изменения вступят в силу после перезагрузки компьютера."
                    if ok else "Сбросить Winsock не удалось — нужны права администратора."),
    }


def network_repair(adapter: str | None = None, progress: Callable[[str, str, bool], None] | None = None,
                   cycle_adapter: bool = False) -> dict:
    """Repair the network stack step by step and report each stage.

    Restarting the adapter is optional: ``cycle_adapter=True`` performs a
    disable/enable cycle via netsh (requires admin rights).
    """
    steps: list[dict] = []

    def _step(name: str, message: str, ok: bool) -> None:
        steps.append({"step": name, "ok": ok, "message": message})
        if progress:
            try:
                progress(name, message, ok)
            except Exception:  # noqa: BLE001
                pass

    flush = flush_dns_cache()
    _step("flush_dns", "Кеш DNS очищен" if flush["ok"] else flush["error"], flush["ok"])

    code, output = _run(["netsh", "int", "ip", "reset"])
    _step("reset_ip", ("Стек TCP/IP сброшен. Требуется перезагрузка."
                       if code == 0 else output.strip() or f"код {code}"), code == 0)

    winsock = reset_winsock()
    _step("reset_winsock", winsock["message"] or winsock["error"], winsock["ok"])

    resolved = (adapter or "").strip()
    if resolved:
        code, output = _run(["ipconfig", "/release", resolved])
        _step("release", (f"Аренда адреса на {resolved} освобождена" if code == 0
                          else output.strip() or f"код {code}"), code == 0)
        code, output = _run(["ipconfig", "/renew", resolved], timeout=90.0)
        _step("renew", (f"адрес на {resolved} обновлён" if code == 0
                        else output.strip() or f"код {code}"), code == 0)
    else:
        _step("renew", "Адаптер не указан — продление аренды пропущено", True)

    if cycle_adapter and resolved:
        code, output = _run(["netsh", "interface", "set", "interface",
                             "name=" + resolved, "admin=disable"])
        enabled_ok = False
        if code == 0:
            _step("cycle_disable", f"Адаптер {resolved} отключён", True)
            time.sleep(1.0)
            code, output = _run(["netsh", "interface", "set", "interface",
                                 "name=" + resolved, "admin=enable"], timeout=45.0)
            enabled_ok = code == 0
        _step("cycle_enable", (f"адаптер {resolved} снова включён" if enabled_ok
                               else output.strip() or f"код {code}"), enabled_ok)

    ok = all(step["ok"] for step in steps)
    return {"ok": ok, "steps": steps, "notice": ("Некоторые изменения сетевого стека "
                                                 "применяются после перезагрузки.")}


def ping(host: str, count: int = 4, timeout_ms: int = 1500) -> dict:
    """System ``ping`` with parsed per-reply and average times."""
    result: dict = {"host": host, "sent": 0, "received": 0, "times_ms": [],
                    "avg_ms": 0.0, "ok": False, "error": ""}
    count = max(1, min(int(count), 50))
    wait_ms = max(200, int(timeout_ms))
    code, output = _run(["ping", "-n", str(count), "-w", str(wait_ms), host],
                        timeout=max(15.0, count * wait_ms / 1000 + 15.0))
    if not output.strip():
        result["error"] = output.strip() or f"ping завершился с кодом {code}"
        return result

    resolved = _IPV4_RE.search(output)
    if resolved:
        result["host"] = resolved.group(0)
    result["times_ms"] = [int(match.group(1)) for match in _PING_TIME_RE.finditer(output)]
    sent_match = _PING_SENT_RE.search(output)
    received_match = _PING_RECEIVED_RE.search(output)
    result["sent"] = int(sent_match.group(1)) if sent_match else len(result["times_ms"])
    result["received"] = int(received_match.group(1)) if received_match else len(result["times_ms"])
    avg_match = _PING_AVG_RE.search(output)
    if avg_match:
        result["avg_ms"] = float(avg_match.group(1))
    elif result["times_ms"]:
        result["avg_ms"] = round(sum(result["times_ms"]) / len(result["times_ms"]), 1)
    result["ok"] = result["received"] > 0
    if not result["ok"]:
        result["error"] = "Хост недоступен (потеря всех пакетов)"
    return result


def _parse_tracert_output(output: str) -> list[dict]:
    """Turn tracert lines into [{"hop": n, "ip": .., "ms": [..] or None}]."""
    hops: list[dict] = []
    for line in output.splitlines():
        match = _TRACE_HOP_RE.match(line)
        if not match:
            continue
        rest = match.group(2)
        times = [int(value) for value in _TRACE_MS_RE.findall(rest)]
        ip_match = _IPV4_RE.search(rest) or re.search(r"[A-Fa-f0-9]{4}(?::[A-Fa-f0-9]{0,4}){2,7}", rest)
        hops.append({
            "hop": int(match.group(1)),
            "ip": ip_match.group(0) if ip_match else "",
            "ms": times if times else None,
        })
    return hops


def traceroute(host: str, max_hops: int = 18, timeout_ms: int = 1500) -> list[dict]:
    """System ``tracert`` without DNS resolution, parsed per hop."""
    max_hops = max(2, int(max_hops))
    timeout_ms = max(200, int(timeout_ms))
    _, output = _run(["tracert", "-d", "-h", str(max_hops), "-w", str(timeout_ms), host],
                     timeout=max_hops * (timeout_ms / 1000) * 3 + 25.0)
    return _parse_tracert_output(output)


def tcp_ping(host: str, port: int, timeout: float = 2.0) -> dict | None:
    """Measure TCP connect latency in ms; ``None`` when connection fails."""
    started = time.perf_counter()
    try:
        with socket.create_connection((host, int(port)), timeout=max(0.05, float(timeout))):
            pass
    except OSError as exc:
        log.debug("tcp_ping %s:%s failed: %s", host, port, exc)
        return None
    return {"host": host, "port": int(port), "ok": True,
            "ms": int(round((time.perf_counter() - started) * 1000))}


def port_scan(host: str, ports: Iterable[int], timeout: float = 0.8) -> list[dict]:
    """Concurrent TCP connect scan, results sorted by port."""
    port_list = sorted({int(port) for port in ports if 0 < int(port) < 65536})
    if not port_list:
        return []

    def _probe(port: int) -> dict:
        try:
            with socket.create_connection((host, port), timeout=max(0.05, float(timeout))):
                return {"port": port, "open": True}
        except OSError:
            return {"port": port, "open": False}

    workers = min(64, len(port_list))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_probe, port_list))


def whois(domain: str, timeout: float = 8.0) -> dict:
    """Domain info via RDAP (registrar, key dates, statuses)."""
    result: dict = {"ok": False, "registrar": "", "created": "", "expires": "",
                    "status": [], "raw_excerpt": None, "error": ""}
    host = domain.strip().lower()
    for prefix in ("http://", "https://", "www."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    host = host.split("/")[0].split("?")[0]
    if not host:
        result["error"] = "Не указан домен"
        return result
    request = urllib.request.Request(
        f"https://rdap.org/domain/{host}",
        headers={"User-Agent": USER_AGENT, "Accept": "application/rdap+json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(262_144).decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        result["error"] = (f"Служба RDAP вернула ошибку {exc.code}" if exc.code == 404
                           else "Домен не найден в службе RDAP")
        return result
    except (OSError, TimeoutError, json.JSONDecodeError) as exc:
        result["error"] = f"Не удалось получить данные о домене: {exc}"
        return result

    events = {event.get("eventAction", ""): event.get("eventDate", "") or ""
              for event in payload.get("events", []) if isinstance(event, dict)}
    registrar = ""
    for entity in payload.get("entities", []):
        if "registrar" not in entity.get("roles", []):
            continue
        vcards = entity.get("vcardArray")
        if isinstance(vcards, list) and len(vcards) > 1:
            for item in vcards[1]:
                if isinstance(item, list) and item and item[0] == "fn":
                    registrar = str(item[-1] or "").strip()
                    break
        if not registrar:
            registrar = str(entity.get("handle", "") or "").strip()
        if registrar:
            break
    result.update({
        "ok": True,
        "registrar": registrar,
        "created": str(events.get("registration", "") or "").strip(),
        "expires": str(events.get("expiration", "") or "").strip(),
        "status": list(payload.get("status", []) or []),
        "raw_excerpt": json.dumps(payload, ensure_ascii=False)[:1500],
        "error": "",
    })
    return result


# --------------------------------------------------------------------- hosts

def hosts_path() -> Path:
    """Path to the system hosts file (WINDIR-aware for tests)."""
    windir = os.environ.get("WINDIR", r"C:/Windows")
    return Path(windir) / "System32" / "drivers" / "etc" / "hosts"


def _parse_hosts_line(raw: str, kind: str) -> list[dict]:
    """Split one hosts-file line into entries, keeping commented ones."""
    text = raw.strip()
    if not text:
        return []
    commented = text.startswith("#")
    if kind == "builtin" and commented:
        return []
    body = text.lstrip("#").strip()
    parts = body.split()
    if len(parts) < 2:
        return []
    try:
        ipaddress.ip_address(parts[0])
    except ValueError:
        return []
    return [{
        "type": kind,
        "ip": parts[0],
        "host": host,
        "enabled": not commented,
        "raw": raw,
    } for host in parts[1:]]


def read_hosts(path: str | Path | None = None) -> list[dict]:
    """Parse the hosts file into builtin and Zentrix-managed entries."""
    target = Path(path) if path else hosts_path()
    entries: list[dict] = []
    try:
        content = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        log.warning("Не удалось прочитать hosts-файл %s: %s", target, exc)
        return entries
    in_group = False
    for raw in content.splitlines():
        stripped = raw.strip()
        group = _HOSTS_GROUP_RE.match(raw)
        if group:
            in_group = True
            continue
        end_marker = _HOSTS_END_RE.match(raw)
        if end_marker:
            in_group = False
            continue
        if not stripped:
            continue
        entries.extend(_parse_hosts_line(raw, "zentrix" if in_group else "builtin"))
    return entries


def hosts_group_bounds(lines: list[str], group_id: str) -> tuple[int, int]:
    """Locate the (start, end) of a Zentrix block; (-1, -1) when absent."""
    start = end = -1
    for index, line in enumerate(lines):
        group_match = _HOSTS_GROUP_RE.match(line)
        if start < 0 and group_match and group_match.group(1) == group_id:
            start = index
            continue
        end_match = _HOSTS_END_RE.match(line)
        if start >= 0 and end_match and end_match.group(1) == group_id:
            end = index
            break
    return start, end


def apply_hosts_group(group_id: str, group_title: str, entries: list[tuple[str, str]],
                      enabled: bool, remove: bool = False,
                      path: str | Path | None = None) -> dict:
    """Rewrite (or remove) one Zentrix hosts group atomically.

    All unrelated lines are preserved byte-for-byte; the file is written via
    a temporary file and ``os.replace``, mirroring settings_store.
    """
    target = Path(path) if path else hosts_path()
    group_id = str(group_id).strip()
    if not group_id:
        return {"ok": False, "error": "Не задан идентификатор группы hosts", "entries": 0}
    try:
        content = target.read_text(encoding="utf-8", errors="replace") if target.exists() else ""
    except OSError as exc:
        return {"ok": False, "error": f"Не удалось прочитать hosts-файл: {exc}", "entries": 0}

    lines = content.splitlines()
    start, end = hosts_group_bounds(lines, group_id)
    if start >= 0 and end < 0:
        return {"ok": False, "error": "Найден незакрытый блок Zentrix в hosts-файле", "entries": 0}

    record_count = 0
    new_block: list[str] = []
    if not remove and entries:
        new_block.append(f"# ZENTRIX-GROUP {group_id} {group_title}".rstrip())
        for ip_value, host in entries:
            ip_value, host = str(ip_value).strip(), str(host).strip()
            if not ip_value or not host:
                continue
            line = f"{ip_value}\t{host}"
            if not enabled:
                line = "# " + line
            new_block.append(line)
            record_count += 1
        new_block.append(f"# ZENTRIX-END {group_id}")

    if start >= 0:
        lines[start:end + 1] = new_block
    elif new_block:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(new_block)

    try:
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
        temporary = Path(str(target) + ".zentrix-tmp")
        temporary.write_text("\n".join(lines).rstrip("\n") + "\n", encoding="utf-8")
        os.replace(temporary, target)
    except OSError as exc:
        return {"ok": False, "error": f"Не удалось записать hosts-файл: {exc}", "entries": 0}
    log.info("Группа hosts %s обновлена: записей %s, включена=%s", group_id,
             record_count, enabled)
    return {"ok": True, "error": "", "entries": record_count}
