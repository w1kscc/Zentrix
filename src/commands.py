"""Command palette (Ctrl+K): searchable registry of pages and actions."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Command:
    key: str
    title: str
    hint: str = ""
    page: str = ""   # navigation target, empty for pure actions
    action: str = ""  # action key handled by MainWindow.execute_command


PAGE_COMMANDS = (
    Command("go:home", "Главная", "Статус и быстрые действия", page="home"),
    Command("go:zapret", "Zapret", "Стратегии, запуск, watchdog", page="zapret"),
    Command("go:vpn", "VPN", "Серверы, подписки, ключи", page="vpn"),
    Command("go:blockcheck", "Проверки", "Блокчеки и история за 7 дней", page="blockcheck"),
    Command("go:tools", "Инструменты", "Ремонт сети, DNS, hosts, диагностика", page="tools"),
    Command("go:monitor", "Мониторинг", "Скорость и TCP-соединения", page="monitor"),
    Command("go:updates", "Обновления", "Zapret, Xray, sing-box, Zentrix", page="updates"),
    Command("go:settings", "Настройки", "Оформление, сценарии, поведение", page="settings"),
)

ACTION_COMMANDS = (
    Command("act:toggle_zapret", "Включить/выключить Zapret", "Переключение обхода",
            action="toggle_zapret"),
    Command("act:best_strategy", "Выбрать лучшую стратегию", "Замер по реальным проверкам",
            action="best_strategy"),
    Command("act:check_blocks", "Проверить блокировки", "Быстрый блокчек сервисов",
            action="check_blocks"),
    Command("act:repair_network", "Починить сеть", "flushdns, Winsock, сброс IP-стека",
            action="repair_network"),
    Command("act:check_updates", "Проверить обновления", "Все компоненты",
            page="updates", action="check_updates"),
    Command("act:cleaner", "Очистка временных файлов", "Кэши и загрузки",
            page="settings", action="cleaner"),
    Command("act:ip_now", "Внешний IP", "Показать текущий внешний IP",
            action="ip_now"),
)


def all_commands() -> list[Command]:
    return list(PAGE_COMMANDS) + list(ACTION_COMMANDS)


def filter_commands(commands: list[Command], query: str) -> list[Command]:
    """Case-insensitive substring match on title and hint."""
    needle = (query or "").strip().casefold()
    if not needle:
        return list(commands)
    words = needle.split()
    scored = []
    for command in commands:
        haystack = f"{command.title} {command.hint}".casefold()
        if all(word in haystack for word in words):
            score = 0
            if command.title.casefold().startswith(needle):
                score -= 2
            if needle in command.title.casefold():
                score -= 1
            scored.append((score, command))
    scored.sort(key=lambda item: item[0])
    return [command for _score, command in scored]
