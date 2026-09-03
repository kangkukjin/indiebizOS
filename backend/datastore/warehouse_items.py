"""비즈니스 아이템 → 공유창고 물질화 (가레지세일 진열).

business.db 의 아이템 하나하나를 문서 파일로 만들어
`공유창고/<비즈니스 레벨>/<비즈니스 이름>/<제목>.md` (+ 첨부 사진 파일들) 로 자동 배치하고,
그 위에 사람이 한눈에 훑는 **카탈로그 한 장**을 얹는다:
`공유창고/<레벨>/<비즈니스 이름> 카탈로그.html` (사진 축소판을 data URI 로 심은 자족 문서,
디자인은 warehouse_catalog.py). 낱개 문서는 AI·이웃 폴러가 집어가는 알갱이, 카탈로그는
사람이 여는 표지 — 같은 데이터의 두 읽기다.
방문자(사람·AI)가 문의 없이 카탈로그 전체를 본다 — "묻기→놓기". 사진은 개별 파일이라
공개면 서빙(EXIF 제거·썸네일)의 기존 관문을 그대로 지난다.

★파생 구역 경계: 이 모듈은 자기가 만든 파일만 지우고 다시 쓴다. 레벨 폴더의 숨김
사이드카(.gen_items.json — 점 파일이라 서빙 walk 에 안 잡힘)가 기계 소유 목록의 단일
진실이고, 사용자가 손으로 던진 파일·폴더(예: 매매/)는 목록에 없으므로 절대 건드리지
않는다. 비즈니스문서.md 와 같은 "DB 바뀌면 갱신 — 볼 때 렌더" 카덴스로
api_portal._ensure_warehouses() 가 부른다.
"""
import json
import re
import shutil
from pathlib import Path

_SIDECAR = ".gen_items.json"
_FP_MARK = "<!-- catalog:"          # 카탈로그 첫 줄의 지문 주석 — 재생성 여부를 싸게 판정
_BAD = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def _safe_name(text: str, fallback: str) -> str:
    """제목 → 파일명. 한글 보존, 경로 문자만 제거, 과장 방지 80자 컷."""
    name = _BAD.sub(" ", (text or "")).strip().strip(".")
    name = re.sub(r"\s+", " ", name)[:80].strip()
    return name or fallback


def _image_paths(item: dict) -> list:
    """attachment_path = 이미지 경로 JSON 배열(레거시: 단일 문자열)."""
    raw = (item or {}).get("attachment_path") or ""
    if not raw:
        return []
    try:
        v = json.loads(raw)
        return v if isinstance(v, list) else [raw]
    except Exception:
        return [raw]


def _read_fp(p: Path) -> str:
    """이미 있는 카탈로그의 지문(첫 줄 주석). 없거나 못 읽으면 빈 문자열."""
    try:
        with p.open("r", encoding="utf-8") as f:
            head = f.readline(200)
    except Exception:
        return ""
    if head.startswith(_FP_MARK):
        return head[len(_FP_MARK):].split("-->")[0].strip()
    return ""


def _stamp(p: Path) -> tuple:
    """(크기, mtime) — 사진의 '바뀌었나' 신호. 사라졌으면 (0, 0)."""
    try:
        st = p.stat()
        return (st.st_size, int(st.st_mtime))
    except Exception:
        return (0, 0)


def _fingerprint(payload) -> str:
    """카탈로그 재생성 판단용 지문. 내용이 그대로면 파일에 손대지 않는다 —
    괜히 다시 쓰면 mtime 이 흔들려 이웃 폴러가 `changed` 로 오독한다(사진 재인코딩도 낭비)."""
    import hashlib
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:16]


def _desired(bm, levels: dict, house: str = "", contacts=None) -> dict:
    """DB → 원하는 상태.

    desired[level][폴더명][파일명] = ("text", 본문) | ("copy", 원본 Path) | ("catalog", (지문, spec))
    폴더명 "" = 레벨 폴더 바로 아래(카탈로그가 여기 산다 — 폴더를 열지 않아도 보이는 표지).
    """
    want = {lv: {} for lv in levels}
    for b in bm.get_businesses():
        lv = int(b.get("level") or 0)
        if lv not in want:
            continue
        items = bm.get_business_items(b["id"])
        if not items:
            continue
        folder = _safe_name(b.get("name") or "", f"비즈니스 {b['id']}")
        files = want[lv].setdefault(folder, {})
        used = set()
        cat_items = []
        for it in items:
            base = _safe_name(it.get("title") or "", f"아이템 {it['id']}")
            if base in used:                      # 같은 제목 둘 → id 로 갈라 결정적 유지
                base = f"{base} ({it['id']})"
            used.add(base)
            body = f"# {(it.get('title') or '').strip()}\n\n{(it.get('details') or '').strip()}\n"
            files[base + ".md"] = ("text", body)
            photos = []
            for i, src in enumerate(_image_paths(it), 1):
                sp = Path(src)
                if sp.is_file() and sp.suffix:    # 사진은 문서 옆에 같은 제목 접두로 (이름순 정렬 시 묶임)
                    name = f"{base} {i}{sp.suffix.lower()}"
                    files[name] = ("copy", sp)
                    # 카탈로그가 가리키는 건 *창고 안의 사본*(공개면 서빙 대상)이지 원본이 아니다.
                    photos.append({"rel": f"{folder}/{name}", "src": sp})
            cat_items.append({"title": it.get("title") or "", "details": it.get("details") or "",
                              "photos": photos})

        spec = {"warehouse_title": house,
                "business": {"name": b.get("name") or "", "description": b.get("description") or ""},
                "contacts": list(contacts or []),
                "items": cat_items}
        # 지문은 *보이는 것*만 — 사진은 경로+크기+mtime 으로(내용이 같으면 다시 굽지 않는다).
        fp = _fingerprint({**spec, "items": [
            {"title": ci["title"], "details": ci["details"],
             "photos": [[p["rel"], *_stamp(p["src"])] for p in ci["photos"]]}
            for ci in cat_items]})
        root = want[lv].setdefault("", {})
        root[f"{folder} 카탈로그.html"] = ("catalog", (fp, spec))
    return want


def _apply(level_dir: Path, want: dict) -> None:
    """한 레벨 폴더를 원하는 상태로 수렴. 사이드카에 적힌 파일만 청소 대상."""
    side = level_dir / _SIDECAR
    try:
        old = json.loads(side.read_text(encoding="utf-8"))
    except Exception:
        old = {}

    new_side = {}
    for folder, files in want.items():
        fd = level_dir / folder if folder else level_dir
        fd.mkdir(parents=True, exist_ok=True)
        for name, (kind, payload) in files.items():
            p = fd / name
            try:
                if kind == "text":
                    if not p.exists() or p.read_text(encoding="utf-8") != payload:
                        p.write_text(payload, encoding="utf-8")
                elif kind == "catalog":
                    fp, spec = payload
                    if _read_fp(p) != fp:        # 지문이 같으면 손대지 않는다(사진 재인코딩 회피)
                        import warehouse_catalog
                        p.write_text(f"{_FP_MARK}{fp} -->\n" + warehouse_catalog.render(spec),
                                     encoding="utf-8")
                else:  # copy — 크기 비교로 재복사 판단(이미지는 내용 불변 파일)
                    if not p.exists() or p.stat().st_size != payload.stat().st_size:
                        shutil.copy2(str(payload), str(p))  # eventloop-ok: 시딩 수렴 1회(크기 같으면 건너뜀) — 소형 이미지
            except Exception:
                continue
        new_side[folder] = sorted(files.keys())

    # 청소: 전에 만들었는데 이제 원하지 않는 파일만. 폴더는 비었을 때만 제거(사용자 파일 보호).
    for folder, names in old.items():
        keep = set(want.get(folder, {}).keys())
        fd = level_dir / folder if folder else level_dir
        for name in names:
            if name not in keep:
                try:
                    (fd / name).unlink(missing_ok=True)
                except Exception:
                    pass
        if not folder:
            # 레벨 폴더 자체는 절대 rmdir 하지 않는다 — 여기 사는 건 카탈로그뿐이고,
            # 그 옆엔 사용자가 손으로 던져 넣은 파일들이 산다(위에서 낡은 카탈로그만 지웠다).
            continue
        if folder not in want:
            try:
                fd.rmdir()
            except Exception:
                pass
            if fd.exists():
                # 사용자 파일이 남아 못 지움 → 빈 목록으로 계속 추적해 다음 sync 가 rmdir 재시도
                # (사용자 파일까지 사라진 뒤 기계 폴더가 빈 채 영영 남는 것 방지).
                new_side[folder] = []

    try:
        if new_side != old:
            if new_side:
                side.write_text(json.dumps(new_side, ensure_ascii=False, indent=1), encoding="utf-8")
            else:
                side.unlink(missing_ok=True)
    except Exception:
        pass


def sync(bm, level_dirs: dict, house: str = "", contacts=None) -> None:
    """전체 동기화. level_dirs = {레벨 int: 창고 폴더 Path}. 실패해도 서빙을 깨지 않는다.

    house·contacts = 카탈로그 머리말·꼬리말에 들어갈 창고 이름과 연락처((라벨, 값) 목록).
    창고의 신원은 api_portal 이 쥐고 있으므로 여기로 넘겨받는다(모듈이 신원을 재발명하지 않게).
    """
    try:
        want = _desired(bm, level_dirs, house=house, contacts=contacts)
    except Exception:
        return
    for lv, d in level_dirs.items():
        try:
            _apply(d, want.get(lv, {}))
        except Exception:
            continue
