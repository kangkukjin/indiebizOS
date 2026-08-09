"""**이미지+글자** 렌더 방식의 톤 정의 — 덱 design_system 이 `image_<톤>` 일 때 쓰인다.

각 톤 = (일러스트 스타일 프롬프트 래퍼 `illus`) + (팔레트·폰트·합성 규칙). 한 덱은 한 톤으로
고정하면 NotebookLM처럼 일관된 '책'이 된다. 갤러리 비교(2026-06-04)로 검증된 4종.

일러스트는 Nano Banana Pro가 그리고, 제목·캡션은 HTML 타이포 레이어로 또렷하게 얹는다.

★여기 있는 톤 키는 `slide_tones.TONES` 의 `paths.image` 값과 일치해야 한다 —
톤이 어느 렌더 방식을 지원하는지의 단일 소스는 slide_tones.py 다.
"""

# 공통 일러스트 지시 (스타일 무관) — AI가 준 '장면'에 이 래퍼를 씌워 생성 프롬프트를 만든다.
# 여백 위치(상단/측면/중앙)는 구성 아키타입마다 달라 scene에 포함시킨다(여기엔 두지 않음).
COMMON_SUFFIX = (
    " Compose the concept clearly and elegantly with a strong focal hierarchy. "
    "Absolutely no text, no words, no letters, no captions, no labels rendered in the image."
)

STYLES = {

    # ── 2026-08-06 그리드 확장: 공용 톤 3종의 이미지+글자 자산 ──────────────
    # 팔레트·폰트는 HTML 판(shadcn_slides.DESIGN_SYSTEMS)과 동일 정체성 — 같은 톤이
    # 렌더 방식만 갈아탈 수 있게. illus 래퍼만 이 경로 전용으로 저작.
    "vintage_book": {
        "ko": "빈티지북",
        "illus": ("Refined vintage textbook book-plate illustration, fine ink linework with delicate "
            "cross-hatching and subtle warm watercolor tinting, palette of deep navy ink and warm "
            "terracotta on aged cream paper with faint grain and gentle foxing, classic scholarly "
            "book illustration aesthetic, warm and restrained."),
        "dark": False,
        "bg": "#F3ECD6", "fade": "243,236,214",
        "title_color": "#2C3E6F", "kicker_color": "#A55A3E", "sub_color": "#5E5236",
        "title_font": "'Gowun Batang',serif", "title_weight": "700",
        "font_links": ["https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=Noto+Sans+KR:wght@400;500;700;900&family=JetBrains+Mono:wght@500&display=swap"],
    },

    # ── 2026-08-09 확장: 남은 3톤의 이미지+글자 자산 ──────────────────────
    # illus = native AESTHETICS 의 화풍에서 **글자·라벨 요소를 걷어낸** 순수 일러스트 판
    # (글자는 HTML 타이포 레이어 몫 — COMMON_SUFFIX 의 no-text 규칙과 한 몸).
    # 팔레트·폰트 = HTML 판(shadcn_design)과 동일 정체성.
    "blueprint": {
        "ko": "청사진",
        "illus": ("Technical blueprint diagram illustration, indigo ink linework on warm pale-blue "
            "drafting paper, faint grid and precise leader lines with round anchor dots, exact "
            "schematic figures drawn with fine even strokes, a single coral accent reserved for "
            "the key part or flow, engineered and intellectual, clean drafting-table aesthetic."),
        "dark": False,
        "bg": "#E9EFF7", "fade": "233,239,247",
        "title_color": "#26305E", "kicker_color": "#D86541", "sub_color": "#525D7A",
        "title_font": "'IBM Plex Sans KR','Noto Sans KR',sans-serif", "title_weight": "700",
        "font_links": ["https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;700;900&family=JetBrains+Mono:wght@400;500&display=swap"],
    },
    "architect": {
        "ko": "아키텍트",
        "illus": ("Systems-architect isometric diagram plate illustration (NotebookLM style), flat "
            "low-rise isometric slabs and cubes in exactly two block colours — muted brick "
            "terracotta and desaturated steel blue — plus neutral slate grey, deep slate-navy "
            "drafting linework with dimension lines, leader lines with round anchor dots and "
            "measurement arrows, warm ivory paper with a very faint drafting grid and small "
            "dot-grid patches, occasional fine ink-line mechanical detail, confident systematic "
            "textbook-plate aesthetic."),
        "dark": False,
        "bg": "#EFEAE0", "fade": "239,234,224",
        "title_color": "#2E3947", "kicker_color": "#CE6440", "sub_color": "#5A6472",
        "title_font": "'Pretendard Variable','Noto Sans KR',sans-serif", "title_weight": "800",
        "font_links": ["https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css",
                       "https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap"],
    },
    "ink_orange": {
        "ko": "먹과 주황",
        "illus": ("Bold editorial infographic-poster illustration, heavy charcoal-black flat pictogram "
            "icons drawn with thick uniform ink strokes (objects, machines, houses, networks), "
            "exactly one vivid orange reserved for FLOW — thick connector lines, arrows, radiating "
            "arcs, organic road-like networks and circular loops — staging a deliberate contrast "
            "between black geometric structure and orange organic movement, bright ivory paper, "
            "graphic declarative poster-like clarity."),
        "dark": False,
        "bg": "#F2EFE6", "fade": "242,239,230",
        "title_color": "#2A2D32", "kicker_color": "#EE5F1C", "sub_color": "#55524B",
        "title_font": "'Pretendard Variable','Noto Sans KR',sans-serif", "title_weight": "900",
        "font_links": ["https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css",
                       "https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&display=swap"],
    },
}


def is_image_style(style: str) -> bool:
    return bool(style) and style in STYLES


def style_keys_help() -> str:
    return " / ".join(f"{k}({v['ko']})" for k, v in STYLES.items())


def build_illustration_prompt(scene: str, style: str) -> str:
    """AI가 준 개념 장면(scene) + 스타일 래퍼 + 공통 접미 = 최종 이미지 프롬프트."""
    s = STYLES[style]
    return f"{s['illus']} Scene: {scene.strip()}{COMMON_SUFFIX}"
