package com.sharingconnect.ui

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
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.sharingconnect.data.SettingsStore
import com.sharingconnect.vpn.LogRepo

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
fun PrimaryButton(text: String, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Button(
        onClick = onClick,
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

/** Экран «Прокси»: статус, адрес из QR, подключение. */
@Composable
fun ProxyScreen(settings: SettingsStore, connected: Boolean, onToggle: () -> Unit, onScanQr: () -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        GlassCard(title = "Локальный шеринг") {
            val proxy = settings.proxy
            Text(
                if (proxy.isValid) proxy.uri else "Отсканируйте QR-код из вкладки «Шеринг» PC-версии",
                color = if (proxy.isValid) ZentrixColors.Text else ZentrixColors.Muted,
                fontSize = 15.sp,
            )
            Spacer(Modifier.height(12.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                PrimaryButton(
                    text = if (connected) "Отключить" else "Подключить",
                    onClick = onToggle,
                    modifier = Modifier.weight(1f),
                )
                GhostButton(text = "Сканировать QR", onClick = onScanQr, modifier = Modifier.weight(1f))
            }
        }
        GlassCard(title = "Как это работает") {
            Text(
                "1. Во вкладке «Шеринг» PC-версии Zentrix включите раздачу.\n" +
                    "2. Отсканируйте QR-код этим приложением.\n" +
                    "3. Нажмите «Подключить» — трафик выбранных приложений пойдёт через ПК.",
                color = ZentrixColors.Muted,
                fontSize = 13.sp,
                lineHeight = 18.sp,
            )
        }
    }
}

/** Экран «Журнал». */
@Composable
fun LogScreen() {
    val lines by remember { LogRepo.live }
    Column(Modifier.fillMaxSize().padding(16.dp)) {
        Text("Журнал", color = ZentrixColors.Text, fontSize = 20.sp, fontWeight = FontWeight.Bold)
        Spacer(Modifier.height(10.dp))
        GlassCard(Modifier.fillMaxWidth()) {
            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                if (lines.isEmpty()) {
                    Text("Журнал пуст", color = ZentrixColors.Muted, fontSize = 13.sp)
                }
                lines.reversed().forEach { line ->
                    Text(line, color = ZentrixColors.Muted, fontSize = 12.sp, lineHeight = 16.sp)
                }
            }
        }
    }
}

/** Экран «Настройки» — все функции бесплатны, PRO-замков нет. */
@Composable
fun SettingsScreen(settings: SettingsStore, onOpenApps: (kind: String) -> Unit, onUpdateCheck: () -> Unit) {
    Column(
        Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
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
            GhostButton("Проверить актуальную версию", onClick = onUpdateCheck, modifier = Modifier.fillMaxWidth())
        }
        Spacer(Modifier.height(24.dp))
    }
}

@Composable
fun SectionHeader(text: String) {
    Text(text, color = ZentrixColors.Accent2, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
}
