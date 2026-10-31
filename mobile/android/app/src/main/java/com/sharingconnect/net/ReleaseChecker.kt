package com.sharingconnect.net

import org.json.JSONObject
import java.net.HttpURLConnection
import java.net.URL

data class ReleaseInfo(
    val version: String,
    val apkUrl: String?,
    val notesUrl: String,
)

/**
 * Проверка актуальной версии APK Sharing Connect через GitHub Releases
 * проекта Zentrix (https://github.com/w1kscc/Zentrix/releases).
 *
 * Тег релиза принадлежит PC-версии (например v1.0.5), поэтому версия APK
 * берётся из ИМЕНИ файла-ассета: SharingConnect-1.0.2.apk. Ассеты без
 * версии в имени игнорируются.
 */
object ReleaseChecker {

    private const val API = "https://api.github.com/repos/w1kscc/Zentrix/releases/latest"
    private val APK_VERSION = Regex("""SharingConnect-(\d+(?:\.\d+)*)\.apk""", RegexOption.IGNORE_CASE)

    fun fetchLatest(timeoutMs: Int = 8000): ReleaseInfo {
        val connection = URL(API).openConnection() as HttpURLConnection
        connection.connectTimeout = timeoutMs
        connection.readTimeout = timeoutMs
        connection.setRequestProperty("Accept", "application/vnd.github+json")
        connection.setRequestProperty("User-Agent", "SharingConnect/1.0")
        try {
            if (connection.responseCode != 200) {
                throw RuntimeException("GitHub API: HTTP ${connection.responseCode}")
            }
            val body = connection.inputStream.bufferedReader().readText()
            val json = JSONObject(body)
            var apkVersion: String? = null
            var apkUrl: String? = null
            val assets = json.getJSONArray("assets")
            for (index in 0 until assets.length()) {
                val asset = assets.getJSONObject(index)
                val name = asset.getString("name")
                val match = APK_VERSION.find(name)
                if (match != null) {
                    apkVersion = match.groupValues[1]
                    apkUrl = asset.getString("browser_download_url")
                    break
                }
            }
            return ReleaseInfo(
                version = apkVersion ?: json.getString("tag_name").removePrefix("v"),
                apkUrl = apkUrl,
                notesUrl = json.getString("html_url"),
            )
        } finally {
            connection.disconnect()
        }
    }

    /** true, если [latest] новее установленной [current] (сравнение 1.2.10 > 1.2.9). */
    fun isNewer(current: String, latest: String): Boolean {
        fun parts(value: String) = value.split('.').map { it.toIntOrNull() ?: 0 }
        val a = parts(current)
        val b = parts(latest)
        for (index in 0 until maxOf(a.size, b.size)) {
            val left = a.getOrElse(index) { 0 }
            val right = b.getOrElse(index) { 0 }
            if (left != right) return left < right
        }
        return false
    }
}
