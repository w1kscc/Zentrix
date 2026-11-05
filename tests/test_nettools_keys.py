"""Nettools pure helpers and free-keys parsing tests."""

from __future__ import annotations

import base64

from src import free_keys, game_mode, nettools


def test_dns_presets_shape():
    assert nettools.DNS_PRESETS["cloudflare"]["servers"] == ["1.1.1.1", "1.0.0.1"]
    assert nettools.DNS_PRESETS["dhcp"]["servers"] == []
    for preset in nettools.DNS_PRESETS.values():
        assert "label" in preset and "servers" in preset


def test_hosts_roundtrip(tmp_path):
    rows = [(True, "0.0.0.0", "ads.example.com"), (False, "127.0.0.1", "local.test")]
    target = tmp_path / "hosts"
    ok, _message = nettools.write_hosts(rows, path=target)
    assert ok
    parsed = nettools.read_hosts(path=target)
    assert parsed == rows


def test_anti_ad_merge():
    existing = [(True, "0.0.0.0", "ads.adfox.ru")]
    merged = nettools.anti_ad_rows(existing)
    hosts = [host for _enabled, _ip, host in merged]
    assert hosts[0] == "ads.adfox.ru"
    assert "googleads.g.doubleclick.net" in hosts
    assert len(hosts) == len(set(hosts))


def test_render_hosts_disables_with_marker():
    text = nettools.render_hosts([(False, "0.0.0.0", "x.test"), (True, "0.0.0.0", "y.test")])
    assert "## 0.0.0.0\tx.test" in text
    assert "0.0.0.0\ty.test" in text


def test_tcp_ping_localhost():
    import socket
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    latency = nettools.tcp_ping("127.0.0.1", port, timeout=1.0)
    assert latency is not None and latency >= 0
    server.close()
    assert nettools.tcp_ping("127.0.0.1", 1, timeout=0.2) is None


def test_parse_active_scheme():
    output = "GUID 381b4222-f694-41f0-9685-ff5bb260df2e  (Сбалансированный)"
    assert game_mode.parse_active_scheme(output) == "381b4222-f694-41f0-9685-ff5bb260df2e"
    assert game_mode.parse_active_scheme("no guid here") == ""


def test_decode_base64_subscription():
    payload = "\n".join([
        "vless://user@example.com:443?security=tls&sni=a.com#NodeA",
        "vmess://eyJ2IjoiMiIsImFkZCI6ImIuY29tIiwicG9ydCI6IjQ0MyJ9",
    ]).encode()
    encoded = base64.b64encode(payload)
    text = free_keys.decode_payload(encoded)
    links = free_keys.extract_links(text)
    assert len(links) == 2
    assert links[0].startswith("vless://")
    assert links[1].startswith("vmess://")


def test_extract_links_filters_and_deduplicates():
    text = """
    - vless://a@x.test:443#One
      trojan://bad@x.test:443#Skip
    vless://a@x.test:443#One
    http://not-a-node.test
    """
    links = free_keys.extract_links(text)
    assert links == ["vless://a@x.test:443#One"]


def test_parse_node_fields():
    node = free_keys.parse_node("vless://u@host.test:8443?x=1#Мой узел", 0, "repo")
    assert node.scheme == "vless"
    assert node.host == "host.test"
    assert node.port == 8443
    assert "BETA" in node.label


def test_summarize():
    assert "не найдено" in free_keys.summarize([]).lower()
    node = free_keys.FreeNode(scheme="vless", raw_link="vless://x", name="x", usable=True)
    assert "добавляйте вручную" in free_keys.summarize([node])
