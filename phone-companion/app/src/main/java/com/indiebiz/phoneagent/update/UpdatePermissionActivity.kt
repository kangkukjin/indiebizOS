package com.indiebiz.phoneagent.update

import android.app.Activity
import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/** Only appears for an update already requested by the registered central owner. */
class UpdatePermissionActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (!ApkUpdater.needsPermission()) { finish(); return }
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(40, 80, 40, 40)
            addView(TextView(context).apply { text = "중앙에서 앱 업데이트를 요청했습니다. IndieBiz의 앱 설치를 허용하면 계속 진행합니다."; textSize = 18f })
            addView(Button(context).apply {
                text = "앱 설치 허용 설정"
                setOnClickListener { startActivity(Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:$packageName"))) }
            })
        })
    }
    override fun onResume() {
        super.onResume()
        if (packageManager.canRequestPackageInstalls()) { Thread { ApkUpdater.resumeInstall() }.start(); finish() }
    }
}
