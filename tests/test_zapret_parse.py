"""Strategy parsing and discovery tests for the Zapret integration."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.engines import zapret


def _make_engine(root: Path) -> Path:
    (root / "bin").mkdir(parents=True)
    (root / "bin" / "winws.exe").write_bytes(b"MZ fake")
    (root / "lists").mkdir()
    (root / "lists" / "list.txt").write_text("example.com\n", encoding="utf-8")
    return root


def test_split_windows_args_keeps_quoted_spaces() -> None:
    args = zapret.split_windows_args('--hostlist="C:\\my lists\\list.txt" --new')
    assert args == ["--hostlist=C:\\my lists\\list.txt", "--new"]


def test_parse_bat_expands_variables_and_skips_start(tmp_path: Path) -> None:
    root = _make_engine(tmp_path / "zapret")
    bat = root / "general.bat"
    bat.write_text(
        "@echo off\n"
        "set BIN=%~dp0bin\\\n"
        "set LISTS=%~dp0lists\\\n"
        "start \"zapret\" \"%BIN%winws.exe\" --wf-tcp=%GAMEFILTERTCP% "
        "--wf-udp=%GAMEFILTERUDP% --filter-tcp=80,443 "
        "--hostlist=\"%LISTS%list.txt\" --dpi-desync=fake,split2 >nul\n",
        encoding="utf-8",
    )

    command = zapret.parse_bat(bat)

    assert command.executable == root / "bin" / "winws.exe"
    assert command.cwd == root / "bin"
    assert "--wf-tcp=12" in command.args
    assert "--wf-udp=12" in command.args
    assert "--filter-tcp=80,443" in command.args
    assert f"--hostlist={root / 'lists' / 'list.txt'}" in command.args
    assert not command.unresolved
    assert "start" not in command.args


def test_game_filter_file_enables_port_range(tmp_path: Path) -> None:
    root = _make_engine(tmp_path / "zapret")
    (root / "utils").mkdir()
    (root / "utils" / "game_filter.enabled").write_text(
        "tcp=1024-65535\nudp=50000-65535\n", encoding="utf-8"
    )
    bat = root / "general.bat"
    bat.write_text(
        "set BIN=%~dp0bin\\\n"
        "%BIN%winws.exe --wf-tcp=%GAMEFILTERTCP% --wf-udp=%GAMEFILTERUDP%\n",
        encoding="utf-8",
    )

    command = zapret.parse_bat(bat)

    assert "--wf-tcp=1024-65535" in command.args
    assert "--wf-udp=50000-65535" in command.args


def test_parse_bat_missing_command_raises(tmp_path: Path) -> None:
    root = _make_engine(tmp_path / "zapret")
    bat = root / "broken.bat"
    bat.write_text("echo nothing here\n", encoding="utf-8")
    with pytest.raises(zapret.EngineError) as error:
        zapret.parse_bat(bat)
    assert error.value.code == "no_command"


def test_discover_strategies_orders_general_first(tmp_path: Path) -> None:
    root = _make_engine(tmp_path / "zapret")
    for name in (
        "general (ALT).bat",
        "general.bat",
        "general (FAKE TLS AUTO).bat",
        "service.bat",
        "readme.txt",
    ):
        (root / name).write_text("@echo off\n", encoding="utf-8")

    names = [item.filename for item in zapret.discover_strategies(root)]

    assert names == ["general.bat", "general (FAKE TLS AUTO).bat", "general (ALT).bat"]
    assert zapret.discover_strategies(root / "missing") == []


def test_ensure_user_lists_creates_upstream_defaults(tmp_path: Path) -> None:
    root = _make_engine(tmp_path / "zapret")

    created = zapret.ensure_user_lists(root)

    assert sorted(item.name for item in created) == sorted(zapret.USER_LIST_DEFAULTS)
    lists = root / "lists"
    assert (lists / "ipset-exclude-user.txt").read_text(encoding="utf-8").split() == [
        "203.0.113.113/32"
    ]
    assert (lists / "list-general-user.txt").read_text(encoding="utf-8").splitlines() == [
        "# Never leave this file empty",
        "domain.example.abc",
    ]
    assert (lists / "list-exclude-user.txt").read_text(encoding="utf-8").split() == [
        "domain.example.abc"
    ]


def test_ensure_user_lists_creates_missing_lists_folder(tmp_path: Path) -> None:
    root = tmp_path / "zapret"
    root.mkdir()

    created = zapret.ensure_user_lists(root)

    assert len(created) == len(zapret.USER_LIST_DEFAULTS)
    assert (root / "lists").is_dir()


def test_ensure_user_lists_never_overwrites_user_files(tmp_path: Path) -> None:
    root = _make_engine(tmp_path / "zapret")
    existing = root / "lists" / "ipset-exclude-user.txt"
    existing.write_text("192.0.2.10/32\n", encoding="utf-8")

    created = zapret.ensure_user_lists(root)

    assert existing not in created
    assert existing.read_text(encoding="utf-8") == "192.0.2.10/32\n"
    assert zapret.ensure_user_lists(root) == []
