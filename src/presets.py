"""Named appearance/sound presets stored as portable JSON files."""

from __future__ import annotations

import copy
import json
import re
import time
from pathlib import Path

from . import paths
from .logger import get_logger
from .settings_store import DEFAULTS, settings

log = get_logger("presets")

DEFAULT_NAME = "Zentrix Default"
RESERVED = {DEFAULT_NAME.lower(), "default", "по умолчанию"}


def _slug(name: str) -> str:
    cleaned = re.sub(r"[^\w\s\-а-яА-ЯёЁ]", "", name, flags=re.UNICODE).strip()
    return re.sub(r"\s+", " ", cleaned)[:48] or f"preset-{int(time.time())}"


def default_preset() -> dict:
    return {
        "name": DEFAULT_NAME,
        "version": 1,
        "builtin": True,
        "created_at": 0,
        "appearance": copy.deepcopy(DEFAULTS["appearance"]),
        "sounds": copy.deepcopy(DEFAULTS["sounds"]),
    }


class PresetStore:
    def __init__(self) -> None:
        paths.ensure_dirs()

    def names(self) -> list[str]:
        names = [DEFAULT_NAME]
        for file in sorted(paths.PRESETS_DIR.glob("*.json")):
            try:
                data = json.loads(file.read_text(encoding="utf-8"))
                name = str(data.get("name") or file.stem)
            except Exception:
                name = file.stem
            if name not in names:
                names.append(name)
        return names

    def path_for(self, name: str) -> Path:
        return paths.PRESETS_DIR / f"{_slug(name)}.json"

    def save(self, name: str) -> Path:
        name = (name or "").strip()
        if not name:
            raise ValueError("Пустое имя пресета")
        if name.lower() in RESERVED:
            raise ValueError("Это имя зарезервировано для встроенного пресета")
        payload = {
            "name": name,
            "version": 1,
            "created_at": int(time.time()),
            "appearance": settings.section("appearance"),
            "sounds": settings.section("sounds"),
        }
        target = self.path_for(name)
        target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        log.info("Пресет сохранён: %s", target.name)
        return target

    def load(self, name: str) -> dict:
        if name == DEFAULT_NAME:
            return default_preset()
        path = self.path_for(name)
        if not path.exists():
            # Allow loading by file stem even if the display name differs.
            matches = list(paths.PRESETS_DIR.glob("*.json"))
            path = next((item for item in matches if item.stem == name), path)
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("appearance", {})
        data.setdefault("sounds", {})
        return data

    def apply(self, name: str) -> dict:
        data = self.load(name)
        merged_appearance = copy.deepcopy(DEFAULTS["appearance"])
        merged_appearance.update(data.get("appearance", {}))
        merged_sounds = copy.deepcopy(DEFAULTS["sounds"])
        merged_sounds.update(data.get("sounds", {}))
        merged_appearance["preset"] = data.get("name", name)
        settings.replace_section("appearance", merged_appearance)
        settings.replace_section("sounds", merged_sounds)
        return data

    def delete(self, name: str) -> bool:
        if name == DEFAULT_NAME:
            return False
        path = self.path_for(name)
        if path.exists():
            path.unlink()
            return True
        for item in paths.PRESETS_DIR.glob("*.json"):
            if item.stem == name:
                item.unlink()
                return True
        return False

    def export(self, name: str, destination: str | Path) -> Path:
        destination = Path(destination)
        data = self.load(name)
        destination.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return destination

    def import_file(self, source: str | Path) -> str:
        source = Path(source)
        data = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or ("appearance" not in data and "sounds" not in data):
            raise ValueError("Файл не похож на пресет Zentrix")
        name = str(data.get("name") or source.stem)
        if name.lower() in RESERVED:
            name = f"{name} (импорт)"
        target = self.path_for(name)
        data["name"] = name
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return name


presets = PresetStore()
