package com.indiebiz.ui

import com.google.crypto.tink.subtle.Ed25519Verify
import org.json.JSONObject
import java.net.URI
import java.security.MessageDigest
import java.util.Base64

/** Signature, file and compatibility checks are shared by the UI installer and both startup loaders. */
class SurfaceReleaseVerifier(private val trust: JSONObject, private val surface: String) {
    val configured get() = trust.optString("feed").isNotEmpty() && trust.optString("publicKey").isNotEmpty()
    private fun hash(bytes: ByteArray) = MessageDigest.getInstance("SHA-256").digest(bytes).joinToString("") { "%02x".format(it) }
    fun origin(url: String): String {
        val uri = URI(url)
        require(uri.scheme == "https" && uri.userInfo == null && uri.fragment == null && uri.host != null) { "업데이트 주소는 HTTPS여야 합니다" }
        return "https://${uri.host}:${if (uri.port < 0) 443 else uri.port}"
    }
    fun verify(envelope: JSONObject, boot: Boolean = false): JSONObject {
        require(configured) { "배포자가 서명된 화면 업데이트 채널을 설정하지 않았습니다" }
        val pem = trust.getString("publicKey").replace("-----BEGIN PUBLIC KEY-----", "").replace("-----END PUBLIC KEY-----", "").replace(Regex("\\s"), "")
        val encoded = Base64.getDecoder().decode(pem)
        val prefix = byteArrayOf(0x30,0x2a,0x30,0x05,0x06,0x03,0x2b,0x65,0x70,0x03,0x21,0x00)
        require(encoded.size == 44 && encoded.copyOfRange(0,12).contentEquals(prefix)) { "Ed25519 배포 공개키가 필요합니다" }
        val bytes = Base64.getDecoder().decode(envelope.getString("manifest"))
        require(bytes.size in 1..65536) { "매니페스트 크기 오류" }
        Ed25519Verify(encoded.copyOfRange(12,44)).verify(Base64.getDecoder().decode(envelope.getString("signature")), bytes)
        val value = JSONObject(String(bytes, Charsets.UTF_8))
        require(value.getString("format") == "indiebiz-member-runtime" && value.getString("kind") == "ui" &&
            value.getString("platform") == "android" && value.getString("arch") == "all" && value.getInt("shell") == 3 &&
            value.getInt("protocol") == 2 && value.getInt("state") == 1 && value.getLong("sequence") in 1..9007199254740991L && value.getString("version").matches(Regex("[0-9]+\\.[0-9]+\\.[0-9]+")) &&
            value.getString("host").matches(Regex("[a-f0-9]{64}"))) { "호환되지 않는 화면입니다. APK를 갱신하세요" }
        require(boot || value.getLong("expires") >= System.currentTimeMillis()/1000) { "만료된 업데이트입니다" }
        val files = value.getJSONArray("files")
        require(files.length() == 1) { "화면 전용 파일 구성 오류" }
        val file = files.getJSONObject(0)
        require(file.getString("name") == "display.json" && file.getInt("size") in 1..8388608 &&
            file.getString("sha256").matches(Regex("[a-f0-9]{64}")) && origin(file.getString("url")) == origin(trust.getString("feed"))) { "화면 자산 검증 오류" }
        return value
    }
    fun payload(manifest: JSONObject, bytes: ByteArray): JSONObject {
        val file = manifest.getJSONArray("files").getJSONObject(0)
        require(bytes.size == file.getInt("size") && hash(bytes) == file.getString("sha256")) { "화면 자산 지문 불일치" }
        val display = JSONObject(String(bytes, Charsets.UTF_8))
        require(display.getString("format") == "indiebiz-display-1" && display.getString("surface") == surface &&
            display.getString("host") == manifest.getString("host") && display.getInt("state") == manifest.getInt("state")) { "화면 호스트 계약 불일치" }
        return display
    }
}
