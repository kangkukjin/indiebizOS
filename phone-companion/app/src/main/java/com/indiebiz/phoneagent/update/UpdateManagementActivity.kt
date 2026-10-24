package com.indiebiz.phoneagent.update

import android.app.Activity
import android.app.AlertDialog
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.os.Bundle
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView

/** Local, user-confirmed exit from optional device ownership. Opening it changes nothing. */
class UpdateManagementActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        render()
    }

    private fun render() {
        val policy = getSystemService(DevicePolicyManager::class.java)
        val owner = policy.isDeviceOwnerApp(packageName)
        title = "IndieBiz 업데이트 관리"
        setContentView(LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(40, 80, 40, 40)
            addView(TextView(context).apply {
                textSize = 18f
                text = if (owner) "IndieBiz가 이 기기의 관리자입니다. 등록된 중앙 PC가 요청한 앱 업데이트를 무인 설치합니다."
                    else "일반 앱 상태입니다. 설치 시 Android의 확인이 필요할 수 있습니다."
            })
            if (owner) addView(Button(context).apply {
                text = "무인 업데이트 관리 해제"
                setOnClickListener {
                    AlertDialog.Builder(this@UpdateManagementActivity)
                        .setTitle("기기 관리자 권한을 해제할까요?")
                        .setMessage("앱과 데이터를 유지하며 IndieBiz의 기기 소유자 권한을 해제합니다. 이후 무인 설치가 불가능할 수 있고, 다시 설정하려면 USB 준비 절차가 필요합니다.")
                        .setNegativeButton("취소", null)
                        .setPositiveButton("해제") { _, _ ->
                            try {
                                @Suppress("DEPRECATION")
                                policy.clearDeviceOwnerApp(packageName)
                                policy.removeActiveAdmin(ComponentName(this@UpdateManagementActivity, UpdateDeviceAdminReceiver::class.java))
                                render()
                            } catch (error: Exception) {
                                AlertDialog.Builder(this@UpdateManagementActivity)
                                    .setMessage("관리 해제 실패: ${error.message}").setPositiveButton("확인", null).show()
                            }
                        }.show()
                }
            })
        })
    }
}
