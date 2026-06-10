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
        val text = extras.getCharSequence("android.text")?.toString() ?: ""
        if (title.isEmpty() && text.isEmpty()) return

        Log.i(TAG, "NOTIF pkg=$pkg | title=$title | text=$text")

        val payload = JSONObject()
            .put("type", "notification")
            .put("pkg", pkg)
            .put("title", title)
            .put("text", text)
            .put("posted_at", sbn.postTime / 1000)
            .toString()

        Sender.sendAsync(applicationContext, payload)
    }

    companion object {
        private const val TAG = "IndieBizAgent"
    }
}
