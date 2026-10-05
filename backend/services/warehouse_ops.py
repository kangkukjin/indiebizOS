"""warehouse_ops.py — 이웃 창고(공유창고 피드) 낱말 `[others:warehouse]` (2026-10-05, 설치 목록 ⑩).

조종실 라우트(api_warehouse_feed)에만 살던 허용 창고 필터·좋아요·리트윗 논리를 여기로 내려 HTTP 와 IBL 이 같은 함수를
부른다. 저장소는 warehouse_feed(SQLite)·business_manager 그대로. HTTP 호출(좋아요·리트윗 내려받기)은 동기 — 호출자가
스레드로 내린다(IBL 은 워커 스레드, 라우트는 to_thread).
"""
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import warehouse_feed as wf

_URLFILE_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
RT_DIRNAME = "리트윗"
COPY_TIMEOUT = 300
COPY_MAX_BYTES = 4 * 1024 * 1024 * 1024
LIMIT_MAX = 500   # feed·search 한 번의 상한 — 넘는 요청은 clamped 로 신고


def _bm():
    from business_manager import BusinessManager
    return BusinessManager()


def allowed_urls(min_level: int = 0, favorites: bool = False, min_score: int = 0) -> Optional[list]:
    """피드·검색 필터의 허용 창고 집합 — min_level(내가 이웃에게 준 레벨) ∩ favorites ∩ min_score(내가 창고에 준 점수). 없으면 None(전체)."""
    if min_level <= 0 and not favorites and min_score <= 0:
        return None
    scores = wf.get_scores_map() if min_score > 0 else {}
    allowed = set()
    for ct in _bm().get_warehouse_contacts():
        base = wf.normalize_base(ct["url"])
        if int(ct.get("info_level") or 0) < min_level:
            continue
        if favorites and not ct.get("favorite"):
            continue
        if min_score > 0 and int(scores.get(base) or 0) < min_score:
            continue
        allowed.add(base)
    return sorted(allowed)


def source_warehouse(target: str, hint: str = "") -> str:
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


def like(wh_url: str, path: str) -> dict:
    """이웃 창고의 /like 를 눌러준다(카운터는 그쪽이 센다) + 로컬 스냅샷 하트 수 즉시 갱신. 동기 HTTP."""
    import requests
    wh_base = wf.normalize_base(wh_url or "")
    path = (path or "").strip()
    if not wh_base or not path:
        raise ValueError("wh_url 과 path 가 필요해요")
    r = requests.post(wh_base + "/like", json={"path": path}, timeout=20, headers={"User-Agent": wf._UA})
    r.raise_for_status()
    res = r.json()
    count = int(res.get("count") or 0)
    try:
        with wf._db_lock, wf._conn() as c:
            c.execute("UPDATE snapshots SET likes=? WHERE wh_url=? AND path=?", (count, wh_base, path))
            c.execute("UPDATE feed SET likes=? WHERE wh_url=? AND path=?", (count, wh_base, path))
    except Exception:
        pass
    return {"success": True, "liked": bool(res.get("liked")), "count": count}


def _chain_from_source(source_wh: str, target: str, path_hint: str) -> dict:
    origin = {"origin_warehouse": source_wh, "origin_url": target, "origin_name": path_hint, "hops": 1}
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
            return {"origin_warehouse": rt.get("origin") or rt.get("origin_warehouse") or "",
                    "origin_url": rt["origin_url"], "origin_name": rt.get("origin_name") or f.get("name") or path_hint,
                    "hops": int(rt.get("hops") or 1) + 1}
        if f.get("link"):
            return {"origin_warehouse": f.get("warehouse") or "", "origin_url": f.get("url") or target,
                    "origin_name": f.get("name") or path_hint, "hops": 2}
        break
    return origin


def _download_to(target: str, dest: Path) -> int:
    import requests
    total = 0
    with requests.get(target, stream=True, timeout=COPY_TIMEOUT, headers={"User-Agent": wf._UA}) as r:
        r.raise_for_status()
        with open(dest, "wb") as fh:
            for chunk in r.iter_content(chunk_size=1024 * 256):
                if not chunk:
                    continue
                total += len(chunk)
                if total > COPY_MAX_BYTES:
                    raise ValueError("파일이 4GB를 넘어요 — 링크 리트윗을 쓰세요")
                fh.write(chunk)
    return total


def _unique_name(dest_dir: Path, name: str) -> str:
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    fname, i = name, 2
    while (dest_dir / fname).exists():
        fname = f"{stem} ({i}).{ext}" if ext else f"{stem} ({i})"
        i += 1
    return fname


def retweet(url: str, name: str = "", level: int = 0, mode: str = "link", warehouse: str = "") -> dict:
    """피드·검색에서 본 파일을 내 창고 <레벨>/리트윗/ 에 소개. mode link(포인터 .url)|copy(파일 복사). 동기 HTTP."""
    import warehouse_paths as WP
    target = (url or "").strip()
    if not (target.startswith("http://") or target.startswith("https://")):
        raise ValueError("가리킬 파일 주소(url)가 필요해요")
    mode = (mode or "link").strip().lower()
    if mode not in ("link", "copy"):
        raise ValueError("mode 는 link|copy")
    lv = WP.check_level(level)
    raw_path = (name or "").strip()
    WP.ensure_dirs()
    dest_dir = WP.warehouse_dir(lv) / RT_DIRNAME
    dest_dir.mkdir(parents=True, exist_ok=True)
    wh = source_warehouse(target, warehouse or "")
    chain = _chain_from_source(wh, target, raw_path)
    size = None
    if mode == "copy":
        base_name = _URLFILE_BAD.sub("_", raw_path.rsplit("/", 1)[-1]) or "파일"
        if base_name.lower().endswith(".url"):
            base_name = base_name[:-4] or "파일"
        fname = _unique_name(dest_dir, base_name)
        dest = dest_dir / fname
        try:
            size = _download_to(target, dest)
        except Exception:
            dest.unlink(missing_ok=True)
            raise
    else:
        nm = _URLFILE_BAD.sub("_", raw_path) or "링크"
        if nm.lower().endswith(".url"):
            nm = nm[:-4] or "링크"
        fname = _unique_name(dest_dir, f"{nm}.url")
        lines = ["[InternetShortcut]", f"URL={target}"] + ([f"WarehouseURL={wh}"] if wh else [])
        (dest_dir / fname).write_text("\n".join(lines) + "\n", encoding="utf-8")
    sidecar = {"mode": mode, "origin_warehouse": chain["origin_warehouse"], "origin_url": chain["origin_url"],
               "origin_name": chain["origin_name"], "via_warehouse": wh, "hops": chain["hops"],
               "retweeted_at": datetime.now().isoformat(timespec="seconds")}
    (dest_dir / f".{fname}.rt.json").write_text(json.dumps(sidecar, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"success": True, "mode": mode, "file": f"{RT_DIRNAME}/{fname}", "level": lv, "warehouse": wh,
            "origin": chain["origin_warehouse"], "hops": chain["hops"], **({"bytes": size} if size is not None else {})}


def _int(v, default=0):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def _limit(params: dict, default: int = 50) -> tuple:
    """(적용 limit, 신고 필드) — 상한을 넘긴 요청은 깎되 응답에 clamped·requested 를 싣는다."""
    requested = _int(params.get("limit"), default)
    limit = max(1, min(LIMIT_MAX, requested))
    return limit, ({"clamped": True, "requested": requested, "limit": limit} if requested != limit else {})


def warehouse_op(params: dict) -> Any:
    """[others:warehouse] — 이웃 창고 피드의 읽기·소통."""
    op = (params.get("op") or "feed").strip()
    try:
        if op == "neighbors":
            rows = _bm().get_warehouse_contacts()
            status, scores = wf.get_status_map(), wf.get_scores_map()
            out = []
            for ct in rows:
                base = wf.normalize_base(ct["url"])
                out.append({**ct, "base": base, "status": status.get(base) or {}, "score": scores.get(base, 0)})
            return {"success": True, "items": out, "count": len(out)}
        if op == "poll":
            url = (params.get("url") or "").strip()
            if url:
                return {"success": True, "result": wf.poll_warehouse(url)}
            rows = wf.poll_all()
            return {"success": True, "items": rows, "count": len(rows)}
        if op == "feed":
            urls = allowed_urls(_int(params.get("min_level")), bool(params.get("favorites")), _int(params.get("min_score")))
            limit, note = _limit(params, 50)
            rows = wf.get_feed(limit=limit, wh_url=params.get("url") or None, group=False, wh_urls=urls, cards=False)
            return {"success": True, "items": rows, "count": len(rows), "filter": {"urls": urls}, **note}
        if op == "browse":
            url = (params.get("url") or "").strip()
            if not url:
                return {"success": False, "error": "browse 에는 url(이웃 창고 주소)이 필요합니다"}
            res = wf.browse_snapshots(url, params.get("path") or "")
            return {"success": True, **res} if isinstance(res, dict) else {"success": True, "items": res}
        if op == "search":
            q = (params.get("query") or params.get("q") or "").strip()
            if not q:
                return {"success": False, "error": "search 에는 query 가 필요합니다"}
            urls = allowed_urls(_int(params.get("min_level")), bool(params.get("favorites")), _int(params.get("min_score")))
            limit, note = _limit(params, 50)
            rows = wf.search_snapshots(q, limit=limit, sort=params.get("sort") or "recent", wh_urls=urls)
            return {"success": True, "items": rows, "count": len(rows), **note}
        if op == "like":
            return like(params.get("url") or params.get("wh_url") or "", params.get("path") or "")
        if op == "retweet":
            return retweet(params.get("url") or "", params.get("name") or "", _int(params.get("level")),
                           params.get("mode") or "link", params.get("warehouse") or "")
        if op == "score":
            url = (params.get("url") or "").strip()
            if not url:
                return {"success": False, "error": "score 에는 url 과 score(0~3)가 필요합니다"}
            return {"success": True, **(wf.set_score(url, _int(params.get("score"))) or {})}
        if op == "memo":
            nid = params.get("neighbor_id")
            if not nid:
                return {"success": False, "error": "memo 에는 neighbor_id 와 memo 가 필요합니다"}
            _bm().update_neighbor_warehouse(int(nid), warehouse_memo=str(params.get("memo") or ""))
            return {"success": True, "neighbor_id": int(nid), "memo": str(params.get("memo") or "")}
        if op == "forget":
            url = (params.get("url") or "").strip()
            if not url:
                return {"success": False, "error": "forget 에는 url 이 필요합니다"}
            base = wf.normalize_base(url)
            removed = 0
            for ct in _bm().get_warehouse_contacts():
                if wf.normalize_base(ct["url"]) == base and ct.get("id"):
                    _bm().delete_contact(ct["id"]); removed += 1
            wf.forget_warehouse(base)
            return {"success": True, "forgot": base, "contacts_removed": removed}
    except ValueError as exc:
        return {"success": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 — 바깥 HTTP·DB 오류는 정직하게
        return {"success": False, "error": f"{type(exc).__name__}: {exc}"}
    return {"success": False, "error": f"알 수 없는 op: {op} (neighbors|poll|feed|browse|search|like|retweet|score|memo|forget)"}
