package com.indiebiz.phoneagent

import android.content.Context
import java.io.File

/**
 * M3 하드웨어 다리: 폰 하드웨어 신호(알림 등)를 폰의 파이썬 뇌가 읽도록 app-private 로컬 저장.
 * BaseBundle 이 지우는 indiebiz_base 의 sibling(filesDir/signals)에 두어 영속.
 * phone_notifications.py(폰 프로파일)가 이 JSONL 을 읽어 [sense:phone] 에 공급한다.
 * Nostr 푸시(데스크탑)와 병행 — 폰 자급 경로를 추가하는 것.
 */
object LocalSignals {
    private const val MAX_LINES = 500

    fun appendNotification(ctx: Context, jsonLine: String) {
        try {
            val dir = File(ctx.filesDir, "signals").apply { mkdirs() }
            val f = File(dir, "notifications.jsonl")
            val lines = if (f.exists()) f.readLines().toMutableList() else mutableListOf()
            lines.add(jsonLine)
            val trimmed = if (lines.size > MAX_LINES)
                lines.subList(lines.size - MAX_LINES, lines.size) else lines
            f.writeText(trimmed.joinToString("\n") + "\n")
        } catch (_: Throwable) {
            // 신호 유실은 치명 아님 — 조용히 넘어간다.
        }
    }
}
