"""IndieNet 공통 기반 (2026-07-18 모듈화 — 1500줄 규칙)

indienet.py 에서 verbatim 이동: pynostr/websocket 가용성 감지(HAS_NOSTR·더미 타입),
폰 프로파일 감지(_ON_PHONE — ★INDIEBIZ_PROFILE 분기의 정의처, 포크-가드 allowlist 등재),
데이터 경로·기본 릴레이·태그 상수. 리프 모듈 — 본체·믹스인이 모두 여기서 import.
"""
import os
from pathlib import Path

try:
    from pynostr.key import PrivateKey, PublicKey
    from pynostr.event import Event, EventKind
    import websocket
    HAS_NOSTR = True
except ImportError:
    HAS_NOSTR = False
    print("⚠️  IndieNet: pynostr 필요 - pip install pynostr websocket-client")
    # 타입 힌트를 위한 더미 클래스 정의
    class Event:
        pass
    class EventKind:
        TEXT_NOTE = 1
        ENCRYPTED_DIRECT_MESSAGE = 4
    class PrivateKey:
        pass
    class PublicKey:
        pass

# 폰 네이티브: pynostr/coincurve(C·libsecp256k1) 가 Chaquopy 에 빌드 불가 → nostr
# 프리미티브를 폰 Kotlin 스택(RelayClient/Sender/NostrCrypto/Nip17/Nip44)에 위임한다.
# (relay 읽기/쓰기·서명·NIP-17/44 = nostr_phone_bridge. 상위 로직은 이 파일에서 공유 → 드리프트 0.)
_ON_PHONE = os.environ.get("INDIEBIZ_PROFILE") == "phone"


# IndieNet 데이터 디렉토리
INDIENET_DIR = Path.home() / '.indiebiz' / 'indienet'
IDENTITY_FILE = INDIENET_DIR / 'identity.json'
SETTINGS_FILE = INDIENET_DIR / 'settings.json'
CACHE_DIR = INDIENET_DIR / 'cache'
POSTS_DB = INDIENET_DIR / 'posts.db'  # 공개 글 영구 캐시 (릴레이 prune 대비)
DMS_DB = INDIENET_DIR / 'dms.db'      # 수신 DM 영구 캐시 (릴레이 prune 대비)

# 기본 릴레이
DEFAULT_RELAYS = [
    # 2026-06-12: 도달성 실측 후 정리 — nostr.wine(403 유료 거부)·nostr.band(상시 타임아웃) 제거,
    # 확인된 무료 릴레이로 중복성 확보(글 prune 대비 fan-out 읽기/쓰기 대상).
    'wss://nos.lol',
    'wss://relay.damus.io',
    'wss://relay.primal.net',
    'wss://relay.snort.social',
    'wss://nostr.mom',
    'wss://purplepag.es',
]

# NIP-17 DM inbox 릴레이 (kind:10050 으로 선언 = 남이 나에게 gift-wrap 을 보낼 주소).
# 일반 릴레이와 목록이 다른 이유: 연결이 열린다고 kind:1059 를 받아 주는 게 아니다.
# 2026-08-30 실측(일회용 키로 만든 gift-wrap 을 릴레이별로 던져 OK 판정을 읽음, 3회):
#   relay.primal.net 3/3 · relay.nostr.net 3/3 · relay.damus.io 2/3(Cloudflare 503 간헐)
#   nos.lol 2/4(간헐 무응답) · nostr.mom 2/3(무응답, NIP-11 없음)
#   purplepag.es 0/3 — "blocked: kind 1059 is not allowed" (메타데이터 전용 릴레이)
# ★핸드셰이크 성공률로 고르면 purplepag.es 를 뽑는 함정이 있다 — 판정은 OK 프레임의
#   수락 플래그로만 내린다(같은 날 _publish_event 수리와 한 벌).
DEFAULT_DM_RELAYS = [
    'wss://nos.lol',
    'wss://relay.damus.io',
    'wss://relay.primal.net',
    'wss://relay.nostr.net',
]

# IndieNet 해시태그
INDIENET_TAG = "IndieNet"

# 폰 네이티브: pynostr/coincurve(C·libsecp256k1) 가 Chaquopy 에 빌드 불가 → nostr
# 프리미티브를 폰 Kotlin 스택(RelayClient/Sender/NostrCrypto/Nip17/Nip44)에 위임한다.
# (relay 읽기/쓰기·서명·NIP-17/44 = nostr_phone_bridge. 상위 로직은 믹스인에서 공유 → 드리프트 0.)
_ON_PHONE = os.environ.get("INDIEBIZ_PROFILE") == "phone"
