package com.indiebiz.phoneagent.screen

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo

/** Some OEM keyguards return black screenshots but expose their controls to accessibility.
 * Show the real control bounds, explicitly labelled as a layout view. The owner can swipe
 * to the keyguard and click its keypad remotely; Android still verifies the credential.
 * Never paint password values, including descendants of password/editable containers.
 */
internal object LockScreenPreview {
    fun label(text: String?, description: String?, protected: Boolean): String =
        if (protected) "보안 입력" else (text?.takeIf { it.isNotBlank() } ?: description.orEmpty()).take(80)

    fun blackContent(pixels: IntArray): Boolean {
        require(pixels.size == 64 * 64)
        // A secure credential window may be black while Android's status/navigation bars
        // remain visible. Do not mistake the white Back icon for readable screen content.
        return (8 until 56).all { y -> (4 until 60).all { x -> pixels[y * 64 + x] and 0x00ffffff == 0 } }
    }

    fun patternGrid(viewId: String?, className: String?): Boolean =
        viewId?.substringAfterLast('/') in setOf("lockPatternView", "lock_pattern_view") ||
            className?.endsWith(".LockPatternView") == true

    fun isBlack(bitmap: Bitmap): Boolean {
        val sample = Bitmap.createScaledBitmap(bitmap, 64, 64, true)
        return try {
            val pixels = IntArray(64 * 64)
            sample.getPixels(pixels, 0, 64, 0, 0, 64, 64)
            blackContent(pixels)
        } finally { if (sample !== bitmap) sample.recycle() }
    }

    fun render(service: AccessibilityService, width: Int, height: Int): Bitmap {
        val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
        val canvas = Canvas(bitmap)
        canvas.drawColor(Color.rgb(20, 24, 32))
        val paint = Paint(Paint.ANTI_ALIAS_FLAG).apply { textSize = width / 32f }
        var visited = 0
        var labelled = 0
        var hasPattern = false
        fun visit(node: AccessibilityNodeInfo, depth: Int, hidden: Boolean) {
            if (++visited > 250 || depth > 40) return
            val protected = hidden || node.isPassword || node.isEditable
            val pattern = patternGrid(node.viewIdResourceName, node.className?.toString())
            val rect = Rect().also { node.getBoundsInScreen(it) }
            if (node.isVisibleToUser && rect.intersect(0, 0, width, height)) {
                val value = if (pattern) "" else label(node.text?.toString(), node.contentDescription?.toString(), protected)
                if (pattern) {
                    hasPattern = true
                    // Only the public, empty 3×3 control grid. Never show the selected path.
                    labelled++
                    paint.style = Paint.Style.FILL; paint.color = Color.WHITE
                    for (row in 0..2) for (column in 0..2) canvas.drawCircle(
                        rect.left + (column + .5f) * rect.width() / 3,
                        rect.top + (row + .5f) * rect.height() / 3, width / 90f, paint)
                }
                if (node.isClickable && rect.width() * rect.height().toLong() < width * height.toLong() * .7) {
                    paint.style = Paint.Style.STROKE; paint.strokeWidth = 2f; paint.color = Color.rgb(103, 151, 204)
                    canvas.drawRect(rect, paint)
                }
                if (value.isNotEmpty()) {
                    labelled++
                    paint.style = Paint.Style.FILL; paint.color = Color.WHITE
                    paint.textAlign = Paint.Align.CENTER
                    val fitted = value.take((maxOf(rect.width(), width / 5) / (paint.textSize * .65)).toInt().coerceAtLeast(1))
                    canvas.drawText(fitted, rect.exactCenterX(), rect.exactCenterY() + paint.textSize / 3, paint)
                }
            }
            // Masked containers need neither their current value nor their child text.
            if (protected || pattern) return
            for (i in 0 until node.childCount) node.getChild(i)?.let { child ->
                try { visit(child, depth + 1, protected) } finally { child.recycle() }
            }
        }
        service.rootInActiveWindow?.let { root ->
            try { visit(root, 0, false) } finally { root.recycle() }
        }
        paint.style = Paint.Style.FILL; paint.color = Color.rgb(35, 61, 90)
        canvas.drawRect(0f, 0f, width.toFloat(), width * .18f, paint)
        paint.color = Color.WHITE; paint.textAlign = Paint.Align.CENTER; paint.textSize = width / 30f
        canvas.drawText("잠금 화면 · 버튼 배치 보기", width / 2f, width * .07f, paint)
        paint.textSize = width / 38f
        val hint = if (hasPattern) "마우스를 누른 채 기존 패턴을 그리세요"
            else if (labelled > 0) "폰의 잠금 화면을 여기서 조작하세요"
            else "Android에서 버튼 정보를 받지 못했습니다"
        canvas.drawText(hint, width / 2f, width * .13f, paint)
        return bitmap
    }
}
