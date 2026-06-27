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

    private fun batteryExempt(): Boolean {
        val pm = getSystemService(Context.POWER_SERVICE) as PowerManager
        return pm.isIgnoringBatteryOptimizations(packageName)
    }

    // 알림 캡처(NotificationListener)는 제거됨(2026-06-22) — 폰 알림 수집/중계 폐기.
    // 상주 준비 게이트는 배터리 최적화 제외만으로 충분.
    private fun allReady() = batteryExempt()

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
            text = "\n시작하려면 한 가지만 한 번 켜주세요.\n주머니 속에서도 백그라운드로 상주합니다.\n"
            textSize = 15f
            setTextColor(Color.DKGRAY)
            gravity = Gravity.CENTER
        })

        if (!batteryExempt()) {
            root.addView(Button(this).apply {
                text = "배터리 최적화 제외"
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
            text = "\n켜면 자동으로 런처가 열립니다."
            textSize = 13f
            setTextColor(Color.parseColor("#2E7D32"))
            gravity = Gravity.CENTER
        })

        setContentView(root)
    }
}
