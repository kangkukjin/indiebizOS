package com.indiebiz.phoneagent

import android.app.Activity
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/**
 * 게이트 화면 — 다른 앱처럼:
 *  - 설정(알림 접근/배터리 예외)이 끝났으면 곧장 런처(LauncherActivity)로 자동 진입.
 *  - 미설정이면 "초기 설정" 화면을 보여주고, 허용하고 돌아오면 자동으로 런처로 넘어감.
 * 백엔드 생명주기는 App(Application)이 관리(포그라운드 동안 실행).
 */
class MainActivity : Activity() {

    private fun notifAccessGranted(): Boolean {
        val flat = Settings.Secure.getString(contentResolver, "enabled_notification_listeners") ?: return false
        return flat.split(":").any { it.contains(packageName) }
    }

    private fun batteryExempt(): Boolean {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        return pm.isIgnoringBatteryOptimizations(packageName)
    }

    private fun allReady() = notifAccessGranted() && batteryExempt()

    override fun onResume() {
        super.onResume()
        if (isFinishing) return
        if (allReady()) {
            // 설정 끝 → 런처 자동 진입(버튼 불필요), 게이트는 닫는다.
            startActivity(Intent(this, LauncherActivity::class.java))
            finish()
        } else {
            renderSetup()
        }
    }

    private fun renderSetup() {
        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(56, 64, 56, 64)
            setBackgroundColor(Color.WHITE)
        }

        root.addView(TextView(this).apply {
            text = "IndieBiz Phone Agent"
            textSize = 22f
            setTextColor(Color.BLACK)
            gravity = Gravity.CENTER
        })

        root.addView(TextView(this).apply {
            text = "\n시작하려면 두 가지만 한 번 켜주세요.\n주머니 속에서도 알림을 받고 상주합니다.\n"
            textSize = 15f
            setTextColor(Color.DKGRAY)
            gravity = Gravity.CENTER
        })

        if (!notifAccessGranted()) {
            root.addView(Button(this).apply {
                text = "① 알림 접근 허용"
                textSize = 16f
                setOnClickListener {
                    startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
                }
            })
        }
        if (!batteryExempt()) {
            root.addView(Button(this).apply {
                text = "② 배터리 최적화 제외"
                textSize = 16f
                setOnClickListener {
                    val i = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                        data = Uri.parse("package:$packageName")
                    }
                    try { startActivity(i) } catch (_: Exception) {
                        startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                    }
                }
            })
        }

        root.addView(TextView(this).apply {
            text = "\n둘 다 켜면 자동으로 런처가 열립니다."
            textSize = 13f
            setTextColor(Color.parseColor("#2E7D32"))
            gravity = Gravity.CENTER
        })

        setContentView(root)
    }
}
