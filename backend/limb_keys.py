"""limb_keys.py — USB 헬퍼(손발) 자격 원장.

USB 로 낯선 PC 에 꽂아 실행하는 헬퍼는 "이 PC 를 내 몸의 착탈식 손발로 붙인다".
그 인가는 **허브 비밀번호가 아니라 여기서 발급하는 limb key** 다 — USB 를 잃어버려도
키 하나만 폐기(revoke)하면 끝이고, 허브 로그인/구독/데이터 API 키는 USB 에 실리지 않는다.

원장은 포털 멤버키 패턴(secrets 토큰 + revoke/regen)에 **만료(TTL)** 를 더했다. 저장은
device_registry 와 같은 무-flock 원자쓰기(threading.RLock + os.replace) — 윈도우 이식성
게이트(fcntl 부류 금지)를 그대로 지킨다.

한 개의 키 = 한 개의 손발 장치(device_id). 접속하면 **자동승인**된다(api_limb.limb_connect,
touch(approve_if_pending=True)) — 오배송(엉뚱한 PC 에서 명령 실행) 방어는 승인 게이트가
아니라 **명령 시 손발 이름 명시**로 옮겼다(손발이 둘 이상이면 handler._resolve_limb 이 이름을
강제). 다른 PC 로 옮겨 붙어도 자동승인하되 host 변경은 알림으로 통지(유출 조기 발견). 유출
시 최종 방어선은 revoke(키 폐기). approve() 는 특정 손발을 수동으로 잠그거나 다시 여는 용도.
해제는 [limbs:guestpc]{op:detach}(헬퍼 종료) 또는 창 닫기.

어휘: [self:limb]{op:issue/list/revoke/approve} 가 이 모듈을 부른다.
수신 API: backend/api_limb.py (/limb/connect·poll·result).
"""
import json
import os
import secrets
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

# 손발의 능력 클래스 — 폰(phone-class)·허브(compute-class)과 구별. 일반 IBL 라우팅
# (ibl_engine._resolve_and_maybe_forward)은 이 클래스를 요구하는 액션이 없으므로 절대
# 자동으로 손발을 대상으로 고르지 않는다 — 손발엔 오직 [limbs:guestpc] 만 명시적으로 닿는다.
GUEST_PC_CLASS = "guest-pc-class"

# 발급 시 기본 유효기간(일). 0=무기한 — 휴대 USB 는 오래 들고 다니므로 기본을 무기한으로
# 둔다. 폐기가 필요하면 revoke 로 명시적으로 한다. 특정 기간을 원하면 ttl_days 로 준다.
DEFAULT_TTL_DAYS = 0

_lock = threading.RLock()
_cache: Optional[Dict] = None


def _store_path() -> Path:
    # 폰은 BaseBundle 이 지우는 트리를 피해 userdata sibling 에 둔다(device_registry 선례).
    ud = os.environ.get("INDIEBIZ_USERDATA")
    if ud:
        return Path(ud) / "limb_keys.json"
    base = os.environ.get("INDIEBIZ_BASE_PATH")
    root = Path(base) if base else Path(__file__).parent.parent
    return root / "data" / "limb_keys.json"


def _now() -> float:
    return time.time()


def _load() -> Dict:
    global _cache
    if _cache is not None:
        return _cache
    p = _store_path()
    data = {"keys": {}}
    try:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                loaded = json.load(f) or {}
            if isinstance(loaded.get("keys"), dict):
                data = loaded
    except Exception:
        data = {"keys": {}}
    _cache = data
    return _cache


def _save() -> None:
    p = _store_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_cache or {"keys": {}}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception as e:
        print(f"[limb_keys] 저장 실패: {e}")


def _expired(rec: Dict, now: Optional[float] = None) -> bool:
    exp = rec.get("expires_at")
    if not exp:
        return False
    return (now or _now()) >= exp


def _public(rec: Dict, now: Optional[float] = None) -> Dict:
    """키 원문을 뺀 표시용 사본 — 원장 노출(list)에서 키 전체를 흘리지 않는다."""
    now = now or _now()
    return {
        "alias": rec.get("alias"),
        "device_id": rec.get("device_id"),
        "key_hint": (rec.get("key") or "")[:6] + "…",
        "created_at": rec.get("created_at"),
        "expires_at": rec.get("expires_at"),
        "revoked": bool(rec.get("revoked")),
        "expired": _expired(rec, now),
        "approved": bool(rec.get("approved")),
        "last_used": rec.get("last_used"),
        "last_host": rec.get("last_host"),
    }


# === 발급 / 폐기 ===

def mint(alias: str = "", ttl_days: float = DEFAULT_TTL_DAYS) -> Dict:
    """새 손발 키 발급. 반환 = {key, device_id, alias, expires_at} (key 는 이때만 원문 노출).

    key 는 USB 페이로드에 박혀 나가고, 원장엔 같은 값이 남아 검증·폐기에 쓰인다.
    device_id 는 이 손발의 안정 식별자 — 승인이 device 단위로 붙는다.
    """
    key = "limb_" + secrets.token_urlsafe(24)
    device_id = "guestpc-" + secrets.token_hex(6)
    now = _now()
    expires_at = (now + float(ttl_days) * 86400.0) if ttl_days and ttl_days > 0 else None
    rec = {
        "key": key,
        "device_id": device_id,
        "alias": alias or ("손발-" + device_id[-4:]),
        "created_at": now,
        "expires_at": expires_at,
        "revoked": False,
        "approved": False,
        "last_used": None,
        "last_host": None,
    }
    with _lock:
        data = _load()
        data["keys"][key] = rec
        _save()
    return {
        "key": key,
        "device_id": device_id,
        "alias": rec["alias"],
        "expires_at": expires_at,
    }


def validate(key: str) -> Optional[Dict]:
    """키가 유효(존재·미폐기·미만료)하면 원장 레코드(내부용, key 포함) 반환, 아니면 None."""
    if not key:
        return None
    with _lock:
        rec = _load()["keys"].get(key)
        if not rec:
            return None
        if rec.get("revoked") or _expired(rec):
            return None
        return dict(rec)


def touch(key: str, host: str = "", approve_if_pending: bool = False) -> Optional[Dict]:
    """접속 시 last_used/last_host 갱신. approve_if_pending=True 면 최초 접속 자동승인(자동승인 키)."""
    with _lock:
        data = _load()
        rec = data["keys"].get(key)
        if not rec:
            return None
        rec["last_used"] = _now()
        if host:
            rec["last_host"] = host
        if approve_if_pending and not rec.get("approved"):
            rec["approved"] = True
        data["keys"][key] = rec
        _save()
        return dict(rec)


def approve(target: str, approved: bool = True) -> Optional[Dict]:
    """손발 승인/승인취소. target = 키 원문 · device_id · alias 중 무엇이든."""
    with _lock:
        data = _load()
        rec = _find_locked(data, target)
        if not rec:
            return None
        rec["approved"] = bool(approved)
        data["keys"][rec["key"]] = rec
        _save()
        return _public(rec)


def revoke(target: str) -> Optional[Dict]:
    """손발 키 폐기(비가역 아님 — 원장엔 남되 revoked=True). target = 키·device_id·alias."""
    with _lock:
        data = _load()
        rec = _find_locked(data, target)
        if not rec:
            return None
        rec["revoked"] = True
        data["keys"][rec["key"]] = rec
        _save()
        return _public(rec)


def _find_locked(data: Dict, target: str) -> Optional[Dict]:
    if not target:
        return None
    keys = data["keys"]
    if target in keys:
        return keys[target]
    for rec in keys.values():
        if rec.get("device_id") == target or rec.get("alias") == target:
            return rec
    return None


def list_keys(include_revoked: bool = True) -> List[Dict]:
    now = _now()
    with _lock:
        recs = list(_load()["keys"].values())
    out = [_public(r, now) for r in recs]
    if not include_revoked:
        out = [r for r in out if not r["revoked"]]
    return out


def get_by_device(device_id: str) -> Optional[Dict]:
    with _lock:
        for rec in _load()["keys"].values():
            if rec.get("device_id") == device_id:
                return dict(rec)
    return None


def invalidate():
    global _cache
    with _lock:
        _cache = None
