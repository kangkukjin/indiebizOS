package com.indiebiz.phoneagent.media

/** A central request prepares its own window. No manually armed state is required. */
internal enum class MediaStartPlan {
    DIRECT, SENSOR_WINDOW, OUTPUT_WINDOW;

    companion object {
        fun forRequest(
            output: Boolean,
            camera: Boolean,
            microphone: Boolean,
            cameraReady: Boolean,
            microphoneReady: Boolean,
            backgroundServiceRestricted: Boolean
        ): MediaStartPlan = when {
            output -> OUTPUT_WINDOW
            (camera && !cameraReady) || (microphone && !microphoneReady) || backgroundServiceRestricted -> SENSOR_WINDOW
            else -> DIRECT
        }
    }
}
