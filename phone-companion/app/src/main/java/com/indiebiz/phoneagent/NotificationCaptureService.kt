package com.indiebiz.phoneagent

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import org.json.JSONObject
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

/**
 * 지정 앱의 알림을 **원문 그대로** 폰에 붙잡아 두는 포획소.
 *
 * 왜 필요한가 — 결제 앱 알림에는 `timeout=PT72H` 가 걸려 있다(2026-08-17 실측).
 * 사용자가 지우지 않아도 72시간이 지나면 안드로이드가 스스로 지운다. 즉 "USB 꽂고
 * 수거 버튼"만으로는 3일을 넘긴 결제를 **원리적으로** 가져올 수 없다. 알림이 도착하는
 * 그 순간(t=0)에 붙잡아 두는 몸이 폰밖에 없다.
 *
 * ★2026-06-22 에 폐기했던 알림 캡처의 **범위 축소 복귀**다. 옛것은 *모든* 앱의 알림을
 * 가로채 적재했고 그게 폐기 사유였다. 이번엔 화이트리스트에 적힌 앱만 붙잡는다 —
 * 목록에 없는 앱의 알림은 파일은커녕 메모리에도 올리지 않고 즉시 버린다.
 *
 * ★공개 릴레이 전송 없음. 옛것은 Nostr DM 으로 PC 에 밀어 보냈으나(2026-06-15 제거),
 * 카드 결제 내역을 공개 릴레이에 올리는 셈이라 되살리지 않는다. 이 서비스는 원문을 적은 뒤
 * **자기 몸의 백엔드(127.0.0.1)만** 깨운다(2026-09-18) — 수거와 PC 원장 머지는 그쪽
 * (phone_finance_sync: 맥 위임 채널 직결·런처 세션 인증)이 맡는다. USB 수거는 예비 경로로 남는다.
 *
 * ★파싱하지 않는다. 결제 문구 파서는 실측이 쌓일 때마다 다듬을 물건이라 PC 에 둔다
 * (폰에 두면 문구 하나 고칠 때마다 APK 재빌드). 폰은 원문만 보관 — 오늘 광고를 결제로
 * 오인한 것 같은 사고도 원문이 남아 있으면 PC 에서 재파싱으로 교정된다.
 *
 * 사용 전 1회: 폰 설정 > 알림 > 고급 설정 > 알림 접근 > IndieBiz 켜기 (보안상 프로그램으론 못 켬).
 */
class NotificationCaptureService : NotificationListenerService() {

    companion object {
        /** 화이트리스트 기본값. 카드사 패키지명은 '세계의 명사'라 아래 config 파일로 덮을 수 있다. */
        private val DEFAULT_PKGS = setOf(
            "com.hanaskcard.paycla",   // 하나카드
            "gov.cheongju.cjpay",      // 청주페이
        )

        /** 파일이 무한정 자라지 않게 — 이 줄 수를 넘으면 오래된 것부터 버린다. */
        private const val MAX_LINES = 3000

        /** 포획 직후 깨울 자기 몸의 백엔드. 수거·PC 머지는 파이썬(phone_finance_sync) 몫. */
        private const val SYNC_URL = "http://127.0.0.1:8765/finance/sync/run"
        /** 한 결제에 알림이 연달아 오므로(하나카드 7~238ms 간격 2회 실측) 잠깐 모았다 한 번만. */
        private const val SYNC_DEBOUNCE_MS = 3000L
        /** 백엔드가 아직 부팅 중일 때의 재시도(이후는 백엔드 기동 시 따라잡기가 맡는다). */
        private const val SYNC_RETRIES = 4
        private const val SYNC_RETRY_MS = 30_000L
    }

    private val io = Executors.newSingleThreadExecutor()
    private val syncTimer = Executors.newSingleThreadScheduledExecutor()
    private var pendingSync: ScheduledFuture<*>? = null
    private var syncGen = 0L   // 새 알림마다 증가 — 묵은 재시도가 새 예약과 겹치지 않게

    /** 이미 적은 알림 키 (중복 append 방지 — 특히 재바인딩 훑기에서). */
    private val seen = LinkedHashSet<String>()

    private val signalsDir: File get() = File(filesDir, "signals")
    private val logFile: File get() = File(signalsDir, "notifications.jsonl")
    private val configFile: File get() = File(signalsDir, "capture_pkgs.json")

    /** 붙잡을 앱 목록. config 파일이 있으면 그것을, 없으면 기본값. */
    private fun whitelist(): Set<String> {
        try {
            if (configFile.exists()) {
                val arr = JSONObject(configFile.readText()).optJSONArray("packages")
                if (arr != null && arr.length() > 0) {
                    return (0 until arr.length()).map { arr.getString(it) }.toSet()
                }
            }
        } catch (e: Throwable) {
            android.util.Log.w("NotiCapture", "config 읽기 실패, 기본값 사용: $e")
        }
        return DEFAULT_PKGS
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        io.execute {
            loadSeenFromTail()
            // 재바인딩·재부팅 직후 따라잡기 — 서비스가 죽어 있는 동안 온 알림도 아직
            // 화면에 살아 있으면 여기서 건진다. (72시간 만료 전이면 아직 있다.)
            try {
                activeNotifications?.forEach { capture(it, catchUp = true) }
            } catch (e: Throwable) {
                android.util.Log.w("NotiCapture", "따라잡기 실패: $e")
            }
        }
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        val n = sbn ?: return
        // ★화이트리스트 밖은 여기서 즉시 반환 — 저장도 가공도 하지 않는다.
        if (n.packageName !in whitelist()) return
        io.execute { capture(n, catchUp = false) }
    }

    /** 알림 제거는 추적하지 않는다 — 포획소는 append-only(사라지는 것을 붙잡는 게 목적). */
    override fun onNotificationRemoved(sbn: StatusBarNotification?) {}

    private fun capture(sbn: StatusBarNotification, catchUp: Boolean) {
        try {
            if (sbn.packageName !in whitelist()) return
            val ex = sbn.notification?.extras ?: return
            fun s(key: String): String = ex.getCharSequence(key)?.toString()?.trim() ?: ""

            val title = s("android.title")
            val big = s("android.bigText")
            val text = if (big.isNotEmpty()) big else s("android.text")
            val sub = s("android.subText")
            if (title.isEmpty() && text.isEmpty()) return   // 내용 없는 알림(진행바 등)

            val key = "${sbn.packageName}|${sbn.postTime}|${title.take(32)}|${text.take(32)}"
            synchronized(seen) {
                if (!seen.add(key)) return                  // 이미 적었다
                while (seen.size > MAX_LINES) seen.remove(seen.first())
            }

            val o = JSONObject()
                .put("type", "notification")                // phone_notifications._recent_local 계약
                .put("pkg", sbn.packageName)
                .put("title", title)
                .put("text", text)
                .put("posted_at", sbn.postTime)
                .put("received_at", System.currentTimeMillis())
            if (sub.isNotEmpty()) o.put("sub", sub)
            if (catchUp) o.put("catch_up", true)

            signalsDir.mkdirs()
            logFile.appendText(o.toString() + "\n")
            trimIfHuge()
            requestSync()
        } catch (e: Throwable) {
            android.util.Log.e("NotiCapture", "포획 실패: $e")
        }
    }

    /** 새로 적은 게 있으니 원장을 갱신하라고 백엔드를 깨운다(디바운스 — 연속 알림은 한 번으로). */
    private fun requestSync() {
        synchronized(syncTimer) {
            pendingSync?.cancel(false)
            val gen = ++syncGen
            pendingSync = syncTimer.schedule({ callSync(gen, SYNC_RETRIES) }, SYNC_DEBOUNCE_MS, TimeUnit.MILLISECONDS)
        }
    }

    private fun callSync(gen: Long, retriesLeft: Int) {
        try {
            (applicationContext as? App)?.ensureBackend()   // 죽어 있으면 기동(idempotent)
            val c = URL(SYNC_URL).openConnection() as HttpURLConnection
            try {
                c.requestMethod = "POST"
                c.connectTimeout = 5_000
                c.readTimeout = 120_000          // 수거 + PC 왕복을 기다린다
                c.doOutput = true
                c.setRequestProperty("content-type", "application/json")
                c.outputStream.use { it.write("{}".toByteArray()) }
                val code = c.responseCode
                if (code != 200) throw IllegalStateException("HTTP $code")
            } finally {
                c.disconnect()
            }
        } catch (e: Throwable) {
            android.util.Log.w("NotiCapture", "원장 갱신 호출 실패(남은 재시도 $retriesLeft): $e")
            if (retriesLeft > 0) {
                synchronized(syncTimer) {
                    // 그 사이 새 알림이 예약을 걸었으면 그쪽이 이어받는다
                    if (gen == syncGen) {
                        pendingSync = syncTimer.schedule({ callSync(gen, retriesLeft - 1) }, SYNC_RETRY_MS, TimeUnit.MILLISECONDS)
                    }
                }
            }
        }
    }

    /** 기존 파일 꼬리에서 키를 복원 — 서비스가 재시작해도 같은 알림을 두 번 적지 않게. */
    private fun loadSeenFromTail() {
        try {
            if (!logFile.exists()) return
            val lines = logFile.readLines()
            synchronized(seen) {
                seen.clear()
                lines.takeLast(MAX_LINES).forEach { line ->
                    try {
                        val d = JSONObject(line)
                        seen.add("${d.optString("pkg")}|${d.optLong("posted_at")}|" +
                                 "${d.optString("title").take(32)}|${d.optString("text").take(32)}")
                    } catch (_: Throwable) { /* 깨진 줄은 건너뛴다 */ }
                }
            }
        } catch (e: Throwable) {
            android.util.Log.w("NotiCapture", "seen 복원 실패: $e")
        }
    }

    private fun trimIfHuge() {
        try {
            val lines = logFile.readLines()
            if (lines.size <= MAX_LINES) return
            logFile.writeText(lines.takeLast(MAX_LINES).joinToString("\n") + "\n")
        } catch (e: Throwable) {
            android.util.Log.w("NotiCapture", "trim 실패: $e")
        }
    }
}
