# 슬라이드 제작 가이드

HTML/Playwright 기반으로 1280x720px 슬라이드 이미지(PNG)를 생성하는 도구입니다.
기본 제공 테마를 사용하거나, `tailwind` 테마 + `custom_html`로 자유롭게 디자인할 수 있습니다.

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
