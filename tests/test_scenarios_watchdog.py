"""Scenario rules and Zapret watchdog decision tests."""

from __future__ import annotations

from src import scenarios, watchdog


def test_plan_actions_youtube_blocked():
    rules = [
        {"id": "1", "enabled": True, "when": "youtube_blocked", "then": "switch_strategy"},
        {"id": "2", "enabled": True, "when": "vpn_lost", "then": "enable_zapret"},
        {"id": "3", "enabled": False, "when": "youtube_blocked", "then": "notify"},
    ]
    actions = scenarios.plan_actions("youtube_blocked", rules, zapret_running=True)
    assert [action.kind for action in actions] == ["switch_strategy"]


def test_plan_actions_vpn_lost_enables_zapret_once():
    rules = [{"id": "1", "enabled": True, "when": "vpn_lost", "then": "enable_zapret"}]
    active = scenarios.plan_actions("vpn_lost", rules, zapret_running=True)
    idle = scenarios.plan_actions("vpn_lost", rules, zapret_running=False)
    assert active == []
    assert [action.kind for action in idle] == ["enable_zapret"]


def test_normalize_rules_drops_garbage():
    cleaned = scenarios.normalize_rules([
        {"id": "a", "enabled": True, "when": "youtube_blocked", "then": "notify"},
        {"when": "nonsense", "then": "notify"},
        {"when": "vpn_lost", "then": "hack_the_planet"},
        "string-rule",
        None,
    ])
    assert len(cleaned) == 1
    assert cleaned[0]["when"] == "youtube_blocked"


def test_blocked_event_detection():
    class Item:
        def __init__(self, id, status):
            self.id, self.status = id, status

    assert scenarios.blocked_event([Item("youtube", "blocked")]) == "youtube_blocked"
    assert scenarios.blocked_event([Item("discord", "blocked")]) == "discord_blocked"
    assert scenarios.blocked_event([Item("youtube", "ok")]) is None


def test_watchdog_budget():
    assert watchdog.should_restart(True, False, 0)
    assert watchdog.should_restart(True, False, 2)
    assert not watchdog.should_restart(True, False, 3)
    assert not watchdog.should_restart(True, True, 0)
    assert not watchdog.should_restart(False, False, 0)
    assert watchdog.attempts_left(1) == 2
