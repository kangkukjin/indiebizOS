"""창고 피드 API — 창고이웃 등기부(contacts contact_type='warehouse') + 피드/검색/폴링/리트윗.

창고주소 = 연락방법의 하나(이메일·nostr 처럼) — 이웃 목록 하나로 창고이웃까지 담는다
(2026-07-18 2차 개정). "창고주소만 아는 상대"도 그 주소가 연락처이므로 정상 이웃:
이름 없이 등록하면 창고 제목(매니페스트 title)이나 호스트명으로 이웃을 만든다.

소유자 전용(로컬 + 로그인된 원격 런처): is_public_remote_path 에 미등록이라
익명 외부는 401 — warehouse-admin 과 같은 보안 모델. 공개면이 아니다.
"""
import json
import re
from urllib.parse import urlparse

from anyio import to_thread
from fastapi import APIRouter, HTTPException, Request

import warehouse_adapters
import warehouse_directory
import warehouse_feed as wf
import warehouse_ops   # ⑩ 좋아요·리트윗·허용 창고 필터의 정본(IBL 과 같은 함수)

router = APIRouter(prefix="/warehouse-feed", tags=["warehouse-feed"])


def _bm():
    return wf._bm()


def _cards():
    """등기부(창고 연락처) + 폴링 상태를 합친 카드 목록."""
    status = wf.get_status_map()
    creds = wf.get_credentials_map()
    scores = wf.get_scores_map()
    cards = []
    for ct in _bm().get_warehouse_contacts():
        base = wf.normalize_base(ct["url"])
        st = status.get(base) or {}
        cr = creds.get(base) or {}
        cards.append({
            "contact_id": ct["contact_id"], "neighbor_id": ct["neighbor_id"],
            "name": ct["name"], "info_level": ct.get("info_level", 0),
            "warehouse_url": base,
            "warehouse_memo": ct.get("warehouse_memo") or "",
            # 즐겨찾기 점수(2026-07-20) — *내가 이 창고에 주는* 평가(0~3, 창고 단위·맥 로컬).
            # 접근 레벨(info_level=내가 준 것 / viewer_level=받은 것)과 독립인 내 쪽 축.
            "score": int(scores.get(base) or 0),
            "last_poll": st.get("last_poll"), "ok": st.get("ok"),
            "error": st.get("error"), "file_count": st.get("file_count"),
            "title": st.get("title") or "", "has_restricted": bool(st.get("has_restricted")),
            # 방언 어댑터(2026-07-20): native 외에도 autoindex·rss·nextcloud·page 창고 지원
            "adapter": st.get("adapter") or "native",
            "adapter_label": warehouse_adapters.adapter_label(st.get("adapter")),
            # 회원 로그인(2026-07-20): 내 계정으로 폴링하면 내 레벨의 매니페스트를 받는다
            "login_user": cr.get("user_id") or "",
            "login_ok": cr.get("login_ok"),
            "login_error": cr.get("login_error") or "",
            "viewer_level": st.get("viewer_level"),
        })
    return cards


@router.get("/neighbors")
async def list_warehouse_neighbors():
    """창고이웃 목록 + 창고 연락처 없는 이웃(기존 이웃에 창고 달기 후보)."""
    bm = _bm()
    cards = _cards()
    with_wh = {c["neighbor_id"] for c in cards}
    candidates = [{"id": n["id"], "name": n["name"]}
                  for n in bm.get_neighbors() if n["id"] not in with_wh]
    return {"neighbors": cards, "candidates": candidates}


# ── 창고 둘러보기(장르별 후보) ────────────────────────────────────
# 이웃찾기(#IndieNet)가 "나를 알린 사람"의 수신면이라면, 여기는 아직 아무 관계도
# 없는 창고를 장르로 훑는 면. 등록은 아래 /neighbors/add 를 그대로 쓴다(신규 배관 0).

@router.get("/directory")
async def directory_genres():
    """장르 칩 목록 — data/warehouse_directory.json 이 단일 소스(사용자 편집 가능)."""
    return {"genres": warehouse_directory.list_genres()}


@router.get("/directory/{key}")
async def directory_candidates(key: str, limit: int = 60, refresh: int = 0):
    """한 장르의 후보 창고. 이미 내 등기부에 있는 주소는 registered 로 표시해
    '＋ 등록' 버튼이 중복으로 뜨지 않게 한다."""
    # ★스레드로: 남의 서버로 나가는 동기 HTTP 를 이벤트 루프에서 하면 그 사이
    #   들어오는 요청(자기 매니페스트 포함)을 못 받는다 — neighbors/add 와 같은 이유.
    out = await to_thread.run_sync(
        lambda: warehouse_directory.candidates(key, limit=limit, refresh=bool(refresh)))
    mine = {c["warehouse_url"] for c in _cards()}
    for it in out.get("items", []):
        it["registered"] = wf.normalize_base(it.get("url") or "") in mine
    return out


async def _body(request: Request) -> dict:
    try:
        return json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")


@router.post("/neighbors/add")
async def add_warehouse_neighbor(request: Request):
    """창고 등록 = 창고 연락처 추가.
    neighbor_id → 기존 이웃에 달기 / name → 그 이름 이웃(없으면 생성)에 달기 /
    둘 다 없으면 → 창고 제목(매니페스트 title)·호스트명으로 이웃 생성(주소만 아는 상대)."""
    body = await _body(request)
    # 몸통은 warehouse_feed.register_neighbor 코어(2026-08-31 하강) — IBL 어휘
    # ([others:neighbor]{op:"save", warehouse})와 단일 로직. ★스레드로(자기교착 방지:
    # 루프에서 동기 HTTP(첫 폴링)를 하면 Worker→터널로 돌아오는 자기 manifest 요청을 못 받는다)
    try:
        r = await to_thread.run_sync(lambda: wf.register_neighbor(
            url=body.get("url") or "",
            npub=body.get("npub") or "",
            name=body.get("name") or "",
            neighbor_id=body.get("neighbor_id"),
            adapter=body.get("adapter") or "",
            memo=body.get("memo"),
        ))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
    url = wf.normalize_base(body.get("url") or "")
    return {"neighbor": next((c for c in _cards() if c["warehouse_url"] == url), None),
            "poll": r["poll"]}


@router.post("/neighbors/remove")
async def remove_warehouse_neighbor(request: Request):
    """등기부에서 창고 연락처를 뗌 — 이웃 레코드는 남김. 같은 주소가 다른 이웃에도
    없으면 캐시(스냅샷·피드)도 삭제."""
    body = await _body(request)
    contact_id = body.get("contact_id")
    if not contact_id:
        raise HTTPException(status_code=400, detail="contact_id 가 필요해요")
    bm = _bm()
    target = next((c for c in bm.get_warehouse_contacts() if c["contact_id"] == int(contact_id)), None)
    bm.delete_contact(int(contact_id))
    if target:
        url = wf.normalize_base(target["url"])
        still = any(wf.normalize_base(c["url"]) == url for c in bm.get_warehouse_contacts())
        if not still:
            wf.forget_warehouse(url)
    return {"success": True}


@router.post("/score")
async def set_warehouse_score(request: Request):
    """즐겨찾기 점수(0~3) — *내가 이 창고에 주는* 평가. 접근 레벨과 독립인 축(레벨 비대칭
    해소: 내 창고엔 관심 없는 상대의 훌륭한 창고를 높게 칠 수 있어야 한다). 0=해제.
    창고=주소가 정체이므로 키는 url(이웃 단위 즐겨찾기 boolean 을 창고 단위 점수로 대체)."""
    body = await _body(request)
    url = wf.normalize_base(body.get("url") or "")
    if not url:
        raise HTTPException(status_code=400, detail="창고 주소(url)가 필요해요")
    try:
        score = int(body.get("score", 0))
    except Exception:
        raise HTTPException(status_code=400, detail="score 는 0~3 숫자")
    if score < 0 or score > 3:
        raise HTTPException(status_code=400, detail="score 는 0~3")
    res = wf.set_score(url, score)
    return {**res,
            "neighbor": next((c for c in _cards() if c["warehouse_url"] == url), None)}


@router.post("/neighbors/memo")
async def set_warehouse_memo(request: Request):
    """창고 메모(냄새) 갱신 — additional_info(수기)와 분리된 창고 전용 필드."""
    body = await _body(request)
    neighbor_id = body.get("neighbor_id")
    if not neighbor_id:
        raise HTTPException(status_code=400, detail="neighbor_id 가 필요해요")
    _bm().update_neighbor_warehouse(int(neighbor_id),
                                    warehouse_memo=str(body.get("memo") or ""))
    return {"neighbor": next((c for c in _cards() if c["neighbor_id"] == int(neighbor_id)), None)}


@router.post("/credentials")
async def set_warehouse_credentials(request: Request):
    """창고 계정 등록 — 상대 창고에 *내가 가입한* 아이디·비밀번호. 폴러가 이걸로 로그인해
    내 레벨의 매니페스트를 받는다(익명 폴링=항상 레벨 0 이던 갭 해소). 빈 아이디=해제.

    즉시 로그인 확인 후, 성공하면 그 자리에서 재폴링 — 승급된 레벨의 파일들이 피드에
    바로 들어온다(30분을 안 기다림). ★스레드로(자기교착 방지 — add/poll 과 같은 부류)."""
    body = await _body(request)
    url = wf.normalize_base(body.get("url") or "")
    if not url:
        raise HTTPException(status_code=400, detail="창고 주소(url)가 필요해요")
    user_id = str(body.get("user_id") or "")
    password = str(body.get("password") or "")
    result = await to_thread.run_sync(wf.set_credentials, url, user_id, password)
    if result.get("ok") and not result.get("cleared"):
        await to_thread.run_sync(wf.poll_warehouse, url)
    return {**result,
            "neighbor": next((c for c in _cards() if c["warehouse_url"] == url), None)}


def _auto_register_warehouse(url: str) -> bool:
    """등기부에 없으면 창고이웃 자동 등록 — 가입/로그인한 창고는 관계가 생긴 창고다.
    add_warehouse_neighbor 의 '주소만 아는 상대' 분기와 같은 규칙(매니페스트 title·npub 앵커).
    반환 True=새로 등록."""
    bm = _bm()
    if bm.get_neighbor_by_contact("warehouse", url):
        return False
    poll = wf.poll_warehouse(url)
    npub = (poll.get("npub") or "").strip()
    npub = npub if npub.startswith("npub") else ""
    n = bm.get_neighbor_by_contact("nostr", npub) if npub else None
    if n is None:
        name = (poll.get("title") or "").strip() or (urlparse(url).hostname or url)
        matches = [x for x in bm.get_neighbors(search=name) if x["name"] == name]
        n = matches[0] if matches else bm.create_neighbor(name=name, info_level=0)
    bm.add_contact(n["id"], "warehouse", url)
    if npub and not bm.get_neighbor_by_contact("nostr", npub):
        bm.add_contact(n["id"], "nostr", npub)
    return True


@router.post("/capture")
async def capture_credentials(request: Request):
    """포식 브라우저 자격 캡처 — 사용자가 이웃 창고 페이지에서 가입/수동 로그인하는 순간
    Electron main(webRequest)이 아이디·비밀번호를 여기로 흘린다(로컬 전용 — 원격 미노출).

    ①실로그인으로 '정말 창고인지' 검증 — 일반 사이트의 우연한 /login POST 는 흔적 0.
      (가입 직후엔 계정 생성이 반영 중일 수 있어 실패 시 잠깐 쉬고 1회 재시도.)
    ②등기부에 없으면 창고이웃 자동 등록 — 가입/로그인=관계 맺음.
    ③자격 저장+재폴링 — 다음 폴링부터 시스템이 그 계정 레벨로 탐색한다.
    다음 방문의 '로그인된 상태'는 포식 브라우저(persist:forage)의 pk 쿠키가 맡는다."""
    body = await _body(request)
    url = wf.normalize_base(body.get("url") or "")
    user_id = str(body.get("user_id") or "").strip()
    password = str(body.get("password") or "")
    if not url or not user_id or not password:
        raise HTTPException(status_code=400, detail="url·user_id·password가 필요해요")

    def _verify_with_retry():
        import time as _t
        try:
            return wf._login(url, user_id, password)
        except Exception:
            _t.sleep(2)                       # 가입 직후 레이스 완충
            return wf._login(url, user_id, password)
    try:
        await to_thread.run_sync(_verify_with_retry)
    except Exception as e:
        return {"ok": False, "captured": False,
                "error": f"창고 로그인 확인 실패 — 저장하지 않음: {e}"}

    registered_new = await to_thread.run_sync(_auto_register_warehouse, url)
    result = await to_thread.run_sync(wf.set_credentials, url, user_id, password)
    if result.get("ok"):
        await to_thread.run_sync(wf.poll_warehouse, url)   # 그 계정 레벨로 즉시 반영
    return {**result, "captured": True, "registered_new": registered_new}


@router.post("/poll")
async def poll_now(request: Request):
    """수동 새로고침 — url 없으면 전체 폴링. ★스레드로(자기교착 방지)."""
    body = await _body(request)
    url = wf.normalize_base(body.get("url") or "")
    if url:
        result = await to_thread.run_sync(wf.poll_warehouse, url)
        return {"results": [result]}
    return {"results": await to_thread.run_sync(wf.poll_all)}


def _name_map():
    """창고 url → 표시 이름(이웃 이름). 같은 주소에 여러 이웃이면 첫 이웃."""
    m = {}
    for ct in _bm().get_warehouse_contacts():
        base = wf.normalize_base(ct["url"])
        m.setdefault(base, ct["name"])
    return m


def _allowed_urls(min_level: int = 0, favorites: bool = False, min_score: int = 0):
    return warehouse_ops.allowed_urls(min_level, favorites, min_score)


@router.get("/feed")
async def feed(limit: int = 100, min_level: int = 0, favorites: int = 0,
               min_score: int = 0, cards: int = 0):
    """타임라인 — 이웃 이름·창고 홈을 붙여 반환.
    min_level=그 레벨 이상 이웃만(레벨=숫자, 의미는 사용자가 정함) /
    min_score=내가 준 즐겨찾기 점수 이상의 창고만 / favorites=구 boolean(호환) /
    cards=1 이면 (창고×폴링×종류) 카드 묶음(데스크탑 새 피드) — 기본 0=행 묶음(원격 호환)."""
    names = _name_map()
    status = wf.get_status_map()
    items = []
    for e in wf.get_feed(limit=limit, cards=bool(cards),
                         wh_urls=_allowed_urls(min_level, bool(favorites), min_score)):
        if e["wh_url"] not in names:
            continue  # 등기부에서 떼어진 창고의 잔여 이벤트는 숨김
        e["neighbor_name"] = names[e["wh_url"]]
        # 창고 제목(매니페스트 title) — 이웃 이름이 npub 같은 주소일 때 카드가 이걸 앞세운다
        e["neighbor_title"] = (status.get(e["wh_url"]) or {}).get("title") or ""
        e["neighbor_home"] = e["wh_url"] + "/"
        items.append(e)
    return {"items": items}


@router.get("/browse")
async def browse(url: str, path: str = ""):
    """이웃 창고 인앱 파인더 — 폴러 스냅샷(현재 색인)을 폴더 단위로 서빙.
    피드가 '변화의 강'이라면 이건 '현재의 창고' — 전체를 보러 외부 브라우저로
    이탈하지 않아도 된다. 데이터는 이미 로컬 DB, 왕복 0."""
    base = wf.normalize_base(url)
    if not base:
        raise HTTPException(400, "창고 주소(url)가 필요합니다")
    out = wf.browse_snapshots(base, path)
    out["neighbor_name"] = _name_map().get(base, base)
    out["wh_url"] = base
    return out


@router.get("/search")
async def search(q: str = "", limit: int = 100, sort: str = "recent",
                 min_level: int = 0, favorites: int = 0, min_score: int = 0):
    """전수 키워드 조사(검색 사다리 1층) — 이웃 전체 창고의 현재 파일명 색인에서.

    sort: recent=최신순(기본) / match=이름 일치순.
    min_level·min_score(·구 favorites)=피드와 같은 신뢰·평가 필터.
    """
    names = _name_map()
    items = []
    for e in wf.search_snapshots(q, limit=limit, sort=sort,
                                 wh_urls=_allowed_urls(min_level, bool(favorites),
                                                       min_score)):
        if e["wh_url"] not in names:
            continue
        e["neighbor_name"] = names[e["wh_url"]]
        e["neighbor_home"] = e["wh_url"] + "/"
        items.append(e)
    return {"items": items, "q": q, "sort": sort}


# ── 리트윗: 남의 창고 파일을 내 창고에 소개한다 — 두 모드 (2026-07-19 확장) ──
# link = 포인터(.url, InternetShortcut): 추천. 클릭=원 창고의 원 파일. 저장 비용 0,
#        원 창고가 꺼지면 죽는다. 큰 파일(동영상)에 자연 선택.
# copy = 전파(진짜 리트윗): 파일 자체를 내려받아 내 창고가 재서빙. 원본 불가동에도 살고,
#        내 이웃은 나에게서 받는다(신뢰 간선을 타는 store-and-forward). "소유하고 싶어서"도 copy.
# 두 모드 모두 <레벨>/리트윗/ 전용 폴더에 놓고(폴더 청결), 사이드카(.<파일명>.rt.json)에
# 출처 사슬을 남긴다 — origin(최초 제공 창고·파일)·via(직전 창고)·hops(리트윗 횟수).
# 리트윗의 리트윗이면 원 창고 매니페스트의 rt 필드에서 사슬을 계승한다(hops+1).
# 사이드카는 dotfile 이라 매니페스트 walk 에서 자동으로 숨고, _walk_accessible 이 읽어
# 항목의 rt 필드로 노출한다(이웃 폴러·AI 가 최초 출처로 거슬러 갈 수 있게).

@router.post("/like")
async def like_neighbor_file(request: Request):
    """피드·검색에서 본 이웃 파일에 좋아요 — 구현은 warehouse_ops.like(IBL [others:warehouse]{op:like} 와 같은 함수)."""
    body = await _body(request)
    try:
        return await to_thread.run_sync(warehouse_ops.like, body.get("wh_url") or "", body.get("path") or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"좋아요를 전하지 못했어요: {e}")


@router.post("/retweet")
async def retweet(request: Request):
    """피드·검색에서 본 파일을 내 창고 <레벨>/리트윗/ 에 소개 — 구현은 warehouse_ops.retweet(IBL 과 같은 함수).
    mode: "link"(기본, 포인터 .url=추천) | "copy"(파일 복사=전파·소유)."""
    body = await _body(request)
    try:
        return await to_thread.run_sync(warehouse_ops.retweet, body.get("url") or "", body.get("name") or "",
                                        body.get("level", 0), body.get("mode") or "link", body.get("warehouse") or "")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"원 파일을 못 가져왔어요: {e}")
