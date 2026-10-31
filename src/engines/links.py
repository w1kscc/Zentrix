"""Share-link parsing and config generation for the headless proxy cores.

Supports vless / vmess / trojan / shadowsocks links, sing-box and Xray JSON
output. Subscription URLs are decoded transparently (base64 or plain list).
"""

from __future__ import annotations

import base64
import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import unquote, urlsplit


def _b64(value: str) -> str:
    value = value.strip().replace("-", "+").replace("_", "/")
    padding = "=" * (-len(value) % 4)
    try:
        return base64.b64decode(value + padding).decode("utf-8", errors="replace")
    except Exception:
        return ""


@dataclass
class ProxyNode:
    protocol: str
    name: str
    server: str
    port: int
    uuid: str = ""
    password: str = ""
    method: str = ""
    network: str = "tcp"
    security: str = "none"
    sni: str = ""
    host: str = ""
    path: str = ""
    service_name: str = ""
    flow: str = ""
    fingerprint: str = ""
    public_key: str = ""
    short_id: str = ""
    spider_x: str = ""
    xhttp_mode: str = ""
    alter_id: int = 0
    alpn: list[str] = field(default_factory=list)
    allow_insecure: bool = False
    raw_link: str = ""

    @property
    def label(self) -> str:
        return self.name or f"{self.server}:{self.port}"

    @property
    def transport_label(self) -> str:
        network = (self.network or "tcp").upper()
        security = (self.security or "none").upper()
        if security in {"", "NONE"}:
            return network
        return f"{network}/{security}"

    def summary(self) -> str:
        return f"{self.protocol.upper()} · {self.server}:{self.port} · {self.transport_label}"

    # -------------------------------------------------------------- xray
    def to_xray_outbound(self) -> dict[str, Any]:
        stream = self._xray_stream()
        if self.protocol == "vless":
            user: dict[str, Any] = {"id": self.uuid, "encryption": "none"}
            if self.flow:
                user["flow"] = self.flow
            outbound = {
                "protocol": "vless",
                "settings": {"vnext": [{"address": self.server, "port": self.port, "users": [user]}]},
            }
        elif self.protocol == "vmess":
            outbound = {
                "protocol": "vmess",
                "settings": {
                    "vnext": [{
                        "address": self.server,
                        "port": self.port,
                        "users": [{"id": self.uuid, "alterId": self.alter_id, "security": "auto"}],
                    }]
                },
            }
        elif self.protocol == "trojan":
            outbound = {
                "protocol": "trojan",
                "settings": {"servers": [{"address": self.server, "port": self.port,
                                          "password": self.password}]},
            }
        elif self.protocol == "ss":
            outbound = {
                "protocol": "shadowsocks",
                "settings": {"servers": [{"address": self.server, "port": self.port,
                                          "method": self.method, "password": self.password}]},
            }
        elif self.protocol in {"socks", "http"}:
            outbound = {
                "protocol": self.protocol,
                "settings": {"servers": [{
                    "address": self.server,
                    "port": self.port,
                    "users": ([{"user": self.uuid, "pass": self.password}]
                              if self.password else []),
                }]},
            }
        else:
            raise ValueError(f"Неподдерживаемый протокол: {self.protocol}")
        outbound["tag"] = "proxy"
        if stream:
            outbound["streamSettings"] = stream
        return outbound

    def _xray_stream(self) -> dict[str, Any]:
        if self.protocol == "ss":
            return {}
        stream: dict[str, Any] = {"network": self.network or "tcp"}
        security = self.security
        if security in {"tls", "reality", "xtls"}:
            stream["security"] = "reality" if security == "reality" else "tls"
            tls: dict[str, Any] = {
                "serverName": self.sni or self.host or self.server,
                "allowInsecure": self.allow_insecure,
            }
            if self.fingerprint:
                tls["fingerprint"] = self.fingerprint
            if self.alpn:
                tls["alpn"] = self.alpn
            if security == "reality":
                tls.pop("fingerprint", None)
                stream["realitySettings"] = {
                    "serverName": self.sni or self.server,
                    "publicKey": self.public_key,
                    "shortId": self.short_id,
                    "fingerprint": self.fingerprint or "chrome",
                    "spiderX": self.spider_x or "/",
                }
            else:
                stream["tlsSettings"] = tls
        else:
            stream["security"] = "none"
        if self.network == "ws":
            stream["wsSettings"] = {
                "path": self.path or "/",
                "headers": {"Host": self.host or self.sni or self.server},
            }
        elif self.network == "grpc":
            stream["grpcSettings"] = {"serviceName": self.service_name or self.path or ""}
        elif self.network in {"xhttp", "splithttp"}:
            stream["network"] = "xhttp"
            xhttp: dict[str, Any] = {"path": self.path or "/"}
            if self.xhttp_mode:
                xhttp["mode"] = self.xhttp_mode
            if self.host:
                xhttp["host"] = self.host
            stream["xhttpSettings"] = xhttp
        elif self.network in {"http", "h2"}:
            stream["network"] = "http"
            stream["httpSettings"] = {
                "path": self.path or "/",
                "host": [self.host] if self.host else [],
            }
        elif self.network == "tcp" and self.host:
            stream["tcpSettings"] = {
                "header": {"type": "http", "request": {"headers": {"Host": [self.host]}}}
            }
        return stream

    # ----------------------------------------------------------- sing-box
    def to_singbox_outbound(self) -> dict[str, Any]:
        outbound: dict[str, Any] = {"tag": "proxy", "server": self.server, "server_port": int(self.port)}
        if self.protocol == "vless":
            outbound.update({"type": "vless", "uuid": self.uuid})
            if self.flow:
                outbound["flow"] = self.flow
        elif self.protocol == "vmess":
            outbound.update({"type": "vmess", "uuid": self.uuid, "security": "auto",
                             "alter_id": int(self.alter_id)})
        elif self.protocol == "trojan":
            outbound.update({"type": "trojan", "password": self.password})
        elif self.protocol == "ss":
            outbound.update({"type": "shadowsocks", "method": self.method, "password": self.password})
        elif self.protocol in {"socks", "http"}:
            outbound.update({"type": self.protocol, "version": "5"})
            if self.password:
                outbound.update({"username": self.uuid, "password": self.password})
        else:
            raise ValueError(f"Неподдерживаемый протокол: {self.protocol}")

        if self.security in {"tls", "reality", "xtls"}:
            tls: dict[str, Any] = {
                "enabled": True,
                "server_name": self.sni or self.host or self.server,
                "insecure": self.allow_insecure,
            }
            if self.alpn:
                tls["alpn"] = self.alpn
            if self.fingerprint:
                tls["utls"] = {"enabled": True, "fingerprint": self.fingerprint}
            if self.security == "reality":
                tls["reality"] = {"enabled": True, "public_key": self.public_key,
                                  "short_id": self.short_id}
            outbound["tls"] = tls

        if self.network in {"xhttp", "splithttp"}:
            raise ValueError(
                "XHTTP-узлы не поддерживаются sing-box. Выберите Happ (Xray) "
                "или узел WS/TCP."
            )
        if self.network == "ws":
            outbound["transport"] = {
                "type": "ws",
                "path": self.path or "/",
                "headers": {"Host": self.host or self.sni or self.server},
            }
        elif self.network == "grpc":
            outbound["transport"] = {"type": "grpc",
                                     "service_name": self.service_name or self.path or ""}
        elif self.network in {"http", "h2"}:
            outbound["transport"] = {
                "type": "http",
                "path": self.path or "/",
                "host": [self.host] if self.host else [],
            }
        return outbound

    def to_dict(self) -> dict[str, Any]:
        return {
            "protocol": self.protocol, "name": self.name, "server": self.server,
            "port": self.port, "network": self.network, "security": self.security,
            "sni": self.sni, "summary": self.summary(),
        }


def _split_host_port(value: str, default_port: int = 443) -> tuple[str, int]:
    value = value.strip()
    if value.startswith("["):  # IPv6
        host, _, rest = value.partition("]")
        host = host.lstrip("[")
        port = int(rest.lstrip(":") or default_port)
        return host, port
    if ":" in value:
        host, _, port_text = value.rpartition(":")
        try:
            return host, int(port_text)
        except ValueError:
            return value, default_port
    return value, default_port


def _query_dict(query: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for part in query.split("&"):
        if not part:
            continue
        key, _, value = part.partition("=")
        result[unquote(key).lower()] = unquote(value)
    return result


def parse_link(link: str) -> ProxyNode | None:
    link = link.strip()
    if not link or link.startswith("#"):
        return None
    try:
        scheme = link.split("://", 1)[0].lower()
        if scheme not in {"vless", "vmess", "trojan", "ss", "socks", "http"}:
            return None
        parts = urlsplit(link)
        name = unquote(parts.fragment or "")
        query = _query_dict(parts.query)

        if scheme == "vmess":
            payload = _b64(link.split("://", 1)[1].split("#", 1)[0])
            data = json.loads(payload)
            node = ProxyNode(
                protocol="vmess",
                name=name or data.get("ps", ""),
                server=str(data.get("add", "")),
                port=int(data.get("port", 443) or 443),
                uuid=str(data.get("id", "")),
                alter_id=int(data.get("aid", 0) or 0),
                network=str(data.get("net", "tcp") or "tcp"),
                security="tls" if str(data.get("tls", "")) == "tls" else "none",
                sni=str(data.get("sni", "") or data.get("host", "")),
                host=str(data.get("host", "")),
                path=str(data.get("path", "")),
                xhttp_mode=str(data.get("mode", "")),
                fingerprint=str(data.get("fp", "")),
                alpn=[item for item in str(data.get("alpn", "")).split(",") if item],
            )
            return node

        host, port = _split_host_port(parts.netloc.rsplit("@", 1)[-1], 443 if scheme != "http" else 80)

        if scheme == "vless":
            node = ProxyNode(
                protocol="vless",
                name=name,
                server=host,
                port=port,
                uuid=unquote(parts.username or ""),
                network=query.get("type", "tcp"),
                security=query.get("security", "none"),
                sni=query.get("sni", ""),
                host=query.get("host", ""),
                path=query.get("path", ""),
                service_name=query.get("servicename", ""),
                flow=query.get("flow", ""),
                fingerprint=query.get("fp", ""),
                public_key=query.get("pbk", ""),
                short_id=query.get("sid", ""),
                spider_x=query.get("spx", ""),
                xhttp_mode=query.get("mode", ""),
                alpn=[item for item in query.get("alpn", "").split(",") if item],
                allow_insecure=query.get("allowinsecure", "0") in {"1", "true"},
            )
        elif scheme == "trojan":
            node = ProxyNode(
                protocol="trojan",
                name=name,
                server=host,
                port=port,
                password=unquote(parts.username or ""),
                network=query.get("type", "tcp"),
                security="tls" if query.get("security", "tls") != "none" else "none",
                sni=query.get("sni", ""),
                host=query.get("host", ""),
                path=query.get("path", ""),
                service_name=query.get("servicename", ""),
                fingerprint=query.get("fp", ""),
                xhttp_mode=query.get("mode", ""),
                alpn=[item for item in query.get("alpn", "").split(",") if item],
                allow_insecure=query.get("allowinsecure", "0") in {"1", "true"},
            )
        elif scheme == "ss":
            node = _parse_ss(link, name)
            if node is None:
                return None
        else:  # socks / http
            username = unquote(parts.username or "")
            password = unquote(parts.password or "")
            node = ProxyNode(
                protocol=scheme,
                name=name,
                server=host,
                port=port,
                uuid=username,
                password=password,
            )
        if not node.server or not node.port:
            return None
        return node
    except Exception:
        return None


def _parse_ss(link: str, name: str) -> ProxyNode | None:
    body = link.split("://", 1)[1]
    body, _, fragment = body.partition("#")
    name = name or unquote(fragment)
    body = body.split("?", 1)[0]
    if "@" in body:
        userinfo, hostpart = body.rsplit("@", 1)
        decoded = _b64(unquote(userinfo))
        if not decoded or ":" not in decoded:
            decoded = unquote(userinfo)
        host, port = _split_host_port(hostpart)
    else:
        decoded_full = _b64(unquote(body))
        if not decoded_full or "@" not in decoded_full:
            return None
        userinfo, hostport = decoded_full.rsplit("@", 1)
        decoded = userinfo
        host, port = _split_host_port(hostport)
    method, _, password = decoded.partition(":")
    return ProxyNode(
        protocol="ss",
        name=name,
        server=host,
        port=port,
        method=method,
        password=password,
        security="none",
    )


def parse_links(text: str) -> list[ProxyNode]:
    """Parse plain links, a base64 subscription body or a full JSON profile."""
    text = (text or "").strip()
    if not text:
        return []
    if text.startswith("{"):
        return _parse_json_profile(text)
    if "://" not in text:
        decoded = _b64(text)
        if decoded:
            text = decoded
    nodes: list[ProxyNode] = []
    for line in re.split(r"[\r\n]+", text):
        node = parse_link(line)
        if node:
            node.raw_link = line.strip()
            nodes.append(node)
    return nodes


def _parse_json_profile(text: str) -> list[ProxyNode]:
    """Extract a single server from an Xray/sing-box JSON profile (best effort)."""
    try:
        data = json.loads(text)
    except Exception:
        return []
    nodes: list[ProxyNode] = []
    for outbound in data.get("outbounds", []) or []:
        try:
            protocol = outbound.get("type") or outbound.get("protocol")
            if protocol not in {"vless", "vmess", "trojan", "shadowsocks", "socks", "http"}:
                continue
            server = outbound.get("server") or ""
            port = int(outbound.get("server_port") or 0)
            if not server:
                settings = outbound.get("settings", {})
                if settings.get("vnext"):
                    server = settings["vnext"][0]["address"]
                    port = settings["vnext"][0]["port"]
                elif settings.get("servers"):
                    server = settings["servers"][0]["address"]
                    port = settings["servers"][0]["port"]
            if not server or not port:
                continue
            nodes.append(
                ProxyNode(
                    protocol="ss" if protocol == "shadowsocks" else protocol,
                    name=outbound.get("tag", "profile"),
                    server=server,
                    port=port,
                    uuid=str(outbound.get("uuid") or ""),
                    password=str(outbound.get("password") or ""),
                )
            )
        except Exception:
            continue
    return nodes


def xray_config(node: ProxyNode, socks_port: int = 10808, http_port: int = 10809,
                listen_host: str = "127.0.0.1") -> dict[str, Any]:
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks-in", "listen": listen_host, "port": socks_port,
                "protocol": "socks", "settings": {"udp": True, "auth": "noauth"},
            },
            {
                "tag": "http-in", "listen": listen_host, "port": http_port,
                "protocol": "http", "settings": {},
            },
        ],
        "outbounds": [node.to_xray_outbound(), {"protocol": "freedom", "tag": "direct"}],
        "routing": {
            "domainStrategy": "AsIs",
            "rules": [
                {"type": "field", "ip": ["127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12",
                                          "192.168.0.0/16", "169.254.0.0/16"],
                 "outboundTag": "direct"},
            ],
        },
    }


def singbox_config(node: ProxyNode | list[ProxyNode], mixed_port: int = 2080,
                   api_port: int = 9091, listen_host: str = "127.0.0.1",
                   backend_ports: list[int] | None = None) -> dict[str, Any]:
    nodes = node if isinstance(node, list) else [node]
    if not nodes:
        raise ValueError("Список узлов sing-box пуст")
    if backend_ports is not None and len(backend_ports) != len(nodes):
        raise ValueError("Количество портов должно совпадать с количеством узлов")

    outbounds: list[dict[str, Any]] = []
    inbounds: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = [
        {"ip_is_private": True, "outbound": "direct"},
    ]
    for index, proxy_node in enumerate(nodes):
        tag = f"proxy-{index + 1}"
        outbound = proxy_node.to_singbox_outbound()
        outbound["tag"] = tag
        outbounds.append(outbound)
        if backend_ports is not None:
            inbound_tag = f"balance-in-{index + 1}"
            inbounds.append({
                "type": "mixed", "tag": inbound_tag, "listen": "127.0.0.1",
                "listen_port": int(backend_ports[index]),
            })
            routes.append({"inbound": [inbound_tag], "outbound": tag})

    if backend_ports is None:
        inbounds.append({
            "type": "mixed", "tag": "mixed-in", "listen": listen_host,
            "listen_port": mixed_port,
        })
        routes.append({"inbound": ["mixed-in"], "outbound": "proxy-1"})
    outbounds.append({"type": "direct", "tag": "direct"})
    return {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": inbounds,
        "outbounds": outbounds,
        "route": {
            "rules": routes,
            "final": "proxy-1",
            "auto_detect_interface": True,
        },
        "experimental": {
            "clash_api": {"external_controller": f"127.0.0.1:{api_port}"},
            "cache_file": {"enabled": True},
        },
    }


def direct_xray_config(socks_port: int = 10808, http_port: int = 10809,
                       listen_host: str = "127.0.0.1") -> dict[str, Any]:
    """Xray config that proxies traffic directly (no tunnel).

    Used by proxy sharing over Zapret: devices connect to the local inbound,
    traffic leaves the PC as-is so winws.exe can process it.
    """
    return {
        "log": {"loglevel": "warning"},
        "inbounds": [
            {
                "tag": "socks-in", "listen": listen_host, "port": socks_port,
                "protocol": "socks", "settings": {"udp": True, "auth": "noauth"},
            },
            {
                "tag": "http-in", "listen": listen_host, "port": http_port,
                "protocol": "http", "settings": {},
            },
        ],
        "outbounds": [{"protocol": "freedom", "tag": "direct"}],
        "routing": {"domainStrategy": "AsIs"},
    }


def direct_singbox_config(mixed_port: int = 2080,
                          listen_host: str = "127.0.0.1") -> dict[str, Any]:
    """sing-box config that proxies traffic directly (no tunnel)."""
    return {
        "log": {"level": "warn", "timestamp": True},
        "inbounds": [
            {"type": "mixed", "tag": "mixed-in", "listen": listen_host,
             "listen_port": mixed_port},
        ],
        "outbounds": [{"type": "direct", "tag": "direct"}],
        "route": {
            "rules": [],
            "final": "direct",
            "auto_detect_interface": True,
        },
    }
