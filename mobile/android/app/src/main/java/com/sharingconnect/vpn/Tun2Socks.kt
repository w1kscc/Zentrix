package com.sharingconnect.vpn

/**
 * JNI-мост к tun2socks (hev-socks5-tunnel).
 *
 * Прекомпилированные .so скачиваются скриптом scripts/fetch_tun2socks.py
 * в app/src/main/jniLibs/<abi>/libtun2socks.so (arm64-v8a, armeabi-v7a,
 * x86_64). Экспортируемая функция соответствует C-API hev-socks5-tunnel:
 *
 *   int tun2socks_main(const char *config);   // блокирует до остановки
 *   void tun2socks_terminate(void);
 *
 * Если используется другая сборка tun2socks — поправьте только этот класс.
 */
object Tun2Socks {

    init {
        System.loadLibrary("tun2socks")
    }

    /** Запустить туннель с JSON-конфигом hev-socks5-tunnel. Блокирует поток. */
    external fun start(configJson: String): Int

    /** Попросить туннель завершиться (вызывается из другого потока). */
    external fun terminate()
}
