"""Share-link parsing and config generation tests."""

from __future__ import annotations

import base64
import json

import pytest

from src.engines import links


def _b64(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


def test_parse_vless_reality() -> None:
    link = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:443"
        "?type=tcp&security=reality&sni=cdn.example.com&fp=chrome"
        "&pbk=public-key&sid=abcd&flow=xtls-rprx-vision#My%20Node"
    )
    node = links.parse_link(link)

    assert node is not None
    assert node.protocol == "vless"
    assert node.server == "example.com"
    assert node.port == 443
    assert node.name == "My Node"
    assert node.security == "reality"
    assert node.public_key == "public-key"
    assert node.flow == "xtls-rprx-vision"


def test_parse_vmess_base64() -> None:
    payload = {
        "v": "2", "ps": "VMess Node", "add": "vm.example.com", "port": "8443",
        "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "aid": "0", "net": "ws",
        "host": "cdn.example.com", "path": "/ws", "tls": "tls",
    }
    link = "vmess://" + _b64(json.dumps(payload))
    node = links.parse_link(link)

    assert node is not None
    assert node.protocol == "vmess"
    assert node.name == "VMess Node"
    assert node.network == "ws"
    assert node.security == "tls"


def test_parse_trojan_and_shadowsocks() -> None:
    trojan = links.parse_link(
        "trojan://secret@trojan.example.com:443?type=ws&path=%2Ftj&sni=t.example.com#TJ"
    )
    assert trojan is not None
    assert (trojan.protocol, trojan.password, trojan.network) == ("trojan", "secret", "ws")

    userinfo = base64.urlsafe_b64encode(b"aes-256-gcm:pass:word").decode().rstrip("=")
    ss = links.parse_link(f"ss://{userinfo}@ss.example.com:8388#SS")
    assert ss is not None
    assert (ss.protocol, ss.method, ss.password) == ("ss", "aes-256-gcm", "pass:word")


def test_parse_subscription_and_json_profile() -> None:
    first = "vless://uuid@one.example.com:443?security=tls&sni=one.example.com#One"
    second = "trojan://pw@two.example.com:443#Two"
    subscription = _b64(first + "\n" + second)

    nodes = links.parse_links(subscription)
    assert [node.name for node in nodes] == ["One", "Two"]

    profile = json.dumps({
        "outbounds": [{
            "type": "vless", "tag": "profile", "server": "three.example.com",
            "server_port": 443, "uuid": "uuid-3",
        }]
    })
    nodes = links.parse_links(profile)
    assert len(nodes) == 1
    assert nodes[0].server == "three.example.com"


def test_xray_and_singbox_configs() -> None:
    node = links.parse_link("vless://uuid@example.com:443?security=tls#Node")
    assert node is not None

    xray = links.xray_config(node, socks_port=10808, http_port=10809)
    assert [inbound["port"] for inbound in xray["inbounds"]] == [10808, 10809]
    assert xray["outbounds"][0]["protocol"] == "vless"
    assert xray["outbounds"][0]["streamSettings"]["security"] == "tls"

    singbox = links.singbox_config(node, mixed_port=2080, api_port=9091)
    assert singbox["inbounds"][0]["listen_port"] == 2080
    assert singbox["outbounds"][0]["type"] == "vless"
    assert singbox["experimental"]["clash_api"]["external_controller"].endswith(":9091")


def test_invalid_links_are_ignored() -> None:
    assert links.parse_link("") is None
    assert links.parse_link("# comment") is None
    assert links.parse_link("ftp://example.com") is None
    assert links.parse_links("not a subscription") == []


def test_xhttp_link_generates_xray_xhttp_settings() -> None:
    link = (
        "vless://11111111-2222-3333-4444-555555555555@example.com:8000"
        "?type=xhttp&security=reality&sni=cdn.example.com&fp=firefox"
        "&pbk=public-key&sid=abcd&mode=stream-one&path=%2Fapi%2Fv1%2Fupdate#XHTTP"
    )
    node = links.parse_link(link)

    assert node is not None
    assert node.network == "xhttp"
    assert node.xhttp_mode == "stream-one"
    assert node.path == "/api/v1/update"

    xray = links.xray_config(node, socks_port=10808, http_port=10809)
    stream = xray["outbounds"][0]["streamSettings"]
    assert stream["network"] == "xhttp"
    assert stream["xhttpSettings"] == {
        "path": "/api/v1/update",
        "mode": "stream-one",
    }


def test_singbox_rejects_xhttp_with_clear_message() -> None:
    node = links.parse_link(
        "vless://11111111-2222-3333-4444-555555555555@example.com:8000"
        "?type=xhttp&security=reality&sni=cdn.example.com&mode=stream-one#XHTTP"
    )
    assert node is not None

    with pytest.raises(ValueError, match="XHTTP"):
        links.singbox_config(node, mixed_port=2080, api_port=9091)


def test_transport_label_and_summary() -> None:
    node = links.parse_link(
        "vless://uuid@example.com:8443?type=ws&security=tls&sni=example.com#WS"
    )
    assert node is not None
    assert node.transport_label == "WS/TLS"
    assert "WS/TLS" in node.summary()
