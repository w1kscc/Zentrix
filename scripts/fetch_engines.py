"""Download the engines Zentrix integrates, without committing binaries.

Examples:

    python scripts/fetch_engines.py                 # Zapret 1.10.4
    python scripts/fetch_engines.py --cores         # Xray-core + sing-box
    python scripts/fetch_engines.py --all           # Zapret + cores
    python scripts/fetch_engines.py --vendor        # official Happ/Hiddify installers
    python scripts/fetch_engines.py --zapret-version latest --force

The resulting ``engines/`` directory is git-ignored. Set GITHUB_TOKEN to avoid
the unauthenticated GitHub API rate limit.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import constants, net, paths  # noqa: E402
from src.engines import cores  # noqa: E402

ZAPRET_REPO = constants.SOURCES["zapret"]["repo"]
DEFAULT_ZAPRET_VERSION = constants.SOURCES["zapret"]["version"]


def log(message: str) -> None:
    print(f"[engines] {message}", flush=True)


def _release_by_tag(repo: str, tag: str) -> net.Release:
    data = net.http_json(f"https://api.github.com/repos/{repo}/releases/tags/{tag}")
    return net.Release(
        repo=repo,
        tag=data.get("tag_name", tag),
        name=data.get("name", "") or tag,
        published_at=data.get("published_at", "") or "",
        body=(data.get("body", "") or "")[:2000],
        assets=[
            net.Asset(
                name=item.get("name", ""),
                url=item.get("browser_download_url", ""),
                size=int(item.get("size", 0) or 0),
            )
            for item in data.get("assets", [])
        ],
        html_url=data.get("html_url", "") or "",
    )


def _resolve_zapret(version: str) -> net.Release:
    if version.lower() in {"latest", ""}:
        log("resolving latest zapret release")
        return net.github_latest(ZAPRET_REPO)
    for tag in (version, f"v{version}"):
        try:
            log(f"resolving zapret {tag}")
            return _release_by_tag(ZAPRET_REPO, tag)
        except Exception as exc:
            log(f"tag {tag}: {exc}")
    log(f"tag {version} not found; falling back to the latest release")
    return net.github_latest(ZAPRET_REPO)


def _safe_extract(archive: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(root):
                log(f"skipping unsafe archive member: {member.filename}")
                continue
            bundle.extract(member, destination)


def install_zapret(version: str, *, force: bool = False) -> Path:
    target = paths.ENGINES_DIR / "zapret"
    if (target / "bin" / "winws.exe").exists() and not force:
        meta = target / "version.json"
        current = ""
        try:
            current = str(json.loads(meta.read_text(encoding="utf-8")).get("version", ""))
        except Exception:
            pass
        log(f"zapret already present ({current or 'unknown version'}); use --force to replace")
        return target

    release = _resolve_zapret(version)
    keywords = ["zapret-discord-youtube", "zapret"]
    exclude = ["source", ".sha", "sha256", ".rar", ".tar", ".7z", ".dgst"]
    release.assets = [
        asset for asset in release.assets
        if asset.name.lower().endswith(".zip")
        and not any(word in asset.name.lower() for word in exclude)
    ]
    asset = net.pick_asset(release, keywords, exclude=exclude)
    if asset is None and release.assets:
        asset = release.assets[0]
    if asset is None or not asset.name.lower().endswith(".zip"):
        raise SystemExit(f"No Windows zip asset in zapret {release.tag}")

    log(f"downloading {asset.name} ({asset.size / 1_048_576:.1f} MB)")
    paths.ensure_dirs()
    archive = paths.DOWNLOADS_DIR / asset.name

    def progress(done: int, total: int) -> None:
        if total:
            sys.stdout.write(f"\r[engines]   {done * 100 // total:3d}%")
            sys.stdout.flush()

    net.download(asset.url, archive, progress=progress)
    print()

    stamp = time.strftime("%Y%m%d-%H%M%S")
    staging = Path(tempfile.mkdtemp(prefix=f"zapret-{stamp}-", dir=str(paths.TEMP_DIR)))
    try:
        _safe_extract(archive, staging)
        winws = next(staging.rglob("winws.exe"), None)
        if winws is None:
            raise SystemExit("winws.exe is missing from the archive")
        root = winws.parent.parent
        backup = None
        if target.exists():
            backup = paths.ENGINES_DIR / f"zapret.old-{stamp}"
            target.rename(backup)
        shutil.copytree(root, target)
        if backup is not None:
            user_lists = backup / "lists"
            if user_lists.exists():
                shutil.copytree(user_lists, target / "lists", dirs_exist_ok=True)
            flag = backup / "utils" / "game_filter.enabled"
            if flag.exists():
                (target / "utils").mkdir(parents=True, exist_ok=True)
                shutil.copy2(flag, target / "utils" / "game_filter.enabled")
            shutil.rmtree(backup, ignore_errors=True)
    finally:
        shutil.rmtree(staging, ignore_errors=True)

    version_value = release.version or version
    (target / "version.json").write_text(
        json.dumps({"version": version_value, "repo": ZAPRET_REPO, "asset": asset.name},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    try:
        archive.unlink()
    except OSError:
        pass
    log(f"zapret {version_value} installed → {target}")
    return target


def install_cores() -> None:
    for kind in ("xray", "singbox"):
        log(f"downloading {kind} core (latest release)")
        try:
            path = cores.install_core(kind)
            log(f"{kind} installed → {path}")
        except Exception as exc:
            log(f"failed to install {kind}: {exc}")


def install_vendors() -> None:
    from src import updater

    for key in ("happ", "hiddify"):
        log(f"downloading {key} vendor installer (latest release)")
        try:
            result = updater.install(key)
            log(result.get("message", f"{key} downloaded"))
        except Exception as exc:
            log(f"failed to download {key}: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Zentrix engines")
    parser.add_argument("--zapret", action="store_true", help="install Zapret")
    parser.add_argument("--cores", action="store_true", help="install Xray-core and sing-box")
    parser.add_argument("--vendor", action="store_true",
                        help="download official Happ/Hiddify installers (optional)")
    parser.add_argument("--all", action="store_true", help="Zapret + cores")
    parser.add_argument("--zapret-version", default=DEFAULT_ZAPRET_VERSION,
                        help=f"Zapret tag, or 'latest' (default: {DEFAULT_ZAPRET_VERSION})")
    parser.add_argument("--force", action="store_true", help="reinstall Zapret even if present")
    args = parser.parse_args()

    paths.ensure_dirs()
    selected = args.zapret or args.cores or args.vendor or args.all
    if not selected:
        args.zapret = True

    if args.zapret or args.all:
        install_zapret(args.zapret_version, force=args.force)
    if args.cores or args.all:
        install_cores()
    if args.vendor:
        install_vendors()

    log(f"engines directory: {paths.ENGINES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
