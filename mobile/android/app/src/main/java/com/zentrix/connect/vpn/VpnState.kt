package com.zentrix.connect.vpn

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

enum class TunnelStatus { STOPPED, STARTING, RUNNING, STOPPING }

/** Глобальное состояние туннеля + кольцевой журнал для UI. */
object VpnState {
    private val _status = MutableStateFlow(TunnelStatus.STOPPED)
    val status: StateFlow<TunnelStatus> = _status

    private val _log = MutableStateFlow<List<String>>(emptyList())
    val log: StateFlow<List<String>> = _log

    fun set(status: TunnelStatus) { _status.value = status }

    fun log(message: String) {
        val stamp = java.text.SimpleDateFormat("HH:mm:ss", java.util.Locale.US)
            .format(java.util.Date())
        _log.value = (_log.value + "[$stamp] $message").takeLast(200)
    }
}
