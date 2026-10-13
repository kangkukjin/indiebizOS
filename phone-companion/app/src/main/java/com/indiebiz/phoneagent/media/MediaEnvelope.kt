package com.indiebiz.phoneagent.media

import org.json.JSONArray
import org.json.JSONObject

/**
 * 허브 → 폰 확장관계 봉투(docs/MEDIA_SESSION_CONTRACT.md §6)의 읽기 모델.
 *
 * 봉투 모양: {"op":"media_session","session_id","grant","purpose","tracks","ice_servers","lease",
 *            "stream":{"url","lan"?},"content"?,"timeout"} — limb_client.py 가 여기에 `auth`
 *            ({key, installation_id} = 등록 자격)와 `delivery`·`secret`(있을 때) 를 덧붙여 넘긴다.
 * 파싱 실패는 [EnvelopeError] 로 — 코드는 계약 실패 코드(permission_required 등)가 아니라
 * 봉투 자체의 결함(invalid_envelope)이다.
 */
class EnvelopeError(val code: String, message: String) : IllegalArgumentException(message)

data class TrackSpec(val id: String, val kind: String, val source: String,
                     val from: String, val to: String, val state: String) {
    /** 폰이 보내는 트랙(= 캡처 대상). */
    val fromDevice: Boolean get() = from == "device"
    /** 폰이 받는 트랙(= 출력 대상). */
    val toDevice: Boolean get() = to == "device"

    fun toJson(): JSONObject = JSONObject().put("id", id).put("kind", kind).put("source", source)
        .put("from", from).put("to", to).put("state", state)
}

data class LanSpec(val urls: List<String>, val certSha256: String?)

data class LeaseSpec(val leaseS: Double, val keepaliveS: Double, val reconnectS: Double)

data class ContentSpec(val ref: String, val url: String, val positionS: Double,
                       val paused: Boolean, val volume: Int)

class MediaEnvelope private constructor(val raw: JSONObject) {
    val sessionId: String = raw.optString("session_id")
    val grant: JSONObject = raw.optJSONObject("grant") ?: JSONObject()
    val grantToken: String = grant.optString("token")
    val purpose: String = raw.optString("purpose")
    val delivery: String = raw.optString("delivery", if (raw.has("content")) "content" else "realtime")
    val localRole: String = raw.optString("local_role", "device")
    val tracks: List<TrackSpec> = parseTracks(raw.optJSONArray("tracks")).map {
        if (localRole == "device") it else it.copy(
            from = if (it.from == localRole) "device" else "hub",
            to = if (it.to == localRole) "device" else "hub")
    }
    val iceServers: JSONArray = raw.optJSONArray("ice_servers") ?: JSONArray()
    val lease: LeaseSpec = parseLease(raw.optJSONObject("lease"))
    val streamUrl: String = raw.optJSONObject("stream")?.optString("url") ?: ""
    val lan: LanSpec? = parseLan(raw.optJSONObject("stream")?.opt("lan"))
    val content: ContentSpec? = parseContent(raw.optJSONObject("content"))
    /** 세션 비밀(일반 통화 §3 mac 용) — 확장관계 봉투엔 보통 없다. 있으면 프레임에 mac 을 싣는다. */
    val secret: String? = raw.optString("secret").takeIf { it.isNotEmpty() }
    val authKey: String = raw.optJSONObject("auth")?.optString("key") ?: ""
    val installationId: String = raw.optJSONObject("auth")?.optString("installation_id") ?: ""
    val timeoutS: Double = raw.optDouble("timeout", 86400.0)

    /** 허브 HTTP 기원 — stream.url(wss://host[:port]/limb/resident/media/<sid>) 에서 거꾸로 만든다. */
    val hubBase: String get() {
        val u = streamUrl
        val schemeEnd = u.indexOf("://")
        if (schemeEnd < 0) return ""
        val scheme = if (u.startsWith("wss")) "https" else "http"
        val rest = u.substring(schemeEnd + 3)
        val host = rest.substringBefore('/')
        return "$scheme://$host"
    }

    /** 콘텐츠 절대 주소(허브 기원 + /media/content/<ref>?token=<grant.token>). 이미 절대면 그대로. */
    fun contentUrl(): String? {
        val c = content ?: return null
        var url = c.url
        if (url.isEmpty() && c.ref.isNotEmpty()) url = "/media/content/${c.ref}"
        if (url.isEmpty()) return null
        if (url.startsWith("/")) url = hubBase + url
        if (!url.contains("token=") && grantToken.isNotEmpty()) {
            url += (if (url.contains('?')) "&" else "?") + "token=" + grantToken
        }
        return url
    }

    fun sendsVideo(): Boolean = tracks.any { it.fromDevice && it.kind == "video" }
    fun sendsAudio(): Boolean = tracks.any { it.fromDevice && it.kind == "audio" }
    fun receivesVideo(): Boolean = tracks.any { it.toDevice && it.kind == "video" }
    fun receivesAudio(): Boolean = tracks.any { it.toDevice && it.kind == "audio" }
    /** 음악 전송(playback 소스) — 음성용 AEC/NS 를 끈다(설계 §7). */
    fun sendsPlaybackAudio(): Boolean = tracks.any { it.fromDevice && it.kind == "audio" && it.source == "playback" }
    /** 통화류(음성 왕복) = VOICE_COMMUNICATION, 스피커·재생 = MEDIA. */
    fun isCallLike(): Boolean = purpose == "voice_call" || purpose == "video_call" || purpose == "microphone"
    /** 콘텐츠 전달(폰이 직접 디코딩) — WebRTC 피어가 필요 없다. */
    fun isContentDelivery(): Boolean = delivery == "content" && content != null
    /** WebRTC 피어가 필요한가(폰이 보내거나 받는 실시간 트랙이 하나라도). */
    fun needsPeer(): Boolean = !isContentDelivery() && tracks.any { it.fromDevice || it.toDevice }

    /** 수신 영상은 미디어 화면에 표시한다. 폰 화면 송출은 아직 지원하지 않는다. */
    fun unsupportedTrack(): TrackSpec? = tracks.firstOrNull {
        (it.kind != "audio" && it.kind != "video") ||
            (it.fromDevice && it.source == "screen") ||
            (it.fromDevice && it.kind == "video" && it.source != "camera") ||
            (it.fromDevice && it.kind == "audio" && it.source != "mic" && it.source != "playback")
    }

    companion object {
        private val PURPOSES = setOf("voice_call", "video_call", "camera", "microphone", "speaker", "playback")

        /** Local authenticated call API snapshot, not an extension enrollment envelope. */
        fun call(session: JSONObject): MediaEnvelope {
            require(session.optString("kind") == "call")
            require(session.optString("local_role") in setOf("caller", "callee"))
            return MediaEnvelope(session)
        }

        fun parse(json: String): MediaEnvelope {
            val obj = try { JSONObject(json) } catch (e: Exception) {
                throw EnvelopeError("invalid_envelope", "봉투가 JSON 객체가 아닙니다")
            }
            val env = MediaEnvelope(obj)
            if (env.sessionId.length < 8) throw EnvelopeError("invalid_envelope", "session_id 없음")
            if (env.grantToken.isEmpty()) throw EnvelopeError("invalid_envelope", "grant.token 없음")
            if (env.purpose !in PURPOSES) throw EnvelopeError("invalid_envelope", "purpose 모름: ${env.purpose}")
            if (!env.streamUrl.startsWith("ws://") && !env.streamUrl.startsWith("wss://") && env.lan == null)
                throw EnvelopeError("invalid_envelope", "stream.url 이 ws(s):// 가 아닙니다")
            if (env.authKey.isEmpty() || env.installationId.isEmpty())
                throw EnvelopeError("invalid_envelope", "auth(key, installation_id) 없음")
            if (env.tracks.isEmpty() && !env.isContentDelivery())
                throw EnvelopeError("invalid_envelope", "tracks 도 content 도 없음")
            return env
        }

        private fun parseTracks(arr: JSONArray?): List<TrackSpec> {
            val out = ArrayList<TrackSpec>()
            if (arr == null) return out
            for (i in 0 until arr.length()) {
                val t = arr.optJSONObject(i) ?: continue
                out.add(TrackSpec(t.optString("id", "t$i"), t.optString("kind"), t.optString("source"),
                    t.optString("from"), t.optString("to"), t.optString("state", "requested")))
            }
            return out
        }

        private fun parseLease(o: JSONObject?): LeaseSpec = LeaseSpec(
            o?.optDouble("lease_s", 20.0) ?: 20.0,
            (o?.optDouble("keepalive_s", 5.0) ?: 5.0).coerceAtLeast(1.0),
            (o?.optDouble("reconnect_s", 30.0) ?: 30.0).coerceAtLeast(1.0))

        private fun parseLan(v: Any?): LanSpec? {
            val o = v as? JSONObject ?: return null
            val urls = ArrayList<String>()
            o.optString("url").takeIf { it.isNotEmpty() }?.let { urls.add(it) }
            o.optJSONArray("urls")?.let { a -> for (i in 0 until a.length()) a.optString(i).takeIf { it.isNotEmpty() }?.let { urls.add(it) } }
            val pin = (o.optString("cert_sha256").takeIf { it.isNotEmpty() } ?: o.optString("sha256").takeIf { it.isNotEmpty() })
            if (urls.isEmpty()) return null
            return LanSpec(urls.take(8), pin)
        }

        private fun parseContent(o: JSONObject?): ContentSpec? {
            o ?: return null
            return ContentSpec(o.optString("ref"), o.optString("url"), o.optDouble("position_s", 0.0),
                o.optBoolean("paused", false), o.optInt("volume", 80).coerceIn(0, 100))
        }
    }
}
