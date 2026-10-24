package com.indiebiz.phoneagent.execution

import org.junit.Assert.*
import org.junit.Test

class ProcessDescendantsTest {
    @Test fun stableTreeStopsAfterOnePass() {
        var scans = 0
        val result = ProcessDescendants.collect(1, "a", { scans++; emptyList() }, { fail("no child") })
        assertEquals(mapOf(1 to "a"), result)
        assertEquals(1, scans)
    }
    @Test fun reversedDescendantsAreFoundAndFrozenBeforeStopping() {
        var scans = 0
        val frozen = mutableListOf<Int>()
        val result = ProcessDescendants.collect(1, "a", {
            scans++; listOf(Triple(3, 2, "c"), Triple(2, 1, "b"), Triple(9, 8, "z"))
        }, { frozen.add(it) })
        assertEquals(mapOf(1 to "a", 2 to "b", 3 to "c"), result)
        assertEquals(listOf(2, 3), frozen)
        assertEquals(3, scans)
    }
    @Test fun growingTreeHasBoundedScans() {
        var scans = 0
        ProcessDescendants.collect(1, "a", {
            scans++; listOf(Triple(scans + 1, scans, "birth-$scans"))
        }, {})
        assertEquals(8, scans)
    }
}
