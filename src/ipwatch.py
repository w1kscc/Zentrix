"""External-IP watcher helpers for Zentrix.

Thin wrappers around :func:`src.net.external_ip_info` plus pure helpers to
detect and describe IP changes. Safe to import from worker threads; there are
no Qt imports here.
"""

from __future__ import annotations

from typing import Any

from .logger import get_logger
from .net import external_ip_info

log = get_logger("ipwatch")


def fetch_ip(timeout: float = 8.0, proxy_url: str | None = None) -> dict[str, str] | None:
    """Return the current external IP info dict, or None on any failure.

    Pass the local VPN proxy URL via ``proxy_url`` to query the tunneled
    address instead of the direct one.
    """
    try:
        info = external_ip_info(proxy_url=proxy_url, timeout=timeout)
    except Exception as exc:  # network errors must never crash the watcher
        log.warning("Не удалось получить внешний IP: %s", exc)
        return None
    return info if info.get("ip") else None


def _ip_of(value: dict[str, Any] | str | None) -> str:
    """Extract the IP string from a dict, a plain string, or None."""
    if isinstance(value, dict):
        return str(value.get("ip", "") or "").strip()
    if isinstance(value, str):
        return value.strip()
    return ""


def ip_changed(
    prev: dict[str, Any] | str | None,
    current: dict[str, Any] | str | None,
) -> bool:
    """True only when both values contain an IP and they differ.

    ``None`` and empty values mean "unknown" and never count as a change.
    """
    prev_ip = _ip_of(prev)
    current_ip = _ip_of(current)
    return bool(prev_ip) and bool(current_ip) and prev_ip != current_ip


def format_change(
    prev: dict[str, Any] | str | None,
    current: dict[str, Any] | str | None,
) -> str:
    """Return Russian notification text describing an IP change."""
    prev_ip = _ip_of(prev) or "неизвестен"
    current_ip = _ip_of(current) or "неизвестен"
    return f"IP изменился: был {prev_ip}, стал {current_ip}"
