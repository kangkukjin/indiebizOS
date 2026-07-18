# IBL 문법층 핸드오프 — 실패 표현 통일 · 순차 연산자 · 문법 검사

**작성**: 2026-07-18 · **완료**: 2026-07-18 (같은 날 후속 세션)
**상태**: ✅ **과제 1·2·3 + §5 + §6 완료** (+ §9-3 블로그 발행·JSON 문자열 실패 감지). 남은 것은 아래 §9 판단 2건(사용자 몫)뿐.

> 아래 §1~§8 은 **작업 지시서 원문 그대로** 둔다(무엇을 왜 했는지의 기록).
> 실제 결과·정정은 **§9** 에 모아 적었다 — 이어받는 사람은 §9 를 먼저 볼 것.

---

## 0. 왜 이 문서가 생겼나

공유창고에 정기 산출물을 발행하려다 "지우고 → 만들고 → 올린다"라는 **평범한 순차를 IBL로 쓸 수 없다**는
걸 발견했다. 파고들었더니 문법층에 세 겹의 문제가 겹쳐 있었다.

가장 상징적인 사실:

> **`??` 폴백 연산자는 한 번도 작동한 적이 없다.**
> `_execute_fallback` 가 `agent_id` 를 인자로 받지 않는데 본문에서 사용 → 호출 즉시 `NameError`.

왜 몇 달간 아무도 몰랐는지가 핵심이다:

| 층 | `??` 상태 |
|---|---|
| `data/system_docs/ibl.md` (명세) | 가르침 |
| `data/common_prompts/consciousness_prompt.md` | 가르침 |
| **해마 코퍼스 2,925 용례** | **0건** |
| 엔진 | 죽어 있음(NameError) |
| self-check (`scripts/ibl_health_check.py` `PIPES`) | 검사 안 함 |

**코퍼스에 없으니 AI가 안 썼고, 안 썼으니 죽은 채로 남았다.** 문서·프롬프트는 어휘를 *주장*하지만
실제로 어휘를 *정의*하는 건 코퍼스다([[execution-memory-architecture]] "코퍼스=몸"). 그 둘이 벌어진
자리에 **유령 문법**이 산다. 이번에 드러난 게 하나일 뿐, 구조적으로 더 있을 수 있다.

> ★반대로 **어휘(명사)는 튼튼했다.** 이 작업에서 "창고에 올리는 새 액션"을 만들려다,
> `self:copy`·`self:read`·`self:file_find`·`table:document` 조합으로 **새 어휘 0**에 해결됐다.
> 문제는 명사가 아니라 명사들을 잇는 문법이다. 어휘를 늘려 해결하려 들지 말 것.

---

## 1. 과제 1 — 실패 표현 통일 (가장 근본)

### 문제
도구가 실패를 **세 가지 방식**으로 알린다.

| 방식 | 예 |
|---|---|
| 문자열 `"Error: …"` | `self:read`, `self:delete`, `self:copy` (system_essentials handler) |
| dict `{"success": false, …}` / `{"error": …}` | `table:document` (data-ops) |
| 예외 | 드라이버·네트워크 계열 |

분기해야 하는 모든 것이 이 셋을 **각자 다르게** 추측한다.

### 이미 두 판정이 복제됐다가 갈라진 상태 (핵심 증거)

`backend/workflow_engine.py`:

```python
# execute_pipeline (>> 경로) — 289~293행: 문자열 O
is_err = False
if isinstance(result, dict):
    if "error" in result and result.get("status") != "not_implemented":
        is_err = True
elif isinstance(result, str) and result.startswith("Error:"):   # ← 이 분기
    is_err = True

# _execute_fallback (?? 경로) — 474행: 문자열 X
is_err = isinstance(result, dict) and "error" in result and result.get("status") != "not_implemented"
```

**`??` 는 에러 문자열을 성공으로 센다.** 그래서 오늘 NameError 를 고친 *뒤에도*
`[self:read]{없는파일} ?? [self:read]{있는파일}` 이 폴백하지 않는다(1차 시도가 `status: ok` 로 기록).
→ **`??` 는 현재 "반만 고쳐진" 상태다.**

### 할 일
1. `_is_error_result(result) -> bool` 을 **단일 소스**로 추출(`workflow_engine.py` 상단 권장).
   - `execute_pipeline`(289행)과 `_execute_fallback`(474행)이 **같은 함수**를 쓰게.
2. 같은 판정을 쓰는 다른 소비자 점검 후 합류:
   - `execute_pipeline` 병렬(`&`) 경로
   - 서킷 브레이커 — [[circuit_breaker_nested_error_falsepos]] 가 같은 가족("성공을 실패로 오인")
   - 평가 에이전트 / `goal_evaluator`
3. **중기(선택)**: 도구 반환 규약 자체를 통화로 수렴시킬지 결정.
   지금은 판정을 통일하는 것만으로 충분하고, 규약 변경은 파급이 크니 별건.

### 함정
- `"Error:"` 접두 판정은 **휴리스틱**이다. 본문에 "Error:" 로 시작하는 정당한 콘텐츠
  (로그 요약·코드 스니펫)를 실패로 오인할 수 있다. 단일 소스로 모으되 이 한계를 주석에 남길 것.
- `status == "not_implemented"` 는 실패로 치지 않는 기존 예외 — 유지.

---

## 2. 과제 2 — 순차 연산자 (의존 없는 "그리고")

### 문제
IBL 에는 **"A 하고, 되든 안 되든 B 한다"** 를 표현할 방법이 없다.

실측(2026-07-18):

| 쓴 것 | 결과 |
|---|---|
| `[self:delete]{없는파일} >> [self:read]{있는파일}` | `0/2` — 뒤가 안 돎 |
| 줄바꿈으로 나눈 **독립 문장 2개** | `0/2` — **이것도 안 돎** |

`>>` 가 세 의미를 한 기호에 뭉쳐놨다: ①다음에 ②결과를 넘기고 ③**성공했을 때만**.
독립 문장도 `execute_pipeline` 이 같은 루프로 처리해 첫 실패에서 전체를 반환한다
(`workflow_engine.py` 305~313행).

### 오늘 쓴 우회 (정직한 기록)
`self:delete` 에 `missing_ok` 파라미터를 추가해 넘어갔다.
→ **문법 결함을 어휘로 때운 것.** 멱등 delete 자체는 `rm -f`·`Path.unlink(missing_ok=True)` 처럼
표준이라 그 자체로 정당하지만, 이걸 고른 이유는 순차 문법이 없어서였다.
과제 2가 끝나면 `missing_ok` 는 **남겨도 되지만 필수는 아니게** 된다.

### 할 일
1. 연산자 하나 신설. 이름 후보(사용자 결정 필요):
   - `;` — 셸·C 계열 관습, "그냥 다음"
   - `&&` 의 반대 개념이라 `,` 도 후보
   - ★[[ibl_naming_law]] 적용 대상. 기호는 파서 코드에 들어가므로 **표준 문법 변경**이다
     → `ibl.md` "언어의 경계" 조항 + `build_ibl_nodes.py` `STANDARD_CORE_NODES` 동시 갱신 검토.
2. 파서: `backend/ibl_parser.py` — 문장 분해는 이미 `_extract_statements`(256행)가 개행으로 한다.
   현재는 나뉜 문장들이 결국 한 파이프 루프로 들어가 실패 전파가 일어남 → **실행기 쪽 분리**가 본체.
3. 실행기: `execute_pipeline` 이 "독립 문장 경계"를 알고, 경계에서는 실패를 전파하지 않게.
   결과는 각 문장별로 `results` 에 쌓되 전체 `success` 는 정책 결정(전부 성공? 하나라도 성공?).
4. 결정 필요: **`_prev_result` 는 경계를 넘지 않는다**(권장 — 독립이란 뜻이므로).

### 왜 지금 필요한가
"지우고 올린다"는 정기 발행의 기본형이다. 창고뿐 아니라 백업·정리·재생성 전부 같은 모양이라,
이게 없으면 매번 `missing_ok` 같은 파라미터를 도구마다 새로 만들게 된다(어휘 오염).

---

## 3. 과제 3 — 문법 검사 (죽은 문법이 다시 몇 달 버티지 못하게)

### 현재 사각지대
| 검사 | 대상 |
|---|---|
| `scripts/build_ibl_nodes.py --check` | **선언 삼각형**(src ↔ tool.json ↔ handler `_OP_DISPATCHERS`) |
| self-check §1A `run_static_ibl_check` | 위 정적 정합성 |
| self-check §1B 통화(fixture) | 액션 반환 형태 |
| self-check §1C **골든 파이프** | `scripts/ibl_health_check.py:226` `PIPES` — **`>>` 5건만** |
| **연산자 `??` · `&`** | **아무도 안 봄** ← `??` 가 몇 달 버틴 이유 |

### 할 일 (신설 아님 — 기존 `PIPES` 확장)
`scripts/ibl_health_check.py` `PIPES`(226행)에 항목 추가:

```python
# ?? — 앞이 실패하면 뒤로 (실패 감지가 문자열/ dict 양쪽 다 되는지 확인)
("fallback_string_err", '[self:read]{path: "__없는파일__.md"} ?? [sense:search_naver]{query: "AI"}', "items"),
("fallback_ok_shortcut", '[sense:search_naver]{query: "AI"} ?? [self:read]{path: "__없는파일__.md"}', "items"),
# & — 병렬 두 입력이 실제로 합류하는지
("parallel_merge", '[sense:search_naver]{query: "AI"} & [sense:search_ddg]{query: "AI"} >> [table:merge]{by: "title"}', "items"),
```

- 첫 항목이 **과제 1의 회귀 테스트**를 겸한다(문자열 에러에도 폴백하는가).
- 둘째 항목은 "성공하면 폴백을 타지 않는가"(단축 평가).
- 과제 2 완료 후 **순차 연산자 fixture 도 여기 추가**.

### 곁다리로 발견된 것 — self-check 계획이 낡음
`data/self_check_plan.json`:
- `generated_at: 2026-06-26`, `total_actions: 118` (**현재 157**)
- 노드 집합 `{engines, self, sense, limbs, others}` — **`table` 없음**
  = 2026-06-30 [[table_node_split]] 이전 상태. 13개 변환자를 아직 `engines:` 로 알고 있다.

→ self-check 가 **3주 낡은 유령 목록**을 점검해 왔다. 재생성 경로(`actions_hash` 로 드리프트 감지하는
듯한 구조)가 왜 안 돌았는지 확인 필요. **과제 3에 포함시킬 것.**

---

## 4. 오늘 이미 손댄 것 (재작업 방지 — 전부 **미커밋**)

| 파일 | 변경 | 상태 |
|---|---|---|
| `backend/workflow_engine.py` | `_execute_fallback` 에 `agent_id` 인자 추가 + 호출부 전달 | ✅ NameError 해소 / ⚠️ **문자열 판정은 아직 안 됨(과제 1)** |
| `data/packages/installed/tools/system_essentials/handler.py` | `delete_path` 에 `missing_ok` | ✅ (과제 2의 우회) |
| 〃 `ibl_actions.yaml` | `missing_ok` 스키마 + `path` 설명 오타 수정(mkdir 복붙이던 것) | ✅ |
| `data/packages/installed/tools/data-ops/handler.py` | `markdown` 입구(`_markdown_to_blocks` 외), 목록 `note`, `default` 테마 재작성, 한글 폰트 스택 | ✅ |
| 〃 `ibl_actions.yaml` | `markdown` 파라미터, `format` enum 에 `markdown` 추가(핸들러는 원래 지원), `required: []` | ✅ build --check 통과 |
| `backend/api_portal.py` | `_ensure_warehouses` 에서 정기 산출물 물질화 훅 제거 | ✅ |
| `backend/warehouse_publish.py`, `data/warehouse_publish.json` | **삭제**(= `self:copy` 재구현이라 폐기) | ✅ |

액션 수 **157 불변**(파라미터·입구 추가라 어휘 증가 없음). 해마 재학습 불필요.

---

## 5. 관련 이음매 버그 (같은 부류, 별건으로 둘 수 있음)

1. **`filename` 절대경로가 말없이 잘림** — `data-ops/handler.py:1521`
   `os.path.splitext(os.path.basename(str(base)))[0]` → 산출물을 원하는 위치에 직접 쓸 수 없다.
   경고도 없어서 "됐다"고 착각하기 쉬움(오늘 실제로 착각함).
2. **스케줄러 소유자 없는 경로가 `project_path="."`** — `backend/calendar_actions.py:177`
   (`channel_poller.py:827` 도 동형) → 스케줄된 IBL 의 **상대경로가 무의미**.
   [[project_newspaper_curation]] 의 04시 트리거가 예전에 이 부류로 매일 실패했던 전례 있음.
   → **§6 스케줄러 배선이 여기서 막혔다.**

---

## 6. 이 다음: 스케줄러 완성 (막혀 있는 작업)

목표: 정기 산출물을 매일 공유창고 레벨0에 발행. 파이프는 **검증 완료**(수동 실행 성공,
실패 시 낡은 판이 사라지는 것까지 확인). 스케줄 등록도 됐으나 **강제 실행 시 산출물 0** —
원인은 §5-2(`project_path="."`).

이미 등록된 작업(그대로 두면 매일 조용히 실패함 — **고치거나 비활성화할 것**):

| id | 시각 | 내용 |
|---|---|---|
| `evt_19b66c4d6f6f` | 04:20 | 보고서 발행 |
| `evt_d0978c477aed` | 07:30 | 신문 발행 |

검증된 파이프(수동 실행 기준, `project_id: 앱모드`):

```
[self:delete]{path: "<REPO>/공유창고/0/오늘의 신문.html", missing_ok: true}
[self:read]{path: "outputs/newspaper_current.md"} >> [table:document]{format: "html", theme: "newspaper", filename: "wh_newspaper"} >> [self:copy]{source: "<REPO>/projects/앱모드/outputs/wh_newspaper.html", destination: "<REPO>/공유창고/0/오늘의 신문.html"}
```

```
[self:delete]{path: "<REPO>/공유창고/0/오늘의 AI 보고서.html", missing_ok: true}
[self:file_find]{pattern: "ai_trend_report_*.md", path: "<REPO>/outputs/ai_trend_reports"} >> [table:take]{n: -1} >> [self:read]{} >> [table:document]{format: "html", filename: "wh_report"} >> [self:copy]{source: "<REPO>/projects/앱모드/outputs/wh_report.html", destination: "<REPO>/공유창고/0/오늘의 AI 보고서.html"}
```

해결 방향(택1, 미결):
- (a) 스케줄 작업에 프로젝트 컨텍스트를 실어 `execute_pipeline(steps, <project_path>)` 로 넘김
- (b) 파이프를 전부 절대경로로 — 단 `table:document` 산출 위치는 `output_base` 가 정하므로 §5-1 선결
- ★과제 2가 끝나면 `missing_ok` 없이 순차 연산자로 다시 쓰는 게 자연스러움

### 소스 위치 (참고)
- 신문: `projects/앱모드/outputs/newspaper_current.md` — 데스크탑 신문앱 '발행' 시 갱신.
  ★같은 폴더의 `.html` 은 **07-14에서 멈춰 있음**(Blob 다운로드 버튼이라 파일 저장 아님) — 쓰지 말 것.
- 보고서: `outputs/ai_trend_reports/ai_trend_report_YYYY-MM-DD.md` — 04:00 스케줄(`evt_c81bab07016e`)이
  `[others:delegate]` 로 생성, 실측 04:05 착지.

### 미결 판단
- **신문의 레벨 0 적정성**: 제호("청주 데일리")·키워드 12개·관점 편성이 공개되면 사는 지역과
  관심사가 드러난다. 창고 의도(공개 얼굴)에 맞으면 유지, 아니면 레벨 1+.
- **신문은 시계가 아니라 '발행 버튼'이 자연스러운 트리거**일 수 있음(수동 발행물이라
  매일 07:30 에 옛 판을 다시 올릴 수 있음).

---

## 7. 검증 방법

```bash
# 과제 1
[self:read]{path: "__없는__.md"} ?? [sense:search_naver]{query: "AI"}
#   → 시도1 status=error, 시도2 실행, 최종 items  (지금은 시도1이 ok 로 기록됨)

# 과제 2 (연산자 확정 후)
[self:delete]{path: "__없는__.html"} ; [self:read]{path: "있는파일.md"}
#   → 2/2, 첫 문장 실패해도 둘째 실행

# 과제 3
python3 scripts/ibl_health_check.py     # PIPES 전건 PASS
python3 scripts/build_ibl_nodes.py --check
```

공통: 핸들러 편집 → `POST /packages/reload` / `backend/*.py` 편집 → uvicorn auto-reload /
`ibl_actions.yaml` 편집 → `build_ibl_nodes.py` 후 reload.

---

## 8. 한 줄 요약

> 어휘는 튼튼한데 **문법이 얇고, 실패의 뜻이 통일돼 있지 않고, 문법을 검사하는 사람이 없다.**
> `??` 가 몇 달간 죽은 채 살아 있었던 건 그 셋의 곱이다.


---

## 9. 완료 기록 (2026-07-18 후속 세션)

### 과제 1 — 실패 표현 통일 ✅
`workflow_engine._is_error_result()` **단일 소스** 신설. `>>`(289행)와 `??`(474행)가 같은 함수를 쓴다.

판정을 세 형태 전부로 넓혔다 — 원래 계획(문자열 판정을 `??` 에도)에 더해 **`success: False`** 도 포함:
핸들러 196곳이 `success:False` 를 쓰는데 그중 다수가 `error` 키 없이 `message` 만 실어서, `error` 키만
보던 옛 판정은 그 실패들을 **전부 성공으로 세고 있었다**(`>>` 도 마찬가지였다).

곁다리로 발견·수정: **폴백 체인 전체 실패의 이음매 구멍** — `_all_failed` 표식을 dict 에만 붙이는데
문자열 에러는 dict 가 아니라 표식을 못 달아, 체인이 전부 실패해도 호출부가 성공으로 셌다.
전체 실패 경로에서만 error dict 로 감싸 해결.

검증: 라이브 `??` 종단(1차 status가 `ok`→**`error`** 로 바뀌고 폴백 발동) + 단축 평가 + 골든 5/5 무회귀.

### 과제 2 — 순차 연산자 `;` ✅ (사용자 결정: 셸·C 관습)
- **파서**(`ibl_parser.py`): `;` 를 **개행과 같은 것**으로 접었다(`_split_by_operator` 재사용 → 문자열·중괄호
  안의 `;` 는 안전). 문장 첫 step 에 `_seq_boundary` 표식.
- **실행기**(`workflow_engine.execute_pipeline`): 표식을 보고 실패해도 다음 문장으로 건너뛴다.
  5개 실패 지점을 `_handle_failure()` 하나로 모았다. `_prev_result` 는 경계를 넘지 않는다.
- **★개행 문장도 같이 고쳐졌다** — §2 가 지적한 "독립 문장 2개도 0/2" 가 같은 수정으로 해소.
- **정직성 정책**(§2-3 미결이던 것): 건너뛰어도 **실패를 숨기지 않는다** — 실패 문장이 있으면
  `success:false` + `statements_failed:N`. 스케줄러·평가자가 조용히 성공으로 읽으면 안 되므로.
- `>>` 는 문장 *안*에서 그대로 실패 시 중단(회귀 가드로 고정).
- `missing_ok` 는 그대로 뒀다(멱등 delete 는 그 자체로 표준) — 다만 이제 **필수가 아니다.**

**★`;` 와 `missing_ok` 는 서로 대체재가 아니다**(실측으로 확인, 아래 §9-2). 원문 §2 는
"과제 2가 끝나면 missing_ok 는 필수가 아니게 된다"고 했는데, 맞지만 **빼라는 뜻은 아니다.**
둘은 다른 층의 일이다: `;` = *흐름*(되든 안 되든 다음), `missing_ok` = *의미*(없는 걸 지우는 건
실패가 아니다). `;` 만 쓰면 파이프는 끝까지 돌지만 `success:false` 로 보고되고
`calendar_actions` 가 **실패 알림을 띄운다**(195~211행). 정기 작업엔 둘 다 쓴다.

### 과제 3 — 문법 검사 ✅
`ibl_health_check.py` 에 **§1C-2 연산자** 절 신설(기존 `PIPES` 확장이 아니라 별도 절 — `PIPES` 는
final_result 의 *모양*만 보므로 "폴백을 탔는가"를 못 본다. `??` 가 몇 달 산 사각지대가 정확히 이것).
5건: `;` 계속 / `>>` 중단(회귀) / `??` 문자열에러 / `??` 단축 / `&` 합류. **5/5 PASS.**
`world_pulse_health.run_ibl_health_check` 에 `operators` 항목 합류(옛 요약은 total=0 → 스킵).

**해마 씨앗 14건**(`;` 8 + `??` 6, source=`manual_seed`) + rebuild_index 2,838→**2,852**.
→ §0 의 교훈("코퍼스에 없으니 AI가 안 썼고, 안 썼으니 죽은 채로 남았다")에 대한 **실제 대응**.
`??` 는 2,838개 코퍼스에 **0건**이었다(진단 그대로). 연상 검증: 두 연산자 모두 top-1 적중.

### ★§3 곁다리 항목의 진단이 틀렸음 (정정)
> 원문: "self-check 가 3주 낡은 유령 목록을 점검해 왔다."

**아니다.** self-check 는 2026-06-27(`065c5a9`)에 이미 fixture 방식으로 옮겨갔고 그 파일을 안 쓴다.
그 커밋이 LLM 분류 생성 함수를 지웠는데 **헬퍼 3개와 캐시 파일만 남았다.**

**진짜 피해자는 조종실 dry-run 의 부작용 라벨**이었다(157개 중 118개만 분류, `table` 노드는 통째로
미분류 → "unknown"). 게다가 같은 판정이 `api_ibl.py` 와 `ibl_health_check.py` 에 **복제**돼 있었다
(과제 1의 `_is_error_result` 와 똑같은 부류).

**해결**(사용자 결정: returns 파생 + 센서 예외) — `backend/ibl_safety.py` **단일 소스** 신설:
- `returns: effect` = 부작용으로 **파생**. 157개 전부 자동 분류(안전 92 / 부작용 65).
  `returns:` 는 전 액션 필수 선언이고 `--check` 가 지키므로, **새 액션이 자동 분류된다** = 유령 목록 재발 불가.
- **두 축이 다르다는 예외**: `returns:` 는 *통화 모양*이지 *부작용*이 아니다. 카메라·마이크는
  scalar 를 반환하지만 셔터를 누르고 녹음을 시작한다 → `sense:here/listen/see` 에 `side_effect: true`
  를 **src yaml 에 선언**(코드에 이름을 박지 않는다 — 헌법 `ibl_standard_core`).
- 정리: `data/self_check_plan.json` **삭제**, `world_pulse_health.py` 죽은 코드 67줄 제거(1190→1123).

곁다리: dry-run 의 "알 수 없는 노드" 문구가 `table` 을 모르던 것(5노드로 굳어 있었음) → 레지스트리 파생으로 교체.

### §5 이음매 버그 ✅
1. **`filename` 절대경로 침묵 절단** → 자르는 동작은 유지하되 **note 로 소리를 낸다**
   ("경로 부분은 무시, 산출 위치는 …, 옮기려면 `>> [self:copy]`"). 침묵이 문제였지 절단이 문제가 아니었다.
2. **스케줄러 `project_path="."`** → **엔진 수정 불필요였다.** `execute_pipeline` 은 이미
   `project_path` 가 `"."` 일 때 head leaf 의 `project_id` 를 전파한다(`_propagate_project_id`).
   파이프가 그걸 **안 싣고 있었을 뿐** → 해결책 (a) 를 *데이터로* 적용.

### §6 스케줄러 ✅ (막힘 해소)
두 파이프에 `project_id: "앱모드"` 를 head leaf 에 실었다. `PUT /scheduler/tasks/{id}` 로 갱신
(★러닝 calendar_manager 가 메모리를 쥐고 있어 파일만 고치면 미반영 — 메모리 노트대로).

**스케줄러와 동일 경로**(`execute_pipeline(steps, ".")`)로 종단 검증:
- 보고서 `evt_19b66c4d6f6f`: **6/6**, 산출물 20,105 바이트
- 신문 `evt_d0978c477aed`: **4/4**, 산출물 45,855 바이트

**두 작업 모두 `enabled: false` 로 두었다** — 아래 §9-1 판단 전까지 켜지 않는다.

### §9-2. 스케줄을 새 문법으로 다시 씀 (2026-07-18, 사용자 질문에서)
두 파이프를 `;` 한 줄로 재작성했다(줄바꿈 → `;`). "지우고 → 만들어 올린다"가 한눈에 읽힌다.

`missing_ok` 를 뺄지 실측한 4-케이스 표:

| 파이프 | 파일 있을 때 | 파일 없을 때 |
|---|---|---|
| `;` + `missing_ok` | success=True, 산출물 O | **success=True, 산출물 O** |
| `;` 만 | success=True, 산출물 O | **success=False(실패 알림), 산출물 O** |

**산출물은 네 경우 다 정상 생성된다** — 차이는 *보고*뿐이다. 그래서 `missing_ok` 를 유지했다.
(첫 실행·수동 정리 후처럼 파일이 없는 날마다 실패 알림이 뜨면, 진짜 고장이 묻힌다.)

검증: 러닝 스케줄러에서 다시 읽어 `execute_pipeline(steps, ".")` 로 —
보고서 6/6·20,105바이트, 신문 4/4·45,855바이트, 두 시나리오 모두 success=True.

### §9-3. 블로그 발행 추가 + `_is_error_result` 4번째 실패 형태 (2026-07-18)

블로그 일일 발행을 붙이다가 **과제 1이 놓친 실패 형태**를 실측으로 찾았다.

**★JSON 문자열 실패가 통째로 새고 있었다.** handler 라우터는 `format_json(...)` 으로 *문자열*을
돌려주므로 실패가 `'{"success": false, "message": …}'` 로 온다. 문자열은 `"Error:"` 접두만 보고
있었으므로 **handler 도구의 실패가 전부 성공으로 셌다**(실측: 블로그 파이프 2건이 내용은 실패인데
`success=True`). `_is_error_result` 가 최상위 JSON 문자열을 파싱하도록 확장 + 판정 정밀화
(`{"success": true, "error": null}` 를 성공으로 — 서킷 브레이커의 옛 교훈을 판정에 반영).
§1C-2 에 회귀 가드 추가(`[table:document]{}` 가 내는 JSON 문자열 실패) → **6/6 PASS**.

**어휘: `[self:blog]{op: "latest"}` 신설** (op 추가 — **액션 수 157 불변**).
설계 원칙 = *선택만 하고 발행은 기존 동사로*: 이 op 은 본문을 렌더하지 않고 **vault .md 경로**만 준다.
`self:read` 가 path 없으면 `_prev_result` 에서 경로를 자동 추출하므로(`_extract_path_from_prev`)
보고서·신문과 **똑같은 파이프 모양**으로 이어진다. 전용 발행 기계를 안 만든 이유는
`warehouse_publish.py` 를 폐기한 이유와 같다(= `self:copy`·`table:document` 재구현).

**곁다리 수정 — YAML frontmatter 가 본문에 노출**: vault .md 를 발행하면 `post_id: "…" title: "…"`
가 글 맨 위에 그대로 보였다. `_markdown_to_blocks(md, meta_out=)` 가 frontmatter 를 벗기고,
`_apply_frontmatter` 가 title·pub_date·category 를 문서 제목·부제로 **올린다**(벗기기만 하면 손실).
Obsidian vault → 발행 경로 전반에 해당.

**스케줄** `evt_ee5cb8e22bb8` 06:30 daily (enabled):
```
[self:blog]{op:"check_new", project_id:"앱모드"} ; [self:blog]{op:"latest"} >> [self:read]{} >> [table:document]{format:"html", filename:"wh_blog"} >> [self:copy]{...}
```
- `;` 가 여기서 제 일을 한다 — RSS 수집이 실패해도(네트워크) 발행은 그대로 간다.
- delete 문장이 없다 — `self:copy` 가 덮어쓰므로 `missing_ok` 도 불필요.
- 검증: 스케줄러 동일 경로 **5/5**, 산출물 13,068바이트, frontmatter 누출 없음.
- 해마 6용례 + rebuild_index 2,852→**2,858**, 연상 3/3 적중.

**★조건("새 글 있을 때만")은 넣지 않았다 — 의도적.** IBL 조건문은 goal 블록(LLM)이라 매일 돌리기엔
과하고, 무엇보다 **무조건 재발행이 멱등·자가치유**다: 어느 날 발행이 실패해도 다음 날 스스로 복구된다.
조건부면 "새 글 없음 → 영영 건너뜀"으로 낡은 판이 창고에 남는다. 내용이 같으면 같은 바이트가
쓰이므로 *창고가 바뀌는 건 새 글이 있을 때뿐*이라 사용자 의도는 그대로 충족된다.

### §9-4. 블로그 본문 마크다운 복원 — "원문을 긁어야 하나?" 에 대한 답 (2026-07-19)

§9-3 에서 "블로그 본문에 문단이 없다(RSS 가 HTML 을 걷어내며 잃었다) → 원문을 긁는 쪽으로
따로 손볼 수 있다"고 적었다. **그 진단이 틀렸다.** 사용자가 "원문 긁기는 느리고 부정확하지
않나"라고 되물어 확인해 보니:

> **RSS 는 문단과 이미지를 이미 다 준다.** description 44,717자 · `<p>` 15개 · `<img>` 1개.
> 잃어버린 건 수집기가 `clean_html` 로 **평문화하면서 버린 것**이었다.

즉 긁을 필요가 없다 — **버리던 구조를 안 버리면 된다.** 스크래핑은 느리고·깨지기 쉽고·
차단 위험이 있는데 얻는 게 없었다. (교훈: "데이터가 없다"고 결론 내리기 전에 원본을 직접 열어볼 것.)

**수정**: `tool_blog_insight.html_to_markdown()` 신설 — HTML → 마크다운(문단·이미지·링크·목록·인용).
- `clean_html` 은 **건드리지 않았다** — 여러 패키지가 '평문' 계약으로 공유하는 유틸이다.
- **새 의존성 0** — 티스토리 태그 집합이 좁아(p·span·figure·img) 이미 있는 bs4 로 충분
  (markdownify 설치는 공급망 승인 게이트 대상이기도 하다).
- vault 정본이 `.md` 라 마크다운이 이 코퍼스의 자연스러운 형태이기도 하다.
- ★함정: 티스토리는 낱말마다 `<span>낱말<span>&nbsp;</span></span>` 로 감싼다. 재귀 변환이
  각 단계에서 `strip()` 하면 그 `&nbsp;` 가 지워져 **단어가 전부 붙는다**("우리는여러가지플랫폼에").
  → `_md_inline_raw`(공백 보존 재귀) / `_md_inline`(최상위 1회 정리)로 분리.

**기존 50편 복원** — `scripts/migrate_blog_markdown.py` (기본 dry-run, `--apply` 로 실행):
vault 는 사용자의 Obsidian 저장소라 조심스럽게 다뤘다.
- 24편에 붙어 있던 **`관련 글`(시맨틱 연결) 블록을 떼어뒀다 다시 붙인다** — 단순 덮어쓰기였다면
  그 링크 그래프가 사라졌다. summary·keywords 도 보존.
- 이미 마크다운이면 건너뛴다(**멱등** — 두 번 돌려도 안전).
- RSS 창(50편) 밖은 원본이 없으므로 손대지 않는다.
- 사본 왕복 시험으로 관련글 6개 보존을 **먼저 증명한 뒤** 적용.

**결과**: 50/50 복원, 관련글 24/24 보존, vault .md 총 4,061개 불변(유실 0),
RAG 재인덱싱 3,702편. 발행물 재생성 → **12문단 + 이미지 1**, frontmatter 누출 없음.

> 남은 한계: RSS 창(50편)보다 오래된 글은 원본이 없어 평문 그대로다.
> 매일 발행되는 건 최신글이라 실사용에는 영향이 없다.

---

## 9-1. 남은 판단 2건 (사용자 몫 — 코드 아님)

1. **스케줄 켤 것인가.** 파이프는 검증됐고 켜기만 하면 매일 돈다
   (`POST /scheduler/tasks/<id>/toggle`). 켜는 순간 **레벨 0 = 익명 공개**로 매일 발행된다.
2. **신문의 레벨 0 적정성**(원문 §6 미결 그대로). 제호·키워드 12개·관점 편성이 공개되면
   사는 지역과 관심사가 드러난다. → 레벨 1+ 로 올릴지, 또는 **신문은 시계가 아니라 '발행 버튼'**
   트리거가 맞을지(수동 발행물이라 07:30 에 옛 판을 다시 올릴 수 있다).

> 참고: 검증 과정에서 `공유창고/0/` 의 두 파일을 오늘 자 내용으로 **갱신**했다.
> 새로 노출한 종류의 콘텐츠는 아니다(원문 §6 대로 이미 수동 발행돼 있던 파일들).

---

## 10. 이번에 다시 확인된 것

> 원문 §8 이 옳았다. 어휘는 튼튼했고 **문법이 얇았다.**
> 이번 작업의 신규 어휘도 **0개**(157 불변) — 고친 건 전부 연산자·판정·검사다.
> 그리고 `??` 가 죽어 있던 진짜 이유는 코드가 아니라 **코퍼스 0건**이었다.
> 그래서 이번엔 `;` 를 문서에만 적지 않고 **코퍼스에 심었다.**
