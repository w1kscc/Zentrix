"""Hiddify app integration: sing-box core in headless mode."""

from __future__ import annotations

from ..settings_store import settings
from . import cores
from .proxy_engine import ProxyEngine


class HiddifyEngine(ProxyEngine):
    core_kind = "singbox"
    ns = "hiddify"
    key = "hiddify"
    title = "Hiddify"

    def ports(self) -> tuple[int, int]:
        return (
            int(settings.get("hiddify.mixed_port", 2080) or 2080),
            int(settings.get("hiddify.api_port", 9091) or 9091),
        )

    def info(self) -> dict:
        return {
            "source": "hiddify-app-4.1.1",
            "core": "sing-box",
            "core_version": cores.core_version("singbox"),
            "mode": "headless",
            "proxy": self.public_proxy(),
        }
