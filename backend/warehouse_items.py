"""비즈니스 아이템 → 공유창고 물질화 (가레지세일 진열).

business.db 의 아이템 하나하나를 문서 파일로 만들어
`공유창고/<비즈니스 레벨>/<비즈니스 이름>/<제목>.md` (+ 첨부 사진 파일들) 로 자동 배치한다.
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


def _desired(bm, levels: dict) -> dict:
    """DB → 원하는 상태. desired[level][폴더명][파일명] = ("text", 본문) | ("copy", 원본 Path)."""
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
        for it in items:
            base = _safe_name(it.get("title") or "", f"아이템 {it['id']}")
            if base in used:                      # 같은 제목 둘 → id 로 갈라 결정적 유지
                base = f"{base} ({it['id']})"
            used.add(base)
            body = f"# {(it.get('title') or '').strip()}\n\n{(it.get('details') or '').strip()}\n"
            files[base + ".md"] = ("text", body)
            for i, src in enumerate(_image_paths(it), 1):
                sp = Path(src)
                if sp.is_file() and sp.suffix:    # 사진은 문서 옆에 같은 제목 접두로 (이름순 정렬 시 묶임)
                    files[f"{base} {i}{sp.suffix.lower()}"] = ("copy", sp)
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
        fd = level_dir / folder
        fd.mkdir(parents=True, exist_ok=True)
        for name, (kind, payload) in files.items():
            p = fd / name
            try:
                if kind == "text":
                    if not p.exists() or p.read_text(encoding="utf-8") != payload:
                        p.write_text(payload, encoding="utf-8")
                else:  # copy — 크기 비교로 재복사 판단(이미지는 내용 불변 파일)
                    if not p.exists() or p.stat().st_size != payload.stat().st_size:
                        shutil.copy2(str(payload), str(p))
            except Exception:
                continue
        new_side[folder] = sorted(files.keys())

    # 청소: 전에 만들었는데 이제 원하지 않는 파일만. 폴더는 비었을 때만 제거(사용자 파일 보호).
    for folder, names in old.items():
        keep = set(want.get(folder, {}).keys())
        fd = level_dir / folder
        for name in names:
            if name not in keep:
                try:
                    (fd / name).unlink(missing_ok=True)
                except Exception:
                    pass
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


def sync(bm, level_dirs: dict) -> None:
    """전체 동기화. level_dirs = {레벨 int: 창고 폴더 Path}. 실패해도 서빙을 깨지 않는다."""
    try:
        want = _desired(bm, level_dirs)
    except Exception:
        return
    for lv, d in level_dirs.items():
        try:
            _apply(d, want.get(lv, {}))
        except Exception:
            continue
