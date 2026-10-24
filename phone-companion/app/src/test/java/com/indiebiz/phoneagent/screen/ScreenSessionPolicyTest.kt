package com.indiebiz.phoneagent.screen

import org.junit.Assert.*
import org.junit.Test

class ScreenSessionPolicyTest {
    @Test fun android9CanReconnectWithoutAnOverlayGrant() {
        assertTrue(ScreenSessionPolicy.canOpenConsent(28, false))
        assertFalse(ScreenSessionPolicy.canOpenConsent(29, false))
        assertTrue(ScreenSessionPolicy.canOpenConsent(29, true))
    }

    @Test fun busyUploadDoesNotInstallAShorterPongDeadlineThanTheHeartbeatLease() {
        val client = ScreenSessionPolicy.client()
        assertEquals(0, client.pingIntervalMillis)
        assertFalse(ScreenSessionPolicy.heartbeatExpired(6_000, 0))
        assertFalse(ScreenSessionPolicy.heartbeatExpired(20_000, 0))
        assertTrue(ScreenSessionPolicy.heartbeatExpired(20_001, 0))
        assertFalse(ScreenSessionPolicy.heartbeatExpired(21_000, 20_000))
    }
}
