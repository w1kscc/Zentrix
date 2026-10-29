"""Happ tab (Xray core, headless)."""

from __future__ import annotations

from .proxy_page import ProxyPage


class HappPage(ProxyPage):
    key = "happ"
    icon_name = "globe"

    def __init__(self, context, parent=None) -> None:
        super().__init__(
            context,
            context.happ,
            "Happ",
            "Headless-интеграция happ-desktop 4.6.1 · ядро Xray, без окон Happ",
            "Источник: happ-desktop-4.6.1 · ядро Xray-core · локальный SOCKS/HTTP",
            "Xray-core",
            parent,
        )
        self.port_a_label.setText("SOCKS")
        self.port_b_label.setText("HTTP")
