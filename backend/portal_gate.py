"""portal_gate.py — 회원이 계기를 빌려 쓰는 자리: 계기 페이지 + 실행 게이트 + 오디오 프록시.

  · GET  /portal/inst/{slug}/{iid}  — 계기 페이지(런처 제네릭 렌더러 재사용, __PORTAL 주입)
  · POST /portal/tool/{slug}/{iid}  — ★회원 실행 게이트
  · GET  /portal/tune/{slug}/{video_id} — 유튜브뮤직 외부망 재생용 오디오 프록시

★실행 게이트가 이 시스템에서 가장 위험한 표면이다 — 범용 /ibl/execute 직결 금지가 전부:
계기 `app:` 블록이 선언한 *템플릿의 인스턴스*만 통과시키고(리터럴 파라미터 일치 강제·
`$key`/`{field}` 자리만 값 허용·파이프/병렬 거부·self/others 노드 하드 거부), 3중 일일
한도와 감사로그를 건다. 화이트리스트 판정은 portal_core 단일 소스.

렌더러를 포크하지 않는다(계기 페이지는 런처 셸을 매개변수화해 재사용) — 포크하는 순간
데스크탑/원격/포털 셋이 되고, 그게 감사 ④가 방금 없앤 부류다.

api_portal.py 분할(2026-08-05 감사 부채 ⑨).
"""

import re
import json
import time
import threading

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from portal_base import (
    _check_secret, _client_ip, _core, _portal_or_404, _renderer, _viewer,
)

router = APIRouter()

# ── 계기 페이지 — 런처 제네릭 렌더러 재사용 (__PORTAL 매개변수화, 포크 금지) ──

@router.get("/inst/{slug}/{iid}")
async def instrument_page(slug: str, iid: str, request: Request,
                          x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    universe = {u["key"]: u for u in core.listable_universe(state)}
    u = universe.get(iid)
    if not u or u["kind"] != "instrument":
        raise HTTPException(status_code=404, detail="no such instrument")
    d = core.display_entry(portal, u)
    viewer = _viewer(core, portal, request, slug)
    lv = int(viewer.get("level", 0)) if viewer else -1
    ml = int(d.get("min_level", 1))
    if not d.get("enabled") or (ml > 0 and lv < ml):
        html = _renderer().render_notice(
            "🔒 회원 전용 계기예요" if d.get("enabled") else "지금은 닫혀 있어요",
            f"레벨 {ml} 이상 이웃만 쓸 수 있어요 — 로그인했는지 확인해 주세요."
            if d.get("enabled") else "운영자가 진열을 켜면 다시 열립니다.",
            home=f"/h/{slug}/")
        return HTMLResponse(html, status_code=403, headers={"Cache-Control": "no-store"})

    inst = core.portal_instrument(iid)
    if not inst:
        raise HTTPException(status_code=404, detail="no such instrument")
    from api_launcher_web import get_launcher_webapp_html
    payload = {"exec": f"/h/{slug}/tool/{iid}", "instrument": inst, "home": f"/h/{slug}/"}
    inject = ("<script>window.__PORTAL="
              + json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
              + "</script>")
    html = get_launcher_webapp_html().replace("</head>", inject + "\n</head>", 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


# ── 회원 실행 게이트 ─────────────────────────────────────────────────────

@router.post("/tool/{slug}/{iid}")
async def tool_gate(slug: str, iid: str, request: Request,
                    x_showcase_secret: str = Header(default=""),
                    x_client_ip: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    code = str(body.get("code", ""))[:2000]
    if not code:
        raise HTTPException(status_code=400, detail="code required")
    ip = _client_ip(request, x_client_ip)
    member_key = request.cookies.get(f"pk_{slug}", "")

    # ① 계기 선언 템플릿 화이트리스트 — 범용 실행이 아니라 선언된 동작의 인스턴스만
    inst = core.portal_instrument(iid)
    if not inst:
        raise HTTPException(status_code=404, detail="no such instrument")
    allowed, reason = core.action_allowed(code, core.collect_templates(inst))
    if not allowed:
        core.audit_log(f"deny:{ip}", iid, code, False, note=reason, portal=slug)
        return JSONResponse({"error": reason}, status_code=403)

    # ② 신원·레벨·한도 (원자적 검사+카운트)
    try:
        auth = core.authorize_and_count(slug, iid, member_key, ip)
    except core.PortalDenied as e:
        core.audit_log(f"deny:{ip}", iid, code, False, note=e.msg, portal=slug)
        return JSONResponse({"error": e.msg}, status_code=e.status)

    # ③ 실행 — 앱 모드와 같은 경로(/ibl/execute 내부 재사용: 프로젝트 해소 + 단일 통화 정규화)
    try:
        from api_ibl import execute_ibl_code, IBLRequest
        # surface='web': 회원은 브라우저로 보고 있다 — 소리·저장이 맥이 아니라 회원 기기에서
        # 나야 한다(운영자 집에서 소리가 나면 안 된다). 게이트가 서버측에서 붙인다.
        result = await execute_ibl_code(IBLRequest(code=code, project_id="앱모드", surface="web"))
        # 유튜브뮤직 등 클라이언트 재생: googlevideo URL 은 맥 IP 에 잠겨 외부망 회원은 403.
        # 오디오 프록시(/h/<slug>/tune/<vid>)로 바꿔치기 — 맥이 집 IP 로 받아 중계한다.
        if (isinstance(result, dict) and result.get("play_in_client")
                and result.get("stream_url") and result.get("video_id")):
            _tune_cache_put(str(result["video_id"]), str(result["stream_url"]))
            result["stream_url"] = f"/h/{slug}/tune/{result['video_id']}"
        core.audit_log(auth.get("who", "?"), iid, code, True, portal=slug)
        return result
    except HTTPException as e:
        core.audit_log(auth.get("who", "?"), iid, code, False, note=str(e.detail)[:100], portal=slug)
        return JSONResponse({"error": "실행 중 문제가 생겼어요 — 잠시 후 다시 시도해 주세요"},
                            status_code=500)


# ── 오디오 프록시 (유튜브뮤직 외부망 재생) ────────────────────────────────
# googlevideo URL 은 해소한 쪽(맥) IP 에 잠긴다 — 회원이 집 밖(LTE)이면 직접 재생 403.
# 그래서 맥이 집 IP 로 받아 회원에게 중계한다(Range 통과 = 구간 탐색). 회원 쿠키 + ytmusic
# 다이얼 게이트 뒤 — 익명 공개면 유튜브 공개 프록시가 되므로 절대 열지 않는다.

_TUNE_CACHE: dict = {}          # video_id -> (googlevideo_url, expire_ts)
_TUNE_LOCK = threading.Lock()
_VID_RE = re.compile(r"^[A-Za-z0-9_-]{5,20}$")


def _tune_cache_put(vid: str, url: str) -> None:
    m = re.search(r"[?&]expire=(\d{10})", url)
    exp = int(m.group(1)) if m else time.time() + 3600
    with _TUNE_LOCK:
        _TUNE_CACHE[vid] = (url, min(exp, time.time() + 5 * 3600))
        if len(_TUNE_CACHE) > 200:
            now = time.time()
            for k in [k for k, (_, e) in _TUNE_CACHE.items() if e < now]:
                _TUNE_CACHE.pop(k, None)


def _tune_cache_get(vid: str):
    with _TUNE_LOCK:
        v = _TUNE_CACHE.get(vid)
    if v and v[1] > time.time() + 60:
        return v[0]
    return None


def _tune_resolve(vid: str) -> str:
    """video_id → 오디오 스트림 URL. m4a 우선(iOS 사파리는 webm/opus 미지원)."""
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                           "format": "bestaudio[ext=m4a]/bestaudio/best"}) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
        return info.get("url", "") or ""


@router.get("/tune/{slug}/{video_id}")
def tune(slug: str, video_id: str, request: Request,
         x_showcase_secret: str = Header(default=""),
         x_client_ip: str = Header(default="")):
    """오디오 스트림 중계 — 동기 def(스레드풀)라 이벤트 루프를 막지 않는다."""
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    if not _VID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="bad video id")

    # 회원 게이트: ytmusic 다이얼(켬 + 레벨) — 손님 불가(익명이면 공개 프록시가 됨)
    viewer = _viewer(core, portal, request, slug)
    universe = {u["key"]: u for u in core.listable_universe(state)}
    u = universe.get("ytmusic")
    d = core.display_entry(portal, u) if u else {}
    if not u or not d.get("enabled"):
        raise HTTPException(status_code=403, detail="닫혀 있는 계기입니다")
    if not viewer or int(viewer.get("level", 0)) < max(1, int(d.get("min_level", 1))):
        raise HTTPException(status_code=403, detail="회원 전용입니다")

    url = _tune_cache_get(video_id)
    if not url:
        # 캐시 미스 = ▶(카운트 완료) 경유가 아닌 수제/만료 요청 — 사용량으로 계산 후 해소
        member_key = request.cookies.get(f"pk_{slug}", "")
        ip = _client_ip(request, x_client_ip)
        try:
            core.authorize_and_count(slug, "ytmusic", member_key, ip)
        except core.PortalDenied as e:
            raise HTTPException(status_code=e.status, detail=e.msg)
        try:
            url = _tune_resolve(video_id)
        except Exception:
            url = ""
        if not url:
            raise HTTPException(status_code=502, detail="오디오를 가져오지 못했어요")
        _tune_cache_put(video_id, url)

    import requests as _rq
    fwd = {}
    rng = request.headers.get("range")
    if rng:
        fwd["Range"] = rng
    try:
        r = _rq.get(url, headers=fwd, stream=True, timeout=(10, 30))
        if r.status_code in (403, 410):     # URL 만료/IP 불일치 — 1회 재해소
            r.close()
            url = _tune_resolve(video_id)
            _tune_cache_put(video_id, url)
            r = _rq.get(url, headers=fwd, stream=True, timeout=(10, 30))
    except Exception:
        raise HTTPException(status_code=502, detail="스트림 연결 실패")
    if r.status_code not in (200, 206):
        r.close()
        raise HTTPException(status_code=502, detail="스트림 오류")
    headers = {k: r.headers[k] for k in ("Content-Type", "Content-Length", "Content-Range")
               if k in r.headers}
    headers.setdefault("Content-Type", "audio/mp4")
    headers["Accept-Ranges"] = "bytes"
    headers["Cache-Control"] = "no-store"
    return StreamingResponse(r.iter_content(65536), status_code=r.status_code, headers=headers)
