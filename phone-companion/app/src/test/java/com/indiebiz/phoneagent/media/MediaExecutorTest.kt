package com.indiebiz.phoneagent.media

import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.junit.Assert.*
import org.junit.Test

class MediaExecutorTest {
    @Test fun lateSocketCallbacksAndTimersAfterCloseAreIgnored() {
        val executor = Executors.newSingleThreadScheduledExecutor()
        executor.shutdown()
        assertTrue(executor.awaitTermination(1, TimeUnit.SECONDS))
        assertNull(submitMediaWork { executor.execute { fail("late socket callback ran") } })
        assertNull(submitMediaWork { executor.schedule({ fail("reconnect ran") }, 0, TimeUnit.SECONDS) })
        assertNull(submitMediaWork { executor.scheduleAtFixedRate({ fail("heartbeat ran") }, 0, 1, TimeUnit.SECONDS) })
    }

    @Test fun workBeforeCloseStillRuns() {
        val executor = Executors.newSingleThreadExecutor()
        try {
            val result = submitMediaWork { executor.submit<Int> { 42 } }
            assertEquals(42, result!!.get(1, TimeUnit.SECONDS))
        } finally { executor.shutdownNow() }
    }

    @Test(expected = IllegalStateException::class)
    fun unrelatedErrorsAreNotHidden() {
        submitMediaWork<Unit> { throw IllegalStateException("broken submission") }
    }
}
