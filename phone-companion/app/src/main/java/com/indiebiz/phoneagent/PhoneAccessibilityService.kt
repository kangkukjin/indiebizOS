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
    private val observationSession = java.util.UUID.randomUUID().toString()

    private fun doSnapshot(): String {
        val root = rootInActiveWindow ?: return err("활성 창 없음(잠금화면/전환 중일 수 있음)")
        val arr = JSONArray()
        var visited = 0
        var truncated = false
        fun visit(node: AccessibilityNodeInfo?, depth: Int, path: String) {
            if (node == null) return
            try {
                if (++visited > 1000 || arr.length() >= 200 || depth > 40) { truncated = true; return }
                val text = if (node.isPassword) "" else node.text?.toString() ?: ""
                val desc = if (node.isPassword) "" else node.contentDescription?.toString() ?: ""
                if (text.isNotEmpty() || desc.isNotEmpty() || node.isClickable || node.isEditable) {
                    val r = Rect(); node.getBoundsInScreen(r)
                    if (r.width() > 0 && r.height() > 0 && node.isVisibleToUser) {
                        arr.put(JSONObject().put("ref", arr.length()).put("path", path)
                            .put("resource_id", node.viewIdResourceName ?: "")
                            .put("label", if (text.isNotEmpty()) text else desc).put("text", text)
                            .put("cx", r.centerX()).put("cy", r.centerY())
                            .put("bounds", JSONArray(listOf(r.left, r.top, r.right, r.bottom)))
                            .put("clickable", node.isClickable).put("editable", node.isEditable)
                            .put("focused", node.isFocused).put("enabled", node.isEnabled)
                            .put("password", node.isPassword)
                            .put("cls", node.className?.toString()?.substringAfterLast('.') ?: ""))
                    }
                }
                for (i in 0 until node.childCount) {
                    if (visited >= 1000 || arr.length() >= 200) { truncated = true; break }
                    visit(node.getChild(i), depth + 1, "$path/$i")
                }
            } finally { node.recycle() }
        }
        val pkg = root.packageName?.toString() ?: ""
        val windowId = root.windowId
        val display = getSystemService(android.view.WindowManager::class.java).defaultDisplay
        val size = android.graphics.Point().also { display.getRealSize(it) }
        visit(root, 0, "0")
        val result = JSONObject().put("success", true).put("ui_contract", 1)
            .put("session", observationSession).put("package", pkg).put("window_id", windowId)
            .put("width", size.x).put("height", size.y).put("rotation", display.rotation)
            .put("count", arr.length()).put("elements", arr).put("truncated", truncated)
        val digest = java.security.MessageDigest.getInstance("SHA-256").digest(result.toString().toByteArray(Charsets.UTF_8))
        return result.put("snapshot_id", digest.joinToString("") { "%02x".format(it) }).toString()
    }

    /** Driver mutations share one guard/dispatch lock. Never retries a dispatched action. */
    @Synchronized private fun doControl(a: JSONObject): String {
        var phase = "before_dispatch"
        var inputNode: AccessibilityNodeInfo? = null
        try {
            val op = a.getString("op")
            require(op in setOf("app_launch", "home", "back", "tap", "type_text")) { "unsupported_ui_action" }
            val before = JSONObject(doSnapshot())
            require(before.optBoolean("success")) { before.optString("error") }
            val guarded = op in setOf("back", "tap", "type_text")
            require(!guarded || a.getString("snapshot_id") == before.getString("snapshot_id")) {
                "STALE_SCREEN: 화면을 다시 읽고 새 요청을 만드세요"
            }
            val result = JSONObject().put("before", before)
            var target: JSONObject? = null
            if (op == "tap" || op == "type_text") {
                if (a.has("ref")) {
                    val nodes = before.getJSONArray("elements")
                    target = (0 until nodes.length()).map { nodes.getJSONObject(it) }
                        .singleOrNull { it.getInt("ref") == a.getInt("ref") }
                    require(target != null && target.getBoolean("enabled")) { "INVALID_TARGET" }
                }
                if (op == "type_text") {
                    require(target != null && target.getBoolean("focused") && target.getBoolean("editable")
                        && !target.getBoolean("password")) { "FOCUSED_EDITABLE_REQUIRED: 입력칸을 먼저 선택하세요" }
                    val text = a.getString("text")
                    require(text.codePointCount(0, text.length) <= 10000) { "text too long" }
                }
                if (target != null) result.put("target_element", target)
            }
            var launch: android.content.Intent? = null
            if (op == "app_launch") {
                launch = packageManager.getLaunchIntentForPackage(a.getString("package"))
                require(launch != null) { "APP_NOT_LAUNCHABLE: 패키지·설치를 확인하세요" }
                result.put("expected_package", a.getString("package"))
            }
            if (op == "home") {
                val intent = android.content.Intent(android.content.Intent.ACTION_MAIN)
                    .addCategory(android.content.Intent.CATEGORY_HOME)
                val home = packageManager.resolveActivity(intent, android.content.pm.PackageManager.MATCH_DEFAULT_ONLY)
                val candidates = packageManager.queryIntentActivities(intent, android.content.pm.PackageManager.MATCH_DEFAULT_ONLY)
                val concrete = candidates.any { it.activityInfo.packageName == home?.activityInfo?.packageName
                    && it.activityInfo.name == home?.activityInfo?.name }
                result.put("expected_package", if (concrete) home?.activityInfo?.packageName ?: "" else "")
            }
            val x = if (op == "tap") target?.getInt("cx") ?: a.getInt("x") else 0
            val y = if (op == "tap") target?.getInt("cy") ?: a.getInt("y") else 0
            if (op == "tap") require(x in 0 until before.getInt("width") && y in 0 until before.getInt("height")) { "INVALID_COORDINATES" }
            // Resolve the observed node itself, not whichever field gained focus later.
            if (op == "type_text") inputNode = resolveInput(before, target!!)
            phase = "dispatch"
            val dispatch = when (op) {
                "app_launch" -> { startActivity(launch!!.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)); JSONObject().put("success", true) }
                "home", "back" -> JSONObject(doPressKey(op))
                "tap" -> JSONObject(doTap(x, y))
                else -> JSONObject(setNodeText(inputNode!!, a.getString("text")))
            }
            return result.put("success", dispatch.optBoolean("success"))
                .put("dispatched", true).put("dispatch", dispatch).put("execution_phase", phase)
                .put("error", dispatch.optString("error")).toString()
        } catch (e: Exception) {
            return JSONObject().put("success", false).put("error", e.message ?: e.toString())
                .put("execution_phase", phase).put("dispatched", phase != "before_dispatch").toString()
        } finally { inputNode?.recycle() }
    }

    private fun resolveInput(before: JSONObject, target: JSONObject): AccessibilityNodeInfo {
        var node = rootInActiveWindow ?: error("STALE_SCREEN: 활성 창 없음")
        try {
            require(node.windowId == before.getInt("window_id") && node.packageName?.toString() == before.getString("package")) { "STALE_SCREEN: 전면 창 변경" }
            for (index in target.getString("path").split('/').drop(1)) {
                val child = node.getChild(index.toInt()) ?: error("STALE_SCREEN: 입력칸 없음")
                node.recycle(); node = child
            }
            require(node.isFocused && node.isEditable && node.isEnabled && !node.isPassword
                && (node.viewIdResourceName ?: "") == target.getString("resource_id")) { "STALE_SCREEN: 입력칸 변경" }
            return node
        } catch (e: Exception) { node.recycle(); throw e }
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

    private fun setNodeText(node: AccessibilityNodeInfo, text: String): String {
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return if (node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args))
            ok("텍스트 교체 요청") else err("입력 실패(편집 불가 요소일 수 있음)")
    }

    private fun doTypeText(text: String): String {
        val root = rootInActiveWindow ?: return err("활성 창 없음")
        val focused = try { root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT) } finally { root.recycle() }
            ?: return err("입력 포커스 없음 — 먼저 입력창을 탭하세요")
        return try { setNodeText(focused, text) } finally { focused.recycle() }
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

        @JvmStatic fun control(args: String): String = instance?.doControl(JSONObject(args)) ?: notReady()
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
