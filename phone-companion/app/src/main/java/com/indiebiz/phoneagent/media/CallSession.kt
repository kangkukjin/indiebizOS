package com.indiebiz.phoneagent.media

import android.content.Context
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONObject
import org.webrtc.IceCandidate
import org.webrtc.VideoTrack
import java.util.UUID
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit

/** Native peer with the same local API used by the desktop call window. */
class CallSession(private val ctx: Context, val id: String, private val ended: () -> Unit) : MediaEngine.Listener {
    companion object {
        val http = OkHttpClient.Builder().pingInterval(10, TimeUnit.SECONDS).build()
        const val BASE = "http://127.0.0.1:8765"
        fun request(path: String, body: JSONObject? = null): JSONObject {
            val builder = Request.Builder().url(BASE + path)
            if (body != null) builder.post(body.toString().toRequestBody("application/json".toMediaType()))
            return http.newCall(builder.build()).execute().use {
                val json = JSONObject(it.body?.string() ?: "{}")
                if (!it.isSuccessful || !json.optBoolean("success", true))
                    throw IllegalStateException(json.optJSONObject("error")?.optString("message") ?: "통화 요청 실패")
                json
            }
        }
    }
    val work = Executors.newSingleThreadScheduledExecutor()
    var engine: MediaEngine? = null; private set
    var localVideo: VideoTrack? = null; private set
    var remoteVideo: VideoTrack? = null; private set
    @Volatile var state = "connecting"; private set
    @Volatile var snapshot = JSONObject(); private set
    private var role = ""
    private var socket: WebSocket? = null
    private var generation = 0
    private var seq = 0
    @Volatile private var closed = false
    private var connected = false
    private var lostAt = 0L
    private val outgoing = ArrayList<String>()
    private var offered = false
    private var remoteSdp = ""
    var changed: (() -> Unit)? = null
    fun start() { enqueue {
        try {
            snapshot = request("/media/sessions/$id").getJSONObject("session")
            role = snapshot.getString("local_role")
            require(snapshot.getString("kind") == "call")
            require(snapshot.optString("state") in setOf("inviting", "accepted", "connecting", "active", "reconnecting"))
            require(role == "caller" || snapshot.getString("state") != "inviting")
            generation = snapshot.optInt("generation")
            engine = MediaEngine(ctx, MediaEnvelope.call(snapshot), this).also { it.start() }
            connect()
            work.scheduleAtFixedRate({ tick() }, 2, 2, TimeUnit.SECONDS)
        } catch (e: Exception) { finish("start_failed: ${e.message}") }
    } }
    private fun enqueue(action: () -> Unit) {
        if (closed || work.isShutdown) return
        try { work.execute(action) } catch (_: java.util.concurrent.RejectedExecutionException) { }
    }
    private fun connect() {
        if (closed) return
        socket = http.newWebSocket(Request.Builder().url("ws://127.0.0.1:8765/media/sessions/$id/ws").build(), object : WebSocketListener() {
            override fun onOpen(ws: WebSocket, response: Response) { enqueue {
                if (closed) { ws.close(1000, "ended"); return@enqueue }
                connected = true; lostAt = 0
                outgoing.forEach { ws.send(it) }; outgoing.clear()
                if (!offered && role == "caller") { offered = true; engine?.createOffer() }
            } }
            override fun onMessage(ws: WebSocket, text: String) { enqueue { if (!closed) receive(JSONObject(text)) } }
            override fun onFailure(ws: WebSocket, t: Throwable, response: Response?) { reconnect() }
            override fun onClosed(ws: WebSocket, code: Int, reason: String) { reconnect() }
            private fun reconnect() { if (!closed) enqueue {
                connected = false
                if (lostAt == 0L) lostAt = System.currentTimeMillis()
                state = "reconnecting"; changed?.invoke()
                work.schedule({ connect() }, 1, TimeUnit.SECONDS)
            } }
        })
    }
    private fun receive(f: JSONObject) {
        when (f.optString("type")) {
            "session" -> {
                snapshot = f.getJSONObject("session")
                if (snapshot.optString("state") == "ended") { finish(snapshot.optString("end_reason"), false); return }
                if (role == "callee") snapshot.optJSONObject("pending_offer")?.let { offer(it) }
                changed?.invoke()
            }
            "offer" -> { generation = maxOf(generation, f.optInt("generation")); offer(f.getJSONObject("payload")) }
            "answer" -> engine?.handleAnswer(f.getJSONObject("payload").getString("sdp"))
            "candidate" -> engine?.addRemoteCandidate(f.getJSONObject("payload"))
            "renegotiate" -> if (role == "caller") { generation++; restartOffer() }
            "end" -> finish(f.optJSONObject("payload")?.optString("reason") ?: "remote_end", false)
            "error", "rejected" -> finish(f.optString("reason", "signaling_failed"))
        }
    }
    private fun restartOffer() {
        try { engine?.updateIce(request("/media/ice-config?session_id=$id").getJSONArray("ice_servers")) }
        catch (_: Exception) { /* current credentials remain available for a brief outage */ }
        engine?.createOffer(true)
    }
    private fun offer(payload: JSONObject) {
        payload.optJSONArray("ice_servers")?.let { engine?.updateIce(it) }
        val sdp = payload.optString("sdp")
        if (sdp.isNotEmpty() && sdp != remoteSdp) { remoteSdp = sdp; engine?.handleOffer(sdp) }
    }
    private fun send(type: String, payload: JSONObject) {
        if (closed) return
        seq++
        val frame = JSONObject().put("v", 1).put("session_id", id).put("msg_id", UUID.randomUUID().toString())
            .put("from", role).put("to", if (role == "caller") "callee" else "caller").put("generation", generation)
            .put("seq", seq).put("expires_at", System.currentTimeMillis() / 1000 + 60).put("type", type).put("payload", payload).toString()
        if (!connected || socket?.send(frame) != true) outgoing.add(frame)
    }
    private fun tick() {
        if (closed) return
        if (lostAt > 0 && System.currentTimeMillis() - lostAt > 30000) { finish("signaling_unavailable"); return }
        engine?.ping()
        send("keepalive", JSONObject().put("peer_alive", engine?.peerAlive == true))
        engine?.collectStats { q -> if (!closed) enqueue {
            send("state", JSONObject().put("state", state).put("quality", q).put("path", engine?.path))
        } }
    }
    override fun onLocalCandidate(c: IceCandidate) { enqueue { send("candidate", JSONObject()
        .put("candidate", c.sdp).put("sdpMid", c.sdpMid).put("sdpMLineIndex", c.sdpMLineIndex)) } }
    override fun onAnswer(sdp: String, fingerprint: String) { enqueue { send("answer", JSONObject().put("sdp", sdp).put("fingerprint", fingerprint)) } }
    override fun onOffer(sdp: String, fingerprint: String) { enqueue { send("offer", JSONObject().put("sdp", sdp).put("fingerprint", fingerprint)) } }
    override fun onVideo(track: VideoTrack, local: Boolean) {
        if (local) localVideo = track else remoteVideo = track
        changed?.invoke()
    }
    override fun onConnectionState(state: String) { enqueue {
        this.state = if (state == "failed") "reconnecting" else state
        if (state == "failed") {
            generation++
            if (role == "caller") restartOffer()
            else send("renegotiate", JSONObject().put("ice_restart", true))
        }
        changed?.invoke()
    } }
    override fun onPath(path: String) {}
    override fun onCameraProblem(code: String, message: String) { enqueue { finish("$code: $message") } }
    fun close(reason: String = "local_end") { if (!closed && !work.isShutdown) enqueue { finish(reason) } }
    private fun finish(reason: String, notify: Boolean = true) {
        if (closed) return
        if (notify) try { request("/media/sessions/$id/end", JSONObject().put("reason", reason)) } catch (_: Exception) { }
        closed = true; state = "ended"
        socket?.close(1000, "ended")
        engine?.close(); engine = null
        changed?.invoke(); ended()
        work.shutdown()
    }
}
