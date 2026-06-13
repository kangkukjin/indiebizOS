package com.indiebiz.phoneagent

import android.content.ContentValues
import android.content.Context
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
}
