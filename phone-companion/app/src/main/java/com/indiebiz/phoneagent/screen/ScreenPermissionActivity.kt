package com.indiebiz.phoneagent.screen

import android.app.Activity
import android.content.Intent
import android.media.projection.MediaProjectionConfig
import android.media.projection.MediaProjectionManager
import android.os.*
import androidx.core.content.ContextCompat

/** A new Android consent token for each session, never persisted or automatically accepted. */
class ScreenPermissionActivity : Activity() {
    private var session: ScreenSession? = null
    private val handler = Handler(Looper.getMainLooper())
    private val check = object : Runnable {
        override fun run() {
            if (session?.active != true) { finish(); return }
            handler.postDelayed(this, 500)
        }
    }
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val s = ScreenBridge.current?.takeIf { it.active && it.id == intent.getStringExtra("screen_id") }
        if (s == null || s.capturing || !s.needsProjectionConsent) { finish(); return }
        session = s
        if (savedInstanceState == null) {
            if (s.permissionRequested) { finish(); return }
            s.permissionRequested = true
            val manager = getSystemService(MediaProjectionManager::class.java)
            val request = if (Build.VERSION.SDK_INT >= 34)
                manager.createScreenCaptureIntent(MediaProjectionConfig.createConfigForDefaultDisplay())
            else manager.createScreenCaptureIntent()
            startActivityForResult(request, 1)
        }
        handler.post(check)
    }
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        super.onActivityResult(requestCode, resultCode, data)
        val s = session
        if (requestCode == 1 && s?.active == true) {
            if (resultCode == RESULT_OK && data != null) {
                try {
                    ContextCompat.startForegroundService(this, Intent(this, ScreenCaptureService::class.java)
                        .putExtra("screen_id", s.id).putExtra("result_code", resultCode).putExtra("capture_data", data))
                } catch (_: Exception) { s.end("capture_failed") }
            } else s.end("denied")
        }
        finish()
    }
    override fun onDestroy() { handler.removeCallbacks(check); super.onDestroy() }
}
