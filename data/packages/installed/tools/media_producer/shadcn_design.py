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

    # academic_paper — 학술 논문 / Beamer 스타일 (흰 종이 + 진남색 + 진홍색 강조)
    "academic_paper": {
        "background": "40 20% 99%",       # #fbfaf7 (살짝 미색)
        "foreground": "222 30% 12%",      # #161c2a (잉크 블루블랙)
        "primary": "222 30% 12%",
        "primary-foreground": "40 20% 99%",
        "secondary": "40 15% 95%",
        "secondary-foreground": "222 30% 12%",
        "muted": "40 12% 93%",
        "muted-foreground": "222 8% 38%",
        "accent": "0 60% 36%",            # #8b1a1a (진홍색 — 학술 강조)
        "border": "222 12% 80%",
        "ring": "0 60% 36%",
        "radius": "0.125rem"
    },

    # tech_minimal — Linear/Vercel 스타일 (다크 남색 + 시안 강조)
    "tech_minimal": {
        "background": "230 20% 6%",       # #0d0f17 (다크)
        "foreground": "220 15% 92%",      # #e6e8ee (오프화이트)
        "primary": "220 15% 92%",
        "primary-foreground": "230 20% 6%",
        "secondary": "230 15% 12%",
        "secondary-foreground": "220 15% 92%",
        "muted": "230 12% 14%",
        "muted-foreground": "220 8% 55%",
        "accent": "190 95% 55%",          # #1ce0ff (시안 네온)
        "border": "230 12% 18%",
        "ring": "190 95% 55%",
        "radius": "0.5rem"
    },

    # magazine_modern — New Yorker/Wired 편집 디자인 (흰+검+선명한 적)
    "magazine_modern": {
        "background": "0 0% 100%",        # 순백
        "foreground": "0 0% 6%",          # 거의 검정
        "primary": "0 0% 6%",
        "primary-foreground": "0 0% 100%",
        "secondary": "30 10% 96%",        # 살짝 따뜻한 회색
        "secondary-foreground": "0 0% 6%",
        "muted": "30 8% 92%",
        "muted-foreground": "0 0% 30%",
        "accent": "356 85% 50%",          # #e6182b (선명한 잡지 적색)
        "border": "0 0% 85%",
        "ring": "356 85% 50%",
        "radius": "0rem"                  # 매거진 스타일 — 모서리 직각
    },

    # sf_blueprint — NotebookLM 양식 SF/블루프린트 (다크 네이비 + 시안 글로우 + HUD)
    # 책 강의·인포그래픽·메타포 시각화에 최적, 매 슬라이드가 다이어그램이 되는 패러다임
    "sf_blueprint": {
        "background": "215 60% 5%",       # #050d1a (심해 네이비)
        "foreground": "190 95% 92%",      # #d6f6ff (글로우 시안 화이트)
        "primary": "190 95% 70%",         # #6ee0ff (밝은 시안)
        "primary-foreground": "215 60% 5%",
        "secondary": "215 50% 12%",       # #0d1a2e (어두운 네이비 카드)
        "secondary-foreground": "190 95% 92%",
        "muted": "215 35% 18%",
        "muted-foreground": "200 30% 70%",
        "accent": "188 100% 55%",         # #1ad3ff (네온 시안 강조)
        "border": "190 70% 35%",          # 시안 라인
        "ring": "188 100% 55%",
        "radius": "0.125rem"              # SF HUD 양식 — 모서리 거의 직각
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

    # academic_paper — 학술 논문 / Beamer 양식 (흰 종이 + 진남색 + 진홍색, 격식)
    "academic_paper": {
        "theme_override": "academic_paper",
        "extra_head": '<link href="https://fonts.googleapis.com/css2?family=Crimson+Text:ital,wght@0,400;0,600;0,700;1,400&family=IBM+Plex+Sans+KR:wght@400;500;600;700&display=swap" rel="stylesheet">',
        "extra_css": """
/* === academic_paper === */
body {
    font-family: 'Crimson Text', 'IBM Plex Sans KR', 'Noto Serif KR', serif !important;
}
.slide-container h1,
.slide-container h2,
.slide-container h3 {
    font-family: 'Crimson Text', 'IBM Plex Sans KR', serif !important;
    font-weight: 700 !important;
    letter-spacing: -0.01em;
}
.slide-container p, .slide-container li, .slide-container td {
    line-height: 1.75 !important;
    font-size: 1.08em !important;
}

/* 라벨 — 작은 caps, 진홍색 */
.slide-container [class*="text-xs"][class*="uppercase"],
.slide-container [class*="text-sm"][class*="uppercase"] {
    font-family: 'IBM Plex Sans KR', sans-serif !important;
    font-weight: 600 !important;
    letter-spacing: 0.18em !important;
    color: hsl(var(--accent)) !important;
}

/* 인용 — 학술적 절제된 좌측 라인 */
.slide-container blockquote {
    border-color: hsl(var(--accent)) !important;
    background: transparent !important;
    font-style: italic;
    font-family: 'Crimson Text', serif !important;
}

/* 표 — 단순한 가로선 (논문 표 양식) */
.slide-container table thead { background: transparent !important; }
.slide-container table thead th {
    color: hsl(var(--foreground)) !important;
    font-family: 'IBM Plex Sans KR', sans-serif !important;
    border-bottom: 2px solid hsl(var(--foreground)) !important;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    font-size: 0.9em !important;
}
.slide-container table tbody tr {
    border-bottom: 1px solid hsl(var(--border)) !important;
}

/* 팩트박스 — 학술 노트 박스 */
.slide-container [class*="rounded-xl"] {
    background: hsl(var(--secondary)) !important;
    border-color: hsl(var(--foreground)) !important;
    border-width: 1px !important;
    border-radius: 0 !important;
}

/* 시그니처 + 페이지 번호 (논문 푸터 양식) */
.slide-container { position: relative; }
.slide-container::after {
    content: '— indieBizOS Lectures —';
    position: absolute;
    bottom: 18px; left: 50%;
    transform: translateX(-50%);
    font-family: 'Crimson Text', serif;
    font-style: italic;
    font-size: 11px;
    color: hsl(var(--muted-foreground));
    opacity: 0.7;
    z-index: 10;
}
""",
        "extra_html": "",
    },

    # tech_minimal — 프리미엄 다크 (Linear/Vercel/Stripe 양식): Pretendard + 레이어드 깊이 + 글래스
    "tech_minimal": {
        "theme_override": "tech_minimal",
        "extra_head": '<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable.min.css" /><link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">',
        "extra_css": """
/* === tech_minimal (premium dark) === */
body {
    font-family: 'Pretendard Variable','Pretendard','Inter','Apple SD Gothic Neo',sans-serif !important;
    background-color: #070A12 !important;
    /* 레이어드 깊이: 시안 글로우(상우) + 바이올렛 글로우(하좌) + 수직 그라데이션 */
    background-image:
        radial-gradient(1100px 720px at 82% -14%, rgba(56,189,248,0.22), transparent 56%),
        radial-gradient(940px 660px at 4% 118%, rgba(124,99,255,0.20), transparent 60%),
        linear-gradient(180deg, #0B1020 0%, #070A12 62%, #05070D 100%) !important;
}
/* 미세 그레인 + 비네트로 깊이 */
body::after {
    content:''; position:fixed; inset:0; pointer-events:none; z-index:0;
    background-image:
        radial-gradient(ellipse at center, transparent 50%, rgba(0,0,0,0.55) 100%),
        url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='tn'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='3'/%3E%3CfeColorMatrix values='0 0 0 0 1 0 0 0 0 1 0 0 0 0 1 0 0 0 0.04 0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23tn)'/%3E%3C/svg%3E");
}
.slide-container { position:relative; z-index:1; }

/* 제목 — 크고 단단하게 */
.slide-container h1 {
    font-family:'Pretendard Variable','Inter',sans-serif !important;
    font-weight:800 !important; letter-spacing:-0.035em !important; line-height:1.08 !important;
}
.slide-container h2, .slide-container h3 { font-weight:700 !important; letter-spacing:-0.02em !important; }
.slide-container p, .slide-container li, .slide-container td { line-height:1.7 !important; font-weight:400; }

/* eyebrow — 모노 시안 */
.slide-container [class*="uppercase"][class*="tracking"],
.slide-container [class*="text-xs"][class*="uppercase"],
.slide-container [class*="text-sm"][class*="uppercase"] {
    font-family:'JetBrains Mono',monospace !important; color:hsl(var(--accent)) !important; font-weight:500 !important;
}

/* 카드/박스 — 글래스모피즘 (납작한 면 금지) */
.slide-container [class*="rounded-2xl"],
.slide-container [class*="rounded-xl"] {
    background: linear-gradient(135deg, rgba(255,255,255,0.07), rgba(255,255,255,0.015)) !important;
    border:1px solid rgba(255,255,255,0.08) !important;
    box-shadow: inset 0 1px 0 rgba(255,255,255,0.06), 0 24px 48px -28px rgba(0,0,0,0.85) !important;
    -webkit-backdrop-filter: blur(8px); backdrop-filter: blur(8px);
}
/* 강조 테두리 카드 — 시안 글로우 */
.slide-container [class*="border-2"] {
    border-color: hsl(var(--accent)) !important;
    box-shadow: 0 0 0 1px hsl(var(--accent) / 0.35), 0 0 48px -10px hsl(var(--accent) / 0.4) !important;
}

/* 인용 */
.slide-container blockquote {
    border-color:hsl(var(--accent)) !important; background:rgba(56,189,248,0.06) !important;
    color:hsl(var(--foreground)) !important;
}
/* 표 — 미니멀 모노 헤더 */
.slide-container table thead { background:rgba(56,189,248,0.08) !important; }
.slide-container table thead th {
    font-family:'JetBrains Mono',monospace !important; color:hsl(var(--accent)) !important;
    text-transform:uppercase; font-size:0.8em !important;
}

/* 우하단 시그니처 */
.slide-container::after {
    content:'indiebiz \\00B7 os'; position:absolute; bottom:26px; right:34px;
    font-family:'JetBrains Mono',monospace; font-size:11px; letter-spacing:0.12em;
    color:hsl(var(--muted-foreground)); opacity:0.7; z-index:10;
}
""",
        "extra_html": "",
    },

    # magazine_modern — New Yorker/Wired 편집 디자인 (흰+검+적색 임팩트)
    "magazine_modern": {
        "theme_override": "magazine_modern",
        "extra_head": '<link href="https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Playfair+Display:ital,wght@0,400;0,600;0,700;0,800;1,400;1,600&family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet">',
        "extra_css": """
/* === magazine_modern === */
body {
    font-family: 'Playfair Display', 'Noto Serif KR', serif !important;
}

/* 큰 제목 — Bebas Neue (잡지 헤드라인) */
.slide-container h1, .slide-container h2 {
    font-family: 'Bebas Neue', 'Black Han Sans', sans-serif !important;
    font-weight: 400 !important;
    letter-spacing: 0.01em;
    line-height: 1.05 !important;
}
.slide-container h3 {
    font-family: 'Playfair Display', serif !important;
    font-weight: 700 !important;
}
.slide-container p, .slide-container li, .slide-container td {
    font-family: 'Playfair Display', 'Noto Serif KR', serif !important;
    line-height: 1.7 !important;
}

/* 라벨 — 적색 두꺼운 가로선과 함께 */
.slide-container [class*="text-xs"][class*="uppercase"],
.slide-container [class*="text-sm"][class*="uppercase"] {
    font-family: 'Inter', sans-serif !important;
    font-weight: 800 !important;
    letter-spacing: 0.2em !important;
    color: hsl(var(--accent)) !important;
    position: relative;
    padding-left: 36px;
}
.slide-container [class*="text-xs"][class*="uppercase"]::before,
.slide-container [class*="text-sm"][class*="uppercase"]::before {
    content: '';
    position: absolute;
    left: 0; top: 50%;
    width: 24px; height: 3px;
    background: hsl(var(--accent));
}

/* 표 — 굵은 검정 헤더라인 */
.slide-container table thead {
    background: hsl(var(--foreground)) !important;
}
.slide-container table thead th {
    color: hsl(var(--primary-foreground)) !important;
    font-family: 'Inter', sans-serif !important;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    font-size: 0.85em !important;
    padding: 12px 16px !important;
}

/* 인용 — 큰 적색 좌측 막대 */
.slide-container blockquote {
    border-color: hsl(var(--accent)) !important;
    border-left-width: 6px !important;
    background: transparent !important;
    font-family: 'Playfair Display', serif !important;
    font-style: italic !important;
    font-size: 1.2em !important;
}

/* 팩트박스 — 매거진 사이드바 */
.slide-container [class*="rounded-xl"] {
    background: hsl(var(--secondary)) !important;
    border: none !important;
    border-left: 8px solid hsl(var(--accent)) !important;
    border-radius: 0 !important;
}

/* 좌상단 적색 사각형 + 우하단 검정 시그니처 */
.slide-container { position: relative; }
.slide-container::before {
    content: '';
    position: absolute;
    top: 28px; left: 32px;
    width: 36px; height: 8px;
    background: hsl(var(--accent));
    z-index: 10;
}
.slide-container::after {
    content: 'INDIEBIZ.OS / LECTURES';
    position: absolute;
    bottom: 24px; right: 32px;
    font-family: 'Inter', sans-serif;
    font-weight: 800;
    font-size: 10px;
    color: hsl(var(--foreground));
    letter-spacing: 0.2em;
    z-index: 10;
}
""",
        "extra_html": "",
    },

    # sf_blueprint — NotebookLM 양식: 다크 네이비 + 시안 글로우 + HUD 격자 + 코너 마크
    # 매 슬라이드가 인포그래픽이 되는 패러다임 (모든 일러스트가 풀-블리드 다이어그램)
    "sf_blueprint": {
        "theme_override": "sf_blueprint",
        "extra_head": '<link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;700;900&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">',
        "extra_css": """
/* === sf_blueprint — NotebookLM SF HUD 양식 === */
body {
    font-family: 'Rajdhani', 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif !important;
    /* 심해 네이비 + HUD 격자 + 라디얼 글로우 */
    background-image:
        radial-gradient(ellipse at 30% 20%, rgba(26, 211, 255, 0.10), transparent 55%),
        radial-gradient(ellipse at 70% 80%, rgba(110, 224, 255, 0.07), transparent 55%),
        repeating-linear-gradient(0deg, transparent, transparent 39px, rgba(110, 224, 255, 0.05) 40px),
        repeating-linear-gradient(90deg, transparent, transparent 39px, rgba(110, 224, 255, 0.05) 40px) !important;
}

/* 제목 — 와이드한 SF 헤드라인 */
.slide-container h1,
.slide-container h2,
.slide-container h3 {
    font-family: 'Noto Sans KR', 'Rajdhani', sans-serif !important;
    font-weight: 900 !important;
    letter-spacing: -0.01em !important;
    text-shadow: 0 0 24px rgba(26, 211, 255, 0.35), 0 0 4px rgba(110, 224, 255, 0.6);
}
.slide-container h1 strong,
.slide-container h2 strong,
.slide-container h3 strong,
.slide-container .accent-glow {
    color: hsl(var(--accent)) !important;
    text-shadow: 0 0 24px rgba(26, 211, 255, 0.7) !important;
}

/* 본문 */
.slide-container p, .slide-container li, .slide-container td {
    font-family: 'Noto Sans KR', 'Rajdhani', sans-serif !important;
    line-height: 1.7 !important;
    font-weight: 500;
}

/* 라벨 — JetBrains Mono + 시안 글로우 */
.slide-container [class*="text-xs"][class*="uppercase"],
.slide-container [class*="text-sm"][class*="uppercase"] {
    font-family: 'JetBrains Mono', monospace !important;
    font-weight: 500 !important;
    letter-spacing: 0.18em !important;
    color: hsl(var(--accent)) !important;
}

/* 표 — HUD 양식 */
.slide-container table thead {
    background: rgba(26, 211, 255, 0.08) !important;
    border-bottom: 1px solid hsl(var(--accent)) !important;
}
.slide-container table thead th {
    color: hsl(var(--accent)) !important;
    font-family: 'JetBrains Mono', monospace !important;
    text-transform: uppercase;
    letter-spacing: 0.12em;
    font-size: 0.85em !important;
    text-shadow: 0 0 12px rgba(26, 211, 255, 0.5);
}
.slide-container table tbody tr {
    border-bottom: 1px solid rgba(110, 224, 255, 0.15) !important;
}

/* 인용 — 글로우 좌측 막대 */
.slide-container blockquote {
    border-color: hsl(var(--accent)) !important;
    background: rgba(26, 211, 255, 0.05) !important;
    box-shadow: -2px 0 16px rgba(26, 211, 255, 0.25);
}

/* 팩트박스 + HUD 패널 (사각형 코너 + 글로우 경계) */
.slide-container [class*="rounded-xl"],
.slide-container .hud-panel {
    background: rgba(13, 26, 46, 0.7) !important;
    border: 1px solid hsl(var(--border)) !important;
    border-radius: 0.125rem !important;
    box-shadow: 0 0 24px rgba(26, 211, 255, 0.15), inset 0 0 0 1px rgba(110, 224, 255, 0.1);
    position: relative;
}
/* HUD 코너 브래킷 — .hud-panel 명시 클래스에만 적용 */
.slide-container .hud-panel::before,
.slide-container .hud-panel::after {
    content: '';
    position: absolute;
    width: 14px; height: 14px;
    border: 2px solid hsl(var(--accent));
    pointer-events: none;
}
.slide-container .hud-panel::before {
    top: -1px; left: -1px;
    border-right: none; border-bottom: none;
}
.slide-container .hud-panel::after {
    bottom: -1px; right: -1px;
    border-left: none; border-top: none;
}

/* 일러스트 통합 — 다크 배경에 자연스럽게 녹아들도록 (screen 블렌드) */
.slide-container .slide-illustration-bleed { position: relative; }
.slide-container .slide-illustration-bleed::before {
    content: '';
    position: absolute;
    inset: 0;
    background: radial-gradient(ellipse at center, transparent 30%, rgba(5, 13, 26, 0.25) 100%);
    pointer-events: none;
    z-index: 0;
}
.slide-container .slide-illustration-bleed > * { z-index: 1; }
.slide-container .slide-illustration {
    mix-blend-mode: screen;
    filter: contrast(1.05) saturate(1.1);
}
.slide-container .slide-illustration-bg {
    mix-blend-mode: screen;
    opacity: 0.95;
    filter: contrast(1.05);
}

/* 코너 마크 + SF 시그니처 */
.slide-container { position: relative; }
.slide-container::before {
    content: '';
    position: absolute;
    top: 24px; left: 28px;
    width: 24px; height: 24px;
    background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 32 32' xmlns='http://www.w3.org/2000/svg' fill='none' stroke='%231ad3ff' stroke-width='1.5'%3E%3Crect x='2' y='2' width='28' height='28'/%3E%3Cline x1='2' y1='16' x2='10' y2='16'/%3E%3Cline x1='22' y1='16' x2='30' y2='16'/%3E%3Cline x1='16' y1='2' x2='16' y2='10'/%3E%3Cline x1='16' y1='22' x2='16' y2='30'/%3E%3Ccircle cx='16' cy='16' r='3' fill='%231ad3ff' stroke='none'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-size: contain;
    filter: drop-shadow(0 0 6px rgba(26, 211, 255, 0.6));
    opacity: 0.85;
    z-index: 10;
}
.slide-container::after {
    content: 'indiebiz.os // lectures';
    position: absolute;
    bottom: 22px; right: 30px;
    font-family: 'JetBrains Mono', monospace;
    font-weight: 500;
    font-size: 10px;
    color: hsl(var(--accent));
    letter-spacing: 0.15em;
    opacity: 0.7;
    text-shadow: 0 0 8px rgba(26, 211, 255, 0.5);
    z-index: 10;
}
""",
        "extra_html": "",
    },
}
