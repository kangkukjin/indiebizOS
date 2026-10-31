package com.indiebiz.phoneagent.screen

import android.app.*
import android.content.*
import android.os.*
import android.provider.Settings
import android.util.Log
import com.indiebiz.phoneagent.PhoneAccessibilityService
import okhttp3.*
import okio.ByteString.Companion.toByteString
import org.json.JSONObject
import java.io.File
import java.util.concurrent.*
import java.util.concurrent.atomic.AtomicBoolean

/** Same authenticated, ephemeral JPEG/input socket as the PC helper. No capture data on disk. */
object ScreenBridge {
    lateinit var context: Context
    @Volatile var current: ScreenSession? = null
        private set
    const val CHANNEL = "remote_screen"
    const val NOTICE = 1010
    @JvmStatic fun init(ctx: Context) { context = ctx.applicationContext }
    @JvmStatic fun capabilities(): String {
        val service = PhoneAccessibilityService.instance
        val unattended = Build.VERSION.SDK_INT >= 30
        return JSONObject().put("capture", if (unattended) "accessibility" else "media_projection")
            .put("unattended", unattended).put("accessibility_enabled", service != null)
            .put("capture_ready", service != null && unattended && AccessibilityScreenCapture.permitted(service))
            .put("reconnect", 1).put("session_consent_required", !unattended).toString()
    }
    @JvmStatic fun run(id: String): String {
        require(Regex("[a-f0-9]{32}").matches(id))
        val session = synchronized(this) {
            check(current == null) { "screen_busy" }
            ScreenSession(id, context).also { current = it }
        }
        try {
            session.connect()
            val start = SystemClock.elapsedRealtime()
            while (!session.done.await(1, TimeUnit.SECONDS)) {
                val now = SystemClock.elapsedRealtime()
                if (ScreenSessionPolicy.heartbeatExpired(now, session.lastMessage)) session.recover()
                if (now - start > 86400000 ||
                    (!session.capturing && now - start > 120000)) session.end("denied")
            }
            return JSONObject().put("success", session.error == null).apply {
                session.error?.let { put("error", it) }
            }.toString()
        } finally {
            session.end()
            if (session.capture != null) session.captureReleased.await(5, TimeUnit.SECONDS)
            synchronized(this) { if (current === session) current = null }
        }
    }
    @JvmStatic fun stop(id: String) { current?.takeIf { it.id == id }?.end() }

    fun notification(ctx: Context, id: String, running: Boolean): Notification {
        val manager = ctx.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "화면 공유", NotificationManager.IMPORTANCE_DEFAULT))
        val open = PendingIntent.getActivity(ctx, 0, Intent(ctx, ScreenPermissionActivity::class.java)
            .putExtra("screen_id", id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(ctx, 1, Intent(ctx, ScreenCaptureService::class.java)
            .setAction("stop").putExtra("screen_id", id), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        return Notification.Builder(ctx, CHANNEL).setSmallIcon(android.R.drawable.ic_menu_view)
            .setContentTitle("IndieBiz 화면 공유")
            .setContentText(if (running) "중앙 PC에서 이 폰을 보고 조작 중입니다" else "눌러서 중앙 PC의 화면 공유 요청을 승인하세요")
            .setContentIntent(open).setOngoing(true)
            .addAction(Notification.Action.Builder(null, "종료", stop).build()).build()
    }
}

class ScreenSession(val id: String, private val ctx: Context) : WebSocketListener() {
    val done = CountDownLatch(1)
    val captureReleased = CountDownLatch(1)
    private val ended = AtomicBoolean()
    private val client = ScreenSessionPolicy.client()
    private val inputs = ThreadPoolExecutor(1, 1, 0, TimeUnit.SECONDS, ArrayBlockingQueue(256))
    private val input = ScreenInput()
    @Volatile var lastMessage = SystemClock.elapsedRealtime()
    @Volatile var capturing = false
    @Volatile var permissionRequested = false
    val needsProjectionConsent get() = Build.VERSION.SDK_INT < 30
    @Volatile var error: String? = null
    @Volatile var capture: ScreenCaptureService? = null
    private var accessibilityCapture: AccessibilityScreenCapture? = null
    @Volatile private var socket: WebSocket? = null
    private lateinit var auth: JSONObject
    @Volatile private var connected = false
    @Volatile private var reconnectMs = 0L
    @Volatile private var reconnectUntil = 0L
    private var generation = 0
    private val handler = Handler(Looper.getMainLooper())
    @Volatile var frameWidth = 1280
        private set
    @Volatile var jpegQuality = 65
        private set
    @Volatile var frameInterval = 400L
        private set
    private var stable = 0
    private var previousFrame: ByteArray? = null
    private var lastFrameSent = 0L
    val transmitting get() = active && connected

    val active get() = !ended.get()

    @Synchronized fun connect() {
        if (!active) return
        if (reconnectUntil != 0L && SystemClock.elapsedRealtime() >= reconnectUntil) { end("capture_failed"); return }
        // Installed trust root, never a command-supplied destination or credential.
        val cfg = JSONObject(File(ctx.filesDir, "secrets/limb_client.json").readText())
        val hub = cfg.getString("hub").trimEnd('/')
        require(hub.startsWith("https://") || hub.startsWith("http://"))
        auth = JSONObject().put("key", cfg.getString("key")).put("installation_id", cfg.getString("installation_id")).put("connection", ++generation)
        val url = hub.replaceFirst("https://", "wss://").replaceFirst("http://", "ws://") + "/limb/resident/screen/$id"
        socket = client.newWebSocket(Request.Builder().url(url).build(), this)
    }
    override fun onOpen(ws: WebSocket, response: Response) {
        if (!active || ws !== socket) { ws.cancel(); return }
        ws.send(auth.toString())
    }
    override fun onMessage(ws: WebSocket, text: String) {
        if (!active || ws !== socket) return
        lastMessage = SystemClock.elapsedRealtime()
        try {
            val message = JSONObject(text)
            when (message.getString("type")) {
                "ready" -> {
                    reconnectMs = (message.optDouble("reconnect_s", 0.0) * 1000).toLong()
                    reconnectUntil = 0L
                    connected = true
                    previousFrame = null

                    Handler(Looper.getMainLooper()).post {
                        if (!active) return@post
                        if (PhoneAccessibilityService.instance == null) { end("accessibility"); return@post }
                        if (!needsProjectionConsent) {
                            if (accessibilityCapture == null) {
                                ctx.getSystemService(NotificationManager::class.java).notify(ScreenBridge.NOTICE, ScreenBridge.notification(ctx, id, true))
                                accessibilityCapture = AccessibilityScreenCapture(this, ctx).also { it.start() }
                            }
                            return@post
                        }
                        if (capturing || permissionRequested) return@post
                        status("permission")
                        ctx.getSystemService(NotificationManager::class.java).notify(ScreenBridge.NOTICE, ScreenBridge.notification(ctx, id, false))
                        // Background activity restrictions start at Android 10. On Android 9,
                        // requiring an overlay grant strands every reconnect at the notification.
                        if (ScreenSessionPolicy.canOpenConsent(Build.VERSION.SDK_INT, Settings.canDrawOverlays(ctx))) {
                            try { ctx.startActivity(Intent(ctx, ScreenPermissionActivity::class.java)
                                .putExtra("screen_id", id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS)) }
                            catch (_: Exception) { /* notification remains the user entry point */ }
                        }
                    }
                }
                "heartbeat" -> Unit
                "close" -> end()
                else -> if (capturing && connected) inputs.execute {
                    if (active && connected && ws === socket) try { input.handle(message) } catch (_: Exception) { end("input_failed") }
                }
            }
        } catch (_: Exception) { end("input_failed") }
    }
    @Synchronized fun frame(jpeg: ByteArray, width: Int, height: Int) {
        if (!transmitting) return
        input.width = width; input.height = height
        val ws = socket ?: return
        val queued = ws.queueSize()
        if (queued > 128 * 1024) {
            stable = 0; frameWidth = 800; jpegQuality = 40; frameInterval = 800L
        } else if (++stable >= 30) {
            frameWidth = 1280; jpegQuality = 65; frameInterval = 400L; stable = 0
        }
        val now = SystemClock.elapsedRealtime()
        if (queued >= 512 * 1024 || (previousFrame?.contentEquals(jpeg) == true && now - lastFrameSent < 2000)) return
        if (ws.send(jpeg.toByteString())) { previousFrame = jpeg; lastFrameSent = now }
    }
    private fun status(code: String) { socket?.send(JSONObject().put("code", code).toString()) }
    @Synchronized fun recover() {
        if (!active) return
        val now = SystemClock.elapsedRealtime()
        if (reconnectMs <= 0 || (reconnectUntil != 0L && now >= reconnectUntil)) { end("capture_failed"); return }
        if (!connected && reconnectUntil != 0L) return
        connected = false
        reconnectUntil = now + reconnectMs
        socket?.cancel(); socket = null
        inputs.queue.clear()
        try { inputs.execute { try { input.handle(JSONObject().put("type", "reset")) } catch (_: Exception) {} } } catch (_: RejectedExecutionException) {}
        handler.postDelayed({ connect() }, 500)
    }
    override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
        if (!active || ws !== socket) return
        Log.w("IndieBizScreen", "screen transport interrupted")
        interrupted(ws)
    }
    @Synchronized private fun interrupted(ws: WebSocket) {
        if (!active || ws !== socket) return
        if (!connected && reconnectUntil != 0L) {
            socket = null
            ws.cancel()
            handler.postDelayed({ connect() }, 500)
        } else recover()
    }
    override fun onClosing(ws: WebSocket, code: Int, reason: String) {
        if (!active || ws !== socket) return
        if (code == 1008) end("denied") else interrupted(ws)
    }
    override fun onClosed(ws: WebSocket, code: Int, reason: String) {
        interrupted(ws)
    }
    fun end(code: String? = null) {
        if (!ended.compareAndSet(false, true)) return
        error = code
        status(code ?: "denied")
        connected = false
        handler.removeCallbacksAndMessages(null)
        socket?.close(1000, "screen ended")
        inputs.shutdownNow()
        Handler(Looper.getMainLooper()).post {
            accessibilityCapture?.close()
            accessibilityCapture = null
            capture?.stopSelf()
            ctx.getSystemService(NotificationManager::class.java).cancel(ScreenBridge.NOTICE)
        }
        client.dispatcher.executorService.shutdown()
        client.connectionPool.evictAll()
        done.countDown()
    }
}
