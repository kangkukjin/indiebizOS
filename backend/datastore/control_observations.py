"""제어 관측 원장 — 드라이버의 세 부품 가운데 데이터 쪽(세계의 명사).

CONTROL_DRIVER_DESIGN_2026_10_20 §3·§12 ①. 가이드·실행 부품은 코드(몸)이고, "어느 폰이
화면 제어를 거절했는지", "어느 사이트가 로그인 없이 302 를 돌려주는지" 같은 개체·환경별
사실은 반증 가능한 데이터다. 51회차 발견 다섯 건이 세션 기억에만 남고 몸에 없던 이유가
이 통로의 부재였다.

행 형식: {observation_id, observed_at, version, environment, fact, source, status, scope, supersedes}
- status: valid · recheck(새 판본·환경에 적용되는지 미확인) · refuted · superseded. **지우지 않는다.**
- 쓰기의 의미는 추가와 정정(행 단위)이다. 목록 덮어쓰기가 아니다.
- 관측 시각과 환경이 없는 행은 받지 않는다 — 시각 없는 사실은 영원히 남아 되는 기능을
  안 되는 줄 알게 만든다.

정본 위치는 대상에 따라 둘이다. 기기(`device:<id>`)는 등록 기록(limb_keys registration /
hardware_registry)의 `observations` 칸, 앱·사이트(`app:`·`site:`)는 이 파일이 소유하는
`data/control_observations.json`(식별자 키). 읽기·쓰기 함수는 하나라 호출자는 자리를 모른다.
"""
import json
import logging
import os
import re
import tempfile
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

DATA_PATH = Path(__file__).resolve().parents[2] / "data"
STORE_PATH = DATA_PATH / "control_observations.json"

STATUSES = ("valid", "recheck", "refuted", "superseded")
FIELDS = ("observation_id", "observed_at", "version", "environment", "fact", "source",
          "status", "scope", "supersedes")
SURFACE_KINDS = ("app", "site", "device")
MAX_ROWS_PER_SURFACE = 500
_lock = threading.RLock()


class ObservationError(ValueError):
    pass


# ---------------------------------------------------------------- 식별자

def normalize_surface(surface) -> str:
    """`app:com.apple.Safari` / `site:example.com` / `device:<id>` — 종류 접두사 필수."""
    if not isinstance(surface, str) or ":" not in surface:
        raise ObservationError("조작면 식별자는 app:·site:·device: 접두사가 필요합니다")
    kind, _, name = surface.strip().partition(":")
    kind = kind.lower()
    if kind not in SURFACE_KINDS or not name.strip():
        raise ObservationError("조작면 식별자는 app:·site:·device: 접두사가 필요합니다")
    name = name.strip()
    if kind != "device":
        name = name.lower()
    return f"{kind}:{name}"


def _is_device(surface: str) -> bool:
    """등록 기록이 정본인 기기. 본체(`device:__local__`)는 등록 기록이 없어 파일 원장이 맡는다."""
    return surface.startswith("device:") and surface != "device:__local__"


# ---------------------------------------------------------------- 행 검증

def _check_time(value) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ObservationError("observed_at(관측 시각)이 필요합니다")
    text = value.strip()
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        raise ObservationError("observed_at 은 ISO 8601 시각이어야 합니다") from None
    return text


def validate_row(row: dict, *, new_id: bool = True) -> dict:
    """한 행을 정규화한다. 환경·시각 없는 행, 알 수 없는 칸, 긴 본문은 거절."""
    if not isinstance(row, dict):
        raise ObservationError("관측 행은 객체여야 합니다")
    unknown = set(row) - set(FIELDS)
    if unknown:
        raise ObservationError(f"알 수 없는 관측 칸: {sorted(unknown)}")
    out = {}
    out["observed_at"] = _check_time(row.get("observed_at"))
    env = row.get("environment")
    if not isinstance(env, dict) or not env:
        raise ObservationError("environment(관측 환경)가 필요합니다 — 기기 ID, 사이트 도메인·프로필·계정 유무 등")
    if len(json.dumps(env, ensure_ascii=False)) > 2000:
        raise ObservationError("environment 가 너무 큽니다")
    out["environment"] = env
    fact = row.get("fact")
    if not isinstance(fact, str) or not fact.strip() or len(fact) > 1000:
        raise ObservationError("fact(관측 사실)는 1000자 이내 문자열이어야 합니다")
    out["fact"] = fact.strip()
    version = row.get("version", "unknown")
    if not isinstance(version, str) or not version.strip() or len(version) > 200:
        raise ObservationError("version 은 문자열이어야 합니다(모르면 \"unknown\")")
    out["version"] = version.strip()
    source = row.get("source", "")
    if not isinstance(source, str) or len(source) > 300:
        raise ObservationError("source 는 300자 이내 문자열이어야 합니다")
    out["source"] = source.strip()
    status = row.get("status", "valid")
    if status not in STATUSES:
        raise ObservationError(f"status 는 {'/'.join(STATUSES)} 가운데 하나입니다")
    out["status"] = status
    scope = row.get("scope", "")
    if scope is None:
        scope = ""
    if not isinstance(scope, str) or len(scope) > 300:
        raise ObservationError("scope 는 300자 이내 문자열이어야 합니다")
    out["scope"] = scope.strip()
    supersedes = row.get("supersedes")
    if supersedes is not None and (not isinstance(supersedes, str) or not supersedes.strip()):
        raise ObservationError("supersedes 는 대체하는 관측 행의 observation_id 입니다")
    out["supersedes"] = supersedes.strip() if supersedes else None
    oid = row.get("observation_id")
    if oid is None and new_id:
        oid = "obs_" + uuid.uuid4().hex[:8]
    if not isinstance(oid, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", oid or ""):
        raise ObservationError("observation_id 는 영숫자·_·-·. 64자 이내입니다")
    out["observation_id"] = oid
    return out


# ---------------------------------------------------------------- 저장소 (앱·사이트)

def _load() -> Dict[str, List[dict]]:
    try:
        data = json.loads(STORE_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        logger.warning("제어 관측 원장을 읽지 못했습니다: %s", exc)
        return {}
    return data if isinstance(data, dict) else {}


def _save(data: Dict[str, List[dict]]) -> None:
    STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(STORE_PATH.parent), prefix=".control_observations.", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=1)
        os.replace(tmp, STORE_PATH)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ---------------------------------------------------------------- 저장소 (기기)

def _device_rows(device_id: str) -> List[dict]:
    import limb_keys
    rec = limb_keys.get_by_device(device_id)
    if rec is None:
        import hardware_registry
        rec = next((r for r in hardware_registry.devices() if r.get("device_id") == device_id), None)
    if rec is None:
        raise ObservationError("등록된 기기가 아닙니다: " + device_id)
    reg = rec.get("registration") or {}
    rows = reg.get("observations")
    return [dict(r) for r in rows] if isinstance(rows, list) else []


def _device_write(device_id: str, rows: List[dict]) -> None:
    import hardware_registry
    import limb_keys
    if hardware_registry.contains(device_id):
        hardware_registry.update(device_id, observations=rows)
        return
    limb_keys.resident_update(device_id, observations=rows)


# ---------------------------------------------------------------- 공개 함수

def rows(surface) -> List[dict]:
    key = normalize_surface(surface)
    with _lock:
        if _is_device(key):
            return _device_rows(key.partition(":")[2])
        return [dict(r) for r in _load().get(key, [])]


def counts() -> Dict[str, int]:
    """소개 행·snapshot 알림용 — 앱·사이트 식별자별 행 수(기기는 등록 기록이 직접 보인다)."""
    with _lock:
        return {k: len(v) for k, v in _load().items() if isinstance(v, list) and v}


def count(surface) -> int:
    try:
        return len(rows(surface))
    except ObservationError:
        return 0


def _merge(existing: List[dict], incoming: List[dict]) -> List[dict]:
    """추가와 정정. 같은 observation_id 는 그 행만 바꾸고, supersedes 는 옛 행을 superseded 로 돌린다."""
    by_id = {r.get("observation_id"): r for r in existing}
    for row in incoming:
        oid = row["observation_id"]
        if oid in by_id:
            # 정정: 사실·시각·환경은 보존, 상태·범위·대체 참조만 바뀐다. 과거 관측은 당시의 사실로 남는다.
            current = by_id[oid]
            for field in ("status", "scope", "supersedes"):
                if row.get(field) is not None or field == "supersedes" and "supersedes" in row:
                    current[field] = row[field]
        else:
            by_id[oid] = row
            existing.append(row)
        if row.get("supersedes"):
            old = by_id.get(row["supersedes"])
            if old is None:
                raise ObservationError(f"대체 대상 관측 행이 없습니다: {row['supersedes']}")
            if old["observation_id"] != oid:
                old["status"] = "superseded"
    if len(existing) > MAX_ROWS_PER_SURFACE:
        raise ObservationError(f"조작면 하나의 관측 행은 {MAX_ROWS_PER_SURFACE}개까지입니다. 일반화·대체로 정리하세요")
    return existing


def record(surface, new_rows, *, source: str = "") -> dict:
    """행 추가·정정. 전부 검증한 뒤에만 쓴다(전부 아니면 무). 반환 = {surface, count, observation_ids}."""
    key = normalize_surface(surface)
    if isinstance(new_rows, dict):
        new_rows = [new_rows]
    if not isinstance(new_rows, list) or not new_rows:
        raise ObservationError("observations 는 관측 행 하나 이상의 목록입니다")
    if len(new_rows) > 50:
        raise ObservationError("한 번에 50행까지 기록합니다")
    with _lock:
        existing = rows(key)
        known = {r.get("observation_id") for r in existing}
        prepared = []
        for raw in new_rows:
            row = validate_row(raw)
            if row["observation_id"] in known and row.get("fact") and "fact" in raw \
                    and next(r for r in existing if r["observation_id"] == row["observation_id"])["fact"] != row["fact"]:
                raise ObservationError("기존 관측 행의 fact 는 바꾸지 않습니다. 새 행을 추가하고 supersedes 로 가리키세요")
            if not row["source"] and source:
                row["source"] = source
            prepared.append(row)
        merged = _merge(existing, prepared)
        if _is_device(key):
            _device_write(key.partition(":")[2], merged)
        else:
            data = _load()
            data[key] = merged
            _save(data)
        return {"surface": key, "count": len(merged),
                "observation_ids": [r["observation_id"] for r in prepared]}


def applicable(surface, *, version: Optional[str] = None) -> List[dict]:
    """실행 전 검사용 — valid·recheck 행만. version 을 주면 판본이 다른 valid 행은 recheck 로 **표시해 돌려준다**
    (저장은 호출자가 record 로 정정한다 — 읽기가 쓰지 않는다)."""
    out = []
    for row in rows(surface):
        if row.get("status") not in ("valid", "recheck"):
            continue
        row = dict(row)
        if (version and row.get("version") not in ("unknown", version) and row["status"] == "valid"
                and not row.get("scope")):
            row["status"] = "recheck"
            row["recheck_reason"] = f"관측 판본 {row.get('version')} ≠ 현재 {version}"
        out.append(row)
    return out
