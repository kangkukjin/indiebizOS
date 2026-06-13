package com.indiebiz.phoneagent

import android.app.Activity
import android.app.Application
import android.os.Bundle
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform

/**
 * Chaquopy 파이썬 부팅 + 폰 백엔드(:8765) 생명주기.
 *
 * 백엔드는 첫 포그라운드 진입에 기동한 뒤, 상주 포그라운드 서비스와 함께 계속 살아있다.
 * (앱을 백그라운드로 보내도 중지하지 않음 — 폰=AI가 언제든 닿는 몸. [limbs:android] 가 다른 앱을
 * 조작하려면 IndieBiz 가 백그라운드여야 하는데, 그때도 명령을 받으려면 백엔드가 살아야 한다.
 * 또 맥→폰 분산 IBL 포워드도 폰이 백그라운드일 때 닿을 수 있어야 한다.)
 * 알림 캡처(NotificationListenerService)·접근성(PhoneAccessibilityService)은 시스템 관리라 무관하게 계속된다.
 */
class App : Application(), Application.ActivityLifecycleCallbacks {
    private var startedCount = 0
    @Volatile private var backendThread: Thread? = null

    override fun onCreate() {
        super.onCreate()
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(this))
        }
        PhoneActions.init(this)   // 송신측(폰→동작) effector 다리 초기화 — [limbs:phone] 가 호출
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
        if (startedCount < 0) startedCount = 0
        // 백엔드는 중지하지 않는다 — 상주 포그라운드 서비스와 함께 계속 살려둔다(폰=상시 닿는 몸).
        // [limbs:android] 자기 화면 조작·맥→폰 분산 포워드가 IndieBiz 백그라운드 상태에서도 동작하도록.
    }

    override fun onActivityCreated(a: Activity, b: Bundle?) {}
    override fun onActivityResumed(a: Activity) {}
    override fun onActivityPaused(a: Activity) {}
    override fun onActivitySaveInstanceState(a: Activity, b: Bundle) {}
    override fun onActivityDestroyed(a: Activity) {}
}
