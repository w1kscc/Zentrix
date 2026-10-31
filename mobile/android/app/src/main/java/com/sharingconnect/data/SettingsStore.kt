package com.sharingconnect.data

import android.content.Context
import android.content.SharedPreferences
import org.json.JSONArray
import org.json.JSONObject

/** Адрес прокси из вкладки «Шеринг» ПК-версии Zentrix (QR-код / ручной ввод). */
data class ProxyConfig(
    val protocol: String = "socks5",   // socks5 | http
    val host: String = "",
    val port: Int = 0,
) {
    val isValid: Boolean get() = host.isNotBlank() && port in 1..65535
    val uri: String get() = "$protocol://$host:$port"

    companion object {
        /** Разбор payload QR-кода: socks5://192.168.1.10:10808 или http://… */
        fun parse(raw: String): ProxyConfig? {
            val value = raw.trim()
            val match = Regex("^(socks5|http)://([\\w.\\-]+):(\\d{1,5})/?$").find(value)
                ?: return null
            return ProxyConfig(
                protocol = match.groupValues[1],
                host = match.groupValues[2],
                port = match.groupValues[3].toInt(),
            )
        }
    }
}

/** Все настройки Sharing Connect. Никаких PRO-замков: все функции бесплатны. */
class SettingsStore(context: Context) {

    private val prefs: SharedPreferences =
        context.getSharedPreferences("sharing_connect", Context.MODE_PRIVATE)

    // ------------------------------------------------------------- прокси
    var proxy: ProxyConfig
        get() = ProxyConfig(
            protocol = prefs.getString("proxy.protocol", "socks5") ?: "socks5",
            host = prefs.getString("proxy.host", "") ?: "",
            port = prefs.getInt("proxy.port", 0),
        )
        set(value) = prefs.edit()
            .putString("proxy.protocol", value.protocol)
            .putString("proxy.host", value.host)
            .putInt("proxy.port", value.port)
            .apply()

    // ---------------------------------------------------------- поведение
    /** Проверять учетные данные тестовым соединением при старте. */
    var testConnection: Boolean
        get() = prefs.getBoolean("proxy.test_connection", true)
        set(value) = prefs.edit().putBoolean("proxy.test_connection", value).apply()

    /** Останавливать службу при потере Wi-Fi. */
    var stopOnWifiLoss: Boolean
        get() = prefs.getBoolean("proxy.stop_on_wifi_loss", false)
        set(value) = prefs.edit().putBoolean("proxy.stop_on_wifi_loss", value).apply()

    /** Маршрутизация частной сети через прокси (10/8, 192.168/16 и т.д.). */
    var routePrivateNetwork: Boolean
        get() = prefs.getBoolean("proxy.route_private", false)
        set(value) = prefs.edit().putBoolean("proxy.route_private", value).apply()

    /** Показывать уведомление при активном прокси-соединении. */
    var notifications: Boolean
        get() = prefs.getBoolean("ui.notifications", true)
        set(value) = prefs.edit().putBoolean("ui.notifications", value).apply()

    // ---------------------------------------------------- split tunneling
    /** Пустой список = все приложения. */
    fun allowedApps(): Set<String> = prefs.getStringSet("tunnel.allowed", emptySet()) ?: emptySet()
    fun disallowedApps(): Set<String> =
        prefs.getStringSet("tunnel.disallowed", emptySet()) ?: emptySet()

    fun setAllowedApps(packages: Set<String>) =
        prefs.edit().putStringSet("tunnel.allowed", packages).apply()

    fun setDisallowedApps(packages: Set<String>) =
        prefs.edit().putStringSet("tunnel.disallowed", packages).apply()

    // -------------------------------------------------------- брандмауэр
    var firewallEnabled: Boolean
        get() = prefs.getBoolean("firewall.enabled", false)
        set(value) = prefs.edit().putBoolean("firewall.enabled", value).apply()

    /** Правила брандмауэра: [{"package": …, "blocked": true}] */
    fun firewallRules(): List<Pair<String, Boolean>> {
        val raw = prefs.getString("firewall.rules", "[]") ?: "[]"
        return runCatching {
            JSONArray(raw).let { array ->
                (0 until array.length()).map { index ->
                    val item = array.getJSONObject(index)
                    item.getString("package") to item.getBoolean("blocked")
                }
            }
        }.getOrDefault(emptyList())
    }

    fun setFirewallRules(rules: List<Pair<String, Boolean>>) {
        val array = JSONArray()
        rules.forEach { (pkg, blocked) ->
            array.put(JSONObject().put("package", pkg).put("blocked", blocked))
        }
        prefs.edit().putString("firewall.rules", array.toString()).apply()
    }

    // ---------------------------------------------------------------- вид
    /** system | dark | light */
    var theme: String
        get() = prefs.getString("ui.theme", "system") ?: "system"
        set(value) = prefs.edit().putString("ui.theme", value).apply()
}
