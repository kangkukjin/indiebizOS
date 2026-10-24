package com.indiebiz.phoneagent.screen

import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.graphics.*
import android.hardware.display.DisplayManager
import android.hardware.display.VirtualDisplay
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.*
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager
import androidx.core.app.ServiceCompat
import java.io.ByteArrayOutputStream
import kotlin.math.roundToInt

/** Bounded latest-frame capture, 5fps JPEG, shared PC viewer wire format. */
class ScreenCaptureService : Service() {
    private var session: ScreenSession? = null
    private var projection: MediaProjection? = null
    private var projectionCallback: MediaProjection.Callback? = null
    private var display: VirtualDisplay? = null
    private var reader: ImageReader? = null
    private val thread = HandlerThread("phone-screen")
    private lateinit var handler: Handler
    private var width = 0
    private var height = 0
    private var pixelsWidth = 0
    private var pixelsHeight = 0
    private var lastFrame = 0L
    override fun onBind(intent: Intent?): IBinder? = null
    override fun onCreate() { super.onCreate(); thread.start(); handler = Handler(thread.looper) }
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val s = ScreenBridge.current?.takeIf { it.active && it.id == intent?.getStringExtra("screen_id") }
        if (intent?.action == "stop") { s?.end(); stopSelf(); return START_NOT_STICKY }
        if (s == null) { stopSelf(); return START_NOT_STICKY }
        if (session != null) return START_NOT_STICKY
        session = s; s.capture = this
        try {
            ServiceCompat.startForeground(this, ScreenBridge.NOTICE, ScreenBridge.notification(this, s.id, true),
                if (Build.VERSION.SDK_INT >= 29) ServiceInfo.FOREGROUND_SERVICE_TYPE_MEDIA_PROJECTION else 0)
            @Suppress("DEPRECATION") val data = intent?.getParcelableExtra<Intent>("capture_data") ?: error("missing consent")
            projection = getSystemService(MediaProjectionManager::class.java)
                .getMediaProjection(intent.getIntExtra("result_code", 0), data)
            projectionCallback = object : MediaProjection.Callback() {
                override fun onStop() { s.end("denied") }
                override fun onCapturedContentResize(w: Int, h: Int) {
                    // Input coordinates are display coordinates: reject an OEM app-only capture.
                    val metrics = metrics()
                    if (w != metrics.widthPixels || h != metrics.heightPixels) s.end("capture_failed")
                }
            }
            projection!!.registerCallback(projectionCallback!!, handler)
            handler.post {
                try { resize(); s.capturing = true; handler.post(tick) }
                catch (e: Exception) { fail("start", e) }
            }
        } catch (e: Exception) { fail("projection", e); stopSelf() }
        return START_NOT_STICKY
    }
    @Suppress("DEPRECATION") private fun metrics() = DisplayMetrics().also {
        getSystemService(WindowManager::class.java).defaultDisplay.getRealMetrics(it)
    }
    private val tick = object : Runnable {
        override fun run() {
            if (session?.active != true) return
            try {
                val m = metrics()
                if (m.widthPixels != pixelsWidth || m.heightPixels != pixelsHeight) resize()
                handler.postDelayed(this, 250)
            } catch (e: Exception) { fail("resize", e) }
        }
    }
    private fun resize() {
        val m = metrics()
        pixelsWidth = m.widthPixels; pixelsHeight = m.heightPixels
        val scale = minOf(1.0, 1280.0 / maxOf(pixelsWidth, pixelsHeight))
        width = (pixelsWidth * scale).roundToInt(); height = (pixelsHeight * scale).roundToInt()
        val old = reader
        val next = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        reader = next
        next.setOnImageAvailableListener({ source ->
            val image = source.acquireLatestImage() ?: return@setOnImageAvailableListener
            try {
                val now = SystemClock.elapsedRealtime()
                if (source !== reader || session?.active != true || now - lastFrame < 200) return@setOnImageAvailableListener
                lastFrame = now
                val plane = image.planes[0]
                val padded = Bitmap.createBitmap(plane.rowStride / plane.pixelStride, image.height, Bitmap.Config.ARGB_8888)
                try {
                    padded.copyPixelsFromBuffer(plane.buffer)
                    val cropped = Bitmap.createBitmap(padded, 0, 0, image.width, image.height)
                    try {
                        val out = ByteArrayOutputStream()
                        cropped.compress(Bitmap.CompressFormat.JPEG, 65, out)
                        session?.frame(out.toByteArray(), pixelsWidth, pixelsHeight)
                    } finally { if (cropped !== padded) cropped.recycle() }
                } finally { padded.recycle() }
            } catch (e: Exception) { fail("frame", e) }
            finally { image.close() }
        }, handler)
        if (display == null) display = projection!!.createVirtualDisplay("IndieBiz remote screen", width, height,
            m.densityDpi, DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR, next.surface, null, handler)
        else { display!!.resize(width, height, m.densityDpi); display!!.surface = next.surface }
        old?.close()
    }
    private fun fail(stage: String, error: Exception) {
        Log.w("IndieBizScreen", "projection $stage failed", error)
        session?.end("capture_failed")
    }
    override fun onDestroy() {
        session?.end()
        handler.post {
            handler.removeCallbacksAndMessages(null)
            projectionCallback?.let { projection?.unregisterCallback(it) }
            reader?.setOnImageAvailableListener(null, null)
            display?.release(); reader?.close(); projection?.stop()
            session?.capture = null
            session?.captureReleased?.countDown()
            thread.quitSafely()
        }
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        super.onDestroy()
    }
}
