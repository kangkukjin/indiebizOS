package com.indiebiz.phoneagent

/**
 * ChaCha20 스트림 암호 (RFC 8439). counter=0 시작, 12바이트 nonce.
 * Android 가 javax.crypto.spec.ChaCha20ParameterSpec 를 공개 API 로 노출하지 않아 직접 구현.
 * NIP-44(backend/nip44.py 의 _chacha20)와 동일: full_nonce = LE(counter=0,4B) + nonce(12B).
 */
object ChaCha20 {

    fun apply(key: ByteArray, nonce12: ByteArray, data: ByteArray): ByteArray {
        require(key.size == 32) { "key 32B" }
        require(nonce12.size == 12) { "nonce 12B" }
        val out = ByteArray(data.size)
        val state = IntArray(16)
        state[0] = 0x61707865; state[1] = 0x3320646e
        state[2] = 0x79622d32; state[3] = 0x6b206574
        for (i in 0 until 8) state[4 + i] = leInt(key, i * 4)
        for (i in 0 until 3) state[13 + i] = leInt(nonce12, i * 4)

        var counter = 0
        var pos = 0
        val block = IntArray(16)
        val ks = ByteArray(64)
        while (pos < data.size) {
            state[12] = counter
            chachaBlock(state, block)
            for (i in 0 until 16) {
                ks[i * 4] = (block[i] and 0xff).toByte()
                ks[i * 4 + 1] = ((block[i] ushr 8) and 0xff).toByte()
                ks[i * 4 + 2] = ((block[i] ushr 16) and 0xff).toByte()
                ks[i * 4 + 3] = ((block[i] ushr 24) and 0xff).toByte()
            }
            val n = minOf(64, data.size - pos)
            for (i in 0 until n) out[pos + i] = (data[pos + i].toInt() xor ks[i].toInt()).toByte()
            pos += n
            counter++
        }
        return out
    }

    private fun leInt(b: ByteArray, off: Int): Int =
        (b[off].toInt() and 0xff) or
        ((b[off + 1].toInt() and 0xff) shl 8) or
        ((b[off + 2].toInt() and 0xff) shl 16) or
        ((b[off + 3].toInt() and 0xff) shl 24)

    private fun rotl(x: Int, n: Int): Int = (x shl n) or (x ushr (32 - n))

    private fun qr(x: IntArray, a: Int, b: Int, c: Int, d: Int) {
        x[a] += x[b]; x[d] = rotl(x[d] xor x[a], 16)
        x[c] += x[d]; x[b] = rotl(x[b] xor x[c], 12)
        x[a] += x[b]; x[d] = rotl(x[d] xor x[a], 8)
        x[c] += x[d]; x[b] = rotl(x[b] xor x[c], 7)
    }

    private fun chachaBlock(input: IntArray, out: IntArray) {
        val x = input.copyOf()
        repeat(10) {                 // 20 rounds = 10 double-rounds
            qr(x, 0, 4, 8, 12); qr(x, 1, 5, 9, 13); qr(x, 2, 6, 10, 14); qr(x, 3, 7, 11, 15)
            qr(x, 0, 5, 10, 15); qr(x, 1, 6, 11, 12); qr(x, 2, 7, 8, 13); qr(x, 3, 4, 9, 14)
        }
        for (i in 0 until 16) out[i] = x[i] + input[i]
    }
}
