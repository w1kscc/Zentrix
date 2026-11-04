"""User-defined "if → then" scenario engine for Zentrix.

Rules are user-facing automation entries: when a ``condition`` matches the
application state (see :func:`evaluate`), the ``action`` should be executed by
the caller. Both maps are JSON-serializable so a rules file can be stored next
to the settings file.

Condition ``service_blocked`` / ``service_ok`` require ``rule.value`` to hold a
service id from :data:`src.constants.SERVICES` (e.g. ``"youtube"``,
``"discord"``). Action ``notify`` stores the message text in ``value`` and
``set_strategy`` stores a zapret strategy ``.bat`` name.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .constants import SERVICES
from .logger import get_logger

log = get_logger("rules")

CONDITION_LABELS = {
    "service_blocked": "Сервис заблокирован",
    "service_ok": "Сервис доступен",
    "vpn_down": "VPN не работает",
    "vpn_up": "VPN подключён",
    "zapret_down": "Zapret остановлен",
}

ACTION_LABELS = {
    "notify": "Показать уведомление",
    "set_strategy": "Сменить стратегию Zapret",
    "start_zapret": "Включить Zapret",
    "stop_zapret": "Остановить Zapret",
}

SERVICE_IDS = [str(entry.get("id", "")) for entry in SERVICES if entry.get("id")]


@dataclass
class Rule:
    """A single "если → то" automation entry."""

    id: str = ""
    title: str = ""
    condition: str = ""
    action: str = ""
    value: str = ""
    enabled: bool = True


def rules_to_json(rules: list[Rule]) -> list[dict[str, Any]]:
    """Serialize rules to plain JSON-friendly dictionaries."""
    return [asdict(rule) for rule in rules]


def rules_from_json(data: Any) -> list[Rule]:
    """Restore rules from JSON dictionaries, skipping malformed entries.

    Unknown conditions or actions are tolerated and dropped so a hand-edited
    rules file can never block the app from loading.
    """
    if not isinstance(data, list):
        return []
    restored: list[Rule] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        condition = str(entry.get("condition", ""))
        action = str(entry.get("action", ""))
        if condition not in CONDITION_LABELS:
            log.warning("Пропущено правило с неизвестным условием: %r", condition)
            continue
        if action not in ACTION_LABELS:
            log.warning("Пропущено правило с неизвестным действием: %r", action)
            continue
        restored.append(Rule(
            id=str(entry.get("id", "")),
            title=str(entry.get("title", "")),
            condition=condition,
            action=action,
            value=str(entry.get("value", "")),
            enabled=bool(entry.get("enabled", True)),
        ))
    return restored


def evaluate(rule: Rule, state: dict[str, Any]) -> bool:
    """Return True when ``rule.condition`` matches the given state.

    Expected state schema::

        {
            "service_status": {service_id: status, ...},
            "zapret_status": "running|stopped|...",
            "proxy_status": "running|stopped|...",
        }
    """
    condition = rule.condition
    if condition in ("service_blocked", "service_ok"):
        wanted = "blocked" if condition == "service_blocked" else "ok"
        services = state.get("service_status") or {}
        if not isinstance(services, dict) or rule.value not in services:
            return False
        return str(services.get(rule.value, "")).lower() == wanted
    if condition == "vpn_down":
        return str(state.get("proxy_status", "")) != "running"
    if condition == "vpn_up":
        return str(state.get("proxy_status", "")) == "running"
    if condition == "zapret_down":
        return str(state.get("zapret_status", "")) != "running"
    log.warning("Неизвестное условие правила: %r", condition)
    return False


def filter_rules(rules: list[Rule], state: dict[str, Any]) -> list[Rule]:
    """Return enabled rules whose condition currently matches ``state``."""
    return [rule for rule in rules if rule.enabled and evaluate(rule, state)]


def validate(rule: Rule) -> str | None:
    """Return a human-readable Russian error message, or None when valid."""
    if rule.condition in ("service_blocked", "service_ok") and not rule.value:
        return "Для условия по сервису выберите сервис"
    if rule.action == "set_strategy" and not rule.value:
        return "Выберите стратегию Zapret"
    return None
