"""media_sessions.py — 공통 미디어 세션 관리자 (2026-10-13).

설계 정본: docs/MEDIA_COMMUNICATION_DESIGN_2026_10_13.md §3·§4·§5·§6·§10, 와이어 계약 docs/MEDIA_SESSION_CONTRACT.md.

한 세션 = 참여 장치·허가 근거·트랙·전송 방식·수명. 허가 근거는 둘뿐이고 서비스가 직접 검증한다:
- accepted_call   : 상대의 수락 사건(초대→수락). 일반 통화. 확장관계 원장을 모른다.
- extension_grant : 확장관계 등록 자격(limb_keys 등록 세대). resident_pcs 가 어댑터.
허가 뒤에는 둘 다 같은 수명(session_lease, 프로필 "media")·같은 시그널 질서(media_signaling)를 쓴다.

미디어 바이트는 여기를 지나지 않는다 — 제어 메시지만. 토큰·SDP·ICE 원문은 로그에 남기지 않는다.
"""
import hashlib
import hmac
import json
import os
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

import media_signaling as sig
import media_store
import runtime_work
import session_lease

PURPOSES = {"voice_call", "video_call", "camera", "microphone", "speaker", "playback"}
CALL_PURPOSES = {"voice_call", "video_call"}
EXTENSION_PURPOSES = {"camera", "microphone", "speaker", "playback"}
ACTIVE_STATES = {"inviting", "ringing", "accepted", "authorized", "connecting", "active", "reconnecting", "needs_local_action"}
_lock = threading.RLock()
_sessions: Dict[str, "Session"] = {}
_requests: Dict[str, str] = {}          # request_id → (fingerprint, session_id)
_hub_secret: Optional[bytes] = None
_sweeper: Optional[threading.Thread] = None
_log: Callable = print
_on_change: List[Callable] = []          # 상태 변화 구독(브라우저 푸시·알림)
rooms = sig.RelayRooms()
nostr = sig.NostrTransport()
device_socket_handler: Optional[Callable] = None   # api_media 가 등록(LAN 직결 제안용)


class MediaError(ValueError):
    def __init__(self, code: str, message: str = ""):
        super().__init__(code)
        self.code, self.message = code, message or code


def _hub_key() -> bytes:
    global _hub_secret
    if _hub_secret is None:
        _hub_secret = secrets.token_bytes(32)
    return _hub_secret


def _now() -> float:
    return time.time()


@dataclass
class Session:
    id: str
    kind: str                       # call | extension
    purpose: str
    basis: str                      # accepted_call | extension_grant
    local_role: str                 # caller | callee | hub
    tracks: List[Dict]
    delivery: str = "realtime"
    participants: List[Dict] = field(default_factory=list)
    consent: Dict = field(default_factory=dict)
    state: str = "inviting"
    revision: int = 0
    generation: int = 0
    lease: session_lease.Lease = field(default_factory=lambda: session_lease.Lease("media"))
    expires_at: Optional[float] = None
    created_at: float = field(default_factory=_now)
    ended_at: Optional[float] = None
    end_reason: str = ""
    error: Optional[Dict] = None
    needs_local_action: Optional[Dict] = None
    path: Optional[str] = None
    quality: Dict = field(default_factory=dict)
    content: Optional[Dict] = None
    signaling: Dict = field(default_factory=dict)
    ice_servers: List[Dict] = field(default_factory=list)
    request_id: Optional[str] = None
    secret: str = ""                # 세션 비밀(hex) — 원격 프레임 HMAC
    peer: Optional[str] = None      # 통화 상대 pubkey(hex)
    device: Optional[str] = None    # 확장 장치 device_id
    device_alias: Optional[str] = None
    relation_generation: Optional[str] = None
    device_job: Optional[str] = None
    grants: Dict[str, Dict] = field(default_factory=dict)
    local_box: sig.Outbox = field(default_factory=sig.Outbox)      # → 브라우저 엔진
    remote_box: sig.Outbox = field(default_factory=sig.Outbox)     # → 장치 WS(확장) 또는 릴레이 회원
    orders: Dict[str, sig.Order] = field(default_factory=dict)
    buffers: Dict[str, sig.CandidateBuffer] = field(default_factory=dict)
    relay_client: Optional[sig.RelayClient] = None
    pending_offer: Optional[Dict] = None     # 초대에 동봉할/동봉된 offer
    pending_answer: Optional[Dict] = None
    bundle_event: threading.Event = field(default_factory=threading.Event)
    accept_sent: bool = False
    invite_sent: bool = False
    early_signals: List[Dict] = field(default_factory=list)
    remote_attached: bool = False
    local_attached: bool = False
    content_state: Dict = field(default_factory=dict)
    quality_profile: Dict = field(default_factory=dict)
    disconnected_at: Optional[float] = None
    out_seq: int = 0                 # 허브 → 장치 keepalive 순번
    camera: Optional[str] = None     # 확장 카메라 선택(front|back), 장치가 해석
    device_caps: Dict = field(default_factory=dict)   # 장치가 ready 로 신고한 능력
    keepalive_sent_at: float = 0.0

    def public(self) -> Dict:
        return {
            "session_id": self.id, "protocol_version": sig.PROTOCOL_VERSION, "kind": self.kind, "purpose": self.purpose,
            "authorization_basis": self.basis, "local_role": self.local_role, "participants": list(self.participants),
            "tracks": [dict(t) for t in self.tracks], "delivery": self.delivery, "consent_scope": dict(self.consent),
            "relation_generation": self.relation_generation, "state": self.state, "revision": self.revision,
            "generation": self.generation,
            "lease": {"lease_s": self.lease.lease_s, "keepalive_s": self.lease.keepalive_s,
                      "reconnect_s": session_lease.profile("media").get("reconnect_s"),
                      "remaining_s": round(self.lease.remaining(), 3)},
            "expires_at": self.expires_at, "ice_servers": list(self.ice_servers),
            "signaling": {k: v for k, v in self.signaling.items() if k != "token"},
            "pending_offer": self.pending_offer if self.local_role == "callee" and self.state != "ended" else None,
            "path": self.path, "quality": dict(self.quality), "quality_profile": dict(self.quality_profile),
            "content": _public_content(self),
            "needs_local_action": self.needs_local_action, "error": self.error,
            "peer": self.peer, "device": self.device, "device_alias": self.device_alias,
            "created_at": self.created_at, "ended_at": self.ended_at, "end_reason": self.end_reason,
            "remote_attached": self.remote_attached, "local_attached": self.local_attached,
        }


# ── 구독·통지 ────────────────────────────────────────────────────────────────────
def subscribe(fn: Callable) -> None:
    if fn not in _on_change:
        _on_change.append(fn)


def unsubscribe(fn: Callable) -> None:
    if fn in _on_change:
        _on_change.remove(fn)


def _changed(s: Session, event: str = "update") -> None:
    s.revision += 1
    snapshot = s.public()
    s.local_box.push({"type": "session", "event": event, "session": snapshot})
    for fn in list(_on_change):
        try:
            fn(event, snapshot)
        except Exception as exc:  # noqa: BLE001
            _log(f"[media] 구독자 실패({event}): {exc.__class__.__name__}")


def _set_state(s: Session, state: str, event: Optional[str] = None) -> None:
    if s.state != state:
        s.state = state
        _changed(s, event or state)


# ── 조회 ────────────────────────────────────────────────────────────────────────
def _get(sid: str) -> Session:
    s = _sessions.get(sid)
    if not s:
        raise MediaError("session_not_found", "세션이 없습니다. 다시 여세요.")
    return s


def get(sid: str) -> Session:
    with _lock:
        return _get(sid)


def status(sid: str) -> Dict:
    with _lock:
        return _get(sid).public()


def refresh_ice(sid: str) -> List[Dict]:
    with _lock:
        s = _get(sid)
        if s.state == "ended":
            raise MediaError("session_ended")
        if sig.turn_configured()[0]:
            s.ice_servers = sig.ice_servers(sid)
        return list(s.ice_servers)


def list_sessions(active_only: bool = True) -> List[Dict]:
    with _lock:
        rows = [s.public() for s in _sessions.values() if not active_only or s.state in ACTIVE_STATES]
    return sorted(rows, key=lambda r: r["created_at"], reverse=True)


def active_for_device(device_id: str) -> Optional[Session]:
    for s in _sessions.values():
        if s.device == device_id and s.state in ACTIVE_STATES:
            return s
    return None


# ── 트랙·동의 ───────────────────────────────────────────────────────────────────
def _tracks_for(purpose: str, kind: str, want_mic: bool = True) -> List[Dict]:
    if purpose == "voice_call":
        return [{"id": "a0", "kind": "audio", "source": "mic", "from": "caller", "to": "callee", "state": "requested"},
                {"id": "a1", "kind": "audio", "source": "mic", "from": "callee", "to": "caller", "state": "requested"}]
    if purpose == "video_call":
        return [{"id": "a0", "kind": "audio", "source": "mic", "from": "caller", "to": "callee", "state": "requested"},
                {"id": "v0", "kind": "video", "source": "camera", "from": "caller", "to": "callee", "state": "requested"},
                {"id": "a1", "kind": "audio", "source": "mic", "from": "callee", "to": "caller", "state": "requested"},
                {"id": "v1", "kind": "video", "source": "camera", "from": "callee", "to": "caller", "state": "requested"}]
    if purpose == "camera":
        rows = [{"id": "v0", "kind": "video", "source": "camera", "from": "device", "to": "hub", "state": "requested"}]
        if want_mic:
            rows.append({"id": "a0", "kind": "audio", "source": "mic", "from": "device", "to": "hub", "state": "requested"})
        return rows
    if purpose == "microphone":
        return [{"id": "a0", "kind": "audio", "source": "mic", "from": "device", "to": "hub", "state": "requested"}]
    if purpose == "speaker":
        return [{"id": "a0", "kind": "audio", "source": "playback", "from": "hub", "to": "device", "state": "requested"}]
    return []   # playback(content) — 트랙 없음


def _consent(tracks: List[Dict], local_role: str) -> Dict:
    inputs = sorted({t["source"] for t in tracks if t["from"] == local_role and t["source"] in ("mic", "camera", "screen")})
    outputs = sorted({"display" if t["kind"] == "video" else "speaker" for t in tracks if t["to"] == local_role})
    return {"inputs": inputs, "outputs": outputs, "record": False}


def _grant(sid: str, role: str, device: str, tracks: List[Dict], ttl_s: float) -> Dict:
    exp = round(_now() + ttl_s, 3)
    token = hmac.new(_hub_key(), f"{sid}|{role}|{device}|{exp}".encode(), hashlib.sha256).hexdigest()
    return {"session_id": sid, "role": role, "device": device, "tracks": [t["id"] for t in tracks],
            "expires_at": exp, "token": token}


def verify_grant(sid: str, role: str, device: str, grant) -> bool:
    if not isinstance(grant, dict):
        return False
    with _lock:
        s = _sessions.get(sid)
        if not s or s.state == "ended":
            return False
        issued = s.grants.get(role)
    if not issued or issued["device"] != device or grant.get("device") != device:
        return False
    if _now() > float(issued["expires_at"]):
        return False
    return hmac.compare_digest(str(grant.get("token") or ""), issued["token"])


def _same_fingerprint(a: str, b: str) -> bool:
    """DTLS 지문(sha-256 AB:CD…) 동일성 — 프로토콜 값(16진 대소문자 무관). 값 판정이 아니라 프로토콜 비교다."""
    norm = lambda x: "".join(str(x).split()).replace(":", "").upper()  # vj-ok: DTLS 지문은 16진 프로토콜 식별자(RFC 8122), 대소문자·구분자 무관
    return hmac.compare_digest(norm(a), norm(b))


def _fingerprint(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def _profile_for(capabilities: Dict, kind: str) -> str:
    if kind == "phone":
        caps = capabilities or {}
        media = caps.get("media_session") if isinstance(caps.get("media_session"), dict) else {}
        abi = str(caps.get("abi") or caps.get("arch") or media.get("abi") or "")   # 폰은 media_session 안에 abi 를 싣는다
        return "phone32" if "v7" in abi or abi in ("arm", "armeabi-v7a") else "phone64"
    return "helper"


# ── 생성 ────────────────────────────────────────────────────────────────────────
def create(kind: str, purpose: str, target: str, *, tracks: Optional[List[Dict]] = None, delivery: str = "realtime",
           request_id: Optional[str] = None, content: Optional[Dict] = None, want_mic: bool = False,
           camera: Optional[str] = None) -> Dict:
    """허가 근거를 호출자가 고르지 못한다 — kind 가 결정한다(call→accepted_call, extension→extension_grant)."""
    if kind not in ("call", "extension"):
        raise MediaError("invalid_kind", "kind 는 call 또는 extension")
    if purpose not in PURPOSES or (kind == "call") != (purpose in CALL_PURPOSES):
        raise MediaError("invalid_purpose", "목적이 종류와 맞지 않습니다")
    if delivery not in ("realtime", "content"):
        raise MediaError("invalid_delivery")
    if purpose == "playback" and delivery == "content" and not content:
        raise MediaError("content_unavailable", "content 에 path 또는 url 이 필요합니다")
    if purpose == "playback" and delivery == "realtime" and content:
        raise MediaError("invalid_delivery", "실시간 재생은 통화 창에서 재생 소스를 선택합니다")
    if purpose != "playback" and delivery == "content":
        raise MediaError("invalid_delivery", "실시간 목적에 content 전달은 쓸 수 없습니다")
    if not isinstance(target, str) or not target.strip():
        raise MediaError("target_required", "대상(장치 이름 또는 상대)을 지정하세요")
    if camera is not None and camera not in ("front", "back"):
        raise MediaError("invalid_request", "camera 는 front 또는 back")
    spec = {"kind": kind, "purpose": purpose, "target": target, "tracks": tracks, "delivery": delivery, "content": content,
            "camera": camera, "want_mic": want_mic}
    with _lock:
        if request_id:
            prev = _requests.get(request_id)
            if prev:
                fp, sid = prev
                if fp != _fingerprint(spec):
                    raise MediaError("request_id_conflict", "같은 request_id 에 다른 내용")
                if sid in _sessions:
                    return _sessions[sid].public()
        live = [s for s in _sessions.values() if s.state in ACTIVE_STATES]
        if len(live) >= int(sig.limits().get("max_active_sessions") or 8):
            raise MediaError("busy", "열린 미디어 세션이 너무 많습니다")
    s = _create_extension(purpose, target, tracks, delivery, content, want_mic) if kind == "extension" \
        else _create_call(purpose, target)
    s.request_id = request_id
    s.camera = camera
    with _lock:
        _sessions[s.id] = s
        if request_id:
            _requests[request_id] = (_fingerprint(spec), s.id)
    media_store.record_start(s.public())
    _ensure_sweeper()
    try:
        _launch(s)
    except MediaError as exc:
        end(s.id, exc.code, error={"code": exc.code, "message": exc.message})
        raise
    _changed(s, "created")
    return status(s.id)


def _create_extension(purpose, target, tracks, delivery, content, want_mic) -> Session:
    import resident_pcs
    try:
        rec = resident_pcs.resolve(target, active=False)
    except ValueError as exc:
        raise MediaError("device_not_found", str(exc)) from exc
    reg = rec["registration"]
    if rec.get("revoked") or reg["state"] != "active" or reg.get("paused"):
        raise MediaError("relation_revoked", "확장관계가 중지·해제·폐기됐습니다")
    if _now() - (reg.get("last_seen") or 0) > 90:
        raise MediaError("device_offline", "장치가 오프라인입니다")
    caps = reg.get("capabilities") or {}
    media_caps = caps.get("media_session") or {}
    if not isinstance(media_caps, dict) or not media_caps:
        raise MediaError("unsupported_track", "이 장치는 미디어 세션을 지원하지 않습니다(설치본·헬퍼 교체 필요)")
    need = {"camera": "camera", "microphone": "microphone", "speaker": "speaker", "playback": "playback"}[purpose]
    if not media_caps.get(need):
        raise MediaError("unsupported_track", f"이 장치는 {need} 를 지원하지 않습니다")
    if purpose == "camera" and want_mic and not media_caps.get("microphone"):
        want_mic = False
    with _lock:
        if active_for_device(rec["device_id"]):
            raise MediaError("device_busy", "이 장치에 열린 미디어 세션을 먼저 닫으세요")
    rows = tracks or _tracks_for(purpose, "extension", want_mic)
    if purpose == "playback" and delivery == "realtime":
        if not media_caps.get("video_receive"):
            raise MediaError("unsupported_track", "이 장치는 실시간 영상 수신을 지원하지 않습니다")
        rows = tracks or [
            {"id": "v0", "kind": "video", "source": "playback", "from": "hub", "to": "device", "state": "requested"},
            {"id": "a0", "kind": "audio", "source": "playback", "from": "hub", "to": "device", "state": "requested"},
        ]
        if not any(t.get("kind") == "video" for t in rows) or any(
                t.get("from") != "hub" or t.get("to") != "device" or t.get("source") != "playback" for t in rows):
            raise MediaError("unsupported_track", "실시간 재생은 중앙에서 장치로 보내는 재생 영상·소리입니다")
    for t in rows:
        if t.get("kind") not in ("audio", "video") or t.get("from") not in ("hub", "device") or t.get("to") not in ("hub", "device"):
            raise MediaError("unsupported_track")
    if content is not None:
        if not isinstance(content, dict) or not (content.get("path") or content.get("url")):
            raise MediaError("content_unavailable", "content 에 path 또는 url 이 필요합니다")
    sid = secrets.token_hex(16)
    s = Session(id=sid, kind="extension", purpose=purpose, basis="extension_grant", local_role="hub", tracks=rows,
                delivery=delivery, device=rec["device_id"], device_alias=rec["alias"],
                relation_generation=reg["generation"], state="authorized", secret=secrets.token_hex(32))
    s.participants = [{"role": "hub", "user": {"id": "self", "name": "중앙"}, "device": {"id": "local", "name": "중앙 PC", "body": "pc"}},
                      {"role": "device", "user": {"id": "self", "name": "중앙"},
                       "device": {"id": rec["device_id"], "name": rec["alias"], "body": reg.get("kind") or "pc"}}]
    s.consent = _consent(rows, "hub")
    s.quality_profile = sig.quality_profile(_profile_for(caps, reg.get("kind") or "pc"))
    s.ice_servers = sig.ice_servers(sid)
    s.signaling = {"route": "extension", "relay": None}
    s.grants["device"] = _grant(sid, "device", rec["device_id"], rows, 86400)
    if content is not None:
        s.content = _content_ref(s, content)
    return s


def _local_device(device_id="local"):
    from runtime_utils import detect_body
    phone = detect_body().get("profile") == "phone"
    return {"id": device_id, "name": "이 폰" if phone else "이 PC", "body": "phone" if phone else "pc"}


def _local_quality_profile():
    from runtime_utils import detect_body
    if detect_body().get("profile") == "phone":
        import struct
        return sig.quality_profile("phone64" if struct.calcsize("P") == 8 else "phone32")
    return sig.quality_profile("default")


def _create_call(purpose, target) -> Session:
    ok, why = nostr.available()
    if not ok:
        raise MediaError("signaling_unavailable", "통화 신원(IndieNet)이 준비되지 않았습니다: " + why)
    peer = resolve_contact(target)
    if media_store.is_blocked(peer):
        raise MediaError("rejected", "차단한 상대입니다")
    rows = _tracks_for(purpose, "call")
    sid = secrets.token_hex(16)
    s = Session(id=sid, kind="call", purpose=purpose, basis="accepted_call", local_role="caller", tracks=rows,
                peer=peer, state="inviting", secret=secrets.token_hex(32))
    s.participants = [{"role": "caller", "user": {"id": nostr.my_pubkey_hex(), "name": "나"}, "device": _local_device()},
                      {"role": "callee", "user": {"id": peer, "name": _contact_name(peer)}, "device": {"id": "?", "name": "", "body": ""}}]
    s.consent = _consent(rows, "caller")
    s.quality_profile = _local_quality_profile()
    s.ice_servers = sig.ice_servers(sid)
    s.expires_at = round(_now() + float(session_lease.profile("media").get("invite_s") or 45), 3)
    route = str((sig.policy().get("signaling") or {}).get("route") or "auto")
    relay = sig.relay_url(sid) if route in ("auto", "relay") else ""
    if route == "relay" and not relay:
        raise MediaError("signaling_unavailable", "relay 경로가 설정됐지만 공개 주소가 없습니다")
    s.signaling = {"route": "relay" if relay else "nostr", "relay": relay or None}
    if relay:
        s.signaling["token"] = rooms.open(sid, s.secret, on_frame=lambda f: receive_remote(f, source="relay"))
    return s


def resolve_contact(target: str) -> str:
    """이름·npub·hex → pubkey hex. 주소록(business.db nostr 연락처)만 신뢰한다."""
    t = (target or "").strip()
    if t.startswith("npub1"):
        try:
            from bech32 import bech32_decode, convertbits
        except ImportError:
            from pynostr.bech32 import bech32_decode, convertbits
        parts = bech32_decode(t)
        hrp, data = parts[:2]
        if len(parts) == 3 and getattr(parts[2], "name", "") != "BECH32":
            data = None
        decoded = convertbits(data, 5, 8, False) if data is not None and hrp == "npub" else None
        if decoded is None or len(decoded) != 32:
            raise MediaError("invalid_target", "올바른 npub 주소가 아닙니다")
        return bytes(decoded).hex()
    if len(t) == 64 and all(c in "0123456789abcdef" for c in t.lower()):
        return t.lower()
    try:
        from business_manager import BusinessManager
        bm = BusinessManager()
        hits = []
        for n in bm.get_neighbors(search=t) or []:
            if str(n.get("name") or "").strip() != t:
                continue
            for c in bm.get_contacts(n["id"]) or []:
                if c.get("contact_type") == "nostr" and c.get("contact_value"):
                    v = str(c["contact_value"]).strip()
                    hits.append(resolve_contact(v) if v.startswith("npub1") else v.lower())
        hits = sorted(set(hits))
        if len(hits) == 1:
            return hits[0]
        if len(hits) > 1:
            raise MediaError("ambiguous_target", f"'{t}' 에 nostr 주소가 {len(hits)}개입니다. npub 으로 지정하세요")
    except MediaError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise MediaError("target_not_found", f"주소록 조회 실패: {exc.__class__.__name__}") from exc
    raise MediaError("target_not_found", f"'{t}' 의 nostr 주소를 주소록에서 찾지 못했습니다")


def _contact_name(pubkey_hex: str) -> str:
    try:
        import nip17
        from business_manager import BusinessManager
        n = BusinessManager().get_neighbor_by_contact("nostr", nip17.hex_to_npub(pubkey_hex))
        return str(n.get("name")) if n else pubkey_hex[:12] + "…"
    except Exception:  # noqa: BLE001
        return pubkey_hex[:12] + "…"


def _content_ref(s: Session, content: Dict) -> Dict:
    ref = secrets.token_hex(16)
    out = {"ref": ref, "position_s": float(content.get("position_s") or 0), "paused": False,
           "volume": content.get("volume") if content.get("volume") is not None else 80,
           "volume_explicit": content.get("volume") is not None}
    if content.get("path"):
        p = os.path.expanduser(str(content["path"]))
        if not os.path.isfile(p):
            raise MediaError("content_unavailable", "파일이 없습니다")
        if os.path.getsize(p) > int(sig.limits().get("content_max_bytes") or 4 * 1024 ** 3):
            raise MediaError("content_unavailable", "파일이 너무 큽니다")
        out.update(kind="file", name=os.path.basename(p), size=os.path.getsize(p))
        s.content_state["_path"] = p
        token = hmac.new(_hub_key(), f"content|{s.id}|{ref}".encode(), hashlib.sha256).hexdigest()[:32]
        base = sig.relay_base()
        out["url"] = (base or "") + f"/media/content/{ref}?token={token}"
        s.content_state["_token"] = token
    else:
        url = str(content["url"]).strip()
        if not url.startswith(("http://", "https://")):
            raise MediaError("content_unavailable", "http(s) 주소만 전달합니다")
        from urllib.parse import urlsplit, urlunsplit
        parsed = urlsplit(url)
        if parsed.hostname in ("localhost", "127.0.0.1", "::1"):
            base = urlsplit(sig.relay_base())
            if not base.netloc:
                raise MediaError("content_unavailable", "로컬 재생 주소를 전달할 공개 주소가 없습니다. 파일 경로로 보내 주세요")
            url = urlunsplit((base.scheme, base.netloc, parsed.path, parsed.query, ""))
        out.update(kind="url", url=url)
    return out


def content_file(ref: str, token: str):
    """콘텐츠 참조 → (파일 경로, 이름). 토큰·세션 유효성 확인. 종료된 세션은 무효."""
    with _lock:
        for s in _sessions.values():
            if s.content and s.content.get("ref") == ref:
                if s.state == "ended":
                    raise MediaError("session_ended")
                grant_token = str((s.grants.get("device") or {}).get("token") or "")
                given = str(token or "")
                if not (hmac.compare_digest(given, str(s.content_state.get("_token") or "x"))
                        or (grant_token and hmac.compare_digest(given, grant_token))):
                    raise MediaError("permission_required")
                return s.content_state.get("_path"), s.content.get("name")
    raise MediaError("content_unavailable")


# ── 시작(허가 뒤 엔진 호출) ───────────────────────────────────────────────────────
def _device_envelope(s: Session) -> Dict:
    import resident_pcs
    import resident_terminal_lan as lan
    stream = {"url": "", "lan": {}}
    base = sig.relay_base()
    if base:
        stream["url"] = base.replace("https://", "wss://", 1).replace("http://", "ws://", 1) + f"/limb/resident/media/{s.id}"
    try:
        # 장치 WS 핸들러는 표면(api_media)이 등록한다 — 서비스가 표면을 import 하지 않는다(층 규율, 의존 역전)
        stream["lan"] = lan.offer(device_socket_handler, channel="media") if device_socket_handler else {}
    except Exception:  # noqa: BLE001
        stream["lan"] = {}
    body = {"session_id": s.id, "grant": s.grants["device"], "purpose": s.purpose, "tracks": s.tracks,
            "ice_servers": s.ice_servers, "lease": {"lease_s": s.lease.lease_s, "keepalive_s": s.lease.keepalive_s,
                                                   "reconnect_s": session_lease.profile("media").get("reconnect_s")},
            "quality_profile": s.quality_profile, "stream": stream, "content": _public_content(s), "delivery": s.delivery,
            "camera": s.camera, "timeout": 86400}
    rec = resident_pcs.resolve(s.device, active=False)
    if (rec["registration"].get("adapter") or "resident-v1") == "indiebiz-v1":
        return {"op": "media", "action": "start", "session": body, "timeout": 30}
    return {"op": "media_session", **body}


def _public_content(s: Session) -> Optional[Dict]:
    """세션 밖으로 나가는 콘텐츠 모양 — 파일 전체 경로·토큰 원문(_path·_token)은 절대 싣지 않는다.
    url 이 '/' 로 시작하면 허브 공개 주소가 없는 것이고, 장치는 자기 허브 base 에 붙여 쓴다(계약 §7)."""
    if not s.content:
        return None
    return {k: v for k, v in {**s.content, **s.content_state}.items() if not k.startswith("_")}


def _launch(s: Session) -> None:
    if s.kind == "extension":
        import resident_pcs
        try:
            receipt = resident_pcs.submit(s.device, _device_envelope(s), "media-" + s.id, allow_media=True)
        except ValueError as exc:
            code = str(exc)
            raise MediaError("device_offline" if "registration" in code else "device_busy", code) from exc
        s.device_job = receipt.get("job_id")
        _set_state(s, "connecting", "launched")
        return
    # call: 초대는 브라우저 offer 를 잠깐(bundle_wait_s) 기다려 동봉한다 — DM 한 번을 아낀다.
    threading.Thread(target=_send_invite, args=(s,), name="media-invite", daemon=True).start()


def _send_invite(s: Session) -> None:
    wait = float((sig.policy().get("signaling") or {}).get("bundle_wait_s") or 0)
    if wait > 0:
        s.bundle_event.wait(wait)
    def done(ok, err):
        if not ok:
            end(s.id, "signaling_unavailable", error={"code": "signaling_unavailable", "message": err or "초대 전송 실패"})

    with _lock:
        if s.state != "inviting":
            return
        offer = s.pending_offer
        payload = {"purpose": s.purpose, "tracks": s.tracks, "from_user": s.participants[0]["user"],
                   "from_device": s.participants[0]["device"], "secret": s.secret, "ice_servers": s.ice_servers,
                   "signaling": {"route": s.signaling.get("route"), "relay": s.signaling.get("relay"),
                                 "token": s.signaling.get("token")},
                   "expires_at": s.expires_at, "quality_profile": s.quality_profile}
        if offer:
            payload["offer"] = offer
            s.pending_offer = None
        frame = sig.sign(sig.new_frame(s.id, "caller", "callee", "invite", payload, generation=s.generation,
                                       ttl_s=max(5.0, s.expires_at - _now())), s.secret)
        peer = s.peer

        # Queue the invitation before any late offer/ICE. NostrTransport preserves send order.
        if s.state == "ended":
            return
        nostr.send(peer, frame, done=done)
        s.invite_sent = True
        for queued in s.early_signals:
            _deliver_remote(s, queued)
        s.early_signals.clear()


# ── 수신 측(초대 받음) ──────────────────────────────────────────────────────────────
def receive_invite(frame: Dict, sender_hex: str) -> Optional[Dict]:
    """Nostr 로 받은 invite → 로컬 세션(callee, ringing). 신선도·차단·중복을 여기서 거른다."""
    payload = frame.get("payload") or {}
    sid = frame.get("session_id")
    secret = str(payload.get("secret") or "")
    if len(secret) != 64 or not sig.verify(frame, secret):
        return None
    fresh = float((sig.policy().get("signaling") or {}).get("freshness_s") or 90)
    exp = float(payload.get("expires_at") or 0)
    if sig.expired(frame) or (exp and _now() > exp + fresh):
        return None
    if media_store.is_blocked(sender_hex):
        return None
    purpose = payload.get("purpose")
    if purpose not in CALL_PURPOSES:
        return None
    with _lock:
        if sid in _sessions:
            return _sessions[sid].public()
        rows = [dict(t) for t in (payload.get("tracks") or _tracks_for(purpose, "call")) if isinstance(t, dict)]
        s = Session(id=sid, kind="call", purpose=purpose, basis="accepted_call", local_role="callee", tracks=rows,
                    peer=sender_hex, state="ringing", secret=secret)
        s.participants = [{"role": "caller", "user": {**(payload.get("from_user") or {}), "id": sender_hex,
                                                      "name": _contact_name(sender_hex)},
                           "device": payload.get("from_device") or {}},
                          {"role": "callee", "user": {"id": nostr.my_pubkey_hex(), "name": "나"},
                           "device": _local_device()}]
        s.consent = _consent(rows, "callee")
        s.quality_profile = _local_quality_profile()
        local_ice = sig.ice_servers(sid)
        s.ice_servers = local_ice if sig.turn_configured()[0] else list(payload.get("ice_servers") or local_ice)
        s.expires_at = exp or round(_now() + 45, 3)
        signaling = payload.get("signaling") or {}
        s.signaling = {"route": "relay" if signaling.get("relay") else "nostr", "relay": signaling.get("relay"),
                       "token": signaling.get("token")}
        offer = payload.get("offer")
        if isinstance(offer, dict) and isinstance(offer.get("sdp"), str) and offer["sdp"]:
            fp = sig.fingerprint_of(offer["sdp"])
            if offer.get("fingerprint") and fp and not _same_fingerprint(str(offer["fingerprint"]), fp):
                return None   # 지문이 SDP 와 다른 초대는 받지 않는다
            s.pending_offer = {"sdp": offer["sdp"], "fingerprint": fp or str(offer.get("fingerprint") or "")}
            s.buffers.setdefault("remote", sig.CandidateBuffer()).mark_described(int(frame.get("generation", 0)))
        s.orders["remote"] = sig.Order()
        s.orders["remote"].admit(frame)
        _sessions[sid] = s
    media_store.record_start(s.public())
    _ensure_sweeper()
    _changed(s, "ringing")
    _ring(s)
    return s.public()


def _ring(s: Session) -> None:
    """벨 = 실제 표시. 런처 알림(클릭=통화 창) + OS 알림 폴백. 시험 프로세스에선 notify_dispatch 가 막는다."""
    try:
        from notify_dispatch import deliver_notification
        caller = s.participants[0]["user"].get("name") or "상대"
        kind = "영상 통화" if s.purpose == "video_call" else "음성 통화"
        deliver_notification(f"{kind} 수신", f"{caller} 님이 {kind}를 걸었습니다", kind="media_call",
                command="open_call_window", command_params={"session_id": s.id})
    except Exception as exc:  # noqa: BLE001
        _log(f"[media] 벨 알림 실패: {exc.__class__.__name__}")


def accept(sid: str, device: str = "local") -> Dict:
    with _lock:
        s = _get(sid)
        if s.state == "ended":
            raise MediaError("session_ended", s.end_reason)
        if s.kind != "call" or s.local_role != "callee":
            raise MediaError("invalid_state", "수락할 초대가 아닙니다")
        if s.state != "ringing":
            raise MediaError("invalid_state", "이미 처리된 초대입니다")   # 첫 수락만 이긴다
        if s.expires_at and _now() > s.expires_at:
            end_locked(s, "invite_expired")
            raise MediaError("invite_expired", "초대가 만료됐습니다")
        s.participants[1]["device"] = _local_device(device)
        s.expires_at = None
        s.lease = session_lease.Lease("media")
        s.lease.generation = s.generation
        _set_state(s, "accepted")
        if s.signaling.get("relay") and s.signaling.get("token"):
            s.relay_client = sig.RelayClient(s.signaling["relay"], s.signaling["token"],
                                             on_frame=lambda f: receive_remote(f, source="relay"), log=_log)
            s.relay_client.start()
    threading.Thread(target=_send_accept, args=(s,), name="media-accept", daemon=True).start()
    return status(sid)


def _send_accept(s: Session) -> None:
    wait = float((sig.policy().get("signaling") or {}).get("bundle_wait_s") or 0)
    if wait > 0:
        s.bundle_event.wait(wait)
    def done(ok, err):
        if not ok:
            end(s.id, "signaling_unavailable", error={"code": "signaling_unavailable", "message": err or "수락 전송 실패"})

    with _lock:
        if s.state == "ended":
            return
        payload = {"device": s.participants[1]["device"]}
        if s.pending_answer:
            payload["answer"] = s.pending_answer
            s.pending_answer = None
        frame = sig.sign(sig.new_frame(s.id, "callee", "caller", "accept", payload, generation=s.generation), s.secret)
        peer = s.peer
        _set_state(s, "connecting")

        nostr.send(peer, frame, done=done)
        s.accept_sent = True
        for queued in s.early_signals:
            _deliver_remote(s, queued)
        s.early_signals.clear()


def reject(sid: str, reason: str = "rejected", *, block: bool = False) -> Dict:
    with _lock:
        s = _get(sid)
        if s.state == "ended":
            return s.public()
        peer, secret, local_role = s.peer, s.secret, s.local_role
        to = "caller" if local_role == "callee" else "callee"
        frame = sig.sign(sig.new_frame(sid, local_role, to, "reject", {"reason": reason}, generation=s.generation), secret)
        if block and peer:
            media_store.block(peer, "통화 화면에서 차단")
        end_locked(s, reason, notify_remote=False)   # 통지는 아래 reject 프레임 하나로
    if s.kind == "call" and peer:
        nostr.send(peer, frame)
    elif s.kind == "extension":
        _deliver_remote(s, frame)
    return status(sid)


# ── 원격 프레임 수신(장치 WS·Nostr·릴레이) ──────────────────────────────────────────
def receive_remote(frame: Dict, *, source: str, sender_hex: Optional[str] = None,
                   device_session: Optional[str] = None, device_id: Optional[str] = None) -> Optional[str]:
    """장치·상대 허브에서 온 프레임. 질서·서명·세션 상태를 확인하고 로컬 엔진으로 넘긴다. 반환=거절 사유."""
    try:
        frame = sig.validate_frame(frame)
    except ValueError as exc:
        return str(exc)
    sid, kind = frame["session_id"], frame["type"]
    if kind == "invite":
        if source != "nostr" or not sender_hex:
            return "invite_only_via_nostr"
        receive_invite(frame, sender_hex)
        return None
    with _lock:
        s = _sessions.get(sid)
        if not s:
            return "session_not_found"
        if source == "device":
            if device_session != sid or s.kind != "extension" or device_id != s.device:
                return "wrong_session"
            if not _relation_still_valid(s):
                end_locked(s, "relation_revoked")
                return "relation_revoked"
        elif source not in ("nostr", "relay"):
            return "invalid_source"
        if frame["from"] != _remote_role(s) or frame["to"] != s.local_role:
            return "wrong_role"
        if source in ("nostr", "relay"):
            if not sig.verify(frame, s.secret):
                return "bad_signature"
            if source == "nostr" and sender_hex and s.peer and sender_hex != s.peer:
                return "wrong_sender"
        if sig.expired(frame):
            return "expired"
        order = s.orders.setdefault("remote", sig.Order())
        ok, why = order.admit(frame)
        if not ok:
            return why
        if s.state == "ended":
            if kind != "end":
                # 늦은 프레임에는 '종료됨'으로 답한다(재활성화 금지)
                _reply_end(s)
            return "session_ended"
        return _apply_remote_locked(s, frame)


def _reply_end(s: Session) -> None:
    frame = sig.sign(sig.new_frame(s.id, s.local_role, _remote_role(s), "end", {"reason": s.end_reason or "ended"},
                                   generation=s.generation), s.secret)
    _deliver_remote(s, frame)


def _remote_role(s: Session) -> str:
    return {"caller": "callee", "callee": "caller", "hub": "device"}[s.local_role]


def _apply_remote_locked(s: Session, frame: Dict) -> Optional[str]:
    kind, payload = frame["type"], frame.get("payload") or {}
    if kind == "accept":
        if s.local_role != "caller" or s.state != "inviting":
            return "invalid_state"
        s.participants[1]["device"] = payload.get("device") or {}
        s.expires_at = None
        s.lease = session_lease.Lease("media")
        s.lease.generation = s.generation
        _set_state(s, "connecting", "accepted")
        if isinstance(payload.get("answer"), dict):
            inner = sig.new_frame(s.id, "callee", "caller", "answer", payload["answer"], generation=frame["generation"])
            s.local_box.push(inner)
            s.buffers.setdefault("remote", sig.CandidateBuffer()).mark_described(int(frame["generation"]))
        return None
    if kind == "reject":
        end_locked(s, payload.get("reason") or "rejected", notify_remote=False)
        return None
    if kind == "end":
        end_locked(s, payload.get("reason") or "ended", notify_remote=False)
        return None
    if kind == "keepalive":
        if not s.lease.renew(frame["generation"], frame["seq"] or None):
            return "stale_keepalive"
        if s.kind == "extension" and not _relation_still_valid(s):
            end_locked(s, "relation_revoked", error={"code": "relation_revoked", "message": "확장관계가 유효하지 않습니다"})
            return "relation_revoked"
        return None
    if kind == "state":
        # A peer's report is never local consent. In particular it cannot turn ringing into active.
        if s.kind == "extension":
            _apply_state_report(s, payload)
        return None
    if kind in ("offer", "answer"):
        sdp = payload.get("sdp")
        if not isinstance(sdp, str) or not sdp:
            return "invalid_sdp"
        fp = sig.fingerprint_of(sdp)
        if payload.get("fingerprint") and fp and not _same_fingerprint(payload["fingerprint"], fp):
            return "fingerprint_mismatch"
        if frame["generation"] > s.generation:
            s.generation = frame["generation"]
            s.lease.advance_generation()
            s.lease.generation = s.generation
        if isinstance(payload.get("ice_servers"), list):
            s.ice_servers = list(payload["ice_servers"])
        if kind == "offer" and s.local_role == "callee":
            s.pending_offer = dict(payload)
            _changed(s, "offer")
    # offer/answer/candidate/candidates_done/renegotiate/update → 로컬 엔진으로(선도착 candidate 는 버퍼)
    buf = s.buffers.setdefault("remote", sig.CandidateBuffer())
    for f in buf.observe(frame):
        s.local_box.push(f)
    return None


def _relation_still_valid(s: Session) -> bool:
    try:
        import limb_keys
        rec = limb_keys.get_by_device(s.device)
        reg = (rec or {}).get("registration") or {}
        return bool(rec) and not rec.get("revoked") and reg.get("state") == "active" and not reg.get("paused") \
            and reg.get("generation") == s.relation_generation
    except Exception:  # noqa: BLE001
        return False


def _apply_state_report(s: Session, payload: Dict) -> None:
    revision = s.revision
    state = payload.get("state")
    if isinstance(payload.get("quality"), dict):
        s.quality = {k: payload["quality"].get(k) for k in ("rtt_ms", "loss", "jitter_ms", "bitrate_kbps", "fps", "width", "height", "dropped")}
    if payload.get("path") in ("direct", "relay"):
        s.path = payload["path"]
    _CONTENT_KEYS = ("playing", "position_s", "paused", "volume", "duration_s", "ended", "control", "has_video", "video_visible", "needs_display", "width", "height", "requested_volume", "player_gain")
    if isinstance(payload.get("content"), dict):
        s.content_state.update({k: v for k, v in payload["content"].items() if k in _CONTENT_KEYS})
    if s.content and any(k in payload for k in _CONTENT_KEYS):   # 장치가 최상위에 실어 보내는 모양도 받는다
        s.content_state.update({k: payload[k] for k in _CONTENT_KEYS if k in payload})
    if state == "needs_local_action":
        action = payload.get("needs_local_action")
        action = action if isinstance(action, dict) else payload
        s.needs_local_action = {"code": action.get("code") or "needs_local_action", "message": action.get("message") or "장치에서 필요한 행동을 해 주세요"}
        _set_state(s, "needs_local_action")
    elif state == "active":
        s.disconnected_at = None
        s.needs_local_action = None
        if s.state != "active":
            media_store.record_connected(s.id, s.path)
        _set_state(s, "active")
    elif state == "reconnecting":
        s.disconnected_at = s.disconnected_at or _now()
        _set_state(s, "reconnecting")
    elif state == "ended":
        end_locked(s, payload.get("reason") or "remote_ended", notify_remote=False)
        return
    else:
        _changed(s, "state")
    if s.revision == revision:
        _changed(s, "state")
    if s.quality:
        media_store.record_quality(s.id, s.quality, s.path)


# ── 로컬 엔진(브라우저) 프레임 ────────────────────────────────────────────────────────
def signal(sid: str, frame: Dict) -> Optional[str]:
    """브라우저 엔진이 보낸 프레임. 세션 비밀로 서명해 상대/장치로 전달한다. 반환=거절 사유."""
    try:
        frame = sig.validate_frame(frame)
    except ValueError as exc:
        return str(exc)
    with _lock:
        s = _sessions.get(sid)
        if not s or frame["session_id"] != sid:
            return "session_not_found"
        if s.state == "ended":
            return "session_ended"
        kind, payload = frame["type"], frame.get("payload") or {}
        frame["from"], frame["to"] = s.local_role, _remote_role(s)
        if kind == "end":
            end_locked(s, payload.get("reason") or "local_ended")
            return None
        if kind == "keepalive":
            # 통화: 브라우저가 DTLS 로 인증된 DataChannel 로 상대의 생존을 확인했을 때만(peer_alive) 임대를 갱신한다
            # (설계 §4 "인증된 참가자의 생존 확인"). 확장: 장치의 keepalive 가 갱신하고, 로컬 확인은 연결 자체가 증명.
            if s.kind == "call" and payload.get("peer_alive") is True and s.state in ("active", "reconnecting"):
                s.lease.renew()
            return None
        if kind == "state":
            # For a remote display, only its rendered output can acknowledge success.
            if not (s.kind == "extension" and any(t.get("to") == "device" and t.get("kind") == "video" for t in s.tracks)):
                _apply_state_report(s, payload)
            return None
        if kind in ("offer", "answer"):
            sdp = payload.get("sdp")
            if not isinstance(sdp, str) or not sdp:
                return "invalid_sdp"
            fp = sig.fingerprint_of(sdp)
            if fp:
                payload["fingerprint"] = fp
            if frame["generation"] > s.generation:
                s.generation = frame["generation"]
                s.lease.advance_generation()
                s.lease.generation = s.generation
            payload["ice_servers"] = refresh_ice(sid)
            # 통화: 초대/수락에 동봉할 수 있으면 보관하고 신호는 보내지 않는다
            if s.kind == "call" and kind == "offer" and s.local_role == "caller" and s.state == "inviting" and not s.invite_sent:
                s.pending_offer = dict(payload)
                s.bundle_event.set()
                return None
            if s.kind == "call" and kind == "answer" and s.local_role == "callee" and s.state in ("accepted",):
                s.pending_answer = dict(payload)
                s.bundle_event.set()
                return None
        if kind == "update" and s.content:
            s.content_state.update({k: v for k, v in payload.items() if k in ("paused", "position_s", "volume")})
        _deliver_remote(s, sig.sign(frame, s.secret))
        return None


def _deliver_remote(s: Session, frame: Dict) -> None:
    """상대/장치로. 확장=장치 WS Outbox, 통화=릴레이(있고 붙었으면) 아니면 Nostr DM."""
    # Engine signals and hub keepalive/control share one outgoing sequence.
    # Separate counters cause helpers to discard liveness after the first offer/candidates.
    s.out_seq += 1
    frame = sig.sign({**frame, "seq": s.out_seq}, s.secret)
    if s.kind == "extension":
        s.remote_box.push(frame)
        return
    if (s.local_role == "caller" and not s.invite_sent) or (s.local_role == "callee" and not s.accept_sent and frame["type"] not in ("end", "reject")):
        s.early_signals.append(frame)
        return
    route = s.signaling.get("route")
    if route == "relay":
        if s.local_role == "caller":
            if rooms.publish(s.id, "host", frame) > 0:
                return
        elif s.relay_client and s.relay_client.send(frame):
            return
    if s.peer:
        nostr.send(s.peer, frame)


# ── 장치 WS 붙이기/떼기 ─────────────────────────────────────────────────────────────
def device_ready(sid: str, capabilities) -> None:
    """장치가 붙은 뒤 보내는 `{"type":"ready","capabilities"}` — 세션에 기록만 한다(시그널 프레임 아님)."""
    with _lock:
        s = _sessions.get(sid)
        if s and isinstance(capabilities, dict):
            s.device_caps = {k: v for k, v in capabilities.items() if not isinstance(v, (bytes, bytearray))}
            _changed(s, "device_ready")


def attach_device(sid: str, device_id: str, grant) -> Session:
    if not verify_grant(sid, "device", device_id, grant):
        raise MediaError("permission_required", "세션 참가 자격이 맞지 않습니다")
    with _lock:
        s = _get(sid)
        if s.remote_attached:
            raise MediaError("device_busy", "이미 붙은 장치가 있습니다")
        s.remote_attached = True
        s.remote_box.attached = True
        s.lease.renew()
        _changed(s, "device_attached")
        return s


def detach_device(sid: str, reason: str = "device_disconnected") -> None:
    with _lock:
        s = _sessions.get(sid)
        if not s or not s.remote_attached:
            return
        s.remote_attached = False
        s.remote_box.attached = False
        if s.state in ("connecting", "active", "reconnecting", "needs_local_action"):
            s.disconnected_at = _now()
            _set_state(s, "reconnecting", reason)


def attach_local(sid: str) -> Session:
    with _lock:
        s = _get(sid)
        if s.state == "ended":
            raise MediaError("session_ended", s.end_reason)
        s.local_attached = True
        s.local_box.attached = True
        _changed(s, "local_attached")
        return s


def detach_local(sid: str) -> None:
    with _lock:
        s = _sessions.get(sid)
        if s:
            s.local_attached = False
            s.local_box.attached = False


# ── 갱신·종료 ───────────────────────────────────────────────────────────────────────
def update(sid: str, expected_revision: int, changes: Dict) -> Dict:
    with _lock:
        s = _get(sid)
        if s.state == "ended":
            raise MediaError("session_ended", s.end_reason)
        if not isinstance(expected_revision, int) or expected_revision != s.revision:
            raise MediaError("stale_revision", f"현재 판본은 {s.revision}")
        if not isinstance(changes, dict):
            raise MediaError("invalid_changes")
        payload = {}
        if "audio_source" in changes:
            source = changes["audio_source"]
            if (s.kind != "extension" or s.purpose != "speaker" or s.local_role != "hub"
                    or source not in ("mic", "playback")):
                raise MediaError("invalid_changes", "audio_source 는 스피커 전송의 mic 또는 playback")
            for track in s.tracks:
                if track["from"] == "hub" and track["to"] == "device" and track["kind"] == "audio":
                    track["source"] = source
            s.consent = _consent(s.tracks, s.local_role)
            payload["audio_source"] = source
        for key in ("mute", "camera"):
            if key in changes:
                if not isinstance(changes[key], bool):
                    raise MediaError("invalid_changes", key + " 는 bool")
                payload[key] = changes[key]
                for t in s.tracks:
                    if t["from"] == s.local_role and ((key == "mute" and t["kind"] == "audio") or (key == "camera" and t["kind"] == "video")):
                        t["state"] = ("muted" if changes[key] else "active") if key == "mute" else ("active" if changes[key] else "muted")
        if isinstance(changes.get("content"), dict):
            c = {k: v for k, v in changes["content"].items() if k in ("paused", "position_s", "volume")}
            if "volume" in c and (isinstance(c["volume"], bool) or not isinstance(c["volume"], (int, float)) or not 0 <= c["volume"] <= 100):
                raise MediaError("invalid_changes", "volume 은 0..100")
            s.content_state.update(c)
            payload["content"] = c
        frame = sig.sign(sig.new_frame(sid, s.local_role, _remote_role(s), "update", payload, generation=s.generation), s.secret)
        _deliver_remote(s, frame)
        s.local_box.push(frame)
        _changed(s, "updated")
        return s.public()


def end(sid: str, reason: str = "ended", *, error: Optional[Dict] = None) -> Dict:
    """멱등 — 두 번째 호출도 성공(현재 투영)."""
    with _lock:
        s = _sessions.get(sid)
        if not s:
            return {"session_id": sid, "state": "ended", "end_reason": "unknown"}
        end_locked(s, reason, error=error)
        return s.public()


def end_locked(s: Session, reason: str, *, error: Optional[Dict] = None, notify_remote: bool = True) -> None:
    if not s.lease.close(reason):
        return
    s.state, s.end_reason, s.ended_at = "ended", reason, _now()
    if error:
        s.error = error
    if notify_remote and s.state is not None:
        try:
            frame = sig.sign(sig.new_frame(s.id, s.local_role, _remote_role(s), "end", {"reason": reason},
                                           generation=s.generation), s.secret)
            _deliver_remote(s, frame)
        except Exception as exc:  # noqa: BLE001
            _log(f"[media] 종료 통지 실패: {exc.__class__.__name__}")
    if s.kind == "extension" and s.device_job:
        try:
            import resident_store
            resident_store.cancel(s.device_job, s.device)
        except Exception:  # noqa: BLE001
            pass
    if s.relay_client:
        s.relay_client.stop()
    rooms.close(s.id)
    media_store.record_end(s.id, reason, error)
    _changed(s, "ended")
    s.local_box.close()
    s.remote_box.close()


def end_for_device(device_id: str, reason: str = "relation_revoked") -> int:
    """확장관계 pause/revoke/remove 훅 — 그 장치의 세션을 전부 닫는다."""
    n = 0
    with _lock:
        for s in list(_sessions.values()):
            if s.device == device_id and s.state != "ended":
                end_locked(s, reason, error={"code": "relation_revoked", "message": "확장관계가 중지·해제·폐기됐습니다"})
                n += 1
    return n


# ── 능력·진단 ────────────────────────────────────────────────────────────────────
def capabilities(target: Optional[str] = None) -> Dict:
    if not target:
        ok, why = nostr.available()
        turn_ok, turn_why = sig.turn_configured()
        return {"body": "hub", "call": ok, "call_reason": why, "turn": turn_ok, "turn_reason": turn_why,
                "relay": bool(sig.relay_base()), "ice_servers": [{"urls": e["urls"]} for e in sig.ice_servers()],
                "quality_profile": sig.quality_profile("default")}
    import resident_pcs
    try:
        rec = resident_pcs.resolve(target, active=False)
    except ValueError as exc:
        raise MediaError("device_not_found", str(exc)) from exc
    reg = rec["registration"]
    caps = reg.get("capabilities") or {}
    online = reg["state"] == "active" and not reg.get("paused") and _now() - (reg.get("last_seen") or 0) <= 90
    busy = active_for_device(rec["device_id"])
    return {"device": rec["device_id"], "alias": rec["alias"], "body": reg.get("kind"), "online": online,
            "media_session": caps.get("media_session") or {}, "busy": busy.id if busy else None,
            "quality_profile": sig.quality_profile(_profile_for(caps, reg.get("kind") or "pc"))}


def health() -> Dict:
    ok, why = nostr.available()
    turn_ok, turn_why = sig.turn_configured()
    turn = []
    if turn_ok:
        for entry in sig.ice_servers("health"):
            for url in entry["urls"]:
                if url.startswith(("turn:", "turns:")):
                    turn.append({"url": url, **sig.probe_turn(url, entry.get("username", ""), entry.get("credential", ""))})
    relay = sig.relay_base()
    return {"signaling": {"nostr": ok, "reason": why, "relay_base": relay or None,
                          "route": (sig.policy().get("signaling") or {}).get("route")},
            "turn": {"configured": turn_ok, "reason": turn_why, "probes": turn},
            "active_sessions": len([s for s in _sessions.values() if s.state in ACTIVE_STATES]),
            "policy_path": str(sig.policy_path())}


# ── 청소기 ───────────────────────────────────────────────────────────────────────
@runtime_work.tracked("media-sweep", defer=True)
def sweep(now: Optional[float] = None) -> int:
    now = now or _now()
    reconnect_s = float(session_lease.profile("media").get("reconnect_s") or 30)
    n = 0
    with _lock:
        for s in list(_sessions.values()):
            if s.state == "ended":
                continue
            if s.state in ("inviting", "ringing") and s.expires_at and now > s.expires_at:
                end_locked(s, "invite_expired", error={"code": "invite_expired", "message": "응답이 없어 초대가 만료됐습니다"},
                           notify_remote=s.state == "inviting")
                n += 1
            elif s.state in ("active", "reconnecting", "needs_local_action") and s.lease.expired():
                end_locked(s, "lease_expired", error={"code": "connectivity_failed", "message": "연결 확인이 끊겨 세션을 닫았습니다"})
                n += 1
            elif s.state == "connecting" and s.lease.age() > s.lease.lease_s + reconnect_s:
                end_locked(s, "connect_timeout", error={"code": "connectivity_failed", "message": "연결이 제시간에 성립하지 않았습니다"})
                n += 1
            elif s.state == "reconnecting" and s.disconnected_at and now - s.disconnected_at > reconnect_s:
                end_locked(s, "reconnect_timeout", error={"code": "connectivity_failed", "message": "복구 시간 안에 다시 연결되지 않았습니다"})
                n += 1
        # 허브 → 확장 장치 keepalive(장치 WS). 장치는 이 순번으로 자기 임대를 갱신한다(계약 §3). 통화는 DataChannel 이 맡는다.
        for s in _sessions.values():
            if s.kind == "extension" and s.remote_attached and s.state != "ended" and now - s.keepalive_sent_at >= s.lease.keepalive_s:
                s.keepalive_sent_at = now
                _deliver_remote(s, sig.new_frame(s.id, "hub", "device", "keepalive", {}, generation=s.generation))
        session_lease.sweep(_sessions, lambda s: None, profile_name="media")
        for rid, (_, sid) in list(_requests.items()):
            if sid not in _sessions:
                _requests.pop(rid, None)
    return n


def _ensure_sweeper() -> None:
    global _sweeper
    if _sweeper and _sweeper.is_alive():
        return
    if os.environ.get("INDIEBIZ_MEDIA_NO_SWEEPER"):
        return

    def _run():
        while True:
            time.sleep(1.0)
            try:
                sweep()
            except Exception as exc:  # noqa: BLE001
                _log(f"[media] sweep 실패: {exc.__class__.__name__}")
    # 상주 스레드는 첫 미디어 요청의 자식이 아니다. 각 sweep의 유한 작업만 등록한다.
    with runtime_work.service_scope():
        _sweeper = threading.Thread(target=_run, name="media-sweeper", daemon=True)
        _sweeper.start()


def reset_for_tests() -> None:
    with _lock:
        for s in list(_sessions.values()):
            if s.state != "ended":
                end_locked(s, "test_reset", notify_remote=False)
        _sessions.clear()
        _requests.clear()
