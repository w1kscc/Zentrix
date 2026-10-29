"""Build Zentrix: PyInstaller onedir bundle + optional Inno Setup installer.

Usage (from the repository root):

    python scripts/build.py
    python scripts/build.py --skip-installer
    python scripts/build.py --no-engines
    python scripts/build.py --installer-only

Engines are never committed. Whatever exists in ``engines/`` at build time is
copied next to ``Zentrix.exe``; use ``scripts/fetch_engines.py`` first.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src import constants  # noqa: E402

DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_DIST = DIST / "Zentrix"
INSTALLER_DIST = DIST / "installer"
INSTALLER_SCRIPT = ROOT / "installer" / "zentrix.iss"
ICON = ROOT / "assets" / "brand" / "zentrix.ico"

PAGE_MODULES = (
    "src.ui.pages.home",
    "src.ui.pages.zapret",
    "src.ui.pages.happ",
    "src.ui.pages.hiddify",
    "src.ui.pages.proxy_page",
    "src.ui.pages.monitor",
    "src.ui.pages.blockcheck",
    "src.ui.pages.updates",
    "src.ui.pages.settings",
)
HIDDEN_IMPORTS = (*PAGE_MODULES, "PySide6.QtMultimedia", "PySide6.QtNetwork")


def log(message: str) -> None:
    print(f"[build] {message}", flush=True)


def check_environment() -> None:
    if sys.platform != "win32":
        raise SystemExit("Zentrix is Windows-only; build it on Windows.")
    import PyInstaller  # noqa: F401

    if not ICON.exists():
        raise SystemExit(f"Missing icon: {ICON}")
    if not (ROOT / "src" / "main.py").exists():
        raise SystemExit("src/main.py not found")


def version_info_text() -> str:
    version = constants.APP_VERSION
    numbers = [int(part) for part in version.split(".") if part.isdigit()]
    while len(numbers) < 4:
        numbers.append(0)
    file_version = tuple(numbers[:4])
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={file_version},
    prodvers={file_version},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [StringStruct('CompanyName', '{constants.APP_PUBLISHER}'),
         StringStruct('FileDescription', '{constants.APP_DESCRIPTION}'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', 'Zentrix'),
         StringStruct('LegalCopyright', 'Copyright (c) 2026 Zentrix Project. MIT License.'),
         StringStruct('OriginalFilename', 'Zentrix.exe'),
         StringStruct('ProductName', 'Zentrix'),
         StringStruct('ProductVersion', '{version}')])
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def clean() -> None:
    for path in (BUILD, DIST):
        if path.exists():
            log(f"removing {path}")
            shutil.rmtree(path, ignore_errors=True)
    spec = ROOT / "Zentrix.spec"
    if spec.exists():
        spec.unlink()


def run_pyinstaller() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    version_file = BUILD / "version_info.txt"
    version_file.write_text(version_info_text(), encoding="utf-8")

    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--windowed",
        "--noupx",
        "--name", "Zentrix",
        "--icon", str(ICON),
        "--version-file", str(version_file),
        "--add-data", f"{ROOT / 'assets'}{os.pathsep}assets",
        "--paths", str(ROOT),
        "--specpath", str(BUILD),
        "--workpath", str(BUILD / "pyinstaller"),
        "--distpath", str(DIST),
        "--log-level", "WARN",
    ]
    for module in HIDDEN_IMPORTS:
        command.extend(["--hidden-import", module])
    command.append(str(ROOT / "src" / "main.py"))

    log("running PyInstaller (this takes a few minutes)")
    subprocess.run(command, cwd=ROOT, check=True)


def copy_engines() -> None:
    source = ROOT / "engines"
    if not source.exists() or not any(source.iterdir()):
        log("engines/ is empty; the app will offer to download cores at runtime")
        return

    target = APP_DIST / "engines"
    log(f"copying engines → {target}")

    def ignore(directory: str, names: list[str]) -> set[str]:
        skipped = {"__pycache__", ".git", "vendor", "downloads", "temp"}
        return {name for name in names if name in skipped or name.endswith((".log", ".part"))}

    shutil.copytree(source, target, ignore=ignore, dirs_exist_ok=True)


def find_iscc() -> Path | None:
    override = os.environ.get("INNO_SETUP_ISCC")
    candidates = [
        Path(override) if override else None,
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
        / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        / "Inno Setup 6" / "ISCC.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.exists():
            return candidate
    found = shutil.which("ISCC")
    return Path(found) if found else None


def run_installer() -> None:
    if not APP_DIST.exists():
        raise SystemExit("dist/Zentrix is missing; run the full build first")
    iscc = find_iscc()
    if iscc is None:
        raise SystemExit(
            "Inno Setup 6 not found. Install it or set INNO_SETUP_ISCC, "
            "then re-run with --installer-only."
        )
    INSTALLER_DIST.mkdir(parents=True, exist_ok=True)
    command = [
        str(iscc),
        f"/DAppVersion={constants.APP_VERSION}",
        f"/DAppPublisher={constants.APP_PUBLISHER}",
        f"/DAppURL={constants.APP_HOMEPAGE}",
        str(INSTALLER_SCRIPT),
    ]
    log(f"compiling installer with {iscc}")
    subprocess.run(command, cwd=ROOT, check=True)


def report() -> None:
    exe = APP_DIST / "Zentrix.exe"
    if exe.exists():
        log(f"portable: {exe} ({exe.stat().st_size / 1_048_576:.1f} MB exe)")
    setup = INSTALLER_DIST / "ZentrixSetup.exe"
    if setup.exists():
        log(f"installer: {setup} ({setup.stat().st_size / 1_048_576:.1f} MB)")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Zentrix")
    parser.add_argument("--skip-installer", action="store_true",
                        help="build only the portable bundle")
    parser.add_argument("--installer-only", action="store_true",
                        help="reuse dist/Zentrix and compile the installer")
    parser.add_argument("--no-engines", action="store_true",
                        help="do not copy the local engines/ directory")
    parser.add_argument("--no-clean", action="store_true",
                        help="keep previous build/ and dist/ output")
    args = parser.parse_args()

    check_environment()
    if not args.no_clean and not args.installer_only:
        clean()

    if not args.installer_only:
        run_pyinstaller()
        if not args.no_engines:
            copy_engines()

    if not args.skip_installer:
        run_installer()

    report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
