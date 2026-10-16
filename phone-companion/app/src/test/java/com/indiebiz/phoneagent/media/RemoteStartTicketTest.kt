package com.indiebiz.phoneagent.media

import org.junit.Assert.*
import org.junit.Test

class RemoteStartTicketTest {
    @Test fun expiredActivityCannotStartSensors() {
        val ticket = RemoteStartTicket("session", "token", 5000)
        assertFalse(ticket.resume(5000))
        assertFalse(ticket.commit(5000))
    }

    @Test fun closingScreenWakesWaiterAndRejectsLateService() {
        val ticket = RemoteStartTicket("session", "token", 5000)
        ticket.cancel()
        assertEquals(0L, ticket.ready.count)
        assertFalse(ticket.resume(100))
        assertFalse(ticket.commit(101))
        assertFalse(ticket.valid(102))
    }

    @Test fun serviceCannotCommitBeforeScreenResumesOrAfterTimeout() {
        val ticket = RemoteStartTicket("session", "token", 5000)
        assertFalse(ticket.commit(100))
        assertTrue(ticket.resume(4999))
        assertFalse(ticket.commit(5000))
    }

    @Test fun acceptedSessionSurvivesStartupDeadlineButNotLocalClose() {
        val ticket = RemoteStartTicket("session", "token", 5000)
        assertTrue(ticket.resume(100))
        assertTrue(ticket.commit(200))
        assertTrue(ticket.valid(60000))
        ticket.cancel()
        assertFalse(ticket.valid(60001))
        assertFalse(ticket.resume(60002))
    }
}
