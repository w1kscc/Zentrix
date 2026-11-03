"""Upstream list updaters for Zapret ("Обновить IPSet" / "Обновить hosts").

Mirrors the upstream service.bat menu items 8 and 9: ipset-all.txt is
refreshed from the Flowseal repository, and the Windows hosts file is kept
in sync with the upstream hosts additions inside a managed block.
"""

from __future__ import annotations

import os
import shutil
import urllib.request
from pathlib import Path

IPSET_URL = ("https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/"
             "refs/heads/main/.service/ipset-service.txt")
HOSTS_URL = ("https://raw.githubusercontent.com/Flowseal/zapret-discord-youtube/"
             "refs/heads/main/.service/hosts")

HOSTS_BEGIN = "# >>> Zentrix Zapret Hosts >>>"
HOSTS_END = "# <<< Zentrix Zapret Hosts <<<"

_UA = {"User-Agent": "Zentrix/1.0"}


def _download(url: str, timeout: float = 20.0) -> str:
    request = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def update_ipset(folder: Path, timeout: float = 20.0) -> int:
    """Replace lists/ipset-all.txt with the upstream list; returns line count.

    The previous file is kept as ipset-all.txt.backup, like upstream does.
    """
    text = _download(IPSET_URL, timeout)
    lines = [line.strip() for line in text.splitlines()
             if line.strip() and not line.strip().startswith("#")]
    # The file ships with a dummy placeholder; a real update is much larger.
    if len(lines) < 10:
        raise RuntimeError("Скачанный ipset выглядит некорректно (мало записей)")
    lists_dir = folder / "lists"
    lists_dir.mkdir(parents=True, exist_ok=True)
    target = lists_dir / "ipset-all.txt"
    if target.exists():
        shutil.copy2(target, lists_dir / "ipset-all.txt.backup")
    target.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8", newline="")
    return len(lines)


def sanitize_list_filename(name: str) -> str | None:
    """Validate a user-supplied list filename; None if it is unsafe."""
    raw = (name or "").strip().strip("\\/")
    name = raw.replace("\\", "/").split("/")[-1].strip()
    if not name or "/" in raw or "\\" in raw or ".." in name:
        return None
    if not name.lower().endswith((".txt", ".lst")):
        return None
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_. ")
    if not set(name) <= allowed:
        return None
    return name


def update_custom_list(folder: Path, filename: str, url: str,
                       timeout: float = 20.0) -> int:
    """Download a user-registered banlist into lists/<filename>; returns line count.

    The previous file is kept as <filename>.backup, like update_ipset does.
    """
    safe = sanitize_list_filename(filename)
    if not safe:
        raise RuntimeError(f"Недопустимое имя файла списка: {filename!r}")
    if not (url or "").lower().startswith(("http://", "https://")):
        raise RuntimeError("Ссылка должна начинаться с http:// или https://")
    text = _download(url, timeout)
    lines = [line.strip() for line in text.splitlines()
             if line.strip() and not line.strip().startswith("#")]
    if not lines:
        raise RuntimeError("Скачанный список пуст")
    lists_dir = folder / "lists"
    lists_dir.mkdir(parents=True, exist_ok=True)
    target = lists_dir / safe
    if target.exists():
        shutil.copy2(target, lists_dir / (safe + ".backup"))
    target.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8", newline="")
    return len(lines)


def update_custom_lists(folder: Path, entries: list[dict]) -> list[tuple[str, bool, str]]:
    """Refresh every user-registered list; returns (name, ok, message) tuples."""
    results: list[tuple[str, bool, str]] = []
    for entry in entries:
        name = str(entry.get("name") or entry.get("file") or "?")
        try:
            count = update_custom_list(folder, str(entry.get("file", "")),
                                       str(entry.get("url", "")))
            results.append((name, True, f"{count} записей"))
        except Exception as exc:  # keep updating the remaining lists
            results.append((name, False, str(exc)))
    return results


def hosts_path() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"


def fetch_hosts(timeout: float = 20.0) -> str:
    """Download the upstream hosts additions as text."""
    content = _download(HOSTS_URL, timeout).strip()
    if not content:
        raise RuntimeError("Скачанный hosts-файл пуст")
    return content


def hosts_managed_block() -> str:
    """Return the current Zentrix block inside the Windows hosts file ("" if none)."""
    try:
        text = hosts_path().read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    if HOSTS_BEGIN not in text or HOSTS_END not in text:
        return ""
    between = text.split(HOSTS_BEGIN, 1)[1].split(HOSTS_END, 1)[0]
    return between.strip()


def hosts_is_up_to_date(content: str) -> bool:
    return hosts_managed_block() == content.strip()


def write_hosts_block(content: str) -> bool:
    """Write (or replace) the managed hosts block. Requires admin rights."""
    hosts = hosts_path()
    try:
        original = hosts.read_text(encoding="utf-8", errors="replace")
    except OSError:
        original = ""
    backup = hosts.with_name("hosts.zentrix.bak")
    if not backup.exists() and original:
        try:
            shutil.copy2(hosts, backup)
        except OSError:
            pass
    text = original
    if HOSTS_BEGIN in text and HOSTS_END in text:
        before = text.split(HOSTS_BEGIN, 1)[0]
        after = text.split(HOSTS_END, 1)[1]
        text = before + after
    text = text.rstrip("\r\n") + "\n\n" if text.strip() else ""
    block = f"{HOSTS_BEGIN}\n{content.strip()}\n{HOSTS_END}\n"
    try:
        hosts.write_text(text + block, encoding="utf-8", newline="")
    except OSError:
        return False
    return True
