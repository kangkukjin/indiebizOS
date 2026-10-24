package com.indiebiz.phoneagent

import org.junit.Assert.*
import org.junit.Test

class HardwareSettingUpdateTest {
    @Test fun onlyAffectedSettingsAreReadTwiceAndWritesHappenOnceInOrder() {
        val values = listOf("mode" to 0, "brightness" to 100)
        val storage = mutableMapOf("mode" to 1, "brightness" to 50)
        val events = mutableListOf<String>()
        val result = HardwareSettingUpdate.apply(values, { key ->
            events.add("read:$key"); storage.getValue(key)
        }, { key, value -> events.add("write:$key"); storage[key] = value; true })
        assertEquals(listOf("read:mode", "read:brightness", "write:mode", "write:brightness", "read:mode", "read:brightness"), events)
        assertEquals(mapOf("mode" to 1, "brightness" to 50), result.before)
        assertEquals(mapOf("mode" to 0, "brightness" to 100), result.after)
        assertTrue(result.verified)
    }

    @Test fun successfulSetterDoesNotReplaceActualReadback() {
        val result = HardwareSettingUpdate.apply(listOf("timeout" to 60000), { 30000 }, { _, _ -> true })
        assertFalse(result.verified)
        assertEquals(30000, result.after["timeout"])
    }

    @Test fun missingSettingDoesNotVerifyFalseOrZero() {
        val result = HardwareSettingUpdate.apply(listOf("rotation" to 0), { -1 }, { _, _ -> true })
        assertFalse(result.verified)
        assertEquals(-1, result.after["rotation"])
    }

    @Test fun partialFailureStopsWithoutReplay() {
        val writes = mutableListOf<String>()
        try {
            HardwareSettingUpdate.apply(listOf("mode" to 0, "brightness" to 100, "extra" to 1), { 1 }, { key, _ ->
                writes.add(key); key != "brightness"
            })
            fail("rejected setting should throw")
        } catch (error: IllegalStateException) { assertTrue(error.message!!.startsWith("setting_rejected: brightness")) }
        assertEquals(listOf("mode", "brightness"), writes)
    }

    @Test fun failedReadbackDoesNotRetryWrites() {
        var reads = 0
        var writes = 0
        try {
            HardwareSettingUpdate.apply(listOf("timeout" to 60000), {
                if (++reads > 1) error("read lost")
                30000
            }, { _, _ -> writes++; true })
            fail("lost observation should throw")
        } catch (error: IllegalStateException) { assertEquals("read lost", error.message) }
        assertEquals(1, writes)
    }
}
