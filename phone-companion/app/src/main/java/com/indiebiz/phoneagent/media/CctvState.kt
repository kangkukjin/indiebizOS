package com.indiebiz.phoneagent.media

import android.os.Build
import java.util.concurrent.atomic.AtomicInteger

/** Current visibility used by the central-request preparation path; not a persistent permission. */
object CctvState {
    // Compatibility with older hub status readers. There is no manually armed mode.
    const val armed = false
    private val visible = AtomicInteger(0)

    fun activityStarted() { visible.incrementAndGet() }
    fun activityStopped() { if (visible.decrementAndGet() < 0) visible.set(0) }
    fun appVisible(): Boolean = visible.get() > 0

    fun cameraReady(): Boolean = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q || appVisible()
    fun microphoneReady(): Boolean = Build.VERSION.SDK_INT < Build.VERSION_CODES.R || appVisible()
}
