package com.indiebiz.phoneagent

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ContentUris
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.provider.MediaStore
import org.json.JSONArray
import android.graphics.Bitmap
import android.graphics.ImageFormat
import android.graphics.SurfaceTexture
import android.hardware.camera2.CameraCaptureSession
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraDevice
import android.hardware.camera2.CameraManager
import android.hardware.camera2.CaptureRequest
import android.location.Geocoder
import android.media.ImageReader
import android.media.MediaRecorder
import android.media.ThumbnailUtils
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.HandlerThread
import android.os.Looper
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.util.Size
import android.view.Surface
import android.widget.Toast
import androidx.core.app.NotificationCompat
import com.google.android.gms.location.LocationServices
import com.google.android.gms.location.Priority
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.Locale
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * 송신측(폰→동작) effector 다리: 폰의 파이썬 뇌([limbs:phone])가 폰 하드웨어를 직접 만지게 한다.
 *
 * Chaquopy Java 브리지로 호출된다 — android 패키지 handler.py(_phone_act)가
 * `jclass("com.indiebiz.phoneagent.PhoneActions").notify(...)` 식으로 부른다.
 * 모든 메서드는 @JvmStatic(폰 프로파일 전용; PC에선 from java import 자체가 실패해 graceful 거부).
 *
 * 출력(effector): notify/vibrate/toast/clipboard/speak/openApp (SMS·통화는 민감해 제외).
 * 입력(sense): getCurrentLocationNow([sense:here] 위치) · transcribeFromMic/recordAudio([sense:listen] 귀)
 *   · capturePhoto([sense:see] 눈). 전부 온디맨드(상시 수집 아님) — 물을 때 1회.
 */
object PhoneActions {
    @Volatile private var appContext: Context? = null
    @Volatile private var tts: TextToSpeech? = null
    @Volatile private var ttsReady = false
    private const val CHANNEL_ID = "indiebiz_brain"
    // 능동 알림([limbs:phone]{op:notify}) 전용 — 소리·진동·헤즈업 있는 고중요도 채널.
    // 옛 indiebiz_brain 은 IMPORTANCE_DEFAULT + 무음으로 이미 생성돼 있어(안드로이드는
    // 생성 후 채널 중요도 상향 불가) "알림이 떠도 기척이 없는" 문제 → 새 채널로 분리.
    private const val CHANNEL_ALERT = "indiebiz_alert"
    private val main = Handler(Looper.getMainLooper())

    /** App.onCreate 에서 1회 호출 — 컨텍스트 보관 + 알림 채널 + TTS 초기화. */
    @JvmStatic
    fun init(ctx: Context) {
        appContext = ctx.applicationContext
        ensureChannel()
        // TTS 는 비동기 초기화 — 미리 준비해 첫 speak 지연/실패를 줄인다.
        try {
            tts = TextToSpeech(appContext) { status ->
                if (status == TextToSpeech.SUCCESS) {
                    try { tts?.language = Locale.KOREAN } catch (_: Throwable) {}
                    ttsReady = true
                }
            }
        } catch (_: Throwable) {}
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val ctx = appContext ?: return
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (nm.getNotificationChannel(CHANNEL_ID) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ID, "IndieBiz 뇌 알림", NotificationManager.IMPORTANCE_DEFAULT)
            )
        }
        if (nm.getNotificationChannel(CHANNEL_ALERT) == null) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL_ALERT, "IndieBiz 알림(소리·진동)",
                                    NotificationManager.IMPORTANCE_HIGH).apply {
                    enableVibration(true)
                }
            )
        }
    }

    /** 알림 표시. (Android 13+ 는 POST_NOTIFICATIONS 런타임 권한 필요 — 없으면 조용히 무시됨.) */
    @JvmStatic
    fun notify(title: String, body: String): Boolean {
        val ctx = appContext ?: return false
        return try {
            val n = NotificationCompat.Builder(ctx, CHANNEL_ALERT)
                .setSmallIcon(android.R.drawable.ic_dialog_info)
                .setContentTitle(title)
                .setContentText(body)
                .setStyle(NotificationCompat.BigTextStyle().bigText(body))
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .setDefaults(NotificationCompat.DEFAULT_ALL)
                .setAutoCancel(true)
                .build()
            val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.notify((System.currentTimeMillis() % 100000).toInt(), n)
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "notify failed: $e"); false
        }
    }

    /** 진동 (ms). VIBRATE 권한(설치시 자동 부여) 필요. */
    @JvmStatic
    fun vibrate(ms: Long): Boolean {
        val ctx = appContext ?: return false
        return try {
            val vib: Vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                (ctx.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as VibratorManager).defaultVibrator
            } else {
                @Suppress("DEPRECATION")
                ctx.getSystemService(Context.VIBRATOR_SERVICE) as Vibrator
            }
            vib.vibrate(VibrationEffect.createOneShot(ms, VibrationEffect.DEFAULT_AMPLITUDE))
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "vibrate failed: $e"); false
        }
    }

    /** 화면에 토스트 (메인 스레드). */
    @JvmStatic
    fun toast(text: String): Boolean {
        val ctx = appContext ?: return false
        main.post { try { Toast.makeText(ctx, text, Toast.LENGTH_LONG).show() } catch (_: Throwable) {} }
        return true
    }

    /** 클립보드에 텍스트 복사. */
    @JvmStatic
    fun setClipboard(text: String): Boolean {
        val ctx = appContext ?: return false
        return try {
            val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            cm.setPrimaryClip(ClipData.newPlainText("IndieBiz", text))
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "clipboard failed: $e"); false
        }
    }

    /**
     * 클립보드 텍스트 읽기 — setClipboard 의 역방향 짝(폰→맥 복사 배관).
     * Android 10+ 은 입력 포커스를 가진 포그라운드 앱만 읽을 수 있다 — 런처 버튼 탭
     * 시점엔 이 앱이 포그라운드라 허용 케이스. HTTP 워커 스레드에서 불리므로
     * 메인 스레드로 홉(일부 기기는 백그라운드 스레드 읽기를 무시) + 래치 대기.
     * 반환: 텍스트(빈 클립보드/비텍스트면 ""), 실패 시 "".
     */
    @JvmStatic
    fun getClipboard(): String {
        val ctx = appContext ?: return ""
        var out = ""
        val latch = CountDownLatch(1)
        main.post {
            try {
                val cm = ctx.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
                val item = cm.primaryClip?.takeIf { it.itemCount > 0 }?.getItemAt(0)
                out = item?.coerceToText(ctx)?.toString() ?: ""
            } catch (e: Throwable) {
                android.util.Log.e("PhoneActions", "getClipboard failed: $e")
            } finally { latch.countDown() }
        }
        latch.await(2, TimeUnit.SECONDS)
        return out
    }

    /** TTS 음성 출력. (한국어 음성 미설치 시 실패 가능.) */
    @JvmStatic
    fun speak(text: String): Boolean {
        val t = tts
        if (t == null || !ttsReady) return false
        return try {
            t.speak(text, TextToSpeech.QUEUE_FLUSH, null, "indiebiz_${System.currentTimeMillis()}")
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "speak failed: $e"); false
        }
    }

    /**
     * SMS 작성창을 수신자·본문 채워 연다 (스테이징 — 전송은 사용자가 탭).
     * ACTION_SENDTO(smsto:) 라 SEND_SMS 위험 권한 불필요. to 비면 본문만 채운 작성창.
     */
    @JvmStatic
    fun composeSms(to: String, text: String): Boolean {
        val ctx = appContext ?: return false
        return try {
            val uri = android.net.Uri.parse("smsto:" + android.net.Uri.encode(to))
            val intent = android.content.Intent(android.content.Intent.ACTION_SENDTO, uri)
            if (text.isNotEmpty()) intent.putExtra("sms_body", text)
            intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(intent)
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "composeSms failed: $e"); false
        }
    }

    /**
     * 다이얼러를 번호 채워 연다 (스테이징 — 통화는 사용자가 탭).
     * ACTION_DIAL 이라 CALL_PHONE 위험 권한 불필요(ACTION_CALL=즉시 발신과 구분).
     */
    @JvmStatic
    fun dial(number: String): Boolean {
        val ctx = appContext ?: return false
        return try {
            val uri = android.net.Uri.parse("tel:" + android.net.Uri.encode(number))
            val intent = android.content.Intent(android.content.Intent.ACTION_DIAL, uri)
            intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(intent)
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "dial failed: $e"); false
        }
    }

    /** 패키지명으로 앱 실행. 런처 인텐트 없으면 false. */
    @JvmStatic
    fun openApp(pkg: String): Boolean {
        val ctx = appContext ?: return false
        return try {
            val intent = ctx.packageManager.getLaunchIntentForPackage(pkg) ?: return false
            intent.addFlags(android.content.Intent.FLAG_ACTIVITY_NEW_TASK)
            ctx.startActivity(intent)
            true
        } catch (e: Throwable) {
            android.util.Log.e("PhoneActions", "openApp failed: $e"); false
        }
    }

    /**
     * 현재 위치를 즉석에서 한 번 조회 ([sense:here] 의 하드웨어 다리).
     *
     * 상시 추적·저장이 아니라, 물을 때 그 순간만 fused GPS 로 한 번 가져온다(augmentation).
     * Chaquopy 가 동기 호출하므로 비동기 fused Task 를 CountDownLatch 로 블록해 결과를 기다린다.
     * 반환=JSON 문자열: {lat,lng,accuracy,captured_at[,address]} 또는 {error}. 핸들러가 파싱.
     */
    @JvmStatic
    fun getCurrentLocationNow(): String {
        val ctx = appContext ?: return """{"error":"context 미초기화"}"""
        val fine = ctx.checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
        val coarse = ctx.checkSelfPermission(Manifest.permission.ACCESS_COARSE_LOCATION) ==
            PackageManager.PERMISSION_GRANTED
        if (!fine && !coarse) {
            return """{"error":"위치 권한 없음 — 설정에서 IndieBiz 위치 권한을 허용하세요"}"""
        }
        val fused = LocationServices.getFusedLocationProviderClient(ctx)
        val latch = CountDownLatch(1)
        val holder = arrayOfNulls<android.location.Location>(1)
        val errMsg = arrayOfNulls<String>(1)
        try {
            fused.getCurrentLocation(Priority.PRIORITY_HIGH_ACCURACY, null)
                .addOnSuccessListener { loc -> holder[0] = loc; latch.countDown() }
                .addOnFailureListener { e -> errMsg[0] = e.message; latch.countDown() }
        } catch (se: SecurityException) {
            return """{"error":"위치 권한 거부(SecurityException)"}"""
        }
        if (!latch.await(15, TimeUnit.SECONDS)) {
            return """{"error":"위치 조회 시간초과(15초)"}"""
        }
        val loc = holder[0]
            ?: return """{"error":"위치 null${if (errMsg[0] != null) " — ${errMsg[0]}" else ""}"}"""
        val out = JSONObject()
            .put("lat", loc.latitude)
            .put("lng", loc.longitude)
            .put("accuracy", loc.accuracy.toDouble())
            .put("captured_at", System.currentTimeMillis() / 1000)
        // 역지오코딩(주소) — best-effort, 오프라인/실패 시 좌표만. "어디"에 사람이 읽을 답을 준다.
        try {
            @Suppress("DEPRECATION")
            val addrs = Geocoder(ctx, Locale.KOREA).getFromLocation(loc.latitude, loc.longitude, 1)
            if (!addrs.isNullOrEmpty()) out.put("address", addrs[0].getAddressLine(0))
        } catch (_: Throwable) {}
        return out.toString()
    }

    private fun errJson(msg: String): String = JSONObject().put("error", msg).toString()

    /**
     * 미디어 라이브 질의 ([self:photo] 의 폰측 다리) — MediaStore 색인 직접.
     *
     * 폰도 OS(MediaStore)가 미디어를 이미 증분 색인 → 선스캔 불필요. file_index 가
     * filters JSON({kind,q,start_ms,end_ms,has_gps,want_gps,limit}) 으로 부른다.
     * 위치(GPS)는 Android 10+ 가 기본 가리므로 want_gps 일 때만 ACCESS_MEDIA_LOCATION +
     * 원본 EXIF 로 읽는다(이미지만, 창 안에서만 — per-file I/O 최소화).
     * 반환=JSON {items:[{path,name,size,mtime,taken_at,kind,width,height,lat?,lng?}], count}.
     */
    @JvmStatic
    fun queryMedia(filtersJson: String): String {
        val ctx = appContext ?: return errJson("context 미초기화")
        val f = try { JSONObject(filtersJson) } catch (e: Exception) { JSONObject() }
        val kind = f.optString("kind", "media")
        val q = f.optString("q", "")
        val startMs = f.optLong("start_ms", 0L)
        val endMs = f.optLong("end_ms", 0L)
        val hasGps = f.optBoolean("has_gps", false)
        val wantGps = f.optBoolean("want_gps", false)
        val limit = f.optInt("limit", 50).coerceIn(1, 2000)
        val minSize = f.optLong("min_size", 0L)   // 바이트 — 큰 파일 필터
        val sort = f.optString("sort", "")          // size/mtime/name/date(기본 DATE_TAKEN)
        val ext = f.optString("ext", "")            // 확장자 필터 (소문자, 점 없음)

        val cId = MediaStore.Files.FileColumns._ID
        val cName = MediaStore.Files.FileColumns.DISPLAY_NAME
        val cData = MediaStore.Files.FileColumns.DATA
        val cTaken = MediaStore.Files.FileColumns.DATE_TAKEN
        val cMod = MediaStore.Files.FileColumns.DATE_MODIFIED
        val cSize = MediaStore.Files.FileColumns.SIZE
        val cW = MediaStore.Files.FileColumns.WIDTH
        val cH = MediaStore.Files.FileColumns.HEIGHT
        val cType = MediaStore.Files.FileColumns.MEDIA_TYPE
        val tImage = MediaStore.Files.FileColumns.MEDIA_TYPE_IMAGE
        val tVideo = MediaStore.Files.FileColumns.MEDIA_TYPE_VIDEO
        val proj = arrayOf(cId, cName, cData, cTaken, cMod,
            MediaStore.Files.FileColumns.MIME_TYPE, cSize, cW, cH, cType)

        val sel = StringBuilder()
        val args = ArrayList<String>()
        when (kind) {
            "image", "photo" -> { sel.append("$cType=?"); args.add(tImage.toString()) }
            "video" -> { sel.append("$cType=?"); args.add(tVideo.toString()) }
            else -> {
                sel.append("($cType=? OR $cType=?)")
                args.add(tImage.toString()); args.add(tVideo.toString())
            }
        }
        if (startMs > 0) { sel.append(" AND $cTaken>=?"); args.add(startMs.toString()) }
        if (endMs > 0) { sel.append(" AND $cTaken<=?"); args.add(endMs.toString()) }
        if (q.isNotBlank()) { sel.append(" AND $cName LIKE ?"); args.add("%$q%") }
        if (minSize > 0) { sel.append(" AND $cSize>=?"); args.add(minSize.toString()) }
        if (ext.isNotBlank()) { sel.append(" AND $cName LIKE ?"); args.add("%.$ext") }

        // 정렬: 맥 Spotlight 와 동일 어휘 (size/mtime/name, 기본 DATE_TAKEN 최신순)
        val order = when (sort) {
            "size" -> "$cSize DESC"
            "mtime" -> "$cMod DESC"
            "name" -> "$cName ASC"
            else -> "$cTaken DESC"
        }

        val uri = MediaStore.Files.getContentUri("external")
        val iso = java.text.SimpleDateFormat("yyyy-MM-dd'T'HH:mm:ss", Locale.US)
        val items = JSONArray()
        var total = 0
        try {
            ctx.contentResolver.query(uri, proj, sel.toString(), args.toTypedArray(),
                order)?.use { c ->
                val iId = c.getColumnIndexOrThrow(cId)
                val iName = c.getColumnIndexOrThrow(cName)
                val iData = c.getColumnIndex(cData)
                val iTaken = c.getColumnIndex(cTaken)
                val iMod = c.getColumnIndex(cMod)
                val iSize = c.getColumnIndex(cSize)
                val iW = c.getColumnIndex(cW)
                val iH = c.getColumnIndex(cH)
                val iType = c.getColumnIndex(cType)
                while (c.moveToNext()) {
                    total++
                    if (items.length() >= limit) break
                    val id = c.getLong(iId)
                    val isVideo = iType >= 0 && c.getInt(iType) == tVideo
                    // GPS 필터/요청 — 이미지만 EXIF, 영상은 위치 없음.
                    var lat: Double? = null; var lng: Double? = null
                    if (wantGps && !isVideo) {
                        val ll = readGps(ctx, id)
                        if (ll != null) { lat = ll[0]; lng = ll[1] }
                    }
                    if (hasGps && (lat == null || lng == null)) continue  // 위치 없으면 제외
                    val o = JSONObject()
                    o.put("path", if (iData >= 0) c.getString(iData) ?: "" else "")
                    o.put("name", c.getString(iName) ?: "")
                    o.put("size", if (iSize >= 0) c.getLong(iSize) else 0L)
                    o.put("mtime", if (iMod >= 0) c.getLong(iMod) else 0L)  // 초 단위
                    val takenMs = if (iTaken >= 0) c.getLong(iTaken) else 0L
                    o.put("taken_at", if (takenMs > 0) iso.format(java.util.Date(takenMs)) else "")
                    o.put("kind", if (isVideo) "video" else "image")
                    if (iW >= 0) o.put("width", c.getInt(iW))
                    if (iH >= 0) o.put("height", c.getInt(iH))
                    if (lat != null && lng != null) { o.put("lat", lat); o.put("lng", lng) }
                    items.put(o)
                }
            }
        } catch (e: Exception) {
            return errJson("MediaStore 질의 실패: ${e.message}")
        }
        return JSONObject().put("items", items).put("count", total).toString()
    }

    /** 원본 EXIF 에서 GPS 읽기 (ACCESS_MEDIA_LOCATION 필요). 없거나 거부면 null. */
    private fun readGps(ctx: Context, id: Long): DoubleArray? {
        return try {
            val img = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, id)
            val orig = MediaStore.setRequireOriginal(img)
            ctx.contentResolver.openInputStream(orig)?.use { ins ->
                val out = FloatArray(2)
                val exif = android.media.ExifInterface(ins)
                if (exif.getLatLong(out) && !(out[0] == 0f && out[1] == 0f))
                    doubleArrayOf(out[0].toDouble(), out[1].toDouble()) else null
            }
        } catch (e: Exception) { null }
    }

    /**
     * 마이크 음성 받아쓰기 ([sense:listen]{op:transcribe} 의 다리) — STT → 텍스트.
     *
     * Android SpeechRecognizer(온디바이스/Google) 로 지금 발화를 듣고 텍스트로. ko-KR.
     * 메인스레드 바인딩 + 비동기 결과라 main.post + CountDownLatch 로 동기화(location 과 동형).
     * 반환=JSON: {text} 또는 {error}. 포워드 시 텍스트라 맥↔폰 무손실.
     */
    @JvmStatic
    fun transcribeFromMic(timeoutSec: Int): String {
        val ctx = appContext ?: return errJson("context 미초기화")
        if (ctx.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
            return errJson("마이크 권한 없음 — 설정에서 IndieBiz 마이크 권한을 허용하세요")
        if (!SpeechRecognizer.isRecognitionAvailable(ctx))
            return errJson("음성 인식 서비스 없음(Google 앱/온디바이스 STT 미설치)")
        val latch = CountDownLatch(1)
        val text = arrayOfNulls<String>(1)
        val err = arrayOfNulls<String>(1)
        main.post {
            try {
                val sr = SpeechRecognizer.createSpeechRecognizer(ctx)
                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, "ko-KR")
                    putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, false)
                }
                sr.setRecognitionListener(object : RecognitionListener {
                    override fun onResults(b: Bundle) {
                        text[0] = b.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull() ?: ""
                        sr.destroy(); latch.countDown()
                    }
                    override fun onError(code: Int) {
                        err[0] = when (code) {
                            SpeechRecognizer.ERROR_SPEECH_TIMEOUT, SpeechRecognizer.ERROR_NO_MATCH -> "발화 감지 못함(무음/미인식)"
                            SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS -> "마이크 권한 부족"
                            else -> "STT 오류코드 $code"
                        }
                        sr.destroy(); latch.countDown()
                    }
                    override fun onReadyForSpeech(p: Bundle?) {}
                    override fun onBeginningOfSpeech() {}
                    override fun onRmsChanged(r: Float) {}
                    override fun onBufferReceived(b: ByteArray?) {}
                    override fun onEndOfSpeech() {}
                    override fun onPartialResults(p: Bundle?) {}
                    override fun onEvent(t: Int, p: Bundle?) {}
                })
                sr.startListening(intent)
            } catch (t: Throwable) { err[0] = t.message; latch.countDown() }
        }
        if (!latch.await(timeoutSec.toLong().coerceIn(5, 60), TimeUnit.SECONDS))
            return errJson("음성 인식 시간초과(${timeoutSec}초) — 발화 없음")
        err[0]?.let { return errJson(it) }
        return JSONObject().put("text", text[0] ?: "").toString()
    }

    /**
     * 마이크 녹음 ([sense:listen]{op:record} 의 다리) — durationSec 초 동안 녹음해 파일로.
     *
     * MediaRecorder(AAC/m4a) → filesDir/recordings/. 동기 호출이라 호출 스레드에서 dur 초 블록.
     * 반환=JSON: {path, duration_sec, bytes} 또는 {error}. 파일은 폰에 잔류(맥 포워드 시 경로만 — 회수는 후속).
     */
    @JvmStatic
    fun recordAudio(durationSec: Int): String {
        val ctx = appContext ?: return errJson("context 미초기화")
        if (ctx.checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED)
            return errJson("마이크 권한 없음 — 설정에서 IndieBiz 마이크 권한을 허용하세요")
        val dur = durationSec.coerceIn(1, 300)
        val dir = File(ctx.filesDir, "recordings").apply { mkdirs() }
        val out = File(dir, "rec_${System.currentTimeMillis()}.m4a")
        @Suppress("DEPRECATION")
        val rec = if (Build.VERSION.SDK_INT >= 31) MediaRecorder(ctx) else MediaRecorder()
        return try {
            rec.setAudioSource(MediaRecorder.AudioSource.MIC)
            rec.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            rec.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            rec.setOutputFile(out.absolutePath)
            rec.prepare(); rec.start()
            Thread.sleep(dur * 1000L)
            rec.stop(); rec.release()
            JSONObject().put("path", out.absolutePath).put("duration_sec", dur)
                .put("bytes", out.length()).toString()
        } catch (t: Throwable) {
            try { rec.release() } catch (_: Throwable) {}
            errJson("녹음 실패: ${t.message}")
        }
    }

    /**
     * 카메라로 사진 1장 촬영 ([sense:see] 의 다리) — 미리보기 없이 정지 캡처.
     *
     * Camera2 + ImageReader(JPEG) — 백그라운드 HandlerThread 에서 비동기 진행을 CountDownLatch 로 동기화.
     * facing=back(기본)/front. 반환=JSON: {path, bytes, facing} 또는 {error}. 파일은 폰에 잔류(맥 포워드 시 경로만).
     * 주의: 앱이 포그라운드일 때 가장 안정적(백그라운드 카메라 접근은 OS 제약 — 호출 시 보통 앱이 떠 있음).
     */
    @JvmStatic
    fun capturePhoto(facing: String): String {
        val ctx = appContext ?: return errJson("context 미초기화")
        if (ctx.checkSelfPermission(Manifest.permission.CAMERA) != PackageManager.PERMISSION_GRANTED)
            return errJson("카메라 권한 없음 — 설정에서 IndieBiz 카메라 권한을 허용하세요")
        val cm = ctx.getSystemService(Context.CAMERA_SERVICE) as CameraManager
        val wantFront = facing.equals("front", true)
        var camId: String? = null
        var jpegSize = Size(1920, 1080)
        try {
            for (id in cm.cameraIdList) {
                val chars = cm.getCameraCharacteristics(id)
                val lens = chars.get(CameraCharacteristics.LENS_FACING)
                val match = (wantFront && lens == CameraCharacteristics.LENS_FACING_FRONT) ||
                    (!wantFront && lens == CameraCharacteristics.LENS_FACING_BACK)
                if (match || camId == null) {
                    val map = chars.get(CameraCharacteristics.SCALER_STREAM_CONFIGURATION_MAP)
                    val sizes = map?.getOutputSizes(ImageFormat.JPEG)
                    val best = sizes?.maxByOrNull { it.width.toLong() * it.height }
                    if (camId == null || match) { camId = id; if (best != null) jpegSize = best }
                    if (match) break
                }
            }
        } catch (t: Throwable) { return errJson("카메라 조회 실패: ${t.message}") }
        val useId = camId ?: return errJson("카메라 없음")

        val dir = File(ctx.filesDir, "photos").apply { mkdirs() }
        val out = File(dir, "photo_${System.currentTimeMillis()}.jpg")
        val latch = CountDownLatch(1)
        val err = arrayOfNulls<String>(1)
        val thread = HandlerThread("cam-capture").apply { start() }
        val handler = Handler(thread.looper)
        val reader = ImageReader.newInstance(jpegSize.width, jpegSize.height, ImageFormat.JPEG, 1)
        reader.setOnImageAvailableListener({ r ->
            try {
                val img = r.acquireNextImage()
                val buf = img.planes[0].buffer
                val bytes = ByteArray(buf.remaining()); buf.get(bytes)
                out.writeBytes(bytes)
                img.close()
            } catch (t: Throwable) { err[0] = "이미지 저장 실패: ${t.message}" }
            latch.countDown()
        }, handler)
        // 더미 프리뷰 표면(화면 없음) — 3A(자동노출/초점) 수렴용. 없으면 첫 정지캡처가 센서 바닥값(흑색)으로 나온다.
        val previewTex = SurfaceTexture(0).apply { setDefaultBufferSize(jpegSize.width, jpegSize.height) }
        val previewSurface = Surface(previewTex)

        var camera: CameraDevice? = null
        try {
            cm.openCamera(useId, object : CameraDevice.StateCallback() {
                override fun onOpened(device: CameraDevice) {
                    camera = device
                    try {
                        device.createCaptureSession(listOf(previewSurface, reader.surface), object : CameraCaptureSession.StateCallback() {
                            override fun onConfigured(session: CameraCaptureSession) {
                                try {
                                    // 1) 프리뷰 반복요청으로 노출/초점 수렴
                                    val preview = device.createCaptureRequest(CameraDevice.TEMPLATE_PREVIEW)
                                    preview.addTarget(previewSurface)
                                    preview.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
                                    preview.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON)
                                    session.setRepeatingRequest(preview.build(), null, handler)
                                    // 2) 수렴 시간(1.5초) 뒤 정지 캡처
                                    handler.postDelayed({
                                        try {
                                            val still = device.createCaptureRequest(CameraDevice.TEMPLATE_STILL_CAPTURE)
                                            still.addTarget(reader.surface)
                                            still.set(CaptureRequest.CONTROL_AF_MODE, CaptureRequest.CONTROL_AF_MODE_CONTINUOUS_PICTURE)
                                            still.set(CaptureRequest.CONTROL_AE_MODE, CaptureRequest.CONTROL_AE_MODE_ON)
                                            session.stopRepeating()
                                            session.capture(still.build(), null, handler)
                                        } catch (t: Throwable) { err[0] = "캡처 실패: ${t.message}"; latch.countDown() }
                                    }, 1500)
                                } catch (t: Throwable) { err[0] = "프리뷰 시작 실패: ${t.message}"; latch.countDown() }
                            }
                            override fun onConfigureFailed(session: CameraCaptureSession) {
                                err[0] = "캡처 세션 설정 실패"; latch.countDown()
                            }
                        }, handler)
                    } catch (t: Throwable) { err[0] = "세션 생성 실패: ${t.message}"; latch.countDown() }
                }
                override fun onDisconnected(device: CameraDevice) { device.close() }
                override fun onError(device: CameraDevice, e: Int) {
                    err[0] = "카메라 오류코드 $e"; device.close(); latch.countDown()
                }
            }, handler)
        } catch (t: Throwable) {
            thread.quitSafely(); previewSurface.release(); previewTex.release()
            return errJson("openCamera 실패: ${t.message}")
        }

        val ok = latch.await(15, TimeUnit.SECONDS)
        try { camera?.close() } catch (_: Throwable) {}
        try { reader.close() } catch (_: Throwable) {}
        try { previewSurface.release() } catch (_: Throwable) {}
        try { previewTex.release() } catch (_: Throwable) {}
        thread.quitSafely()
        if (!ok) return errJson("촬영 시간초과(15초)")
        err[0]?.let { return errJson(it) }
        if (!out.exists() || out.length() == 0L) return errJson("촬영 실패(빈 파일)")
        return JSONObject().put("path", out.absolutePath).put("bytes", out.length())
            .put("facing", if (wantFront) "front" else "back")
            .put("width", jpegSize.width).put("height", jpegSize.height).toString()
    }

    /**
     * 동영상 썸네일(대표 프레임) — ffmpeg 미번들 폰의 [self:photo] video-thumbnail 다리.
     *
     * 사진은 PIL(api_photo)로 되지만 동영상 컨테이너는 PIL이 못 열고 폰엔 ffmpeg가 없다.
     * Android 네이티브 ThumbnailUtils 가 OS 디코더로 파일에서 프레임을 뽑는다(API 29+).
     * 반환=JPEG 바이트(Chaquopy→Python bytes). 실패/없음=빈 배열(phone_api 가 폴백).
     * path=MediaStore DATA 절대경로(/storage/...). 캐싱은 호출부(phone_api)가 담당.
     */
    @JvmStatic
    fun videoThumbnail(path: String, size: Int): ByteArray {
        return try {
            val f = File(path)
            if (!f.exists()) return ByteArray(0)
            val s = if (size > 0) size else 200
            val bmp: Bitmap = ThumbnailUtils.createVideoThumbnail(f, Size(s, s), null)
            val out = ByteArrayOutputStream()
            bmp.compress(Bitmap.CompressFormat.JPEG, 80, out)
            bmp.recycle()
            out.toByteArray()
        } catch (e: Throwable) {
            ByteArray(0)
        }
    }
}
