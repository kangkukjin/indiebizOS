package com.indiebiz.phoneagent

import android.app.Activity
import android.app.Application
import android.os.Bundle
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * Chaquopy 파이썬 부팅 + 폰 백엔드(:8765) 생명주기.
 *
 * 백엔드는 앱이 포그라운드에 있는 동안만 실행한다(다른 앱처럼) — 액티비티 카운터로 관리해
 * MainActivity↔LauncherActivity 전환 중에는 끊기지 않고, 앱을 떠나면(모든 액티비티 stop) 중지.
 * 알림 캡처(NotificationListenerService)는 시스템 관리라 이와 무관하게 계속된다.
 */
class App : Application(), Application.ActivityLifecycleCallbacks {
    private var startedCount = 0
    @Volatile private var backendThread: Thread? = null

    override fun onCreate() {
        super.onCreate()
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
        registerActivityLifecycleCallbacks(this)
    }

    private fun startBackend() {
        if (backendThread?.isAlive == true) return
        val ctx = applicationContext
        backendThread = Thread {
            try {
                val base = BaseBundle.ensure(ctx)
                Python.getInstance().getModule("phone_api").callAttr("serve", 8765, base)
            } catch (e: Throwable) {
                android.util.Log.e("PYSERVER", "serve failed: $e")
            }
        }.apply { isDaemon = true; start() }
    }

    private fun stopBackend() {
        Thread {
            try {
                Python.getInstance().getModule("phone_api").callAttr("stop")
            } catch (e: Throwable) {
                android.util.Log.e("PYSERVER", "stop failed: $e")
            }
        }.start()
    }

    override fun onActivityStarted(activity: Activity) {
        if (startedCount == 0) {
            // 앱이 포그라운드 진입 — 상주 서비스 + 백엔드 기동
            AgentForegroundService.start(this)
            startBackend()
        }
        startedCount++
    }

    override fun onActivityStopped(activity: Activity) {
        startedCount--
        if (startedCount <= 0) {
            startedCount = 0
            stopBackend()   // 앱이 포그라운드를 떠남 — 백엔드 중지
        }
    }

    override fun onActivityCreated(a: Activity, b: Bundle?) {}
    override fun onActivityResumed(a: Activity) {}
    override fun onActivityPaused(a: Activity) {}
    override fun onActivitySaveInstanceState(a: Activity, b: Bundle) {}
    override fun onActivityDestroyed(a: Activity) {}
}
