"""Safe "clean up extra files" module.

Every candidate is previewed with its size before anything is deleted. The
cleaner refuses to touch paths outside the Zentrix data directory or the
``engines/`` folder, and never removes the engines that are currently in use.
"""

from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable

from . import paths
from .logger import get_logger
from .settings_store import settings

log = get_logger("cleaner")

CATEGORY_LABELS = {
    "cache": "Кэш приложения",
    "sounds": "Кэш звуков",
    "logs": "Старые логи",
    "updates": "Временные файлы обновлений",
    "engines": "Старые версии движков",
    "presets": "Неиспользуемые пресеты",
    "temp": "Временные файлы",
}

CURRENT_ENGINE_NAMES = {"zapret", "happ", "hiddify"}


@dataclass
class CleanItem:
    path: Path
    size: int
    category: str
    reason: str
    is_dir: bool = False

    def as_dict(self) -> dict:
        return {
            "path": str(self.path),
            "size": self.size,
            "category": self.category,
            "reason": self.reason,
            "is_dir": self.is_dir,
        }


@dataclass
class CleanReport:
    items: list[CleanItem] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    scanned_at: float = field(default_factory=time.time)

    @property
    def total_size(self) -> int:
        return sum(item.size for item in self.items)

    def by_category(self) -> dict[str, list[CleanItem]]:
        grouped: dict[str, list[CleanItem]] = {}
        for item in self.items:
            grouped.setdefault(item.category, []).append(item)
        return grouped


def _dir_size(path: Path, budget_seconds: float = 3.0) -> int:
    total = 0
    deadline = time.monotonic() + budget_seconds
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    for root, _dirs, files in os.walk(path):
        if time.monotonic() > deadline:
            break
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total


def _iter_files(folder: Path) -> Iterable[Path]:
    if not folder.exists():
        return []
    try:
        return [item for item in folder.iterdir() if item.is_file()]
    except OSError:
        return []


def _allowed(path: Path) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in (paths.DATA_DIR.resolve(), paths.ENGINES_DIR.resolve()):
        try:
            if resolved == root or resolved.is_relative_to(root):
                return True
        except AttributeError:  # pragma: no cover
            if str(resolved).startswith(str(root)):
                return True
    return False


def _is_current_engine(path: Path) -> bool:
    try:
        relative = path.resolve().relative_to(paths.ENGINES_DIR.resolve())
    except Exception:
        return False
    parts = relative.parts
    return bool(parts) and parts[0].lower() in CURRENT_ENGINE_NAMES and not any(
        marker in part.lower()
        for part in parts[1:]
        for marker in (".old", "bak", "backup", "staging", "update-")
    )


class Cleaner:
    """Scans and removes disposable files. All methods are blocking; call from a worker."""

    def scan(self, *, include_presets: bool = False, include_sound_cache: bool = True,
             older_than_days: int = 3) -> CleanReport:
        report = CleanReport()
        cutoff = time.time() - max(0, older_than_days) * 86_400

        def add(path: Path, category: str, reason: str, *, is_dir: bool = False) -> None:
            if not _allowed(path):
                report.skipped.append(str(path))
                return
            report.items.append(CleanItem(path, _dir_size(path), category, reason, is_dir))

        # Rotated logs (the active zentrix.log is kept).
        for file in _iter_files(paths.LOGS_DIR):
            if file.name == "zentrix.log":
                continue
            if file.suffix in {".log", ".txt", ".dmp", ".old"} or ".log." in file.name:
                add(file, "logs", "Ротация логов")

        # Application cache (excluding the sound cache, which has its own switch).
        for child in list(paths.CACHE_DIR.iterdir()) if paths.CACHE_DIR.exists() else []:
            if child == paths.SOUNDS_CACHE_DIR:
                continue
            try:
                if child.is_dir():
                    add(child, "cache", "Кэш миниатюр и временных данных", is_dir=True)
                elif child.suffix in {".tmp", ".cache", ".bin"}:
                    add(child, "cache", "Файл кэша")
            except OSError:
                continue

        if include_sound_cache:
            for file in _iter_files(paths.SOUNDS_CACHE_DIR):
                if file.suffix == ".wav":
                    add(file, "sounds", "Звук будет сгенерирован заново")

        # Update leftovers.
        for file in _iter_files(paths.DOWNLOADS_DIR):
            try:
                if file.suffix == ".part" or file.stat().st_mtime < cutoff:
                    add(file, "updates", "Загруженный архив обновления")
            except OSError:
                continue
        for child in list(paths.TEMP_DIR.iterdir()) if paths.TEMP_DIR.exists() else []:
            add(child, "temp", "Временная папка обновлений", is_dir=child.is_dir())

        # Old engine snapshots created by the updater.
        if paths.ENGINES_DIR.exists():
            for child in paths.ENGINES_DIR.iterdir():
                name = child.name.lower()
                if not child.is_dir():
                    if child.suffix in {".zip", ".part", ".old"}:
                        add(child, "engines", "Архив/бэкап движка")
                    continue
                if _is_current_engine(child):
                    continue
                if any(marker in name for marker in (".old", "bak", "backup", "staging", "update-")):
                    add(child, "engines", "Старая версия движка", is_dir=True)

        # Unused presets (opt-in, never the active or default one).
        if include_presets and paths.PRESETS_DIR.exists():
            active = str(settings.get("appearance.preset", "") or "")
            for file in _iter_files(paths.PRESETS_DIR):
                if file.suffix != ".json":
                    continue
                if file.stem in {active, "Zentrix Default"}:
                    continue
                try:
                    json.loads(file.read_text(encoding="utf-8"))
                except Exception:
                    add(file, "presets", "Повреждённый пресет")
                    continue
                add(file, "presets", "Пользовательский пресет (не выбран в оформлении)")

        report.items.sort(key=lambda item: (item.category, -item.size))
        log.info("Очистка: найдено %s объектов на %s байт", len(report.items), report.total_size)
        return report

    def delete(self, items: list[CleanItem], progress: Callable[[int, int, str], None] | None = None) -> tuple[int, int, list[str]]:
        removed = 0
        freed = 0
        errors: list[str] = []
        total = len(items)
        for index, item in enumerate(items, start=1):
            if progress:
                progress(index, total, item.path.name)
            if not _allowed(item.path) or _is_current_engine(item.path):
                errors.append(f"Пропущено (защищено): {item.path}")
                continue
            try:
                if item.path.is_dir():
                    shutil.rmtree(item.path)
                else:
                    item.path.unlink()
                removed += 1
                freed += item.size
            except FileNotFoundError:
                removed += 1
                freed += item.size
            except OSError as exc:
                errors.append(f"{item.path.name}: {exc.strerror or exc}")
        settings.set("maintenance.last_clean", int(time.time()))
        settings.set("maintenance.cleaned_total", int(settings.get("maintenance.cleaned_total", 0) or 0) + freed)
        log.info("Очистка завершена: удалено %s объектов, освобождено %s байт", removed, freed)
        return removed, freed, errors

    def auto_clean(self, older_than_days: int | None = None) -> int:
        """Conservative cleanup executed on startup when enabled."""
        days = older_than_days if older_than_days is not None else int(
            settings.get("general.auto_clean_days", 7) or 7
        )
        report = self.scan(include_presets=False, include_sound_cache=False, older_than_days=days)
        safe = [item for item in report.items if item.category in {"logs", "updates", "temp", "engines"}]
        if not safe:
            return 0
        _removed, freed, _errors = self.delete(safe)
        return freed
