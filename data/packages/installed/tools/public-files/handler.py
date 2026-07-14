"""
public-files/handler.py
공개파일 노출 층 — 선택 폴더를 외부 공개 사이트(Cloudflare R2 + Worker)로 비춘다.

이음매(헌법 1조): 이 핸들러(맥, superstructure)는 썸네일·매니페스트를 만들어 R2 로
push 한다. 공개 Worker(substrate)는 manifest.json 계약(docs/PUBLIC_FILES_APP_DESIGN.md §6)만
안다. 앱을 지워도 사이트는 마지막 동기화 상태로 산다.

P0 = 어휘 골격. add/remove/sync/config/status 는 상태 파일(showcase_state.json)만
읽고 쓰는 스텁이다. 썸네일 생성(self:photo 재사용)·R2 push·Worker 는 P1~P3 에서 채운다.
"""

import sys
import json
import secrets
from pathlib import Path

# 프로젝트 루트 = data/packages/installed/tools/public-files/handler.py 에서 5단계 위.
_ROOT = Path(__file__).resolve().parents[5]

# backend/common 통화 생성자
_BACKEND = str(_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from common.currency import items  # IBL 단일 통화 생성자

# 상태·설정 영속 (auto_response_state.json 선례) — data/showcase_state.json
_DATA_DIR = _ROOT / "data"
_STATE_PATH = _DATA_DIR / "showcase_state.json"

# 로컬 스테이징 — R2 버킷과 동일 레이아웃(P2 는 이 디렉토리를 그대로 업로드).
#   showcase_stage/manifest.json
#   showcase_stage/thumbs/<folder_id>/<item_id>.jpg
#   showcase_stage/media/<folder_id>/<item_id>.<ext>   (P4 push_originals)
_STAGE_DIR = _DATA_DIR / "showcase_stage"
_THUMB_SIZE = 512
# 점진적 표시 — 이만큼 처리할 때마다 부분 manifest+썸네일을 R2 로 flush 해서
# 거대 폴더도 그리드가 실시간으로 자라게(폴더 완주 후 all-or-nothing 아님).
_FLUSH_EVERY = 200
_EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", ".Trash", "thumbnail_cache"}

_DEFAULT_SETTINGS = {
    "access": "link_only",       # link_only | public
    "strip_exif": True,          # 위치·EXIF 제거 후 업로드
    "push_originals": True,       # false면 썸네일만
    "transcode_video": True,      # .mov/HEVC/MKV → H.264 MP4
    "on_uninstall": "freeze",     # freeze | purge
    "r2_bucket": "",
    "public_base": "",            # 공개 사이트 base URL
    "link_token": "",             # link_only 접근 토큰
}


def _load_state() -> dict:
    """상태 로드 (없으면 기본). {settings, folders:[...], baskets:[...]}"""
    if _STATE_PATH.exists():
        try:
            st = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            st = {}
    else:
        st = {}
    settings = {**_DEFAULT_SETTINGS, **(st.get("settings") or {})}
    return {
        "settings": settings,
        "folders": st.get("folders") or [],
        # 바스켓(공간) = 여러 비밀 공개주소. 각 바스켓은 folder_ids 부분집합을
        # 자기 slug(긴 랜덤 토큰) 아래 spaces/<slug>/manifest.json 으로 비춘다.
        "baskets": st.get("baskets") or [],
    }


import threading
from contextlib import contextmanager

_SAVE_LOCK = threading.Lock()
_SYNCING: set = set()          # 현재 백그라운드 동기화 중인 folder id (재진입 방지)
_SYNC_GUARD = threading.Lock()
# read-modify-write 직렬화 — 백그라운드 sync 의 잦은 진행상황 기록이 사용자의
# 폴더 토글(hidden/title)을 덮어쓰는 lost-update 방지. RLock 이라 같은 스레드
# 재진입(_locked_state 안에서 _update_folder 호출 등) 안전.
_STATE_LOCK = threading.RLock()


def _save_state(state: dict) -> None:
    # 원자적 저장 — 백그라운드 동기화 스레드와 status 읽기가 겹쳐도 torn read 방지.
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _SAVE_LOCK:
        tmp = _STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_STATE_PATH)


@contextmanager
def _locked_state():
    """state 를 락 안에서 새로 읽어 넘기고, 블록 종료 시 저장. 모든 writer 가
    이걸 쓰면 load→modify→save 가 원자적이라 lost-update 가 사라진다.
    ★네트워크(R2)·스레드 시작은 되도록 이 블록 밖에서 — 락 보유시간 최소화."""
    with _STATE_LOCK:
        st = _load_state()
        yield st
        _save_state(st)


def _public_url(settings: dict, folder: dict) -> str:
    """폴더의 공개 URL 조립 (P3 Worker 배포 전엔 base 미설정 → 빈 문자열)."""
    base = (settings.get("public_base") or "").rstrip("/")
    if not base:
        return ""
    fid = folder.get("id") or ""
    url = f"{base}/f/{fid}" if fid else base
    if settings.get("access") == "link_only" and settings.get("link_token"):
        url += f"?t={settings['link_token']}"
    return url


def _canon(path: str) -> str:
    """경로를 canonical 절대경로로 — add 저장 형태와 sync/remove 매칭 형태를 일치."""
    if not path:
        return ""
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:
        return str(path).strip()


def _folder_id(path: str) -> str:
    """경로 → 안정적 폴더 id (basename 슬러그).
    ★macOS 파일시스템은 한글을 NFD(분해형 자모 U+1100대)로 준다 — 그대로 슬러그하면
    조합형 범위 '가-힣'(U+AC00~)에 안 걸려 전부 치환·빈 슬러그→'fld_root' 됨.
    NFC 정규화로 분해 자모를 조합 음절로 되돌린 뒤 슬러그(예: '사진자료모음'→fld_사진자료모음)."""
    import re, unicodedata
    base = unicodedata.normalize("NFC", Path(path).name or "root")
    slug = re.sub(r"[^a-zA-Z0-9가-힣_-]+", "-", base).strip("-").lower()
    return f"fld_{slug}" if slug else "fld_root"


def _fmt_bytes(n: int) -> str:
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or unit == "TB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


def _folder_row(settings: dict, f: dict) -> dict:
    """폴더 → 표시 통화(title/meta/path/url) + 구조 필드."""
    count = f.get("count", 0)
    synced = f.get("synced_at") or "미동기화"
    hidden = bool(f.get("hidden"))
    vis = "🔒 비공개" if hidden else "🌐 공개"
    if f.get("syncing"):
        done, tot = f.get("sync_done", 0), f.get("sync_total", 0)
        meta = f"⏳ 동기화 중… {done}/{tot}장" if tot else "⏳ 동기화 준비 중…"
    elif f.get("interrupted") and not count:
        meta = "⚠️ 동기화 중단됨 — '동기화' 눌러 다시"
    else:
        meta = f"{vis} · {count}개 · {_fmt_bytes(f.get('bytes', 0))} · {synced}"
    return {
        "title": f.get("title") or Path(f.get("path", "")).name,
        "meta": meta,
        "path": f.get("path", ""),
        # 비공개면 공개 URL 없음(목록·접근 둘 다 막힘).
        "url": "" if hidden else _public_url(settings, f),
        "id": f.get("id", ""),
        "mode": f.get("mode", "media"),
        "count": count,
        "hidden": hidden,
        # 앱 토글 라벨(list_action 버튼) — 현재 상태의 반대 동작.
        "vis_action": "공개로" if hidden else "비공개로",
    }


# === P1 로컬 동기화 — 폴더 walk + 썸네일(공유 모듈) + manifest.json ===

def _item_id(abspath: str) -> str:
    import hashlib
    return "it_" + hashlib.md5(abspath.encode("utf-8")).hexdigest()[:12]


def _iter_files(folder_path: str, mode: str):
    """폴더를 walk 하며 파일 절대경로 yield. media 모드=사진·동영상만."""
    import os
    from thumbnails import classify
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d not in _EXCLUDE_DIRS and not d.startswith(".")]
        for fn in sorted(files):
            if fn.startswith("."):
                continue
            ap = os.path.join(root, fn)
            if mode == "media" and classify(ap) is None:
                continue
            yield ap


def _sync_folder(folder: dict, files: list = None, progress_cb=None, flush_cb=None) -> tuple:
    """폴더 하나 동기화 — 썸네일을 스테이징에 생성, (items[], total_bytes) 반환.
    증분: 썸네일이 원본보다 새로우면 재생성 스킵. progress_cb(done,total) 주기 호출.
    flush_cb(items_so_far, index_so_far) 를 _FLUSH_EVERY 마다 호출 → 점진적 R2 반영."""
    import os
    from thumbnails import generate_thumbnail, classify
    fid = folder["id"]
    mode = folder.get("mode", "media")
    thumb_dir = _STAGE_DIR / "thumbs" / fid
    if files is None:
        files = list(_iter_files(folder["path"], mode))
    n_total = len(files)
    out, total, index = [], 0, {}
    for i, ap in enumerate(files):
        try:
            size = os.path.getsize(ap)
        except OSError:
            continue
        total += size
        iid = _item_id(ap)
        kind = classify(ap) or "file"
        # 발행 루트 기준 하위 디렉토리(공개 사이트가 원본 폴더 구조를 그대로 탐색하도록).
        rel = os.path.relpath(os.path.dirname(ap), folder["path"])
        entry = {"id": iid, "title": os.path.basename(ap), "kind": kind, "size": size,
                 "dir": "" if rel == "." else rel.replace(os.sep, "/")}
        if kind in ("photo", "video"):
            dst = thumb_dir / f"{iid}.jpg"
            fresh = dst.exists() and dst.stat().st_mtime >= os.path.getmtime(ap)
            if not fresh:
                generate_thumbnail(ap, str(dst), _THUMB_SIZE, kind)
            if dst.exists():
                entry["thumb"] = f"thumbs/{fid}/{iid}.jpg"
            # src = 온디맨드 원본 경로(Worker 가 R2 캐시 없으면 맥에서 끌어옴).
            entry["src"] = f"media/{fid}/{iid}"
        index[iid] = ap  # 비공개 색인(맥 전용, R2 미업로드) — item_id→실제 경로
        out.append(entry)
        if progress_cb and (i + 1) % 100 == 0:
            progress_cb(i + 1, n_total)
        if flush_cb and (i + 1) % _FLUSH_EVERY == 0:
            flush_cb(out, index)  # 점진적: 부분 manifest+새 썸네일 R2 반영
    return out, total, index


def _manifest_path():
    return _STAGE_DIR / "manifest.json"


def _origin_index_path():
    # 비공개 색인(맥 전용) — item_id→실제 경로. R2 에 절대 올리지 않는다.
    return _STAGE_DIR / "_origin_index.json"


def _load_origin_index() -> dict:
    p = _origin_index_path()
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def _save_origin_index(full: dict) -> None:
    _STAGE_DIR.mkdir(parents=True, exist_ok=True)
    _origin_index_path().write_text(json.dumps(full, ensure_ascii=False), encoding="utf-8")


# === 폴더별 items 저장소 ===
# items 를 루트 manifest 안이 아니라 폴더별 파일(showcase_stage/items/<fid>.json)에
# 둔다. 이래야 hidden(루트 비공개)이라 루트 manifest 에서 빠진 폴더도 items 가 살아
# 바스켓 manifest 를 조립할 수 있다(루트 공개 ↔ 바스켓 소속이 독립).

def _items_dir() -> Path:
    return _STAGE_DIR / "items"


def _items_path(fid: str) -> Path:
    return _items_dir() / f"{fid}.json"


def _save_items(fid: str, items_list: list) -> None:
    _items_dir().mkdir(parents=True, exist_ok=True)
    _items_path(fid).write_text(json.dumps(items_list, ensure_ascii=False), encoding="utf-8")


def _load_items(fid: str) -> list:
    """폴더 items 로드. 폴더별 파일 우선, 없으면 옛 루트 manifest 에서 백필
    (per-folder store 도입 전 동기화된 폴더를 재동기화 없이 이관)."""
    p = _items_path(fid)
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            pass
    # 백필 — 기존 루트 manifest.json 에 남아 있으면 거기서.
    mf = _manifest_path()
    if mf.exists():
        try:
            m = json.loads(mf.read_text(encoding="utf-8"))
            for f in m.get("folders", []):
                if f.get("id") == fid:
                    return f.get("items", [])
        except Exception:
            pass
    return []


def _delete_items(fid: str) -> None:
    p = _items_path(fid)
    if p.exists():
        try:
            p.unlink()
        except OSError:
            pass


def _manifest_dict(state: dict, folders_src: list) -> dict:
    """folders_src(폴더 리스트)로 manifest 계약(§6) dict 조립. items 는 폴더별 저장소에서."""
    settings = state["settings"]
    folders = []
    for f in folders_src:
        folders.append({
            "id": f["id"],
            "title": f.get("title") or Path(f.get("path", "")).name,
            "mode": f.get("mode", "media"),
            "count": f.get("count", 0),
            "items": _load_items(f["id"]),
        })
    return {
        "version": 1,
        "title": "공개파일",
        "access": settings.get("access", "link_only"),
        "token_required": settings.get("access", "link_only") == "link_only",
        "folders": folders,
    }


def _write_manifest(state: dict) -> None:
    """루트 manifest.json + fids.json 재작성 — 비공개(hidden) 제외한 폴더만."""
    visible = [f for f in state["folders"] if not f.get("hidden")]
    manifest = _manifest_dict(state, visible)
    _STAGE_DIR.mkdir(parents=True, exist_ok=True)
    _manifest_path().write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    # fids.json — Worker 가 bare /thumbs·/media 접근을 루트 공개 폴더로만 게이트.
    _fids_path().write_text(
        json.dumps([f["id"] for f in visible], ensure_ascii=False), encoding="utf-8"
    )


# === 바스켓(공간) — 여러 비밀 공개주소 ===

def _fids_path() -> Path:
    return _STAGE_DIR / "fids.json"


def _basket_id() -> str:
    return "bsk_" + secrets.token_hex(6)


def _new_slug() -> str:
    # 긴 랜덤 토큰(≈22자, ~128bit) — 주소 자체가 비밀(추측 불가). "링크 아는 사람만".
    return secrets.token_urlsafe(16)


def _basket_url(settings: dict, basket: dict) -> str:
    base = (settings.get("public_base") or "").rstrip("/")
    slug = basket.get("slug") or ""
    return f"{base}/s/{slug}" if base and slug else ""


def _basket_stage_dir(slug: str) -> Path:
    return _STAGE_DIR / "spaces" / slug


def _basket_folders(state: dict, basket: dict) -> list:
    """바스켓에 담긴 폴더 객체들(folder_ids 순서, 존재하는 것만)."""
    by_id = {f["id"]: f for f in state["folders"]}
    return [by_id[fid] for fid in basket.get("folder_ids", []) if fid in by_id]


def _write_basket_local(state: dict, basket: dict) -> None:
    """바스켓 manifest.json + fids.json 을 스테이징에 기록(spaces/<slug>/)."""
    folders = _basket_folders(state, basket)
    manifest = _manifest_dict(state, folders)
    manifest["title"] = basket.get("title") or "공개파일"
    d = _basket_stage_dir(basket["slug"])
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (d / "fids.json").write_text(
        json.dumps([f["id"] for f in folders], ensure_ascii=False), encoding="utf-8")


def _baskets_with_folder(state: dict, fid: str) -> list:
    return [b for b in state.get("baskets", []) if fid in b.get("folder_ids", [])]


def _folder_served_anywhere(state: dict, fid: str) -> bool:
    """폴더가 어디든 공개 중인가 — 루트 공개(non-hidden) 또는 바스켓 소속."""
    f = next((x for x in state["folders"] if x.get("id") == fid), None)
    if f and not f.get("hidden"):
        return True
    return bool(_baskets_with_folder(state, fid))


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _upload_partial_r2(state: dict, fid: str, items_so_far: list, uploaded_iids: set) -> int:
    """지금까지 만든 썸네일 중 **아직 안 올린 것만** + manifest.json 을 R2 로 업로드.
    uploaded_iids(참조로 전달) 로 재업로드 회피 → 거대 폴더 flush 가 싸다. 올린 수 반환."""
    from r2_client import is_configured, put_object
    bucket = state["settings"].get("r2_bucket")
    if not is_configured() or not bucket:
        return 0
    tdir = _STAGE_DIR / "thumbs" / fid
    n = 0
    for it in items_so_far:
        iid = it.get("id")
        if not iid or iid in uploaded_iids:
            continue
        tf = tdir / f"{iid}.jpg"
        if tf.exists():
            ok, _ = put_object(bucket, f"thumbs/{fid}/{tf.name}", tf.read_bytes())
            if ok:
                uploaded_iids.add(iid)
                n += 1
    mf = _manifest_path()
    if mf.exists():
        put_object(bucket, "manifest.json", mf.read_bytes(), "application/json")
    fp = _fids_path()
    if fp.exists():
        put_object(bucket, "fids.json", fp.read_bytes(), "application/json")
    return n


def _r2_upload_basket(state: dict, basket: dict) -> None:
    """바스켓의 스테이징 manifest.json + fids.json 을 R2 spaces/<slug>/ 로 push.
    담긴 폴더의 썸네일은 전역(thumbs/<fid>) 공유라 재업로드 불필요(sync 가 이미 올림)."""
    from r2_client import is_configured, put_object
    bucket = state["settings"].get("r2_bucket")
    if not is_configured() or not bucket:
        return
    slug = basket.get("slug")
    if not slug:
        return
    _write_basket_local(state, basket)
    d = _basket_stage_dir(slug)
    for name in ("manifest.json", "fids.json"):
        p = d / name
        if p.exists():
            put_object(bucket, f"spaces/{slug}/{name}", p.read_bytes(), "application/json")


def _r2_delete_basket(state: dict, slug: str) -> None:
    from r2_client import is_configured, delete_object
    bucket = state["settings"].get("r2_bucket")
    if not is_configured() or not bucket or not slug:
        return
    for name in ("manifest.json", "fids.json"):
        delete_object(bucket, f"spaces/{slug}/{name}")


def _refresh_baskets_for_folder(state: dict, fid: str) -> None:
    """폴더 items 가 바뀌면(sync/remove) 그 폴더를 담은 모든 바스켓 manifest 재빌드·업로드."""
    for b in _baskets_with_folder(state, fid):
        _r2_upload_basket(state, b)


def _update_folder(path: str, **kv) -> None:
    """state 에서 폴더 하나의 필드만 갱신(진행상황 기록용). 락 안에서 최신 state 를
    다시 읽어 델타(kv)만 적용 → 동시에 바뀐 사용자 토글(hidden/title)을 덮어쓰지 않음."""
    with _STATE_LOCK:
        st = _load_state()
        f = next((x for x in st["folders"] if x.get("path") == path), None)
        if f:
            f.update(kv)
            _save_state(st)


def _bg_sync_worker(paths: list) -> None:
    """백그라운드 동기화 스레드 — 폴더별 썸네일 생성·manifest·R2 업로드. 진행상황을 state 에 기록.
    ★거대 폴더(수만 장)도 백엔드를 막지 않도록 요청 밖 스레드에서 실행."""
    for path in paths:
        state = _load_state()
        folder = next((f for f in state["folders"] if f.get("path") == path), None)
        if not folder:
            continue
        fid = folder["id"]
        with _SYNC_GUARD:
            if fid in _SYNCING:
                continue
            _SYNCING.add(fid)
        try:
            files = list(_iter_files(path, folder.get("mode", "media")))
            _update_folder(path, syncing=True, interrupted=False, sync_total=len(files), sync_done=0)

            # 점진적 flush — _FLUSH_EVERY 장마다 부분 manifest+새 썸네일을 R2 로 올려
            # 그리드가 실시간으로 자라게. uploaded_iids 로 재업로드 회피(거대 폴더도 쌈).
            uploaded_iids: set = set()

            def _flush(items_so_far, index_so_far):
                with _STATE_LOCK:
                    st_f = _load_state()
                    ff = next((x for x in st_f["folders"] if x.get("path") == path), None)
                    if not ff or not _folder_served_anywhere(st_f, fid):
                        return  # 도중 제거 / (루트 비공개 && 바스켓에도 없음)이면 flush 스킵
                    full = _load_origin_index()
                    full[fid] = dict(index_so_far)   # 클릭 시 원본 해소되도록 부분 색인
                    _save_origin_index(full)
                    ff["count"] = len(items_so_far)  # 그리드 헤더 진행 반영(state 저장은 안 함)
                    _save_items(fid, list(items_so_far))
                    _write_manifest(st_f)
                _upload_partial_r2(st_f, fid, items_so_far, uploaded_iids)  # 네트워크는 락 밖

            items_list, total, index = _sync_folder(
                folder, files=files,
                progress_cb=lambda done, tot: _update_folder(path, sync_done=done),
                flush_cb=_flush,
            )
            # 비공개 색인 저장(item_id→경로, 맥 전용) — 온디맨드 원본 끌어오기용.
            # 같은 락으로 remove/config 의 origin 색인 pop 과 직렬화(lost-update 방지).
            with _STATE_LOCK:
                full_index = _load_origin_index()
                full_index[fid] = index
                _save_origin_index(full_index)
            # 로컬 manifest + state 마감 — 락 안에서 최신 state 재읽기(sync 중 바뀐
            # 사용자 토글 보존). R2 업로드는 락 밖.
            with _STATE_LOCK:
                st = _load_state()
                f2 = next((f for f in st["folders"] if f.get("path") == path), None)
                if f2:
                    f2["count"] = len(items_list)
                    f2["bytes"] = total
                    f2["synced_at"] = _now_iso()
                    f2["syncing"] = False
                    f2.pop("sync_total", None)
                    f2.pop("sync_done", None)
                _save_items(fid, items_list)
                _write_manifest(st)
                _save_state(st)
            # R2 최종 업로드(설정 시) — 마지막 flush 이후 남은 썸네일 + 완성 manifest 만
            # (uploaded_iids 로 이미 올린 건 스킵). 작은 폴더면 여기서 전량 업로드.
            # 비공개(hidden)라도 바스켓에 담겼으면 썸네일을 올려야 그 비밀주소에서 보인다.
            if f2 and _folder_served_anywhere(st, fid):
                _upload_partial_r2(st, fid, items_list, uploaded_iids)
            # 이 폴더를 담은 바스켓들 manifest 재빌드·업로드(items 갱신 반영).
            _refresh_baskets_for_folder(st, fid)
        except Exception:
            _update_folder(path, syncing=False)
        finally:
            with _SYNC_GUARD:
                _SYNCING.discard(fid)


def _start_bg_sync(paths: list) -> int:
    """대상 폴더 동기화를 백그라운드 스레드로 시작. 시작한(아직 안 도는) 폴더 수 반환."""
    todo = [p for p in paths if not _sync_in_progress(p)]
    if todo:
        threading.Thread(target=_bg_sync_worker, args=(todo,), daemon=True).start()
    return len(todo)


def _sync_in_progress(path: str) -> bool:
    st = _load_state()
    f = next((x for x in st["folders"] if x.get("path") == path), None)
    return bool(f and f.get("syncing"))


# === op 핸들러 ===

def _reconcile_stale_syncing(state: dict) -> bool:
    """syncing=True 인데 실제 스레드 없음(백엔드 재시작 등) = stale → 중단됨으로 정리.
    스레드는 재시작에 안 살아남으므로 _SYNCING(인메모리)에 없으면 죽은 것."""
    changed = False
    for f in state["folders"]:
        if f.get("syncing") and f.get("id") not in _SYNCING:
            f["syncing"] = False
            f["interrupted"] = True
            f.pop("sync_total", None)
            f.pop("sync_done", None)
            changed = True
    return changed


def _sc_status(params: dict) -> str:
    state = _load_state()
    if _reconcile_stale_syncing(state):
        _save_state(state)
    settings = state["settings"]
    rows = [_folder_row(settings, f) for f in state["folders"]]
    # 단일 폴더 상세 요청(path) — 드릴/필터
    path = params.get("path")
    if path:
        rows = [r for r in rows if r["path"] == path]
    return json.dumps(
        items(rows, settings=settings, public_base=settings.get("public_base", "")),
        ensure_ascii=False,
    )


def _sc_add(params: dict) -> str:
    path = (params.get("path") or "").strip()
    if not path:
        return json.dumps(items([], success=False, message="폴더 경로가 필요합니다."), ensure_ascii=False)
    p = Path(path).expanduser()
    if not p.is_dir():
        return json.dumps(items([], success=False, message=f"폴더가 아닙니다: {path}"), ensure_ascii=False)
    path = _canon(path)  # canonical 절대경로 — remove/sync 매칭 안정화
    state = _load_state()
    if any(f.get("path") == path for f in state["folders"]):
        return json.dumps(items([], success=False, message="이미 공개 중인 폴더입니다."), ensure_ascii=False)
    folder = {
        "id": _folder_id(path),
        "path": path,
        "title": (params.get("title") or "").strip() or p.name,
        "mode": params.get("mode") or "media",
        "synced_at": None,
        "count": 0,
        "bytes": 0,
    }
    state["folders"].append(folder)
    _save_state(state)
    # 추가 후 백그라운드 동기화 시작(썸네일·manifest·R2). 거대 폴더도 즉시 반환.
    _start_bg_sync([path])
    return json.dumps(
        items(
            [_folder_row(state["settings"], folder)],
            success=True,
            message=f"'{folder['title']}' 공개 추가 — 백그라운드에서 동기화 중입니다. 새로고침하면 진행상황이 보입니다.",
        ),
        ensure_ascii=False,
    )


def _sc_remove(params: dict) -> str:
    import shutil
    path = _canon(params.get("path"))
    state = _load_state()
    removed = next((f for f in state["folders"] if f.get("path") == path), None)
    if not removed:
        return json.dumps(items([], success=False, message="공개 목록에 없는 폴더입니다."), ensure_ascii=False)
    rid = removed["id"]
    state["folders"] = [f for f in state["folders"] if f.get("path") != path]
    # 담긴 바스켓에서도 제거(고아 folder_id 방지).
    for b in state.get("baskets", []):
        if rid in b.get("folder_ids", []):
            b["folder_ids"] = [x for x in b["folder_ids"] if x != rid]
    # 로컬 스테이징 정리 — 썸네일 디렉토리 삭제 + items 파일 삭제.
    removed_items = _load_items(rid)  # R2 삭제용으로 키 확보
    _delete_items(rid)
    thumb_dir = _STAGE_DIR / "thumbs" / rid
    if thumb_dir.exists():
        shutil.rmtree(thumb_dir, ignore_errors=True)
    with _STATE_LOCK:  # bg sync 의 origin 색인 쓰기와 직렬화.
        oidx = _load_origin_index()
        oidx.pop(rid, None)
        _save_origin_index(oidx)
    _write_manifest(state)
    _save_state(state)
    # 이 폴더를 담았던 바스켓 manifest 재빌드·업로드(사이트에서 폴더 사라짐).
    for b in state.get("baskets", []):
        _r2_upload_basket(state, b)
    # R2 반영 — 설정 시: manifest 는 항상 갱신(사이트에서 폴더 사라짐).
    # purge=true 면 R2 객체(썸네일·원본)까지 삭제, 아니면 보존(freeze).
    purge = bool(params.get("purge"))
    r2_msg = ""
    try:
        from r2_client import is_configured, put_object, delete_object
        bucket = state["settings"].get("r2_bucket")
        if is_configured() and bucket:
            mf = _manifest_path()
            if mf.exists():
                put_object(bucket, "manifest.json", mf.read_bytes(), "application/json")
            fp = _fids_path()
            if fp.exists():
                put_object(bucket, "fids.json", fp.read_bytes(), "application/json")
            if purge:
                deleted = 0
                for it in removed_items:
                    for key in (it.get("thumb"), it.get("src")):
                        if key:
                            ok, _ = delete_object(bucket, key)
                            if ok:
                                deleted += 1
                r2_msg = f" · R2 {deleted}개 삭제 + manifest 갱신"
            else:
                r2_msg = " · R2 manifest 갱신(썸네일 보존)"
    except Exception as e:
        r2_msg = f" · R2 정리 오류: {e}"
    return json.dumps(items([], success=True, message="공개 해제 · 스테이징 정리" + r2_msg), ensure_ascii=False)


def _sc_sync(params: dict) -> str:
    state = _load_state()
    path = _canon(params.get("path")) if params.get("path") else None
    targets = [f for f in state["folders"] if (not path or f.get("path") == path)]
    if not targets:
        return json.dumps(items([], success=False, message="동기화할 폴더가 없습니다."), ensure_ascii=False)
    # 백그라운드 동기화 시작(썸네일·manifest·R2). 거대 폴더도 백엔드를 막지 않음.
    started = _start_bg_sync([f["path"] for f in targets])
    msg = (f"{started}개 폴더 동기화 시작(백그라운드). 새로고침하면 진행상황이 보입니다."
           if started else "이미 동기화 중입니다.")
    return json.dumps(
        items([_folder_row(state["settings"], f) for f in targets], success=True, message=msg),
        ensure_ascii=False,
    )


def _as_bool(v) -> bool:
    return str(v).lower() in ("true", "1", "yes", "on")


def _sc_detail(params: dict) -> str:
    """폴더 하나 상세 — 앱 드릴 form 바인딩용 {folder:{...}} + settings."""
    cpath = _canon(params.get("path"))
    state = _load_state()
    f = next((x for x in state["folders"] if x.get("path") == cpath), None)
    if not f:
        return json.dumps(items([], success=False, message="공개 목록에 없는 폴더입니다."), ensure_ascii=False)
    row = _folder_row(state["settings"], f)
    return json.dumps(items([row], folder=row, settings=state["settings"]), ensure_ascii=False)


def _config_folder(params: dict) -> str:
    """폴더별 설정 — 표시명·공개/비공개(hidden). 비공개=R2 객체 삭제+목록 제외, 공개=재업로드."""
    from r2_client import is_configured, put_object, delete_object
    cpath = _canon(params.get("path"))
    state = _load_state()
    f = next((x for x in state["folders"] if x.get("path") == cpath), None)
    if not f:
        return json.dumps(items([], success=False, message="공개 목록에 없는 폴더입니다."), ensure_ascii=False)
    if (params.get("title") or "").strip():
        f["title"] = params["title"].strip()
    bucket = state["settings"].get("r2_bucket")
    r2_on = is_configured() and bucket
    extra = ""
    hid = params.get("hidden")
    if hid is not None and hid != "":
        new_hidden = _as_bool(hid)
        was_hidden = bool(f.get("hidden"))
        f["hidden"] = new_hidden
        if not new_hidden and was_hidden:
            # 공개 전환 → 백그라운드 재동기화(썸네일 재업로드 + manifest 포함).
            f["syncing"] = True
            _save_state(state)
            _start_bg_sync([f["path"]])
            return json.dumps(
                items([_folder_row(state["settings"], f)], success=True,
                      message=f"'{f['title']}' 공개 전환 — 백그라운드 동기화 중"),
                ensure_ascii=False)
        if new_hidden and not was_hidden and r2_on:
            # 비공개 전환 → 루트에서 내림. 단 바스켓에 담겨 있으면 썸네일은 보존
            # (그 비밀주소에선 계속 보여야 함). 어느 바스켓에도 없을 때만 R2 객체 삭제.
            if _baskets_with_folder(state, f["id"]):
                extra = " · 루트에서 내림(바스켓 주소에선 유지)"
            else:
                for it in _load_items(f["id"]):
                    for key in (it.get("thumb"), it.get("src")):
                        if key:
                            delete_object(bucket, key)
                extra = " · R2에서 내림"
    # 루트 manifest 재작성(hidden 제외/표시명 반영) + 업로드.
    _write_manifest(state)
    _save_state(state)
    if r2_on:
        mf = _manifest_path()
        if mf.exists():
            put_object(bucket, "manifest.json", mf.read_bytes(), "application/json")
        fp = _fids_path()
        if fp.exists():
            put_object(bucket, "fids.json", fp.read_bytes(), "application/json")
        # 표시명이 바뀌었으면 담긴 바스켓 manifest 도 갱신.
        for b in _baskets_with_folder(state, f["id"]):
            _r2_upload_basket(state, b)
    return json.dumps(
        items([_folder_row(state["settings"], f)], success=True,
              message=f"'{f['title']}' 설정 저장{extra}"),
        ensure_ascii=False)


def _sc_config(params: dict) -> str:
    # path 가 있으면 폴더별 설정(표시명·공개/비공개), 없으면 전역 설정.
    if (params.get("path") or "").strip():
        return _config_folder(params)
    state = _load_state()
    settings = state["settings"]
    # 명시적 읽기 — 앱-템플릿 param 가드가 정적 스캔으로 인식(침묵 무시 방지).
    if params.get("access"):
        settings["access"] = params.get("access")
    if params.get("strip_exif") is not None and params.get("strip_exif") != "":
        settings["strip_exif"] = _as_bool(params.get("strip_exif"))
    if params.get("push_originals") is not None and params.get("push_originals") != "":
        settings["push_originals"] = _as_bool(params.get("push_originals"))
    if params.get("transcode_video") is not None and params.get("transcode_video") != "":
        settings["transcode_video"] = _as_bool(params.get("transcode_video"))
    if params.get("on_uninstall"):
        settings["on_uninstall"] = params.get("on_uninstall")
    if params.get("r2_bucket"):
        settings["r2_bucket"] = params.get("r2_bucket")
    if params.get("public_base"):
        settings["public_base"] = params.get("public_base")
    if params.get("link_token"):
        settings["link_token"] = params.get("link_token")
    state["settings"] = settings
    _save_state(state)
    return json.dumps(
        items([], settings=settings, success=True, message="설정 저장."),
        ensure_ascii=False,
    )


# === 바스켓(공간) op — 여러 비밀 공개주소 ===

def _basket_row(settings: dict, state: dict, b: dict) -> dict:
    """바스켓 → 표시 통화(title/meta/url/id)."""
    fids = b.get("folder_ids", [])
    return {
        "title": b.get("title") or "이름 없는 바스켓",
        "meta": f"📁 {len(fids)}개 폴더 · 비밀주소",
        "url": _basket_url(settings, b),
        "id": b.get("id", ""),
        "slug": b.get("slug", ""),
    }


def _sc_basket_list(params: dict) -> str:
    state = _load_state()
    settings = state["settings"]
    rows = [_basket_row(settings, state, b) for b in state.get("baskets", [])]
    return json.dumps(
        items(rows, settings=settings, public_base=settings.get("public_base", "")),
        ensure_ascii=False,
    )


def _sc_basket_save(params: dict) -> str:
    """바스켓 생성(basket_id 없으면) 또는 이름 변경(있으면)."""
    title = (params.get("title") or "").strip()
    bid = (params.get("basket_id") or "").strip()
    state = _load_state()
    if bid:
        b = next((x for x in state["baskets"] if x.get("id") == bid), None)
        if not b:
            return json.dumps(items([], success=False, message="바스켓을 찾을 수 없습니다."), ensure_ascii=False)
        if title:
            b["title"] = title
        _save_state(state)
        _r2_upload_basket(state, b)   # 제목이 manifest.title 로 들어가므로 재업로드.
        return json.dumps(items([_basket_row(state["settings"], state, b)], success=True,
                                message=f"'{b['title']}' 저장."), ensure_ascii=False)
    # 신규 — 긴 랜덤 slug 발급.
    b = {"id": _basket_id(), "slug": _new_slug(), "title": title or "새 바스켓",
         "folder_ids": [], "created_at": _now_iso()}
    state["baskets"].append(b)
    _save_state(state)
    _r2_upload_basket(state, b)       # 빈 manifest 라도 주소가 바로 살도록.
    return json.dumps(items([_basket_row(state["settings"], state, b)], success=True,
                            message=f"'{b['title']}' 바스켓 생성 — 비밀주소가 만들어졌습니다."),
                      ensure_ascii=False)


def _sc_basket_detail(params: dict) -> str:
    """바스켓 하나 상세 — 앱 드릴용. {basket:{...}} + folders[](전 폴더에 소속여부·토글 액션)."""
    bid = (params.get("basket_id") or "").strip()
    state = _load_state()
    b = next((x for x in state["baskets"] if x.get("id") == bid), None)
    if not b:
        return json.dumps(items([], success=False, message="바스켓을 찾을 수 없습니다."), ensure_ascii=False)
    member = set(b.get("folder_ids", []))
    folders = []
    for f in state["folders"]:
        inb = f["id"] in member
        folders.append({
            "id": f["id"],
            "title": f.get("title") or Path(f.get("path", "")).name,
            "meta": ("✅ 이 주소에 포함" if inb else "➕ 담기 가능")
                     + (" · 🔒 루트 비공개" if f.get("hidden") else ""),
            "in_basket": inb,
            "member_action": "빼기" if inb else "담기",
            "basket_id": b["id"],     # list_action 버튼이 참조(행 컨텍스트에 바스켓 못박음).
        })
    row = _basket_row(state["settings"], state, b)
    return json.dumps(items([row], basket=row, folders=folders, settings=state["settings"]),
                      ensure_ascii=False)


def _sc_basket_toggle(params: dict) -> str:
    """바스켓에 폴더 하나 담기/빼기. 담을 때 썸네일이 없으면(루트 비공개였다면) 동기화."""
    bid = (params.get("basket_id") or "").strip()
    fid = (params.get("folder_id") or "").strip()
    state = _load_state()
    b = next((x for x in state["baskets"] if x.get("id") == bid), None)
    if not b:
        return json.dumps(items([], success=False, message="바스켓을 찾을 수 없습니다."), ensure_ascii=False)
    f = next((x for x in state["folders"] if x.get("id") == fid), None)
    if not f:
        return json.dumps(items([], success=False, message="폴더를 찾을 수 없습니다."), ensure_ascii=False)
    fids = b.setdefault("folder_ids", [])
    if fid in fids:
        fids.remove(fid)
        msg = f"'{f.get('title')}' 을(를) 바스켓에서 뺐습니다."
    else:
        fids.append(fid)
        msg = f"'{f.get('title')}' 을(를) 바스켓에 담았습니다."
    _save_state(state)
    # 담긴 폴더 썸네일이 R2 에 없을 수 있음(루트 비공개라 안 올랐거나 미동기화) → 필요시 동기화.
    need_sync = fid in fids and not _items_path(fid).exists() and not _load_items(fid)
    if fid in fids and (need_sync or not f.get("synced_at")):
        _start_bg_sync([f["path"]])   # 완료 후 _refresh_baskets_for_folder 가 바스켓 재빌드.
    _r2_upload_basket(state, b)        # 즉시 manifest 반영(썸네일은 sync 완료 시 뒤따름).
    return json.dumps(items([_basket_row(state["settings"], state, b)], success=True, message=msg),
                      ensure_ascii=False)


def _sc_basket_delete(params: dict) -> str:
    bid = (params.get("basket_id") or "").strip()
    state = _load_state()
    b = next((x for x in state["baskets"] if x.get("id") == bid), None)
    if not b:
        return json.dumps(items([], success=False, message="바스켓을 찾을 수 없습니다."), ensure_ascii=False)
    slug = b.get("slug", "")
    state["baskets"] = [x for x in state["baskets"] if x.get("id") != bid]
    _save_state(state)
    _r2_delete_basket(state, slug)     # 그 비밀주소를 죽인다(폴더·썸네일 자체는 보존).
    return json.dumps(items([], success=True, message="바스켓(비밀주소) 삭제 — 폴더는 그대로입니다."),
                      ensure_ascii=False)


_OP_DISPATCHERS = {
    "showcase_op": {
        "status": _sc_status,
        "add": _sc_add,
        "remove": _sc_remove,
        "sync": _sc_sync,
        "config": _sc_config,
        "detail": _sc_detail,
        "basket_list": _sc_basket_list,
        "basket_save": _sc_basket_save,
        "basket_detail": _sc_basket_detail,
        "basket_toggle": _sc_basket_toggle,
        "basket_delete": _sc_basket_delete,
    },
}
_OP_DEFAULTS = {
    "showcase_op": "status",
}


def execute(tool_input: dict, context) -> str:
    """공개파일 도구 실행 (ToolContext 시그니처)."""
    tool_name = context.tool_name
    try:
        if tool_name in _OP_DISPATCHERS:
            op = tool_input.get("op") or _OP_DEFAULTS.get(tool_name)
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if not fn:
                return json.dumps(
                    {"success": False, "message": f"알 수 없는 op: {op}"},
                    ensure_ascii=False,
                )
            return fn(tool_input)
        return f"Unknown tool: {tool_name}"
    except Exception as e:
        return json.dumps({"success": False, "message": f"오류: {e}"}, ensure_ascii=False)
