package com.indiebiz.phoneagent

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import org.json.JSONObject

/**
 * 알림을 가로채 NIP-17 DM 으로 indiebizOS 에 push.
 * 검증: `adb logcat -s IndieBizAgent` + 백엔드 fetch_dms_nip17.
 */
class NotificationCaptureService : NotificationListenerService() {

    override fun onListenerConnected() {
        Log.i(TAG, "NotificationListener 연결됨 — 알림 캡처 시작")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification) {
        val pkg = sbn.packageName
        // 자기 자신/시스템 소음 제외
        if (pkg == packageName || pkg == "com.android.systemui") return

        val extras = sbn.notification.extras
        val title = extras.getString("android.title") ?: ""
        // bigText(펼친 전체 본문) 우선 — android.text 만 읽으면 긴 알림이 절단된다
        // ("지금 어디야?"→"지금"). 인박스 스타일은 textLines 합본으로 폴백.
        val text = (extras.getCharSequence("android.bigText")
            ?: extras.getCharSequence("android.text")
            ?: (extras.getCharSequenceArray("android.textLines")
                ?.joinToString("\n") { it.toString() }))?.toString()?.trim() ?: ""
        if (title.isEmpty() && text.isEmpty()) return

        Log.i(TAG, "NOTIF pkg=$pkg | title=$title | text=$text")

        val payload = JSONObject()
            .put("type", "notification")
            .put("pkg", pkg)
            .put("title", title)
            .put("text", text)
            .put("posted_at", sbn.postTime / 1000)
            .toString()

        // 폰 로컬 뇌가 [sense:phone] 으로 읽도록 app-private JSONL 에 기록 (로컬 전용).
        LocalSignals.appendNotification(applicationContext, payload)
        // (2026-06-15) 데스크탑 Nostr DM 푸시 제거.
        // 기존엔 모든 알림(시스템 "USB 충전 중" 등 잡음 포함)을 무차별 NIP-17 DM 으로 발행해
        // 사용자에게 DM 폭주를 일으켰고 릴레이 rate-limit 까지 유발했다. 폰 로컬 뇌가
        // LocalSignals 를 [sense:phone] 으로 직접 읽으므로 네트워크 푸시는 불필요 — 로컬에만 적재한다.
    }

    companion object {
        private const val TAG = "IndieBizAgent"
    }
}
