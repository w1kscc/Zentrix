<div align="center">

<img src="assets/brand/zentrix.png" width="112" alt="Zentrix">

# Zentrix

**Одно окно для Zapret и VPN.**
Обход блокировок, прокси, мониторинг и проверки — в аккуратном нативном интерфейсе Windows.

![Windows 10/11](https://img.shields.io/badge/Windows-10%20%2F%2011-0078D4?logo=windows&logoColor=white)
![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![PySide6 6.12](https://img.shields.io/badge/Qt-PySide6%206.12-41CD52?logo=qt&logoColor=white)
![License MIT](https://img.shields.io/badge/license-MIT-7C5CFF)
![Release](https://img.shields.io/github/v/release/w1kscc/Zentrix?label=release&color=7C5CFF)
![Build](https://img.shields.io/github/actions/workflow/status/w1kscc/Zentrix/build.yml?label=build)

<br>

<a href="https://w1kscc.github.io/Zentrix/"><img src="docs/buttons/site.svg" height="56" alt="Сайт проекта"></a> &nbsp;
<a href="https://w1kscc.github.io/Zentrix/#download"><img src="docs/buttons/download.svg" height="56" alt="Скачать установщик"></a> &nbsp;
<a href="https://github.com/w1kscc/Zentrix/releases"><img src="docs/buttons/releases.svg" height="56" alt="Все релизы"></a>

</div>

---

Zentrix объединяет Zapret и VPN на ядрах Xray и sing-box. Ключи хранятся в одном
общем списке и доступны при смене ядра. Движки запускаются скрыто, а управление
ими идёт из единого интерфейса.

> **Сайт проекта:** <https://w1kscc.github.io/Zentrix/> — установщик
> и портативная сборка в один клик.

## Возможности

### Главная — уровень 1: всё важное сразу

- **Статус-пилюли:** Zapret, VPN и TG WS Proxy — что работает прямо сейчас.
- **Починить сеть** в один клик: `flushdns` → сброс Winsock → сброс IP-стека →
  очистка кэша Zentrix.
- **Игровой режим:** высокий приоритет процессам игр и план питания
  «Максимальная производительность» (`powercfg`); при выключении всё
  возвращается автоматически.
- **Внешний IP** с алертами: тост «IP изменился: был …, стал …».
- **Быстрое переключение стратегий Zapret** и кнопка **«Выбрать лучший»** —
  поочерёдный замер стратегий реальными проверками сервисов.
- **«Проверить блокировки»** — быстрый запуск блокчека.
- Служебное (обновления, очистка, оформление) — только мелкими ссылками.

### Zapret — обход DPI

- Автоматически находит стратегии в `.bat`-файлах и запускает
  `bin\winws.exe` напрямую, без `cmd.exe` и `start`.
- 22 стратегии, поиск лучшей стратегии с реальным опросом сервисов,
  проверка выбранной стратегии, живой лог.
- Фильтр игровых портов (game filter), свои бан-листы с авто-обновлением.
- **Watchdog:** следит за `winws.exe` и автоматически перезапускает
  (до 3 попыток) с уведомлением.
- **TG WS Proxy (встроенный).** Локальный MTProto-over-WebSocket мост для
  Telegram Desktop — ядро [Flowseal/tg-ws-proxy](https://github.com/Flowseal/tg-ws-proxy)
  работает **внутри Zentrix** (отдельный поток, никаких сторонних окон и
  второй иконки в трее). Включение, порт и автозапуск — на вкладке Zapret;
  статус — на Главной; подключение Telegram — по кнопке «Открыть в Telegram»
  (`tg://proxy`-ссылка) или копированием ссылки. Ядро скачивается и
  обновляется автоматически с GitHub-релизов.

### VPN — Xray и sing-box

- Один общий список серверов для обоих ядер: вставьте `vless://`, `vmess://`,
  `trojan://` или `ss://` — Zentrix разберёт ссылку и поднимет локальный
  SOCKS/HTTP прокси. Смена ядра — один выпадающий список.
- **Ping серверов** (TCP-замер каждого) и **«Выбрать лучший»**.
- **Подписки:** URL и авто-обновление по интервалу.
- Под-вкладки «Подключение / Серверы и подписки» — один экран, единый скролл.
- Мульти-прокси (BETA): новые TCP-соединения распределяются между первыми
  пятью серверами sing-box (одна загрузка скорость не суммирует).
- IP и местоположение: прямой адрес и адрес через туннель (ipapi.co).
- **Поиск бесплатных ключей (BETA, выключен по умолчанию):** источник —
  [igareck/vpn-configs-for-russia](https://github.com/igareck/vpn-configs-for-russia)
  с выбором категорий (чёрные/белые списки, мобильные, слабый DPI) и
  протоколов (VLESS/VMess/Trojan/Shadowsocks); авто-обновление раз в час,
  добавление узлов — строго вручную, пометка «BETA / не проверено».
  ⚠️ Бесплатные узлы не гарантируют безопасность: возможен сбор данных и
  MITM — используйте на свой страх и риск.

### Проверки

- DNS против DoH, TCP-доступность и классификация TLS SNI для YouTube,
  Discord, Telegram, Instagram, X, Steam, GitHub и других.
- **История в SQLite** (`%APPDATA%\Zentrix\cache.db`): доступность каждого
  сервиса за 7 дней.
- Понятный вердикт и рекомендация: что работает, что заблокировано и чем.

### Инструменты

- **Починить сеть:** flushdns, Winsock, сброс IP-стека, кэш Zentrix.
- **Смена DNS в один клик:** Cloudflare / Google / AdGuard / Family / DHCP.
- **Редактор hosts:** анти-рекламный пресет, групповое вкл/выкл записей.
- **Диагностика:** ping, traceroute, whois, скан портов.
- **Игровой режим:** список игр, приоритет процессов, план питания.

### Мониторинг

- Скорость, графики, активные TCP-соединения и процессы, держащие сеть.
- Запускается вручную и останавливается при уходе со страницы.

### Обновления

- Проверка релизов Zapret, Xray/sing-box, **TG WS Proxy** и самого Zentrix
  через GitHub API.
- Скачивание с докачкой после обрыва (HTTP Range), валидация архива до
  распаковки, атомарная замена движка с откатом при ошибке.
- Обновление Zapret сохраняет ваши `lists/` и флаг игрового фильтра.
- Happ/Hiddify распространяются отдельными установщиками — это явно указано.

### Настройки и автоматизация

- **Сценарии «если → то»:** «если YouTube недоступен → сменить стратегию»,
  «если VPN пропал → включить Zapret», реакция на смену IP.
- **Авто-тема «Как в Windows»:** чтение `AppsUseLightTheme`, реакция на
  смену темы на лету.
- **Палитра команд Ctrl+K:** быстрый поиск по страницам и действиям.
- Оформление: тёмная/светлая темы, пресеты, акценты, видео-фон, звуки,
  синтезируемые на лету; трей, автозапуск, единственный экземпляр;
  `%APPDATA%\Zentrix` для настроек и логов.

### Быстрый старт и приватность

- Ленивая загрузка страниц, тяжёлая работа в фоновых потоках — целевое время
  холодного старта до 1,5 секунды.
- Zentrix не отправляет данные никуда, кроме явных проверок: GitHub API
  (обновления), ipapi.co (GeoIP), проверки доступности сервисов.


## Установка

### Готовый установщик

1. Скачайте `ZentrixSetup.exe` из раздела **Releases**.
2. Запустите установщик. Установка **для текущего пользователя**, права
   администратора не нужны.
3. При первом запуске откроется главная страница. Для Zapret может потребоваться
   повышение прав — используйте кнопку **«Перезапустить от администратора»** в
   настройках (драйвер WinDivert).
4. VPN работает в локальном прокси-режиме и не требует прав администратора.
   Системный прокси настраивается в разделе VPN.

Установщик кладёт приложение в `%LOCALAPPDATA%\Programs\Zentrix`, настройки — в
`%APPDATA%\Zentrix`. При удалении пользовательские настройки и профили
сохраняются.

### Из исходников

```powershell
git clone https://github.com/w1kscc/Zentrix.git
cd zentrix
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python scripts/fetch_engines.py --zapret
python -m src.main
```

Требования: Windows 10/11 x64, Python 3.12, ~250 МБ свободного места (с ядрами).

## Движки и локальные пути

Движки **не хранятся в репозитории** и не попадают в git. Они скачиваются
скриптом или через страницу «Обновления»:

```
engines/
  zapret/                 # zapret-discord-youtube 1.10.4
    bin/winws.exe
    general.bat, general (ALT).bat, ...
    lists/
  xray/core/xray.exe      # ядро для интеграции Happ
  singbox/core/sing-box.exe
  happ/vendor/            # опционально: оригинальный установщик Happ
  hiddify/vendor/         # опционально: оригинальный установщик Hiddify
```

Загрузить всё необходимое:

```powershell
python scripts/fetch_engines.py --zapret      # Zapret 1.10.4
python scripts/fetch_engines.py --cores       # Xray-core + sing-box
python scripts/fetch_engines.py --all         # всё перечисленное
```

Абсолютные пути к локальным копиям движков можно задать в git-ignored файле
`settings.local.json` (пример — `settings.local.json.example`). В коде и
документации жёстких путей нет.

## Как устроен Zentrix

```
src/
  main.py                 # единственный экземпляр, окно, трей, пост-старт
  constants.py            # версии, источники, сервисы
  settings_store.py       # атомарные настройки JSON
  cleaner.py              # безопасная очистка
  netmon.py               # psutil + TCP-таблица Windows
  blocking_check.py       # DNS / DoH / TCP / TLS SNI
  updater.py              # GitHub-релизы и установка обновлений
  sound_generator.py      # процедурный синтез звуков
  engines/                # zapret, happ, hiddify, links, cores
  ui/
    main_window.py        # frameless-окно, ленивые страницы
    theme.py              # палитры и QSS
    widgets.py            # фон, карточки, иконки, тосты
    pages/                # 8 страниц
scripts/
  fetch_engines.py        # загрузка движков
  build.py                # PyInstaller + Inno Setup
  make_icons.py           # генерация SVG/PNG/ICO/ICNS
installer/
  zentrix.iss             # Inno Setup (per-user)
tests/                    # pytest
docs/                     # архитектура, сборка, troubleshooting, лендинг
```

Подробности: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/BUILD.md](docs/BUILD.md), [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md).

### Почему нет отдельных окон

| Инструмент | Что делает Zentrix | Чего не происходит |
|---|---|---|
| Zapret | Парсит `.bat`, подставляет `%BIN%`, `%LISTS%` и запускает `winws.exe` | Не открывается `cmd.exe`, не мигает консоль |
| Happ | Генерирует конфиг Xray и запускает `xray.exe` | Не запускается GUI Happ |
| Hiddify | Генерирует конфиг sing-box и запускает `sing-box.exe` | Не запускается GUI Hiddify |

Логи движков читаются из stdout/stderr и показываются внутри Zentrix. При
выходе все дочерние процессы завершаются, а системный прокси сбрасывается.

## Тесты и сборка

```powershell
python -m pytest -q
python scripts/build.py                  # portable + installer
python scripts/build.py --skip-installer # только dist/Zentrix
```

Результат:

```
dist/Zentrix/Zentrix.exe          # portable
dist/installer/ZentrixSetup.exe   # установщик Inno Setup
```

Для сборки установщика нужен [Inno Setup 6](https://jrsoftware.org/isinfo.php).
CI (`.github/workflows/build.yml`) собирает portable и установщик на
`windows-latest` и прикладывает артефакты к запуску.

## Третьи стороны

Zentrix — независимый проект. Он не аффилирован с авторами перечисленных
инструментов. Каждый компонент распространяется по своей лицензии:

| Компонент | Версия | Лицензия | Источник |
|---|---|---|---|
| **zapret-discord-youtube-1.10.4** | 1.10.4 | MIT | [Flowseal/zapret-discord-youtube](https://github.com/Flowseal/zapret-discord-youtube) · [LICENSE](https://github.com/Flowseal/zapret-discord-youtube/blob/main/LICENSE.txt) |
| **happ-desktop-4.6.1** | 4.6.1 | Proprietary (Happ) | [Happ-proxy/happ-desktop](https://github.com/Happ-proxy/happ-desktop) |
| **hiddify-app-4.1.1** | 4.1.1 | CC BY-NC-SA 4.0 | [hiddify/hiddify-app](https://github.com/hiddify/hiddify-app) · [LICENSE](https://github.com/hiddify/hiddify-app/blob/main/LICENSE.md) |
| Xray-core | актуальная | MPL-2.0 | [XTLS/Xray-core](https://github.com/XTLS/Xray-core) |
| sing-box | актуальная | GPL-3.0 | [SagerNet/sing-box](https://github.com/SagerNet/sing-box) |
| Qt / PySide6 | 6.12.0 | LGPL-3.0 / GPL-3.0 / commercial | [qt.io](https://www.qt.io/qt-6/lgpl) |
| psutil | 7.2.2 | BSD-3-Clause | [giampaolo/psutil](https://github.com/giampaolo/psutil) |
| Inno Setup | 6.x | Inno Setup License | [jrsoftware.org](https://jrsoftware.org/isinfo.php) |

Zentrix не перераспространяет установщики Happ и Hiddify: приложение скачивает
ядра с официальных GitHub-релизов по запросу пользователя. Условия
использования Happ и Hiddify определяются их авторами; коммерческое
использование Hiddify ограничено лицензией CC BY-NC-SA 4.0.

## Безопасность и приватность

- Настройки, логи и профили хранятся только локально в `%APPDATA%\Zentrix`.
- Приложение не отправляет телеметрию. Сеть используется для проверки
  обновлений, загрузки ядер и проверок доступности сервисов.
- Очистка работает только с известными временными каталогами и кэшем Zentrix;
  перед удалением показывается предпросмотр.
- Для работы Zapret требуются права администратора (WinDivert). Happ/Hiddify
  могут работать без них в режиме локального прокси.

## Ограничения

- Только Windows 10/11 x64. macOS/Linux не поддерживаются.
- Эффективность обхода зависит от провайдера, региона и выбранной стратегии.
- Проект предоставляется «как есть», без гарантий. Соблюдайте законодательство
  своей страны и условия использования сервисов.

## Лицензия

Код Zentrix распространяется по лицензии **MIT** — см. [LICENSE](LICENSE).
Сторонние движки и библиотеки сохраняют свои лицензии (таблица выше).
