package com.sharingconnect.vpn

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.net.IpPrefix
import android.net.VpnService
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import android.os.ParcelFileDescriptor
import androidx.core.app.NotificationCompat
import com.sharingconnect.R
import com.sharingconnect.data.ProxyConfig
import com.sharingconnect.data.SettingsStore
import java.io.File

/**
 * VpnService Sharing Connect.
 *
 * Все операции туннеля (старт/стоп) выполняются СТРОГО последовательно
 * в одном фоновом потоке (HandlerThread): главный поток только ставит
 * задачи в очередь. Это исключает гонки «стоп начат — старт пришёл»,
 * из-за которых раньше кнопка переставала работать после отключения.
 */
class SharingVpnService : VpnService() {

    private lateinit var settings: SettingsStore

    private lateinit var tunnelLooper: HandlerThread
    private lateinit var tunnelHandler: Handler

    override fun onCreate() {
        super.onCreate()
        settings = SettingsStore(this)
        tunnelLooper = HandlerThread("sharing-tunnel").apply { start() }
        tunnelHandler = Handler(tunnelLooper.looper)
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val action = intent?.action
        if (action == ACTION_STOP) {
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
            LogRepo.log("Уже подключено/подключается — старт проигнорирован")
            return
        }
        val config = settings.proxy
        if (!config.isValid) {
            LogRepo.log("Адрес прокси не задан — отсканируйте QR из «Шеринга»")
            finishSelf(startId)
            return
        }
        setStatus(TunnelStatus.STARTING)
        LogRepo.log("Подключение к ${config.uri}…")

        // Останавливаем прошлый туннель, если нативный код ещё жив.
        stopNative(waitMs = 5000)

        // Прошлый VPN-интерфейс может держаться, пока нативный поток
        // прошлого туннеля не выйдет — ретраим establish до 5 раз.
        var tunFd: Int? = null
        for (attempt in 1..5) {
            try {
                tunFd = buildVpnInterface().establish()?.detachFd()
            } catch (error: Exception) {
                LogRepo.log("Ошибка VPN-интерфейса (попытка $attempt): ${error.message}")
            }
            if (tunFd != null) break
            LogRepo.log("VPN-интерфейс занят, жду… (попытка $attempt)")
            Thread.sleep(400)
        }
        if (tunFd == null) {
            LogRepo.log("Не удалось создать VPN-интерфейс за 5 попыток")
            setStatus(TunnelStatus.STOPPED)
            finishSelf(startId)
            return
        }

        val configFile = writeTun2SocksConfig(config)
        val started = Tun2Socks.start(configFile, tunFd)
        if (!started || !Tun2Socks.isRunning()) {
            LogRepo.log("tun2socks не запустился")
            closeFd(tunFd)
            setStatus(TunnelStatus.STOPPED)
            finishSelf(startId)
            return
        }
        setStatus(TunnelStatus.RUNNING)
        LogRepo.log("Подключено: ${config.uri}")
    }

    // ---------------------------------------------------------- остановка
    private fun doStop(userInitiated: Boolean, startId: Int) {
        // Всегда глушим нативный туннель, даже если статус-машина думает,
        // что всё остановлено: рассинхрон = зависший прокси в системе.
        setStatus(TunnelStatus.STOPPING)
        stopNative(waitMs = 5000)
        setStatus(TunnelStatus.STOPPED)
        if (userInitiated) {
            LogRepo.log("Отключено")
            finishSelf(startId)
        }
    }

    /** terminate + активное ожидание подтверждения остановки нативного туннеля. */
    private fun stopNative(waitMs: Long) {
        if (!Tun2Socks.isRunning()) return
        runCatching { Tun2Socks.terminate() }
        var waited = 0L
        while (Tun2Socks.isRunning() && waited < waitMs) {
            Thread.sleep(100)
            waited += 100
        }
        if (Tun2Socks.isRunning()) {
            LogRepo.log("tun2socks не подтвердил остановку за ${waitMs}мс")
        }
    }

    // ---------------------------------------------------------- интерфейс
    private fun buildVpnInterface(): Builder {
        val builder = Builder()
            .setSession("Sharing Connect")
            .setMtu(8500)
            .addAddress("26.26.26.1", 24)
            .addDnsServer("26.26.26.2")
            .addRoute("0.0.0.0", 1)
            .addRoute("128.0.0.0", 1)
        val config = settings.proxy
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            runCatching { builder.excludeRoute(IpPrefix(java.net.InetAddress.getByName(config.host), 32)) }
            if (!settings.routePrivateNetwork) {
                ROUTE_PRIVATE.forEach {
                    runCatching { builder.excludeRoute(IpPrefix(java.net.InetAddress.getByName(it.first), it.second)) }
                }
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
        return builder
    }

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

    private fun setStatus(status: TunnelStatus) = VpnState.set(status)

    override fun onDestroy() {
        VpnState.set(TunnelStatus.STOPPED)
        tunnelLooper.quitSafely()
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
