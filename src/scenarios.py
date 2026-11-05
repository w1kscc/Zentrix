"""«Если → то» automation rules.

Rules are stored in settings under ``scenarios.rules`` as a list of dicts::

    {"id": "...", "enabled": True,
     "when": "youtube_blocked" | "vpn_lost" | "ip_changed",
     "then": "switch_strategy" | "enable_zapret" | "notify"}

Evaluation is pure: :func:`plan_actions` maps an event plus rule set to a list
of concrete actions, so it is fully unit-testable without Qt or network.
"""

from __future__ import annotations

from dataclasses import dataclass

WHEN_OPTIONS = (
    ("youtube_blocked", "если YouTube недоступен"),
    ("discord_blocked", "если Discord недоступен"),
    ("vpn_lost", "если VPN пропал"),
    ("ip_changed", "если сменился внешний IP"),
)

THEN_OPTIONS = (
    ("switch_strategy", "подобрать лучшую стратегию Zapret"),
    ("enable_zapret", "включить Zapret"),
    ("notify", "показать уведомление"),
)

KNOWN_WHEN = {value for value, _label in WHEN_OPTIONS}
KNOWN_THEN = {value for value, _label in THEN_OPTIONS}


@dataclass(frozen=True)
class Action:
    kind: str  # switch_strategy | enable_zapret | notify
    rule_id: str = ""
    message: str = ""


def normalize_rules(raw) -> list[dict]:
    """Sanitize stored rules: drop malformed ones, keep the field order."""
    result: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            continue
        when = str(item.get("when", "") or "")
        then = str(item.get("then", "") or "")
        if when not in KNOWN_WHEN or then not in KNOWN_THEN:
            continue
        result.append({
            "id": str(item.get("id", "") or ""),
            "enabled": bool(item.get("enabled", True)),
            "when": when,
            "then": then,
        })
    return result


def plan_actions(event: str, rules, *, zapret_running: bool = False,
                 strategy: str = "") -> list[Action]:
    """Map an event to the actions the runner should execute, in order."""
    actions: list[Action] = []
    for rule in normalize_rules(rules):
        if not rule["enabled"] or rule["when"] != event:
            continue
        then = rule["then"]
        if then == "enable_zapret" and zapret_running:
            continue
        if then == "switch_strategy" and not strategy and not zapret_running:
            # Nothing to restart and no strategy to pick — the engine is absent.
            actions.append(Action("notify", rule["id"],
                                  "Сценарий: стратегию не подобрать — Zapret не установлен"))
            continue
        actions.append(Action(then, rule["id"]))
    return actions


def blocked_event(results) -> str | None:
    """Return the scenario event for a blocked service, if any rule cares."""
    for item in results:
        if getattr(item, "id", "") == "youtube" and getattr(item, "status", "") == "blocked":
            return "youtube_blocked"
        if getattr(item, "id", "") == "discord" and getattr(item, "status", "") == "blocked":
            return "discord_blocked"
    return None


def event_label(event: str) -> str:
    return dict(WHEN_OPTIONS).get(event, event)


def then_label(then: str) -> str:
    return dict(THEN_OPTIONS).get(then, then)


def rule_summary(rule: dict) -> str:
    return f"{event_label(rule['when'])} → {then_label(rule['then'])}"
