package com.zentrix.connect.vpn

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.net.VpnService
import android.os.Handler
import android.os.HandlerThread
import android.os.ParcelFileDescriptor
import androidx.core.app.NotificationCompat
import com.zentrix.connect.R
import com.zentrix.connect.data.ProxyConfig
import com.zentrix.connect.data.ProxyProtocol
import com.zentrix.connect.data.SettingsStore
import hev.htproxy.TProxyService
import java.io.File

/**
 * VpnService Sharing Connect: поднимает TUN и направляет весь трафик
 * в tun2socks (hev-socks5-tunnel), upstream — прокси ПК.
 *
 * SOCKS5 → ядро идёт прямо на ПК.
 * HTTP   → сначала через локальный SOCKS5→HTTP CONNECT конвертер.
 *
 * Старт/стоп — строго последовательно в фоновом потоке службы.
 */
class SharingVpnService : VpnService() {

    private lateinit var settings: SettingsStore
    private lateinit var tunnelLooper: HandlerThread
    private lateinit var tunnelHandler: Handler
    private var tunFd: Int? = null
    private var converter: HttpConnectConverter? = null

    override fun onCreate() {
        super.onCreate()
        settings = SettingsStore(this)
        tunnelLooper = HandlerThread("sharing-tunnel").apply { start() }
        tunnelHandler = Handler(tunnelLooper.looper)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            startForegroundNotification()
            tunnelHandler.post { doStop(userInitiated = true, startId = startId) }
            return START_NOT_STICKY
        }
        startForegroundNotification()
        tunnelHandler.post { doStart(startId) }
        return START_STICKY
    }

    // ------------------------------------------------------------- старт
    private fun doStart(startId: Int) {
        val current = VpnState.status.value
        if (current == TunnelStatus.RUNNING || current == TunnelStatus.STARTING) {
            VpnState.log("Уже подключено/подключается — старт проигнорирован")
            return
        }
        val config = settings.proxy
        if (!config.isValid) {
            VpnState.log("Не задан адрес прокси — заполните IP и порт в настройках")
            finishSelf(startId)
            return
        }

        VpnState.set(TunnelStatus.STARTING)
        VpnState.log("Подключение к ${config.uri}…")

        stopTunnel(waitMs = 5000)

        // Upstream: HTTP-прокси прячем за локальным SOCKS5-конвертером.
        var upstreamHost = config.host
        var upstreamPort = config.port
        if (config.protocol == ProxyProtocol.HTTP) {
            val local = HttpConnectConverter(HTTP_CONVERTER_PORT)
            if (!local.start(config)) {
                VpnState.set(TunnelStatus.STOPPED)
                finishSelf(startId)
                return
            }
            converter = local
            upstreamHost = "127.0.0.1"
            upstreamPort = local.port
            VpnState.log("HTTP-режим: локальный конвертер на 127.0.0.1:${local.port}")
        }

        var fd: Int? = null
        for (attempt in 1..5) {
            try {
                fd = buildVpnInterface().establish()?.detachFd()
            } catch (error: Exception) {
                VpnState.log("Ошибка VPN-интерфейса (попытка $attempt): ${error.message}")
            }
            if (fd != null) break
            Thread.sleep(400)
        }
        if (fd == null) {
            VpnState.log("Не удалось создать VPN-интерфейс за 5 попыток (нет разрешения?)")
            converter?.stop(); converter = null
            VpnState.set(TunnelStatus.STOPPED)
            finishSelf(startId)
            return
        }
        tunFd = fd

        val configFile = writeTun2SocksConfig(upstreamHost, upstreamPort)
        val started = TProxyService.TProxyStartService(configFile, fd)
        if (!started || !TProxyService.TProxyIsRunning()) {
            VpnState.log("tun2socks не запустился")
            closeFd(fd); tunFd = null
            converter?.stop(); converter = null
            VpnState.set(TunnelStatus.STOPPED)
            finishSelf(startId)
            return
        }
        VpnState.set(TunnelStatus.RUNNING)
        VpnState.log("Подключено: ${config.uri}")
    }

    // ---------------------------------------------------------- остановка
    private fun doStop(userInitiated: Boolean, startId: Int) {
        VpnState.set(TunnelStatus.STOPPING)
        stopTunnel(waitMs = 5000)
        VpnState.set(TunnelStatus.STOPPED)
        if (userInitiated) {
            VpnState.log("Отключено")
            finishSelf(startId)
        }
    }

    private fun stopTunnel(waitMs: Long) {
        if (TProxyService.TProxyIsRunning()) {
            runCatching { TProxyService.TProxyStopService() }
            var waited = 0L
            while (TProxyService.TProxyIsRunning() && waited < waitMs) {
                Thread.sleep(100)
                waited += 100
            }
        }
        tunFd?.let { closeFd(it); tunFd = null }
        converter?.stop(); converter = null
    }

    // ---------------------------------------------------------- интерфейс
    private fun buildVpnInterface(): Builder {
        return Builder()
            .setSession("Sharing Connect")
            .setMtu(8500)
            .addAddress("26.26.26.1", 24)
            .addDnsServer("26.26.26.2")
            .addRoute("0.0.0.0", 1)
            .addRoute("128.0.0.0", 1)
            // Весь трафик процесса приложения (tun2socks + конвертер)
            // идёт МИМО туннеля — иначе петля на собственный upstream.
            .addDisallowedApplication(packageName)
    }

    private fun writeTun2SocksConfig(host: String, port: Int): String {
        val file = File(cacheDir, "tun2socks.yaml")
        file.writeText(
            """
            tunnel:
              mtu: 8500
              multi-queue: true
              ipv4: 26.26.26.1
            socks5:
              address: "$host"
              port: $port
              udp: 'udp'
            misc:
              log-level: warn
            """.trimIndent() + "\n",
        )
        return file.absolutePath
    }

    // -------------------------------------------------------------- прочее
    private fun closeFd(fd: Int) {
        runCatching { ParcelFileDescriptor.adoptFd(fd).close() }
    }

    private fun finishSelf(startId: Int? = null) {
        stopForeground(STOP_FOREGROUND_REMOVE)
        if (startId != null) stopSelfResult(startId) else stopSelf()
    }

    private fun startForegroundNotification() {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "Прокси-соединение", NotificationManager.IMPORTANCE_LOW)
        )
        val stopIntent = Intent(this, SharingVpnService::class.java).setAction(ACTION_STOP)
        val notification: Notification = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(R.drawable.ic_shield)
            .setContentTitle("Sharing Connect")
            .setContentText("Трафик идёт через прокси ПК")
            .setOngoing(true)
            .addAction(0, "Отключить", android.app.PendingIntent.getService(
                this, 0, stopIntent,
                android.app.PendingIntent.FLAG_IMMUTABLE
            ))
            .build()
        startForeground(NOTIFICATION_ID, notification)
    }

    override fun onDestroy() {
        VpnState.set(TunnelStatus.STOPPED)
        tunnelLooper.quitSafely()
        super.onDestroy()
    }

    companion object {
        const val ACTION_STOP = "com.zentrix.connect.STOP"
        private const val CHANNEL_ID = "sharing_tunnel"
        private const val NOTIFICATION_ID = 1
        private const val HTTP_CONVERTER_PORT = 18080
    }
}
