"""Procedural sound synthesis for Zentrix.

No audio files ship with the application: every blip is rendered from sine /
triangle partials with an ADSR envelope, written to a content-addressed WAV
cache and played through QtMultimedia (falling back to winsound).

The cache key is a hash of the synthesis parameters, so changing the tone
profile produces new files while repeat runs reuse the existing ones.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from . import paths
from .logger import get_logger

log = get_logger("sound")

SAMPLE_RATE = 44100
GENERATOR_VERSION = 3

# Base frequencies (Hz) — equal temperament, A4 = 440.
NOTES = {
    "C3": 130.81, "D3": 146.83, "E3": 164.81, "F3": 174.61, "G3": 196.00, "A3": 220.00, "B3": 246.94,
    "C4": 261.63, "D4": 293.66, "E4": 329.63, "F4": 349.23, "G4": 392.00, "A4": 440.00, "B4": 493.88,
    "C5": 523.25, "D5": 587.33, "E5": 659.25, "F5": 698.46, "G5": 783.99, "A5": 880.00, "B5": 987.77,
    "C6": 1046.50, "D6": 1174.66, "E6": 1318.51, "G6": 1567.98,
}

TONE_PROFILES = {
    # name: (partials [(ratio, amplitude)], decay_curve, attack)
    "soft": ([(1.0, 1.0), (2.0, 0.20), (3.0, 0.06)], 2.4, 0.012),
    "standard": ([(1.0, 1.0), (2.0, 0.32), (4.0, 0.10)], 3.2, 0.008),
    "bright": ([(1.0, 1.0), (2.0, 0.45), (3.0, 0.20), (5.0, 0.08)], 4.2, 0.004),
}


@dataclass(frozen=True)
class Note:
    freq: float
    duration: float
    delay: float = 0.0
    gain: float = 1.0


# Recipes are expressed as note sequences; overlapping notes create a chord.
RECIPES: dict[str, list[Note]] = {
    # Ambient chime on startup.
    "startup": [
        Note(NOTES["C5"], 0.85, 0.00, 0.75),
        Note(NOTES["G5"], 0.90, 0.09, 0.55),
        Note(NOTES["E5"], 1.00, 0.18, 0.40),
        Note(NOTES["C6"], 0.80, 0.27, 0.18),
    ],
    "tray": [
        Note(NOTES["E5"], 0.28, 0.00, 0.55),
        Note(NOTES["C5"], 0.45, 0.10, 0.45),
    ],
    "exit": [
        Note(NOTES["G4"], 0.55, 0.00, 0.50),
        Note(NOTES["C4"], 0.95, 0.14, 0.55),
        Note(NOTES["E4"], 0.70, 0.26, 0.25),
    ],
    "enable": [
        Note(NOTES["C5"], 0.22, 0.00, 0.55),
        Note(NOTES["E5"], 0.22, 0.08, 0.55),
        Note(NOTES["G5"], 0.55, 0.16, 0.60),
    ],
    "disable": [
        Note(NOTES["G5"], 0.22, 0.00, 0.50),
        Note(NOTES["E5"], 0.22, 0.08, 0.50),
        Note(NOTES["C5"], 0.48, 0.16, 0.45),
    ],
    "update": [
        Note(NOTES["C6"], 0.30, 0.00, 0.45),
        Note(NOTES["E6"], 0.30, 0.07, 0.40),
        Note(NOTES["G6"], 0.60, 0.14, 0.35),
    ],
    "error": [
        Note(NOTES["A3"], 0.45, 0.00, 0.55),
        Note(NOTES["F3"], 0.65, 0.12, 0.45),
    ],
    "notify": [
        Note(NOTES["A5"], 0.16, 0.00, 0.40),
        Note(NOTES["A5"], 0.30, 0.10, 0.30),
    ],
    "click": [
        Note(NOTES["B5"], 0.045, 0.00, 0.16),
    ],
}


def _adsr(index: int, total: int, attack: float, release: float) -> float:
    t = index / SAMPLE_RATE
    duration = total / SAMPLE_RATE
    if t < attack:
        return t / attack
    remaining = duration - t
    if remaining < release:
        return max(0.0, remaining / release)
    return 1.0


def _render_with_params(event: str, tone: str, params: dict) -> bytes:
    partials, decay, attack = TONE_PROFILES.get(tone, TONE_PROFILES["soft"])
    notes: Iterable[Note] = RECIPES.get(event, RECIPES["notify"])
    notes = list(notes)
    length = max(int((note.delay + note.duration) * SAMPLE_RATE) for note in notes) + int(0.05 * SAMPLE_RATE)
    buffer = [0.0] * length

    for note in notes:
        start = int(note.delay * SAMPLE_RATE)
        total = int(note.duration * SAMPLE_RATE)
        release = min(0.25, note.duration * 0.65)
        for i in range(total):
            t = i / SAMPLE_RATE
            env = _adsr(i, total, attack, release)
            # Exponential body decay keeps the timbre bell-like.
            body = math.exp(-decay * t)
            sample = 0.0
            for ratio, amplitude in partials:
                sample += amplitude * math.sin(2 * math.pi * note.freq * ratio * t)
            # A touch of triangle wave for warmth.
            tri = 2 / math.pi * math.asin(math.sin(2 * math.pi * note.freq * t))
            sample = sample * 0.82 + tri * 0.18
            buffer[start + i] += sample * env * body * note.gain * 0.24

    # Gentle stereo-free soft clip + normalisation.
    peak = max(1e-9, max(abs(value) for value in buffer))
    scale = min(1.0, 0.92 / peak)
    frames = bytearray()
    for value in buffer:
        frames += struct.pack("<h", int(max(-1.0, min(1.0, value * scale)) * 32000))
    return bytes(frames)


def _cache_key(event: str, tone: str) -> str:
    payload = json.dumps(
        {"event": event, "tone": tone, "version": GENERATOR_VERSION, "rate": SAMPLE_RATE},
        sort_keys=True,
    )
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


class SoundManager:
    """Synthesises, caches and plays UI sounds."""

    def __init__(self, tone: str = "soft", volume: int = 40, enabled: bool = True) -> None:
        self.tone = tone if tone in TONE_PROFILES else "soft"
        self.volume = max(0, min(100, int(volume)))
        self.enabled = bool(enabled)
        self._effects: dict[str, object] = {}
        self._players_ready = False
        paths.ensure_dirs()

    # ---------------------------------------------------------------- config
    def configure(self, *, tone: str | None = None, volume: int | None = None,
                  enabled: bool | None = None) -> None:
        if tone is not None and tone in TONE_PROFILES:
            self.tone = tone
        if volume is not None:
            self.volume = max(0, min(100, int(volume)))
        if enabled is not None:
            self.enabled = bool(enabled)
        for name, effect in self._effects.items():
            try:
                effect.setVolume(self.volume / 100.0)  # type: ignore[attr-defined]
                effect.setMuted(not self.enabled)  # type: ignore[attr-defined]
            except Exception:
                pass

    # ---------------------------------------------------------------- paths
    def path_for(self, event: str) -> Path:
        return paths.SOUNDS_CACHE_DIR / f"{event}_{self.tone}_{_cache_key(event, self.tone)}.wav"

    def ensure_generated(self, events: Iterable[str] | None = None, *, force: bool = False) -> int:
        """Generate missing sounds. Returns the number of files written."""
        written = 0
        for event in events or RECIPES.keys():
            target = self.path_for(event)
            if target.exists() and not force:
                continue
            try:
                frames = _render_with_params(event, self.tone, {})
                with wave.open(str(target), "wb") as handle:
                    handle.setnchannels(1)
                    handle.setsampwidth(2)
                    handle.setframerate(SAMPLE_RATE)
                    handle.writeframes(frames)
                written += 1
            except Exception as exc:  # pragma: no cover - disk issues
                log.warning("Не удалось сгенерировать звук %s: %s", event, exc)
        return written

    def clear_cache(self) -> int:
        removed = 0
        for file in paths.SOUNDS_CACHE_DIR.glob("*.wav"):
            try:
                file.unlink()
                removed += 1
            except OSError:
                pass
        self.invalidate()
        return removed

    def invalidate(self) -> None:
        """Forget cached QSoundEffect objects (e.g. after the cache was cleaned)."""
        self._effects.clear()
        self._players_ready = False

    def regenerate_all(self) -> int:
        self.clear_cache()
        return self.ensure_generated(force=True)

    # ---------------------------------------------------------------- play
    def play(self, event: str) -> None:
        if not self.enabled or self.volume <= 0:
            return
        target = self.path_for(event)
        if not target.exists():
            if self.ensure_generated([event]) == 0:
                return
        try:
            if not self._players_ready:
                self._init_players()
            effect = self._effects.get(event)
            if effect is None:
                self._effects[event] = effect = self._create_effect(target)
            effect.play()  # type: ignore[attr-defined]
            return
        except Exception:
            pass
        # Fallback: system async playback (no per-app volume control).
        try:
            import winsound
            winsound.PlaySound(str(target), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
        except Exception:
            pass

    def _init_players(self) -> None:
        from PySide6.QtMultimedia import QSoundEffect  # lazy, heavy import

        self._QSoundEffect = QSoundEffect
        self._players_ready = True

    def _create_effect(self, path: Path):
        from PySide6.QtCore import QUrl

        effect = self._QSoundEffect()
        effect.setSource(QUrl.fromLocalFile(str(path)))
        effect.setVolume(self.volume / 100.0)
        effect.setMuted(not self.enabled)
        return effect

    # ------------------------------------------------------------ preview
    def preview(self, event: str = "notify") -> None:
        self.ensure_generated([event])
        self.play(event)

    def describe(self) -> dict[str, object]:
        return {
            "tone": self.tone,
            "volume": self.volume,
            "enabled": self.enabled,
            "cached_files": len(list(paths.SOUNDS_CACHE_DIR.glob("*.wav"))),
        }
