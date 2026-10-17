package com.indiebiz.phoneagent.media

import org.junit.Assert.assertEquals
import org.junit.Test

class MediaStartPlanTest {
    @Test fun videoReceptionPreparesOutputEvenWhenNoSensorIsReady() {
        assertEquals(MediaStartPlan.OUTPUT_WINDOW,
            MediaStartPlan.forRequest(true, false, false, false, false, true))
    }

    @Test fun duplexVideoUsesOneOutputWindowToPrepareBothDirections() {
        assertEquals(MediaStartPlan.OUTPUT_WINDOW,
            MediaStartPlan.forRequest(true, true, true, false, false, true))
    }

    @Test fun backgroundCameraAndMicrophonePrepareWithoutManualArming() {
        assertEquals(MediaStartPlan.SENSOR_WINDOW,
            MediaStartPlan.forRequest(false, true, false, false, true, false))
        assertEquals(MediaStartPlan.SENSOR_WINDOW,
            MediaStartPlan.forRequest(false, false, true, true, false, false))
    }

    @Test fun backgroundSpeakerAlsoPreparesAWindowWhenServiceStartRequiresIt() {
        assertEquals(MediaStartPlan.SENSOR_WINDOW,
            MediaStartPlan.forRequest(false, false, false, true, true, true))
    }

    @Test fun alreadyReadySensorsNeedNoStandbyScreen() {
        assertEquals(MediaStartPlan.DIRECT,
            MediaStartPlan.forRequest(false, true, true, true, true, false))
    }
}
