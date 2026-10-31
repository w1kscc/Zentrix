package com.sharingconnect.ui

import android.app.Activity
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Button
import android.widget.CheckBox
import android.widget.LinearLayout
import android.widget.ScrollView
import com.sharingconnect.data.SettingsStore

/**
 * Выбор приложений: split tunneling (разрешённые/запрещённые) и правила
 * брандмауэра. Все функции бесплатны.
 */
class AppPickerActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val kind = intent.getStringExtra("kind") ?: "allowed"
        val settings = SettingsStore(this)
        val pm = packageManager
        val installed = pm.getInstalledApplications(PackageManager.GET_META_DATA)
            .filter { pm.getLaunchIntentForPackage(it.packageName) != null }
            .sortedBy { it.loadLabel(pm).toString().lowercase() }

        val selected = when (kind) {
            "allowed" -> settings.allowedApps().toMutableSet()
            "disallowed" -> settings.disallowedApps().toMutableSet()
            else -> settings.firewallRules().filter { it.second }.map { it.first }.toMutableSet()
        }

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 48, 48, 48)
        }
        layout.addView(android.widget.TextView(this).apply {
            text = when (kind) {
                "allowed" -> "Разрешённые приложения (пусто = все)"
                "disallowed" -> "Запрещённые приложения"
                else -> "Брандмауэр: блокировать доступ в интернет"
            }
            textSize = 18f
            setPadding(0, 0, 0, 32)
        })

        val boxes = mutableListOf<Pair<String, CheckBox>>()
        val scroll = ScrollView(this)
        val listLayout = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL }
        installed.forEach { app: ApplicationInfo ->
            val label = app.loadLabel(pm).toString()
            val box = CheckBox(this).apply {
                text = "$label (${app.packageName})"
                isChecked = app.packageName in selected
                setOnCheckedChangeListener { _, checked ->
                    if (checked) selected.add(app.packageName) else selected.remove(app.packageName)
                }
            }
            boxes.add(app.packageName to box)
            listLayout.addView(box)
        }
        scroll.addView(listLayout)
        layout.addView(scroll)

        layout.addView(Button(this).apply {
            text = "Сохранить"
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
        })
        setContentView(layout)
    }
}
