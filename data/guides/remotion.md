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

### ⚠️ 필수: 모든 이미지 사용 규칙

**asset_paths에 제공된 모든 이미지는 반드시 동영상에 포함되어야 합니다!**

```tsx
// ❌ 잘못된 예: 이미지 5개 중 3개만 사용
// asset_paths: [img1.png, img2.png, img3.png, img4.png, img5.png]
const images = ['img1.png', 'img2.png', 'img3.png']; // 2개 누락!

// ✅ 올바른 예: 모든 이미지 사용
const images = ['img1.png', 'img2.png', 'img3.png', 'img4.png', 'img5.png'];
```

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

// ⚠️ 핵심: Sequence 내부에서 useCurrentFrame()은 항상 0부터 시작합니다!
// Sequence가 자동으로 프레임을 리셋하므로, Scene 안에서 timing.startFrame을 빼면 안 됩니다!
const Scene = ({title, durationInFrames}: {title: string; durationInFrames: number}) => {
  const frame = useCurrentFrame(); // Sequence 내부이므로 0부터 시작!
  // ❌ 절대 하지 마세요: const relativeFrame = frame - timing.startFrame;
  // ✅ 그냥 frame을 바로 사용하세요 (이미 0부터 시작)
  const opacity = interpolate(frame, [0, 15, durationInFrames - 15, durationInFrames], [0, 1, 1, 0], {extrapolateLeft: 'clamp', extrapolateRight: 'clamp'});
  return (
    <AbsoluteFill style={{opacity}}>
      <h1>{title}</h1>
    </AbsoluteFill>
  );
};

export default function MyVideo(props: {narrationTimings?: Timing[]}) {
  const timings = props.narrationTimings || [
    {index: 0, startFrame: 0, durationInFrames: 90, durationSec: 3, text: ''},
    {index: 1, startFrame: 90, durationInFrames: 90, durationSec: 3, text: ''},
  ];
  return (
    <AbsoluteFill>
      {timings.map((t, i) => (
        <Sequence key={i} from={t.startFrame} durationInFrames={t.durationInFrames}>
          {/* Scene에는 durationInFrames만 전달. startFrame은 Sequence가 처리함 */}
          <Scene title={`씬 ${i+1}`} durationInFrames={t.durationInFrames} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
}
```

**⚠️ 가장 흔한 실수 (검은 화면의 원인):**
```tsx
// ❌ 이 코드는 두 번째 씬부터 검은 화면이 됩니다!
const Scene = ({timing}) => {
  const frame = useCurrentFrame();
  const relativeFrame = frame - timing.startFrame; // ← 이미 0부터인데 또 빼면 음수!
  const opacity = interpolate(relativeFrame, [0, 15, ...], [0, 1, ...]);
  // 두 번째 씬: frame=0, startFrame=300 → relativeFrame=-300 → opacity=0 → 검은 화면!
};
```
Sequence 내부의 useCurrentFrame()은 이미 **해당 Sequence의 시작 프레임 기준 0부터** 카운트됩니다.
Scene 컴포넌트에서 `timing.startFrame`을 빼는 이중 차감을 하면 안 됩니다!

**핵심 규칙**: narration_texts가 있으면 → export default 함수에 `props` 파라미터 필수 → `props.narrationTimings`로 Sequence의 `from`과 `durationInFrames` 설정 → 하드코딩된 씬 길이 사용 금지 → **Scene 내부에서 startFrame을 빼지 말 것**

추가 props: totalNarrationFrames, totalNarrationDuration

---

## ⚠️ 이미지-나레이션-씬 1:1:1 매칭 (필수!)

이미지와 나레이션을 함께 사용할 때 **반드시 개수를 맞춰야** 합니다.

### 황금 규칙: 이미지 N개 = 나레이션 N개 = 씬 N개

```
이미지 5개 생성 → 나레이션 5개 작성 → 씬 5개 생성
각 씬[i]에서: 이미지[i] 표시 + 나레이션[i] 재생
```

### ❌ 흔한 실수들

```tsx
// 실수 1: 이미지 5개인데 나레이션 3개
asset_paths: [img1, img2, img3, img4, img5]  // 5개
narration_texts: [text1, text2, text3]        // 3개 → 불일치!

// 실수 2: 이미지 5개인데 씬 3개만 생성
const scenes = images.slice(0, 3);  // 2개 누락!

// 실수 3: 나레이션 타이밍과 이미지 순서 불일치
// 나레이션 1이 재생될 때 이미지 3이 표시됨 → 내용 불일치
```

### ✅ 올바른 패턴

```tsx
// 이미지와 나레이션 개수가 같다고 가정
const images = ['scene1.png', 'scene2.png', 'scene3.png', 'scene4.png', 'scene5.png'];

export default function MyVideo(props: {narrationTimings?: Timing[]}) {
  const timings = props.narrationTimings || [];

  // 검증: 이미지 수와 나레이션 수가 같아야 함
  const sceneCount = Math.min(images.length, timings.length);

  return (
    <AbsoluteFill>
      {timings.slice(0, sceneCount).map((timing, i) => (
        <Sequence key={i} from={timing.startFrame} durationInFrames={timing.durationInFrames}>
          {/* 씬 i에서 이미지 i와 나레이션 i가 함께 표시됨 */}
          <SceneWithImage
            image={images[i]}
            narrationText={timing.text}
            durationInFrames={timing.durationInFrames}
          />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
}

const SceneWithImage = ({image, narrationText, durationInFrames}) => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 15, durationInFrames-15, durationInFrames], [0,1,1,0], {extrapolateLeft:'clamp',extrapolateRight:'clamp'});

  return (
    <AbsoluteFill style={{opacity}}>
      <Img src={staticFile(image)} className="w-full h-full object-cover" />
      {/* 자막 표시 */}
      <div className="absolute bottom-20 left-0 right-0 text-center">
        <p className="text-2xl text-white bg-black/50 px-4 py-2 inline-block rounded">
          {narrationText}
        </p>
      </div>
    </AbsoluteFill>
  );
};
```

### 영상 제작 전 체크리스트

동영상 제작 전에 반드시 확인하세요:

1. **개수 확인**: `이미지 수 === 나레이션 수` 인가?
2. **순서 확인**: 이미지[0]의 내용이 나레이션[0]과 맞는가?
3. **전체 사용**: 모든 이미지가 코드에서 사용되는가?
4. **타이밍 사용**: narrationTimings를 사용해 씬 길이를 결정하는가?

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

```tsx
// 애니메이션 그라데이션 배경 + Tailwind 레이아웃
const angle = interpolate(frame, [0, 90], [0, 360]);
<AbsoluteFill
  className="flex items-center justify-center"
  style={{background: `linear-gradient(${angle}deg, #1a1a2e, #16213e, #0f3460)`}}
/>
```

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

**나레이션 자막 표시 (narrationTimings.text 사용 시)**:
- narrationTimings의 text는 전체 나레이션 문장이므로 길 수 있음 (100자 이상)
- 반드시 세로 넘침을 방지하는 스타일을 적용할 것:
```tsx
// 자막/나레이션 텍스트 컨테이너 권장 스타일
<div style={{
  maxWidth: '85%',
  maxHeight: '40%',        // 화면 높이의 40% 이하
  overflow: 'hidden',
  fontSize: 'clamp(20px, 2.5vw, 34px)',  // 반응형 폰트 크기
  wordBreak: 'keep-all',
  overflowWrap: 'break-word',
  lineHeight: 1.5,
}}>
  {text}
</div>
```
- `maxHeight`로 세로 넘침 방지
- `fontSize: clamp()`로 긴 텍스트에 자동 축소 (최소 20px, 최대 34px)
- 텍스트가 100자 이상이면 fontSize를 24~28px로 줄이기

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

### 🔴 최우선 (이것부터 확인!)
1. **이미지 전부 사용**: asset_paths의 모든 이미지가 동영상에 포함되는가?
2. **1:1:1 매칭**: 이미지 수 = 나레이션 수 = 씬 수 인가?
3. **순서 일치**: 이미지[i]와 나레이션[i]의 내용이 서로 맞는가?
4. **나레이션 동기화**: narration_texts 사용 시 반드시 `props.narrationTimings`로 Sequence 타이밍 결정 (하드코딩 금지)

### 🟡 시각 품질
5. **배경**: 항상 그라데이션 또는 동적 그라데이션 사용 (단색 금지)
6. **텍스트 등장**: 단순 페이드 외에 슬라이드/스케일/타이핑/글자별 중 택1
7. **장식 요소**: 도형, 라인, SVG, 파티클, 프로그레스바 중 최소 1개
8. **씬 전환**: 이전 씬 fadeOut + 다음 씬 슬라이드/와이프/줌 인 조합
9. **색상**: 씬마다 다른 컬러 팔레트, 최소 3색 이상
10. **카드/컨테이너**: 글래스모피즘 또는 그라데이션 배경 카드 활용

### 🟢 코드 품질
11. **Tailwind 우선**: 정적 스타일은 className, 동적 애니메이션만 style prop
12. **커스텀 폰트**: 제목에 디자인 폰트, 본문에 NotoSansKR 사용
13. **텍스트 넘침 없음**: 모든 텍스트가 화면 안에 완전히 표시됨 (한글 제목 24자, 본문 40자 이내)
