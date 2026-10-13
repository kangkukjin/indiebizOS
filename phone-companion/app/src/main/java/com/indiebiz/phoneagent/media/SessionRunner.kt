package com.indiebiz.phoneagent.media

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.net.wifi.WifiManager
import android.os.PowerManager
import android.util.Log
import org.json.JSONObject
import org.webrtc.IceCandidate
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * 세션 하나의 수명 — 시그널링(SignalingClient) ↔ 엔진(MediaEngine | ContentPlayer) 을 잇고
 * 오디오 포커스·모드·WakeLock 을 쥔다. 종료는 멱등(허브 end · 로컬 중지 · 시그널링 상실 · 시간 초과 · 서비스 파괴).
 */
class SessionRunner(private val ctx: Context, val env: MediaEnvelope, private val onEnded: (String) -> Unit)
    : SignalingClient.Listener, MediaEngine.Listener, ContentPlayer.Listener {

    val sessionId: String get() = env.sessionId
    @Volatile var state: String = "connecting"; private set
    @Volatile var ended: Boolean = false; private set
    @Volatile var endReason: String = ""; private set
    @Volatile private var needsLocalAction: JSONObject? = null
    @Volatile private var lastQuality: JSONObject? = null
    @Volatile private var lastPlayback: JSONObject? = null

    private val signaling = SignalingClient(env, this)
    private var engine: MediaEngine? = null
    private var player: ContentPlayer? = null
    private val exec = Executors.newSingleThreadScheduledExecutor()
    private var statsTask: ScheduledFuture<*>? = null
    private var timeoutTask: ScheduledFuture<*>? = null
    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null
    private var focus: AudioFocusRequest? = null
    private val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val startedAt = System.currentTimeMillis()

    fun start() {
        acquireLocks()
        setupAudio()
        try {
            if (env.needsPeer()) engine = MediaEngine(ctx, env, this).also { it.start() }
            if (env.isContentDelivery()) player = ContentPlayer(ctx, env, this).also { it.start() }
        } catch (t: Throwable) {
            Log.e(TAG, "엔진 시작 실패: $t")
            needsLocalAction = JSONObject().put("code", "camera_unavailable").put("message", "엔진 시작 실패: ${t.message}")
            state = "needs_local_action"
        }
        signaling.connect()
        val period = maxOf(env.lease.keepaliveS, 5.0)
        statsTask = exec.scheduleAtFixedRate({ reportQuality() }, (period * 1000).toLong(), (period * 1000).toLong(), TimeUnit.MILLISECONDS)
        timeoutTask = exec.schedule({ end("timeout", notifyHub = true) }, (env.timeoutS * 1000).toLong(), TimeUnit.MILLISECONDS)
    }

    private fun acquireLocks() {
        try {
            val pm = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "indiebiz:media_session").apply { acquire() }
        } catch (_: Throwable) {}
        try {
            val wm = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
            wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "indiebiz_media_session").apply { acquire() }
        } catch (_: Throwable) {}
    }

    /** 통화류 = VOICE_COMMUNICATION + 통신 모드 + 스피커폰, 스피커·재생 = MEDIA. 화면 없는 몸은 늘 스피커로. */
    @Suppress("DEPRECATION")
    private fun setupAudio() {
        if (!(env.receivesAudio() || env.isContentDelivery() || env.sendsAudio())) return
        val call = env.isCallLike()
        val attrs = AudioAttributes.Builder()
            .setUsage(if (call) AudioAttributes.USAGE_VOICE_COMMUNICATION else AudioAttributes.USAGE_MEDIA)
            .setContentType(if (call) AudioAttributes.CONTENT_TYPE_SPEECH else AudioAttributes.CONTENT_TYPE_MUSIC).build()
        try {
            focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN).setAudioAttributes(attrs).build()
            am.requestAudioFocus(focus!!)
        } catch (_: Throwable) {}
        try {
            am.mode = if (call) AudioManager.MODE_IN_COMMUNICATION else AudioManager.MODE_NORMAL
            am.isSpeakerphoneOn = true
        } catch (_: Throwable) {}
    }

    @Suppress("DEPRECATION")
    private fun releaseAudio() {
        try { focus?.let { am.abandonAudioFocusRequest(it) } } catch (_: Throwable) {}
        try { am.mode = AudioManager.MODE_NORMAL; am.isSpeakerphoneOn = false } catch (_: Throwable) {}
    }

    // ── 상태 보고 ────────────────────────────────────────────────────────────────
    private fun reportState(extra: JSONObject? = null) {
        if (ended) return
        signaling.sendState(state, engine?.path ?: (if (player != null) "direct" else null), lastQuality, needsLocalAction, extra)
    }

    private fun reportQuality() {
        if (ended) return
        val e = engine
        if (e == null) { reportState(lastPlayback); return }
        e.collectStats { q -> lastQuality = q; reportState() }
    }

    fun statusJson(): JSONObject = JSONObject().put("session_id", sessionId).put("purpose", env.purpose)
        .put("state", if (ended) "ended" else state).put("path", engine?.path ?: JSONObject.NULL)
        .put("generation", signaling.generation).put("signaling", if (signaling.connected) signaling.transport else "down")
        .put("quality", lastQuality ?: JSONObject.NULL).put("playback", lastPlayback ?: JSONObject.NULL)
        .put("needs_local_action", needsLocalAction ?: JSONObject.NULL).put("end_reason", endReason)
        .put("elapsed_s", (System.currentTimeMillis() - startedAt) / 1000)

    // ── SignalingClient.Listener ───────────────────────────────────────────────
    override fun onReady(reconnected: Boolean) {
        if (reconnected && engine != null) {
            signaling.bumpGeneration()
            engine?.restartIce()
            signaling.send("renegotiate", JSONObject().put("reason", "signaling_reconnected").put("ice_restart", true))
            if (state == "active") state = "reconnecting"
        }
        reportState(lastPlayback)
    }
    override fun onOffer(sdp: String, generation: Int) { engine?.handleOffer(sdp) }
    override fun onCandidate(candidate: JSONObject) { engine?.addRemoteCandidate(candidate) }
    override fun onCandidatesDone() {}
    override fun onRenegotiate(payload: JSONObject) { /* 허브가 곧 새 offer 를 보낸다 — answerer 는 기다린다 */ }
    override fun onUpdate(changes: JSONObject) {
        engine?.let { e ->
            if (changes.has("mute")) e.setMuted(changes.optBoolean("mute"))
            when (val cam = changes.opt("camera")) {
                is Boolean -> e.setCameraEnabled(cam)
                "front", "back" -> e.switchCamera()
                "off" -> e.setCameraEnabled(false)
                "on" -> e.setCameraEnabled(true)
            }
            changes.optJSONObject("quality")?.let { q ->
                e.setCaptureFormat(q.optInt("width", e.width), q.optInt("height", e.height), q.optInt("fps", e.fps))
            }
        }
        if (changes.has("content")) player?.apply(changes)
    }
    override fun onEnd(reason: String) { end(reason, notifyHub = false) }
    override fun onLost(reason: String) { end(reason, notifyHub = false) }

    // ── MediaEngine.Listener ───────────────────────────────────────────────────
    override fun onLocalCandidate(c: IceCandidate) { signaling.sendCandidate(c) }
    override fun onAnswer(sdp: String, fingerprint: String) { signaling.sendAnswer(sdp, fingerprint) }
    override fun onConnectionState(s: String) {
        when (s) {
            "active" -> { state = "active"; needsLocalAction = null; reportState() }
            "reconnecting", "connecting" -> { state = s; reportState() }
            "failed" -> {
                state = "reconnecting"
                signaling.bumpGeneration()
                engine?.restartIce()
                signaling.send("renegotiate", JSONObject().put("reason", "ice_failed").put("ice_restart", true))
                reportState()
            }
        }
    }
    override fun onPath(path: String) { reportState() }
    override fun onCameraProblem(code: String, message: String) {
        needsLocalAction = JSONObject().put("code", code).put("message", message)
        state = "needs_local_action"
        reportState()
    }

    // ── ContentPlayer.Listener ─────────────────────────────────────────────────
    override fun onPlayback(report: JSONObject) {
        lastPlayback = report
        if (state != "active" && report.optBoolean("playing")) state = "active"
        reportState(report)
    }
    override fun onContentError(code: String, message: String) {
        signaling.sendState("ended", null, null, null, JSONObject().put("error", JSONObject().put("code", code).put("message", message)))
        end(code, notifyHub = true)
    }

    // ── 종료(멱등) ─────────────────────────────────────────────────────────────
    @Synchronized
    fun end(reason: String, notifyHub: Boolean) {
        if (ended) return
        ended = true; endReason = reason; state = "ended"
        Log.i(TAG, "세션 종료 ${sessionId.take(8)}… ($reason)")
        statsTask?.cancel(false); timeoutTask?.cancel(false)
        if (notifyHub) { try { signaling.sendEnd(reason) } catch (_: Throwable) {} }
        try { signaling.close() } catch (_: Throwable) {}
        try { engine?.close() } catch (t: Throwable) { Log.w(TAG, "엔진 정리 실패: $t") }
        try { player?.stop() } catch (_: Throwable) {}
        releaseAudio()
        try { wakeLock?.let { if (it.isHeld) it.release() } } catch (_: Throwable) {}
        try { wifiLock?.let { if (it.isHeld) it.release() } } catch (_: Throwable) {}
        exec.shutdown()
        onEnded(reason)
    }

    companion object { private const val TAG = "IndieBizMediaSession" }
}
