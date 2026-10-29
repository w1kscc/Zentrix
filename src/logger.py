"""Rotating file logging plus a small in-memory tail for the UI."""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from collections import deque

from . import paths

_BUFFER: deque[str] = deque(maxlen=500)
_BUFFER_LOCK = threading.Lock()
_CONFIGURED = False


class _RingHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:
            return
        with _BUFFER_LOCK:
            _BUFFER.append(message)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    global _CONFIGURED
    logger = logging.getLogger("zentrix")
    if _CONFIGURED:
        return logger
    _CONFIGURED = True
    paths.ensure_dirs()
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-7s %(name)s: %(message)s", datefmt="%H:%M:%S"
    )
    try:
        file_handler = logging.handlers.RotatingFileHandler(
            paths.LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except OSError:
        pass

    ring = _RingHandler()
    ring.setFormatter(formatter)
    logger.addHandler(ring)

    if sys.stderr is not None and not getattr(sys, "frozen", False):
        stream = logging.StreamHandler(sys.stderr)
        stream.setFormatter(formatter)
        logger.addHandler(stream)
    return logger


def get_logger(name: str = "zentrix") -> logging.Logger:
    return logging.getLogger(name if name.startswith("zentrix") else f"zentrix.{name}")


def tail(limit: int = 200) -> list[str]:
    with _BUFFER_LOCK:
        return list(_BUFFER)[-limit:]
