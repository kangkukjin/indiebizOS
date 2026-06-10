package com.indiebiz.phoneagent

import android.util.Base64
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec
import java.security.SecureRandom
import kotlin.math.floor
import kotlin.math.ln

/**
 * NIP-44 v2 (ChaCha20 + HKDF-SHA256 + HMAC-SHA256).
 * backend/nip44.py 와 1:1 동일 — 그래야 백엔드가 복호한다.
 */
object Nip44 {
    private val rng = SecureRandom()
    private val SALT = "nip44-v2".toByteArray(Charsets.UTF_8)

    fun conversationKey(privHex: String, pubXonlyHex: String): ByteArray {
        val sharedX = NostrCrypto.ecdhX(privHex, pubXonlyHex)
        return hkdfExtract(SALT, sharedX)
    }

    private fun hmac(key: ByteArray, data: ByteArray): ByteArray {
        val m = Mac.getInstance("HmacSHA256")
        m.init(SecretKeySpec(key, "HmacSHA256"))
        return m.doFinal(data)
    }

    private fun hkdfExtract(salt: ByteArray, ikm: ByteArray) = hmac(salt, ikm)

    private fun hkdfExpand(prk: ByteArray, info: ByteArray, length: Int): ByteArray {
        val out = ByteArray(length)
        var t = ByteArray(0)
        var pos = 0
        var i = 1
        while (pos < length) {
            val m = Mac.getInstance("HmacSHA256")
            m.init(SecretKeySpec(prk, "HmacSHA256"))
            m.update(t); m.update(info); m.update(byteArrayOf(i.toByte()))
            t = m.doFinal()
            val n = minOf(t.size, length - pos)
            System.arraycopy(t, 0, out, pos, n)
            pos += n; i++
        }
        return out
    }

    private fun calcPaddedLen(unpadded: Int): Int {
        if (unpadded <= 32) return 32
        val nextPower = 1 shl (floor(ln((unpadded - 1).toDouble()) / ln(2.0)).toInt() + 1)
        val chunk = if (nextPower <= 256) 32 else nextPower / 8
        return chunk * (floor((unpadded - 1).toDouble() / chunk).toInt() + 1)
    }

    private fun pad(plaintext: String): ByteArray {
        val unpadded = plaintext.toByteArray(Charsets.UTF_8)
        val n = unpadded.size
        require(n in 1..65535) { "평문 길이 범위 위반: $n" }
        val paddedLen = calcPaddedLen(n)
        val out = ByteArray(2 + paddedLen)
        out[0] = ((n ushr 8) and 0xff).toByte()         // big-endian 길이 prefix
        out[1] = (n and 0xff).toByte()
        System.arraycopy(unpadded, 0, out, 2, n)
        return out
    }

    fun encrypt(plaintext: String, conversationKey: ByteArray, nonce: ByteArray? = null): String {
        val nn = nonce ?: ByteArray(32).also { rng.nextBytes(it) }
        val keys = hkdfExpand(conversationKey, nn, 76)
        val chachaKey = keys.copyOfRange(0, 32)
        val chachaNonce = keys.copyOfRange(32, 44)
        val hmacKey = keys.copyOfRange(44, 76)
        val padded = pad(plaintext)
        val ciphertext = ChaCha20.apply(chachaKey, chachaNonce, padded)
        val mac = hmac(hmacKey, nn + ciphertext)        // aad = nonce
        val payload = byteArrayOf(2) + nn + ciphertext + mac
        return Base64.encodeToString(payload, Base64.NO_WRAP)
    }
}
