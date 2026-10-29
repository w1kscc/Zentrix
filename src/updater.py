"""Update checks and installation for the four Zentrix components."""

from __future__ import annotations

import json
import shutil
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

from . import constants, net, paths
from .logger import get_logger
from .settings_store import settings

log = get_logger("updater")


@dataclass
class ComponentStatus:
    key: str
    name: str
    current: str = ""
    latest: str = ""
    has_update: bool = False
    asset_name: str = ""
    asset_url: str = ""
    notes: str = ""
    error: str = ""
    html_url: str = ""
    source_url: str = ""
    license: str = ""
    kind: str = "engine"
    checked_at: float = field(default_factory=time.time)


COMPONENTS = {
    "zapret": {
        "name": "Zapret",
        "source": "zapret-discord-youtube",
        "repo": "Flowseal/zapret-discord-youtube",
        "keywords": ["zapret-discord-youtube", "zapret"],
        "exclude": ["source", ".sha", "sha256", ".rar", ".tar", ".7z", ".dgst"],
        "kind": "engine",
        "license": "MIT",
        "url": "https://github.com/Flowseal/zapret-discord-youtube",
    },
    "happ": {
        "name": "Happ",
        "source": "happ-desktop",
        "repo": "Happ-proxy/happ-desktop",
        "keywords": ["setup-happ.x64.exe", "windows", ".exe"],
        "exclude": ["arm64", "macos", "linux", "android", ".dmg", ".deb", ".rpm"],
        "kind": "vendor",
        "license": "Proprietary",
        "url": "https://github.com/Happ-proxy/happ-desktop",
    },
    "hiddify": {
        "name": "Hiddify",
        "source": "hiddify-app",
        "repo": "hiddify/hiddify-app",
        "keywords": ["windows", ".exe"],
        "exclude": ["arm64", "macos", "linux", "android", "portable"],
        "kind": "vendor",
        "license": "CC BY-NC-SA 4.0",
        "url": "https://github.com/hiddify/hiddify-app",
    },
    "zentrix": {
        "name": "Zentrix",
        "source": "Zentrix",
        "repo": constants.ZENTRIX_REPO,
        "keywords": ["setup", ".exe"],
        "exclude": ["arm64", ".blockmap"],
        "kind": "self",
        "license": "MIT",
        "url": constants.APP_HOMEPAGE,
    },
}


def _installed_version(key: str) -> str:
    meta = paths.ENGINES_DIR / key / "version.json"
    try:
        payload = json.loads(meta.read_text(encoding="utf-8"))
        return str(payload.get("version", "") or "")
    except Exception:
        pass
    if key == "zapret" and (paths.ENGINES_DIR / "zapret" / "bin" / "winws.exe").exists():
        return constants.SOURCES["zapret"]["version"]
    if key in {"happ", "hiddify"}:
        core_kind = "xray" if key == "happ" else "singbox"
        core_meta = paths.ENGINES_DIR / core_kind / "core" / "version.json"
        try:
            payload = json.loads(core_meta.read_text(encoding="utf-8"))
            return str(payload.get("version", "") or "")
        except Exception:
            pass
        if (paths.ENGINES_DIR / core_kind / "core").exists():
            return constants.SOURCES[key]["version"]
    if key == "zentrix":
        return constants.APP_VERSION
    return ""


def installed_version(key: str) -> str:
    """Version of an installed component, without any network access."""
    return _installed_version(key)


def component_repo(key: str) -> str:
    if key == "zentrix":
        return str(settings.get("updates.zentrix_repo", constants.ZENTRIX_REPO) or constants.ZENTRIX_REPO)
    return COMPONENTS[key]["repo"]


def check(key: str) -> ComponentStatus:
    meta = COMPONENTS[key]
    repo = component_repo(key)
    status = ComponentStatus(
        key=key,
        name=meta["name"],
        current=_installed_version(key),
        source_url=meta["url"],
        license=meta["license"],
        kind=meta["kind"],
    )
    status.notes = f"Репозиторий: {repo}"
    try:
        release = net.github_latest(repo)
        status.latest = release.version
        status.html_url = release.html_url
        asset = net.pick_asset(release, meta["keywords"], exclude=meta["exclude"])
        if asset is None and release.assets:
            asset = release.assets[0]
        if asset:
            status.asset_name = asset.name
            status.asset_url = asset.url
        status.has_update = not status.current or net.is_newer(status.latest, status.current)
        if release.name and release.name != release.tag:
            status.notes = release.name[:120]
    except Exception as exc:
        status.error = _friendly_error(exc)
        log.warning("Проверка обновлений %s: %s", key, exc)
    return status


def _friendly_error(exc: Exception) -> str:
    text = str(exc)
    if "404" in text:
        return "Репозиторий не найден (проверьте адрес в настройках)"
    if "403" in text or "rate limit" in text.lower():
        return "GitHub ограничил запросы. Повторите позже или задайте GITHUB_TOKEN"
    if "timed out" in text.lower() or "timeout" in text.lower():
        return "Превышено время ожидания. Проверьте подключение"
    if "Name or service not known" in text or "getaddrinfo" in text:
        return "Нет подключения к интернету"
    return text[:180] or "Неизвестная ошибка"


def check_all(keys: list[str] | None = None) -> dict[str, ComponentStatus]:
    return {key: check(key) for key in (keys or COMPONENTS.keys())}


def download(key: str, progress=None, cancel=None) -> Path:
    status = check(key)
    if status.error:
        raise RuntimeError(status.error)
    if not status.asset_url:
        raise RuntimeError(f"В релизе {status.latest} нет подходящего файла Windows")
    target = paths.DOWNLOADS_DIR / status.asset_name
    log.info("Скачивание %s %s → %s", key, status.latest, target.name)
    net.download(status.asset_url, target, progress=progress, cancel=cancel)
    return target


def _extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = destination / member.filename
            if ".." in Path(member.filename).parts:
                continue
            bundle.extract(member, destination)


def install(key: str, progress=None, cancel=None) -> dict:
    """Download and install an update. Returns a dict describing the result."""
    if key == "zentrix":
        path = download("zentrix", progress=progress, cancel=cancel)
        return {"mode": "installer", "path": path, "message": f"Установщик загружен: {path.name}"}

    meta = COMPONENTS[key]
    archive = download(key, progress=progress, cancel=cancel)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    version = check(key).latest or "latest"

    if key == "zapret":
        if archive.suffix.lower() != ".zip":
            raise RuntimeError("Ожидался zip-архив со стратегиями zapret")
        staging = paths.TEMP_DIR / f"zapret-{stamp}"
        _extract(archive, staging)
        root = staging
        if not (root / "bin" / "winws.exe").exists():
            candidates = list(staging.rglob("winws.exe"))
            if not candidates:
                raise RuntimeError("В архиве не найден winws.exe")
            root = candidates[0].parent.parent
        target = paths.ENGINES_DIR / "zapret"
        backup = paths.ENGINES_DIR / f"zapret.old-{stamp}"
        if target.exists():
            target.rename(backup)
        shutil.copytree(root, target)
        # Upstream updates ship their own lists; keep the user's custom lists
        # and game-filter toggle on top of the fresh strategy files.
        if backup.exists():
            user_lists = backup / "lists"
            if user_lists.exists():
                shutil.copytree(user_lists, target / "lists", dirs_exist_ok=True)
            game_flag = backup / "utils" / "game_filter.enabled"
            if game_flag.exists():
                (target / "utils").mkdir(parents=True, exist_ok=True)
                shutil.copy2(game_flag, target / "utils" / "game_filter.enabled")
        (target / "version.json").write_text(
            json.dumps({"version": version, "repo": meta["repo"]}, indent=2), encoding="utf-8"
        )
        shutil.rmtree(staging, ignore_errors=True)
        _cleanup_archive(archive)
        return {"mode": "engine", "path": target, "backup": backup,
                "message": f"Zapret обновлён до {version}"}

    # Happ / Hiddify: keep the vendor payload next to the integration core.
    vendor = paths.ENGINES_DIR / key / "vendor"
    vendor.mkdir(parents=True, exist_ok=True)
    copied = vendor / archive.name
    shutil.copy2(archive, copied)
    if archive.suffix.lower() == ".zip":
        _extract(archive, vendor / archive.stem)
    version_file = paths.ENGINES_DIR / key / "version.json"
    version_file.parent.mkdir(parents=True, exist_ok=True)
    version_file.write_text(
        json.dumps({"version": version, "repo": meta["repo"], "asset": archive.name}, indent=2),
        encoding="utf-8",
    )
    _cleanup_archive(archive)
    return {"mode": "installer", "path": copied,
            "message": f"{meta['name']} {version} загружен в engines/{key}/vendor"}


def _cleanup_archive(archive: Path) -> None:
    try:
        archive.unlink()
    except OSError:
        pass


def launch_installer(path: Path) -> bool:
    """Run a downloaded Zentrix installer elevated (no console window)."""
    import ctypes

    try:
        result = ctypes.windll.shell32.ShellExecuteW(
            None, "runas", str(path), "/SILENT", str(path.parent), 5
        )
        return int(result) > 32
    except Exception:
        return False
