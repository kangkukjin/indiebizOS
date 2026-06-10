package com.indiebiz.phoneagent

import fr.acinq.secp256k1.Secp256k1
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * Nostr 기본 크립토: 키, x-only pubkey, 이벤트 id(NIP-01 정규직렬화),
 * schnorr 서명(BIP340), ECDH 원시 X좌표(NIP-44 공유비밀).
 * backend/nip44.py·nip17.py 와 정확히 일치해야 한다.
 */
object NostrCrypto {
    private val rng = SecureRandom()

    fun randomPrivKey(): ByteArray = ByteArray(32).also { rng.nextBytes(it) }

    /** priv → x-only(32B) pubkey. */
    fun xonlyPub(priv: ByteArray): ByteArray {
        val pub = Secp256k1.pubkeyCreate(priv)          // 65B uncompressed
        val comp = Secp256k1.pubKeyCompress(pub)        // 33B compressed
        return comp.copyOfRange(1, 33)
    }

    fun sha256(b: ByteArray): ByteArray =
        MessageDigest.getInstance("SHA-256").digest(b)

    fun toHex(b: ByteArray): String {
        val hex = "0123456789abcdef"
        val sb = StringBuilder(b.size * 2)
        for (x in b) {
            val v = x.toInt() and 0xff
            sb.append(hex[v ushr 4]).append(hex[v and 0x0f])
        }
        return sb.toString()
    }

    fun fromHex(s: String): ByteArray {
        val out = ByteArray(s.length / 2)
        for (i in out.indices) {
            out[i] = ((Character.digit(s[2 * i], 16) shl 4) +
                    Character.digit(s[2 * i + 1], 16)).toByte()
        }
        return out
    }

    /** NIP-44 공유비밀: ECDH 점의 원시 X좌표(해시 안 함). lift(x-only, even-Y) * priv. */
    fun ecdhX(privHex: String, pubXonlyHex: String): ByteArray {
        val priv = fromHex(privHex)
        val compressed = ByteArray(33)
        compressed[0] = 0x02                            // even-Y lift (BIP340/Nostr 관례)
        System.arraycopy(fromHex(pubXonlyHex), 0, compressed, 1, 32)
        val point = Secp256k1.pubkeyParse(compressed)   // 65B
        val shared = Secp256k1.pubKeyTweakMul(point, priv)  // priv * Point, 65B
        return shared.copyOfRange(1, 33)                // X
    }

    fun signSchnorr(msg32: ByteArray, priv: ByteArray): ByteArray {
        val aux = ByteArray(32).also { rng.nextBytes(it) }
        return Secp256k1.signSchnorr(msg32, priv, aux)
    }

    fun verifySchnorr(sig: ByteArray, msg32: ByteArray, pubXonly: ByteArray): Boolean =
        Secp256k1.verifySchnorr(sig, msg32, pubXonly)

    /** NIP-01 이벤트 id: sha256( [0,pubkey,created_at,kind,tags,content] 정규직렬화 ). */
    fun eventId(pubHex: String, createdAt: Long, kind: Int,
                tags: List<List<String>>, content: String): ByteArray {
        val sb = StringBuilder()
        sb.append("[0,\"").append(pubHex).append("\",")
            .append(createdAt).append(',').append(kind).append(',')
            .append(tagsToJson(tags)).append(',')
            .append(escape(content)).append(']')
        return sha256(sb.toString().toByteArray(Charsets.UTF_8))
    }

    private fun tagsToJson(tags: List<List<String>>): String {
        val sb = StringBuilder("[")
        for ((i, tag) in tags.withIndex()) {
            if (i > 0) sb.append(',')
            sb.append('[')
            for ((j, e) in tag.withIndex()) {
                if (j > 0) sb.append(',')
                sb.append(escape(e))
            }
            sb.append(']')
        }
        return sb.append(']').toString()
    }

    /** NIP-01 문자열 이스케이프(따옴표 포함). 제어문자는 code 로 비교. */
    fun escape(s: String): String {
        val sb = StringBuilder("\"")
        for (c in s) {
            when (c.code) {
                0x22 -> sb.append("\\\"")
                0x5C -> sb.append("\\\\")
                0x0A -> sb.append("\\n")
                0x0D -> sb.append("\\r")
                0x09 -> sb.append("\\t")
                0x08 -> sb.append("\\b")
                0x0C -> sb.append("\\f")
                else -> if (c.code < 0x20)
                    sb.append("\\u").append(String.format("%04x", c.code))
                else sb.append(c)
            }
        }
        return sb.append("\"").toString()
    }
}
