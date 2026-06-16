package com.indiebiz.phoneagent

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * 상주용 포그라운드 서비스. 프로세스를 살려두어 알림 캡처·발신이 죽지 않게 한다.
 * (NotificationListenerService 자체는 시스템 바인드지만, 삼성의 백그라운드 학살에 대비.)
 */
class AgentForegroundService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        startForeground(NOTIF_ID, buildNotification())
        Log.i(TAG, "포그라운드 서비스 시작 — 상주")
        // 앱 UI 없이도 :8765 백엔드 기동 — 부팅·START_STICKY 재시작 시에도 맥→폰 분산
        // 포워드가 닿게. (App.ensureBackend 는 idempotent: 이미 떠 있으면 즉시 반환.)
        (application as? App)?.ensureBackend()
        // 위치·걸음 상시 수집기(SignalCollector)는 제거됨(2026-06-12 — 상시 추적/푸시 폐기).
        // 위치는 이제 [sense:here] 온디맨드 1회 조회(PhoneActions.getCurrentLocationNow)로만.
        return START_STICKY
    }

    private fun buildNotification(): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        val ch = NotificationChannel(CH_ID, "IndieBiz Agent", NotificationManager.IMPORTANCE_MIN)
        ch.setShowBadge(false)
        nm.createNotificationChannel(ch)
        return Notification.Builder(this, CH_ID)
            .setContentTitle("IndieBiz Phone Agent")
            .setContentText("알림을 indiebizOS로 중계 중")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setOngoing(true)
            .build()
    }

    companion object {
        private const val TAG = "IndieBizAgent"
        const val CH_ID = "agent_fg"
        const val NOTIF_ID = 1001

        fun start(ctx: Context) {
            ContextCompat.startForegroundService(
                ctx, Intent(ctx, AgentForegroundService::class.java))
        }
    }
}
