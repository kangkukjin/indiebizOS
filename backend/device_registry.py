"""device_registry.py — 다중 노드 프레즌스 레지스트리 (Stage 1: 단일 사용자, 기기 여러 대)

폰 수를 어디에도 고정하지 않는다. 각 노드가 허브(맥)에 자기를 등록(register)하고 주기적으로
heartbeat 하면, 허브가 "지금 연결된 노드" 라이브 테이블을 유지한다 → 폰 N대째 추가 = 그 폰만
켜면 끝(다른 폰·허브 설정 무수정). "지금 몇 대?"는 연결(연락)으로 확인한다.

- 능력 클래스(거친 2종): phone-class(폰=센서·effector) / compute-class(맥=무거운 연산·네이티브).
- 라우팅(ibl_engine)이 능력으로 로컬/원격 판정 후, 원격이면 라이브 후보 중 선택
  (명시 @주소 > 자기-가능 > 주(主)기기 > 모호하면 되물음).
- 도달성의 최종 검증은 포워드 시도 자체(_forward_*의 phone_unreachable).

설계: docs/MULTINODE_TOPOLOGY_DESIGN.md
"""
import json
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

# === 능력 클래스 (Stage 1, 거친 2종) ===
PHONE_CLASS = "phone-class"
COMPUTE_CLASS = "compute-class"

# heartbeat 후 이 시간(초) 안에 본 노드만 "라이브". self 항목은 TTL 면제(항상 라이브).
LIVE_TTL = 150.0

_lock = threading.RLock()
_cache: Optional[Dict] = None


def _base_path() -> Path:
    env = os.environ.get("INDIEBIZ_BASE_PATH")
    if env:
        return Path(env)
    return Path(__file__).parent.parent


def _store_path() -> Path:
    # 폰은 BaseBundle 이 지우는 트리를 피해 userdata sibling 에 둔다(business.db 선례).
    ud = os.environ.get("INDIEBIZ_USERDATA")
    if ud:
        return Path(ud) / "device_registry.json"
    return _base_path() / "data" / "device_registry.json"


def _now() -> float:
    return time.time()


def _load() -> Dict:
    global _cache
    if _cache is not None:
        return _cache
    p = _store_path()
    data = {"nodes": {}}
    try:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                loaded = json.load(f) or {}
            if isinstance(loaded.get("nodes"), dict):
                data = loaded
    except Exception:
        data = {"nodes": {}}
    _cache = data
    return _cache


def _save() -> None:
    p = _store_path()
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_cache or {"nodes": {}}, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception as e:
        print(f"[device_registry] 저장 실패: {e}")


# === 능력 매핑 ===

def required_capability(runs_on: Optional[str]) -> Optional[str]:
    """액션의 runs_on → 요구 능력 클래스. anywhere/None = 요구 없음(로컬 가능)."""
    if runs_on == "phone_only":
        return PHONE_CLASS
    if runs_on == "pc_only":   # 폰이 아닌 데스크톱(맥·리눅스·윈도우) 몸 = compute-class
        return COMPUTE_CLASS
    return None


def _body_profile() -> str:
    """이 몸의 종류를 *감지*해서 반환(detect_body 경유 — 포크-가드: profile 직접 분기 금지,
    감지하되 적어주지 않음). detect_body 미가용이면 빈 문자열(→ compute-class 기본)."""
    try:
        from runtime_utils import detect_body
        return detect_body().get("profile", "") or ""
    except Exception:
        return ""


def local_capabilities(profile: Optional[str] = None) -> List[str]:
    """이 몸이 제공하는 능력 클래스. 자기-보고용 (detect_body 기반)."""
    if profile is None:
        profile = _body_profile()
    if profile == "phone":
        return [PHONE_CLASS]
    return [COMPUTE_CLASS]


# === 등록 / heartbeat ===

def register(device_id: str, alias: str, capabilities: List[str], url: str,
             auth: str = "x_phone_token", owner: str = "self",
             primary: bool = False, is_self: bool = False) -> Dict:
    """노드 자기등록(upsert). last_seen 갱신. 허브가 호출(POST /nodes/register) 또는 자기 항목."""
    if not device_id:
        return {"error": "device_id 필수"}
    with _lock:
        data = _load()
        entry = data["nodes"].get(device_id, {})
        entry.update({
            "device_id": device_id,
            "alias": alias or entry.get("alias") or device_id,
            "capabilities": list(capabilities or entry.get("capabilities") or []),
            "url": (url or entry.get("url") or "").rstrip("/"),
            "auth": auth or entry.get("auth") or "x_phone_token",
            "owner": owner or entry.get("owner") or "self",
            # primary 는 허브가 set_primary(/nodes/primary)로만 정함 — 노드 재등록(heartbeat 재기동)이
            # 사용자의 주(主) 지정을 덮어쓰지 않도록 기존 값 보존(신규 항목만 payload 기본값).
            "primary": entry.get("primary", bool(primary)),
            "self": bool(is_self) or bool(entry.get("self")),
            "last_seen": _now(),
        })
        data["nodes"][device_id] = entry
        _save()
        return dict(entry)


def heartbeat(device_id: str) -> bool:
    with _lock:
        data = _load()
        e = data["nodes"].get(device_id)
        if not e:
            return False
        e["last_seen"] = _now()
        _save()
        return True


def self_device_id() -> str:
    """이 설치본의 안정 device_id (없으면 생성·영속). 같은 기종 2대도 충돌 안 함.

    npub(사람 신원)이 아니라 *기기* 식별자 — Stage1은 owner=self 라 device_id 만으로 충분.
    """
    import uuid
    p = _store_path().parent / "device_id.txt"
    try:
        if p.exists():
            v = p.read_text(encoding="utf-8").strip()
            if v:
                return v
        v = uuid.uuid4().hex[:12]
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(v, encoding="utf-8")
        return v
    except Exception:
        # 영속 실패해도 프로세스 동안 일관된 id (재시작 시 바뀜 — graceful)
        return "node-" + uuid.uuid4().hex[:8]


def self_alias(profile: Optional[str] = None) -> str:
    """주소지정용 사람 친화 별칭. 명시(INDIEBIZ_NODE_ALIAS) 우선, 없으면 프로파일 기본.

    폰 기본값은 device_id 접미사를 붙여 *충돌 없는* 고유 별칭을 보장(여러 폰이 다 "폰"이 되어
    @주소가 모호해지는 것 방지). 사용자가 INDIEBIZ_NODE_ALIAS(provision --alias)로 "폰2" 등
    친화 이름을 주면 그게 우선.
    """
    a = os.environ.get("INDIEBIZ_NODE_ALIAS")
    if a:
        return a.strip()
    if profile is None:
        profile = _body_profile()
    if profile == "phone":
        return "폰-" + self_device_id()[-4:]
    return "맥"


def ensure_self(device_id: str = "", alias: str = "", url: str = "",
                auth: str = "launcher_session", primary: bool = True) -> Dict:
    """현재 프로세스 자신을 레지스트리에 등록(부팅 시). 자기 능력은 프로파일에서 자기-보고."""
    return register(device_id or self_device_id(), alias or self_alias(),
                    local_capabilities(), url, auth=auth, is_self=True, primary=primary)


# === 조회 ===

def _is_live(entry: Dict, ttl: float = LIVE_TTL) -> bool:
    if entry.get("self"):
        return True
    ls = entry.get("last_seen") or 0
    return (_now() - ls) <= ttl


def list_live(ttl: float = LIVE_TTL) -> List[Dict]:
    with _lock:
        data = _load()
        return [dict(e) for e in data["nodes"].values() if _is_live(e, ttl)]


def live_aliases(ttl: float = LIVE_TTL) -> List[str]:
    return [e.get("alias", "?") for e in list_live(ttl)]


def get_by_alias(alias: str, ttl: float = LIVE_TTL) -> Optional[Dict]:
    if not alias:
        return None
    with _lock:
        data = _load()
        for e in data["nodes"].values():
            if e.get("alias") == alias and _is_live(e, ttl):
                return dict(e)
    return None


def get(device_id: str) -> Optional[Dict]:
    with _lock:
        e = _load()["nodes"].get(device_id)
        return dict(e) if e else None


def live_with_capability(cap: str, ttl: float = LIVE_TTL,
                         exclude_self: bool = True) -> List[Dict]:
    """그 능력을 제공하는, 지금 라이브인 노드들. exclude_self=원격 후보만(자기 제외)."""
    out = []
    for e in list_live(ttl):
        if exclude_self and e.get("self"):
            continue
        if cap in (e.get("capabilities") or []):
            out.append(e)
    return out


def set_primary(target: str) -> Optional[Dict]:
    """target(별칭 또는 device_id)을 그 능력의 주(主)기기로 지정.

    같은 능력 클래스를 공유하는 다른 노드의 primary 는 해제(능력당 0~1 보장) — 주소 생략 시
    자동선택이 유일하게 결정되도록. 대상 미발견이면 None.
    """
    with _lock:
        data = _load()
        tgt = None
        for e in data["nodes"].values():
            if e.get("device_id") == target or e.get("alias") == target:
                tgt = e
                break
        if tgt is None:
            return {"error": f"'{target}' 노드를 찾을 수 없습니다."}
        tgt_caps = set(tgt.get("capabilities") or [])
        for e in data["nodes"].values():
            if e is tgt:
                e["primary"] = True
            elif tgt_caps & set(e.get("capabilities") or []):
                # 같은 능력을 공유하는 노드만 주(主) 해제 (다른 능력 클래스는 영향 없음)
                e["primary"] = False
        _save()
        return dict(tgt)


def prune(ttl: float = LIVE_TTL) -> int:
    """오래 안 보인 비-self 항목 제거(선택). 제거 수 반환."""
    with _lock:
        data = _load()
        dead = [k for k, e in data["nodes"].items()
                if not e.get("self") and not _is_live(e, ttl)]
        for k in dead:
            del data["nodes"][k]
        if dead:
            _save()
        return len(dead)


def invalidate():
    global _cache
    with _lock:
        _cache = None
