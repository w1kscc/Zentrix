package com.zentrix.connect

import android.app.Activity
import android.content.Intent
import android.net.VpnService
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.zentrix.connect.data.ProxyConfig
import com.zentrix.connect.data.ProxyProtocol
import com.zentrix.connect.data.SettingsStore
import com.zentrix.connect.vpn.SharingVpnService
import com.zentrix.connect.vpn.TunnelStatus
import com.zentrix.connect.vpn.VpnState
import kotlin.concurrent.thread

/** Палитра Zentrix. */
object ZentrixColors {
    val Bg = Color(0xFF080B12)
    val Card = Color(0x14FFFFFF)
    val Text = Color(0xFFEAF0FF)
    val Muted = Color(0xFF93A0B8)
    val Accent = Color(0xFF7C5CFF)
    val Accent2 = Color(0xFF22D3EE)
    val Success = Color(0xFF3DDC97)
    val Danger = Color(0xFFFF5C7A)
    val Warning = Color(0xFFFFC46B)
}

class MainActivity : ComponentActivity() {

    private lateinit var settings: SettingsStore

    private val vpnPermission =
        registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
            if (result.resultCode == Activity.RESULT_OK) {
                startForegroundService(Intent(this, SharingVpnService::class.java))
            } else {
                VpnState.log("Разрешение VPN не выдано")
                Toast.makeText(this, "Без разрешения VPN подключение невозможно", Toast.LENGTH_SHORT).show()
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        settings = SettingsStore(this)
        setContent { App() }
    }

    @Composable
    private fun App() {
        MaterialTheme(
            colorScheme = darkColorScheme(
                primary = ZentrixColors.Accent,
                background = ZentrixColors.Bg,
                surface = ZentrixColors.Bg,
                onPrimary = Color.White,
                onBackground = ZentrixColors.Text,
                onSurface = ZentrixColors.Text,
            ),
        ) {
            MainScreen()
        }
    }

    @Composable
    private fun MainScreen() {
        val status by VpnState.status.collectAsState()
        val logLines by VpnState.log.collectAsState()
        val proxy = remember { settings.proxy }
        var host by remember { mutableStateOf(proxy.host) }
        var port by remember { mutableStateOf(if (proxy.port > 0) proxy.port.toString() else "") }
        var protocol by remember { mutableStateOf(proxy.protocol) }
        val connected = status == TunnelStatus.RUNNING
        val busy = status == TunnelStatus.STARTING || status == TunnelStatus.STOPPING

        Column(
            Modifier
                .fillMaxSize()
                .background(ZentrixColors.Bg)
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 16.dp),
        ) {
            Spacer(Modifier.height(16.dp))
            Text("Sharing Connect", color = ZentrixColors.Text, fontSize = 22.sp, fontWeight = FontWeight.Bold)
            Text("Подключение к раздаче ПК (Zentrix Шеринг)", color = ZentrixColors.Muted, fontSize = 12.5.sp)
            Spacer(Modifier.height(20.dp))

            // --- большая кнопка ПУСК/СТОП ---
            BigButton(
                connected = connected,
                busy = busy,
                onClick = {
                    when {
                        busy -> return@BigButton
                        connected -> stopConnection()
                        else -> startConnection(host, port, protocol)
                    }
                },
            )
            Spacer(Modifier.height(10.dp))
            Text(
                when {
                    !connected && busy -> "ПОДКЛЮЧЕНИЕ…"
                    connected -> "ПОДКЛЮЧЕНО"
                    busy -> "ОТКЛЮЧЕНИЕ…"
                    else -> "ОТКЛЮЧЕНО"
                },
                color = when {
                    connected -> ZentrixColors.Success
                    busy -> ZentrixColors.Warning
                    else -> ZentrixColors.Muted
                },
                fontSize = 13.sp, fontWeight = FontWeight.Bold,
                modifier = Modifier.align(Alignment.CenterHorizontally),
                letterSpacing = 1.2.sp,
            )
            Spacer(Modifier.height(20.dp))

            // --- настройки подключения ---
            GlassCard(title = "Настройка прокси ПК") {
                Text("IP компьютера, на котором включена раздача", color = ZentrixColors.Muted, fontSize = 11.5.sp)
                Spacer(Modifier.height(4.dp))
                OutlinedTextField(
                    value = host,
                    onValueChange = { host = it.trim() },
                    placeholder = { Text("192.168.1.100", color = ZentrixColors.Muted) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    colors = fieldColors(),
                )
                Spacer(Modifier.height(10.dp))
                Text("Порт прокси", color = ZentrixColors.Muted, fontSize = 11.5.sp)
                Spacer(Modifier.height(4.dp))
                OutlinedTextField(
                    value = port,
                    onValueChange = { port = it.filter { char -> char.isDigit() } },
                    placeholder = { Text("10808", color = ZentrixColors.Muted) },
                    singleLine = true,
                    modifier = Modifier.fillMaxWidth(),
                    colors = fieldColors(),
                )
                Spacer(Modifier.height(12.dp))
                Text("Протокол", color = ZentrixColors.Muted, fontSize = 11.5.sp)
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    listOf(ProxyProtocol.SOCKS5 to "SOCKS5", ProxyProtocol.HTTP to "HTTP").forEach { (key, label) ->
                        OutlinedButton(
                            onClick = { protocol = key },
                            colors = ButtonDefaults.outlinedButtonColors(
                                contentColor = if (protocol == key) ZentrixColors.Accent else ZentrixColors.Muted,
                            ),
                        ) { Text(label) }
                    }
                }
            }
            Spacer(Modifier.height(12.dp))

            // --- журнал ---
            GlassCard(title = "Журнал") {
                if (logLines.isEmpty()) {
                    Text("Журнал пуст", color = ZentrixColors.Muted, fontSize = 12.5.sp)
                } else {
                    Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                        logLines.reversed().take(8).forEach { line ->
                            Text(line, color = ZentrixColors.Muted, fontSize = 11.5.sp, lineHeight = 15.sp)
                        }
                    }
                }
            }
            Spacer(Modifier.height(24.dp))
        }
    }

    // ------------------------------------------------------------ действия
    private fun startConnection(host: String, port: String, protocol: ProxyProtocol) {
        val config = ProxyConfig(host = host, port = port.toIntOrNull() ?: 0, protocol = protocol)
        if (!config.isValid) {
            Toast.makeText(this, "Заполните IP и порт прокси ПК", Toast.LENGTH_SHORT).show()
            return
        }
        settings.proxy = config
        VpnState.log("Профиль сохранён: ${config.uri}")
        val intent = VpnService.prepare(this)
        if (intent == null) {
            startForegroundService(Intent(this, SharingVpnService::class.java))
        } else {
            vpnPermission.launch(intent)
        }
    }

    private fun stopConnection() {
        startService(
            Intent(this, SharingVpnService::class.java).setAction(SharingVpnService.ACTION_STOP)
        )
    }
}

// -------------------------------------------------------------- UI-мелочи
@Composable
private fun fieldColors() = OutlinedTextFieldDefaults.colors(
    focusedTextColor = ZentrixColors.Text,
    unfocusedTextColor = ZentrixColors.Text,
    cursorColor = ZentrixColors.Accent,
    focusedBorderColor = ZentrixColors.Accent,
    unfocusedBorderColor = ZentrixColors.Muted.copy(alpha = 0.4f),
)

@Composable
private fun GlassCard(title: String? = null, content: @Composable () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth(),
        shape = RoundedCornerShape(18.dp),
        colors = CardDefaults.cardColors(containerColor = ZentrixColors.Card),
    ) {
        Column(Modifier.padding(16.dp)) {
            if (title != null) {
                Text(title, color = ZentrixColors.Text, fontSize = 16.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(10.dp))
            }
            content()
        }
    }
}

/** Большая круглая кнопка ПУСК/СТОП в стиле Zentrix: кольца + градиент. */
@Composable
private fun BigButton(connected: Boolean, busy: Boolean, onClick: () -> Unit) {
    val accent = when {
        busy -> ZentrixColors.Warning
        connected -> ZentrixColors.Accent2
        else -> ZentrixColors.Accent
    }
    Box(Modifier.fillMaxWidth(), contentAlignment = Alignment.Center) {
        Box(
            modifier = Modifier
                .size(160.dp)
                .clip(CircleShape)
                .background(
                    Brush.radialGradient(
                        listOf(accent.copy(alpha = if (connected) 0.5f else 0.2f), Color.Transparent),
                    ),
                ),
        )
        Box(
            modifier = Modifier
                .size(124.dp)
                .clip(CircleShape)
                .background(Brush.linearGradient(listOf(accent, accent.copy(alpha = 0.7f))))
                .border(2.dp, Color.White.copy(alpha = 0.25f), CircleShape)
                .clickableNoRipple(onClick),
            contentAlignment = Alignment.Center,
        ) {
            Text(
                when {
                    busy -> "…" 
                    connected -> "СТОП"
                    else -> "ПУСК"
                },
                color = Color.White,
                fontSize = 26.sp,
                fontWeight = FontWeight.ExtraBold,
                letterSpacing = 2.sp,
            )
        }
    }
}

private fun Modifier.clickableNoRipple(onClick: () -> Unit): Modifier =
    this.then(Modifier.clickable(onClick = onClick))
