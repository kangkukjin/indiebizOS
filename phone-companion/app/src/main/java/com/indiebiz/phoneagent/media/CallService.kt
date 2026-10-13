package com.indiebiz.phoneagent.media

import android.app.*
import android.content.*
import android.content.pm.ServiceInfo
import android.media.*
import android.os.*
import androidx.core.app.ServiceCompat

/** Started only by a visible call activity after the user accepts or dials. */
class CallService : Service() {
    companion object { @Volatile var session: CallSession? = null; const val CHANNEL = "media_calls_active" }
    private var focus: AudioFocusRequest? = null
    private var wake: PowerManager.WakeLock? = null
    override fun onBind(intent: Intent?) = null
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == "end") { session?.close(); stopSelf(); return START_NOT_STICKY }
        val id = intent?.getStringExtra("session_id") ?: return START_NOT_STICKY
        if (session != null) return START_NOT_STICKY
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel(CHANNEL, "진행 중인 통화", NotificationManager.IMPORTANCE_LOW))
        val show = PendingIntent.getActivity(this, 0, Intent(this, CallActivity::class.java).putExtra("session_id", id), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val stop = PendingIntent.getService(this, 1, Intent(this, CallService::class.java).setAction("end"), PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notification = Notification.Builder(this, CHANNEL).setSmallIcon(android.R.drawable.sym_call_incoming)
            .setContentTitle("IndieBiz 통화 중").setContentText("눌러서 통화 화면 열기").setContentIntent(show)
            .setOngoing(true).addAction(Notification.Action.Builder(null, "종료", stop).build()).build()
        var type = 0
        if (Build.VERSION.SDK_INT >= 30) {
            type = ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE or ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PLAYBACK
            if (intent.getBooleanExtra("video", false)) type = type or ServiceInfo.FOREGROUND_SERVICE_TYPE_CAMERA
        } else if (Build.VERSION.SDK_INT >= 29) type = ServiceInfo.FOREGROUND_SERVICE_TYPE_MANIFEST
        ServiceCompat.startForeground(this, 1202, notification, type)
        val audio = getSystemService(AudioManager::class.java)
        focus = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN)
            .setAudioAttributes(AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION).build())
            .setOnAudioFocusChangeListener { change -> if (change == AudioManager.AUDIOFOCUS_LOSS) session?.close("audio_focus_lost") }.build()
        audio.requestAudioFocus(focus!!); audio.mode = AudioManager.MODE_IN_COMMUNICATION
        @Suppress("DEPRECATION")
        audio.isSpeakerphoneOn = intent.getBooleanExtra("video", false)
        wake = getSystemService(PowerManager::class.java).newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "indiebiz:call").also { it.acquire() }
        session = CallSession(applicationContext, id) { session = null; stopSelf() }.also { it.start() }
        return START_NOT_STICKY
    }
    override fun onDestroy() {
        session?.close("service_destroyed")
        val audio = getSystemService(AudioManager::class.java)
        focus?.let { audio.abandonAudioFocusRequest(it) }; audio.mode = AudioManager.MODE_NORMAL
        wake?.let { if (it.isHeld) it.release() }
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
}
