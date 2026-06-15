"""
shadcn_slides.py
shadcn/ui 컴포넌트와 web-builder 테마를 활용한 슬라이드 생성
"""

import os
import json
import uuid
import base64
import urllib.request
from jinja2 import Template

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

# ============================================
# 슬라이드 템플릿 (shadcn 스타일)
# ============================================

SLIDE_BASE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <script src="https://cdn.tailwindcss.com"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=Do+Hyeon&family=Gothic+A1:wght@400;700;900&family=Noto+Sans+KR:wght@300;400;500;700;900&family=Sunflower:wght@300;500;700&family=Jua&family=Inter:wght@300;400;500;600;700;800;900&family=Montserrat:wght@400;600;700;800;900&family=Playfair+Display:wght@400;600;700;900&family=Poppins:wght@300;400;500;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css"/>
    <script src="https://unpkg.com/lucide@latest"></script>
    <script src="https://unpkg.com/@lottiefiles/lottie-player@2/dist/lottie-player.js"></script>
    {{design_system_head|safe}}
    <style>
        /* style_overrides — spec.style_overrides 적용 (있을 때만 비어있지 않음) */
        {{style_overrides_css|safe}}
    </style>
    <style>

        :root {
            --background: {{theme.background}};
            --foreground: {{theme.foreground}};
            --primary: {{theme.primary}};
            --primary-foreground: {{theme['primary-foreground']}};
            --secondary: {{theme.secondary}};
            --secondary-foreground: {{theme['secondary-foreground']}};
            --muted: {{theme.muted}};
            --muted-foreground: {{theme['muted-foreground']}};
            --accent: {{theme.accent}};
            --border: {{theme.border}};
            --ring: {{theme.ring}};
            --radius: {{theme.radius}};
        }

        body {
            margin: 0;
            padding: 0;
            width: {{width}}px;
            height: {{height}}px;
            overflow: hidden;
            font-family: 'Noto Sans KR', 'Inter', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
            background: hsl(var(--background));
            color: hsl(var(--foreground));
        }

        .slide-container {
            width: {{width}}px;
            height: {{height}}px;
            overflow: hidden;
        }

        /* shadcn Button 스타일 */
        .btn {
            display: inline-flex;
            align-items: center;
            justify-content: center;
            gap: 0.5rem;
            white-space: nowrap;
            border-radius: var(--radius);
            font-size: 0.875rem;
            font-weight: 500;
            transition: all 0.2s;
            padding: 0.5rem 1rem;
        }
        .btn-default {
            background: hsl(var(--primary));
            color: hsl(var(--primary-foreground));
        }
        .btn-secondary {
            background: hsl(var(--secondary));
            color: hsl(var(--secondary-foreground));
        }
        .btn-outline {
            border: 1px solid hsl(var(--border));
            background: transparent;
        }
        .btn-lg {
            padding: 0.75rem 2rem;
            font-size: 1.125rem;
        }

        /* shadcn Badge 스타일 */
        .badge {
            display: inline-flex;
            align-items: center;
            border-radius: 9999px;
            padding: 0.25rem 0.75rem;
            font-size: 0.75rem;
            font-weight: 600;
        }
        .badge-default {
            background: hsl(var(--primary));
            color: hsl(var(--primary-foreground));
        }
        .badge-secondary {
            background: hsl(var(--secondary));
            color: hsl(var(--secondary-foreground));
        }

        /* shadcn Card 스타일 */
        .card {
            border-radius: var(--radius);
            border: 1px solid hsl(var(--border));
            background: hsl(var(--background));
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        .card-header {
            padding: 1.5rem;
        }
        .card-title {
            font-size: 1.5rem;
            font-weight: 600;
            line-height: 1;
        }
        .card-description {
            font-size: 0.875rem;
            color: hsl(var(--muted-foreground));
            margin-top: 0.5rem;
        }
        .card-content {
            padding: 0 1.5rem 1.5rem;
        }

        /* === Design System CSS (적용된 디자인 시스템의 비주얼 정체성) === */
        {{design_system_css|safe}}

        /* PNG 캡처는 정적이므로 animate.css 지연/지속시간을 0으로 만들어 최종 상태로 즉시 도달 */
        .animate__animated {
            animation-delay: 0s !important;
            animation-duration: 0s !important;
            animation-fill-mode: both !important;
        }
    </style>
    <script>
        tailwind.config = {
            theme: {
                extend: {
                    colors: {
                        background: 'hsl(var(--background))',
                        foreground: 'hsl(var(--foreground))',
                        primary: {
                            DEFAULT: 'hsl(var(--primary))',
                            foreground: 'hsl(var(--primary-foreground))'
                        },
                        secondary: {
                            DEFAULT: 'hsl(var(--secondary))',
                            foreground: 'hsl(var(--secondary-foreground))'
                        },
                        muted: {
                            DEFAULT: 'hsl(var(--muted))',
                            foreground: 'hsl(var(--muted-foreground))'
                        },
                        accent: {
                            DEFAULT: 'hsl(var(--accent))',
                            foreground: 'hsl(var(--accent-foreground))'
                        },
                        border: 'hsl(var(--border))',
                    },
                    borderRadius: {
                        lg: 'var(--radius)',
                        md: 'calc(var(--radius) - 2px)',
                        sm: 'calc(var(--radius) - 4px)',
                    }
                }
            }
        }
    </script>
</head>
<body>
    <div class="slide-container">
        {{content|safe}}
        {{design_system_html|safe}}
    </div>
    <script>
        lucide.createIcons();
    </script>
</body>
</html>
"""

# ============================================
# 슬라이드 타입별 레이아웃
# ============================================

SLIDE_LAYOUTS = {
    # 히어로 슬라이드 (중앙 정렬)
    "hero": """
<div class="w-full h-full flex flex-col items-center justify-center p-16 bg-gradient-to-br from-background to-muted/30">
    {% if badge %}<span class="badge badge-secondary mb-6 animate__animated animate__fadeInDown">{{badge}}</span>{% endif %}
    <h1 class="text-6xl font-black text-center tracking-tight mb-6 animate__animated animate__fadeInUp" style="color: hsl(var(--foreground))">
        {{title}}
    </h1>
    {% if subtitle %}
    <p class="text-2xl text-center max-w-3xl animate__animated animate__fadeInUp animate__delay-1s" style="color: hsl(var(--muted-foreground))">
        {{subtitle}}
    </p>
    {% endif %}
    {% if cta_text %}
    <div class="mt-10 animate__animated animate__fadeInUp animate__delay-2s">
        <span class="btn btn-default btn-lg">{{cta_text}}</span>
    </div>
    {% endif %}
</div>
""",

    # 히어로 + 이미지 (좌우 분할 — 일러스트가 배경에 녹아드는 통합형)
    "hero_image": """
<div class="w-full h-full flex slide-illustration-bleed">
    <div class="w-1/2 h-full flex flex-col justify-center p-16">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-wider mb-3" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        {% if badge %}<span class="badge badge-secondary mb-4">{{badge}}</span>{% endif %}
        <h1 class="text-5xl font-bold tracking-tight mb-6 leading-tight" style="color: hsl(var(--foreground))">
            {{title}}
        </h1>
        {% if subtitle %}
        <p class="text-xl mb-8 leading-relaxed" style="color: hsl(var(--muted-foreground))">
            {{subtitle}}
        </p>
        {% endif %}
        {% if cta_text %}
        <div>
            <span class="btn btn-default btn-lg">{{cta_text}}</span>
        </div>
        {% endif %}
    </div>
    <div class="w-1/2 h-full flex items-center justify-center p-10">
        {% if image_data %}
        <img src="{{image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
        {% else %}
        <div class="w-80 h-80 flex items-center justify-center opacity-30">
            <i data-lucide="image" class="w-20 h-20" style="color: hsl(var(--muted-foreground))"></i>
        </div>
        {% endif %}
    </div>
</div>
""",

    # 기능 그리드 (3열)
    "features": """
<div class="w-full h-full p-16">
    {% if title %}
    <div class="text-center mb-12">
        <h2 class="text-4xl font-bold mb-4" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if subtitle %}<p class="text-xl" style="color: hsl(var(--muted-foreground))">{{subtitle}}</p>{% endif %}
    </div>
    {% endif %}
    <div class="grid grid-cols-3 gap-8">
        {% for feature in features %}
        <div class="card p-6">
            <div class="w-12 h-12 rounded-lg flex items-center justify-center mb-4" style="background: hsl(var(--primary) / 0.1)">
                {% if feature.icon %}
                <span class="text-2xl">{{feature.icon}}</span>
                {% else %}
                <i data-lucide="star" class="w-6 h-6" style="color: hsl(var(--primary))"></i>
                {% endif %}
            </div>
            <h3 class="text-xl font-semibold mb-2" style="color: hsl(var(--foreground))">{{feature.title}}</h3>
            <p class="text-sm" style="color: hsl(var(--muted-foreground))">{{feature.description}}</p>
        </div>
        {% endfor %}
    </div>
</div>
""",

    # 통계 (4열)
    "stats": """
<div class="w-full h-full flex flex-col justify-center p-16" style="background: hsl(var(--primary)); color: hsl(var(--primary-foreground))">
    {% if title %}
    <h2 class="text-4xl font-bold text-center mb-16">{{title}}</h2>
    {% endif %}
    <div class="grid grid-cols-4 gap-8">
        {% for stat in stats %}
        <div class="text-center">
            <p class="text-5xl font-bold mb-2">{{stat.value}}</p>
            <p class="text-lg opacity-80">{{stat.label}}</p>
        </div>
        {% endfor %}
    </div>
</div>
""",

    # 인용/후기
    "testimonial": """
<div class="w-full h-full flex items-center justify-center p-16" style="background: hsl(var(--muted) / 0.3)">
    <div class="max-w-4xl text-center">
        <i data-lucide="quote" class="w-16 h-16 mx-auto mb-8 opacity-20" style="color: hsl(var(--primary))"></i>
        <p class="text-3xl font-medium mb-8 leading-relaxed" style="color: hsl(var(--foreground))">
            "{{quote|default('인용문을 입력하세요')}}"
        </p>
        <div class="flex items-center justify-center gap-4">
            {% if avatar_data %}
            <img src="{{avatar_data}}" class="w-16 h-16 rounded-full">
            {% else %}
            <div class="w-16 h-16 rounded-full flex items-center justify-center text-xl font-bold" style="background: hsl(var(--primary)); color: hsl(var(--primary-foreground))">
                {{(author|default('익명'))[:2]|upper}}
            </div>
            {% endif %}
            <div class="text-left">
                <p class="font-semibold" style="color: hsl(var(--foreground))">{{author|default('익명')}}</p>
                <p class="text-sm" style="color: hsl(var(--muted-foreground))">{{role|default('')}}</p>
            </div>
        </div>
    </div>
</div>
""",

    # 가격표
    "pricing": """
<div class="w-full h-full p-12">
    {% if title %}
    <h2 class="text-4xl font-bold text-center mb-8" style="color: hsl(var(--foreground))">{{title}}</h2>
    {% endif %}
    <div class="grid grid-cols-3 gap-6 h-[calc(100%-80px)]">
        {% for plan in plans %}
        <div class="card flex flex-col {% if plan.highlighted %}border-2{% endif %}" {% if plan.highlighted %}style="border-color: hsl(var(--primary))"{% endif %}>
            {% if plan.highlighted %}
            <div class="text-center py-2 text-sm font-medium" style="background: hsl(var(--primary)); color: hsl(var(--primary-foreground))">추천</div>
            {% endif %}
            <div class="p-6 flex-1 flex flex-col">
                <h3 class="text-xl font-semibold" style="color: hsl(var(--foreground))">{{plan.name}}</h3>
                <p class="text-sm mt-1" style="color: hsl(var(--muted-foreground))">{{plan.description}}</p>
                <div class="my-6">
                    <span class="text-4xl font-bold" style="color: hsl(var(--foreground))">{{plan.price}}</span>
                    <span style="color: hsl(var(--muted-foreground))">{{plan.period|default('/월')}}</span>
                </div>
                <ul class="space-y-2 flex-1">
                    {% for feature in plan.features %}
                    <li class="flex items-center gap-2 text-sm">
                        <i data-lucide="check" class="w-4 h-4" style="color: hsl(var(--primary))"></i>
                        <span style="color: hsl(var(--foreground))">{{feature}}</span>
                    </li>
                    {% endfor %}
                </ul>
                <div class="mt-6">
                    <span class="btn {% if plan.highlighted %}btn-default{% else %}btn-outline{% endif %} w-full justify-center">
                        {{plan.cta_text|default('선택하기')}}
                    </span>
                </div>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
""",

    # CTA 배너
    "cta": """
<div class="w-full h-full flex flex-col items-center justify-center p-16" style="background: hsl(var(--primary)); color: hsl(var(--primary-foreground))">
    <h2 class="text-5xl font-bold text-center mb-6">{{title}}</h2>
    {% if subtitle %}
    <p class="text-xl text-center opacity-90 max-w-2xl mb-10">{{subtitle}}</p>
    {% endif %}
    <span class="btn btn-lg" style="background: hsl(var(--primary-foreground)); color: hsl(var(--primary))">
        {{cta_text|default('시작하기')}}
    </span>
</div>
""",

    # 콘텐츠 + 이미지 (좌우 분할 — 일러스트가 배경에 녹아드는 통합형)
    "content_image": """
<div class="w-full h-full flex slide-illustration-bleed {% if image_position == 'left' %}flex-row-reverse{% endif %}">
    <div class="w-1/2 h-full flex flex-col justify-center p-16">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-wider mb-3" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        <h2 class="text-4xl font-bold mb-6 leading-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        <p class="text-lg leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.85">{{content}}</p>
        {% if cta_text %}
        <div class="mt-8">
            <span class="btn btn-default">{{cta_text}}</span>
        </div>
        {% endif %}
    </div>
    <div class="w-1/2 h-full flex items-center justify-center p-10">
        {% if image_data %}
        <img src="{{image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
        {% else %}
        <div class="w-full h-full flex items-center justify-center opacity-20">
            <i data-lucide="image" class="w-24 h-24" style="color: hsl(var(--muted-foreground))"></i>
        </div>
        {% endif %}
    </div>
</div>
""",

    # 타임라인/단계
    "steps": """
<div class="w-full h-full p-16">
    {% if title %}
    <h2 class="text-4xl font-bold text-center mb-12" style="color: hsl(var(--foreground))">{{title}}</h2>
    {% endif %}
    <div class="flex justify-between items-start gap-4">
        {% for step in steps %}
        <div class="flex-1 text-center">
            <div class="w-16 h-16 rounded-full mx-auto mb-4 flex items-center justify-center text-2xl font-bold" style="background: hsl(var(--primary)); color: hsl(var(--primary-foreground))">
                {{loop.index}}
            </div>
            <h3 class="text-xl font-semibold mb-2" style="color: hsl(var(--foreground))">{{step.title}}</h3>
            <p class="text-sm" style="color: hsl(var(--muted-foreground))">{{step.description}}</p>
        </div>
        {% if not loop.last %}
        <div class="flex-shrink-0 mt-8">
            <i data-lucide="arrow-right" class="w-8 h-8" style="color: hsl(var(--border))"></i>
        </div>
        {% endif %}
        {% endfor %}
    </div>
</div>
""",

    # === 강의용 레이아웃 (lecture series) ===

    # 강의 본문 — 제목 + 본문 단락 + 선택적 불릿/인용 (가장 자주 쓰는 강의 슬라이드)
    "lecture_body": """
<div class="w-full h-full flex flex-col p-14">
    <div class="mb-6">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-wider mb-2" style="color: hsl(var(--primary))">{{eyebrow}}</p>{% endif %}
        <h2 class="text-4xl font-bold tracking-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if subtitle %}<p class="text-xl mt-2" style="color: hsl(var(--muted-foreground))">{{subtitle}}</p>{% endif %}
    </div>
    <div class="flex-1 flex flex-col gap-5 text-lg leading-relaxed" style="color: hsl(var(--foreground))">
        {% if body %}<p>{{body}}</p>{% endif %}
        {% if bullets %}
        <ul class="space-y-3 pl-2">
            {% for b in bullets %}
            <li class="flex gap-3">
                <span class="flex-shrink-0 mt-2 w-2 h-2 rounded-full" style="background: hsl(var(--primary))"></span>
                <span>{{b}}</span>
            </li>
            {% endfor %}
        </ul>
        {% endif %}
        {% if quote %}
        <blockquote class="border-l-4 pl-6 py-3 italic text-xl my-2" style="border-color: hsl(var(--primary)); background: hsl(var(--muted) / 0.3)">
            {{quote}}
        </blockquote>
        {% endif %}
    </div>
    {% if footer %}<p class="text-sm mt-6 pt-4 border-t" style="color: hsl(var(--muted-foreground)); border-color: hsl(var(--border))">{{footer}}</p>{% endif %}
</div>
""",

    # 메타포 스토리 — 큰 본문 스토리 + 한 줄 부연 (햄릿/깜깜한 계단 같은 핵심 메타포용)
    "metaphor_story": """
<div class="w-full h-full flex flex-col items-center justify-center p-20" style="background: linear-gradient(135deg, hsl(var(--background)), hsl(var(--muted) / 0.4))">
    {% if label %}
    <span class="badge badge-secondary mb-8 text-sm tracking-wider uppercase">{{label}}</span>
    {% endif %}
    <p class="text-3xl text-center leading-loose max-w-5xl font-medium" style="color: hsl(var(--foreground))">
        {{story}}
    </p>
    {% if takeaway %}
    <div class="mt-12 pt-8 border-t max-w-3xl" style="border-color: hsl(var(--border))">
        <p class="text-xl text-center font-semibold" style="color: hsl(var(--primary))">{{takeaway}}</p>
    </div>
    {% endif %}
</div>
""",

    # 비교 표 — 좌우 또는 다열 비교 (v0 vs v5, 마케팅 카드 vs 강의 슬라이드 같은 비교)
    "comparison_table": """
<div class="w-full h-full flex flex-col p-14">
    <div class="mb-8">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-wider mb-2" style="color: hsl(var(--primary))">{{eyebrow}}</p>{% endif %}
        <h2 class="text-4xl font-bold tracking-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if subtitle %}<p class="text-lg mt-2" style="color: hsl(var(--muted-foreground))">{{subtitle}}</p>{% endif %}
    </div>
    <div class="flex-1 overflow-hidden">
        <table class="w-full text-base" style="color: hsl(var(--foreground))">
            {% if headers %}
            <thead>
                <tr style="border-bottom: 2px solid hsl(var(--primary))">
                    {% for h in headers %}
                    <th class="text-left py-4 px-4 font-bold text-lg">{{h}}</th>
                    {% endfor %}
                </tr>
            </thead>
            {% endif %}
            <tbody>
                {% for row in rows %}
                <tr style="border-bottom: 1px solid hsl(var(--border))">
                    {% for cell in row %}
                    <td class="py-4 px-4 align-top leading-relaxed">{{cell|safe}}</td>
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% if footer %}<p class="text-sm mt-6" style="color: hsl(var(--muted-foreground))">{{footer}}</p>{% endif %}
</div>
""",

    # 팩트박스 — 책의 팩트박스/부연 정보 (역사, 정의, 수치 등 보조 자료)
    "factbox": """
<div class="w-full h-full flex items-center justify-center p-14">
    <div class="max-w-4xl w-full rounded-xl p-12 shadow-lg" style="background: hsl(var(--muted) / 0.4); border: 2px solid hsl(var(--border))">
        <div class="flex items-center gap-3 mb-6">
            <i data-lucide="info" class="w-6 h-6" style="color: hsl(var(--primary))"></i>
            <span class="text-sm font-bold uppercase tracking-wider" style="color: hsl(var(--primary))">{{label|default('팩트박스')}}</span>
        </div>
        <h3 class="text-3xl font-bold mb-6 tracking-tight" style="color: hsl(var(--foreground))">{{title}}</h3>
        <div class="text-lg leading-relaxed space-y-4" style="color: hsl(var(--foreground))">
            {% if body %}<p>{{body}}</p>{% endif %}
            {% if items %}
            <ul class="space-y-2 pl-2">
                {% for it in items %}
                <li class="flex gap-3">
                    <span class="flex-shrink-0 mt-3 w-1.5 h-1.5 rounded-full" style="background: hsl(var(--primary))"></span>
                    <span>{{it}}</span>
                </li>
                {% endfor %}
            </ul>
            {% endif %}
        </div>
        {% if source %}<p class="text-xs mt-6 italic" style="color: hsl(var(--muted-foreground))">출처: {{source}}</p>{% endif %}
    </div>
</div>
""",

    # 인용 풀스크린 — 강력한 핵심 인용 한 줄 (testimonial과 다름: 카드형이 아닌 임팩트 풀스크린)
    "quote": """
<div class="w-full h-full flex flex-col items-center justify-center p-20" style="background: hsl(var(--background))">
    <i data-lucide="quote" class="w-20 h-20 mb-10" style="color: hsl(var(--primary)); opacity: 0.15"></i>
    <p class="text-4xl text-center font-medium leading-relaxed max-w-5xl" style="color: hsl(var(--foreground))">
        "{{quote}}"
    </p>
    {% if attribution %}
    <p class="text-xl mt-10" style="color: hsl(var(--muted-foreground))">— {{attribution}}</p>
    {% endif %}
    {% if context %}
    <p class="text-base mt-4 max-w-3xl text-center italic" style="color: hsl(var(--muted-foreground))">{{context}}</p>
    {% endif %}
</div>
""",

    # === NotebookLM 스타일 통합형 레이아웃 ===
    # 이미지와 텍스트가 한 화면 안에서 융합 — 일러스트는 슬라이드 배경과 자연스럽게 흐른다.
    # 키 포인트: 이미지 영역에 별도 배경/박스 없음, slide-illustration 클래스로 design_system이 후킹.

    # hero_illustration — 중앙 영웅 일러스트 + 상하 텍스트 (NotebookLM 표지/장 표지 스타일)
    # 사용처: 책 표지, 장 도입, 핵심 개념 단일 시각화
    "hero_illustration": """
<div class="w-full h-full flex flex-col items-center justify-center px-16 py-10 slide-illustration-bleed">
    {% if eyebrow %}<p class="text-xs font-semibold uppercase tracking-[0.3em] mb-3 opacity-80" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
    <div class="flex-1 flex items-center justify-center w-full max-w-5xl my-3 min-h-0">
        {% if image_data %}
        <img src="{{image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
        {% else %}
        <div class="w-96 h-96 flex items-center justify-center opacity-20">
            <i data-lucide="image" class="w-24 h-24" style="color: hsl(var(--muted-foreground))"></i>
        </div>
        {% endif %}
    </div>
    <h1 class="text-6xl font-black text-center tracking-tight mb-3 leading-[1.15]" style="color: hsl(var(--foreground))">
        {{title}}
    </h1>
    {% if subtitle %}
    <p class="text-xl text-center max-w-4xl leading-relaxed" style="color: hsl(var(--muted-foreground))">
        {{subtitle}}
    </p>
    {% endif %}
    {% if footer %}<p class="text-sm mt-6" style="color: hsl(var(--muted-foreground))">{{footer}}</p>{% endif %}
</div>
""",

    # illustration_anchor — 상단 큰 일러스트 + 하단 텍스트 (가장 활용도 높은 강의 슬라이드)
    # 사용처: 개념 설명, 다이어그램 + 캡션, 일러스트로 보여주고 글로 마무리
    "illustration_anchor": """
<div class="w-full h-full flex flex-col p-14 slide-illustration-bleed">
    <div class="flex-1 flex items-center justify-center min-h-0 mb-8">
        {% if image_data %}
        <img src="{{image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
        {% else %}
        <div class="w-full h-full flex items-center justify-center opacity-20">
            <i data-lucide="image" class="w-24 h-24" style="color: hsl(var(--muted-foreground))"></i>
        </div>
        {% endif %}
    </div>
    <div class="flex-shrink-0">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-wider mb-2" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        <h2 class="text-4xl font-bold tracking-tight mb-3 leading-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if body %}
        <p class="text-lg leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.85">{{body}}</p>
        {% endif %}
        {% if takeaway %}
        <p class="text-lg font-semibold mt-4 pl-4 border-l-4" style="color: hsl(var(--accent)); border-color: hsl(var(--accent))">{{takeaway}}</p>
        {% endif %}
    </div>
</div>
""",

    # split_concept — 좌우 개념 대비 (양쪽 모두 일러스트+캡션, 가운데 결론 박스)
    # 사용처: A vs B, 문제 vs 해결, 전/후, 뇌 vs 몸 같은 대조
    "split_concept": """
<div class="w-full h-full flex flex-col slide-illustration-bleed">
    {% if title %}
    <div class="px-14 pt-10 pb-4 flex-shrink-0">
        <h2 class="text-4xl font-bold text-center tracking-tight leading-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if subtitle %}<p class="text-lg text-center mt-2" style="color: hsl(var(--muted-foreground))">{{subtitle}}</p>{% endif %}
    </div>
    {% endif %}
    <div class="flex-1 flex min-h-0 relative">
        <div class="w-1/2 h-full flex flex-col items-center px-8 py-6" style="background: linear-gradient(180deg, transparent, hsl(var(--secondary) / 0.3))">
            <div class="flex items-center justify-center w-full" style="flex: 1 1 60%; min-height: 0;">
                {% if left_image_data %}
                <img src="{{left_image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
                {% endif %}
            </div>
            <div class="flex-shrink-0 w-full text-center mt-2" style="flex: 0 0 auto;">
                <h3 class="text-2xl font-bold mb-2" style="color: hsl(var(--foreground))">{{left_title}}</h3>
                {% if left_body %}
                <p class="text-base leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.8">{{left_body}}</p>
                {% endif %}
            </div>
        </div>
        <div class="w-1/2 h-full flex flex-col items-center px-8 py-6" style="background: linear-gradient(180deg, transparent, hsl(var(--accent) / 0.12))">
            <div class="flex items-center justify-center w-full" style="flex: 1 1 60%; min-height: 0;">
                {% if right_image_data %}
                <img src="{{right_image_data}}" class="max-w-full max-h-full object-contain slide-illustration">
                {% endif %}
            </div>
            <div class="flex-shrink-0 w-full text-center mt-2" style="flex: 0 0 auto;">
                <h3 class="text-2xl font-bold mb-2" style="color: hsl(var(--accent))">{{right_title}}</h3>
                {% if right_body %}
                <p class="text-base leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.8">{{right_body}}</p>
                {% endif %}
            </div>
        </div>
        {% if conclusion %}
        <div class="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 max-w-md px-7 py-4 rounded-lg shadow-xl text-center" style="background: hsl(var(--background)); border: 1.5px solid hsl(var(--accent)); z-index: 5;">
            <p class="text-base font-medium leading-relaxed" style="color: hsl(var(--foreground))">{{conclusion}}</p>
        </div>
        {% endif %}
    </div>
</div>
""",

    # comparison_iconic — 시각적 헤더가 있는 비교 표 (NotebookLM 5페이지 스타일)
    # 사용처: A vs B (말하는 챗봇 vs 일하는 에이전트, 도구 없는 AI vs 도구 가진 AI)
    # comparison_table과 다른 점: 헤더 행에 이모지/일러스트 + 큰 컬럼 제목 + 부드러운 배경
    #
    # 데이터 구조:
    #   title, subtitle (선택), eyebrow (선택)
    #   label_header: 좌측 라벨 컬럼 헤더 (예: "구분")
    #   columns: [{title: "도구가 없는 AI", subtitle: "(Chatbot)", icon: "💬"}, {title: "도구를 가진 AI", subtitle: "(Agent + Harness)", icon: "⚙️", highlighted: true}]
    #   rows: [{label: "역할", cells: ["통역사 및 조언자", "실제 문제를 해결하는 작업자"]}, ...]
    #         (주의: values가 아닌 cells — Jinja에서 .values는 dict 메서드와 충돌)
    #   footer (선택)
    "comparison_iconic": """
<div class="w-full h-full flex flex-col p-12 slide-illustration-bleed">
    <div class="mb-6 text-center flex-shrink-0">
        {% if eyebrow %}<p class="text-xs font-semibold uppercase tracking-[0.25em] mb-2 opacity-80" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        <h2 class="text-4xl font-bold tracking-tight leading-tight" style="color: hsl(var(--foreground))">{{title}}</h2>
        {% if subtitle %}<p class="text-base mt-2" style="color: hsl(var(--muted-foreground))">{{subtitle}}</p>{% endif %}
    </div>
    <div class="flex-1 flex items-center justify-center min-h-0">
        <table class="w-full max-w-6xl border-separate" style="border-spacing: 0; color: hsl(var(--foreground))">
            <thead>
                <tr>
                    <th class="w-[14%] py-5 px-4 text-base font-bold text-center" style="background: hsl(var(--secondary)); border: 1px solid hsl(var(--border)); border-right: none;">
                        {{label_header|default('구분')}}
                    </th>
                    {% for col in columns %}
                    <th class="py-5 px-6 text-center" style="
                        background: {% if col.highlighted %}hsl(var(--accent) / 0.15){% else %}hsl(var(--secondary)){% endif %};
                        border: 1px solid hsl(var(--border));
                        {% if not loop.last %}border-right: none;{% endif %}
                    ">
                        {% if col.icon %}<div class="text-3xl mb-2 leading-none">{{col.icon}}</div>{% endif %}
                        <div class="text-xl font-bold leading-tight" style="color: hsl(var(--foreground))">{{col.title}}</div>
                        {% if col.subtitle %}<div class="text-sm mt-1" style="color: hsl(var(--muted-foreground))">{{col.subtitle}}</div>{% endif %}
                    </th>
                    {% endfor %}
                </tr>
            </thead>
            <tbody>
                {% for row in rows %}
                <tr>
                    <td class="py-5 px-4 text-center font-bold text-base" style="
                        background: hsl(var(--secondary) / 0.5);
                        border: 1px solid hsl(var(--border));
                        border-top: none;
                        border-right: none;
                        color: hsl(var(--foreground));
                    ">
                        {{row.label}}
                    </td>
                    {% for val in row.cells %}
                    <td class="py-5 px-6 text-center text-base leading-relaxed" style="
                        background: {% if columns[loop.index0].highlighted %}hsl(var(--accent) / 0.05){% else %}transparent{% endif %};
                        border: 1px solid hsl(var(--border));
                        border-top: none;
                        {% if not loop.last %}border-right: none;{% endif %}
                        color: hsl(var(--foreground));
                    ">
                        {{val|safe}}
                    </td>
                    {% endfor %}
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
    {% if footer %}<p class="text-sm mt-4 text-center flex-shrink-0" style="color: hsl(var(--muted-foreground))">{{footer}}</p>{% endif %}
</div>
""",

    # illustration_background — 전면 일러스트 배경 + 오버레이 텍스트
    # 사용처: 강한 인상의 부 도입, 영화 같은 한 장면, 분위기 슬라이드
    # 옵션: text_align="center" (NotebookLM 부 표지 양식) / "left" (영화 자막 양식, 기본)
    "illustration_background": """
<div class="w-full h-full relative slide-illustration-bleed">
    {% if image_data %}
    <img src="{{image_data}}" class="absolute inset-0 w-full h-full object-cover slide-illustration-bg">
    {% endif %}
    {% set _align = text_align|default('left') %}
    {% if _align == 'center' %}
    <!-- center 모드: 일러스트 위에 텍스트가 직접 겹치므로 강한 라디얼 스크림 -->
    <div class="absolute inset-0" style="background: radial-gradient(ellipse 70% 50% at center, hsl(var(--background) / 0.78) 0%, hsl(var(--background) / 0.45) 65%, hsl(var(--background) / 0.65) 100%)"></div>
    <div class="relative w-full h-full flex flex-col items-center justify-center p-16 text-center">
        {% if eyebrow %}<p class="text-base font-semibold tracking-[0.3em] mb-6 opacity-80" style="color: hsl(var(--muted-foreground))">{{eyebrow}}</p>{% endif %}
        <h1 class="text-7xl font-black tracking-tight mb-5 leading-[1.1]" style="color: hsl(var(--foreground))">{{title}}</h1>
        {% if subtitle %}
        <p class="text-xl max-w-4xl leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.9">{{subtitle}}</p>
        {% endif %}
    </div>
    {% else %}
    <div class="absolute inset-0" style="background: linear-gradient(180deg, hsl(var(--background) / 0.1) 0%, hsl(var(--background) / 0.4) 50%, hsl(var(--background) / 0.85) 100%)"></div>
    <div class="relative w-full h-full flex flex-col justify-end p-16">
        {% if eyebrow %}<p class="text-sm font-semibold uppercase tracking-[0.3em] mb-4" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        <h1 class="text-6xl font-black tracking-tight mb-4 leading-tight" style="color: hsl(var(--foreground))">{{title}}</h1>
        {% if subtitle %}
        <p class="text-xl max-w-3xl leading-relaxed" style="color: hsl(var(--foreground)); opacity: 0.85">{{subtitle}}</p>
        {% endif %}
    </div>
    {% endif %}
</div>
""",

    # illustration_overlay — NotebookLM 양식: 풀-블리드 일러스트 + 자유 좌표 라벨 박스 N개
    # 사용처: 다이어그램형 슬라이드, 한 일러스트 안의 여러 구성요소를 한국어로 라벨링
    # 필수 키:
    #   - image_path / image_data : 풀-블리드 배경 이미지 (가급적 영문 라벨만 박힌 다이어그램)
    #   - labels : [{text, position}] 리스트
    #              position: "top-left" | "top-center" | "top-right" | "middle-left" |
    #                       "middle-center" | "middle-right" | "bottom-left" | "bottom-center" |
    #                       "bottom-right" 또는 {top: "20%", left: "10%", width: "30%"} 같은 절대 좌표
    #              variant(선택): "label"(작은 캡션, 기본) | "title"(큰 제목) | "panel"(다중행 본문)
    #              subtext(선택): variant=panel일 때 본문 줄들
    # 선택 키:
    #   - title : 상단 헤더 (선택). 없으면 라벨만 그려짐 — NotebookLM 다이어그램 슬라이드처럼.
    #   - eyebrow : 헤더 위 작은 라벨
    #   - footer_quote : 하단 결론 박스 (NotebookLM 5/8/10페이지 양식)
    "illustration_overlay": """
<div class="w-full h-full relative slide-illustration-bleed" style="background: hsl(var(--background));">
    {% if image_data %}
    <img src="{{image_data}}" class="absolute inset-0 w-full h-full object-cover slide-illustration-bg">
    {% endif %}

    {% if title or eyebrow %}
    <div class="absolute top-0 left-0 right-0 px-16 pt-12 pb-4 z-10" style="background: linear-gradient(180deg, hsl(var(--background) / 0.85) 0%, hsl(var(--background) / 0.5) 70%, transparent 100%);">
        {% if eyebrow %}<p class="text-xs font-semibold uppercase tracking-[0.25em] mb-2" style="color: hsl(var(--accent))">{{eyebrow}}</p>{% endif %}
        {% if title %}<h1 class="text-4xl font-black tracking-tight text-center" style="color: hsl(var(--foreground))">{{title}}</h1>{% endif %}
    </div>
    {% endif %}

    {% set _pos_map = {
        'top-left':       {'top': '14%', 'left': '4%',    'width': '26%', 'text-align': 'left'},
        'top-center':     {'top': '14%', 'left': '32%',   'width': '36%', 'text-align': 'center'},
        'top-right':      {'top': '14%', 'right': '4%',   'width': '26%', 'text-align': 'right'},
        'middle-left':    {'top': '42%', 'left': '4%',    'width': '26%', 'text-align': 'left'},
        'middle-center':  {'top': '42%', 'left': '32%',   'width': '36%', 'text-align': 'center'},
        'middle-right':   {'top': '42%', 'right': '4%',   'width': '26%', 'text-align': 'right'},
        'bottom-left':    {'bottom': '14%', 'left': '4%', 'width': '34%', 'text-align': 'left'},
        'bottom-center':  {'bottom': '14%', 'left': '20%','width': '60%', 'text-align': 'center'},
        'bottom-right':   {'bottom': '14%', 'right': '4%','width': '34%', 'text-align': 'right'}
    } %}

    {% for lbl in labels or [] %}
        {% set _v = lbl.variant or 'label' %}
        {% set _p = lbl.position %}
        {% if _p is string %}
            {% set _coord = _pos_map[_p] %}
        {% else %}
            {% set _coord = _p %}
        {% endif %}
        <div class="absolute z-20 hud-panel"
             style="
                {% if _coord.top %}top: {{_coord.top}};{% endif %}
                {% if _coord.bottom %}bottom: {{_coord.bottom}};{% endif %}
                {% if _coord.left %}left: {{_coord.left}};{% endif %}
                {% if _coord.right %}right: {{_coord.right}};{% endif %}
                {% if _coord.width %}width: {{_coord.width}};{% endif %}
                text-align: {{_coord['text-align'] or 'left'}};
                padding: {% if _v == 'title' %}14px 20px{% elif _v == 'panel' %}16px 22px{% else %}10px 16px{% endif %};
                background: hsl(var(--secondary) / 0.86);
                backdrop-filter: blur(6px);
             ">
            {% if _v == 'title' %}
                <p class="font-black tracking-tight" style="font-size: 1.6rem; color: hsl(var(--foreground)); line-height: 1.2">{{lbl.text}}</p>
                {% if lbl.subtext %}<p class="text-sm mt-1 opacity-80" style="color: hsl(var(--muted-foreground))">{{lbl.subtext}}</p>{% endif %}
            {% elif _v == 'panel' %}
                <p class="font-bold mb-2" style="font-size: 1.05rem; color: hsl(var(--accent))">{{lbl.text}}</p>
                {% if lbl.subtext %}
                    {% if lbl.subtext is string %}
                        <p class="text-sm leading-relaxed" style="color: hsl(var(--foreground))">{{lbl.subtext}}</p>
                    {% else %}
                        {% for line in lbl.subtext %}
                        <p class="text-sm leading-relaxed mb-1" style="color: hsl(var(--foreground))">{{line}}</p>
                        {% endfor %}
                    {% endif %}
                {% endif %}
            {% else %}
                <p class="font-semibold" style="font-size: 0.95rem; color: hsl(var(--foreground)); line-height: 1.4">{{lbl.text}}</p>
                {% if lbl.subtext %}<p class="text-xs mt-1 opacity-75" style="color: hsl(var(--muted-foreground))">{{lbl.subtext}}</p>{% endif %}
            {% endif %}
        </div>
    {% endfor %}

    {% if footer_quote %}
    <div class="absolute left-12 right-12 z-20 hud-panel" style="bottom: 36px; padding: 16px 24px; background: hsl(var(--secondary) / 0.92); backdrop-filter: blur(8px); text-align: center;">
        <p class="font-bold" style="font-size: 1.1rem; color: hsl(var(--foreground)); line-height: 1.5">{{footer_quote}}</p>
    </div>
    {% endif %}
</div>
""",

    # 커스텀 (Tailwind 자유 작성)
    "custom": """
{{custom_html|safe}}
"""
}


def get_image_base64(image_path: str) -> str:
    """이미지를 Base64로 변환"""
    if not image_path or not os.path.exists(image_path):
        return None
    try:
        with open(image_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode('utf-8')
            ext = os.path.splitext(image_path)[1].lower()
            mime = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".webp": "image/webp",
                ".gif": "image/gif"
            }.get(ext, "image/png")
            return f"data:{mime};base64,{encoded}"
    except Exception as e:
        print(f"이미지 로드 실패: {e}")
        return None


def render_slide(slide_data: dict, theme_name: str = "default", width: int = 1280, height: int = 720, design_system_name: str = "default") -> str:
    """슬라이드 HTML 생성

    Args:
        slide_data: 슬라이드 dict (layout + 레이아웃별 키)
        theme_name: 색 테마 (THEMES dict 키). design_system이 theme_override를 가지면 무시됨.
        design_system_name: 디자인 시스템 (DESIGN_SYSTEMS dict 키). 색+폰트+텍스처+장식 일관 묶음.
    """
    from jinja2 import Environment, BaseLoader, Undefined

    # Undefined 변수에 대해 빈 문자열 반환하는 환경 설정
    class SilentUndefined(Undefined):
        def _fail_with_undefined_error(self, *args, **kwargs):
            return ''
        def __str__(self):
            return ''
        def __iter__(self):
            return iter([])
        def __bool__(self):
            return False
        def __getitem__(self, key):
            return ''
        def __getattr__(self, name):
            return SilentUndefined()

    env = Environment(loader=BaseLoader(), undefined=SilentUndefined)

    # 디자인 시스템 가져오기 (먼저 — theme_override 적용 위해)
    ds = DESIGN_SYSTEMS.get(design_system_name, DESIGN_SYSTEMS["default"])

    # 테마 결정: 디자인 시스템이 override하면 그쪽, 아니면 외부 인자
    effective_theme_name = ds.get("theme_override") or theme_name
    theme = THEMES.get(effective_theme_name, THEMES["default"])

    # 레이아웃 타입
    layout_type = slide_data.get("layout", "hero")
    layout_template = SLIDE_LAYOUTS.get(layout_type, SLIDE_LAYOUTS["hero"])

    # 이미지 처리
    if slide_data.get("image_path"):
        slide_data["image_data"] = get_image_base64(slide_data["image_path"])
    if slide_data.get("avatar_path"):
        slide_data["avatar_data"] = get_image_base64(slide_data["avatar_path"])
    if slide_data.get("left_image_path"):
        slide_data["left_image_data"] = get_image_base64(slide_data["left_image_path"])
    if slide_data.get("right_image_path"):
        slide_data["right_image_data"] = get_image_base64(slide_data["right_image_path"])

    # 레이아웃 렌더링 (SilentUndefined 사용)
    layout_tpl = env.from_string(layout_template)
    content_html = layout_tpl.render(**slide_data)

    # style_overrides — spec에 사용자가 지정한 미세 조정값 (없으면 빈 CSS)
    style_overrides_css = _build_style_overrides_css(slide_data.get("style_overrides"))

    # 베이스 템플릿에 삽입 (디자인 시스템 주입 포함)
    base_tpl = env.from_string(SLIDE_BASE_TEMPLATE)
    full_html = base_tpl.render(
        theme=theme,
        width=width,
        height=height,
        content=content_html,
        design_system_head=ds.get("extra_head", ""),
        design_system_css=ds.get("extra_css", ""),
        design_system_html=ds.get("extra_html", ""),
        style_overrides_css=style_overrides_css,
    )

    return full_html


def _build_style_overrides_css(overrides) -> str:
    """spec.style_overrides → 슬라이드별 추가 CSS.

    지원 키:
      - font_scale: float (0.7 ~ 1.4). html root font-size 조정 → 모든 rem 단위 비례.
      - text_align: 'left' | 'center' | 'right'. 본문 텍스트 강제 정렬.
      - accent_color: hex 문자열 (예: '#a55a3e'). primary 색 override.

    1280×720 viewport에서 font_scale은 텍스트만 비례 확대/축소 (이미지·여백은 그대로).
    너무 큰 값은 슬라이드가 잘릴 수 있음 — 0.85~1.25 권장.
    """
    if not overrides or not isinstance(overrides, dict):
        return ""

    parts = []

    # font_scale — html root font-size 조정 (tailwind rem 단위 비례)
    fs = overrides.get("font_scale")
    if isinstance(fs, (int, float)) and 0.5 <= float(fs) <= 2.0 and float(fs) != 1.0:
        parts.append(f"html {{ font-size: {16 * float(fs):.2f}px !important; }}")

    # text_align — 본문 텍스트 강제 정렬
    ta = overrides.get("text_align")
    if ta in ("left", "center", "right"):
        parts.append(
            f".slide-container h1, .slide-container h2, .slide-container h3, "
            f".slide-container p, .slide-container li, .slide-container blockquote "
            f"{{ text-align: {ta} !important; }}"
        )

    # accent_color — primary 색 override (text/bg/border-primary 클래스)
    ac = overrides.get("accent_color")
    if isinstance(ac, str) and ac.startswith("#") and len(ac) in (4, 7):
        parts.append(
            f".slide-container [class*='text-primary'] {{ color: {ac} !important; }}\n"
            f".slide-container [class*='bg-primary'] {{ background-color: {ac} !important; }}\n"
            f".slide-container [class*='border-primary'] {{ border-color: {ac} !important; }}"
        )

    return "\n".join(parts)


_LEGACY_SLIDE_THEMES = {
    "modern", "tech", "business", "title_bold", "dark_tech",
    "glassmorphism", "gradient_modern", "split_asymmetric",
    "minimal_white", "image_fullscreen", "data_card", "tailwind",
}


def _adapt_legacy_slide_input(tool_input: dict) -> dict:
    """옛 slide 스키마 입력을 [engines:slide_shadcn] 입력으로 호환 변환.

    옛 slide dict: {title, body, theme(modern/tech/...), image_path, bg_color, ...}
    새 slide dict: {layout, title, body, ...}

    layout이 없는 슬라이드에 한해 image_path/body 유무 기반으로 기본 layout 주입.
    옛 theme(slide_shadcn의 theme와 의미 다름)과 색상 키들은 제거.
    """
    adapted = dict(tool_input)
    slides = adapted.get("slides")
    if not isinstance(slides, list):
        return adapted
    new_slides = []
    for s in slides:
        if not isinstance(s, dict):
            new_slides.append(s)
            continue
        s = dict(s)
        if "layout" not in s:
            if s.get("image_path") or s.get("image_data"):
                s["layout"] = "content_image"
            elif s.get("body"):
                s["layout"] = "lecture_body"
            else:
                s["layout"] = "hero"
        for legacy_key in ("theme", "bg_color", "text_color", "accent_color"):
            s.pop(legacy_key, None)
        new_slides.append(s)
    adapted["slides"] = new_slides
    if adapted.get("theme") in _LEGACY_SLIDE_THEMES:
        adapted.pop("theme")
    return adapted


def _bundle_slides(png_paths: list, output_dir: str, fmt: str, width: int, height: int) -> str:
    """렌더된 슬라이드 PNG들을 단일 공유 파일로 묶음 — 디자인 보존(이미지 그대로).
    pdf=슬라이드당 1페이지 / pptx=슬라이드당 풀블리드 이미지. 반환: 산출 파일 절대경로."""
    if fmt == "pdf":
        from PIL import Image
        imgs = [Image.open(p).convert("RGB") for p in png_paths]
        out = os.path.join(output_dir, "slides.pdf")
        imgs[0].save(out, save_all=True, append_images=imgs[1:])
        return out
    if fmt == "pptx":
        from pptx import Presentation
        from pptx.util import Emu
        prs = Presentation()
        prs.slide_width = Emu(int(width / 96 * 914400))   # px→EMU (96dpi 가정, 슬라이드 비율 유지)
        prs.slide_height = Emu(int(height / 96 * 914400))
        blank = prs.slide_layouts[6]
        for p in png_paths:
            s = prs.slides.add_slide(blank)
            s.shapes.add_picture(p, 0, 0, width=prs.slide_width, height=prs.slide_height)
        out = os.path.join(output_dir, "slides.pptx")
        prs.save(out)
        return out
    raise ValueError(f"지원하지 않는 format: {fmt}")


def create_shadcn_slides(tool_input: dict, output_base: str) -> str:
    """
    shadcn 스타일 슬라이드 생성"""
    tool_input = _adapt_legacy_slide_input(tool_input)
    return _create_shadcn_slides_impl(tool_input, output_base)


def _create_shadcn_slides_impl(tool_input: dict, output_base: str) -> str:
    """
    shadcn 스타일 슬라이드 생성 (실제 구현)

    Args:
        tool_input: {
            "slides": [
                {
                    # layout 옵션:
                    #   마케팅: hero / hero_image / features / stats / testimonial / pricing / cta / content_image / steps / custom
                    #   강의:   lecture_body / metaphor_story / comparison_table / factbox / quote
                    #   통합형 일러스트(NotebookLM 스타일):
                    #           hero_illustration / illustration_anchor / split_concept /
                    #           illustration_background / comparison_iconic
                    "layout": "hero",
                    "title": "제목",
                    "subtitle": "부제목",
                    # 일러스트가 필요한 layout에 image_path 절대경로(자동 base64 변환):
                    #   - image_path  → image_data  (hero_illustration / illustration_anchor / illustration_background / hero_image / content_image)
                    #   - left_image_path  → left_image_data  (split_concept)
                    #   - right_image_path → right_image_data (split_concept)
                    #   - avatar_path → avatar_data           (testimonial)
                    ...
                }
            ],
            "theme": "blue",          # default / blue / green / purple / orange / dark
            "design_system": "vintage_book",  # default / vintage_book / academic_paper / tech_minimal / magazine_modern
            "output_dir": "경로",     # 선택. 미지정 시 output_base/shadcn_slides_<8자hex>/
            "width": 1280,            # 선택. 슬라이드 가로 픽셀 (기본 1280)
            "height": 720             # 선택. 슬라이드 세로 픽셀 (기본 720)
        }

    Returns:
        JSON: {success, message, output_dir, images[], html_files[], theme}
    """
    slides_data = tool_input.get("slides", [])

    # 가드: 빈 slides + 옛 호출 패턴 감지
    if not slides_data:
        legacy_keys = [k for k in ("topic", "file") if k in tool_input]
        if legacy_keys:
            return (
                "오류: [engines:slide_shadcn]는 'slides' 배열 인라인 호출만 받습니다. "
                f"'{', '.join(legacy_keys)}'는 지원하지 않습니다. "
                "올바른 호출: [engines:slide_shadcn]{slides: [{layout: \"hero\", title: \"제목\", subtitle: \"부제\"}, ...]}. "
                "레이아웃 목록은 read_guide(query=\"슬라이드\")로 가이드 확인."
            )
        return (
            "오류: [engines:slide_shadcn] 호출에 slides 배열이 비어있습니다. "
            "[engines:slide_shadcn]{slides: [{layout, title, ...}, ...]} 형태로 인라인 배열을 전달하세요."
        )

    theme_name = tool_input.get("theme", "default")
    design_system_name = tool_input.get("design_system", "default")
    if design_system_name not in DESIGN_SYSTEMS:
        return (
            f"오류: 알 수 없는 design_system: '{design_system_name}'. "
            f"사용 가능: {', '.join(DESIGN_SYSTEMS.keys())}"
        )
    custom_output_dir = tool_input.get("output_dir")
    width = tool_input.get("width", 1280)
    height = tool_input.get("height", 720)

    output_dir = custom_output_dir if custom_output_dir else os.path.join(output_base, f"shadcn_slides_{uuid.uuid4().hex[:8]}")
    output_dir = os.path.abspath(output_dir)  # 외부와 소통하는 모든 경로는 절대경로 (AI 안내가 cwd에 의존하지 않도록)
    os.makedirs(output_dir, exist_ok=True)

    generated_paths = []
    html_paths = []

    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": width, "height": height})

            for i, slide in enumerate(slides_data):
                # HTML 생성
                html_content = render_slide(slide, theme_name, width, height, design_system_name)

                # HTML 파일 저장 (디버깅용)
                html_path = os.path.join(output_dir, f"slide_{i+1:02d}.html")
                with open(html_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                html_paths.append(html_path)

                # 렌더링
                page.set_content(html_content)
                page.wait_for_load_state("networkidle")
                page.wait_for_timeout(800)  # Tailwind/폰트/아이콘 로딩 대기

                # 스크린샷
                png_path = os.path.join(output_dir, f"slide_{i+1:02d}.png")
                page.screenshot(path=png_path)
                generated_paths.append(png_path)

            browser.close()

        # emitter 정리: 슬라이드 IR(slides[]) → png(기본, 슬라이드별 이미지) / pdf / pptx.
        # ★슬라이드 layout은 디자인된 HTML이라, pdf·pptx는 렌더된 PNG를 그대로 보존(네이티브 도형 재구성=디자인 파괴).
        fmt = (tool_input.get("format") or "png").strip().lower()
        result = {
            "success": True,
            "message": f"{len(generated_paths)}개의 슬라이드가 생성되었습니다",
            "output_dir": output_dir,
            "images": generated_paths,
            "html_files": html_paths,
            "theme": theme_name,
            "format": "png",
        }
        if fmt in ("pdf", "pptx") and generated_paths:
            try:
                bundle = _bundle_slides(generated_paths, output_dir, fmt, width, height)
                result["format"] = fmt
                result["path"] = bundle
                result["file"] = bundle
                result["message"] = f"{len(generated_paths)}개 슬라이드를 {fmt.upper()}로 묶었습니다."
            except Exception as e:
                result["message"] += f" (단, {fmt} 묶기 실패 → PNG 유지: {e})"
        return json.dumps(result, ensure_ascii=False)

    except ImportError:
        return json.dumps({
            "success": False,
            "error": "Playwright가 설치되어 있지 않습니다. 'pip install playwright && playwright install chromium' 실행 필요"
        }, ensure_ascii=False)
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        }, ensure_ascii=False)


if __name__ == "__main__":
    # 테스트
    test_input = {
        "theme": "blue",
        "slides": [
            {
                "layout": "hero",
                "badge": "New Release",
                "title": "IndieBiz OS",
                "subtitle": "AI 기반 통합 비즈니스 관리 시스템",
                "cta_text": "시작하기"
            },
            {
                "layout": "features",
                "title": "주요 기능",
                "features": [
                    {"icon": "🤖", "title": "AI 에이전트", "description": "맞춤형 AI 비서가 업무를 도와줍니다"},
                    {"icon": "📊", "title": "데이터 분석", "description": "실시간 인사이트를 제공합니다"},
                    {"icon": "🔗", "title": "통합 연동", "description": "다양한 서비스와 연결됩니다"}
                ]
            },
            {
                "layout": "stats",
                "title": "성과",
                "stats": [
                    {"value": "10K+", "label": "활성 사용자"},
                    {"value": "99.9%", "label": "가동률"},
                    {"value": "24/7", "label": "지원"},
                    {"value": "50+", "label": "통합 서비스"}
                ]
            },
            {
                "layout": "cta",
                "title": "지금 시작하세요",
                "subtitle": "무료로 체험해보고 비즈니스를 성장시키세요",
                "cta_text": "무료 체험 시작"
            }
        ]
    }

    result = create_shadcn_slides(test_input, "/tmp/test_slides")
    print(result)
