# HTML 영상 제작 가이드

각 씬을 완전한 HTML 문서로 작성하면 Playwright가 프레임을 캡처하여 MP4 동영상을 생성합니다.

## 파이프라인
HTML(씬별) → Playwright 프레임 캡처 → FFmpeg MP4 인코딩 → 나레이션/BGM 합성

## 필수 규칙

### 1. 씬 분리 (가장 중요)
- **각 씬(scene)은 반드시 독립된 HTML 문서**여야 합니다.

```json
{
  "scenes": [
    {"html": "<!DOCTYPE html><html>...<body>인트로</body></html>", "duration": 5},
    {"html": "<!DOCTYPE html><html>...<body>기능 소개</body></html>", "duration": 7},
    {"html": "<!DOCTYPE html><html>...<body>마무리</body></html>", "duration": 5}
  ]
}
```

### 2. HTML 레이아웃 (정렬 깨짐 방지)

**body 고정 크기** (필수):
```css
body { width: 1280px; height: 720px; overflow: hidden; margin: 0; padding: 0; }
```
Tailwind의 `w-full h-full`만으로는 부족합니다. 반드시 CSS에서 px 단위로 고정하세요.

**통일된 레이아웃 패턴** (권장):
```html
<div style="width:1280px; height:720px; display:flex; flex-direction:column; align-items:center; justify-content:center; padding:60px; box-sizing:border-box;">
  ... 콘텐츠 ...
</div>
```
또는 Tailwind:
```html
<div class="w-[1280px] h-[720px] flex flex-col items-center justify-center p-[60px] box-border">
```

### 3. 콘텐츠 크기 제한
- 모든 콘텐츠가 1280x720px 영역 안에 들어와야 합니다.
- padding이 큰 경우(p-20 = 80px) 실제 콘텐츠 영역은 1120x560px
- `position:absolute` 대신 flex/grid를 사용하세요.

### ⚠️ 텍스트 넘침 방지 (필수)
텍스트가 화면 밖으로 벗어나는 것은 영상 품질을 크게 떨어뜨립니다. 반드시 아래 규칙을 지키세요.

**한 줄 텍스트 길이 제한**:
- 1280px 폭에서 padding 양쪽 60px을 빼면 실제 텍스트 영역은 **최대 1160px**
- 한글 기준: text-6xl(60px)일 때 **한 줄 최대 약 18자**, text-4xl(36px)일 때 **약 30자**
- 텍스트가 길면 반드시 줄바꿈하거나 폰트 크기를 줄이세요

**필수 CSS 적용**:
```css
/* 텍스트 컨테이너에 반드시 적용 */
.text-container {
  max-width: 100%;
  word-break: keep-all;      /* 한글 단어 단위 줄바꿈 */
  overflow-wrap: break-word;  /* 긴 단어 강제 줄바꿈 */
}
```

**Tailwind 사용 시**:
```html
<div class="w-full max-w-full break-keep">
  <h1 class="text-5xl font-bold leading-tight">여기에 제목 텍스트</h1>
</div>
```

**텍스트 넘침 확인 체크**:
- 한글 제목이 18자 이상이면 text-5xl 이하로 줄이기
- 부제목/설명이 40자 이상이면 두 줄로 분리
- 리스트 항목은 한 줄당 35자 이내
- `white-space: nowrap`은 짧은 라벨에만 사용 (긴 텍스트에 절대 금지)

### 4. 폰트 크기 기준
| 용도 | Tailwind | px |
|------|----------|----|
| 메인 제목 | text-6xl ~ text-7xl | 48~72px |
| 부제목/설명 | text-2xl ~ text-3xl | 24~30px |
| 본문/라벨 | text-lg ~ text-xl | 18~20px |

- text-8xl(96px)은 짧은 텍스트만 가능
- 한국어 텍스트는 영어보다 공간을 더 차지하므로 한 단계 작은 크기를 사용

---

## 자동 포함 리소스 (불완전한 HTML일 때)
불완전한 HTML(body만 있는 경우)은 아래 리소스가 자동 포함된 문서로 래핑됩니다:
- **Tailwind CSS** (CDN)
- **Google Fonts**: Noto Sans KR, Black Han Sans, Do Hyeon, Gothic A1, Sunflower, Jua, Inter, Montserrat, Playfair Display, Poppins
- **Animate.css** (CDN)
- **Lucide Icons** (CDN)
- **GSAP 3.12.2** (CDN)
- **Lottie Player** (CDN)

완전한 HTML(`<!DOCTYPE html>`로 시작)을 직접 작성할 때는 필요한 CDN을 직접 `<head>`에 추가하세요.

---

## 시각 기법 가이드

### 배경
- Tailwind 그라데이션: `bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900`
- 방사형 그라데이션: `radial-gradient(circle at 30% 40%, #1a1a2e, #16213e)`
- 여러 겹 배경 레이어: absolute 포지셔닝으로 반투명 오버레이 겹치기
- **단색 배경 금지** — 항상 그라데이션 또는 다층 배경 사용

### 글래스모피즘 카드
```html
<div class="bg-white/10 backdrop-blur-xl rounded-3xl p-12 border border-white/20 shadow-2xl">
  <h2 class="text-3xl font-bold text-white mb-4">카드 제목</h2>
  <p class="text-lg text-white/70">내용</p>
</div>
```

### 텍스트 효과
- 텍스트 그라데이션: `text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-400`
- 네온 글로우: `drop-shadow-[0_0_20px_rgba(0,232,255,0.5)]`
- 뱃지: `px-4 py-1 rounded-full bg-cyan-500/20 text-cyan-300 text-sm font-medium`

### 레이아웃 패턴
- 그리드: `grid grid-cols-2 gap-6`
- 아이콘 원형 배경: `w-12 h-12 rounded-full bg-cyan-500/20 flex items-center justify-center`
- 구분선: `w-16 h-1 bg-gradient-to-r from-cyan-400 to-purple-400 rounded-full`

---

## GSAP 애니메이션 (권장 — 프로급 모션)

GSAP(GreenSock Animation Platform)은 웹에서 가장 강력한 애니메이션 라이브러리입니다.
CSS @keyframes보다 훨씬 세밀한 시퀀스 제어가 가능합니다.

### 기본 타임라인 패턴
```html
<script>
const tl = gsap.timeline();
tl.from('.title', {y: 50, opacity: 0, duration: 0.8, ease: 'power3.out'})
  .from('.subtitle', {y: 30, opacity: 0, duration: 0.6, ease: 'power2.out'}, '-=0.3')
  .from('.card', {scale: 0.8, opacity: 0, duration: 0.5, stagger: 0.15, ease: 'back.out(1.7)'}, '-=0.2')
  .from('.footer', {y: 20, opacity: 0, duration: 0.4}, '-=0.1');
</script>
```

### 주요 기법

**순차 등장 (stagger)**:
```javascript
gsap.from('.item', {
  y: 40, opacity: 0, duration: 0.6,
  stagger: 0.15,  // 각 요소 간 0.15초 간격
  ease: 'power3.out'
});
```

**카운트업 숫자 애니메이션**:
```javascript
gsap.to('.number', {
  textContent: 1000,
  duration: 2,
  snap: {textContent: 1},  // 정수로 스냅
  ease: 'power2.out'
});
```

**텍스트 글자별 등장**:
```javascript
// 먼저 각 글자를 span으로 분리
const text = document.querySelector('.text');
text.innerHTML = text.textContent.split('').map(ch => `<span class="char">${ch}</span>`).join('');

gsap.from('.char', {
  opacity: 0, y: 20,
  duration: 0.4,
  stagger: 0.05,
  ease: 'back.out(1.7)'
});
```

**진행 바 애니메이션**:
```javascript
gsap.from('.progress-fill', {
  width: 0,
  duration: 1.5,
  ease: 'power2.out',
  delay: 0.5
});
```

**SVG 선 그리기 (drawSVG 효과)**:
```javascript
const path = document.querySelector('.line-path');
const length = path.getTotalLength();
gsap.fromTo(path,
  {strokeDasharray: length, strokeDashoffset: length},
  {strokeDashoffset: 0, duration: 2, ease: 'power2.inOut'}
);
```

**3D 카드 플립**:
```javascript
gsap.from('.card', {
  rotationY: 90, opacity: 0,
  duration: 0.8,
  stagger: 0.2,
  ease: 'power3.out',
  transformPerspective: 800
});
```

### 이징(Easing) 레퍼런스
| 이징 | 효과 | 용도 |
|------|------|------|
| `power2.out` | 자연스러운 감속 | 일반 등장 |
| `power3.out` | 강한 감속 | 타이틀, 큰 요소 |
| `back.out(1.7)` | 튀어나왔다 안착 | 카드, 버튼, 아이콘 |
| `elastic.out(1, 0.5)` | 탄성/진동 | 강조 요소 |
| `expo.out` | 극적인 감속 | 드라마틱 등장 |
| `power2.inOut` | 부드러운 가감속 | 이동, 전환 |
| `none` (linear) | 일정 속도 | 진행 바, 회전 |
| `bounce.out` | 바운스 | 재미있는 등장 |

### 타임라인 시간 오프셋
```javascript
const tl = gsap.timeline();
tl.from('.a', {opacity: 0, duration: 1})        // 0초에 시작
  .from('.b', {opacity: 0, duration: 1})        // .a 끝난 후 시작 (1초)
  .from('.c', {opacity: 0, duration: 1}, '-=0.5') // .b와 0.5초 겹침
  .from('.d', {opacity: 0, duration: 1}, '+=0.3') // .c 끝나고 0.3초 후
  .from('.e', {opacity: 0, duration: 1}, 2);      // 절대 시간 2초에 시작
```

### ⚠️ 주의사항
- GSAP 애니메이션 총 시간이 씬 duration보다 **짧아야** 합니다.
  - 예: 애니메이션 3초 → duration: 5 (여유 2초)
- Playwright가 프레임을 캡처하는 방식이므로 requestAnimationFrame 기반 애니메이션이 모두 지원됩니다.
- `gsap.set()`으로 초기 상태를 설정하고 `gsap.to()`로 애니메이션하는 패턴도 유용합니다.

---

## Animate.css 사용법
간단한 애니메이션은 Animate.css 클래스만으로도 가능합니다:
```html
<h1 class="animate__animated animate__fadeInUp">제목</h1>
<p class="animate__animated animate__fadeInUp animate__delay-1s">부제목</p>
```

---

## Lottie 애니메이션 사용법
벡터 애니메이션을 로드하여 풍부한 모션 그래픽을 추가합니다:
```html
<lottie-player
  src="https://lottie.host/.../animation.json"
  background="transparent"
  speed="1"
  style="width:200px;height:200px"
  loop autoplay>
</lottie-player>
```
- LottieFiles.com에서 무료 JSON 애니메이션 URL을 찾아 사용
- 로딩/스피너, 체크마크, 축하, 화살표 등 다양한 모션 그래픽 가능

---

## Google Fonts 추천 조합
| 조합 | 제목 폰트 | 본문 폰트 |
|------|-----------|-----------|
| 임팩트 | Black Han Sans | Noto Sans KR |
| 친근함 | Do Hyeon / Jua | Noto Sans KR |
| 모던 | Gothic A1 (전체) | - |
| 따뜻함 | Sunflower | Noto Sans KR |
| 영문 프리미엄 | Playfair Display | Inter |
| 영문 모던 | Montserrat | Poppins |

```html
<!-- 제목 -->
<h1 style="font-family: 'Black Han Sans'">굵은 제목</h1>
<!-- 본문 -->
<p style="font-family: 'Noto Sans KR'">본문 텍스트</p>
```

---

## 핵심 원칙 체크리스트
매 씬을 작성할 때 다음을 확인하세요:

1. ✅ **배경**: 그라데이션 또는 다층 배경 사용 (단색 금지)
2. ✅ **텍스트 등장**: 단순 표시가 아닌 GSAP/CSS 애니메이션 적용
3. ✅ **장식 요소**: 도형, 라인, SVG, 파티클, 프로그레스바 중 최소 1개
4. ✅ **색상**: 씬마다 다른 컬러 팔레트, 최소 3색 이상
5. ✅ **카드/컨테이너**: 글래스모피즘 또는 그라데이션 배경의 카드 활용
6. ✅ **레이아웃 고정**: body에 1280x720px 고정, overflow:hidden
7. ✅ **커스텀 폰트**: 제목에 디자인 폰트, 본문에 Noto Sans KR
8. ✅ **Duration 여유**: 애니메이션 시간 + 2초 이상
9. ✅ **텍스트 넘침 없음**: 모든 텍스트가 화면 안에 완전히 표시됨 (한글 제목 18자, 본문 35자 이내)
