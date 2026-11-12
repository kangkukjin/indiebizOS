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
import hashlib
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
MEMBER_PC_CLASS = "member-pc-class"



def has_ibl_body(registration) -> bool:
    """등록 기기에 IBL 문장을 받아 자기 사전으로 실행할 IndieBiz OS 가 있는가 — 기기의 신고가 근거다.

    폰은 설치본 자체가 손발(adapter indiebiz-v1)이고, PC 는 헬퍼가 그 PC 의 로컬 IndieBiz OS 응답을
    `ibl: true` 로 신고한다. 이것이 있으면 그 기기에 시킬 일의 기본 통로는 그 몸이고, 헬퍼 조작은
    몸이 없거나 응답하지 않을 때의 아래층이다(2026-11-12 사용자 결정)."""
    reg = registration or {}
    return reg.get("adapter") == "indiebiz-v1" or (reg.get("capabilities") or {}).get("ibl") is True


def is_member(rec: Dict) -> bool:
    """회원 PC 등록과 구형 이웃 결합 자격을 일반 손발과 구분한다."""
    return bool(rec.get("member_id")) or rec.get("neighbor_id") not in (None, "")

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
    root = Path(base) if base else Path(__file__).parent.parent.parent
    return root / "data" / "limb_keys.json"


def _now() -> float:
    return time.time()


_cache_mtime = None


def _file_mtime(p: Path):
    try:
        return p.stat().st_mtime_ns
    except OSError:
        return None


def _load() -> Dict:
    """원장 로드 — 파일 mtime 이 바뀌었으면 캐시를 버린다(2026-10-13).

    provision_phone_limb.py 처럼 *다른 프로세스*가 원장에 자격을 쓰면 라이브 허브가 그걸 바로 봐야
    한다(안 그러면 폰이 enroll 직후 sync 할 때 invalid_registration). 매 호출 stat 1회 — 싸다."""
    global _cache, _cache_mtime
    p = _store_path()
    m = _file_mtime(p)
    if _cache is not None and m == _cache_mtime:
        return _cache
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
    _cache_mtime = m
    return _cache


def _save() -> None:
    global _cache
    p = _store_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            os.chmod(tmp, 0o600)
            json.dump(_cache or {"keys": {}}, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, p)
        global _cache_mtime
        _cache_mtime = _file_mtime(p)
        # 쓰기 관문 원장 — 손발 자격 발급·폐기는 보안 사건(관측, 실패 무해)
        try:
            from write_ledger import log_write
            log_write(p, event="write", gate="limb_keys")
        except Exception:
            pass
    except Exception as e:
        _cache = None
        raise OSError("limb credential persistence failed") from e


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
        # 접속 때 헬퍼가 올린 환경 프로브 — 그 PC 가 어떤 기계인지 왕복 없이 보이게.
        # (키 원문과 달리 민감하지 않고, 이게 없으면 프로브를 저장해둔 뜻이 없다.)
        "env": rec.get("env") or (rec.get("registration") or {}).get("capabilities"),
        "neighbor_id": rec.get("neighbor_id"),
        "member_id": rec.get("member_id"),
        "member_pc": rec.get("member_pc"),
        "registration": rec.get("registration"),
        "invitation": bool(rec.get("invitation")),
    }


# === 발급 / 폐기 ===

def mint(alias: str = "", ttl_days: float = DEFAULT_TTL_DAYS, neighbor_id=None,
         *, member_pc: Optional[Dict] = None) -> Dict:
    """새 손발 키 발급. 반환 = {key, device_id, alias, expires_at} (key 는 이때만 원문 노출).

    key 는 USB 페이로드에 박혀 나가고, 원장엔 같은 값이 남아 검증·폐기에 쓰인다.
    device_id 는 이 손발의 안정 식별자 — 승인이 device 단위로 붙는다.
    """
    key = "limb_" + secrets.token_urlsafe(24)
    if member_pc is not None and neighbor_id is not None:
        raise ValueError("회원 PC 등록은 이웃과 결합하지 않습니다")
    device_id = ("memberpc-" if member_pc is not None else "guestpc-") + secrets.token_hex(6)
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
        # 회원 열쇠(2026-09-14): 기존 이웃에 결합된 손발 — /m/chat 의 주체·레벨이 이 사람에게서 온다.
        "neighbor_id": neighbor_id,
    }
    if member_pc is not None:
        rec.update(member_id=device_id, approved=True,
                   member_pc={"user_label": str(member_pc.get("user_label", "")),
                              "note": str(member_pc.get("note", "")), "enabled": True,
                              "ttl_days": ttl_days})
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
        if (rec.get("revoked") or _expired(rec) or rec.get("invitation") or rec.get("registration")
                or (rec.get("member_pc") or {}).get("enabled") is False):
            return None
        return dict(rec)


def touch(key: str, host: str = "", approve_if_pending: bool = False,
          new_session: bool = False, env: Optional[Dict] = None) -> Optional[Dict]:
    """접속 시 last_used/last_host 갱신. approve_if_pending=True 면 최초 접속 자동승인(자동승인 키).

    new_session=True(=/limb/connect)면 **세션 id 를 새로 발급**한다. 이게 '최신 헬퍼가
    이긴다' 규칙의 근거다 — 같은 키로 헬퍼가 둘 이상 붙으면 큐를 나눠 가져 명령이 어느
    PC 에서 도는지 비결정적이 되고(실측), 세션 cwd 같은 상태까지 갈라진다. 낡은 세션은
    poll 에서 stale 통보를 받고 스스로 물러난다. USB 를 다른 PC 로 옮기는 정상 로밍도
    이 규칙으로 깔끔히 정리된다(옛 PC 의 창이 저절로 닫힌다)."""
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
        if new_session:
            rec["session"] = secrets.token_hex(8)
        if env:
            # 접속 시 환경 프로브 — 허브가 그 PC 신상(os·권한·셸·패키지매니저·GUI)을
            # 왕복 없이 갖는다. AI 가 낯선 PC 에서 문법을 추측하다 실패하는 걸 막는 밑천.
            rec["env"] = env
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
    for rec in sorted(keys.values(), key=lambda item: bool(item.get("invitation"))):
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


def update_member_pc(device_id: str, *, alias=None, user_label=None, note=None,
                     enabled=None, revoke_key=False, rotate_key=False) -> Optional[Dict]:
    """PC 등록 메타데이터·자격을 원자 갱신. 재발급도 기기와 사용량 ID는 유지한다."""
    with _lock:
        data = _load()
        rec = next((r for r in data["keys"].values() if r.get("device_id") == device_id
                    and r.get("member_id") and isinstance(r.get("member_pc"), dict)), None)
        if not rec or rec.get("revoked"):
            return None
        if alias is not None:
            rec["alias"] = alias
        for name, value in (("user_label", user_label), ("note", note), ("enabled", enabled)):
            if value is not None:
                rec["member_pc"][name] = value
        if enabled is not None or revoke_key or rotate_key:
            rec["session"] = secrets.token_hex(8)
            rec["env"] = {}
        if revoke_key:
            rec["revoked"] = True
        if rotate_key:
            rec.pop("desktop", None)
            rec.pop("desktop_invite", None)
            del data["keys"][rec["key"]]
            rec["key"] = "limb_" + secrets.token_urlsafe(24)
            days = rec["member_pc"].get("ttl_days", 0)
            rec["expires_at"] = _now() + days * 86400 if days else None
            rec["last_used"] = None
            rec["last_host"] = None
            rec["env"] = {}
        data["keys"][rec["key"]] = rec
        _save()
        out = _public(rec)
        if rotate_key:
            out["key"] = rec["key"]
        return out


def resident_invite(alias, ttl_days=0):
    """One-use installation invitation; never a command credential."""
    import math
    days = float(ttl_days)
    if isinstance(ttl_days, bool) or not math.isfinite(days) or days < 0:
        raise ValueError("ttl_days must be a finite nonnegative number")
    with _lock:
        issued = mint(alias, ttl_days=0)
        rec = _load()["keys"][issued["key"]]
        rec.update(invitation=True, invite_until=_now() + 86400,
                   resident_days=days)
        _save()
        return issued


def resident_installer():
    """Reusable USB enrollment credential, never accepted for execution."""
    with _lock:
        for rec in _load()["keys"].values():
            if rec.get("installer") and not rec.get("revoked"):
                return dict(rec)
        issued = mint("USB PC 등록", ttl_days=0)
        rec = _load()["keys"][issued["key"]]
        rec.update(invitation=True, installer=True, installations={}, resident_days=0)
        _save()
        return dict(rec)


def resident_installer_revoke():
    """Stop future USB enrollments without revoking installed PCs."""
    with _lock:
        for rec in _load()["keys"].values():
            if rec.get("installer"):
                rec["revoked"] = True
        _save()


def resident_enroll(invitation, installation_id, alias=None, kind="pc", adapter="resident-v1", *, enrollment_proof=None):
    """초대를 이 설치(installation_id)에 묶어 실행 자격으로 바꾼다.

    kind/adapter (2026-10-13): 헬퍼 PC = ("pc", "resident-v1") / IndieBiz OS 폰 손발 = ("phone", "indiebiz-v1").
    adapter 는 허브가 하달 봉투 종류를 고르는 축(resident_pcs.submit) — 폰엔 ibl·info 만."""
    import re
    if adapter not in ("resident-v1", "indiebiz-v1") or kind not in ("pc", "phone"):
        raise ValueError("invalid_adapter")
    if not re.fullmatch(r"[a-f0-9]{32}", installation_id):
        raise ValueError("invalid_installation_id")
    if enrollment_proof is not None and not re.fullmatch(r"[a-f0-9]{64}", enrollment_proof):
        raise ValueError("invalid_enrollment_proof")
    proof_hash = hashlib.sha256(enrollment_proof.encode()).hexdigest() if enrollment_proof else None
    with _lock:
        data = _load()
        rec = data["keys"].get(invitation)
        if not rec or not rec.get("invitation") or rec.get("revoked"):
            raise ValueError("invalid_invitation")
        if rec.get("installer"):
            bound_key = rec.get("installations", {}).get(installation_id)
        else:
            bound_key = rec.get("bound_key")
        if bound_key:
            if not rec.get("installer") and rec["bound_installation"] != installation_id:
                raise ValueError("invitation_used")
            bound = data["keys"].get(bound_key)
            if not bound or bound.get("revoked") or _expired(bound) or bound["registration"]["state"] != "active":
                raise ValueError("registration_closed")
            protected = bound["registration"].get("enrollment_proof_hash")
            if protected and not secrets.compare_digest(protected, proof_hash or ""):
                raise PermissionError("enrollment_proof_required")
            if proof_hash and not protected:
                raise ValueError("existing_registration_not_protected")
            return dict(bound)
        if not rec.get("installer") and _now() > rec["invite_until"]:
            raise ValueError("invitation_expired")
        name = alias if alias is not None else ("" if rec.get("installer") else rec["alias"])
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80 or any(ord(c) < 32 for c in name):
            raise ValueError("PC 이름을 1~80자로 입력하세요")
        name = name.strip()
        if any(r.get("registration", {}).get("state") != "removed" and r.get("registration")
               and not r.get("revoked") and r.get("alias") == name for r in data["keys"].values()):
            raise ValueError("이미 등록된 PC 이름입니다. 다른 이름을 입력하세요")
        issued = mint(name, rec["resident_days"])
        bound = data["keys"][issued["key"]]
        bound["approved"] = True
        bound["registration"] = {"installation_id": installation_id, "generation": secrets.token_hex(16),
                                 "kind": kind, "adapter": adapter, "state": "active",
                                 "paused": False, "wake": None}
        if proof_hash:
            bound["registration"]["enrollment_proof_hash"] = proof_hash
        if rec.get("installer"):
            rec["installations"][installation_id] = issued["key"]
        else:
            rec.update(bound_installation=installation_id, bound_key=issued["key"])
        _save()
        return dict(bound)


# === 하드웨어 묶음 — 한 PC 의 여러 설치를 손발 하나로 (2026-11-11) ===
#
# Windows 는 화면을 다루는 프로세스(사용자 세션)와 로그인 없이 관리자 권한으로 도는 프로세스
# (LocalSystem 서비스)를 하나로 만들 수 없고, 권한이 다른 둘은 열쇠도 따로 가진다. 그래서 설치
# 등록은 둘이지만 그것은 안쪽 사정이다 — 주인과 AI 가 보는 단위는 하드웨어 하나다.
# 관리 서비스 등록의 registration.attached_to 가 같은 PC 의 사용자 세션 등록(주 등록)을 가리킨다.
# 이 칸은 허브가 주인 결정으로만 쓴다. 헬퍼가 보고한 값(호스트 이름 등)으로 자동 결합하지 않는다 —
# 유출된 등록 자격으로 남의 PC 이름을 대고 그 PC 의 관리자 명령을 가로채는 길이 되기 때문이다.

def _alive(rec) -> bool:
    reg = (rec or {}).get("registration") or {}
    return bool(reg) and not rec.get("revoked") and reg.get("state") != "removed"


def _primary_locked(data, rec):
    """딸린 통로의 주 등록. 주 등록이 사라졌으면 None — 고아 통로는 독립 손발로 다시 보인다."""
    primary = ((rec or {}).get("registration") or {}).get("attached_to")
    if not primary:
        return None
    owner = next((r for r in data["keys"].values() if r.get("device_id") == primary), None)
    return owner if _alive(owner) else None


def hardware_of(device_id: str) -> Optional[str]:
    """이 등록이 다른 손발에 딸린 통로면 그 주 등록의 device_id, 아니면 None."""
    with _lock:
        data = _load()
        rec = next((r for r in data["keys"].values() if r.get("device_id") == device_id), None)
        owner = _primary_locked(data, rec) if _alive(rec) else None
        return owner["device_id"] if owner else None


def channels(device_id: str) -> List[Dict]:
    """주 등록에 딸린 살아 있는 통로들(내부용 사본, key 포함)."""
    with _lock:
        data = _load()
        return [dict(r) for r in data["keys"].values()
                if _alive(r) and r["registration"].get("attached_to") == device_id
                and _primary_locked(data, r)]


def fold_channels(rows: List[Dict]) -> List[Dict]:
    """표시용 행에서 딸린 통로를 주 등록 행의 channels 로 접는다.

    주 등록이 같은 목록에 살아 있을 때만 접는다. 그렇지 않은 통로는 그대로 남아 눈에 보인다."""
    by_id = {r.get("device_id"): r for r in rows if _alive(r)}
    out = []
    for row in rows:
        owner = by_id.get(((row.get("registration") or {}).get("attached_to")))
        if _alive(row) and owner is not None and owner is not row:
            owner.setdefault("channels", []).append(row)
        else:
            out.append(row)
    return out


def resident_attach(device, primary):
    """관리 서비스 등록을 같은 PC 의 사용자 세션 등록에 딸린 통로로 묶는다. primary=None 이면 푼다."""
    with _lock:
        data = _load()
        rec = _find_locked(data, device)
        if not _alive(rec):
            raise ValueError("resident_not_found")
        reg = rec["registration"]
        if primary is None:
            reg.pop("attached_to", None)
            _save()
            return _public(rec)
        owner = _find_locked(data, primary)
        if not _alive(owner) or owner is rec:
            raise ValueError("묶을 대상 PC를 찾지 못했습니다")
        owned = owner["registration"]
        caps, owner_caps = reg.get("capabilities") or {}, owned.get("capabilities") or {}
        if reg["state"] != "active" or owned["state"] != "active":
            raise ValueError("등록이 활성 상태인 PC만 묶을 수 있습니다")
        if (reg.get("adapter"), owned.get("adapter")) != ("resident-v1", "resident-v1"):
            raise ValueError("PC 헬퍼 등록만 묶을 수 있습니다")
        if caps.get("service_scope") != "machine" or owner_caps.get("service_scope") == "machine":
            raise ValueError("관리 서비스를 사용자 세션 헬퍼에 묶습니다. 방향이나 종류가 맞지 않습니다")
        if owned.get("attached_to"):
            raise ValueError("대상이 이미 다른 PC에 딸린 통로입니다")
        if not caps.get("hostname") or caps.get("hostname") != owner_caps.get("hostname"):
            raise ValueError("두 헬퍼가 보고한 컴퓨터 이름이 다릅니다. 같은 PC인지 확인하세요")
        if any(_alive(r) and r is not rec and r["registration"].get("attached_to") == owner["device_id"]
               for r in data["keys"].values()):
            raise ValueError("이 PC에는 이미 관리 서비스가 묶여 있습니다")
        if any(_alive(r) and r["registration"].get("attached_to") == rec["device_id"]
               for r in data["keys"].values()):
            raise ValueError("다른 통로가 딸려 있는 등록은 묶을 수 없습니다")
        reg["attached_to"] = owner["device_id"]
        _save()
        return _public(rec)


def resident_update(device, **changes):
    allowed = {"state", "paused", "wake", "capabilities", "last_seen", "removal_receipt", "context", "observations"}
    if changes.keys() - allowed:
        raise ValueError("invalid_registration_field")
    if "observations" in changes:
        # 제어 관측 칸(CONTROL_DRIVER_DESIGN §3) — 행 검증·추가·정정의 주인은 control_observations 이다.
        # 여기서는 "목록" 모양만 지키고 통째로 받는다(그 모듈이 병합한 전체를 넘긴다).
        if not isinstance(changes["observations"], list) or len(changes["observations"]) > 500:
            raise ValueError("관측 칸은 500행 이내 목록이어야 합니다")
    if "context" in changes:
        context = changes["context"]
        if not isinstance(context, str) or len(context) > 1000:
            raise ValueError("장치 설명은 1000자 이내 문자열이어야 합니다")
        changes["context"] = context.strip()
    with _lock:
        rec = _find_locked(_load(), device)
        if not rec or not rec.get("registration"):
            raise ValueError("resident_not_found")
        reg = rec["registration"]
        if reg["state"] != "active" and changes.get("state") == "active":
            raise ValueError("registration_closed")
        if reg["state"] == "removed" and changes.get("state", "removed") != "removed":
            raise ValueError("registration_closed")
        reg.update(changes)
        _save()
        return _public(rec)


def resident_auth(key, installation_id, cleanup=False):
    """Removal-only traffic may authenticate after expiry, never after hard revoke."""
    with _lock:
        rec = _load()["keys"].get(key)
        reg = (rec or {}).get("registration") or {}
        if (not rec or rec.get("revoked") or reg.get("installation_id") != installation_id
                or not reg or (reg.get("state") == "removed" and not cleanup)):
            raise ValueError("invalid_registration")
        if _expired(rec) and reg["state"] == "active":
            reg["state"] = "removal_pending"
            _save()
        if not cleanup and (reg["state"] != "active" or reg.get("paused")):
            raise ValueError("registration_unavailable")
        return dict(rec)
