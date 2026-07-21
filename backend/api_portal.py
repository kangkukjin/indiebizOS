"""api_portal.py — 개인 포털(커뮤니티 홈) 공개 서빙 + 회원 실행 게이트.

공개 Worker(public-files 와 공유)가 /h/<slug>/... 요청을 이 엔드포인트로 끌어온다.
  · GET  /portal/page/{slug}            — 공개 홈 (쿠키의 회원키 → 레벨별 절단면)
  · GET  /portal/key/{slug}/{memberkey} — 개인 링크 착지: 장수 쿠키 심고 홈으로 리다이렉트
  · POST /portal/join/{slug}            — 가입 신청 (레벨 0 자동 등록 + 개인 링크 반환)
  · GET  /portal/inst/{slug}/{iid}      — 계기 페이지 (런처 제네릭 렌더러 재사용 — __PORTAL 주입)
  · POST /portal/tool/{slug}/{iid}      — ★회원 실행 게이트: 쿠키→레벨→다이얼→한도→
                                          app: 선언 템플릿 화이트리스트→실행→감사로그
보안: X-Showcase-Secret(Worker 만 보유) + slug 일치. 개인화 응답이라 Worker 는 no-store.
상태·게이트 로직은 community-portal 패키지 portal_core.py 단일 소스(★수정 시 백엔드 재시작).
"""

import os
import re
import json
import time
import threading
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

router = APIRouter(prefix="/portal", tags=["portal"])

_ROOT = Path(__file__).resolve().parent.parent
_PKG = _ROOT / "data" / "packages" / "installed" / "tools" / "community-portal"

_COOKIE_MAX_AGE = 365 * 24 * 3600


def _read_env(name: str) -> str:
    v = os.environ.get(name, "")
    if v:
        return v
    envp = _ROOT / ".env"
    if envp.exists():
        try:
            for line in envp.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return ""


def _check_secret(secret_header: str) -> None:
    secret = _read_env("SHOWCASE_ORIGIN_SECRET")
    if not secret or secret_header != secret:
        raise HTTPException(status_code=403, detail="forbidden")


def _core():
    """portal_core 공유 인스턴스 (handler 와 같은 sys.modules 키 — 프로세스당 1개)."""
    import sys
    import importlib.util
    name = "indiebiz_portal_core"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, str(_PKG / "portal_core.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


_HTML = None


def _renderer():
    """홈 HTML 렌더러(패키지 portal_html.py) — 디자인 단일 소스."""
    global _HTML
    if _HTML is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_portal_html_api", str(_PKG / "portal_html.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _HTML = mod
    return _HTML


def _portal_or_404(core, state: dict, slug: str) -> dict:
    p = core.portal_by_slug(state, slug)
    if not p:
        raise HTTPException(status_code=404, detail="no such portal")
    return p


def _viewer(core, portal: dict, request: Request, slug: str):
    key = request.cookies.get(f"pk_{slug}", "")
    return core.find_member(portal, key=key) if key else None


def _client_ip(request: Request, x_client_ip: str) -> str:
    return x_client_ip or (request.client.host if request.client else "")


def _set_session(resp, slug: str, key: str, persistent: bool = True):
    """로그인 쿠키 — persistent(자동 로그인)면 1년, 아니면 브라우저 세션."""
    kw = {"max_age": _COOKIE_MAX_AGE} if persistent else {}
    resp.set_cookie(key=f"pk_{slug}", value=key, path=f"/h/{slug}",
                    httponly=True, samesite="lax", secure=True, **kw)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── 공개 홈 (포털별 절단면) ──────────────────────────────────────────────

@router.get("/page/{slug}")
async def page(slug: str, request: Request, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    viewer = _viewer(core, portal, request, slug)
    tiles = core.visible_tiles(state, portal, viewer.get("level") if viewer else None)
    html = _renderer().render_home(portal, viewer, tiles)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


# ── 노드의 공개 얼굴 = 레벨 창고(전용 폴더 0~4 + 로그인/레벨) ────────────────
# 설계(FOAF 창고): 레벨0~4 마다 '전용 폴더'가 따로 있다 — 기존 공개파일(사진 바스켓)과 무관.
#   · 기본 내용물 = 그 레벨의 비즈니스 문서(business_documents, 레벨별)가 자동 물질화(.md)
#   · 사용자는 Finder 로 그 폴더에 뭐든 던져넣는다(형식 자유 창고 — schema-on-read)
#   · 익명=레벨0 창고만, 로그인(단일 노드 쿠키 pk)=자기 레벨 이하 전부. 위 레벨은 has_restricted
#     냄새로만(이름·개수 안 샘). 서빙은 즉석 walk(공개파일 '구조' 재사용 — 인덱싱 없음).
# 주소: 노드는 하나, canonical `/manifest`. 창고는 `/w/<level>/`(레벨 자체가 주소 — 슬러그 없음).

_MANIFEST_ABOUT = ("이 노드가 공유하는 파일 목록(요청자 레벨로 절단). url 로 내용을 가져간다. "
                   "운영자가 이웃으로 승급하면 더 많은 파일이 열린다. has_restricted=잠긴 것 "
                   "존재(내용은 안 샘 = FOAF 라우팅 단서). 회원이면 login 계약대로 로그인해 "
                   "쿠키를 받으면 같은 주소들이 더 열린다. name 은 창고 안 상대경로라 "
                   "'폴더/파일' 로 폴더 구조가 실린다. truncated=true 면 목록이 상한에서 "
                   "잘린 것(total=실제 개수) — 빠진 이름을 '삭제'로 해석하면 안 된다. "
                   "rt 필드가 있으면 리트윗(남의 창고에서 소개해 온 것): origin=최초 제공 창고, "
                   "origin_url=최초 파일, hops=리트윗 횟수. link=true 는 포인터(url=원 창고 직행), "
                   "link 없는 rt 항목은 이 창고가 사본을 직접 서빙한다.")

_WAREHOUSE_ROOT = _ROOT / "공유창고"
_WAREHOUSE_LEVELS = {0: "0", 1: "1", 2: "2", 3: "3", 4: "4"}
_WAREHOUSE_CONFIG = _ROOT / "data" / "warehouse.json"   # {title} — 미추적(실명 등 PII는 코드 밖)


def _warehouse_title() -> str:
    try:
        return (json.loads(_WAREHOUSE_CONFIG.read_text(encoding="utf-8")).get("title")
                or "공유창고")
    except Exception:
        return "공유창고"
_BIZDOC_NAME = "비즈니스문서.md"
_NODE_NPUB = None   # 프로세스 캐시 — IndieNetIdentity 로드가 매 요청 로그를 찍지 않게


def _node_npub() -> str:
    """노드의 Nostr 주소. 시스템 AI 의 nostr 서명·수신 신원 = indienet 신원(channel_engine 공유)
    이므로 이 npub 이 곧 'AI 에게 닿는 연락처'다."""
    global _NODE_NPUB
    if _NODE_NPUB is None:
        try:
            from indienet import IndieNetIdentity
            idn = IndieNetIdentity()
            _NODE_NPUB = (idn.npub or "") if idn.load_or_create() else ""
        except Exception:
            _NODE_NPUB = ""
    return _NODE_NPUB


def _contact_block() -> str:
    """비즈니스문서 꼬리의 연락처 절. npub=자동(신원 의무), 이메일=warehouse.json 에
    사용자가 선택적으로 넣은 것만(email 키 — 미추적 파일이라 PII 가 repo 밖에 머문다)."""
    lines = []
    npub = _node_npub()
    if npub:
        lines.append(f"- Nostr (DM): {npub}")
    try:
        email = (json.loads(_WAREHOUSE_CONFIG.read_text(encoding="utf-8")).get("email") or "").strip()
    except Exception:
        email = ""
    if email:
        lines.append(f"- 이메일: {email}")
    return ("\n## 연락처\n\n" + "\n".join(lines) + "\n") if lines else ""
# 창고 전체(레벨 0..요청자, 하위폴더 재귀) 목록 상한 — 응답 폭주 방지용 러너웨이 가드.
# ★옛 값 500 은 "한 디렉토리 목록" 상한이었다(디렉토리 단위 브라우징 시절). 뷰가 평면화되면서
#   같은 상수가 창고 전체에 걸리게 범위가 넓어졌으므로 재산정. 절단 시 매니페스트가
#   truncated 로 반드시 신고한다 — 조용히 자르면 이웃 폴러가 "삭제"로 오독한다.
_WAREHOUSE_LIST_CAP = 5000
_WAREHOUSE_OPEN_MAX = 50           # 이하면 홈에서 최상위 폴더를 펼쳐 둔다(그 이상은 접힘)


def _warehouse_dir(level: int) -> Path:
    return _WAREHOUSE_ROOT / _WAREHOUSE_LEVELS[level]


def _ensure_warehouses() -> None:
    """창고 폴더 0~4 생성 + 레벨별 비즈니스 문서 물질화(DB 가 바뀌면 파일 갱신 — 볼 때 렌더).

    정기 산출물(보고서·신문·블로그)은 여기서 만들지 않는다 — 그건 IBL 파이프의 일이다:
    `[self:read] >> [table:document]{format:html} >> [self:copy]{destination: 공유창고/<레벨>/…}`
    (창고에 놓기 = self:copy. 전용 기계를 두면 파이프가 쓴 파일을 덮어써 서로 싸운다.)
    """
    try:
        import business_manager
        bm = business_manager.BusinessManager()
    except Exception:
        bm = None
    for lv, name in _WAREHOUSE_LEVELS.items():
        d = _WAREHOUSE_ROOT / name
        d.mkdir(parents=True, exist_ok=True)
        if bm is None:
            continue
        try:
            doc = bm.get_business_document(lv)
            content = ((doc or {}).get("content") or "").strip()
            contact = _contact_block()
            # 내용이 없어도 연락처가 있으면 쓴다 — 문서의 최소 의무=신원(연락 방법).
            if content or contact:
                title = (doc or {}).get("title") or "비즈니스 문서"
                body = f"# {title}\n\n{content}\n" if content else f"# {title}\n"
                body += contact
                f = d / _BIZDOC_NAME
                if not f.exists() or f.read_text(encoding="utf-8") != body:
                    f.write_text(body, encoding="utf-8")
        except Exception:
            pass
    # 아이템 물질화 — 가레지세일 진열: 아이템마다 문서(+사진)를 <레벨>/<비즈니스 이름>/ 에.
    # 파생 구역 경계·청소는 warehouse_items 사이드카가 책임진다(사용자 파일 불가침).
    if bm is not None:
        try:
            import warehouse_items
            warehouse_items.sync(bm, {lv: _WAREHOUSE_ROOT / name
                                      for lv, name in _WAREHOUSE_LEVELS.items()})
        except Exception:
            pass


def _viewer_level(core, request: Request):
    """단일 노드 쿠키(pk) → (viewer, level). 익명이면 (None, 0)."""
    key = request.cookies.get("pk", "")
    viewer = core.find_member(None, key=key) if key else None
    return viewer, (int(viewer.get("level", 0)) if viewer else 0)


def _parse_urlfile(p) -> tuple:
    """.url(InternetShortcut) 파일에서 (대상, 출처 창고) 추출.
    출처 창고(WarehouseURL)는 표준 밖 확장 키라 없을 수도 있다(옛 리트윗 파일).
    대상 추출 실패면 ("", "") — 일반 파일로 서빙한다."""
    target, warehouse = "", ""
    try:
        for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
            line = line.strip()
            up = line.upper()
            if up.startswith("URL="):
                t = line[4:].strip()
                if t.startswith("http://") or t.startswith("https://"):
                    target = t
            elif up.startswith("WAREHOUSEURL="):
                w = line[len("WarehouseURL="):].strip()
                if w.startswith("http://") or w.startswith("https://"):
                    warehouse = w
    except Exception:
        pass
    return (target, warehouse) if target else ("", "")


def _walk_accessible(level: int, base: str = "") -> tuple:
    """(상한까지 자른 목록, 자르기 전 총 개수) — 절단 여부를 호출자가 알 수 있게 총계도 준다.

    레벨 0..level 창고를 병합 — 방문자에게 레벨 구조를 흘리지 않는다. 같은 상대경로는 높은
    레벨 판이 이김 → 비즈니스문서.md 가 자동으로 딱 1개(내 레벨 판).

    폴더는 항목이 되지 않고 그 안의 파일만 나온다. 폴더 구조는 name 의 상대경로로 보존
    ("매매/망의 시대.txt") — 레벨 병합만 평면이고, 사용자가 만든 폴더 의미는 살아남는다.
    """
    from urllib.parse import quote
    seen = {}
    for lv in sorted((l for l in _WAREHOUSE_LEVELS if l <= level), reverse=True):
        d = _warehouse_dir(lv)
        try:
            for p in d.rglob("*"):
                if not p.is_file() or p.name.startswith("."):
                    continue
                rel = str(p.relative_to(d))
                if rel not in seen:
                    st = p.stat()
                    entry = {"name": rel, "bytes": st.st_size,
                             "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                             "url": f"{base}/f?path={quote(rel)}"}
                    # 리트윗 링크 파일(.url, InternetShortcut) — target 을 해석해 url 로 노출:
                    # 방문자·구독자 클릭이 곧장 원 창고의 원 파일로 간다(포인터=파일인 FOAF 발견).
                    if rel.lower().endswith(".url") and st.st_size <= 4096:
                        target, warehouse = _parse_urlfile(p)
                        if target:
                            entry["url"] = target
                            entry["link"] = True
                            # 출처 창고 = 다음 이웃 후보. 파일이 사라져도 이 주소는 남는다.
                            if warehouse:
                                entry["warehouse"] = warehouse
                    # 리트윗 사이드카(.<파일명>.rt.json, dotfile 이라 목록엔 안 나옴) —
                    # 출처 사슬(최초 제공 창고·파일, 리트윗 횟수)을 rt 필드로 노출.
                    # 이웃 폴러·AI 가 사본을 최초 출처로 거슬러 가고, 같은 origin 사본을 묶는다.
                    sc = p.parent / f".{p.name}.rt.json"
                    if sc.exists():
                        try:
                            rt = json.loads(sc.read_text(encoding="utf-8"))
                            entry["rt"] = {"origin": rt.get("origin_warehouse") or "",
                                           "origin_url": rt.get("origin_url") or "",
                                           "origin_name": rt.get("origin_name") or "",
                                           "hops": int(rt.get("hops") or 1)}
                        except Exception:
                            pass
                    seen[rel] = entry
        except Exception:
            continue
    # 비즈니스문서(노드 소개)가 맨 앞, 나머지는 이름순
    files = sorted(seen.values(), key=lambda f: (f["name"] != _BIZDOC_NAME, f["name"]))
    return files[:_WAREHOUSE_LIST_CAP], len(files)


def _accessible_files(level: int, base: str = "") -> list:
    """_walk_accessible 의 목록만 — 총계가 필요 없는 호출자용."""
    return _walk_accessible(level, base)[0]


def _file_tree(files: list) -> dict:
    """평면 목록의 상대경로("매매/망의 시대.txt")를 폴더 트리로 되접는다. 임의 깊이.
    각 파일은 (원본 entry, 표시용 파일명) 쌍으로 담긴다 — 표시는 짧게, 키는 전체 경로."""
    root = {"dirs": {}, "files": []}
    for f in files:
        parts = f["name"].split("/")
        node = root
        for seg in parts[:-1]:
            node = node["dirs"].setdefault(seg, {"dirs": {}, "files": []})
        node["files"].append((f, parts[-1]))
    return root


def _tree_agg(node: dict) -> tuple:
    """(하위 전체 파일 수, 바이트 합) — 폴더 요약에 쓴다."""
    cnt = len(node["files"])
    size = sum(f.get("bytes") or 0 for f, _ in node["files"])
    for sub in node["dirs"].values():
        c2, s2 = _tree_agg(sub)
        cnt += c2
        size += s2
    return cnt, size


def _manifest_payload(node_title: str, base: str, level: int, is_member: bool) -> dict:
    _ensure_warehouses()
    files, total = _walk_accessible(level, base)
    # 좋아요 카운트 — 파일 항목에 likes 필드(0 이면 생략). 이웃 폴러가 피드에 하트를 싣는다.
    import warehouse_likes
    warehouse_likes.annotate(files)
    # 이사 공지 — 프로바이더 교체 등으로 공개 주소가 바뀌면(public_face.moved_to) 매니페스트에
    # 실어, 옛 주소를 폴링하는 이웃의 폴러가 등기부를 자동 치유하게 한다(우체국 주소이전).
    # 옛 주소가 살아 있는 동안만 전파되므로, 전환기엔 두 프로바이더를 함께 켜 둔다.
    moved_to = ""
    try:
        import public_face
        moved_to = public_face.get_moved_to()
    except Exception:
        pass
    payload_extra = {"moved_to": moved_to} if moved_to else {}
    return {
        **payload_extra,
        "about": _MANIFEST_ABOUT,
        "title": node_title,
        # 신원의 닻 — 주소(창고 url)는 프로바이더 전환으로 바뀔 수 있지만 키(npub)는
        # 그 사람이다. 이웃 폴러가 이걸 읽어 등기부 신원을 치유한다(같은 사람 2명 방지).
        "npub": _node_npub(),
        "node_url": (base + "/manifest") if base else "/manifest",
        "viewer_level": level,
        "is_member": is_member,
        # 로그인·가입 계약(기계 판독) — 외부 AI가 홈 HTML 을 역공학하지 않아도 되게 여기 명시.
        "login": {"url": (base + "/login") if base else "/login", "method": "POST",
                  "content_type": "application/json",
                  "body": {"user_id": "<아이디>", "password": "<비밀번호>"},
                  "note": "성공 시 쿠키(pk)가 실리고 이후 /manifest·파일 url 이 내 레벨로 열린다."},
        "join": {"url": (base + "/join") if base else "/join", "method": "POST",
                 "content_type": "application/json",
                 "body": {"name": "<이름>", "user_id": "<아이디>", "password": "<비밀번호>",
                          "email": "<복구용 이메일>"},
                 "note": "가입=레벨 0 등록+즉시 로그인(쿠키 pk). 높은 레벨은 창고 주인이 준다."},
        "files": files,
        # 절단 신고 — 이게 없으면 폴러가 밀려난 파일을 "삭제"로 오독한다(조용한 유실).
        "truncated": total > len(files),
        "total": total,
        "has_restricted": level < max(_WAREHOUSE_LEVELS),
    }


# ── 창고 홈 (사람용) — 사이트 맨 루트(/)가 이 페이지다. 가장 짧은 주소 = 노드의 얼굴. ──
# 옛 bare-루트 잠금은 showcase(주소=비밀) 시절 규칙 — 창고는 보안이 레벨이라 루트를 당당히 연다.

def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.0f}B"


@router.get("/home")
async def node_home(request: Request, x_showcase_secret: str = Header(default="")):
    """창고 홈(사람용 HTML) — 내 레벨 이하 창고의 파일들 + 로그인. 루트(/)에서 서빙."""
    import html as _h
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = core.ensure_default_portal(state)
    viewer, level = _viewer_level(core, request)
    _ensure_warehouses()

    title = _h.escape(_warehouse_title())
    # 단일 목록 — 방문자에게 레벨 구조(어느 파일이 어느 등급인지)를 보여주지 않는다.
    # 비즈니스문서는 내 레벨 판 1개만(높은 레벨 판이 이기는 병합 규칙이 자동으로 보장).
    # ★평면인 건 '레벨'뿐이다. 사용자가 만든 폴더는 name 의 상대경로에 살아 있으므로
    #   여기서 접이식 트리로 되살린다(레벨 은닉과 폴더 은닉은 서로 다른 문제).
    files, total = _walk_accessible(level)
    # 좋아요 카운트 — 파일 옆 ♥N (누르면 토글, 회원=계정·손님=IP 단위)
    import warehouse_likes
    lk_counts = warehouse_likes.count_map()
    # 방명록도 같은 절단면으로 — 상위 레벨 파일에 달린 글은 여기서 이미 빠져 있다.
    gb = _gb_for_level(level)
    gb_counts: dict = {}
    for _e in gb:
        if _e.get("about"):
            gb_counts[_e["about"]] = gb_counts.get(_e["about"], 0) + 1

    # 이름 = 열기(브라우저가 표시·재생), ⬇ = 내려받기(원본 바이트). 해석은 가져간 쪽 몫.
    # label = 화면에 보일 이름(폴더 안에선 파일명만). f["name"] 은 창고 기준 전체 상대경로라
    # 방명록 인용 키로는 그쪽을 쓴다 — 표시만 짧아지고 기록의 키는 안 흔들린다.
    def _row(f, label=None):
        u = _h.escape(f["url"])
        sep = "&" if "?" in f["url"] else "?"
        # 소개한 파일(링크)이면 그 파일이 사는 창고로 건너뛰는 문 하나 — 발견이 한 홉 더 간다
        wh = f.get("warehouse")
        wh_link = (f'<a class="dl" href="{_h.escape(wh)}/" title="이 파일이 있는 창고 열기">📦</a>'
                   if wh else '')
        # 이 파일에서 방명록 글 시작 — 경로는 폼에 인용으로 실린다(레코드의 키가 아니라 기록).
        n = gb_counts.get(f["name"], 0)
        gb_link = (f'<a class="dl gb" href="#gb" data-p="{_h.escape(f["name"])}" '
                   f'onclick="return ab(this)" title="이 파일에 글 남기기">💬{n or ""}</a>')
        nl = lk_counts.get(f["name"], 0)
        lk_link = (f'<a class="dl lk" href="#" data-p="{_h.escape(f["name"])}" '
                   f'onclick="return lk(this)" title="좋아요">♥<span>{nl or ""}</span></a>')
        return (f'<li><a href="{u}">{_h.escape(label if label is not None else f["name"])}</a>'
                f'<span class="sz">{_fmt_bytes(f["bytes"])}</span>{wh_link}{lk_link}{gb_link}'
                f'<a class="dl" href="{u}{sep}download=1" download '
                f'title="내려받기">⬇</a></li>')

    # 파일 먼저, 폴더 나중 — 비즈니스문서(노드의 얼굴)가 맨 위에 남게 하는 정렬을 존중한다.
    def _render(node, top=False):
        out = []
        lis = "".join(_row(f, label) for f, label in node["files"])
        if lis:
            out.append(f'<ul>{lis}</ul>')
        for name in sorted(node["dirs"]):
            sub = node["dirs"][name]
            cnt, size = _tree_agg(sub)
            # 작은 창고는 펼쳐 두고(방문자가 바로 봄), 커지면 접는다(뒤죽박죽 방지).
            op = " open" if (top and total <= _WAREHOUSE_OPEN_MAX) else ""
            out.append(f'<details class="fd"{op}><summary>📁 {_h.escape(name)}'
                       f'<span class="sz">{cnt}개 · {_fmt_bytes(size)}</span></summary>'
                       f'{_render(sub)}</details>')
        return "".join(out)

    body = _render(_file_tree(files), top=True) or '<ul><li class="empty">비어 있어요</li></ul>'
    trunc_note = (f'<p class="locked">목록이 {_WAREHOUSE_LIST_CAP}개에서 잘렸어요 '
                  f'(전체 {total}개).</p>' if total > len(files) else '')
    sections = [f'<section>{body}{trunc_note}</section>']

    # ── 방명록 ── 인용(about)은 세 상태로 정직하게 표시: 현재 판 / 이전 판 / 없는 파일.
    from urllib.parse import quote as _q
    def _gb_row(e):
        who = _h.escape(e["name"])
        tag = (f'<span class="mb">레벨 {e["level"]}</span>' if e["member"]
               else '<span class="gs">손님</span>')
        st, ab = e.get("about_state", ""), e.get("about", "")
        if not ab:
            q = ''
        elif st == "current":
            q = f'<div class="q"><a href="/f?path={_q(ab)}">{_h.escape(ab)}</a></div>'
        elif st == "old":
            q = f'<div class="q stale">{_h.escape(ab)} · 이전 판에 대한 글</div>'
        else:
            q = f'<div class="q stale">{_h.escape(ab)} · 지금은 없는 파일</div>'
        return (f'<li>{q}<div class="gm">{_h.escape(e["msg"])}</div>'
                f'<div class="gw">{who} {tag} · {_h.escape(e["at"])}</div></li>')
    gb_rows = "".join(_gb_row(e) for e in reversed(gb)) or '<li class="empty">아직 글이 없어요</li>'
    gb_ph = '손님으로 글을 남깁니다' if not viewer else '글을 남깁니다'
    sections.append(
        f'<h2 id="gb">방명록</h2><section>'
        f'<form onsubmit="gp(this);return false">'
        f'<input name="website" class="hp" tabindex="-1" autocomplete="off" aria-hidden="true">'
        f'<div id="abt" class="abt"></div>'
        f'<textarea name="msg" rows="2" placeholder="{gb_ph}"></textarea>'
        f'<button>남기기</button></form>'
        f'<ul class="gbl">{gb_rows}</ul></section>')
    locked_note = ('<p class="locked">🔒 더 높은 레벨의 창고가 있어요 — 로그인하거나 승급하면 열립니다.</p>'
                   if level < max(_WAREHOUSE_LEVELS) else '')
    if viewer:
        who = (f'<span>{_h.escape(viewer.get("name",""))} · 레벨 {level}</span> '
               f'<button onclick="lo()">로그아웃</button>')
        login_form = ''
        join_box = ''
    else:
        who = '<span>손님 (레벨 0)</span>'
        login_form = ('<form onsubmit="li(this);return false"><input name="u" placeholder="아이디" '
                      'autocomplete="username"><input name="p" type="password" placeholder="비밀번호" '
                      'autocomplete="current-password"><button>로그인</button></form>'
                      '<button type="button" class="jt" onclick="jf()">가입</button>')
        # 가입 = 아이디·비밀번호를 스스로 만들고 이메일(비밀번호 찾기용)을 남긴다.
        # 레벨 0 자동 등록 + 즉시 로그인 — 높은 레벨은 창고 주인이 이웃 레벨로 준다.
        join_box = ('<section id="joinbox" class="joinbox" style="display:none">'
                    '<h2>창고 가입</h2>'
                    '<form onsubmit="jn(this);return false">'
                    '<input name="n" placeholder="이름" autocomplete="name">'
                    '<input name="u" placeholder="아이디 (영문 소문자·숫자 3~20자)" autocomplete="username">'
                    '<input name="p" type="password" placeholder="비밀번호" autocomplete="new-password">'
                    '<input name="e" type="email" placeholder="이메일 (비밀번호 찾기용)" autocomplete="email">'
                    '<button>가입하기</button></form>'
                    '<p class="jn-note">가입하면 레벨 0 회원으로 바로 로그인됩니다 — '
                    '더 높은 레벨은 창고 주인이 열어줍니다.</p></section>')
    html_doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{title}</title><link rel="alternate" type="application/json" href="/manifest">
<style>
/* 배경을 명시하지 않으면 다크모드 방문자에겐 UA 검은 배경 위에 color:#222 라 글이 안 보인다 */
body{{font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;max-width:680px;margin:2rem auto;padding:0 1rem;color:#222;background:#fff}}
header{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem;border-bottom:2px solid #222;padding-bottom:.7rem}}
h1{{font-size:1.4rem;margin:0}} h2{{font-size:1rem;margin:1.2rem 0 .4rem;color:#555}}
ul{{list-style:none;padding:0;margin:0}} li{{padding:.45rem .2rem;border-bottom:1px solid #eee;display:flex;align-items:center;gap:1rem}}
li>a:first-child{{flex:1;min-width:0}}
a{{color:#0a58ca;text-decoration:none;word-break:break-all}} a:hover{{text-decoration:underline}}
.sz{{color:#999;font-size:.85rem;white-space:nowrap}} .empty{{color:#aaa}} .locked{{color:#888;font-size:.9rem}}
/* 폴더 = 접이식. 안쪽은 들여쓰기로 계층을 보이되 세로선 하나로 가볍게. */
.fd{{border-bottom:1px solid #eee}}
.fd>summary{{padding:.45rem .2rem;cursor:pointer;display:flex;align-items:center;gap:1rem;list-style:none}}
.fd>summary::-webkit-details-marker{{display:none}}
.fd>summary::before{{content:"▸";color:#999;font-size:.8rem;flex-shrink:0}}
.fd[open]>summary::before{{content:"▾"}}
.fd>summary>.sz{{margin-left:auto}}
.fd>ul,.fd>.fd{{margin-left:1rem;border-left:1px solid #eee;padding-left:.6rem}}
.fd>.fd{{border-bottom:none}} .fd>ul>li:last-child{{border-bottom:none}}
.dl{{color:#555;text-decoration:none;font-size:1.05rem;padding:0 .2rem;flex-shrink:0}} .dl:hover{{color:#0a58ca;text-decoration:none}}
form{{display:flex;gap:.4rem;flex-wrap:wrap}} input{{padding:.35rem .5rem;border:1px solid #ccc;border-radius:6px;width:8.5rem}}
button{{padding:.35rem .8rem;border:1px solid #222;background:#222;color:#fff;border-radius:6px;cursor:pointer}}
.acct{{display:flex;align-items:center;gap:.6rem;font-size:.9rem;color:#555}}
.hp{{position:absolute;left:-9999px;width:1px;height:1px}}
textarea{{width:100%;padding:.45rem .55rem;border:1px solid #ccc;border-radius:6px;font:inherit;resize:vertical;box-sizing:border-box}}
form textarea+button{{margin-top:.4rem}}
.abt{{font-size:.85rem;color:#555;margin-bottom:.3rem}} .abt b{{color:#222}}
.abt button{{background:none;border:none;color:#999;padding:0 .3rem;cursor:pointer;font-size:.9rem}}
.gbl li{{display:block;padding:.6rem .2rem}}
.gm{{white-space:pre-wrap;word-break:break-word}}
.gw{{color:#888;font-size:.82rem;margin-top:.25rem}}
.mb{{background:#222;color:#fff;border-radius:4px;padding:0 .3rem;font-size:.75rem}}
.gs{{color:#aaa;font-size:.78rem;border:1px solid #ddd;border-radius:4px;padding:0 .3rem}}
.q{{font-size:.85rem;color:#555;border-left:3px solid #ddd;padding-left:.5rem;margin-bottom:.3rem}}
.q.stale{{color:#aaa;font-style:italic}}
.jt{{background:none;color:#0a58ca;border:1px solid #0a58ca}}
.joinbox{{border:1px solid #ddd;border-radius:10px;padding: .8rem 1rem;margin-top:1rem}}
.joinbox h2{{margin:.1rem 0 .6rem}}
.joinbox input{{width:14rem;max-width:100%}}
.jn-note{{color:#888;font-size:.85rem;margin:.5rem 0 0}}
</style></head><body>
<header><h1>{title}</h1><div class="acct">{who}{login_form}</div></header>
{join_box}
{''.join(sections)}
{locked_note}
<script>
// ★폼 핸들러 계약: 인라인 onsubmit 은 "fn(this);return false" — async 함수의 return false 는
//   Promise 라 기본 제출을 못 막고, 기본 GET 제출이 fetch 와 경주해 로그인/글이 조용히
//   유실되고 비밀번호가 URL 에 노출된다(실측: POST 와 GET /?u=&p= 동시 발생).
async function li(f){{const r=await fetch('/login',{{method:'POST',headers:{{'Content-Type':'application/json'}},
body:JSON.stringify({{user_id:f.u.value,password:f.p.value,auto:true}})}});
if(r.ok)location.reload();else alert((await r.json()).detail||'로그인 실패');return false}}
async function lo(){{await fetch('/logout',{{method:'POST'}});location.reload()}}
// 가입 폼 토글 + 제출 — 성공하면 쿠키(pk)가 실린 채 새로고침(즉시 로그인).
function jf(){{const b=document.getElementById('joinbox');
b.style.display=b.style.display==='none'?'':'none';
if(b.style.display!=='none')b.querySelector('input').focus()}}
async function jn(f){{
const r=await fetch('/join',{{method:'POST',headers:{{'Content-Type':'application/json'}},
body:JSON.stringify({{name:f.n.value,user_id:f.u.value,password:f.p.value,email:f.e.value,auto:true}})}});
// /join 라우트가 없는 옛 Worker 는 SPA 폴백을 200 으로 줄 수 있다 — json ok 까지 확인(침묵 실패 방지).
let j=null; try{{j=await r.json()}}catch(e){{}}
if(r.ok&&j&&j.ok){{location.reload()}}
else{{alert((j&&j.detail)||'가입하지 못했어요 — 잠시 후 다시 시도해 주세요')}}
return false}}
// 파일 옆 ♥ → 좋아요 토글(회원=계정, 손님=IP 단위). 새로고침 없이 숫자만 갱신.
async function lk(a){{
const r=await fetch('/like',{{method:'POST',headers:{{'Content-Type':'application/json'}},
body:JSON.stringify({{path:a.dataset.p}})}});
let j=null; try{{j=await r.json()}}catch(e){{}}
if(r.ok&&j&&j.ok){{a.querySelector('span').textContent=j.count||'';a.style.color=j.liked?'#d63384':''}}
else{{alert((j&&j.detail)||'좋아요를 남기지 못했어요')}}
return false}}
// 파일 옆 💬 → 그 경로를 인용으로 달고 방명록 폼으로. 인용은 글의 키가 아니라 기록이라
// 지우고 일반 글로 남겨도 된다.
var AB='';
function ab(a){{AB=a.dataset.p;
document.getElementById('abt').innerHTML='<b>'+AB.replace(/</g,'&lt;')+'</b>에 대해 '+
'<button type="button" onclick="ax()" title="인용 빼기">✕</button>';
document.querySelector('textarea').focus();return false}}
function ax(){{AB='';document.getElementById('abt').innerHTML=''}}
async function gp(f){{
const m=f.msg.value.trim(); if(!m)return false;
const r=await fetch('/gb',{{method:'POST',headers:{{'Content-Type':'application/json'}},
body:JSON.stringify({{msg:m,about:AB,website:f.website.value}})}});
// 상태코드만 믿지 않는다 — /gb 라우트가 없는 Worker 는 SPA 폴백을 200 으로 준다.
// 그때 성공으로 오판하면 새로고침되며 글이 조용히 사라진다(침묵 유실 > 정직한 실패).
let j=null; try{{j=await r.json()}}catch(e){{}}
if(r.ok&&j&&j.ok){{location.reload()}}
else{{alert((j&&j.detail)||'남기지 못했어요 — 잠시 후 다시 시도해 주세요')}}
return false}}
</script></body></html>"""
    return HTMLResponse(html_doc, headers={"Cache-Control": "no-store"})


@router.get("/manifest")
async def node_manifest(request: Request, x_showcase_secret: str = Header(default="")):
    """노드의 공개 얼굴 — 슬러그 없는 canonical 창고 목록. 익명=레벨0, 쿠키(pk)=회원 레벨."""
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = core.ensure_default_portal(state)
    viewer, level = _viewer_level(core, request)
    base = (state.get("public_base") or "").rstrip("/")
    return JSONResponse(_manifest_payload(_warehouse_title(), base, level, bool(viewer)),
                        headers={"Cache-Control": "no-store"})


# ── 창고 파일 서빙 — /f?path= 단일 관문. 레벨 게이트가 서빙 자체에 걸린다. ────
# 주소에 레벨이 안 드러난다(어느 파일이 어느 등급인지 = 정보라서 숨김). 서버가 방문자 레벨
# 이하 창고를 높은 레벨부터 뒤져 첫 일치를 서빙. 레벨 밖 파일은 403 이 아니라 404(존재 자체
# 를 안 흘림). 공개파일(/s/)과 달리 주소를 알아도 레벨이 안 되면 열리지 않는다.

def _safe_rel(base: Path, rel: str) -> Path:
    p = (base / rel.lstrip("/")).resolve()
    if not str(p).startswith(str(base.resolve()) + os.sep) and p != base.resolve():
        raise HTTPException(status_code=400, detail="bad path")
    return p


_WH_MEDIA_CACHE = _ROOT / "data" / "warehouse_media_web"   # 동영상 트랜스코드 캐시


def _download_headers(name: str) -> dict:
    """Content-Disposition: attachment — 한글 파일명은 RFC 5987(filename*)로.

    ASCII 폴백은 구형 클라이언트용. 한글만 있는 이름은 ASCII 로 죽으니(예 '비즈니스문서.md'
    → '.md') 확장자는 살리고 몸통은 'file' 로 세운다. 요즘 브라우저는 filename* 를 쓴다."""
    from urllib.parse import quote
    stem, dot, ext = name.rpartition(".")
    a_stem = (stem if dot else name).encode("ascii", "ignore").decode().strip(" .") or "file"
    a_ext = ext.encode("ascii", "ignore").decode().strip() if dot else ""
    ascii_fb = f"{a_stem}.{a_ext}" if a_ext else a_stem
    return {"Content-Disposition":
            f'attachment; filename="{ascii_fb}"; filename*=UTF-8\'\'{quote(name)}'}


def _serve_warehouse_file(abspath: Path, strip_exif: bool, download: bool = False):
    """창고 파일 서빙 — showcase 와 같은 thumbnails 모듈 재사용.

    ① 사진 + strip_exif → EXIF/GPS 벗긴 JPEG (공개면 전용. 창고는 '뭐든 던져넣기'라
       촬영 위치가 딸려 나가기 쉽다 — 경계는 또렷해야 한다). 다운로드에도 적용 —
       받아가는 경로로 GPS 가 새면 열람만 막은 게 무의미하다.
    ② 동영상 + 브라우저 비재생 코덱(HEVC 등) → H.264 MP4 로 변환해 캐시.
       코덱 판정이라 `.mp4` 껍데기 안의 HEVC 도 잡는다. 소유자 열람에도 적용 — 안 그러면
       원격 런처에서 아이폰 영상이 그냥 안 열린다.
       ★단 download 면 변환하지 않는다 — 받는 사람이 원하는 건 *원본*이지 재생용 사본이
       아니고, 변환은 손실이다(브라우저 재생 제약은 다운로드엔 해당 없음).
    ③ 그 외 → FileResponse 가 Content-Type + Range(206) 자동 처리 = 브라우저가 사진 표시·
       동영상 재생·텍스트 열람. download 면 Content-Disposition 으로 저장 강제.

    ★파일을 *읽어* 텍스트로 바꿔주지는 않는다(pdf/docx 변환 등). 창고는 바이트만 내주고
    해석은 가져간 쪽 몫 = asker-pays. 변환을 여기서 하면 비용이 소유자에게 되돌아온다.
    """
    import mimetypes
    from fastapi.responses import FileResponse, Response
    import thumbnails

    p = str(abspath)
    nostore = {"Cache-Control": "no-store"}
    if download:
        nostore = {**nostore, **_download_headers(abspath.name)}
    try:
        kind = thumbnails.classify(p)
    except Exception:
        kind = None

    if strip_exif and kind == "photo":
        try:
            if thumbnails.needs_exif_strip(p):
                data = thumbnails.sanitize_image_bytes(p)
                if data:
                    return Response(content=data, media_type="image/jpeg", headers=nostore)
        except Exception:
            pass   # 벗기기 실패 시 아래 원본 폴백

    if kind == "video" and not download:   # 다운로드는 원본 그대로
        try:
            if thumbnails.needs_video_transcode(p):
                import hashlib
                st = abspath.stat()
                # mtime+size 를 키에 넣어 같은 이름으로 갈아끼워도 캐시가 낡지 않게.
                key = hashlib.md5(f"{p}|{st.st_mtime_ns}|{st.st_size}".encode("utf-8")).hexdigest()[:16]
                cache = _WH_MEDIA_CACHE / (key + ".mp4")
                if not (cache.exists() and cache.stat().st_size > 0):
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    thumbnails.transcode_video_to_mp4(p, str(cache))
                if cache.exists() and cache.stat().st_size > 0:
                    return FileResponse(str(cache), media_type="video/mp4", headers=nostore)
        except Exception:
            pass   # 변환 실패 시 원본 폴백(적어도 받아는 진다)

    # .md 등의 매핑은 mime_compat 가 부팅 시 전역 보강(윈도우 임베디드 파이썬 구멍).
    ctype = mimetypes.guess_type(abspath.name)[0] or "application/octet-stream"
    if ctype.startswith("text/") and "charset" not in ctype:
        ctype += "; charset=utf-8"   # 한글 문서가 브라우저 인코딩 추측으로 깨지지 않게
    return FileResponse(p, media_type=ctype, headers=nostore)


@router.get("/file")
async def node_file(request: Request, path: str = "", download: int = 0,
                    x_showcase_secret: str = Header(default="")):
    """공개 파일 서빙. `download=1` 이면 저장(내려받기) — 방문자·외부 AI 가 바이트를 가져간다."""
    _check_secret(x_showcase_secret)
    core = _core()
    _viewer, level = _viewer_level(core, request)
    _ensure_warehouses()
    for lv in sorted((l for l in _WAREHOUSE_LEVELS if l <= level), reverse=True):
        f = _safe_rel(_warehouse_dir(lv), path)
        if f.is_file():
            # 공개면 = EXIF 제거(열람이든 다운로드든)
            return _serve_warehouse_file(f, strip_exif=True, download=bool(download))
    raise HTTPException(status_code=404, detail="no such file")


# ── 창고 방명록 — 한 창고에 스트림 하나. 파일별 댓글이 아니라 "파일에서 시작하는 글". ──
# 설계(왜 파일별 댓글이 아닌가): 창고의 불변식은 '색인 없음 · 파일시스템이 진실 · 즉석 walk'
# 라 파일에 안정적 ID 가 없다. 경로로 키잉하면 Finder 이름변경에 고아가 되고(감지도 못 함),
# 내용해시로 키잉하면 한 줄만 고쳐도 사라진다. 그래서 `about` 은 **외래키가 아니라 출처 기록**:
# 무결성을 강제하지 않고, GC 도 없고, 어긋나면 레코드가 깨지는 대신 '낡은 인용'이 될 뿐이다.
# 그 대신 어긋남을 읽는 사람에게 **보여준다**(about_state). 특정 파일의 글 모아보기는 별도
# 기능이 아니라 이 스트림을 about 으로 거르는 것 = 조회 방식.
#
# 판(version) 문제: 같은 이름 파일이 교체되면 경로는 같고 내용이 달라져 글이 조용히 엉뚱한
# 판에 붙는다(이름변경의 반대 방향 누수). 글 남길 때 그때의 mtime 을 함께 적어 두고 렌더 때
# 대조해 '이전 판에 대한 글'로 표시한다. 해시가 아니라 mtime 인 이유 = 이미 walk 에 들어 있어
# 공짜고, **이웃 폴러가 `changed` 를 판정하는 바로 그 신호**다(한 시스템에 '바뀌었다' 정의 2개 금지).
#
# 레벨: about 에 파일 이름이 박히므로 그대로 두면 레벨 0 손님이 상위 파일명을 알게 된다
# (404≠403 · has_restricted='이름 없는 냄새' 규율이 깨짐). 그래서 렌더 시 방문자 절단면과
# 대조해 **상위 레벨 파일에 달린 글은 항목째 숨긴다**(about 만 지우면 본문이 그 파일을 언급할
# 수 있다). 결과적으로 방명록이 레벨 게이트를 공짜로 물려받는다.
#
# 신원: 손님은 이름을 입력하지 않는다(자동 '손님') — 입력란이 없으면 회원 사칭이 불가능하다.
# 로그인 상태면 쿠키(pk)에서 이름·레벨이 붙는다(서명된 글). 이름은 그 시점 스냅샷.

_GB_STORE = _ROOT / "data" / "warehouse_guestbook.json"
_GB_MSG_MAX = 1000
_GB_MAX_ENTRIES = 2000
_GB_MIN_INTERVAL_S = 20          # IP 간격(연타·봇) — 초과 시 429
_GB_LOCK = threading.Lock()
_GB_LAST_BY_IP: dict = {}


def _gb_load() -> list:
    try:
        return json.loads(_GB_STORE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _gb_save(entries: list) -> None:
    _GB_STORE.parent.mkdir(parents=True, exist_ok=True)
    tmp = _GB_STORE.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries[-_GB_MAX_ENTRIES:], ensure_ascii=False, indent=1),
                   encoding="utf-8")
    tmp.replace(_GB_STORE)


def _all_warehouse_paths() -> dict:
    """전 레벨(0..4) 상대경로 → mtime. '내 레벨 위라 숨김'과 '아예 없음(이름변경·삭제)'을 가른다."""
    out = {}
    for lv in sorted(_WAREHOUSE_LEVELS, reverse=True):
        try:
            d = _warehouse_dir(lv)
            for p in d.rglob("*"):
                if not p.is_file() or p.name.startswith("."):
                    continue
                rel = str(p.relative_to(d))
                if rel not in out:
                    out[rel] = datetime.fromtimestamp(p.stat().st_mtime).isoformat(timespec="seconds")
        except Exception:
            continue
    return out


def _gb_for_level(level: int) -> list:
    """방문자 절단면 기준으로 방명록을 거른다 — 4가지 경우(설계 주석 참조).
      about 없음        → 그냥 보임(일반 인사)
      내 절단면 · mtime 같음 → current (현재 판에 대한 글)
      내 절단면 · mtime 다름 → old     ('이전 판에 대한 글')
      내 레벨 위          → 숨김(누수 방지)
      어디에도 없음        → gone    (낡은 인용 — 없는 파일이라 누수 아님)
    """
    mine = {f["name"]: f.get("mtime", "") for f in _accessible_files(level)}
    every = _all_warehouse_paths()
    out = []
    for e in _gb_load():
        about = (e.get("about") or "").strip()
        row = {"id": e.get("id", ""), "name": e.get("name", "손님"),
               "member": bool(e.get("member")), "level": int(e.get("level", 0) or 0),
               "msg": e.get("msg", ""), "at": e.get("at", ""), "about": about}
        if not about:
            row["about_state"] = ""
        elif about in mine:
            row["about_state"] = "current" if mine[about] == e.get("about_mtime", "") else "old"
        elif about in every:
            continue                      # 내 레벨 위 — 이름도 본문도 안 흘린다
        else:
            row["about_state"] = "gone"
        out.append(row)
    return out


@router.get("/gb")
async def gb_list(request: Request, about: str = "", x_showcase_secret: str = Header(default="")):
    """방명록 목록(내 레벨 절단). about= 주면 그 파일에 달린 글만 = '파일별 댓글' 조회."""
    _check_secret(x_showcase_secret)
    core = _core()
    _viewer, level = _viewer_level(core, request)
    _ensure_warehouses()
    entries = _gb_for_level(level)
    if about:
        entries = [e for e in entries if e.get("about") == about]
    entries.reverse()
    return JSONResponse({"entries": entries[:200]}, headers={"Cache-Control": "no-store"})


@router.post("/gb")
async def gb_post(request: Request, x_showcase_secret: str = Header(default=""),
                  x_client_ip: str = Header(default="")):
    """글 남기기. 손님=자동 '손님'(이름 입력란 없음 → 사칭 불가), 회원=쿠키 신원 서명."""
    _check_secret(x_showcase_secret)
    core = _core()
    viewer, level = _viewer_level(core, request)
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    if str(body.get("website", "")).strip():        # 허니팟 — 사람은 못 보는 칸
        return JSONResponse({"ok": True})
    msg = str(body.get("msg", "")).strip()[:_GB_MSG_MAX]
    if not msg:
        raise HTTPException(status_code=400, detail="msg required")

    ip = x_client_ip or (request.client.host if request.client else "")
    now = time.time()
    if ip and now - _GB_LAST_BY_IP.get(ip, 0) < _GB_MIN_INTERVAL_S:
        raise HTTPException(status_code=429, detail="너무 빠릅니다. 잠시 후 다시 시도해 주세요.")

    # about 은 클라이언트 말을 믿지 않는다 — 내 절단면에 실제로 있는 파일일 때만 달리고,
    # 그 시점 mtime 은 서버가 찍는다(볼 수 없는 파일에 글 달아 존재를 떠보는 것도 차단).
    about = str(body.get("about", "")).strip()[:400]
    about_mtime = ""
    if about:
        mine = {f["name"]: f.get("mtime", "") for f in _accessible_files(level)}
        if about not in mine:
            raise HTTPException(status_code=404, detail="no such file")
        about_mtime = mine[about]

    _GB_LAST_BY_IP[ip] = now
    entry = {"id": f"{int(now*1000):x}", "msg": msg,
             "name": (viewer.get("name") or "이웃") if viewer else "손님",
             "member": bool(viewer), "level": level if viewer else 0,
             "about": about, "about_mtime": about_mtime,
             "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "ip": ip}
    with _GB_LOCK:
        entries = _gb_load()
        entries.append(entry)
        _gb_save(entries)
    return JSONResponse({"ok": True})


# ── 창고 관리(소유자 전용) — 런처 '공유창고' 표면(데스크탑·원격)이 부른다. ────────
# _check_secret 없음 + is_public_remote_path 미등록 → 익명 외부는 터널 게이트 401.
# 단, 로그인된 원격 런처는 launcher_session 쿠키가 있어 remote_access_guard 를 통과한다
# (= 소유자의 리모컨). 그래서 이 관리 엔드포인트는 "맥 로컬 + 로그인한 소유자 원격"에서
# 도달한다. add=맥 로컬 파일 경로 복사(데스크탑 드롭/선택), upload=raw body 업로드(원격
# 브라우저는 로컬 경로가 없으므로 바이트를 직접 올린다), 빼기=공유창고/휴지통/<level>/
# 이동(가역 — 0..4 폴더만 서빙 대상이라 휴지통은 공개면에 안 나온다).
_WH_UPLOAD_MAX_BYTES = 200 * 1024 * 1024   # 원격 업로드 1건 상한(200MB)

def _admin_level(level) -> int:
    try:
        lv = int(level)
    except Exception:
        raise HTTPException(status_code=400, detail="bad level")
    if lv not in _WAREHOUSE_LEVELS:
        raise HTTPException(status_code=400, detail="bad level")
    return lv


@router.get("/warehouse-admin/list")
async def warehouse_admin_list(level: int = 0):
    lv = _admin_level(level)
    _ensure_warehouses()
    counts = {}
    for l in _WAREHOUSE_LEVELS:
        d = _warehouse_dir(l)
        counts[l] = sum(1 for p in d.rglob("*") if p.is_file() and not p.name.startswith("."))
    files = []
    dirs = []          # 빈 폴더도 뷰에 보여야 한다(mkdir 직후) — 파일 접두사만으론 못 유도
    d = _warehouse_dir(lv)
    for p in d.rglob("*"):
        if p.name.startswith("."):
            continue
        if p.is_dir():
            dirs.append(str(p.relative_to(d)))
            continue
        if not p.is_file():
            continue
        st = p.stat()
        files.append({"name": str(p.relative_to(d)), "bytes": st.st_size, "path": str(p),
                      "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    files.sort(key=lambda f: f["mtime"], reverse=True)
    # 공개면 부품(portal_core)은 여기선 장식(공개 주소 표시·레벨 라벨)일 뿐 —
    # 로컬 창고 창은 공개 사이트가 하나도 없어도(부품이 죽어도) 열려야 한다
    # (2026-07-20 윈도우: portal_core 이식성 버그가 로컬 목록까지 연좌 500).
    base, labels = "", {}
    try:
        core = _core()
        state = core.load_state()
        base = (state.get("public_base") or "").rstrip("/")
        labels = getattr(core, "LEVEL_LABELS", {}) or {}
    except Exception as e:
        print(f"[창고] 공개면 부품 로드 실패(로컬 목록은 계속): {e}")
    return {"title": _warehouse_title(), "public_url": (base + "/") if base else "",
            "levels": counts, "level": lv, "files": files, "dirs": dirs,
            "level_labels": {str(k): v for k, v in labels.items()},
            # 이 몸의 창고가 디스크 어디에 사는지 — UI 상단 표기용 (새 PC에서 "창고가 어디지?" 답)
            "root_path": str(_WAREHOUSE_ROOT), "folder_path": str(d)}


_WH_ADD_MAX_FILES = 2000     # 폴더 하나를 넣을 때 딸려 들어갈 수 있는 파일 수 상한


def _copy_folder_into(src: Path, dest_dir: Path):
    """폴더를 하위 구조 그대로 창고에 복사 — (넣은 폴더 이름, 파일 수).

    폴더는 창고에서 '한 덩어리'가 아니다. 안의 파일 하나하나가 공개 항목이 되고
    폴더는 그 이름의 접두사로 남는다(_walk_accessible). 그래서 통째로 넣는 건
    '안 열어본 하위 폴더까지 이 레벨로 공개'라는 뜻 — 상한과 자기포함 방어를 둔다.
    """
    import shutil
    src_r = src.resolve()
    # 목적지를 품은 폴더를 넣으면 복사가 자기를 다시 먹는다(무한 증식).
    if str(dest_dir.resolve()).startswith(str(src_r) + os.sep):
        raise ValueError("이 폴더 안에 창고가 들어 있어요 — 통째로는 넣을 수 없어요")
    # 숨김(.DS_Store 등)은 세지도 넣지도 않는다 — 공개면도 어차피 숨김을 뺀다.
    files = [p for p in src_r.rglob("*")
             if p.is_file() and not any(s.startswith(".") for s in p.relative_to(src_r).parts)]
    if not files:
        raise ValueError("빈 폴더예요")
    if len(files) > _WH_ADD_MAX_FILES:
        raise ValueError(f"파일이 너무 많아요({len(files)}개, 상한 {_WH_ADD_MAX_FILES}개)")
    dest = dest_dir / src_r.name
    n = 2
    while dest.exists():
        dest = dest_dir / f"{src_r.name} ({n})"
        n += 1
    shutil.copytree(str(src_r), str(dest), ignore=shutil.ignore_patterns(".*"))
    return dest.name, len(files)


@router.post("/warehouse-admin/add")
async def warehouse_admin_add(request: Request):
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    lv = _admin_level(body.get("level", 0))
    paths = body.get("paths") or []
    if not isinstance(paths, list) or not paths:
        raise HTTPException(status_code=400, detail="paths required")
    import shutil
    _ensure_warehouses()
    # dest = 창고 안 하위폴더(상대경로, 빈 값=레벨 루트) — 파인더식 "보고 있는 폴더로 넣기"
    dest_dir = _safe_rel(_warehouse_dir(lv), str(body.get("dest", "")).strip())
    if not dest_dir.is_dir():
        raise HTTPException(status_code=400, detail="목적지가 폴더가 아니에요")
    added, skipped = [], []
    for raw in paths[:200]:
        src = Path(str(raw)).expanduser()
        if src.is_dir():
            try:
                name, cnt = _copy_folder_into(src, dest_dir)
                added.append(f"{name}/ ({cnt}개)")
            except ValueError as e:
                skipped.append({"path": str(raw), "reason": str(e)})
            except Exception as e:
                skipped.append({"path": str(raw), "reason": str(e)})
            continue
        if not src.is_file():
            skipped.append({"path": str(raw), "reason": "없는 경로예요"})
            continue
        dest = dest_dir / src.name
        n = 2
        while dest.exists():
            dest = dest_dir / f"{src.stem} ({n}){src.suffix}"
            n += 1
        try:
            shutil.copy2(str(src), str(dest))
            added.append(dest.name)
        except Exception as e:
            skipped.append({"path": str(raw), "reason": str(e)})
    return {"ok": True, "level": lv, "added": added, "skipped": skipped}


@router.post("/warehouse-admin/remove")
async def warehouse_admin_remove(request: Request):
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    lv = _admin_level(body.get("level", 0))
    name = str(body.get("name", ""))
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    src = _safe_rel(_warehouse_dir(lv), name)
    if not src.exists() or src == _warehouse_dir(lv):
        raise HTTPException(status_code=404, detail="no such item")
    trash = _WAREHOUSE_ROOT / "휴지통" / _WAREHOUSE_LEVELS[lv]
    trash.mkdir(parents=True, exist_ok=True)
    dest = trash / src.name
    if dest.exists():
        dest = (trash / f"{src.stem}.{int(time.time())}{src.suffix}" if src.is_file()
                else trash / f"{src.name}.{int(time.time())}")
    src.rename(dest)   # 같은 볼륨 → 이동. 폴더도 통째로(파인더식 빼기).
    return {"ok": True, "trashed": str(dest)}


@router.post("/warehouse-admin/move")
async def warehouse_admin_move(request: Request):
    """창고 안에서 옮기기·이름변경 — 파일이든 폴더든. self:move 와 같은 의미론
    (같은 폴더+new_name=이름변경, dest 다르면 이동)의 창고 스코프판.

    dest_level 이 있으면 레벨을 넘는 이동 = '공개 범위 변경' — 드래그로 레벨 탭에
    떨어뜨리는 명시적 제스처에만 쓴다(2026-07-20 사용자 승인으로 허용).
    같은 볼륨이라 rename = 원자적 이동 — 복사본이 생기지 않는다.
    """
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    lv = _admin_level(body.get("level", 0))
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    root = _warehouse_dir(lv)
    src = _safe_rel(root, name)
    if not src.exists():
        raise HTTPException(status_code=404, detail="no such item")
    dst_lv = _admin_level(body.get("dest_level", lv))
    _ensure_warehouses()                                # dest_level 폴더가 아직 없을 수 있다
    dst_root = _warehouse_dir(dst_lv)
    dst_dir = _safe_rel(dst_root, str(body.get("dest", "")).strip())   # 빈 값 = 창고 루트
    if not dst_dir.is_dir():
        raise HTTPException(status_code=400, detail="목적지가 폴더가 아니에요")
    # 폴더를 자기 자신·자기 하위로 옮기면 트리가 끊긴다(자기를 삼킴).
    if src.is_dir() and (dst_dir == src
                         or str(dst_dir.resolve()).startswith(str(src.resolve()) + os.sep)):
        raise HTTPException(status_code=400, detail="폴더를 자기 안으로는 옮길 수 없어요")
    new_name = str(body.get("new_name", "")).strip()
    if new_name and ("/" in new_name or new_name.startswith(".")):
        raise HTTPException(status_code=400, detail="쓸 수 없는 이름이에요")
    base_name = new_name or src.name
    if src.parent == dst_dir and base_name == src.name:
        return {"ok": True, "moved": name, "noop": True}

    def _is_src(p: Path) -> bool:
        # 맥 기본 파일시스템은 대소문자 무시 — 케이스만 바꾸는 이름변경에서
        # target.exists() 가 자기 자신을 보고 참이 된다. 문자열 비교로는 못 가른다.
        try:
            return os.path.samefile(p, src)
        except OSError:
            return False
    target = dst_dir / base_name
    if new_name and target.exists() and not _is_src(target):
        raise HTTPException(status_code=409, detail="같은 이름이 이미 있어요")
    n = 2
    while target.exists() and not _is_src(target):
        stem, dot, ext = base_name.rpartition(".")
        target = dst_dir / (f"{stem} ({n}).{ext}" if (dot and src.is_file())
                            else f"{base_name} ({n})")
        n += 1
    src.rename(target)
    return {"ok": True, "moved": str(target.relative_to(dst_root)), "level": dst_lv}


@router.post("/warehouse-admin/mkdir")
async def warehouse_admin_mkdir(request: Request):
    """빈 폴더 생성 — 파인더식 '새 폴더'. AI 는 self:mkdir 로 같은 일을 한다(어휘 중복
    아님 — 이건 GUI 배관: 경로 감옥 + 이름 충돌 시 '(2)' 관례가 창고 스코프에 산다)."""
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    lv = _admin_level(body.get("level", 0))
    _ensure_warehouses()
    root = _warehouse_dir(lv)
    parent = _safe_rel(root, str(body.get("dest", "")).strip())    # 빈 값 = 창고 루트
    if not parent.is_dir():
        raise HTTPException(status_code=400, detail="목적지가 폴더가 아니에요")
    name = str(body.get("name", "")).strip() or "새 폴더"
    if "/" in name or name.startswith("."):
        raise HTTPException(status_code=400, detail="쓸 수 없는 이름이에요")
    target = parent / name
    n = 2
    while target.exists():
        target = parent / f"{name} ({n})"
        n += 1
    target.mkdir()
    return {"ok": True, "created": str(target.relative_to(root))}


@router.get("/warehouse-admin/trash")
async def warehouse_admin_trash():
    """휴지통 내용 — 뺀 단위(파일·폴더) 그대로, 전 레벨 합쳐서. 복구 목적지를 알아야
    하니 각 항목에 원래 레벨이 실린다(휴지통/<level>/ 구조가 그 기억)."""
    items = []
    trash_root = _WAREHOUSE_ROOT / "휴지통"
    for lv, sub in _WAREHOUSE_LEVELS.items():
        d = trash_root / sub
        if not d.is_dir():
            continue
        for p in d.iterdir():
            if p.name.startswith("."):
                continue
            st = p.stat()
            if p.is_dir():
                inner = [f for f in p.rglob("*") if f.is_file() and not f.name.startswith(".")]
                items.append({"name": p.name, "level": lv, "is_dir": True,
                              "count": len(inner), "bytes": sum(f.stat().st_size for f in inner),
                              "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
            else:
                items.append({"name": p.name, "level": lv, "is_dir": False,
                              "count": 1, "bytes": st.st_size,
                              "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")})
    items.sort(key=lambda i: i["mtime"], reverse=True)
    return {"items": items, "count": len(items)}


@router.post("/warehouse-admin/restore")
async def warehouse_admin_restore(request: Request):
    """휴지통에서 원래 레벨의 창고 루트로 복구 — remove 의 역방향."""
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    lv = _admin_level(body.get("level", 0))
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    trash_dir = _WAREHOUSE_ROOT / "휴지통" / _WAREHOUSE_LEVELS[lv]
    src = _safe_rel(trash_dir, name)
    if src.parent != trash_dir or not src.exists():
        raise HTTPException(status_code=404, detail="no such item")
    _ensure_warehouses()
    root = _warehouse_dir(lv)
    target = root / src.name
    n = 2
    while target.exists():
        target = root / (f"{src.stem} ({n}){src.suffix}" if src.is_file()
                         else f"{src.name} ({n})")
        n += 1
    src.rename(target)
    return {"ok": True, "restored": str(target.relative_to(root)), "level": lv}


@router.post("/warehouse-admin/trash-delete")
async def warehouse_admin_trash_delete(request: Request):
    """휴지통 영구 삭제 — {level, name} 단건 또는 {all: true} 비우기. 여기만 파괴적
    (창고 본체의 remove 는 언제나 휴지통 이동) — UI 가 confirm 을 앞세운다."""
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    import shutil
    trash_root = _WAREHOUSE_ROOT / "휴지통"
    if body.get("all"):
        removed = 0
        for sub in _WAREHOUSE_LEVELS.values():
            d = trash_root / sub
            if not d.is_dir():
                continue
            for p in d.iterdir():
                if p.name.startswith("."):
                    continue
                shutil.rmtree(p) if p.is_dir() else p.unlink()
                removed += 1
        return {"ok": True, "removed": removed}
    lv = _admin_level(body.get("level", 0))
    name = str(body.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    trash_dir = trash_root / _WAREHOUSE_LEVELS[lv]
    src = _safe_rel(trash_dir, name)
    if src.parent != trash_dir or not src.exists():
        raise HTTPException(status_code=404, detail="no such item")
    shutil.rmtree(src) if src.is_dir() else src.unlink()
    return {"ok": True, "removed": 1}


@router.get("/warehouse-admin/file")
async def warehouse_admin_file(level: int = 0, name: str = "", download: int = 0):
    """소유자 열람·내려받기 — 런처 창고 표면(데스크탑·원격)에서 파일을 연다/받는다.

    공개면과 달리 EXIF 를 벗기지 않는다(내 파일의 원본을 본다). 동영상 변환은 열람에만 —
    안 그러면 원격 런처에서 아이폰 영상이 열리지 않는다. `download=1` 은 원본 그대로."""
    lv = _admin_level(level)
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    f = _safe_rel(_warehouse_dir(lv), name)
    if not f.is_file():
        raise HTTPException(status_code=404, detail="no such file")
    return _serve_warehouse_file(f, strip_exif=False, download=bool(download))


@router.post("/warehouse-admin/upload")
async def warehouse_admin_upload(request: Request, level: int = 0, filename: str = ""):
    """원격 업로드 — raw body(멀티파트 아님). 원격 런처는 로컬 파일 경로가 없으므로
    바이트를 직접 올린다(add=맥 로컬 복사의 원격 짝). 한 번에 한 파일.

    filename 에 상대경로("사진/2024/a.jpg")가 오면 하위 폴더째 만든다 — 브라우저는
    폴더를 통째로 못 보내므로 폴더 넣기 = 이 호출을 파일 수만큼 반복하는 것이다.
    """
    lv = _admin_level(level)
    # 경로는 살리되 각 마디는 살균: 숨김(.)·상위이동(..)·빈 마디를 떨어낸다.
    segs = [s.strip().lstrip(".") for s in (filename or "").replace("\\", "/").split("/")]
    segs = [s for s in segs if s and s not in (".", "..")]
    name = "/".join(segs)
    if not name:
        raise HTTPException(status_code=400, detail="filename required")
    cl = request.headers.get("content-length")
    if cl and int(cl) > _WH_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="too large")
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="empty body")
    if len(body) > _WH_UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="too large")
    _ensure_warehouses()
    dest_dir = _warehouse_dir(lv)
    dest = _safe_rel(dest_dir, name)     # 경로이탈 방어(../ 등)
    parent, stem, suffix = dest.parent, dest.stem, dest.suffix
    n = 2
    while dest.exists():
        dest = parent / f"{stem} ({n}){suffix}"
        n += 1
    parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return {"ok": True, "level": lv, "added": str(dest.relative_to(dest_dir))}


@router.get("/warehouse-admin/gb")
async def warehouse_admin_gb_list():
    """소유자 모더레이션 — 레벨 절단 없이 전부(상위 파일에 달린 글 포함). ip 는 안 내보낸다."""
    entries = [{k: v for k, v in e.items() if k != "ip"} for e in _gb_load()]
    entries.reverse()
    return {"entries": entries, "count": len(entries)}


@router.post("/warehouse-admin/gb/delete")
async def warehouse_admin_gb_delete(request: Request):
    try:
        eid = str((await request.json()).get("id", "")).strip()
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    if not eid:
        raise HTTPException(status_code=400, detail="id required")
    with _GB_LOCK:
        entries = _gb_load()
        left = [e for e in entries if e.get("id") != eid]
        if len(left) == len(entries):
            raise HTTPException(status_code=404, detail="no such entry")
        _gb_save(left)
    return {"ok": True, "removed": eid}


# ── 단일 노드 로그인 — 루트(/) 스코프 쿠키 pk. 슬러그 없는 주소에서도 레벨 절단면을 읽게. ──

@router.post("/node/login")
async def node_login(request: Request, x_showcase_secret: str = Header(default=""),
                     x_client_ip: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    ip = _client_ip(request, x_client_ip)
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    user_id = str(body.get("user_id", "")).strip()
    password = str(body.get("password", ""))
    if not core.login_rate_ok(ip):
        raise HTTPException(status_code=429, detail="시도가 너무 잦아요 — 잠시 후 다시")
    m = core.find_member_by_login(None, user_id)
    if not m or m.get("revoked") or not core.verify_password(m, password):
        core.audit_log(f"node-login-fail:{ip}", "portal", f"login {user_id}", False)
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 맞지 않아요")
    core.audit_log(f"{m['name']}({m['id']})", "portal", "node login", True)
    resp = JSONResponse({"ok": True, "name": m["name"], "level": m["level"]})
    kw = {"max_age": _COOKIE_MAX_AGE} if bool(body.get("auto", True)) else {}
    resp.set_cookie(key="pk", value=m["key"], path="/", httponly=True,
                    samesite="lax", secure=True, **kw)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.post("/node/logout")
async def node_logout(x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key="pk", path="/")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.post("/node/join")
async def node_join(request: Request, x_showcase_secret: str = Header(default=""),
                    x_client_ip: str = Header(default="")):
    """창고 가입 — 방문자가 아이디·비밀번호를 만들고 이메일(복구용)을 남긴다.
    레벨 0 자동 등록 → 즉시 로그인(루트 스코프 pk 쿠키, node_login 과 동일).
    회원=이웃(business.db) — 포털 가입(join/{slug})과 같은 전역 명부라, 창고에서
    가입한 계정으로 포털에도 로그인된다(레벨 승급은 창고 주인이 이웃 레벨로)."""
    _check_secret(x_showcase_secret)
    core = _core()
    ip = _client_ip(request, x_client_ip)
    if not core.join_rate_ok(ip):
        raise HTTPException(status_code=429, detail="너무 빨라요 — 잠시 후 다시 시도해 주세요")
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    name = str(body.get("name", "")).strip()
    user_id = str(body.get("user_id", "")).strip()
    password = str(body.get("password", ""))
    email = str(body.get("email", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력해 주세요")
    if not user_id or not password:
        raise HTTPException(status_code=400, detail="아이디와 비밀번호를 입력해 주세요")
    if not core.valid_email(email):
        raise HTTPException(status_code=400, detail="비밀번호 찾기에 쓸 이메일을 정확히 입력해 주세요")
    try:
        m = core.create_member(None, name, email, 0, login_id=user_id, password=password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    core.audit_log(f"join:{ip}", "portal", f"창고 가입 {name} ({user_id})", True)
    try:  # 운영자 알림 — best effort
        from notification_manager import get_notification_manager
        get_notification_manager().info(
            "창고 가입",
            f"{name} 님이 공개 창고에 가입했어요 (레벨 0) — 이웃 레벨을 주면 그 레벨 창고가 열립니다.",
            source="portal")
    except Exception:
        pass
    resp = JSONResponse({"ok": True, "name": name, "level": 0})
    kw = {"max_age": _COOKIE_MAX_AGE} if bool(body.get("auto", True)) else {}
    resp.set_cookie(key="pk", value=m["key"], path="/", httponly=True,
                    samesite="lax", secure=True, **kw)
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── 개인 링크 착지 (운영자 발급 열쇠 → 쿠키. 비밀번호 분실 복구 경로 겸용) ──

@router.get("/key/{slug}/{memberkey}")
async def key_landing(slug: str, memberkey: str, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    m = core.find_member(portal, key=memberkey)
    if not m:
        html = _renderer().render_notice(
            "링크가 유효하지 않아요",
            "회수됐거나 새 링크로 바뀌었을 수 있어요 — 운영자에게 재발급을 부탁하세요.",
            home=f"/h/{slug}/")
        return HTMLResponse(html, status_code=404, headers={"Cache-Control": "no-store"})
    resp = RedirectResponse(url=f"/h/{slug}/", status_code=302)
    return _set_session(resp, slug, memberkey)


# ── 가입 (아이디+비밀번호, 레벨 0 자동 등록 → 즉시 로그인) ────────────────

@router.post("/join/{slug}")
async def join(slug: str, request: Request, x_showcase_secret: str = Header(default=""),
               x_client_ip: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    ip = _client_ip(request, x_client_ip)
    if not core.join_rate_ok(ip):
        raise HTTPException(status_code=429, detail="너무 빨라요 — 잠시 후 다시 시도해 주세요")
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    name = str(body.get("name", "")).strip()
    user_id = str(body.get("user_id", "")).strip()
    password = str(body.get("password", ""))
    email = str(body.get("email", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력해 주세요")
    if not user_id or not password:
        raise HTTPException(status_code=400, detail="아이디와 비밀번호를 입력해 주세요")
    if not core.valid_email(email):
        raise HTTPException(status_code=400, detail="비밀번호 찾기에 쓸 이메일을 정확히 입력해 주세요")

    # 회원 = 이웃(business.db) — 가입하면 이웃 책에 레벨 0 으로 등록/연결된다.
    try:
        m = core.create_member(portal, name, email, 0, login_id=user_id, password=password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    core.audit_log(f"join:{ip}", "portal", f"가입 {name} ({user_id})", True, portal=slug)
    try:  # 운영자 알림 — best effort
        from notification_manager import get_notification_manager
        get_notification_manager().info("포털 가입",
                                        f"{name} 님이 '{slug}' 포털에 가입했어요 (레벨 0) — 승급하면 회원 계기가 열립니다.",
                                        source="portal")
    except Exception:
        pass
    resp = JSONResponse({"ok": True, "name": name})
    return _set_session(resp, slug, m["key"], persistent=bool(body.get("auto", True)))


# ── 로그인 / 로그아웃 (네이버식 — 아이디+비밀번호, 자동 로그인) ────────────

@router.post("/login/{slug}")
async def login(slug: str, request: Request, x_showcase_secret: str = Header(default=""),
                x_client_ip: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    ip = _client_ip(request, x_client_ip)
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    user_id = str(body.get("user_id", "")).strip()
    password = str(body.get("password", ""))
    if not core.login_rate_ok(ip):
        raise HTTPException(status_code=429, detail="시도가 너무 잦아요 — 잠시 후 다시")
    m = core.find_member_by_login(portal, user_id)
    if not m or m.get("revoked") or not core.verify_password(m, password):
        core.audit_log(f"login-fail:{ip}", "portal", f"login {user_id}", False, portal=slug)
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 맞지 않아요")

    core.audit_log(f"{m['name']}({m['id']})", "portal", "login", True, portal=slug)
    resp = JSONResponse({"ok": True, "name": m["name"]})
    return _set_session(resp, slug, m["key"], persistent=bool(body.get("auto", True)))


@router.post("/logout/{slug}")
async def logout(slug: str, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key=f"pk_{slug}", path=f"/h/{slug}")
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── 비밀번호 찾기 (임시 비밀번호를 등록 이메일로 발송) ─────────────────────

def _send_email(to: str, subject: str, body: str):
    """시스템 Gmail 계정으로 발송. (성공, 오류메시지)."""
    try:
        from channel_engine import _get_system_gmail_address
        from api_gmail import get_gmail_client_for_email
        sys_email = _get_system_gmail_address()
        if not sys_email:
            return False, "시스템 Gmail 계정이 설정되지 않았어요 (gmail extension config.yaml)"
        client = get_gmail_client_for_email(sys_email)
        if not client:
            return False, "Gmail 클라이언트를 준비하지 못했어요 (인증 필요)"
        client.send_message(to=to, subject=subject, body=body)
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _reset_email_body(portal: dict, home: str, member: dict, temp: str) -> str:
    title = portal.get("title") or "포털"
    return (
        f"{member.get('name','')}님, 안녕하세요.\n\n"
        f"'{title}' 로그인용 임시 비밀번호를 보내드려요.\n\n"
        f"    아이디: {member.get('login_id','')}\n"
        f"    임시 비밀번호: {temp}\n\n"
        f"이 비밀번호로 로그인한 뒤, 홈에서 '비밀번호 변경'으로 원하는 비밀번호로 바꿔 주세요.\n"
        f"로그인: {home}\n\n"
        f"본인이 요청하지 않았다면 이 메일은 무시하셔도 됩니다 (기존 비밀번호는 이미 바뀌었으니, "
        f"다시 '비밀번호 찾기'로 재설정해 주세요).\n"
    )


@router.post("/reset/{slug}")
async def reset_password(slug: str, request: Request, x_showcase_secret: str = Header(default=""),
                         x_client_ip: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    ip = _client_ip(request, x_client_ip)
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    email = str(body.get("email", "")).strip()
    if not core.valid_email(email):
        raise HTTPException(status_code=400, detail="가입할 때 쓴 이메일을 정확히 입력해 주세요")
    # 메일 폭탄 방어 — 같은 이메일·같은 IP 둘 다 제한.
    if not core.reset_rate_ok(email.lower()) or not core.reset_rate_ok(f"ip:{ip}"):
        raise HTTPException(status_code=429, detail="요청이 너무 잦아요 — 잠시 후 다시 시도해 주세요")

    m = core.find_member_by_email(portal, email)
    if not m or m.get("revoked") or not m.get("login_id"):
        # 작은 가족 포털이라 명확히 안내(남용은 rate limit 이 막음).
        return JSONResponse({"ok": False, "detail": "그 이메일로 가입된 계정이 없어요"}, status_code=404)

    temp = core.gen_temp_password()
    home = core.portal_url(state, portal) or f"/h/{slug}/"
    # ★비밀번호는 메일 발송에 성공한 뒤에만 바꾼다(발송 실패로 잠기는 것 방지).
    ok, err = _send_email(email, f"[{portal.get('title','포털')}] 임시 비밀번호",
                          _reset_email_body(portal, home, m, temp))
    if not ok:
        core.audit_log(f"reset-fail:{ip}", "portal", f"pw reset {m.get('login_id')}", False,
                       note=err, portal=slug)
        raise HTTPException(status_code=502, detail=f"메일을 보내지 못했어요: {err}")

    core.set_password(m, temp)   # 이웃 레코드의 portal_pw 갱신(전역)
    core.audit_log(f"reset:{ip}", "portal", f"pw reset {m.get('login_id')}", True, portal=slug)
    resp = JSONResponse({"ok": True, "message": "등록된 이메일로 임시 비밀번호를 보냈어요 — 메일함을 확인해 주세요"})
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── 비밀번호 변경 (로그인한 회원 본인) ────────────────────────────────────

@router.post("/password/{slug}")
async def change_password(slug: str, request: Request, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    viewer = _viewer(core, portal, request, slug)
    if not viewer:
        raise HTTPException(status_code=401, detail="로그인이 필요해요")
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    new_pw = str(body.get("new_password", ""))
    m = core.find_member(portal, member_id=viewer["id"])
    if not m:
        raise HTTPException(status_code=400, detail="회원을 찾을 수 없어요")
    try:
        core.set_password(m, new_pw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    core.audit_log(f"{viewer['name']}({viewer['id']})", "portal", "pw change", True, portal=slug)
    resp = JSONResponse({"ok": True, "message": "비밀번호를 바꿨어요"})
    resp.headers["Cache-Control"] = "no-store"
    return resp


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
