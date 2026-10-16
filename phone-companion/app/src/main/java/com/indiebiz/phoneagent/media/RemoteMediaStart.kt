package com.indiebiz.phoneagent.media

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.provider.Settings
import java.io.File
import java.lang.ref.WeakReference
import java.util.UUID
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import org.json.JSONObject

/** One bounded attempt. Late activity/service delivery cannot revive a cancelled request. */
internal class RemoteStartTicket(val sessionId: String, val token: String, val deadline: Long) {
    val ready = CountDownLatch(1)
    @Volatile var resumed = false
        private set
    @Volatile var committed = false
        private set
    @Volatile var cancelled = false
        private set
    var activity: WeakReference<Activity>? = null

    @Synchronized fun valid(now: Long) = !cancelled && (committed || now < deadline)
    @Synchronized fun resume(now: Long): Boolean {
        if (!valid(now)) return false
        resumed = true
        ready.countDown()
        return true
    }
    @Synchronized fun commit(now: Long): Boolean {
        if (!resumed || !valid(now)) return false
        committed = true
        return true
    }
    @Synchronized fun cancel() { cancelled = true; resumed = false; ready.countDown() }
}

/** Registered owner requests may show a dedicated sensor screen using an explicit OS permission.
 * This never dismisses the keyguard and never grants camera/microphone permission itself.
 */
internal object RemoteMediaStart {
    const val EXTRA_TOKEN = "remote_media_start_token"
    private val main = Handler(Looper.getMainLooper())
    @Volatile private var current: RemoteStartTicket? = null

    private fun registration(ctx: Context): JSONObject? = try {
        JSONObject(File(ctx.filesDir, "secrets/limb_client.json").readText())
    } catch (_: Exception) { null }

    fun available(ctx: Context): Boolean = Settings.canDrawOverlays(ctx) && registration(ctx) != null

    private fun authorized(ctx: Context, env: MediaEnvelope): Boolean {
        val cfg = registration(ctx) ?: return false
        return Settings.canDrawOverlays(ctx) && env.localRole == "device" && env.authKey.isNotEmpty()
            && cfg.optString("key") == env.authKey && cfg.optString("installation_id") == env.installationId
    }

    fun prepare(ctx: Context, env: MediaEnvelope): RemoteStartTicket? {
        if (Looper.myLooper() == Looper.getMainLooper() || !authorized(ctx, env)) return null
        val ticket = RemoteStartTicket(env.sessionId, UUID.randomUUID().toString(), SystemClock.elapsedRealtime() + 5000)
        synchronized(this) {
            if (current != null) return null
            current = ticket
        }
        main.post {
            if (current !== ticket || !ticket.valid(SystemClock.elapsedRealtime())) return@post
            try {
                ctx.startActivity(Intent(ctx, RemoteMediaActivity::class.java)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS)
                    .putExtra(EXTRA_TOKEN, ticket.token))
            } catch (_: Exception) { release(ticket.sessionId) }
        }
        try { ticket.ready.await(5, TimeUnit.SECONDS) } catch (_: InterruptedException) {
            Thread.currentThread().interrupt()
        }
        if (current === ticket && ticket.resumed && ticket.valid(SystemClock.elapsedRealtime())) return ticket
        release(ticket.sessionId)
        return null
    }

    @Synchronized fun attach(activity: Activity, token: String): RemoteStartTicket? {
        val ticket = current ?: return null
        if (ticket.token != token || !ticket.valid(SystemClock.elapsedRealtime())) return null
        ticket.activity = WeakReference(activity)
        return ticket
    }

    fun ready(sessionId: String, token: String): Boolean {
        val ticket = current ?: return false
        return ticket.sessionId == sessionId && ticket.token == token && ticket.resumed
            && ticket.valid(SystemClock.elapsedRealtime())
    }

    fun commit(ticket: RemoteStartTicket): Boolean = current === ticket && ticket.commit(SystemClock.elapsedRealtime())

    fun release(sessionId: String?): Boolean {
        val ticket = synchronized(this) {
            current?.takeIf { sessionId == null || it.sessionId == sessionId }?.also { current = null; it.cancel() }
        } ?: return false
        main.post { ticket.activity?.get()?.finish() }
        return true
    }
}
