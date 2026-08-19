# 원샷 낱말 설계 — 통화 대수 세 자리 (ONESHOT VOCAB DESIGN)

**작성일**: 2026-08-19
**상태**: ✅ 구현 완료 (2026-08-19 — 판정 4건 전부 권고안대로 확정·집행, §12 구현 기록 참조)
**선행 문서**: `outputs/IBL_어휘_원자성_감사보고서.md`(2026-08-18) · `docs/HIGHER_ORDER_SENTENCE_DESIGN.md`(each 선례) · `backend/services/ingest_engine.py` 머리 주석(4층 분해)

---

## 0. 한 줄 요약

**원샷 AI 호출을 IBL 파이프의 시민으로 승격하되, 낱말은 통화 대수의 세 자리(입구·중간·출구)에 하나씩 둔다. 모델은 기어 실행 축을 타고, 낱말의 자격은 AI 호출이 아니라 그 뒤의 결정론 검증 관문이 만든다.**

---

## 1. 배경 — 왜 지금인가

### 1-1. 실증: 앱 개발 관행이 이미 18번 증명했다

`oneshot_ai_call`은 15개 파일·약 18개 호출부에서 재사용된다(감사 보고서의 "42곳"은 grep 총 언급 수 — import·def 포함 — 로 과장이며, 실호출은 18곳). 전부 같은 패턴이다: **결정론 파이프라인을 짜다가 의미론적 이음매(비정형→구조화, 선별, 판정, 작명, 요약)에 도달하면 원샷 AI를 함수처럼 꽂아 돌파한다.**

- ingest_engine `extract_records`(영수증·문서→레코드), 신문 편집장 일괄 curate, 플레이리스트 2단 선곡·작명, 무의식 분류기, 평가자, 기억 정리 병합, 포식 증류…

그런데 이 돌파술이 IBL **문장 안**에는 없다. 파이프 중간에 의미 판단이 필요해지는 순간 문장 전체가 불가능해지고 작업이 자율주행(풀 에이전트 루프)으로 승격된다. 유일한 노출인 `self:ask`는 `returns: scalar`(경량 단답)라 통화를 내지 못한다.

### 1-2. 함의: 결정화 사다리가 "AI 판단이 낀 작업"까지 내려온다

현재 결정화(자율주행→조종실→앱)는 순수 결정론 흐름만 담는다. 원샷 낱말이 생기면 "수집→AI 선별→조판", "올리기→구조화→저장", "수집→요약→보내기" 같은 반(半)의미론적 흐름이 **문장 한 줄**로 결정화된다. 풀 에이전트 루프(시스템 프롬프트+히스토리+도구 왕복 N턴) 대비 토큰이 크게 줄면서 지능은 유지되는 것 — 이것이 이 설계의 지능 증분이다.

### 1-3. 실사용 분포가 설계를 결정한다

18개 호출부를 통화 대수의 자리로 분류하면:

| 자리 | 형태 | 실사용 예 | 비중 |
|---|---|---|---|
| **입구** | 비정형 → items | extract_records(영수증·문서·이미지), 자막→구조화 | 굵음 |
| **중간** | items → items | 편집장 curate(기사들→선별), 기억 병합 | **소수** |
| **출구** | items → 산문·판정·이름 | 평가자 판정, 분류, 작명, 요약 | **최다** |

★ **items→items 단일 형태로 잠그면 조합성이 줄어든다** — 실사용의 다수(입구·출구)를 배제하기 때문. 세 자리 전부 연다.

---

## 2. 설계 원리 (헌법 정합)

1. **낱말 수 = 타입 시그니처 수.** 검수기(dry-run)가 파이프를 타입 체크하려면 낱말의 returns 가 정적으로 하나여야 한다. 낱말 하나가 do 내용에 따라 items 를 냈다 산문을 냈다 하면 "한 returns 라벨 아래 이질적 출력" 균열을 새 낱말에서 재생산하는 것. → **자리마다 낱말 하나, 총 3개.** filter 와 document 가 딴 낱말인 것과 같은 이유다.
2. **같은 시그니처 안에서는 낱말 증식 금지.** map/judge/extract/curate 를 쪼개지 않는다 — 의미는 `do` 지시문이 나른다(반-어휘-증식: 새 어휘의 기본 답=스크립트 등록을 이기려면, 낱말은 대수적 자리만 표시하고 의미는 데이터가 나른다).
3. **명사의 자리**: schema·do 는 자유 텍스트/라벨 = 세계의 명사는 데이터가 나른다. 코드에 도메인 스키마 이름을 박지 않는다.
4. **기존 복합어와 공존, 은퇴 아님.** `finance{op:ingest}`·`health{op:ingest}`·`video{op:summarize}` 등은 빈도 높은 흐름의 결정화된 낱말로 존치(결정화 사다리 원칙). 원자는 그 옆에 서서 **새 조합**을 연다.
5. **`self:ask` 현행 유지.** 경량 scalar 단답이라는 정직한 정체성 그대로. ask 에 items 반환 모드를 얹는 확장은 금지(원리 1 위반).

---

## 3. 낱말 명세 (3개)

> 이름은 전부 **가칭** — 최종 명명은 사용자 판정(§10). 아래는 계약 명세.

### 3-1. 입구 — `[self:struct]` (가칭): 비정형 → items

```
[self:struct]{file|text|url, schema, do?}  → returns: items
```

- **입력**: `file`(경로 — 이미지·PDF·텍스트), `text`(직접 본문), `url` 중 하나. 운반·원문 추출은 `ingest_engine.extract_source`(①②층) **재사용** — 이 엔진이 이미 분해를 갖고 있어 구현 비용이 낮다는 것이 감사 보고서의 핵심 발견.
- **schema**: 자유 라벨(예: `"finance"`, `"명함"`) 또는 필드 명세 텍스트. 도메인 원장 스키마와의 사상은 데이터(패키지 yaml)로.
- **출력**: `{items:[...]}` 통화. 이후 filter/each/save 로 자유 조합.
- **경계**: `self:read{tables:true}`(결정론 표 추출)와 구분 — read=이미 표인 것을 기계적으로 뽑음 / struct=비정형을 **의미론적으로** 구조화. 입력이 이미 정형이면 struct 가 아니라 read 를 쓰라고 desc 에 명시(동음이의 방지).
- **예문**: `[self:struct]{file:"영수증.jpg", schema:"finance"} >> [table:filter]{where:"amount > 50000"} >> [self:finance]{op:"save"}`

### 3-2. 중간 — `[table:ai]` (가칭): items → items 의미론적 변환자

```
... >> [table:ai]{do, schema?} >> ...  → returns: transform
```

- **입력**: 파이프 통화(items 집합 전체를 **한 호출**에 넣는다 — §6).
- **do**: 자연어 지시("광고성 행 제거", "각 행 한 줄 요약 추가", "중요도순 5개만"). 의미 분화의 유일한 축.
- **schema**(선택): 출력 행 필드 강제. 생략 시 입력 필드 보존+추가만 허용.
- **출력**: items(transform). filter/sort 의 의미론적 형제.
- **예문**: `[sense:search]{q:"청주 창업 지원", source:"naver"} >> [table:ai]{do:"실제 지원사업 공고만 남기고 마감일 필드 추가"} >> [table:sort]{by:"마감일"}`

### 3-3. 출구 — `[table:brief]` (가칭): items → 산문 봉투 (의미론적 emitter)

```
... >> [table:brief]{do}  → returns: scalar (산문/문서 봉투)
```

- **자리**: emitter 가족(chart·spreadsheet·document·structure)의 형제. `table:document`가 결정론 조판이라면 brief 는 **AI 종합**이다. returns 는 `structure`(scalar) 선례를 따른다.
- **출력**: 산문 봉투 — write 싱크의 산문 관례(2026-08-17 v4 정본)와 blocks IR 렌더(notebook ask 선례)에 그대로 접속. 판정·작명·요약이 전부 이 자리(출력이 산문/단문이라는 공통 시그니처).
- **예문**: `[sense:stock]{op:"quote", symbols:[...]} >> [table:brief]{do:"어제 대비 급변한 종목 중심으로 3문장 보고"} >> [self:notify_user]{message:"$prev"}`

---

## 4. 모델 축 — 기어 실행 축을 탄다 (사용자 결정, 2026-08-19)

**세 낱말 모두 `model_resolver`의 실행 축을 참조한다. 경량 고정도, 본격 하드코딩도 아니다.**

근거:
1. **등가교환**: 이 낱말은 실행 에이전트의 한 턴을 문장 안으로 접은 것이다. 대체물이 원본보다 멍청하면 사용자가 "버튼판이 직접 시키는 것보다 못하다"를 학습하고 결정화 사다리가 무너진다.
2. **기존 티어 논리 정합**: Reflex→경량의 근거는 "새 사고 없음", EXECUTE 실행 축→본격의 근거는 "실제 작업 품질 방어"였다. 원샷 낱말은 데이터를 놓고 새 의미 판단을 하는 자리 = 명백히 후자 부류.
3. **능력 문제**: 경량·중급(딥시크)은 비전이 없다(2026-08-13 실측 400). 입구 낱말의 대표 용례가 이미지 구조화이므로 경량 배치는 품질 저하가 아니라 **기능 부재**다.
4. **주권 보존**: 실행 축 참조이므로 절약 기어에서는 원샷도 같이 내려간다 — 조종실 기어 레버가 지배한다는 헌법 유지. 모델 이름을 낱말 정의에 박지 않는다.
5. **폰 몸**: 폰 기어 기본=균형(실행=중급 v4-flash·비전 없음) → 입구 낱말의 이미지 입력은 폰에서 **정직 거부**(텍스트 입력은 동작). 08-13에 분류한 "낮은 기어 비전 한계" 부류 — 새 부채 아님. `runs_on: anywhere`.

---

## 5. 정직성 관문 — 낱말의 자격은 검증이 만든다

AI 낱말은 파이프 침묵 실패(P-계열)의 최대 발생원이 될 수 있다(환각 행이 items 로 흘러들면 하류 전체 오염). 방어는 낱말 안에 내장한다:

1. **스키마 강제 + 재시도 1회**: 출력을 JSON 스키마로 검증, 불일치 시 오류를 되먹여 1회 재생성, 재실패 = **정직 실패**(빈 items 로 위장 금지 — B8 부류 재발 방지).
2. **행 수 보존 규율**(table:ai): do 가 명시적으로 행을 줄이라는 지시가 아니면 입력 행 수 ≠ 출력 행 수일 때 `_dropped` 카운트를 결과에 동반(조용한 깎기 금지 — silent-clamp 부류).
3. **근거 고정**(struct, 선택): `grounded: true` 시 각 레코드에 원문 인용 필드를 요구하고 **코드가 원문에서 결정론 대조**(notebook 인용 후검증 선례 이식). 재무·건강 등 원장 적재 전 단계에 권장.
4. **provenance**: 모든 출력 items 에 `_ai: true` 마킹 — 하류·증류·감사가 AI 산출임을 안다.

---

## 6. 비용은 티어가 아니라 호출 모양으로 다스린다

- **기본 = 집합 단위 원샷**: items 전체를 한 호출에 넣는다(신문 편집장 일괄 curate 선례). 문장당 원샷 호출은 보통 1~3회로 수렴 → 본격 티어를 쓰고도 풀 에이전트 대비 토큰 절감 유지.
- **each 결합은 행별 독립 처리가 정말 필요할 때만**: `[table:each]{do:"[table:brief]{...}"}` 는 limit(기본 20)이 이미 상한을 건다. 검수기는 each×AI 결합에 "최대 N회 AI 호출" 경고를 표시(§7).
- **페이로드 상한**: 집합 호출의 입력 items 가 모델 컨텍스트를 넘으면 정직 거절 + "take/filter 로 줄이거나 each 로 나누라" 안내(조용한 절단 금지).

---

## 7. 표면별 취급 — 0토큰 계약의 표시 의무

앱 표면의 약속은 "결정화된 문장 = 0토큰 결정론"이었다. AI 낱말이 낀 문장은 실행마다 토큰이 들고 출력이 비결정적이다. **금지가 아니라 표시 의무**로 푼다:

1. **소스 플래그**: 세 낱말에 `ai_call: true` 신설(each 의 `side_effect: true` 와 같은 계층의 검수 신호). dry-run 은 초록불 대신 "이 문장은 실행마다 AI 호출 N회·비용 발생·출력 편차 있음" 고지.
2. **앱 매니페스트**: `app:` 블록 파생 시 AI 낱말 포함 모드에 비용 배지 전파(두 렌더러 동기).
3. **포털 대여 계기**: AI 낱말 포함 템플릿은 **기본 노출 금지**(min_level 무관) — 외부인 클릭이 곧 내 모델 비용. 개별 허용은 포털 limits 판정과 함께 별도 결정.
4. **검수기 타입 체크는 그대로 산다**: returns 가 정적이므로 파이프 성립 여부는 실행 전에 판정 가능. 비결정은 내용이지 타입이 아니다 — 이것이 §2-1 (자리마다 낱말 하나)의 대가로 얻는 것.

---

## 8. 배치와 층 — 어디에 사는가

### 8-1. 권고: 패키지 fragment (표준 개정 회피)

`table` 노드의 13개 변환자·emitter 는 이미 **data-ops 패키지 fragment**에 산다(코어 src 에는 each 만 — 실행이 엔진 재귀라 층 역전 때문). AI 낱말은 엔진 재귀가 아니라 **모델 접근**이 필요하므로 each 와 사정이 다르다:

- **구현 경로**: 신규 패키지(가칭 `ai-ops`) 또는 data-ops 동거 → handler 가 services 층 파사드(가칭 `backend/services/oneshot_facade.py` — ingest_engine 이 cognition 의 oneshot_ai_call 을 쓰는 기존 층 관계 그대로) 경유. **층 역전 없음** (finance handler→ingest_engine 선례).
- **거버넌스**: 패키지 fragment = 개인 사전(내용어) 취급 → `STANDARD_CORE_NODES` 표준 개정 **불요**. table 노드는 always_on 이라 fragment 기여 액션도 노드 on/off 에서 생존.
- **입구 낱말**(self:struct)은 self 노드 fragment(system_essentials 또는 ai-ops).

### 8-2. 대안 (기각 사유 명시)

- 코어 src(table.yaml) + router:system: 표준 기능어 선언 = 언어 개정 절차(ibl.md '언어의 경계' + STANDARD_CORE_NODES 동시 갱신). **아직 이르다** — 실사용이 기능어급임을 증명하면 그때 승격(each 도 실측 후 개정했다).
- self:ask 확장: §2-5 에서 금지.

---

## 9. 하지 않는 것 (명시적 비목표)

1. `self:ask` 에 items 반환 모드 추가 — returns 이중화 금지.
2. `finance/health{op:ingest}`·`video{op:summarize}` 등 복합 op 은퇴 — 공존이 원칙.
3. map/judge/extract/curate 낱말 분화 — do 가 나른다.
4. 실패 시 경량 모델 폴백 — 티어 강등은 조용한 품질 편차. 실패는 정직 반환.
5. 루프·자기교정 다단(에이전트化) — 원샷은 원샷이다. 재시도는 스키마 불일치 1회뿐. 그 이상이 필요한 작업은 자율주행의 영토.

---

## 10. 열린 판정 (사용자 몫)

| # | 판정 | 후보 | 권고 (2026-08-19) |
|---|---|---|---|
| 1 | **이름 3개** | 입구: `struct` / `extract` · 중간: `ai` / `refine` · 출구: `brief` / `compose` / `digest` | **struct / ai / brief** — extract=ingest 내부 함수명·결정론 추출과 동음이의 / ai=수단이 곧 개념인 드문 경우+dry-run 가독성(문장에 비용 지점이 보임)+최단 / brief=요약·판정·작명 공통 시그니처("items→짧은 산문"), compose=은퇴 음악 compose 어형 충돌·digest=요약 전용. ★struct↔table:structure 혼동 대조 시드 필수 |
| 2 | 배치 | §8-1 권고(패키지 fragment) 승인 여부 | **승인 + 신규 `ai-ops` 패키지**(data-ops 동거 비권장 — data-ops의 "모델 접근 없음" 정체성 보존, 세 낱말+oneshot 파사드 응집. self:struct 도 동거) |
| 3 | 포털 노출 | AI 낱말 포함 계기의 기본 금지(§7-3) 확정 여부 | **기본 금지 확정** — 실행 축=본격이라 손님 클릭 1회=본격 모델 비용, 포털 한도=횟수 회계지 토큰 회계 아님(유튜브 tune "익명=공개 프록시화 금지" 판정과 같은 부류). 개방은 후일 "회원 전용+강화 한도+토큰 회계" 조건부 별도 판정 |
| 4 | grounded 기본값 | struct 의 근거 고정을 원장 적재 스키마(finance·health)에서 기본 on 으로 할지 | **스키마 조건부** — 원장 적재 스키마=기본 on(환각 레코드의 원장 오염=가장 비싼 하류 침묵 실패, 검증 비용은 notebook 후검증이 실증, 탈락 수 명시 보고) / 일반 구조화=기본 off(근거 필드 강제=스키마 오염·과잉) / `grounded` 파라미터로 양방향 오버라이드 |

---

## 11. 검증·측정 계획

1. **배터리**: 세 낱말 × {정상/스키마 불일치 재시도/재실패 정직/페이로드 초과 거절/행 수 보존/each 결합 limit/폰 이미지 정직 거부} + P-계열 회귀(test_pipe_currency_failures.py) 통과.
2. **빌드 가드**: `build_ibl_nodes.py --check` 전 가드 + `ai_call` 플래그 검증 합류.
3. **시딩**: 자리별 용례 세트(입구·중간·출구·조합 문장) — **파이프라인 모양으로 시드**(단발 시드=반사 오발 역효과, reflex-veto 교훈). add_examples_batch(manual_seed) + `_load_model_sync` 후 재색인.
4. **재학습 대기열 합류** 후 라이브 번역 일반화 실증(조종실 번역기가 세 낱말 문장을 생산하는지).
5. **문법 교육**: `12_ibl_only.md` 에 자리별 정형 예시 1줄씩(번역기는 read_guide 없음 — 이 줄이 유일 교본) + guides/ai_words.md 신설 + guide_db 등록. vocab_change_docs 의무(checklist + 7표면).
6. **측정**: `scripts/vocab_composition_metrics.py` 4지표(파이프 길이 중앙값·미조합 수·문형 수·파트너 다양성) 전/후 비교 — ★조합률 시딩 부풀림 금지 원칙 유지. 성패 기준은 승격 자체가 아니라 **실사용 증류에서 세 낱말 문장이 자연 발생하는가**(수 주 관찰).

---

## 12. 구현 기록 (2026-08-19 — 판정 4건 확정 후 당일 구현)

**확정된 판정**: ①이름 = `self:struct` / `table:ai` / `table:brief` ②배치 = 신규 **ai-ops 패키지**(fragment, 표준 개정 회피) ③포털 = AI 낱말 기본 거부 ④grounded = 원장 스키마(finance/health)만 기본 on.

**설계 대비 변경 2건**:
- 지시문 파라미터 `do` → **`instruction`** (§3-2·3-3 수정): `do` 는 IBL *문장*을 나르는 자리(M1 통일 — each/schedule/trigger)라 자연어 지시에 쓰면 개념이 흐려진다. `table:structure` 의 instruction 선례를 따름(param canon: 같은 개념=같은 이름). `do`·`prompt` 는 aliases 로 수용.
- `table:ai` 의 schema 파라미터 → **`fields`**(출력 행 필드 강제 배열): items→items 자리에서 "스키마"는 필드 목록이 정직한 이름.

**구현 자산**:
- 공용 관문 `backend/services/oneshot_facade.py` (execution_oneshot·oneshot_json[재시도 1회]·records_gate·grounded_filter·mark_ai) — LAYERS services 등재.
- 패키지 `data/packages/installed/tools/ai-ops/` (handler.py + ibl_actions.yaml 형식 B[nodes: self/table] + tool.json 빌드 파생). PHONE_VERIFIED_PACKAGES 등재(모듈레벨 stdlib만, ⏳A36 실기 확정).
- `ai_call: true` 플래그: api_ibl /validate 가 step `ai_call`+`has_ai_call`+비용 고지 / portal_core.action_allowed 가 레지스트리 파생 집합으로 기본 거부(폴백=몸의 어휘 이름).
- 교재 12_ibl_only.md AI 낱말 절+예문 1줄 / guides/ai_words.md(guide_db 66) / ibl.md §4.6 하위절 / src README `ai_call` 절 / new_action_checklist 주석 / changelog / system_structure(148 액션·41 패키지) / CLAUDE.md.
- 이미지 입력 = 비전 패스스루(ingest_engine._gemini_vision_json — 모달리티는 기어 무관, §4 원칙 유지).

**검증**: 빌드 17가드·층 가드·배터리 25/25(`backend/test_ai_ops_words.py`)+P1~P20 회귀 · 라이브 종단(dry-run has_ai_call 고지 → [table:ai] 실모델 의미 선별[rows_dropped 신고] → [self:struct]{finance}>>[table:brief] 파이프[grounded 3/3 원문 대조 통과]) · 포털 게이트 거부/회귀.

**해마**: 시드 16건(파이프라인 모양 12+대조 4 — reflex-veto 규율)+ibl_distilled 820. 직행 4/6(리모델링 0.908·광고 제거 top-1), 대조 영토 보존(영수증→ingest 우선·PDF표→read·평문 요약→ask). ⏳"시세→brief 보고" 부류는 재학습 대기열.

**남은 것(코드 밖)**: 커밋 · 재학습 대기열 합류 · A36 폰 실기 확정 · 실사용 증류 관찰(§11-6 — 성패 지표).

---

## 부록 A — 논거 요약 (대화 이력, 2026-08-19)

1. 감사 보고서의 `[self:struct]` 권고는 입구 자리만 본 것 — 사용자 명제("원샷 에이전트가 조합되기 좋은 어휘로 있으면 IBL 문장이 훨씬 많은 일을 한다. 앱 만들 때 실제로 그렇게 돌파한다")가 세 자리 일반화의 출발.
2. items→items 단일 형태는 조합성을 줄인다(실사용 분포: 입구·출구가 다수) — 세 자리 확정.
3. 모델 = 기어 실행 축(사용자 결정: "self:ask 처럼 경량이 아니라 실행 에이전트와 같은 모델").
4. 파이프는 execute_ibl 한 번 안 서버측 순차 실행 — 원자화의 비용은 왕복이 아니라 번역 난이도. 따라서 시딩·재학습·교재가 성패의 사슬(§11-3~5).

## 부록 B — 코드 증거

- `oneshot_ai_call` 정의: `backend/cognition/consciousness_agent.py` (15파일 ~18 실호출)
- ingest 4층 분해: `backend/services/ingest_engine.py` 머리 주석
- each 코어 배치 근거: `data/ibl_nodes_src/table.yaml:3-6`
- emitter returns 선례: `data/packages/installed/tools/data-ops/ibl_actions.yaml` (structure=scalar, document=effect)
- `self:ask` scalar 계약: `data/packages/installed/tools/system_essentials/ibl_actions.yaml`
