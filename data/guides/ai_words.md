# 원샷 AI 낱말 가이드 — [self:struct] · [table:ai] · [table:brief]

원샷 AI 호출을 IBL 파이프의 시민으로 승격한 세 낱말(ai-ops 패키지, 2026-08-19).
정본 설계 = `docs/ONESHOT_VOCAB_DESIGN.md`.

## 언제 쓰나 — 세 자리

파이프의 어느 자리에 의미 판단이 필요한가로 고른다:

| 자리 | 낱말 | 형태 | 대표 용례 |
|---|---|---|---|
| 입구 | `[self:struct]{file\|text, schema}` | 비정형 → items | 영수증·문서 이미지→레코드, 크롤 본문→목록 |
| 중간 | `[table:ai]{instruction}` | items → items | "광고성 행 제거", "각 행에 요약 필드 추가" |
| 출구 | `[table:brief]{instruction}` | items → 산문 | "3문장 보고", "어느 것이 최적인지 판정" |

**규칙으로 적을 수 있으면 결정론 낱말이 먼저다** — filter/sort/take 는 싸고 결정적이며 dry-run 이 초록불을 켠다. AI 낱말은 규칙으로 못 적는 판단에만.

## 조합 예

```
# 수집 → 의미 선별 → 산문 보고 → 저장
[sense:search]{query: "청주 창업 지원", source: "naver"} >> [table:ai]{instruction: "실제 지원사업 공고만"} >> [table:brief]{instruction: "마감 임박 순 3문장 보고"} >> [self:write]{path: "outputs/브리핑.md"}

# 크롤 본문 → 구조화 → 필터
[sense:crawl]{url: "https://..."} >> [self:struct]{schema: "행사명, 날짜, 장소"} >> [table:filter]{where: {"장소": "청주"}}

# 영수증 이미지 → 재무 레코드 (grounded 는 finance/health 스키마에서 자동 on)
[self:struct]{file: "영수증.jpg", schema: "finance"}
```

## 계약 (낱말의 자격 = 검증 관문)

- **모델 = 기어 실행 축** — `self:ask`(경량 단답)와 다르다. 실행 에이전트와 같은 지능. 이미지 입력은 비전 패스스루(Gemini — 모달리티는 기어 무관).
- **JSON 검증 + 재시도 1회 + 정직 실패** — 빈 결과로 위장하지 않는다.
- **행 수 신고** — `table:ai` 는 rows_in/rows_out(+rows_dropped)을 항상 동반(조용한 깎기 금지).
- **grounded**(struct) — 각 레코드에 원문 발췌 `_quote` 를 요구하고 **코드가 원문과 대조**(notebook 인용 후검증 부류). finance/health 원장 스키마=기본 on, 그 외 off, `grounded:` 파라미터로 오버라이드. 탈락 수는 `dropped_ungrounded` 로 신고, 전멸=정직 실패.
- **_ai provenance** — 출력 items 행에 `_ai: true`.
- **비용 = 집합 단위 1호출** — items 전체를 한 번에. 입력 상한(6만 자) 초과=정직 거절(take/filter 로 줄이기). 0행 입력=**세 낱말 모두 호출 생략(비용 0)·빈손 성공** — `table:ai` 는 `items:[]`, `brief` 는 `message` 없이 `note`+`rows_in:0`(F20-3 판정 2026-08-22: 0행은 고장이 아니라 정당한 빈손이다. 감시자 문형 `[table:since] >> [table:brief]` 이 첫 실행마다 error 로 끝나던 원인). **통화 자체가 없으면 여전히 정직 거절** — 두 갈래를 섞지 말 것.
- **`ai_call: true`** — dry-run 이 "실행마다 모델 호출(비용·편차)" 을 고지하고, 포털 대여 계기에서는 기본 거부된다.

## criteria — 품질 계약 (2026-08-27 언어 개정)

원샷 낱말의 지배적 실패는 예외가 아니라 **그럴듯하지만 나쁜 출력의 성공 반환**이다.
출력이 표면(write·notify·발행)으로 직행하는 자리에는 `criteria` 로 기준을 선언하라:

```
[sense:feed]{url: "…"} >> [table:brief]{instruction: "급변 종목 3문장 보고",
                                         criteria: "종목명·수치 포함, items 에 없는 주장 없음"}
```

- 엔진 소유 런타임 메타 param — 핸들러에 도달하지 않고, 실행 직후 판정자가 심사한다. 판정자의 모델 수준은 **기어의 평가 축**(role=evaluate — GoalEval 평가자와 같은 축)이 정한다: 절약·균형=경량, 최대=고급.
- **미달 → 재시도 1회**(판정 사유를 instruction 에 얹어 재실행 — ai_call+instruction 선언 낱말만) → 재판정 → 그래도 미달이면 `error_type: "quality"` 실패. 트레이스백이 그 step 을 가리키고 `rejected_result` 에 미달 출력이 남는다.
- 통과=`criteria_verdict: "pass"`, 재시도 통과=`pass_after_retry`+`_criteria_retried`(정직 표지 — 출처가 재시도본), 판정 불능=통과+`unjudged` 신고.
- **비용**: step 당 판정 최대 2회+재실행 1회의 추가 원샷. 규칙으로 적을 수 있으면(행 수·필드 유무) filter/take/스키마 가드가 먼저다 — criteria 는 의미 품질 전용.
- ★`[engines:image_read]{op:"critic"}` 의 criteria 는 그 도구 자신의 입력이다(화면 심사 기준) — 액션이 선언한 param 이 항상 이긴다.

## 함정·경계

- **지시문 자리는 `instruction`** — `do` 는 IBL *문장*을 나르는 자리(each·schedule)라 자연어 지시에 쓰지 않는다(별칭 do·prompt 는 수용).
- `[table:structure]` 와 구분: structure=텍스트→**문서 IR**(조판용, 경량 편집장) / struct=비정형→**레코드 items**(데이터화, 실행 축) / brief=items→**산문**.
- 이미 표인 입력은 `[self:read]{tables:true}`(결정론 표 추출)가 먼저다.
- 평문 텍스트 요약·질문은 `[self:ask]{prompt}` — brief 는 items 통화 전용.
- 행별 독립 처리가 정말 필요하면 `[table:each]{do: "[table:brief]{...}"}` — limit(기본 20)만큼 모델 호출이 곱해지니 집합 호출이 기본.
- 다단·도구 루프가 필요한 작업은 원샷의 영토가 아니다 — 자율주행(위임)으로.
