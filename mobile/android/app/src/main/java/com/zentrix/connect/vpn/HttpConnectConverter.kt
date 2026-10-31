package com.zentrix.connect.vpn

import com.zentrix.connect.data.ProxyConfig
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.net.InetSocketAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.atomic.AtomicBoolean

/**
 * Локальный SOCKS5-сервер для режима HTTP-прокси.
 *
 * Ядро tun2socks умеет upstream только SOCKS5, а ПК в HTTP-режиме отдаёт
 * HTTP CONNECT. Поэтому слушаем 127.0.0.1 и переводим протоколы:
 *  - TCP CONNECT  → "CONNECT host:port HTTP/1.1" на ПК;
 *  - UDP ASSOCIATE → ретрансляция напрямую (DNS), минуя HTTP-прокси.
 */
class HttpConnectConverter(
    private val listenPort: Int = 18080,
) {
    private val running = AtomicBoolean(false)
    private var server: ServerSocket? = null
    private val workers = mutableListOf<Thread>()
    private val relays = mutableListOf<DatagramSocket>()

    val port: Int get() = listenPort

    fun start(target: ProxyConfig): Boolean {
        if (running.get()) return true
        return try {
            val socket = ServerSocket()
            socket.bind(InetSocketAddress("127.0.0.1", listenPort))
            server = socket
            running.set(true)
            val acceptor = Thread {
                while (running.get()) {
                    try {
                        val client = socket.accept()
                        Thread { handleClient(client, target) }.also {
                            synchronized(workers) { workers.add(it) }
                            it.start()
                        }
                    } catch (error: Exception) {
                        if (running.get()) VpnState.log("SOCKS5 accept: ${error.message}")
                    }
                }
            }.apply { isDaemon = true }
            synchronized(workers) { workers.add(acceptor) }
            acceptor.start()
            true
        } catch (error: Exception) {
            VpnState.log("Не удалось поднять локальный SOCKS5: ${error.message}")
            false
        }
    }

    fun stop() {
        running.set(false)
        runCatching { server?.close() }
        server = null
        synchronized(workers) { workers.clear() }
        synchronized(relays) {
            relays.forEach { runCatching { it.close() } }
            relays.clear()
        }
    }

    // ------------------------------------------------------------- TCP
    private fun handleClient(client: Socket, target: ProxyConfig) {
        try {
            client.tcpNoDelay = true
            val input = BufferedInputStream(client.getInputStream())
            val output = BufferedOutputStream(client.getOutputStream())

            if (!readSocksGreeting(input, output)) return
            val request = readSocksRequest(input) ?: return
            when (request[1].toInt()) {
                1 -> { // CONNECT
                    val host = hostFromRequest(request)
                    val port = portFromRequest(request)
                    replySocks(output, 0x00)
                    forwardTcp(client, target, host, port)
                }
                3 -> { // UDP ASSOCIATE — DNS и прочее напрямую, минуя HTTP-прокси:
                       // весь процесс исключён из VPN через addDisallowedApplication.
                    val relayPort = openUdpRelay()
                    replyUdpAssociate(output, relayPort)
                    relayUdp(relayPort)
                }
                else -> replySocks(output, 0x07)
            }
        } catch (error: Exception) {
            VpnState.log("SOCKS5 клиент: ${error.message}")
        } finally {
            runCatching { client.close() }
        }
    }

    private fun forwardTcp(client: Socket, target: ProxyConfig, host: String, port: Int) {
        try {
            val remote = Socket(target.host, target.port)
            remote.tcpNoDelay = true
            val out = BufferedOutputStream(remote.getOutputStream())
            out.write("CONNECT $host:$port HTTP/1.1\r\nHost: $host:$port\r\n\r\n".toByteArray())
            out.flush()
            val answer = readHttpConnectAnswer(remote.getInputStream())
            if (answer != 200) {
                VpnState.log("HTTP CONNECT отказан: $answer ($host:$port)")
                runCatching { remote.close() }
                return
            }
            // Двунаправленная перекачка данных.
            val a = Thread { pipe(client.getInputStream(), remote.getOutputStream()) }
            val b = Thread { pipe(remote.getInputStream(), client.getOutputStream()) }
            a.isDaemon = true; b.isDaemon = true
            a.start(); b.start()
            a.join(); b.join()
            runCatching { remote.close() }
        } catch (error: Exception) {
            VpnState.log("Туннель TCP: ${error.message}")
        } finally {
            runCatching { client.close() }
        }
    }

    // ------------------------------------------------------------- UDP
    private fun openUdpRelay(): Int {
        val relay = DatagramSocket(0, InetAddress.getByName("127.0.0.1"))
        relays.add(relay)
        return relay.localPort
    }

    private fun replyUdpAssociate(output: BufferedOutputStream, relayPort: Int) {
        val head = byteArrayOf(0x05, 0x00, 0x00, 0x01, 127, 0, 0, 1)
        val portBytes = byteArrayOf(
            ((relayPort shr 8) and 0xFF).toByte(), (relayPort and 0xFF).toByte(),
        )
        output.write(head); output.write(portBytes); output.flush()
    }

    private fun relayUdp(relayPort: Int) {
        val relay = DatagramSocket(relayPort, InetAddress.getByName("127.0.0.1"))
        relays.add(relay)
        // Прямые UDP-пакеты от ядра → в интернет, ответы → обратно ядру.
        val upstream = DatagramSocket()
        val fromKernel = Thread {
            val buf = ByteArray(65536)
            val packet = DatagramPacket(buf, buf.size)
            while (running.get()) {
                try {
                    relay.receive(packet)
                    // SOCKS5-заголовок: RSV FRD ATYP ADDR PORT
                    val data = packet.data
                    val offset = packet.offset
                    val atyp = data[offset + 3].toInt() and 0xFF
                    var pos = offset + 4
                    val addr: InetAddress = when (atyp) {
                        1 -> InetAddress.getByAddress(data.copyOfRange(pos, pos + 4)).also { pos += 4 }
                        4 -> InetAddress.getByAddress(data.copyOfRange(pos, pos + 16)).also { pos += 16 }
                        else -> continue
                    }
                    val port = ((data[pos].toInt() and 0xFF) shl 8) or (data[pos + 1].toInt() and 0xFF)
                    pos += 2
                    val payload = data.copyOfRange(pos, packet.offset + packet.length)
                    upstream.send(DatagramPacket(payload, payload.size, addr, port))
                } catch (error: Exception) {
                    if (running.get()) return@Thread
                }
            }
        }
        val toKernel = Thread {
            val buf = ByteArray(65536)
            val packet = DatagramPacket(buf, buf.size)
            var peer: InetSocketAddress? = null
            while (running.get()) {
                try {
                    upstream.receive(packet)
                    peer = InetSocketAddress(packet.address, packet.port)
                    val addr = packet.address.address
                    val head = mutableListOf<Byte>(0, 0, 0, 1)
                    head.addAll(addr.map { it.toByte() })
                    head.add(((packet.port shr 8) and 0xFF).toByte())
                    head.add((packet.port and 0xFF).toByte())
                    val payload = head.toByteArray() + buf.copyOf(packet.length)
                    relay.send(DatagramPacket(payload, payload.size, peer))
                } catch (error: Exception) {
                    if (running.get()) return@Thread
                }
            }
        }
        fromKernel.isDaemon = true; toKernel.isDaemon = true
        synchronized(workers) { workers.add(fromKernel); workers.add(toKernel) }
        fromKernel.start(); toKernel.start()
    }

    // ------------------------------------------------------ SOCKS5 парсинг
    private fun readSocksGreeting(input: BufferedInputStream, output: BufferedOutputStream): Boolean {
        val version = input.read()
        val methods = input.read()
        if (version != 5 || methods <= 0) return false
        repeat(methods) { input.read() }
        output.write(byteArrayOf(0x05, 0x00)); output.flush() // без аутентификации
        return true
    }

    private fun readSocksRequest(input: BufferedInputStream): ByteArray? {
        val head = ByteArray(4) // VER CMD RSV ATYP
        if (input.readNBytesCompat(head, 4) != 4) return null
        var addrLen = 0
        when (head[3].toInt()) {
            1 -> addrLen = 4
            4 -> addrLen = 16
            3 -> addrLen = input.read() // длина домена
        }
        if (addrLen <= 0) return null
        val rest = ByteArray(addrLen + 2) // ADDR + PORT
        if (input.readNBytesCompat(rest, rest.size) != rest.size) return null
        return head + rest
    }

    private fun hostFromRequest(request: ByteArray): String {
        return when (request[3].toInt()) {
            1 -> InetAddress.getByAddress(request.copyOfRange(4, 8)).hostAddress ?: ""
            4 -> InetAddress.getByAddress(request.copyOfRange(4, 20)).hostAddress ?: ""
            else -> String(request, 5, request[4].toInt(), Charsets.US_ASCII)
        }
    }

    private fun portFromRequest(request: ByteArray): Int {
        val portPos = when (request[3].toInt()) {
            1 -> 8
            4 -> 20
            else -> 5 + request[4].toInt()
        }
        return ((request[portPos].toInt() and 0xFF) shl 8) or (request[portPos + 1].toInt() and 0xFF)
    }

    private fun replySocks(output: BufferedOutputStream, code: Int) {
        output.write(byteArrayOf(0x05, code.toByte(), 0x00, 0x01, 0, 0, 0, 0, 0, 0))
        output.flush()
    }

    /** Ответ HTTP-прокси: код из строки статуса или -1. */
    private fun readHttpConnectAnswer(stream: java.io.InputStream): Int {
        val reader = stream.bufferedReader(Charsets.ISO_8859_1)
        while (true) {
            val line = reader.readLine() ?: return -1
            if (line.startsWith("HTTP/")) return line.substringAfter(' ').substringBefore(' ').toIntOrNull() ?: -1
            if (line.isEmpty()) return -1 // заголовков без статуса не бывает
        }
    }

    private fun pipe(source: java.io.InputStream, sink: java.io.OutputStream) {
        val buf = ByteArray(65536)
        while (true) {
            val n = source.read(buf)
            if (n < 0) break
            sink.write(buf, 0, n)
            sink.flush()
        }
        sink.close()
    }

    private fun java.io.InputStream.readNBytesCompat(target: ByteArray, length: Int): Int {
        var filled = 0
        while (filled < length) {
            val n = read(target, filled, length - filled)
            if (n < 0) break
            filled += n
        }
        return filled
    }
}
