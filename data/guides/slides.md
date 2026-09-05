# 슬라이드 제작 가이드 (통합)

슬라이드 만드는 법은 **하나**다: `[self:slide]{op: "create"}`. 이미지 모델이 한글 글자·다이어그램·일러스트를 **한 장에 통째로 저작**한다(native, NotebookLM과 같은 방식 — 시각과 의미가 한 컴포지션에서 융합). 글자 레이어와 그림을 따로 만들어 합치던 옛 방식(2층)은 은퇴했다.

이 한 문서가 슬라이드의 전부다 — 원칙, 만드는 법, 강의 협업, 덱·내보내기까지.

---

## 1. 품질의 핵심 — 메시지 큐레이션

도구가 아니라 **이 사고**가 슬라이드의 격을 결정한다. 톤·디자인이 NotebookLM과 똑같아도 이걸 건너뛰면 "텍스트의 나열"이 된다.

### 1-0. 먼저 — 자료의 *핵심 주장(프레임)*을 잡아라 ★★ 무엇보다 먼저

장별 슬라이드를 뽑기 **전에**, 자료 전체를 읽고 *딱 한 문장*으로 답하라:

> **"이 글이 진짜 하려는 단 하나의 주장(렌즈)은 무엇인가?"**

이게 덱의 **척추**다. 그리고 반드시 지킨다:

- **1번 슬라이드 = 그 핵심 주장.** 표지부터 글의 논지가 보여야 한다.
- **덱 전체가 그 주장에 복무한다.** 모든 슬라이드는 그 주장을 *비추는 거울*이지, 제각각 흩어진 사실이 아니다.
- **저자가 스스로 내건 프레임(제목·도입부)을 보존하라.** 글 제목이 "AI에 대한 잘못된 언어들"이면, 덱의 핵심도 *언어/개념의 혼동*이다. 그걸 버리고 다른 펀치라인으로 갈아끼우지 마라.

**★실패 패턴 — 반드시 피하라 (실제로 일어난 오류):**
어떤 글이 *"잘못된 언어가 잘못된 사고(유령)를 낳는다"*를 주장하며, 그 예시로 *"AI = 보편 모델 + 하네스"* 라는 개념 혼동을 든다고 하자. 흔한 실패는 — 가장 정교하게 전개된 **예시(보편/하네스 등식)를 덱의 척추로 승격**시키고, 정작 **글의 진짜 주장(언어 혼동)을 떨어뜨리는** 것이다. *가장 단단한 논증*이나 *가장 시각화하기 쉬운 부분*이 곧 핵심 주장은 아니다. **예시를 주제로 착각하지 마라.** 자료를 줬는데 그 핵심 주장이 덱에서 안 보이면, 그건 실패다 — 변명의 여지가 없다.

### 1-1. 그다음 — 장별 큐레이션

핵심 주장을 정한 뒤, 매 슬라이드마다 거친다:

1. **명제 추출** — 원문 문단을 옮기지 말고, *핵심 주장을 비추는* 단 하나의 주장을 벼린다.
2. **제목 = 명제** — 라벨('AI의 역사')이 아니라 단정문. 단, **저자의 프레임을 버리는 펀치라인은 금지**(1-0).
3. **한 장 = 한 아이디어** — 두 가지를 말하려 하지 않는다.
4. **시각 장치로 극화** — 핵심을 글로 길게 쓰지 말고 그림이 의미를 나르게 한다. 단, *시각화하기 쉬운 것*이 아니라 *핵심 주장에 본질적인 것*을 슬라이드로. 장치:
   - equation(등식·취소선 대조) / flow(흐름도·단계·붕괴) / comparison(좌우 대비) / hierarchy(계층·동심원·피라미드) / metaphor(은유 일러스트) / bigfact(거대한 숫자·단어) / matrix·timeline.
5. **구체화** — 수치·인명·사례는 평문에 묻지 말고 큰 숫자·강조 박스로 격리. 글자는 키워드 단위(한 장 ~80자 이내).

근거가 있으면 `content`로 넘겨 인용하고 지어내지 않는다.

---

## 2. 만드는 법 — `[self:slide]{op: "create"}`

**슬라이드는 항상 덱에 산다.** `lecture_id`를 주면 그 강의 덱에, 안 주면 **스크래치 덱**(자동 생성·재사용)에 등록된다 — 만든 뒤 편집(`op:"edit"`)·순서(`[self:deck]{op:"reorder"}`)·내보내기(`export`)·나레이션→영상까지 같은 어휘로 이어진다. (구 `[engines:slide]` 단발 생성은 2026-08-05 여기로 흡수.)

### 한 장 (단발 — 스크래치 덱)
```
[self:slide]{
  op: "create",
  instruction: "AI를 마법으로 오해하는 통념을 깨고 'AI = AI 모델 + 하네스' 공식을 한 장으로 각인",
  content: "<해당 대목 원문 — 사실·표현·고유명사를 여기서>",
  aesthetic: "vintage_book"
}
```
- 렌더는 **native**(통짜 이미지)가 기본 — 따로 지정할 것 없다.
- **aesthetic(톤, 한 덱 고정 = 일관된 책)**: `vintage_book`(빈티지북 — 기본) / `blueprint`(청사진) / `architect`(아키텍트) / `ink_orange`(먹과 주황). 같은 톤의 단발 생성은 같은 스크래치 덱에 모인다.
- 옵션: `image_quality`(pro 기본/fast).

### 렌더 3단 사다리 — render 스위치 (2026-08-06 개편)
선택은 **두 축뿐**이다: **톤**(무엇처럼 보이나)과 **렌더 방식**(무엇으로 만드나). 구조(layout)는
**AI가 내용을 보고 고른다** — 사람이 고르는 축이 아니다.

| `render` | 뜻 | 비용·속도 | 나중에 편집 |
|---|---|---|---|
| `native` (기본) | 이미지 모델이 글자까지 한 장에 통째로 | 유료·느림 | 재생성만 |
| `image` | 글자 없는 그림 + HTML 타이포 합성 | 유료·느림 | 재생성만 |
| `html` | 글자도 그림도 HTML | 무료·빠름 | 필드 직접 편집 ✅ |

`render`를 명시하면 그 한 장만 덱 기본과 다른 방식으로 그린다(혼합 덱). **톤이 그 방식을
지원해야 한다** — 지원 안 하면 조용히 다른 걸 그리지 않고 명시 오류를 낸다.
- `native` 지원 톤: `vintage_book`·`blueprint`·`architect`·`ink_orange` (4톤 전부)
- `image` 지원 톤: `vintage_book` 만
- `html` 지원 톤: `vintage_book`·`blueprint`·`architect`·`ink_orange` (4톤 전부)
- ★톤을 새로 지을 때: "깨끗한 흰 배경 + 파란 강조" 같은 서술은 디자인이 아니라 **디자인의 부재**다. 살아남은 톤들의 공통점 = ①한글 디스플레이 서체 정체성 ②재질(종이·잉크·인쇄공정) ③절제된 팔레트 — 셋 다 갖춰야 등록한다.
- **★은퇴 톤 (2026-08-07 대압축 — 되살리지 말 것, 필요하면 사용자 결정 후 백업에서)**: 사용자 판정 "많기만 하고 도움 안 됨" — 실사용·완성도 기준 4톤만 존치. 은퇴: `academic_paper`·`tech_minimal`·`magazine_modern`·`dark_keynote`·`sf_hud`(구 sf_blueprint)·`ink_blueprint`·`cinematic_3d`·`isometric`·`lineart_duotone`·`swiss_grid`·`riso_print`·`botanical_plate`·`bauhaus`·`ma_quiet`·`midcentury_print`. 옛 덱의 은퇴 톤 문자열은 기본 톤으로 조용히 접힌다(기존 PNG 무손상). 정의 전문 백업 = `data/packages/_archive/retired_tones_20260807.py.txt`.
(정본은 `media_producer/slide_tones.py` — 톤이 늘면 이 목록보다 레지스트리를 믿을 것.)

`layout`은 HTML 구조 강제용으로 남아 있지만 **보통 쓰지 말 것**(자연어로 "표로 정리해줘",
"좌우로 대비해서", "자유롭게 배치해줘"가 같은 일을 한다). 쓰면 그 장은 HTML 경로로 간다:
- **shadcn 구조 레이아웃**: 강의형 `lecture_body`/`quote`/`comparison_table`/`factbox` 등 + **마케팅형** `features`(3열 카드)/`stats`(숫자)/`pricing`(가격표)/`cta`/`testimonial`/`hero_image`/`content_image`/`steps` — 피치덱·랜딩 자료는 이쪽.
- **custom(가장 일반·자유)**: `layout:"custom"` — AI가 Tailwind HTML을 자유 작성.
```
[self:slide]{op: "create", instruction: "핵심 요약 카드 한 장", render: "html", aesthetic: "architect"}
[self:slide]{op: "create", instruction: "요금제 3단 가격표", layout: "pricing"}
```

### 여러 장
슬라이드마다 같은 `aesthetic`으로 `op:"create"`를 호출한다(병렬은 `&` — 같은 스크래치 덱에 순서대로 쌓인다). 한 장 한 명제 원칙은 장마다 적용. 제대로 된 강의 덱(제목·논지·청중 컨텍스트)은 §4처럼 `[self:lecture]{op:"create"}`로 먼저 덱을 만들고 `lecture_id`를 지정한다.

---

## 3. 강의 슬라이드 = 한 장씩 협업

강의·교육 슬라이드는 **AI가 한 번에 뱉는 산출물이 아니다**. 강의자의 호흡·사고를 무시하면 "AI의 요약본"이 된다. 4대 원칙:

1. **한 번에 다 만들지 마라** — 첫 장 → 코멘트 → 다음 장.
2. **추상적 질문 금지** — "톤 어떻게 할까요?"가 아니라 항상 **구체적 선택지 2~3개 + 열린 질문 1개**.
3. **누적 메모 유지** — 강의자가 거부한 방향·채택한 톤·좋아한 메타포를 매 라운드 기록해 호흡을 학습.
4. **메시지 큐레이션(§1)을 매 장 적용** — outline을 통째로 미리 짜지 말고 한 장씩.

**흐름**: ①초기 합의(주제·청중·"절대 잊지 말 단 하나"·분량 정도만 가볍게) → ②명제 후보 5~7개 테이블로 제시 → 강의자가 ✓/✗/수정 → ③한 장씩 루프(다음 장 제안 → 코멘트 → 작성 → 메모 업데이트) → ④마무리 회수 슬라이드는 합의 후(자동 생성 금지).

---

## 4. 덱 관리·편집·내보내기 — 강의 워크스페이스

여러 장을 **하나의 덱으로 묶어 관리**(순서·편집·재생성·내보내기)하려면 `[self:lecture]` 워크스페이스를 쓴다. 렌더는 동일하게 native다.

- `[self:lecture]{op:"create", title, audience?, thesis?}` — 덱 생성. `design_system` 은 **`<렌더 접두>_<톤>`** 문법(접두 없음 = html): `native_vintage_book`(기본·통짜 이미지) / `image_vintage_book`(이미지+글자 합성) / `ink_orange`(HTML). 두 축이 문자열 하나에 인코딩된다. **4톤(vintage_book·blueprint·architect·ink_orange) × 3렌더 전부 지원**(2026-08-09 이미지+글자 3톤 확장 — illus=native 화풍의 무글자 판, 팔레트·폰트=HTML 판 승계).
- `[self:slide]{op:"create", lecture_id, instruction, content?}` — 덱에 한 장 추가(native 저작). `op:"edit"`로 특정 장 재생성, `op:"delete"`/순서 조정.
- `[self:slide]{op:"image_edit", lecture_id, slide_id, instruction}` — **통짜 이미지/이미지 슬라이드 부분수정**: 다시 그리지 않고 현재 PNG를 편집(제목 한 줄만 바꾸기 등). 전체 재생성보다 싸고 구도가 유지된다. 글자가 PNG에 구워진 장(layout이 `native`/`composite`/`image`)에만 — HTML 슬라이드는 `op:"patch"` 필드 편집.
- `[self:slide]{op:"image_edit", lecture_id, slide_id, overlay_text:"자료: 국토부 2026", overlay_position:"bottom-right"}` — **결정론 '글자 얹기'**: 이미지 모델을 부르지 않고 현재 그림 위에 문구만 합성(그림 픽셀 완전 보존·즉시·무료). "이미지 구석에 한 줄만 넣고 싶다"가 이 경로 — instruction(모델 편집)과 달리 그림이 절대 안 달라진다. 옵션 `overlay_position`(9방: top-left|top|top-right|left|center|right|bottom-left|bottom|bottom-right, 기본 bottom-right) 또는 **자유 좌표** `overlay_x`/`overlay_y`(박스 좌상단, 슬라이드 폭·높이의 % — position 보다 우선)·`overlay_size`(small|medium|large) 또는 `overlay_size_vw`(자유 크기, 폭의 % 0.5~12)·`overlay_width`(**글상자 폭**, 슬라이드 폭의 % 5~100 — 좁히면 긴 문구가 그 폭에서 자동 줄바꿈되어 2~3줄이 된다. 생략하면 내용 폭·70% 상한. 편집기에서는 선택한 박스의 주황 손잡이 드래그 또는 '폭' 슬라이더, 문구 칸의 Enter 로 직접 줄바꿈)·`overlay_font`(sans 고딕|serif 명조|gowun 고운바탕|jua 둥근 제목|black 헤드라인|pen 손글씨|brush 붓글씨 — 웹폰트는 Google Fonts, 오프라인=시스템 폴백)·`overlay_shadow`(글자 그림자, **기본 없음** — 배경과 색이 비슷해 안 보일 때만 true)·`overlay_color`(white|black|#hex)·`overlay_chip`(true=반투명 배경칩)·`overlay_set`(오버레이 객체 배열로 전체 교체 — 강의 창 🎯 배치 편집기의 저장 경로, 빈 배열=원본 복원). 강의 창에서는 **🎯 배치 편집**(글자 얹기 모드)으로 글자 박스를 마우스 드래그·크기 슬라이더·서체·색 피커로 PowerPoint식 직접 조작 가능. 원본은 `{slide_id}.base.png` 로 자동 보존되어 여러 번 얹어도 겹겹이 안 구워지고, `overlay_clear:true` 로 전부 지우고 원본 복원. 이후 모델 편집(instruction)·재생성을 하면 얹은 글자는 그 픽셀에 구워진 것으로 확정된다.
- `[self:slide]{op:"patch", lecture_id, slide_id, patch:{title:"..."}}` — **이미지+글자(composite) 슬라이드의 글자 직접 수정**: 텍스트 필드(title/kicker/subtitle/body/bullets/captions/labels/steps)만 patch 하면 보존된 원료 일러스트(`{slide_id}_img.png`)로 **그림 그대로 재합성**(이미지 모델 호출 0, 글자 얹기와 같은 원리). 강의 창에서는 composite 카드의 ✏️(글자 직접 편집). scene·composition·style 변경은 재생성(edit) 경로. native/image 통짜는 여전히 patch 불가.
- `[self:slide]{op:"note", lecture_id, slide_id, note}` — **스피커 노트(말할 내용) 설정**. AI 0·렌더 0·PNG 무접촉.
  덱 한 벌에 한꺼번에 달려면 `notes` 객체(키=slide_id, 값=노트)로 일괄. 빈 문자열 = 그 장의 노트 제거.
  없는 slide_id 는 `missing` 으로 신고한다(조용히 삼키지 않는다 — 노트 없는 장은 **무나레이션 씬**이 된다).
  ★노트는 spec 이 아니라 덱 메타다 — `op:"patch"` 로는 못 단다(patch 는 시각 필드 전용이고 native 슬라이드는 거부).
  노트 = `[self:deck]{op:"video"}` 의 나레이션 원문이므로, 원본 전사문이 있으면 그 문장을 그대로 옮기는 게 가장 좋다.
- 덱은 폴더 단위로 영속(슬라이드 PNG + deck.json).
- **동영상**: `[self:deck]{op:"video", lecture_id}` — 슬라이드+스피커 노트를 TTS 나레이션 MP4 로(백그라운드, video_workflow.md 참조).
- **내보내기**: `[self:deck]{op:"export", lecture_id, format:"pptx"}` — 덱의 슬라이드를 순서대로 묶는다. format은 `pptx`(슬라이드당 풀블리드 이미지·디자인 완벽 보존) / `pdf`(다중 페이지) / `pptx_editable`(텍스트박스 분해 — native 슬라이드는 구운 이미지라 통짜로 보존되지만, **'글자 얹기'로 올린 문구는 원본 그림 + 편집 가능한 진짜 텍스트박스**로 분해되어 PPT에서 수정·이동 가능). NotebookLM처럼 .pptx로 받을 때 이걸 쓴다. / `images`(**이미지 폴더** — 슬라이드 각 장을 순번+제목 PNG 파일로 폴더 하나에 복사하고 같은 이름 ZIP 도 생성. 다운로드 전달체=ZIP, 로컬에선 exports/ 안 폴더가 바로 산출물. 통화에 `folder`/`path`(zip) 둘 다 온다).

> native 덱은 톤만 다시 입히는 rerender가 아니라 **재생성**(edit/create)이 맞다 — 통짜 이미지라 그렇다.

---

## 5. 원칙 요약

- 슬라이드 만드는 길은 `[self:slide]{op:"create"}` 하나 — lecture_id 없으면 스크래치 덱. 덱 관리는 `[self:lecture]`/`[self:deck]`.
- native(통짜 이미지)가 기본.
- 품질은 도구가 아니라 **메시지 큐레이션**(§1)에서 나온다. 책 본문을 옮기지 말고 명제를 추출하라.
- 강의는 한 장씩 협업(§3).

## 실측 기록 (자동 누적)
- 2026-09-05 실측: '글자 얹기'(overlay_text)는 백엔드가 아니라 프론트에서 막혀 있었다 — `frontend/src/components/lecture/chat.tsx:66-68` 의 `focusBaked = native|composite|image` 블록 안에만 버튼이 있어 `layout:"custom"`(HTML) 슬라이드에는 렌더 자체가 안 됐다.
- 2026-09-05 실측: 한 덱 안에 native/image/composite/custom 이 섞여 있으면(해당 강의 s064·s066만 custom) 특정 순번 슬라이드에서만 옵션이 사라지는 형태로 증상이 나타난다 — 슬라이드 번호가 아니라 그 장의 layout 을 먼저 실측할 것.
- 2026-09-05 실측: #repair 로 만든 수정이 격리 사본(proposal-20260905_162707 워크트리)에만 쌓여 있으면 시스템을 재기동해도 라이브 코드에는 없다 — '재기동했는데 그대로'는 코드 미적용을 먼저 의심해야 한다.
- 2026-08-29 실측: data/criteria/ 에는 visual_base.yaml·web.yaml·sheet.yaml 3개뿐 — 슬라이드 전용 기준 파일이 없다(§1 메시지 큐레이션은 산문 지침으로만 존재하고 데이터화된 기준이 아니다).
- 2026-08-29 실측: 실측 규모: media_producer 핸들러 6,115줄 / lecture_workspace 4,677줄 / web-builder 2,278줄 — 슬라이드 어휘층 두께는 전용 도구와 견줄 수준이고, 품질 열세의 병목은 어휘가 아니다.

> 실행 에이전트가 턴 종료 후 덧붙인다.
- 2026-08-29 실측: 톤 목록(TONES)은 `slide_tones.py:57`에 있지만 톤의 실제 정의 본문(팔레트·폰트·재질, 6,316B/98줄)은 `slide_styles.py`에 따로 산다 — 가이드가 정본으로 지목한 slide_tones.py만 보면 톤 '내용'은 측정되지 않는다.
- 2026-08-29 실측: 웹 테마는 슬라이드 톤과 완전히 별개 레지스트리(`edit_styles.py:43` THEME_PRESETS, 6종)로 산다 — 슬라이드 4톤과 개수·정의 형식이 다르고 서로 참조하지 않는다.
