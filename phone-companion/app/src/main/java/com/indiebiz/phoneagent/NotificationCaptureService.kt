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

        // M3: 폰 로컬 뇌가 [sense:phone] 으로 읽도록 app-private JSONL 에도 기록.
        LocalSignals.appendNotification(applicationContext, payload)
        // 데스크탑 푸시(기존 경로) — 병행 유지.
        Sender.sendAsync(applicationContext, payload)
    }

    companion object {
        private const val TAG = "IndieBizAgent"
    }
}
