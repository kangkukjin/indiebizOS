"""media_signaling.py — 시그널 메시지 계약·서명·순서·전송 어댑터 (2026-10-13).

설계 정본: docs/MEDIA_COMMUNICATION_DESIGN_2026_10_13.md §3·§5·§8, 와이어 계약: docs/MEDIA_SESSION_CONTRACT.md §3·§5.

이 모듈은 세션 상태를 모른다. 하는 일:
- 프레임 모양 검증·서명(HMAC-SHA256)·검증 — 릴레이가 바꾸면 검증 실패.
- 세대·순번 질서(낮은 세대·지난 순번·만료 거절), 선도착 candidate 의 세대 한정 버퍼.
- 소비자(브라우저 WS·장치 WS·릴레이 회원)를 위한 Outbox(큐 + 깨우기).
- 정책 데이터(data/media_policy.yaml): ICE 서버(TURN 단기 자격), 릴레이 주소, 품질 프로필.
- 전송 어댑터: Nostr(NIP-17 DM, 통화 제어 태그), 릴레이 방(호스트)·릴레이 클라이언트(아웃바운드 WS), TURN 탐침.
토큰·SDP·ICE 원문은 로그에 남기지 않는다.
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import socket
import struct
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

PROTOCOL_VERSION = 1
CALL_TAG = ("indiebiz-call", "1")   # NIP-17 rumor 태그 — 통화 제어 메시지 표식(채팅·AI 자동응답으로 가지 않는다)
FRAME_TYPES = {"invite", "accept", "reject", "offer", "answer", "candidate", "candidates_done", "keepalive", "ack",
               "state", "renegotiate", "update", "end"}
ROLES = {"caller", "callee", "hub", "device"}
_policy_cache = (None, None)
_policy_lock = threading.Lock()
_DEFAULT_POLICY = {
    "signaling": {"route": "auto", "relay_base": "", "bundle_wait_s": 1.5, "freshness_s": 90},
    "ice_servers": [{"urls": ["stun:stun.l.google.com:19302"]}],
    "quality_profiles": {"default": {"width": 1280, "height": 720, "fps": 24, "max_bitrate_kbps": 1500, "audio_kbps": 32}},
    "ringing": {"os_notification": True, "sound": True},
    "limits": {"max_active_sessions": 8, "max_frame_bytes": 65536, "content_max_bytes": 4 * 1024 ** 3},
}


# ── 정책 ────────────────────────────────────────────────────────────────────────
def policy_path() -> Path:
    from runtime_utils import get_data_path
    return Path(get_data_path()) / "media_policy.yaml"


def policy() -> Dict:
    """data/media_policy.yaml (mtime 캐시). 없거나 깨지면 기본값."""
    global _policy_cache
    p = policy_path()
    try:
        mtime = p.stat().st_mtime_ns
    except OSError:
        mtime = None
    with _policy_lock:
        if _policy_cache[0] == mtime and _policy_cache[1] is not None:
            return _policy_cache[1]
        doc = {}
        if mtime is not None:
            try:
                import yaml
                doc = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
            except Exception:  # noqa: BLE001
                doc = {}
        merged = json.loads(json.dumps(_DEFAULT_POLICY))
        for key, value in (doc or {}).items():
            if isinstance(value, dict) and isinstance(merged.get(key), dict):
                merged[key].update(value)
            else:
                merged[key] = value
        _policy_cache = (mtime, merged)
        return merged


def limits() -> Dict:
    return dict(policy().get("limits") or {})


def quality_profile(name: str) -> Dict:
    profiles = policy().get("quality_profiles") or {}
    return dict(profiles.get(name) or profiles.get("default") or _DEFAULT_POLICY["quality_profiles"]["default"])


def ice_servers(session_id: str = "") -> List[Dict]:
    """ICE 서버 목록 — TURN 단기 자격(coturn REST: username=만료:세션, credential=HMAC-SHA1 base64)."""
    out = []
    for row in policy().get("ice_servers") or []:
        if not isinstance(row, dict):
            continue
        urls = [u for u in (row.get("urls") or []) if isinstance(u, str) and u]
        if not urls:
            continue
        entry = {"urls": urls}
        if row.get("credential_mode") == "ephemeral":
            secret = os.environ.get(str(row.get("secret_env") or "MEDIA_TURN_SECRET"), "")
            if not secret:
                continue   # 비밀 없는 TURN 은 내려보내지 않는다(health 가 신고)
            ttl = int(row.get("ttl_s") or 600)
            username = f"{int(time.time()) + ttl}:{session_id or 'hub'}"
            digest = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
            entry.update(username=username, credential=base64.b64encode(digest).decode())
        elif row.get("username"):
            entry.update(username=row["username"], credential=row.get("credential") or "")
        out.append(entry)
    return out


def turn_configured() -> Tuple[bool, str]:
    """(설정됨?, 사유코드) — 주소 없음=turn_unconfigured, 비밀 없음=turn_secret_missing."""
    rows = [r for r in policy().get("ice_servers") or [] if isinstance(r, dict)
            and any(str(u).startswith(("turn:", "turns:")) for u in (r.get("urls") or []))]
    if not rows:
        return False, "turn_unconfigured"
    for r in rows:
        if r.get("credential_mode") == "ephemeral" and not os.environ.get(str(r.get("secret_env") or "MEDIA_TURN_SECRET"), ""):
            return False, "turn_secret_missing"
    return True, "ok"


def relay_base() -> str:
    base = str((policy().get("signaling") or {}).get("relay_base") or "").strip().rstrip("/")
    if base:
        return base
    try:
        import resident_pcs
        return (resident_pcs.public_base() or "").rstrip("/")
    except Exception:  # noqa: BLE001
        return ""


def relay_url(room: str) -> str:
    base = relay_base()
    if not base.startswith("https://"):
        return ""
    return "wss://" + base[len("https://"):] + "/media/relay/" + room


# ── 프레임 ──────────────────────────────────────────────────────────────────────
def canonical(frame: Dict) -> bytes:
    body = {k: v for k, v in frame.items() if k != "mac"}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign(frame: Dict, secret: str) -> Dict:
    out = dict(frame)
    out["mac"] = hmac.new(bytes.fromhex(secret), canonical(out), hashlib.sha256).hexdigest()
    return out


def verify(frame: Dict, secret: str) -> bool:
    mac = frame.get("mac")
    if not isinstance(mac, str) or not secret:
        return False
    expected = hmac.new(bytes.fromhex(secret), canonical(frame), hashlib.sha256).hexdigest()
    return hmac.compare_digest(mac, expected)


def new_frame(session_id: str, from_role: str, to_role: str, kind: str, payload: Optional[Dict] = None, *,
              generation: int = 0, seq: int = 0, ttl_s: float = 60.0) -> Dict:
    return {"v": PROTOCOL_VERSION, "session_id": session_id, "msg_id": secrets.token_hex(8),
            "from": from_role, "to": to_role, "generation": int(generation), "seq": int(seq),
            "expires_at": round(time.time() + float(ttl_s), 3), "type": kind, "payload": payload or {}}


def validate_frame(frame, *, max_bytes: Optional[int] = None) -> Dict:
    """계약 §3 모양 검사. 틀리면 ValueError(code)."""
    if not isinstance(frame, dict):
        raise ValueError("invalid_frame")
    if frame.get("v") != PROTOCOL_VERSION:
        raise ValueError("unsupported_protocol_version")
    sid = frame.get("session_id")
    if not isinstance(sid, str) or len(sid) != 32 or any(c not in "0123456789abcdef" for c in sid):
        raise ValueError("invalid_session_id")
    if frame.get("type") not in FRAME_TYPES:
        raise ValueError("invalid_frame_type")
    if frame.get("from") not in ROLES or frame.get("to") not in ROLES:
        raise ValueError("invalid_frame_role")
    for key in ("generation", "seq"):
        v = frame.get(key, 0)
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            raise ValueError("invalid_frame_" + key)
    exp = frame.get("expires_at")
    if exp is not None and (isinstance(exp, bool) or not isinstance(exp, (int, float))):
        raise ValueError("invalid_frame_expiry")
    if not isinstance(frame.get("payload", {}), dict):
        raise ValueError("invalid_frame_payload")
    cap = max_bytes or int(limits().get("max_frame_bytes") or 65536)
    if len(canonical(frame)) > cap:
        raise ValueError("frame_too_large")
    out = dict(frame)
    out.setdefault("payload", {})
    out.setdefault("generation", 0)
    out.setdefault("seq", 0)
    if not isinstance(out.get("msg_id"), str) or not out["msg_id"]:
        out["msg_id"] = secrets.token_hex(8)
    return out


def expired(frame: Dict, now: Optional[float] = None) -> bool:
    exp = frame.get("expires_at")
    return isinstance(exp, (int, float)) and (now or time.time()) > float(exp)


def fingerprint_of(sdp: str) -> str:
    """SDP 의 DTLS 지문(a=fingerprint:sha-256 AB:CD…) — 없으면 ''."""
    for line in (sdp or "").splitlines():
        line = line.strip()
        if line.lower().startswith("a=fingerprint:"):
            return line[len("a=fingerprint:"):].strip()
    return ""


class Order:
    """한 방향(한 발신자)의 세대·순번 질서. 같은 세대 안에서 순번은 증가만, 낮은 세대는 버린다.
    순번 0 은 '순번 없음'(순서 무관 프레임)으로 통과시킨다."""

    def __init__(self):
        self.generation = 0
        self.seq = 0
        self.seen: deque = deque(maxlen=512)

    def admit(self, frame: Dict) -> Tuple[bool, str]:
        if frame.get("msg_id") in self.seen:
            return False, "duplicate"
        gen, seq = int(frame.get("generation", 0)), int(frame.get("seq", 0))
        if gen < self.generation:
            return False, "stale_generation"
        if gen > self.generation:
            self.generation, self.seq = gen, 0
        if seq:
            if seq <= self.seq:
                return False, "stale_seq"
            self.seq = seq
        self.seen.append(frame.get("msg_id"))
        return True, "ok"


class CandidateBuffer:
    """offer/answer 보다 먼저 온 candidate 를 같은 세대 안에서만 붙든다."""

    def __init__(self):
        self.generation = -1
        self.described = False
        self.held: List[Dict] = []

    def mark_described(self, generation: int) -> None:
        """offer/answer 가 다른 경로(초대·수락 동봉)로 이미 전달됐을 때 — 그 세대의 candidate 를 더 붙들지 않는다."""
        if generation != self.generation:
            self.generation, self.held = generation, []
        self.described = True

    def observe(self, frame: Dict) -> List[Dict]:
        """프레임을 보고 '지금 흘려보낼 프레임 목록'을 돌려준다(버퍼 플러시 포함)."""
        gen = int(frame.get("generation", 0))
        if gen != self.generation:
            self.generation, self.described, self.held = gen, False, []
        kind = frame.get("type")
        if kind in ("offer", "answer"):
            self.described = True
            out, self.held = [frame] + self.held, []
            return out
        if kind == "candidate" and not self.described:
            if len(self.held) < 256:
                self.held.append(frame)
            return []
        return [frame]


class Outbox:
    """소비자(WS 핸들러) 하나를 위한 큐. 다른 스레드가 push 하면 소비자의 이벤트 루프를 깨운다."""

    def __init__(self, maxlen: int = 1024):
        self._q: deque = deque(maxlen=maxlen)
        self._waiter: Optional[Tuple] = None
        self._lock = threading.Lock()
        self.closed = False
        self.attached = False
        self.dropped = 0

    def push(self, message: Dict) -> None:
        with self._lock:
            if len(self._q) == self._q.maxlen:
                self.dropped += 1
            self._q.append(message)
            self._wake()

    def _wake(self) -> None:
        if self._waiter:
            loop, event = self._waiter
            try:
                loop.call_soon_threadsafe(event.set)
            except RuntimeError:
                pass

    def watch(self, loop, event) -> None:
        with self._lock:
            self._waiter = (loop, event)
            if self._q or self.closed:
                self._wake()

    def unwatch(self) -> None:
        with self._lock:
            self._waiter = None

    def take(self) -> List[Dict]:
        with self._lock:
            out, self._q = list(self._q), deque(maxlen=self._q.maxlen)
            return out

    def close(self) -> None:
        with self._lock:
            self.closed = True
            self._wake()


# ── Nostr 전송 ───────────────────────────────────────────────────────────────────
class NostrTransport:
    """통화 제어 프레임을 NIP-17 DM 으로. 동기 발송(수 초)이므로 스레드에서 보낸다."""

    def __init__(self, sender: Optional[Callable] = None, log: Callable = print):
        self._sender = sender
        self.log = log

    def available(self) -> Tuple[bool, str]:
        if self._sender:
            return True, "ok"
        try:
            from indienet import get_indienet
            net = get_indienet()
            if not net.is_initialized():
                return False, "nostr_identity_missing"
            return True, "ok"
        except Exception as exc:  # noqa: BLE001
            return False, "nostr_unavailable:" + exc.__class__.__name__

    def my_pubkey_hex(self) -> str:
        try:
            from indienet import get_indienet
            key = get_indienet().identity.public_key
            return key.hex() if hasattr(key, "hex") else str(key or "")
        except Exception:  # noqa: BLE001
            return ""

    def send(self, to_hex: str, frame: Dict, *, done: Optional[Callable] = None) -> None:
        def _run():
            ok, err = False, ""
            try:
                content = json.dumps(frame, ensure_ascii=False, separators=(",", ":"))
                if self._sender:
                    ok = bool(self._sender(to_hex, content, [list(CALL_TAG)]))
                else:
                    from indienet import get_indienet
                    ok = bool(get_indienet().send_dm_nip17(to_hex, content, extra_tags=[list(CALL_TAG)]))
                if not ok:
                    err = "signaling_unavailable"
            except Exception as exc:  # noqa: BLE001
                err = "signaling_unavailable:" + exc.__class__.__name__
                self.log(f"[media] Nostr 시그널 발송 실패({frame.get('type')}): {exc.__class__.__name__}")
            if done:
                done(ok, err)
        threading.Thread(target=_run, name="media-nostr-send", daemon=True).start()


def is_call_frame_tags(tags) -> bool:
    for t in tags or []:
        if isinstance(t, list) and len(t) >= 2 and t[0] == CALL_TAG[0]:
            return True
    return False


def is_call_frame_content(content: str) -> bool:
    """태그가 유실된 경로(폰 브리지·dms.db)용 보조 판정 — 통화 제어 JSON 모양인가."""
    if not isinstance(content, str) or not content.startswith("{") or '"session_id"' not in content:
        return False
    try:
        obj = json.loads(content)
    except ValueError:
        return False
    return isinstance(obj, dict) and obj.get("v") == PROTOCOL_VERSION and obj.get("type") in FRAME_TYPES


# ── 릴레이 방(호스트) ─────────────────────────────────────────────────────────────
class RelayRooms:
    """이 허브가 중계만 하는 방. 토큰 = HMAC(session_secret, room). 메시지는 손대지 않고 다른 회원에게 전달."""

    def __init__(self):
        self._rooms: Dict[str, Dict] = {}
        self._lock = threading.Lock()

    @staticmethod
    def token(secret: str, room: str) -> str:
        return hmac.new(bytes.fromhex(secret), room.encode(), hashlib.sha256).hexdigest()[:32]

    def open(self, room: str, secret: str, on_frame: Optional[Callable] = None) -> str:
        with self._lock:
            self._rooms[room] = {"token": self.token(secret, room), "members": {}, "on_frame": on_frame,
                                 "opened": time.monotonic()}
            return self._rooms[room]["token"]

    def close(self, room: str) -> None:
        with self._lock:
            info = self._rooms.pop(room, None)
        if info:
            for box in info["members"].values():
                box.close()

    def join(self, room: str, token: str, member: str) -> Outbox:
        with self._lock:
            info = self._rooms.get(room)
            if not info or not hmac.compare_digest(info["token"], token or ""):
                raise ValueError("relay_unauthorized")
            if member in info["members"]:
                raise ValueError("relay_member_attached")
            box = Outbox()
            info["members"][member] = box
            return box

    def leave(self, room: str, member: str) -> None:
        with self._lock:
            info = self._rooms.get(room)
            if info:
                box = info["members"].pop(member, None)
                if box:
                    box.close()

    def publish(self, room: str, sender: str, frame: Dict) -> int:
        """sender 를 제외한 회원에게 전달 + 호스트 콜백(허브 자신이 참가자일 때)."""
        with self._lock:
            info = self._rooms.get(room)
            if not info:
                return 0
            targets = [b for m, b in info["members"].items() if m != sender]
            cb = info.get("on_frame")
        for box in targets:
            box.push(frame)
        if cb and sender != "host":
            cb(frame)
        return len(targets)

    def members(self, room: str) -> List[str]:
        with self._lock:
            info = self._rooms.get(room)
            return list(info["members"].keys()) if info else []


class RelayClient:
    """다른 허브의 릴레이 방에 아웃바운드 WS 로 붙는 클라이언트(수신 허브 쪽)."""

    def __init__(self, url: str, token: str, on_frame: Callable, log: Callable = print):
        self.url, self.token, self.on_frame, self.log = url, token, on_frame, log
        self._ws = None
        self._stop = threading.Event()
        self.connected = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="media-relay-client", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        import websocket
        backoff = 1.0
        while not self._stop.is_set():
            try:
                self._ws = websocket.WebSocketApp(
                    self.url + "?token=" + self.token,
                    on_open=lambda ws: self.connected.set(),
                    on_message=lambda ws, msg: self._on_message(msg),
                    on_close=lambda ws, *a: self.connected.clear(),
                    on_error=lambda ws, err: None)
                self._ws.run_forever(ping_interval=20, ping_timeout=10)
            except Exception:  # noqa: BLE001
                pass
            self.connected.clear()
            if self._stop.is_set():
                break
            self._stop.wait(backoff)
            backoff = min(backoff * 2, 10.0)

    def _on_message(self, msg: str) -> None:
        try:
            frame = json.loads(msg)
        except ValueError:
            return
        if isinstance(frame, dict):
            self.on_frame(frame)

    def send(self, frame: Dict) -> bool:
        ws = self._ws
        if not ws or not self.connected.is_set():
            return False
        try:
            ws.send(json.dumps(frame, ensure_ascii=False, separators=(",", ":")))
            return True
        except Exception:  # noqa: BLE001
            return False

    def stop(self) -> None:
        self._stop.set()
        ws = self._ws
        if ws:
            try:
                ws.close()
            except Exception:  # noqa: BLE001
                pass


# ── TURN 탐침 ─────────────────────────────────────────────────────────────────────
_STUN_MAGIC = 0x2112A442


def _stun_attr(kind: int, value: bytes) -> bytes:
    pad = (4 - len(value) % 4) % 4
    return struct.pack("!HH", kind, len(value)) + value + b"\x00" * pad


def _stun_message(msg_type: int, attrs: bytes, txid: bytes, key: Optional[bytes] = None) -> bytes:
    if key is None:
        return struct.pack("!HHI", msg_type, len(attrs), _STUN_MAGIC) + txid + attrs
    # MESSAGE-INTEGRITY: 길이는 MI 속성(24바이트)까지 포함한 값으로 계산
    header = struct.pack("!HHI", msg_type, len(attrs) + 24, _STUN_MAGIC) + txid
    mac = hmac.new(key, header + attrs, hashlib.sha1).digest()
    return header + attrs + _stun_attr(0x0008, mac)


def _parse_attrs(data: bytes) -> Dict[int, bytes]:
    out, pos = {}, 20
    while pos + 4 <= len(data):
        kind, length = struct.unpack("!HH", data[pos:pos + 4])
        out[kind] = data[pos + 4:pos + 4 + length]
        pos += 4 + length + (4 - length % 4) % 4
    return out


def probe_turn(url: str, username: str, credential: str, timeout: float = 3.0) -> Dict:
    """TURN Allocate 한 번(UDP 또는 TCP) — 자격·도달성 검증. 성공=relayed address 확보.
    결과: {ok, code, detail}. 코드: ok / unreachable / unauthorized / unsupported_url / error."""
    try:
        scheme, rest = url.split(":", 1)
        if scheme not in ("turn", "turns"):
            return {"ok": False, "code": "unsupported_url", "detail": url}
        hostport, _, query = rest.partition("?")
        host, _, port = hostport.partition(":")
        port = int(port or (5349 if scheme == "turns" else 3478))
        transport = "udp"
        for part in query.split("&"):
            if part.startswith("transport="):
                transport = part.split("=", 1)[1]
        if scheme == "turns":
            transport = "tls"
        txid = secrets.token_bytes(12)
        req1 = _stun_message(0x0003, _stun_attr(0x0019, struct.pack("!B3x", 17)), txid)   # Allocate, UDP relay
        if transport == "udp":
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.settimeout(timeout)
            sock.sendto(req1, (host, port))
            data, _ = sock.recvfrom(2048)
        else:
            raw = socket.create_connection((host, port), timeout=timeout)
            sock = raw
            if transport == "tls":
                import ssl
                sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
            sock.sendall(req1)
            data = sock.recv(2048)
        attrs = _parse_attrs(data)
        realm, nonce = attrs.get(0x0014, b""), attrs.get(0x0015, b"")
        if struct.unpack("!H", data[:2])[0] != 0x0113 or not realm or not nonce:
            sock.close()
            return {"ok": False, "code": "error", "detail": "unexpected_first_response"}
        key = hashlib.md5((username + ":" + realm.decode(errors="replace") + ":" + credential).encode()).digest()
        attrs2 = (_stun_attr(0x0019, struct.pack("!B3x", 17)) + _stun_attr(0x0006, username.encode())
                  + _stun_attr(0x0014, realm) + _stun_attr(0x0015, nonce))
        req2 = _stun_message(0x0003, attrs2, secrets.token_bytes(12), key)
        if transport == "udp":
            sock.sendto(req2, (host, port))
            data, _ = sock.recvfrom(2048)
        else:
            sock.sendall(req2)
            data = sock.recv(2048)
        sock.close()
        kind = struct.unpack("!H", data[:2])[0]
        if kind == 0x0103:
            return {"ok": True, "code": "ok", "detail": "allocated"}
        err = _parse_attrs(data).get(0x0009, b"")
        code = (err[2] & 0x07) * 100 + err[3] if len(err) >= 4 else 0
        return {"ok": False, "code": "unauthorized" if code in (401, 438) else "error", "detail": f"stun_error_{code}"}
    except (socket.timeout, ConnectionError, OSError) as exc:
        return {"ok": False, "code": "unreachable", "detail": exc.__class__.__name__}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "code": "error", "detail": exc.__class__.__name__}
