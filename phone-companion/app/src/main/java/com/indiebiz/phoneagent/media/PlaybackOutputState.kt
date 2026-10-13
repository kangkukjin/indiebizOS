package com.indiebiz.phoneagent.media

/** Output acknowledgement belongs to the display, not merely to decoder preparation. */
class PlaybackOutputState {
    var hasVideo = false
    var visible = false
        set(value) { field = value; if (!value) rendered = false }
    var rendered = false
    var paused = false
    var seeking = false
    var ended = false
    val canPlay get() = !paused && !seeking && !ended && (!hasVideo || visible)
    fun playing(playerRunning: Boolean) = canPlay && playerRunning && (!hasVideo || rendered)
    val needsDisplay get() = hasVideo && !visible && !ended
}
