"""file_index.py — OS 네이티브 파일/미디어 색인 어댑터 (몸별 바인딩의 단일 출처).

사진·음악·문서·영상은 모두 '파일'의 한 종류다. 그것들을 OS 색인에서 질의하는
*보편적인* 일(필터 조립·실행·메타 투영·정렬·몸 분기)은 여기서 **한 번만** 한다.
각 종류의 특별함(사진=썸네일·지도, 음악=재생, PDF=본문)은 호출자(얇은 preset)가 얹는다.

  맥  : Spotlight (mdfind 로 필터, mdls 로 색인 메타). 선스캔 불필요·항상 최신.
  폰  : MediaStore (Chaquopy, Phase 3). detect_body 능력게이트로 분기.

이 모듈은 '데이터'만 돌려준다(표시/렌더링 결정 없음). title/meta/image 같은
records 통화 포장은 각 preset 의 몫 — 그래서 보편 질의는 중복되지 않는다.

fork-guard: detect_body() 능력게이트로만 몸을 가른다(환경변수 직접 분기 없음)
→ 이음매-위 금지에 걸리지 않는다(allowlist 불필요).
"""
from __future__ import annotations

import os
import json
import time
import calendar
import plistlib
import subprocess
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence

_IS_MAC = sys.platform == "darwin"

try:
    from runtime_utils import detect_body
except Exception:  # 폴백 — 능력게이트 부재 시 맥으로 (어댑터 안전 기본값)
    def detect_body() -> dict:  # type: ignore
        return {"profile": "mac"}


# 사용자 파일이 아닌 시스템/앱/캐시를 기본 배제 (질의 노이즈 제거).
# 절대-dead 포식 필터 — 어떤 의도로도 사용자 자료가 아닌 가지(설치 의존성·캐시·시스템).
# fs_query(결과 path-substring 필터)와 file_find(walk 가지치기)가 공유하는 *단일 출처*.
# ★ ~/Library 를 통째로 빼지 않는다 — ~/Library/Mobile Documents(iCloud Drive)·iBooks 는
#    실제 사용자 자료(예: iCloud 전자책). 캐시·컨테이너 등 *특정 하위만* 제외.
_NOISE_SUBSTR = (
    "/System/", "/Applications/", "/Library/Caches/",
    "/Library/Application Support/", "/Library/Containers/",
    "/Library/Group Containers/", "/node_modules/", "/.Trash", ".app/",
    "/__pycache__/", "/site-packages/", "/.venv/", "/venv/",
    "/.git/", "/DerivedData/", "/.gradle/", "/.cargo/", "/.npm/",
)
# 공개 별칭 — file_find(system_essentials) 가 import 해 같은 목록으로 walk 가지치기.
ABSOLUTE_DEAD_SUBSTR = _NOISE_SUBSTR


def is_dead_path(path: str) -> bool:
    """절대-dead(설치트리·캐시·시스템) 경로면 True — 모든 포식이 무조건 제외(의도 불문)."""
    return any(n in path for n in _NOISE_SUBSTR)
_MAX_CANDIDATES = 20000  # mtime 정렬 상한 가드 (질의를 path/날짜로 좁히도록 권장)

# kind → Spotlight content-type-tree 절. 'media'=이미지+영상.
_KIND_CLAUSE = {
    "image": "kMDItemContentTypeTree == 'public.image'c",
    "photo": "kMDItemContentTypeTree == 'public.image'c",
    "video": "kMDItemContentTypeTree == 'public.movie'c",
    "audio": "kMDItemContentTypeTree == 'public.audio'c",
    "pdf": "kMDItemContentType == 'com.adobe.pdf'",
    "media": "(kMDItemContentTypeTree == 'public.image'c"
             " || kMDItemContentTypeTree == 'public.movie'c)",
    "any": None,
}

# facet 이름 → Spotlight mdls 키. 호출자가 facets 로 고르면 출력에 포함.
_FACET_KEY = {
    "taken_at": "kMDItemContentCreationDate",
    "lat": "kMDItemLatitude",
    "lng": "kMDItemLongitude",
    "camera": "kMDItemAcquisitionModel",
    "width": "kMDItemPixelWidth",
    "height": "kMDItemPixelHeight",
    "duration": "kMDItemDurationSeconds",
    "genre": "kMDItemMusicalGenre",
    "authors": "kMDItemAuthors",
    "pages": "kMDItemNumberOfPages",
    "title": "kMDItemTitle",
}

# 폴백 walk 시 인식할 확장자 → kind.
_EXT_KIND = {
    **{e: "image" for e in (".jpg", ".jpeg", ".png", ".heic", ".heif", ".gif",
                            ".tiff", ".webp", ".bmp")},
    **{e: "video" for e in (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm")},
    **{e: "audio" for e in (".mp3", ".m4a", ".flac", ".wav", ".aac", ".ogg")},
    **{".pdf": "pdf"},
}


def _truthy(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on", "참")


def _iso_bound(date_str: Optional[str], end: bool) -> Optional[str]:
    """YYYY-MM 또는 YYYY-MM-DD → mdfind $time.iso 인자 (end면 그 단위의 끝)."""
    s = (date_str or "").strip()
    if not s:
        return None
    parts = s.replace(".", "-").replace("/", "-").split("-")
    try:
        y = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else (12 if end else 1)
        d = int(parts[2]) if len(parts) > 2 else (
            calendar.monthrange(y, m)[1] if end else 1)
    except (ValueError, IndexError):
        return None
    return f"{y:04d}-{m:02d}-{d:02d}T{'23:59:59' if end else '00:00:00'}Z"


def _safe_stat(path: str, mtime: bool = True):
    try:
        st = os.stat(path)
        return st.st_mtime if mtime else st.st_size
    except OSError:
        return 0


def _kind_of(content_type: str, tree: Sequence) -> str:
    ct = str(content_type or "")
    tl = [str(t) for t in (tree or [])]
    if ct.startswith("public.image") or any("image" in t for t in tl):
        return "image"
    if ct.startswith(("public.movie", "public.video")) or any("movie" in t or "video" in t for t in tl):
        return "video"
    if ct.startswith("public.audio") or any("audio" in t for t in tl):
        return "audio"
    if "pdf" in ct:
        return "pdf"
    return "file"


# ----------------------------------------------------------------------------
# 맥 (Spotlight)
# ----------------------------------------------------------------------------
def _build_mdfind_query(kind: str, q: Optional[str], start: Optional[str],
                        end: Optional[str], has_gps: bool, ext: Optional[str],
                        min_size: Optional[int] = None) -> str:
    clauses: List[str] = []
    kc = _KIND_CLAUSE.get((kind or "any").lower(), _KIND_CLAUSE["any"])
    if kc:
        clauses.append(kc)
    s = _iso_bound(start, end=False)
    if s:
        clauses.append(f"kMDItemContentCreationDate >= $time.iso({s})")
    e = _iso_bound(end, end=True)
    if e:
        clauses.append(f"kMDItemContentCreationDate <= $time.iso({e})")
    if has_gps:
        # lat 필드 존재 + 0 아님 (0,0 = GPS 미보유인데 0으로 채워진 허위양성 제거).
        clauses.append("(kMDItemLatitude == '*' && kMDItemLatitude != 0)")
    if ext:
        clauses.append(f"kMDItemFSName == '*.{str(ext).lstrip('.')}'c")
    if min_size and int(min_size) > 0:
        clauses.append(f"kMDItemFSSize >= {int(min_size)}")
    if q:
        qq = str(q).replace("'", "").replace('"', "")
        clauses.append(f"(kMDItemFSName == '*{qq}*'cd"
                       f" || kMDItemAcquisitionModel == '*{qq}*'cd"
                       f" || kMDItemTitle == '*{qq}*'cd)")
    return " && ".join(clauses) if clauses else "kMDItemFSName == '*'"


def _run_mdfind(query: str, onlyin: Optional[str]) -> List[str]:
    cmd = ["mdfind"]
    if onlyin:
        cmd += ["-onlyin", onlyin]
    cmd.append(query)
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    except (subprocess.TimeoutExpired, OSError):
        return []
    paths = []
    for line in out.stdout.splitlines():
        p = line.strip()
        if p and not any(n in p for n in _NOISE_SUBSTR):
            paths.append(p)
    return paths


def _mdls_meta(path: str) -> Dict[str, Any]:
    try:
        out = subprocess.run(["mdls", "-plist", "-", path],
                             capture_output=True, timeout=10)
        if out.returncode != 0 or not out.stdout:
            return {}
        d = plistlib.loads(out.stdout)
        return d if isinstance(d, dict) else {}
    except (subprocess.TimeoutExpired, OSError, plistlib.InvalidFileException, ValueError):
        return {}


def _item_from_meta(path: str, facets: Sequence[str]) -> Dict[str, Any]:
    """경로 + 색인 메타 → 보편 필드 + 요청 facet 의 순수 데이터 한 줄."""
    meta = _mdls_meta(path)
    item: Dict[str, Any] = {
        "path": path,
        "name": os.path.basename(path),
        "ext": os.path.splitext(path)[1].lower().lstrip("."),
        "size": _safe_stat(path, mtime=False),
        "mtime": _safe_stat(path, mtime=True),
        "kind": _kind_of(meta.get("kMDItemContentType"),
                         meta.get("kMDItemContentTypeTree") or []),
    }
    for f in facets:
        mk = _FACET_KEY.get(f)
        if not mk:
            continue
        val = meta.get(mk)
        if val is None:
            continue
        if isinstance(val, datetime):
            iso = val.isoformat()
            item[f] = iso
            if f == "taken_at":
                item["month"] = iso[:7]
        elif f in ("lat", "lng"):
            try:
                item[f] = float(val)
            except (TypeError, ValueError):
                pass
        else:
            item[f] = val
    # (0,0) = GPS 미보유인데 필드만 0으로 채워진 경우 → 위치 없음으로 처리.
    if item.get("lat") == 0 and item.get("lng") == 0:
        item.pop("lat", None)
        item.pop("lng", None)
    return item


def _spotlight_query(kind, q, start, end, has_gps, ext, path, limit, sort, facets, min_size=None):
    onlyin = os.path.abspath(os.path.expanduser(path)) if path else os.path.expanduser("~")
    query = _build_mdfind_query(kind, q, start, end, has_gps, ext, min_size)
    paths = _run_mdfind(query, onlyin)

    if not paths and path and os.path.isdir(onlyin):
        return _walk_fallback(onlyin, kind, limit, sort, facets)

    total = len(paths)
    # 후보가 많으면 mtime(stat, 무subprocess)으로 창을 좁힌 뒤 그 창만 mdls →
    # mdls 호출을 limit 개로 제한 (보편 질의의 비용 절약).
    paths = paths[:_MAX_CANDIDATES]
    paths.sort(key=lambda p: _safe_stat(p, mtime=True), reverse=True)
    window = paths[:limit]
    items = [_item_from_meta(p, facets) for p in window]
    _sort_items(items, sort)
    return {"success": True, "count": total, "shown": len(items),
            "scope": onlyin, "items": items}


def _walk_fallback(root, kind, limit, sort, facets):
    """비색인 경로(Spotlight off/외장) 폴백 — 그 폴더만 라이브 순회(무영속)."""
    want = None
    if kind and kind.lower() not in ("any", "media"):
        want = {kind.lower()}
    elif (kind or "").lower() == "media":
        want = {"image", "video"}
    found = []
    for dp, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for name in files:
            ek = _EXT_KIND.get(os.path.splitext(name)[1].lower())
            if ek and (want is None or ek in want):
                found.append(os.path.join(dp, name))
        if len(found) > _MAX_CANDIDATES:
            break
    found.sort(key=lambda p: _safe_stat(p, mtime=True), reverse=True)
    items = [_item_from_meta(p, facets) for p in found[:limit]]
    _sort_items(items, sort)
    return {"success": True, "count": len(found), "shown": len(items),
            "scope": root, "fallback": "walk (비색인 경로)", "items": items}


def _sort_items(items: List[Dict[str, Any]], sort: str) -> None:
    key = {"date": "taken_at", "mtime": "mtime", "size": "size", "name": "name"}.get(sort, "mtime")
    if key == "taken_at":
        items.sort(key=lambda r: r.get("taken_at") or "", reverse=True)
    elif key == "name":
        items.sort(key=lambda r: r.get("name") or "")
    else:
        items.sort(key=lambda r: r.get(key) or 0, reverse=True)


# ----------------------------------------------------------------------------
# 폰 (MediaStore) — Chaquopy→Kotlin PhoneActions.queryMedia 브리지
# ----------------------------------------------------------------------------
def _epoch_ms(date_str: Optional[str], end: bool) -> int:
    """날짜 문자열 → epoch ms (로컬 자정 경계). 0 = 경계 없음."""
    iso = _iso_bound(date_str, end)
    if not iso:
        return 0
    try:
        dt = datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")
        return int(time.mktime(dt.timetuple()) * 1000)
    except (ValueError, OverflowError):
        return 0


def _mediastore_query(*, kind, q, start, end, has_gps, ext, path, limit, sort, facets, min_size=None):
    """폰 MediaStore 라이브 질의 (선스캔 0). PhoneActions.queryMedia 위임."""
    try:
        from java import jclass  # Chaquopy — 폰 네이티브에만 존재
    except Exception:
        return {"success": False, "phone_only": True, "items": [],
                "error": "[self:photo] 폰 질의는 폰 네이티브 앱에서만 동작합니다"}
    want_gps = bool(has_gps) or ("lat" in facets) or ("lng" in facets)
    filt = {
        "kind": (kind or "media"),
        "q": q or "",
        "start_ms": _epoch_ms(start, end=False),
        "end_ms": _epoch_ms(end, end=True),
        "has_gps": bool(has_gps),
        "want_gps": want_gps,
        "limit": int(limit),
        # 맥 Spotlight 와 동일 필터를 폰 MediaStore 로도 전달 (큰 파일/확장자/정렬 — 누락 시 침묵 무시됐음).
        "min_size": int(min_size) if min_size else 0,
        "sort": sort or "",
        "ext": (ext or "").lower().lstrip("."),
    }
    try:
        PA = jclass("com.indiebiz.phoneagent.PhoneActions")
        raw = PA.queryMedia(json.dumps(filt))
        data = json.loads(str(raw))
    except Exception as e:
        return {"success": False, "items": [], "error": f"queryMedia 실패: {e}"}
    if data.get("error"):
        return {"success": False, "items": [], "error": data["error"]}
    items = data.get("items") or []
    for it in items:  # month 파생 (맥과 동일 통화 형태로)
        ta = it.get("taken_at") or ""
        it["month"] = ta[:7] if ta else ""
    return {"success": True, "count": data.get("count", len(items)),
            "shown": len(items), "scope": "phone:MediaStore", "items": items}


# ----------------------------------------------------------------------------
# 공개 진입점
# ----------------------------------------------------------------------------
def describe(path: str, facets: Sequence[str] = ()) -> Dict[str, Any]:
    """단일 파일의 보편 필드 + facet (경로가 곧 신원). 맥=mdls. 폰은 Phase 3."""
    if (detect_body().get("profile") or "mac") == "phone":
        return {"path": path, "name": os.path.basename(path)}  # Phase 3 보강
    return _item_from_meta(path, tuple(facets))


def candidate_paths(*, kind: str = "any", q: Optional[str] = None,
                    start: Optional[str] = None, end: Optional[str] = None,
                    ext: Optional[str] = None, path: Optional[str] = None,
                    min_size: Optional[int] = None) -> List[str]:
    """질의에 매칭되는 *전체* 후보 경로 목록 (정렬·mdls 없음, 표본추출용).

    query() 는 표시용으로 정렬·상한·메타를 입히지만, 음성-단언 측정(residual)은
    '모집단 전체'가 필요하다 — 균일 무작위 표본을 뽑으려면 후보 모수를 알아야.
    맥=mdfind 경로 목록, 비색인=walk 폴백. (폰은 미디어-한정 — residual 은 맥 자아 전용.)
    """
    onlyin = os.path.abspath(os.path.expanduser(path)) if path else os.path.expanduser("~")
    query_str = _build_mdfind_query(kind, q, start, end, False, ext, min_size)
    paths = _run_mdfind(query_str, onlyin)
    if not paths and path and os.path.isdir(onlyin):
        want = None
        if kind and kind.lower() not in ("any", "media"):
            want = {kind.lower()}
        elif (kind or "").lower() == "media":
            want = {"image", "video"}
        for dp, dirs, files in os.walk(onlyin):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for name in files:
                ek = _EXT_KIND.get(os.path.splitext(name)[1].lower())
                if want is None or (ek and ek in want):
                    paths.append(os.path.join(dp, name))
            if len(paths) > _MAX_CANDIDATES:
                break
    return paths


# 코드 몸(code:<repo>) candidate 열거용 — 소스 확장자 + 잡음 디렉토리.
# FORAGER_MULTIBODY_DESIGN §4: residual 의 몸별 candidate provider(코드판).
_CODE_EXTS = frozenset((
    ".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c", ".cpp",
    ".h", ".hpp", ".rb", ".php", ".swift", ".kt", ".scala", ".sh", ".yaml", ".yml",
    ".json", ".css", ".html", ".md", ".sql",
))
_CODE_NOISE_DIRS = frozenset((
    ".git", "node_modules", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", ".cache", "target", ".pytest_cache", "_archive", ".mypy_cache",
))


def code_candidate_paths(repo_root: str, *, q: Optional[str] = None,
                         exts: Optional[Sequence[str]] = None) -> List[str]:
    """코드레포 모집단 — repo_root 아래 소스파일 전체(잡음 디렉토리 제외).

    residual(음성-단언)의 *코드판* candidate provider. 디스크판 candidate_paths 가
    mdfind/walk 로 파일 모수를 주듯, 코드는 repo walk + 소스 확장자 필터로 모수를 준다.
    q 는 경로/파일명 부분일치(선택). exts 로 확장자 제한(기본=소스 전반).
    """
    root = os.path.abspath(os.path.expanduser(repo_root))
    if not os.path.isdir(root):
        return []
    want = frozenset(e.lower() if e.startswith(".") else "." + e.lower()
                     for e in exts) if exts else _CODE_EXTS
    ql = (q or "").lower().strip()
    out: List[str] = []
    for dp, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _CODE_NOISE_DIRS and not d.startswith(".")]
        for name in files:
            if os.path.splitext(name)[1].lower() not in want:
                continue
            full = os.path.join(dp, name)
            if ql and ql not in full.lower():
                continue
            out.append(full)
        if len(out) > _MAX_CANDIDATES:
            break
    return out


# 거친 골격(디렉토리-온리) 잡음 — basename 기반이라 OS 독립(경로 구분자 무관).
# 집중 관심 폴더(사용자 콘텐츠) 아래만 도므로 시스템 잡음(/System·Program Files)은
# 애초에 범위 밖 → dev 잡동사니 + 닷폴더만 쳐내면 충분(크로스플랫폼). OS-특수 basename 은
# OS_PORTABILITY_SEAM 정신대로 여기에 합집합으로 더한다(폰 .thumbnails, 윈도우 $RECYCLE.BIN 등).
_SKELETON_NOISE_DIRS = frozenset((
    # 공통 dev 잡동사니
    "node_modules", "__pycache__", ".git", "dist", "build", "vendor",
    ".venv", "venv", ".cache", ".npm", ".yarn", ".gradle", ".idea", ".vscode",
    "target", ".next", ".pytest_cache", ".mypy_cache", "site-packages",
    "DerivedData", ".cargo", "_archive",
    # OS-특수 (basename) — 합집합이라 해당 없는 OS 에선 무해
    "$RECYCLE.BIN", "System Volume Information",   # windows
    ".thumbnails", ".Trash", ".Trashes",          # android / mac 휴지통
))


def disk_skeleton(roots: Sequence[str], *, maxdepth: int = 3,
                  per_root_cap: int = 4000) -> str:
    """집중 관심 폴더(roots) 아래 거친 디렉토리 골격을 indent 문자열로 — *몸 독립*.

    상시-on 거친 지도("어디에")용. 디렉토리만(파일 미열거 → storage:scan 보다 한두 자릿수 쌈),
    maxdepth 로 깊이 제한, basename 잡음 제외(OS 독립). 깊은 상세·큐레이션은 forager 몫.
    OS 무관(os.walk + os.path) — 맥/윈도우/리눅스/폰이 같은 생성기로 자기 roots 아래를 돈다.

    Args:
        roots: 집중 관심 폴더 절대경로 목록(몸별 해소 결과). 존재하는 것만 처리.
        maxdepth: roots 각각으로부터의 최대 깊이(기본 3).
        per_root_cap: root 당 디렉토리 상한(폭주 가드).
    Returns:
        루트별 indent 트리를 이어붙인 문자열(없으면 "").
    """
    blocks: List[str] = []
    for raw in roots:
        root = os.path.abspath(os.path.expanduser(raw))
        if not os.path.isdir(root):
            continue
        base_depth = root.rstrip(os.sep).count(os.sep)
        lines: List[str] = []
        for cur, dirs, _files in os.walk(root):
            dirs[:] = sorted(d for d in dirs
                             if d not in _SKELETON_NOISE_DIRS and not d.startswith("."))
            depth = cur.rstrip(os.sep).count(os.sep) - base_depth
            if depth >= maxdepth:
                dirs[:] = []
            name = os.path.basename(cur) or cur
            lines.append(f"{'  ' * depth}{name}/")
            if len(lines) >= per_root_cap:
                lines.append(f"{'  ' * (depth + 1)}… (생략 — {per_root_cap}개 상한)")
                break
        if lines:
            blocks.append("\n".join(lines))
    return "\n".join(blocks)


def _walk_query(kind, q, start, end, has_gps, ext, path, limit, sort, facets, min_size=None):
    """비-맥(윈도우/리눅스) 파일 질의 — Spotlight(mdfind) 없이 os.walk 로 사용자 roots 순회.

    맥의 _spotlight_query 와 같은 필터 의미를 stdlib 만으로 재현:
      q=파일명 부분일치 / kind·ext=확장자 / 시간=mtime 창 / min_size=바이트.
    한계: has_gps·EXIF facet(taken_at/lat/lng)은 색인이 없어 미지원(기본 파일 검색만).
    """
    root = os.path.abspath(os.path.expanduser(path)) if path else os.path.expanduser("~")
    want = None
    if kind and kind.lower() not in ("any", "media"):
        want = {kind.lower()}
    elif (kind or "").lower() == "media":
        want = {"image", "video"}
    q_low = (q or "").strip().lower() or None
    ext_low = ext.lower().lstrip(".") if ext else None
    start_ep = (_epoch_ms(start, False) or 0) / 1000 if start else 0
    end_ep = (_epoch_ms(end, True) or 0) / 1000 if end else 0
    min_sz = min_size if isinstance(min_size, int) and min_size > 0 else None

    found: List[tuple] = []
    if os.path.isdir(root):
        for dp, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs
                       if d not in _SKELETON_NOISE_DIRS and not d.startswith(".")]
            for name in files:
                fp = os.path.join(dp, name)
                if any(n in fp for n in _NOISE_SUBSTR):
                    continue
                dot_ext = os.path.splitext(name)[1].lower()
                ek = _EXT_KIND.get(dot_ext)
                if want is not None and ek not in want:
                    continue
                if ext_low and dot_ext.lstrip(".") != ext_low:
                    continue
                if q_low and q_low not in name.lower():
                    continue
                mt = _safe_stat(fp, mtime=True) or 0
                if start_ep and mt < start_ep:
                    continue
                if end_ep and mt > end_ep:
                    continue
                if min_sz and (_safe_stat(fp, mtime=False) or 0) < min_sz:
                    continue
                found.append((fp, ek))
            if len(found) > _MAX_CANDIDATES:
                break

    found.sort(key=lambda t: _safe_stat(t[0], mtime=True) or 0, reverse=True)
    items = []
    for fp, ek in found[:limit]:
        it = _item_from_meta(fp, facets)
        if ek:  # 윈도우엔 mdls 없어 kind 가 generic → 확장자 기반으로 교정
            it["kind"] = ek
        items.append(it)
    _sort_items(items, sort)
    return {"success": True, "count": len(found), "shown": len(items),
            "scope": root, "engine": "walk", "items": items}


def query(*, kind: str = "any", q: Optional[str] = None,
          start: Optional[str] = None, end: Optional[str] = None,
          has_gps: bool = False, ext: Optional[str] = None,
          path: Optional[str] = None, limit: int = 50,
          sort: str = "mtime", facets: Sequence[str] = (),
          min_size: Optional[int] = None) -> Dict[str, Any]:
    """OS 파일/미디어 색인 라이브 질의 (선스캔 불필요).

    보편 필드(path/name/ext/size/mtime/kind) + 요청 facet 만 담은 순수 데이터.
    표시/렌더링(썸네일·meta 라인)은 호출자가 얹는다.
    """
    try:
        limit = max(1, int(limit))
    except (TypeError, ValueError):
        limit = 50
    body = detect_body().get("profile") or "mac"
    args = dict(kind=kind, q=q, start=start, end=end, has_gps=_truthy(has_gps),
                ext=ext, path=path, limit=limit, sort=sort, facets=tuple(facets),
                min_size=min_size)
    if body == "phone":
        return _mediastore_query(**args)
    if _IS_MAC:
        return _spotlight_query(**args)
    return _walk_query(**args)  # 윈도우/리눅스 — Spotlight 없이 os.walk
