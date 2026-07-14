"""
public-files/handler.py — 공개파일 (라이브 서빙, 인덱싱 없음).

폴더·바스켓은 상태 파일(showcase_state.json)만 관리한다. 실제 목록·썸네일·원본은
맥이 요청 시 즉석에서 서빙(backend/api_showcase.py) — 사전 인덱싱·manifest·R2 push 가
전혀 없다. 파일시스템이 곧 진실이라, 파일을 옮기거나 지우면 다음 조회에 즉시 반영된다.

이음매(헌법 1조): 공개 Worker(substrate)는 slug 게이트 + 지연 캐시만. 맥(superstructure)이
바스켓→폴더 소속을 검증하고 디렉토리를 훑어 준다. R2 는 SPA 호스팅 + 썸네일/원본 캐시로만.
"""

import sys
import json
import secrets
import threading
from pathlib import Path
from contextlib import contextmanager

# 프로젝트 루트 = data/packages/installed/tools/public-files/handler.py 에서 5단계 위.
_ROOT = Path(__file__).resolve().parents[5]

_BACKEND = str(_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from common.currency import items  # IBL 단일 통화 생성자

_DATA_DIR = _ROOT / "data"
_STATE_PATH = _DATA_DIR / "showcase_state.json"

_DEFAULT_SETTINGS = {
    "strip_exif": True,        # 원본 서빙 시 위치·EXIF 제거
    "transcode_video": True,   # .mov/HEVC/MKV → H.264 MP4
    "public_base": "",         # 공개 사이트 base URL (바스켓 주소 조립용)
}

_SAVE_LOCK = threading.Lock()
_STATE_LOCK = threading.RLock()


def _load_state() -> dict:
    """상태 로드. {settings, folders:[...], baskets:[...]}"""
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
        "baskets": st.get("baskets") or [],
    }


def _save_state(state: dict) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    with _SAVE_LOCK:
        tmp = _STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_STATE_PATH)


@contextmanager
def _locked_state():
    with _STATE_LOCK:
        st = _load_state()
        yield st
        _save_state(st)


# === 공통 유틸 ===

def _canon(path: str) -> str:
    if not path:
        return ""
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:
        return str(path).strip()


def _folder_id(path: str) -> str:
    """경로 → 안정적 폴더 id (basename NFC 슬러그). macOS NFD 자모를 NFC 로 정규화."""
    import re, unicodedata
    base = unicodedata.normalize("NFC", Path(path).name or "root")
    slug = re.sub(r"[^a-zA-Z0-9가-힣_-]+", "-", base).strip("-").lower()
    return f"fld_{slug}" if slug else "fld_root"


def _unique_fid(state: dict, base_id: str) -> str:
    ids = {f.get("id") for f in state["folders"]}
    if base_id not in ids:
        return base_id
    i = 2
    while f"{base_id}-{i}" in ids:
        i += 1
    return f"{base_id}-{i}"


def _now_iso() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _as_bool(v) -> bool:
    return str(v).lower() in ("true", "1", "yes", "on")


def _baskets_with_folder(state: dict, fid: str) -> list:
    """이 폴더를 노출하는 바스켓들 — 명시 소속(folder_ids) + 전체공개(all_folders)."""
    return [b for b in state.get("baskets", [])
            if b.get("all_folders") or fid in b.get("folder_ids", [])]


def _folder_row(state: dict, f: dict) -> dict:
    """폴더 → 표시 통화. 공개 여부 = 어떤 바스켓(주소)에 담겼는가."""
    baskets = _baskets_with_folder(state, f["id"])
    if baskets:
        names = ", ".join(b.get("title") or "이름없음" for b in baskets[:3])
        extra = " 외" if len(baskets) > 3 else ""
        meta = f"🌐 공개 중: {names}{extra}"
    else:
        meta = "⚪ 아직 어느 주소에도 없음 — '바스켓' 탭에서 담아 공개"
    return {
        "title": f.get("title") or Path(f.get("path", "")).name,
        "meta": meta,
        "path": f.get("path", ""),
        "id": f.get("id", ""),
        "mode": f.get("mode", "media"),
    }


# === 바스켓(공개 주소) ===

def _basket_id() -> str:
    return "bsk_" + secrets.token_hex(6)


def _new_slug(existing=None) -> str:
    """짧은 5자 대문자 코드(A-Z). 26^5 ≈ 1,180만 — bare 루트가 잠겨 있어 이 정도면 충분.
    충돌 시 재발급."""
    import string
    existing = existing or set()
    while True:
        s = "".join(secrets.choice(string.ascii_uppercase) for _ in range(5))
        if s not in existing:
            return s


def _basket_url(settings: dict, basket: dict) -> str:
    base = (settings.get("public_base") or "").rstrip("/")
    slug = basket.get("slug") or ""
    return f"{base}/s/{slug}" if base and slug else ""


def _basket_folders(state: dict, basket: dict) -> list:
    if basket.get("all_folders"):
        return list(state["folders"])
    by_id = {f["id"]: f for f in state["folders"]}
    return [by_id[fid] for fid in basket.get("folder_ids", []) if fid in by_id]


def _basket_row(settings: dict, state: dict, b: dict) -> dict:
    if b.get("all_folders"):
        meta = f"🌐 전체 폴더({len(state['folders'])}개) · 공개 갤러리"
    else:
        meta = f"📁 {len(b.get('folder_ids', []))}개 폴더 · 주소"
    return {
        "title": b.get("title") or "이름 없는 바스켓",
        "meta": meta,
        "url": _basket_url(settings, b),
        "id": b.get("id", ""),
        "slug": b.get("slug", ""),
        "all_folders": bool(b.get("all_folders")),
    }


# === 폴더 op ===

def _sc_status(params: dict) -> str:
    state = _load_state()
    settings = state["settings"]
    rows = [_folder_row(state, f) for f in state["folders"]]
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
    path = _canon(path)
    with _locked_state() as state:
        if any(f.get("path") == path for f in state["folders"]):
            return json.dumps(items([], success=False, message="이미 추가된 폴더입니다."), ensure_ascii=False)
        folder = {
            "id": _unique_fid(state, _folder_id(path)),
            "path": path,
            "title": (params.get("title") or "").strip() or p.name,
            "mode": params.get("mode") or "media",
            "added_at": _now_iso(),
        }
        state["folders"].append(folder)
        row = _folder_row(state, folder)
    return json.dumps(
        items([row], success=True,
              message=f"'{folder['title']}' 추가 — '바스켓' 탭에서 주소에 담으면 바로 공개됩니다."),
        ensure_ascii=False,
    )


def _sc_remove(params: dict) -> str:
    path = _canon(params.get("path"))
    with _locked_state() as state:
        removed = next((f for f in state["folders"] if f.get("path") == path), None)
        if not removed:
            return json.dumps(items([], success=False, message="목록에 없는 폴더입니다."), ensure_ascii=False)
        rid = removed["id"]
        state["folders"] = [f for f in state["folders"] if f.get("path") != path]
        for b in state.get("baskets", []):
            if rid in b.get("folder_ids", []):
                b["folder_ids"] = [x for x in b["folder_ids"] if x != rid]
    return json.dumps(items([], success=True, message="폴더 제거 — 모든 주소에서 빠졌습니다."), ensure_ascii=False)


def _sc_detail(params: dict) -> str:
    cpath = _canon(params.get("path"))
    state = _load_state()
    f = next((x for x in state["folders"] if x.get("path") == cpath), None)
    if not f:
        return json.dumps(items([], success=False, message="목록에 없는 폴더입니다."), ensure_ascii=False)
    row = _folder_row(state, f)
    return json.dumps(items([row], folder=row, settings=state["settings"]), ensure_ascii=False)


def _sc_config(params: dict) -> str:
    # path 있으면 폴더별(표시명), 없으면 전역 설정.
    if (params.get("path") or "").strip():
        cpath = _canon(params.get("path"))
        with _locked_state() as state:
            f = next((x for x in state["folders"] if x.get("path") == cpath), None)
            if not f:
                return json.dumps(items([], success=False, message="목록에 없는 폴더입니다."), ensure_ascii=False)
            if (params.get("title") or "").strip():
                f["title"] = params["title"].strip()
            row = _folder_row(state, f)
        return json.dumps(items([row], success=True, message=f"'{row['title']}' 저장."), ensure_ascii=False)
    with _locked_state() as state:
        settings = state["settings"]
        if params.get("strip_exif") not in (None, ""):
            settings["strip_exif"] = _as_bool(params.get("strip_exif"))
        if params.get("transcode_video") not in (None, ""):
            settings["transcode_video"] = _as_bool(params.get("transcode_video"))
        if params.get("public_base"):
            settings["public_base"] = params.get("public_base")
    return json.dumps(items([], settings=settings, success=True, message="설정 저장."), ensure_ascii=False)


# === 바스켓 op — 순수 상태 CRUD (R2·manifest 없음) ===

def _sc_basket_list(params: dict) -> str:
    state = _load_state()
    settings = state["settings"]
    rows = [_basket_row(settings, state, b) for b in state.get("baskets", [])]
    return json.dumps(
        items(rows, settings=settings, public_base=settings.get("public_base", "")),
        ensure_ascii=False,
    )


def _sc_basket_save(params: dict) -> str:
    title = (params.get("title") or "").strip()
    bid = (params.get("basket_id") or "").strip()
    with _locked_state() as state:
        if bid:
            b = next((x for x in state["baskets"] if x.get("id") == bid), None)
            if not b:
                return json.dumps(items([], success=False, message="바스켓을 찾을 수 없습니다."), ensure_ascii=False)
            if title:
                b["title"] = title
            row = _basket_row(state["settings"], state, b)
            return json.dumps(items([row], success=True, message=f"'{b['title']}' 저장."), ensure_ascii=False)
        all_folders = _as_bool(params.get("all_folders"))
        existing = {x.get("slug") for x in state["baskets"]}
        b = {"id": _basket_id(), "slug": _new_slug(existing),
             "title": title or ("전체 공개" if all_folders else "새 바스켓"),
             "folder_ids": [], "all_folders": all_folders, "created_at": _now_iso()}
        state["baskets"].append(b)
        row = _basket_row(state["settings"], state, b)
    kind = "전체 공개 갤러리" if row["all_folders"] else "바스켓"
    return json.dumps(items([row], success=True, message=f"'{row['title']}' {kind} 생성 — 주소가 만들어졌습니다."),
                      ensure_ascii=False)


def _sc_basket_detail(params: dict) -> str:
    bid = (params.get("basket_id") or "").strip()
    state = _load_state()
    b = next((x for x in state["baskets"] if x.get("id") == bid), None)
    if not b:
        return json.dumps(items([], success=False, message="바스켓을 찾을 수 없습니다."), ensure_ascii=False)
    row = _basket_row(state["settings"], state, b)
    if b.get("all_folders"):
        note = "이 주소는 모든 폴더를 자동으로 공개합니다. 폴더를 추가하면 자동 반영됩니다. 널리 공유해도 되는 '전체 공개' 갤러리예요."
        return json.dumps(items([row], basket=row, folders=[], note=note, settings=state["settings"]),
                          ensure_ascii=False)
    member = set(b.get("folder_ids", []))
    folders = []
    for f in state["folders"]:
        inb = f["id"] in member
        folders.append({
            "id": f["id"],
            "title": f.get("title") or Path(f.get("path", "")).name,
            "meta": "✅ 이 주소에 포함" if inb else "➕ 담기 가능",
            "in_basket": inb,
            "member_action": "빼기" if inb else "담기",
            "basket_id": b["id"],
        })
    note = "아래에서 이 주소로 공개할 폴더를 담거나 빼세요."
    return json.dumps(items([row], basket=row, folders=folders, note=note, settings=state["settings"]),
                      ensure_ascii=False)


def _sc_basket_toggle(params: dict) -> str:
    bid = (params.get("basket_id") or "").strip()
    fid = (params.get("folder_id") or "").strip()
    with _locked_state() as state:
        b = next((x for x in state["baskets"] if x.get("id") == bid), None)
        if not b:
            return json.dumps(items([], success=False, message="바스켓을 찾을 수 없습니다."), ensure_ascii=False)
        if b.get("all_folders"):
            return json.dumps(items([], success=False,
                                    message="전체 공개 갤러리는 모든 폴더를 자동 포함해 개별 조정하지 않습니다."),
                              ensure_ascii=False)
        f = next((x for x in state["folders"] if x.get("id") == fid), None)
        if not f:
            return json.dumps(items([], success=False, message="폴더를 찾을 수 없습니다."), ensure_ascii=False)
        fids = b.setdefault("folder_ids", [])
        if fid in fids:
            fids.remove(fid)
            msg = f"'{f.get('title')}' 을(를) 주소에서 뺐습니다."
        else:
            fids.append(fid)
            msg = f"'{f.get('title')}' 을(를) 주소에 담았습니다 — 바로 공개됩니다."
        row = _basket_row(state["settings"], state, b)
    return json.dumps(items([row], success=True, message=msg), ensure_ascii=False)


def _sc_basket_delete(params: dict) -> str:
    bid = (params.get("basket_id") or "").strip()
    with _locked_state() as state:
        b = next((x for x in state["baskets"] if x.get("id") == bid), None)
        if not b:
            return json.dumps(items([], success=False, message="바스켓을 찾을 수 없습니다."), ensure_ascii=False)
        state["baskets"] = [x for x in state["baskets"] if x.get("id") != bid]
    return json.dumps(items([], success=True, message="주소 삭제 — 폴더 자체는 그대로입니다."), ensure_ascii=False)


_OP_DISPATCHERS = {
    "showcase_op": {
        "status": _sc_status,
        "add": _sc_add,
        "remove": _sc_remove,
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
                return json.dumps({"success": False, "message": f"알 수 없는 op: {op}"}, ensure_ascii=False)
            return fn(tool_input)
        return f"Unknown tool: {tool_name}"
    except Exception as e:
        return json.dumps({"success": False, "message": f"오류: {e}"}, ensure_ascii=False)
