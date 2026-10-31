package com.sharingconnect

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.List
import androidx.compose.material.icons.filled.Settings
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import com.google.zxing.integration.android.IntentIntegrator
import com.sharingconnect.data.ProxyConfig
import com.sharingconnect.data.SettingsStore
import com.sharingconnect.net.ConnectionTester
import com.sharingconnect.net.ReleaseChecker
import com.sharingconnect.ui.LogScreen
import com.sharingconnect.ui.ProxyScreen
import com.sharingconnect.ui.SettingsScreen
import com.sharingconnect.ui.ZentrixColors
import com.sharingconnect.vpn.LogRepo
import com.sharingconnect.vpn.SharingVpnService
import kotlin.concurrent.thread

class MainActivity : ComponentActivity() {

    private lateinit var settings: SettingsStore

    private val vpnPermission =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == Activity.RESULT_OK) {
                startForegroundService(Intent(this, SharingVpnService::class.java))
            } else {
                LogRepo.log("Разрешение VPN не выдано")
                Toast.makeText(this, "Без разрешения VPN подключение невозможно", Toast.LENGTH_SHORT).show()
            }
        }

    private val qrScanner =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            val contents = IntentIntegrator.parseActivityResult(result.resultCode, result.data)?.contents
            if (contents != null) {
                ProxyConfig.parse(contents)?.let { parsed ->
                    settings.proxy = parsed
                    LogRepo.log("Прокси из QR: ${parsed.uri}")
                    Toast.makeText(this, "Прокси сохранён: ${parsed.uri}", Toast.LENGTH_SHORT).show()
                } ?: run {
                    LogRepo.log("QR не распознан: ${contents.take(40)}")
                    Toast.makeText(this, "QR не содержит адрес прокси Zentrix", Toast.LENGTH_SHORT).show()
                }
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = SettingsStore(this)
        // QR из внешнего сканера или share-интент: socks5://host:port
        intent?.getStringExtra(Intent.EXTRA_TEXT)?.let { raw ->
            ProxyConfig.parse(raw)?.let { settings.proxy = it }
        }
        setContent { App() }
    }

    @Composable
    private fun App() {
        val darkTheme = when (settings.theme) {
            "dark" -> true
            "light" -> false
            else -> isSystemInDarkTheme()
        }
        MaterialTheme(
            colorScheme = if (darkTheme) darkColorScheme(
                primary = ZentrixColors.Accent,
                secondary = ZentrixColors.Accent2,
                background = ZentrixColors.Bg,
                surface = ZentrixColors.Bg2,
                onPrimary = Color.White,
                onBackground = ZentrixColors.Text,
                onSurface = ZentrixColors.Text,
            ) else lightColorScheme(
                primary = ZentrixColors.Accent,
                secondary = ZentrixColors.Accent2,
            ),
        ) {
            MainLayout()
        }
    }

    @Composable
    private fun MainLayout() {
        var tab by remember { mutableStateOf(0) }
        val logLines by LogRepo.live.collectAsState()

        Scaffold(
            containerColor = ZentrixColors.Bg,
            bottomBar = {
                NavigationBar(containerColor = ZentrixColors.Bg2) {
                    NavigationBarItem(
                        selected = tab == 0, onClick = { tab = 0 },
                        icon = { Icon(Icons.Filled.Shield, null) }, label = { Text("Прокси") },
                    )
                    NavigationBarItem(
                        selected = tab == 1, onClick = { tab = 1 },
                        icon = { Icon(Icons.Filled.List, null) }, label = { Text("Журнал") },
                    )
                    NavigationBarItem(
                        selected = tab == 2, onClick = { tab = 2 },
                        icon = { Icon(Icons.Filled.Settings, null) }, label = { Text("Настройки") },
                    )
                }
            },
        ) { padding ->
            Column(
                Modifier
                    .fillMaxSize()
                    .background(ZentrixColors.Bg)
                    .padding(padding),
            ) {
                when (tab) {
                    0 -> ProxyScreen(
                        settings = settings,
                        connected = false, // статус читается из службы в реальной сборке
                        onToggle = ::toggleConnection,
                        onScanQr = ::scanQr,
                    )
                    1 -> LogScreen()
                    2 -> SettingsScreen(
                        settings = settings,
                        onOpenApps = ::openAppPicker,
                        onUpdateCheck = ::checkRelease,
                    )
                }
            }
        }
    }

    private fun toggleConnection() {
        val config = settings.proxy
        if (!config.isValid) {
            Toast.makeText(this, "Сначала отсканируйте QR из «Шеринга»", Toast.LENGTH_SHORT).show()
            scanQr()
            return
        }
        if (settings.testConnection) {
            thread {
                val result = ConnectionTester.test(config.host, config.port, config.protocol)
                runOnUiThread {
                    result.fold({ latency ->
                        LogRepo.log("Тест соединения: OK · $latency мс")
                        requestVpnAndStart()
                    }, { error ->
                        LogRepo.log("Тест соединения не прошёл: ${error.message}")
                        Toast.makeText(this, "Прокси недоступен: ${error.message}", Toast.LENGTH_LONG).show()
                    })
                }
            }
            return
        }
        requestVpnAndStart()
    }

    private fun requestVpnAndStart() {
        val intent = VpnService.prepare(this)
        if (intent == null) {
            vpnPermission.launch(Intent(this, SharingVpnService::class.java))
        } else {
            vpnPermission.launch(intent)
        }
    }

    private fun scanQr() {
        val integrator = IntentIntegrator(this)
        integrator.setPrompt("Отсканируйте QR-код из вкладки «Шеринг» Zentrix")
        integrator.setDesiredBarcodeFormats(IntentIntegrator.QR_CODE)
        integrator.setBeepEnabled(true)
        integrator.initiateScan()
    }

    private fun openAppPicker(kind: String) {
        startActivity(
            Intent(this, Class.forName("com.sharingconnect.ui.AppPickerActivity"))
                .putExtra("kind", kind)
        )
    }

    private fun checkRelease() {
        thread {
            val current = BuildConfig.VERSION_NAME
            val outcome = runCatching { ReleaseChecker.fetchLatest() }
            runOnUiThread {
                outcome.fold({ release ->
                    if (ReleaseChecker.isNewer(current, release.version)) {
                        LogRepo.log("Доступна новая версия: ${release.version}")
                        Toast.makeText(this, "Новая версия: ${release.version} — страница релиза открыта в README проекта", Toast.LENGTH_LONG).show()
                    } else {
                        LogRepo.log("Установлена актуальная версия ($current)")
                        Toast.makeText(this, "У вас актуальная версия $current", Toast.LENGTH_SHORT).show()
                    }
                }, { error ->
                    LogRepo.log("Проверка версии: ${error.message}")
                    Toast.makeText(this, "Не удалось проверить версию", Toast.LENGTH_SHORT).show()
                })
            }
        }
    }
}
