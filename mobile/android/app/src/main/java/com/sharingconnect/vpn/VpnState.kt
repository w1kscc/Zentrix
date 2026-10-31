package com.sharingconnect.vpn

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Глобальное состояние туннеля — единственный источник правды для UI. */
object VpnState {
    private val flow = MutableStateFlow(false)

    /** true = туннель запущен. UI читает только отсюда, без нативных вызовов. */
    val connected: StateFlow<Boolean> = flow.asStateFlow()

    fun set(value: Boolean) {
        flow.value = value
    }
}
