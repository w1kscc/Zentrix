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
            "Xray",
            "VPN через ядро Xray · совместимые узлы VLESS / VMess / Trojan / SS",
            "Источник: happ-desktop-4.6.1 · ядро Xray-core · локальный SOCKS/HTTP",
            "Xray-core",
            parent,
        )
        self.port_a_label.setText("SOCKS")
        self.port_b_label.setText("HTTP")
