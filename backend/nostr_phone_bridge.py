"""
폰 네이티브 nostr 브리지 (Chaquopy Java ↔ Python).

폰(Chaquopy)에선 pynostr/coincurve(C·libsecp256k1) 가 빌드 불가하므로, nostr
프리미티브를 폰의 Kotlin 스택(RelayClient/Sender/NostrCrypto/Nip17/Nip44)에 위임한다.
indienet.py 가 INDIEBIZ_PROFILE=phone 일 때만 이 모듈로 분기한다(상위 로직=피드 필터
구성·이벤트 파싱·보드 그룹핑은 indienet 에서 공유 — 드리프트 0).

★ 이 모듈은 폰에서만 import 된다. PC(맥)에선 절대 import 되지 않는다(java 브리지 부재).
"""
import json

_RelayClient = None
_Sender = None
_NostrCrypto = None
_Nip17 = None
_app_ctx = None


def _ensure():
    """Chaquopy Java 클래스 + Android Context 지연 바인딩."""
    global _RelayClient, _Sender, _NostrCrypto, _Nip17, _app_ctx
    if _RelayClient is not None:
        return
    from java import jclass
    _RelayClient = jclass("com.indiebiz.phoneagent.RelayClient")
    _Sender = jclass("com.indiebiz.phoneagent.Sender")
    _NostrCrypto = jclass("com.indiebiz.phoneagent.NostrCrypto")
    _Nip17 = jclass("com.indiebiz.phoneagent.Nip17")
    from com.chaquo.python import Python
    _app_ctx = Python.getPlatform().getApplication()


def _jlist(seq):
    """Python list → java.util.ArrayList (Chaquopy 자동 변환 미지원 우회)."""
    from java.util import ArrayList
    jl = ArrayList()
    for x in seq:
        jl.add(str(x))
    return jl


def query_relays(req_filter: dict, relays, timeout: int = 10) -> list:
    """전 릴레이에 동일 REQ fan-out → 수집·dedup 된 이벤트 dict 리스트.

    파싱/accept 는 호출자(indienet)가 한다 — 여기선 raw nostr event 만 돌려준다.
    """
    _ensure()
    raw = _RelayClient.query(json.dumps(req_filter), _jlist(relays), int(timeout * 1000))
    try:
        return json.loads(str(raw))
    except Exception:
        return []


def publish_note(kind: int, tags, content: str, relays, created_at: int = None) -> str:
    """이벤트 빌드+서명(NostrCrypto) → 전 릴레이 발행(RelayClient). event id 반환."""
    _ensure()
    import time
    if created_at is None:
        created_at = int(time.time())
    ev_json = str(_NostrCrypto.INSTANCE.buildEvent(
        priv_hex(), int(kind), json.dumps(tags), content, int(created_at)))
    _RelayClient.INSTANCE.publish(ev_json, _jlist(relays))
    try:
        return json.loads(ev_json).get("id")
    except Exception:
        return None


def send_dm(to_hex: str, content: str, relays) -> str:
    """NIP-17 gift-wrap(Kotlin Nip17.wrapDm) 빌드 → DM 릴레이 발행. gift-wrap id 반환."""
    _ensure()
    wrap = str(_Nip17.INSTANCE.wrapDm(priv_hex(), to_hex, content))
    _RelayClient.INSTANCE.publish(wrap, _jlist(relays))
    try:
        return json.loads(wrap).get("id")
    except Exception:
        return None


def unwrap_dm(event: dict):
    """수신 gift-wrap(kind:1059) 언랩(Kotlin Nip17.unwrapDm) → {sender, content, created_at}.

    우리 대상 아님/복호 실패 시 None (예외를 잡아 스킵).
    """
    _ensure()
    try:
        out = str(_Nip17.INSTANCE.unwrapDm(priv_hex(), json.dumps(event)))
        return json.loads(out)
    except Exception:
        return None


def priv_hex() -> str:
    """폰 nostr 개인키 hex (SharedPreferences phoneagent/priv, 없으면 생성)."""
    _ensure()
    # Kotlin object 메서드(비-@JvmStatic) → INSTANCE 로 호출.
    return str(_Sender.INSTANCE.phonePrivHex(_app_ctx))


def pub_hex() -> str:
    """폰 nostr 공개키(xonly, 32B) hex."""
    _ensure()
    nc = _NostrCrypto.INSTANCE
    priv = nc.fromHex(priv_hex())
    return str(nc.toHex(nc.xonlyPub(priv)))
