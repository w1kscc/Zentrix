package com.sharingconnect.net

import java.net.InetSocketAddress
import java.net.Proxy
import java.net.Socket
import javax.net.ssl.SSLSocket
import javax.net.ssl.SSLContext
import kotlin.math.roundToInt

data class SpeedTestResult(
    val downMbps: Double?,
    val upMbps: Double?,
    val error: String? = null,
)

/**
 * Тест входящего и исходящего потока через прокси ПК
 * (Cloudflare speed endpoints, SOCKS5/HTTP из профиля).
 *
 * Прогресс и результат — в Мбит/с.
 */
object SpeedTest {

    private const val HOST = "speed.cloudflare.com"
    private const val DOWN_PATH = "/__down?bytes=10000000"
    private const val UP_PATH = "/__up"
    private const val TIMEOUT_MS = 15000
    private const val UP_BYTES = 4L * 1024 * 1024

    /** Скачать ~10 МБ через прокси, вернуть скорость Мбит/с. */
    fun measureDown(host: String, port: Int, protocol: String, onProgress: (Double) -> Unit = {}): Double? {
        val tls = connect(host, port, protocol) ?: return null
        try {
            val request = "GET $DOWN_PATH HTTP/1.1\r\n" +
                "Host: $HOST\r\n" +
                "User-Agent: SharingConnect\r\n" +
                "Connection: close\r\n\r\n"
            tls.outputStream.write(request.toByteArray())
            tls.outputStream.flush()
            val input = tls.inputStream
            // пропускаем HTTP-заголовки: ждём последовательность CR LF CR LF
            val pattern = intArrayOf(13, 10, 13, 10)
            var matched = 0
            while (matched < 4) {
                val byte = input.read()
                if (byte < 0) return null
                matched = if (byte == pattern[matched]) matched + 1 else if (byte == pattern[0]) 1 else 0
            }
            val started = System.currentTimeMillis()
            var total = 0L
            val buffer = ByteArray(64 * 1024)
            while (true) {
                val read = input.read(buffer)
                if (read < 0) break
                total += read
                onProgress(mbps(total, System.currentTimeMillis() - started))
                if (System.currentTimeMillis() - started > TIMEOUT_MS) break
            }
            val elapsed = (System.currentTimeMillis() - started).coerceAtLeast(1)
            return if (total > 0) mbps(total, elapsed) else null
        } finally {
            runCatching { tls.close() }
        }
    }

    /** Отправить 4 МБ через прокси, вернуть скорость Мбит/с. */
    fun measureUp(host: String, port: Int, protocol: String, onProgress: (Double) -> Unit = {}): Double? {
        val tls = connect(host, port, protocol) ?: return null
        try {
            val payload = ByteArray(64 * 1024)
            java.util.Random(42).nextBytes(payload)
            val request = "POST $UP_PATH HTTP/1.1\r\n" +
                "Host: $HOST\r\n" +
                "Content-Type: application/octet-stream\r\n" +
                "Content-Length: $UP_BYTES\r\n" +
                "Connection: close\r\n\r\n"
            val started = System.currentTimeMillis()
            val output = tls.outputStream
            output.write(request.toByteArray())
            var total = 0L
            while (total < UP_BYTES) {
                val chunk = minOf(payload.size.toLong(), UP_BYTES - total).toInt()
                output.write(payload, 0, chunk)
                output.flush()
                total += chunk
                onProgress(mbps(total, System.currentTimeMillis() - started))
            }
            runCatching {
                val buffer = ByteArray(4096)
                val input = tls.inputStream
                while (input.read(buffer) > 0) { /* ответ сервера до закрытия */ }
            }
            val elapsed = (System.currentTimeMillis() - started).coerceAtLeast(1)
            return mbps(total, elapsed)
        } finally {
            runCatching { tls.close() }
        }
    }

    private fun connect(host: String, port: Int, protocol: String): SSLSocket? {
        val proxy = Proxy(
            if (protocol == "http") Proxy.Type.HTTP else Proxy.Type.SOCKS,
            InetSocketAddress(host, port),
        )
        val context = SSLContext.getInstance("TLS")
        context.init(null, null, null)
        val socket = Socket(proxy)
        try {
            socket.connect(InetSocketAddress(HOST, 443), TIMEOUT_MS)
            socket.soTimeout = TIMEOUT_MS
            val tls = context.socketFactory.createSocket(socket, HOST, 443, true) as SSLSocket
            tls.startHandshake()
            return tls
        } catch (error: Exception) {
            runCatching { socket.close() }
            return null
        }
    }

    private fun mbps(bytes: Long, elapsedMs: Long): Double {
        if (elapsedMs <= 0) return 0.0
        val value = bytes * 8.0 / (elapsedMs / 1000.0) / 1_000_000.0
        return (value * 100).roundToInt() / 100.0
    }
}
