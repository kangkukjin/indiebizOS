"""ask_mailbox.py — [others:ask] 보편 우편함 (Nostr DM/NIP-17 신호층)

특권 소멸 1단계 (docs/NO_PRIVILEGED_RAILS_HANDOFF.md): 몸 사이 신호층(부탁·클립보드
텍스트 같은 작고 드문 것)을 env 주소+공유 토큰 전용선이 아니라 **보편 매체**(Nostr
DM)로 나른다. HTTP 직결이 안 될 때(LTE/CGNAT·다른 네트워크)의 ask 폴백이자,
하트비트 푸시 큐(허브-위성 특권 배관 #1)의 이웃-문법 대체.

원칙:
- 발신자 신원 = **npub**(NIP-17 seal 서명이 증명 — 자기보고 device_id 의 승격).
  신뢰 판정은 body_ask.handle_ask 의 원장 게이트가 한다(identity 키 = "npub:<hex>").
  낯선 npub = 낯선 몸 = 정직한 거절. 이 우편함은 몸끼리든 낯선 몸이든 같은 문.
- 상대의 코드는 건너오지 않는다 — 자연어 부탁(+payload 동봉)만. 컴파일은 받는 몸의 일.
- 신호층 한정: 봉투는 NIP-44 평문 한도(64KB) 안. 파일·스트림은 대량층(HTTP)의 일.

배관:
- 발신: 봉투(JSON)를 NIP-17 gift-wrap 으로 ASK_RELAYS 에 발행. 맥=nip17+IndieNet,
  폰=nostr_phone_bridge(Kotlin). 상관관계 id 로 결과 봉투를 기다린다(수신 경로 공유
  + 능동 폴 — 리스너가 없어도 발신자는 자급).
- 수신: 맥=channel_poller 상시 구독(kind:1059)이 handle_dm_content 로 넘김 /
  폰=phone_api 폴링 데몬(poll_once, 릴레이가 EOSE 에 닫혀 상시 구독 불가 — 원샷 REQ 주기).
- 중복 제거: gift-wrap id(언랩 전) + 봉투 id(언랩 후, 디스크 영속) 2층 — 릴레이
  재전달·재시작 재생을 막는다. freshness: 봉투 ts 기준 TTL(과거 백필 대량 실행 방지).

★자기교착 부류: 이 모듈의 발행/폴/실행은 전부 이벤트 루프 밖(워커/데몬 스레드)에서.
"""
import json
import os
import threading
import time
from typing import Any, Dict, List, Optional

# 양쪽 몸이 같은 곳을 보는 우편함 릴레이 — indienet_social._self_dm_relays 와 정렬
# (kind:10050 선언·맥 상시 구독 대상과 겹침). 바꾸면 양쪽 몸을 함께 바꿔야 한다.
ASK_RELAYS = ["wss://nos.lol", "wss://relay.damus.io"]

ENVELOPE_KEY = "indiebiz_ask"   # 봉투 감지 키 (rumor content JSON 최상위)
ASK_TTL_SEC = 600               # op=ask 신선도 창 — 이보다 낡은 부탁은 실행 안 함
_SEEN_PRUNE_SEC = 2 * 3600      # 봉투 id 영속 기억 보존 창(TTL 의 여유 배수)
_MAX_CONTENT_BYTES = 60 * 1024  # NIP-44 평문 한도(64KB) 안전 마진

_gift_seen: set = set()                       # gift-wrap id (프로세스 내)
_env_seen: Dict[str, float] = {}              # 봉투 id → ts (디스크 영속)
_env_seen_lock = threading.Lock()
_env_seen_loaded = False

_waiters: Dict[str, Dict[str, Any]] = {}      # corr_id → {event, result}
_waiters_lock = threading.Lock()


def _base() -> str:
    return os.environ.get("INDIEBIZ_BASE_PATH") or os.path.join(os.path.dirname(__file__), "..")


def _seen_path() -> str:
    return os.path.join(_base(), "data", "ask_mailbox_seen.json")


def _on_phone() -> bool:
    # 포크-가드: PROFILE env 직접 분기 금지 — detect_body 경유.
    try:
        from runtime_utils import detect_body
        return (detect_body() or {}).get("profile") == "phone"
    except Exception:
        return False


def _self_keys() -> Optional[Dict[str, str]]:
    """이 몸의 nostr 키쌍 {priv, pub}(hex). 신원 미가용이면 None(우편함 비활성)."""
    try:
        if _on_phone():
            import nostr_phone_bridge as bridge
            return {"priv": bridge.priv_hex(), "pub": bridge.pub_hex()}
        from indienet import get_indienet
        idn = get_indienet()
        if not getattr(idn, "_initialized", False):
            return None
        return {"priv": idn.identity.private_key.hex(),
                "pub": idn.identity.public_key.hex()}
    except Exception:
        return None


# === 봉투 id 영속 기억 (재시작 후 재생 방지) ===

def _load_env_seen():
    global _env_seen_loaded
    if _env_seen_loaded:
        return
    with _env_seen_lock:
        if _env_seen_loaded:
            return
        try:
            with open(_seen_path(), "r", encoding="utf-8") as f:
                data = json.load(f)
            now = time.time()
            _env_seen.update({k: v for k, v in (data or {}).items()
                              if now - float(v) < _SEEN_PRUNE_SEC})
        except Exception:
            pass
        _env_seen_loaded = True


def _mark_env_seen(env_id: str) -> bool:
    """봉투 id 기억. 이미 본 것이면 False(중복)."""
    _load_env_seen()
    now = time.time()
    with _env_seen_lock:
        if env_id in _env_seen:
            return False
        _env_seen[env_id] = now
        for k in [k for k, v in _env_seen.items() if now - v > _SEEN_PRUNE_SEC]:
            _env_seen.pop(k, None)
        try:
            with open(_seen_path(), "w", encoding="utf-8") as f:
                json.dump(_env_seen, f)
        except Exception:
            pass
    return True


# === 발신 프리미티브 (몸-인식) ===

def _send_envelope(to_hex: str, env: Dict[str, Any]) -> Optional[str]:
    """봉투를 NIP-17 gift-wrap 으로 ASK_RELAYS 에 발행. gift-wrap id 반환."""
    content = json.dumps(env, ensure_ascii=False)
    if len(content.encode("utf-8")) > _MAX_CONTENT_BYTES:
        raise ValueError("봉투가 신호층 한도(60KB)를 넘습니다 — 파일·대용량은 대량층(HTTP)으로.")
    if _on_phone():
        import nostr_phone_bridge as bridge
        return bridge.send_dm(to_hex, content, ASK_RELAYS)
    keys = _self_keys()
    if not keys:
        return None
    import nip17
    from indienet import get_indienet
    wrap = nip17.wrap_dm(keys["priv"], to_hex, content,
                         extra_tags=[[nip17.INDIEBIZ_TAG, nip17.INDIEBIZ_PROTOCOL]])
    return get_indienet()._publish_event(wrap, relays=ASK_RELAYS)


# === 수신 프리미티브 (몸-인식) ===

def _raw_query(limit: int = 40, timeout: int = 8) -> List[dict]:
    keys = _self_keys()
    if not keys:
        return []
    flt = {"kinds": [1059], "#p": [keys["pub"]], "limit": limit}
    if _on_phone():
        import nostr_phone_bridge as bridge
        return bridge.query_relays(flt, ASK_RELAYS, timeout=timeout) or []
    from indienet import get_indienet
    return get_indienet()._query_relays(flt, lambda ev: ev, timeout=timeout,
                                        relays=ASK_RELAYS) or []


def _unwrap(event: dict) -> Optional[dict]:
    try:
        if _on_phone():
            import nostr_phone_bridge as bridge
            return bridge.unwrap_dm(event)
        keys = _self_keys()
        if not keys:
            return None
        import nip17
        return nip17.unwrap_dm(keys["priv"], event)
    except Exception:
        return None


def poll_once(limit: int = 40) -> int:
    """우편함 원샷 폴 — 새 gift-wrap 만 언랩해 봉투 처리. 처리한 봉투 수 반환.

    폰 데몬(phone_api)·발신 대기 루프가 공용. gift id 를 언랩 *전에* 걸러
    반복 폴의 언랩 비용을 없앤다(릴레이는 매번 최근 N 개를 다시 준다).
    """
    n = 0
    try:
        events = _raw_query(limit=limit)
    except Exception:
        return 0
    for ev in events:
        gid = (ev or {}).get("id")
        if not gid or gid in _gift_seen:
            continue
        _gift_seen.add(gid)
        out = _unwrap(ev)
        if not out or not out.get("content"):
            continue
        if handle_dm_content(out.get("sender", ""), out["content"],
                             out.get("created_at")):
            n += 1
    if len(_gift_seen) > 4000:  # 무한 성장 방지(오래된 절반 버림 — 봉투 id 층이 재차 거름)
        for k in list(_gift_seen)[:2000]:
            _gift_seen.discard(k)
    return n


# === 봉투 처리 (수신 공용 진입점) ===

def handle_dm_content(sender_hex: str, content: str, created_at=None) -> bool:
    """DM 평문이 ask 봉투면 소비하고 True — 아니면 False(일반 DM, 호출자가 계속 처리).

    맥 channel_poller._handle_nostr_giftwrap 과 폰 poll_once 가 공용으로 부른다.
    """
    if not content or not content.startswith("{") or ENVELOPE_KEY not in content[:40]:
        return False
    try:
        env = json.loads(content)
    except Exception:
        return False
    if not isinstance(env, dict) or ENVELOPE_KEY not in env:
        return False

    env_id = str(env.get("id") or "")
    op = env.get("op")
    if not env_id or op not in ("ask", "result"):
        return True  # 봉투이긴 하나 형식 불량 — 소비(일반 DM 로 흘리지 않음)

    if op == "result":
        # 결과는 살아있는 대기자에게만 의미 — 대기자 없으면 조용히 소비.
        with _waiters_lock:
            w = _waiters.get(env_id)
            if w is not None:
                w["result"] = env.get("result")
                w["event"].set()
        return True

    # op == "ask"
    if not _mark_env_seen(env_id):
        return True  # 중복(릴레이 재전달·재시작 재생)
    ts = env.get("ts") or created_at or 0
    if ts and time.time() - float(ts) > ASK_TTL_SEC:
        return True  # 낡은 부탁 — 실행하지 않는다(백필 대량 실행 방지)

    # 실행은 워커 스레드로 — 수신 스레드(ws 리스너/폴 데몬)를 막지 않는다.
    threading.Thread(target=_serve_ask, args=(sender_hex, env), daemon=True).start()
    return True


def _serve_ask(sender_hex: str, env: Dict[str, Any]):
    """부탁 봉투 실행 + 결과 봉투 회신. 신뢰 게이트는 handle_ask 원장 게이트가 담당
    (identity 키 = "npub:<hex>" — 부여식에서 npub 접점이 붙은 몸만 통과)."""
    t0 = time.time()
    try:
        from body_ask import handle_ask
        result = handle_ask(env.get("message") or "",
                            dry_run=bool(env.get("dry_run")),
                            from_body=env.get("from_body") or "",
                            device_id=f"npub:{sender_hex}",
                            payload=env.get("payload"))
    except Exception as e:  # noqa: BLE001 — 결과는 항상 봉투로 돌아간다
        result = {"success": False, "error": f"우편함 실행 오류: {e}"}
    reply = {ENVELOPE_KEY: 1, "op": "result", "id": env.get("id"),
             "ts": int(time.time()), "result": result}
    try:
        _send_envelope(sender_hex, reply)
    except Exception as e:
        print(f"[ask_mailbox] 결과 회신 실패: {e}")
    print(f"[ask_mailbox] ask 봉투 처리 {int((time.time()-t0)*1000)}ms "
          f"(from npub:{sender_hex[:12]}…, ok={not (isinstance(result, dict) and result.get('success') is False)})")


# === 발신 (ask_peer 의 우편함 경로) ===

def ask_via_mailbox(to_hex: str, message: str, payload: Optional[dict] = None,
                    from_body: str = "", device_id: str = "",
                    dry_run: bool = False, timeout: float = 60.0) -> Dict[str, Any]:
    """이웃 몸의 npub 로 부탁 봉투를 보내고 결과 봉투를 기다린다.

    결과 수신 = 수동(내 상시 리스너가 result 봉투를 _waiters 로 배달) + 능동(대기
    중 주기 폴 — 리스너가 없어도 자급). timeout 내 미도착 = queued 반환(받는 몸은
    수신 즉시 실행하므로 부탁 자체는 살아 있다 — 클립보드처럼 상대 표면에 결과가
    나타나는 부탁은 그걸로 완결).
    """
    if not to_hex:
        return {"success": False, "error": "상대 몸의 npub 를 모릅니다(명함 미교환)."}
    keys = _self_keys()
    if not keys:
        return {"success": False, "error": "이 몸에 nostr 신원이 없어 우편함을 못 씁니다."}

    import uuid
    corr = uuid.uuid4().hex
    env = {ENVELOPE_KEY: 1, "op": "ask", "id": corr, "ts": int(time.time()),
           "message": message, "from_body": from_body, "device_id": device_id,
           "dry_run": bool(dry_run)}
    if payload:
        env["payload"] = payload

    waiter = {"event": threading.Event(), "result": None}
    with _waiters_lock:
        _waiters[corr] = waiter
    try:
        gid = _send_envelope(to_hex, env)
        if not gid:
            return {"success": False, "error": "우편함 발행 실패(릴레이 무응답)",
                    "node_unreachable": True}
        deadline = time.time() + max(5.0, timeout)
        while time.time() < deadline:
            if waiter["event"].wait(timeout=4.0):
                break
            poll_once()  # 능동 폴 — 상시 리스너 부재/구독 릴레이 불일치에도 자급
        if waiter["event"].is_set():
            res = waiter["result"]
            if isinstance(res, dict):
                res.setdefault("_via", "mailbox")
                return res
            return {"success": True, "result": res, "_via": "mailbox"}
        return {"success": True, "queued": True, "_via": "mailbox",
                "message": "우편함(Nostr DM)에 부탁을 넣었습니다 — 상대 몸이 수신하는 대로 "
                           "실행합니다(결과 회신은 시간 내 도착하지 않음)."}
    finally:
        with _waiters_lock:
            _waiters.pop(corr, None)


def peer_npub(alias: str = "") -> Optional[str]:
    """이웃 몸의 npub(hex) 해소 — 명함 캐시(peer_cards)에서. alias 미지정 시 유일 명함."""
    try:
        from peer_cards import load_all
        cards = [c for c in load_all()
                 if ((c.get("identity") or {}).get("npub"))]
        if alias:
            cards = [c for c in cards if c.get("_alias") == alias
                     or ((c.get("identity") or {}).get("device_id")) == alias]
        if len(cards) == 1:
            return (cards[0].get("identity") or {}).get("npub")
        if alias and cards:
            return (cards[0].get("identity") or {}).get("npub")
    except Exception:
        pass
    return None
