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

> **Сайт проекта:** <https://w1kscc.github.io/Zentrix/> — скриншоты,
> установщик и портативная сборка в один клик.

## Возможности

- **Одно окно, без консолей.** Zapret запускается напрямую через `winws.exe`,
  VPN — через headless-ядро Xray или sing-box.
  Дочерние процессы создаются с `CREATE_NO_WINDOW`.
- **Zapret.** Автоматически находит стратегии в `.bat`-файлах, разворачивает
  переменные и запускает `bin\winws.exe` без `cmd.exe` и `start`. 22 стратегии,
  фильтр игровых портов, свои списки доменов, живой лог, проверка выбранной стратегии
  и автоматический поиск лучшей стратегии с опросом доступности сервисов.
  **Watchdog:** если `winws.exe` упадёт — авто-перезапуск (до 3 попыток) с уведомлением.
- **VPN.** Вставьте `vless://`, `vmess://`, `trojan://` или `ss://` —
  Zentrix разберёт ссылку, сгенерирует конфиг и поднимет локальный SOCKS/HTTP
  прокси. Выберите Xray или sing-box; оба ядра используют общий профиль серверов.
  Поддержка **подписок** (вставьте URL — список серверов загрузится сам; опционально
  авто-обновление каждые N часов). **Ping серверов:** TCP-замер задержки каждого
  сервера и кнопка «выбрать самый быстрый». Экспериментальный мульти‑прокси режим
  распределяет новые TCP‑соединения между первыми пятью серверами sing-box.
- **Проверки блокировок.** DNS против DoH, TCP-доступность и классификация TLS
  SNI для YouTube, Discord, Telegram, Instagram, X, Steam, GitHub и других
  сервисов. Каждая проверка сохраняется в SQLite (history в `cache.db`), и на
  странице строится **график доступности за 7 дней** по каждому сервису.
- **Инструменты.** Кнопка «починить сеть» (сброс DNS-кэша, Winsock и IP-стека),
  смена DNS в один клик (Cloudflare / Google / AdGuard / Family / DHCP),
  редактор **hosts** с готовым анти-рекламным списком, диагностика
  (ping · traceroute · whois · порт-скан) и **Game Mode** — повышенный приоритет
  процесса игры и план питания «максимальная производительность».
- **Сценарии «если → то».** Простая автоматика: «если YouTube заблокирован →
  сменить стратегию», «если VPN пропал → включить Zapret» — в настройках.
- **IP-мониторинг.** Тихая проверка внешнего IP каждые 5 минут: тост при смене
  exit-ноды и опциональный хук в сценарии.
- **Мониторинг.** Скорость, графики, активные TCP-соединения и процессы,
  которые держат сеть. Мониторинг запускается вручную и останавливается при
  уходе со страницы — без фоновой нагрузки.
- **Обновления.** Проверка релизов Zapret, Xray, sing-box и самого Zentrix через
  GitHub API. Обновление Zapret сохраняет ваши `lists/` и настройку игрового
  фильтра.
- **Очистка.** Безопасный предпросмотр временных файлов, кэшей и логов с
  оценкой освобождаемого места. Необязательный автозапуск при старте.
- **Внешний вид.** Тёмная, светлая или **авто-тема как в Windows** (следит за
  системной), пресеты оформления, акцентные цвета, скругления, видео-фон
  (MP4/WebM/MOV/MKV, по желанию), 35 векторных иконок и полностью кастомный
  title bar.
- **Палитра команд (Ctrl+K).** Быстрый поиск по страницам и действиям приложения.
- **Звуки без аудиофайлов.** Все сигналы синтезируются на лету (синус/треугольник,
  ADSR-огибающая) и кэшируются как WAV.
- **Трей, автозапуск, единственный экземпляр.** Закрытие в трей, запуск
  свёрнутым, `%APPDATA%\Zentrix` для настроек и логов.
- **Быстрый старт.** Ленивая загрузка страниц, тяжёлая работа в фоновых
  потоках, целевое время холодного старта — до 1,5 секунды.

## Скриншоты

| Главная | Zapret | VPN |
|:---:|:---:|:---:|
| ![Главная](docs/screenshots/home.png) | ![Zapret](docs/screenshots/zapret.png) | ![Happ](docs/screenshots/happ.png) |

| VPN · прежний кадр | Мониторинг | Проверки |
|:---:|:---:|:---:|
| ![Hiddify](docs/screenshots/hiddify.png) | ![Мониторинг](docs/screenshots/monitor.png) | ![Проверки](docs/screenshots/blockcheck.png) |

| Обновления | Настройки · оформление | Светлая тема |
|:---:|:---:|:---:|
| ![Обновления](docs/screenshots/updates.png) | ![Оформление](docs/screenshots/settings-appearance.png) | ![Светлая тема](docs/screenshots/home-light.png) |

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
  nettools.py             # DNS, hosts, ping/traceroute/whois/порты, ремонт
  blocking_check.py       # DNS / DoH / TCP / TLS SNI
  check_history.py        # SQLite-история результатов проверок
  rules.py                # сценарии «если → то»
  ipwatch.py              # отслеживание внешнего IP
  updater.py              # GitHub-релизы и установка обновлений
  sound_generator.py      # процедурный синтез звуков
  engines/                # zapret, happ, hiddify, links, cores
  ui/
    main_window.py        # frameless-окно, ленивые страницы
    command_palette.py    # Ctrl+K палитра команд
    runtime.py            # IP-алерты, сценарии, авто-подписки
    game_mode.py          # Game Mode (приоритет, план питания)
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
docs/                     # архитектура, сборка, troubleshooting, скриншоты
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

## Журнал изменений

### 1.1.0

**Добавлено**

- Страница **«Инструменты»**: ремонт сети (DNS-кэш / Winsock / полный сброс),
  смена DNS в один клик (Cloudflare, Google, AdGuard, Family, DHCP),
  менеджер hosts-файла с анти-рекламным пресетом и включением групп доменов,
  диагностика (ping · traceroute · whois · порт-скан) и Game Mode.
- **Game Mode** — повышенный приоритет процесса игры (psutil) и план питания
  «максимальная производительность» `powercfg`; всё возвращается автоматически.
- **Watchdog Zapret** — авто-перезапуск `winws.exe` после неожиданного падения
  (до 3 попыток) с уведомлением.
- **История проверок** — результаты блокчеков сохраняются в SQLite
  (`%APPDATA%\Zentrix\cache.db`), на странице «Проверки» график доступности
  за 7 дней по каждому сервису.
- **Сценарии «если → то»** — автоматизация (уведомить, сменить стратегию,
  включить/выключить Zapret) по событиям сервисов, VPN и Zapret.
- **Авто-обновление подписок** VPN по интервалу.
- **Ping серверов** — TCP-замер до каждого сервера профиля + выбор самого
  быстрого.
- **Алерты смены IP** — проверка внешнего IP раз в 5 минут, уведомление при
  смене exit-ноды.
- **Палитра команд Ctrl+K.**
- **Авто-тема** «Как в Windows» (следит за AppsUseLightTheme).
- Навигация переупорядочена: главное (Zapret, VPN, Проверки, Инструменты)
  теперь сверху, служебное (Мониторинг, Обновления, Настройки) — снизу.

**Удалено**

- **Шеринг в локальной сети** — причина: функция работала нестабильно.
  Раздача продолжала висеть при смене ядра (Xray ↔ sing-box) и после
  смены IP-адреса в LAN, повторно занимая порты запущенного VPN-движка.
  Оставить надёжный вариант «только 127.0.0.1» было проще и безопаснее.

### 1.0.7

- Разные исправления стабильности, bump версии.

## Лицензия

Код Zentrix распространяется по лицензии **MIT** — см. [LICENSE](LICENSE).
Сторонние движки и библиотеки сохраняют свои лицензии (таблица выше).
