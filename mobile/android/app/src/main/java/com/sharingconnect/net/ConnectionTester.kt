package com.sharingconnect.net

import java.io.IOException
import java.net.InetSocketAddress
import java.net.Proxy
import java.net.Socket
import javax.net.ssl.SSLContext

/** Проверка соединения: TLS-рукопожатие с gstatic через заданный SOCKS/HTTP прокси. */
object ConnectionTester {

    fun test(host: String, port: Int, protocol: String, timeoutMs: Int = 6000): Result<Long> {
        val type = if (protocol == "http") Proxy.Type.HTTP else Proxy.Type.SOCKS
        val started = System.currentTimeMillis()
        return try {
            val proxy = Proxy(type, InetSocketAddress(host, port))
            val context = SSLContext.getInstance("TLS")
            context.init(null, null, null)
            Socket(proxy).use { socket ->
                socket.connect(InetSocketAddress("www.gstatic.com", 443), timeoutMs)
                socket.soTimeout = timeoutMs
                context.socketFactory.createSocket(socket, "www.gstatic.com", 443, true).use { tls ->
                    tls.startHandshake()
                }
            }
            Result.success(System.currentTimeMillis() - started)
        } catch (error: IOException) {
            Result.failure(error)
        } catch (error: Exception) {
            Result.failure(error)
        }
    }
}
