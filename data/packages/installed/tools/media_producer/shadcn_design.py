"""
shadcn_design.py — HTML 렌더 경로의 비주얼 정체성 상수 (shadcn_slides.py 에서 분리, 2026-08-06 1500줄 규칙)

THEMES = shadcn/ui 테마 색(CSS 변수)만 / DESIGN_SYSTEMS = 색·폰트·배경 텍스처·장식의
일관된 묶음. 순수 데이터 — 로직 금지. 톤 목록의 진실 소스는 slide_tones.py.
"""

# ============================================
# shadcn/ui 테마 색상 (CSS 변수)
# ============================================

THEMES = {
    "default": {
        "background": "0 0% 100%",
        "foreground": "0 0% 3.9%",
        "primary": "0 0% 9%",
        "primary-foreground": "0 0% 98%",
        "secondary": "0 0% 96.1%",
        "secondary-foreground": "0 0% 9%",
        "muted": "0 0% 96.1%",
        "muted-foreground": "0 0% 45.1%",
        "accent": "0 0% 96.1%",
        "border": "0 0% 89.8%",
        "ring": "0 0% 3.9%",
        "radius": "0.5rem"
    },
    "blue": {
        "background": "0 0% 100%",
        "foreground": "222.2 84% 4.9%",
        "primary": "221.2 83.2% 53.3%",
        "primary-foreground": "210 40% 98%",
        "secondary": "210 40% 96.1%",
        "secondary-foreground": "222.2 47.4% 11.2%",
        "muted": "210 40% 96.1%",
        "muted-foreground": "215.4 16.3% 46.9%",
        "accent": "210 40% 96.1%",
        "border": "214.3 31.8% 91.4%",
        "ring": "221.2 83.2% 53.3%",
        "radius": "0.5rem"
    },
    "green": {
        "background": "0 0% 100%",
        "foreground": "240 10% 3.9%",
        "primary": "142.1 76.2% 36.3%",
        "primary-foreground": "355.7 100% 97.3%",
        "secondary": "240 4.8% 95.9%",
        "secondary-foreground": "240 5.9% 10%",
        "muted": "240 4.8% 95.9%",
        "muted-foreground": "240 3.8% 46.1%",
        "accent": "240 4.8% 95.9%",
        "border": "240 5.9% 90%",
        "ring": "142.1 76.2% 36.3%",
        "radius": "0.5rem"
    },
    "purple": {
        "background": "0 0% 100%",
        "foreground": "224 71.4% 4.1%",
        "primary": "262.1 83.3% 57.8%",
        "primary-foreground": "210 20% 98%",
        "secondary": "220 14.3% 95.9%",
        "secondary-foreground": "220.9 39.3% 11%",
        "muted": "220 14.3% 95.9%",
        "muted-foreground": "220 8.9% 46.1%",
        "accent": "220 14.3% 95.9%",
        "border": "220 13% 91%",
        "ring": "262.1 83.3% 57.8%",
        "radius": "0.5rem"
    },
    "orange": {
        "background": "0 0% 100%",
        "foreground": "20 14.3% 4.1%",
        "primary": "24.6 95% 53.1%",
        "primary-foreground": "60 9.1% 97.8%",
        "secondary": "60 4.8% 95.9%",
        "secondary-foreground": "24 9.8% 10%",
        "muted": "60 4.8% 95.9%",
        "muted-foreground": "25 5.3% 44.7%",
        "accent": "60 4.8% 95.9%",
        "border": "20 5.9% 90%",
        "ring": "24.6 95% 53.1%",
        "radius": "0.5rem"
    },
    "dark": {
        "background": "0 0% 3.9%",
        "foreground": "0 0% 98%",
        "primary": "0 0% 98%",
        "primary-foreground": "0 0% 9%",
        "secondary": "0 0% 14.9%",
        "secondary-foreground": "0 0% 98%",
        "muted": "0 0% 14.9%",
        "muted-foreground": "0 0% 63.9%",
        "accent": "0 0% 14.9%",
        "border": "0 0% 14.9%",
        "ring": "0 0% 83.1%",
        "radius": "0.5rem"
    },
    # vintage_book 디자인 시스템 전용 팔레트 — 베이지 종이 + 청색·적갈색 잉크
    "vintage_book": {
        "background": "44 53% 89%",       # #f3ecd6 (베이지 종이)
        "foreground": "222 43% 31%",      # #2c3e6f (청색 잉크)
        "primary": "222 43% 31%",         # 동일한 청색
        "primary-foreground": "44 53% 95%",
        "secondary": "44 38% 84%",        # 베이지 어두운 톤
        "secondary-foreground": "222 43% 31%",
        "muted": "44 30% 82%",
        "muted-foreground": "39 18% 35%", # #5e5236 (회갈색)
        "accent": "16 47% 44%",           # #a55a3e (적갈색)
        "border": "222 25% 60%",
        "ring": "16 47% 44%",
        "radius": "0.25rem"               # 빈티지하게 모서리 덜 둥글게
    },

    # blueprint — 제도 도면 청사진 (연청 제도용지 + 인디고 잉크 + 산호 강조)
    # ★sf_blueprint(다크 네온 HUD)와 다른 톤 — native AESTHETICS["blueprint"]와 같은 정체성.
    "blueprint": {
        "background": "210 45% 94%",      # #e9eff7 (연청 제도용지)
        "foreground": "230 42% 26%",      # #26305e (인디고 잉크)
        "primary": "230 42% 26%",
        "primary-foreground": "210 45% 96%",
        "secondary": "212 38% 88%",       # 연청 카드
        "secondary-foreground": "230 42% 26%",
        "muted": "212 30% 86%",
        "muted-foreground": "225 20% 40%",# #525d7a (슬레이트 인디고)
        "accent": "11 66% 55%",           # #d86541 (산호 — 강조·치수선)
        "border": "226 28% 64%",          # 인디고 옅은 선
        "ring": "11 66% 55%",
        "radius": "0.125rem"              # 도면 양식 — 모서리 거의 직각
    },

    # architect — 아키텍트 (아이보리 + 슬레이트 네이비 잉크 + 벽돌 테라코타·강청 블록)
    # 2026-08-07 The_AI_Architect.pdf 실물 연구에서 증류. native AESTHETICS["architect"]와 동일 정체성.
    "architect": {
        "background": "42 31% 91%",       # #efeae0 (따뜻한 아이보리)
        "foreground": "213 21% 23%",      # #2e3947 (슬레이트 네이비 잉크)
        "primary": "213 43% 35%",         # #33597f (강청 — 블록 2색 중 하나)
        "primary-foreground": "42 31% 95%",
        "secondary": "42 24% 86%",        # 아이보리 어두운 카드
        "secondary-foreground": "213 21% 23%",
        "muted": "42 20% 84%",
        "muted-foreground": "213 12% 40%",# 회슬레이트
        "accent": "16 58% 53%",
        "border": "213 18% 62%",
        "ring": "16 58% 53%",
        "radius": "0.25rem"
    },

    # ink_orange — 먹과 주황 (아이보리 + 먹 픽토그램 잉크 + 주황 흐름)
    # 2026-08-07 Reinventing_the_Internet_with_Personal_AI.pdf 실물 연구에서 증류.
    "ink_orange": {
        "background": "45 27% 93%",       # #f2efe6 (밝은 아이보리)
        "foreground": "220 8% 18%",       # #2a2d32 (먹 챠콜)
        "primary": "220 8% 18%",          # 먹 — 구조의 색
        "primary-foreground": "45 27% 95%",
        "secondary": "45 20% 88%",
        "secondary-foreground": "220 8% 18%",
        "muted": "45 16% 86%",
        "muted-foreground": "220 6% 38%",
        "accent": "21 87% 52%",           # #ee5f1c (주황 — 흐름의 색, 유일한 강조)
        "border": "220 8% 45%",
        "ring": "21 87% 52%",
        "radius": "0.125rem"              # 포스터 양식 — 모서리 거의 직각
    }
}


# ============================================
# 디자인 시스템 — 색·폰트·배경 텍스처·장식의 일관된 묶음
# (THEMES는 색만, DESIGN_SYSTEMS는 그 외 모든 비주얼 정체성)
# ============================================
DESIGN_SYSTEMS = {
    # default — 기존 동작 그대로 (디자인 시스템 없음)
    "default": {
        "theme_override": None,   # 외부에서 받은 theme을 그대로 사용
        "extra_head": "",
        "extra_css": "",
        "extra_html": "",
    },

    # vintage_book — 베이지 종이 + 청·적갈 잉크 + 디스플레이 한글 폰트 + 종이 텍스처
    # 책 강의·인문 발표·고전 양식 콘텐츠에 적합
    "vintage_book": {
        "theme_override": "vintage_book",
        "extra_head": '<link href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=Noto+Serif+KR:wght@400;500;700;900&display=swap" rel="stylesheet">',
        "extra_css": """
/* === vintage_book === */
body {
    font-family: 'Noto Serif KR', 'Apple SD Gothic Neo', serif !important;
    /* 베이지 위에 종이 노이즈 텍스처 + 모서리 음영 */
    background-image:
        radial-gradient(ellipse at top left, rgba(165, 90, 62, 0.07), transparent 60%),
        radial-gradient(ellipse at bottom right, rgba(44, 62, 111, 0.06), transparent 60%),
        url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' /%3E%3CfeColorMatrix values='0 0 0 0 0.3 0 0 0 0 0.25 0 0 0 0 0.18 0 0 0 0.15 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' /%3E%3C/svg%3E") !important;
    background-blend-mode: multiply !important;
}

/* 모든 제목에 디스플레이 폰트 자동 적용 (Gowun Batang — 세련된 모던 명조) */
.slide-container h1,
.slide-container h2,
.slide-container h3 {
    font-family: 'Gowun Batang', 'Noto Serif KR', serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em;
}
.slide-container .badge {
    font-family: 'Gowun Batang', 'Noto Serif KR', serif !important;
    font-weight: 700 !important;
}

/* 본문 텍스트 행간 약간 키움 (출판물 느낌) */
.slide-container p,
.slide-container li,
.slide-container td {
    line-height: 1.85 !important;
}

/* 라벨 (eyebrow) — 청·적갈 양쪽 줄 장식 */
.slide-container [class*="text-xs"][class*="uppercase"],
.slide-container [class*="text-sm"][class*="uppercase"] {
    letter-spacing: 0.15em !important;
    position: relative;
    display: inline-flex;
    align-items: center;
    gap: 12px;
}

/* 테이블 — 양피지 헤더 */
.slide-container table thead {
    background: rgba(165, 90, 62, 0.12);
}
.slide-container table thead th {
    color: hsl(var(--accent)) !important;
    font-family: 'Gowun Batang', 'Noto Serif KR', serif !important;
    font-weight: 700 !important;
}

/* 인용 박스 — 청색 좌측 굵은 선 */
.slide-container blockquote {
    border-color: hsl(var(--accent)) !important;
    background: rgba(165, 90, 62, 0.06) !important;
}

/* 팩트박스 — 양피지 카드 */
.slide-container [class*="rounded-xl"] {
    background: rgba(247, 240, 218, 0.6) !important;
    border-color: rgba(165, 90, 62, 0.3) !important;
}

/* === 일러스트 통합 — 이미지가 양피지 배경에 녹아들도록 === */
/* 일러스트가 있는 슬라이드 — 종이 노이즈를 더 강하게 깔아 이미지가 떠 보이지 않게 */
.slide-container .slide-illustration-bleed {
    position: relative;
}
.slide-container .slide-illustration-bleed::before {
    content: '';
    position: absolute;
    inset: 0;
    background-image:
        radial-gradient(ellipse at center, rgba(243, 236, 214, 0) 30%, rgba(165, 90, 62, 0.04) 100%),
        url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n2'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.65' numOctaves='3' /%3E%3CfeColorMatrix values='0 0 0 0 0.3 0 0 0 0 0.25 0 0 0 0 0.18 0 0 0 0.08 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n2)' /%3E%3C/svg%3E");
    pointer-events: none;
    z-index: 0;
}
/* z-index만 부여 — position은 자식 element의 클래스가 결정 (absolute/relative 유지) */
.slide-container .slide-illustration-bleed > * { z-index: 1; }

/* 일러스트 자체 — 박스 그림자 없이, multiply 블렌드로 종이에 흡수 */
.slide-container .slide-illustration {
    mix-blend-mode: multiply;
    filter: contrast(0.96) saturate(0.92);
}

/* 전면 배경 일러스트 — 페이드 처리 */
.slide-container .slide-illustration-bg {
    mix-blend-mode: multiply;
    opacity: 0.85;
    filter: sepia(0.15) contrast(0.95);
}

/* slide-container에 코너 마크 + 시그니처 */
.slide-container { position: relative; }
.slide-container::before {
    content: '';
    position: absolute;
    top: 28px; left: 36px;
    width: 28px; height: 28px;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 32 32' xmlns='http://www.w3.org/2000/svg' fill='none' stroke='%232c3e6f' stroke-width='1.5'%3E%3Ccircle cx='16' cy='16' r='14'/%3E%3Ccircle cx='16' cy='16' r='4' fill='%23a55a3e' stroke='none'/%3E%3Cline x1='16' y1='2' x2='16' y2='8'/%3E%3Cline x1='16' y1='24' x2='16' y2='30'/%3E%3Cline x1='2' y1='16' x2='8' y2='16'/%3E%3Cline x1='24' y1='16' x2='30' y2='16'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-size: contain;
    opacity: 0.7;
    z-index: 10;
}
.slide-container::after {
    content: 'indieBizOS';
    position: absolute;
    bottom: 24px; right: 32px;
    font-family: 'Gowun Batang', serif;
    font-weight: 700;
    font-size: 11px;
    color: hsl(var(--muted-foreground));
    letter-spacing: 0.15em;
    opacity: 0.5;
    z-index: 10;
}
""",
        "extra_html": "",
    },

    # blueprint — 제도 도면 청사진: 연청 제도용지 + 인디고 잉크 선화 + 산호 강조 + 도면 틀
    # (2026-08-07 신설 — 청사진 톤의 HTML 판. sf_blueprint 다크 HUD와 별개 정체성.)
    "blueprint": {
        "theme_override": "blueprint",
        "extra_head": '<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans+KR:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;700;900&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">',
        "extra_css": """
/* === blueprint — 제도 도면 (연청 용지 + 인디고 선화 + 산호 강조) === */
body {
    font-family: 'IBM Plex Sans KR', 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif !important;
    /* 제도용지 이중 눈금(가는 8px · 굵은 40px) + 모서리 은은한 채색 */
    background-image:
        radial-gradient(ellipse at top right, rgba(216, 101, 65, 0.05), transparent 55%),
        radial-gradient(ellipse at bottom left, rgba(38, 48, 94, 0.07), transparent 60%),
        repeating-linear-gradient(0deg, transparent, transparent 7px, rgba(38, 48, 94, 0.05) 8px),
        repeating-linear-gradient(90deg, transparent, transparent 7px, rgba(38, 48, 94, 0.05) 8px),
        repeating-linear-gradient(0deg, transparent, transparent 39px, rgba(38, 48, 94, 0.10) 40px),
        repeating-linear-gradient(90deg, transparent, transparent 39px, rgba(38, 48, 94, 0.10) 40px) !important;
}

/* 제목 — 인디고 잉크, 공학적 절제 (글로우 없음) */
.slide-container h1,
.slide-container h2,
.slide-container h3 {
    font-family: 'IBM Plex Sans KR', 'Noto Sans KR', sans-serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.015em;
    color: hsl(var(--foreground));
}
.slide-container .badge {
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 500 !important;
}

/* 본문 — 도면 주기(note) 밀도 */
.slide-container p, .slide-container li, .slide-container td {
    line-height: 1.75 !important;
}

/* 라벨 (eyebrow) — 도면 번호처럼: 모노 + 산호 */
.slide-container [class*="text-xs"][class*="uppercase"],
.slide-container [class*="text-sm"][class*="uppercase"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 500 !important;
    letter-spacing: 0.18em !important;
    color: hsl(var(--accent)) !important;
}

/* 표 — 제도 괘선 (수평 룰 중심) */
.slide-container table thead { background: rgba(38, 48, 94, 0.06); }
.slide-container table thead th {
    color: hsl(var(--foreground)) !important;
    font-family: 'JetBrains Mono', monospace !important;
    font-size: 0.85em !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    border-bottom: 2px solid hsl(var(--foreground)) !important;
}
.slide-container table tbody tr {
    border-bottom: 1px solid rgba(38, 48, 94, 0.22) !important;
}

/* 인용 — 산호 치수선 느낌의 좌측 룰 */
.slide-container blockquote {
    border-color: hsl(var(--accent)) !important;
    background: rgba(38, 48, 94, 0.05) !important;
}

/* 팩트박스 — 도면 위 노트 카드 (반투명 종이 + 인디고 실선) */
.slide-container [class*="rounded-xl"] {
    background: rgba(255, 255, 255, 0.55) !important;
    border: 1px solid hsl(var(--border)) !important;
    border-radius: 0.125rem !important;
}

/* 일러스트 통합 — 선화가 제도용지에 잉크처럼 스미도록 (multiply) */
.slide-container .slide-illustration-bleed { position: relative; }
.slide-container .slide-illustration-bleed::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at center, rgba(233, 239, 247, 0) 35%, rgba(38, 48, 94, 0.05) 100%);
    pointer-events: none;
    z-index: 0;
}
.slide-container .slide-illustration-bleed > * { z-index: 1; }
.slide-container .slide-illustration {
    mix-blend-mode: multiply;
    filter: contrast(0.97) saturate(0.9);
}
.slide-container .slide-illustration-bg {
    mix-blend-mode: multiply;
    opacity: 0.88;
    filter: contrast(0.96);
}

/* 코너 마크 — 제도 정합 표식(레지스트레이션 마크) + 시그니처 */
.slide-container { position: relative; }
.slide-container::before {
    content: '';
    position: absolute;
    top: 30px; left: 36px;
    width: 26px; height: 26px;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 32 32' xmlns='http://www.w3.org/2000/svg' fill='none' stroke='%2326305e' stroke-width='1.5'%3E%3Ccircle cx='16' cy='16' r='13'/%3E%3Cline x1='16' y1='0' x2='16' y2='9'/%3E%3Cline x1='16' y1='23' x2='16' y2='32'/%3E%3Cline x1='0' y1='16' x2='9' y2='16'/%3E%3Cline x1='23' y1='16' x2='32' y2='16'/%3E%3Ccircle cx='16' cy='16' r='2.5' fill='%23d86541' stroke='none'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-size: contain;
    opacity: 0.65;
    z-index: 10;
}
.slide-container::after {
    content: 'indiebiz.os — DWG';
    position: absolute;
    bottom: 26px; right: 34px;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    font-size: 10px;
    color: hsl(var(--muted-foreground));
    letter-spacing: 0.18em;
    opacity: 0.55;
    z-index: 10;
}
""",
        # 도면 시트 틀 — 이중 괘선. 텅 빈 중앙 메시지 한 장도 '설계 도면 위'로 보이게 하는 정체성.
        "extra_html": (
            "<div style=\"position:absolute; inset:16px; border:1.5px solid rgba(38,48,94,0.38); "
            "border-radius:2px; pointer-events:none; z-index:9\"></div>"
            "<div style=\"position:absolute; inset:22px; border:1px solid rgba(38,48,94,0.16); "
            "border-radius:1px; pointer-events:none; z-index:9\"></div>"
        ),
    },

    # architect — 아키텍트: 아이보리 제도용지 + 슬레이트 네이비 잉크 + 벽돌·강청 도해
    # (2026-08-07 신설 — The_AI_Architect.pdf 12페이지 실물 연구에서 증류. 정체성 장치:
    #  모눈+코너 도트 패치 / 테라코타 핵심문장 배너(blockquote) / 강청 솔리드 표 헤더 / 콜아웃 카드)
    "architect": {
        "theme_override": "architect",
        "extra_head": '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css"><link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700;900&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">',
        "extra_css": """
/* === architect — 시스템 설계 도해 (아이보리 + 슬레이트 잉크 + 벽돌·강청) === */
body {
    font-family: 'Pretendard Variable', 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif !important;
    /* 아이보리 용지 + 아주 옅은 제도 모눈 + 모서리 음영 */
    background-image:
        radial-gradient(ellipse at top left, rgba(46, 57, 71, 0.05), transparent 55%),
        radial-gradient(ellipse at bottom right, rgba(206, 100, 64, 0.05), transparent 55%),
        repeating-linear-gradient(0deg, transparent, transparent 39px, rgba(46, 57, 71, 0.06) 40px),
        repeating-linear-gradient(90deg, transparent, transparent 39px, rgba(46, 57, 71, 0.06) 40px) !important;
}

/* 제목 — 슬레이트 잉크, 기하학적 산세리프 (PDF의 Inter 볼드 좌상단 헤드라인) */
.slide-container h1,
.slide-container h2,
.slide-container h3 {
    font-family: 'Pretendard Variable', 'Noto Sans KR', sans-serif !important;
    font-weight: 800 !important;
    letter-spacing: -0.02em !important;
    color: hsl(var(--foreground));
}
.slide-container .badge {
    font-family: 'JetBrains Mono', 'Noto Sans KR', monospace !important;
    font-weight: 500 !important;
}

/* 본문 — 큼직하고 여유로운 행간 (PDF 본문 톤) */
.slide-container p, .slide-container li, .slide-container td {
    line-height: 1.75 !important;
    font-weight: 450;
}

/* 라벨 (eyebrow) — 도면 주기: 모노 + 강청 */
.slide-container [class*="text-xs"][class*="uppercase"],
.slide-container [class*="text-sm"][class*="uppercase"] {
    font-family: 'JetBrains Mono', 'Noto Sans KR', monospace !important;
    font-weight: 500 !important;
    letter-spacing: 0.16em !important;
    color: hsl(var(--primary)) !important;
}

/* 표 — 강청 솔리드 헤더 밴드 + 교차 행 (PDF p.3 표 그대로) */
.slide-container table thead { background: hsl(var(--primary)) !important; }
.slide-container table thead th {
    color: hsl(var(--primary-foreground)) !important;
    font-weight: 700 !important;
    border-bottom: none !important;
}
.slide-container table tbody tr { border-bottom: 1px solid rgba(46, 57, 71, 0.22) !important; }
.slide-container table tbody tr:nth-child(odd) { background: rgba(46, 57, 71, 0.06); }

/* 인용 — 테라코타 핵심문장 배너 (PDF의 풀폭 주황 배너: 흰 굵은 글자) */
.slide-container blockquote {
    background: hsl(var(--accent)) !important;
    border: none !important;
    border-left: none !important;
    color: hsl(var(--primary-foreground)) !important;
    font-weight: 700;
    font-style: normal !important;
    box-shadow: 0 2px 10px rgba(46, 57, 71, 0.18);
}
.slide-container blockquote p, .slide-container blockquote strong {
    color: hsl(var(--primary-foreground)) !important;
}

/* 팩트박스 — 콜아웃 카드 (밝은 카드 + 가는 잉크 테두리 + 낮은 그림자) */
.slide-container [class*="rounded-xl"] {
    background: rgba(250, 248, 242, 0.85) !important;
    border: 1px solid rgba(46, 57, 71, 0.45) !important;
    border-radius: 0.25rem !important;
    box-shadow: 3px 3px 0 rgba(46, 57, 71, 0.12);
}

/* 일러스트 통합 — 도해가 용지에 잉크처럼 스미도록 (multiply) */
.slide-container .slide-illustration-bleed { position: relative; }
.slide-container .slide-illustration-bleed::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at center, rgba(239, 234, 224, 0) 35%, rgba(46, 57, 71, 0.05) 100%);
    pointer-events: none;
    z-index: 0;
}
.slide-container .slide-illustration-bleed > * { z-index: 1; }
.slide-container .slide-illustration {
    mix-blend-mode: multiply;
    filter: contrast(0.97) saturate(0.94);
}
.slide-container .slide-illustration-bg {
    mix-blend-mode: multiply;
    opacity: 0.9;
    filter: contrast(0.96);
}

/* 코너 마크 — 치수 십자 + 시그니처 */
.slide-container { position: relative; }
.slide-container::before {
    content: '';
    position: absolute;
    top: 30px; left: 36px;
    width: 24px; height: 24px;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 32 32' xmlns='http://www.w3.org/2000/svg' fill='none' stroke='%232e3947' stroke-width='1.5'%3E%3Cline x1='16' y1='2' x2='16' y2='30'/%3E%3Cline x1='2' y1='16' x2='30' y2='16'/%3E%3Cpath d='M13 5 L16 2 L19 5'/%3E%3Cpath d='M27 13 L30 16 L27 19'/%3E%3Ccircle cx='16' cy='16' r='3' fill='%23ce6440' stroke='none'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-size: contain;
    opacity: 0.55;
    z-index: 10;
}
.slide-container::after {
    content: 'indiebiz.os — ARCH';
    position: absolute;
    bottom: 26px; right: 34px;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    font-size: 10px;
    color: hsl(var(--muted-foreground));
    letter-spacing: 0.18em;
    opacity: 0.55;
    z-index: 10;
}
""",
        # 코너 도트 패치 — PDF의 우상단·좌하단 도트 그리드 장식(정체성 표식).
        "extra_html": (
            "<div style=\"position:absolute; top:24px; right:24px; width:190px; height:110px; "
            "background-image:radial-gradient(circle, rgba(46,57,71,0.22) 1.2px, transparent 1.2px); "
            "background-size:13px 13px; pointer-events:none; z-index:9\"></div>"
            "<div style=\"position:absolute; bottom:24px; left:24px; width:150px; height:90px; "
            "background-image:radial-gradient(circle, rgba(46,57,71,0.18) 1.2px, transparent 1.2px); "
            "background-size:13px 13px; pointer-events:none; z-index:9\"></div>"
        ),
    },

    # ink_orange — 먹과 주황: 아이보리 포스터 + 먹 굵은 잉크 + 주황 흐름 강조
    # (2026-08-07 신설 — Reinventing_the_Internet_with_Personal_AI.pdf 13페이지 실물 연구에서 증류.
    #  정체성 장치: 극굵은 먹 헤드라인 / 주황 결론 배너(blockquote, 흰 명조) / 얇은 괘선 콜아웃 카드 /
    #  먹 굵은 괘선 표(헤더 밴드 없음) / 옵트인 .ink-card(먹 카드+흰 글자). 배경은 깨끗한 종이 — 모눈 없음.)
    "ink_orange": {
        "theme_override": "ink_orange",
        "extra_head": '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css"><link href="https://fonts.googleapis.com/css2?family=Noto+Serif+KR:wght@500;700;900&family=Noto+Sans+KR:wght@400;500;700;900&display=swap" rel="stylesheet">',
        "extra_css": """
/* === ink_orange — 먹과 주황 (인포그래픽 포스터: 먹 구조 vs 주황 흐름) === */
body {
    font-family: 'Pretendard Variable', 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif !important;
    /* 깨끗한 아이보리 종이 — 미세한 그레인만, 격자 없음 (포스터 여백이 정체성) */
    background-image:
        radial-gradient(ellipse at 50% 0%, rgba(42, 45, 50, 0.03), transparent 60%),
        url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3'/%3E%3CfeColorMatrix values='0 0 0 0 0.16 0 0 0 0 0.17 0 0 0 0 0.19 0 0 0 0.05 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E") !important;
}

/* 제목 — 극굵은 먹 헤드라인 (이 톤의 서체 성격: 무겁고 단호하게) */
.slide-container h1,
.slide-container h2,
.slide-container h3 {
    font-family: 'Pretendard Variable', 'Noto Sans KR', sans-serif !important;
    font-weight: 900 !important;
    letter-spacing: -0.025em !important;
    color: hsl(var(--foreground));
}

/* 본문 — 진하고 큼직하게 (포스터 가독) */
.slide-container p, .slide-container li, .slide-container td {
    line-height: 1.72 !important;
    font-weight: 500;
}

/* 라벨 (eyebrow) — 주황 굵은 산세리프 (이 톤엔 모노 없음) */
.slide-container [class*="text-xs"][class*="uppercase"],
.slide-container [class*="text-sm"][class*="uppercase"] {
    font-family: 'Pretendard Variable', 'Noto Sans KR', sans-serif !important;
    font-weight: 800 !important;
    letter-spacing: 0.14em !important;
    color: hsl(var(--accent)) !important;
}

/* 표 — 먹 굵은 괘선 (헤더 밴드 없음, PDF p.9 표 그대로) */
.slide-container table thead { background: transparent !important; }
.slide-container table thead th {
    color: hsl(var(--foreground)) !important;
    font-weight: 800 !important;
    border-bottom: 3px solid hsl(var(--foreground)) !important;
}
.slide-container table tbody tr { border-bottom: 1.5px solid rgba(42, 45, 50, 0.55) !important; }

/* 인용 — 주황 결론 배너 (풀폭 주황 + 흰 '명조' — PDF의 선언 장치) */
.slide-container blockquote {
    background: hsl(var(--accent)) !important;
    border: none !important;
    border-left: none !important;
    font-family: 'Noto Serif KR', serif !important;
    font-weight: 700;
    font-style: normal !important;
    color: #faf7f0 !important;
}
.slide-container blockquote p, .slide-container blockquote strong,
.slide-container blockquote em {
    color: #faf7f0 !important;
    font-family: 'Noto Serif KR', serif !important;
}

/* 팩트박스 — 얇은 괘선 콜아웃 (밝은 카드 + 먹 실선, PDF '작동 원리' 박스) */
.slide-container [class*="rounded-xl"] {
    background: rgba(250, 247, 240, 0.8) !important;
    border: 1.5px solid rgba(42, 45, 50, 0.75) !important;
    border-radius: 0.125rem !important;
}
/* 옵트인 먹 카드 — custom_html 이 쓰는 다크 정보 카드 (.ink-card: 먹 배경 + 흰 글자) */
.slide-container .ink-card {
    background: hsl(var(--foreground)) !important;
    border: none !important;
    border-radius: 0.125rem !important;
}
.slide-container .ink-card, .slide-container .ink-card * { color: #f2efe6 !important; }

/* 일러스트 통합 — 픽토그램이 종이에 잉크처럼 (multiply) */
.slide-container .slide-illustration-bleed { position: relative; }
.slide-container .slide-illustration-bleed::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at center, rgba(242, 239, 230, 0) 40%, rgba(42, 45, 50, 0.04) 100%);
    pointer-events: none;
    z-index: 0;
}
.slide-container .slide-illustration-bleed > * { z-index: 1; }
.slide-container .slide-illustration {
    mix-blend-mode: multiply;
    filter: contrast(0.98) saturate(0.96);
}
.slide-container .slide-illustration-bg {
    mix-blend-mode: multiply;
    opacity: 0.9;
    filter: contrast(0.97);
}

/* 코너 마크 — 주황 방사 호(브로드캐스트) + 시그니처 */
.slide-container { position: relative; }
.slide-container::before {
    content: '';
    position: absolute;
    top: 28px; left: 34px;
    width: 26px; height: 26px;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 32 32' xmlns='http://www.w3.org/2000/svg' fill='none' stroke='%23ee5f1c' stroke-width='2.2'%3E%3Cpath d='M6 26 A20 20 0 0 1 26 6'/%3E%3Cpath d='M6 18 A12 12 0 0 1 18 6'/%3E%3Cpath d='M6 10 A4 4 0 0 1 10 6'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-size: contain;
    opacity: 0.8;
    z-index: 10;
}
.slide-container::after {
    content: 'indiebiz.os';
    position: absolute;
    bottom: 26px; right: 34px;
    font-family: 'Pretendard Variable', sans-serif;
    font-weight: 700;
    font-size: 10px;
    color: hsl(var(--foreground));
    letter-spacing: 0.2em;
    opacity: 0.45;
    z-index: 10;
}
""",
        "extra_html": "",
    },
}
