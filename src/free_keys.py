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

# Curated public sources (owner/repo). Extend deliberately, never crawl.
SOURCES: list[str] = [
    "Au1rxx/free-vpn-subscriptions",
]
KNOWN_FILES = ("sub.txt", "sub.md", "all.txt", "README.md", "config.yaml", "list.txt")

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


def extract_links(text: str) -> list[str]:
    """Collect unique vless:// and vmess:// links (also inside YAML scalars)."""
    links: list[str] = []
    seen: set[str] = set()
    for line in text.splitlines():
        candidate = line.strip().strip("'\"").rstrip(",")
        if "://" not in candidate:
            continue
        scheme = candidate.split("://", 1)[0].lower() + "://"
        if scheme not in SUPPORTED_SCHEMES:
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


def fetch_source_links(repo: str) -> list[str]:
    """Fetch known files from one public repo via the GitHub API."""
    links: list[str] = []
    try:
        listing = net.http_json(f"https://api.github.com/repos/{repo}/contents/",
                                timeout=FETCH_TIMEOUT)
    except Exception as exc:
        log.warning("Список файлов %s: %s", repo, exc)
        return links
    names = [item.get("name", "") for item in listing if isinstance(item, dict)]
    targets = [name for name in names
               if name.lower() in KNOWN_FILES or name.lower().endswith((".txt", ".yaml", ".yml"))]
    for name in targets[:8]:
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


def search(progress=None, cancelled=None) -> list[FreeNode]:
    """Download every curated source and return unique nodes. Blocking."""
    collected: list[FreeNode] = []
    seen: set[str] = set()
    for repo_index, repo in enumerate(SOURCES, start=1):
        if cancelled and cancelled():
            break
        if progress:
            progress(repo_index, len(SOURCES), repo)
        for index, link in enumerate(fetch_source_links(repo)):
            if link in seen:
                continue
            seen.add(link)
            collected.append(parse_node(link, len(collected), repo))
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
