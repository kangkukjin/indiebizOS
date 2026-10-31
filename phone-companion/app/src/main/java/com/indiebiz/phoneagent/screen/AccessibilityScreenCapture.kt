package com.indiebiz.phoneagent.screen

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.app.KeyguardManager
import android.content.Context
import android.content.Intent
import android.graphics.Bitmap
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.view.Display
import com.indiebiz.phoneagent.PhoneAccessibilityService
import java.io.ByteArrayOutputStream
import java.util.concurrent.Executors
import kotlin.math.roundToInt

/** Android 11+: the enabled accessibility grant owns capture, not a projection token.
 * One screenshot at a time; even a callback arriving after close releases its buffer.
 * Screen pixels never leave the authenticated ScreenSession or enter storage.
 */
internal class AccessibilityScreenCapture(private val session: ScreenSession, private val ctx: Context) {
    private val handler = Handler(Looper.getMainLooper())
    @Volatile private var closed = false
    private var failures = 0
    private var screenAwake = false
    private var wake: PowerManager.WakeLock? = null
    private val next = Runnable { capture() }

    fun start() {
        check(Build.VERSION.SDK_INT >= 30)
        if (!session.active) return
        if (!session.transmitting) { schedule(); return }
        val service = PhoneAccessibilityService.instance
        if (service == null) { session.end("accessibility"); return }
        if (!permitted(service)) { session.end("capture_permission"); return }
        // Session-scoped only. Wake the display without dismissing its keyguard or changing settings.
        @Suppress("DEPRECATION")
        try {
            wake = ctx.getSystemService(PowerManager::class.java).newWakeLock(
                PowerManager.SCREEN_BRIGHT_WAKE_LOCK or PowerManager.ACQUIRE_CAUSES_WAKEUP,
                "IndieBiz:remote-screen"
            ).apply { setReferenceCounted(false); acquire(86400000L) }
        } catch (_: SecurityException) { /* Capture reports the actual display state below. */ }
        if (!ctx.getSystemService(PowerManager::class.java).isInteractive) {
            try {
                service.startActivity(Intent(service, ScreenWakeActivity::class.java)
                    .putExtra("screen_id", session.id)
                    .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_EXCLUDE_FROM_RECENTS))
            } catch (_: Exception) { session.end("wake_failed"); return }
        }
        handler.postDelayed(next, 350)
    }

    private fun capture() {
        if (closed || !session.active) return
        if (ctx.getSystemService(PowerManager::class.java).isInteractive) screenAwake = true
        else if (screenAwake) { session.end("screen_sleep"); return }
        if (!session.transmitting) { schedule(); return }
        val service = PhoneAccessibilityService.instance
        if (service == null) { session.end("accessibility"); return }
        try {
            service.takeScreenshot(Display.DEFAULT_DISPLAY, encoder, object : AccessibilityService.TakeScreenshotCallback {
                override fun onSuccess(result: AccessibilityService.ScreenshotResult) {
                    val buffer = result.hardwareBuffer
                    try {
                        if (closed || !session.active) return
                        val hardware = Bitmap.wrapHardwareBuffer(buffer, result.colorSpace) ?: error("empty screenshot")
                        try {
                            var software = hardware.copy(Bitmap.Config.ARGB_8888, false) ?: error("empty bitmap")
                            try {
                                if (ctx.getSystemService(KeyguardManager::class.java).isKeyguardLocked && LockScreenPreview.isBlack(software)) {
                                    val controls = LockScreenPreview.render(service, software.width, software.height)
                                    software.recycle()
                                    software = controls
                                }
                                val scale = minOf(1.0, session.frameWidth.toDouble() / maxOf(software.width, software.height))
                                val frame = Bitmap.createScaledBitmap(software,
                                    (software.width * scale).roundToInt().coerceAtLeast(1),
                                    (software.height * scale).roundToInt().coerceAtLeast(1), true)
                                try {
                                    val bytes = ByteArrayOutputStream()
                                    check(frame.compress(Bitmap.CompressFormat.JPEG, session.jpegQuality, bytes))
                                    if (!closed && session.active) {
                                        session.capturing = true
                                        session.frame(bytes.toByteArray(), software.width, software.height)
                                    }
                                } finally { if (frame !== software) frame.recycle() }
                            } finally { software.recycle() }
                        } finally { hardware.recycle() }
                        handler.post { failures = 0; schedule() }
                    } catch (_: Exception) {
                        handler.post { failed(AccessibilityService.ERROR_TAKE_SCREENSHOT_INTERNAL_ERROR) }
                    } finally { buffer.close() }
                }
                override fun onFailure(errorCode: Int) { handler.post { failed(errorCode) } }
            })
        } catch (_: SecurityException) { session.end("capture_permission") }
        catch (_: Exception) { failed(AccessibilityService.ERROR_TAKE_SCREENSHOT_INTERNAL_ERROR) }
    }

    private fun schedule() {
        if (!closed && session.active) handler.postDelayed(next, session.frameInterval)
    }

    private fun failed(code: Int) {
        if (closed || !session.active) return
        when (code) {
            AccessibilityService.ERROR_TAKE_SCREENSHOT_NO_ACCESSIBILITY_ACCESS -> session.end("capture_permission")
            AccessibilityService.ERROR_TAKE_SCREENSHOT_SECURE_WINDOW -> session.end("secure_screen")
            else -> {
                // Transient rotation / screen wake / OS rate limiting must not demand a new grant.
                if (++failures >= 5) session.end("capture_failed") else schedule()
            }
        }
    }

    fun close() {
        closed = true
        handler.removeCallbacksAndMessages(null)
        wake?.let { if (it.isHeld) it.release() }
        wake = null
    }

    companion object {
        // Late callbacks must still run to close HardwareBuffer. A process-owned daemon never
        // rejects them after a session ends; only one active screen session can submit work.
        private val encoder = Executors.newSingleThreadExecutor { task -> Thread(task, "accessibility-screen").apply { isDaemon = true } }
        fun permitted(service: AccessibilityService): Boolean = Build.VERSION.SDK_INT >= 30 &&
            service.serviceInfo.capabilities and AccessibilityServiceInfo.CAPABILITY_CAN_TAKE_SCREENSHOT != 0
    }
}
