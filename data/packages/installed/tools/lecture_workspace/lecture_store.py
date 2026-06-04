"""
lecture_store.py - 강의 데이터 레이어 (deck.json + materials/ + slides/)

저장 위치: {indiebizOS_root}/outputs/lectures/{lecture_id}/

deck.json 스키마 (version 1):
{
  "version": 1,
  "lecture_id": "harness-1bu",
  "title": "하네스란 무엇인가? 1부",
  "audience": "일반인",
  "thesis": "한 줄 요지",
  "duration_minutes": 60,
  "design_system": "vintage_book",
  "created_at": "2026-05-23T19:00:00",
  "updated_at": "2026-05-23T19:00:00",
  "slide_order": ["s001", "s002"],
  "slides": {
    "s001": {
      "id": "s001",
      "title": "표지",
      "layout": "hero_illustration",
      "spec_file": "slides/s001.json",
      "png_file": "slides/s001.png",
      "created_at": "...",
      "updated_at": "..."
    }
  },
  "cumulative_memo": {
    "tone_preferred": [],
    "tone_rejected": [],
    "metaphors_adopted": [],
    "decisions": []
  },
  "materials": [
    {"file": "materials/하네스_원고.docx", "type": "docx", "added_at": "..."}
  ]
}

설계 원칙:
- lecture_id는 안정적 슬러그. 폴더명·deck.json 안 양쪽에 동일.
- slide_id는 s001, s002 ... 형식. 재배열은 slide_order만 갱신 (파일 안 건드림).
- 모든 경로는 절대경로로 반환 (호출자 cwd에 의존하지 않도록).
- deck.json 쓰기는 항상 updated_at 갱신.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional


DECK_SCHEMA_VERSION = 1

# 유효한 design_system 값.
#  - CSS 디자인: media_producer/shadcn_slides.py의 DESIGN_SYSTEMS와 일치 (default는 UI에서 숨김 — 호환 위해 허용 유지)
#  - 프리미엄 이미지: media_producer/slide_styles.py의 STYLES (slide_image 경로)
#  - "auto": 슬라이드마다 AI가 이미지 스타일 선택
VALID_DESIGN_SYSTEMS = {
    # CSS
    "default",
    "vintage_book",
    "academic_paper",
    "tech_minimal",
    "magazine_modern",
    "sf_blueprint",
    # 프리미엄 이미지 (slide_image)
    "ink_blueprint",
    "cinematic_3d",
    "isometric",
    "lineart_duotone",
    # AI 자율
    "auto",
}

# indiebizOS 루트 경로 — 이 파일은 data/packages/installed/tools/lecture_workspace/lecture_store.py 에 있음
# parents[5] = indiebizOS 루트 (lecture_workspace/ → tools/ → installed/ → packages/ → data/ → indiebizOS/)
INDIEBIZOS_ROOT = Path(__file__).resolve().parents[5]
LECTURES_ROOT = INDIEBIZOS_ROOT / "outputs" / "lectures"


# ─────────────────────────────────────────────────────────────────────
# Slug 생성 — 한글 제목 → ascii 슬러그
# ─────────────────────────────────────────────────────────────────────

# 한글 자모 로마자 표기 (국어의 로마자 표기법 약식)
# Hangul 음절 U+AC00 ~ U+D7A3 = 초성(19) × 중성(21) × 종성(28)
_CHOSEONG = [
    'g', 'kk', 'n', 'd', 'tt', 'r', 'm', 'b', 'pp', 's',
    'ss', '', 'j', 'jj', 'ch', 'k', 't', 'p', 'h'
]
_JUNGSEONG = [
    'a', 'ae', 'ya', 'yae', 'eo', 'e', 'yeo', 'ye', 'o', 'wa',
    'wae', 'oe', 'yo', 'u', 'wo', 'we', 'wi', 'yu', 'eu', 'ui', 'i'
]
_JONGSEONG = [
    '', 'k', 'k', 'k', 'n', 'n', 'n', 't', 'l', 'k',
    'm', 'l', 'l', 'l', 'p', 'l', 'm', 'p', 'p', 't',
    't', 'ng', 't', 't', 'k', 't', 'p', 't'
]


def _romanize_hangul(text: str) -> str:
    """한글을 로마자로 약식 변환. 한글이 아닌 글자는 그대로 유지.

    예: "하네스란 무엇인가? 1부" → "haneseuran mueosinga? 1bu"
    """
    out = []
    for ch in text:
        code = ord(ch)
        if 0xAC00 <= code <= 0xD7A3:
            idx = code - 0xAC00
            cho = idx // (21 * 28)
            jung = (idx % (21 * 28)) // 28
            jong = idx % 28
            out.append(_CHOSEONG[cho] + _JUNGSEONG[jung] + _JONGSEONG[jong])
        else:
            out.append(ch)
    return ''.join(out)


def _slugify(text: str) -> str:
    """한글/특수문자 포함 텍스트를 ascii 슬러그로 변환.

    1순위: unidecode (있으면)
    2순위: 한글 자모 로마자화 (내장)
    3순위: hex 폴백
    """
    # 1. unidecode 시도
    try:
        from unidecode import unidecode  # type: ignore
        ascii_text = unidecode(text)
    except ImportError:
        # 2. 내장 한글 로마자화
        ascii_text = _romanize_hangul(text)

    # 3. 소문자화, 영숫자/공백/하이픈만 남기기
    slug = ascii_text.lower()
    slug = re.sub(r'[^a-z0-9\s\-]', '', slug)
    # 4. 공백/하이픈 그룹 → 단일 하이픈
    slug = re.sub(r'[\s\-]+', '-', slug).strip('-')
    # 5. 길이 제한
    slug = slug[:60].rstrip('-')

    # 6. 너무 짧으면 hex 폴백
    if not slug or len(slug) < 2:
        slug = f"lecture-{uuid.uuid4().hex[:6]}"

    return slug


def generate_unique_lecture_id(title: str) -> str:
    """제목으로부터 충돌 없는 lecture_id 생성. 이미 있으면 -2, -3 ...

    LECTURES_ROOT가 없으면 생성.
    """
    LECTURES_ROOT.mkdir(parents=True, exist_ok=True)

    base = _slugify(title)
    candidate = base
    n = 2
    while (LECTURES_ROOT / candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    return candidate


# ─────────────────────────────────────────────────────────────────────
# 경로 헬퍼
# ─────────────────────────────────────────────────────────────────────

def lecture_dir(lecture_id: str) -> Path:
    return LECTURES_ROOT / lecture_id


def deck_path(lecture_id: str) -> Path:
    return lecture_dir(lecture_id) / "deck.json"


def materials_dir(lecture_id: str) -> Path:
    return lecture_dir(lecture_id) / "materials"


def slides_dir(lecture_id: str) -> Path:
    return lecture_dir(lecture_id) / "slides"


def lecture_exists(lecture_id: str) -> bool:
    return deck_path(lecture_id).exists()


# ─────────────────────────────────────────────────────────────────────
# deck.json 읽기/쓰기
# ─────────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def read_deck(lecture_id: str) -> dict:
    """deck.json 읽기. 파일 없으면 FileNotFoundError."""
    path = deck_path(lecture_id)
    if not path.exists():
        raise FileNotFoundError(f"강의 데이터가 없습니다: {lecture_id} (경로: {path})")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_deck(lecture_id: str, deck: dict) -> None:
    """deck.json 저장. updated_at 자동 갱신."""
    deck["updated_at"] = _now_iso()
    path = deck_path(lecture_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(deck, f, ensure_ascii=False, indent=2)


# ─────────────────────────────────────────────────────────────────────
# 강의 CRUD
# ─────────────────────────────────────────────────────────────────────

def create_lecture(
    title: str,
    audience: Optional[str] = None,
    thesis: Optional[str] = None,
    duration_minutes: Optional[int] = None,
    design_system: str = "vintage_book",
) -> dict:
    """새 강의 생성. 폴더 + 빈 deck.json + materials/ + slides/ 생성. 새 deck 반환."""
    if design_system not in VALID_DESIGN_SYSTEMS:
        raise ValueError(
            f"알 수 없는 design_system: {design_system!r}. "
            f"사용 가능: {sorted(VALID_DESIGN_SYSTEMS)}"
        )
    lecture_id = generate_unique_lecture_id(title)
    ld = lecture_dir(lecture_id)
    ld.mkdir(parents=True, exist_ok=True)
    materials_dir(lecture_id).mkdir(exist_ok=True)
    slides_dir(lecture_id).mkdir(exist_ok=True)

    now = _now_iso()
    deck = {
        "version": DECK_SCHEMA_VERSION,
        "lecture_id": lecture_id,
        "title": title,
        "audience": audience or "",
        "thesis": thesis or "",
        "duration_minutes": duration_minutes or 0,
        "design_system": design_system,
        "created_at": now,
        "updated_at": now,
        "slide_order": [],
        "slides": {},
        "cumulative_memo": {
            "tone_preferred": [],
            "tone_rejected": [],
            "metaphors_adopted": [],
            "decisions": [],
        },
        "materials": [],
    }
    write_deck(lecture_id, deck)
    return deck


def list_lectures() -> list[dict]:
    """모든 강의의 요약 목록. {lecture_id, title, audience, slide_count, updated_at}."""
    if not LECTURES_ROOT.exists():
        return []
    out = []
    for entry in sorted(LECTURES_ROOT.iterdir()):
        if not entry.is_dir():
            continue
        dp = entry / "deck.json"
        if not dp.exists():
            continue
        try:
            with open(dp, "r", encoding="utf-8") as f:
                deck = json.load(f)
            out.append({
                "lecture_id": deck.get("lecture_id", entry.name),
                "title": deck.get("title", ""),
                "audience": deck.get("audience", ""),
                "slide_count": len(deck.get("slide_order", [])),
                "updated_at": deck.get("updated_at", ""),
            })
        except Exception as e:
            # 손상된 deck.json은 목록에 표시하되 에러 마킹
            out.append({
                "lecture_id": entry.name,
                "title": "(읽기 실패)",
                "error": str(e),
            })
    # updated_at 역순 정렬 (최근 먼저)
    out.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return out


def load_lecture(lecture_id: str) -> dict:
    """deck 전체 + slides_dir/materials_dir 절대경로 반환."""
    deck = read_deck(lecture_id)
    return {
        "deck": deck,
        "slides_dir": str(slides_dir(lecture_id).resolve()),
        "materials_dir": str(materials_dir(lecture_id).resolve()),
        "lecture_dir": str(lecture_dir(lecture_id).resolve()),
    }


_MUTABLE_META_FIELDS = {"title", "audience", "thesis", "duration_minutes", "design_system"}


def update_deck_meta(lecture_id: str, patch: dict) -> dict:
    """deck.json의 메타 필드를 부분 갱신.

    허용 필드: title, audience, thesis, duration_minutes, design_system.
    design_system은 VALID_DESIGN_SYSTEMS 안에 있어야 함.
    slide_order, slides, materials, cumulative_memo 등은 별도 함수로 갱신 (의도 분리).
    """
    deck = read_deck(lecture_id)
    if "design_system" in patch and patch["design_system"] is not None:
        if patch["design_system"] not in VALID_DESIGN_SYSTEMS:
            raise ValueError(
                f"알 수 없는 design_system: {patch['design_system']!r}. "
                f"사용 가능: {sorted(VALID_DESIGN_SYSTEMS)}"
            )
    for key, value in patch.items():
        if key in _MUTABLE_META_FIELDS and value is not None:
            deck[key] = value
    write_deck(lecture_id, deck)
    return deck


def delete_lecture(lecture_id: str) -> dict:
    """강의 폴더 전체 삭제. 호출자가 confirm=True 검증 후 호출."""
    ld = lecture_dir(lecture_id)
    if not ld.exists():
        raise FileNotFoundError(f"강의 폴더가 없습니다: {lecture_id}")
    shutil.rmtree(ld)
    return {"deleted": lecture_id, "path": str(ld)}


# ─────────────────────────────────────────────────────────────────────
# 데크 조작 (순서/슬라이드 삭제)
# ─────────────────────────────────────────────────────────────────────

def reorder_deck(lecture_id: str, new_order: list[str]) -> dict:
    """slide_order 배열만 갱신. 기존 슬라이드 전체를 빠짐없이 포함해야 함."""
    deck = read_deck(lecture_id)
    current = set(deck.get("slide_order", []))
    proposed = list(new_order)
    proposed_set = set(proposed)
    if current != proposed_set:
        missing = current - proposed_set
        extra = proposed_set - current
        raise ValueError(
            f"reorder 검증 실패: 슬라이드 집합이 일치하지 않습니다. "
            f"누락={sorted(missing)}, 잉여={sorted(extra)}"
        )
    if len(proposed) != len(proposed_set):
        raise ValueError("reorder 검증 실패: 중복된 slide_id가 있습니다.")
    deck["slide_order"] = proposed
    write_deck(lecture_id, deck)
    return {"lecture_id": lecture_id, "slide_order": proposed}


def delete_slide(lecture_id: str, slide_id: str) -> dict:
    """특정 슬라이드 파일 삭제 + deck에서 제거."""
    deck = read_deck(lecture_id)
    if slide_id not in deck.get("slides", {}):
        raise ValueError(f"슬라이드를 찾을 수 없습니다: {slide_id}")
    slide_meta = deck["slides"].pop(slide_id)
    if slide_id in deck.get("slide_order", []):
        deck["slide_order"].remove(slide_id)

    # 슬라이드 파일 삭제 (있으면)
    for key in ("spec_file", "png_file"):
        rel = slide_meta.get(key)
        if rel:
            fp = lecture_dir(lecture_id) / rel
            if fp.exists():
                fp.unlink()
    write_deck(lecture_id, deck)
    return {"deleted": slide_id, "remaining": deck["slide_order"]}


# ─────────────────────────────────────────────────────────────────────
# 슬라이드 등록 (Step 2/3에서 AI가 사용할 예정)
# ─────────────────────────────────────────────────────────────────────

def next_slide_id(deck: dict) -> str:
    """기존 slide_id 중 최댓값 + 1을 s001 형식으로."""
    existing = deck.get("slides", {}).keys()
    nums = []
    for sid in existing:
        m = re.match(r'^s(\d+)$', sid)
        if m:
            nums.append(int(m.group(1)))
    next_n = (max(nums) + 1) if nums else 1
    return f"s{next_n:03d}"


def register_slide(
    lecture_id: str,
    slide_id: str,
    title: str,
    layout: str,
    spec_file: str,
    png_file: str,
    insert_at: Optional[int] = None,
) -> dict:
    """슬라이드 메타를 deck에 등록. insert_at이 None이면 끝에 추가, 정수면 그 위치에 삽입.

    spec_file/png_file은 lecture_dir 기준 상대 경로 (예: 'slides/s001.json').
    """
    deck = read_deck(lecture_id)
    now = _now_iso()
    deck.setdefault("slides", {})[slide_id] = {
        "id": slide_id,
        "title": title,
        "layout": layout,
        "spec_file": spec_file,
        "png_file": png_file,
        "created_at": now,
        "updated_at": now,
    }
    order = deck.setdefault("slide_order", [])
    if slide_id in order:
        order.remove(slide_id)
    if insert_at is None or insert_at >= len(order):
        order.append(slide_id)
    else:
        order.insert(max(0, insert_at), slide_id)
    write_deck(lecture_id, deck)
    return deck["slides"][slide_id]


# ─────────────────────────────────────────────────────────────────────
# 재료 관리
# ─────────────────────────────────────────────────────────────────────

def _detect_material_type(filename: str) -> str:
    ext = Path(filename).suffix.lower().lstrip('.')
    if ext in ("docx",):
        return "docx"
    if ext in ("pdf",):
        return "pdf"
    if ext in ("md", "txt"):
        return "text"
    if ext in ("png", "jpg", "jpeg", "webp", "gif"):
        return "image"
    return ext or "unknown"


def add_material_from_file(lecture_id: str, source_path: str) -> dict:
    """외부 파일을 materials/로 복사."""
    src = Path(source_path).expanduser().resolve()
    if not src.exists():
        raise FileNotFoundError(f"원본 파일이 없습니다: {source_path}")
    md = materials_dir(lecture_id)
    md.mkdir(parents=True, exist_ok=True)
    dest = md / src.name
    # 중복 이름이면 -2, -3 ...
    if dest.exists():
        stem = dest.stem
        suffix = dest.suffix
        n = 2
        while True:
            cand = md / f"{stem}-{n}{suffix}"
            if not cand.exists():
                dest = cand
                break
            n += 1
    shutil.copy2(src, dest)

    deck = read_deck(lecture_id)
    rel = f"materials/{dest.name}"
    entry = {
        "file": rel,
        "type": _detect_material_type(dest.name),
        "added_at": _now_iso(),
        "source": str(src),
    }
    deck.setdefault("materials", []).append(entry)
    write_deck(lecture_id, deck)
    return entry


def add_material_from_text(lecture_id: str, text: str, filename: str) -> dict:
    """텍스트를 materials/{filename}에 직접 쓰기."""
    md = materials_dir(lecture_id)
    md.mkdir(parents=True, exist_ok=True)
    safe_name = re.sub(r'[/\\]', '_', filename) or "note.md"
    dest = md / safe_name
    if dest.exists():
        stem = Path(safe_name).stem
        suffix = Path(safe_name).suffix
        n = 2
        while True:
            cand = md / f"{stem}-{n}{suffix}"
            if not cand.exists():
                dest = cand
                break
            n += 1
    with open(dest, "w", encoding="utf-8") as f:
        f.write(text)

    deck = read_deck(lecture_id)
    rel = f"materials/{dest.name}"
    entry = {
        "file": rel,
        "type": _detect_material_type(dest.name),
        "added_at": _now_iso(),
        "source": "inline_text",
    }
    deck.setdefault("materials", []).append(entry)
    write_deck(lecture_id, deck)
    return entry


def remove_material(lecture_id: str, filename: str) -> dict:
    """materials/{filename} 삭제 + deck에서 제거."""
    md = materials_dir(lecture_id)
    fp = md / filename
    if fp.exists():
        fp.unlink()
    deck = read_deck(lecture_id)
    rel = f"materials/{filename}"
    before = len(deck.get("materials", []))
    deck["materials"] = [m for m in deck.get("materials", []) if m.get("file") != rel]
    after = len(deck["materials"])
    write_deck(lecture_id, deck)
    return {"removed": filename, "deleted_from_deck": before - after}


# ─────────────────────────────────────────────────────────────────────
# 누적 메모 (Step 3에서 AI가 사용)
# ─────────────────────────────────────────────────────────────────────

def update_cumulative_memo(lecture_id: str, patch: dict) -> dict:
    """cumulative_memo의 각 키(tone_preferred, tone_rejected 등)에 항목 추가.

    patch는 {"tone_preferred": ["새 항목"], ...} 형식.
    리스트는 append (중복 제거), 다른 타입은 덮어쓰기.
    """
    deck = read_deck(lecture_id)
    memo = deck.setdefault("cumulative_memo", {
        "tone_preferred": [],
        "tone_rejected": [],
        "metaphors_adopted": [],
        "decisions": [],
    })
    for key, value in patch.items():
        if isinstance(value, list):
            existing = memo.setdefault(key, [])
            for item in value:
                if item not in existing:
                    existing.append(item)
        else:
            memo[key] = value
    write_deck(lecture_id, deck)
    return memo
