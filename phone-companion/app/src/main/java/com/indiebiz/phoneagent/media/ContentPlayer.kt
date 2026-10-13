package com.indiebiz.phoneagent.media

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.view.Surface
import org.json.JSONObject

/** A session-owned audio/video player. All MediaPlayer operations run on the main looper. */
class ContentPlayer(private val ctx: Context, private val env: MediaEnvelope, private val listener: Listener) {
    interface Listener {
        fun onPlayback(report: JSONObject)
        fun onContentError(code: String, message: String)
    }
    private val main = Handler(Looper.getMainLooper())
    private var mp: MediaPlayer? = null
    private var surface: Surface? = null
    private var prepared = false
    private var closed = false
    private var pendingSeekS = env.content?.positionS ?: 0.0
    private var volume = env.content?.volume ?: 80
    private val output = PlaybackOutputState().apply { paused = env.content?.paused ?: false }
    private var width = 0
    private var height = 0
    @Volatile private var latest = JSONObject()
    private val tick = object : Runnable {
        override fun run() { if (!closed) { report(); main.postDelayed(this, 1000) } }
    }
    private fun onMain(action: () -> Unit) {
        if (Looper.myLooper() == Looper.getMainLooper()) action() else main.post { if (!closed) action() }
    }

    fun start() = onMain {
        val url = env.contentUrl()
        if (url == null) { listener.onContentError("content_unavailable", "재생 주소가 없습니다"); return@onMain }
        val p = MediaPlayer()
        mp = p
        try {
            p.setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_MEDIA)
                .setContentType(AudioAttributes.CONTENT_TYPE_MOVIE).build())
            p.setWakeMode(ctx, PowerManager.PARTIAL_WAKE_LOCK)
            p.setSurface(surface)
            p.setOnVideoSizeChangedListener { _, w, h ->
                width = w; height = h
                if (w > 0 && h > 0) output.hasVideo = true
                reconcile(); report()
            }
            p.setOnPreparedListener {
                if (!closed) {
                    prepared = true
                    output.hasVideo = p.videoWidth > 0 || p.trackInfo.any { it.trackType == MediaPlayer.TrackInfo.MEDIA_TRACK_TYPE_VIDEO }
                    width = p.videoWidth; height = p.videoHeight
                    applyVolume()
                    if (pendingSeekS > 0) seek(pendingSeekS) else reconcile()
                    report(); main.post(tick)
                }
            }
            p.setOnSeekCompleteListener { output.seeking = false; reconcile(); report() }
            p.setOnInfoListener { _, what, _ ->
                if (what == MediaPlayer.MEDIA_INFO_VIDEO_RENDERING_START) { output.rendered = output.visible; report() }
                false
            }
            p.setOnErrorListener { _, what, extra ->
                listener.onContentError("content_unavailable", "동영상을 재생하지 못했습니다 ($what/$extra)"); true
            }
            p.setOnCompletionListener { output.ended = true; report() }
            p.setDataSource(url)
            p.prepareAsync()
        } catch (t: Throwable) { listener.onContentError("content_unavailable", "콘텐츠 열기 실패: ${t.message}") }
    }

    /** Detaching/locking pauses video without changing the owner's requested pause state. Audio continues. */
    fun setSurface(next: Surface?) = onMain {
        surface = next
        output.visible = next?.isValid == true
        try {
            mp?.setSurface(next)
            reconcile()
            report()
        } catch (t: Throwable) { listener.onContentError("display_unavailable", "영상 화면 연결 실패: ${t.message}") }
    }

    fun frameRendered() = onMain {
        if (prepared && output.hasVideo && output.visible && !output.seeking && !output.rendered) { output.rendered = true; report() }
    }

    private fun seek(seconds: Double) {
        pendingSeekS = seconds.coerceAtLeast(0.0)
        output.seeking = true; output.ended = false
        mp?.seekTo((pendingSeekS * 1000).toLong(), MediaPlayer.SEEK_CLOSEST)
    }
    private fun reconcile() {
        if (!prepared || closed) return
        try {
            val p = mp ?: return
            if (output.canPlay) { if (!p.isPlaying) p.start() }
            else if (p.isPlaying) p.pause()
        } catch (t: Throwable) { listener.onContentError("content_unavailable", "재생 제어 실패: ${t.message}") }
    }
    fun apply(changes: JSONObject) = onMain {
        val c = changes.optJSONObject("content") ?: changes
        try {
            if (c.has("volume")) { volume = c.optInt("volume", volume).coerceIn(0, 100); applyVolume() }
            if (c.has("paused")) { output.paused = c.optBoolean("paused"); if (!output.paused) output.ended = false }
            if (c.has("position_s")) {
                pendingSeekS = c.optDouble("position_s", 0.0).coerceAtLeast(0.0)
                if (prepared) seek(pendingSeekS)
            }
            reconcile(); report()
        } catch (t: Throwable) { listener.onContentError("content_unavailable", "재생 제어 실패: ${t.message}") }
    }
    fun snapshot(): JSONObject = latest
    private fun report() {
        if (closed) return
        val p = mp
        val running = try { prepared && p?.isPlaying == true } catch (_: Throwable) { false }
        val pos = try { if (prepared) p!!.currentPosition / 1000.0 else pendingSeekS } catch (_: Throwable) { pendingSeekS }
        val duration = try { if (prepared) (p!!.duration / 1000.0).coerceAtLeast(0.0) else 0.0 } catch (_: Throwable) { 0.0 }
        latest = JSONObject().put("playing", output.playing(running)).put("position_s", pos)
            .put("paused", output.paused).put("volume", volume).put("duration_s", duration).put("ended", output.ended)
            .put("has_video", output.hasVideo).put("video_visible", output.visible && output.rendered)
            .put("needs_display", output.needsDisplay).put("width", width).put("height", height)
        listener.onPlayback(latest)
    }
    private fun applyVolume() {
        val am = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        am.setStreamVolume(AudioManager.STREAM_MUSIC, Math.round(am.getStreamMaxVolume(AudioManager.STREAM_MUSIC) * volume / 100f), 0)
        mp?.setVolume(1f, 1f)
    }
    fun stop() = onMain {
        if (!closed) {
            closed = true; main.removeCallbacksAndMessages(null)
            mp?.release(); mp = null; surface = null
        }
    }
}
