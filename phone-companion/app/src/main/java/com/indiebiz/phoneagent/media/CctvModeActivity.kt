package com.indiebiz.phoneagent.media

import android.Manifest
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.view.Gravity
import android.view.WindowManager
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicInteger

/**
 * 센서 준비 상태(앱 가시성) — Android 11+ 는 백그라운드에서 시작한 포그라운드 서비스에
 * 카메라·마이크 접근을 막는다(while-in-use). 이 상태는 "지금 허브의 start 가 센서를 열 수 있는가"
 * 의 정직한 판정 근거이지, 나중의 백그라운드 접근을 보장하는 설정 저장이 아니다(설계 §9).
 */
object CctvState {
    @Volatile var armed: Boolean = false            // 카메라 대기 모드 화면이 떠 있다
        private set
    private val visible = AtomicInteger(0)           // 떠 있는 액티비티 수(App 생명주기 콜백)

    fun setArmed(on: Boolean) { armed = on }
    fun activityStarted() { visible.incrementAndGet() }
    fun activityStopped() { if (visible.decrementAndGet() < 0) visible.set(0) }
    fun appVisible(): Boolean = visible.get() > 0

    /** 카메라 FGS 를 지금 열 수 있는가 — Android 10 미만(J7·Android 9)은 백그라운드 카메라 허용. */
    fun cameraReady(): Boolean = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q || armed || appVisible()
    /** 마이크 FGS — Android 11 부터 백그라운드 시작 제한. */
    fun microphoneReady(): Boolean = Build.VERSION.SDK_INT < Build.VERSION_CODES.R || armed || appVisible()
}

/**
 * '카메라 대기 모드' — 사용자가 폰에서 직접 켜 두는 화면. 켜져 있는 동안:
 *  - 화면을 어둡게 켜 둔 채(FLAG_KEEP_SCREEN_ON + 최저 밝기) 앱을 가시 상태로 유지 → 허브의
 *    카메라/마이크 세션 start 가 사용자 손 없이 성공한다.
 *  - 부분 WakeLock 으로 CPU 를 깨워 둔다(세션 서비스가 돌 때도 같은 락을 따로 쥔다).
 * 화면을 끄거나 이 화면을 떠나면 대기가 풀린다 — 그때의 start 는 needs_local_action 으로 정직하게 돌아간다.
 */
class CctvModeActivity : Activity() {
    private var wakeLock: PowerManager.WakeLock? = null
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var status: TextView
    private val ticker = object : Runnable {
        override fun run() { refresh(); handler.postDelayed(this, 2000) }
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        window.attributes = window.attributes.apply { screenBrightness = 0.05f }

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(48, 64, 48, 64)
            setBackgroundColor(Color.BLACK)
        }
        root.addView(TextView(this).apply {
            text = "카메라 대기 모드"
            textSize = 20f; setTextColor(Color.LTGRAY); gravity = Gravity.CENTER
        })
        root.addView(TextView(this).apply {
            text = "\n이 화면이 떠 있는 동안 중앙 PC 가 이 폰의 카메라·마이크 세션을 열 수 있습니다.\n" +
                "화면을 끄거나 나가면 대기가 풀립니다.\n"
            textSize = 13f; setTextColor(Color.GRAY); gravity = Gravity.CENTER
        })
        status = TextView(this).apply { textSize = 12f; setTextColor(Color.DKGRAY); gravity = Gravity.CENTER }
        root.addView(status)
        root.addView(Button(this).apply {
            text = "카메라·마이크 권한 요청"
            setOnClickListener { requestSensorPermissions() }
        })
        root.addView(Button(this).apply {
            text = "대기 끝내기"
            setOnClickListener { finish() }
        })
        setContentView(root)
        if (!hasPermission(Manifest.permission.CAMERA) || !hasPermission(Manifest.permission.RECORD_AUDIO)) {
            requestSensorPermissions()
        }
    }

    private fun hasPermission(p: String) = checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED

    private fun requestSensorPermissions() {
        val need = listOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO).filter { !hasPermission(it) }
        if (need.isNotEmpty()) requestPermissions(need.toTypedArray(), 7001)
    }

    override fun onStart() {
        super.onStart()
        CctvState.setArmed(true)
        try {
            val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "indiebiz:cctv").apply { acquire() }
        } catch (_: Throwable) {}
        handler.post(ticker)
    }

    override fun onStop() {
        handler.removeCallbacks(ticker)
        CctvState.setArmed(false)
        try { wakeLock?.let { if (it.isHeld) it.release() } } catch (_: Throwable) {}
        wakeLock = null
        super.onStop()
    }

    private fun refresh() {
        val st = try { JSONObject(MediaBridge.status()) } catch (_: Throwable) { JSONObject() }
        val sid = st.optString("session_id")
        val line = if (sid.isEmpty()) "세션 없음 — 대기 중" else
            "세션 ${sid.take(8)}… ${st.optString("purpose")} ${st.optString("state")} 경로=${st.optString("path", "-")}"
        val perm = "권한: 카메라=${hasPermission(Manifest.permission.CAMERA)} 마이크=${hasPermission(Manifest.permission.RECORD_AUDIO)}"
        status.text = "$perm\n$line"
    }

    companion object {
        fun launch(ctx: Context) {
            ctx.startActivity(Intent(ctx, CctvModeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
        }
    }
}
