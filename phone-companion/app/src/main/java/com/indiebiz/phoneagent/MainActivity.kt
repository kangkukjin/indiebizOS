package com.indiebiz.phoneagent

import android.app.Activity
import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.os.Build
import android.os.PowerManager
import android.provider.Settings
import android.view.Gravity
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import java.io.File

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

    private fun registeredDevice() = File(filesDir, "secrets/limb_client.json").isFile
    private fun missingSensors() = listOf(Manifest.permission.CAMERA, Manifest.permission.RECORD_AUDIO)
        .filter { checkSelfPermission(it) != PackageManager.PERMISSION_GRANTED }
    private fun remoteScreenReady() = Build.VERSION.SDK_INT < Build.VERSION_CODES.Q || Settings.canDrawOverlays(this)
    private fun allReady() = batteryExempt() &&
        (!registeredDevice() || (missingSensors().isEmpty() && remoteScreenReady()))

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
            text = if (registeredDevice()) "\n원격 장치 최초 설정\n권한을 허용하면 중앙 PC 요청에 따라 자동으로 준비하고 실행합니다.\n"
                else "\n배터리 최적화 제외를 한 번 허용해 주세요.\n주머니 속에서도 백그라운드로 상주합니다.\n"
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

        if (registeredDevice() && missingSensors().isNotEmpty()) {
            root.addView(Button(this).apply {
                text = "카메라·마이크 권한 허용"
                setOnClickListener { requestPermissions(missingSensors().toTypedArray(), 7001) }
            })
        }
        if (registeredDevice() && !remoteScreenReady()) {
            root.addView(Button(this).apply {
                text = "중앙 요청의 화면 자동 열기 허용"
                setOnClickListener {
                    startActivity(Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION, Uri.parse("package:$packageName")))
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

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<out String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == 7001) {
            if (allReady()) {
                startActivity(Intent(this, LauncherActivity::class.java))
                finish()
            } else renderSetup()
        }
    }
}
