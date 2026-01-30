# Remotion 영상 제작 가이드

React/TSX 컴포넌트를 Remotion으로 렌더링하여 MP4 동영상을 생성하는 도구의 사용 가이드입니다.

## composition_code 작성 규칙

1. React 컴포넌트를 export default로 내보내야 합니다
2. Remotion의 useCurrentFrame, useVideoConfig, interpolate, spring 등을 import하여 사용
3. Tailwind CSS className 사용 가능 (권장). 동적 값만 style prop 사용
4. composition_code는 유효한 TSX여야 합니다

## Remotion API

- `useCurrentFrame()`: 현재 프레임 번호 (0부터 시작)
- `useVideoConfig()`: {fps, width, height, durationInFrames}
- `interpolate(frame, inputRange, outputRange, options)`: 프레임 보간
- `spring({frame, fps, config})`: 스프링 물리 애니메이션
- `Sequence`: 시간 기반 시퀀스 배치 (from, durationInFrames props)
- `AbsoluteFill`: 전체 화면 채우기
- `Img`: 이미지 컴포넌트

## 이미지 사용법 (asset_paths + staticFile)

asset_paths에 이미지 파일 경로를 전달하면 자동으로 public/ 폴더에 복사됩니다.
composition_code에서 staticFile('파일명')으로 참조하세요.

- asset_paths: ["/path/to/hero.png", "/path/to/logo.png"]
- composition_code에서: `<Img src={staticFile('hero.png')} />`
- 절대경로나 file:// URL은 동작하지 않습니다. 반드시 staticFile() 사용

## 나레이션 사용법 (narration_texts)

narration_texts에 텍스트 배열을 전달하면 edge-tts로 음성을 생성하여 동영상에 믹싱합니다.

### ⚠️ 나레이션-씬 동기화 (필수! 반드시 지켜야 합니다)

narration_texts를 사용할 때는 **반드시** `props.narrationTimings`를 사용하여 씬 길이를 결정해야 합니다.
나레이션마다 길이가 다르므로 **하드코딩된 SCENE_DURATION을 절대 사용하지 마세요!**

나레이션이 있을 때 props에 자동으로 narrationTimings 배열이 주입됩니다.

**❌ 절대 하면 안 되는 코드 (영상-나레이션 불일치 발생):**
```tsx
// 이렇게 하면 안 됩니다! 나레이션 길이와 영상 길이가 맞지 않습니다!
const SCENE_DURATION = 240;
<Sequence from={i * SCENE_DURATION} durationInFrames={SCENE_DURATION}>
```

**✅ 반드시 이렇게 해야 합니다:**
```tsx
type Timing = {index: number; startFrame: number; durationInFrames: number; durationSec: number; text: string};

export default function MyVideo(props: {narrationTimings?: Timing[]}) {
  const timings = props.narrationTimings || [
    {index: 0, startFrame: 0, durationInFrames: 90, durationSec: 3, text: ''},
    {index: 1, startFrame: 90, durationInFrames: 90, durationSec: 3, text: ''},
  ];
  return (
    <AbsoluteFill>
      {timings.map((t, i) => (
        <Sequence key={i} from={t.startFrame} durationInFrames={t.durationInFrames}>
          <Scene index={i} timing={t} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
}
```

**핵심 규칙**: narration_texts가 있으면 → export default 함수에 `props` 파라미터 필수 → `props.narrationTimings`로 Sequence의 `from`과 `durationInFrames` 설정 → 하드코딩된 씬 길이 사용 금지

추가 props: totalNarrationFrames, totalNarrationDuration

---

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

## 배경 기법
- Tailwind 그라데이션: `bg-gradient-to-br from-indigo-900 via-blue-900 to-cyan-900`
- 애니메이션 그라데이션 (동적): `style={{background: \`linear-gradient(${angle}deg, ...)\`}}`
- 방사형 그라데이션: `style={{background: \`radial-gradient(circle at ${x}% ${y}%, ...)\`}}`
- 여러 겹 배경 레이어: position: absolute로 반투명 오버레이 겹치기

## ⚠️ 텍스트 넘침 방지 (필수)
텍스트가 화면 밖으로 벗어나면 영상 품질이 크게 떨어집니다. 반드시 아래 규칙을 지키세요.

**한 줄 텍스트 길이 제한** (1920x1080 기준, padding 양쪽 60px → 실제 1800px):
- 한글 기준: text-7xl(72px)일 때 **한 줄 최대 약 24자**, text-5xl(48px)일 때 **약 36자**
- 텍스트가 길면 줄바꿈(`<br/>`)하거나 폰트 크기를 줄이세요

**필수 스타일 적용**:
```tsx
// 텍스트 컨테이너에 반드시 적용
<div className="max-w-full" style={{wordBreak: 'keep-all', overflowWrap: 'break-word'}}>
  <h1 className="text-6xl font-bold leading-tight">제목 텍스트</h1>
</div>
```

**텍스트 넘침 확인 체크**:
- 한글 제목이 24자 이상이면 text-5xl 이하로 줄이기
- 부제목/설명이 50자 이상이면 두 줄로 분리
- 리스트 항목은 한 줄당 40자 이내
- `whiteSpace: 'nowrap'`은 짧은 라벨에만 사용 (긴 텍스트에 절대 금지)

## 텍스트/타이포그래피
- Tailwind 텍스트: `text-7xl font-black text-white tracking-tight`
- 글자별 순차 등장: 배열 분해 + delay
- 타이핑 효과: `text.slice(0, visibleChars)`
- 글로우: `drop-shadow-[0_0_20px_rgba(0,232,255,0.5)]`

```tsx
// 글자별 순차 등장
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
// spring 바운스
const scale = spring({frame, fps, config: {damping: 8, mass: 0.5, stiffness: 100}});

// clipPath 와이프 전환
const wipe = interpolate(frame, [0, 20], [0, 100], {extrapolateRight: 'clamp'});
<div style={{clipPath: `inset(0 ${100 - wipe}% 0 0)`}}>새 씬</div>
```

## 도형/장식 요소

```tsx
// 떠다니는 파티클
const particles = Array.from({length: 8}, (_, i) => ({
  x: (i * 160) % 1280,
  speed: 0.5 + (i % 3) * 0.3,
  size: ['w-3 h-3','w-4 h-4','w-5 h-5','w-6 h-6'][i % 4],
  color: ['bg-rose-400','bg-teal-400','bg-sky-400','bg-orange-400'][i % 4]
}));

// 프로그레스 바
const progress = interpolate(frame, [0, 60], [0, 100], {extrapolateRight: 'clamp'});
<div className="w-full h-2 bg-white/10 rounded-full overflow-hidden">
  <div className="h-full bg-gradient-to-r from-cyan-400 to-purple-400 rounded-full" style={{width: `${progress}%`}} />
</div>
```

## 레이아웃

```tsx
// 글래스모피즘 카드
<div className="bg-white/10 backdrop-blur-xl rounded-3xl p-12 border border-white/20 shadow-2xl max-w-2xl">
  <h2 className="text-3xl font-bold text-white mb-4">카드 제목</h2>
  <p className="text-lg text-white/70 leading-relaxed">카드 내용</p>
</div>

// 카메라 줌인 효과
const zoom = interpolate(frame, [0, 60], [1, 1.3], {extrapolateRight: 'clamp'});
<div style={{transform: `scale(${zoom}) translateX(${panX}px)`}}>콘텐츠</div>
```

## Google Fonts (커스텀 폰트)

```tsx
import {loadFont} from '@remotion/google-fonts/NotoSansKR';
const {fontFamily} = loadFont();

import {loadFont as loadBlackHan} from '@remotion/google-fonts/BlackHanSans';
const {fontFamily: titleFont} = loadBlackHan();

<h1 style={{fontFamily: titleFont}}>굵은 제목</h1>
<p style={{fontFamily}}>본문 텍스트</p>
```

### 추천 폰트 조합
| 조합 | 제목 폰트 | 본문 폰트 |
|------|-----------|-----------|
| 임팩트 | BlackHanSans | NotoSansKR |
| 친근함 | DoHyeon / JuaFont | NotoSansKR |
| 모던 | GothicA1(전체) | - |
| 따뜻함 | Sunflower | NotoSansKR |
| 영문 프리미엄 | Playfair Display | Inter |
| 영문 모던 | Montserrat | Poppins |

폰트 import 규칙: 이름에서 공백/하이픈 제거 (`Noto Sans KR` → `NotoSansKR`)

## Lottie 애니메이션

```tsx
import {Lottie, LottieAnimationData} from '@remotion/lottie';
import {useEffect, useState} from 'react';

const [animData, setAnimData] = useState<LottieAnimationData | null>(null);
useEffect(() => {
  fetch('https://assets5.lottiefiles.com/packages/lf20_jcikwtux.json')
    .then(r => r.json()).then(setAnimData);
}, []);
if (!animData) return null;
return <Lottie animationData={animData} />;
```

LottieFiles.com에서 무료 JSON 애니메이션 URL을 찾아 사용하세요.

---

## 핵심 원칙 체크리스트

1. **배경**: 항상 그라데이션 또는 동적 그라데이션 사용 (단색 금지)
2. **텍스트 등장**: 단순 페이드 외에 슬라이드/스케일/타이핑/글자별 중 택1
3. **장식 요소**: 도형, 라인, SVG, 파티클, 프로그레스바 중 최소 1개
4. **씬 전환**: 이전 씬 fadeOut + 다음 씬 슬라이드/와이프/줌 인 조합
5. **색상**: 씬마다 다른 컬러 팔레트, 최소 3색 이상
6. **카드/컨테이너**: 글래스모피즘 또는 그라데이션 배경 카드 활용
7. **Tailwind 우선**: 정적 스타일은 className, 동적 애니메이션만 style prop
8. **커스텀 폰트**: 제목에 디자인 폰트, 본문에 NotoSansKR 사용
9. **텍스트 넘침 없음**: 모든 텍스트가 화면 안에 완전히 표시됨 (한글 제목 24자, 본문 40자 이내)
10. **나레이션 동기화**: narration_texts 사용 시 반드시 `props.narrationTimings`로 Sequence 타이밍 결정 (하드코딩 금지)
