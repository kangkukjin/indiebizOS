# 동영상 제작 워크플로우 가이드

동영상 제작은 여러 단계의 원자적 액션을 조합하여 수행합니다.
한 번의 복합 액션으로 동영상을 만들지 마세요. 단계별로 작업하면 오류 수정과 품질 향상이 가능합니다.

## 제작 방식 선택

| 방식 | 특징 | 적합한 경우 |
|------|------|-------------|
| **HTML 영상** | HTML/CSS/GSAP 기반, Playwright 캡처 | 슬라이드형, 인포그래픽, 빠른 제작 |
| **Remotion 영상** | React/TSX 기반, 프레임 단위 애니메이션 | 복잡한 모션, 프로그래밍적 애니메이션 |

---

## HTML 영상 제작 워크플로우

### Step 1: 계획
사용자 요청을 분석하고 씬 구성을 계획합니다.
- 몇 개의 씬이 필요한지
- 각 씬의 내용과 duration
- 나레이션 필요 여부
- 이미지/BGM 필요 여부

### Step 2: 이미지 생성 (필요 시)
```
execute_ibl(node="forge", action="image", target="프롬프트", params={...})
```
AI 이미지가 필요하면 먼저 생성합니다. 생성된 이미지 경로를 기록해 둡니다.

### Step 3: 씬 HTML 코드 작성
각 씬을 별도 HTML 파일로 작성합니다. `system:write`로 파일에 저장합니다.
```
execute_ibl(node="system", action="write", target="outputs/video_project/scene_01.html", params={"content": "<!DOCTYPE html>..."})
execute_ibl(node="system", action="write", target="outputs/video_project/scene_02.html", params={"content": "<!DOCTYPE html>..."})
```

**HTML 작성 시 html_video_guide.md 참조 필수:**
- body 크기 1280x720px 고정
- 텍스트 넘침 방지 (한글 제목 18자, 본문 35자)
- 그라데이션 배경, GSAP 애니메이션 활용

### Step 4: 미리보기 (선택)
HTML을 이미지로 렌더링하여 레이아웃을 확인합니다.
```
execute_ibl(node="forge", action="render_html", target="<씬 HTML 코드>")
```
결과 이미지를 보고 문제가 있으면 Step 3으로 돌아가 `system:edit`로 수정합니다.

### Step 5: 오류 수정 (필요 시)
텍스트 넘침, 레이아웃 깨짐 등을 발견하면 파일을 수정합니다.
```
execute_ibl(node="system", action="edit", target="outputs/video_project/scene_01.html", params={"old_string": "...", "new_string": "..."})
```
수정 후 다시 render_html로 미리보기하여 확인합니다.

### Step 6: TTS 나레이션 생성 (필요 시)
각 씬의 나레이션 텍스트를 음성 파일로 변환합니다.
```
execute_ibl(node="forge", action="tts", target="첫 번째 씬의 나레이션 텍스트", params={"output_filename": "narration_01.mp3"})
execute_ibl(node="forge", action="tts", target="두 번째 씬의 나레이션 텍스트", params={"output_filename": "narration_02.mp3"})
```

### Step 7: 최종 렌더링
모든 파일이 준비되면 render_video로 MP4를 생성합니다.
```
execute_ibl(node="forge", action="render_video", target="outputs/video_project/", params={
  "scene_files": [
    {"path": "outputs/video_project/scene_01.html", "duration": 5},
    {"path": "outputs/video_project/scene_02.html", "duration": 7}
  ],
  "narration_files": [
    "outputs/video_project/narration_01.mp3",
    "outputs/video_project/narration_02.mp3"
  ],
  "bgm_path": "경로/bgm.mp3",
  "output_filename": "final_video.mp4"
})
```

또는 scene_dir로 폴더 전체를 지정할 수도 있습니다:
```
execute_ibl(node="forge", action="render_video", target="outputs/video_project/", params={
  "default_duration": 5,
  "output_filename": "final_video.mp4"
})
```

---

## Remotion 영상 제작 워크플로우

### Step 1: 계획
HTML 영상과 동일하게 씬 구성을 계획합니다.

### Step 2: 이미지/에셋 준비 (필요 시)
```
execute_ibl(node="forge", action="image", target="프롬프트")
```

### Step 3: TSX 컴포지션 코드 작성
React/TSX 코드를 파일로 작성합니다.
```
execute_ibl(node="system", action="write", target="outputs/video_project/composition.tsx", params={"content": "import {AbsoluteFill, useCurrentFrame}..."})
```

**TSX 작성 시 remotion_guide.md, visual_guide.md 참조 필수:**
- `useCurrentFrame()`, `interpolate()` 활용
- Tailwind className으로 정적 스타일
- Google Fonts 로드
- spring 애니메이션 등

### Step 4: 렌더링
TSX 파일 경로를 지정하여 렌더링합니다.
```
execute_ibl(node="forge", action="render_remotion", target="outputs/video_project/composition.tsx", params={
  "duration_in_frames": 300,
  "fps": 30,
  "width": 1280,
  "height": 720,
  "asset_paths": ["이미지경로1.png", "이미지경로2.png"],
  "output_filename": "remotion_video.mp4"
})
```

### Step 5: 오류 수정 (필요 시)
렌더링 실패 시 에러 메시지를 확인하고 TSX 코드를 수정합니다.
```
execute_ibl(node="system", action="edit", target="outputs/video_project/composition.tsx", params={"old_string": "...", "new_string": "..."})
```
수정 후 다시 render_remotion을 실행합니다.

---

## 빠른 제작 (기존 복합 액션)

간단한 영상이라면 기존 복합 액션도 사용 가능합니다:
```
# HTML 영상 - 코드를 직접 전달
execute_ibl(node="forge", action="video", target="주제", params={
  "scenes": [...],
  "narration_texts": [...]
})

# Remotion 영상 - 코드를 직접 전달
execute_ibl(node="forge", action="remotion", target="<TSX 코드>", params={...})
```
단, 이 방식은 코드 오류 수정이 어렵습니다. 품질이 중요한 영상은 위의 단계별 워크플로우를 사용하세요.

---

## 액션 요약

| 액션 | 용도 | 핵심 파라미터 |
|------|------|---------------|
| `forge:image` | AI 이미지 생성 | prompt |
| `forge:tts` | 텍스트 → MP3 | text, voice, output_filename |
| `forge:render_html` | HTML → 이미지 (미리보기) | html |
| `forge:render_video` | HTML 파일들 → MP4 | scene_files/scene_dir, narration_files |
| `forge:render_remotion` | TSX 파일 → MP4 | composition_file |
| `system:write` | 코드를 파일로 저장 | path, content |
| `system:edit` | 파일 부분 수정 | path, old_string, new_string |
| `system:read` | 파일 내용 확인 | path |
