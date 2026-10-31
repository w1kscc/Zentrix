package com.sharingconnect.ui

import android.app.Activity
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Bundle
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import com.sharingconnect.data.SettingsStore
import kotlin.concurrent.thread

/**
 * Выбор приложений: split tunneling (разрешённые/запрещённые) и правила
 * брандмауэра. Список установленных (не системных) приложений ищется
 * по нажатию кнопки «Найти приложения».
 */
class AppPickerActivity : Activity() {

    private lateinit var settings: SettingsStore
    private lateinit var kind: String
    private val selected = mutableSetOf<String>()

    private lateinit var findButton: Button
    private lateinit var progress: ProgressBar
    private lateinit var statusLabel: TextView
    private lateinit var scroll: ScrollView
    private lateinit var listLayout: LinearLayout
    private lateinit var saveButton: Button

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        kind = intent.getStringExtra("kind") ?: "allowed"
        settings = SettingsStore(this)
        selected.clear()
        when (kind) {
            "allowed" -> selected.addAll(settings.allowedApps())
            "disallowed" -> selected.addAll(settings.disallowedApps())
            else -> selected.addAll(settings.firewallRules().filter { it.second }.map { it.first })
        }

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 48, 48, 32)
        }
        layout.addView(TextView(this).apply {
            text = when (kind) {
                "allowed" -> "Разрешённые приложения (пусто = все)"
                "disallowed" -> "Запрещённые приложения"
                else -> "Брандмауэр: блокировать доступ в интернет"
            }
            textSize = 18f
            setPadding(0, 0, 0, 16)
        })
        findButton = Button(this).apply {
            text = "Найти приложения"
            setOnClickListener { startSearch() }
        }
        progress = ProgressBar(this).apply { visibility = View.GONE }
        statusLabel = TextView(this).apply { text = "Нажмите «Найти приложения» для сканирования" }
        scroll = ScrollView(this).apply { visibility = View.GONE }
        listLayout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        scroll.addView(listLayout)
        saveButton = Button(this).apply {
            text = "Сохранить"
            isEnabled = false
            setOnClickListener {
                when (kind) {
                    "allowed" -> settings.setAllowedApps(selected)
                    "disallowed" -> settings.setDisallowedApps(selected)
                    else -> {
                        val others = settings.firewallRules().filterNot { it.second }
                        settings.setFirewallRules(others + selected.map { it to true })
                    }
                }
                setResult(RESULT_OK)
                finish()
            }
        }
        layout.addView(findButton)
        layout.addView(progress)
        layout.addView(statusLabel)
        layout.addView(scroll)
        layout.addView(saveButton)
        setContentView(layout)
    }

    private fun startSearch() {
        findButton.isEnabled = false
        progress.visibility = View.VISIBLE
        statusLabel.text = "Ищу установленные приложения…"
        scroll.visibility = View.GONE
        listLayout.removeAllViews()
        saveButton.isEnabled = false

        val pm = packageManager
        thread {
            val apps: List<Pair<String, String>> = runCatching {
                pm.getInstalledApplications(PackageManager.GET_META_DATA)
                    .asSequence()
                    .filter { it.flags and ApplicationInfo.FLAG_SYSTEM == 0 }  // без системных
                    .filter { pm.getLaunchIntentForPackage(it.packageName) != null }
                    .map { it.loadLabel(pm).toString() to it.packageName }
                    .sortedBy { it.first.lowercase() }
                    .toList()
            }.getOrDefault(emptyList())
            runOnUiThread {
                progress.visibility = View.GONE
                findButton.isEnabled = true
                if (apps.isEmpty()) {
                    statusLabel.text = "Установленные приложения не найдены"
                    return@runOnUiThread
                }
                statusLabel.text = "Найдено приложений: ${apps.size}"
                scroll.visibility = View.VISIBLE
                saveButton.isEnabled = true
                apps.forEach { (label, pkg) ->
                    listLayout.addView(CheckBox(this).apply {
                        text = "$label\n$pkg"
                        isChecked = pkg in selected
                        setOnCheckedChangeListener { _, checked ->
                            if (checked) selected.add(pkg) else selected.remove(pkg)
                        }
                    })
                }
            }
        }
    }
}
