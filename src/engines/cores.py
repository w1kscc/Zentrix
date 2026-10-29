"""Download and locate the headless cores used by the Happ/Hiddify tabs."""

from __future__ import annotations

import json
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from .. import net, paths
from ..logger import get_logger

log = get_logger("cores")

CORE_REPOS = {
    "xray": ("XTLS/Xray-core", ["windows-64", "win64"], ["sha256", ".dgst", ".sig"]),
    "singbox": ("SagerNet/sing-box", ["windows-amd64", "windows_amd64"], ["sha256", ".sig"]),
}

EXECUTABLES = {"xray": "xray.exe", "singbox": "sing-box.exe"}


def core_root(kind: str) -> Path:
    return paths.ENGINES_DIR / kind / "core"


def find_core(kind: str, configured: str = "") -> Path | None:
    executable = EXECUTABLES.get(kind, "")
    if configured:
        candidate = Path(configured)
        if candidate.is_file() and candidate.exists():
            return candidate
        if candidate.is_dir():
            for match in candidate.rglob(executable):
                return match
    root = core_root(kind)
    if root.exists():
        direct = root / executable
        if direct.exists():
            return direct
        for match in root.rglob(executable):
            return match
    return None


def core_version(kind: str) -> str:
    meta = core_root(kind) / "version.json"
    try:
        return str(json.loads(meta.read_text(encoding="utf-8")).get("version", ""))
    except Exception:
        return ""


def latest_core(kind: str) -> net.Release:
    repo, keywords, exclude = CORE_REPOS[kind]
    release = net.github_latest(repo)
    release.assets = [asset for asset in release.assets
                      if any(keyword in asset.name.lower() for keyword in keywords)]
    return release


def _safe_extract(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            member_path = destination / member.filename
            try:
                if not member_path.resolve().is_relative_to(destination.resolve()):
                    continue
            except AttributeError:  # pragma: no cover - Python < 3.9
                if ".." in Path(member.filename).parts:
                    continue
            bundle.extract(member, destination)


def install_core(kind: str, progress: Callable[[int, int], None] | None = None,
                 cancel: Callable[[], bool] | None = None) -> Path:
    executable = EXECUTABLES.get(kind)
    if not executable:
        raise ValueError(kind)
    repo, keywords, exclude = CORE_REPOS[kind]
    release = net.github_latest(repo)
    if not release.assets:
        # GitHub may return an empty asset list only for unpublished releases.
        raise RuntimeError(f"В релизе {release.tag} нет файлов")
    asset = net.pick_asset(release, keywords, exclude=exclude)
    if asset is None:
        raise RuntimeError(f"Не найден архив для Windows в релизе {release.tag}")
    log.info("Скачивание %s %s", executable, release.tag)
    paths.ensure_dirs()
    archive = paths.DOWNLOADS_DIR / asset.name
    net.download(asset.url, archive, progress=progress, cancel=cancel)

    with tempfile.TemporaryDirectory(dir=str(paths.TEMP_DIR)) as temp:
        temp_path = Path(temp)
        _safe_extract(archive, temp_path)
        found = None
        for match in temp_path.rglob(executable):
            found = match
            break
        if not found:
            raise RuntimeError(f"В архиве нет {executable}")
        target_dir = core_root(kind)
        if target_dir.exists():
            shutil.rmtree(target_dir, ignore_errors=True)
        target_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(found, target_dir / executable)
        # Copy companion assets (geoip.dat, wintun.dll, ...) but skip docs.
        for companion in found.parent.iterdir():
            if companion.is_file() and companion.suffix.lower() in {".dat", ".dll", ".json"}:
                shutil.copy2(companion, target_dir / companion.name)
        (target_dir / "version.json").write_text(
            json.dumps({"version": release.version, "tag": release.tag, "repo": repo}, indent=2),
            encoding="utf-8",
        )
    try:
        archive.unlink()
    except OSError:
        pass
    return core_root(kind) / executable
