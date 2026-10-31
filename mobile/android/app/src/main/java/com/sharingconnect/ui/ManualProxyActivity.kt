package com.sharingconnect.ui

import android.app.Activity
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.Toast
import com.sharingconnect.data.ProxyConfig
import com.sharingconnect.data.SettingsStore

/** Ручной ввод адреса прокси (если QR недоступен): socks5://host:port или host + порт. */
class ManualProxyActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val settings = SettingsStore(this)

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(48, 48, 48, 48)
        }
        val protocol = EditText(this).apply { hint = "Протокол: socks5 или http"; setText(settings.proxy.protocol) }
        val host = EditText(this).apply { hint = "IP компьютера (из «Шеринга»)"; setText(settings.proxy.host) }
        val port = EditText(this).apply {
            hint = "Порт"
            if (settings.proxy.port > 0) setText(settings.proxy.port.toString())
        }
        layout.addView(protocol)
        layout.addView(host)
        layout.addView(port)
        layout.addView(Button(this).apply {
            text = "Сохранить"
            setOnClickListener {
                val config = ProxyConfig(
                    protocol = protocol.text.toString().trim().ifBlank { "socks5" },
                    host = host.text.toString().trim(),
                    port = port.text.toString().trim().toIntOrNull() ?: 0,
                )
                if (config.isValid) {
                    settings.proxy = config
                    Toast.makeText(this@ManualProxyActivity, "Сохранено: ${config.uri}", Toast.LENGTH_SHORT).show()
                    finish()
                } else {
                    Toast.makeText(this@ManualProxyActivity, "Некорректный адрес", Toast.LENGTH_SHORT).show()
                }
            }
        })
        setContentView(layout)
    }
}
