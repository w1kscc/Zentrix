"""Scanner for installed games.

Reads launcher libraries (Steam, Epic Games, EA, GOG) and the Windows
uninstall registry without spawning anything. Pure filesystem/registry
reads, safe to run from a worker thread.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

try:  # winreg only exists on Windows; keep the module importable elsewhere
    import winreg
except ImportError:  # pragma: no cover
    winreg = None  # type: ignore[assignment]


@dataclass(frozen=True)
class GameEntry:
    name: str
    exe: str
    source: str  # steam | epic | ea | gog | registry | manual


def _is_game_exe(path: Path) -> bool:
    name = path.name
    if name.lower() in {"steam.exe", "steamerrorreporter.exe", "easteam.exe"}:
        return False
    stem = path.stem.lower()
    if re.search(r"(unins|setup|instal|update|updater|patch(er)?|crash|report"
                 r"|redist|vcredist|dotnet|directx|dxsetup|dxweb|cache|cleanup"
                 r"|prereq|helper|cef|eac|easyanticheat|anticheat|bat)", stem):
        return False
    return True


def _exes_in(folder: Path, limit: int = 6) -> list[Path]:
    try:
        candidates = [item for item in folder.iterdir()
                      if item.is_file() and item.suffix.lower() == ".exe"]
    except OSError:
        return []
    games = [item for item in candidates if _is_game_exe(item)]
    # Some titles keep the binary in a Win64/Binaries subfolder.
    if not games:
        for sub in ("Win64", "Binaries", "Win64\\Shipping", "Binaries\\Win64", "bin", "Game"):
            subfolder = folder / sub
            if subfolder.is_dir():
                games = [item for item in _exes_in(subfolder, limit) ]
                if games:
                    break
    return games[:limit]


def _steam_root() -> Path | None:
    for env in ("ProgramFiles(x86)", "ProgramFiles"):
        base = os.environ.get(env)
        if base:
            candidate = Path(base) / "Steam"
            if candidate.exists():
                return candidate
    return None


def _parse_vdf_value(text: str, key: str) -> list[str]:
    return re.findall(rf'"{key}"\s+"([^"]+)"', text)


def scan_steam() -> list[GameEntry]:
    root = _steam_root()
    if root is None:
        return []
    entries: list[GameEntry] = []
    libraries = {str(root)}
    for vdf in (root / "config" / "libraryfolders.vdf", root / "steamapps" / "libraryfolders.vdf"):
        if vdf.exists():
            try:
                libraries.update(_parse_vdf_value(vdf.read_text(encoding="utf-8",
                                                              errors="replace"), "path"))
            except OSError:
                pass
    for library in sorted(libraries):
        steamapps = Path(library) / "steamapps"
        try:
            manifests = list(steamapps.glob("appmanifest_*.acf"))
        except OSError:
            continue
        for manifest in manifests:
            try:
                text = manifest.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            names = _parse_vdf_value(text, "name")
            dirs = _parse_vdf_value(text, "installdir")
            if not names or not dirs:
                continue
            game_dir = steamapps / "common" / dirs[0]
            for exe in _exes_in(game_dir):
                entries.append(GameEntry(names[0], str(exe), "steam"))
    return entries


def scan_epic() -> list[GameEntry]:
    base = Path(os.environ.get("ProgramData", r"C:\ProgramData"))
    manifests_dir = base / "Epic" / "EpicGamesLauncher" / "Data" / "Manifests"
    entries: list[GameEntry] = []
    if not manifests_dir.is_dir():
        return entries
    for manifest in manifests_dir.glob("*.item"):
        try:
            data = json.loads(manifest.read_text(encoding="utf-8", errors="replace"))
        except (OSError, ValueError):
            continue
        install = str(data.get("InstallLocation") or "")
        launch = str(data.get("LaunchExecutable") or "")
        name = str(data.get("DisplayName") or data.get("AppName") or "")
        if not install or not launch:
            continue
        exe = Path(install) / launch.replace("/", "\\")
        if exe.exists():
            entries.append(GameEntry(name or exe.stem, str(exe), "epic"))
    return entries


def _registry_values(root, path: str, wow64: bool) -> list[dict[str, str]]:
    if winreg is None:  # pragma: no cover - non-Windows
        return []
    results: list[dict[str, str]] = []
    access = winreg.KEY_READ | (winreg.KEY_WOW64_32KEY if wow64 else winreg.KEY_WOW64_64KEY)
    try:
        key = winreg.OpenKey(root, path, 0, access)
    except OSError:
        return results
    try:
        index = 0
        while True:
            try:
                subkey_name = winreg.EnumKey(key, index)
            except OSError:
                break
            index += 1
            try:
                subkey = winreg.OpenKey(key, subkey_name, 0, access)
            except OSError:
                continue
            values: dict[str, str] = {}
            try:
                value_index = 0
                while True:
                    try:
                        name, value, _kind = winreg.EnumValue(subkey, value_index)
                    except OSError:
                        break
                    value_index += 1
                    if isinstance(value, str):
                        values[name.lower()] = value
            finally:
                winreg.CloseKey(subkey)
            results.append(values)
    finally:
        winreg.CloseKey(key)
    return results


def scan_gog() -> list[GameEntry]:
    entries: list[GameEntry] = []
    if winreg is None:
        return entries
    paths = [r"SOFTWARE\WOW6432Node\GOG.com\Games", r"SOFTWARE\GOG.com\Games"]
    for wow64 in (True, False):
        for values in _registry_values(winreg.HKEY_LOCAL_MACHINE, paths[0 if wow64 else 1], wow64):
            install = values.get("path") or values.get("installpath")
            if not install:
                continue
            name = values.get("gamename") or ""
            for exe in _exes_in(Path(install)):
                entries.append(GameEntry(name or exe.stem, str(exe), "gog"))
    return entries


def scan_ea() -> list[GameEntry]:
    entries: list[GameEntry] = []
    if winreg is None:
        return entries
    for wow64 in (True, False):
        path = r"SOFTWARE\WOW6432Node\EA Games" if wow64 else r"SOFTWARE\EA Games"
        for values in _registry_values(winreg.HKEY_LOCAL_MACHINE, path, wow64):
            install = values.get("install dir")
            if not install:
                continue
            for exe in _exes_in(Path(install)):
                entries.append(GameEntry(exe.stem, str(exe), "ea"))
    return entries


def scan_registry() -> list[GameEntry]:
    """Generic uninstall-registry scan (catches standalone installs)."""
    entries: list[GameEntry] = []
    if winreg is None:
        return entries
    uninstall = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    roots = ((winreg.HKEY_LOCAL_MACHINE, True), (winreg.HKEY_LOCAL_MACHINE, False),
             (winreg.HKEY_CURRENT_USER, True), (winreg.HKEY_CURRENT_USER, False))
    for root, wow64 in roots:
        for values in _registry_values(root, uninstall, wow64):
            install = values.get("installlocation") or ""
            name = values.get("displayname") or ""
            if not install or not name:
                continue
            folder = Path(install)
            if not folder.is_dir():
                continue
            for exe in _exes_in(folder):
                entries.append(GameEntry(name, str(exe), "registry"))
    return entries


def scan_games() -> list[GameEntry]:
    """Full scan across all sources, deduplicated and sorted by name."""
    merged: dict[str, GameEntry] = {}
    for scanner in (scan_steam, scan_epic, scan_ea, scan_gog, scan_registry):
        try:
            found = scanner()
        except Exception:
            continue
        for entry in found:
            key = entry.exe.lower()
            if key not in merged:
                merged[key] = entry
    return sorted(merged.values(), key=lambda item: item.name.lower())
