package com.indiebiz.phoneagent

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.util.Log
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import org.json.JSONObject
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * 자기상태 신호 수집: 위치(인터벌) + 걸음수(1일 1회) → NIP-17 DM 으로 push.
 * 포그라운드 서비스가 살아있는 동안 주기적으로 점검한다.
 */
object SignalCollector {
    private const val TAG = "IndieBizAgent"
    private const val LOCATION_INTERVAL_MS = 30 * 60 * 1000L  // 위치: 30분 간격
    private const val CHECK_INTERVAL_MS = 5 * 60 * 1000L      // 점검: 5분마다

    @Volatile private var running = false

    fun start(ctx: Context) {
        if (running) return
        running = true
        Thread {
            try { Thread.sleep(10_000) } catch (_: InterruptedException) {}
            while (running) {
                try {
                    maybeLocation(ctx.applicationContext)
                    maybeDailySteps(ctx.applicationContext)
                } catch (e: Throwable) {
                    Log.e(TAG, "신호 수집 오류: ${e.message}")
                }
                try { Thread.sleep(CHECK_INTERVAL_MS) } catch (_: InterruptedException) {}
            }
        }.apply { isDaemon = true }.start()
        Log.i(TAG, "신호 수집기 시작 (위치 ${LOCATION_INTERVAL_MS / 60000}분 간격, 걸음 1일1회)")
    }

    private fun prefs(ctx: Context) =
        ctx.getSharedPreferences("phoneagent", Context.MODE_PRIVATE)

    private fun has(ctx: Context, perm: String) =
        ctx.checkSelfPermission(perm) == PackageManager.PERMISSION_GRANTED

    // ---- 위치 (인터벌) ----
    private fun maybeLocation(ctx: Context) {
        val sp = prefs(ctx)
        val now = System.currentTimeMillis()
        if (now - sp.getLong("loc_last", 0) < LOCATION_INTERVAL_MS) return
        if (!has(ctx, Manifest.permission.ACCESS_FINE_LOCATION)) {
            Log.w(TAG, "위치 권한 없음 — 건너뜀"); return
        }
        val fused = LocationServices.getFusedLocationProviderClient(ctx)
        try {
            fused.getCurrentLocation(Priority.PRIORITY_BALANCED_POWER_ACCURACY, null)
                .addOnSuccessListener { loc ->
                    if (loc == null) { Log.w(TAG, "위치 null"); return@addOnSuccessListener }
                    sp.edit().putLong("loc_last", now).apply()
                    val payload = JSONObject()
                        .put("type", "location")
                        .put("lat", loc.latitude)
                        .put("lng", loc.longitude)
                        .put("accuracy", loc.accuracy.toDouble())
                        .put("captured_at", now / 1000)
                        .toString()
                    Log.i(TAG, "위치 ${loc.latitude},${loc.longitude} (±${loc.accuracy}m) → push")
                    Sender.sendAsync(ctx, payload)
                }
                .addOnFailureListener { Log.w(TAG, "위치 실패: ${it.message}") }
        } catch (se: SecurityException) {
            Log.w(TAG, "위치 SecurityException(백그라운드 권한?)")
        }
    }

    // ---- 걸음수 (1일 1회: 전날 누적 걸음을 하루에 한 번 보고) ----
    private fun maybeDailySteps(ctx: Context) {
        val sp = prefs(ctx)
        val today = SimpleDateFormat("yyyy-MM-dd", Locale.US).format(Date())
        if (sp.getString("steps_day", "") == today) return  // 오늘 이미 처리
        if (!has(ctx, Manifest.permission.ACTIVITY_RECOGNITION)) {
            Log.w(TAG, "활동인식 권한 없음 — 걸음 건너뜀"); return
        }
        val cumulative = readStepCounter(ctx) ?: return
        val prevDay = sp.getString("steps_day", "") ?: ""
        val prevCumulative = sp.getFloat("steps_cumulative", -1f)
        // 직전 측정 → 지금까지의 걸음(= 종료된 날의 걸음). 재부팅 시 누적이 줄면 현재값으로.
        val daySteps =
            if (prevCumulative >= 0f)
                (if (cumulative >= prevCumulative) cumulative - prevCumulative else cumulative).toInt()
            else -1
        sp.edit()
            .putString("steps_day", today)
            .putFloat("steps_cumulative", cumulative)
            .apply()
        if (daySteps >= 0 && prevDay.isNotEmpty()) {
            val payload = JSONObject()
                .put("type", "steps")
                .put("date", prevDay)               // 걸음이 쌓인 그 날
                .put("steps", daySteps)
                .put("cumulative", cumulative.toInt())
                .put("captured_at", System.currentTimeMillis() / 1000)
                .toString()
            Log.i(TAG, "걸음 $prevDay: $daySteps → push")
            Sender.sendAsync(ctx, payload)
        } else {
            Log.i(TAG, "걸음 기준선 설정 — 첫 보고는 내일")
        }
    }

    private fun readStepCounter(ctx: Context): Float? {
        val sm = ctx.getSystemService(Context.SENSOR_SERVICE) as SensorManager
        val sensor = sm.getDefaultSensor(Sensor.TYPE_STEP_COUNTER)
            ?: run { Log.w(TAG, "걸음 센서 없음"); return null }
        var value: Float? = null
        val latch = CountDownLatch(1)
        val listener = object : SensorEventListener {
            override fun onSensorChanged(e: SensorEvent) {
                if (value == null) { value = e.values[0]; latch.countDown() }
            }
            override fun onAccuracyChanged(s: Sensor?, a: Int) {}
        }
        sm.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_FASTEST)
        try { latch.await(5, TimeUnit.SECONDS) } catch (_: InterruptedException) {}
        sm.unregisterListener(listener)
        return value
    }
}
