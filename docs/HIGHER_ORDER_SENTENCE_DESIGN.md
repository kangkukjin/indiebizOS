# 고차 문장 설계 — 문장을 값으로 받는 낱말 (2026-08-15)

> **집행 상태 (같은 날)**: M1 ✅ · 선행 수리 ✅ · M2 ✅ · 측정 스크립트 ✅ · 시드 ✅(14건)
> · **M3 = 미착수**(측정 후 별건) · ⏳재학습 대기열 · ⏳커밋(동시 세션 있으니 pathspec)
>
> **집행 중 설계에서 바뀐 것 2가지 (기록)**
> 1. **M1 별칭 방향이 설계와 반대**: `_normalize_param_aliases` 는 alias→정규키로 *복사*하고
>    정규키는 핸들러가 읽는 키다. 그래서 `do` 를 정규키로 만들면 핸들러·저장된 트리거/
>    워크플로 데이터를 전부 고쳐야 한다 → **정규키는 기존 키 유지, `do` 를 별칭으로** 선언했다.
>    언어 표면(desc·AI 가 쓰는 이름)만 `do` 로 통일 = 코드·데이터 변경 0. "어휘 이름이 코드에
>    박히면 안 된다"는 헌법이 정확히 이 형태로 작동한 사례.
> 2. **측정 지표 자체에 결함이 있었다**: 문형을 전체 문장 기준으로 세니 "발신 973" 이 나와
>    조합이 되고 있다는 착시를 줬다. 문형은 **파이프 문장 기준**으로만 세도록 고쳤다
>    (`scripts/vocab_composition_metrics.py`). 고친 뒤 실측 = 발신은 **파이프 56 대 단발 917**
>    — §1 의 "others 계열이 파이프에 한 번도 안 들어온다"는 과장이었고, 정확히는
>    **"싱크 어휘는 쓰이되 거의 언제나 단발"**, 그리고 **시간 어휘만 조합 0**이었다.
>
> **시드 후 실측 (전 → 후)**: 문형 4 → **6**(적용 0→11 신설 · 시간 0→2) · 미조합 액션
> 69 → **64** · 파트너 다양성 최대 21 → 28 · `$변수` 19 → 30.
> **파이프 길이 중앙값은 2 그대로** — 시드 14건이 3,222 문장의 중앙값을 움직였다면 그건
> 지표를 속인 것이다. 이 값은 재학습 후 *실사용* 문장이 쌓여야 움직인다(그게 진짜 신호).

> **목적**: 가능성 공간을 덧셈(낱말 수)에서 곱셈(문형 수)으로 바꾸는 최소 수술.
> 자매 문서: `VOCAB_COMPOSABILITY_HANDOFF.md`(어휘 층) · `IBL_GRAMMAR_HANDOFF.md`(문법 층) ·
> `data/system_docs/ibl.md` "언어의 경계"(헌법 — 이 설계의 M2는 **언어 개정**에 해당).

---

## 0. 실측 — 무엇이 이미 있고 무엇이 없나

### 0-1. 코퍼스가 말하는 것 (해마 3,208 문장 전수)

```
파이프(>>) 포함              236 / 3,208   (7%)
파이프 평균 길이             2.45  (2단이 72%, 최대 6)
한 번도 조합된 적 없는 액션   68 / 150   (45%)
조합 파트너 다양성 1위        table:take = 21, 그 아래 급락 / 파트너 1개뿐 = 19개

문법 기능 사용률   & 4.2% | $변수 0.6% | ; 0.6% | ?? 0.2% | if/case 0.2% | @몸 0.2%
```

미조합 68개의 성격이 무작위가 아니다:
- `others:` 거의 전부 — channel_send · delegate · publish · ask · board · feed · nostr · notify
- `self:` 의 시간·기억·원장 — schedule · trigger · workflow · goal · memory · storage · output · forage · notebook

조합되는 것은 `sense:*`(소스)와 `table:*`(변환)뿐이고, 파이프 끝(싱크) 상위도 전부 `table:*`.
**이 언어가 말할 줄 아는 문장은 사실상 한 종류다 — "가져와서 정리해서 사람에게".**

### 0-2. 추상은 이미 있다 (구현 실측)

| 있는 것 | 위치 | 상태 |
|---|---|---|
| 문장을 파라미터로 받는 낱말 **5곳** | `trigger.pipeline` · `workflow.steps` · `schedule.action` · `manage_events.event_action` · `delegate.steps` | **이름이 5개로 갈라짐** |
| 변수 바인딩 `$var = 문장` | `ibl_parser._extract_statements` → `{{_step_N_result}}` 치환 | 있음 / 코퍼스 0.6% |
| 조건·분기·목표 블록 | `[if:]` `[case:]` `[goal:]` (`ibl_parser_blocks`) | 있음 / 코퍼스 0.2% |
| **중첩 실행기** | `_execute_condition`·`_execute_case` 가 `execute_ibl` 재귀 호출 | 있음 / **깊이 제한 없음** |
| 매개변수화 | `workflow run{params}` | 있음 / 미사용 |

### 0-3. 없는 것 — 단 하나

**`table` 13 변환자 전부가 데이터→데이터다. 문장을 인자로 받는 변환자가 0개다.**

```
filter sort take select dedup groupby join union merge   ← 전부 데이터만
structure document spreadsheet chart                      ← 전부 데이터만
```

즉 **적용/반복(map)이 없다.** "찾은 것 *각각에 대해* ~해라"를 이 언어로 쓸 방법이 없다.

---

## 1. 진단 — map 부재가 싱크 부재를 만든다

싱크(`channel_send`·`notify_user`·`delegate`·`publish`)는 대부분 **항목 단위** 어휘다.
목록 전체를 통째로 싱크에 넘기는 문장은 대개 말이 안 된다. 그래서:

```
지금 가능한 것:  [sense:used]{q:"자전거"} >> [table:filter]{...}     ← 여기서 끝. 사람이 읽는다.
쓰고 싶은 것:    ... >> (각 항목마다) [self:notify_user]{...}        ← 표현 불가
```

**AI가 싱크를 안 붙이는 게 아니라, 붙일 문법이 없어서 2단에서 멈춘다.** 이것이 파이프 길이
중앙값 2와 미조합 68개(특히 others 계열 전멸)의 공통 원인이라는 것이 이 설계의 가설이다.
반증 가능: M2 구현 후 파이프 길이 중앙값과 others 계열 편입 수를 재측정한다(§6).

---

## 2. 설계 — 세 수(手)

### M1. 문장 자리의 이름을 하나로 — `do:`

현재 같은 것(=실행할 IBL 문장)이 다섯 이름으로 불린다: `pipeline` / `steps` / `action` /
`event_action` / `steps`. AI 입장에서는 낱말마다 따로 외워야 하는 다섯 개의 관용구이고,
전이가 일어나지 않는다.

- **정본 이름 = `do`** (짧고, 술어 자리임이 자명하고, 기존 파라미터와 충돌 없음)
- 기존 5개는 전부 **`aliases:` 로 흡수** — 옛 이름 계속 작동(호환층 아님, 별칭은 영구 어휘)
- 배열/단문 둘 다 허용: `do: "[a:b]{}"` 또는 `do: ["[a:b]{}", "[c:d]{}"]`

> **분류: 사전 편집.** yaml `aliases:` 블록만 바뀐다(→ `param_aliases_always_on_datafication`).
> 파서·엔진 무수정이 불변식. 위험 ~0, 선행 착수 대상.

효과: "문장을 넘기는 자리"가 한 형태가 되어, 한 곳에서 배운 것이 나머지 넷으로 전이된다.

---

### M2. 빠진 조각 — `[table:each]` (적용/반복)

```
[table:each]{
  do:       "<IBL 문장>",       # 필수. 각 행에 적용할 문장
  as:       "it",               # 행 참조 변수명 (기본 "it" → 문장 안에서 $it.title)
  limit:    20,                 # 안전 상한 (기본 20, 명시로 상향)
  on_error: "continue"          # continue(기본) | stop — 어느 쪽이든 실패는 집계 반환
}
```

**통화 계약** (`IBL_CURRENCY_CONTRACT.md` 준수) — ★2026-08-23 개정, 아래 각주 참조
- 입력: `{items:[...]}`
- 출력: `{items:[...]}` — **성공은 통화로**: `do` 가 통화를 내면 그 행들이 감싸기 없이 흐르고
  (뒤에 변환자를 바로 이을 수 있다), 통화를 안 내면(효과·스칼라) **원 행**이 흐르며
  봉투가 `passthrough_rows` 로 그 사실을 말한다.
- **실패는 봉투로**: `errors: [{원 행…, _error}]` + `error_count` + `warning`.
  통화에 섞지 않는다.
- `keep: [부모 필드]` — 팬아웃 결과 행에 원 행의 필드를 승계(옛 `flatten{keep}` 의 자리 이동).
- 요약 필드: `{ok_count, error_count, rows_processed, skipped}` — **침묵 금지**(§4-3)

> **★개정 각주 (2026-08-23, 사용자 판정)** — 초판은 출력 행을 `원 행 + _ok + (_error|_result)`
> 봉투로 쌌고, 명분은 바로 위에 적혀 있던 *"원 행 보존 = `>> [table:filter]{where:"_ok == false"}`
> 로 실패만 추리는 문장이 가능"* 이었다. 그 기능은 실제로 잘 작동했다 — 그런데 **코퍼스
> 3,582문장에서 `_ok` 를 쓴 문장이 0건**이었다. 반대편에서는 그 봉투 때문에 뒤에 붙는 변환자가
> 전부 "그 필드 없다"로 끊겨 `each` 가 항상 `>> [table:flatten]` 을 동반하는 2낱말 관용구였다
> (each 문장 49건 중 15건, 최다 후속). **한 번도 안 쓰인 관용구를 위해 매번 쓰이는 관용구를
> 끊고 있었다.** 실사용도 8일간 7건에 그쳤고, 같은 기간 "한 문장으로 접힐 수 있었던" 연속
> 동일 액션 반복이 700여 건이었다.
>
> 그리고 이 몸은 이미 답을 갖고 있었다: `halted_steps`·`skipped_steps`·`branches_failed`·
> `empty_notes` 가 전부 **부분 실패는 봉투로** 나른다. `each` 만 2026-08-15(이 문서)에 그 규약이
> 서기 전에 만들어져 실패를 통화 *안*에 섞었고, 그래서 IBL 에서 유일하게 통화-in/통화-out 이
> 아닌 변환자였다. 개정은 그 예외를 없앤 것이다.
>
> 능력은 잃지 않았다 — `flatten{keep}` 은 `each{keep}` 으로 자리를 옮겼고, 실패 원 행은
> `errors` 에 그대로 있다. 부수 은퇴: `collect` 파라미터(그 일이 이제 기본 동작이다).
> 이행: 코퍼스 15문장 이관(DB+`data/training/ibl_distilled.json` 양쪽), 옛 관용구
> `each >> flatten` 은 flatten 이 "이미 평탄합니다 — flatten 없이 바로 이으세요"로 정직하게 거절.
> 가드 `backend/test_each_currency_contract.py` C1~C11.

**왜 `table` 노드인가**: 통화를 먹고 통화를 뱉는 변환자라는 `table` 의 정의에 정확히 부합한다.
그리고 `always_on: true` 라 어떤 노드 선별에서도 살아남는다 — 문형의 뼈대가 꺼지면 안 된다.

**실행**: `execute_ibl(step, project_path, agent_id)` 재귀. `_execute_condition`/`_execute_case`
가 이미 쓰는 바로 그 기법이라 새 실행 기제가 아니다.

**이것이 열어주는 문형** (지금은 표현 불가)

```ibl
# 발신형 — 각 항목마다 알린다
[sense:used]{q:"자전거", source:"danggeun"} >> [table:filter]{where:"price < 100000"}
  >> [table:each]{do: "[self:notify_user]{message: '$it.title / $it.price원'}"}

# 축적형 — 문장 결과가 내 원장으로 되돌아온다
[sense:feed]{url:"..."} >> [table:take]{n:5}
  >> [table:each]{do: "[self:notebook]{op:'add', notebook:'AI팁', path:'$it.url'}"}

# 확장형 — 목록의 각 행을 다시 소스로 쓴다(2단 조회)
[sense:search]{q:"국내 리츠"} >> [table:take]{n:3}
  >> [table:each]{do: "[sense:crawl]{url:'$it.url'}"}
  >> [table:document]{title:"리츠 브리핑"}
```

> **분류: 언어 개정.** 표준 코어(`table`, always_on)에 낱말이 는다.
> 동반 갱신 의무 — `data/ibl_nodes_src/table.yaml` · `build_ibl_nodes.py` 의
> `STANDARD_CORE_NODES` 선언 · `ibl.md` "언어의 경계" 조항 · `new_action_checklist.md` ·
> 표준-코어 가드 통과 확인. (헌법이 요구하는 "의식적 개정" 절차를 그대로 밟는다.)

---

### M3. 문장 원장을 하나로 — `workflow` 승격, `trigger` 는 시간축만

지금 이름 붙은 문장이 **세 군데**에 산다:

| 저장소 | 나르는 것 | 성격 |
|---|---|---|
| `self:workflow` | IBL 문장 배열 (DB) | 문장 원장 |
| `self:script` | 외부 파일 경로 (id 참조) | 코드 원장 — **의도적으로 코드를 안 나름** |
| `self:trigger{pipeline}` | IBL 문장 + 시간 | 문장 + 시간이 한 낱말에 엉킴 |

**새 낱말을 만들지 않는다**(반-어휘-증식 — 4번째 저장소를 만드는 순간 이 설계는 자기모순).
대신 역할을 가른다:

- **`self:workflow` = 문장 원장의 정본.** 이름 붙은 문장의 저장·조회·실행·매개변수화(`params`).
- **`self:trigger` = 시간·조건 축만.** 내용물은 참조로:
  `[self:trigger]{op:"create", cron:"0 9 * * *", do:"[self:workflow]{op:'run', workflow_id:'조간'}"}`
- 즉석 실행은 `trigger{do: "<문장>"}` 그대로 허용(저장 없이) — 참조를 강제하지 않는다.

이렇게 하면 §4 "스케줄 6형제" 가 **문장 원장(workflow) + 시간축(trigger) + 평가 루프(goal)** 로
수렴하고, `schedule` 은 `trigger` 의 op(지연/1회)로, 나머지는 아래 심사 대상이 된다.

> **⚠ 심사 필요 (원칙 2 — 핸들러를 연다)**: `manage_events` 는 📅 캘린더 계기를 보유하고
> (`app:` 블록), `switch` 는 별도 스위치 시스템(`switch_runner`)을 가진다. 둘의 은퇴·흡수는
> 계기 개편을 동반하므로 **M3 은 M1·M2 와 분리해 별건으로 착수**한다. 이 문서는 방향만 고정한다.

---

## 3. 왜 낱말을 하나만 더하는가

`map` 외에 `filter_by`·`reduce`·`while` 같은 고차 낱말을 함께 만들지 않는 이유 — 원칙 1의 재적용:

- **filter**: 이미 있다(`table:filter{where}` DSL). 문장이 필요할 만큼 복잡하면 `each` + `_ok` 필터로 표현된다.
- **reduce**: `table:groupby` 의 집계(count/sum/avg/min/max)가 실사용 영역을 덮는다.
- **while/until**: 정지 조건 판단은 AI 의 몫이다(`FILE_FORAGING_RESEARCH` 의 "정지는 AI" 와 같은 판정).
  기계적 반복이 필요하면 `self:script` 가 기본 답이다.

**`each` 하나만 있으면 나머지는 문장으로 표현된다.** 그것이 이 설계가 곱셈인 이유다.

---

## 4. 안전 설계 (전부 필수 — 하나라도 빠지면 착수 금지)

### 4-1. 재귀 깊이 — 현재 **무제한**이 실측
`_execute_condition` → `execute_ibl` → … 에 깊이 제한이 없다. `each` 는 이 재귀를 훨씬 쉽게
만들므로(`do` 안에 `each` 를 넣을 수 있다) 선행 수리가 필요하다.
- `tool_input["_depth"]` 전파, 상한 **3**, 초과 시 실행 거부 + 명시 오류
- 상한은 `each`뿐 아니라 if/case/goal/trigger 전 중첩 경로에 공통 적용

### 4-2. 폭발 방지
- `limit` **기본 20**(무지정 시). 1,000행 × 외부 호출은 사고다.
- `limit` 초과 시 조용히 자르지 말고 `skipped: N` 을 결과에 명시 (§4-3 과 같은 원칙)
- 총 스텝 예산: 한 `each` 가 소비할 수 있는 하위 스텝 수 상한(제안 200)

### 4-3. 침묵 금지 — 이 프로젝트의 기존 계약
`pipe-silent-failure-fixes` 로 종결한 계열을 되살리지 않는다.
- `on_error: "continue"` 여도 **실패를 삼키지 않는다** — 행마다 `_ok:false` + `_error`, 요약에 `error_count`
- 전 행 실패 시 결과는 성공이 아니다 — `error_count == 총 행수` 면 상위로 실패 전파
- 회귀 테스트는 `test_pipe_currency_failures.py` 옆에 `each` 케이스로 추가

> **★부수 발견 (별건)**: `_execute_condition` 이 조건 평가 실패를 `except: continue` 로 삼키고
> 있다(`ibl_executors.py:568`). 침묵 실패 계열의 잔존 개체다. `_depth` 작업과 같은 자리이므로
> 함께 수리하는 것이 효율적.

### 4-4. dry-run 가시성
조종실 `/ibl/validate` 가 **중첩 문장까지 파싱·검증**해야 한다. `do` 안의 문장이 미검증으로
통과하면 검수 화면이 거짓말을 한다.
- 부작용 있는 액션(`side_effect: true`)이 `do` 에 있으면 dry-run 결과에 **명시 경고 + 예상 실행 횟수**
- ⚠ 선행 결함: `/ibl/validate` 가 병렬(`&`)을 전부 반려하는 기존 버그(태스크 칩 발행됨)를
  먼저 고치는 것이 좋다 — 중첩 검증을 그 위에 얹게 된다.

---

## 5. 검증 계약

```bash
python3 scripts/build_ibl_nodes.py && python3 scripts/build_ibl_nodes.py --check   # 전 가드 + 표준-코어 가드
python3 -m pytest tests/test_pipe_currency_failures.py                              # 기존 회귀 (P1~P19)
# 신규: each 케이스 — 정상/부분실패/전실패/limit초과/깊이초과/중첩each
# 라이브: /packages/reload → /ibl/validate 중첩 검증 → /ibl/execute 종단 3문형(발신·축적·확장)
```

---

## 6. 성공 기준 (측정 — 조합률로 재지 않는다)

시딩으로 올릴 수 있는 지표는 지표가 아니다. 아래 넷을 M2 **구현 전/후**로 같은 자로 잰다.

| 지표 | 현재 | 목표 |
|---|---|---|
| 파이프 길이 중앙값 | 2 | 3 |
| 미조합 액션 수 | 68 / 150 | others 계열이 편입되는가 |
| 문형 수 (조회/발신/축적/시간/조건) | 사실상 1 | 3 이상 |
| 낱말당 조합 파트너 다양성 중앙값 | (스크립트로 고정) | 증가 |

**순서가 중요하다: 문형을 만들고 나서 가르친다.** 코퍼스 시드는 M2 구현 *후*에.
지금 시드를 더 넣으면 존재하지 않는 문형은 못 가르치고 `소스 >> table:*` 만 두꺼워진다.

---

## 7. 착수 순서

1. **M1** — `do` 별칭 통일 (사전 편집, 위험 ~0)
2. **선행 수리** — `_depth` 상한 + `_execute_condition` 침묵 제거 (+가능하면 validate 병렬 버그)
3. **M2** — `[table:each]` 신설 (언어 개정 절차 전부)
4. **시드 + 재학습** — 새 문형 3종 위주 (발신·축적·확장), feed·open_window 대기열과 함께
5. **측정** — §6 네 지표 전후 비교
6. **M3** — 문장 원장 단일화 (별건, 계기 개편 동반 심사부터)

---

## 8. 판정 필요 (착수 전 사용자 결정)

| 항목 | 선택지 | 기본 제안 |
|---|---|---|
| 문장 자리 이름 | `do` / `then` / `body` / `run` | **`do`** |
| 행 참조 변수 | `$it` / `$row` / `$each` | **`$it`** (`as` 로 개명 가능) |
| `each` 기본 limit | 20 / 50 / 무제한+경고 | **20** |
| M3 착수 여부 | 지금 / M2 측정 후 / 보류 | **M2 측정 후** |
| 재귀 깊이 상한 | 2 / 3 / 5 | **3** |

---

## 9. M3 심사 결과 (2026-08-15 — 원칙 2 절차로 핸들러를 열었다)

### 9-1. 설계 전제가 바뀌었다 — 문장 원장은 이미 한 번 전멸했다

같은 날 다른 세션이 `워크플로 원장 전량 정리`(`df93ad6`)를 커밋했다. **남아 있던 6건이
전부 죽은 참조**였다 — `self:file` · `search_papers` · `search_stock` · `video_info` ·
`limbs:transcript`, 전부 은퇴 어휘. 현재 원장은 **0건**이다.

즉 §2 의 M3("workflow 를 문장 원장의 정본으로 승격")를 그대로 집행하면 **사망률 100% 가
실증된 그릇으로 통합**하는 셈이 된다. 통합이 문제가 아니라 **저장된 문장이 썩는다는 것**이
문제였다. 이것은 온톨로지 부패가 시스템 *안에서* 나타난 사례다.

### 9-2. 결정적 비대칭 — 읽을 때 검증하는가

| 원장 | 나르는 것 | 읽을 때 검증 | 결과 |
|---|---|---|---|
| `self:script` | 파일 **참조**(id) | **있음** — 파일 실존·인터프리터 해석 → `runnable:false`+사유, 실패를 원장에 기록 | 살아 있음(계수 internal 3·manual 3) |
| `self:workflow` | **문장** | 없음 | 전 항목 사망 → 전량 폐기 |
| `self:trigger` | **문장** + 시간 | 없음 | 현재 3건은 건강(최근 생성) — 같은 병에 노출 |

선례가 이미 기록돼 있다: 04시 정기보고 트리거가 은퇴한 `[self:report]{op:new}` 를 부르며
**매일 조용히 실패**하고 있었다(CLAUDE.md). 트리거는 새벽에 혼자 도니 아무도 모른다.

### 9-3. 그래서 M3 는 두 단계로 갈린다

**M3-0 — 저장된 문장에 pre-flight (✅ 집행함, 판정 불요)**
`workflow_engine.preflight_sentence(code)` 신설 — `ibl_parse` + `get_node_actions` 로
어휘 생존만 검사해 `{runnable, problem, dead_vocab}` 반환. `list_workflows()` 와
`_list_triggers()` 가 항목마다 동반한다. `self:script` 의 선례를 문장 원장에 복제한 것이라
새 개념이 아니다. 부수로 `list_workflows` 의 `except: pass`(깨진 yaml 이 목록에서 조용히
사라지던 것) 제거.
- 한계(실측): 파서가 관대해 `[sense:search]{query: ` 같은 미종료 문자열도 통과한다.
  이 검사가 보장하는 것은 **어휘 생존**이지 문장의 의도가 아니다.
- 다음 결합점: 12시간 자가점검 순찰이 이 신호를 읽으면 "어휘 은퇴가 저장 문장을 깨뜨린
  순간"이 자동 검출된다(현재는 사람이 볼 때만 보인다).

**M3-1 — 원장 단일화 (미집행 — 사용자 판정 필요)**
pre-flight 가 붙은 *뒤에야* 의미가 있다. 판정 사안:

| 항목 | 실측 | 질문 |
|---|---|---|
| `self:manage_events` | **📅 calendar 계기 보유**(6형제 중 유일) · 계수 agent 1 | 흡수하면 계기 개편 동반 — 지금 할 것인가 |
| `self:switch` | 별도 `switch_runner` 시스템 · 계수 agent 1 | trigger 로 접히는가, 별개 정체인가 |
| `self:schedule` vs `self:trigger` | 둘 다 읽기키가 `pipeline`(=`do`) · 지연/1회 vs cron | schedule 을 trigger 의 op 로 접는가 |
| `self:workflow` | 원장 0건 · 계수 agent 1·internal 1 | 빈 그릇을 정본으로 승격할 근거가 지금 있는가 |

★참고: 08-15 이후 보정 계수는 6형제 전부 1~2건이라 **아직 판정 근거가 얇다**.
`self:script` 만 internal 3·manual 3 으로 실제 배관 사용이 있다.
