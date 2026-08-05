"""family-news/handler.py — 가족신문.

USB 로 연결된 폰의 사진(MediaStore)을 지난 발행 이후 구간으로 모아, 날짜·장소(EXIF GPS→
행정동)를 붙인 정적 신문 HTML 로 조판하고, 공개 주소(/n/<5자 코드>)에 판을 누적 발행한다.
공개 페이지의 방명록·가족 사진 업로드(쓰기 방향)는 backend/api_family_news.py 가 받는다.

이음매(헌법 1조): Worker(substrate)는 slug 게이트 + 지연 캐시만. 판 조판·검수·발행 판단은
전부 맥(superstructure). 웹판 사진은 EXIF/GPS 를 벗겨 내보내고 장소는 텍스트로만 싣는다.
"""

import os
import re
import io
import sys
import json
import shutil
import secrets
import threading
import subprocess
import importlib.util
from pathlib import Path
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

# 프로젝트 루트 = data/packages/installed/tools/family-news/handler.py 에서 5단계 위.
_ROOT = Path(__file__).resolve().parents[5]
_BACKEND = str(_ROOT / "backend")
if _BACKEND not in sys.path:
    sys.path.insert(0, _BACKEND)
from common.currency import items  # IBL 단일 통화 생성자

_DATA = _ROOT / "data" / "family_news"
_STATE_PATH = _DATA / "state.json"
_EDITIONS = _DATA / "editions"
_UPLOADS = _DATA / "uploads"
_UPLOADS_META = _UPLOADS / "uploads.json"
_GEO_CACHE = _DATA / "geo_cache.json"
_TMP_PULL = _DATA / "_tmp_pull"

_WEB_MAX_PX = 1600
_WEB_QUALITY = 88
_DEFAULT_LIMIT = 48          # 판당 사진 수 상한 (config photo_limit)
_DEFAULT_DAYS = 7            # 첫 판(이전 발행 없음)의 기본 구간

_WEEKDAYS_KO = ["월", "화", "수", "목", "금", "토", "일"]

_SAVE_LOCK = threading.Lock()
_STATE_LOCK = threading.RLock()


# ── 상태 ────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    st = {}
    if _STATE_PATH.exists():
        try:
            st = json.loads(_STATE_PATH.read_text(encoding="utf-8"))
        except Exception:
            st = {}
    st.setdefault("slug", "")
    st.setdefault("title", "우리 가족 신문")
    st.setdefault("photo_limit", _DEFAULT_LIMIT)
    st.setdefault("public_base", _default_public_base())
    st.setdefault("editions", [])
    return st


def _save_state(state: dict) -> None:
    _DATA.mkdir(parents=True, exist_ok=True)
    with _SAVE_LOCK:
        tmp = _STATE_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_STATE_PATH)


def _default_public_base() -> str:
    """공개 사이트 base — 공개파일(showcase)과 같은 Worker 를 쓰므로 그 설정을 기본값으로."""
    try:
        sc = json.loads((_ROOT / "data" / "showcase_state.json").read_text(encoding="utf-8"))
        return (sc.get("settings") or {}).get("public_base", "") or ""
    except Exception:
        return ""


def _now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _new_slug() -> str:
    import string
    return "".join(secrets.choice(string.ascii_uppercase) for _ in range(5))


def _public_url(state: dict) -> str:
    base = (state.get("public_base") or "").rstrip("/")
    slug = state.get("slug") or ""
    return f"{base}/n/{slug}/" if base and slug else ""


def _preview_url(eid: str) -> str:
    return f"http://localhost:8765/family-news/preview/{eid}/"


def _ok(rows, **extra) -> str:
    return json.dumps(items(rows, **extra), ensure_ascii=False)


def _fail(msg: str) -> str:
    return json.dumps(items([], success=False, message=msg), ensure_ascii=False)


# ── 폰(MediaStore) ──────────────────────────────────────────────────────

def _adb_photos_since(since_ms: int, until_ms: int) -> list:
    """MediaStore 조회 → [(폰경로, datetaken_ms)] 시간순. DCIM 만(스크린샷 제외)."""
    # 삼성 등은 스크린샷도 DCIM/Screenshots 에 넣으므로 명시 제외(카메라 사진만).
    where = (f"datetaken>{since_ms} AND datetaken<={until_ms} "
             "AND _data LIKE '%/DCIM/%' AND _data NOT LIKE '%/Screenshot%'")
    cmd = ["adb", "shell",
           "content query --uri content://media/external/images/media "
           f"--projection _data:datetaken --where \"{where}\""]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=30)
    except FileNotFoundError:
        raise RuntimeError("adb 를 찾을 수 없습니다 (Android platform-tools 필요)")
    except subprocess.TimeoutExpired:
        raise RuntimeError("폰 응답이 없습니다 — USB 연결을 확인해 주세요")
    out = r.stdout.decode("utf-8", "ignore")
    if "no devices" in r.stderr.decode("utf-8", "ignore").lower():
        raise RuntimeError("연결된 폰이 없습니다 — USB 연결을 확인해 주세요")
    photos = []
    for m in re.finditer(r"_data=(.+?), datetaken=(\d+)", out):
        photos.append((m.group(1).strip(), int(m.group(2))))
    photos.sort(key=lambda x: x[1])
    return photos


def _sample_photos(photos: list, cap: int) -> list:
    """캡 초과 시 날짜별 비례 배분 + 날 내부 균등 스트라이드 — 하루 폭주가 판을 독점하지 않게."""
    if len(photos) <= cap:
        return photos
    by_day = {}
    for p in photos:
        d = datetime.fromtimestamp(p[1] / 1000).strftime("%Y-%m-%d")
        by_day.setdefault(d, []).append(p)
    days = sorted(by_day)
    if len(days) >= cap:
        # 날이 캡보다 많음 — 날짜를 균등 선별해 하루 1장(그날 중간 사진).
        picked_days = sorted({days[round(i * (len(days) - 1) / (cap - 1))] for i in range(cap)})
        return [by_day[d][len(by_day[d]) // 2] for d in picked_days]
    total = len(photos)
    quotas = {d: max(1, int(cap * len(by_day[d]) / total)) for d in days}
    # 배분 합 보정(내림 잔여분은 사진 많은 날부터).
    for d in sorted(days, key=lambda x: -len(by_day[x])):
        if sum(quotas.values()) >= cap:
            break
        quotas[d] += 1
    while sum(quotas.values()) > cap:
        d = max(days, key=lambda x: quotas[x])
        quotas[d] -= 1
    out = []
    for d in days:
        group, q = by_day[d], min(quotas[d], len(by_day[d]))
        if q >= len(group):
            out.extend(group)
        else:
            out.extend(group[round(i * (len(group) - 1) / max(1, q - 1))] for i in range(q))
    # 스트라이드 중복 제거(경로 기준) 후 시간순.
    seen, dedup = set(), []
    for p in sorted(out, key=lambda x: x[1]):
        if p[0] not in seen:
            seen.add(p[0])
            dedup.append(p)
    return dedup


def _adb_pull(src: str, dst: Path) -> bool:
    try:
        r = subprocess.run(["adb", "pull", src, str(dst)], capture_output=True, timeout=60)
        return r.returncode == 0 and dst.exists() and dst.stat().st_size > 0
    except Exception:
        return False


# ── EXIF · 장소 ─────────────────────────────────────────────────────────

def _open_image(path: Path):
    """PIL open — HEIC 등 PIL 미지원 포맷은 macOS sips 로 JPEG 변환 폴백."""
    from PIL import Image
    try:
        img = Image.open(path)
        img.load()
        return img, path
    except Exception:
        pass
    conv = path.with_suffix(".conv.jpg")
    try:
        subprocess.run(["sips", "-s", "format", "jpeg", str(path), "--out", str(conv)],
                       capture_output=True, timeout=30)
        if conv.exists():
            img = Image.open(conv)
            img.load()
            return img, conv
    except Exception:
        pass
    return None, None


def _gps_from_exif(path: Path):
    """EXIF GPS → (lat, lon) 또는 None. 원본에서만 읽고, 웹판에는 싣지 않는다."""
    from PIL import Image
    try:
        with Image.open(path) as img:
            exif = img.getexif()
            gps = exif.get_ifd(34853) if exif else None  # GPSInfo IFD
        if not gps:
            return None

        def _deg(dms, ref):
            d, m, s = (float(x) for x in dms)
            v = d + m / 60.0 + s / 3600.0
            return -v if ref in ("S", "W") else v

        lat = _deg(gps[2], gps.get(1, "N"))
        lon = _deg(gps[4], gps.get(3, "E"))
        if lat == 0 and lon == 0:
            return None
        return (lat, lon)
    except Exception:
        return None


_LOC_HANDLER = None


def _reverse_geocode(lat: float, lon: float) -> str:
    """좌표 → '시군구 동' 텍스트. location-services 의 Kakao 역지오코딩 재사용 + 파일 캐시."""
    key = f"{lat:.2f},{lon:.2f}"   # ~1km 격자 — 같은 동네는 한 번만 조회
    cache = {}
    try:
        cache = json.loads(_GEO_CACHE.read_text(encoding="utf-8"))
    except Exception:
        pass
    if key in cache:
        return cache[key]

    global _LOC_HANDLER
    place = ""
    try:
        if _LOC_HANDLER is None:
            p = _ROOT / "data" / "packages" / "installed" / "tools" / "location-services" / "handler.py"
            spec = importlib.util.spec_from_file_location("_family_news_loc", str(p))
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _LOC_HANDLER = mod
        res = _LOC_HANDLER.reverse_geocode_kakao(x=lon, y=lat)
        if isinstance(res, dict) and not res.get("error"):
            r2 = res.get("region_2depth", "")
            r3 = res.get("region_3depth", "")
            place = f"{r2} {r3}".strip() or res.get("address", "")
    except Exception:
        place = ""
    if place:   # 실패(빈값)는 캐시하지 않는다 — 일시 장애가 영구 공백이 되지 않게
        cache[key] = place
        try:
            _DATA.mkdir(parents=True, exist_ok=True)
            _GEO_CACHE.write_text(json.dumps(cache, ensure_ascii=False, indent=1), encoding="utf-8")
        except Exception:
            pass
    return place


def _make_web_photo(src: Path, dst: Path) -> bool:
    """원본 → 웹판 JPEG (EXIF 회전 굽기 + 메타 전부 제거 + 1600px 축소)."""
    from PIL import ImageOps, Image
    img, real = _open_image(src)
    if img is None:
        return False
    try:
        img = ImageOps.exif_transpose(img)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((_WEB_MAX_PX, _WEB_MAX_PX), Image.Resampling.LANCZOS)
        dst.parent.mkdir(parents=True, exist_ok=True)
        img.save(dst, "JPEG", quality=_WEB_QUALITY)   # exif= 미지정 → GPS·기기 메타 제거
        return dst.exists() and dst.stat().st_size > 0
    except Exception:
        return False
    finally:
        try:
            img.close()
            if real is not None and real != src:
                real.unlink(missing_ok=True)
        except Exception:
            pass


# ── 업로드(가족이 보낸 사진) 메타 ────────────────────────────────────────

def _load_uploads() -> list:
    try:
        return json.loads(_UPLOADS_META.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_uploads(entries: list) -> None:
    _UPLOADS.mkdir(parents=True, exist_ok=True)
    tmp = _UPLOADS_META.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(_UPLOADS_META)


def _pending_uploads(entries: list) -> list:
    """다음 판 후보 업로드 — 이미 실렸거나(used_in) 편집에서 뺀(rejected) 사진 제외."""
    return [u for u in entries if not u.get("used_in") and not u.get("rejected")]


# ── 신문 렌더 ────────────────────────────────────────────────────────────

_NEWS_HTML = None


def _renderer():
    global _NEWS_HTML
    if _NEWS_HTML is None:
        p = Path(__file__).with_name("newspaper_html.py")
        spec = importlib.util.spec_from_file_location("_family_newspaper_html", str(p))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _NEWS_HTML = mod
    return _NEWS_HTML


def _render_edition_html(eid: str, state: dict) -> None:
    ed_dir = _EDITIONS / eid
    edition = json.loads((ed_dir / "edition.json").read_text(encoding="utf-8"))
    html = _renderer().render_edition(edition, state.get("title", "우리 가족 신문"))
    (ed_dir / "index.html").write_text(html, encoding="utf-8")


# ── 판 행(row) 통화 ─────────────────────────────────────────────────────

def _edition_row(state: dict, ed: dict) -> dict:
    pub = bool(ed.get("published_at"))
    status = f"발행 {ed['published_at']}" if pub else "초안 — 미리보기로 확인 후 발행하세요"
    url = _public_url(state) + f"e/{ed['id']}/" if pub and _public_url(state) else _preview_url(ed["id"])
    return {
        "title": f"제 {ed.get('no', '?')} 호",
        "meta": f"{ed.get('range_from', '')}~{ed.get('range_to', '')} · 사진 {ed.get('photo_count', 0)}장 · {status}",
        "url": url,
        "id": ed.get("id", ""),
        "no": ed.get("no", 0),
        "is_draft": not pub,
        "places": ", ".join(ed.get("places", [])[:4]) or "(위치 정보 없음)",
        "preview_url": _preview_url(ed["id"]),
    }


# ── op 구현 ─────────────────────────────────────────────────────────────

def _mutate_state(fn):
    """load-modify-save 를 락으로 직렬화 (백그라운드 제작 스레드 ↔ 요청 핸들러)."""
    with _STATE_LOCK:
        state = _load_state()
        fn(state)
        _save_state(state)
        return state


def _set_building(info) -> None:
    def _f(st):
        if info is None:
            st.pop("building", None)
        else:
            st["building"] = {**info, "updated_at": _now_iso()}
    _mutate_state(_f)


def _building_status(state: dict) -> dict:
    """진행 중인 제작 정보. 10분 넘게 갱신 없으면 죽은 것으로 간주."""
    b = state.get("building")
    if not b:
        return {}
    try:
        age = datetime.now() - datetime.strptime(b.get("updated_at", ""), "%Y-%m-%d %H:%M")
        if age > timedelta(minutes=10):
            return {}
    except Exception:
        pass
    return b


def _fn_status(params: dict) -> str:
    state = _load_state()
    eds = sorted(state["editions"], key=lambda e: e.get("no", 0), reverse=True)
    rows = [_edition_row(state, e) for e in eds]
    drafts = [r for r in rows if r["is_draft"]]
    published = [r for r in rows if not r["is_draft"]]
    pub_url = _public_url(state)
    uploads_new = len(_pending_uploads(_load_uploads()))
    paper = {
        "title": state.get("title", ""),
        "url": pub_url or "(아직 발행 전 — 첫 발행 때 주소가 만들어집니다)",
        "slug": state.get("slug", ""),
        "photo_limit": state.get("photo_limit", _DEFAULT_LIMIT),
        "uploads_new": uploads_new,
    }
    building = _building_status(state)
    if building:
        msg = f"🛠 제작 중 — {building.get('stage', '')} (새로고침하면 갱신됩니다)"
    elif state.get("last_build_error"):
        msg = f"⚠️ 지난 제작 실패: {state['last_build_error']}"
    else:
        msg = "" if rows else "아직 만든 신문이 없습니다. '제작' 탭에서 첫 신문을 만들어 보세요."
    return _ok(rows, drafts=drafts, published=published, paper=paper, building=building,
               settings={"title": state.get("title"), "photo_limit": state.get("photo_limit"),
                         "public_base": state.get("public_base")},
               message=msg)


def _since_ms(state: dict, params: dict) -> tuple:
    """수집 구간 [since, until]. 이전 발행판이 있으면 그 판의 수집 종료 시점부터."""
    until = datetime.now()
    days = params.get("days")
    published = [e for e in state["editions"] if e.get("published_at")]
    if days not in (None, ""):
        since = until - timedelta(days=max(1, int(float(days))))
    elif published:
        last = max(published, key=lambda e: e.get("no", 0))
        try:
            since = datetime.strptime(last["captured_until"], "%Y-%m-%d %H:%M")
        except Exception:
            since = until - timedelta(days=_DEFAULT_DAYS)
    else:
        since = until - timedelta(days=_DEFAULT_DAYS)
    return int(since.timestamp() * 1000), int(until.timestamp() * 1000)


def _fn_create(params: dict) -> str:
    """폰 사진으로 새 판 초안 제작. 조회·검증은 즉시, 조판(pull·변환·렌더)은 백그라운드
    (도구 실행 60초 제한 + '거대 작업=백그라운드' 원칙). 진행은 op:status 로 확인."""
    state = _load_state()
    if _building_status(state):
        return _fail("이미 제작이 진행 중입니다 — '신문' 탭에서 진행 상황을 확인하세요.")
    cap = int(params.get("photo_limit") or state.get("photo_limit") or _DEFAULT_LIMIT)
    since_ms, until_ms = _since_ms(state, params)

    # 폰에서 후보 조회(즉시 — 폰 미연결 등은 여기서 바로 알림)
    try:
        candidates = _adb_photos_since(since_ms, until_ms)
    except RuntimeError as e:
        return _fail(str(e))
    uploads = _pending_uploads(_load_uploads())

    # 미발행 초안이 있으면 갈아엎고 다시 만든다(호수 재사용, 실렸던 가족 사진은 후보로 복귀).
    old_draft = next((e for e in state["editions"] if not e.get("published_at")), None)
    if old_draft:
        no = old_draft.get("no")
        shutil.rmtree(_EDITIONS / old_draft["id"], ignore_errors=True)
        ups = _load_uploads()
        for u in ups:
            if u.get("used_in") == old_draft["id"]:
                u["used_in"] = None
        _save_uploads(ups)
        uploads = _pending_uploads(ups)

        def _drop(st):
            st["editions"] = [e for e in st["editions"] if e.get("published_at")]
        state = _mutate_state(_drop)
    else:
        no = max([e.get("no", 0) for e in state["editions"]], default=0) + 1

    if not candidates and not uploads:
        f = datetime.fromtimestamp(since_ms / 1000).strftime("%m/%d")
        return _fail(f"{f} 이후 폰에 새 사진이 없습니다 (가족이 보낸 사진도 없음).")
    picked = _sample_photos(candidates, cap)
    # 안 뽑힌 후보는 pool 로 판에 동봉 — 편집(remove_photo)에서 빈 자리를 채우는 재료.
    picked_set = {p[0] for p in picked}
    pool = [[src, ms] for src, ms in candidates if src not in picked_set]

    base_id = datetime.now().strftime("%Y-%m-%d")
    existing = {e["id"] for e in state["editions"]}
    eid, i = base_id, 2
    while eid in existing or (_EDITIONS / eid).exists():
        eid = f"{base_id}-{i}"
        i += 1

    def _clear_err(st):
        st.pop("last_build_error", None)
    _mutate_state(_clear_err)
    _set_building({"eid": eid, "no": no, "stage": f"사진 {len(picked)}장 가져오는 중"})
    t = threading.Thread(
        target=_build_edition,
        args=(eid, no, picked, uploads, since_ms, until_ms, pool),
        daemon=True,
    )
    t.start()
    msg = (f"제 {no} 호 제작 시작 — 후보 {len(candidates)}장 중 {len(picked)}장"
           + (f" + 가족 사진 {len(uploads)}장" if uploads else "")
           + " 조판 중입니다. 잠시 후 '신문' 탭에서 초안을 확인하세요.")
    return _ok([], success=True, building=True, edition_id=eid, message=msg)


def _build_edition(eid: str, no: int, picked: list, uploads: list,
                   since_ms: int, until_ms: int, pool: list) -> None:
    """백그라운드 조판 — pull → GPS·장소 → 웹판 → 섹션 → HTML → state 반영."""
    try:
        ed_dir = _EDITIONS / eid
        photos_dir = ed_dir / "photos"
        photos_dir.mkdir(parents=True, exist_ok=True)
        shutil.rmtree(_TMP_PULL, ignore_errors=True)
        _TMP_PULL.mkdir(parents=True, exist_ok=True)

        # 폰 → 맥 pull (병렬 4)
        done = [0]

        def _pull_one(idx_photo):
            idx, (src, ms) = idx_photo
            ext = os.path.splitext(src)[1].lower() or ".jpg"
            dst = _TMP_PULL / f"{idx:03d}{ext}"
            ok = _adb_pull(src, dst)
            done[0] += 1
            if done[0] % 8 == 0:
                _set_building({"eid": eid, "no": no,
                               "stage": f"사진 가져오는 중 {done[0]}/{len(picked)}"})
            return (idx, src, ms, dst) if ok else None

        with ThreadPoolExecutor(max_workers=4) as ex:
            pulled = [p for p in ex.map(_pull_one, enumerate(picked)) if p]
        if not pulled and not uploads:
            raise RuntimeError("사진을 폰에서 가져오지 못했습니다 — USB 연결을 확인해 주세요.")

        # GPS(원본에서만) → 장소, 웹판 생성(EXIF 제거)
        _set_building({"eid": eid, "no": no, "stage": f"사진 {len(pulled)}장 변환·장소 확인 중"})

        def _process(one):
            idx, src, ms, tmp = one
            gps = _gps_from_exif(tmp)
            place = _reverse_geocode(*gps) if gps else ""
            fname = f"{idx:03d}.jpg"
            if not _make_web_photo(tmp, photos_dir / fname):
                return None
            dt = datetime.fromtimestamp(ms / 1000)
            # src(폰 경로)·ms 는 편집(remove_photo)의 제외 목록·자리 계산용 — 렌더러는 무시.
            return {"file": fname, "src": src, "ms": ms, "date": dt.strftime("%Y-%m-%d"),
                    "time": dt.strftime("%H:%M"), "place": place}

        with ThreadPoolExecutor(max_workers=4) as ex:
            processed = [p for p in ex.map(_process, pulled) if p]
        shutil.rmtree(_TMP_PULL, ignore_errors=True)
        processed.sort(key=lambda p: p["ms"])

        # 날짜별 섹션
        days, by_day = [], {}
        for p in processed:
            by_day.setdefault(p["date"], []).append(p)
        for d in sorted(by_day):
            dt = datetime.strptime(d, "%Y-%m-%d")
            label = f"{dt.month}월 {dt.day}일 ({_WEEKDAYS_KO[dt.weekday()]})"
            places = list(dict.fromkeys(p["place"] for p in by_day[d] if p["place"]))
            days.append({"date": d, "label": label, "places": places,
                         "photos": [{"file": p["file"], "src": p["src"], "ms": p["ms"],
                                     "time": p["time"], "place": p["place"]}
                                    for p in by_day[d]]})

        # 가족이 보내온 사진(미사용 업로드) 합류
        family, used_files = [], []
        for j, u in enumerate(uploads):
            src = _UPLOADS / u.get("file", "")
            if not src.exists():
                continue
            fname = f"f_{j:03d}.jpg"
            if _make_web_photo(src, photos_dir / fname):
                # src_upload=업로드 원본 파일명 — 편집에서 빼면 그 업로드를 후보에서도 제외하는 열쇠.
                family.append({"file": fname, "name": u.get("name", ""), "at": u.get("at", ""),
                               "src_upload": u.get("file", "")})
                used_files.append(u.get("file"))

        total = len(processed) + len(family)
        if total == 0:
            shutil.rmtree(ed_dir, ignore_errors=True)
            raise RuntimeError("사진 처리에 실패했습니다 (변환 가능한 사진이 없음).")

        _set_building({"eid": eid, "no": no, "stage": "신문 조판 중"})
        all_places = list(dict.fromkeys(p["place"] for p in processed if p["place"]))
        cover = processed[0]["file"] if processed else (family[0]["file"] if family else "")
        edition = {
            "id": eid, "no": no, "created_at": _now_iso(),
            "range_from": datetime.fromtimestamp(since_ms / 1000).strftime("%Y-%m-%d"),
            "range_to": datetime.fromtimestamp(until_ms / 1000).strftime("%Y-%m-%d"),
            "days": days, "family": family, "photo_count": total,
            # 편집 재료 — pool: 안 뽑힌 후보(폰 경로+datetaken), excluded: 사용자가 뺀 사진의 원본.
            "pool": pool, "excluded": [],
        }
        (ed_dir / "edition.json").write_text(json.dumps(edition, ensure_ascii=False, indent=1),
                                             encoding="utf-8")

        summary = {"id": eid, "no": no, "created_at": edition["created_at"],
                   "captured_until": datetime.fromtimestamp(until_ms / 1000).strftime("%Y-%m-%d %H:%M"),
                   "range_from": edition["range_from"], "range_to": edition["range_to"],
                   "photo_count": total, "places": all_places,
                   "cover": cover, "published_at": None}

        def _append(st):
            st["editions"] = [e for e in st["editions"] if e["id"] != eid] + [summary]
        state = _mutate_state(_append)
        _render_edition_html(eid, state)

        # 업로드 소비 표시(발행 전엔 초안에 묶임 — 초안 갈아엎으면 되살아남)
        if used_files:
            ups = _load_uploads()
            for u in ups:
                if u.get("file") in used_files:
                    u["used_in"] = eid
            _save_uploads(ups)
        _set_building(None)
    except Exception as e:
        shutil.rmtree(_TMP_PULL, ignore_errors=True)

        def _err(st):
            st.pop("building", None)
            st["last_build_error"] = str(e)
        _mutate_state(_err)


# ── 편집 (초안 사진 빼기·보충) ──────────────────────────────────────────

def _resolve_draft(state: dict, params: dict):
    """편집 대상 초안 판 — edition_id 생략 시 초안이 하나면 그 판. (판 dict, 실패응답)"""
    eid = (params.get("edition_id") or "").strip()
    drafts = [e for e in state["editions"] if not e.get("published_at")]
    if not eid:
        if len(drafts) == 1:
            return drafts[0], None
        if not drafts:
            return None, _fail("편집할 초안이 없습니다 — '제작' 탭에서 먼저 신문을 만드세요.")
        return None, _fail("초안이 여럿입니다 — edition_id 를 지정해 주세요.")
    ed = next((e for e in state["editions"] if e["id"] == eid), None)
    if not ed:
        return None, _fail(f"판을 찾을 수 없습니다: {eid}")
    if ed.get("published_at"):
        return None, _fail(f"제 {ed.get('no')} 호는 이미 발행되어 편집할 수 없습니다 — 편집은 발행 전(초안)에만 됩니다.")
    return ed, None


def _load_edition(eid: str):
    try:
        return json.loads((_EDITIONS / eid / "edition.json").read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_edition(edition: dict) -> None:
    p = _EDITIONS / edition["id"] / "edition.json"
    p.write_text(json.dumps(edition, ensure_ascii=False, indent=1), encoding="utf-8")


def _recount_edition(edition: dict) -> None:
    """빼기·보충 후 photo_count·day places 재계산 + 빈 날 제거."""
    edition["days"] = [d for d in edition.get("days", []) if d.get("photos")]
    for d in edition["days"]:
        d["places"] = list(dict.fromkeys(p.get("place") for p in d["photos"] if p.get("place")))
    edition["photo_count"] = (sum(len(d["photos"]) for d in edition["days"])
                              + len(edition.get("family") or []))


def _sync_summary(edition: dict) -> dict:
    """edition.json → state 요약(사진 수·장소·표지) 동기화 후 최신 state 반환."""
    day_photos = [p for d in edition.get("days", []) for p in d.get("photos", [])]
    fam = edition.get("family") or []
    places = list(dict.fromkeys(p.get("place") for p in day_photos if p.get("place")))
    cover = day_photos[0]["file"] if day_photos else (fam[0]["file"] if fam else "")

    def _f(st):
        for e in st["editions"]:
            if e["id"] == edition["id"]:
                e["photo_count"] = edition.get("photo_count", 0)
                e["places"] = places
                e["cover"] = cover
    return _mutate_state(_f)


def _pool_candidates(edition: dict) -> list:
    excluded = set(edition.get("excluded") or [])
    return [c for c in (edition.get("pool") or []) if c[0] not in excluded]


def _next_edit_name(photos_dir: Path) -> str:
    n = 0
    while (photos_dir / f"e{n:03d}.jpg").exists():
        n += 1
    return f"e{n:03d}.jpg"


def _insert_day_photo(edition: dict, photo: dict) -> None:
    """보충 사진을 날짜 자리에 끼움 — 없는 날이면 섹션 신설, 시간순 유지."""
    days = edition.setdefault("days", [])
    day = next((d for d in days if d.get("date") == photo["date"]), None)
    if day is None:
        dt = datetime.strptime(photo["date"], "%Y-%m-%d")
        day = {"date": photo["date"],
               "label": f"{dt.month}월 {dt.day}일 ({_WEEKDAYS_KO[dt.weekday()]})",
               "places": [], "photos": []}
        days.append(day)
        days.sort(key=lambda d: d.get("date", ""))
    day["photos"].append(photo)
    day["photos"].sort(key=lambda p: p.get("ms") or 0)


def _refill_from_pool(edition: dict, photos_dir: Path, ref_ms: int):
    """뺀 자리 보충 — 뺀 사진과 촬영 시각이 가까운 후보부터 폰에서 당겨 채운다.
    (보충 사진, 실패 사유) 반환. 폰 미연결이면 pull 이 전부 실패한다."""
    cands = sorted(_pool_candidates(edition), key=lambda c: abs(int(c[1]) - ref_ms))
    if not cands:
        return None, "남은 후보 사진이 없어 그대로 둡니다"
    excluded = edition.setdefault("excluded", [])
    _TMP_PULL.mkdir(parents=True, exist_ok=True)
    for src, ms in cands[:6]:
        ext = os.path.splitext(src)[1].lower() or ".jpg"
        tmp = _TMP_PULL / f"refill{ext}"
        tmp.unlink(missing_ok=True)
        if not _adb_pull(src, tmp):
            continue   # 폰 미연결·파일 소실 — 다음 후보
        gps = _gps_from_exif(tmp)
        place = _reverse_geocode(*gps) if gps else ""
        fname = _next_edit_name(photos_dir)
        ok = _make_web_photo(tmp, photos_dir / fname)
        tmp.unlink(missing_ok=True)
        if not ok:
            excluded.append(src)   # 변환 불가 후보는 다시 시도하지 않는다
            continue
        dt = datetime.fromtimestamp(int(ms) / 1000)
        photo = {"file": fname, "src": src, "ms": int(ms), "date": dt.strftime("%Y-%m-%d"),
                 "time": dt.strftime("%H:%M"), "place": place}
        _insert_day_photo(edition, photo)
        edition["pool"] = [c for c in edition.get("pool") or [] if c[0] != src]
        return photo, ""
    return None, "폰에서 후보 사진을 가져오지 못했습니다 — USB 연결 후 다시 빼면 채워집니다"


def _fn_photos(params: dict) -> str:
    """초안 사진 목록(편집용) — 각 사진의 날짜·시간·장소·썸네일 + 남은 후보 수."""
    state = _load_state()
    ed, err = _resolve_draft(state, params)
    if err:
        return err
    edition = _load_edition(ed["id"])
    if edition is None:
        return _fail("판 데이터를 읽지 못했습니다 — '제작'을 다시 실행해 주세요.")
    photos_dir = _EDITIONS / ed["id"] / "photos"
    rows = []
    for day in edition.get("days", []):
        for p in day.get("photos", []):
            rows.append({
                "edition_id": ed["id"], "file": p.get("file", ""),
                "title": f"{day.get('label', day.get('date', ''))} {p.get('time', '')}".strip(),
                "meta": f"📍 {p['place']}" if p.get("place") else "장소 정보 없음",
                "place": p.get("place", ""),
                "image": f"/photo/thumbnail?path={photos_dir / p.get('file', '')}",
            })
    for f in edition.get("family") or []:
        rows.append({
            "edition_id": ed["id"], "file": f.get("file", ""),
            "title": f"가족이 보낸 사진 · {f.get('name', '')}",
            "meta": f.get("at", "") or "가족 업로드",
            "place": "",
            "image": f"/photo/thumbnail?path={photos_dir / f.get('file', '')}",
        })
    pool_left = len(_pool_candidates(edition))
    if edition.get("pool") is None:
        hint = "이 초안은 후보 정보가 없어 빼기만 됩니다 (새로 만든 초안부터 자동 보충)."
    elif pool_left:
        hint = f"사진을 빼면 남은 후보 {pool_left}장에서 자동으로 채웁니다 (폰 USB 연결 시)."
    else:
        hint = "남은 후보 사진이 없어, 빼면 그 자리는 비웁니다."
    return _ok(rows, edition_id=ed["id"], pool_left=pool_left,
               message=f"제 {ed.get('no')} 호 초안 · 사진 {len(rows)}장. {hint}")


def _fn_remove_photo(params: dict) -> str:
    """초안에서 사진 1장 빼기 — 남은 후보가 있으면 자동으로 채우고 신문을 다시 조판."""
    state = _load_state()
    if _building_status(state):
        return _fail("제작이 진행 중입니다 — 끝난 뒤 편집해 주세요.")
    ed, err = _resolve_draft(state, params)
    if err:
        return err
    fname = (params.get("file") or "").strip()
    if not fname:
        return _fail("뺄 사진의 file 을 지정해 주세요.")
    edition = _load_edition(ed["id"])
    if edition is None:
        return _fail("판 데이터를 읽지 못했습니다 — '제작'을 다시 실행해 주세요.")
    photos_dir = _EDITIONS / ed["id"] / "photos"

    removed, is_family = None, False
    for day in edition.get("days", []):
        hit = next((p for p in day.get("photos", []) if p.get("file") == fname), None)
        if hit:
            removed = hit
            day["photos"].remove(hit)
            break
    if removed is None:
        hit = next((f for f in edition.get("family") or [] if f.get("file") == fname), None)
        if hit:
            removed, is_family = hit, True
            edition["family"].remove(hit)
    if removed is None:
        return _fail(f"사진을 찾을 수 없습니다: {fname}")

    (photos_dir / fname).unlink(missing_ok=True)
    filled, why_not = None, ""
    if is_family:
        # 뺀 가족 사진은 업로드 후보에서도 제외 — 다음 판에 되살아나지 않게.
        srcu = removed.get("src_upload")
        if srcu:
            ups = _load_uploads()
            for u in ups:
                if u.get("file") == srcu:
                    u["rejected"] = True
                    u["used_in"] = None
            _save_uploads(ups)
    else:
        if removed.get("src"):
            edition.setdefault("excluded", []).append(removed["src"])
        if edition.get("pool") is not None:
            ref_ms = int(removed.get("ms") or 0)
            filled, why_not = _refill_from_pool(edition, photos_dir, ref_ms)

    _recount_edition(edition)
    _save_edition(edition)
    state = _sync_summary(edition)
    _render_edition_html(ed["id"], state)

    if filled:
        where = f"{filled['date']} {filled['time']}" + (f" · {filled['place']}" if filled.get("place") else "")
        msg = f"사진을 뺐습니다 — 후보에서 1장을 새로 채웠습니다 ({where})."
    elif is_family:
        msg = "가족이 보낸 사진을 뺐습니다 — 이 사진은 다음 신문에도 실리지 않습니다."
    else:
        msg = "사진을 뺐습니다." + (f" {why_not}." if why_not else "")
    return _ok([], success=True, filled=bool(filled),
               photo_count=edition.get("photo_count", 0), message=msg)


def _fn_publish(params: dict) -> str:
    eid = (params.get("edition_id") or "").strip()
    state = _load_state()
    if not eid:
        drafts = [e for e in state["editions"] if not e.get("published_at")]
        if len(drafts) != 1:
            return _fail("발행할 판의 edition_id 를 지정해 주세요.")
        eid = drafts[0]["id"]
    ed = next((e for e in state["editions"] if e["id"] == eid), None)
    if not ed:
        return _fail(f"판을 찾을 수 없습니다: {eid}")
    if ed.get("published_at"):
        return _fail(f"이미 발행된 판입니다: 제 {ed.get('no')} 호")
    if not (_EDITIONS / eid / "index.html").exists():
        return _fail("판 파일이 없습니다 — '제작'을 다시 실행해 주세요.")
    if not state.get("slug"):
        state["slug"] = _new_slug()
    if not state.get("public_base"):
        state["public_base"] = _default_public_base()
    ed["published_at"] = _now_iso()
    _save_state(state)
    url = _public_url(state)
    row = _edition_row(state, ed)
    return _ok([row], success=True, public_url=url,
               message=f"제 {ed.get('no')} 호 발행 완료 — 가족에게 이 주소를 공유하세요: {url}")


def _fn_detail(params: dict) -> str:
    eid = (params.get("edition_id") or "").strip()
    state = _load_state()
    ed = next((e for e in state["editions"] if e["id"] == eid), None)
    if not ed:
        return _fail(f"판을 찾을 수 없습니다: {eid}")
    row = _edition_row(state, ed)
    pub_url = _public_url(state)
    info = {
        "제호": f"제 {ed.get('no')} 호",
        "기간": f"{ed.get('range_from')} ~ {ed.get('range_to')}",
        "사진": f"{ed.get('photo_count', 0)}장",
        "장소": ", ".join(ed.get("places", [])) or "(위치 정보 없음)",
        "상태": f"발행됨 ({ed.get('published_at')})" if ed.get("published_at") else "초안",
        "미리보기": _preview_url(eid),
        "공개 주소": (pub_url + f"e/{eid}/") if ed.get("published_at") and pub_url else "(발행 후 생김)",
    }
    return _ok([row], edition=row, info=[{"k": k, "v": v} for k, v in info.items()])


def _fn_delete(params: dict) -> str:
    eid = (params.get("edition_id") or "").strip()
    state = _load_state()
    ed = next((e for e in state["editions"] if e["id"] == eid), None)
    if not ed:
        return _fail(f"판을 찾을 수 없습니다: {eid}")
    if ed.get("published_at") and str(params.get("force")).lower() not in ("true", "1"):
        return _fail("발행된 판입니다. 정말 지우려면 force: true 로 다시 호출하세요 (공개 주소에서도 사라집니다).")
    shutil.rmtree(_EDITIONS / eid, ignore_errors=True)
    state["editions"] = [e for e in state["editions"] if e["id"] != eid]
    _save_state(state)
    ups = _load_uploads()
    for u in ups:
        if u.get("used_in") == eid:
            u["used_in"] = None
    _save_uploads(ups)
    return _ok([], success=True, message=f"제 {ed.get('no')} 호 삭제 — 실렸던 가족 사진은 다음 판 후보로 되돌렸습니다.")


def _fn_comments(params: dict) -> str:
    gb_path = _DATA / "guestbook.json"
    try:
        entries = json.loads(gb_path.read_text(encoding="utf-8"))
    except Exception:
        entries = []
    eid = (params.get("edition_id") or "").strip()
    if eid:
        entries = [e for e in entries if e.get("edition") == eid]
    rows = [{"title": e.get("name", ""), "meta": f"{e.get('at', '')}"
             + (f" · {e.get('edition')}" if e.get("edition") else ""),
             "summary": e.get("msg", "")}
            for e in reversed(entries[-200:])]
    msg = "" if rows else "아직 방명록 글이 없습니다."
    return _ok(rows, message=msg)


def _fn_uploads(params: dict) -> str:
    rows = []
    for u in reversed(_load_uploads()[-200:]):
        p = _UPLOADS / u.get("file", "")
        if not p.exists():
            continue
        status = (f"제 {u.get('used_in')} 판에 실림" if u.get("used_in")
                  else "편집에서 뺌 — 다시 실리지 않습니다" if u.get("rejected")
                  else "다음 신문 후보")
        rows.append({
            "title": u.get("name", ""),
            "meta": f"{u.get('at', '')} · {status}",
            "image": f"/photo/thumbnail?path={p}",
            "path": str(p),
        })
    msg = "" if rows else "가족이 보낸 사진이 아직 없습니다. 신문 맨 아래 '사진 보내기'로 보낼 수 있어요."
    return _ok(rows, message=msg)


def _fn_config(params: dict) -> str:
    state = _load_state()
    changed = []
    if (params.get("title") or "").strip():
        state["title"] = params["title"].strip()
        changed.append("제호")
    if params.get("photo_limit") not in (None, ""):
        try:
            state["photo_limit"] = max(4, min(200, int(float(params["photo_limit"]))))
            changed.append("사진 수 상한")
        except Exception:
            pass
    if (params.get("public_base") or "").strip():
        state["public_base"] = params["public_base"].strip()
        changed.append("공개 base")
    _save_state(state)
    return _ok([], success=True,
               settings={"title": state["title"], "photo_limit": state["photo_limit"],
                         "public_base": state["public_base"]},
               message=("저장: " + ", ".join(changed)) if changed else "변경 없음.")


_OP_DISPATCHERS = {
    "family_news_op": {
        "status": _fn_status,
        "create": _fn_create,
        "photos": _fn_photos,
        "remove_photo": _fn_remove_photo,
        "publish": _fn_publish,
        "detail": _fn_detail,
        "delete": _fn_delete,
        "comments": _fn_comments,
        "uploads": _fn_uploads,
        "config": _fn_config,
    },
}
_OP_DEFAULTS = {
    "family_news_op": "status",
}


def execute(tool_input: dict, context) -> str:
    """가족신문 도구 실행 (ToolContext 시그니처)."""
    tool_name = context.tool_name
    try:
        if tool_name in _OP_DISPATCHERS:
            op = tool_input.get("op") or _OP_DEFAULTS.get(tool_name)
            fn = _OP_DISPATCHERS[tool_name].get(op)
            if not fn:
                return json.dumps({"success": False, "error": f"알 수 없는 op: {op}"}, ensure_ascii=False)
            return fn(tool_input)
        return json.dumps({"success": False, "error": f"Unknown tool: {tool_name}"}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"오류: {e}"}, ensure_ascii=False)
