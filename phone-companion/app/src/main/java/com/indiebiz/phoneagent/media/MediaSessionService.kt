package com.indiebiz.phoneagent.media

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * 미디어 세션 포그라운드 서비스 — 용도에 맞는 FGS 유형(camera | microphone | mediaPlayback)으로 뜬다.
 * AgentForegroundService(specialUse)는 상주용일 뿐, 카메라·마이크 실행 요건을 채우지 않는다(설계 §9).
 *
 * 한 번에 한 세션(그 밖은 device_busy). START_NOT_STICKY — 프로세스가 죽으면 세션은 끝난 것이다
 * (낡은 봉투로 되살리지 않는다; 허브는 임대 만료로 안다).
 * 시작 실패(while-in-use 제한·FGS 권한)는 접수 결과에 needs_local_action 으로 정직하게 돌아간다.
 */
class MediaSessionService : Service() {

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> handleStart(intent.getStringExtra(EXTRA_ENVELOPE) ?: "", intent.getStringExtra(RemoteMediaStart.EXTRA_TOKEN))
            ACTION_STOP -> {
                val sid = intent.getStringExtra(EXTRA_SESSION)
                val r = runner
                if (r != null && (sid.isNullOrEmpty() || r.sessionId == sid)) r.end(intent.getStringExtra(EXTRA_REASON) ?: "local_stop", notifyHub = true)
                else finish()
            }
            else -> finish()
        }
        return START_NOT_STICKY
    }

    private fun handleStart(json: String, remoteToken: String?) {
        val env = try { MediaEnvelope.parse(json) } catch (e: Throwable) {
            deliver(JSONObject().put("error", "invalid_envelope").put("message", e.message)); finish(); return
        }
        if (remoteToken != null && !RemoteMediaStart.ready(env.sessionId, remoteToken)) {
            deliver(JSONObject().put("error", "needs_local_action").put("message", "원격 카메라 시작 화면이 닫혔습니다"))
            finish(); return
        }
        synchronized(LOCK) {
            val cur = runner
            if (cur != null && !cur.ended) {
                deliver(JSONObject().put("error", if (cur.sessionId == env.sessionId) "accepted" else "device_busy")
                    .put("active_session", cur.sessionId))
                return
            }
        }
        try {
            ServiceCompat.startForeground(this, NOTIF_ID, buildNotification(env), fgsType(env))
        } catch (t: Throwable) {
            // Android 12+: 백그라운드 FGS 시작 제한 / Android 14: 유형별 권한·while-in-use → 정직한 로컬 행동 요청
            Log.w(TAG, "포그라운드 전환 실패: $t")
            lastError = JSONObject().put("code", "needs_local_action").put("message", t.toString())
            deliver(JSONObject().put("error", "needs_local_action").put("message", localActionMessage(env))
                .put("needs_local_action", JSONObject().put("code", "permission_required").put("reason", t.javaClass.simpleName)
                    .put("message", localActionMessage(env))))
            finish(); return
        }
        val r = SessionRunner(applicationContext, env) { reason ->
            Log.i(TAG, "세션 끝남($reason) — 서비스 내림")
            synchronized(LOCK) { if (runner?.sessionId == env.sessionId) runner = null }
            lastEnd = JSONObject().put("session_id", env.sessionId).put("reason", reason)
            RemoteMediaStart.release(env.sessionId)
            finish()
        }
        synchronized(LOCK) { runner = r }
        try { r.start() } catch (t: Throwable) {
            Log.e(TAG, "세션 시작 실패: $t")
            r.end("start_failed", notifyHub = false)
            deliver(JSONObject().put("error", "needs_local_action").put("message", t.toString())
                .put("needs_local_action", JSONObject().put("code", "camera_unavailable").put("message", t.toString())))
            return
        }
        deliver(JSONObject().put("accepted", true).put("session_id", env.sessionId).put("purpose", env.purpose)
            .put("fgs_type", fgsType(env)))
    }

    private fun finish() {
        try { ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE) } catch (_: Throwable) {}
        stopSelf()
    }

    override fun onDestroy() {
        runner?.takeIf { !it.ended }?.end("service_destroyed", notifyHub = true)
        super.onDestroy()
    }

    /** API 30+: 용도별 비트. API 29: mediaPlayback 또는 매니페스트 전체. API 28(J7·Android 9): 유형 없음. */
    private fun fgsType(env: MediaEnvelope): Int {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.Q) return 0
        val playback = env.receivesAudio() || env.receivesVideo() || env.isContentDelivery()
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) {
            return if (playback && !env.sendsVideo() && !env.sendsAudio()) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
                   else ServiceInfo.FOREGROUND_SERVICE_TYPE_MANIFEST
        }
        var t = 0
        if (env.sendsVideo()) t = t or ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA
        if (env.sendsAudio()) t = t or ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE
        if (playback) t = t or ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
        return if (t == 0) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK else t
    }

    private fun buildNotification(env: MediaEnvelope): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(NotificationChannel(CH_ID, "IndieBiz 미디어 세션", NotificationManager.IMPORTANCE_LOW).apply { setShowBadge(false) })
        val what = when (env.purpose) {
            "camera" -> "카메라를 중앙 PC 로 보내는 중"
            "microphone" -> "마이크를 중앙 PC 로 보내는 중"
            "speaker" -> "중앙 PC 의 소리를 재생 중"
            "playback" -> "중앙 PC 가 보낸 콘텐츠 재생 중"
            "voice_call" -> "음성 통화 중"
            "video_call" -> "영상 통화 중"
            else -> "미디어 세션"
        }
        val display = env.isContentDelivery() || env.receivesVideo()
        val tap = PendingIntent.getActivity(this, 0, Intent(this, if (display) MediaDisplayActivity::class.java else CctvModeActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
        return Notification.Builder(this, CH_ID)
            .setContentTitle("IndieBiz 미디어 세션").setContentText(what)
            .setSmallIcon(android.R.drawable.ic_menu_camera).setOngoing(true).setContentIntent(tap).build()
    }

    companion object {
        private const val TAG = "IndieBizMediaSvc"
        const val CH_ID = "media_session"
        const val NOTIF_ID = 1002
        const val ACTION_START = "com.indiebiz.phoneagent.media.START"
        const val ACTION_STOP = "com.indiebiz.phoneagent.media.STOP"
        const val EXTRA_ENVELOPE = "envelope"
        const val EXTRA_SESSION = "session_id"
        const val EXTRA_REASON = "reason"
        private val LOCK = Any()
        @Volatile private var runner: SessionRunner? = null
        @Volatile private var pending: CountDownLatch? = null
        @Volatile private var pendingResult: JSONObject? = null
        @Volatile private var lastError: JSONObject? = null
        @Volatile private var lastEnd: JSONObject? = null

        private fun localActionMessage(env: MediaEnvelope): String =
            if (env.isContentDelivery() || env.receivesVideo()) "폰에서 미디어 화면을 열고 다시 시도해 주세요"
            else "폰에서 카메라 대기 모드를 시작해 주세요"

        fun currentRunner(): SessionRunner? = runner?.takeIf { !it.ended }

        fun currentSessionId(): String? = runner?.takeIf { !it.ended }?.sessionId

        private fun deliver(result: JSONObject) { pendingResult = result; pending?.countDown() }

        /** MediaBridge.start → 서비스 접수 결과를 동기(≤3초)로. 그 뒤는 시그널링 WS 가 보고한다. */
        fun request(ctx: Context, env: MediaEnvelope, remoteToken: String? = null): JSONObject {
            // ★LOCK 은 검사·등록에만 — 서비스 onStartCommand(메인 스레드)도 LOCK 을 잡으므로 대기 중엔 놓는다.
            val latch = CountDownLatch(1)
            synchronized(LOCK) {
                runner?.takeIf { !it.ended }?.let { r ->
                    return if (r.sessionId == env.sessionId) JSONObject().put("accepted", true).put("session_id", r.sessionId).put("already_active", true)
                           else JSONObject().put("error", "device_busy").put("message", "다른 미디어 세션이 진행 중입니다").put("active_session", r.sessionId)
                }
                if (pending != null) return JSONObject().put("error", "device_busy").put("message", "다른 세션 접수가 진행 중입니다")
                pending = latch; pendingResult = null
            }
            val intent = Intent(ctx, MediaSessionService::class.java).setAction(ACTION_START).putExtra(EXTRA_ENVELOPE, env.raw.toString())
                .putExtra(RemoteMediaStart.EXTRA_TOKEN, remoteToken)
            try { ContextCompat.startForegroundService(ctx, intent) } catch (t: Throwable) {
                pending = null
                return JSONObject().put("error", "needs_local_action").put("message", "서비스 시작 거부: $t")
                    .put("needs_local_action", JSONObject().put("code", "permission_required").put("message", localActionMessage(env)))
            }
            try { latch.await(3, TimeUnit.SECONDS) } catch (_: InterruptedException) {}
            pending = null
            val r = pendingResult ?: return JSONObject().put("error", "needs_local_action").put("message", "서비스 접수 응답 없음(3초)")
                .put("needs_local_action", JSONObject().put("code", "permission_required").put("message", localActionMessage(env)))
            if (r.optString("error") == "accepted") return JSONObject().put("accepted", true).put("session_id", r.optString("active_session")).put("already_active", true)
            return r
        }

        fun stop(ctx: Context, sessionId: String?, reason: String): JSONObject {
            val r = runner?.takeIf { !it.ended }
            if (r == null || (sessionId != null && r.sessionId != sessionId)) {
                return JSONObject().put("stopped", false).put("session_id", r?.sessionId ?: JSONObject.NULL)
                    .put("reason", if (r == null) "no_active_session" else "session_mismatch")
            }
            r.end(reason, notifyHub = true)
            return JSONObject().put("stopped", true).put("session_id", r.sessionId)
        }

        fun statusJson(): JSONObject {
            val r = runner
            if (r != null && !r.ended) return r.statusJson()
            return JSONObject().put("session_id", JSONObject.NULL).put("state", "idle")
                .put("last_end", lastEnd ?: JSONObject.NULL).put("last_error", lastError ?: JSONObject.NULL)
                .put("armed", CctvState.armed)
        }
    }
}
