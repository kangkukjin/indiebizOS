package com.indiebiz.phoneagent.execution

import com.indiebiz.phoneagent.PhoneActions
import com.indiebiz.phoneagent.PhoneAccessibilityService
import org.json.JSONArray
import org.json.JSONObject

/** Only resource-owning calls need IPC. Ordinary framework APIs are called directly. */
object RemoteDeviceCalls {
    fun call(method: String, args: String): String = try {
        val a = JSONArray(args)
        val value: Any = when (method) {
            "snapshot" -> JSONObject(PhoneAccessibilityService.snapshot())
            "tap" -> JSONObject(PhoneAccessibilityService.tap(a.getInt(0), a.getInt(1)))
            "tapByText" -> JSONObject(PhoneAccessibilityService.tapByText(a.getString(0), a.optInt(1, 0)))
            "swipe" -> JSONObject(PhoneAccessibilityService.swipe(a.getInt(0), a.getInt(1), a.getInt(2), a.getInt(3), a.optInt(4, 300)))
            "typeText" -> JSONObject(PhoneAccessibilityService.typeText(a.getString(0)))
            "pressKey" -> JSONObject(PhoneAccessibilityService.pressKey(a.getString(0)))
            "capturePhoto" -> JSONObject(PhoneActions.capturePhoto(a.optString(0, "back")))
            "recordAudio" -> JSONObject(PhoneActions.recordAudio(a.getInt(0).coerceIn(1, 300)))
            "streamStatus" -> JSONObject(PhoneActions.streamStatus())
            else -> throw IllegalArgumentException("unsupported_device_call: $method")
        }
        JSONObject().put("success", true).put("value", value).toString()
    } catch (error: Throwable) {
        JSONObject().put("success", false).put("error", error.toString()).toString()
    }
}
