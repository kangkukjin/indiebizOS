package com.indiebiz.phoneagent.media

import com.chaquo.python.Python
import okhttp3.*
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Persistent authenticated NIP-17 receive path, independent of chat polling and extension grants. */
object CallInbox {
    private val http = OkHttpClient.Builder().pingInterval(20, TimeUnit.SECONDS).build()
    private val worker = Executors.newSingleThreadScheduledExecutor()
    private val sockets = mutableMapOf<String, WebSocket>()
    private var identity = ""
    @JvmStatic @Synchronized fun start(relays: String, pub: String) {
        if (identity == pub && sockets.isNotEmpty()) return
        sockets.values.forEach { it.cancel() }; sockets.clear(); identity = pub
        val list = JSONArray(relays)
        for (i in 0 until list.length()) connect(list.getString(i), pub)
    }
    @Synchronized private fun connect(url: String, pub: String) {
        if (identity != pub || !url.startsWith("wss://")) return
        val ws = http.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) {
                ws.send(JSONArray().put("REQ").put("calls").put(JSONObject()
                    .put("kinds", JSONArray().put(1059)).put("#p", JSONArray().put(pub)).put("limit", 50)).toString())
            }
            override fun onMessage(ws: WebSocket, text: String) {
                if (text.length > 262144) return
                try {
                    val msg = JSONArray(text)
                    if (msg.optString(0) != "EVENT") return
                    val event = msg.getJSONObject(2).toString()
                    worker.execute { try {
                        Python.getInstance().getModule("phone_media").callAttr("receive_event", event)
                    } catch (_: Exception) { /* invalid gift-wraps are never invitations */ } }
                } catch (_: Exception) { }
            }
            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) = retry()
            override fun onClosed(ws: WebSocket, code: Int, reason: String) = retry()
            private fun retry() { worker.schedule({ connect(url, pub) }, 5, TimeUnit.SECONDS) }
        })
        sockets[url] = ws
    }
}
