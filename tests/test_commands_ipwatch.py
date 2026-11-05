"""Command palette and IP-watch logic tests."""

from __future__ import annotations

from src import commands, ipwatch


def test_all_commands_have_targets():
    for command in commands.all_commands():
        assert command.page or command.action or command.key.startswith("go:")


def test_filter_commands():
    everything = commands.all_commands()
    assert len(commands.filter_commands(everything, "")) == len(everything)
    zapret = commands.filter_commands(everything, "zapret")
    assert zapret and all("zapret" in f"{c.title} {c.hint}".casefold() for c in zapret)
    best = commands.filter_commands(everything, "лучшую стратегию")
    assert any(c.action == "best_strategy" for c in best)
    assert commands.filter_commands(everything, "zzzznope") == []


def test_change_message():
    message = ipwatch.change_message("1.2.3.4", "5.6.7.8")
    assert "1.2.3.4" in message and "5.6.7.8" in message
    assert message.startswith("IP изменился")


def test_describe():
    assert ipwatch.describe({"ip": "1.1.1.1"}) == "1.1.1.1"
    text = ipwatch.describe({"ip": "1.1.1.1", "city": "London", "country_name": "UK"})
    assert "1.1.1.1 (London, UK)" == text


def test_is_changed():
    assert not ipwatch.is_changed(None, {"ip": "1.1.1.1"})
    assert not ipwatch.is_changed({"ip": ""}, {"ip": "1.1.1.1"})
    assert ipwatch.is_changed({"ip": "1.1.1.1"}, {"ip": "2.2.2.2"})
    assert not ipwatch.is_changed({"ip": "1.1.1.1"}, {"ip": "1.1.1.1"})
