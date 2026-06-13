package com.indiebiz.phoneagent

import org.json.JSONArray
import org.json.JSONObject
import java.security.SecureRandom

/**
 * NIP-17 gift-wrap DM. rumor(14) → seal(13) → gift wrap(1059).
 * backend/nip17.py 와 동일 구조. 결과 wrap JSON 을 DM 릴레이로 발행한다.
 */
object Nip17 {
    private val rng = SecureRandom()
    private const val KIND_DM = 14
    private const val KIND_SEAL = 13
    private const val KIND_GIFT = 1059
    private const val TWO_DAYS = 2 * 24 * 3600

    private fun randomPast(now: Long): Long = now - rng.nextInt(TWO_DAYS + 1).toLong()

    private fun pTag(recipient: String) = JSONArray().put(JSONArray().put("p").put(recipient))

    fun wrapDm(senderPrivHex: String, recipientPubHex: String, message: String): String {
        val now = System.currentTimeMillis() / 1000
        val senderPub = NostrCrypto.toHex(NostrCrypto.xonlyPub(NostrCrypto.fromHex(senderPrivHex)))
        val recipTags = listOf(listOf("p", recipientPubHex))

        // 1) rumor (kind 14, 미서명)
        val rumorId = NostrCrypto.toHex(
            NostrCrypto.eventId(senderPub, now, KIND_DM, recipTags, message))
        val rumor = JSONObject()
            .put("id", rumorId)
            .put("pubkey", senderPub)
            .put("created_at", now)
            .put("kind", KIND_DM)
            .put("tags", pTag(recipientPubHex))
            .put("content", message)

        // 2) seal (kind 13): rumor 를 발신자→수신자 NIP-44 암호화, 발신자 서명
        val sealCk = Nip44.conversationKey(senderPrivHex, recipientPubHex)
        val sealContent = Nip44.encrypt(rumor.toString(), sealCk)
        val sealCreated = randomPast(now)
        val sealId = NostrCrypto.eventId(senderPub, sealCreated, KIND_SEAL, emptyList(), sealContent)
        val sealSig = NostrCrypto.toHex(NostrCrypto.signSchnorr(sealId, NostrCrypto.fromHex(senderPrivHex)))
        val seal = JSONObject()
            .put("id", NostrCrypto.toHex(sealId))
            .put("pubkey", senderPub)
            .put("created_at", sealCreated)
            .put("kind", KIND_SEAL)
            .put("tags", JSONArray())
            .put("content", sealContent)
            .put("sig", sealSig)

        // 3) gift wrap (kind 1059): 일회용 임시키로 seal 암호화·서명, #p=수신자
        val ephPriv = NostrCrypto.randomPrivKey()
        val ephPrivHex = NostrCrypto.toHex(ephPriv)
        val ephPub = NostrCrypto.toHex(NostrCrypto.xonlyPub(ephPriv))
        val wrapCk = Nip44.conversationKey(ephPrivHex, recipientPubHex)
        val wrapContent = Nip44.encrypt(seal.toString(), wrapCk)
        val wrapCreated = randomPast(now)
        val wrapId = NostrCrypto.eventId(ephPub, wrapCreated, KIND_GIFT, recipTags, wrapContent)
        val wrapSig = NostrCrypto.toHex(NostrCrypto.signSchnorr(wrapId, ephPriv))
        val wrap = JSONObject()
            .put("id", NostrCrypto.toHex(wrapId))
            .put("pubkey", ephPub)
            .put("created_at", wrapCreated)
            .put("kind", KIND_GIFT)
            .put("tags", pTag(recipientPubHex))
            .put("content", wrapContent)
            .put("sig", wrapSig)

        return wrap.toString()
    }

    /**
     * gift wrap(1059) 수신 → 언랩. wrapDm 역순: gift 복호 → seal 복호 → rumor.
     * @return JSON {sender(발신 pubkey hex), content(평문), created_at(rumor 시각)}
     */
    fun unwrapDm(recipientPrivHex: String, giftWrapJson: String): String {
        val wrap = JSONObject(giftWrapJson)
        val ephPub = wrap.getString("pubkey")
        // 1) gift wrap 복호(임시키→나) → seal
        val wrapCk = Nip44.conversationKey(recipientPrivHex, ephPub)
        val seal = JSONObject(Nip44.decrypt(wrap.getString("content"), wrapCk))
        // 2) seal 복호(발신자→나) → rumor
        val senderPub = seal.getString("pubkey")
        val sealCk = Nip44.conversationKey(recipientPrivHex, senderPub)
        val rumor = JSONObject(Nip44.decrypt(seal.getString("content"), sealCk))
        // 3) rumor.pubkey 가 진짜 발신자(seal.pubkey 와 같아야 정상)
        return JSONObject()
            .put("sender", rumor.getString("pubkey"))
            .put("content", rumor.getString("content"))
            .put("created_at", rumor.optLong("created_at"))
            .toString()
    }
}
