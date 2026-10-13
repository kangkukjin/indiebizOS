package com.indiebiz.phoneagent.media

import org.junit.Assert.*
import org.junit.Test

class PlaybackOutputStateTest {
    @Test fun videoNeedsVisibleRenderedFrameBeforeHandoff() {
        val state = PlaybackOutputState().apply { hasVideo = true }
        assertTrue(state.needsDisplay)
        assertFalse(state.canPlay)
        assertFalse(state.playing(true))
        state.visible = true
        assertTrue(state.canPlay)
        assertFalse(state.playing(true))
        state.rendered = true
        assertTrue(state.playing(true))
        state.visible = false
        assertFalse(state.playing(true))
        state.visible = true
        assertFalse(state.playing(true)) // old frame cannot acknowledge a newly attached display
    }
    @Test fun audioContinuesWithoutDisplayButPauseSeekAndEndBlockAcknowledgement() {
        val state = PlaybackOutputState()
        assertTrue(state.playing(true))
        state.paused = true
        assertFalse(state.canPlay)
        state.paused = false; state.seeking = true
        assertFalse(state.playing(true))
        state.seeking = false; state.ended = true
        assertFalse(state.playing(true))
        state.ended = false
        assertTrue(state.playing(true))
        assertFalse(state.playing(false))
    }
}
