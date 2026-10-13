package com.indiebiz.phoneagent.media

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.net.wifi.WifiManager
import android.os.PowerManager
import android.util.Log
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * 콘텐츠 전달(purpose=playback, delivery=content, 계약 §7) — 허브가 발급한 세션 소유 참조
 * `/media/content/<ref>?token=` 을 폰이 직접 디코딩한다. PhoneActions.playStream 과 같은 MediaPlayer
 * 쓰임이지만 **세션에 묶인다**: 2초마다 state{playing, position_s, paused, volume} 보고, update 로
 * pause/resume/seek/volume, 세션 종료 = 재생 종료. (Media3 는 필요가 생길 때 — 지금은 MediaPlayer 로 충분.)
 */
class ContentPlayer(private val ctx: Context, private val env: MediaEnvelope, private val listener: Listener) {
    interface Listener {
        fun onPlayback(report: JSONObject)                 // {playing, position_s, paused, volume, duration_s, ended?}
        fun onContentError(code: String, message: String)
    }

    private val exec = Executors.newSingleThreadScheduledExecutor()
    private var reporter: ScheduledFuture<*>? = null
    private var mp: MediaPlayer? = null
    private var wifiLock: WifiManager.WifiLock? = null
    @Volatile private var prepared = false
    @Volatile private var paused = env.content?.paused ?: false
    @Volatile private var volume = env.content?.volume ?: 80
    @Volatile private var ended = false
    private var pendingSeekS: Double = env.content?.positionS ?: 0.0

    fun start() {
        val url = env.contentUrl()
        if (url == null) { listener.onContentError("content_unavailable", "content.url/ref 없음"); return }
        val p = MediaPlayer()
        mp = p
        try {
            p.setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MUSIC).build())
            p.setWakeMode(ctx, PowerManager.PARTIAL_WAKE_LOCK)
            p.setOnPreparedListener {
                prepared = true
                try {
                    if (pendingSeekS > 0) it.seekTo((pendingSeekS * 1000).toInt())
                    applyVolume(it, volume)
                    if (!paused) it.start()
                } catch (t: Throwable) { listener.onContentError("content_unavailable", "재생 시작 실패: ${t.message}") }
                report()
                reporter = exec.scheduleAtFixedRate({ report() }, 2000, 2000, TimeUnit.MILLISECONDS)
            }
            p.setOnErrorListener { _, what, extra ->
                listener.onContentError("content_unavailable", "MediaPlayer 오류 $what/$extra"); true
            }
            p.setOnCompletionListener { ended = true; report() }
            try {
                val wm = ctx.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
                wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "indiebiz_media_content").apply { acquire() }
            } catch (_: Throwable) {}
            p.setDataSource(url)
            p.prepareAsync()
        } catch (t: Throwable) {
            listener.onContentError("content_unavailable", "콘텐츠 열기 실패: ${t.message}")
        }
    }

    /** 허브 update changes{content{paused, position_s, volume}} — 반영 뒤 즉시 보고(조작 반영 p95 300ms 목표). */
    fun apply(changes: JSONObject) {
        val c = changes.optJSONObject("content") ?: changes
        val p = mp
        try {
            if (c.has("volume")) { volume = c.optInt("volume", volume).coerceIn(0, 100); p?.let { applyVolume(it, volume) } }
            if (c.has("position_s")) {
                val pos = c.optDouble("position_s", 0.0).coerceAtLeast(0.0)
                if (prepared && p != null) p.seekTo((pos * 1000).toInt()) else pendingSeekS = pos
            }
            if (c.has("paused")) {
                paused = c.optBoolean("paused", paused)
                if (prepared && p != null) { if (paused) { if (p.isPlaying) p.pause() } else { ended = false; p.start() } }
            }
        } catch (t: Throwable) { Log.w(TAG, "update 반영 실패: $t") }
        report()
    }

    fun snapshot(): JSONObject {
        val p = mp
        val playing = try { prepared && p?.isPlaying == true } catch (_: Throwable) { false }
        val pos = try { if (prepared && p != null) p.currentPosition / 1000.0 else pendingSeekS } catch (_: Throwable) { 0.0 }
        val dur = try { if (prepared && p != null && p.duration > 0) p.duration / 1000.0 else 0.0 } catch (_: Throwable) { 0.0 }
        return JSONObject().put("playing", playing).put("position_s", pos).put("paused", paused)
            .put("volume", volume).put("duration_s", dur).put("ended", ended)
    }

    private fun report() { try { listener.onPlayback(snapshot()) } catch (_: Throwable) {} }

    private fun applyVolume(p: MediaPlayer, vol: Int) {
        // 무인 폰은 미디어 볼륨이 0 일 수 있다 — PhoneActions.playStream 과 같은 규칙으로 스트림 볼륨을 퍼센트로.
        try {
            val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
            val max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
            am.setStreamVolume(AudioManager.STREAM_MUSIC, Math.round(max * vol / 100f), 0)
        } catch (_: Throwable) {}
        try { p.setVolume(1f, 1f) } catch (_: Throwable) {}
    }

    fun stop() {
        reporter?.cancel(false)
        exec.shutdown()
        val p = mp ?: return
        mp = null
        try { if (p.isPlaying) p.stop() } catch (_: Throwable) {}
        try { p.release() } catch (_: Throwable) {}
        try { wifiLock?.let { if (it.isHeld) it.release() } } catch (_: Throwable) {}
        wifiLock = null
    }

    companion object { private const val TAG = "IndieBizMediaContent" }
}
