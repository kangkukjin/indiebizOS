package com.indiebiz.phoneagent

import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/** gift-wrap 이벤트를 여러 DM 릴레이에 ["EVENT", ev] 로 발행. + REQ 구독 읽기(query). */
object RelayClient {
    private const val TAG = "IndieBizAgent"
    private val client = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .build()

    /**
     * 전 릴레이에 동일 REQ 를 fan-out 하고 EVENT 를 수집·dedup(id 기준) 한다.
     * 파이썬 indienet._query_relays 의 폰 대응물 — accept/파싱은 파이썬이 한다.
     * @param filterJson Nostr REQ 필터 JSON ({kinds, "#t", "#p", limit, since ...})
     * @param relays 조회할 릴레이 wss URL 목록
     * @param timeoutMs 릴레이별 EOSE 대기 최대 시간(ms)
     * @return 수집된 이벤트 객체들의 JSON 배열 문자열 (각 원소 = nostr event)
     */
    @JvmStatic
    fun query(filterJson: String, relays: List<String>, timeoutMs: Long): String {
        val collected = ConcurrentHashMap<String, JSONObject>()
        val latch = CountDownLatch(relays.size)
        val reqId = "q_" + System.nanoTime().toString(16).takeLast(8)
        val reqMsg = JSONArray().put("REQ").put(reqId).put(JSONObject(filterJson)).toString()

        for (relay in relays) {
            try {
                val req = Request.Builder().url(relay).build()
                client.newWebSocket(req, object : WebSocketListener() {
                    override fun onOpen(ws: WebSocket, response: Response) {
                        ws.send(reqMsg)
                    }
                    override fun onMessage(ws: WebSocket, text: String) {
                        try {
                            val arr = JSONArray(text)
                            when (arr.optString(0)) {
                                "EVENT" -> {
                                    val ev = arr.optJSONObject(2)
                                    val id = ev?.optString("id")
                                    if (ev != null && !id.isNullOrEmpty()) collected[id] = ev
                                }
                                "EOSE" -> { ws.close(1000, null) }
                            }
                        } catch (_: Exception) {}
                    }
                    override fun onClosed(ws: WebSocket, code: Int, reason: String) { latch.countDown() }
                    override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) {
                        Log.w(TAG, "query $relay FAIL: ${t.message}")
                        latch.countDown()
                    }
                })
            } catch (e: Exception) {
                Log.w(TAG, "query $relay open FAIL: ${e.message}")
                latch.countDown()
            }
        }
        latch.await(timeoutMs, TimeUnit.MILLISECONDS)
        val out = JSONArray()
        for (ev in collected.values) out.put(ev)
        Log.i(TAG, "query → ${collected.size} events from ${relays.size} relays")
        return out.toString()
    }

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
