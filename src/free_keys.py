"""BETA: search public free-key repositories for vless/vmess configs.

Disabled by default. Only curated, well-known public repositories are used —
no random internet crawling. Nothing is applied automatically: the user must
explicitly press «Добавить в мой список», and every imported node is marked
«BETA / не проверено».

Security note surfaced in the UI: free nodes can intercept traffic (MITM) and
collect metadata; use at your own risk.
"""

from __future__ import annotations

import base64
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from . import net
from .logger import get_logger

log = get_logger("free-keys")

# Curated public source: igareck/vpn-configs-for-russia. The repo groups
# hand-tested, auto-refreshed configs into categories (black/white lists,
# mobile variants). Only these exact files are fetched — no crawling.
SOURCE_REPO = "igareck/vpn-configs-for-russia"

# (key, label, [files in the repo], hint). Keys are stored in settings.
CATEGORIES: list[dict] = [
    {"key": "black_vless", "label": "VLESS — чёрные списки (РКН)",
     "files": ["BLACK_VLESS_RUS.txt"], "schemes": ["vless"]},
    {"key": "black_vless_mobile", "label": "VLESS мобильные операторы (чёрные списки)",
     "files": ["BLACK_VLESS_RUS_mobile.txt"], "schemes": ["vless"]},
    {"key": "black_ss_all", "label": "Все протоколы — чёрные списки (SS, VLESS, VMess…)",
     "files": ["BLACK_SS+All_RUS.txt"], "schemes": ["vless", "vmess", "trojan", "ss"]},
    {"key": "black_ss_weak_dpi", "label": "Слабый DPI — чёрные списки",
     "files": ["BLACK_SS_WEAK_DPI_RUS.txt"], "schemes": ["vless", "vmess", "trojan", "ss"]},
    {"key": "white_reality_mobile", "label": "VLESS Reality — белые списки (моб. операторы)",
     "files": ["Vless-Reality-White-Lists-Rus-Mobile.txt"], "schemes": ["vless"]},
    {"key": "white_cidr_checked", "label": "Белые CIDR — проверенные",
     "files": ["WHITE-CIDR-RU-checked.txt"], "schemes": ["vless"]},
    {"key": "white_cidr_all", "label": "Белые CIDR — все",
     "files": ["WHITE-CIDR-RU-all.txt"], "schemes": ["vless"]},
    {"key": "white_sni", "label": "Белые SNI",
     "files": ["WHITE-SNI-RU-all.txt"], "schemes": ["vless"]},
]
CATEGORY_KEYS = [item["key"] for item in CATEGORIES]

# Protocols the user can filter by. Zentrix engines support these schemes.
SUPPORTED_SCHEMES = ("vless://", "vmess://", "trojan://", "ss://", "hysteria2://", "tuic://")
IMPORTABLE_SCHEMES = ("vless://", "vmess://", "trojan://", "ss://")

REFRESH_INTERVAL = 3600  # the upstream repo refreshes roughly every 1-2 hours

SUPPORTED_SCHEMES = ("vless://", "vmess://")
FETCH_TIMEOUT = 12.0


@dataclass
class FreeNode:
    scheme: str
    raw_link: str
    name: str
    host: str = ""
    port: int = 0
    source: str = ""
    ping_ms: float | None = None
    usable: bool | None = None  # None = not probed
    checked_at: float = field(default_factory=time.time)

    @property
    def label(self) -> str:
        marker = "BETA / не проверено"
        ping = f" · {self.ping_ms:.0f} мс" if self.ping_ms is not None else ""
        return f"{self.name} [{marker}]{ping}"


def decode_payload(data: bytes) -> str:
    """Decode a subscription payload: base64 first, then plain text."""
    text = data.decode("utf-8", errors="replace")
    stripped = "".join(text.split())
    if stripped and not any(scheme in text for scheme in SUPPORTED_SCHEMES):
        try:
            padded = stripped + "=" * (-len(stripped) % 4)
            decoded = base64.b64decode(padded, validate=False).decode("utf-8",
                                                                      errors="replace")
            if any(scheme in decoded for scheme in SUPPORTED_SCHEMES):
                return decoded
        except Exception:
            pass
    return text


def extract_links(text: str, schemes=None) -> list[str]:
    """Collect unique config links, optionally filtered to ``schemes``."""
    allowed = tuple(schemes) if schemes else SUPPORTED_SCHEMES
    links: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        candidate = line.strip().strip("'\"").rstrip(",")
        if "://" not in candidate:
            continue
        scheme = candidate.split("://", 1)[0].lower() + "://"
        if scheme not in allowed:
            continue
        candidate = candidate[candidate.index(scheme):].strip()
        if candidate and candidate not in seen:
            seen.add(candidate)
            links.append(candidate)
    return links


def _node_name(link: str, index: int) -> str:
    from urllib.parse import unquote, urlparse
    try:
        parsed = urlparse(link)
        fragment = unquote(parsed.fragment or "").strip()
        return fragment or f"Бесплатный узел #{index + 1}"
    except Exception:
        return f"Бесплатный узел #{index + 1}"


def parse_node(link: str, index: int, source: str) -> FreeNode:
    scheme = link.split("://", 1)[0].lower()
    host, port = "", 0
    try:
        from urllib.parse import urlparse
        parsed = urlparse(link)
        host = parsed.hostname or ""
        port = parsed.port or 0
    except Exception:
        pass
    return FreeNode(scheme=scheme, raw_link=link, name=_node_name(link, index),
                    host=host, port=port, source=source)


def fetch_source_links(repo: str, files: list[str] | None = None) -> list[str]:
    """Fetch the named raw files from one public repo (GitHub API listing)."""
    links: list[str] = []
    try:
        listing = net.http_json(f"https://api.github.com/repos/{repo}/contents/",
                                timeout=FETCH_TIMEOUT)
    except Exception as exc:
        log.warning("Список файлов %s: %s", repo, exc)
        return links
    names = {item.get("name", "") for item in listing if isinstance(item, dict)}
    targets = [name for name in (files or [])
               if any(name.casefold() == candidate.casefold() for candidate in names)]
    for name in targets:
        try:
            raw = net.http_json(
                f"https://api.github.com/repos/{repo}/contents/{name}",
                timeout=FETCH_TIMEOUT,
            )
            import base64 as b64
            content = str(raw.get("content", "") or "")
            if not content:
                continue
            data = b64.b64decode(content)
            links.extend(extract_links(decode_payload(data)))
        except Exception as exc:
            log.debug("Файл %s/%s: %s", repo, name, exc)
    return links


def category_by_key(key: str) -> dict | None:
    return next((item for item in CATEGORIES if item["key"] == key), None)


def normalize_categories(raw) -> list[str]:
    """Stored category keys -> valid list; empty/None = the VLESS default."""
    if not raw:
        return ["black_vless"]
    keys = [str(item) for item in raw if str(item) in CATEGORY_KEYS]
    return keys or ["black_vless"]


def search(progress=None, cancelled=None, categories=None, schemes=None) -> list[FreeNode]:
    """Fetch selected categories from the curated repo. Blocking.

    ``categories`` — list of CATEGORIES keys; ``schemes`` — list like
    ["vless", "vmess"]. A category's native schemes are honoured too: a file
    only yields protocols it actually contains.
    """
    chosen = [category_by_key(key) for key in normalize_categories(categories)]
    chosen = [item for item in chosen if item]
    collected: list[FreeNode] = []
    seen: set[str] = set()
    scheme_filter = {s.lower().rstrip(":/") for s in schemes} if schemes else None
    for index, category in enumerate(chosen, start=1):
        if cancelled and cancelled():
            break
        if progress:
            progress(index, len(chosen), category["label"])
        wanted = [s for s in category["schemes"]
                  if scheme_filter is None or s in scheme_filter]
        if not wanted:
            continue
        for link in fetch_source_links(SOURCE_REPO, category["files"]):
            scheme = link.split("://", 1)[0].lower()
            if scheme not in wanted:
                continue
            if link in seen:
                continue
            seen.add(link)
            collected.append(parse_node(link, len(collected), category["label"]))
    return collected


def probe_nodes(nodes: list[FreeNode], timeout: float = 3.5) -> None:
    """TCP-probe each node in place (latency + reachability). Blocking."""
    from .nettools import tcp_ping

    def probe(node: FreeNode):
        if not node.host or not node.port:
            return
        node.ping_ms = tcp_ping(node.host, node.port, timeout=timeout)
        node.usable = node.ping_ms is not None

    with ThreadPoolExecutor(max_workers=min(8, len(nodes) or 1)) as pool:
        futures = [pool.submit(probe, node) for node in nodes]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                pass


def summarize(nodes: list[FreeNode]) -> str:
    if not nodes:
        return "Ничего не найдено в известных источниках"
    alive = sum(1 for node in nodes if node.usable)
    if alive:
        return f"Найдено {len(nodes)} узлов, доступно {alive} — добавляйте вручную"
    return f"Найдено {len(nodes)} узлов, доступность не проверялась или нулевая"
