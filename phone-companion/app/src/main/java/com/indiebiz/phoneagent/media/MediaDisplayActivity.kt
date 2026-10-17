package com.indiebiz.phoneagent.media

import android.app.Activity
import android.graphics.Color
import android.graphics.SurfaceTexture
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.view.Surface
import android.view.TextureView
import android.view.View
import android.view.WindowManager
import android.widget.Button
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import org.json.JSONObject
import org.webrtc.RendererCommon
import org.webrtc.SurfaceViewRenderer
import org.webrtc.VideoTrack

/** Local output surface for registered-device sessions. No camera/microphone permissions or enrollment. */
class MediaDisplayActivity : Activity(), TextureView.SurfaceTextureListener {
    private val main = Handler(Looper.getMainLooper())
    private lateinit var stage: FrameLayout
    private lateinit var texture: TextureView
    private lateinit var status: TextView
    private lateinit var pause: Button
    private lateinit var seek: SeekBar
    private lateinit var volume: SeekBar
    private var surface: Surface? = null
    private var runner: SessionRunner? = null
    private var renderer: SurfaceViewRenderer? = null
    private var track: VideoTrack? = null
    private var foreground = false
    private var seeking = false
    private var ticket: RemoteStartTicket? = null
    private var sessionId = ""
    private val poll = object : Runnable {
        override fun run() { if (foreground) { refresh(); main.postDelayed(this, 400) } }
    }

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        val token = intent.getStringExtra(RemoteMediaStart.EXTRA_TOKEN)
        if (token != null) {
            ticket = RemoteMediaStart.attach(this, token)
            if (ticket == null) { finish(); return }
            sessionId = ticket!!.sessionId
        } else {
            // A notification may reopen only its still-running session, never a waiting screen.
            sessionId = intent.getStringExtra(MediaSessionService.EXTRA_SESSION) ?: ""
            if (sessionId.isEmpty() || MediaSessionService.currentSessionId() != sessionId) { finish(); return }
        }
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        volumeControlStream = android.media.AudioManager.STREAM_MUSIC
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        val root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setBackgroundColor(Color.BLACK) }
        status = TextView(this).apply { setTextColor(Color.WHITE); setPadding(20, 12, 20, 12) }
        root.addView(status)
        stage = FrameLayout(this)
        texture = TextureView(this).apply { surfaceTextureListener = this@MediaDisplayActivity }
        stage.addView(texture, FrameLayout.LayoutParams(-1, -1))
        root.addView(stage, LinearLayout.LayoutParams(-1, 0, 1f))
        seek = SeekBar(this).apply {
            max = 1000
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onStartTrackingTouch(bar: SeekBar) { seeking = true }
                override fun onProgressChanged(bar: SeekBar, value: Int, fromUser: Boolean) {}
                override fun onStopTrackingTouch(bar: SeekBar) {
                    val duration = runner?.playbackSnapshot()?.optDouble("duration_s", 0.0) ?: 0.0
                    runner?.onUpdate(JSONObject().put("content", JSONObject().put("position_s", duration * bar.progress / 1000)))
                    seeking = false
                }
            })
        }
        root.addView(seek)
        volume = SeekBar(this).apply {
            max = 100
            contentDescription = "재생 볼륨"
            setOnSeekBarChangeListener(object : SeekBar.OnSeekBarChangeListener {
                override fun onStartTrackingTouch(bar: SeekBar) {}
                override fun onStopTrackingTouch(bar: SeekBar) {}
                override fun onProgressChanged(bar: SeekBar, value: Int, fromUser: Boolean) {
                    if (fromUser) runner?.onUpdate(JSONObject().put("content", JSONObject().put("volume", value)))
                }
            })
        }
        root.addView(volume)
        val buttons = LinearLayout(this)
        pause = Button(this).apply {
            text = "일시정지"
            setOnClickListener {
                val snapshot = runner?.playbackSnapshot()
                val paused = snapshot?.optBoolean("paused", false) == true || snapshot?.optBoolean("ended", false) == true
                runner?.onUpdate(JSONObject().put("content", JSONObject().put("paused", !paused)))
            }
        }
        buttons.addView(pause)
        buttons.addView(Button(this).apply { text = "재생 종료"; setOnClickListener { runner?.end("local_end", true) } })
        buttons.addView(Button(this).apply { text = "닫기"; setOnClickListener { finish() } })
        root.addView(buttons)
        setContentView(root)
    }

    override fun onResume() {
        super.onResume()
        if (isFinishing) return
        foreground = true; main.post(poll); markVisible()
    }
    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) markVisible()
    }
    private fun markVisible() {
        main.post {
            val t = ticket ?: return@post
            if (foreground && hasWindowFocus() && !isFinishing &&
                texture.isAvailable && getSystemService(PowerManager::class.java).isInteractive) {
                if (!t.resume(SystemClock.elapsedRealtime())) finish()
            }
        }
    }
    override fun onPause() {
        foreground = false; main.removeCallbacks(poll); detach()
        super.onPause()
    }
    override fun onStop() {
        val t = ticket
        if (t == null || t.resumed || isFinishing) {
            RemoteMediaStart.release(sessionId)
            MediaSessionService.stop(applicationContext, sessionId, "local_display_closed")
        }
        super.onStop()
    }
    override fun onDestroy() {
        main.removeCallbacksAndMessages(null)
        ticket?.let { RemoteMediaStart.release(it.sessionId) }
        detach(); surface?.release(); surface = null; super.onDestroy()
    }

    private fun detach() {
        val old = runner
        old?.releaseDisplay = null
        old?.setOutputSurface(null)
        old?.setVideoVisible(false)
        track?.removeSink(renderer); track = null
        renderer?.release(); renderer?.let { stage.removeView(it) }; renderer = null
        runner = null
    }
    private fun refresh() {
        if (ticket?.valid(SystemClock.elapsedRealtime()) == false) { finish(); return }
        val next = MediaSessionService.currentRunner()?.takeIf {
            it.sessionId == sessionId && (it.env.isContentDelivery() || it.env.receivesVideo())
        }
        if (next !== runner) {
            detach(); runner = next
            next?.releaseDisplay = { detach(); finish() }
            next?.setOutputSurface(surface)
            next?.setVideoVisible(true)
        }
        val r = runner
        val content = r?.env?.isContentDelivery() == true
        pause.visibility = if (content) View.VISIBLE else View.GONE
        seek.visibility = pause.visibility; volume.visibility = pause.visibility
        if (r == null) {
            status.text = "중앙 PC의 영상 연결 중"
            if (ticket == null || ticket?.committed == true) finish()
            return
        }
        if (content) {
            texture.visibility = View.VISIBLE
            val p = r.playbackSnapshot()
            val pos = p.optDouble("position_s", 0.0); val duration = p.optDouble("duration_s", 0.0)
            status.text = "${if (p.optBoolean("ended")) "재생 완료" else if (p.optBoolean("paused")) "일시정지" else if (p.optBoolean("playing")) "재생 중" else "영상 준비 중"} · ${pos.toInt()} / ${duration.toInt()}초"
            pause.text = if (p.optBoolean("paused") || p.optBoolean("ended")) "재생" else "일시정지"
            seek.isEnabled = duration > 0
            if (!seeking) seek.progress = if (duration > 0) (pos / duration * 1000).toInt() else 0
            volume.progress = p.optInt("volume", 80)
            val w = p.optInt("width"); val h = p.optInt("height")
            if (w > 0 && h > 0 && stage.width > 0 && stage.height > 0) {
                val ratio = minOf(stage.width.toFloat() / w, stage.height.toFloat() / h)
                val params = texture.layoutParams as FrameLayout.LayoutParams
                val newW = (w * ratio).toInt(); val newH = (h * ratio).toInt()
                if (params.width != newW || params.height != newH) {
                    params.width = newW; params.height = newH; params.gravity = android.view.Gravity.CENTER; texture.layoutParams = params
                }
            }
        } else {
            texture.visibility = View.INVISIBLE
            status.text = when (r.state) { "active" -> "중앙PC 영상 수신 중"; "reconnecting" -> "재연결 중"; else -> "영상 연결 중" }
            val incoming = r.remoteVideo
            if (incoming != null && incoming !== track) {
                track?.removeSink(renderer)
                if (renderer == null) {
                    renderer = SurfaceViewRenderer(this).also { view ->
                        view.init(r.eglContext, object : RendererCommon.RendererEvents {
                            override fun onFirstFrameRendered() { main.post { if (runner === r) r.videoFrameRendered() } }
                            override fun onFrameResolutionChanged(w: Int, h: Int, rotation: Int) {}
                        })
                        view.setScalingType(RendererCommon.ScalingType.SCALE_ASPECT_FIT)
                        stage.addView(view, FrameLayout.LayoutParams(-1, -1))
                    }
                }
                track = incoming; incoming.addSink(renderer)
            }
        }
    }
    override fun onSurfaceTextureAvailable(value: SurfaceTexture, width: Int, height: Int) {
        surface?.release(); surface = Surface(value)
        markVisible()
        if (foreground) { runner?.setOutputSurface(surface); if (runner?.env?.receivesVideo() != true) runner?.setVideoVisible(true) }
    }
    override fun onSurfaceTextureSizeChanged(value: SurfaceTexture, width: Int, height: Int) {}
    override fun onSurfaceTextureDestroyed(value: SurfaceTexture): Boolean {
        runner?.setOutputSurface(null); if (runner?.env?.receivesVideo() != true) runner?.setVideoVisible(false)
        surface?.release(); surface = null
        return true
    }
    override fun onSurfaceTextureUpdated(value: SurfaceTexture) { runner?.contentFrameRendered() }
}
