package com.indiebiz.phoneagent

import android.Manifest
import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.net.Uri
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.provider.Settings
import android.view.WindowManager
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** Hardware only. Runs in the resident process: worker exit must not extinguish a torch.
 * No media/app/content operations. OS permissions remain authoritative.
 */
object HardwareControl {
    private lateinit var context: Context
    private val main = Handler(Looper.getMainLooper())
    private val torches = ConcurrentHashMap<String, Boolean>()
    private val unavailable = ConcurrentHashMap.newKeySet<String>()
    private var torchListening = false
    private val sensors = linkedMapOf("light" to Sensor.TYPE_LIGHT, "proximity" to Sensor.TYPE_PROXIMITY,
        "accelerometer" to Sensor.TYPE_ACCELEROMETER, "gyroscope" to Sensor.TYPE_GYROSCOPE,
        "magnetic_field" to Sensor.TYPE_MAGNETIC_FIELD, "pressure" to Sensor.TYPE_PRESSURE)

    fun init(ctx: Context) {
        context = ctx.applicationContext
        try { watchTorch() } catch (_: Exception) { /* Recheck availability on request. */ }
    }
    private fun camera() = context.getSystemService(CameraManager::class.java)
    private fun canCamera() = context.checkSelfPermission(Manifest.permission.CAMERA) == PackageManager.PERMISSION_GRANTED
    @Synchronized private fun watchTorch() {
        if (torchListening) return
        camera().registerTorchCallback(object : CameraManager.TorchCallback() {
            override fun onTorchModeChanged(id: String, enabled: Boolean) { torches[id] = enabled; unavailable.remove(id) }
            override fun onTorchModeUnavailable(id: String) { torches.remove(id); unavailable.add(id) }
        }, main)
        torchListening = true
    }
    private fun flashIds() = camera().cameraIdList.filter {
        camera().getCameraCharacteristics(it).get(CameraCharacteristics.FLASH_INFO_AVAILABLE) == true
    }
    private fun setting(key: String) = Settings.System.getInt(context.contentResolver, key, -1)
    private fun bool(a: JSONObject, key: String): Boolean {
        require(a.opt(key) is Boolean) { "$key must be boolean" }; return a.getBoolean(key)
    }
    private fun number(a: JSONObject, key: String, low: Int, high: Int): Int {
        val v = a.opt(key)
        require(v is Number && v.toDouble().isFinite() && v.toDouble() == v.toInt().toDouble() && v.toInt() in low..high) { "$key must be integer $low..$high" }
        return v.toInt()
    }

    fun state(): JSONObject {
        val power = context.getSystemService(PowerManager::class.java)
        val lock = context.getSystemService(android.app.KeyguardManager::class.java)
        val battery = context.getSystemService(BatteryManager::class.java)
        val sensorManager = context.getSystemService(SensorManager::class.java)
        val display = context.getSystemService(WindowManager::class.java).defaultDisplay
        val point = android.graphics.Point().also { display.getRealSize(it) }
        val sensorList = JSONArray()
        for ((name, type) in sensors) sensorManager.getDefaultSensor(type)?.let {
            sensorList.put(JSONObject().put("id", name).put("name", it.name).put("type", type)
                .put("resolution", it.resolution).put("max_range", it.maximumRange))
        }
        val lights = JSONArray()
        var torchError: String? = null
        try {
            watchTorch()
            for (id in flashIds()) lights.put(JSONObject().put("id", id)
                .put("enabled", torches[id] ?: JSONObject.NULL)
                .put("available", !unavailable.contains(id) && torches.containsKey(id)))
        } catch (e: Exception) { torchError = e.javaClass.simpleName }
        val connectivity = context.getSystemService(ConnectivityManager::class.java)
        val net = connectivity.getNetworkCapabilities(connectivity.activeNetwork)
        val transports = JSONArray()
        for ((name, type) in listOf("wifi" to NetworkCapabilities.TRANSPORT_WIFI,
            "cellular" to NetworkCapabilities.TRANSPORT_CELLULAR, "ethernet" to NetworkCapabilities.TRANSPORT_ETHERNET,
            "bluetooth" to NetworkCapabilities.TRANSPORT_BLUETOOTH, "vpn" to NetworkCapabilities.TRANSPORT_VPN)) {
            if (net?.hasTransport(type) == true) transports.put(name)
        }
        val wifi = try { (context.getSystemService(Context.WIFI_SERVICE) as WifiManager).isWifiEnabled } catch (_: SecurityException) { null }
        val settings = Settings.System.canWrite(context)
        return JSONObject().put("success", true).put("hardware_control", 1)
            .put("screen_on", power.isInteractive).put("locked", lock.isKeyguardLocked)
            .put("width", point.x).put("height", point.y).put("brightness", setting(Settings.System.SCREEN_BRIGHTNESS))
            .put("brightness_auto", setting(Settings.System.SCREEN_BRIGHTNESS_MODE) == Settings.System.SCREEN_BRIGHTNESS_MODE_AUTOMATIC)
            .put("auto_rotate", setting(Settings.System.ACCELEROMETER_ROTATION) == 1)
            .put("screen_timeout_ms", setting(Settings.System.SCREEN_OFF_TIMEOUT))
            .put("battery", battery.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY)).put("charging", battery.isCharging)
            .put("power_save", power.isPowerSaveMode).put("wifi_enabled", wifi ?: JSONObject.NULL)
            .put("network_transports", transports).put("network_validated", net?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true)
            .put("sensors", sensorList).put("torches", lights).put("torch_error", torchError ?: JSONObject.NULL)
            .put("capabilities", JSONObject().put("settings_write", settings).put("camera_permission", canCamera())
                .put("screen_off", PhoneAccessibilityService.instance != null)
                .put("screen_on", Settings.canDrawOverlays(context))
                .put("wifi_toggle", false).put("bluetooth_toggle", false).put("device_power", false))
    }

    private fun setSystem(a: JSONObject, op: String): JSONObject {
        check(Settings.System.canWrite(context)) { "settings_permission_required: 폰에서 시스템 설정 변경을 허용하세요" }
        val values = when (op) {
            "brightness" -> listOf(Settings.System.SCREEN_BRIGHTNESS_MODE to Settings.System.SCREEN_BRIGHTNESS_MODE_MANUAL,
                Settings.System.SCREEN_BRIGHTNESS to number(a, "value", 1, 255))
            "brightness_auto" -> listOf(Settings.System.SCREEN_BRIGHTNESS_MODE to if (bool(a, "enabled")) 1 else 0)
            "rotation" -> if (bool(a, "enabled")) listOf(Settings.System.ACCELEROMETER_ROTATION to 1) else
                listOf(Settings.System.USER_ROTATION to context.getSystemService(WindowManager::class.java).defaultDisplay.rotation,
                    Settings.System.ACCELEROMETER_ROTATION to 0)
            "timeout" -> listOf(Settings.System.SCREEN_OFF_TIMEOUT to number(a, "seconds", 15, 600) * 1000)
            else -> error("unsupported_setting")
        }
        val update = HardwareSettingUpdate.apply(values, ::setting) { key, value ->
            Settings.System.putInt(context.contentResolver, key, value)
        }
        return settingFields(update.after).put("success", true).put("hardware_control", 1)
            .put("observation_scope", "settings").put("op", op)
            .put("before", settingFields(update.before)).put("verified", update.verified)
            .put("capabilities", JSONObject().put("settings_write", Settings.System.canWrite(context)))
            .put("message", if (update.verified) "설정 적용값을 확인했습니다." else "설정값이 요청과 다릅니다. 상태를 다시 확인하세요.")
    }

    private fun settingFields(values: Map<String, Int>): JSONObject = JSONObject().apply {
        values[Settings.System.SCREEN_BRIGHTNESS]?.let { put("brightness", it) }
        values[Settings.System.SCREEN_BRIGHTNESS_MODE]?.let {
            put("brightness_auto", if (it < 0) JSONObject.NULL else it == Settings.System.SCREEN_BRIGHTNESS_MODE_AUTOMATIC)
        }
        values[Settings.System.ACCELEROMETER_ROTATION]?.let { put("auto_rotate", if (it < 0) JSONObject.NULL else it == 1) }
        values[Settings.System.USER_ROTATION]?.let { put("user_rotation", it) }
        values[Settings.System.SCREEN_OFF_TIMEOUT]?.let { put("screen_timeout_ms", it) }
    }

    private fun sample(a: JSONObject): JSONObject {
        val name = a.getString("sensor")
        val type = sensors[name] ?: error("unsupported_sensor")
        val manager = context.getSystemService(SensorManager::class.java)
        val sensor = manager.getDefaultSensor(type) ?: error("sensor_not_present")
        val done = CountDownLatch(1)
        var reading: JSONObject? = null
        val listener = object : SensorEventListener {
            override fun onAccuracyChanged(s: Sensor?, accuracy: Int) {}
            override fun onSensorChanged(event: SensorEvent) {
                if (reading == null) {
                    reading = JSONObject().put("values", JSONArray(event.values.toList())).put("accuracy", event.accuracy)
                        .put("timestamp_ns", event.timestamp)
                    done.countDown()
                }
            }
        }
        try {
            check(manager.registerListener(listener, sensor, SensorManager.SENSOR_DELAY_NORMAL, main)) { "sensor_unavailable" }
            check(done.await(1500, TimeUnit.MILLISECONDS)) { "sensor_timeout: 화면 꺼짐·백그라운드 제한 또는 센서 미응답" }
            return JSONObject().put("success", true).put("op", "sensor").put("sensor", name).put("reading", reading)
                .put("message", "센서값을 한 번 읽고 구독을 해제했습니다.")
        } finally { manager.unregisterListener(listener) }
    }

    @Synchronized fun run(a: JSONObject): JSONObject {
        check(::context.isInitialized) { "hardware_unavailable" }
        check(Looper.myLooper() != Looper.getMainLooper()) { "hardware_on_main_thread" }
        return when (val op = a.optString("op", "status")) {
            "status" -> state().put("message", "기기 상태를 조회했습니다.")
            "brightness", "brightness_auto", "rotation", "timeout" -> setSystem(a, op)
            "sensor" -> sample(a)
            "torch" -> {
                val enabled = bool(a, "enabled")
                check(canCamera()) { "camera_permission_required" }
                watchTorch()
                val ids = flashIds()
                val id = a.optString("camera_id").ifEmpty { ids.firstOrNull() ?: error("torch_not_present") }
                require(id in ids) { "unknown_torch" }
                camera().setTorchMode(id, enabled)
                for (i in 0..9) { if (torches[id] == enabled) break; Thread.sleep(50) }
                state().put("op", op).put("verified", torches[id] == enabled)
                    .put("message", if (torches[id] == enabled) "손전등 상태를 확인했습니다." else "손전등 변경을 요청했지만 상태는 미확인입니다.")
            }
            "screen_off" -> {
                val service = PhoneAccessibilityService.instance ?: error("accessibility_required")
                check(service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_LOCK_SCREEN)) { "screen_lock_rejected" }
                for (i in 0..9) { if (!context.getSystemService(PowerManager::class.java).isInteractive) break; Thread.sleep(100) }
                val after = state()
                after.put("op", op).put("verified", !after.getBoolean("screen_on"))
                    .put("message", "화면 끄기·잠금을 요청했습니다. verified는 관측 시점의 화면 꺼짐 확인입니다.")
            }
            "screen_on" -> {
                check(Settings.canDrawOverlays(context)) { "overlay_permission_required" }
                context.startActivity(Intent(context, HardwareWakeActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                for (i in 0..14) { if (context.getSystemService(PowerManager::class.java).isInteractive) break; Thread.sleep(100) }
                val after = state()
                after.put("op", op).put("verified", after.getBoolean("screen_on"))
                    .put("message", "화면 켜기를 요청했습니다. 잠금은 해제하지 않습니다.")
            }
            "settings_permission" -> {
                context.startActivity(Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS, Uri.parse("package:" + context.packageName)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
                JSONObject().put("success", true).put("op", op).put("verified", false)
                    .put("message", "시스템 설정 변경 권한 화면을 요청했습니다. 폰에서 허용 후 상태를 새로 조회하세요.")
            }
            else -> error("unsupported_hardware_op: $op")
        }
    }
}
