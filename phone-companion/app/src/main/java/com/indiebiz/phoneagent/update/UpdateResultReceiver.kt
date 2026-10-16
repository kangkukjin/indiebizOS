package com.indiebiz.phoneagent.update

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent

class UpdateResultReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        ApkUpdater.init(context)
        ApkUpdater.onResult(intent)
    }
}
