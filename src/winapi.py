"""Thin, defensive ctypes bindings for the Windows APIs Zentrix needs.

Every function is safe to import on non-Windows platforms (it simply reports
"unsupported"), which keeps the unit tests portable.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes as wt
import json
import os
import socket
import struct
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from . import paths

IS_WINDOWS = sys.platform == "win32"

CREATE_NO_WINDOW = 0x08000000 if IS_WINDOWS else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if IS_WINDOWS else 0
SW_SHOWNORMAL = 1

if IS_WINDOWS:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    iphlpapi = ctypes.WinDLL("iphlpapi", use_last_error=True)
    wininet = ctypes.WinDLL("wininet", use_last_error=True)
else:  # pragma: no cover - only used by tests on non-Windows hosts
    kernel32 = shell32 = user32 = iphlpapi = wininet = None


# --------------------------------------------------------------------------- admin
def is_admin() -> bool:
    if not IS_WINDOWS:
        return False
    try:
        return bool(shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin(extra_args: list[str] | None = None) -> bool:
    """Re-launch the current executable elevated. Returns True on success."""
    if not IS_WINDOWS:
        return False
    try:
        if getattr(sys, "frozen", False):
            exe = sys.executable
            args = " ".join(extra_args or [])
        else:
            exe = sys.executable
            module = Path(sys.argv[0]).resolve()
            args = f'"{module}" ' + " ".join(f'"{a}"' for a in (extra_args or []))
        result = shell32.ShellExecuteW(None, "runas", exe, args, str(Path.cwd()), SW_SHOWNORMAL)
        return int(result) > 32
    except Exception:
        return False


# ----------------------------------------------------------------------- processes
@dataclass(frozen=True)
class ProcessInfo:
    pid: int
    name: str


def list_processes() -> list[ProcessInfo]:
    if not IS_WINDOWS:
        return []
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wt.DWORD),
            ("cntUsage", wt.DWORD),
            ("th32ProcessID", wt.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wt.DWORD),
            ("cntThreads", wt.DWORD),
            ("th32ParentProcessID", wt.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wt.DWORD),
            ("szExeFile", wt.WCHAR * 260),
        ]

    processes: list[ProcessInfo] = []
    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot in (0, -1):
        return processes
    try:
        entry = PROCESSENTRY32W()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return processes
        while True:
            processes.append(ProcessInfo(entry.th32ProcessID, entry.szExeFile))
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return processes


def find_processes(name: str) -> list[int]:
    name = name.lower()
    return [p.pid for p in list_processes() if p.name.lower() == name]


def is_pid_alive(pid: int) -> bool:
    if not IS_WINDOWS or pid <= 0:
        return False
    handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED_INFORMATION
    if not handle:
        return False
    try:
        code = wt.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == 259  # STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def process_exe_path(pid: int) -> str:
    if not IS_WINDOWS or pid <= 0:
        return ""
    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return ""
    try:
        size = wt.DWORD(1024)
        buffer = ctypes.create_unicode_buffer(1024)
        if kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return buffer.value
    finally:
        kernel32.CloseHandle(handle)
    return ""


def process_name(pid: int) -> str:
    path = process_exe_path(pid)
    return Path(path).name if path else f"PID {pid}"


@dataclass
class IoCounters:
    read_bytes: int = 0
    write_bytes: int = 0
    other_bytes: int = 0

    @property
    def total(self) -> int:
        return self.read_bytes + self.write_bytes + self.other_bytes


def process_io(pid: int) -> IoCounters | None:
    if not IS_WINDOWS or pid <= 0:
        return None

    class IO_COUNTERS(ctypes.Structure):
        _fields_ = [
            ("ReadOperationCount", ctypes.c_ulonglong),
            ("WriteOperationCount", ctypes.c_ulonglong),
            ("OtherOperationCount", ctypes.c_ulonglong),
            ("ReadTransferCount", ctypes.c_ulonglong),
            ("WriteTransferCount", ctypes.c_ulonglong),
            ("OtherTransferCount", ctypes.c_ulonglong),
        ]

    handle = kernel32.OpenProcess(0x1000, False, pid)
    if not handle:
        return None
    try:
        counters = IO_COUNTERS()
        if kernel32.GetProcessIoCounters(handle, ctypes.byref(counters)):
            return IoCounters(
                counters.ReadTransferCount,
                counters.WriteTransferCount,
                counters.OtherTransferCount,
            )
    finally:
        kernel32.CloseHandle(handle)
    return None


def kill_tree(pid: int, timeout: float = 5.0) -> None:
    """Terminate a process and all children without showing a console."""
    if not IS_WINDOWS or pid <= 0:
        return
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            creationflags=CREATE_NO_WINDOW,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except Exception:
        try:
            handle = kernel32.OpenProcess(0x0001, False, pid)  # PROCESS_TERMINATE
            if handle:
                kernel32.TerminateProcess(handle, 1)
                kernel32.CloseHandle(handle)
        except Exception:
            pass


# ------------------------------------------------------------------------ traffic
@dataclass
class InterfaceStats:
    index: int
    alias: str
    description: str
    received: int
    sent: int


def interface_stats() -> list[InterfaceStats]:
    """Cumulative byte counters for connected, non-loopback interfaces."""
    try:
        import psutil

        states = psutil.net_if_stats()
        counters = psutil.net_io_counters(pernic=True)
        result: list[InterfaceStats] = []
        for index, (name, snapshot) in enumerate(counters.items(), start=1):
            info = states.get(name)
            if name.lower().startswith(("loopback", "lo")) or (info and not info.isup):
                continue
            result.append(
                InterfaceStats(
                    index=index,
                    alias=name,
                    description=name,
                    received=int(snapshot.bytes_recv),
                    sent=int(snapshot.bytes_sent),
                )
            )
        return result
    except Exception:
        return []


@dataclass(frozen=True)
class TcpConnection:
    pid: int
    local: str
    remote: str
    state: str

    @property
    def remote_host(self) -> str:
        return self.remote.rsplit(":", 1)[0] if ":" in self.remote else self.remote


TCP_STATES = {
    1: "CLOSED", 2: "LISTEN", 3: "SYN_SENT", 4: "SYN_RECV", 5: "ESTABLISHED",
    6: "FIN_WAIT1", 7: "FIN_WAIT2", 8: "CLOSE_WAIT", 9: "CLOSING",
    10: "LAST_ACK", 11: "TIME_WAIT", 12: "DELETE_TCB",
}

MIB_TCP_TABLE_OWNER_PID_ALL = 5
AF_INET = 2


def tcp_connections(established_only: bool = True) -> list[TcpConnection]:
    if not IS_WINDOWS:
        return []

    class MIB_TCPROW_OWNER_PID(ctypes.Structure):
        _fields_ = [
            ("dwState", wt.DWORD),
            ("dwLocalAddr", wt.DWORD),
            ("dwLocalPort", wt.DWORD),
            ("dwRemoteAddr", wt.DWORD),
            ("dwRemotePort", wt.DWORD),
            ("dwOwningPid", wt.DWORD),
        ]

    size = wt.DWORD(0)
    iphlpapi.GetExtendedTcpTable(None, ctypes.byref(size), False, AF_INET,
                                 MIB_TCP_TABLE_OWNER_PID_ALL, 0)
    if size.value == 0:
        return []
    buffer = ctypes.create_string_buffer(size.value)
    result = iphlpapi.GetExtendedTcpTable(buffer, ctypes.byref(size), False, AF_INET,
                                          MIB_TCP_TABLE_OWNER_PID_ALL, 0)
    if result != 0:
        return []
    count = ctypes.cast(buffer, ctypes.POINTER(wt.DWORD)).contents.value
    array = ctypes.cast(
        ctypes.byref(buffer, 4), ctypes.POINTER(MIB_TCPROW_OWNER_PID * count)
    ).contents
    connections: list[TcpConnection] = []
    for index in range(count):
        row = array[index]
        if established_only and row.dwState != 5:
            continue
        local_ip = socket.inet_ntoa(struct.pack("<I", row.dwLocalAddr))
        remote_ip = socket.inet_ntoa(struct.pack("<I", row.dwRemoteAddr))
        local_port = struct.unpack("<H", struct.pack("<I", row.dwLocalPort)[:2])[0]
        remote_port = struct.unpack("<H", struct.pack("<I", row.dwRemotePort)[:2])[0]
        connections.append(
            TcpConnection(
                pid=int(row.dwOwningPid),
                local=f"{local_ip}:{local_port}",
                remote=f"{remote_ip}:{remote_port}",
                state=TCP_STATES.get(row.dwState, str(row.dwState)),
            )
        )
    return connections


# ------------------------------------------------------------------------ proxy
INTERNET_OPTION_REFRESH = 37
INTERNET_OPTION_SETTINGS_CHANGED = 39
_PROXY_BACKUP_FILE = paths.DATA_DIR / "system-proxy-backup.json"


def _read_system_proxy_state() -> dict[str, object]:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_QUERY_VALUE) as key:
        try:
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            enabled_exists = True
        except FileNotFoundError:
            enabled, enabled_exists = 0, False
        try:
            server, _ = winreg.QueryValueEx(key, "ProxyServer")
            server_exists = True
        except FileNotFoundError:
            server, server_exists = "", False
    return {"enabled": bool(enabled), "enabled_exists": enabled_exists,
            "server": str(server), "server_exists": server_exists}


def _write_system_proxy_state(state: dict[str, object]) -> bool:
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            if state.get("enabled_exists", True):
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD,
                                  1 if state.get("enabled") else 0)
            else:
                try:
                    winreg.DeleteValue(key, "ProxyEnable")
                except FileNotFoundError:
                    pass
            if state.get("server_exists", True):
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ,
                                  str(state.get("server", "")))
            else:
                try:
                    winreg.DeleteValue(key, "ProxyServer")
                except FileNotFoundError:
                    pass
        wininet.InternetSetOptionW(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
        wininet.InternetSetOptionW(None, INTERNET_OPTION_REFRESH, None, 0)
        return True
    except Exception:
        return False


def restore_stale_system_proxy() -> bool:
    """Restore the user's previous WinINET values after an unclean exit."""
    if not IS_WINDOWS or not _PROXY_BACKUP_FILE.exists():
        return False
    try:
        state = json.loads(_PROXY_BACKUP_FILE.read_text(encoding="utf-8"))
        if not isinstance(state, dict):
            return False
        current = _read_system_proxy_state()
        expected_server = str(state.get("zentrix_server", ""))
        if not current.get("enabled") or current.get("server") != expected_server:
            # The user changed the proxy after Zentrix exited; preserve that choice.
            _PROXY_BACKUP_FILE.unlink(missing_ok=True)
            return False
        if not _write_system_proxy_state(state):
            return False
        _PROXY_BACKUP_FILE.unlink(missing_ok=True)
        return True
    except Exception:
        return False


def set_system_proxy(enable: bool, server: str = "") -> bool:
    """Configure the per-user WinINET proxy (browsers and most desktop apps)."""
    if not IS_WINDOWS:
        return False
    import winreg

    key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
    try:
        if enable and not _PROXY_BACKUP_FILE.exists():
            original = _read_system_proxy_state()
            original["zentrix_server"] = server
            _PROXY_BACKUP_FILE.parent.mkdir(parents=True, exist_ok=True)
            _PROXY_BACKUP_FILE.write_text(json.dumps(original), encoding="utf-8")
        elif enable and _PROXY_BACKUP_FILE.exists():
            original = json.loads(_PROXY_BACKUP_FILE.read_text(encoding="utf-8"))
            original["zentrix_server"] = server
            _PROXY_BACKUP_FILE.write_text(json.dumps(original), encoding="utf-8")
        if not enable and _PROXY_BACKUP_FILE.exists():
            try:
                original = json.loads(_PROXY_BACKUP_FILE.read_text(encoding="utf-8"))
            except Exception:
                original = None
            if isinstance(original, dict):
                current = _read_system_proxy_state()
                expected_server = str(original.get("zentrix_server", ""))
                if current.get("enabled") and current.get("server") == expected_server:
                    if not _write_system_proxy_state(original):
                        return False
                # Preserve changes made manually while Zentrix was connected.
                _PROXY_BACKUP_FILE.unlink(missing_ok=True)
                return True
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1 if enable else 0)
            if enable and server:
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, server)
        wininet.InternetSetOptionW(None, INTERNET_OPTION_SETTINGS_CHANGED, None, 0)
        wininet.InternetSetOptionW(None, INTERNET_OPTION_REFRESH, None, 0)
        return True
    except Exception:
        return False


def autostart_command() -> str:
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    entry = Path(sys.argv[0]).resolve()
    return f'"{sys.executable}" "{entry}" --minimized'


def set_autostart(enable: bool) -> bool:
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        ) as key:
            if enable:
                winreg.SetValueEx(key, "Zentrix", 0, winreg.REG_SZ, autostart_command())
            else:
                try:
                    winreg.DeleteValue(key, "Zentrix")
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


def is_autostart_enabled() -> bool:
    if not IS_WINDOWS:
        return False
    import winreg

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "Zentrix")
            return bool(value)
    except Exception:
        return False


# ------------------------------------------------------------------------ dns
def active_interface_alias() -> str:
    """Best-effort name of the interface carrying the default route."""
    if not IS_WINDOWS:
        return ""
    try:
        import psutil

        local_ip = ""
        try:
            probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                probe.connect(("8.8.8.8", 80))
                local_ip = probe.getsockname()[0]
            finally:
                probe.close()
        except OSError:
            local_ip = ""
        stats = psutil.net_if_stats()
        addrs = psutil.net_if_addrs()
        if local_ip:
            for name, entries in addrs.items():
                if any(entry.address == local_ip for entry in entries):
                    return name
        for name, snapshot in stats.items():
            if snapshot.isup and not name.lower().startswith(("loopback", "lo")):
                return name
    except Exception:
        return ""
    return ""


def set_dns(primary: str, secondary: str = "") -> tuple[bool, str]:
    """Switch IPv4 DNS of the active adapter (requires administrator rights)."""
    if not IS_WINDOWS:
        return False, "Поддерживается только Windows"
    if not is_admin():
        return False, "Требуются права администратора"
    alias = active_interface_alias()
    if not alias:
        return False, "Не удалось определить активный сетевой интерфейс"
    base = ["netsh", "interface", "ipv4"]
    commands = [
        [*base, "set", "dnsservers", f"name={alias}", "static", primary, "primary"],
    ]
    if secondary:
        commands.append(
            [*base, "add", "dnsservers", f"name={alias}", secondary, "index=2"]
        )
    try:
        for command in commands:
            completed = subprocess.run(
                command, capture_output=True, text=True, timeout=20,
                creationflags=CREATE_NO_WINDOW,
            )
            if completed.returncode != 0:
                message = (completed.stderr or completed.stdout or "").strip()
                return False, message[:180] or f"netsh завершился с кодом {completed.returncode}"
        subprocess.run(
            ["ipconfig", "/flushdns"], capture_output=True, text=True, timeout=15,
            creationflags=CREATE_NO_WINDOW,
        )
        return True, alias
    except Exception as exc:
        return False, str(exc)[:180]


# ------------------------------------------------------------------------ misc
def set_dark_titlebar(hwnd: int, dark: bool = True) -> None:
    """Best-effort immersive dark mode for the native frame (Win10 2004+)."""
    if not IS_WINDOWS or not hwnd:
        return
    try:
        value = ctypes.c_int(1 if dark else 0)
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                wt.HWND(hwnd), attribute, ctypes.byref(value), ctypes.sizeof(value)
            ) == 0:
                break
    except Exception:
        pass


def open_in_explorer(path: str | Path) -> None:
    try:
        os.startfile(str(path))  # type: ignore[attr-defined]
    except Exception:
        pass
