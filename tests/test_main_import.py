"""Smoke-test the frozen entry point's imports.

PyInstaller users hit import errors that unit tests miss when a symbol lives in
a different Qt module; importing ``src.main`` here catches that early.
"""

from __future__ import annotations

import importlib


def test_entry_point_imports() -> None:
    module = importlib.import_module("src.main")
    assert callable(module.main)
