# Sharing Connect (Android)

Приложение подключается к раздаче ПК («Шеринг» Zentrix) как VPN:
весь трафик телефона идёт через SOCKS5/HTTP-прокси компьютера.

- Кнопка **ПУСК/СТОП** — старт и остановка туннеля.
- Настройка: **IP**, **порт**, протокол **SOCKS5** или **HTTP**.

## Сборка

```bash
python scripts/fetch_core.py   # один раз: скачать ядро tun2socks
./gradlew assembleRelease
```

Ядро — [hev-socks5-tunnel](https://github.com/heiher/hev-socks5-tunnel) AAR (~600 КБ).
Для HTTP-режима приложение поднимает локальный SOCKS5→HTTP CONNECT
конвертер (`HttpConnectConverter`), UDP/DNS при этом идёт напрямую.
