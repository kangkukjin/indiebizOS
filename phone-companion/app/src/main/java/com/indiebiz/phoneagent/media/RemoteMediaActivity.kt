package com.indiebiz.phoneagent.media

import android.app.Activity
import android.graphics.Color
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/** Visible, session-bound sensor screen above the still-locked keyguard. No launcher navigation. */
class RemoteMediaActivity : Activity() {
    private var ticket: RemoteStartTicket? = null
    private var resumed = false
    private val handler = Handler(Looper.getMainLooper())
    private val deadlineCheck = object : Runnable {
        override fun run() {
            val t = ticket ?: return
            if (!t.valid(SystemClock.elapsedRealtime())) { finish(); return }
            handler.postDelayed(this, 500)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val t = RemoteMediaStart.attach(this, intent.getStringExtra(RemoteMediaStart.EXTRA_TOKEN) ?: "")
        if (t == null) { finish(); return }
        ticket = t
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON or WindowManager.LayoutParams.FLAG_SECURE)
        window.attributes = window.attributes.apply { screenBrightness = 0.05f }
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            setPadding(48, 64, 48, 64); setBackgroundColor(Color.BLACK)
        }
        root.addView(TextView(this).apply {
            text = "등록된 PC의 카메라·마이크 연결\n\n연결 중에는 이 화면이 켜져 있습니다.\n종료하면 잠금 화면으로 돌아갑니다."
            textSize = 18f; setTextColor(Color.LTGRAY); gravity = Gravity.CENTER
        })
        root.addView(Button(this).apply { text = "연결 종료"; setOnClickListener { finish() } })
        setContentView(root)
        handler.post(deadlineCheck)
    }

    override fun onResume() {
        super.onResume()
        resumed = true
        markVisible()
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus) markVisible()
    }

    private fun markVisible() {
        // Waking from Samsung AOD can deliver resume→stop→resume before the screen has focus.
        // Only the actual visible screen releases the sensor startup waiter.
        handler.post {
            if (resumed && hasWindowFocus() && !isFinishing &&
                getSystemService(PowerManager::class.java).isInteractive) {
                if (ticket?.resume(SystemClock.elapsedRealtime()) != true) finish()
            }
        }
    }

    override fun onPause() {
        resumed = false
        super.onPause()
    }

    override fun onStop() {
        ticket?.let {
            if (it.resumed || isFinishing) {
                RemoteMediaStart.release(it.sessionId)
                MediaSessionService.stop(applicationContext, it.sessionId, "local_display_closed")
            }
        }
        super.onStop()
    }

    override fun onDestroy() {
        handler.removeCallbacks(deadlineCheck)
        ticket?.let { RemoteMediaStart.release(it.sessionId) }
        super.onDestroy()
    }
}
