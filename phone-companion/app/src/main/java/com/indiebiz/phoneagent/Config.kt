package com.indiebiz.phoneagent

/** indiebizOS(indienet) 수신 신원 + DM 릴레이. */
object Config {
    // indienet 계정 pubkey (x-only hex) — 폰이 gift-wrap DM 을 이쪽으로 보낸다.
    const val RECIPIENT_PUB = "8480af0aa2476f927535ab3a05bac58412ffb8eab1fed16d6c82bf4317255ed9"

    val DM_RELAYS = listOf(
        "wss://nos.lol",
        "wss://relay.damus.io",
        "wss://relay.nostr.band",
        "wss://relay.primal.net",
        "wss://nostr.wine"
    )
}
