package com.indiebiz.phoneagent

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.graphics.Rect
import android.os.Bundle
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * 폰이 자기 화면을 독해·조작하는 손 ([limbs:android] 의 폰 네이티브 다리).
 *
 * 기존 PC-ADB(uiautomator+input)는 USB 연결이 있어야 폰을 제어한다. 이 서비스는 폰 안에서
 * AccessibilityService 로 같은 일을 한다 — USB 없이 자급. handler.py 가 INDIEBIZ_PROFILE=phone 일 때
 * Chaquopy 로 companion 의 @JvmStatic 다리를 호출한다.
 *
 * snapshot(노드트리 독해) → tap/type/swipe/key/long_press. 한글 입력은 ACTION_SET_TEXT 라 IME 불필요.
 * 사용 전 1회: 폰 설정 > 접근성 > 설치된 서비스 > IndieBiz 켜기 (보안상 프로그램으론 못 켬).
 */
class PhoneAccessibilityService : AccessibilityService() {

    override fun onServiceConnected() { instance = this }
    override fun onDestroy() { if (instance === this) instance = null; super.onDestroy() }
    override fun onInterrupt() {}
    override fun onAccessibilityEvent(event: AccessibilityEvent?) {}

    // ---- 화면 독해 ----
    private fun doSnapshot(): String {
        val root = rootInActiveWindow ?: return err("활성 창 없음(잠금화면/전환 중일 수 있음)")
        val arr = JSONArray()
        val counter = intArrayOf(0)
        fun visit(node: AccessibilityNodeInfo?, depth: Int) {
            if (node == null || counter[0] >= 200 || depth > 40) return
            val text = node.text?.toString()?.trim() ?: ""
            val desc = node.contentDescription?.toString()?.trim() ?: ""
            val clickable = node.isClickable
            if (text.isNotEmpty() || desc.isNotEmpty() || clickable) {
                val r = Rect(); node.getBoundsInScreen(r)
                if (r.width() > 0 && r.height() > 0) {
                    arr.put(
                        JSONObject()
                            .put("ref", counter[0])
                            .put("label", if (text.isNotEmpty()) text else desc)
                            .put("cx", r.centerX()).put("cy", r.centerY())
                            .put("clickable", clickable)
                            .put("editable", node.isEditable)
                            .put("cls", node.className?.toString()?.substringAfterLast('.') ?: "")
                    )
                    counter[0]++
                }
            }
            for (i in 0 until node.childCount) visit(node.getChild(i), depth + 1)
        }
        visit(root, 0)
        return JSONObject().put("success", true).put("count", arr.length())
            .put("elements", arr).toString()
    }

    private fun findByText(query: String, index: Int): AccessibilityNodeInfo? {
        val root = rootInActiveWindow ?: return null
        val matches = ArrayList<AccessibilityNodeInfo>()
        val q = query.lowercase()
        fun visit(node: AccessibilityNodeInfo?) {
            if (node == null) return
            val t = ((node.text?.toString() ?: "") + " " + (node.contentDescription?.toString() ?: "")).lowercase()
            if (t.contains(q)) matches.add(node)
            for (i in 0 until node.childCount) visit(node.getChild(i))
        }
        visit(root)
        return matches.getOrNull(index)
    }

    // ---- 제스처 (dispatchGesture 는 비동기 — latch 로 동기화) ----
    private fun dispatchAndWait(g: GestureDescription): Boolean {
        val latch = CountDownLatch(1)
        val ok = booleanArrayOf(false)
        val posted = dispatchGesture(g, object : GestureResultCallback() {
            override fun onCompleted(d: GestureDescription?) { ok[0] = true; latch.countDown() }
            override fun onCancelled(d: GestureDescription?) { latch.countDown() }
        }, null)
        if (!posted) return false
        latch.await(8, TimeUnit.SECONDS)
        return ok[0]
    }

    private fun gestureTap(x: Int, y: Int, durationMs: Long): Boolean {
        val path = Path().apply { moveTo(x.toFloat(), y.toFloat()) }
        val g = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, durationMs)).build()
        return dispatchAndWait(g)
    }

    private fun gestureSwipe(x1: Int, y1: Int, x2: Int, y2: Int, durationMs: Long): Boolean {
        val path = Path().apply { moveTo(x1.toFloat(), y1.toFloat()); lineTo(x2.toFloat(), y2.toFloat()) }
        val g = GestureDescription.Builder()
            .addStroke(GestureDescription.StrokeDescription(path, 0, durationMs)).build()
        return dispatchAndWait(g)
    }

    private fun doTap(x: Int, y: Int): String =
        if (gestureTap(x, y, 50)) ok("탭 ($x,$y)") else err("탭 실패")

    private fun doTapByText(query: String, index: Int): String {
        val node = findByText(query, index) ?: return err("요소 못 찾음: '$query' (snapshot 으로 라벨 확인)")
        val r = Rect(); node.getBoundsInScreen(r)
        return if (gestureTap(r.centerX(), r.centerY(), 50)) ok("탭 '$query'") else err("탭 실패 '$query'")
    }

    private fun doLongPress(x: Int, y: Int, durationMs: Long): String =
        if (gestureTap(x, y, durationMs)) ok("롱프레스 ($x,$y)") else err("롱프레스 실패")

    private fun doSwipe(x1: Int, y1: Int, x2: Int, y2: Int, durationMs: Long): String =
        if (gestureSwipe(x1, y1, x2, y2, durationMs)) ok("스와이프") else err("스와이프 실패")

    private fun doSwipeDir(direction: String): String {
        val dm = resources.displayMetrics
        val w = dm.widthPixels; val h = dm.heightPixels
        val cx = w / 2; val cy = h / 2
        return when (direction.lowercase()) {
            "up" -> doSwipe(cx, (h * 0.7).toInt(), cx, (h * 0.3).toInt(), 300)
            "down" -> doSwipe(cx, (h * 0.3).toInt(), cx, (h * 0.7).toInt(), 300)
            "left" -> doSwipe((w * 0.7).toInt(), cy, (w * 0.3).toInt(), cy, 300)
            "right" -> doSwipe((w * 0.3).toInt(), cy, (w * 0.7).toInt(), cy, 300)
            else -> err("방향: up/down/left/right")
        }
    }

    private fun doTypeText(text: String): String {
        val root = rootInActiveWindow ?: return err("활성 창 없음")
        val focused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
            ?: return err("입력 포커스 없음 — 먼저 입력창을 탭하세요")
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return if (focused.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args))
            ok("입력: ${text.take(20)}") else err("입력 실패(편집 불가 요소일 수 있음)")
    }

    private fun doPressKey(key: String): String {
        val action = when (key.lowercase()) {
            "back" -> GLOBAL_ACTION_BACK
            "home" -> GLOBAL_ACTION_HOME
            "recent", "recents" -> GLOBAL_ACTION_RECENTS
            "notifications", "notification" -> GLOBAL_ACTION_NOTIFICATIONS
            else -> return err("지원 키: back/home/recent/notifications (enter 등 직접 키주입은 미지원)")
        }
        return if (performGlobalAction(action)) ok("키: $key") else err("키 실패: $key")
    }

    private fun ok(msg: String) = JSONObject().put("success", true).put("message", msg).toString()
    private fun err(msg: String) = JSONObject().put("success", false).put("error", msg).toString()

    companion object {
        @Volatile @JvmStatic var instance: PhoneAccessibilityService? = null

        private fun notReady() = JSONObject().put("success", false)
            .put("error", "접근성 서비스 미활성 — 폰 설정 > 접근성 > 설치된 서비스 > IndieBiz 를 켜세요")
            .put("needs_accessibility", true).toString()

        @JvmStatic fun snapshot(): String = instance?.doSnapshot() ?: notReady()
        @JvmStatic fun tap(x: Int, y: Int): String = instance?.doTap(x, y) ?: notReady()
        @JvmStatic fun tapByText(q: String, idx: Int): String = instance?.doTapByText(q, idx) ?: notReady()
        @JvmStatic fun longPress(x: Int, y: Int, dur: Int): String = instance?.doLongPress(x, y, dur.toLong()) ?: notReady()
        @JvmStatic fun swipe(x1: Int, y1: Int, x2: Int, y2: Int, dur: Int): String = instance?.doSwipe(x1, y1, x2, y2, dur.toLong()) ?: notReady()
        @JvmStatic fun swipeDir(direction: String): String = instance?.doSwipeDir(direction) ?: notReady()
        @JvmStatic fun typeText(t: String): String = instance?.doTypeText(t) ?: notReady()
        @JvmStatic fun pressKey(k: String): String = instance?.doPressKey(k) ?: notReady()
    }
}
