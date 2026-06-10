package com.indiebiz.phoneagent

import android.content.Context
import android.util.Log

/** 폰 키 관리 + 메시지를 NIP-17 DM 으로 indiebizOS 에 push. */
object Sender {
    private const val TAG = "IndieBizAgent"

    /** 폰 에이전트의 영속 Nostr privkey (없으면 생성). */
    fun phonePrivHex(ctx: Context): String {
        val sp = ctx.getSharedPreferences("phoneagent", Context.MODE_PRIVATE)
        var hex = sp.getString("priv", null)
        if (hex == null) {
            hex = NostrCrypto.toHex(NostrCrypto.randomPrivKey())
            sp.edit().putString("priv", hex).apply()
            val pub = NostrCrypto.toHex(NostrCrypto.xonlyPub(NostrCrypto.fromHex(hex)))
            Log.i(TAG, "폰 신원 생성: pubkey=$pub")
        }
        return hex
    }

    /** 백그라운드 스레드에서 호출 권장(크립토+소켓). */
    fun send(ctx: Context, message: String) {
        try {
            val priv = phonePrivHex(ctx)
            val wrap = Nip17.wrapDm(priv, Config.RECIPIENT_PUB, message)
            Log.i(TAG, "NIP-17 wrap 생성 (${wrap.length}B) → 발행")
            RelayClient.publish(wrap, Config.DM_RELAYS)
        } catch (e: Throwable) {
            Log.e(TAG, "send 실패: ${e.message}", e)
        }
    }

    fun sendAsync(ctx: Context, message: String) {
        Thread { send(ctx.applicationContext, message) }.start()
    }
}
