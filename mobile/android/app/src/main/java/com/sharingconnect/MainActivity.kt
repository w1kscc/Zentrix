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
import androidx.compose.material.icons.filled.Home
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
import com.journeyapps.barcodescanner.ScanContract
import com.journeyapps.barcodescanner.ScanOptions
import com.sharingconnect.data.ProxyConfig
import com.sharingconnect.data.SettingsStore
import com.sharingconnect.net.ConnectionTester
import com.sharingconnect.net.ReleaseInfo
import com.sharingconnect.net.ReleaseChecker
import com.sharingconnect.ui.HomeScreen
import com.sharingconnect.ui.TestScreen
import com.sharingconnect.ui.ProfileEditorScreen
import com.sharingconnect.ui.ProxyScreen
import com.sharingconnect.ui.SettingsScreen
import com.sharingconnect.ui.ZentrixColors
import com.sharingconnect.vpn.LogRepo
import com.sharingconnect.vpn.SharingVpnService
import com.sharingconnect.vpn.TunnelStatus
import com.sharingconnect.vpn.VpnState
import kotlin.concurrent.thread

class MainActivity : ComponentActivity() {

    private lateinit var settings: SettingsStore
    private var profileVersion by mutableStateOf(0)  // сигнал перерисовать профиль

    private val vpnPermission =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == Activity.RESULT_OK) {
                startForegroundService(Intent(this, SharingVpnService::class.java))
            } else {
                LogRepo.log("Разрешение VPN не выдано")
                Toast.makeText(this, "Без разрешения VPN подключение невозможно", Toast.LENGTH_SHORT).show()
            }
        }

    /** QR-сканер через ScanContract — результат приходит гарантированно. */
    private val qrScanner = registerForActivityResult(ScanContract()) { result ->
        val contents = result.contents
        if (contents == null) {
            LogRepo.log("Сканирование отменено")
            return@registerForActivityResult
        }
        val parsed = ProxyConfig.parse(contents)
        if (parsed == null) {
            LogRepo.log("QR не содержит адрес прокси: ${contents.take(60)}")
            Toast.makeText(this, "Это не QR из «Шеринга» Zentrix", Toast.LENGTH_LONG).show()
            return@registerForActivityResult
        }
        settings.proxy = parsed
        profileVersion++
        LogRepo.log("Прокси из QR: ${parsed.uri}")
        Toast.makeText(this, "Сохранено: ${parsed.uri}", Toast.LENGTH_LONG).show()
    }

    private val appPicker =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = SettingsStore(this)
        // Приём адреса из внешнего сканера / share-интента
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
        var editingProfile by remember { mutableStateOf(false) }

        Scaffold(
            containerColor = ZentrixColors.Bg,
            bottomBar = {
                NavigationBar(containerColor = ZentrixColors.Bg2) {
                    NavigationBarItem(
                        selected = tab == 0, onClick = { tab = 0 },
                        icon = { Icon(Icons.Filled.Home, null) }, label = { Text("Главная") },
                    )
                    NavigationBarItem(
                        selected = tab == 1, onClick = { tab = 1 },
                        icon = { Icon(Icons.Filled.Shield, null) }, label = { Text("Прокси") },
                    )
                    NavigationBarItem(
                        selected = tab == 2, onClick = { tab = 2 },
                        icon = { Icon(Icons.Filled.List, null) }, label = { Text("Тест") },
                    )
                    NavigationBarItem(
                        selected = tab == 3, onClick = { tab = 3 },
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
                    0 -> HomeScreen(
                        settings = settings,
                        profileVersion = profileVersion,
                        onStart = ::startConnection,
                        onStop = ::stopConnection,
                        onGoProxy = { tab = 1 },
                    )
                    1 -> {
                        if (editingProfile) {
                            ProfileEditorScreen(
                                settings = settings,
                                onSaved = {
                                    profileVersion++
                                    editingProfile = false
                                },
                                onCancelled = { editingProfile = false },
                            )
                        } else {
                            ProxyScreen(
                                settings = settings,
                                profileVersion = profileVersion,
                                onStart = ::startConnection,
                                onStop = ::stopConnection,
                                onScanQr = ::scanQr,
                                onEditProfile = { editingProfile = true },
                            )
                        }
                    }
                    2 -> TestScreen(settings = settings)
                    3 -> SettingsScreen(
                        settings = settings,
                        onOpenApps = ::openAppPicker,
                        onUpdateCheck = ::checkRelease,
                    )
                }
            }
        }
    }

    /** «Запустить» — тест соединения (по настройке) и старт службы. */
    private fun startConnection() {
        val config = settings.proxy
        if (!config.isValid) {
            Toast.makeText(
                this,
                "Сначала сохраните профиль: отсканируйте QR или заполните вручную",
                Toast.LENGTH_LONG,
            ).show()
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

    /** «Выключить» — всегда отправляет явную команду остановки службе. */
    private fun stopConnection() {
        startService(
            Intent(this, SharingVpnService::class.java)
                .setAction(SharingVpnService.ACTION_STOP)
        )
    }

    private fun requestVpnAndStart() {
        val intent = VpnService.prepare(this)
        if (intent == null) {
            // Разрешение уже выдано — запускаем СЛУЖБУ (не через activity-launcher!).
            startForegroundService(Intent(this, SharingVpnService::class.java))
        } else {
            // Системный диалог запроса разрешения VPN.
            vpnPermission.launch(intent)
        }
    }

    private fun scanQr() {
        val options = ScanOptions()
            .setPrompt("Наведите камеру на QR-код из вкладки «Шеринг» Zentrix")
            .setDesiredBarcodeFormats(ScanOptions.QR_CODE)
            .setBeepEnabled(true)
            .setOrientationLocked(false)
        qrScanner.launch(options)
    }

    private fun openAppPicker(kind: String) {
        appPicker.launch(
            Intent(this, com.sharingconnect.ui.AppPickerActivity::class.java).putExtra("kind", kind)
        )
    }

    private fun checkRelease(onResult: (ReleaseInfo?) -> Unit) {
        thread {
            val outcome = runCatching { ReleaseChecker.fetchLatest() }
            runOnUiThread {
                outcome.fold({ release ->
                    val current = BuildConfig.VERSION_NAME
                    if (ReleaseChecker.isNewer(current, release.version)) {
                        LogRepo.log("Доступна новая версия APK: ${release.version}")
                    } else {
                        LogRepo.log("Установлена актуальная версия ($current)")
                    }
                    onResult(release)
                }, { error ->
                    LogRepo.log("Проверка версии: ${error.message}")
                    onResult(null)
                })
            }
        }
    }
}
