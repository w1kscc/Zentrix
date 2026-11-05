"""External IP watch: detect changes and produce user-facing alerts."""

from __future__ import annotations

import threading
import time

from . import net
from .logger import get_logger
from .settings_store import settings

log = get_logger("ipwatch")

CHECK_INTERVAL = 600  # seconds between background probes


def describe(info: dict[str, str]) -> str:
    """Human-readable one-liner for an external_ip_info result."""
    ip_value = str(info.get("ip", "") or "?")
    country = str(info.get("country_name", "") or "").strip()
    city = str(info.get("city", "") or "").strip()
    place = ", ".join(part for part in (city, country) if part)
    return f"{ip_value} ({place})" if place else ip_value


def change_message(old: str, new: str) -> str:
    return f"IP изменился: был {old}, стал {new}"


def is_changed(previous: dict | None, current: dict) -> bool:
    if not previous or not str(previous.get("ip", "") or "").strip():
        return False
    return str(previous.get("ip", "")) != str(current.get("ip", ""))


def load_stored_ip() -> str:
    return str(settings.get("ipwatch.last_ip", "") or "")


def store_ip(info: dict) -> None:
    settings.set("ipwatch.last_ip", str(info.get("ip", "")))


def probe(proxy_url: str | None = None) -> dict[str, str]:
    """Blocking network probe — call from a worker thread."""
    return net.external_ip_info(proxy_url=proxy_url)


class IpWatcher:
    """Background poller; ``callback(kind, message)`` fires on changes/errors.

    ``kind`` is ``"changed"`` (with a toast-ready message), ``"error"`` or
    ``"same"``. Thread-safe: only one probe runs at a time.
    """

    def __init__(self, callback, interval: float = CHECK_INTERVAL) -> None:
        self._callback = callback
        self._interval = interval
        self._timer: threading.Timer | None = None
        self._busy = threading.Lock()
        self._stopped = threading.Event()

    def start(self) -> None:
        self._stopped.clear()
        self._schedule(1.0)

    def stop(self) -> None:
        self._stopped.set()
        if self._timer:
            self._timer.cancel()
            self._timer = None

    def _schedule(self, delay: float) -> None:
        if self._stopped.is_set():
            return
        self._timer = threading.Timer(delay, self._tick)
        self._timer.daemon = True
        self._timer.name = "ipwatch"
        self._timer.start()

    def _tick(self) -> None:
        if not self._busy.acquire(blocking=False):
            self._schedule(self._interval)
            return
        try:
            info = probe()
            old_ip = load_stored_ip()
            new_ip = str(info.get("ip", ""))
            if old_ip and old_ip != new_ip:
                self._callback("changed", change_message(old_ip, describe(info)))
            store_ip(info)
        except Exception as exc:
            log.debug("Проверка внешнего IP не удалась: %s", exc)
            self._callback("error", str(exc))
        finally:
            self._busy.release()
        self._schedule(self._interval)
