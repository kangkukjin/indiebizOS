package com.indiebiz.phoneagent.screen

import org.junit.Assert.*
import org.junit.Test

class PointerStrokeTest {
    @Test fun releaseBuildsDragAndResetCancelsIt() {
        val input = PointerStroke()
        assertNull(input.pointer(.1, .2, 0, 0))
        assertNull(input.pointer(.1, .2, 1, 100))
        assertNull(input.pointer(.4, .6, 1, 250))
        val drag = input.pointer(.9, .8, 0, 500)!!
        assertEquals(400L, drag.duration)
        assertEquals(listOf(PointerStroke.Point(.1, .2), PointerStroke.Point(.4, .6), PointerStroke.Point(.9, .8)), drag.points)
        input.pointer(.1, .2, 1, 600)
        input.reset()
        assertNull(input.pointer(.9, .8, 0, 700))
    }
    @Test fun boundedHoldAndMotionAndInvalidCoordinates() {
        val input = PointerStroke()
        repeat(10000) { input.pointer(.5, .5, 1, it.toLong()) }
        val hold = input.pointer(.5, .5, 0, 20000)!!
        assertEquals(3000L, hold.duration)
        assertTrue(hold.points.size <= 513)
        assertThrows(IllegalArgumentException::class.java) { input.pointer(Double.NaN, .5, 1, 0) }
        assertThrows(IllegalArgumentException::class.java) { input.pointer(1.1, .5, 1, 0) }
    }
}
