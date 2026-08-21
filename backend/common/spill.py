"""spill.py — 파이프 통화의 스필(외부화)과 참조 해소 (2026-08-22, 프로그램급 IBL M5 / 설계 §2.5-3·2.6).

크기는 문장이 모르는 런타임 사실이라 엔진만 안다. 통화가 임계를 넘으면 엔진이 파일로 내리고
파이프에는 **참조**만 흘린다 — 그리고 **신고**한다(침묵 클램프 금지).

참조 봉투 모양(= `[self:write]{spill:true}` 와 같은 규약):
    {"items": [], "ref": {"path", "kind", "count", "bytes", "expires_at"}, "_spilled": true}

소비자(변환자 `_get_items`·each 입력·$items 바인딩·write 싱크)는 `resolve_ref` 한 줄로 투명하게
읽는다. 디렉토리 `data/spill/` 은 소유 선언상 **cache** 계급 — 문장을 다시 돌리면 재생산되는
파생물이라 기계 삭제가 맞다(2026-08-22 판정): 쓸 때마다 24h 지난 파일을 기회주의적으로 거둔다.
"""
import json
import os
import time
import uuid
from typing import Any, Dict, Optional, Tuple

SPILL_TTL_S = 24 * 3600
AUTO_SPILL_THRESHOLD = 200_000          # 문자 — 이 위는 모델 컨텍스트로 돌려 보낼 크기가 아니다


def _root() -> str:
    here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(here, "data", "spill")


def spill_dir() -> str:
    d = _root()
    os.makedirs(d, exist_ok=True)
    return d


def gc(max_age_s: int = SPILL_TTL_S) -> int:
    """TTL 지난 스필 파일 삭제 — 삭제 수 반환. 실패는 조용히(캐시 청소가 본 작업을 깨면 안 된다)."""
    n = 0
    try:
        d = _root()
        if not os.path.isdir(d):
            return 0
        now = time.time()
        for name in os.listdir(d):
            p = os.path.join(d, name)
            try:
                if os.path.isfile(p) and now - os.path.getmtime(p) > max_age_s:
                    os.remove(p)
                    n += 1
            except OSError:
                pass
    except Exception:
        pass
    return n


def make_ref(path: str, kind: str, count: Optional[int], nbytes: int) -> Dict[str, Any]:
    return {"path": path, "kind": kind, "count": count, "bytes": nbytes,
            "expires_at": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(time.time() + SPILL_TTL_S))}


def spill_write(payload: str, tag: str = "step") -> Dict[str, Any]:
    """통화(문자열)를 스필 파일로 내리고 참조 봉투(dict)를 돌려준다."""
    gc()
    d = spill_dir()
    name = f"{time.strftime('%Y%m%d_%H%M%S')}_{tag}_{uuid.uuid4().hex[:6]}.json"
    path = os.path.join(d, name)
    with open(path, "w", encoding="utf-8") as f:
        f.write(payload)
    kind, count = "text", None
    s = payload.lstrip()
    if s[:1] in "{[":
        try:
            obj = json.loads(payload)
            if isinstance(obj, dict) and isinstance(obj.get("items"), list):
                kind, count = "items", len(obj["items"])
            elif isinstance(obj, list):
                kind, count = "list", len(obj)
            else:
                kind = "json"
        except Exception:
            pass
    return {"items": [], "ref": make_ref(path, kind, count, len(payload)), "_spilled": True}


def is_ref(obj: Any) -> bool:
    return (isinstance(obj, dict) and isinstance(obj.get("ref"), dict)
            and isinstance(obj["ref"].get("path"), str)
            and (obj.get("_spilled") or obj.get("spilled")))


def read_ref(ref: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    """(본문, 오류문). 만료·부재는 정직한 오류."""
    path = ref.get("path")
    if not path or not os.path.isfile(path):
        return None, (f"스필 참조가 가리키는 파일이 없습니다: {path} — 스필은 {SPILL_TTL_S // 3600}h 뒤 "
                      "삭제됩니다(캐시). 문장을 다시 실행하세요.")
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(), None
    except OSError as e:
        return None, f"스필 참조 읽기 실패: {e}"


def resolve_ref(obj: Any) -> Tuple[Any, Optional[str]]:
    """참조 봉투면 본문(파싱 시도)으로, 아니면 그대로. (값, 오류문)."""
    if not is_ref(obj):
        return obj, None
    body, err = read_ref(obj["ref"])
    if err:
        return obj, err
    s = body.lstrip()
    if s[:1] in "{[":
        try:
            return json.loads(body), None
        except Exception:
            pass
    return body, None


def resolve_ref_str(raw: Any) -> Tuple[Any, Optional[str]]:
    """문자열 봉투(JSON)도 받는 해소판 — 파이프 이음매(_prev_result)는 문자열이다."""
    if isinstance(raw, str):
        s = raw.lstrip()
        if s.startswith("{") and '"ref"' in s[:400]:
            try:
                obj = json.loads(raw)
            except Exception:
                return raw, None
            if is_ref(obj):
                return resolve_ref(obj)
        return raw, None
    return resolve_ref(raw)
