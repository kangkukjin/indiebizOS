# 일러스트가 들어간 강의 슬라이드 만들기

책 강의·발표 슬라이드에 **자동 생성 일러스트**를 통합하는 워크플로우. NotebookLM 수준의 시각적 완성도가 목표.

원칙: 코드 통합이 아니라 **AI가 가이드를 읽고 IBL 액션을 조합**해서 만든다. 슬라이드 엔진은 그대로, 이 가이드와 `[engines:image_gemini]` + `[engines:slide_shadcn]` 두 액션의 합주로 결과를 낸다.

---

## 1. 언제 이 가이드를 따르는가

- 책 한 부 또는 한 챕터를 강의용 슬라이드로 만들어야 할 때
- 일반 강의용 슬라이드는 `slides.md` 가이드로 충분 — **메타포·개념을 시각화해야 강의가 살아나는 경우** 이 가이드를 따른다
- 사용자가 "NotebookLM 같은", "일러스트 들어간", "고품질 강의", "시각 자료가 있는" 같은 표현을 쓰면 이 가이드

---

## 2. 5단계 워크플로우 (전체 흐름)

```
1. 슬라이드 기획 (텍스트 outline) — 어떤 슬라이드 N장, 각각 무엇을 말할지
2. 일러스트 필요한 슬라이드 식별 (§4 기준)
3. 디자인 시스템 선택 + 슬라이드별 일러스트 프롬프트 작성 (§3, §5)
4. [engines:image_gemini] 호출로 이미지 생성 → 경로 수집
5. [engines:slide_shadcn]{design_system, slides} 호출 (image_path 포함된 slides)
```

각 단계는 다음 섹션에서 상세히.

---

## 3. 디자인 시스템별 일러스트 스타일 프리픽스 (가장 중요)

**일러스트가 슬라이드와 어울리려면 같은 디자인 언어로 그려져야 한다.** 모든 일러스트 프롬프트의 앞에 디자인 시스템 프리픽스를 붙인다. 이게 NotebookLM이 책 한 권의 모든 그림이 한 작가가 그린 것처럼 보이는 핵심 비결.

### vintage_book
```
Style: vintage Da Vinci-style ink illustration on aged beige parchment paper,
hand-drawn cross-hatching, navy ink (#2c3e6f) and terracotta accents (#a55a3e),
anatomical or architectural diagram aesthetic, subtle paper texture visible,
minimal background, scholarly composition, restrained color palette.
```

### academic_paper
```
Style: clean editorial technical diagram, deep navy linework (#161c2a) on
off-white paper (#fbfaf7), minimal geometric shapes, subtle deep red accents
(#8b1a1a), publication-quality vector illustration, no shadows, labeled
schematic style, academic figure aesthetic.
```

### tech_minimal
```
Style: isometric 3D minimalist illustration on dark navy background (#0d0f17),
cyan neon highlights (#1ce0ff), clean geometric forms with subtle glow,
wireframe overlay, vector art, futuristic minimal, Linear/Vercel aesthetic,
high contrast, no decorative elements.
```

### magazine_modern
```
Style: bold editorial photograph or illustration with high contrast,
dramatic composition, accent red (#e6182b) integrated, large negative space,
Wired/New Yorker magazine aesthetic, striking and minimal, single subject focus.
```

**프롬프트 조합 = 스타일 프리픽스 + 슬라이드 콘텐츠 설명**:

```
[Style: vintage Da Vinci-style ink illustration...] +
[Content: A brain alone on the left side and a brain connected through veins
and muscles to a robotic arm reaching for an apple on the right side. Comparison
illustration showing "thinking without body" vs "thinking with embodied tools".]
```

---

## 4. 어느 슬라이드가 일러스트 가치가 있는가

**일러스트로 가르치는 슬라이드** (생성 가치 ★★★):
- `metaphor_story` — 메타포 자체가 시각적 (햄릿 무대, 깜깜한 계단, 부산→서울)
- `hero` 표지 — 책 전체 컨셉을 한 장에 압축
- `quote` 풀스크린 인용 — 인용과 함께 강력한 비주얼 (선택)
- 핵심 개념 슬라이드 — "AI 모델 vs 하네스" 같은 대비 (커스텀 hero_image)

**텍스트만으로 충분한 슬라이드** (일러스트 불필요):
- `lecture_body` 본문 단락 — 글 자체가 강의
- `comparison_table` 비교표 — 표가 시각 도구
- `factbox` 보조 정보 — 텍스트 박스가 형식
- `steps` 단계 — 다이어그램이 이미 그 자체

**기준**: "이 메타포/개념을 그림으로 보여주면 강의가 더 명확해지는가?" → Yes면 일러스트.

15장짜리 강의 슬라이드라면 보통 **3~5장에만 일러스트** (표지 + 핵심 메타포 2~3개 + 마무리 비주얼). 모든 슬라이드에 일러스트 = 비용·시간 낭비 + 시각 피로.

---

## 5. 일러스트 프롬프트 작성 요령

좋은 일러스트 프롬프트 = **스타일 프리픽스 + 명확한 비주얼 묘사 + 구성 지시**.

### 좋은 예 (vintage_book + 햄릿 메타포)
```
[Style prefix: vintage Da Vinci-style ink illustration on aged beige parchment...]

Content: A theatrical mask on the left representing an actor reading from a
thick script, with a smaller figure of a director whispering instructions
on the right. Old theater stage backdrop sketched lightly. The actor holds
the same script but the directions vary by scene — show this with multiple
small instruction notes floating around. Composition: left-right narrative
balance, ink crosshatching for shadows, no color background, just paper.
```

### 나쁜 예
```
"햄릿 배우"  ← 너무 짧음, AI가 추측해야 함
"좋은 일러스트로 햄릿을 그려줘"  ← 추상적
```

### 핵심 요소
- **무엇을 그릴지** (구체적 객체·인물·상황)
- **구성** (좌우/상하/중앙, 비율)
- **무엇을 강조할지** (책의 핵심 메시지)
- **무엇을 빼야 할지** (배경 단순화, 색 제한 등)

---

## 6. Gemini 이미지 생성 호출

### 단일 호출
```
execute_ibl(code='[engines:image_gemini]{
  prompt: "[스타일 프리픽스]. [구체적 비주얼 묘사]",
  aspect_ratio: "16:9",
  output_path: "lecture_illust_01.png"
}')
```

### 병렬 호출 (여러 장 동시 생성 — 빠름)
```
execute_ibl(code='
  [engines:image_gemini]{prompt: "[프리픽스]. 햄릿 메타포...", aspect_ratio: "16:9", output_path: "illust_01.png"} &
  [engines:image_gemini]{prompt: "[프리픽스]. 깜깜한 계단...", aspect_ratio: "16:9", output_path: "illust_02.png"} &
  [engines:image_gemini]{prompt: "[프리픽스]. 뇌+사과 비교...", aspect_ratio: "16:9", output_path: "illust_03.png"}
')
```

**aspect_ratio 선택**:
- `16:9` — `hero_image`, `content_image`, 슬라이드 전체 배경용 (가장 자주 씀)
- `1:1` — 카드형 슬라이드의 일러스트
- `4:3` — `hero` 표지의 중앙 배치 일러스트

### 결과 확인
응답에 절대 경로가 포함됨 (`/Users/.../outputs/illust_01.png`). 이 경로를 슬라이드 dict의 `image_path`로 전달.

---

## 7. 일러스트가 들어가는 슬라이드 레이아웃

기존 layout 중 image_path를 지원하는 것:

| layout | 이미지 위치 |
|--------|-------------|
| `hero_image` | 우측 50% — 좌측 텍스트와 좌우 분할 |
| `content_image` | 한쪽 — `image_position: "left"` 또는 "right" |
| `image_fullscreen` | 전체 배경 (텍스트가 그 위에) |

`metaphor_story`는 현재 텍스트 전용 — 일러스트 메타포를 만들고 싶으면 **`hero_image`로 대체**해서 좌측에 메타포 본문 + 우측에 일러스트.

### 표지 (hero) 슬라이드
일반적으로 hero 레이아웃은 텍스트 중앙 정렬이라 큰 이미지가 안 들어감. 책 표지처럼 만들고 싶으면 `custom` layout에 직접 HTML 작성:

```
{layout: "custom", custom_html: "<div class='flex flex-col items-center justify-center w-full h-full'><img src='file:///abs/path/illust.png' class='max-h-[420px] mb-12'/><h1 class='text-6xl font-black'>제목</h1><p class='text-2xl mt-4'>부제</p></div>"}
```

(주의: `image_path`를 file:// 로 절대경로 사용)

---

## 8. 전체 워크플로우 예시 (책 1부 15장 강의)

```
[1단계] 슬라이드 기획
  - 15장 outline 작성 (텍스트 노트)
  - 일러스트 가치 있는 슬라이드 식별: 1번(표지), 3번(햄릿 메타포),
    7번(부산→서울), 10번(깜깜한 계단), 15번(자전거)
  - 디자인 시스템 결정: vintage_book

[2단계] 일러스트 프롬프트 작성
  - 5개 슬라이드 각각에 [vintage_book 프리픽스] + [슬라이드별 묘사] 프롬프트 준비

[3단계] 일러스트 병렬 생성
  execute_ibl(code='
    [engines:image_gemini]{prompt: "...표지...", aspect_ratio: "16:9", output_path: "p1_cover.png"} &
    [engines:image_gemini]{prompt: "...햄릿 메타포...", aspect_ratio: "16:9", output_path: "p1_hamlet.png"} &
    [engines:image_gemini]{prompt: "...부산→서울 교통수단...", aspect_ratio: "16:9", output_path: "p1_busan.png"} &
    [engines:image_gemini]{prompt: "...깜깜한 계단 발 조정...", aspect_ratio: "16:9", output_path: "p1_stairs.png"} &
    [engines:image_gemini]{prompt: "...자전거 타기 메타포...", aspect_ratio: "16:9", output_path: "p1_bike.png"}
  ')
  → 5개 절대경로 수집

[4단계] 슬라이드 배열 구성
  - 15개 슬라이드 중 5개에 image_path 추가, 해당 layout을 hero_image 또는 content_image로
  - 나머지 10개는 lecture_body / comparison_table / factbox / quote (텍스트 전용)

[5단계] 슬라이드 데크 생성
  execute_ibl(code='[engines:slide_shadcn]{
    design_system: "vintage_book",
    slides: [
      {layout: "custom", custom_html: "...표지 + p1_cover.png..."},
      {layout: "lecture_body", title: "...", body: "..."},
      {layout: "hero_image", title: "...", subtitle: "...", image_path: "/abs/path/p1_hamlet.png"},
      ...
    ]
  }')
```

---

## 9. 검증 사이클 — 한 장 먼저 시도

15장 일러스트를 한 번에 만들었다가 스타일이 안 맞으면 비용·시간 큰 낭비. **먼저 1장만 생성하고 사용자에게 확인**.

```
[1차] execute_ibl(code='[engines:image_gemini]{prompt: "...첫 메타포...", aspect_ratio: "16:9"}')
→ 결과 PNG를 사용자에게 보여주거나 [self:read]로 확인
→ "이 스타일이 맞나요?" 물어봄 (ask_user_question)
→ OK면 나머지 4장 병렬 생성
→ NOT OK면 프롬프트 수정 후 재시도
```

이게 검증 사이클 없이 한 번에 가는 것보다 결과적으로 빠르고 비용도 적다.

---

## 10. 비용·할당량·실패 대응

### Gemini 이미지 비용
- `gemini-2.5-flash-image` 한 장당 약 $0.04 정도 (변동 가능, 공식 단가 확인)
- 5장 = ~$0.20, 15장 = ~$0.60 (모든 슬라이드에 일러스트 시)

### 할당량 초과 (429 에러)
응답에 `"error": { "code": 429 }` 또는 "exceeded your current quota":
- 즉시 텍스트 전용 폴백 (이미지 없는 lecture_body / metaphor_story 사용)
- 사용자에게 "일러스트 생성 할당량 초과 — 텍스트로만 진행하겠습니다" 알림

### 실패 시 폴백 원칙
일러스트 생성이 실패해도 **슬라이드 데크는 만들어진다.** 해당 슬라이드의 layout을 hero_image → metaphor_story로 바꾸고 image_path 제거. 강의 자체가 멈추면 안 됨.

### 캐시
같은 프롬프트로 같은 이미지를 두 번 생성하지 않도록 — 한 번 만든 파일은 `output_path`를 명시해 재사용 (디렉토리에 이미 있으면 호출 생략 가능).

---

## 11. 회피해야 할 실수

- **스타일 프리픽스 빼먹기** — 이게 빠지면 각 일러스트가 다 다른 화풍으로 나옴 → NotebookLM과의 격차 다시 벌어짐
- **모든 슬라이드에 일러스트 욕심** — 비용·시간·시각 피로. §4 기준에 맞게 3~5장만.
- **검증 없이 15장 한 번에 생성** — 스타일 안 맞으면 전부 다시. §9 사이클 따를 것.
- **image_path를 상대경로로 전달** — 슬라이드 엔진은 절대경로 또는 file:// 필요. image_gemini 응답의 절대경로 그대로 사용.
- **aspect_ratio 잘못** — hero_image/content_image는 16:9 가로형. 1:1로 만들면 좌우에 흰 공간 생김.
- **너무 추상적인 프롬프트** — "좋은 일러스트" "메타포 그림" 같은 단어로 끝내면 안 됨. 구체적 객체·구성·강조점을 명시.
- **디자인 시스템과 일러스트 톤 불일치** — tech_minimal 데크에 vintage 일러스트 넣으면 어색. 디자인 시스템 결정 → 그 프리픽스 → 데크 전체.

---

## 12. 한 줄 요약

> 텍스트 강의 슬라이드는 `slides.md`로, **일러스트가 들어간 책 강의 슬라이드는 이 가이드 + image_gemini + slide_shadcn의 5단계 합주로** 만든다. 핵심은 디자인 시스템 프리픽스로 화풍 통일.
