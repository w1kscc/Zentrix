# Сборка Zentrix

Инструкция для Windows 10/11 x64. Сборка проверена на Python 3.12.10,
PySide6 6.12.0, PyInstaller 6.22.3 и Inno Setup 6.

## 1. Требования

- Windows 10/11 x64
- Python 3.12 (64-bit) с `py`/`python` в PATH
- ~2 ГБ свободного места (venv, PyInstaller, движки)
- [Inno Setup 6](https://jrsoftware.org/isinfo.php) — только для установщика

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
```

## 2. Движки

Движки не хранятся в git. Перед сборкой загрузите то, что должно попасть в
дистрибутив:

```powershell
python scripts/fetch_engines.py --zapret        # Zapret 1.10.4 (MIT)
python scripts/fetch_engines.py --cores         # Xray-core + sing-box
python scripts/fetch_engines.py --all           # Zapret + оба ядра
```

Проверка:

```powershell
Test-Path engines\zapret\bin\winws.exe
Test-Path engines\xray\core\xray.exe
Test-Path engines\singbox\core\sing-box.exe
```

Скрипт пишет `version.json` рядом с движком. Повторный запуск не перекачивает
уже установленный Zapret; используйте `--force` для замены. Официальные
установщики Happ/Hiddify (опционально, для архива) скачиваются флагом
`--vendor`; для работы Zentrix они не нужны.

> Установщик Happ/Hiddify не включается в сборку: Zentrix использует только
> headless-ядра Xray/sing-box. Это уменьшает размер и не нарушает лицензии
> upstream.

## 3. Тесты

```powershell
python -m pytest -q
```

Ожидается `37 passed`. Тесты не требуют дисплея (используется offscreen Qt).

## 4. Сборка

```powershell
python scripts/build.py
```

Что происходит:

1. Очищаются `build/` и `dist/`.
2. Генерируется `build/version_info.txt` из `src/constants.py`.
3. PyInstaller собирает onedir-бандл `dist/Zentrix/` с `assets/` внутри.
4. Содержимое `engines/` копируется в `dist/Zentrix/engines/` (без `vendor/`).
5. Inno Setup компилирует `dist/installer/ZentrixSetup.exe`.

Полезные варианты:

```powershell
python scripts/build.py --skip-installer   # только portable
python scripts/build.py --no-engines       # без движков (скачаются в приложении)
python scripts/build.py --installer-only   # пересобрать установщик
python scripts/build.py --no-clean         # инкрементальная сборка
```

Если Inno Setup установлен в нестандартное место:

```powershell
$env:INNO_SETUP_ISCC = "D:\Tools\Inno Setup 6\ISCC.exe"
python scripts/build.py --installer-only
```

## 5. Результат

```
dist\
  Zentrix\
    Zentrix.exe
    _internal\            # Python, Qt, assets
    engines\              # Zapret и/или ядра
  installer\
    ZentrixSetup.exe
```

Быстрая проверка portable-сборки:

```powershell
.\dist\Zentrix\Zentrix.exe
```

Проверьте: окно открывается без консоли, вкладки переключаются, Zapret
запускается (от администратора), настройки сохраняются в
`%APPDATA%\Zentrix\settings.json`, при выходе не остаётся процессов
`winws.exe` / `xray.exe` / `sing-box.exe`.

## 6. Установщик

`installer/zentrix.iss`:

- per-user установка в `%LOCALAPPDATA%\Programs\Zentrix` (`PrivilegesRequired=lowest`);
- без UAC, но с предупреждением, если Zentrix уже запущен (AppMutex);
- ярлыки в меню «Пуск», опционально на рабочем столе и в автозапуске;
- лицензия MIT на странице установки;
- удаление не трогает `%APPDATA%\Zentrix` (профили, пресеты, настройки).

Пересборка только установщика после изменения `.iss`:

```powershell
python scripts/build.py --installer-only
```

## 7. Иконки и брендинг

Исходник — `assets/brand/logo.svg`. Все PNG, ICO, ICNS и tray-варианты
генерируются скриптом:

```powershell
python scripts/make_icons.py
```

Скрипт создаёт:

```
assets/brand/zentrix.ico            16–256 px, multi-size
assets/brand/zentrix.icns           macOS (для будущих портов/доков)
assets/brand/zentrix.png            512 px
assets/brand/png/zentrix-*.png      16, 24, 32, 48, 64, 128, 256, 512, 1024
assets/brand/png/tray-*.png         16, 24, 32, 48
```

Иконки интерфейса — `assets/icons/*.svg` (35 штук). Корневой элемент должен
содержать `fill="none" stroke="#EAF0FF"`, иначе `svg_pixmap()` не сможет
перекрасить иконку под тему.

## 8. CI

`.github/workflows/build.yml` на `windows-latest`:

1. ставит Python 3.12 и зависимости;
2. запускает pytest;
3. скачивает Zapret;
4. собирает portable и установщик;
5. загружает `dist/Zentrix` и `dist/installer/ZentrixSetup.exe` как артефакты.

CI не скачивает Happ/Hiddify vendor-установщики: приложение получает ядра
Xray/sing-box по запросу пользователя.

## 9. Чек-лист релиза

- [ ] Обновлена версия в `src/constants.py` (`APP_VERSION`).
- [ ] Обновлены версии upstream в `SOURCES`, если изменились.
- [ ] `python -m pytest -q` — зелёный.
- [ ] `python scripts/build.py` — без ошибок.
- [ ] Запуск portable и установленной версии проверен на чистом профиле.
- [ ] Проверены тёмная/светлая темы, трей, автозапуск, выход без «хвостов».
- [ ] Обновлены скриншоты в `docs/screenshots/` (1440×900).
- [ ] Проверен `ZentrixSetup.exe` (установка, запуск, удаление).
- [ ] Тег `v1.0.3`, артефакты приложены к GitHub Release.

## 10. Подпись кода (опционально)

Для распространения без предупреждений SmartScreen нужен сертификат
Authenticode. Подпишите `Zentrix.exe`, затем установщик:

```powershell
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
  /f cert.pfx /p $env:CERT_PASSWORD dist\Zentrix\Zentrix.exe
python scripts/build.py --installer-only
signtool sign /fd SHA256 /tr http://timestamp.digicert.com /td SHA256 `
  /f cert.pfx /p $env:CERT_PASSWORD dist\installer\ZentrixSetup.exe
```

Сертификат и пароль не коммитятся. В CI добавьте секреты и шаг подписи после
сборки.
