package com.indiebiz.phoneagent

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/** 재부팅 후 상주 서비스 자동 복원. */
class BootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action == Intent.ACTION_BOOT_COMPLETED) {
            Log.i("IndieBizAgent", "부팅 완료 — 포그라운드 서비스 복원")
            AgentForegroundService.start(context.applicationContext)
        }
    }
}
