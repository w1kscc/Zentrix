package com.sharingconnect.ui

import android.app.Activity
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.os.Bundle
import android.text.Editable
import android.text.TextWatcher
import android.view.View
import android.widget.Button
import android.widget.CheckBox
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.ProgressBar
import android.widget.ScrollView
import android.widget.TextView
import com.sharingconnect.data.SettingsStore
import kotlin.concurrent.thread

/**
 * Выбор приложений: split tunneling (разрешённые/запрещённые) и правила
 * брандмауэра. Сканируются ВСЕ установленные приложения — сразу при открытии,
 * с постоянным поиском по названию и имени пакета.
 */
class AppPickerActivity : Activity() {

    private lateinit var settings: SettingsStore
    private lateinit var kind: String
    private val selected = mutableSetOf<String>()

    private var apps: List<Pair<String, String>> = emptyList()
    private var query: String = ""

    private lateinit var progress: ProgressBar
    private lateinit var statusLabel: TextView
    private lateinit var searchField: EditText
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
        progress = ProgressBar(this).apply { visibility = View.GONE }
        statusLabel = TextView(this).apply { text = "Ищу установленные приложения…" }
        searchField = EditText(this).apply {
            hint = "Поиск: название или пакет…"
            setSingleLine(true)
            addTextChangedListener(object : TextWatcher {
                override fun beforeTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun onTextChanged(s: CharSequence?, a: Int, b: Int, c: Int) {}
                override fun afterTextChanged(s: Editable?) {
                    query = s?.toString()?.trim()?.lowercase() ?: ""
                    renderApps()
                }
            })
        }
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
        layout.addView(progress)
        layout.addView(statusLabel)
        layout.addView(searchField)
        layout.addView(scroll, LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT, 0, 1f))
        layout.addView(saveButton)
        setContentView(layout)
        startSearch()
    }


    /** Отрисовать список с учётом поискового запроса. */
    private fun renderApps() {
        listLayout.removeAllViews()
        val filtered = if (query.isEmpty()) apps else apps.filter { (label, pkg) ->
            label.lowercase().contains(query) || pkg.lowercase().contains(query)
        }
        if (filtered.isEmpty()) {
            listLayout.addView(TextView(this).apply {
                text = "Ничего не найдено"
                setPadding(0, 24, 0, 24)
            })
            return
        }
        filtered.forEach { (label, pkg) ->
            listLayout.addView(CheckBox(this).apply {
                text = "$label\n$pkg"
                isChecked = pkg in selected
                setOnCheckedChangeListener { _, checked ->
                    if (checked) selected.add(pkg) else selected.remove(pkg)
                }
            })
        }
    }

    private fun startSearch() {
        progress.visibility = View.VISIBLE
        statusLabel.text = "Ищу установленные приложения…"
        scroll.visibility = View.GONE
        listLayout.removeAllViews()
        saveButton.isEnabled = false

        val pm = packageManager
        thread {
            apps = runCatching {
                pm.getInstalledApplications(PackageManager.GET_META_DATA)
                    .asSequence()
                    .map {
                        val label = it.loadLabel(pm).toString()
                        val mark = if (it.flags and ApplicationInfo.FLAG_SYSTEM != 0)
                            " · системное" else ""
                        "$label$mark" to it.packageName
                    }
                    .sortedBy { it.first.lowercase() }
                    .toList()
            }.getOrDefault(emptyList())
            runOnUiThread {
                progress.visibility = View.GONE
                if (apps.isEmpty()) {
                    statusLabel.text = "Установленные приложения не найдены"
                    return@runOnUiThread
                }
                statusLabel.text = "Найдено приложений: ${apps.size}"
                scroll.visibility = View.VISIBLE
                saveButton.isEnabled = true
                renderApps()
            }
        }
    }
}
