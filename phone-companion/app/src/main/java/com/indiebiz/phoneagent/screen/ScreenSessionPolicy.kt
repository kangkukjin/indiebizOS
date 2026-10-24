package com.indiebiz.phoneagent.screen

import okhttp3.OkHttpClient

/** The hub's application heartbeat owns liveness, including while a busy phone uploads frames. */
internal object ScreenSessionPolicy {
    fun canOpenConsent(sdk: Int, overlayGranted: Boolean) = sdk < 29 || overlayGranted

    fun heartbeatExpired(now: Long, lastMessage: Long) = now - lastMessage > 20_000

    fun client(): OkHttpClient = OkHttpClient.Builder().build()
    // Do not add a short OkHttp pingInterval: it is also the pong deadline. It can
    // terminate a live stream after 5s of upload/UI contention, before the 20s
    // heartbeat lease expires. The server already sends heartbeats every second;
    // ScreenBridge.run closes an actually silent connection independently.
}
