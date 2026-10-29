"""Zapret engine wrapper.

Instead of executing the upstream ``.bat`` files (which call ``start`` and
would pop a console window) Zentrix parses a strategy, fully expands its
variables and launches ``winws.exe`` directly with CREATE_NO_WINDOW.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import Signal

from .. import paths, winapi
from ..logger import get_logger
from ..settings_store import settings
from .base import BaseEngine, EngineError

log = get_logger("zapret")

VAR_RE = re.compile(r"%([A-Za-z_][A-Za-z0-9_]*)%")
TILDE_RE = re.compile(r"%~(?:dp|f|n|nx|p|x|s|a|t|z|d|dp0)[^%\s]*", re.IGNORECASE)
DELAYED_RE = re.compile(r"!([A-Za-z_][A-Za-z0-9_]*)!")
SET_RE = re.compile(r'^\s*set\s+(?:"([^"=]+)=([^"]*)"|([^=\s]+)=(.*?))\s*$', re.IGNORECASE)

# Upstream service.bat normally creates these on first launch through its
# load_user_lists routine. Zentrix parses strategy .bat files directly, so it
# must provide the same defaults or winws exits with "cannot access ipset file".
USER_LIST_DEFAULTS: dict[str, tuple[str, ...]] = {
    "ipset-exclude-user.txt": ("203.0.113.113/32",),
    "list-general-user.txt": ("# Never leave this file empty", "domain.example.abc"),
    "list-exclude-user.txt": ("domain.example.abc",),
}


def ensure_user_lists(folder: Path) -> list[Path]:
    """Create the upstream ``*-user.txt`` list defaults that winws expects.

    Existing files are never touched: they belong to the user. Returns the
    files that were created during this call.
    """
    lists_dir = folder / "lists"
    created: list[Path] = []
    for name, lines in USER_LIST_DEFAULTS.items():
        target = lists_dir / name
        if target.exists():
            continue
        try:
            lists_dir.mkdir(parents=True, exist_ok=True)
            target.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8", newline="")
            created.append(target)
        except OSError as exc:
            log.warning("Не удалось создать список %s: %s", target, exc)
    if created:
        log.info("Созданы пользовательские списки Zapret: %s",
                 ", ".join(item.name for item in created))
    return created


@dataclass
class ParsedCommand:
    executable: Path
    args: list[str]
    cwd: Path
    unresolved: list[str] = field(default_factory=list)
    raw_line: str = ""

    @property
    def argv(self) -> list[str]:
        return [str(self.executable), *self.args]

    def preview(self, limit: int = 160) -> str:
        joined = " ".join(self.args)
        return joined if len(joined) <= limit else joined[: limit - 1] + "…"


@dataclass(frozen=True)
class Strategy:
    name: str
    filename: str
    path: Path
    size: int

    @property
    def complexity(self) -> str:
        lowered = self.name.lower()
        if "fake tls" in lowered:
            return "Fake TLS"
        if "simple" in lowered:
            return "Simple"
        if "alt" in lowered:
            return "ALT"
        if "exp" in lowered:
            return "Experimental"
        return "General"


def split_windows_args(text: str) -> list[str]:
    """Split a Windows command line into arguments (quotes, no shell escapes)."""
    args: list[str] = []
    current: list[str] = []
    in_quotes = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == '"':
            in_quotes = not in_quotes
        elif char.isspace() and not in_quotes:
            if current:
                args.append("".join(current))
                current = []
        else:
            current.append(char)
        index += 1
    if current:
        args.append("".join(current))
    return args


def read_bat(path: Path) -> str:
    for encoding in ("utf-8-sig", "cp866", "cp1251"):
        try:
            return path.read_text(encoding=encoding).replace("\r\n", "\n")
        except UnicodeDecodeError:
            continue
        except OSError:
            break
    try:
        return path.read_bytes().decode("utf-8", errors="replace").replace("\r\n", "\n")
    except OSError:
        return ""


def parse_bat(path: Path) -> ParsedCommand:
    text = read_bat(path)
    if not text:
        raise EngineError(f"Не удалось прочитать стратегию {path.name}", "unreadable")
    base = path.parent
    bin_dir = base / "bin"
    lists_dir = base / "lists"

    # Join caret continuations before parsing so a strategy is one long line.
    text = re.sub(r"\^\s*\n", " ", text)
    lines = [line for line in text.split("\n") if not re.match(r"^\s*(::|rem\b)", line, re.IGNORECASE)]

    variables: dict[str, str] = {
        "BIN": str(bin_dir) + "\\",
        "LISTS": str(lists_dir) + "\\",
        "GAMEFILTER": "12",
        "GAMEFILTERTCP": "12",
        "GAMEFILTERUDP": "12",
    }
    # Upstream stores game-filter settings in utils/game_filter.enabled; when the
    # toggle is off every strategy uses port 12 (an unused port) so the game
    # rules stay inert.
    game_flag = base / "utils" / "game_filter.enabled"
    if game_flag.exists():
        variables["GAMEFILTERTCP"] = "1024-65535"
        variables["GAMEFILTERUDP"] = "1024-65535"
        try:
            for raw in game_flag.read_text(encoding="utf-8", errors="replace").splitlines():
                if "=" not in raw:
                    continue
                key, value = raw.split("=", 1)
                key = key.strip().lower()
                if key in {"tcp", "tcp_range"}:
                    variables["GAMEFILTERTCP"] = value.strip() or "1024-65535"
                elif key in {"udp", "udp_range"}:
                    variables["GAMEFILTERUDP"] = value.strip() or "1024-65535"
        except OSError:
            pass
    for line in lines:
        match = SET_RE.match(line)
        if not match:
            continue
        key = (match.group(1) or match.group(3) or "").strip().upper()
        value = match.group(2) if match.group(1) else (match.group(4) or "")
        if not key or key in {"LOCAL_VERSION", "SERVICENAME", "SRVCNAME", "CHOICE", "MENU_CHOICE"}:
            continue
        variables[key] = value.strip()

    def expand(value: str) -> str:
        previous = None
        for _ in range(6):
            if value == previous:
                break
            previous = value
            value = value.replace("%~dp0", str(base) + "\\")
            value = value.replace("%~f0", str(path))
            value = value.replace("%~n0", path.stem)
            value = re.sub(r"%~[A-Za-z0-9]*", "", value)

            def repl(match: re.Match[str]) -> str:
                token = match.group(1)
                if token.lower() in {"cd", "date", "time", "random"}:
                    return ""
                return variables.get(token.upper(), "")

            value = VAR_RE.sub(repl, value)
            value = DELAYED_RE.sub(lambda m: variables.get(m.group(1).upper(), ""), value)
        return value

    expanded_lines = [expand(line) for line in lines]

    command_line = ""
    for line in expanded_lines:
        if "winws.exe" in line.lower():
            command_line = line
            break
    if not command_line:
        raise EngineError(
            f"В стратегии {path.name} не найдена команда winws.exe",
            "no_command",
        )

    lowered = command_line.lower()
    index = lowered.find("winws.exe")
    # Strip the executable path (possibly quoted) and take everything after it.
    tail = command_line[index + len("winws.exe"):]
    if tail.startswith('"'):
        tail = tail[1:]
    # Stop at shell chaining / redirection operators.
    for separator in ("||", "&&", "&", ">", "<", "|"):
        position = tail.find(separator)
        if position != -1:
            tail = tail[:position]
    args = split_windows_args(tail)

    cleaned: list[str] = []
    unresolved: list[str] = []
    for arg in args:
        if "%" in arg:
            unresolved.append(arg)
            continue
        if arg.startswith("--wf-") and "," in arg and arg.endswith(","):
            head, values = arg.split("=", 1)
            ports = [port for port in values.split(",") if port]
            arg = f"{head}={','.join(ports)}" if ports else ""
        if arg in {"--wf-tcp=", "--wf-udp=", "--filter-tcp=", "--filter-udp="}:
            continue
        if arg:
            cleaned.append(arg)

    executable = bin_dir / "winws.exe"
    if not executable.exists():
        candidate = base / "winws.exe"
        if candidate.exists():
            executable = candidate
        else:
            raise EngineError(
                f"winws.exe не найден в {bin_dir}",
                "missing_binary",
            )
    return ParsedCommand(executable=executable, args=cleaned, cwd=bin_dir,
                         unresolved=unresolved, raw_line=command_line.strip())


def discover_strategies(folder: Path) -> list[Strategy]:
    if not folder.exists():
        return []
    items: list[Strategy] = []
    for file in folder.glob("*.bat"):
        if file.name.lower() == "service.bat":
            continue
        try:
            size = file.stat().st_size
        except OSError:
            size = 0
        items.append(Strategy(name=file.stem, filename=file.name, path=file, size=size))

    def sort_key(strategy: Strategy) -> tuple:
        lowered = strategy.name.lower()
        # Plain "general" presets first, then alt/simple/experimental, then the rest.
        if lowered == "general":
            rank = 0
        elif lowered.startswith("general (fake tls auto"):
            rank = 1
        elif lowered.startswith("general (fake tls"):
            rank = 2
        elif lowered.startswith("general (alt"):
            rank = 3
        elif lowered.startswith("general (simple"):
            rank = 4
        elif lowered.startswith("general"):
            rank = 5
        else:
            rank = 6
        return (rank, strategy.name)

    return sorted(items, key=sort_key)


def resolve_zapret_folder() -> Path:
    configured = str(settings.get("zapret.path", "") or "").strip()
    if configured:
        candidate = Path(configured)
        if candidate.exists():
            return candidate
    for name in ("zapret", "zapret-discord-youtube", "zapret-discord-youtube-1.10.4"):
        candidate = paths.ENGINES_DIR / name
        if candidate.exists():
            return candidate
    return paths.ENGINES_DIR / "zapret"


class ZapretEngine(BaseEngine):
    key = "zapret"
    title = "Zapret"
    strategy_started = Signal(str)

    def folder(self) -> Path:
        return resolve_zapret_folder()

    def strategies(self) -> list[Strategy]:
        return discover_strategies(self.folder())

    def strategy(self, filename: str | None = None) -> Strategy | None:
        wanted = filename or str(settings.get("zapret.strategy", "general.bat"))
        for item in self.strategies():
            if item.filename == wanted:
                return item
        items = self.strategies()
        return items[0] if items else None

    def is_available(self) -> bool:
        return (self.folder() / "bin" / "winws.exe").exists()

    def external_processes(self) -> list[int]:
        return winapi.find_processes("winws.exe")

    # ------------------------------------------------------------------ start
    def start_with(self, filename: str | None = None) -> None:
        if self.running:
            raise EngineError("Zapret уже запущен", "already_running")
        strategy = self.strategy(filename)
        if strategy is None:
            raise EngineError(
                "Стратегии не найдены. Укажите папку zapret-discord-youtube в настройках.",
                "missing_folder",
            )
        if not self.is_available():
            raise EngineError(
                f"winws.exe не найден в {self.folder()}\\bin. Проверьте путь к движку.",
                "missing_binary",
            )
        if not winapi.is_admin():
            raise EngineError(
                "Для запуска Zapret нужны права администратора (драйвер WinDivert).",
                "admin_required",
            )
        ensure_user_lists(self.folder())
        missing_lists = [name for name in USER_LIST_DEFAULTS
                         if not (self.folder() / "lists" / name).is_file()]
        if missing_lists:
            raise EngineError(
                "Не удалось создать списки Zapret: "
                f"{', '.join(missing_lists)}. Проверьте права на папку движка.",
                "user_lists_failed",
            )
        command = parse_bat(strategy.path)
        self._set_status("starting", f"Запуск {strategy.name}…")
        self._intentional_stop = False
        try:
            pid = self.supervisor.start(command.argv, command.cwd, pid_file=self._pid_file())
        except EngineError as exc:
            self._set_status("error", str(exc))
            raise
        # winws fails fast (driver missing / port busy); give it a moment.
        time.sleep(0.35)
        if not self.supervisor.running:
            if self._status != "error":
                self._set_status("error", "winws.exe завершился сразу после запуска")
            raise EngineError(
                "winws.exe завершился сразу после запуска. Подробности в журнале.",
                "exited",
            )
        settings.set("zapret.strategy", strategy.filename, save=True)
        self._set_status("running", f"{strategy.name} · PID {pid}")
        self.strategy_started.emit(strategy.name)
        self.log_line.emit(f"[Zentrix] Стратегия: {strategy.name}")
        self.log_line.emit(f"[Zentrix] PID: {pid} · {command.executable}")
        if command.unresolved:
            self.log_line.emit(f"[Zentrix] Нераскрытые переменные: {', '.join(command.unresolved)}")

    def start(self) -> None:
        self.start_with()

    def stop(self) -> None:
        self._intentional_stop = True
        self._set_status("stopping", "Остановка…")
        self.supervisor.stop()
        # Clean up any orphaned winws from a previous crash.
        for pid in self.external_processes():
            try:
                winapi.kill_tree(pid)
            except Exception:
                pass
        self._pid_file().unlink(missing_ok=True)
        self._set_status("stopped", "Остановлено")

    def command_preview(self, filename: str | None = None) -> str:
        strategy = self.strategy(filename)
        if not strategy:
            return ""
        try:
            return parse_bat(strategy.path).preview()
        except EngineError as exc:
            return f"⚠ {exc}"
