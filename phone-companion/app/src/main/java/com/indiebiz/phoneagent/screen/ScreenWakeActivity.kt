package com.indiebiz.phoneagent.screen

import android.app.Activity
import android.app.KeyguardManager
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.view.Gravity
import android.view.WindowManager
import android.widget.TextView
import android.widget.Button
import android.widget.LinearLayout

/** Samsung may immediately sleep again when a wake-only activity finishes. Keep the
 * requesting window alive while Android presents its own credential screen instead.
 * requestDismissKeyguard never bypasses a secure PIN/pattern; Android verifies it.
 */
class ScreenWakeActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    private var session: ScreenSession? = null
    private var requested = false
    private val timeout = Runnable {
        if (!getSystemService(PowerManager::class.java).isInteractive) {
            session?.end("wake_failed")
            finish()
        }
    }
    private val checkSession = object : Runnable {
        override fun run() {
            if (session?.active != true) { finish(); return }
            handler.postDelayed(this, 250)
        }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        session = ScreenBridge.current?.takeIf { it.active && it.id == intent.getStringExtra("screen_id") }
        if (session == null) { finish(); return }
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER
            setBackgroundColor(0xff141820.toInt())
            addView(TextView(this@ScreenWakeActivity).apply {
                text = "PC의 원격 화면에서 이 폰의 잠금을 해제하세요"
                gravity = Gravity.CENTER; setTextColor(0xffffffff.toInt())
            })
            addView(Button(this@ScreenWakeActivity).apply {
                text = "잠금 화면 열기"; setOnClickListener { requestUnlock() }
            })
        })
        handler.postDelayed(timeout, 5000)
        handler.post(checkSession)
    }

    override fun onWindowFocusChanged(hasFocus: Boolean) {
        super.onWindowFocusChanged(hasFocus)
        if (hasFocus && !requested && getSystemService(PowerManager::class.java).isInteractive) {
            requested = true
            handler.post { requestUnlock() }
        }
    }

    private fun requestUnlock() {
        if (session?.active != true || isFinishing) { finish(); return }
        val keyguard = getSystemService(KeyguardManager::class.java)
        if (!keyguard.isKeyguardLocked) { finish(); return }
        keyguard.requestDismissKeyguard(this, object : KeyguardManager.KeyguardDismissCallback() {
            override fun onDismissSucceeded() { finish() }
            // Cancel/error leaves the explicit retry button, never a repeated credential prompt.
        })
    }

    override fun onDestroy() {
        handler.removeCallbacksAndMessages(null)
        super.onDestroy()
    }
}
