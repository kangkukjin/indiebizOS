# 일러스트가 들어간 강의 슬라이드 만들기

책 강의·발표 슬라이드에 **자동 생성 일러스트**를 통합하는 워크플로우. NotebookLM 수준의 시각적 완성도가 목표.

원칙: 코드 통합이 아니라 **AI가 가이드를 읽고 IBL 액션을 조합**해서 만든다. 슬라이드 엔진은 그대로, 이 가이드와 `[engines:image_gemini]` + `[engines:slide_shadcn]` 두 액션의 합주로 결과를 낸다.

> **2026-05 업데이트**: ① 일러스트와 텍스트가 한 화면에서 융합되는 **통합형 레이아웃 4종**(hero_illustration / illustration_anchor / split_concept / illustration_background) 추가 — `custom` HTML 우회 더 이상 불필요. ② 이미지 모델 **Nano Banana 2(`gemini-3.1-flash-image-preview`) 기본**, 한국어 텍스트 렌더링 개선·4K 지원. ③ `style_preset` 파라미터 도입 — 디자인 시스템과 매칭되는 스타일 프리픽스 자동 주입, 수동 작성 불필요.
>
> **2026-05-22 업데이트 (NotebookLM 따라잡기)**: ④ **`sf_blueprint` 디자인 시스템 + style_preset 추가** — 다크 네이비 + 시안 글로우 + HUD 격자, NotebookLM 양식. ⑤ **`illustration_overlay` 레이아웃 추가** — 풀-블리드 일러스트 위에 자유 좌표 한글 라벨 박스 N개를 얹는 NotebookLM 패턴. ⑥ **책 강의 패러다임 전환**: "3~5장만 일러스트"에서 **"매 장이 다이어그램"으로 기본 정책 변경** (§4 참조). ⑦ 일러스트 프롬프트를 "씬(scene)"이 아닌 "**인포그래픽/다이어그램**"으로 작성, 영문 라벨/HUD 텍스트 적극 허용.

---

## 1. 언제 이 가이드를 따르는가

- 책 한 부 또는 한 챕터를 강의용 슬라이드로 만들어야 할 때
- 일반 강의용 슬라이드는 `slides.md` 가이드로 충분 — **메타포·개념을 시각화해야 강의가 살아나는 경우** 이 가이드를 따른다
- 사용자가 "NotebookLM 같은", "일러스트 들어간", "고품질 강의", "시각 자료가 있는" 같은 표현을 쓰면 이 가이드

### 모드 분기 (먼저 결정)

사용자 요청을 보고 두 모드 중 어느 것인지 먼저 정한다 — 가이드 전체에서 이 선택이 모든 세부 결정에 영향을 준다.

- **모드 A (클래식 강의록)**: 사용자가 "강의록", "발표 자료", "책 본문 슬라이드" 같은 일반 표현을 쓸 때. `vintage_book`/`academic_paper`/`magazine_modern` 디자인. 표지+메타포 3~5장만 일러스트.
- **모드 B (NotebookLM 양식 인포그래픽)** ★: 사용자가 "**NotebookLM처럼**", "**인포그래픽**", "**다이어그램 슬라이드**", "**시각 자료가 풍성한**", "**모든 장에 그림이**" 같은 표현을 쓸 때. `sf_blueprint` 디자인 + `illustration_overlay` 메인 레이아웃. 거의 모든 장이 일러스트+한글 라벨 박스.

판단이 애매하면 사용자에게 한 번 물어본다: "클래식 강의록 양식과 NotebookLM 인포그래픽 양식 중 어느 쪽을 원하세요?"

---

## 2. 5단계 워크플로우 (전체 흐름)

```
1. 슬라이드 기획 — 메시지 큐레이션 5단계 (lecture_slide_principles.md §2)  ★ 절대 건너뛰지 말 것
   ① 명제 추출 (책 한 부에서 "잊으면 안 될 명제 N개")
   ② 슬라이드 제목 = 명제 (챕터명을 라벨로 가져오면 안 됨)
   ③ 수사 장치 매핑 (좌우대비/단계/등식/수치/동심원 5종 중 하나)
   ④ 구체화 의무 (수치·인명·사례는 격리해서 시각 요소로)
   ⑤ 이중 회수 (마지막 두 장은 비교표 + 체계 정리, 그 후 선택적 인용)
   → 산출물: 슬라이드별 (명제 / 장치 / 일러스트 구도 / 구체화 요소) outline 표

2. 레이아웃·디자인 시스템 결정 (§3, §4, §5)
   - 모드 A 클래식 vs 모드 B NotebookLM 양식
   - 일러스트 가치 있는 슬라이드 식별 + 레이아웃 매핑

3. 슬라이드별 일러스트 프롬프트 작성 (§6) — 다이어그램형, 영문 라벨 명시, 한글 라벨 자리 빈 공간 확보
4. [engines:image_gemini] 호출 (style_preset 지정) — 경로 수집
5. [engines:slide_shadcn]{design_system, slides} 호출 (image_path 포함된 slides)
```

**1단계가 핵심.** 디자인 톤·일러스트가 NotebookLM과 동일해도 1단계를 건너뛰면 "텍스트의 나열" 결과물이 된다. 1단계 outline이 완성되기 전에 일러스트 생성에 들어가지 말 것 — 그러면 그림은 만들어졌는데 그림을 어떻게 활용할지 모르는 사태가 발생함.

---

## 3. 통합형 레이아웃 (NotebookLM 스타일 — 우선 선택)

일러스트가 슬라이드 배경과 자연스럽게 흐르는 통합형 레이아웃. **옛 hero_image/content_image의 우측 박스 분할 패턴이 아니라 이쪽을 기본**으로 한다.

| layout | 구성 | 적합한 슬라이드 |
|---|---|---|
| **`illustration_overlay`** ★ | **풀-블리드 일러스트 + 자유 좌표 한글 라벨 박스 N개** | **다이어그램 슬라이드 (NotebookLM 양식의 핵심)** — 한 일러스트의 여러 부위를 한국어로 설명 |
| `hero_illustration` | 중앙 영웅 일러스트 + 상하 텍스트 | **표지, 장 도입** (NotebookLM 책 표지 스타일) |
| `illustration_anchor` | 상단 큰 일러스트 + 하단 텍스트(title/body/takeaway) | **개념 설명** — 라벨 N개 필요 없을 때 |
| `split_concept` | 좌우 대비, 양쪽 일러스트+캡션 + 중앙 결론 박스 | **A vs B** (뇌 vs 몸, 문제 vs 해결, 전/후) — 단, NotebookLM은 한 일러스트 안에 좌우 비교를 그려넣고 `illustration_overlay`로 처리하는 편이 더 일관됨 |
| `illustration_background` | 전면 배경 일러스트 + 그라데이션 스크림 + 오버레이 텍스트 | **부 도입, 임팩트 슬라이드** |
| `comparison_iconic` | 이모지/일러스트 헤더가 있는 시각적 비교 표 | **결론 정리, 챕터 마무리** |

각 레이아웃의 필수 키:
- **`illustration_overlay`** (★ NotebookLM 패턴): `image_path` 또는 `image_data`, `labels: [{text, position, variant?, subtext?}]`. 선택: `title`/`eyebrow`/`footer_quote`.
    - **position**: 9방위 프리셋(`"top-left"`/`"top-center"`/`"top-right"`/`"middle-left"`/`"middle-center"`/`"middle-right"`/`"bottom-left"`/`"bottom-center"`/`"bottom-right"`) 또는 절대 좌표 dict (`{top: "20%", left: "10%", width: "30%"}`).
    - **variant**: `"label"`(기본, 작은 캡션) / `"title"`(큰 제목) / `"panel"`(다중행 본문 + 강조 헤더). NotebookLM 3페이지(망막/뇌/외부세계 라벨)는 `label`, 5페이지(컨텍스트 박스)는 `panel`.
    - **subtext**: 본문 줄들. `panel`일 때 문자열 또는 리스트 가능 (리스트면 줄별로 박힘).
    - **footer_quote**: 하단 결론 박스 (NotebookLM 5/8/10페이지의 청록 인용 박스 양식).
    - **이미지 프롬프트 필수 조건**: 라벨이 들어갈 자리에 의도적으로 빈 공간을 비워두도록 프롬프트에 명시 (§6 참조).
- `hero_illustration`: `title`, `image_data` 또는 `image_path`, 선택: `eyebrow`/`subtitle`/`footer`
- `illustration_anchor`: `title`, `body`, `image_data`, 선택: `eyebrow`/`takeaway`
- `split_concept`: `title`, `left_title`/`left_image_data`/`left_body`, `right_title`/`right_image_data`/`right_body`, 선택: `subtitle`/`conclusion`
- `illustration_background`: `title`, `image_data`, 선택: `eyebrow`/`subtitle`/`text_align`("left" 기본 — 영화 자막 양식 / "center" — NotebookLM 부 표지 양식, 라디얼 스크림으로 가독성 보장). 일러스트가 화면 중앙에 강한 형태(부채꼴·동그라미)를 가지면 left를, 좌우 균형 잡힌 추상 패턴이면 center를 권장.
- `comparison_iconic`: `title`, `columns: [{title, subtitle, icon, highlighted}]`, `rows: [{label, cells: [...]}]`, 선택: `eyebrow`/`subtitle`/`label_header`/`footer`. **주의: row 필드명은 `cells` (`values` 아님 — Jinja 충돌)**. icon은 이모지(💬 ⚙️ 🧠 등) 또는 작은 SVG 인라인. highlighted=True 컬럼은 적갈색 강조 배경

기존 좌우분할 `hero_image`/`content_image`도 통합형 처리로 개선됨(우측 박스/배경 제거, blend 처리) — 단순 좌우 분할이 꼭 필요할 때만 사용.

---

## 4. 어느 슬라이드가 일러스트 가치가 있는가

### 두 가지 운영 모드

**모드 A — 클래식 강의록** (책의 본문 흐름이 주력, 일러스트는 보조)
- 표지 + 핵심 메타포 3~5장만 일러스트. 나머지는 `lecture_body`/`comparison_table`/`factbox`.
- 사용처: 일반 발표, 강의록 인쇄본, 텍스트 무게가 중요한 인문서.
- 디자인 시스템: `vintage_book` / `academic_paper` / `magazine_modern`.

**모드 B — NotebookLM 양식 인포그래픽** (★ 새 기본값 for 책 강의)
- **거의 모든 슬라이드가 일러스트 + 라벨 오버레이**. 본문 텍스트는 일러스트 위 한글 라벨로 박힘.
- 사용처: 책 한 권/한 부를 강의 슬라이드로 만들 때 **시각적 임팩트가 텍스트 무게보다 중요**할 때. NotebookLM과 동일 패러다임.
- 디자인 시스템: **`sf_blueprint`** (다크 네이비 + 시안 글로우 HUD).
- 메인 레이아웃: **`illustration_overlay`**.
- 사용자가 "NotebookLM처럼", "다이어그램 강의", "인포그래픽 슬라이드"를 요청하면 이 모드.

### 모드 B(NotebookLM 양식) 슬라이드 구성 권장

| 슬라이드 종류 | 레이아웃 | 일러스트 패턴 |
|---|---|---|
| 표지 | `illustration_background` (text_align=center) | 책 전체 컨셉의 풀-블리드 영웅 일러스트 |
| 부 도입 | `illustration_background` | 분위기 일러스트 |
| 메타포 다이어그램 | **`illustration_overlay`** | 영문 라벨이 박힌 다이어그램 + 한글 라벨 박스 3~5개 |
| A vs B 비교 | **`illustration_overlay`** (한 일러스트 안에 좌우 그려넣기) | 좌/우 비교가 한 일러스트로, `position: middle-left` + `middle-right` 라벨 |
| 결론 표/마무리 | `comparison_iconic` 또는 `illustration_overlay` + footer_quote | — |
| 인용 한 줄 | `quote` (일러스트 없음) | — |

15장이면 일러스트 12~14장, 나머지 1~3장만 텍스트 슬라이드. **모드 A의 "3~5장만" 정책은 모드 B에서 정반대로 뒤집힘.**

### 일러스트 가치 판단 기준 (모드 무관)

"이 슬라이드를 시각 자료 없이 텍스트만으로 봤을 때, 강의가 더 약해지는가?" → Yes면 일러스트. 모드 B에서는 거의 모든 슬라이드에서 Yes가 나온다.

---

## 5. 레이아웃 선택 가이드

### 모드 B (NotebookLM 양식) — 책 강의 기본
```
표지 한 장이다 ────────────────────────→ illustration_background (text_align=center) 또는 hero_illustration
한 개념을 다이어그램으로 설명 + 라벨 ──→ illustration_overlay  ★ 가장 자주 씀
A vs B 비교 (한 일러스트 안에 좌우) ───→ illustration_overlay (middle-left/middle-right 라벨)
A vs B 비교 (별도 일러스트 2장) ───────→ split_concept
부 시작면, 강한 분위기 한 장 ──────────→ illustration_background
챕터 결론 표 ──────────────────────────→ comparison_iconic
일러스트 + 한 줄 결론 ─────────────────→ illustration_overlay (footer_quote 사용)
인용 한 줄 풀스크린 ──────────────────→ quote (또는 illustration_background)
```

### 모드 A (클래식 강의록)
```
표지 한 장이다 ────────────────────────→ hero_illustration
한 개념을 일러스트로 설명한다 ──────────→ illustration_anchor
두 개념을 나란히 대조한다 ──────────────→ split_concept
부 시작면, 강한 분위기 한 장이 필요 ────→ illustration_background
챕터 결론 표, 시각적 임팩트 있는 비교 ──→ comparison_iconic
순수 본문 강의 ────────────────────────→ lecture_body
순수 텍스트 표 ────────────────────────→ comparison_table
보조 정보·팩트박스 ────────────────────→ factbox / steps
인용 한 줄 풀스크린 ───────────────────→ quote
```

---

## 6. 일러스트 프롬프트 작성 (style_preset이 다 해준다)

**중요 변화**: 예전에는 vintage_book 스타일 프리픽스를 프롬프트 앞에 길게 붙여야 했지만, 이제 `style_preset` 파라미터 하나로 자동 주입된다.

### 호출 패턴 (간단)
```
execute_ibl(code='[engines:image_gemini]{
  prompt: "A theatrical mask on the left representing an actor reading from a thick script, with a smaller figure of a director whispering instructions on the right.",
  style_preset: "vintage_book",
  aspect_ratio: "16:9",
  image_size: "2K",
  output_path: "p1_hamlet.png"
}')
```

`style_preset`이 자동으로 추가하는 토큰:
- vintage_book: 낡은 베이지 양피지, 청-적갈 펜화, 격자 배경, **한글·장식 라틴어 텍스트 금지**
- academic_paper: 흰 종이, 진남색+진홍 학술 도식, 가는 펜선
- tech_minimal: 다크 + 시안 네온, Linear/Vercel 양식
- magazine_modern: 흑백+적색 임팩트 편집 일러스트
- **sf_blueprint** ★ (NotebookLM 양식): 다크 네이비 + 시안 글로우 + HUD 격자, 와이어프레임/x-ray 양식, **영문 라벨 및 영문 기술 주석 허용** (예: EYE, MASS, F=ma, FAILURE STATE), 한글만 금지. 라벨 박스가 들어갈 공간을 일러스트 측면/하단에 비워두도록 명시.

→ **모든 슬라이드의 일러스트가 한 작가가 그린 것처럼 통일됨.** NotebookLM의 비결.

### 프롬프트 본문 작성 — 모드별 패러다임

**모드 A (클래식 강의록)**: 회화적 "씬(scene)"으로 작성.
- 예: `"A theatrical mask on the left representing an actor reading from a thick script, with a smaller figure of a director whispering instructions on the right."`

**모드 B (NotebookLM 양식)** ★: **"씬"이 아니라 "다이어그램/인포그래픽"으로 작성**.
- ✓ 좋은 예 (sf_blueprint): `"Sci-fi HUD infographic comparing two states side by side. Left panel: a glowing brain trapped inside a transparent glass jar, label 'BRAIN IN A JAR' below. Right panel: same brain but surrounded by exploding shards of glass and connected to gears, sensors and robotic arms, label 'EMBODIED' below. Connecting arrows between panels. Dark navy background, cyan glow wireframe rendering. Leave roughly the top 15% of the canvas empty for a Korean title overlay, and reserve clean rectangular regions under each panel for Korean caption boxes."`
- ✗ 나쁜 예: `"뇌와 몸 대비"` (너무 짧음) / `"AI 모델 vs 하네스"` (한글 + 추상적)

다이어그램형 프롬프트의 필수 요소:
1. **구도 명시**: "side by side", "concentric circles", "central subject with radiating labels", "before/after panels", "exploded view"
2. **객체 위치 + 영문 라벨**: 각 객체에 어떤 영문 라벨을 박을지 명시 — Nano Banana 2가 영문은 잘 그림.
3. **여백 보존 지시**: "Leave the right one-third of the canvas empty for caption overlay" / "Top 15% reserved for Korean title". 한글 라벨이 들어갈 자리를 미리 비워두는 게 illustration_overlay 성패를 가름.
4. **HUD/블루프린트 요소**: corner brackets, schematic grid, glow, technical annotations, arrows.

### 한글 vs 영문 라벨 정책 (개정)
- **한글은 절대 이미지 안에 넣지 않는다** — 변함없음. 한글 라벨은 슬라이드 텍스트 레이어(`illustration_overlay`의 labels)에서 처리.
- **영문 기술 라벨/HUD 텍스트는 적극 허용** (sf_blueprint 한정). EYE, MASS, F=ma, FAILURE STATE, SUCCESS STATE, BRAIN, BODY 같은 짧은 영문은 인포그래픽의 핵심 요소이므로 프롬프트에 명시.
- **장식적 가짜 라틴어/암호 텍스트는 금지** — style_preset이 자동 차단.

---

## 7. Gemini 이미지 모델 선택

| quality | 모델 | 용도 | 비용/장 |
|---|---|---|---|
| `"fast"` (기본) | gemini-3.1-flash-image-preview (Nano Banana 2) | 일반 강의 일러스트 | 1K ~$0.045 |
| `"pro"` | gemini-3-pro-image-preview (Nano Banana Pro) | 표지, 인쇄 결과물, 핵심 1장 | 더 비쌈, 4K 가능 |
| `"legacy"` | gemini-2.5-flash-image | 폴백, 3.x가 문제 일으킬 때 | 1K ~$0.039 |

**기본 권장**: `quality` 생략(=fast) + `image_size: "1K"` — 슬라이드용으로 충분하고 가장 저렴.
**표지만 고급**: `quality: "pro"` + `image_size: "2K"` 또는 `"4K"`.

### 종횡비 (aspect_ratio)
- `16:9` — `hero_illustration`/`illustration_anchor`/`illustration_background` (가장 자주 씀)
- `1:1` — `split_concept`의 좌우 일러스트 (정사각형이 좌우 균형 좋음)
- `4:3`/`3:4` — 특정 구성용

---

## 8. 병렬 호출 (여러 장 동시 생성)
```
execute_ibl(code='
  [engines:image_gemini]{prompt: "표지 콘텐츠...", style_preset: "vintage_book", aspect_ratio: "16:9", image_size: "2K", output_path: "p1_cover.png"} &
  [engines:image_gemini]{prompt: "햄릿 메타포 콘텐츠...", style_preset: "vintage_book", aspect_ratio: "16:9", output_path: "p1_hamlet.png"} &
  [engines:image_gemini]{prompt: "뇌+사과 vs 뇌+팔 콘텐츠...", style_preset: "vintage_book", aspect_ratio: "1:1", output_path: "p1_brain_left.png"} &
  [engines:image_gemini]{prompt: "...뇌+팔+사과...", style_preset: "vintage_book", aspect_ratio: "1:1", output_path: "p1_brain_right.png"}
')
```

응답에 절대 경로 포함됨. 이 경로를 슬라이드 dict의 `image_path` 또는 `left_image_data`/`right_image_data`로 전달.

---

## 9. 전체 워크플로우 예시 (책 1부 15장 강의)

```
[1단계] 슬라이드 기획
  - 15장 outline 작성 (텍스트 노트)
  - 일러스트 가치 있는 슬라이드 식별:
    1번 표지 → hero_illustration
    3번 햄릿 메타포 → illustration_anchor
    5번 AI 모델 vs 하네스 → split_concept (좌우 일러스트 2장)
    8번 제1부 표지 → illustration_background
    15번 마무리 → hero_illustration
  - 디자인 시스템: vintage_book

[2단계] 일러스트 프롬프트 작성
  - 6장의 일러스트(split_concept는 2장 필요) — 콘텐츠 묘사만, 스타일은 style_preset에 위임

[3단계] 일러스트 병렬 생성
  execute_ibl(code='
    [engines:image_gemini]{prompt: "표지 콘텐츠", style_preset: "vintage_book", aspect_ratio: "16:9", quality: "pro", image_size: "2K", output_path: "p1_cover.png"} &
    [engines:image_gemini]{prompt: "햄릿 메타포 콘텐츠", style_preset: "vintage_book", aspect_ratio: "16:9", output_path: "p1_hamlet.png"} &
    [engines:image_gemini]{prompt: "뇌 단독", style_preset: "vintage_book", aspect_ratio: "1:1", output_path: "p1_brain_solo.png"} &
    [engines:image_gemini]{prompt: "뇌+근육+팔+사과", style_preset: "vintage_book", aspect_ratio: "1:1", output_path: "p1_brain_arm.png"} &
    [engines:image_gemini]{prompt: "제1부 표지 분위기", style_preset: "vintage_book", aspect_ratio: "16:9", output_path: "p1_part1.png"} &
    [engines:image_gemini]{prompt: "마무리 콘텐츠", style_preset: "vintage_book", aspect_ratio: "16:9", output_path: "p1_finale.png"}
  ')

[4단계] 슬라이드 배열 구성
  - 6장에 일러스트, 나머지 9장은 lecture_body / comparison_table / factbox / quote
  - 통합형 레이아웃 키 정확히 매칭 (image_data vs left_image_data/right_image_data)

[5단계] 슬라이드 데크 생성
  execute_ibl(code='[engines:slide_shadcn]{
    design_system: "vintage_book",
    slides: [
      {layout: "hero_illustration", eyebrow: "하네스란 무엇인가",
       title: "하네스 — AI 시대의 새로운 몸",
       subtitle: "문자 이후, 두 번째 언어의 탄생과 인간의 조건",
       image_path: "/abs/p1_cover.png", footer: "원작: 강국진"},
      {layout: "lecture_body", title: "...", body: "..."},
      {layout: "illustration_anchor", eyebrow: "메타포",
       title: "햄릿의 무대", body: "...", image_path: "/abs/p1_hamlet.png"},
      {layout: "split_concept",
       title: "AI 모델만으로는 세계를 만날 수 없다",
       left_title: "뇌 (AI 모델)",
       left_body: "보편적 법칙으로 압축된 방대한 데이터",
       left_image_path: "/abs/p1_brain_solo.png",
       right_title: "몸 (하네스)",
       right_body: "특정 목적에 맞게 뇌를 감싸고 도구를 연결하는 장치",
       right_image_path: "/abs/p1_brain_arm.png",
       conclusion: "보편을 학습한 모델은 원리적으로 특수한 맥락을 스스로 공급할 수 없다."},
      ...
    ]
  }')
```

> **`image_path` vs `image_data`**: 슬라이드 엔진은 절대경로의 `image_path`를 받으면 자동으로 base64로 변환해 `image_data`에 채워준다. 호출자는 `image_path`만 신경쓰면 된다. 같은 자동 변환이 `left_image_path`/`right_image_path`(split_concept)와 `avatar_path`(testimonial), `illustration_overlay`의 `image_path`에도 적용된다.

---

## 9-B. NotebookLM 양식 워크플로우 (모드 B, sf_blueprint + illustration_overlay)

책 1부를 15장 인포그래픽 슬라이드로 만드는 경우의 전형적인 패턴.

```
[1단계] 슬라이드 기획 — 메시지 큐레이션 5단계 (lecture_slide_principles.md §2)
  ① 명제 추출: 책 1부에서 "잊으면 안 될 한 줄 명제 N개"를 먼저 뽑는다
     예: "AI 모델 ≠ AI의 실체", "나는 무지개를 직접 보지 않는다",
         "한 번의 속삭임에서 끊임없는 대화로", "팔이 없으면 문제 자체를 정의할 수 없다", ...
  ② 슬라이드 제목 = 명제 (챕터명 그대로 가져오기 금지)
  ③ 각 명제를 수사 장치에 매핑:
     - "AI 모델 ≠ AI의 실체" → 좌우 대비 → illustration_overlay (한 일러스트에 좌우 패널)
     - "나는 무지개를 직접 보지 않는다" → 단계 다이어그램 → illustration_overlay (4단 체인)
     - "컨텍스트 창이 폭발적으로 커졌다" → 수치 폭증 → illustration_overlay (4,096 → 1,000,000+ 박스)
     - "하네스는 5층 구조다" → 동심원 → illustration_overlay (계층 다이어그램)
  ④ 본문의 수치·고유명사·연도를 격리해서 라벨 박스로 (4,096 vs 1,000,000+, v0(600줄) vs v5(200줄) 등)
  ⑤ 마지막 두 장은 회수 슬라이드 고정:
     - N+1번: comparison_iconic 비교표 (과거 패러다임 vs 하네스 패러다임, 5축)
     - N+2번: illustration_overlay 동심원 (5층 구조 정리)
     - N+3번(선택): quote 인용 마무리

[1.5단계] 레이아웃·디자인 시스템 매핑 — 이제서야 시각 디자인 결정
  - 디자인 시스템: sf_blueprint
  - 표지 → illustration_background (text_align=center)
  - 부 도입 → illustration_background
  - 명제 슬라이드 N장 → illustration_overlay (수사 장치별 라벨 배치)
  - 회수 1 → comparison_iconic
  - 회수 2 → illustration_overlay (동심원)
  - 인용 → quote

[2단계] 일러스트 프롬프트 — 다이어그램형 작성
  - 각 일러스트의 "구도 + 영문 라벨 + 빈 공간 위치"를 명시
  - 라벨 위치: 한글 라벨이 들어갈 영역을 미리 빈 공간으로 비워두도록 프롬프트에 박음

[3단계] 일러스트 병렬 생성
  execute_ibl(code='
    [engines:image_gemini]{prompt: "Sci-fi HUD cover illustration: a glowing armored sphere with internal symbols, surrounded by floating wrenches and tools, deep space backdrop with faint constellations. Leave bottom 25% relatively empty for Korean title overlay.", style_preset: "sf_blueprint", aspect_ratio: "16:9", quality: "pro", image_size: "2K", output_path: "p1_cover.png"} &
    [engines:image_gemini]{prompt: "Side-by-side HUD diagram. Left: a glowing brain trapped in a transparent glass jar with arrows pointing in/out, label \"BRAIN IN A JAR\". Right: same brain with exploding glass shards and connected gears, sensors, labels \"SENSORS\" \"MEMORY\" \"ACTUATORS\" radiating outward. Cyan glow on dark navy. Leave a strip across the top 12% empty for a Korean header, and clean rectangular regions under each panel for Korean caption boxes.", style_preset: "sf_blueprint", aspect_ratio: "16:9", output_path: "p1_brain_vs_body.png"} &
    [engines:image_gemini]{prompt: "Horizontal infographic flow showing four stages from consciousness to external world: a glowing wireframe brain on the far left labeled \"BRAIN\", connecting via neural waveform to an eye cross-section labeled \"EYE/RETINA\", connecting to a rainbow labeled \"EXTERNAL WORLD\". HUD circuit traces beneath. Sci-fi blueprint style on deep navy. Leave the bottom 30% empty for a Korean explanation panel.", style_preset: "sf_blueprint", aspect_ratio: "16:9", output_path: "p1_signal_chain.png"}
    ... (12장 정도)
  ')

[4단계] 슬라이드 데크 — illustration_overlay 라벨 좌표 설계
  execute_ibl(code='[engines:slide_shadcn]{
    design_system: "sf_blueprint",
    slides: [
      {layout: "illustration_background", text_align: "center",
       eyebrow: "하네스란 무엇인가",
       title: "하네스 — AI 시대의 새로운 몸",
       subtitle: "문자 이후, 두 번째 언어의 탄생",
       image_path: "/abs/p1_cover.png"},

      {layout: "illustration_overlay",
       title: "하네스는 단순한 부속이 아닌 언어다",
       image_path: "/abs/p1_brain_vs_body.png",
       labels: [
         {text: "우리가 생각하는 AI", subtext: "(통상적 AI 모델)",
          position: "top-left", variant: "title"},
         {text: "AI의 진정한 실체", subtext: "(모델 + 하네스)",
          position: "top-right", variant: "title"},
         {text: "유리병 속의 뇌",
          subtext: ["인류의 방대한 텍스트를 압축한 보편적 지능",
                    "맥락·목적·세계관이 결여된 무력한 지능"],
          position: "bottom-left", variant: "panel"},
         {text: "새로운 몸",
          subtext: ["목적과 맥락에 맞게 모델을 감싸는 장치",
                    "도구를 연결하고 기억을 관리하며 세계를 구성"],
          position: "bottom-right", variant: "panel"}
       ]},

      {layout: "illustration_overlay",
       image_path: "/abs/p1_signal_chain.png",
       labels: [
         {text: "의식 (나)", position: "top-left", variant: "label"},
         {text: "전기 신호 (언어)", position: "top-center", variant: "label"},
         {text: "망막과 신경 (신체/타자)", position: "top-right", variant: "label"},
         {text: "외부 세계", position: "middle-right", variant: "label"}
       ],
       footer_quote: "나는 무지개를 직접 보지 않는다. 하네스란, AI 모델에게도 세계를 감각하고 전달할 \"타자의 언어\"입니다."},
      ...
    ],
    output_dir: "/abs/path/p1_notebooklm_style"
  }')
```

핵심 차이 (모드 A 대비):
- 일러스트 12~14장 vs 3~6장
- design_system + style_preset 모두 `sf_blueprint`
- 본문 슬라이드의 주력 레이아웃이 `illustration_overlay`
- 한글 본문이 일러스트 위 라벨 박스로 박힘 (lecture_body 거의 사용 안 함)

---

> **`output_dir` 옵션**: 슬라이드 데크 생성 시 `output_dir`를 절대경로로 지정하면 그 폴더에 저장된다. 미지정 시 자동으로 `outputs/shadcn_slides_<8자hex>/`에 저장. 같은 폴더에 재생성하면 기존 파일이 덮어써진다 (수정 워크플로우에 유용). 예시: `[engines:slide_shadcn]{slides: [...], design_system: "vintage_book", output_dir: "/abs/path/my_deck"}`.

---

## 10. 검증 사이클 — 한 장 먼저 시도

15장 일러스트를 한 번에 만들었다가 스타일이 안 맞으면 비용·시간 큰 낭비. **먼저 1장만 생성하고 사용자에게 확인**.

```
[1차] execute_ibl(code='[engines:image_gemini]{prompt: "첫 메타포 콘텐츠", style_preset: "vintage_book", aspect_ratio: "16:9"}')
→ 결과 PNG를 사용자에게 보여주거나 [self:read]로 확인
→ "이 스타일이 맞나요?" 물어봄 (ask_user_question)
→ OK면 나머지 병렬 생성
→ NOT OK면 프롬프트 콘텐츠 수정 후 재시도 (style_preset은 거의 손대지 않음 — 그게 일관성 자산)
```

---

## 11. 비용·할당량·실패 대응

### 모델별 비용 (2026-05)
- `quality: "fast"` (Nano Banana 2) — 1K $0.045 / 4K $0.151
- `quality: "pro"` (Nano Banana Pro) — 더 비쌈, 4K까지 정밀
- `quality: "legacy"` (Nano Banana 1) — 1K $0.039 (다른 옵션 무시)

5장 fast/1K = ~$0.225, 표지 1장 pro/4K = ~$0.151. 일반 강의 데크 비용 거의 미미.

### 할당량 초과 (429 에러)
즉시 폴백:
- `quality: "legacy"`로 재시도
- 그래도 실패하면 해당 슬라이드를 일러스트 없는 `lecture_body`/`metaphor_story`로 대체
- 사용자에게 "일러스트 생성 할당량 초과 — 텍스트로만 진행하겠습니다" 알림

### 실패 시 폴백 원칙
일러스트 생성이 실패해도 **슬라이드 데크는 만들어진다.** 해당 슬라이드의 layout을 `illustration_anchor` → `lecture_body`로 바꾸고 image_path 제거. 강의 자체가 멈추면 안 됨.

### 캐시
같은 프롬프트로 같은 이미지를 두 번 생성하지 않도록 — 한 번 만든 파일은 `output_path`를 명시해 재사용 (디렉토리에 이미 있으면 호출 생략 가능).

---

## 12. 회피해야 할 실수

**기획 단계 (가장 큰 함정):**
- **메시지 큐레이션 단계 건너뛰고 일러스트부터 만들기** — 가장 흔하고 가장 치명적인 실수. 디자인은 NotebookLM과 똑같은데 결과물이 "텍스트의 나열"이 되는 이유는 거의 항상 이것. `lecture_slide_principles.md` §2 5단계를 먼저 outline 표로 완성한 다음에야 image_gemini 호출.
- **챕터명을 슬라이드 제목으로 그대로 가져오기** — "지워진 신경신호, 그리고 몸을 주는 언어" 같은 라벨 제목 금지. 제목은 명제여야 함 (§2 ②).
- **수치·구체 사례를 본문 평문에 묻기** — 4,096 → 1,000,000+ 같은 수치는 일러스트 위 라벨 박스로 격리 (§2 ④).
- **회수 슬라이드 없이 인용으로만 마무리** — 부의 마지막 두 장은 비교표 + 체계 정리 다이어그램 (§2 ⑤).

**작성 단계:**
- **style_preset 지정 빠뜨림** — 이게 빠지면 각 일러스트가 다 다른 화풍으로 나옴. **항상 지정**.
- **프롬프트에 한글 단어 넣기** — style_preset이 "Hangul 금지"를 자동 주입하지만, 프롬프트 본문에도 영문으로만 쓸 것. (예외: sf_blueprint에서 영문 기술 라벨은 OK)
- **모드 잘못 선택** — 책 강의에서 클래식 강의록(모드 A) "3~5장만" 정책을 그대로 적용하면 NotebookLM 양식이 나오지 않음. 사용자가 "NotebookLM처럼"이라고 했다면 **모드 B + sf_blueprint + illustration_overlay**가 정답.
- **illustration_overlay 라벨 위치를 일러스트와 안 맞춤** — 일러스트의 빈 공간과 라벨 position이 어긋나면 라벨이 일러스트를 가리거나 일러스트가 라벨에 가려짐. 프롬프트 단계에서 "어디를 비울지" 명시 + 라벨 좌표 설계를 일러스트 구도에 맞춰 결정.
- **검증 없이 일러스트 한 번에 다 생성** — 스타일 안 맞으면 전부 다시. §10 사이클.
- **image_path를 상대경로로 전달** — 슬라이드 엔진은 절대경로 또는 file:// 필요. image_gemini 응답의 절대경로 그대로 사용.
- **aspect_ratio 잘못** — hero_illustration/illustration_anchor/illustration_background/illustration_overlay는 **16:9**, split_concept의 좌우는 1:1 권장.
- **너무 추상적인 프롬프트** — "좋은 일러스트" "메타포 그림" 같은 단어만 쓰면 안 됨. 구체적 객체·구성·강조점 명시. 모드 B에서는 추가로 영문 라벨까지 명시.
- **디자인 시스템과 style_preset 불일치** — slide_shadcn의 `design_system: "sf_blueprint"`이면 image_gemini도 `style_preset: "sf_blueprint"`. 반드시 매칭.
- **옛 `custom` HTML로 표지 우회 시도** — 더 이상 불필요. `hero_illustration` / `illustration_background` 사용.

---

## 13. 한 줄 요약

> 일러스트가 들어간 책 강의 슬라이드는 두 가지 모드로 만든다.
> **모드 A 클래식**: 표지+메타포 3~5장만 일러스트(`vintage_book`·`academic_paper` 등) + 나머지는 텍스트.
> **모드 B NotebookLM 양식**: **거의 모든 장이 다이어그램**(`sf_blueprint` + `illustration_overlay`) + 한글 본문은 일러스트 위 라벨 박스로.
> design_system과 style_preset을 매칭하면 한 작가가 그린 듯한 화풍이 자동 유지된다.
