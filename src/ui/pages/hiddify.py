"""Hiddify tab (sing-box core, headless)."""

from __future__ import annotations

from .proxy_page import ProxyPage


class HiddifyPage(ProxyPage):
    key = "hiddify"
    icon_name = "shield"

    def __init__(self, context, parent=None) -> None:
        super().__init__(
            context,
            context.hiddify,
            "Hiddify",
            "Headless-интеграция hiddify-app 4.1.1 · ядро sing-box, без окон Hiddify",
            "Источник: hiddify-app-4.1.1 · ядро sing-box · mixed-прокси + Clash API",
            "sing-box",
            parent,
        )
        self.port_a_label.setText("Mixed")
        self.port_b_label.setText("API")
