package com.sharingconnect.vpn

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.text.SimpleDateFormat
import java.util.ArrayDeque
import java.util.Date
import java.util.Locale

/** Простой журнал соединений для вкладки «Журнал». */
object LogRepo {

    private const val MAX_LINES = 500
    private val lines = ArrayDeque<String>(MAX_LINES)
    private val format = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
    private val flow = MutableStateFlow<List<String>>(emptyList())

    /** Подписка UI: список строк журнала (от старых к новым). */
    val live: StateFlow<List<String>> = flow.asStateFlow()

    fun log(message: String) {
        synchronized(lines) {
            lines.addLast("[${format.format(Date())}] $message")
            while (lines.size > MAX_LINES) lines.removeFirst()
        }
        flow.value = snapshot()
    }

    fun snapshot(): List<String> = synchronized(lines) { lines.toList() }

    fun clear() = synchronized(lines) { lines.clear() }.also { flow.value = emptyList() }
}
