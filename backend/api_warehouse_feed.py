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

import warehouse_feed as wf

router = APIRouter(prefix="/warehouse-feed", tags=["warehouse-feed"])


def _bm():
    return wf._bm()


def _cards():
    """등기부(창고 연락처) + 폴링 상태를 합친 카드 목록."""
    status = wf.get_status_map()
    cards = []
    for ct in _bm().get_warehouse_contacts():
        base = wf.normalize_base(ct["url"])
        st = status.get(base) or {}
        cards.append({
            "contact_id": ct["contact_id"], "neighbor_id": ct["neighbor_id"],
            "name": ct["name"], "info_level": ct.get("info_level", 0),
            "warehouse_url": base,
            "warehouse_memo": ct.get("warehouse_memo") or "",
            # 즐겨찾기는 이웃의 성질(neighbors.favorite) — 빠른 연락처와 같은 표식을 공유한다.
            "favorite": bool(ct.get("favorite")),
            "last_poll": st.get("last_poll"), "ok": st.get("ok"),
            "error": st.get("error"), "file_count": st.get("file_count"),
            "title": st.get("title") or "", "has_restricted": bool(st.get("has_restricted")),
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
    url = wf.normalize_base(body.get("url") or "")
    if not url:
        raise HTTPException(status_code=400, detail="창고 주소(url)가 필요해요")
    # npub = 서명된 신원(선택) — 이웃찾기 탭이 소개 작성자의 npub 을 함께 보낸다.
    # 창고(풀)·nostr(푸시) 두 접점을 한 이웃에 모으고, 신원 기준 중복 등록을 막는 앵커.
    npub = (body.get("npub") or "").strip()
    if not npub.startswith("npub"):
        npub = ""                      # hex·축약 등 비정형은 버림 (contacts 규약 = npub 문자열)
    bm = _bm()
    # 같은 주소가 이미 등기부에 있으면 그 카드 반환 (중복 등록 방지).
    # npub 이 딸려 왔고 아직 누구에게도 없으면 그 이웃에게 붙여준다 — 재클릭이 신원을 치유.
    dup = bm.get_neighbor_by_contact("warehouse", url)
    if dup:
        if npub and not bm.get_neighbor_by_contact("nostr", npub):
            bm.add_contact(dup["id"], "nostr", npub)
        return {"neighbor": next((c for c in _cards() if c["warehouse_url"] == url), None),
                "poll": {"ok": True, "note": "이미 등록된 창고"}}
    # 첫 폴링을 먼저 — 연결 확인 + 이름 유도(title)에 쓴다. ★스레드로(자기교착 방지:
    # 루프에서 동기 HTTP 를 하면 Worker→터널로 돌아오는 자기 manifest 요청을 못 받는다)
    poll = await to_thread.run_sync(wf.poll_warehouse, url)
    neighbor_id = body.get("neighbor_id")
    name = (body.get("name") or "").strip()
    # ★신원 앵커 우선: 같은 npub 의 이웃이 이미 있으면(커뮤니티/메신저 경로로 등록된 그 사람)
    #   새 이웃을 만들지 않고 그에게 창고 연락처를 단다 — 경로가 달라도 레코드는 하나.
    n = bm.get_neighbor_by_contact("nostr", npub) if npub else None
    if n is None and neighbor_id:
        n = bm.get_neighbor(int(neighbor_id))
        if not n:
            raise HTTPException(status_code=404, detail="이웃을 찾을 수 없어요")
    elif n is None:
        if not name:
            # 주소만 아는 상대 — 창고 제목이 곧 그 사람의 이름표
            name = (poll.get("title") or "").strip() or (urlparse(url).hostname or url)
        matches = [x for x in bm.get_neighbors(search=name) if x["name"] == name]
        n = matches[0] if matches else bm.create_neighbor(name=name, info_level=0)
    bm.add_contact(n["id"], "warehouse", url)
    if npub and not bm.get_neighbor_by_contact("nostr", npub):
        bm.add_contact(n["id"], "nostr", npub)
    if body.get("memo") is not None:
        bm.update_neighbor_warehouse(n["id"], warehouse_memo=str(body.get("memo")))
    return {"neighbor": next((c for c in _cards() if c["warehouse_url"] == url), None),
            "poll": poll}


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


@router.post("/neighbors/favorite")
async def toggle_warehouse_favorite(request: Request):
    """즐겨찾기 토글 — 이웃 단위(neighbors.favorite). 한 이웃의 창고가 여럿이면 함께 움직인다."""
    body = await _body(request)
    nid = body.get("neighbor_id")
    if not isinstance(nid, int):
        raise HTTPException(status_code=400, detail="neighbor_id(정수)가 필요해요")
    n = _bm().toggle_neighbor_favorite(nid)
    if not n:
        raise HTTPException(status_code=404, detail="그런 이웃이 없어요")
    return {"neighbor_id": nid, "favorite": bool(n.get("favorite"))}


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


@router.get("/feed")
async def feed(limit: int = 100):
    """타임라인 — 이웃 이름·창고 홈을 붙여 반환."""
    names = _name_map()
    items = []
    for e in wf.get_feed(limit=limit):
        if e["wh_url"] not in names:
            continue  # 등기부에서 떼어진 창고의 잔여 이벤트는 숨김
        e["neighbor_name"] = names[e["wh_url"]]
        e["neighbor_home"] = e["wh_url"] + "/"
        items.append(e)
    return {"items": items}


@router.get("/search")
async def search(q: str = "", limit: int = 100, sort: str = "recent"):
    """전수 키워드 조사(검색 사다리 1층) — 이웃 전체 창고의 현재 파일명 색인에서.

    sort: recent=최신순(기본) / match=이름 일치순.
    """
    names = _name_map()
    items = []
    for e in wf.search_snapshots(q, limit=limit, sort=sort):
        if e["wh_url"] not in names:
            continue
        e["neighbor_name"] = names[e["wh_url"]]
        e["neighbor_home"] = e["wh_url"] + "/"
        items.append(e)
    return {"items": items, "q": q, "sort": sort}


# ── 리트윗: 남의 창고 파일을 가리키는 링크 파일을 내 창고에 놓는다 ──
# 리트윗=포인터 파일(FOAF 발견을 파일로): 내 구독자 피드에 흘러가고, 클릭=원 창고의
# 원 파일. 형식=.url(InternetShortcut) — OS·타 하네스도 아는 표준, 공개면(_accessible_files)
# 이 target 을 해석해 매니페스트·홈에서 곧장 원 파일로 링크한다.

_URLFILE_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _source_warehouse(target: str, hint: str = "") -> str:
    """링크가 가리키는 파일이 사는 창고의 베이스 주소.

    파일 주소가 곧 창고를 말한다(`{base}/f?path=…`) → 목표에서 직접 유도하는 게 가장 정확.
    리트윗의 리트윗이면 목표가 이미 원 창고를 가리키므로 중간 창고가 아니라 원 창고가 잡힌다.
    유도 실패 시 호출자 힌트(피드 항목의 wh_url), 그것도 없으면 등기부 주소 접두 일치."""
    head = target.split("/f?", 1)[0]
    if head != target and head.startswith("http"):
        return wf.normalize_base(head)
    hint = wf.normalize_base(hint or "")
    if hint and target.startswith(hint):
        return hint
    try:
        for ct in _bm().get_warehouse_contacts():
            base = wf.normalize_base(ct["url"])
            if base and target.startswith(base + "/"):
                return base
    except Exception:
        pass
    return hint


@router.post("/retweet")
async def retweet(request: Request):
    """피드·검색에서 본 파일을 내 창고 레벨 폴더에 링크 파일로 소개."""
    body = await _body(request)
    target = (body.get("url") or "").strip()
    if not (target.startswith("http://") or target.startswith("https://")):
        raise HTTPException(status_code=400, detail="가리킬 파일 주소(url)가 필요해요")
    level = body.get("level", 0)
    try:
        level = int(level)
    except Exception:
        level = 0
    if level < 0 or level > 4:
        raise HTTPException(status_code=400, detail="레벨은 0~4")
    name = _URLFILE_BAD.sub("_", (body.get("name") or "").strip()) or "링크"
    if name.lower().endswith(".url"):    # 리트윗의 리트윗 → .url.url 방지
        name = name[:-4] or "링크"
    import api_portal
    api_portal._ensure_warehouses()
    dest_dir = api_portal._warehouse_dir(level)
    fname, i = f"{name}.url", 2
    while (dest_dir / fname).exists():
        fname = f"{name} ({i}).url"
        i += 1
    # 파일 주소 + 그 파일이 사는 창고 주소를 함께 적는다. 파일은 지워지거나 옮겨져도
    # 창고는 남는다 — 구독자가 원 파일을 놓쳐도 출처 창고로 건너갈 수 있어야 발견이 이어진다.
    # (WarehouseURL 은 InternetShortcut 표준 밖 키 — 모르는 파서는 조용히 무시한다)
    wh = _source_warehouse(target, body.get("warehouse") or "")
    lines = ["[InternetShortcut]", f"URL={target}"]
    if wh:
        lines.append(f"WarehouseURL={wh}")
    (dest_dir / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"success": True, "file": fname, "level": level, "warehouse": wh}
