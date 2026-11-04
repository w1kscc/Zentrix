"""Nettools pure helpers: output decoding, parsing and hosts-file management."""

from __future__ import annotations

from pathlib import Path

import pytest

from src import nettools


@pytest.fixture()
def hosts_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point WINDIR at a temp tree containing a realistic hosts file."""
    etc = tmp_path / "Windows" / "System32" / "drivers" / "etc"
    etc.mkdir(parents=True)
    monkeypatch.setenv("WINDIR", str(tmp_path / "Windows"))
    hosts = etc / "hosts"
    hosts.write_text(
        "# Copyright (c) 1993-2009 Microsoft Corp.\n"
        "# Пример несуществующей записи (комментарий)\n"
        "\n"
        "127.0.0.1\tlocalhost\n"
        "::1\tlocalhost\n",
        encoding="utf-8",
    )
    return hosts


# ------------------------------------------------------------------ decoding

def test_decode_output_prefers_cp866_for_cyrillic() -> None:
    raw = "Обмен пакетами с 1.1.1.1 по 32 байтам".encode("cp866")

    decoded = nettools._decode_output(raw)

    assert "Обмен пакетами" in decoded
    assert "\ufffd" not in decoded


def test_decode_output_keeps_utf8() -> None:
    assert nettools._decode_output("Среднее = 25мс".encode("utf-8")).endswith("25мс")


# ------------------------------------------------------------------ parsing

def test_ping_time_extraction_russian_and_english() -> None:
    russian = "Ответ от 93.184.216.34: число байт=32 время=25мс TTL=55"
    english = "Reply from 93.184.216.34: bytes=32 time=25ms TTL=55"

    assert [int(v) for v in nettools._PING_TIME_RE.findall(russian + "\n" + english)] == [25, 25]


def test_ping_summary_regexes() -> None:
    russian = "Пакетов: отправлено = 4, получено = 4, потеряно = 0 (0% потерь)"
    english = "Packets: Sent = 4, Received = 3, Lost = 1 (25% loss)"

    assert nettools._PING_SENT_RE.search(russian).group(1) == "4"
    assert nettools._PING_RECEIVED_RE.search(russian).group(1) == "4"
    assert nettools._PING_SENT_RE.search(english).group(1) == "4"
    assert nettools._PING_RECEIVED_RE.search(english).group(1) == "3"


def test_parse_tracert_output() -> None:
    output = (
        "Трассировка маршрута к example.com [93.184.216.34]\n"
        "с максимальным числом прыжков 30:\n"
        "\n"
        "  1    <1 мс   <1 мс   <1 мс  192.168.1.1\n"
        "  2     9 мс     8 мс    10 мс  10.20.30.40\n"
        "  3     *        *        *     Превышен интервал ожидания для запроса.\n"
        "  4    42 мс    41 мс    40 мс  93.184.216.34\n"
    )

    hops = nettools._parse_tracert_output(output)

    assert hops == [
        {"hop": 1, "ip": "192.168.1.1", "ms": [1, 1, 1]},
        {"hop": 2, "ip": "10.20.30.40", "ms": [9, 8, 10]},
        {"hop": 3, "ip": "", "ms": None},
        {"hop": 4, "ip": "93.184.216.34", "ms": [42, 41, 40]},
    ]


def test_dns_presets_documented_keys() -> None:
    assert set(nettools.DNS_PRESETS) == {"auto", "cloudflare", "google", "adguard", "family"}
    assert nettools.DNS_PRESETS["family"] == ("1.1.1.3", "1.0.0.3")


# --------------------------------------------------------------------- hosts

def test_hosts_path_uses_windir(hosts_file: Path) -> None:
    assert nettools.hosts_path() == hosts_file


def test_read_hosts_builtin_entries(hosts_file: Path) -> None:
    entries = nettools.read_hosts()

    assert len(entries) == 2
    assert {entry["host"] for entry in entries} == {"localhost"}
    assert all(entry["type"] == "builtin" for entry in entries)
    assert all(entry["enabled"] for entry in entries)
    assert any(entry["ip"] == "::1" for entry in entries)


def test_hosts_group_roundtrip(hosts_file: Path) -> None:
    original = hosts_file.read_text(encoding="utf-8")

    applied = nettools.apply_hosts_group(
        "media", "Пример для медиа",
        [("1.2.3.4", "example.com"), ("5.6.7.8", "cdn.example.net")],
        enabled=True,
    )

    assert applied == {"ok": True, "error": "", "entries": 2}
    entries = [item for item in nettools.read_hosts() if item["type"] == "zentrix"]
    assert sorted((item["ip"], item["host"]) for item in entries) == [
        ("1.2.3.4", "example.com"),
        ("5.6.7.8", "cdn.example.net"),
    ]
    assert all(item["enabled"] for item in entries)

    # Бuiltin-блок затронут не был
    assert "127.0.0.1\tlocalhost" in hosts_file.read_text(encoding="utf-8")
    assert "# ZENTRIX-GROUP media" in hosts_file.read_text(encoding="utf-8")
    assert "# ZENTRIX-GROUP media Пример для медиа" in hosts_file.read_text(encoding="utf-8")
    assert original.splitlines()[0] == hosts_file.read_text(encoding="utf-8").splitlines()[0]


def test_hosts_group_replacement_updates_entries(hosts_file: Path) -> None:
    nettools.apply_hosts_group("media", "Медиа", [("1.1.1.1", "a.example")], enabled=True)
    nettools.apply_hosts_group(
        "media", "Медиа", [("2.2.2.2", "b.example"), ("3.3.3.3", "c.example")],
        enabled=False,
    )
    content = hosts_file.read_text(encoding="utf-8")

    # Блок одна штука, записи закомментированы
    assert content.count("# ZENTRIX-GROUP media") == 1
    assert content.count("# ZENTRIX-END media") == 1
    entries = [item for item in nettools.read_hosts() if item["type"] == "zentrix"]
    assert len(entries) == 2
    assert all(not item["enabled"] for item in entries)
    assert content.count("2.2.2.2") == 1
    assert "1.1.1.1" not in content


def test_hosts_remove_restores_original(hosts_file: Path) -> None:
    original = hosts_file.read_text(encoding="utf-8")

    nettools.apply_hosts_group("block", "Блокировка", [(nettools.HOSTS_HOST, "ads.example")],
                               enabled=True)
    assert "# ZENTRIX-GROUP block" in hosts_file.read_text(encoding="utf-8")

    removed = nettools.apply_hosts_group("block", "Блокировка", [], enabled=True, remove=True)

    assert removed["ok"] is True
    assert removed["entries"] == 0
    assert "ZENTRIX" not in hosts_file.read_text(encoding="utf-8")
    assert hosts_file.read_text(encoding="utf-8") == original


def test_hosts_missing_group_id_rejected() -> None:
    result = nettools.apply_hosts_group("", "x", [("1.1.1.1", "a.example")], enabled=True)

    assert result["ok"] is False
    assert result["error"]


def test_hosts_unterminated_block_reported(tmp_path: Path) -> None:
    target = tmp_path / "hosts"
    target.write_text(
        "127.0.0.1\tlocalhost\n# ZENTRIX-GROUP lonely\n1.1.1.1\ta.example\n",
        encoding="utf-8",
    )

    result = nettools.apply_hosts_group("lonely", "x", [("2.2.2.2", "b.example")],
                                        enabled=True, path=target)

    assert result["ok"] is False
    assert "незакрыт" in result["error"]
