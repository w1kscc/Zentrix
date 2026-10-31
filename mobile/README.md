# Sharing Connect — мобильный клиент Zentrix (Android)

Приложение-компаньон к вкладке **«Шеринг»** PC-версии Zentrix: телефон
подключается к прокси, который поднимает ПК, и сканирует QR-код
подключения. Название и стиль повторяют ПК-приложение (тёмная палитра
Zentrix, акцент #7C5CFF / #22D3EE, стеклянные карточки).

**Все функции бесплатны** — PRO-замков, которые есть у аналогов, здесь нет:
Split tunneling, брандмауэр с правилами и синхронизация доступны сразу.

## Возможности

- **QR-сканер** — камера телефона считывает QR из вкладки «Шеринг»
  (`socks5://IP:порт`); также принимается share-интент от сторонних
  сканеров и есть ручной ввод адреса.
- **VPN-туннель** — Android `VpnService` + `tun2socks`
  (hev-socks5-tunnel): трафик телефона уходит в SOCKS5/HTTP прокси ПК.
- **Split tunneling** — разрешённые/запрещённые приложения, без ограничений.
- **Брандмауэр** — запрет отдельных приложениям доступа в интернет.
- **Проверка соединения** — TLS-тест через прокси перед подключением.
- **Журнал** — события подключения в реальном времени.
- **Проверка актуальной версии** — через GitHub Releases проекта
  `w1kscc/Zentrix` (см. `net/ReleaseChecker.kt`). APK выкладывается
  ассетом в тот же релиз, что и PC-версия.
- **Адаптивный интерфейс** — Jetpack Compose; экран сам подстраивается
  под разрешение и тему телефона (тёмная/светлая/системная).

## Сборка

Нужны JDK 17 и Android SDK (Platform 35).

```bash
cd mobile/android
python scripts/fetch_tun2socks.py   # скачать hev-socks5-tunnel.aar в app/libs/
gradle assembleDebug                # APK: app/build/outputs/apk/debug/
```

Проверено: сборка проходит на JDK 21 (JAVA_HOME=C:\Program Files\Java\jdk-21.0.12)
и Gradle 8.10.2. JDK из состава Android Studio не подходит — Kotlin-компилятор
не распознаёт Java 25. Android 10+ (minSdk 29): требование AAR hev-socks5-tunnel.

Релизная сборка: `gradle assembleRelease` (подпись — локальный keystore).

## Публикация версии

1. Поднимите `versionName`/`versionCode` в `app/build.gradle.kts`.
2. Соберите `assembleRelease`, переименуйте APK в `SharingConnect.apk`.
3. Приложите APK ассетом к релизу Zentrix на GitHub — мобильное
   приложение при «Проверить актуальную версию» увидит новую версию.

## Структура

```
mobile/android/
├── app/src/main/java/com/sharingconnect/
│   ├── MainActivity.kt            # нижняя навигация: Прокси / Журнал / Настройки
│   ├── ui/Screens.kt              # Compose-экраны и палитра Zentrix
│   ├── ui/AppPickerActivity.kt    # split tunneling и правила брандмауэра
│   ├── ui/ManualProxyActivity.kt  # ручной ввод адреса прокси
│   ├── vpn/SharingVpnService.kt   # VpnService + правила маршрутизации
│   ├── vpn/Tun2Socks.kt           # мост к hev.htproxy.TProxyService (AAR)
│   ├── vpn/LogRepo.kt             # журнал
│   ├── data/SettingsStore.kt      # настройки и разбор QR-адреса
│   ├── net/ReleaseChecker.kt      # проверка версии через GitHub API
│   └── net/ConnectionTester.kt    # тест прокси-соединения
└── scripts/fetch_tun2socks.py     # загрузка нативной библиотеки
```

## Что учесть при первой сборке

- `fetch_tun2socks.py` скачивает прекомпилированные `.so`; если ABI
  upstream-релиза отличается — поправьте `ABI_MAP` в скрипте.
- Брандмауэр блокирует приложения через те же правила VpnService
  (запрещённый пакет полностью исключается из туннеля); для жёсткого
  блока без прокси можно дополнительно ограничивать через
  `DevicePolicyManager`, в текущей версии достаточно правил туннеля.
