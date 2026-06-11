package com.indiebiz.phoneagent

import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.speech.tts.TextToSpeech
import android.widget.Toast
import androidx.core.app.NotificationCompat
import java.util.Locale

/**
 * 송신측(폰→동작) effector 다리: 폰의 파이썬 뇌([limbs:phone])가 폰 하드웨어를 직접 만지게 한다.
 *
 * Chaquopy Java 브리지로 호출된다 — android 패키지 handler.py(_phone_act)가
 * `jclass("com.indiebiz.phoneagent.PhoneActions").notify(...)` 식으로 부른다.
 * 모든 메서드는 @JvmStatic(폰 프로파일 전용; PC에선 from java import 자체가 실패해 graceful 거부).
 *
 * [sense:phone](하드웨어 입력)의 출력 짝. 새 위험 권한 없이 견고한 첫 세트:
 * notify/vibrate/toast/clipboard/speak/openApp. SMS·통화는 민감(메시지 발송)이라 제외.
 */
object PhoneActions {
    @Volatile private var appContext: Context? = null
    @Volatile private var tts: TextToSpeech? = null
    @Volatile private var ttsReady = false
    private const val CHANNEL_ID = "indiebiz_brain"
    private val main = Handler(Looper.getMainLooper())

    /** App.onCreate 에서 1회 호출 — 컨텍스트 보관 + 알림 채널 + TTS 초기화. */
    @JvmStatic
    fun init(ctx: Context) {
        appContext = ctx.applicationContext
        ensureChannel()
        // TTS 는 비동기 초기화 — 미리 준비해 첫 speak 지연/실패를 줄인다.
        try {
            tts = TextToSpeech(appContext) { status ->
                if (status == TextToSpeech.SUCCESS) {
                    try { tts?.language = Locale.KOREAN } catch (_: Throwable) {}
                    ttsReady = true
                }
            }
        } catch (_: Throwable) {}
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val ctx = appContext ?: return
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (nm.getNotificationChannel(CHANNEL_ID) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "IndieBiz 뇌 알림", NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
    }

    /** 알림 표시. (Android 13+ 는 POST_NOTIFICATIONS 런타임 권한 필요 — 없으면 조용히 무시됨.) */
    @JvmStatic
    fun notify(title: String, body: String): Boolean {
        val ctx = appContext ?: return false
        return try {
            val n = NotificationCompat.Builder(ctx, CHANNEL_ID)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(NotificationCompat.BigTextStyle().bigText(body))
                .setAutoCancel(true)
                .build()
            val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.notify((System.currentTimeMillis() % 100000).toInt(), n)
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "notify failed: $e"); false
        }
    }

    /** 진동 (ms). VIBRATE 권한(설치시 자동 부여) 필요. */
    @JvmStatic
    fun vibrate(ms: Long): Boolean {
        val ctx = appContext ?: return false
        return try {
            val vib: Vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                (ctx.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                ctx.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
            }
            vib.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "vibrate failed: $e"); false
        }
    }

    /** 화면에 토스트 (메인 스레드). */
    @JvmStatic
    fun toast(text: String): Boolean {
        val ctx = appContext ?: return false
        main.post { try { Toast.makeText(ctx, text, Toast.LENGTH_LONG).show() } catch (_: Throwable) {} }
        return true
    }

    /** 클립보드에 텍스트 복사. */
    @JvmStatic
    fun setClipboard(text: String): Boolean {
        val ctx = appContext ?: return false
        return try {
            val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            cm.setPrimaryClip(ClipData.newPlainText("IndieBiz", text))
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "clipboard failed: $e"); false
        }
    }

    /** TTS 음성 출력. (한국어 음성 미설치 시 실패 가능.) */
    @JvmStatic
    fun speak(text: String): Boolean {
        val t = tts
        if (t == null || !ttsReady) return false
        return try {
            t.speak(text, TextToSpeech.QUEUE_FLUSH, null, "indiebiz_${System.currentTimeMillis()}")
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "speak failed: $e"); false
        }
    }

    /**
     * SMS 작성창을 수신자·본문 채워 연다 (스테이징 — 전송은 사용자가 탭).
     * ACTION_SENDTO(smsto:) 라 SEND_SMS 위험 권한 불필요. to 비면 본문만 채운 작성창.
     */
    @JvmStatic
    fun composeSms(to: String, text: String): Boolean {
        val ctx = appContext ?: return false
        return try {
            val uri = android.net.Uri.parse("smsto:" + android.net.Uri.encode(to))
            val intent = android.content.Intent(android.content.Intent.ACTION_SENDTO, uri)
            if (text.isNotEmpty()) intent.putExtra("sms_body", text)
            intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(intent)
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "composeSms failed: $e"); false
        }
    }

    /**
     * 다이얼러를 번호 채워 연다 (스테이징 — 통화는 사용자가 탭).
     * ACTION_DIAL 이라 CALL_PHONE 위험 권한 불필요(ACTION_CALL=즉시 발신과 구분).
     */
    @JvmStatic
    fun dial(number: String): Boolean {
        val ctx = appContext ?: return false
        return try {
            val uri = android.net.Uri.parse("tel:" + android.net.Uri.encode(number))
            val intent = android.content.Intent(android.content.Intent.ACTION_DIAL, uri)
            intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(intent)
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "dial failed: $e"); false
        }
    }

    /** 패키지명으로 앱 실행. 런처 인텐트 없으면 false. */
    @JvmStatic
    fun openApp(pkg: String): Boolean {
        val ctx = appContext ?: return false
        return try {
            val intent = ctx.packageManager.getLaunchIntentForPackage(pkg) ?: return false
            intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(intent)
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "openApp failed: $e"); false
        }
    }
}
