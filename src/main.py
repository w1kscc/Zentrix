"""Zentrix entry point: single instance, fast start, window and tray."""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication, QIcon
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from src import constants, paths, winapi
from src.cleaner import Cleaner
from src.logger import get_logger, setup_logging
from src.settings_store import settings
from src.sound_generator import SoundManager
from src.ui.context import AppContext

SERVER_NAME = "Zentrix.SingleInstance.v1"
MUTEX_NAME = "Local\\Zentrix.SingleInstance.v1"
ERROR_ALREADY_EXISTS = 183

log = get_logger("main")


def _acquire_mutex():
    """Return (handle, already_running) using a Windows named mutex."""
    if sys.platform != "win32":
        return None, False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.restype = ctypes.c_void_p
        kernel32.CreateMutexW.argtypes = (ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p)
        handle = kernel32.CreateMutexW(None, False, MUTEX_NAME)
        return handle, ctypes.get_last_error() == ERROR_ALREADY_EXISTS
    except Exception:
        return None, False


def _signal_existing_instance(timeout: float = 2.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        socket = QLocalSocket()
        socket.connectToServer(SERVER_NAME)
        if socket.waitForConnected(250):
            socket.write(b"show")
            socket.flush()
            socket.waitForBytesWritten(300)
            socket.disconnectFromServer()
            return True
        socket.abort()
        time.sleep(0.1)
    return False


def _install_exception_hook(window_holder: list) -> None:
    def _hook(exc_type, exc_value, exc_tb):
        log.error("Необработанное исключение", exc_info=(exc_type, exc_value, exc_tb))
        window = window_holder[0] if window_holder else None
        try:
            if window is not None:
                window.ctx.notify(f"Внутренняя ошибка: {exc_value}", "err", "error")
        except Exception:
            pass

    sys.excepthook = _hook


def _post_start(window, sound: SoundManager, context: AppContext, minimized: bool) -> None:
    """Work that must not delay the first painted frame."""
    if not minimized:
        QTimer.singleShot(260, lambda: sound.play("startup"))

    def _warm_sounds() -> None:
        try:
            sound.ensure_generated()
        except Exception:
            log.exception("Не удалось прогреть кэш звуков")

    threading.Thread(target=_warm_sounds, daemon=True, name="sound-warmup").start()

    if bool(settings.get("general.auto_clean", False)):
        def _auto_clean() -> None:
            try:
                freed = Cleaner().auto_clean()
                if freed:
                    log.info("Автоочистка освободила %s байт", freed)
            except Exception:
                log.exception("Автоочистка не удалась")

        threading.Thread(target=_auto_clean, daemon=True, name="auto-clean").start()

    QTimer.singleShot(900, context.autostart_engines)


def main() -> int:
    setup_logging()
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                f"Zentrix.{constants.APP_VERSION}"
            )
        except Exception:
            pass

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName(constants.APP_NAME)
    app.setApplicationDisplayName(constants.APP_DISPLAY_NAME)
    app.setApplicationVersion(constants.APP_VERSION)
    app.setOrganizationName(constants.APP_PUBLISHER)
    app.setStyle("Fusion")
    app.setQuitOnLastWindowClosed(False)
    icon_file = paths.BRAND_DIR / "zentrix.ico"
    if icon_file.exists():
        app.setWindowIcon(QIcon(str(icon_file)))

    _mutex, already_running = _acquire_mutex()
    if already_running:
        if not _signal_existing_instance():
            log.info("Второй экземпляр Zentrix уже запущен")
        return 0

    paths.ensure_dirs()
    sound_data = settings.section("sounds")
    sound = SoundManager(
        tone=str(sound_data.get("tone", "soft") or "soft"),
        volume=int(sound_data.get("volume", 40) or 0),
        enabled=bool(sound_data.get("enabled", True)),
    )
    if sound.enabled and sound.volume > 0:
        sound.ensure_generated(["startup"])

    context = AppContext(app, sound)

    from src.ui.main_window import MainWindow

    window_holder: list = []
    _install_exception_hook(window_holder)
    window = MainWindow(context)
    window_holder.append(window)

    server = QLocalServer(window)
    QLocalServer.removeServer(SERVER_NAME)
    if not server.listen(SERVER_NAME):
        log.warning("Не удалось открыть канал единственного экземпляра: %s", server.errorString())
    else:
        def _on_connection() -> None:
            while server.hasPendingConnections():
                connection = server.nextPendingConnection()
                if connection is not None:
                    connection.readyRead.connect(connection.deleteLater)
                    connection.disconnected.connect(connection.deleteLater)
            window.show_window()

        server.newConnection.connect(_on_connection)

    requested_minimized = "--minimized" in sys.argv[1:]
    minimized = requested_minimized or bool(settings.get("general.start_minimized", False))
    if minimized and window.tray.is_visible():
        window.hide()
        QTimer.singleShot(600, lambda: window.tray.notify(
            "Zentrix работает в трее — двойной клик откроет окно", "info"
        ))
    else:
        minimized = False
        window.show()

    _post_start(window, sound, context, minimized)
    app.aboutToQuit.connect(context.shutdown)
    log.info("Zentrix %s запущен", constants.APP_VERSION)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
