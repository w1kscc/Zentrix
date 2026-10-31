#!/usr/bin/env python3
"""Download prebuilt libtun2socks.so (hev-socks5-tunnel) for Android.

Run before the first Gradle build:

    python scripts/fetch_tun2socks.py

The script fetches the latest release of the upstream hev-socks5-tunnel
project and unpacks the Android binaries into app/src/main/jniLibs/.
If the upstream asset layout changes, adjust ASSET_FILTER below.
"""

from __future__ import annotations

import io
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

REPO = "heiher/hev-socks5-tunnel"
ABI_MAP = {
    "arm64-v8a": "arm64-v8a",
    "armeabi-v7a": "armeabi-v7a",
    "x86_64": "x86_64",
}
DEST = Path(__file__).resolve().parent.parent / "app" / "src" / "main" / "jniLibs"


def main() -> int:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{REPO}/releases/latest",
        headers={"User-Agent": "SharingConnect"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        release = json.loads(response.read().decode("utf-8"))
    assets = [a for a in release.get("assets", []) if "android" in a["name"].lower()]
    if not assets:
        print("Не найден Android-ассет в релизе", release.get("tag_name"))
        return 1
    for asset in assets:
        for abi, dest_abi in ABI_MAP.items():
            if abi in asset["name"].lower() or dest_abi in asset["name"].lower():
                target = DEST / dest_abi / "libtun2socks.so"
                target.parent.mkdir(parents=True, exist_ok=True)
                with urllib.request.urlopen(asset["browser_download_url"], timeout=60) as response:
                    payload = response.read()
                if asset["name"].endswith(".zip"):
                    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                        so_name = next(n for n in archive.namelist() if n.endswith(".so"))
                        target.write_bytes(archive.read(so_name))
                else:
                    target.write_bytes(payload)
                print(f"{dest_abi}: {target} ({target.stat().st_size} байт)")
    print("Готово — можно собирать: gradle assembleDebug")
    return 0


if __name__ == "__main__":
    sys.exit(main())
