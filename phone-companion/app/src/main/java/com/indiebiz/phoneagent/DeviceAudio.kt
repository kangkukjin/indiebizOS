package com.indiebiz.phoneagent

import android.content.Context
import android.media.AudioManager
import org.json.JSONObject

/** STREAM_MUSIC belongs to the device, independently of any player's lifetime. */
object DeviceAudio {
    private fun manager(ctx: Context) = ctx.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    @JvmStatic fun state(ctx: Context): JSONObject {
        val am = manager(ctx)
        val actual = am.getStreamVolume(AudioManager.STREAM_MUSIC)
        val max = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
        return JSONObject().put("stream", "music").put("actual", actual).put("max", max)
            .put("volume", if (max > 0) Math.round(actual * 100f / max) else 0)
            .put("fixed", am.isVolumeFixed)
    }

    @JvmStatic fun setPercent(ctx: Context, percent: Int): JSONObject {
        require(percent in 0..100) { "volume_must_be_0_to_100" }
        val am = manager(ctx)
        check(!am.isVolumeFixed) { "fixed_volume" }
        val step = Math.round(am.getStreamMaxVolume(AudioManager.STREAM_MUSIC) * percent / 100f)
        am.setStreamVolume(AudioManager.STREAM_MUSIC, step, 0)
        val state = state(ctx).put("requested_volume", percent).put("requested", step)
        return state.put("applied", state.getInt("actual") == step)
    }

    /** Replaying a start envelope after reconnect must not replay an old volume intent. */
    @Synchronized fun startSession(ctx: Context, id: String, volume: Int?) {
        val prefs = ctx.getSharedPreferences("media_volume_intents", Context.MODE_PRIVATE)
        if (prefs.contains(id)) return
        if (volume != null) {
            check(setPercent(ctx, volume).getBoolean("applied")) { "volume_not_applied" }
        }
        val edit = prefs.edit()
        if (prefs.all.size >= 256) {
            prefs.all.entries.sortedBy { (it.value as? Long) ?: 0L }.take(128).forEach { edit.remove(it.key) }
        }
        check(edit.putLong(id, System.currentTimeMillis()).commit()) { "volume_intent_not_saved" }
    }
}
