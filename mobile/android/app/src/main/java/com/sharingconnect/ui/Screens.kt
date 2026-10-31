package com.sharingconnect.ui

import androidx.compose.animation.core.LinearEasing
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
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
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.border
import androidx.compose.material.icons.Icons
import androidx.compose.material3.Icon
import androidx.compose.foundation.clickable
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.filled.Shield
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
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
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import android.widget.Toast
import com.sharingconnect.data.ProxyConfig
import com.sharingconnect.BuildConfig
import com.sharingconnect.data.SettingsStore
import com.sharingconnect.vpn.LogRepo
import com.sharingconnect.net.ReleaseChecker
import com.sharingconnect.net.SpeedTestResult
import com.sharingconnect.net.SpeedTest
import kotlin.concurrent.thread
import com.sharingconnect.net.ReleaseInfo
import com.sharingconnect.vpn.TunnelStatus
import com.sharingconnect.vpn.VpnState

/** Палитра PC-версии Zentrix. */
object ZentrixColors {
    val Bg = Color(0xFF080B12)
    val Bg2 = Color(0xFF101726)
    val Card = Color(0x14FFFFFF)
    val CardStrong = Color(0x24FFFFFF)
    val Text = Color(0xFFEAF0FF)
    val Muted = Color(0xFF93A0B8)
    val Accent = Color(0xFF7C5CFF)
    val Accent2 = Color(0xFF22D3EE)
    val Success = Color(0xFF3DDC97)
    val Danger = Color(0xFFFF5C7A)
    val Warning = Color(0xFFFFC46B)
}

/** Карточка в стиле GlassCard из PC-версии. */
@Composable
fun GlassCard(modifier: Modifier = Modifier, title: String? = null, content: @Composable () -> Unit) {
    Card(
        modifier = modifier.fillMaxWidth(),
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

/** Строка настройки: заголовок, описание, переключатель. */
@Composable
fun ToggleRow(title: String, subtitle: String, checked: Boolean, onChange: (Boolean) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .padding(vertical = 8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Column(Modifier.weight(1f)) {
            Text(title, color = ZentrixColors.Text, fontSize = 15.sp, fontWeight = FontWeight.Medium)
            if (subtitle.isNotBlank()) {
                Text(subtitle, color = ZentrixColors.Muted, fontSize = 12.5.sp, lineHeight = 17.sp)
            }
        }
        Spacer(Modifier.width(12.dp))
        Switch(
            checked = checked,
            onCheckedChange = onChange,
            colors = SwitchDefaults.colors(
                checkedThumbColor = Color.White,
                checkedTrackColor = ZentrixColors.Accent,
                uncheckedTrackColor = ZentrixColors.Muted.copy(alpha = 0.30f),
            ),
        )
    }
}

@Composable
fun DangerButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier,
                 enabled: Boolean = true) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.height(46.dp),
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(
            containerColor = ZentrixColors.Danger.copy(alpha = if (enabled) 0.9f else 0.35f),
            contentColor = Color.White,
        ),
    ) {
        Text(text, fontWeight = FontWeight.SemiBold)
    }
}

@Composable
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier,
                  enabled: Boolean = true) {
    Button(
        onClick = onClick,
        enabled = enabled,
        modifier = modifier.height(46.dp),
        shape = RoundedCornerShape(12.dp),
        colors = ButtonDefaults.buttonColors(containerColor = Color.Transparent),
        contentPadding = androidx.compose.foundation.layout.PaddingValues(),
    ) {
        Box(
            Modifier
                .fillMaxSize()
                .background(Brush.linearGradient(listOf(ZentrixColors.Accent, Color(0xFF4C63E6)))),
            contentAlignment = Alignment.Center,
        ) {
            Text(text, color = Color.White, fontWeight = FontWeight.SemiBold)
        }
    }
}

@Composable
fun GhostButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    OutlinedButton(onClick = onClick, modifier = modifier.height(46.dp)) {
        Text(text, color = ZentrixColors.Text)
    }
}

/** Экран «Прокси»: большая круглая кнопка в центре, как на ПК. */
@Composable
fun ProxyScreen(
    settings: SettingsStore,
    profileVersion: Int,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onScanQr: () -> Unit,
    onEditProfile: () -> Unit,
) {
    val status by VpnState.status.collectAsState()
    val connected = status == TunnelStatus.RUNNING
    val busy = status == TunnelStatus.STARTING || status == TunnelStatus.STOPPING
    val proxy = remember(profileVersion) { settings.proxy }
    val canStart = proxy.isValid && !connected && !busy
    val canStop = connected

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        PageHeading("Прокси", "Соединение с ПК через QR или вручную")
        Spacer(Modifier.height(4.dp))

        // --- большая кнопка в центре ---
        BigConnectButton(status = status)
        Spacer(Modifier.height(14.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            PrimaryButton(
                text = "Запустить",
                onClick = onStart,
                enabled = canStart,
                modifier = Modifier.weight(1f),
            )
            DangerButton(
                text = "Выключить",
                onClick = onStop,
                enabled = canStop,
                modifier = Modifier.weight(1f),
            )
        }
        Spacer(Modifier.height(10.dp))
        Text(
            when {
                !proxy.isValid -> "Профиль не настроен"
                status == TunnelStatus.STARTING -> "ПОДКЛЮЧЕНИЕ…"
                status == TunnelStatus.STOPPING -> "ОТКЛЮЧЕНИЕ…"
                status == TunnelStatus.RUNNING -> "ПОДКЛЮЧЕНО"
                else -> "ОТКЛЮЧЕНО"
            },
            color = when {
                !proxy.isValid -> ZentrixColors.Muted
                status == TunnelStatus.RUNNING -> ZentrixColors.Success
                status == TunnelStatus.STARTING || status == TunnelStatus.STOPPING -> ZentrixColors.Warning
                else -> ZentrixColors.Muted
            },
            fontSize = 13.sp,
            fontWeight = FontWeight.Bold,
            letterSpacing = 1.2.sp,
        )
        Spacer(Modifier.height(18.dp))

        // --- профиль ---
        GlassCard(Modifier.fillMaxWidth()) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.weight(1f)) {
                    Text("Профиль подключения", color = ZentrixColors.Muted, fontSize = 11.5.sp)
                    Text(
                        if (proxy.isValid) proxy.uri else "Не настроен",
                        color = if (proxy.isValid) ZentrixColors.Text else ZentrixColors.Muted,
                        fontSize = 14.sp,
                        fontWeight = FontWeight.Medium,
                    )
                }
            }
            Spacer(Modifier.height(10.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GhostButton(text = "Сканировать QR", onClick = onScanQr, modifier = Modifier.weight(1f))
                GhostButton(text = "Изменить профиль", onClick = onEditProfile, modifier = Modifier.weight(1f))
            }
        }

        Spacer(Modifier.height(12.dp))
        GlassCard(title = "Как это работает", modifier = Modifier.fillMaxWidth()) {
            Text(
                "1. Во вкладке «Шеринг» PC-версии Zentrix включите раздачу." + chr(10) +
                    "2. Отсканируйте QR-код этим приложением или заполните профиль вручную." + chr(10) +
                    "3. Нажмите большую кнопку — трафик приложений пойдёт через ПК.",
                color = ZentrixColors.Muted,
                fontSize = 13.sp,
                lineHeight = 18.sp,
            )
        }
    }
}

private fun chr(code: Int): String = code.toChar().toString()

/**
 * Большая круглая кнопка подключения: концентрические кольца с градиентом,
 * пульсирующее свечение в подключённом состоянии — как hero-кнопка ПК-версии.
 */
@Composable
fun BigConnectButton(status: TunnelStatus) {
    val connected = status == TunnelStatus.RUNNING
    val busy = status == TunnelStatus.STARTING || status == TunnelStatus.STOPPING
    val pulse = rememberInfiniteTransition(label = "pulse")
    val glow by pulse.animateFloat(
        initialValue = 0.25f,
        targetValue = 0.65f,
        animationSpec = infiniteRepeatable(tween(1400, easing = LinearEasing)),
        label = "glow",
    )
    val ringColor = if (connected) ZentrixColors.Accent2 else ZentrixColors.Muted.copy(alpha = 0.35f)
    val glowAlpha = if (connected) glow else 0.10f

    Box(
        modifier = Modifier.size(240.dp),
        contentAlignment = Alignment.Center,
    ) {
        // внешнее кольцо — мягкое свечение
        Box(
            Modifier
                .size(240.dp)
                .clip(CircleShape)
                .background(
                    Brush.radialGradient(
                        listOf(ZentrixColors.Accent.copy(alpha = glowAlpha), Color.Transparent),
                    ),
                ),
        )
        // среднее кольцо
        Box(
            Modifier
                .size(190.dp)
                .clip(CircleShape)
                .background(Color.Transparent)
                .border(1.5.dp, ringColor.copy(alpha = if (connected) glowAlpha + 0.25f else 0.35f), CircleShape),
        )
        // внутреннее кольцо
        Box(
            Modifier
                .size(150.dp)
                .clip(CircleShape)
                .background(Color.Transparent)
                .border(1.dp, ringColor.copy(alpha = 0.55f), CircleShape),
        )
        // сама кнопка
        Box(
            modifier = Modifier
                .size(116.dp)
                .clip(CircleShape)
                .background(
                    Brush.linearGradient(
                        when {
                            busy -> listOf(ZentrixColors.Warning.copy(alpha = 0.85f), Color(0xFFB08A3E))
                            connected -> listOf(ZentrixColors.Accent2, Color(0xFF3B82F6))
                            else -> listOf(ZentrixColors.Accent, Color(0xFF4C63E6))
                        },
                    ),
                )
                .border(2.dp, Color.White.copy(alpha = 0.25f), CircleShape),
            contentAlignment = Alignment.Center,
        ) {
            Icon(
                imageVector = if (connected) Icons.Filled.Check else Icons.Filled.Shield,
                contentDescription = null,
                tint = Color.White,
                modifier = Modifier.size(46.dp),
            )
        }
    }
}

/** Экран профиля: имя/протокол/сервер/порт — как в референсах SuperProxy. */
@Composable
fun ProfileEditorScreen(settings: SettingsStore, onSaved: () -> Unit, onCancelled: () -> Unit) {
    val context = androidx.compose.ui.platform.LocalContext.current
    var protocol by remember { mutableStateOf(settings.proxy.protocol) }
    var host by remember { mutableStateOf(settings.proxy.host) }
    var port by remember { mutableStateOf(if (settings.proxy.port > 0) settings.proxy.port.toString() else "") }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        GlassCard(title = "Профиль") {
            FieldLabel("Протокол")
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("socks5" to "SOCKS5", "http" to "HTTP").forEach { (key, label) ->
                    OutlinedButton(
                        onClick = { protocol = key },
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = if (protocol == key) ZentrixColors.Accent else ZentrixColors.Muted,
                        ),
                    ) { Text(label) }
                }
            }
            Spacer(Modifier.height(10.dp))
            FieldLabel("Сервер")
            OutlinedTextField(
                value = host,
                onValueChange = { host = it },
                placeholder = { Text("IP компьютера из «Шеринга»", color = ZentrixColors.Muted) },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            Spacer(Modifier.height(10.dp))
            FieldLabel("Порт")
            OutlinedTextField(
                value = port,
                onValueChange = { port = it.filter { char -> char.isDigit() } },
                placeholder = { Text("10808", color = ZentrixColors.Muted) },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                PrimaryButton(
                    text = "Сохранить",
                    onClick = {
                        val config = ProxyConfig(
                            protocol = protocol,
                            host = host.trim(),
                            port = port.toIntOrNull() ?: 0,
                        )
                        if (config.isValid) {
                            settings.proxy = config
                            LogRepo.log("Профиль сохранён: ${config.uri}")
                            Toast.makeText(context, "Сохранено: ${config.uri}", Toast.LENGTH_SHORT).show()
                            onSaved()
                        } else {
                            Toast.makeText(context, "Заполните сервер и порт", Toast.LENGTH_SHORT).show()
                        }
                    },
                    modifier = Modifier.weight(1f),
                )
                GhostButton(text = "Отмена", onClick = onCancelled, modifier = Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun FieldLabel(text: String) {
    Text(text, color = ZentrixColors.Muted, fontSize = 12.sp)
    Spacer(Modifier.height(4.dp))
}

/** Экран «Тест»: скорость входящего/исходящего потока + журнал с копированием. */
@Composable
fun TestScreen(settings: SettingsStore) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val logLines by LogRepo.live.collectAsState()
    var testing by remember { mutableStateOf(false) }
    var down by remember { mutableStateOf<Double?>(null) }
    var up by remember { mutableStateOf<Double?>(null) }
    var progress by remember { mutableStateOf(0f) }
    var phase by remember { mutableStateOf("") }

    val mainHandler = android.os.Handler(android.os.Looper.getMainLooper())
    fun runTest() {
        val proxy = settings.proxy
        if (!proxy.isValid) {
            Toast.makeText(context, "Сначала настройте профиль во вкладке «Прокси»", Toast.LENGTH_SHORT).show()
            return
        }
        if (testing) return
        testing = true
        down = null; up = null; progress = 0f; phase = "Входящий поток…"
        LogRepo.log("Тест скорости: запуск (${proxy.uri})")
        thread {
            val result = runCatching {
                val d = SpeedTest.measureDown(proxy.host, proxy.port, proxy.protocol) { value ->
                    mainHandler.post { down = value }
                }
                mainHandler.post {
                    phase = "Исходящий поток…"
                    LogRepo.log(d?.let { "Входящий: $it Мбит/с" } ?: "Входящий: не удалось измерить")
                }
                val u = SpeedTest.measureUp(proxy.host, proxy.port, proxy.protocol) { value ->
                    mainHandler.post { up = value }
                }
                mainHandler.post {
                    LogRepo.log(u?.let { "Исходящий: $it Мбит/с" } ?: "Исходящий: не удалось измерить")
                }
                SpeedTestResult(d, u)
            }.getOrElse {
                LogRepo.log("Тест скорости: ошибка — ${it.message}")
                SpeedTestResult(null, null, it.message)
            }
            mainHandler.post {
                testing = false
                phase = if (result.error != null) "Ошибка: ${result.error}" else ""
                progress = 1f
                val text = "Тест завершён: ↓ ${result.downMbps ?: "—"} · ↑ ${result.upMbps ?: "—"} Мбит/с"
                Toast.makeText(context, text, Toast.LENGTH_SHORT).show()
            }
        }
    }

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text("Тест потока", color = ZentrixColors.Text, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Text("Скорость входящего и исходящего потока", color = ZentrixColors.Muted, fontSize = 12.5.sp)
        Spacer(Modifier.height(12.dp))
        GlassCard {
            Row(horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                StatColumn("ВХОДЯЩИЙ", down, Modifier.weight(1f))
                StatColumn("ИСХОДЯЩИЙ", up, Modifier.weight(1f))
            }
            if (phase.isNotEmpty()) {
                Spacer(Modifier.height(6.dp))
                Text(phase, color = ZentrixColors.Muted, fontSize = 12.sp)
            }
            Spacer(Modifier.height(10.dp))
            PrimaryButton(
                text = if (testing) "Идёт тест…" else "Запустить тест",
                onClick = ::runTest,
                enabled = !testing,
                modifier = Modifier.fillMaxWidth(),
            )
            Spacer(Modifier.height(6.dp))
            Text(
                "Через прокси ПК скачивается и отправляется тестовый трафик (Cloudflare).",
                color = ZentrixColors.Muted, fontSize = 11.5.sp,
            )
        }

        GlassCard {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text("Журнал", color = ZentrixColors.Text, fontSize = 15.sp, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.weight(1f))
                GhostButton(
                    text = "Копировать всё",
                    onClick = {
                        val text = logLines.joinToString("\n")
                        val clipboard = context.getSystemService(android.content.Context.CLIPBOARD_SERVICE) as android.content.ClipboardManager
                        clipboard.setPrimaryClip(android.content.ClipData.newPlainText("Sharing Connect log", text))
                        Toast.makeText(context, "Журнал скопирован", Toast.LENGTH_SHORT).show()
                    },
                )
            }
            Spacer(Modifier.height(8.dp))
            if (logLines.isEmpty()) {
                Text("Журнал пуст", color = ZentrixColors.Muted, fontSize = 12.5.sp)
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    logLines.reversed().forEach { line ->
                        Text(line, color = ZentrixColors.Muted, fontSize = 11.5.sp, lineHeight = 15.sp)
                    }
                }
            }
        }
    }
}

@Composable
private fun StatColumn(caption: String, value: Double?, modifier: Modifier = Modifier) {
    Column(modifier) {
        Text(caption, color = ZentrixColors.Muted, fontSize = 10.5.sp, fontWeight = FontWeight.Bold, letterSpacing = 0.5.sp)
        Text(
            value?.let { "$it Мбит/с" } ?: "—",
            color = ZentrixColors.Text,
            fontSize = 19.sp,
            fontWeight = FontWeight.ExtraBold,
        )
    }
}

/** Экран «Настройки» — все функции бесплатны, PRO-замков нет. */
@Composable
fun SettingsScreen(settings: SettingsStore, onOpenApps: (kind: String) -> Unit, onUpdateCheck: ((ReleaseInfo?) -> Unit) -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        PageHeading("Настройки", "Все функции бесплатны и разблокированы")
        SectionHeader("Внешний вид")
        GlassCard {
            var theme by remember { mutableStateOf(settings.theme) }
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                listOf("system" to "Как в системе", "dark" to "Тёмная", "light" to "Светлая").forEach { (key, label) ->
                    OutlinedButton(
                        onClick = { settings.theme = key; theme = key },
                        colors = ButtonDefaults.outlinedButtonColors(
                            contentColor = if (theme == key) ZentrixColors.Accent else ZentrixColors.Muted,
                        ),
                    ) { Text(label) }
                }
            }
            Spacer(Modifier.height(6.dp))
            var notifications by remember { mutableStateOf(settings.notifications) }
            ToggleRow("Уведомления", "Уведомление при активном прокси-соединении", notifications) {
                settings.notifications = it; notifications = it
            }
        }

        SectionHeader("Прокси")
        GlassCard {
            var test by remember { mutableStateOf(settings.testConnection) }
            ToggleRow("Проверка соединения", "Проверьте учетные данные тестовым соединением", test) {
                settings.testConnection = it; test = it
            }
            var stopOnLoss by remember { mutableStateOf(settings.stopOnWifiLoss) }
            ToggleRow("Останавливать автоматически", "Останавливать службу при потере беспроводного соединения", stopOnLoss) {
                settings.stopOnWifiLoss = it; stopOnLoss = it
            }
        }

        SectionHeader("Split tunneling")
        GlassCard {
            Text("Выберите приложения для использования VPN", color = ZentrixColors.Muted, fontSize = 12.5.sp)
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                GhostButton("Разрешённые", onClick = { onOpenApps("allowed") }, modifier = Modifier.weight(1f))
                GhostButton("Запрещённые", onClick = { onOpenApps("disallowed") }, modifier = Modifier.weight(1f))
            }
        }

        SectionHeader("Брандмауэр")
        GlassCard {
            var firewall by remember { mutableStateOf(settings.firewallEnabled) }
            ToggleRow("Включить брандмауэр", "Запретите определённым приложениям доступ в интернет", firewall) {
                settings.firewallEnabled = it; firewall = it
            }
            GhostButton("Правила брандмауэра", onClick = { onOpenApps("firewall") }, modifier = Modifier.fillMaxWidth())
        }

        SectionHeader("Дополнительные настройки")
        GlassCard {
            var routePrivate by remember { mutableStateOf(settings.routePrivateNetwork) }
            ToggleRow(
                "Маршрутизация частной сети",
                "Маршрутизация трафика из диапазонов частных IP-адресов через прокси",
                routePrivate,
            ) {
                settings.routePrivateNetwork = it; routePrivate = it
            }
        }

        GlassCard {
            Text("Версия", color = ZentrixColors.Text, fontSize = 15.sp, fontWeight = FontWeight.Medium)
            Spacer(Modifier.height(8.dp))
            var checking by remember { mutableStateOf(false) }
            var hasUpdate by remember { mutableStateOf(false) }
            var apkUrl by remember { mutableStateOf<String?>(null) }
            var apkVersion by remember { mutableStateOf<String?>(null) }
            val context = androidx.compose.ui.platform.LocalContext.current
            GhostButton(
                text = if (checking) "Проверяю…" else "Проверить актуальную версию",
                onClick = {
                    if (!checking) {
                        checking = true
                        onUpdateCheck { release ->
                            checking = false
                            apkUrl = release?.apkUrl
                            apkVersion = release?.version
                            hasUpdate = release != null &&
                                ReleaseChecker.isNewer(BuildConfig.VERSION_NAME, release.version)
                            if (release == null) {
                                Toast.makeText(context, "Не удалось связаться с GitHub", Toast.LENGTH_SHORT).show()
                            }
                        }
                    }
                },
                modifier = Modifier.fillMaxWidth(),
            )
            apkVersion?.let { version ->
                Spacer(Modifier.height(6.dp))
                Text(
                    if (hasUpdate) "Доступна новая версия APK: $version"
                    else "У вас актуальная версия ($version)",
                    color = if (hasUpdate) ZentrixColors.Success else ZentrixColors.Muted,
                    fontSize = 12.5.sp,
                )
            }
            Spacer(Modifier.height(6.dp))
            // Кнопка активна только когда найдена версия новее установленной.
            PrimaryButton(
                text = if (hasUpdate) "Загрузить актуальную версию APK" else "Загрузить актуальную версию APK (нет обновлений)",
                onClick = {
                    val url = apkUrl ?: return@PrimaryButton
                    runCatching {
                        context.startActivity(
                            android.content.Intent(
                                android.content.Intent.ACTION_VIEW,
                                android.net.Uri.parse(url),
                            )
                        )
                    }.onFailure {
                        Toast.makeText(context, "Откройте ссылку в браузере: $url", Toast.LENGTH_LONG).show()
                    }
                },
                enabled = hasUpdate,
                modifier = Modifier.fillMaxWidth(),
            )
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
fun SectionHeader(text: String) {
    Text(text, color = ZentrixColors.Accent2, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
}

/** Заголовок страницы в стиле page_heading ПК-версии: титул + подпись. */
@Composable
fun PageHeading(title: String, subtitle: String) {
    Column(Modifier.padding(top = 18.dp, bottom = 6.dp)) {
        Text(title, color = ZentrixColors.Text, fontSize = 22.sp, fontWeight = FontWeight.Bold)
        if (subtitle.isNotBlank()) {
            Spacer(Modifier.height(3.dp))
            Text(subtitle, color = ZentrixColors.Muted, fontSize = 12.5.sp)
        }
    }
}

/** Цветной бейдж состояния, как Badge ПК-версии. */
@Composable
fun StatusBadge(text: String, color: Color) {
    Box(
        Modifier
            .background(color.copy(alpha = 0.14f), RoundedCornerShape(8.dp))
            .border(1.dp, color.copy(alpha = 0.35f), RoundedCornerShape(8.dp))
            .padding(horizontal = 10.dp, vertical = 4.dp),
    ) {
        Text(text, color = color, fontSize = 10.5.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
    }
}

private fun statusInfo(status: TunnelStatus, proxyValid: Boolean): Triple<String, Color, String> {
    return when {
        !proxyValid -> Triple("НЕ НАСТРОЕН", ZentrixColors.Warning, "Профиль не заполнен")
        status == TunnelStatus.RUNNING -> Triple("РАБОТАЕТ", ZentrixColors.Success, "Трафик идёт через прокси ПК")
        status == TunnelStatus.STARTING -> Triple("ЗАПУСК…", ZentrixColors.Warning, "Поднимаю туннель")
        status == TunnelStatus.STOPPING -> Triple("ОСТАНОВКА…", ZentrixColors.Warning, "Гашу туннель")
        else -> Triple("ВЫКЛЮЧЕН", ZentrixColors.Muted, "Zapret и VPN — под одним стеклом")
    }
}

/**
 * Экран «Главная» — дашборд в стиле HomePage ПК-версии: hero-карточка
 * с орбом статуса и быстрыми кнопками, сводка профиля, журнал.
 */
@Composable
fun HomeScreen(
    settings: SettingsStore,
    profileVersion: Int,
    onStart: () -> Unit,
    onStop: () -> Unit,
    onGoProxy: () -> Unit,
) {
    val status by VpnState.status.collectAsState()
    val logLines by LogRepo.live.collectAsState()
    val proxy = remember(profileVersion) { settings.proxy }
    val (badge, badgeColor, subtitle) = statusInfo(status, proxy.isValid)
    val connected = status == TunnelStatus.RUNNING
    val busy = status == TunnelStatus.STARTING || status == TunnelStatus.STOPPING

    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp),
    ) {
        PageHeading("Главная", "Обход блокировок — под контролем")

        // --- hero ---
        GlassCard(Modifier.fillMaxWidth()) {
            Row(horizontalArrangement = Arrangement.spacedBy(14.dp)) {
                Column(Modifier.weight(1f)) {
                    StatusBadge(badge, badgeColor)
                    Spacer(Modifier.height(10.dp))
                    Text(
                        if (connected) "Подключение\nпод контролем" else "Подключение\nвыключено",
                        color = ZentrixColors.Text,
                        fontSize = 19.sp,
                        fontWeight = FontWeight.Bold,
                        lineHeight = 24.sp,
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(subtitle, color = ZentrixColors.Muted, fontSize = 12.5.sp)
                    Spacer(Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        PrimaryButton(
                            text = if (connected) "Выключить" else "Включить",
                            onClick = if (connected) onStop else onStart,
                            enabled = proxy.isValid && (connected || !busy),
                            modifier = Modifier.weight(1f),
                        )
                        GhostButton(text = "Прокси", onClick = onGoProxy, modifier = Modifier.weight(1f))
                    }
                }
                // мини-орб статуса
                Box(Modifier.size(96.dp), contentAlignment = Alignment.Center) {
                    Box(
                        Modifier
                            .size(96.dp)
                            .clip(CircleShape)
                            .background(
                                Brush.radialGradient(
                                    listOf(
                                        (if (connected) ZentrixColors.Accent else ZentrixColors.Muted)
                                            .copy(alpha = if (connected) 0.45f else 0.15f),
                                        Color.Transparent,
                                    ),
                                ),
                            ),
                    )
                    Box(
                        Modifier
                            .size(64.dp)
                            .clip(CircleShape)
                            .border(1.dp, (if (connected) ZentrixColors.Accent2 else ZentrixColors.Muted).copy(alpha = 0.5f), CircleShape)
                            .background(Color.Transparent),
                        contentAlignment = Alignment.Center,
                    ) {
                        Icon(
                            imageVector = if (connected) Icons.Filled.Check else Icons.Filled.Shield,
                            contentDescription = null,
                            tint = if (connected) ZentrixColors.Accent2 else ZentrixColors.Muted,
                            modifier = Modifier.size(28.dp),
                        )
                    }
                }
            }
        }
        Spacer(Modifier.height(12.dp))

        // --- движок (сводка ядра) ---
        GlassCard(title = "Ядро туннеля") {
            EngineRow("Hiddify Core (sing-box)", if (connected) "активно" else "ожидает", connected)
            Spacer(Modifier.height(8.dp))
            EngineRow("SOCKS5 → ПК", proxy.uri, proxy.isValid)
        }
        Spacer(Modifier.height(12.dp))

        // --- профиль ---
        GlassCard(title = "Профиль") {
            if (proxy.isValid) {
                Text(proxy.uri, color = ZentrixColors.Text, fontSize = 14.sp, fontWeight = FontWeight.Medium)
            } else {
                Text("Профиль не настроен — отсканируйте QR из «Шеринга»", color = ZentrixColors.Muted, fontSize = 13.sp)
            }
            Spacer(Modifier.height(8.dp))
            GhostButton(text = "Настроить во вкладке «Прокси»", onClick = onGoProxy, modifier = Modifier.fillMaxWidth())
        }
        Spacer(Modifier.height(12.dp))

        // --- журнал ---
        GlassCard(title = "Журнал") {
            if (logLines.isEmpty()) {
                Text("Журнал пуст", color = ZentrixColors.Muted, fontSize = 12.5.sp)
            } else {
                Column(verticalArrangement = Arrangement.spacedBy(3.dp)) {
                    logLines.reversed().take(6).forEach { line ->
                        Text(line, color = ZentrixColors.Muted, fontSize = 11.5.sp, lineHeight = 15.sp)
                    }
                }
            }
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
private fun EngineRow(title: String, value: String, ok: Boolean) {
    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(if (ok) ZentrixColors.Success else ZentrixColors.Muted.copy(alpha = 0.5f)),
        )
        Spacer(Modifier.width(8.dp))
        Text(title, color = ZentrixColors.Text, fontSize = 13.sp, modifier = Modifier.weight(1f))
        Text(value, color = ZentrixColors.Muted, fontSize = 11.5.sp)
    }
}
