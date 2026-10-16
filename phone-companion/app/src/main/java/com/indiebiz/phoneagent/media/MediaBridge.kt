package com.indiebiz.phoneagent.media

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import org.json.JSONArray
import org.json.JSONObject

/**
 * Python(limb_client.py) → Kotlin 미디어 엔진 다리. Chaquopy 에서
 * `jclass("com.indiebiz.phoneagent.media.MediaBridge").start(json)` 식으로 부른다(PhoneActions 와 같은 꼴).
 *
 * 모든 메서드는 JSON 문자열을 주고받는다 — 영상·음성 프레임은 절대 이 다리를 지나지 않는다(설계 §9).
 * 실패는 계약 코드로 정직하게: permission_required · device_busy · unsupported_track · needs_local_action.
 * `start` 는 화면 준비(최대 5초)와 서비스 접수(최대 3초)를 기다린다. 그 뒤의 협상·상태·품질은
 * 시그널링 WS(SignalingClient) 로 허브에 직접 보고한다 — 작업 결과 통로를 오래 붙들지 않는다.
 */
object MediaBridge {
    const val LIBRARY = "io.github.webrtc-sdk:android"
    const val LIBRARY_VERSION = "144.7559.15"

    @Volatile private var appContext: Context? = null

    /** App.onCreate 에서 1회. */
    @JvmStatic
    fun init(ctx: Context) { appContext = ctx.applicationContext }

    @JvmStatic
    fun callEvent(event: String, sessionJson: String) {
        val ctx = appContext ?: return
        CallActivity.notifySession(ctx, event, JSONObject(sessionJson))
    }

    private fun err(code: String, message: String?, extra: ((JSONObject) -> Unit)? = null): String {
        val o = JSONObject().put("error", code).put("message", message ?: code)
        extra?.invoke(o)
        return o.toString()
    }

    private fun granted(ctx: Context, p: String) = ctx.checkSelfPermission(p) == PackageManager.PERMISSION_GRANTED

    /** 세션 시작 — 접수 여부만 동기로. {"accepted":true,"session_id"} 또는 {"error":<code>,...}. */
    @JvmStatic
    fun start(envelopeJson: String): String {
        val ctx = appContext ?: return err("unavailable", "MediaBridge 미초기화(context 없음)")
        val env = try { MediaEnvelope.parse(envelopeJson) } catch (e: EnvelopeError) {
            return err(e.code, e.message)
        }
        if (CallService.session != null) return err("device_busy", "통화가 진행 중입니다")
        val current = MediaSessionService.currentSessionId()
        if (current != null && current == env.sessionId) {
            return JSONObject().put("accepted", true).put("session_id", current).put("already_active", true).toString()
        }
        if (current != null) return err("device_busy", "다른 미디어 세션이 진행 중입니다") { it.put("active_session", current) }
        env.unsupportedTrack()?.let { t ->
            return err("unsupported_track", "이 폰이 다룰 수 없는 트랙: ${t.kind}/${t.source} ${t.from}→${t.to}") {
                it.put("track", t.toJson())
            }
        }
        val missing = JSONArray()
        if (env.sendsVideo() && !granted(ctx, Manifest.permission.CAMERA)) missing.put("camera")
        if (env.sendsAudio() && !granted(ctx, Manifest.permission.RECORD_AUDIO)) missing.put("record_audio")
        if (missing.length() > 0) {
            return err("permission_required", "폰에서 권한을 허용해 주세요: $missing") { it.put("permissions", missing) }
        }
        if (env.sendsVideo() && !ctx.packageManager.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY)) {
            return err("needs_local_action", "이 폰에 카메라가 없습니다") {
                it.put("needs_local_action", JSONObject().put("code", "camera_unavailable").put("message", "카메라 없음"))
            }
        }
        val needsScreen = (env.sendsVideo() && !CctvState.cameraReady()) ||
            (env.sendsAudio() && !CctvState.microphoneReady())
        val remoteStart = if (needsScreen) RemoteMediaStart.prepare(ctx, env) else null
        if (needsScreen && remoteStart == null) {
            return err("needs_local_action", "폰에서 카메라 대기 모드를 시작해 주세요") {
                it.put("needs_local_action", JSONObject().put("code", "camera_unavailable")
                    .put("reason", "remote_start_unavailable").put("message", "원격 화면 시작이 허용되지 않았습니다. 폰에서 카메라 대기 모드를 열거나 IndieBiz의 다른 앱 위에 표시를 허용해 주세요"))
            }
        }
        val result = MediaSessionService.request(ctx, env, remoteStart?.token)
        if (remoteStart != null) {
            if (!result.optBoolean("accepted")) RemoteMediaStart.release(env.sessionId)
            else if (!RemoteMediaStart.commit(remoteStart)) {
                MediaSessionService.stop(ctx, env.sessionId, "local_display_closed")
                RemoteMediaStart.release(env.sessionId)
                return err("needs_local_action", "폰에서 연결 화면을 닫았습니다. 다시 요청해 주세요")
            }
        }
        return result.toString()
    }

    /** 세션 종료(멱등). {"stopped":true|false,"session_id"} */
    @JvmStatic
    fun stop(sessionId: String?, reason: String?): String {
        val ctx = appContext ?: return err("unavailable", "MediaBridge 미초기화")
        val sid = sessionId?.takeIf { it.isNotEmpty() }
        val cancelledStart = RemoteMediaStart.release(sid)
        val result = MediaSessionService.stop(ctx, sid, reason ?: "hub_stop")
        if (cancelledStart) result.put("stopped", true).put("session_id", sid ?: JSONObject.NULL)
        return result.toString()
    }

    /** 현재 세션 상태 — 없으면 {"session_id":null,"state":"idle"}. */
    @JvmStatic
    fun status(): String = MediaSessionService.statusJson().toString()

    /** 능력 신고(허브 capabilities 의 media_session 칸). 권한 상태는 사실만 — 광고하지 않는다. */
    @JvmStatic
    fun capabilities(): String {
        val ctx = appContext
        val cam = ctx?.packageManager?.hasSystemFeature(PackageManager.FEATURE_CAMERA_ANY) ?: false
        val mic = ctx?.packageManager?.hasSystemFeature(PackageManager.FEATURE_MICROPHONE) ?: false
        val camPerm = ctx?.let { granted(it, Manifest.permission.CAMERA) } ?: false
        val micPerm = ctx?.let { granted(it, Manifest.permission.RECORD_AUDIO) } ?: false
        val is64 = android.os.Process.is64Bit()
        val profile = if (is64) JSONObject().put("width", 1280).put("height", 720).put("fps", 24)
                      else JSONObject().put("width", 640).put("height", 480).put("fps", 15)
        return JSONObject()
            .put("media_session", JSONObject()
                .put("camera", cam).put("microphone", mic).put("speaker", true).put("playback", true)
                .put("video_receive", true).put("video_playback", true)
                .put("screen", false)
                .put("camera_ready", cam && camPerm && CctvState.cameraReady())
                .put("microphone_ready", mic && micPerm && CctvState.microphoneReady())
                .put("armed", CctvState.armed)
                .put("remote_sensor_start", ctx?.let { RemoteMediaStart.available(it) } ?: false)
                .put("active_session", MediaSessionService.currentSessionId())
                .put("video_profile", profile))
            .put("abi", Build.SUPPORTED_ABIS.firstOrNull() ?: "unknown")
            .put("sdk", Build.VERSION.SDK_INT)
            .put("permissions", JSONObject().put("camera", camPerm).put("record_audio", micPerm))
            .put("engine", JSONObject().put("library", LIBRARY).put("version", LIBRARY_VERSION))
            .toString()
    }
}
