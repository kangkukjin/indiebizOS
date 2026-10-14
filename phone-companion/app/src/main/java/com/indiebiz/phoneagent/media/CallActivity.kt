package com.indiebiz.phoneagent.media

import android.Manifest
import android.app.*
import android.content.*
import android.content.pm.PackageManager
import android.media.AudioManager
import android.os.*
import android.view.WindowManager
import android.widget.*
import androidx.core.content.ContextCompat
import org.json.JSONObject
import org.webrtc.SurfaceViewRenderer
import org.webrtc.VideoTrack
import java.util.concurrent.Executors

/** Ordinary phone calls. No extension key or provisioning is consulted here. */
class CallActivity : Activity() {
    private val worker = Executors.newSingleThreadExecutor()
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var root: LinearLayout
    private lateinit var status: TextView
    private var id = ""
    private var video = false
    private var pending: (() -> Unit)? = null
    private var remote: SurfaceViewRenderer? = null
    private var preview: SurfaceViewRenderer? = null
    private var boundLocal: VideoTrack? = null
    private var boundRemote: VideoTrack? = null
    private var muted = false
    private var cameraOff = false
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        root = LinearLayout(this).apply { orientation = LinearLayout.VERTICAL; setPadding(20, 32, 20, 20) }
        status = TextView(this).apply { text = "IndieBiz 통화"; textSize = 20f }; root.addView(status)
        setContentView(root)
        id = savedInstanceState?.getString("session_id") ?: intent.getStringExtra("session_id") ?: ""
        if (id.isEmpty() && intent.hasExtra("target")) {
            startOutgoing()
            return
        }
        if (id.isEmpty()) id = CallService.session?.id ?: ""
        if (id.isEmpty()) worker.execute {
            try {
                val items = CallSession.request("/media/sessions").getJSONArray("items")
                for (i in 0 until items.length()) {
                    val s = items.getJSONObject(i)
                    if (s.optString("state") == "ringing") { id = s.getString("session_id"); break }
                }
            } catch (_: Exception) { }
            runOnUiThread { if (id.isEmpty()) status.text = "메신저에서 이웃을 선택해 통화하세요." else showSession() }
        } else showSession()
    }
    private fun button(label: String, action: () -> Unit) { root.addView(Button(this).apply { text = label; setOnClickListener { action() } }) }
    private fun error(t: Throwable) { runOnUiThread { status.text = t.message ?: "통화 오류" } }
    private fun startOutgoing() {
        val target = intent.getStringExtra("target") ?: ""
        val purpose = intent.getStringExtra("purpose") ?: ""
        if (!target.matches(Regex("(npub1[023456789acdefghjklmnpqrstuvwxyz]{58}|[0-9a-fA-F]{64})")) ||
            purpose !in listOf("voice_call", "video_call")) {
            status.text = "통화할 이웃의 연락처를 확인해 주세요."; return
        }
        if (CallService.session != null || MediaSessionService.currentSessionId() != null) {
            status.text = "진행 중인 통화나 미디어 세션을 먼저 종료해 주세요."; return
        }
        video = purpose == "video_call"
        permissions { worker.execute { try {
            val s = CallSession.request("/media/sessions", JSONObject().put("kind", "call")
                .put("purpose", purpose).put("target", target)
                .put("request_id", java.util.UUID.randomUUID().toString())).getJSONObject("session")
            id = s.getString("session_id"); runOnUiThread { begin() }
        } catch (e: Exception) { error(e) } } }
    }
    override fun onSaveInstanceState(outState: Bundle) {
        outState.putString("session_id", id)
        super.onSaveInstanceState(outState)
    }
    private fun showSession() { worker.execute { try {
        val s = CallSession.request("/media/sessions/$id").getJSONObject("session")
        video = s.optString("purpose") == "video_call"
        runOnUiThread {
            if (s.optString("state") == "ended") { status.text = "종료: ${s.optString("end_reason")}"; return@runOnUiThread }
            if (s.optString("state") == "ringing") {
                status.text = "${if (video) "영상" else "음성"} 통화 수신"
                button("수락") { permissions { worker.execute { try {
                    CallSession.request("/media/sessions/$id/accept", JSONObject()); runOnUiThread { begin() }
                } catch (e: Exception) { error(e) } } } }
                button("거절") { worker.execute { try { CallSession.request("/media/sessions/$id/reject", JSONObject()) } finally { runOnUiThread { finish() } } } }
            } else permissions { begin() }
        }
    } catch (e: Exception) { error(e) } } }
    private fun permissions(action: () -> Unit) {
        val need = mutableListOf(Manifest.permission.RECORD_AUDIO)
        if (video) need.add(Manifest.permission.CAMERA)
        if (Build.VERSION.SDK_INT >= 33) need.add(Manifest.permission.POST_NOTIFICATIONS)
        val missing = need.filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
        if (missing.isEmpty()) action() else { pending = action; requestPermissions(missing.toTypedArray(), 21) }
    }
    override fun onRequestPermissionsResult(code: Int, permissions: Array<out String>, results: IntArray) {
        super.onRequestPermissionsResult(code, permissions, results)
        val action = pending; pending = null
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED &&
            (!video || checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED)) action?.invoke()
        else status.text = "통화하려면 마이크·카메라 권한을 허용해 주세요."
    }
    private fun begin() {
        if (CallService.session != null && CallService.session?.id != id) {
            status.text = "다른 통화가 진행 중입니다."; return
        }
        if (MediaSessionService.currentSessionId() != null) { status.text = "확장 장치 미디어 세션을 먼저 종료해 주세요."; return }
        root.removeAllViews(); root.addView(status)
        ContextCompat.startForegroundService(this, Intent(this, CallService::class.java).putExtra("session_id", id).putExtra("video", video))
        button("마이크 켜기/끄기") { muted = !muted; CallService.session?.engine?.setMuted(muted); status.text = if (muted) "마이크 꺼짐" else "마이크 켜짐" }
        if (video) {
            button("카메라 켜기/끄기") { cameraOff = !cameraOff; CallService.session?.engine?.setCameraEnabled(!cameraOff) }
            button("카메라 전환") { CallService.session?.engine?.switchCamera() }
        }
        button("스피커/수화기 전환") {
            val audio = getSystemService(AudioManager::class.java)
            @Suppress("DEPRECATION")
            audio.isSpeakerphoneOn = !audio.isSpeakerphoneOn
        }
        button("종료") { CallService.session?.close(); finish() }
        handler.post(refresh)
    }
    private val refresh = object : Runnable {
        override fun run() {
            val call = CallService.session
            if (call?.id == id) {
                status.text = when (call.state) { "active" -> "통화 중"; "reconnecting" -> "다시 연결 중"; "ended" -> "통화 종료"; else -> "연결 중" }
                val engine = call.engine
                if (engine != null && video && remote == null) {
                    remote = SurfaceViewRenderer(this@CallActivity).also { it.init(engine.eglContext, null); root.addView(it, LinearLayout.LayoutParams(-1, 0, 1f)) }
                    preview = SurfaceViewRenderer(this@CallActivity).also { it.init(engine.eglContext, null); it.setMirror(true); root.addView(it, LinearLayout.LayoutParams(-1, 220)) }
                }
                if (call.remoteVideo !== boundRemote && remote != null) { boundRemote?.removeSink(remote); boundRemote = call.remoteVideo; boundRemote?.addSink(remote) }
                if (call.localVideo !== boundLocal && preview != null) { boundLocal?.removeSink(preview); boundLocal = call.localVideo; boundLocal?.addSink(preview) }
            }
            handler.postDelayed(this, 500)
        }
    }
    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        boundRemote?.removeSink(remote); boundLocal?.removeSink(preview)
        remote?.release(); preview?.release(); worker.shutdown()
        super.onDestroy()
    }
    companion object {
        fun notifySession(ctx: Context, event: String, s: JSONObject) {
            if (s.optString("kind") != "call") return
            val id = s.getString("session_id")
            val nm = ctx.getSystemService(NotificationManager::class.java)
            if (s.optString("state") != "ringing") { nm.cancel(id, 1201); return }
            if (event != "ringing") return
            val channel = "media_incoming_calls"
            nm.createNotificationChannel(NotificationChannel(channel, "수신 통화", NotificationManager.IMPORTANCE_HIGH))
            val open = PendingIntent.getActivity(ctx, id.hashCode(), Intent(ctx, CallActivity::class.java).putExtra("session_id", id), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
            nm.notify(id, 1201, Notification.Builder(ctx, channel).setSmallIcon(android.R.drawable.sym_call_incoming)
                .setContentTitle("IndieBiz 통화 수신").setContentText("눌러서 수락하거나 거절하세요")
                .setCategory(Notification.CATEGORY_CALL).setContentIntent(open).setAutoCancel(true).setTimeoutAfter(45000).build())
        }
    }
}
