package com.sharingconnect.vpn

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.net.IpPrefix
import android.net.VpnService
import android.os.Build
import android.os.ParcelFileDescriptor
import androidx.core.app.NotificationCompat
import com.sharingconnect.R
import com.sharingconnect.data.ProxyConfig
import com.sharingconnect.data.SettingsStore
import java.io.File

/**
 * VpnService Sharing Connect: поднимает TUN-интерфейс и передаёт его
 * tun2socks, который заворачивает трафик в SOCKS5/HTTP прокси ПК
 * (вкладка «Шеринг» Zentrix).
 *
 * Split tunneling (разрешённые/запрещённые приложения) и правила
 * брандмауэра настраиваются в разделе «Настройки» — бесплатно, без PRO.
 */
class SharingVpnService : VpnService() {

    private lateinit var settings: SettingsStore
    private var tunnelFd: ParcelFileDescriptor? = null
    private var tunnelThread: Thread? = null

    override fun onCreate() {
        super.onCreate()
        settings = SettingsStore(this)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_STOP) {
            stopTunnel()
            return START_NOT_STICKY
        }
        startForegroundNotification()
        return startTunnel() ?: run {
            stopSelf()
            START_NOT_STICKY
        }
    }

    private fun startTunnel(): Int? {
        val config = settings.proxy
        if (!config.isValid) {
            LogRepo.log("Адрес прокси не задан — отсканируйте QR из «Шеринга»")
            return null
        }
        stopTunnel(quiet = true)

        val builder = Builder()
            .setSession("Sharing Connect")
            .setMtu(8500)
            .addAddress("26.26.26.1", 24)
            .addDnsServer("26.26.26.2")
            // Весь IPv4 уходит в туннель; исключения — только сам ПК-адрес и LAN
            .addRoute("0.0.0.0", 1)
            .addRoute("128.0.0.0", 1)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            runCatching { builder.excludeRoute(IpPrefix(java.net.InetAddress.getByName(config.host), 32)) }
            if (settings.routePrivateNetwork.not()) {
                ROUTE_PRIVATE.forEach { runCatching { builder.excludeRoute(IpPrefix(java.net.InetAddress.getByName(it.first), it.second)) } }
            }
        }

        // Split tunneling: разрешённые приложения (если заданы) или запрещённые
        val allowed = settings.allowedApps()
        val disallowed = settings.disallowedApps()
        if (allowed.isNotEmpty()) {
            allowed.forEach(builder::addAllowedApplication)
        } else {
            disallowed.forEach(builder::addDisallowedApplication)
        }

        val tunFd = try {
            builder.establish()?.detachFd()
        } catch (error: Exception) {
            LogRepo.log("Не удалось поднять VPN: ${error.message}")
            return null
        }
        if (tunFd == null) {
            LogRepo.log("VPN-разрешение не выдано системой")
            return null
        }

        // tun2socks — синглтон: дожидаемся полной остановки прошлого туннеля.
        if (Tun2Socks.isRunning()) {
            Tun2Socks.terminate()
            var waited = 0
            while (Tun2Socks.isRunning() && waited < 3000) {
                Thread.sleep(100)
                waited += 100
            }
        }
        // tun2socks — синглтон: полностью останавливаем прошлый туннель и
        // дожидаемся, пока нативный код подтвердит остановку.
        if (Tun2Socks.isRunning()) {
            LogRepo.log("Останавливаю предыдущий туннель…")
            Tun2Socks.terminate()
            var waited = 0
            while (Tun2Socks.isRunning() && waited < 5000) {
                Thread.sleep(100)
                waited += 100
            }
            if (Tun2Socks.isRunning()) {
                LogRepo.log("Не удалось остановить предыдущий туннель — попробуйте ещё раз")
                return null
            }
        }
        val configFile = writeTun2SocksConfig(config)
        LogRepo.log("Подключение к ${config.uri}…")
        tunnelThread = Thread {
            val started = Tun2Socks.start(configFile, tunFd)
            if (!started) LogRepo.log("tun2socks не запустился")
            VpnState.set(false)
            LogRepo.log("Туннель завершён")
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }.also { it.start() }
        VpnState.set(true)
        LogRepo.log("Подключено: ${config.uri}")
        return START_STICKY
    }

    /** YAML-конфиг hev-socks5-tunnel: TUN fd передаётся отдельным аргументом. */
    private fun writeTun2SocksConfig(config: ProxyConfig): String {
        val file = File(cacheDir, "tun2socks.yaml")
        file.writeText(
            """
            tun:
              mtu: 8500
              multi-queue: true
            socks5:
              address: "${config.host}"
              port: ${config.port}
              udp: 'udp'
            misc:
              log-level: warn
            """.trimIndent() + "\n",
        )
        return file.absolutePath
    }

    private fun stopTunnel(quiet: Boolean = false) {
        VpnState.set(false)
        if (Tun2Socks.isRunning()) {
            runCatching { Tun2Socks.terminate() }
            var waited = 0
            while (Tun2Socks.isRunning() && waited < 5000) {
                Thread.sleep(100)
                waited += 100
            }
        }
        tunnelThread?.join(2000)
        tunnelThread = null
        if (!quiet) {
            LogRepo.log("Отключено")
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun startForegroundNotification() {
        val manager = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "Прокси-соединение", NotificationManager.IMPORTANCE_LOW)
            )
        }
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

    private fun String.parseIpv4Cidr(): Pair<String, Int> {
        val address = substringBefore('/')
        val prefix = substringAfter('/', "32").toInt()
        return address to prefix
    }

    override fun onDestroy() {
        VpnState.set(false)
        stopTunnel(quiet = true)
        super.onDestroy()
    }

    companion object {
        const val ACTION_STOP = "com.sharingconnect.STOP"
        private const val CHANNEL_ID = "sharing_tunnel"
        private const val NOTIFICATION_ID = 1

        /** Частные диапазоны, исключаемые из туннеля по умолчанию. */
        private val ROUTE_PRIVATE = listOf(
            "10.0.0.0" to 8, "172.16.0.0" to 12, "192.168.0.0" to 16,
            "169.254.0.0" to 16, "127.0.0.0" to 8, "224.0.0.0" to 4,
        )
    }
}
