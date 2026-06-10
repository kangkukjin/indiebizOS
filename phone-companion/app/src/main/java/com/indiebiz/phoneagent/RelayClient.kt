package com.indiebiz.phoneagent

import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.TimeUnit

/** gift-wrap 이벤트를 여러 DM 릴레이에 ["EVENT", ev] 로 발행. */
object RelayClient {
    private const val TAG = "IndieBizAgent"
    private val client = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .build()

    fun publish(eventJson: String, relays: List<String>) {
        val msg = JSONArray().put("EVENT").put(JSONObject(eventJson)).toString()
        for (relay in relays) {
            val req = Request.Builder().url(relay).build()
            client.newWebSocket(req, object : WebSocketListener() {
                override fun onOpen(ws: WebSocket, response: Response) {
                    ws.send(msg)
                    Log.i(TAG, "relay $relay <- EVENT")
                }
                override fun onMessage(ws: WebSocket, text: String) {
                    Log.i(TAG, "relay $relay -> $text")   // ["OK", id, true, ""] 기대
                    ws.close(1000, null)
                }
                override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                    Log.w(TAG, "relay $relay FAIL: ${t.message}")
                }
            })
        }
    }
}
