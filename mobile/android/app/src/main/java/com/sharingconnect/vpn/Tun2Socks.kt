package com.sharingconnect.vpn

/**
 * Мост к tun2socks: официальный прекомпилированный AAR
 * (hev-socks5-tunnel, скачивается скриптом scripts/fetch_tun2socks.py
 * в app/libs/hev-socks5-tunnel.aar). Natives зарегистрированы на
 * класс hev.htproxy.TProxyService.
 */
object Tun2Socks {

    /** Запустить туннель: [configPath] — YAML-конфиг, [fd] — дескриптор TUN. */
    fun start(configPath: String, fd: Int): Boolean {
        hev.htproxy.TProxyService.TProxyStartService(configPath, fd)
        return isRunning()
    }

    fun terminate() {
        hev.htproxy.TProxyService.TProxyStopService()
    }

    fun isRunning(): Boolean = hev.htproxy.TProxyService.TProxyIsRunning()
}
