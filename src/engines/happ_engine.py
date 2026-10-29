"""Happ desktop integration: Xray core in headless mode."""

from __future__ import annotations

from ..settings_store import settings
from . import cores
from .proxy_engine import ProxyEngine


class HappEngine(ProxyEngine):
    core_kind = "xray"
    ns = "happ"
    key = "happ"
    title = "Happ"

    def ports(self) -> tuple[int, int]:
        return (
            int(settings.get("happ.socks_port", 10808) or 10808),
            int(settings.get("happ.http_port", 10809) or 10809),
        )

    def info(self) -> dict:
        return {
            "source": "happ-desktop-4.6.1",
            "core": "Xray-core",
            "core_version": cores.core_version("xray"),
            "mode": "headless",
            "proxy": self.public_proxy(),
        }
