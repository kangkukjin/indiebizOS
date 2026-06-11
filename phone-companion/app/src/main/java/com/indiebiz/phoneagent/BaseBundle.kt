package com.indiebiz.phoneagent

import android.content.Context
import android.util.Log
import java.io.File
import java.util.zip.ZipInputStream

/**
 * 정본 IBL 엔진 트리(indiebiz_base.zip 에셋)를 filesDir 로 풀어 실제 파일 트리를 만든다.
 * tool_loader 가 iterdir/exists/파일경로 동적로드를 쓰므로 물리적 파일이 필요하다.
 * 반환 경로를 phone_api.serve 에 넘겨 INDIEBIZ_BASE_PATH 로 쓴다.
 *
 * 앱 열 때마다 자동 시작되므로 버전(=설치 시각) 마커로 재추출을 스킵 — 이미 현재 APK 의
 * 트리가 풀려 있으면 그대로 쓴다. 재설치(개발 갱신) 시에만 재추출.
 */
object BaseBundle {
    private const val ASSET = "indiebiz_base.zip"
    private const val DIR = "indiebiz_base"

    fun ensure(ctx: Context): String {
        val target = File(ctx.filesDir, DIR)
        val marker = File(target, ".version")
        val version = try {
            ctx.packageManager.getPackageInfo(ctx.packageName, 0).lastUpdateTime.toString()
        } catch (_: Throwable) { "0" }

        // 같은 APK 의 트리가 이미 풀려 있으면 재추출 스킵(빠른 자동시작).
        if (target.exists() && marker.exists() && marker.readText().trim() == version) {
            return target.absolutePath
        }

        if (target.exists()) target.deleteRecursively()
        target.mkdirs()
        val canonicalRoot = target.canonicalPath + File.separator

        ctx.assets.open(ASSET).use { ins ->
            ZipInputStream(ins.buffered()).use { zis ->
                var entry = zis.nextEntry
                while (entry != null) {
                    val out = File(target, entry.name)
                    // zip-slip 방어(우리 빌드 산출이지만 안전벨트)
                    if (!out.canonicalPath.startsWith(canonicalRoot)) {
                        throw SecurityException("zip 항목 경로 이탈: ${entry.name}")
                    }
                    if (entry.isDirectory) {
                        out.mkdirs()
                    } else {
                        out.parentFile?.mkdirs()
                        out.outputStream().use { zis.copyTo(it) }
                    }
                    entry = zis.nextEntry
                }
            }
        }
        marker.writeText(version)
        Log.i("BaseBundle", "엔진 트리 추출 완료(v=$version) → ${target.absolutePath}")
        return target.absolutePath
    }
}
