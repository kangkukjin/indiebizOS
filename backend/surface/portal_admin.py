"""portal_admin.py — 창고 관리(소유자 전용). 런처 '공유창고' 표면(데스크탑·원격)이 부른다.

  · /portal/warehouse-admin/{list,add,remove,move,mkdir,trash,restore,trash-delete,file,upload,gb}

★공개 면이 아니다 — is_public_remote_path 에 등록돼 있지 않아 런처 세션 게이트 뒤에 있다
(그래서 이 파일의 라우트만 `_check_secret` 을 안 부른다). 공개로 착각해 시크릿 게이트를
빼거나, 반대로 여기를 공개 목록에 등록하는 순간 남의 창고를 남이 편집하게 된다.

api_portal.py 분할(2026-08-05 감사 부채 ⑨).
"""

import os
import json
import time
import asyncio
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request

from portal_base import _core
from portal_warehouse import (
    _WAREHOUSE_LEVELS, _WAREHOUSE_ROOT, _GB_LOCK,
    _ensure_warehouses, _gb_load, _gb_save, _parse_urlfile, _safe_rel,
    _serve_warehouse_file, _warehouse_dir, _warehouse_title,
)

router = APIRouter()


import warehouse_admin   # ⑩ 내 창고 관리의 정본(IBL [self:warehouse] 와 같은 함수)


async def _json(request: Request) -> dict:
    try:
        return json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")


def _svc(fn, *args):
    """서비스 예외 → HTTP: ValueError/FileExistsError=400·409, LookupError=404."""
    try:
        return fn(*args)
    except FileExistsError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))

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
def warehouse_admin_list(level: int = 0):  # 동기 def=스레드풀: 블로킹 작업이 이벤트 루프를 막지 않게(check_event_loop)
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
        entry = {"name": str(p.relative_to(d)), "bytes": st.st_size, "path": str(p),
                 "mtime": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}
        # 리트윗 포인터(.url) — 공개면(_walk_accessible)과 동형으로 target 해석.
        # 없으면 로컬 창고 창이 포인터를 일반 파일로 취급해 다운로드한다(2026-07-28 신고).
        if p.name.lower().endswith(".url") and st.st_size <= 4096:
            target, warehouse = _parse_urlfile(p)
            if target:
                entry["link"] = target
                if warehouse:
                    entry["warehouse"] = warehouse
        files.append(entry)
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
    # 폴더 rglob·copytree·copy2 는 워커 스레드로 — 이벤트 루프 위에서 폴더를 통째로 복사하면
    # 서버 전체가 선다(2026-09-03 사진 스캔 사고와 같은 부류).
    return await asyncio.to_thread(_warehouse_admin_add_sync, body)


def _warehouse_admin_add_sync(body: dict) -> dict:
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
    body = await _json(request)
    return await asyncio.to_thread(_svc, warehouse_admin.remove, body.get("level", 0), str(body.get("name", "")))

@router.post("/warehouse-admin/move")
async def warehouse_admin_move(request: Request):
    """창고 안에서 옮기기·이름변경 — 구현은 warehouse_admin.move([self:warehouse]{op:move} 와 같은 함수)."""
    body = await _json(request)
    return await asyncio.to_thread(_svc, warehouse_admin.move, body.get("level", 0), str(body.get("name", "")),
                                   str(body.get("dest", "")), body.get("dest_level"), str(body.get("new_name", "")))

@router.post("/warehouse-admin/mkdir")
async def warehouse_admin_mkdir(request: Request):
    body = await _json(request)
    return await asyncio.to_thread(_svc, warehouse_admin.mkdir, body.get("level", 0), str(body.get("name", "")), str(body.get("dest", "")))

@router.get("/warehouse-admin/trash")
def warehouse_admin_trash():  # 동기 def=스레드풀
    return warehouse_admin.trash_list()

@router.post("/warehouse-admin/restore")
async def warehouse_admin_restore(request: Request):
    body = await _json(request)
    return await asyncio.to_thread(_svc, warehouse_admin.restore, body.get("level", 0), str(body.get("name", "")))

@router.post("/warehouse-admin/trash-delete")
async def warehouse_admin_trash_delete(request: Request):
    """휴지통 영구 삭제 — {level, name} 단건 또는 {all: true}. 구현은 warehouse_admin.purge(여기만 파괴적)."""
    body = await _json(request)
    return await asyncio.to_thread(_svc, warehouse_admin.purge, body.get("level", 0), str(body.get("name", "")), bool(body.get("all")))


@router.get("/warehouse-admin/file")
def warehouse_admin_file(level: int = 0, name: str = "", download: int = 0):  # 동기 def=스레드풀: 블로킹 작업이 이벤트 루프를 막지 않게(check_event_loop)
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
