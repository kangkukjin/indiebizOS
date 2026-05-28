# 강의 만들기 워크스페이스 가이드

`[self:lecture]` · `[self:slide]` · `[self:material]` · `[self:deck]` 4개 단일 액션으로 강의 슬라이드를 한 장씩 협업으로 만드는 도구. 강의별 폴더(deck.json + materials/ + slides/) 단위로 영구 상태를 유지한다.

슬라이드 *내용*에 관한 원칙(메시지 큐레이션 5단계, 챕터명 제목 금지 등)은 별도 가이드 [`lecture_slide_principles.md`](lecture_slide_principles.md)를 우선 따른다. 이 가이드는 **워크플로우와 액션 사용법**에 집중한다.

## 핵심 원리: 한 장씩 협업

채팅으로 데크 전체를 한 번에 만들면 컨텍스트 재구축·수동 조작 불가 같은 한계가 생긴다. 이 도구는 **한 슬라이드씩 만들고 즉시 검토·수정**하는 워크플로우를 강제한다.

```
[self:lecture]{op:"create", title:"하네스란 무엇인가? 1부", design_system:"vintage_book"}
→ lecture_id 생성, 폴더 + 빈 deck.json
[self:material]{op:"add", lecture_id:..., file_path:"/Users/k/.../원고.docx"}
[self:slide]{op:"create", lecture_id:..., instruction:"표지 슬라이드"}
→ 결과 PNG 검토 후 수정 or 다음 슬라이드
```

원칙: **한 장 만들고 결과 확인.** PNG 보고 수정할지 다음으로 넘어갈지 판단.

---

## 4 액션 · op 사양

### `[self:lecture]{op}` — 워크스페이스 수준

| op | 필수 | 선택 | 결과 |
|---|---|---|---|
| `list` | (없음) | — | 모든 강의 메타 요약 |
| `create` | `title` | `audience`, `thesis`, `duration_minutes`, `design_system` | 새 강의 폴더 + 빈 deck.json |
| `load` | `lecture_id` | — | deck.json 전체 + 파일 경로 |
| `delete` | `lecture_id`, `confirm:true` | — | 폴더 전체 삭제 (되돌릴 수 없음) |
| `open` | (없음) | `lecture_id` | Electron 강의 만들기 창 |

### `[self:slide]{op}` — 슬라이드 한 장 (lecture_id 공통 필수)

| op | 필수 | 선택 | AI 호출 |
|---|---|---|---|
| `create` | `instruction` | `insert_at` (0-based 삽입 위치) | ✓ |
| `edit` | `slide_id`, `instruction` | — | ✓ (현재 spec을 컨텍스트로) |
| `delete` | `slide_id` | — | ✗ |
| `patch` | `slide_id`, `patch` (객체) | — | ✗ (PowerPoint식 직접 편집) |
| `rerender` | `slide_id` | — | ✗ (design_system만 다시 적용) |

### `[self:material]{op}` — 강의 재료 (lecture_id 공통 필수)

| op | 필수 | 선택 | 동작 |
|---|---|---|---|
| `add` | `file_path` *또는* `text` + `filename` | — | 파일 모드는 복사, 텍스트 모드는 직접 쓰기 |
| `remove` | `filename` | — | materials/ 파일 삭제 + deck 갱신 |

### `[self:deck]{op}` — 데크 조작 (lecture_id 공통 필수)

| op | 필수 | 선택 | 결과 |
|---|---|---|---|
| `reorder` | `order` (slide_id 배열, 전체 포함) | — | slide_order만 갱신, 파일 안 건드림 |
| `export` | `format` (`pdf` \| `pptx`) | — | outputs/lectures/{id}/exports/ 저장 |

---

## AI 호출 op vs 직접 op (가장 중요)

| 분류 | op | 결정성 |
|---|---|---|
| **AI 호출** | `slide.create`, `slide.edit` | 비결정적. 같은 instruction이어도 결과가 달라질 수 있음 |
| **직접 편집** | `slide.patch`, `slide.rerender`, `slide.delete`, `deck.reorder`, `deck.export` | 결정적. spec 안 건드리거나 명시한 필드만 건드림 |

**언제 어느 쪽을 쓰는가:**

- "톤을 더 능동적으로" 같은 *의미 변경* → `slide.edit`
- "이 단어만 바꾸기" / "footer 추가" / "bullets 한 줄 추가" → `slide.patch`
- "design_system 바꾼 뒤 같은 내용 다시 그려" → `slide.rerender`
- spec은 그대로 두고 화면만 새로 그릴 때 → `slide.rerender`

**`patch`의 거부 조건**: `layout` 키 변경은 거부됨 (필요 필드가 달라져 spec 깨질 위험). layout 바꾸려면 `slide.edit`로 재생성하거나 삭제 후 다시 만든다.

---

## design_system 4종

`lecture.create`에서 지정. 강의 톤 결정. 중간에 바꾸려면 deck.json 직접 편집 후 `slide.rerender`로 전 슬라이드 다시 그림.

| 이름 | 톤 |
|---|---|
| `vintage_book` | 빈티지 책 — 따뜻한 베이지, 세리프, 차분 (기본값) |
| `academic_paper` | 학술 논문 — 흑백, 격식, 인용·각주 친화 |
| `tech_minimal` | 테크 미니멀 — 모노스페이스, 코드·시스템 강조 |
| `magazine_modern` | 모던 매거진 — 컬러풀, 산세리프, 활기 |

---

## 표준 워크플로우

### 1) 새 강의 시작
```
[self:lecture]{op:"create", title:"하네스란 무엇인가? 1부",
               audience:"일반인", thesis:"하네스는 도구가 아니라 작업 환경이다",
               duration_minutes:60, design_system:"vintage_book"}
→ lecture_id 받음
```

### 2) 재료 추가 (반복)
```
[self:material]{op:"add", lecture_id:..., file_path:"/Users/k/.../원고.docx"}
[self:material]{op:"add", lecture_id:..., text:"...메모...", filename:"notes.md"}
```

### 3) 슬라이드 한 장씩 만들기 (반복)
```
[self:slide]{op:"create", lecture_id:..., instruction:"표지 슬라이드"}
→ PNG 결과 검토
   - 만족 → 다음 슬라이드
   - 의미 수정 필요 → [self:slide]{op:"edit", lecture_id:..., slide_id:"s001", instruction:"톤을 더 단호하게"}
   - 단어 수정 → [self:slide]{op:"patch", lecture_id:..., slide_id:"s001", patch:{title:"새 제목"}}
[self:slide]{op:"create", lecture_id:..., instruction:"명제 1: 하네스의 본질"}
...
```

### 4) 순서 조정·삭제
```
[self:deck]{op:"reorder", lecture_id:..., order:["s003","s001","s002",...]}
[self:slide]{op:"delete", lecture_id:..., slide_id:"s002"}
```

### 5) 톤 바꾸기 (design_system 교체 후)
deck.json의 `design_system` 필드 수정 → 각 슬라이드 rerender.
```
[self:slide]{op:"rerender", lecture_id:..., slide_id:"s001"}
... 반복
```

### 6) 내보내기
```
[self:deck]{op:"export", lecture_id:..., format:"pdf"}
→ outputs/lectures/{id}/exports/{id}_{timestamp}.pdf
```

---

## 데이터 구조 (참고)

```
indiebizOS/outputs/lectures/{lecture_id}/
├── deck.json          # 메타 + slide_order + slides 맵 + cumulative_memo
├── materials/         # 재료 파일들
└── slides/            # {slide_id}.json (spec) + {slide_id}.png (렌더)
```

`deck.json` 핵심 필드:
- `title`, `audience`, `thesis`, `duration_minutes`, `design_system`
- `slide_order`: ["s001", "s002", ...] — 표시 순서
- `slides`: {slide_id: {spec_file, updated_at, ...}}
- `cumulative_memo`: AI가 슬라이드 만들면서 추출한 메타포·결정사항 (다음 슬라이드 컨텍스트로 자동 주입)
- `materials`: [{filename, type, added_at}, ...]

`slide spec`(slides/{sid}.json) 주요 필드: `layout`(예: title/bullet/two_column/quote), `title`, `bullets`, `body`, `footer`, `source` 등. layout마다 필요 필드가 다르다.

---

## 주의

- **`lecture.delete`는 영구**. confirm:true 필수. 사용자 명시적 확인 받기.
- **slide_id 안정성**: `deck.reorder`는 slide_id를 그대로 두고 순서만 바꾼다. ID 충돌·재할당 없음.
- **slide_order에 빠짐 없는 ID 배열 필수**: reorder 시 기존 슬라이드를 전부 포함해야 검증 통과.
- **`material.add`의 file_path는 절대경로**.
- **AI 호출(create/edit)은 비결정적**: 같은 instruction이어도 결과가 달라질 수 있음. 슬라이드가 마음에 들지 않으면 `slide.edit`로 다듬되 결정적 조작이 더 적합하면 `slide.patch`/`slide.rerender`.
- **AI 컨텍스트**: `slide.create`는 매 호출 self-contained (채팅 히스토리 없음). 강의 메타 + 재료 색인 + 데크 개요 + cumulative_memo만 들어감. 따라서 instruction은 명확하게 단독으로 의미가 통해야 한다.

## 관련 가이드

- [`lecture_slide_principles.md`](lecture_slide_principles.md) — 슬라이드 내용 원칙 (메시지 큐레이션 5단계, 챕터명 제목 금지)
- [`lecture_slides_with_illustrations.md`](lecture_slides_with_illustrations.md) — 일러스트 통합 레이아웃
