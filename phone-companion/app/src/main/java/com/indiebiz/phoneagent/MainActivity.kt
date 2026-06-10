package com.indiebiz.phoneagent

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/**
 * 진입 화면: 상주 서비스 시작 + 권한 안내(알림 접근/배터리 예외) + 테스트 DM.
 */
class MainActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        // 앱을 열면 상주 포그라운드 서비스 보장
        AgentForegroundService.start(this)

        val root = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            gravity = Gravity.CENTER
            setPadding(48, 48, 48, 48)
            setBackgroundColor(Color.WHITE)
        }

        root.addView(TextView(this).apply {
            text = "IndieBiz Phone Agent"
            textSize = 22f
            setTextColor(Color.BLACK)
            gravity = Gravity.CENTER
        })

        root.addView(TextView(this).apply {
            text = "\n① 알림 접근 허용  ② 배터리 최적화 제외\n둘 다 켜야 주머니 속에서도 상주합니다.\n"
            textSize = 15f
            setTextColor(Color.DKGRAY)
            gravity = Gravity.CENTER
        })

        root.addView(Button(this).apply {
            text = "① 알림 접근 권한 열기"
            setOnClickListener {
                startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
            }
        })

        root.addView(Button(this).apply {
            text = "② 배터리 최적화 제외 요청"
            setOnClickListener {
                val i = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS).apply {
                    data = Uri.parse("package:$packageName")
                }
                try { startActivity(i) } catch (_: Exception) {
                    startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
                }
            }
        })

        root.addView(Button(this).apply {
            text = "테스트 DM 전송 (indiebizOS)"
            setOnClickListener {
                val pub = NostrCrypto.toHex(
                    NostrCrypto.xonlyPub(NostrCrypto.fromHex(Sender.phonePrivHex(this@MainActivity))))
                Sender.sendAsync(
                    this@MainActivity,
                    "{\"type\":\"test\",\"msg\":\"phone-agent tracer bullet\",\"from\":\"$pub\"}")
            }
        })

        setContentView(root)
    }
}
