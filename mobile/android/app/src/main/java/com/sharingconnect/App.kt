package com.sharingconnect

import android.app.Application
import com.sharingconnect.vpn.LogRepo
import java.io.File
import java.io.PrintWriter
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Ловит необработанные исключения и сохраняет полный краш-лог
 * (стектрейс + журнал приложения) в папку приложения:
 *
 *   Android/data/com.sharingconnect/files/crash/crash-<дата>.txt
 *
 * Файл можно открыть через любой файловый менеджер или «Файлы» Android.
 * После записи краш передаётся системному обработчику как обычно.
 */
class App : Application() {

    override fun onCreate() {
        super.onCreate()
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, throwable ->
            runCatching { saveCrashLog(thread, throwable) }
            previous?.uncaughtException(thread, throwable)
        }
    }

    private fun saveCrashLog(thread: Thread, throwable: Throwable) {
        val dir = File(getExternalFilesDir(null) ?: filesDir, "crash").apply { mkdirs() }
        val stamp = SimpleDateFormat("yyyyMMdd-HHmmss", Locale.getDefault()).format(Date())
        val file = File(dir, "crash-$stamp.txt")
        PrintWriter(file.bufferedWriter()).use { writer ->
            writer.println("Sharing Connect ${BuildConfig.VERSION_NAME} (code ${BuildConfig.VERSION_CODE})")
            writer.println("Время: ${SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault()).format(Date())}")
            writer.println("Поток: ${thread.name}")
            writer.println()
            writer.println("=== Стектрейс ===")
            throwable.printStackTrace(writer)
            var cause = throwable.cause
            while (cause != null) {
                writer.println()
                writer.println("=== Причина: ${cause.javaClass.name} ===")
                cause.printStackTrace(writer)
                cause = cause.cause
            }
            writer.println()
            writer.println("=== Журнал приложения ===")
            LogRepo.snapshot().forEach(writer::println)
        }
        // Оставляем только последние 10 логов, старые удаляем.
        dir.listFiles { f -> f.name.startsWith("crash-") }
            ?.sortedByDescending { it.name }
            ?.drop(10)
            ?.forEach { it.delete() }
    }
}
