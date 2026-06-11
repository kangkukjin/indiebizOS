package com.indiebiz.phoneagent

/** indiebizOS(indienet) 수신 신원 + DM 릴레이. */
object Config {
    // indienet 계정 pubkey (x-only hex) — 폰이 gift-wrap DM 을 이쪽으로 보낸다.
    const val RECIPIENT_PUB = "8480af0aa2476f927535ab3a05bac58412ffb8eab1fed16d6c82bf4317255ed9"

    // 런처 백엔드 주소: 데스크탑 연결 시 adb reverse 로 127.0.0.1 이 맥미니로 포워드되고,
    // 추후 폰 임베드 파이썬으로 가면 진짜 로컬이 된다. 어느 쪽이든 같은 URL.
    const val LAUNCHER_URL = "http://127.0.0.1:8765/launcher/app"

    val DM_RELAYS = listOf(
        "wss://nos.lol",
        "wss://relay.damus.io",
        "wss://relay.nostr.band",
        "wss://relay.primal.net",
        "wss://nostr.wine"
    )
}
