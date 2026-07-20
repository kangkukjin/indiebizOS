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
            # 방언 어댑터(2026-07-20): native 외에도 autoindex·rss·nextcloud·page 창고 지원
            "adapter": st.get("adapter") or "native",
            "adapter_label": warehouse_adapters.adapter_label(st.get("adapter")),
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
    # 호출자가 npub 을 안 줬으면(주소만 등록) 매니페스트의 자기선언 npub 을 앵커로 —
    # 주소만 아는 상대도 신원 있는 레코드로 합류해 "같은 사람 2명"을 처음부터 막는다.
    if not npub:
        m_npub = (poll.get("npub") or "").strip()
        npub = m_npub if m_npub.startswith("npub") else ""
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


def _allowed_urls(min_level: int, favorites: bool):
    """피드·검색 필터의 허용 창고 집합 — 내가 이웃에게 준 레벨(info_level)·즐겨찾기 기준.
    같은 주소에 여러 이웃이면 하나라도 조건을 넘으면 허용. 필터 없으면 None(전체)."""
    if min_level <= 0 and not favorites:
        return None
    allowed = set()
    for ct in _bm().get_warehouse_contacts():
        if int(ct.get("info_level") or 0) < min_level:
            continue
        if favorites and not ct.get("favorite"):
            continue
        allowed.add(wf.normalize_base(ct["url"]))
    return sorted(allowed)


@router.get("/feed")
async def feed(limit: int = 100, min_level: int = 0, favorites: int = 0):
    """타임라인 — 이웃 이름·창고 홈을 붙여 반환.
    min_level=그 레벨 이상 이웃만(레벨=숫자, 의미는 사용자가 정함) / favorites=즐겨찾기만."""
    names = _name_map()
    items = []
    for e in wf.get_feed(limit=limit, wh_urls=_allowed_urls(min_level, bool(favorites))):
        if e["wh_url"] not in names:
            continue  # 등기부에서 떼어진 창고의 잔여 이벤트는 숨김
        e["neighbor_name"] = names[e["wh_url"]]
        e["neighbor_home"] = e["wh_url"] + "/"
        items.append(e)
    return {"items": items}


@router.get("/search")
async def search(q: str = "", limit: int = 100, sort: str = "recent",
                 min_level: int = 0, favorites: int = 0):
    """전수 키워드 조사(검색 사다리 1층) — 이웃 전체 창고의 현재 파일명 색인에서.

    sort: recent=최신순(기본) / match=이름 일치순. min_level·favorites=피드와 같은 신뢰 필터.
    """
    names = _name_map()
    items = []
    for e in wf.search_snapshots(q, limit=limit, sort=sort,
                                 wh_urls=_allowed_urls(min_level, bool(favorites))):
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

_URLFILE_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
_RT_DIRNAME = "리트윗"
_COPY_TIMEOUT = 300          # 초 — 큰 파일 내려받기 여유
_COPY_MAX_BYTES = 4 * 1024 * 1024 * 1024   # 4GB 러너웨이 가드 (이보다 크면 link 를 권함)


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


def _like_remote(wh_base: str, path: str) -> dict:
    """이웃 창고의 /like 를 눌러준다(스레드에서 호출) — 손님 좋아요(그쪽에서 내 IP 단위)."""
    import requests
    r = requests.post(wh_base + "/like", json={"path": path},
                      timeout=20, headers={"User-Agent": wf._UA})
    r.raise_for_status()
    return r.json()


@router.post("/like")
async def like_neighbor_file(request: Request):
    """피드·검색에서 본 이웃 파일에 좋아요 — 카운터는 그 파일의 원 창고가 센다.
    성공하면 로컬 스냅샷의 하트 수도 즉시 갱신(다음 폴링을 안 기다림)."""
    body = await _body(request)
    wh_base = wf.normalize_base(body.get("wh_url") or "")
    path = (body.get("path") or "").strip()
    if not wh_base or not path:
        raise HTTPException(status_code=400, detail="wh_url 과 path 가 필요해요")
    try:
        res = await to_thread.run_sync(_like_remote, wh_base, path)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"좋아요를 전하지 못했어요: {e}")
    count = int(res.get("count") or 0)
    try:
        with wf._db_lock, wf._conn() as c:
            c.execute("UPDATE snapshots SET likes=? WHERE wh_url=? AND path=?",
                      (count, wh_base, path))
            c.execute("UPDATE feed SET likes=? WHERE wh_url=? AND path=?",
                      (count, wh_base, path))
    except Exception:
        pass
    return {"success": True, "liked": bool(res.get("liked")), "count": count}


def _chain_from_source(source_wh: str, target: str, path_hint: str) -> dict:
    """출처 사슬 계승 — 원 창고 매니페스트를 그 자리에서 한 번 읽어(폴러 캐시가 아니라
    현재 상태), 리트윗하려는 항목이 이미 리트윗이면 origin·hops 를 이어받는다.

    반환: {origin_warehouse, origin_url, origin_name, hops} — hops 는 *내 것 포함* 사슬 길이.
    매니페스트를 못 읽거나 항목을 못 찾으면 = 원 창고가 최초 제공자(hops 1)."""
    origin = {"origin_warehouse": source_wh, "origin_url": target,
              "origin_name": path_hint, "hops": 1}
    if not source_wh:
        return origin
    try:
        data = wf.fetch_manifest(source_wh)
    except Exception:
        return origin
    for f in (data.get("files") or []):
        if (f.get("url") or "") != target and (f.get("name") or "") != path_hint:
            continue
        rt = f.get("rt") or {}
        if rt.get("origin_url"):
            # 사슬이 이미 있다 — 최초 출처를 그대로 이어받고 한 홉 늘린다
            return {"origin_warehouse": rt.get("origin") or rt.get("origin_warehouse") or "",
                    "origin_url": rt["origin_url"],
                    "origin_name": rt.get("origin_name") or f.get("name") or path_hint,
                    "hops": int(rt.get("hops") or 1) + 1}
        if f.get("link"):
            # 구식 포인터(.url, 사이드카 없음) — 리트윗을 한 번 거친 것은 확실
            return {"origin_warehouse": f.get("warehouse") or "",
                    "origin_url": f.get("url") or target,
                    "origin_name": f.get("name") or path_hint, "hops": 2}
        break
    return origin


def _download_to(target: str, dest) -> int:
    """원 파일을 스트리밍으로 내려받는다(스레드에서 호출). 반환=바이트 수."""
    import requests
    total = 0
    with requests.get(target, stream=True, timeout=_COPY_TIMEOUT,
                      headers={"User-Agent": wf._UA}) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                total += len(chunk)
                if total > _COPY_MAX_BYTES:
                    raise ValueError("파일이 4GB를 넘어요 — 링크 리트윗을 쓰세요")
                fh.write(chunk)
    return total


def _unique_name(dest_dir, name: str) -> str:
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    fname, i = name, 2
    while (dest_dir / fname).exists():
        fname = f"{stem} ({i}).{ext}" if ext else f"{stem} ({i})"
        i += 1
    return fname


@router.post("/retweet")
async def retweet(request: Request):
    """피드·검색에서 본 파일을 내 창고 <레벨>/리트윗/ 에 소개.
    mode: "link"(기본, 포인터 .url=추천) | "copy"(파일 복사=전파·소유)."""
    body = await _body(request)
    target = (body.get("url") or "").strip()
    if not (target.startswith("http://") or target.startswith("https://")):
        raise HTTPException(status_code=400, detail="가리킬 파일 주소(url)가 필요해요")
    mode = (body.get("mode") or "link").strip().lower()
    if mode not in ("link", "copy"):
        raise HTTPException(status_code=400, detail="mode 는 link|copy")
    level = body.get("level", 0)
    try:
        level = int(level)
    except Exception:
        level = 0
    if level < 0 or level > 4:
        raise HTTPException(status_code=400, detail="레벨은 0~4")
    raw_path = (body.get("name") or "").strip()

    import api_portal
    api_portal._ensure_warehouses()
    dest_dir = api_portal._warehouse_dir(level) / _RT_DIRNAME
    dest_dir.mkdir(parents=True, exist_ok=True)

    wh = _source_warehouse(target, body.get("warehouse") or "")
    # 출처 사슬 + (copy 면) 파일 내려받기 — 둘 다 바깥 HTTP 라 스레드로 내린다
    # (이벤트 루프 위 동기 HTTP 금지 — 자기 창고 리트윗이 터널로 되돌아오는 경우 자기교착)
    chain = await to_thread.run_sync(_chain_from_source, wh, target, raw_path)

    if mode == "copy":
        # 파일명 = 경로의 마지막 조각(원 폴더 구조는 origin_name 이 기억한다)
        base_name = _URLFILE_BAD.sub("_", raw_path.rsplit("/", 1)[-1]) or "파일"
        if base_name.lower().endswith(".url"):
            base_name = base_name[:-4] or "파일"
        fname = _unique_name(dest_dir, base_name)
        dest = dest_dir / fname
        try:
            size = await to_thread.run_sync(_download_to, target, dest)
        except Exception as e:
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
            raise HTTPException(status_code=502, detail=f"원 파일을 못 가져왔어요: {e}")
    else:
        name = _URLFILE_BAD.sub("_", raw_path) or "링크"
        if name.lower().endswith(".url"):    # 리트윗의 리트윗 → .url.url 방지
            name = name[:-4] or "링크"
        fname = _unique_name(dest_dir, f"{name}.url")
        # 파일 주소 + 그 파일이 사는 창고 주소를 함께 적는다. 파일은 지워지거나 옮겨져도
        # 창고는 남는다 — 구독자가 원 파일을 놓쳐도 출처 창고로 건너갈 수 있어야 발견이 이어진다.
        # (WarehouseURL 은 InternetShortcut 표준 밖 키 — 모르는 파서는 조용히 무시한다)
        lines = ["[InternetShortcut]", f"URL={target}"]
        if wh:
            lines.append(f"WarehouseURL={wh}")
        (dest_dir / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")
        size = None

    # 사이드카 = 출처 사슬(최초 제공자·직전 창고·리트윗 횟수). dotfile 이라 매니페스트
    # walk 에서 숨고, _walk_accessible 이 읽어 rt 필드로 노출한다.
    from datetime import datetime
    sidecar = {
        "mode": mode,
        "origin_warehouse": chain["origin_warehouse"],
        "origin_url": chain["origin_url"],
        "origin_name": chain["origin_name"],
        "via_warehouse": wh,
        "hops": chain["hops"],
        "retweeted_at": datetime.now().isoformat(timespec="seconds"),
    }
    (dest_dir / f".{fname}.rt.json").write_text(
        json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8")

    return {"success": True, "mode": mode, "file": f"{_RT_DIRNAME}/{fname}",
            "level": level, "warehouse": wh,
            "origin": chain["origin_warehouse"], "hops": chain["hops"],
            **({"bytes": size} if size is not None else {})}
