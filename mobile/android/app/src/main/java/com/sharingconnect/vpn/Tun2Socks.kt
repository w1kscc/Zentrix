package com.sharingconnect.vpn

/**
 * Мост к tun2socks: официальный прекомпилированный AAR
 * (hev-socks5-tunnel, скачивается скриптом scripts/fetch_tun2socks.py
 * в app/libs/hev-socks5-tunnel.aar). Natives зарегистрированы на
 * класс hev.htproxy.TProxyService.
 *
 * Все вызовы обёрнуты в try/catch: нативная библиотека не должна
 * ронять приложение ни при каких условиях.
 */
object Tun2Socks {

    fun start(configPath: String, fd: Int): Boolean = try {
        hev.htproxy.TProxyService.TProxyStartService(configPath, fd)
        true
    } catch (error: Throwable) {
        LogRepo.log("tun2socks: ошибка запуска — ${error.javaClass.simpleName}: ${error.message}")
        VpnState.set(false)
        false
    }

    fun terminate() {
        try {
            hev.htproxy.TProxyService.TProxyStopService()
        } catch (error: Throwable) {
            LogRepo.log("tun2socks: ошибка остановки — ${error.message}")
        }
    }

    fun isRunning(): Boolean = try {
        hev.htproxy.TProxyService.TProxyIsRunning()
    } catch (error: Throwable) {
        // До первого старта службы библиотека может быть не готова — это норма.
        false
    }
}
