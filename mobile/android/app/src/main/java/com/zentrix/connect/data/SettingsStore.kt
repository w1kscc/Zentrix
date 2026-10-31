package com.zentrix.connect.data

import android.content.Context

enum class ProxyProtocol { SOCKS5, HTTP }

data class ProxyConfig(
    val host: String = "",
    val port: Int = 0,
    val protocol: ProxyProtocol = ProxyProtocol.SOCKS5,
) {
    val isValid: Boolean get() = host.isNotBlank() && port in 1..65535
    val uri: String get() = "${if (protocol == ProxyProtocol.SOCKS5) "socks5" else "http"}://$host:$port"
}

/** Настройки подключения: адрес, порт и протокол прокси ПК. */
class SettingsStore(context: Context) {

    private val prefs = context.getSharedPreferences("settings", Context.MODE_PRIVATE)

    var proxy: ProxyConfig
        get() = ProxyConfig(
            host = prefs.getString(KEY_HOST, "") ?: "",
            port = prefs.getInt(KEY_PORT, 0),
            protocol = if (prefs.getBoolean(KEY_HTTP, false)) ProxyProtocol.HTTP else ProxyProtocol.SOCKS5,
        )
        set(value) {
            prefs.edit()
                .putString(KEY_HOST, value.host.trim())
                .putInt(KEY_PORT, value.port)
                .putBoolean(KEY_HTTP, value.protocol == ProxyProtocol.HTTP)
                .apply()
        }

    private companion object {
        const val KEY_HOST = "host"
        const val KEY_PORT = "port"
        const val KEY_HTTP = "http"
    }
}
