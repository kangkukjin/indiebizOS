package com.indiebiz.phoneagent.media

import android.util.Log
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import org.webrtc.IceCandidate
import java.net.InetAddress
import java.security.MessageDigest
import java.security.SecureRandom
import java.security.cert.X509Certificate
import java.util.TreeMap
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicLong
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import javax.net.ssl.SSLContext
import javax.net.ssl.X509TrustManager

/**
 * 허브 시그널링 WS(계약 §5 extension 경로: `/limb/resident/media/{sid}`, limb 인증 + grant).
 *
 * - 첫 프레임 `{"key","installation_id","grant"}`, 이어 `ready`(능력). 이후 §3 모양의 시그널 프레임.
 * - `stream.lan` 이 {url(s), cert_sha256} 을 주면 LAN 주소를 먼저 시도한다 — 인증된 허브 작업으로 받은
 *   지문만 믿는 핀 고정(helper/resident_terminal_lan.go 와 같은 생각). 실패하면 허브 주소.
 * - keepalive 는 lease.keepalive_s 마다, 같은 세대 안에서 증가하는 seq 로. 재접속·ICE 재시작은 세대 +1.
 * - WS 를 잃으면 lease.reconnect_s 동안 지수 백오프로 재시도, 넘기면 onLost — 제어망 상실 = 로컬 종료(설계 §8).
 */
class SignalingClient(private val env: MediaEnvelope, private val listener: Listener) {
    interface Listener {
        fun onReady(reconnected: Boolean)
        fun onIceServers(servers: org.json.JSONArray) {}
        fun onOffer(sdp: String, generation: Int)
        fun onCandidate(candidate: JSONObject)
        fun onCandidatesDone()
        fun onRenegotiate(payload: JSONObject)
        fun onUpdate(changes: JSONObject)
        fun onEnd(reason: String)
        fun onLost(reason: String)
    }

    @Volatile var generation: Int = 0
        private set
    @Volatile var connected: Boolean = false
        private set
    @Volatile var transport: String = "hub"          // lan | hub
        private set
    private val seq = AtomicLong(0)
    private val exec = Executors.newSingleThreadScheduledExecutor()
    private val random = SecureRandom()
    @Volatile private var ws: WebSocket? = null
    @Volatile private var closedByUs = false
    private var keepalive: ScheduledFuture<*>? = null
    private var everConnected = false
    private var lostSinceMs = 0L
    private var backoffS = 1.0
    private val hubClient = OkHttpClient.Builder().pingInterval(15, TimeUnit.SECONDS)
        .readTimeout(0, TimeUnit.MILLISECONDS).connectTimeout(10, TimeUnit.SECONDS).build()

    fun connect() { submitMediaWork { exec.execute { dial(preferLan = true) } } }

    fun bumpGeneration(): Int { generation += 1; seq.set(0); return generation }

    // ── 전송 ────────────────────────────────────────────────────────────────────
    private fun frame(type: String, payload: JSONObject): JSONObject {
        val f = JSONObject().put("v", 1).put("session_id", env.sessionId).put("msg_id", hex(8))
            .put("from", "device").put("to", "hub").put("generation", generation)
            .put("seq", seq.incrementAndGet()).put("expires_at", System.currentTimeMillis() / 1000.0 + 30.0)
            .put("type", type).put("payload", payload)
        env.secret?.let { f.put("mac", mac(it, canonical(f))) }
        return f
    }

    fun send(type: String, payload: JSONObject): Boolean {
        val sock = ws ?: return false
        return try { sock.send(frame(type, payload).toString()) } catch (_: Throwable) { false }
    }

    fun sendState(state: String, path: String?, quality: JSONObject?, needsLocalAction: JSONObject?, extra: JSONObject? = null): Boolean {
        val p = JSONObject().put("state", state).put("path", path ?: JSONObject.NULL)
        p.put("quality", quality ?: JSONObject.NULL)
        if (needsLocalAction != null) p.put("needs_local_action", needsLocalAction)
        extra?.keys()?.forEach { k -> p.put(k, extra.get(k)) }
        return send("state", p)
    }

    fun sendAnswer(sdp: String, fingerprint: String) = send("answer", JSONObject().put("sdp", sdp).put("fingerprint", fingerprint))

    fun sendCandidate(c: IceCandidate) = send("candidate", JSONObject()
        .put("candidate", c.sdp).put("sdpMid", c.sdpMid).put("sdpMLineIndex", c.sdpMLineIndex))

    fun sendEnd(reason: String) = send("end", JSONObject().put("reason", reason))

    fun close() {
        closedByUs = true
        keepalive?.cancel(false)
        try { ws?.close(1000, "device_close") } catch (_: Throwable) {}
        ws = null
        exec.shutdown()
    }

    // ── 접속 ────────────────────────────────────────────────────────────────────
    private fun dial(preferLan: Boolean) {
        if (closedByUs) return
        val lan = env.lan
        if (preferLan && lan != null && lan.certSha256 != null) {
            val url = lanStreamUrl(lan)
            if (url != null) {
                val client = pinnedClient(lan.certSha256)
                if (client != null) { open(url, client, "lan"); return }
            }
        }
        if (env.streamUrl.isEmpty()) { listener.onLost("signaling_unavailable"); return }
        open(env.streamUrl, hubClient, "hub")
    }

    /** LAN 기원(https://사설IPv4[:port]) → wss://.../limb/resident/media/<sid>. 공인 주소·경로 달린 주소는 거부. */
    private fun lanStreamUrl(lan: LanSpec): String? {
        for (base in lan.urls) {
            val u = try { java.net.URI(base) } catch (_: Throwable) { continue }
            val host = u.host ?: continue
            if (u.scheme != "https" && u.scheme != "wss") continue
            if (!u.path.isNullOrEmpty() && u.path != "/") continue
            if (u.query != null || u.userInfo != null) continue
            val ip = try { InetAddress.getByName(host) } catch (_: Throwable) { continue }
            if (ip.address.size != 4 || !(ip.isSiteLocalAddress || ip.isLoopbackAddress)) continue
            val port = if (u.port > 0) ":${u.port}" else ""
            return "wss://$host$port/limb/resident/media/${env.sessionId}"
        }
        return null
    }

    private fun pinnedClient(pinHex: String): OkHttpClient? {
        val pin = try { pinHex.chunked(2).map { it.toInt(16).toByte() }.toByteArray() } catch (_: Throwable) { return null }
        if (pin.size != 32) return null
        val tm = object : X509TrustManager {
            override fun checkClientTrusted(chain: Array<X509Certificate>, authType: String) {}
            override fun checkServerTrusted(chain: Array<X509Certificate>, authType: String) {
                if (chain.isEmpty()) throw java.security.cert.CertificateException("LAN 인증서 없음")
                val digest = MessageDigest.getInstance("SHA-256").digest(chain[0].encoded)
                if (!MessageDigest.isEqual(digest, pin)) throw java.security.cert.CertificateException("LAN 인증서 지문 불일치")
            }
            override fun getAcceptedIssuers(): Array<X509Certificate> = arrayOf()
        }
        return try {
            val ssl = SSLContext.getInstance("TLS").apply { init(null, arrayOf(tm), SecureRandom()) }
            OkHttpClient.Builder().sslSocketFactory(ssl.socketFactory, tm).hostnameVerifier { _, _ -> true }
                .connectTimeout(2, TimeUnit.SECONDS).pingInterval(15, TimeUnit.SECONDS)
                .readTimeout(0, TimeUnit.MILLISECONDS).build()
        } catch (_: Throwable) { null }
    }

    private fun open(url: String, client: OkHttpClient, via: String) {
        if (closedByUs) return
        Log.i(TAG, "시그널링 접속 시도($via)")
        client.newWebSocket(Request.Builder().url(url).build(), object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                val submitted = submitMediaWork { exec.execute {
                    if (closedByUs) { webSocket.close(1000, null); return@execute }
                    ws = webSocket; transport = via; connected = true
                    lostSinceMs = 0L; backoffS = 1.0
                    val auth = JSONObject().put("key", env.authKey).put("installation_id", env.installationId)
                        .put("grant", env.grant)
                    webSocket.send(auth.toString())
                    val caps = try { JSONObject(MediaBridge.capabilities()) } catch (_: Throwable) { JSONObject() }
                    val ready = frame("ready", JSONObject().put("capabilities", caps))
                    ready.put("capabilities", caps)
                    webSocket.send(ready.toString())
                    startKeepalive()
                    val re = everConnected
                    everConnected = true
                    listener.onReady(re)
                } }
                if (submitted == null) webSocket.close(1000, "session_closed")
            }
            override fun onMessage(webSocket: WebSocket, text: String) {
                submitMediaWork { exec.execute { if (!closedByUs) handle(text) } }
            }
            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) { webSocket.close(1000, null) }
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) {
                submitMediaWork { exec.execute { onDown(webSocket, via, "closed:$code:$reason") } }
            }
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                submitMediaWork { exec.execute { onDown(webSocket, via, "failure:${t.javaClass.simpleName}:${t.message}") } }
            }
        })
    }

    private fun onDown(sock: WebSocket, via: String, why: String) {
        if (closedByUs) return
        val wasOurs = ws === sock
        if (!wasOurs && !connected && via == "lan") {           // LAN 시도 실패 → 허브 주소
            Log.i(TAG, "LAN 시그널링 실패($why) — 허브 주소로")
            if (env.streamUrl.isEmpty()) { listener.onLost("signaling_unavailable"); return }
        open(env.streamUrl, hubClient, "hub"); return
        }
        if (!wasOurs && ws != null) return                        // 옛 소켓의 늦은 종료
        ws = null; connected = false
        keepalive?.cancel(false)
        if (lostSinceMs == 0L) lostSinceMs = System.currentTimeMillis()
        val elapsed = (System.currentTimeMillis() - lostSinceMs) / 1000.0
        if (elapsed > env.lease.reconnectS) {
            Log.w(TAG, "시그널링 재접속 포기(${env.lease.reconnectS}s 초과): $why")
            listener.onLost("signaling_unavailable"); return
        }
        Log.i(TAG, "시그널링 끊김($why) — ${backoffS}s 뒤 재시도")
        val delay = (backoffS * 1000).toLong()
        backoffS = (backoffS * 2).coerceAtMost(8.0)
        submitMediaWork { exec.schedule({ dial(preferLan = true) }, delay, TimeUnit.MILLISECONDS) }
    }

    private fun startKeepalive() {
        keepalive?.cancel(false)
        val period = (env.lease.keepaliveS * 1000).toLong()
        keepalive = submitMediaWork {
            exec.scheduleAtFixedRate({ send("keepalive", JSONObject()) }, period, period, TimeUnit.MILLISECONDS)
        }
    }

    // ── 수신 ────────────────────────────────────────────────────────────────────
    private fun handle(text: String) {
        val f = try { JSONObject(text) } catch (_: Throwable) { return }
        f.optJSONObject("error")?.let { e ->
            val code = e.optString("code", "signaling_error")
            Log.w(TAG, "허브 거절: $code ${e.optString("message")}")
            if (code == "session_ended" || code == "invalid_grant" || code == "invalid_registration" || code == "relation_revoked") {
                closedByUs = true; listener.onLost(code)
            }
            return
        }
        val type = f.optString("type")
        if (type == "session") {                                   // 상태 푸시 — content 변경만 소비
            f.optJSONObject("session")?.optJSONObject("content")?.let { listener.onUpdate(JSONObject().put("content", it)) }
            return
        }
        val sid = f.optString("session_id")
        if (sid.isNotEmpty() && sid != env.sessionId) return
        val gen = f.optInt("generation", generation)
        if (gen < generation && type != "end") return             // 낮은 세대는 버린다(§3)
        if (gen > generation) { generation = gen; seq.set(0) }
        val payload = f.optJSONObject("payload") ?: JSONObject()
        payload.optJSONArray("ice_servers")?.let { listener.onIceServers(it) }
        when (type) {
            "offer" -> payload.optString("sdp").takeIf { it.isNotEmpty() }?.let { listener.onOffer(it, gen) }
            "candidate" -> listener.onCandidate(payload)
            "candidates_done" -> listener.onCandidatesDone()
            "renegotiate" -> listener.onRenegotiate(payload)
            "update" -> listener.onUpdate(payload.optJSONObject("changes") ?: payload)
            "end" -> listener.onEnd(payload.optString("reason", "hub_end"))
            "keepalive", "ack", "state" -> {}
            else -> Log.d(TAG, "모르는 프레임 type=$type")
        }
    }

    // ── 보조 ────────────────────────────────────────────────────────────────────
    private fun hex(n: Int): String { val b = ByteArray(n); random.nextBytes(b); return b.joinToString("") { "%02x".format(it) } }

    /** canonical_json: 키 정렬·공백 없음(mac 제외). */
    private fun canonical(o: JSONObject): String {
        val m = TreeMap<String, Any?>()
        o.keys().forEach { k -> if (k != "mac") m[k] = o.get(k) }
        val sb = StringBuilder("{")
        var first = true
        for ((k, v) in m) {
            if (!first) sb.append(','); first = false
            sb.append(JSONObject.quote(k)).append(':').append(canonicalValue(v))
        }
        return sb.append('}').toString()
    }

    private fun canonicalValue(v: Any?): String = when (v) {
        null, JSONObject.NULL -> "null"
        is JSONObject -> canonical(v)
        is org.json.JSONArray -> (0 until v.length()).joinToString(",", "[", "]") { canonicalValue(v.opt(it)) }
        is String -> JSONObject.quote(v)
        is Double -> if (v == Math.floor(v) && !v.isInfinite()) v.toLong().toString() else v.toString()
        else -> v.toString()
    }

    private fun mac(secret: String, data: String): String {
        val m = Mac.getInstance("HmacSHA256")
        m.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
        return m.doFinal(data.toByteArray(Charsets.UTF_8)).joinToString("") { "%02x".format(it) }
    }

    companion object { private const val TAG = "IndieBizMediaSig" }
}
