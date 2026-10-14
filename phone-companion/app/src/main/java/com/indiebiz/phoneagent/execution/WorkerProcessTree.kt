package com.indiebiz.phoneagent.execution

import android.os.Process
import android.os.SystemClock
import java.io.File

/** Best-effort observed descendants, checked against process start ticks to avoid PID reuse. */
object WorkerProcessTree {
    fun info(pid: Int): Pair<Int, String>? = try {
        val values = File("/proc/$pid/stat").readText().substringAfterLast(") ").split(' ')
        Pair(values[1].toInt(), values[19])
    } catch (_: Throwable) { null }

    fun terminate(pid: Int, birth: String?, allowSelf: Boolean = false): Boolean {
        if (pid <= 0 || (pid == Process.myPid() && !allowSelf) || birth == null) return false
        if (info(pid)?.second != birth) return true
        if (pid != Process.myPid()) Process.sendSignal(pid, 19)
        val owned = mutableMapOf(pid to birth!!)
        // Freeze newly observed children before another snapshot so ordinary child forks stop.
        repeat(8) {
            val before = owned.size
            File("/proc").listFiles()?.forEach { file ->
                val pid = file.name.toIntOrNull() ?: return@forEach
                val info = info(pid) ?: return@forEach
                if (info.first in owned && pid !in owned) {
                    owned[pid] = info.second
                    if (pid != Process.myPid()) Process.sendSignal(pid, 19)
                }
            }
            if (owned.size == before) return@repeat
        }
        owned.entries.sortedBy { if (it.key == pid) 1 else 0 }.forEach { (pid, birth) ->
            if (info(pid)?.second == birth) Process.killProcess(pid)
        }
        val deadline = SystemClock.elapsedRealtime() + 3000
        while (owned.any { info(it.key)?.second == it.value } && SystemClock.elapsedRealtime() < deadline) Thread.sleep(20)
        return owned.none { info(it.key)?.second == it.value }
    }
}
