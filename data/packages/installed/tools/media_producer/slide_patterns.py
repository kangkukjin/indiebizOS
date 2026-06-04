"""
슬라이드 레이아웃 패턴 라이브러리 — [engines:slide] 저작 AI의 '디자인 어휘 사전'.

자유형 custom_html을 백지에서 짜면 품질이 들쭉날쭉하다. 프로 슬라이드는 검증된 패턴
(비교·타임라인·통계 히어로·프로세스 플로우·벤토 그리드 등)을 *변주*해서 만든다. 이 모듈은
웹 리서치(consulting deck 분석 9구조 + 12컬럼 그리드 규칙 + 2026 벤토 그리드 트렌드 + 시각위계
원칙)로 추린 패턴을 design_system CSS 변수 기반 HTML 스켈레톤으로 박제한 것이다.

사용처: slide_author 가 저작 시스템 프롬프트에 이 패턴들을 주입한다. AI는 고정 메뉴로 쓰지 말고
**내용에 맞게 고르고 변주**하라(틀이 아니라 출발점). 잘 나온 슬라이드를 여기에 증류해 라이브러리를
키울 수 있다(해마와 동형).

출처:
- Deckary, "PowerPoint Layout Ideas: 9 Proven Structures" (consulting deck 300+ 분석)
- SlideBazaar, "The Invisible Grid System" (12컬럼·여백 5-10%·4/8px baseline)
- SlideModel/Visme/BrightCarbon (시각위계·여백·rule of three·벤토 그리드)
"""

# ── 전역 디자인 원칙 (연구 합의) ──────────────────────────────────────
DESIGN_PRINCIPLES = """## 디자인 원칙 (모든 패턴에 공통 — 프로 슬라이드의 합의)
- **시각 위계**: 제목이 가장 크고 굵다(명제). 부제 < 본문 순으로 작아진다. 한눈에 읽는 순서가 보여야 함.
- **그리드 정렬**: 모든 요소를 보이지 않는 격자에 맞춘다(좌/우 끝선·열 경계). 눈대중 배치 금지. flex/grid로 정렬.
- **여백**: 가장자리 패딩은 슬라이드 폭의 5~10%(`p-16`~`p-20`). 빽빽함보다 숨 쉴 공간. 한 장에 한 아이디어.
- **핵심은 좌상단**: 가장 중요한 정보를 좌상단~상단에(서구식 읽기 동선).
- **정보 밀도 절제**: 불릿 3~4개 max, 벤토 박스 6개 이하. 더 많으면 두 장으로.
- **강조 격리**: 수치·고유명사는 평문에 묻지 말고 큰 글씨/강조색(`hsl(var(--accent))`)/박스로 분리.
"""

# ── 패턴들 ───────────────────────────────────────────────────────────
# 각 패턴: name(영문 키) · ko(한글 이름) · use(언제) · html(스켈레톤, 변주 대상)
# html은 design_system CSS 변수만 쓴다 — 색 하드코딩 금지. Tailwind/lucide/이모지/SVG 사용.

PATTERNS = [
    {
        "name": "single_column",
        "ko": "단일 컬럼 (요약·결론)",
        "use": "executive summary, 전략 결론. 명제 + 불릿 3~4개, 넉넉한 여백.",
        "html": """<div class="w-full h-full flex flex-col justify-center p-20" style="color:hsl(var(--foreground))">
  <p class="text-sm font-semibold uppercase tracking-widest mb-4" style="color:hsl(var(--accent))">EYEBROW</p>
  <h1 class="text-5xl font-black leading-tight mb-10 max-w-4xl">핵심 결론을 단정문으로</h1>
  <ul class="space-y-5 text-2xl max-w-3xl">
    <li class="flex gap-4"><span class="font-bold" style="color:hsl(var(--accent))">→</span><span>요점 하나</span></li>
    <li class="flex gap-4"><span class="font-bold" style="color:hsl(var(--accent))">→</span><span>요점 둘</span></li>
    <li class="flex gap-4"><span class="font-bold" style="color:hsl(var(--accent))">→</span><span>요점 셋</span></li>
  </ul>
</div>""",
    },
    {
        "name": "two_column",
        "ko": "2단 (텍스트 + 시각)",
        "use": "대부분의 본문. 좌 설명(불릿) + 우 시각요소(차트/아이콘/큰 수치).",
        "html": """<div class="w-full h-full flex flex-col p-16" style="color:hsl(var(--foreground))">
  <h1 class="text-5xl font-black mb-10 leading-[1.1] max-w-4xl">헤드라인 명제</h1>
  <div class="flex gap-12 flex-1 min-h-0">
    <ul class="w-1/2 space-y-5 text-xl self-center">
      <li class="flex gap-3"><i data-lucide="check" class="w-6 h-6 shrink-0" style="color:hsl(var(--accent))"></i><span>핵심 포인트 1</span></li>
      <li class="flex gap-3"><i data-lucide="check" class="w-6 h-6 shrink-0" style="color:hsl(var(--accent))"></i><span>핵심 포인트 2</span></li>
      <li class="flex gap-3"><i data-lucide="check" class="w-6 h-6 shrink-0" style="color:hsl(var(--accent))"></i><span>핵심 포인트 3</span></li>
    </ul>
    <div class="w-1/2 flex items-center justify-center rounded-2xl p-8" style="background:hsl(var(--muted))">
      <!-- 시각요소: SVG 막대/도넛, 큰 수치, 또는 이모지 다이어그램 -->
      <div class="text-7xl font-black" style="color:hsl(var(--accent))">72%</div>
    </div>
  </div>
</div>""",
    },
    {
        "name": "three_column",
        "ko": "3단 (프레임워크·rule of three)",
        "use": "세 항목/세 기둥 비교, 프레임워크 구성요소. 동일 폭 3열.",
        "html": """<div class="w-full h-full flex flex-col p-16" style="color:hsl(var(--foreground))">
  <h1 class="text-5xl font-black mb-12 text-center leading-[1.1]">세 기둥으로 보는 명제</h1>
  <div class="grid grid-cols-3 gap-8 flex-1 min-h-0">
    <div class="flex flex-col p-7 rounded-2xl" style="background:hsl(var(--muted))">
      <div class="text-5xl mb-5">🧭</div>
      <h3 class="text-2xl font-bold mb-3">기둥 하나</h3>
      <p class="text-lg leading-relaxed" style="color:hsl(var(--muted-foreground))">짧은 설명</p>
    </div>
    <div class="flex flex-col p-7 rounded-2xl" style="background:hsl(var(--muted))">
      <div class="text-5xl mb-5">⚙️</div>
      <h3 class="text-2xl font-bold mb-3">기둥 둘</h3>
      <p class="text-lg leading-relaxed" style="color:hsl(var(--muted-foreground))">짧은 설명</p>
    </div>
    <div class="flex flex-col p-7 rounded-2xl" style="background:hsl(var(--muted))">
      <div class="text-5xl mb-5">🚀</div>
      <h3 class="text-2xl font-bold mb-3">기둥 셋</h3>
      <p class="text-lg leading-relaxed" style="color:hsl(var(--muted-foreground))">짧은 설명</p>
    </div>
  </div>
</div>""",
    },
    {
        "name": "stat_hero",
        "ko": "통계 히어로 (큰 숫자)",
        "use": "핵심 수치 하나로 명제 증명(hero fact). 거대 숫자 + 의미. 보조 수치 trio 변주 가능.",
        "html": """<div class="w-full h-full flex flex-col justify-center items-center p-16 text-center" style="color:hsl(var(--foreground))">
  <p class="text-2xl mb-6 max-w-2xl" style="color:hsl(var(--muted-foreground))">이 수치가 말하는 맥락 한 줄</p>
  <div class="font-black leading-none" style="font-size:11rem;color:hsl(var(--accent))">87<span class="text-7xl align-top">%</span></div>
  <p class="text-3xl font-bold mt-6 max-w-3xl">숫자의 의미를 명제로</p>
</div>""",
    },
    {
        "name": "timeline",
        "ko": "타임라인 (가로 연대)",
        "use": "연혁·로드맵·변화 과정. 가로 축에 노드 + 연도/사건. 마지막 노드를 도달점으로 격리.",
        "html": """<div class="w-full h-full flex flex-col justify-center p-20" style="color:hsl(var(--foreground))">
  <p class="text-sm font-semibold uppercase tracking-[0.25em] mb-5" style="color:hsl(var(--accent))">GROWTH TIMELINE</p>
  <h1 class="text-6xl font-black leading-[1.08] mb-16 max-w-4xl">변화의 과정을 한 문장 명제로</h1>
  <div class="flex items-start gap-2">
    <div class="flex-1 relative pr-8">
      <div class="flex items-center mb-6">
        <span class="relative flex h-4 w-4 shrink-0"><span class="absolute inline-flex h-full w-full rounded-full opacity-30 animate-ping" style="background:hsl(var(--accent))"></span><span class="relative inline-flex rounded-full h-4 w-4" style="background:hsl(var(--accent))"></span></span>
        <span class="h-px flex-1 ml-1" style="background:linear-gradient(90deg,hsl(var(--accent)/0.6),hsl(var(--border)))"></span>
      </div>
      <div class="text-5xl font-black tracking-tight" style="color:hsl(var(--accent))">2024</div>
      <div class="text-xl font-bold mt-3">창업</div>
      <div class="text-base mt-2 leading-relaxed" style="color:hsl(var(--muted-foreground))">짧은 설명</div>
    </div>
    <div class="flex-1 relative pr-8">
      <div class="flex items-center mb-6">
        <span class="relative inline-flex rounded-full h-4 w-4 shrink-0" style="background:hsl(var(--accent))"></span>
        <span class="h-px flex-1 ml-1" style="background:linear-gradient(90deg,hsl(var(--accent)/0.6),hsl(var(--border)))"></span>
      </div>
      <div class="text-5xl font-black tracking-tight" style="color:hsl(var(--accent))">2025</div>
      <div class="text-xl font-bold mt-3">전환점</div>
      <div class="text-base mt-2 leading-relaxed" style="color:hsl(var(--muted-foreground))">짧은 설명</div>
    </div>
    <div class="flex-1 relative">
      <div class="flex items-center mb-6">
        <span class="relative inline-flex items-center justify-center rounded-full h-5 w-5 shrink-0" style="background:hsl(var(--foreground))"><i data-lucide="check" class="w-3 h-3" style="color:hsl(var(--background))"></i></span>
      </div>
      <div class="text-5xl font-black tracking-tight">2026</div>
      <div class="text-xl font-bold mt-3">도달점</div>
      <div class="text-base mt-2 leading-relaxed" style="color:hsl(var(--muted-foreground))">짧은 설명</div>
    </div>
  </div>
</div>""",
    },
    {
        "name": "process_flow",
        "ko": "프로세스 플로우 (단계+화살표)",
        "use": "작동 원리·절차·인과 흐름. 단계 박스 사이 화살표.",
        "html": """<div class="w-full h-full flex flex-col p-16" style="color:hsl(var(--foreground))">
  <h1 class="text-5xl font-black mb-16 leading-[1.1] max-w-4xl">어떻게 작동하는가</h1>
  <div class="flex items-center justify-between flex-1">
    <div class="flex-1 text-center px-3"><div class="text-5xl mb-3">📥</div><div class="font-bold text-xl">입력</div><div class="text-sm mt-1" style="color:hsl(var(--muted-foreground))">설명</div></div>
    <i data-lucide="arrow-right" class="w-10 h-10 shrink-0" style="color:hsl(var(--accent))"></i>
    <div class="flex-1 text-center px-3"><div class="text-5xl mb-3">⚙️</div><div class="font-bold text-xl">처리</div><div class="text-sm mt-1" style="color:hsl(var(--muted-foreground))">설명</div></div>
    <i data-lucide="arrow-right" class="w-10 h-10 shrink-0" style="color:hsl(var(--accent))"></i>
    <div class="flex-1 text-center px-3"><div class="text-5xl mb-3">✅</div><div class="font-bold text-xl">결과</div><div class="text-sm mt-1" style="color:hsl(var(--muted-foreground))">설명</div></div>
  </div>
</div>""",
    },
    {
        "name": "bento_grid",
        "ko": "벤토 그리드 (2026 트렌드)",
        "use": "다지표 대시보드·포트폴리오. 비대칭 박스 격자(6개 이하). 큰 박스 1 + 작은 박스들.",
        "html": """<div class="w-full h-full flex flex-col p-16" style="color:hsl(var(--foreground))">
  <h1 class="text-3xl font-black mb-6 leading-tight">한눈에 보는 현황</h1>
  <div class="grid grid-cols-3 grid-rows-2 gap-5 flex-1 min-h-0">
    <div class="col-span-2 row-span-1 rounded-2xl p-7 flex flex-col justify-center" style="background:hsl(var(--muted))">
      <div class="text-6xl font-black" style="color:hsl(var(--accent))">1.2M</div><div class="text-xl mt-2">주요 지표</div>
    </div>
    <div class="rounded-2xl p-6 flex flex-col justify-center" style="background:hsl(var(--muted))"><div class="text-4xl font-black">+38%</div><div class="text-sm mt-1" style="color:hsl(var(--muted-foreground))">성장</div></div>
    <div class="rounded-2xl p-6 flex flex-col justify-center" style="background:hsl(var(--muted))"><div class="text-4xl font-black">4.8★</div><div class="text-sm mt-1" style="color:hsl(var(--muted-foreground))">만족</div></div>
    <div class="col-span-2 rounded-2xl p-6 flex items-center gap-4" style="background:hsl(var(--muted))"><i data-lucide="trending-up" class="w-10 h-10" style="color:hsl(var(--accent))"></i><span class="text-lg">한 줄 인사이트</span></div>
  </div>
</div>""",
    },
    {
        "name": "comparison",
        "ko": "대비 (A vs B)",
        "use": "두 항 대조(전/후, 우리/경쟁, 도구/협업자). 좌우 카드 + 중앙 화살표/VS.",
        "html": """<div class="w-full h-full flex flex-col p-16" style="color:hsl(var(--foreground))">
  <h1 class="text-5xl font-black mb-10 leading-[1.1] max-w-4xl">A는 B가 되었다</h1>
  <div class="flex items-stretch gap-6 flex-1 min-h-0">
    <div class="flex-1 rounded-2xl p-8 flex flex-col" style="background:hsl(var(--muted))">
      <div class="flex items-center gap-3 mb-5"><i data-lucide="circle-dashed" class="w-7 h-7" style="color:hsl(var(--muted-foreground))"></i><h3 class="text-2xl font-bold">이전 (A)</h3></div>
      <ul class="space-y-3 text-lg" style="color:hsl(var(--muted-foreground))"><li>특징 1</li><li>특징 2</li><li>특징 3</li></ul>
    </div>
    <div class="flex items-center"><i data-lucide="arrow-right" class="w-9 h-9" style="color:hsl(var(--accent))"></i></div>
    <div class="flex-1 rounded-2xl p-8 flex flex-col border-2" style="border-color:hsl(var(--accent))">
      <div class="flex items-center gap-3 mb-5"><i data-lucide="sparkles" class="w-7 h-7" style="color:hsl(var(--accent))"></i><h3 class="text-2xl font-bold" style="color:hsl(var(--accent))">이후 (B)</h3></div>
      <ul class="space-y-3 text-lg"><li>특징 1</li><li>특징 2</li><li>특징 3</li></ul>
    </div>
  </div>
</div>""",
    },
    {
        "name": "section_divider",
        "ko": "섹션 표지 (큰 제목)",
        "use": "부 도입·구획 전환. 거대 중앙 텍스트, rule of thirds, 강한 여백.",
        "html": """<div class="w-full h-full flex flex-col justify-center items-center p-16 text-center" style="color:hsl(var(--foreground))">
  <p class="text-lg font-semibold uppercase tracking-[0.3em] mb-8" style="color:hsl(var(--accent))">PART 02</p>
  <h1 class="text-7xl font-black leading-tight max-w-4xl">부의 제목을 명제로</h1>
  <div class="w-24 h-1 mt-10" style="background:hsl(var(--accent))"></div>
</div>""",
    },
    {
        "name": "quote_feature",
        "ko": "인용 강조 (풀스크린)",
        "use": "핵심 인용·회수·임팩트 한 문장. 거대 인용부호 + 큰 문장.",
        "html": """<div class="w-full h-full flex flex-col justify-center p-24" style="color:hsl(var(--foreground))">
  <div class="font-black leading-none mb-2" style="font-size:8rem;color:hsl(var(--accent));opacity:0.5">&ldquo;</div>
  <blockquote class="text-5xl font-bold leading-snug max-w-4xl -mt-8">기억에 남길 한 문장을 여기에.</blockquote>
  <p class="text-2xl mt-10" style="color:hsl(var(--muted-foreground))">— 출처 / 화자</p>
</div>""",
    },
]


def render_pattern_library() -> str:
    """저작 프롬프트에 주입할 패턴 라이브러리 텍스트 생성."""
    lines = [
        "# 레이아웃 패턴 라이브러리 (디자인 어휘 — 백지에서 짜지 말 것)",
        "아래는 프로 슬라이드에서 검증된 배치 패턴이다. 내용에 맞는 패턴을 **골라서 변주**하라 "
        "(고정 틀이 아니라 출발점 — 색·아이콘·항목 수·구조를 자유롭게 조정). 어느 패턴도 안 맞으면 "
        "원칙만 지켜 새로 설계해도 된다. 모든 HTML은 design_system CSS 변수를 쓴다(색 하드코딩 금지).",
        "",
        DESIGN_PRINCIPLES,
        "## 패턴 목록",
    ]
    for p in PATTERNS:
        lines.append(f"\n### {p['name']} — {p['ko']}\n- 언제: {p['use']}\n```html\n{p['html']}\n```")
    return "\n".join(lines)
