"""슬라이드 **톤 레지스트리** — 톤 × 렌더 방식 지원 매트릭스의 단일 소스 (2026-08-06).

강의 창의 선택은 두 축뿐이다:

  ① 톤(design tone)      — 이 파일의 TONES. 슬라이드의 전체적인 룩.
  ② 렌더 방식(render)    — 이 파일의 RENDERS. 그 룩을 무엇으로 만들 것인가.

    native  "이미지 only"   이미지 모델이 글자까지 한 장에 통째로 그림  (slide_native.AESTHETICS)
    image   "이미지+글자"   글자 없는 그림 + HTML 타이포 레이어 합성    (slide_styles.STYLES)
    html    "HTML"          글자도 그림도 HTML                          (shadcn_slides.DESIGN_SYSTEMS)

구조(layout/composition)는 **AI가 내용을 보고 고른다** — 사람이 고르는 축이 아니다.

덱의 `design_system` 문자열이 이 두 축을 인코딩한다:

    vintage_book          → 톤=vintage_book, 렌더=html    (접두 없음)
    native_vintage_book   → 톤=vintage_book, 렌더=native
    image_ink_blueprint   → 톤=ink_blueprint, 렌더=image

★세 렌더러가 각자 자기 스타일 테이블을 갖고 있고 키 이름도 어긋난다(청사진 톤이 native 에선
`blueprint`, html 에선 `sf_blueprint`). 그 매핑을 여기 한 곳에 모아두는 것이 이 파일의 일이다.
표면(강의 창)은 `/lectures/design-systems` 로 이 매트릭스를 받아 드롭다운을 그린다 —
프론트엔드에 톤 목록을 하드코딩하지 말 것(그 드리프트가 은퇴한 톤을 계속 노출시킨 원인이었다).
"""

from __future__ import annotations


# 렌더 방식 — key 는 design_system 접두와 같다(html 은 접두 없음).
RENDERS = [
    {
        "key": "native",
        "ko": "이미지 only",
        "desc": "이미지 모델이 글자까지 한 장에 통째로 — 가장 완성도 높은 룩. 나중에 글자 수정은 재생성",
    },
    {
        "key": "image",
        "ko": "이미지+글자",
        "desc": "글자 없는 그림 위에 또렷한 타이포를 얹어 합성 — 그림은 전면, 글자는 선명",
    },
    {
        "key": "html",
        "ko": "HTML",
        "desc": "글자도 그림도 HTML — 빠르고 무료, 만든 뒤 필드 직접 편집 가능",
    },
]

DEFAULT_RENDER = "native"
DEFAULT_TONE = "vintage_book"


# 톤 × 경로. 값 = 그 렌더러의 스타일 키(None = 그 방식 미지원).
#   native → slide_native.AESTHETICS
#   image  → slide_styles.STYLES
#   html   → shadcn_slides.DESIGN_SYSTEMS
TONES = {
    "vintage_book": {
        "ko": "빈티지북",
        "desc": "베이지 종이 + 청·적갈 잉크 · 책 강의·인문",
        "paths": {"native": "vintage_book", "image": "vintage_book", "html": "vintage_book"},
    },
    "academic_paper": {
        "ko": "학술 논문",
        "desc": "미색 + 진남 + 진홍 강조 · 연구·논문",
        "paths": {"native": "academic_paper", "image": "academic_paper", "html": "academic_paper"},
    },
    "tech_minimal": {
        "ko": "테크 미니멀",
        "desc": "프리미엄 다크 + 글래스 · 개발자·테크",
        "paths": {"native": "tech_minimal", "image": "tech_minimal", "html": "tech_minimal"},
    },
    "magazine_modern": {
        "ko": "잡지 모던",
        "desc": "흰·검·적색 · 편집·홍보",
        "paths": {"native": "magazine_modern", "image": None, "html": "magazine_modern"},
    },
    "dark_keynote": {
        "ko": "다크 키노트",
        "desc": "칠흑 배경 + 청록·호박 발광 · 극적·프리미엄",
        "paths": {"native": "dark_keynote", "image": None, "html": None},
    },
    "blueprint": {
        "ko": "청사진",
        "desc": "인디고 선화 + 산호 강조 · 도해·구조",
        # ★native 는 "blueprint", html 은 "sf_blueprint" — 같은 톤의 서로 다른 이름.
        "paths": {"native": "blueprint", "image": None, "html": "sf_blueprint"},
    },
    "ink_blueprint": {
        "ko": "잉크+청사진",
        "desc": "손그림 잉크 + 청사진 격자 · 인문·개념",
        "paths": {"native": None, "image": "ink_blueprint", "html": None},
    },
    "cinematic_3d": {
        "ko": "시네마틱 3D",
        "desc": "빛·유리·볼륨 렌더 · 표지·임팩트",
        "paths": {"native": None, "image": "cinematic_3d", "html": None},
    },
    "isometric": {
        "ko": "아이소메트릭",
        "desc": "30도 도면 + 파스텔 · 시스템·구조",
        "paths": {"native": None, "image": "isometric", "html": None},
    },
    "lineart_duotone": {
        "ko": "라인아트 듀오톤",
        "desc": "미니멀 선화 + 두 색 · 모던·고급",
        "paths": {"native": None, "image": "lineart_duotone", "html": None},
    },
}


# ── design_system 문자열 ↔ (톤, 렌더) ────────────────────────────────

def parse_design_system(design: str) -> tuple[str, str]:
    """`design_system` → (tone, render). 모르는 값은 기본값으로 접는다(절대 예외 없음).

    옛 표기 `native` / `native:<톤>` 도 받는다(콜론 구분 레거시).
    """
    d = (design or "").strip()
    if not d:
        return DEFAULT_TONE, DEFAULT_RENDER
    for render in ("native", "image"):
        for sep in ("_", ":"):
            if d.startswith(render + sep):
                tone = d.split(sep, 1)[1] or DEFAULT_TONE
                return (tone if tone in TONES else DEFAULT_TONE), render
        if d == render:  # 접두만 있고 톤이 없는 옛 값
            return DEFAULT_TONE, render
    # 접두 없음 = HTML 경로. "default"(디자인 시스템 없음)는 톤이 아니므로 그대로 통과시킨다.
    return d, "html"


def build_design_system(tone: str, render: str) -> str:
    """(tone, render) → `design_system` 문자열. UI·API가 조립할 때 쓰는 정본."""
    tone = tone if tone in TONES else DEFAULT_TONE
    if render == "html":
        return tone
    return f"{render}_{tone}"


def supports(tone: str, render: str) -> bool:
    t = TONES.get(tone)
    return bool(t and t["paths"].get(render))


def style_key(tone: str, render: str) -> str | None:
    """톤을 그 렌더러가 아는 스타일 키로 변환. 미지원이면 None."""
    t = TONES.get(tone)
    return t["paths"].get(render) if t else None


def renders_for(tone: str) -> list[str]:
    t = TONES.get(tone)
    return [r for r in ("native", "image", "html") if t and t["paths"].get(r)] if t else []


def valid_design_systems() -> set[str]:
    """레지스트리에서 파생한 유효 `design_system` 전체 — lecture_store 검증과 동기 유지용."""
    out = {"default"}  # HTML 경로의 '디자인 시스템 없음'
    for tone, meta in TONES.items():
        for render, key in meta["paths"].items():
            if key:
                out.add(build_design_system(tone, render))
    return out


def matrix() -> dict:
    """표면(강의 창)에 그대로 내려보내는 선택지 매트릭스."""
    return {
        "renders": RENDERS,
        "tones": [
            {
                "key": key,
                "ko": meta["ko"],
                "desc": meta["desc"],
                "renders": renders_for(key),
            }
            for key, meta in TONES.items()
        ],
        "default_tone": DEFAULT_TONE,
        "default_render": DEFAULT_RENDER,
    }
