package com.indiebiz.phoneagent

import android.app.Activity
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.TextView

/** Wake only: never dismiss or enter a credential on the keyguard. */
class HardwareWakeActivity : Activity() {
    private val handler = Handler(Looper.getMainLooper())
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setShowWhenLocked(true)
        setTurnScreenOn(true)
        setContentView(TextView(this).apply {
            text = "원격 요청으로 화면을 켰습니다"
            gravity = android.view.Gravity.CENTER
        })
        handler.postDelayed({ finish() }, 2000)
    }
    override fun onDestroy() { handler.removeCallbacksAndMessages(null); super.onDestroy() }
}
