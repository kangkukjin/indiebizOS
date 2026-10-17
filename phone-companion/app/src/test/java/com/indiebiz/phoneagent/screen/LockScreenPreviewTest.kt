package com.indiebiz.phoneagent.screen

import org.junit.Assert.*
import org.junit.Test

class LockScreenPreviewTest {
    @Test fun passwordAndEditableValuesNeverEnterThePreview() {
        assertEquals("보안 입력", LockScreenPreview.label("private credential", "spoken credential", true))
        assertEquals("보안 입력", LockScreenPreview.label(null, "spoken credential", true))
    }
    @Test fun keypadAndNavigationLabelsRemainUsable() {
        assertEquals("1", LockScreenPreview.label("1", "one", false))
        assertEquals("삭제", LockScreenPreview.label("", "삭제", false))
        assertEquals(80, LockScreenPreview.label("x".repeat(1000), null, false).length)
    }
    @Test fun systemBarsDoNotHideAnOtherwiseRedactedCredentialWindow() {
        val pixels = IntArray(64 * 64)
        pixels[2 * 64 + 30] = 0xffffff
        pixels[61 * 64 + 45] = 0xffffff
        assertTrue(LockScreenPreview.blackContent(pixels))
        pixels[32 * 64 + 32] = 0xffffff
        assertFalse(LockScreenPreview.blackContent(pixels))
    }
    @Test fun onlyTheKnownPatternControlGetsAnEmptyGrid() {
        assertTrue(LockScreenPreview.patternGrid("com.android.systemui:id/lockPatternView", "android.view.View"))
        assertTrue(LockScreenPreview.patternGrid(null, "com.android.internal.widget.LockPatternView"))
        assertFalse(LockScreenPreview.patternGrid("com.android.systemui:id/keyguard_pattern_view", "android.widget.FrameLayout"))
        assertFalse(LockScreenPreview.patternGrid(null, "android.view.View"))
    }
}
