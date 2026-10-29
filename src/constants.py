"""Application-wide constants for Zentrix.

Keep this module import-free of heavy libraries: it is loaded very early
during the cold-start path and must stay cheap.
"""

from __future__ import annotations

APP_NAME = "Zentrix"
APP_DISPLAY_NAME = "Zentrix"
APP_VERSION = "1.0.2"
APP_PUBLISHER = "Zentrix Project"
APP_DESCRIPTION = "GUI для обхода блокировок: Zapret, Happ и Hiddify в одном окне"
APP_LICENSE = "MIT"
APP_HOMEPAGE = "https://github.com/wikscc/Zentrix"

# Repository used for self-updates (owner/name). Can be overridden in settings.
ZENTRIX_REPO = "wikscc/Zentrix"
GITHUB_API = "https://api.github.com/repos/{repo}/releases/latest"

# Upstream projects wrapped by Zentrix.
SOURCES = {
    "zapret": {
        "name": "zapret-discord-youtube",
        "version": "1.10.4",
        "repo": "Flowseal/zapret-discord-youtube",
        "url": "https://github.com/Flowseal/zapret-discord-youtube",
        "license": "MIT",
        "license_url": "https://github.com/Flowseal/zapret-discord-youtube/blob/main/LICENSE.txt",
        "folder": "zapret-discord-youtube-1.10.4",
        "engine_dir": "zapret",
    },
    "happ": {
        "name": "Happ Desktop",
        "version": "4.6.1",
        "repo": "Happ-proxy/happ-desktop",
        "url": "https://github.com/Happ-proxy/happ-desktop",
        "license": "Proprietary (Happ)",
        "license_url": "https://github.com/Happ-proxy/happ-desktop",
        "folder": "happ-desktop-4.6.1",
        "engine_dir": "happ",
    },
    "hiddify": {
        "name": "Hiddify",
        "version": "4.1.1",
        "repo": "hiddify/hiddify-app",
        "url": "https://github.com/hiddify/hiddify-app",
        "license": "CC BY-NC-SA 4.0",
        "license_url": "https://github.com/hiddify/hiddify-app/blob/main/LICENSE.md",
        "folder": "hiddify-app-4.1.1",
        "engine_dir": "hiddify",
    },
}

# Core binaries that Zentrix launches headlessly.
CORES = {
    "xray": {
        "name": "Xray-core",
        "repo": "XTLS/Xray-core",
        "url": "https://github.com/XTLS/Xray-core",
        "license": "MPL-2.0",
        "asset_keyword": "windows-64",
    },
    "singbox": {
        "name": "sing-box",
        "repo": "SagerNet/sing-box",
        "url": "https://github.com/SagerNet/sing-box",
        "license": "GPL-3.0",
        "asset_keyword": "windows-amd64",
    },
}

# Services probed by the blocking-check page.
# `strategy` refers to a local zapret strategy name fragment.
SERVICES = [
    {"id": "youtube", "name": "YouTube", "host": "www.youtube.com", "icu": "YT",
     "strategy": "general.bat", "note": "DPI + QUIC"},
    {"id": "discord", "name": "Discord", "host": "discord.com", "icu": "DC",
     "strategy": "general.bat", "note": "UDP/STUN"},
    {"id": "telegram", "name": "Telegram", "host": "web.telegram.org", "icu": "TG",
     "strategy": "general.bat", "note": "TCP 443"},
    {"id": "instagram", "name": "Instagram", "host": "www.instagram.com", "icu": "IG",
     "strategy": "general.bat", "note": "TLS/SNI"},
    {"id": "twitter", "name": "X / Twitter", "host": "x.com", "icu": "X",
     "strategy": "general.bat", "note": "TLS/SNI"},
    {"id": "steam", "name": "Steam", "host": "store.steampowered.com", "icu": "ST",
     "strategy": "general (ALT).bat", "note": "CDN"},
    {"id": "github", "name": "GitHub", "host": "github.com", "icu": "GH",
     "strategy": "general.bat", "note": "TLS"},
    {"id": "googlevideo", "name": "Google Video", "host": "redirector.googlevideo.com", "icu": "GV",
     "strategy": "general.bat", "note": "QUIC/CDN"},
    {"id": "whatsapp", "name": "WhatsApp", "host": "web.whatsapp.com", "icu": "WA",
     "strategy": "general.bat", "note": "TLS"},
    {"id": "spotify", "name": "Spotify", "host": "open.spotify.com", "icu": "SP",
     "strategy": "general (ALT3).bat", "note": "CDN"},
]

# Sound events generated at runtime.
SOUND_EVENTS = [
    ("startup", "Р—Р°РїСѓСЃРє РїСЂРёР»РѕР¶РµРЅРёСЏ"),
    ("tray", "РЎРІРѕСЂР°С‡РёРІР°РЅРёРµ РІ С‚СЂРµР№"),
    ("exit", "Р’С‹С…РѕРґ"),
    ("enable", "РћР±С…РѕРґ РІРєР»СЋС‡С‘РЅ"),
    ("disable", "РћР±С…РѕРґ РІС‹РєР»СЋС‡РµРЅ"),
    ("update", "РћР±РЅРѕРІР»РµРЅРёРµ СѓСЃС‚Р°РЅРѕРІР»РµРЅРѕ"),
    ("error", "РћС€РёР±РєР°"),
    ("notify", "РЈРІРµРґРѕРјР»РµРЅРёРµ"),
    ("click", "РќР°Р¶Р°С‚РёРµ"),
]

# Presets bundled with the app (also written to disk on first run).
DEFAULT_PRESET_NAME = "Zentrix Default"
