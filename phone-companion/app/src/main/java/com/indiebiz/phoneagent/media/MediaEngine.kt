package com.indiebiz.phoneagent.media

import android.content.Context
import android.media.AudioAttributes
import android.media.MediaRecorder
import android.os.Build
import android.util.Log
import org.json.JSONObject
import org.webrtc.AudioSource
import org.webrtc.AudioTrack
import org.webrtc.Camera1Enumerator
import org.webrtc.Camera2Enumerator
import org.webrtc.CameraEnumerator
import org.webrtc.CameraVideoCapturer
import org.webrtc.CandidatePairChangeEvent
import org.webrtc.DataChannel
import org.webrtc.DefaultVideoDecoderFactory
import org.webrtc.DefaultVideoEncoderFactory
import org.webrtc.EglBase
import org.webrtc.IceCandidate
import org.webrtc.MediaConstraints
import org.webrtc.MediaStream
import org.webrtc.PeerConnection
import org.webrtc.PeerConnectionFactory
import org.webrtc.RtpReceiver
import org.webrtc.RtpTransceiver
import org.webrtc.SdpObserver
import org.webrtc.SessionDescription
import org.webrtc.SurfaceTextureHelper
import org.webrtc.VideoSource
import org.webrtc.VideoTrack
import org.webrtc.audio.JavaAudioDeviceModule
import java.math.BigInteger

/**
 * WebRTC 피어(answerer) — 허브(브라우저 엔진)가 항상 offerer(계약 §6).
 * 카메라(Camera2, 미지원 기기는 Camera1)·마이크 캡처와 수신 음성 재생을 쥔다. 프레임은 네이티브 안에서만 흐른다.
 * 품질 프로필: 32비트 몸 640x480@15, 64비트 1280x720@24 — 허브 update 로 내릴 수 있다.
 */
class MediaEngine(private val ctx: Context, private val env: MediaEnvelope, private val listener: Listener) {
    interface Listener {
        fun onLocalCandidate(c: IceCandidate)
        fun onOffer(sdp: String, fingerprint: String) {}
        fun onVideo(track: VideoTrack, local: Boolean) {}
        fun onAnswer(sdp: String, fingerprint: String)
        fun onConnectionState(state: String)          // connecting | active | reconnecting | failed
        fun onPath(path: String)                      // direct | relay
        fun onCameraProblem(code: String, message: String)
    }

    private val egl: EglBase = EglBase.create()
    private var factory: PeerConnectionFactory? = null
    private var adm: JavaAudioDeviceModule? = null
    private var pc: PeerConnection? = null
    private var videoSource: VideoSource? = null
    private var videoTrack: VideoTrack? = null
    private var audioSource: AudioSource? = null
    private var audioTrack: AudioTrack? = null
    private var capturer: CameraVideoCapturer? = null
    private var textureHelper: SurfaceTextureHelper? = null
    private val pendingCandidates = ArrayList<IceCandidate>()
    @Volatile private var remoteSet = false
    @Volatile private var closed = false
    @Volatile var path: String = "direct"
        private set
    val eglContext get() = egl.eglBaseContext
    private var channel: DataChannel? = null
    @Volatile private var lastPong = 0L
    val peerAlive get() = System.currentTimeMillis() - lastPong < 10000
    fun ping() { sendData("ping") }
    private fun sendData(text: String) {
        channel?.takeIf { it.state() == DataChannel.State.OPEN }?.send(
            DataChannel.Buffer(java.nio.ByteBuffer.wrap(text.toByteArray()), false))
    }
    private fun liveness(d: DataChannel) {
        if (d.label() != "liveness") return
        channel = d
        d.registerObserver(object : DataChannel.Observer {
            override fun onBufferedAmountChange(previous: Long) {}
            override fun onStateChange() {}
            override fun onMessage(buffer: DataChannel.Buffer) {
                val bytes = ByteArray(buffer.data.remaining()); buffer.data.get(bytes)
                when (String(bytes)) { "ping" -> sendData("pong"); "pong" -> lastPong = System.currentTimeMillis() }
            }
        })
    }
    @Volatile private var awaitingMedia = true
    private var lastBytes = 0.0
    private var lastStatsTs = 0.0
    var width = if (is64()) 1280 else 640; private set
    var height = if (is64()) 720 else 480; private set
    var fps = if (is64()) 24 else 15; private set

    fun start() {
        env.raw.optJSONObject("quality_profile")?.let { q ->
            width = q.optInt("width", width); height = q.optInt("height", height); fps = q.optInt("fps", fps)
        }
        ensureInit(ctx)
        val music = env.sendsPlaybackAudio()
        val attrs = AudioAttributes.Builder()
            .setUsage(if (env.isCallLike()) AudioAttributes.USAGE_VOICE_COMMUNICATION else AudioAttributes.USAGE_MEDIA)
            .setContentType(if (env.isCallLike()) AudioAttributes.CONTENT_TYPE_SPEECH else AudioAttributes.CONTENT_TYPE_MUSIC)
            .build()
        adm = JavaAudioDeviceModule.builder(ctx)
            .setUseHardwareAcousticEchoCanceler(!music && JavaAudioDeviceModule.isBuiltInAcousticEchoCancelerSupported())
            .setUseHardwareNoiseSuppressor(!music && JavaAudioDeviceModule.isBuiltInNoiseSuppressorSupported())
            .setAudioSource(if (music) MediaRecorder.AudioSource.MIC else MediaRecorder.AudioSource.VOICE_COMMUNICATION)
            .setAudioAttributes(attrs)
            .createAudioDeviceModule()
        val f = PeerConnectionFactory.builder()
            .setAudioDeviceModule(adm)
            .setVideoEncoderFactory(DefaultVideoEncoderFactory(egl.eglBaseContext, true, true))
            .setVideoDecoderFactory(DefaultVideoDecoderFactory(egl.eglBaseContext))
            .createPeerConnectionFactory()
        factory = f
        val cfg = PeerConnection.RTCConfiguration(iceServers()).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_CONTINUALLY
        }
        pc = f.createPeerConnection(cfg, observer) ?: throw IllegalStateException("PeerConnection 생성 실패")
        if (env.localRole == "caller") liveness(pc!!.createDataChannel("liveness", DataChannel.Init()))
        if (env.sendsAudio()) addAudio(f, music)
        if (env.sendsVideo()) addVideo(f)
        if (env.receivesAudio() && !env.sendsAudio()) {
            pc?.addTransceiver(org.webrtc.MediaStreamTrack.MediaType.MEDIA_TYPE_AUDIO,
                RtpTransceiver.RtpTransceiverInit(RtpTransceiver.RtpTransceiverDirection.RECV_ONLY))
        }
        listener.onConnectionState("connecting")
    }

    fun updateIce(servers: org.json.JSONArray) {
        env.raw.put("ice_servers", servers)
        pc?.setConfiguration(PeerConnection.RTCConfiguration(iceServers()).apply {
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            continualGatheringPolicy = PeerConnection.ContinualGatheringPolicy.GATHER_CONTINUALLY
        })
    }
    private fun iceServers(): List<PeerConnection.IceServer> {
        val out = ArrayList<PeerConnection.IceServer>()
        for (i in 0 until (env.raw.optJSONArray("ice_servers") ?: env.iceServers).length()) {
            val s = (env.raw.optJSONArray("ice_servers") ?: env.iceServers).optJSONObject(i) ?: continue
            val urls = ArrayList<String>()
            s.optJSONArray("urls")?.let { a -> for (j in 0 until a.length()) a.optString(j).takeIf { it.isNotEmpty() }?.let { urls.add(it) } }
            s.optString("urls").takeIf { it.isNotEmpty() && s.optJSONArray("urls") == null }?.let { urls.add(it) }
            if (urls.isEmpty()) continue
            val b = PeerConnection.IceServer.builder(urls)
            s.optString("username").takeIf { it.isNotEmpty() }?.let { b.setUsername(it) }
            s.optString("credential").takeIf { it.isNotEmpty() }?.let { b.setPassword(it) }
            out.add(b.createIceServer())
        }
        return out
    }

    private fun addAudio(f: PeerConnectionFactory, music: Boolean) {
        val c = MediaConstraints()
        val on = if (music) "false" else "true"      // 음악 전송엔 음성용 처리(AEC/NS/AGC)를 끈다(설계 §7)
        for (k in listOf("googEchoCancellation", "googNoiseSuppression", "googAutoGainControl", "googHighpassFilter"))
            c.mandatory.add(MediaConstraints.KeyValuePair(k, on))
        audioSource = f.createAudioSource(c)
        audioTrack = f.createAudioTrack("a0", audioSource)
        pc?.addTrack(audioTrack, listOf("indiebiz"))
    }

    private fun addVideo(f: PeerConnectionFactory) {
        val enumerator: CameraEnumerator = if (Camera2Enumerator.isSupported(ctx)) Camera2Enumerator(ctx) else Camera1Enumerator(true)
        val wantFront = env.raw.optString("camera", "back") == "front"
        val names = enumerator.deviceNames
        val name = names.firstOrNull { if (wantFront) enumerator.isFrontFacing(it) else enumerator.isBackFacing(it) }
            ?: names.firstOrNull()
        if (name == null) { listener.onCameraProblem("camera_unavailable", "카메라 장치 없음"); return }
        val cap = enumerator.createCapturer(name, object : CameraVideoCapturer.CameraEventsHandler {
            override fun onCameraError(msg: String) { listener.onCameraProblem("camera_unavailable", msg) }
            override fun onCameraDisconnected() { listener.onCameraProblem("camera_unavailable", "카메라 연결 끊김") }
            override fun onCameraFreezed(msg: String) { listener.onCameraProblem("camera_unavailable", "카메라 멈춤: $msg") }
            override fun onCameraOpening(name: String) {}
            override fun onFirstFrameAvailable() {}
            override fun onCameraClosed() {}
        })
        textureHelper = SurfaceTextureHelper.create("IndieBizCapture", egl.eglBaseContext)
        val src = f.createVideoSource(false)
        cap.initialize(textureHelper, ctx, src.capturerObserver)
        cap.startCapture(width, height, fps)
        videoSource = src; capturer = cap
        videoTrack = f.createVideoTrack("v0", src)
        pc?.addTrack(videoTrack, listOf("indiebiz"))
        videoTrack?.let { listener.onVideo(it, true) }
    }

    // ── 협상(answerer) ──────────────────────────────────────────────────────────
    fun handleOffer(sdp: String) {
        val p = pc ?: return
        remoteSet = false
        p.setRemoteDescription(object : Sdp() {
            override fun onSetSuccess() {
                remoteSet = true
                synchronized(pendingCandidates) { pendingCandidates.forEach { p.addIceCandidate(it) }; pendingCandidates.clear() }
                p.createAnswer(object : Sdp() {
                    override fun onCreateSuccess(desc: SessionDescription) {
                        p.setLocalDescription(object : Sdp() {
                            override fun onSetSuccess() { listener.onAnswer(desc.description, fingerprint(desc.description)) }
                        }, desc)
                    }
                }, MediaConstraints())
            }
        }, SessionDescription(SessionDescription.Type.OFFER, sdp))
    }

    fun createOffer(restart: Boolean = false) {
        val p = pc ?: return
        val constraints = MediaConstraints()
        if (restart) constraints.mandatory.add(MediaConstraints.KeyValuePair("IceRestart", "true"))
        p.createOffer(object : Sdp() {
            override fun onCreateSuccess(desc: SessionDescription) {
                p.setLocalDescription(object : Sdp() {
                    override fun onSetSuccess() { listener.onOffer(desc.description, fingerprint(desc.description)) }
                }, desc)
            }
        }, constraints)
    }

    fun handleAnswer(sdp: String) {
        val p = pc ?: return
        p.setRemoteDescription(object : Sdp() {
            override fun onSetSuccess() {
                remoteSet = true
                synchronized(pendingCandidates) { pendingCandidates.forEach { p.addIceCandidate(it) }; pendingCandidates.clear() }
            }
        }, SessionDescription(SessionDescription.Type.ANSWER, sdp))
    }

    fun addRemoteCandidate(json: JSONObject) {
        val sdp = json.optString("candidate"); if (sdp.isEmpty()) return
        val c = IceCandidate(json.optString("sdpMid", null) ?: "", json.optInt("sdpMLineIndex", 0), sdp)
        if (remoteSet) pc?.addIceCandidate(c) else synchronized(pendingCandidates) { pendingCandidates.add(c) }
    }

    fun restartIce() { try { pc?.restartIce() } catch (t: Throwable) { Log.w(TAG, "restartIce 실패: $t") } }

    // ── 조작 ────────────────────────────────────────────────────────────────────
    fun setMuted(mute: Boolean) { audioTrack?.setEnabled(!mute) }
    fun setCameraEnabled(on: Boolean) { videoTrack?.setEnabled(on) }
    fun switchCamera() { capturer?.switchCamera(null) }
    fun setCaptureFormat(w: Int, h: Int, f: Int) {
        width = w.coerceIn(160, 1920); height = h.coerceIn(120, 1080); fps = f.coerceIn(1, 30)
        try { capturer?.changeCaptureFormat(width, height, fps) } catch (t: Throwable) { Log.w(TAG, "포맷 변경 실패: $t") }
        videoSource?.adaptOutputFormat(width, height, fps)
    }

    /** getStats → 계약 quality 모양 {rtt_ms, loss, jitter_ms, bitrate_kbps, fps, width, height, dropped}. */
    fun collectStats(cb: (JSONObject) -> Unit) {
        val p = pc ?: return
        p.getStats { report ->
            val q = JSONObject()
            var bytes = 0.0; var rtt = 0.0; var lost = 0.0; var jitter = 0.0
            var fpsV = 0.0; var w = 0.0; var h = 0.0; var frames = 0.0; var encoded = 0.0
            var decoded = false
            var relay = false
            val all = report.statsMap.values
            for (s in all) {
                val m = s.members
                when (s.type) {
                    "outbound-rtp" -> {
                        bytes += num(m["bytesSent"])
                        if (m["kind"] == "video") {
                            fpsV = num(m["framesPerSecond"]); w = num(m["frameWidth"]); h = num(m["frameHeight"])
                            encoded = num(m["framesEncoded"])
                        }
                    }
                    "inbound-rtp" -> { decoded = decoded || num(m["framesDecoded"]) > 0 || num(m["totalSamplesReceived"]) > 0 || num(m["totalSamplesDuration"]) > 0; bytes += num(m["bytesReceived"]); lost += num(m["packetsLost"]); jitter = maxOf(jitter, num(m["jitter"])) }
                    "remote-inbound-rtp" -> { lost += num(m["packetsLost"]); jitter = maxOf(jitter, num(m["jitter"])); rtt = maxOf(rtt, num(m["roundTripTime"])) }
                    "media-source" -> if (m["kind"] == "video") frames = num(m["frames"])
                    "candidate-pair" -> if (m["nominated"] == true || m["state"] == "succeeded") {
                        if (num(m["currentRoundTripTime"]) > 0) rtt = num(m["currentRoundTripTime"])
                        val local = report.statsMap[m["localCandidateId"] as? String ?: ""]
                        val remote = report.statsMap[m["remoteCandidateId"] as? String ?: ""]
                        if (local?.members?.get("candidateType") == "relay" || remote?.members?.get("candidateType") == "relay") relay = true
                    }
                }
            }
            val now = report.timestampUs / 1_000_000.0
            val kbps = if (lastStatsTs > 0 && now > lastStatsTs) (bytes - lastBytes) * 8 / 1000.0 / (now - lastStatsTs) else 0.0
            lastBytes = bytes; lastStatsTs = now
            val newPath = if (relay) "relay" else "direct"
            if (newPath != path) { path = newPath; listener.onPath(path) }
            q.put("rtt_ms", Math.round(rtt * 1000)).put("loss", lost.toLong()).put("jitter_ms", Math.round(jitter * 1000))
                .put("bitrate_kbps", Math.round(kbps)).put("fps", Math.round(fpsV)).put("width", w.toLong()).put("height", h.toLong())
                .put("dropped", maxOf(0.0, frames - encoded).toLong())
            val receives = env.receivesAudio() || env.tracks.any { it.toDevice && it.kind == "video" }
            if (awaitingMedia && (if (receives) decoded else bytes > 0)) {
                awaitingMedia = false; listener.onConnectionState("active")
            }
            cb(q)
        }
    }

    fun close() {
        if (closed) return
        closed = true
        try { capturer?.stopCapture() } catch (_: Throwable) {}
        try { capturer?.dispose() } catch (_: Throwable) {}
        try { textureHelper?.dispose() } catch (_: Throwable) {}
        try { channel?.close(); channel?.dispose() } catch (_: Throwable) {}
        try { pc?.close() } catch (_: Throwable) {}
        try { pc?.dispose() } catch (_: Throwable) {}
        for (d in listOf<(() -> Unit)?>({ videoTrack?.dispose() }, { videoSource?.dispose() }, { audioTrack?.dispose() },
                                        { audioSource?.dispose() }, { factory?.dispose() }, { adm?.release() }, { egl.release() }))
            try { d?.invoke() } catch (_: Throwable) {}
        pc = null; factory = null
    }

    // ── 관찰자 ──────────────────────────────────────────────────────────────────
    private val observer = object : PeerConnection.Observer {
        override fun onSignalingChange(s: PeerConnection.SignalingState) {}
        override fun onIceConnectionChange(s: PeerConnection.IceConnectionState) {}
        override fun onIceConnectionReceivingChange(b: Boolean) {}
        override fun onIceGatheringChange(s: PeerConnection.IceGatheringState) {}
        override fun onIceCandidate(c: IceCandidate) { listener.onLocalCandidate(c) }
        override fun onIceCandidatesRemoved(cs: Array<out IceCandidate>) {}
        override fun onAddStream(s: MediaStream) {}
        override fun onRemoveStream(s: MediaStream) {}
        override fun onDataChannel(d: DataChannel) { liveness(d) }
        override fun onRenegotiationNeeded() {}                   // answerer — 허브가 재협상을 연다
        override fun onConnectionChange(s: PeerConnection.PeerConnectionState) {
            when (s) {
                PeerConnection.PeerConnectionState.CONNECTED -> { awaitingMedia = true; listener.onConnectionState("connecting") }
                PeerConnection.PeerConnectionState.DISCONNECTED -> { awaitingMedia = true; listener.onConnectionState("reconnecting") }
                PeerConnection.PeerConnectionState.FAILED -> listener.onConnectionState("failed")
                else -> {}
            }
        }
        override fun onSelectedCandidatePairChanged(e: CandidatePairChangeEvent) {
            val relay = e.local.sdp.contains("typ relay") || e.remote.sdp.contains("typ relay")
            val newPath = if (relay) "relay" else "direct"
            if (newPath != path) { path = newPath; listener.onPath(path) }
        }
        override fun onAddTrack(r: RtpReceiver, streams: Array<out MediaStream>) {
            (r.track() as? AudioTrack)?.setEnabled(true)
            (r.track() as? VideoTrack)?.let { listener.onVideo(it, false) }
        }
    }

    private abstract class Sdp : SdpObserver {
        override fun onCreateSuccess(desc: SessionDescription) {}
        override fun onSetSuccess() {}
        override fun onCreateFailure(e: String) { Log.w(TAG, "SDP 생성 실패: $e") }
        override fun onSetFailure(e: String) { Log.w(TAG, "SDP 적용 실패: $e") }
    }

    companion object {
        private const val TAG = "IndieBizMediaEngine"
        @Volatile private var initialized = false

        @Synchronized fun ensureInit(ctx: Context) {
            if (initialized) return
            PeerConnectionFactory.initialize(PeerConnectionFactory.InitializationOptions.builder(ctx.applicationContext)
                .setEnableInternalTracer(false).createInitializationOptions())
            initialized = true
        }

        fun is64(): Boolean = android.os.Process.is64Bit()

        /** SDP 의 a=fingerprint 를 봉투에도 적는다(계약 §3) — 수신 측이 둘을 대조. */
        fun fingerprint(sdp: String): String =
            sdp.lineSequence().firstOrNull { it.startsWith("a=fingerprint:") }?.removePrefix("a=fingerprint:")?.trim() ?: ""

        private fun num(v: Any?): Double = when (v) {
            null -> 0.0
            is Double -> v
            is Float -> v.toDouble()
            is Long -> v.toDouble()
            is Int -> v.toDouble()
            is BigInteger -> v.toDouble()
            is Number -> v.toDouble()
            else -> 0.0
        }
    }
}
