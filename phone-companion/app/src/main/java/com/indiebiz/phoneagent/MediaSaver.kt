package com.indiebiz.phoneagent

import android.content.ContentValues
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import java.io.File

/**
 * 분산 IBL — 빌린 연산(맥 yt-dlp)의 산출물(mp3)을 폰 Music 폴더에 저장하는 네이티브 헬퍼.
 *
 * 폰엔 yt-dlp 가 없어 다운로드는 맥에 위임하지만, "폰서 누른 다운로드 = 폰에 파일" 이라야
 * 자연스럽다(빌린 연산, 로컬 산출물). 맥이 mp3 를 base64 로 돌려주면 폰 Python(phone_api)이
 * 디코드해 이 헬퍼로 넘기고, MediaStore Audio 로 공용 Music 폴더에 쓴다(음악 앱이 인식).
 *
 * 큰 b64 는 WebView JS 브리지가 아니라 Python↔Kotlin(Chaquopy bytes→byte[])으로만 흐른다.
 * Context 는 nostr 브리지와 같이 Python.getPlatform().getApplication() 으로 획득(별도 init 불필요).
 * API 29+(scoped storage)는 자기 생성 파일이라 저장소 권한 불필요. 모든 @JvmStatic.
 */
object MediaSaver {
    @JvmStatic
    fun saveAudio(data: ByteArray, filename: String): String {
        return try {
            val ctx: Context = (Python.getPlatform() as AndroidPlatform).application
            val name = if (filename.endsWith(".mp3", true)) filename else "$filename.mp3"
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                val values = ContentValues().apply {
                    put(MediaStore.Audio.Media.DISPLAY_NAME, name)
                    put(MediaStore.Audio.Media.MIME_TYPE, "audio/mpeg")
                    put(MediaStore.Audio.Media.RELATIVE_PATH, Environment.DIRECTORY_MUSIC)
                    put(MediaStore.Audio.Media.IS_PENDING, 1)
                }
                val resolver = ctx.contentResolver
                val uri = resolver.insert(MediaStore.Audio.Media.EXTERNAL_CONTENT_URI, values)
                    ?: return "ERROR: MediaStore insert 실패"
                resolver.openOutputStream(uri)?.use { it.write(data) }
                    ?: return "ERROR: openOutputStream 실패"
                values.clear()
                values.put(MediaStore.Audio.Media.IS_PENDING, 0)
                resolver.update(uri, values, null, null)
                "Music/$name"
            } else {
                // API 28 폴백(공용 디렉토리 직접 — 실기기는 API 29+ 이라 거의 안 탐)
                val dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_MUSIC)
                if (!dir.exists()) dir.mkdirs()
                val f = File(dir, name)
                f.outputStream().use { it.write(data) }
                f.absolutePath
            }
        } catch (e: Exception) {
            "ERROR: ${e.javaClass.simpleName}: ${e.message}"
        }
    }

    /**
     * 임의 파일(신문·보고서 등)을 공유 가능한 위치(공용 Downloads)에 저장한다.
     *
     * saveAudio 와 같은 MediaStore 패턴이되 Downloads 컬렉션 — 앱 사설 outputs/ 와 달리
     * 카카오톡 등 다른 앱이 접근 가능. API 29+ scoped storage 라 저장소 권한 불필요.
     * 저장이 반환하는 content:// URI 는 그대로 공유(ACTION_SEND)에 쓸 수 있다(FileProvider 불필요).
     * 반환: 성공 시 "Download/<이름>", 실패 시 "ERROR: ...".
     */
    private fun writeToDownloads(data: ByteArray, filename: String, mime: String): android.net.Uri {
        val ctx: Context = (Python.getPlatform() as AndroidPlatform).application
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val resolver = ctx.contentResolver
            // 같은 이름이 이미 있으면 지운다 — 최신 판 하나만(MediaStore 는 기본적으로 "newspaper (1).html"
            // 로 사본을 쌓는데, 신문/보고서는 덮어쓰기가 맞다. Downloads 안 같은 이름만 대상).
            try {
                resolver.delete(
                    MediaStore.Downloads.EXTERNAL_CONTENT_URI,
                    "${MediaStore.Downloads.DISPLAY_NAME}=? AND ${MediaStore.Downloads.RELATIVE_PATH} LIKE ?",
                    arrayOf(filename, "${Environment.DIRECTORY_DOWNLOADS}%")
                )
            } catch (_: Exception) { /* 없으면 무시 */ }
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, filename)
                put(MediaStore.Downloads.MIME_TYPE, mime)
                put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values)
                ?: throw IllegalStateException("MediaStore insert 실패")
            resolver.openOutputStream(uri)?.use { it.write(data) }
                ?: throw IllegalStateException("openOutputStream 실패")
            values.clear()
            values.put(MediaStore.Downloads.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
            return uri
        } else {
            // API 28 폴백 — 실기기는 API 29+ 이라 거의 안 탐(공유엔 content URI 필요).
            val dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            if (!dir.exists()) dir.mkdirs()
            val f = File(dir, filename)
            f.outputStream().use { it.write(data) }
            return android.net.Uri.fromFile(f)
        }
    }

    @JvmStatic
    fun saveToDownloads(data: ByteArray, filename: String, mime: String): String {
        return try {
            writeToDownloads(data, filename, mime)
            "Download/$filename"
        } catch (e: Exception) {
            "ERROR: ${e.javaClass.simpleName}: ${e.message}"
        }
    }

    /**
     * 파일을 Downloads 에 저장한 뒤, 그 content:// URI 로 안드로이드 공유 시트(ACTION_SEND)를 연다.
     * 사용자가 카카오톡 등 앱을 골라 공유한다(스테이징 — 실제 공유는 사용자 탭, sms/call 과 같은 모델).
     * 백그라운드에서도 뜨도록 NEW_TASK, 대상 앱에 읽기 권한을 GRANT.
     */
    @JvmStatic
    fun shareFile(data: ByteArray, filename: String, mime: String): String {
        return try {
            val ctx: Context = (Python.getPlatform() as AndroidPlatform).application
            val uri = writeToDownloads(data, filename, mime)
            val send = Intent(Intent.ACTION_SEND).apply {
                type = mime
                putExtra(Intent.EXTRA_STREAM, uri)
                putExtra(Intent.EXTRA_TITLE, filename)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            val chooser = Intent.createChooser(send, "공유").apply {
                addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
            }
            ctx.startActivity(chooser)
            "Download/$filename"
        } catch (e: Exception) {
            "ERROR: ${e.javaClass.simpleName}: ${e.message}"
        }
    }
}
