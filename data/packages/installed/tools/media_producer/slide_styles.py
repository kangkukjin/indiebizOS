"""프리미엄 이미지 슬라이드 스타일 프리셋 — [engines:slide]{style:...}의 룩 정의.

각 프리셋 = (일러스트 스타일 프롬프트 래퍼) + (팔레트·폰트·합성 규칙). 한 덱은 한 프리셋으로
고정하면 NotebookLM처럼 일관된 '책'이 된다. 갤러리 비교(2026-06-04)로 검증된 4종.

일러스트는 Nano Banana Pro가 그리고, 제목·캡션은 HTML 타이포 레이어로 또렷하게 얹는다.
"""

# 공통 일러스트 지시 (스타일 무관) — AI가 준 '장면'에 이 래퍼를 씌워 생성 프롬프트를 만든다.
# 여백 위치(상단/측면/중앙)는 구성 아키타입마다 달라 scene에 포함시킨다(여기엔 두지 않음).
COMMON_SUFFIX = (
    " Compose the concept clearly and elegantly with a strong focal hierarchy. "
    "Absolutely no text, no words, no letters, no captions, no labels rendered in the image."
)

STYLES = {
    "ink_blueprint": {
        "ko": "잉크+청사진",
        "illus": ("Refined editorial concept illustration, hand-drawn fine ink linework plus subtle "
            "blueprint grid and faint technical leader lines, strict two-tone palette of deep navy ink "
            "and warm terracotta on warm cream paper with faint grain, premium vintage textbook-"
            "illustration aesthetic, restrained and elegant."),
        "dark": False,
        "bg": "#F2ECDD", "fade": "242,236,221",
        "title_color": "#1B2A47", "kicker_color": "#B0552F", "sub_color": "#54607A",
        "title_font": "'Gowun Batang',serif", "title_weight": "700",
        "font_links": ["https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=Noto+Sans+KR:wght@400;500;700;900&family=JetBrains+Mono:wght@500&display=swap"],
    },
    "cinematic_3d": {
        "ko": "시네마틱 3D",
        "illus": ("Cinematic 3D render, dramatic volumetric lighting, premium octane quality, glossy "
            "translucent glass and polished chrome forms, deep dark navy-to-black gradient background, "
            "teal and amber rim light, fine particle bokeh, soft god rays, glossy reflective floor, "
            "ultra-detailed, photoreal."),
        "dark": True,
        "bg": "#06080E", "fade": "6,8,14",
        "title_color": "#F4F7FB", "kicker_color": "#34E0D0", "sub_color": "rgba(244,247,251,0.72)",
        "title_font": "'Pretendard Variable',sans-serif", "title_weight": "800",
        "font_links": ["https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css",
                       "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500&display=swap"],
    },
    "isometric": {
        "ko": "아이소메트릭",
        "illus": ("Clean isometric 3D vector illustration, precise 30-degree axonometric projection, soft "
            "pastel palette with one warm orange accent, subtle long shadows, flat-tech infographic "
            "aesthetic on a light cool-grey background, crisp clean linework, modular and structural."),
        "dark": False,
        "bg": "#EAF0F7", "fade": "234,240,247",
        "title_color": "#1E2A44", "kicker_color": "#E8722E", "sub_color": "#54607A",
        "title_font": "'Pretendard Variable',sans-serif", "title_weight": "800",
        "font_links": ["https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css",
                       "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500&display=swap"],
    },
    "lineart_duotone": {
        "ko": "라인아트 듀오톤",
        "illus": ("Minimal elegant line-art illustration, single consistent thin stroke weight, strict "
            "duotone of deep indigo and coral on warm off-white, lots of negative space, premium luxury "
            "editorial feel, restrained and sophisticated, a few faint technical leader lines."),
        "dark": False,
        "bg": "#F6F3EC", "fade": "246,243,236",
        "title_color": "#2B2D6B", "kicker_color": "#E0644C", "sub_color": "#54607A",
        "title_font": "'Pretendard Variable',sans-serif", "title_weight": "800",
        "font_links": ["https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css",
                       "https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@500&display=swap"],
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
