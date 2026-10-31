#!/usr/bin/env python3
"""Download the prebuilt hev-socks5-tunnel AAR (with bundled natives).

Run before the first Gradle build:

    python scripts/fetch_tun2socks.py

The AAR is attached to upstream releases by CI; natives are registered
to hev.htproxy.TProxyService, so no local NDK build is required.
"""

from __future__ import annotations

import json
import sys
import urllib.request
from pathlib import Path

REPO = "heiher/hev-socks5-tunnel"
DEST = Path(__file__).resolve().parent.parent / "app" / "libs" / "hev-socks5-tunnel.aar"


def main() -> int:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/latest",
        headers={"User-Agent": "SharingConnect"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        release = json.loads(response.read().decode("utf-8"))
    aar = next((a for a in release.get("assets", []) if a["name"].lower().endswith(".aar")), None)
    if aar is None:
        print("AAR не найден в релизе", release.get("tag_name"))
        return 1
    DEST.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(aar["browser_download_url"], timeout=120) as response:
        DEST.write_bytes(response.read())
    print(f"{DEST} ({DEST.stat().st_size} байт) · релиз {release.get('tag_name')}")
    print("Готово — можно собирать: gradle assembleDebug")
    return 0


if __name__ == "__main__":
    sys.exit(main())
