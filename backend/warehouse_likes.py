"""
warehouse_likes.py — 창고 파일 좋아요 (2026-07-19).

방명록(warehouse_guestbook)의 형제 — 파일 주인(원 창고)에게 쌓이는 공개 쓰기 면.
좋아요는 원 창고가 세는 카운터다: 방문자·이웃 런처가 POST /portal/like(공개 주소 /like)로
토글하고, 카운트는 매니페스트 파일 항목(likes)과 창고 홈(♥N)에 실린다 → 이웃 폴러가
스냅샷에 담아 피드에서도 보인다.

중복 방지 키 = 회원이면 "m:<member id>"(기기 무관), 손님이면 "g:<ip>". 완벽하지 않지만
(IP 로테이션) 좋아요는 부드러운 신호라 이 수준이 맞다 — 방명록이 ip 를 적는 것과 같은 결.
저장 = data/warehouse_likes.json {경로: [키…]} (런타임 상태 — repo 미추적 데이터 구역).
파일이 삭제·이동하면 경로 키가 남는데, 카운트 소비처가 전부 "현재 파일 목록에 annotate"
방식이라 고아 키는 조용히 안 보인다(방명록 gone 처리와 같은 결).

api_portal 과의 관계: 이 모듈이 라우터(/portal/like)를 갖고, api_portal 은 annotate()만
가져다 쓴다(1500줄 규칙 — api_portal 비대화 방지). 순환 임포트는 핸들러 안 지연 임포트로 회피.
"""

import json
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

_ROOT = Path(__file__).resolve().parent.parent
_STORE = _ROOT / "data" / "warehouse_likes.json"
_LOCK = threading.Lock()
_MIN_INTERVAL_S = 2            # IP 연타 가드 (토글이라 파괴적이지 않음 — 가볍게)
_LAST_BY_IP: dict = {}

router = APIRouter(prefix="/portal", tags=["portal"])


def _load() -> dict:
    try:
        d = json.loads(_STORE.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _save(d: dict) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _STORE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_STORE)


def toggle(path: str, key: str) -> tuple:
    """좋아요 토글 — (liked 지금 눌린 상태인가, count) 반환."""
    with _LOCK:
        d = _load()
        keys = list(d.get(path) or [])
        if key in keys:
            keys.remove(key)
            liked = False
        else:
            keys.append(key)
            liked = True
        if keys:
            d[path] = keys
        else:
            d.pop(path, None)
        _save(d)
        return liked, len(keys)


def count_map() -> dict:
    """경로 → 좋아요 수 (0 인 경로는 없음)."""
    return {p: len(k) for p, k in _load().items() if k}


def annotate(files: list) -> list:
    """파일 항목 목록(name 키)에 likes 를 얹는다 — 0 이면 필드 자체를 안 실어 매니페스트를
    가볍게 유지. 목록이 이미 레벨 절단면이라 숨은 파일 카운트는 새지 않는다."""
    counts = count_map()
    for f in files:
        n = counts.get(f.get("name") or "")
        if n:
            f["likes"] = n
    return files


@router.post("/like")
async def like(request: Request, x_showcase_secret: str = Header(default=""),
               x_client_ip: str = Header(default="")):
    """좋아요 토글 — 공개 주소 /like 가 여기 닿는다(Worker·직접 서빙 게이트웨이가 매핑).
    회원(pk 쿠키)=계정 단위, 손님=IP 단위 중복 방지. 내 절단면에 보이는 파일만
    (방명록 about 과 같은 규칙 — 안 보이는 파일 존재를 좋아요로 떠보는 것 차단)."""
    import api_portal
    api_portal._check_secret(x_showcase_secret)
    core = api_portal._core()
    viewer, level = api_portal._viewer_level(core, request)
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    path = str(body.get("path", "")).strip()[:400]
    if not path:
        raise HTTPException(status_code=400, detail="path required")

    ip = x_client_ip or (request.client.host if request.client else "")
    now = time.time()
    if ip and now - _LAST_BY_IP.get(ip, 0) < _MIN_INTERVAL_S:
        raise HTTPException(status_code=429, detail="너무 빠릅니다")
    _LAST_BY_IP[ip] = now

    api_portal._ensure_warehouses()
    mine = {f["name"] for f in api_portal._accessible_files(level)}
    if path not in mine:
        raise HTTPException(status_code=404, detail="no such file")

    if viewer:
        key = f"m:{viewer.get('id') or viewer.get('key') or viewer.get('login_id') or 'member'}"
    else:
        key = f"g:{ip or 'unknown'}"
    liked, count = toggle(path, key)
    return JSONResponse({"ok": True, "liked": liked, "count": count},
                        headers={"Cache-Control": "no-store"})
