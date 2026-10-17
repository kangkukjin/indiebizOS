package com.indiebiz.phoneagent.screen

import android.app.*
import android.content.*
import android.os.*
import android.provider.Settings
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
            .put("session_consent_required", !unattended).toString()
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
                if (now - session.lastMessage > 20000 || now - start > 86400000 ||
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
    private val client = OkHttpClient.Builder().pingInterval(5, TimeUnit.SECONDS).build()
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
    val active get() = !ended.get()

    fun connect() {
        // Installed trust root, never a command-supplied destination or credential.
        val cfg = JSONObject(File(ctx.filesDir, "secrets/limb_client.json").readText())
        val hub = cfg.getString("hub").trimEnd('/')
        require(hub.startsWith("https://") || hub.startsWith("http://"))
        auth = JSONObject().put("key", cfg.getString("key")).put("installation_id", cfg.getString("installation_id"))
        val url = hub.replaceFirst("https://", "wss://").replaceFirst("http://", "ws://") + "/limb/resident/screen/$id"
        socket = client.newWebSocket(Request.Builder().url(url).build(), this)
    }
    override fun onOpen(ws: WebSocket, response: Response) {
        if (!active) { ws.cancel(); return }
        ws.send(auth.toString())
    }
    override fun onMessage(ws: WebSocket, text: String) {
        if (!active) return
        lastMessage = SystemClock.elapsedRealtime()
        try {
            val message = JSONObject(text)
            when (message.getString("type")) {
                "ready" -> {
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
                        status("permission")
                        ctx.getSystemService(NotificationManager::class.java).notify(ScreenBridge.NOTICE, ScreenBridge.notification(ctx, id, false))
                        if (Settings.canDrawOverlays(ctx)) {
                            try { ctx.startActivity(Intent(ctx, ScreenPermissionActivity::class.java)
                                .putExtra("screen_id", id).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS)) }
                            catch (_: Exception) { /* notification remains the user entry point */ }
                        }
                    }
                }
                "heartbeat" -> Unit
                "close" -> end()
                else -> if (capturing) inputs.execute {
                    if (active) try { input.handle(message) } catch (_: Exception) { end("input_failed") }
                }
            }
        } catch (_: Exception) { end("input_failed") }
    }
    fun frame(jpeg: ByteArray, width: Int, height: Int) {
        if (!active) return
        input.width = width; input.height = height
        val ws = socket ?: return
        if (ws.queueSize() < 512 * 1024) ws.send(jpeg.toByteString())
    }
    private fun status(code: String) { socket?.send(JSONObject().put("code", code).toString()) }
    override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) { end("capture_failed") }
    override fun onClosing(ws: WebSocket, code: Int, reason: String) { end() }
    override fun onClosed(ws: WebSocket, code: Int, reason: String) { end() }
    fun end(code: String? = null) {
        if (!ended.compareAndSet(false, true)) return
        error = code
        if (code != null) status(code)
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
