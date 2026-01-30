# Remotion 시각 기법 가이드

Remotion은 React + Tailwind CSS + Google Fonts + Lottie를 지원합니다. 단조로운 텍스트만 표시하지 말고 아래 기법을 적극 조합하세요.

## Tailwind CSS 사용법 (핵심!)
Tailwind CSS가 설치되어 있으므로 className으로 스타일링하세요.
동적 값(frame 기반 애니메이션)만 style prop을 사용하고, 나머지는 Tailwind className으로 처리합니다.

```tsx
// Tailwind + 동적 style 조합 (권장 패턴)
<AbsoluteFill className="bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center">
  <div style={{opacity, transform: `scale(${scale})`}}>
    <h1 className="text-8xl font-black text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-400">
      제목
    </h1>
    <div className="w-24 h-1 bg-cyan-400 mx-auto mt-6 rounded-full" />
  </div>
</AbsoluteFill>
```

### 자주 쓰는 Tailwind 클래스 조합
- 배경: `bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900`
- 글래스모피즘: `bg-white/10 backdrop-blur-xl rounded-3xl border border-white/20 shadow-2xl`
- 텍스트 그라데이션: `text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-400`
- 네온 글로우: `drop-shadow-[0_0_20px_rgba(0,232,255,0.5)]`
- 카드: `bg-white/5 rounded-2xl p-8 border border-white/10 shadow-lg`
- 뱃지: `px-4 py-1 rounded-full bg-cyan-500/20 text-cyan-300 text-sm font-medium`
- 구분선: `w-16 h-1 bg-gradient-to-r from-cyan-400 to-purple-400 rounded-full`
- 그리드: `grid grid-cols-2 gap-6`
- 아이콘 원형 배경: `w-12 h-12 rounded-full bg-cyan-500/20 flex items-center justify-center`

### 동적 값에만 style 사용
```tsx
// frame 기반 값 → style
const opacity = interpolate(frame, [0, 30], [0, 1], {extrapolateRight: 'clamp'});
const translateY = interpolate(frame, [0, 20], [40, 0], {extrapolateRight: 'clamp'});

// 정적 레이아웃/색상 → className
<div
  className="text-4xl font-bold text-white text-center"
  style={{opacity, transform: `translateY(${translateY}px)`}}
>
  텍스트
</div>
```

## 배경 기법
- Tailwind 그라데이션: `bg-gradient-to-br from-indigo-900 via-blue-900 to-cyan-900`
- 애니메이션 그라데이션 (동적): `style={{background: `linear-gradient(${angle}deg, ...)`}}`
- 방사형 그라데이션: `style={{background: `radial-gradient(circle at ${x}% ${y}%, ...)`}}`
- 여러 겹 배경 레이어: position: absolute로 반투명 오버레이 겹치기

```tsx
// 애니메이션 그라데이션 배경 + Tailwind 레이아웃
const angle = interpolate(frame, [0, 90], [0, 360]);
<AbsoluteFill
  className="flex items-center justify-center"
  style={{background: `linear-gradient(${angle}deg, #1a1a2e, #16213e, #0f3460)`}}
/>
```

## 텍스트/타이포그래피
- Tailwind 텍스트: `text-7xl font-black text-white tracking-tight`
- 텍스트 그라데이션: `text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-blue-400`
- 글자별 순차 등장: 배열 분해 + delay
- 타이핑 효과: `text.slice(0, visibleChars)`
- 글로우: `drop-shadow-[0_0_20px_rgba(0,232,255,0.5)]`

```tsx
// 글자별 순차 등장 + Tailwind
const text = "안녕하세요";
const chars = text.split('');
<div className="flex">
  {chars.map((ch, i) => {
    const delay = i * 3;
    const opacity = interpolate(frame, [delay, delay + 10], [0, 1], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    const y = interpolate(frame, [delay, delay + 10], [30, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
    return <span key={i} className="text-7xl font-bold text-white" style={{opacity, transform: `translateY(${y}px)`}}>{ch}</span>;
  })}
</div>
```

## 모션/전환
- `spring({frame, fps, config: {damping: 8, mass: 0.5}})` 바운스 등장
- 다방향 슬라이드: translateX/Y
- 회전 + 스케일: `transform: rotate(${r}deg) scale(${s})`
- 씬 전환: 페이드, 와이프(clipPath), 줌
- stagger: 여러 요소가 시간차로 등장

```tsx
// spring 바운스 + Tailwind
const scale = spring({frame, fps, config: {damping: 8, mass: 0.5, stiffness: 100}});
<div className="text-center" style={{transform: `scale(${scale})`}}>
  <h1 className="text-6xl font-bold text-white">바운스!</h1>
</div>

// clipPath 와이프 전환
const wipe = interpolate(frame, [0, 20], [0, 100], {extrapolateRight: 'clamp'});
<div style={{clipPath: `inset(0 ${100 - wipe}% 0 0)`}}>새 씬</div>
```

## 도형/장식 요소
- Tailwind 원형: `w-4 h-4 rounded-full bg-cyan-400`
- 인라인 SVG: `<svg>` 로 원, 별, 화살표 직접 그리기
- 떠다니는 장식: 여러 작은 도형이 각기 다른 속도/방향으로 이동
- 프로그레스 바, 구분선, 뱃지

```tsx
// 떠다니는 파티클 + Tailwind
const particles = Array.from({length: 8}, (_, i) => ({
  x: (i * 160) % 1280,
  speed: 0.5 + (i % 3) * 0.3,
  size: ['w-3 h-3','w-4 h-4','w-5 h-5','w-6 h-6'][i % 4],
  color: ['bg-rose-400','bg-teal-400','bg-sky-400','bg-orange-400'][i % 4]
}));
<>
  {particles.map((p, i) => {
    const y = (frame * p.speed + i * 100) % 800;
    return <div key={i} className={`absolute rounded-full ${p.size} ${p.color} opacity-40`}
      style={{left: p.x, top: y}} />;
  })}
</>

// 프로그레스 바
const progress = interpolate(frame, [0, 60], [0, 100], {extrapolateRight: 'clamp'});
<div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
  <div className="h-full bg-gradient-to-r from-cyan-400 to-purple-400 rounded-full" style={{width: `${progress}%`}} />
</div>
```

## 레이아웃
- Tailwind grid: `grid grid-cols-2 gap-6`
- Tailwind flex: `flex items-center justify-between gap-4`
- 글래스모피즘 카드: `bg-white/10 backdrop-blur-xl rounded-3xl border border-white/20`
- 카메라 줌: 전체 래퍼에 scale/translate
- 레이어링: absolute positioning

```tsx
// 글래스모피즘 카드 + Tailwind
<div className="bg-white/10 backdrop-blur-xl rounded-3xl p-12 border border-white/20 shadow-2xl max-w-2xl">
  <h2 className="text-3xl font-bold text-white mb-4">카드 제목</h2>
  <p className="text-lg text-white/70 leading-relaxed">카드 내용입니다.</p>
  <div className="flex gap-3 mt-6">
    <span className="px-4 py-1 rounded-full bg-cyan-500/20 text-cyan-300 text-sm">태그1</span>
    <span className="px-4 py-1 rounded-full bg-purple-500/20 text-purple-300 text-sm">태그2</span>
  </div>
</div>

// 2컬럼 그리드 레이아웃
<div className="grid grid-cols-2 gap-8 p-16 w-full">
  <div className="bg-white/5 rounded-2xl p-8 border border-white/10">항목 1</div>
  <div className="bg-white/5 rounded-2xl p-8 border border-white/10">항목 2</div>
  <div className="bg-white/5 rounded-2xl p-8 border border-white/10">항목 3</div>
  <div className="bg-white/5 rounded-2xl p-8 border border-white/10">항목 4</div>
</div>

// 카메라 줌인 효과
const zoom = interpolate(frame, [0, 60], [1, 1.3], {extrapolateRight: 'clamp'});
const panX = interpolate(frame, [0, 60], [0, -50], {extrapolateRight: 'clamp'});
<div style={{transform: `scale(${zoom}) translateX(${panX}px)`}}>
  전체 씬 콘텐츠
</div>
```

## Google Fonts (커스텀 폰트)
`@remotion/google-fonts`가 설치되어 있습니다. 기본 시스템 폰트 대신 디자인 폰트를 적극 활용하세요.

```tsx
// 한국어 폰트 로드
import {loadFont} from '@remotion/google-fonts/NotoSansKR';
const {fontFamily} = loadFont(); // 'Noto Sans KR'

// 제목용 굵은 폰트
import {loadFont as loadBlackHan} from '@remotion/google-fonts/BlackHanSans';
const {fontFamily: titleFont} = loadBlackHan();

// 사용: style에 fontFamily 지정
<h1 className="text-8xl font-black text-white" style={{fontFamily: titleFont}}>
  굵은 제목
</h1>
<p className="text-xl text-white/70" style={{fontFamily}}>
  본문 텍스트
</p>
```

### 추천 폰트 조합
- **제목 + 본문**: BlackHanSans(제목) + NotoSansKR(본문)
- **모던**: GothicA1(전체) — 깔끔한 고딕
- **따뜻한 느낌**: Sunflower(제목) + NotoSansKR(본문)
- **캐주얼**: DoHyeon(제목) 또는 JuaFont(제목)
- **영문 프리미엄**: Playfair Display(제목) + Inter(본문)
- **영문 모던**: Montserrat(제목) + Poppins(본문)

### 폰트 import 규칙
- 폰트 이름의 공백과 하이픈을 제거: `Noto Sans KR` → `NotoSansKR`
- 각 폰트마다 별도 import 필요
- `loadFont()` 반환값의 `fontFamily`를 style prop에 전달

## Lottie 애니메이션
`@remotion/lottie`가 설치되어 있습니다. JSON URL에서 벡터 애니메이션을 로드하여 영상을 풍부하게 만드세요.

```tsx
import {Lottie, LottieAnimationData} from '@remotion/lottie';
import {useEffect, useState} from 'react';
import {useCurrentFrame, useVideoConfig, interpolate} from 'remotion';

// Lottie 애니메이션 로드 + 재생
const MyLottieScene = () => {
  const frame = useCurrentFrame();
  const {durationInFrames} = useVideoConfig();
  const [animData, setAnimData] = useState<LottieAnimationData | null>(null);

  useEffect(() => {
    fetch('https://assets5.lottiefiles.com/packages/lf20_jcikwtux.json')
      .then(r => r.json())
      .then(setAnimData);
  }, []);

  if (!animData) return null;

  return (
    <div className="w-64 h-64">
      <Lottie animationData={animData} />
    </div>
  );
};
```

### Lottie 활용 팁
- **LottieFiles.com**에서 무료 JSON 애니메이션 URL을 찾아 사용
- 로딩/스피너, 체크마크, 축하, 화살표, 아이콘 등 다양한 모션 그래픽 가능
- `<Lottie>` 컴포넌트를 Tailwind 컨테이너로 감싸서 크기/위치 조절
- 주의: 네트워크 fetch가 필요하므로 렌더링 시 인터넷 연결 필요

## 핵심 원칙: 매 씬에서 반드시 다음을 지킬 것

1. **배경**: 항상 `bg-gradient-to-*` 또는 동적 그라데이션 사용 (단색 금지)
2. **텍스트 등장**: 단순 페이드 외에 슬라이드/스케일/타이핑/글자별 중 택1
3. **장식 요소**: 도형, 라인, SVG, 파티클, 프로그레스바 중 최소 1개 추가
4. **씬 전환**: 이전 씬 fadeOut + 다음 씬 슬라이드/와이프/줌 인 조합
5. **색상**: 씬마다 다른 컬러 팔레트, 최소 3색 이상
6. **카드/컨테이너**: `bg-white/10 backdrop-blur rounded-2xl border border-white/20` 활용
7. **Tailwind 우선**: 정적 스타일은 className, 동적 애니메이션만 style prop
8. **커스텀 폰트**: 제목에는 BlackHanSans/DoHyeon 등 디자인 폰트, 본문에는 NotoSansKR 사용
