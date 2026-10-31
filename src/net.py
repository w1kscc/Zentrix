"""Networking helpers: GitHub release discovery and streaming downloads."""

from __future__ import annotations

import json
import ipaddress
import os
import re
import shutil
import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

USER_AGENT = "Zentrix/1.0 (+https://github.com/w1kscc/Zentrix)"
ProgressCallback = Callable[[int, int], None]


@dataclass
class Asset:
    name: str
    url: str
    size: int = 0


@dataclass
class Release:
    repo: str
    tag: str
    name: str
    published_at: str = ""
    body: str = ""
    assets: list[Asset] = field(default_factory=list)
    html_url: str = ""

    @property
    def version(self) -> str:
        return normalize_version(self.tag)


def normalize_version(value: str) -> str:
    return value.strip().lstrip("vV") if value else value


def version_tuple(value: str) -> tuple[int, ...]:
    parts = re.findall(r"\d+", normalize_version(value))
    return tuple(int(part) for part in parts[:4]) or (0,)


def is_newer(candidate: str, current: str) -> bool:
    return version_tuple(candidate) > version_tuple(current)


def _request(url: str, *, timeout: float = 15.0) -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token and "api.github.com" in url:
        headers["Authorization"] = f"Bearer {token}"
    return urllib.request.Request(url, headers=headers)


def http_json(url: str, timeout: float = 15.0) -> dict:
    with urllib.request.urlopen(_request(url, timeout=timeout), timeout=timeout) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8", errors="replace"))


def github_latest(repo: str, timeout: float = 15.0) -> Release:
    data = http_json(f"https://api.github.com/repos/{repo}/releases/latest", timeout=timeout)
    assets = [
        Asset(
            name=item.get("name", ""),
            url=item.get("browser_download_url", ""),
            size=int(item.get("size", 0) or 0),
        )
        for item in data.get("assets", [])
    ]
    return Release(
        repo=repo,
        tag=data.get("tag_name", "") or "",
        name=data.get("name", "") or data.get("tag_name", ""),
        published_at=data.get("published_at", "") or "",
        body=(data.get("body", "") or "")[:4000],
        assets=assets,
        html_url=data.get("html_url", "") or "",
    )


def pick_asset(release: Release, keywords: list[str], *, exclude: list[str] | None = None) -> Asset | None:
    exclude = [word.lower() for word in (exclude or [])]
    lowered = [(asset, asset.name.lower()) for asset in release.assets]
    for keyword in keywords:
        needle = keyword.lower()
        for asset, name in lowered:
            if needle in name and not any(word in name for word in exclude):
                return asset
    return None


def download(url: str, destination: Path, progress: ProgressCallback | None = None,
             cancel: "Callable[[], bool] | None" = None, timeout: float = 30.0,
             attempts: int = 3) -> Path:
    """Download ``url`` to ``destination`` atomically, reporting progress.

    Transient TLS resets and timeouts are retried a few times; the partial file
    is removed between attempts so a truncated download is never installed.
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    last_error: Exception | None = None
    for attempt in range(1, max(1, attempts) + 1):
        try:
            with urllib.request.urlopen(_request(url, timeout=timeout), timeout=timeout) as response:
                total = int(response.headers.get("Content-Length", 0) or 0)
                done = 0
                with open(temporary, "wb") as handle:
                    while True:
                        if cancel and cancel():
                            raise InterruptedError("download cancelled")
                        chunk = response.read(262_144)
                        if not chunk:
                            break
                        handle.write(chunk)
                        done += len(chunk)
                        if progress:
                            progress(done, total)
            os.replace(temporary, destination)
            return destination
        except urllib.error.HTTPError:
            raise
        except InterruptedError:
            _remove_quietly(temporary)
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
            _remove_quietly(temporary)
            if attempt >= attempts:
                break
            time.sleep(min(6.0, 1.5 * attempt))
    assert last_error is not None
    raise last_error


def _remove_quietly(path: Path) -> None:
    try:
        path.unlink()
    except OSError:
        pass


def download_to(url: str, target_dir: Path, progress: ProgressCallback | None = None) -> Path:
    target_dir.mkdir(parents=True, exist_ok=True)
    name = url.split("?")[0].rsplit("/", 1)[-1] or "download.bin"
    return download(url, target_dir / name, progress)


def install_tree(source: Path, destination: Path) -> None:
    """Replace ``destination`` with ``source`` (both directories)."""
    if destination.exists():
        shutil.rmtree(destination, ignore_errors=True)
    shutil.copytree(source, destination)


def is_connected(timeout: float = 2.5) -> bool:
    try:
        with urllib.request.urlopen(_request("https://api.github.com", timeout=timeout), timeout=timeout):
            return True
    except urllib.error.HTTPError:
        return True  # reachable, just an auth/rate-limit response
    except Exception:
        return False


def external_ip_info(proxy_url: str | None = None, timeout: float = 8.0) -> dict[str, str]:
    """Return public IP and approximate GeoIP data from ipapi.co.

    The endpoint sees the client address, so callers may provide the local VPN
    proxy URL to query the tunneled address instead of the direct one.
    """
    request = urllib.request.Request(
        "https://ipapi.co/json/",
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        if proxy_url else urllib.request.ProxyHandler({})
    )
    with opener.open(request, timeout=timeout) as response:
        payload = json.loads(response.read(64 * 1024).decode("utf-8", errors="replace"))
    ip_value = str(payload.get("ip", "")).strip()
    if not ip_value:
        raise ValueError("Сервис GeoIP не вернул IP-адрес")
    return {
        "ip": ip_value,
        "city": str(payload.get("city", "") or "").strip(),
        "country_name": str(payload.get("country_name", "") or "").strip(),
        "country_code": str(payload.get("country_code", "") or "").strip(),
    }


def lan_ipv4_addresses() -> list[str]:
    """List private IPv4 addresses on active non-tunnel adapters."""
    try:
        import psutil
    except ImportError:
        return []
    addresses: list[str] = []
    for name, stats in psutil.net_if_stats().items():
        lowered = name.casefold()
        if not stats.isup or any(token in lowered for token in
                                 ("vpn", "tap", "tun", "wintun", "wireguard", "loopback",
                                  "virtual", "vethernet")):
            continue
        for address in psutil.net_if_addrs().get(name, []):
            if address.family != socket.AF_INET:
                continue
            try:
                ip = ipaddress.ip_address(address.address)
            except ValueError:
                continue
            if ip.is_private and not ip.is_loopback and not ip.is_link_local:
                value = str(ip)
                if value not in addresses:
                    addresses.append(value)
    return addresses
