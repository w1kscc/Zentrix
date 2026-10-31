package com.sharingconnect.vpn

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Intent
import android.net.VpnService
import android.os.Build
import android.os.Handler
import android.os.HandlerThread
import androidx.core.app.NotificationCompat
import com.hiddify.core.mobile.Mobile
import com.hiddify.core.mobile.SetupOptions
import com.sharingconnect.R
import com.sharingconnect.data.ProxyConfig
import com.sharingconnect.data.SettingsStore
import java.io.File

/**
 * VpnService Sharing Connect на движке Hiddify Core (sing-box/libbox).
 *
 * Go-ядро само поднимает TUN через колбэк openTun в
 * [CorePlatform] (паттерн Hiddify/SFA), а мы лишь передаём sing-box
 * конфиг строкой: Mobile.start("", configJson) / Mobile.stop().
 *
 * Все операции выполняются СТРОГО последовательно в фоновом потоке
 * службы (HandlerThread) — гонки старт/стоп исключены.
 */
class SharingVpnService : VpnService() {

    private lateinit var settings: SettingsStore

    private lateinit var tunnelLooper: HandlerThread
    private lateinit var tunnelHandler: Handler
    private val corePlatform by lazy { CorePlatform(this) }

    override fun onCreate() {
        super.onCreate()
        settings = SettingsStore(this)
        AppContext.context = this
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

        try {
            coreSetupOnce()
            corePlatform.activeProfileName = config.uri
            // Конфиг передаём строкой: TUN будет создан в openTun колбэке.
            val configJson = buildSingBoxConfig(config)
            Mobile.start("", configJson)
        } catch (error: Throwable) {
            LogRepo.log("Не удалось запустить ядро: ${error.message}")
            setStatus(TunnelStatus.STOPPED)
            finishSelf(startId)
            return
        }
        setStatus(TunnelStatus.RUNNING)
        LogRepo.log("Подключено: ${config.uri}")
    }

    // ---------------------------------------------------------- остановка
    private fun doStop(userInitiated: Boolean, startId: Int) {
        setStatus(TunnelStatus.STOPPING)
        try {
            Mobile.stop()
            LogRepo.log("Ядро остановлено")
        } catch (error: Throwable) {
            LogRepo.log("Ошибка остановки ядра: ${error.message}")
        }
        setStatus(TunnelStatus.STOPPED)
        if (userInitiated) {
            LogRepo.log("Отключено")
            finishSelf(startId)
        }
    }

    // --------------------------------------------------------------- ядро
    private fun coreSetupOnce() {
        val baseDir = filesDir.apply { mkdirs() }
        val workingDir = getExternalFilesDir(null)?.apply { mkdirs() } ?: filesDir
        val tempDir = cacheDir.apply { mkdirs() }
        Mobile.setup(
            SetupOptions().also {
                it.basePath = baseDir.path
                it.workingDir = workingDir.path
                it.tempDir = tempDir.path
                it.mode = 4L            // GRPC_BACKGROUND_INSECURE — как в Hiddify
                it.listen = "127.0.0.1:2334"
                it.secret = ""
                it.debug = false
                it.fixAndroidStack = false
            },
            corePlatform,
        )
    }

    // ------------------------------------------------------- конфиг ядра
    /**
     * Sing-box конфиг: TUN-вход + SOCKS5-выход на ПК.
     * Split tunneling и исключения маршрутов — в самом конфиге.
     */
    private fun buildSingBoxConfig(config: ProxyConfig): String {
        val allowed = settings.allowedApps()
        val disallowed = settings.disallowedApps()
        val excludeAddr = mutableListOf("\"${config.host}/32\"")
        if (!settings.routePrivateNetwork) {
            listOf("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16",
                "169.254.0.0/16", "224.0.0.0/4").forEach { excludeAddr.add("\"$it\"") }
        }

        val sb = StringBuilder()
        sb.append("{\n")
        sb.append("  \"log\": {\"level\": \"info\", \"timestamp\": true},\n")
        sb.append("  \"dns\": {\n")
        sb.append("    \"servers\": [\n")
        sb.append("      {\"tag\": \"proxy-dns\", \"type\": \"udp\", \"server\": \"1.1.1.1\", \"detour\": \"pc\"},\n")
        sb.append("      {\"tag\": \"local-dns\", \"type\": \"local\"}\n")
        sb.append("    ],\n")
        sb.append("    \"rules\": [{\"outbound\": \"any\", \"server\": \"local-dns\"}],\n")
        sb.append("    \"final\": \"proxy-dns\"\n")
        sb.append("  },\n")
        sb.append("  \"inbounds\": [{\n")
        sb.append("    \"type\": \"tun\", \"tag\": \"tun-in\", \"mtu\": 8500,\n")
        sb.append("    \"address\": [\"172.19.0.1/30\"],\n")
        sb.append("    \"auto_route\": true, \"strict_route\": false, \"stack\": \"mixed\"")
        if (allowed.isNotEmpty()) {
            sb.append(",\n    \"include_package\": ")
            sb.append(allowed.joinToString(",", "[", "]") { "\"$it\"" })
        } else if (disallowed.isNotEmpty()) {
            sb.append(",\n    \"exclude_package\": ")
            sb.append(disallowed.joinToString(",", "[", "]") { "\"$it\"" })
        }
        sb.append(",\n    \"route_exclude_address\": ")
        sb.append(excludeAddr.joinToString(",", "[", "]"))
        sb.append("\n  }],\n")
        sb.append("  \"outbounds\": [\n")
        sb.append("    {\"type\": \"socks\", \"tag\": \"pc\", \"server\": \"${config.host}\", \"server_port\": ${config.port}},\n")
        sb.append("    {\"type\": \"direct\", \"tag\": \"direct\"}\n")
        sb.append("  ],\n")
        sb.append("  \"route\": {\n")
        sb.append("    \"auto_detect_interface\": true,\n")
        sb.append("    \"rules\": [{\"action\": \"sniff\"}, {\"protocol\": \"dns\", \"action\": \"hijack-dns\"}],\n")
        sb.append("    \"final\": \"pc\"\n")
        sb.append("  }\n")
        sb.append("}")
        return sb.toString()
    }

    // -------------------------------------------------------------- прочее
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


    /** Построение VPN-интерфейса из TunOptions ядра (паттерн Hiddify/SFA). */
    fun newVpnBuilder(options: com.hiddify.core.libbox.TunOptions): Builder {
        val builder = Builder()
            .setSession("Sharing Connect")
            .setMtu(options.mtu)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) builder.setMetered(false)

        val inet4 = options.inet4Address
        while (inet4.hasNext()) builder.addAddress(inet4.next().address(), inet4.next().prefix())
        val inet6 = options.inet6Address
        while (inet6.hasNext()) builder.addAddress(inet6.next().address(), inet6.next().prefix())

        if (options.autoRoute) {
            if (options.dnsMode.value != com.hiddify.core.libbox.Libbox.DNSModeDisabled) {
                val dns = options.dnsServerAddress
                while (dns.hasNext()) builder.addDnsServer(dns.next())
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                val routes = options.inet4RouteAddress
                while (routes.hasNext()) routes.next().string().applyCidr(builder, exclude = false)
                val routes6 = options.inet6RouteAddress
                while (routes6.hasNext()) routes6.next().string().applyCidr(builder, exclude = false)
                val excl = options.inet4RouteExcludeAddress
                while (excl.hasNext()) excl.next().string().applyCidr(builder, exclude = true)
                val excl6 = options.inet6RouteExcludeAddress
                while (excl6.hasNext()) excl6.next().string().applyCidr(builder, exclude = true)
            } else {
                val routes = options.inet4RouteRange
                while (routes.hasNext()) {
                    val address = routes.next()
                    builder.addRoute(address.address(), address.prefix())
                }
            }
        }
        // само приложение не заворачиваем в собственный туннель
        builder.addDisallowedApplication(packageName)
        return builder
    }

    private fun String.applyCidr(builder: Builder, exclude: Boolean) {
        val address = java.net.InetAddress.getByName(substringBefore('/'))
        val prefix = substringAfter('/').toInt()
        if (exclude) builder.excludeRoute(android.net.IpPrefix(address, prefix))
        else builder.addRoute(address, prefix)
    }

    override fun onDestroy() {
        VpnState.set(TunnelStatus.STOPPED)
        tunnelLooper.quitSafely()
        super.onDestroy()
    }

    companion object {
        const val ACTION_STOP = "com.sharingconnect.STOP"
        private const val CHANNEL_ID = "sharing_tunnel"
        private const val NOTIFICATION_ID = 1
    }
}
