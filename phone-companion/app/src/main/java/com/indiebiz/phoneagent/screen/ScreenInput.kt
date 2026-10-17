package com.indiebiz.phoneagent.screen

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.os.*
import android.view.accessibility.AccessibilityNodeInfo
import com.indiebiz.phoneagent.PhoneAccessibilityService
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.math.abs

/** Gestures are submitted on release; disconnect/reset never completes a partial drag. */
internal class PointerStroke {
    data class Point(val x: Double, val y: Double)
    data class Stroke(val points: List<Point>, val duration: Long)
    private val points = mutableListOf<Point>()
    private var started = 0L
    fun reset() { points.clear() }
    fun pointer(x: Double, y: Double, buttons: Int, now: Long): Stroke? {
        require(x.isFinite() && y.isFinite() && x in 0.0..1.0 && y in 0.0..1.0)
        if (buttons and 1 != 0) {
            if (points.isEmpty()) started = now
            if (points.size < 512) points.add(Point(x, y)) else points[points.lastIndex] = Point(x, y)
            return null
        }
        if (points.isEmpty()) return null
        points.add(Point(x, y))
        val result = Stroke(points.toList(), (now - started).coerceIn(50, 3000))
        reset()
        return result
    }
}

internal class ScreenInput {
    @Volatile var width = 1
    @Volatile var height = 1
    private val pointer = PointerStroke()
    fun handle(m: JSONObject) {
        val service = PhoneAccessibilityService.instance ?: error("accessibility")
        when (m.getString("type")) {
            "reset" -> pointer.reset()
            "pointer" -> pointer.pointer(m.getDouble("x"), m.getDouble("y"), m.getInt("buttons"), SystemClock.elapsedRealtime())?.let { stroke ->
                val path = Path()
                stroke.points.forEachIndexed { i, point ->
                    val x = (point.x * (width - 1)).toFloat(); val y = (point.y * (height - 1)).toFloat()
                    if (i == 0) path.moveTo(x, y) else path.lineTo(x, y)
                }
                gesture(service, path, stroke.duration)
            }
            "wheel" -> {
                val dx = m.optDouble("dx"); val dy = m.optDouble("dy")
                if (abs(dx) + abs(dy) < 1) return
                val x = (m.getDouble("x") * width).toFloat().coerceIn(1f, (width - 1).toFloat())
                val y = (m.getDouble("y") * height).toFloat().coerceIn(1f, (height - 1).toFloat())
                val endX = (x - dx.coerceIn(-width * .6, width * .6)).toFloat().coerceIn(1f, (width - 1).toFloat())
                val endY = (y - dy.coerceIn(-height * .6, height * .6)).toFloat().coerceIn(1f, (height - 1).toFloat())
                gesture(service, Path().apply { moveTo(x, y); lineTo(endX, endY) }, 180)
            }
            "navigation" -> check(JSONObject(PhoneAccessibilityService.pressKey(m.getString("action"))).getBoolean("success"))
            "text" -> edit(service, m.getString("text"), "")
            "key" -> if (m.getBoolean("down")) {
                when (m.getString("code")) {
                    "Escape" -> check(service.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK))
                    "Backspace", "Delete", "ArrowLeft", "ArrowRight", "Home", "End", "Enter" -> edit(service, "", m.getString("code"))
                    else -> if (m.getString("key").codePointCount(0, m.getString("key").length) == 1) edit(service, m.getString("key"), "")
                }
            }
        }
    }
    private fun gesture(service: AccessibilityService, path: Path, duration: Long) {
        val done = CountDownLatch(1)
        var success = false
        check(service.dispatchGesture(GestureDescription.Builder().addStroke(
            GestureDescription.StrokeDescription(path, 0, duration)).build(), object : AccessibilityService.GestureResultCallback() {
            override fun onCompleted(gestureDescription: GestureDescription?) { success = true; done.countDown() }
            override fun onCancelled(gestureDescription: GestureDescription?) { done.countDown() }
        }, Handler(Looper.getMainLooper())))
        check(done.await(5, TimeUnit.SECONDS) && success)
    }
    private fun edit(service: AccessibilityService, text: String, key: String) {
        val node = service.rootInActiveWindow?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) ?: error("no_input_focus")
        if (key == "Enter" && Build.VERSION.SDK_INT >= 30 && node.actionList.contains(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER)) {
            check(node.performAction(AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id)); return
        }
        val before = node.text?.toString() ?: ""
        var start = node.textSelectionStart.coerceIn(0, before.length)
        var end = node.textSelectionEnd.coerceIn(start, before.length)
        when (key) {
            "ArrowLeft", "ArrowRight", "Home", "End" -> {
                val cursor = when (key) {
                    "Home" -> 0; "End" -> before.length
                    "ArrowLeft" -> if (start > 0) before.offsetByCodePoints(start, -1) else 0
                    else -> if (end < before.length) before.offsetByCodePoints(end, 1) else before.length
                }
                check(node.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, Bundle().apply {
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, cursor)
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, cursor)
                })); return
            }
            "Backspace" -> if (start == end && start > 0) start = before.offsetByCodePoints(start, -1)
            "Delete" -> if (start == end && end < before.length) end = before.offsetByCodePoints(end, 1)
        }
        val insert = if (key == "Enter") "\n" else text
        check(node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, before.substring(0, start) + insert + before.substring(end))
        }))
        node.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, Bundle().apply {
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, start + insert.length)
            putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, start + insert.length)
        })
    }
}
