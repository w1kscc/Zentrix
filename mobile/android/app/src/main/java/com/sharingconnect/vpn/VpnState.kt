package com.sharingconnect.vpn

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Статус туннеля — единый источник правды для UI. */
enum class TunnelStatus { STOPPED, STARTING, RUNNING, STOPPING }

/** Глобальное состояние туннеля. Меняется только службой. */
object VpnState {
    private val flow = MutableStateFlow(TunnelStatus.STOPPED)

    val status: StateFlow<TunnelStatus> = flow.asStateFlow()

    fun set(value: TunnelStatus) {
        flow.value = value
    }
}
