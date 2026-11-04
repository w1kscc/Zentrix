"""Rules engine and IP watcher: JSON roundtrip, evaluation and change helpers."""

from __future__ import annotations

from src.ipwatch import fetch_ip, format_change, ip_changed
from src.rules import (
    ACTION_LABELS,
    CONDITION_LABELS,
    Rule,
    evaluate,
    filter_rules,
    rules_from_json,
    rules_to_json,
    validate,
)

# --- rules: JSON roundtrip -------------------------------------------------


def test_rules_json_roundtrip() -> None:
    rules = [
        Rule(
            id="r1",
            title="YouTube сломался",
            condition="service_blocked",
            action="notify",
            value="YouTube недоступен",
            enabled=True,
        ),
        Rule(
            id="r2",
            title="Перезапуск Zapret",
            condition="zapret_down",
            action="start_zapret",
            enabled=False,
        ),
    ]
    data = rules_to_json(rules)
    assert isinstance(data, list) and len(data) == 2

    restored = rules_from_json(data)
    assert restored == rules


def test_rules_from_json_skips_unknown_condition_and_action() -> None:
    data = [
        {"condition": "moon_phase", "action": "notify", "title": "bad condition"},
        {"condition": "vpn_down", "action": "halo_jump", "title": "bad action"},
        {"condition": "vpn_down", "action": "notify", "title": "good", "value": "упс"},
        "not-a-dict",
    ]
    restored = rules_from_json(data)
    assert [rule.title for rule in restored] == ["good"]
    assert restored[0].condition == "vpn_down"
    assert restored[0].value == "упс"
    # A broken payload must not raise at all.
    assert rules_from_json(None) == []


def test_condition_and_action_labels_are_russian() -> None:
    assert CONDITION_LABELS["service_blocked"] == "Сервис заблокирован"
    assert CONDITION_LABELS["service_ok"] == "Сервис доступен"
    assert CONDITION_LABELS["vpn_down"] == "VPN не работает"
    assert CONDITION_LABELS["vpn_up"] == "VPN подключён"
    assert CONDITION_LABELS["zapret_down"] == "Zapret остановлен"
    assert ACTION_LABELS["notify"] == "Показать уведомление"
    assert ACTION_LABELS["set_strategy"] == "Сменить стратегию Zapret"
    assert ACTION_LABELS["start_zapret"] == "Включить Zapret"
    assert ACTION_LABELS["stop_zapret"] == "Остановить Zapret"


# --- rules: evaluate / filter ----------------------------------------------


def test_evaluate_service_conditions_match_by_service_id() -> None:
    state = {"service_status": {"youtube": "blocked", "discord": "ok"}}

    assert evaluate(
        Rule(condition="service_blocked", value="youtube"), state
    ) is True
    assert evaluate(
        Rule(condition="service_ok", value="discord"), state
    ) is True
    # Unknown or not-probed service ids never match.
    assert evaluate(
        Rule(condition="service_blocked", value="spotify"), state
    ) is False
    assert evaluate(
        Rule(condition="service_ok", value="youtube"), state
    ) is False
    assert evaluate(
        Rule(condition="service_blocked", value="unknown"), state
    ) is False


def test_evaluate_status_conditions() -> None:
    running = {"zapret_status": "running", "proxy_status": "running"}
    stopped = {"zapret_status": "stopped", "proxy_status": "stopped"}

    assert evaluate(Rule(condition="vpn_up"), running) is True
    assert evaluate(Rule(condition="vpn_down"), running) is False
    assert evaluate(Rule(condition="vpn_down"), stopped) is True
    assert evaluate(Rule(condition="vpn_up"), stopped) is False
    assert evaluate(Rule(condition="zapret_down"), running) is False
    assert evaluate(Rule(condition="zapret_down"), stopped) is True


def test_filter_rules_returns_only_matching_enabled() -> None:
    state = {"service_status": {"youtube": "blocked"}, "proxy_status": "stopped"}
    rules = [
        Rule(id="a", condition="service_blocked", value="youtube"),
        Rule(id="b", condition="service_blocked", value="youtube", enabled=False),
        Rule(id="c", condition="vpn_down"),
        Rule(id="d", condition="service_ok", value="youtube"),
    ]
    matched = filter_rules(rules, state)
    assert [rule.id for rule in matched] == ["a", "c"]


def test_validate_reports_missing_values_in_russian() -> None:
    assert validate(Rule(condition="service_blocked", value="")) == (
        "Для условия по сервису выберите сервис"
    )
    assert validate(Rule(action="set_strategy", condition="vpn_down", value="")) == (
        "Выберите стратегию Zapret"
    )
    assert validate(
        Rule(condition="vpn_down", action="notify", value="youtube упал")
    ) is None

# --- ipwatch ----------------------------------------------------------------


def test_ip_changed_edge_cases() -> None:
    assert ip_changed(None, None) is False
    assert ip_changed(None, "5.6.7.8") is False
    assert ip_changed("1.2.3.4", None) is False
    assert ip_changed("", "5.6.7.8") is False
    assert ip_changed("1.2.3.4", "1.2.3.4") is False
    assert ip_changed(
        {"ip": "1.2.3.4"}, {"ip": "1.2.3.4", "city": "Москва"}
    ) is False
    assert ip_changed("1.2.3.4", "5.6.7.8") is True
    assert ip_changed(
        {"ip": "1.2.3.4"}, {"ip": "5.6.7.8"}
    ) is True


def test_format_change_russian_text() -> None:
    assert format_change("1.2.3.4", "5.6.7.8") == (
        "IP изменился: был 1.2.3.4, стал 5.6.7.8"
    )
    assert format_change({"ip": "1.2.3.4"}, {"ip": "5.6.7.8"}) == (
        "IP изменился: был 1.2.3.4, стал 5.6.7.8"
    )
    assert format_change(None, "5.6.7.8") == (
        "IP изменился: был неизвестен, стал 5.6.7.8"
    )
    assert format_change("1.2.3.4", None) == (
        "IP изменился: был 1.2.3.4, стал неизвестен"
    )


def test_fetch_ip_returns_none_on_network_failure() -> None:
    # Offline / invalid endpoint must degrade to None, never raise.
    assert fetch_ip(timeout=0.05, proxy_url="http://127.0.0.1:1") is None
