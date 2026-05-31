# 슬라이드 제작 가이드

HTML/Playwright 기반으로 1280x720px 슬라이드 이미지(PNG)를 생성하는 도구입니다.
기본 제공 테마를 사용하거나, `tailwind` 테마 + `custom_html`로 자유롭게 디자인할 수 있습니다.

## 강의·교육용 슬라이드를 만든다면 — 먼저 읽을 가이드

본 가이드는 **도구 사용법**이다. 강의·교육·발표 슬라이드라면 도구를 호출하기 전에 다음을 먼저 읽는다:

- **[lecture_slide_principles.md](lecture_slide_principles.md) §2 — 메시지 큐레이션 5단계** ★ 명제 추출 → 슬라이드=명제 → 수사장치 매핑 → 구체화 → 이중 회수. **이 단계가 슬라이드 품질을 결정한다.** 톤·디자인이 NotebookLM과 똑같아도 이 단계가 빠지면 결과물의 격이 다르다.
- 일러스트가 들어가는 강의 슬라이드는 [lecture_slides_with_illustrations.md](lecture_slides_with_illustrations.md) 추가 참조.

도구만 호출하면 "텍스트 나열" 슬라이드가 나오기 쉽다. 책 본문을 슬라이드에 옮기는 게 아니라, 명제를 추출해서 슬라이드 = 명제로 만들어야 한다.

## 뷰포트 고정 규칙 (필수)

**모든 슬라이드는 1280x720px 고정입니다.** 콘텐츠가 이 영역을 초과하면 잘립니다.

---

## 방법 1: 기본 테마 사용

title, body, theme만 지정하면 자동으로 HTML이 생성됩니다.

### 사용 가능한 테마

| 테마 | 설명 | 추가 파라미터 |
|------|------|--------------|
| modern (기본) | 깔끔한 모던 스타일 | bg_color, text_color |
| tech | 모노스페이스 다크 해커 스타일 | - |
| business | 비즈니스 프레젠테이션 | - |
| title_bold | 대형 타이포그래피 | accent_color |
| dark_tech | 다크모드 + 네온 그리드 | - |
| glassmorphism | 유리 효과 카드 | bg_color1, bg_color2 |
| gradient_modern | 그라데이션 배경 | bg_color1, bg_color2 |
| split_asymmetric | 좌우 비대칭 분할 | accent_color |
| minimal_white | 미니멀 화이트 | - |
| image_fullscreen | 전체 배경 이미지 + 오버레이 | image_path (필수) |
| data_card | 숫자/데이터 3열 강조 | data1_value, data1_label, ... |
| tailwind | Tailwind CSS 자유 디자인 | custom_html (아래 참조) |

### 기본 사용 예시

```json
{
  "slides": [
    {"title": "서비스 소개", "body": "AI 기반 자동화 솔루션", "theme": "dark_tech"},
    {"title": "핵심 수치", "body": "", "theme": "data_card",
     "data1_value": "99.9%", "data1_label": "가동률",
     "data2_value": "50+", "data2_label": "고객사",
     "data3_value": "24/7", "data3_label": "모니터링"},
    {"title": "감사합니다", "body": "문의: hello@example.com",
     "theme": "glassmorphism", "bg_color1": "#667eea", "bg_color2": "#764ba2"}
  ]
}
```

---

## 방법 2: tailwind 테마 + custom_html (권장)

가장 자유도가 높은 방법입니다. custom_html에 Tailwind CSS로 슬라이드를 직접 디자인합니다.

### 필수 레이아웃 규칙

```html
<!-- custom_html 내용 (body 안에 삽입됨) -->
<div style="width:1280px; height:720px; overflow:hidden; margin:0;"
     class="flex flex-col items-center justify-center p-[60px] box-border bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">

  <h1 class="text-7xl font-black text-white mb-6">제목</h1>
  <p class="text-2xl text-white/70">부제목</p>

</div>
```

**핵심 규칙:**
1. 최상위 래퍼에 `width:1280px; height:720px; overflow:hidden; margin:0;` 고정 (inline style)
2. Tailwind의 `w-full h-full`만으로는 부족 — 반드시 px 단위 고정
3. `flex` 또는 `grid` 레이아웃 사용 (absolute 지양)
4. 가로 배치는 3개 이하 또는 `flex-wrap` 사용
5. 한국어 텍스트는 영어보다 공간을 더 차지 — 폰트를 한 단계 작게

### 폰트 크기 기준

| 용도 | Tailwind | px |
|------|----------|----|
| 메인 제목 | text-6xl ~ text-7xl | 48~72px |
| 부제목 | text-2xl ~ text-3xl | 24~30px |
| 본문/라벨 | text-lg ~ text-xl | 18~20px |
| text-8xl(96px)은 짧은 영어 텍스트만 가능 | | |

### 자동 포함 리소스 (tailwind 테마)

tailwind 테마를 사용하면 다음이 자동으로 로드됩니다:
- **Tailwind CSS** (CDN)
- **Google Fonts**: Noto Sans KR, Black Han Sans, Do Hyeon, Gothic A1, Sunflower, Jua, Inter, Montserrat, Playfair Display, Poppins
- **Animate.css**: `animate__animated animate__fadeInUp` 등
- **Lucide Icons**: `<i data-lucide="아이콘명"></i>`
- **GSAP 3.12.2**: `gsap.from(...)` 등 (정적 이미지에서는 첫 프레임만 캡처됨)
- **Lottie Player**: `<lottie-player src="URL" ...></lottie-player>`

---

## 시각 디자인 가이드

### 배경 기법
- 그라데이션 필수 (단색 배경 금지)
- `bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900`
- `bg-gradient-to-r from-indigo-900 via-blue-900 to-cyan-900`
- 방사형: `style="background: radial-gradient(circle at 30% 40%, #1a1a2e, #16213e)"`

### 글래스모피즘 카드
```html
<div class="bg-white/10 backdrop-blur-xl rounded-3xl p-12 border border-white/20 shadow-2xl">
  <h2 class="text-3xl font-bold text-white mb-4">카드 제목</h2>
  <p class="text-lg text-white/70">내용</p>
</div>
```

### 텍스트 효과
- 그라데이션 텍스트: `text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-400`
- 네온 글로우: `drop-shadow-[0_0_20px_rgba(0,232,255,0.5)]`
- 뱃지: `px-4 py-1 rounded-full bg-cyan-500/20 text-cyan-300 text-sm font-medium`

### 레이아웃 패턴
- 그리드: `grid grid-cols-2 gap-6` / `grid grid-cols-3 gap-8`
- 아이콘 원형: `w-12 h-12 rounded-full bg-cyan-500/20 flex items-center justify-center`
- 구분선: `w-16 h-1 bg-gradient-to-r from-cyan-400 to-purple-400 rounded-full`

### Google Fonts 적용
```html
<h1 style="font-family: 'Black Han Sans'">임팩트 있는 제목</h1>
<p style="font-family: 'Noto Sans KR'">본문 텍스트</p>
```

| 조합 | 제목 | 본문 |
|------|------|------|
| 임팩트 | Black Han Sans | Noto Sans KR |
| 친근함 | Do Hyeon / Jua | Noto Sans KR |
| 모던 | Gothic A1 | - |
| 영문 프리미엄 | Playfair Display | Inter |
| 영문 모던 | Montserrat | Poppins |

### Lucide 아이콘
```html
<i data-lucide="rocket" class="w-8 h-8 text-cyan-400"></i>
<i data-lucide="shield-check" class="w-6 h-6 text-green-400"></i>
<i data-lucide="zap" class="w-10 h-10 text-yellow-400"></i>
```
[아이콘 목록](https://lucide.dev/icons) — search, star, heart, settings, users, chart-bar 등

### Lottie 애니메이션
```html
<lottie-player
  src="https://lottie.host/.../animation.json"
  background="transparent" speed="1"
  style="width:200px;height:200px"
  loop autoplay>
</lottie-player>
```

---

## custom_html 실전 예시

### 기능 소개 카드 (3열)
```html
<div style="width:1280px;height:720px;overflow:hidden;margin:0;"
     class="flex flex-col items-center justify-center p-[60px] box-border bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900">

  <p class="px-4 py-1 rounded-full bg-cyan-500/20 text-cyan-300 text-sm font-medium mb-6">핵심 기능</p>
  <h1 class="text-5xl font-black text-white mb-12 text-center" style="font-family:'Black Han Sans'">왜 선택해야 할까요?</h1>

  <div class="grid grid-cols-3 gap-8 w-full">
    <div class="bg-white/10 backdrop-blur rounded-2xl p-8 border border-white/20">
      <div class="w-12 h-12 rounded-full bg-cyan-500/20 flex items-center justify-center mb-4">
        <i data-lucide="zap" class="w-6 h-6 text-cyan-400"></i>
      </div>
      <h3 class="text-xl font-bold text-white mb-2">빠른 속도</h3>
      <p class="text-white/60 text-sm">실시간 처리로 즉각적인 결과를 제공합니다.</p>
    </div>
    <div class="bg-white/10 backdrop-blur rounded-2xl p-8 border border-white/20">
      <div class="w-12 h-12 rounded-full bg-purple-500/20 flex items-center justify-center mb-4">
        <i data-lucide="shield-check" class="w-6 h-6 text-purple-400"></i>
      </div>
      <h3 class="text-xl font-bold text-white mb-2">보안</h3>
      <p class="text-white/60 text-sm">엔터프라이즈급 보안으로 데이터를 보호합니다.</p>
    </div>
    <div class="bg-white/10 backdrop-blur rounded-2xl p-8 border border-white/20">
      <div class="w-12 h-12 rounded-full bg-pink-500/20 flex items-center justify-center mb-4">
        <i data-lucide="sparkles" class="w-6 h-6 text-pink-400"></i>
      </div>
      <h3 class="text-xl font-bold text-white mb-2">AI 기반</h3>
      <p class="text-white/60 text-sm">최신 AI 모델로 지능적인 자동화를 실현합니다.</p>
    </div>
  </div>
</div>
```

### 히어로 + 이미지 분할
```html
<div style="width:1280px;height:720px;overflow:hidden;margin:0;" class="flex">
  <div class="w-[55%] h-full bg-gradient-to-br from-indigo-900 to-blue-900 flex flex-col justify-center px-16">
    <p class="text-cyan-400 text-sm font-semibold tracking-widest mb-4">INTRODUCING</p>
    <h1 class="text-6xl font-black text-white mb-6 leading-tight" style="font-family:'Black Han Sans'">
      차세대 솔루션
    </h1>
    <p class="text-xl text-blue-200/80 leading-relaxed mb-8">
      혁신적인 기술로 비즈니스의 미래를 만들어갑니다.
    </p>
    <div class="flex gap-4">
      <div class="px-6 py-3 bg-cyan-500 rounded-lg text-white font-semibold text-sm">시작하기</div>
      <div class="px-6 py-3 border border-white/30 rounded-lg text-white/80 text-sm">더 알아보기</div>
    </div>
  </div>
  <div class="w-[45%] h-full bg-gradient-to-br from-cyan-500 to-blue-600"></div>
</div>
```

### 통계 숫자 강조
```html
<div style="width:1280px;height:720px;overflow:hidden;margin:0;"
     class="flex flex-col items-center justify-center p-[80px] box-border"
     style="background: linear-gradient(135deg, #0a0a0f, #1a1a2e)">

  <h2 class="text-4xl font-bold text-white mb-16 text-center">성장 지표</h2>

  <div class="grid grid-cols-4 gap-12 w-full">
    <div class="text-center">
      <div class="text-6xl font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-400 mb-3">99.9%</div>
      <div class="text-lg text-white/50">가동률</div>
    </div>
    <div class="text-center">
      <div class="text-6xl font-black text-transparent bg-clip-text bg-gradient-to-r from-purple-400 to-pink-400 mb-3">150+</div>
      <div class="text-lg text-white/50">글로벌 고객</div>
    </div>
    <div class="text-center">
      <div class="text-6xl font-black text-transparent bg-clip-text bg-gradient-to-r from-green-400 to-emerald-400 mb-3">3.2x</div>
      <div class="text-lg text-white/50">ROI 향상</div>
    </div>
    <div class="text-center">
      <div class="text-6xl font-black text-transparent bg-clip-text bg-gradient-to-r from-orange-400 to-red-400 mb-3">24/7</div>
      <div class="text-lg text-white/50">지원</div>
    </div>
  </div>
</div>
```

---

## 디자인 체크리스트

1. **배경**: 그라데이션 또는 다층 배경 (단색 금지)
2. **폰트**: 제목에 디자인 폰트(Black Han Sans 등), 본문에 Noto Sans KR
3. **색상**: 슬라이드마다 다른 컬러 팔레트, 최소 3색
4. **카드**: 글래스모피즘 또는 그라데이션 배경 카드 활용
5. **장식**: 아이콘, 뱃지, 구분선, 도형 중 최소 1개
6. **레이아웃**: 1280x720px 고정, 콘텐츠 넘침 없이 여유 있게
7. **한국어**: 영어보다 한 단계 작은 폰트 크기

---

# 강의·발표용 슬라이드 (slide_shadcn의 강의 레이아웃)

마케팅·카드뉴스용 레이아웃(hero/features/stats/cta 등)은 본문이 한두 줄로 압축되어 강의에 부적합하다. 책 한 권을 강의하거나 깊이 있는 콘텐츠를 가르치려면 본문 분량을 담을 수 있는 강의 전용 레이아웃을 사용한다.

## 언제 어느 강의 레이아웃을 쓰는가

| 강의 요소 | 적합 레이아웃 | 비고 |
|----------|------------|------|
| 한 챕터의 핵심 본문 + 설명 + 결론 | `lecture_body` | 가장 자주 씀. 본문 단락 + 4~6개 불릿 + 강조 인용 한 칸 |
| 핵심 메타포 (햄릿 무대, 깜깜한 계단 등) | `metaphor_story` | 메타포 본문을 큰 폰트로 + 결론 한 줄 |
| 두 개 이상 항목 비교 (v0 vs v5, A vs B) | `comparison_table` | 마크다운 표보다 가독성 ↑ |
| 보조 정보 (역사·정의·수치) | `factbox` | 책의 팩트박스 그대로 옮길 때 |
| 강력한 한 줄 명제 | `quote` | 풀스크린 임팩트 |
| 표지·부 도입·총정리 (텍스트만) | `hero` 또는 `cta` | 마케팅 레이아웃 재사용 |
| 표지·부 도입 (일러스트 포함) | `hero_illustration` / `illustration_background` | `lecture_slides_with_illustrations.md` 가이드 참조 |

## lecture_body — 가장 많이 쓰는 강의 슬라이드

```json
{
  "layout": "lecture_body",
  "eyebrow": "1부 · 1장",
  "title": "한 번의 속삭임이 끊임없는 대화가 되다",
  "subtitle": "(선택) 부제목",
  "body": "에이전틱 루프는 결국 프롬프트라는 바깥 층을 끝없이 다시 구성하는 기계다. 연출가는 한 번 지시하고 사라지지 않는다.",
  "bullets": [
    "지시 → AI에게 프롬프트 전달",
    "행동 → AI가 도구 사용 명령 출력",
    "관찰 → 도구 실행 결과 수집",
    "다음 지시 → 결과를 합쳐 새 프롬프트 구성"
  ],
  "quote": "에이전틱 루프가 적용되자 AI는 전보다 훨씬 더 많은 일을 할 수 있게 되었다.",
  "footer": "용어의 변화: 프롬프트 엔지니어링 → 컨텍스트 엔지니어링"
}
```

모든 필드(eyebrow/subtitle/body/bullets/quote/footer)는 선택. 필요한 것만 채우면 됨.

## metaphor_story — 핵심 메타포

```json
{
  "layout": "metaphor_story",
  "label": "메타포 · 4장 — 세계 모델이란",
  "story": "깜깜한 밤에 계단을 내려오는데 예상보다 한 단 더 낮다. 그 순간 — 발이 바닥에 닿기 전에 이미 무릎이 굽혀지고 골반이 낮아지고 반대쪽 팔이 균형을 잡는다. 생각은 그다음에 온다.",
  "takeaway": "어두운 계단에서 당신을 살린 것은 뇌의 지능이 아니라 몸의 지능이다."
}
```

## comparison_table — 비교

```json
{
  "layout": "comparison_table",
  "eyebrow": "막간 · 좋은 시스템 프롬프트",
  "title": "v0 → v5: 사전에서 존재 서술로",
  "headers": ["", "v0", "v5"],
  "rows": [
    ["분량", "~600줄", "<200줄"],
    ["형식", "이런 상황엔 이렇게 해라", "너는 ~이고, ~신경계가 있고"],
    ["출처", "Claude Code 복제", "indieBizOS 세계관 재작성"]
  ],
  "footer": "결론 — 좋은 시스템 프롬프트는 공식이 아니라 나무처럼 키우는 것이다."
}
```

## factbox — 책의 팩트박스

```json
{
  "layout": "factbox",
  "label": "팩트박스",
  "title": "MCP의 역사",
  "body": "MCP는 앤스로픽의 엔지니어가 2024년 7월에 만들었다.",
  "items": [
    "2024년 11월: 오픈소스 공개",
    "2025년 3월: 오픈AI 채택 → 업계 표준화",
    "2025년 12월: 리눅스 재단 AAIF에 기부"
  ],
  "source": "강국진, 『하네스란 무엇인가?』"
}
```

## quote — 풀스크린 인용

```json
{
  "layout": "quote",
  "quote": "팔이 없으면 뇌는 사과를 잡는 문제를 정의할 수 없다.",
  "attribution": "강국진, 『하네스란 무엇인가?』 제1부 2장",
  "context": "(선택) 인용에 대한 짧은 부연"
}
```

## 디자인 시스템 — 책 한 권의 비주얼 정체성

`design_system` 키로 슬라이드 전체에 색·폰트·배경 텍스처·장식까지 일관된 비주얼 정체성을 부여한다. theme(색만 바꿈)과 달리 design_system은 한 권의 책처럼 보이게 하는 모든 요소를 묶는다.

### 사용 가능한 디자인 시스템

| 이름 | 비주얼 | 추천 용도 |
|------|--------|----------|
| `default` | 흰 배경 + 검정 글씨 + Tailwind 기본 | 가벼운 마케팅·카드뉴스 |
| `vintage_book` | 베이지 종이 + 청·적갈 잉크 + Gowun Batang 명조 + 종이 노이즈 + 컴퍼스 코너 마크 | 책 강의·인문 발표·고전 양식 |
| `academic_paper` | 미색 종이 + 진남색 + 진홍색 강조 + Crimson Text 세리프 + IBM Plex 라벨 + 중앙 푸터 | 학술 논문·연구 발표·기술 보고서 |
| `tech_minimal` | 다크 남색 + 시안 네온 + Inter + JetBrains Mono 라벨 + 그리드 배경 + 빛나는 시안 점 | 테크 컨퍼런스·제품 데모·개발자 발표 |
| `magazine_modern` | 흰 배경 + 검정 + 선명한 적색 + Bebas Neue 헤드라인 + Playfair Display 본문 + 굵은 적색 막대 | 편집·잡지·트렌드 콘텐츠 |

### 호출 방법

```json
{
  "design_system": "vintage_book",
  "slides": [
    {"layout": "hero", "title": "...", "subtitle": "..."},
    {"layout": "lecture_body", "title": "...", "body": "..."},
    ...
  ]
}
```

design_system을 지정하면 **모든 layout**(hero/lecture_body/metaphor_story/comparison_table/factbox/quote 등)이 자동으로 그 디자인 언어로 렌더된다. 한 슬라이드씩 따로 디자인할 필요 없음.

### vintage_book 적용 효과

- 배경: 베이지 (#f3ecd6) + 미세한 종이 노이즈 텍스처
- 본문: Noto Serif KR (한국 출판 표준 명조 계열)
- 제목·라벨·표 헤더: Black Han Sans (굵은 디스플레이 한글)
- 색: 청색(#2c3e6f) 본문 + 적갈색(#a55a3e) 강조
- 좌상단: 컴퍼스 코너 마크 (책의 시그니처)
- 우하단: "indieBizOS" 워터마크
- 표: 양피지 적갈색 헤더
- 인용 박스: 적갈색 좌측 굵은 선
- 팩트박스: 베이지 카드 + 적갈색 테두리

### 책 단위 강의 슬라이드 권장

책 한 권의 강의를 만들 때는 처음부터 design_system을 정한다. 1부·2부·3부 모든 슬라이드가 같은 design_system을 쓰면 — 강의 전체가 그 책의 시각적 정체성을 갖는다.

---

## 강의 슬라이드 전체 구성 권장

한 챕터(예: 1부 1장)를 강의한다면 보통 3~5장의 슬라이드로 구성:

1. **부/장 도입** — `hero` (텍스트만) 또는 `hero_illustration`/`illustration_background` (일러스트 있는 경우, `lecture_slides_with_illustrations.md` 참조)
2. **메타포** — `metaphor_story` (텍스트만) 또는 `illustration_anchor` (일러스트 메타포)
3. **본문 설명** — `lecture_body` 1~3장
4. **비교/팩트** — `comparison_table` 또는 `factbox` (있다면)
5. **핵심 명제 정리** — `quote` 또는 `lecture_body`로 마무리

책 한 권의 한 부(part)는 보통 30~50장 분량의 강의 슬라이드가 적합하다 — 짧으면 깊이가 사라지고, 너무 길면 한 슬라이드에 정보가 넘친다.

---

# 마케팅 / 발표용 layout 카탈로그 (slide_shadcn)

랜딩 페이지, 제품 소개, 피치덱, 마케팅 자료에 쓰는 shadcn UI 기반 layout 10종. 각 layout은 `[engines:slide_shadcn]{slides: [{layout: "<이름>", ...}]}` 형태로 호출하며 `design_system`·`theme` 옵션으로 색·폰트 통합 가능.

## 빠른 참고

| layout | 용도 | 핵심 키 |
|---|---|---|
| `hero` | 표지·도입 (텍스트만) | title, subtitle, badge, cta_text |
| `hero_image` | 표지+일러스트 (좌우 분할) | title, subtitle, image_path, eyebrow, badge, cta_text |
| `features` | 기능 3열 그리드 | title, features: `[{title, description, icon}]` |
| `stats` | 통계 4열 강조 (primary 배경) | title, stats: `[{value, label}]` |
| `testimonial` | 인용·후기 (풀스크린 quote) | quote, author, role, avatar_path |
| `pricing` | 가격표 3열 카드 | title, plans: `[{name, description, price, period, features, cta_text, highlighted}]` |
| `cta` | Call-to-Action 배너 (primary 배경) | title, subtitle, cta_text |
| `content_image` | 콘텐츠+이미지 좌우 분할 | title, content, image_path, eyebrow, image_position |
| `steps` | 단계·타임라인 (가로 화살표) | title, steps: `[{title, description}]` (번호 자동) |
| `custom` | 자유 Tailwind HTML | custom_html |

> 강의·발표용 슬라이드(`lecture_body` 등)는 위 강의 섹션 참조. 일러스트 통합 layout(`hero_illustration` 등)은 `lecture_slides_with_illustrations.md` 참조.

## design_system / theme 매칭

| 옵션 | 영향 |
|---|---|
| `theme` (색만) | default / blue / green / purple / orange / dark — primary/secondary/accent CSS 변수만 |
| `design_system` (색+폰트+텍스처+장식 통합) | default / vintage_book / academic_paper / tech_minimal / magazine_modern |

**마케팅 자료라면 `tech_minimal`(SaaS/개발자) 또는 `magazine_modern`(에디토리얼/소비재)이 어울린다.** 데크 한 벌의 모든 슬라이드에 같은 design_system을 쓰면 시각적 정체성이 유지된다.

## hero — 표지·도입

```
[engines:slide_shadcn]{slides: [{
  layout: "hero",
  badge: "v2.0 출시",
  title: "더 빠른 작업, 더 적은 도구",
  subtitle: "IndieBiz OS는 흩어진 개인 데이터를 하나의 신경계로 묶어줍니다",
  cta_text: "지금 시작하기"
}], design_system: "tech_minimal"}
```

- `badge`(선택): 좌상단에 작은 라벨 칩
- `cta_text`(선택): 하단 액션 버튼 (실제 링크는 없음 — 데모용 시각만)
- 사용 시점: 데크 첫 슬라이드, 부/장 도입

## hero_image — 표지 + 이미지 (좌우 분할)

```
[engines:slide_shadcn]{slides: [{
  layout: "hero_image",
  eyebrow: "INTRODUCING",
  title: "당신의 데이터, 당신의 AI",
  subtitle: "Gmail·NAS·CCTV·홈페이지를 하나의 어시스턴트로",
  cta_text: "데모 보기",
  image_path: "/abs/path/hero.png"
}], design_system: "tech_minimal"}
```

- `eyebrow`(선택): 제목 위 작은 대문자 라벨 (예 "INTRODUCING")
- `image_path` 절대경로는 자동 base64 변환되어 우측 절반에 표시
- 일러스트가 슬라이드 배경에 녹아드는 통합형(`slide-illustration-bleed`) — design_system의 일러스트 블렌드 처리 적용

## features — 기능 3열 그리드

```
[engines:slide_shadcn]{slides: [{
  layout: "features",
  title: "왜 IndieBiz OS인가",
  subtitle: "흩어진 도구를 하나로",
  features: [
    {title: "통합 신경계", description: "IBL로 모든 정보 소스 표준화", icon: "🧠"},
    {title: "자율 실행", description: "스케줄러 + 에이전트가 알아서", icon: "⚙️"},
    {title: "개인 데이터", description: "외부 클라우드 없이 NAS·로컬", icon: "🔒"}
  ]
}]}
```

- `features` 정확히 3개 권장 (그리드 `grid-cols-3` 고정)
- `icon`: 이모지 또는 비워두면 Lucide `star` 기본 아이콘
- 사용 시점: 제품 핵심 가치 3가지

## stats — 통계 4열 강조

```
[engines:slide_shadcn]{slides: [{
  layout: "stats",
  title: "숫자로 보는 성과",
  stats: [
    {value: "332→208", label: "IBL 액션 통합"},
    {value: "-37%", label: "시스템 프롬프트 비용"},
    {value: "95.3%", label: "해마 Top-5 정확도"},
    {value: "1h", label: "Pulse 주기"}
  ]
}], theme: "blue"}
```

- `stats` 정확히 4개 권장 (`grid-cols-4`)
- 슬라이드 전체가 primary 색 배경 — `theme`/`design_system`의 primary가 강조됨
- `value` 큰 폰트 + `label` 작은 폰트 (역피라미드)

## testimonial — 인용·후기

```
[engines:slide_shadcn]{slides: [{
  layout: "testimonial",
  quote: "원래는 도구마다 따로 열어서 썼는데, 이제는 그냥 '어시스턴트야'라고 부르면 끝납니다",
  author: "강국진",
  role: "IndieBiz OS 사용자",
  avatar_path: "/abs/path/avatar.png"
}]}
```

- `avatar_path`(선택): 절대경로 → 자동 base64. 없으면 author 첫 2글자 이니셜 원형
- `quote` 자동으로 따옴표 감쌈 — 본문에 따옴표 넣지 말 것
- 사용 시점: 사용자 후기, 한 줄 임팩트, 핵심 인용

## pricing — 가격표 3열

```
[engines:slide_shadcn]{slides: [{
  layout: "pricing",
  title: "요금",
  plans: [
    {
      name: "Free",
      description: "개인 사용",
      price: "0원",
      period: "/월",
      features: ["IBL 기본 액션", "1개 프로젝트", "커뮤니티 지원"],
      cta_text: "시작하기"
    },
    {
      name: "Pro",
      description: "프리랜서·1인 사업자",
      price: "29,000원",
      period: "/월",
      features: ["IBL 전체", "프로젝트 무제한", "스케줄러 자동화", "이메일 지원"],
      cta_text: "구독",
      highlighted: true
    },
    {
      name: "Team",
      description: "소규모 팀",
      price: "문의",
      features: ["Pro 전체", "멀티 에이전트", "전담 지원"],
      cta_text: "상담 신청"
    }
  ]
}]}
```

- `plans` 정확히 3개 (`grid-cols-3`)
- `highlighted: true` → "추천" 라벨 + primary 테두리 강조
- `period`(선택): 기본 `/월`. 없애려면 빈 문자열 `""`
- `description`(선택): 플랜 이름 아래 한 줄 설명
- 사용 시점: 가격·플랜 비교

## cta — Call-to-Action 배너

```
[engines:slide_shadcn]{slides: [{
  layout: "cta",
  title: "지금 시작하세요",
  subtitle: "30초 만에 첫 IBL 액션을 실행할 수 있습니다",
  cta_text: "무료로 시작"
}], theme: "purple"}
```

- 슬라이드 전체가 primary 색 배경 (stats와 비슷, 통계가 아닌 행동 유도)
- 데크 마지막 슬라이드로 자주 사용
- 사용 시점: 데모 마무리, 등록 유도, "다음 단계는?"

## content_image — 콘텐츠 + 이미지 (좌우 분할)

```
[engines:slide_shadcn]{slides: [{
  layout: "content_image",
  eyebrow: "How it works",
  title: "신경계가 먼저, 도구는 그 위에",
  content: "IBL은 모든 외부 데이터(주가·날씨·CCTV·이메일)를 통일된 문법으로 추상화합니다. AI는 도구가 아닌 *언어*를 학습합니다.",
  image_path: "/abs/path/diagram.png",
  image_position: "right",
  cta_text: "기술 문서 보기"
}]}
```

- `image_position`: `right`(기본) 또는 `left`. left면 이미지가 왼쪽, 텍스트가 오른쪽
- `eyebrow`(선택): 제목 위 작은 대문자 라벨
- hero_image와 차이: hero_image는 표지용 큰 제목, content_image는 본문용 일반 제목
- 사용 시점: 기능 상세 설명, 다이어그램 + 해설

## steps — 단계·타임라인

```
[engines:slide_shadcn]{slides: [{
  layout: "steps",
  title: "3단계로 시작",
  steps: [
    {title: "설치", description: "macOS/Windows 한 줄 명령어"},
    {title: "연결", description: "Gmail·NAS·홈페이지 등록"},
    {title: "지시", description: "자연어로 어시스턴트 호출"}
  ]
}]}
```

- `steps` 3~4개 권장 (개수에 따라 자동 분할, 사이에 화살표 자동)
- 번호는 `loop.index`로 자동 (`1`, `2`, `3` 원형 배지)
- 사용 시점: 온보딩, 워크플로우, 절차 안내

## custom — 자유 Tailwind HTML

기본 layout으로 안 되는 디자인은 `custom`으로 직접 HTML 작성.

```
[engines:slide_shadcn]{slides: [{
  layout: "custom",
  custom_html: '<div class="w-full h-full bg-black text-white flex items-center justify-center"><h1 class="text-9xl font-black">2026</h1></div>'
}]}
```

- `custom_html`은 그대로 슬라이드 영역(`1280x720`)에 삽입됨
- Tailwind CSS, shadcn 컴포넌트 클래스(`card`, `badge`, `btn` 등), Lucide 아이콘 모두 사용 가능
- `slides.md`의 "방법 2: tailwind 테마 + custom_html (권장)" 섹션의 디자인 가이드(글래스모피즘, 그라데이션, Google Fonts, Lucide, Lottie 등) 동일 적용
- 사용 시점: 카운트다운 화면, 임팩트 통계 한 글자, 브랜드 풀스크린 등 카탈로그에 없는 디자인

## 데크 구성 권장 (마케팅 자료)

10~15장 분량의 제품 소개 데크 예시 구성:

| # | layout | 역할 |
|---|---|---|
| 1 | `hero` 또는 `hero_image` | 표지 — 한 줄 가치 제안 |
| 2 | `content_image` | 문제 정의 (왜 필요한가) |
| 3 | `features` | 솔루션 — 핵심 3가지 |
| 4-6 | `content_image` ×3 | 각 기능 상세 |
| 7 | `stats` | 성과·실적 (숫자로) |
| 8 | `steps` | 도입 절차 |
| 9 | `testimonial` | 사용자 후기 |
| 10 | `pricing` | 가격 |
| 11 | `cta` | 다음 단계 |

`design_system`은 데크 전체에 한 번만 지정하면 모든 슬라이드에 적용된다.
