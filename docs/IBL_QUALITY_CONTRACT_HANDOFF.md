# criteria 품질 계약 — 설계·집행 핸드오프 (2026-08-27)

> 정본. 요지 = `data/system_docs/ibl.md` 엔진 규약 문단 + `data/guides/ai_words.md`,
> 구현 단일 소스 = `backend/ibl/ibl_quality.py`, 회귀 = `backend/test_ibl_criteria_contract.py`.
> 전편(형식 기반) = `docs/IBL_TRACEBACK_HANDOFF.md` — quality 는 그 §6 의 집행이다.

## 1. 문제 — 원샷 AI 의 지배적 실패 모드

IBL 문장은 중간에 원샷 AI 단계(`ai_call: true` — `table:ai`·`table:brief`·`self:struct` 등)를
품는다. 이 단계들은 거의 예외를 던지지 않는다 — **그럴듯하지만 나쁜 결과를 성공으로
반환**한다. 기존 장치의 커버리지:

- **0층(구조, 무료)** — 낱말 자체의 계약: JSON 검증+재시도 1회, rows_in/out, grounded
  원문 대조, `_ai` provenance. "형식이 깨졌다"는 잡지만 "내용이 나쁘다"는 못 잡는다.
- **시각 검수** — `engines:render` prescreen(0층) + `image_read{op:critic}`(비전 심사).
  화면 산출물 한정.
- **인지층** — `cognitive_eval` 의 achievement_criteria 평가 루프(ACHIEVED/NOT_ACHIEVED
  +severity+재실행). **에피소드 수준**이고 조종실 의식 에이전트 경로에서만 돈다 —
  스케줄러·워크플로우·goal 라운드·폰 단독 실행은 아무도 판정하지 않으며, 판정이 있어도
  어느 step 이 물을 흐렸는지 위치가 없다.

구멍 = **IBL 실행 층의 step 단위 품질 계약**. 트레이스백(전편)이 형식(`error_type:
"quality"` 예약)을 만들어 뒀고, 이 배치가 그 자리를 채운다: 품질 미달 = 위치 있는 실패.

## 2. 사용자 판정 (2026-08-27)

- 이름 = **`criteria`** (`expect` 기각 — 인지층 achievement_criteria·critic 의 criteria 와
  한 낱말이 세 층을 관통).
- 미달 시 **재시도 1회 = 기본 on** (JSON 재시도 1회·others:ask 1회 자가교정의 거울).
- 새 검수 낱말(`[table:check]` 류)은 기각 — 반-어휘-증식이고, 실패 위치가 검수 step 으로
  어긋난다. `criteria` 는 `on_error` 처럼 엔진 소유 기능어.

## 3. 의미론

```
[table:brief]{instruction: "급변 종목 3문장 보고",
              criteria: "종목명·수치 포함, items 에 없는 주장 없음"}
```

1. `execute_ibl` 최외곽 관문이 leaf 액션 params 에서 `criteria` 를 pop(핸들러 불도달 —
   미인식 param 경고 경로도 안 탄다). 실행 → 구조적 성공이면 판정자
   (`oneshot_ai_call`, **role=evaluate — 기어 평가 축**, GoalEval 평가자와 같은 축.
   2026-08-27 정정: 초판은 background(분류 축)로 박아 "경량"을 단언했는데 그건 기어의
   평가-축 의도를 우회하는 티어 하드코딩의 변형 — 사용자 지적으로 수리. 절약·균형=경량,
   최대=고급이 기어 실물) 1회:
   `{"pass": bool, "reason"}` JSON 강제, 관용 파싱(PASS/FAIL 토큰 폴백).
2. **미달 → 재시도 1회**: 판정 사유+기준을 `instruction` 에 얹어 그 step 재실행 —
   `ai_call: true` 이고 `instruction` 을 **선언한** 액션만(선언 = tool.json input_schema,
   B34 관문과 같은 진실 소스. 피드백 얹을 자리가 없는 결정론 액션 재실행 = 같은 결과).
3. 재판정도 미달 → **quality 실패**: `{success: false, error: "criteria 미달: …",
   criteria, criteria_verdict: "fail", quality_retried, rejected_result(≤4000자 원형,
   초과=summarize_result 구조 요약), traceback: {error_type: "quality"}}`.
   파이프 이음매가 트레이스백을 승계해 pipeline 프레임을 얹는다 — **그 step 이 찍힌다.**
   이후는 보통 실패와 동일(`>>` 중단·`??` 폴백·`on_error` 존중).
4. 통과 신고: `criteria_verdict: "pass"` / 재시도 통과 = `"pass_after_retry"` +
   `criteria_feedback`(첫 미달 사유) + **`_criteria_retried`**(정직 표지, ibl_honesty
   HONESTY_FLAG_KEYS — repeat·병렬 경계를 자동으로 넘는다). 스칼라 결과는
   `_quality_meta` side-channel 로 step 기록에 신고(F19-1 규약).
5. **판정 불능 = 통과 + 신고**(`criteria_verdict: "unjudged"` + note) —
   parse_eval_verdict 선례: 잘못된 미달 판정은 재실행 낭비가 더 비싸다. 침묵은 없다.
6. 실행 자체가 실패한 step 은 판정하지 않는다(실행 실패 우선, 트레이스백이 이미 위치를
   나른다). criteria 없으면 판정자 호출 0 — 옵트인, 기존 문장 무변경.

### 경계 규칙
- **액션 선언 우선**: 액션이 `criteria` 를 자기 param 으로 선언하면
  (`engines:image_read{op:"critic"}`) 엔진이 가로채지 않는다 — 그 도구의 입력이다.
- **블록 비적용**: `_try/_goal/_condition/_case/_repeat/_assign/_parallel` — goal 은 자기
  달성 판정을 갖고, 블록 몸의 leaf 들이 각자 criteria 를 갖는 것이 맞다.
- `criteria` 는 `RUNTIME_META_KEYS`(ibl_param_vocab — 어휘 관문·빌드 코퍼스 검사 공유
  단일 소스)에 등재.

## 4. goal 라운드 배선 (같은 배치)

goal 은 문장이 끝난 뒤에도 사는 유일한 구조인데, 라운드가 `agent_goals` 에서
`execute_ibl` 을 직접 불러 파이프 조립점을 우회했고 `str(result)[:500]` 절단이 봉투째
뭉갰다. 이번 배선:

- 라운드 액션 실패: 봉투 트레이스백 승계 + `{kind: "goal", goal_id, round}` 프레임 →
  rounds_data 에 JSON 으로 기록(500자 절단 제거 — 트레이스백은 구조상 유계).
- 라운드 실행 예외: `error_type: "exception"` + py_tail + goal 프레임.
- NOT_ACHIEVED 판정 사유(`last_judgment`)를 버리지 않고 종료 보고에 승계.
- 미달성 종료(expired/limit_reached) 보고: `not_achieved: true` +
  `traceback(error_type: "quality", goal 프레임)`. **success 는 뒤집지 않는다** —
  repeat halted 규약("성공도 실패도 아님·신고는 크게")과 동형.

## 5. 비용 정직

criteria 1개 = 판정 최대 2회 + 재실행 1회의 추가 원샷. **판정 비용의 수준은 기어
평가 축이 정한다** — 절약·균형이면 경량, 최대면 고급(평가 품질과 비용을 사용자가
기어 한 손잡이로 트레이드). 교재·가이드가 "규칙으로 적을 수 있으면
filter/take/스키마 가드가 먼저"를 가르친다. 0층(구조 가드)은 여전히 무료·항상 on.

## 6. 증류 게이트 셋째 신호 — ✅ 같은 날 집행 (2026-08-27 후속 판정)

"판정 데이터가 쌓인 뒤"로 미뤘던 초안을 사용자 지적으로 재검토 → 기각하고 즉시 배선.
근거: 게이트 규칙("미달 용례를 학습하지 마라")은 데이터로 정당화되는 게 아니라 지금
참이고, 미루면 그 사이 오염 용례가 코퍼스에 들어가 재학습 때 해마에 구워진다(되돌리기
비싼 침묵 누수 — each 면제 기각과 같은 부류).

- **미달(fail) 배제**: 새 코드 0줄 — quality 실패 봉투는 success:false 라
  `agent_pipeline`(is_error_result 재판정) → `distill_experience` 성공 필터가 이미
  거른다. 이 사슬의 핵심 고리를 회귀로 고정(C9).
- **재시도-통과(pass_after_retry) 신호**: `agent_pipeline._quality_of_result` 가 결과
  봉투(마킹 dict·파이프 results[])에서 표지+`criteria_feedback` 을 캐서 tool_calls 에
  병기 → `distill_experience` 가 반성 프롬프트에 "첫 미달 사유 + instruction 을 재발
  않게 다듬어라(criteria 는 보존)" 로 먹인다 — 약한 지시 대신 **개선된 지시**가
  증류된다. 학습 회로의 닫힘점.
- goal NOT_ACHIEVED 게이트(기존 `goal_eval_outcome`)와 3층 대칭: 실행 실패(구조) ·
  품질 미달(criteria) · 목표 미달성(goal).

## 7. 남긴 것 (의도적)

- **작성 시점 린트**: "AI 출력이 표면 싱크로 직행하는데 criteria 없음" 경고 — 교재
  (12_ibl_only.md)에 규범으로 먼저 실었다. 정적 검수(F13-2 자리) 편입은 실사용 오탐률
  관찰 후(스위치화 금지 판정 존중 — 강제 관문 아님). *이건 데이터가 진짜 선행 조건인
  경우다: 오탐률을 모르는 경고는 소음이 된다.*
- **판정자 오탐 관찰**: unjudged 비율·재시도 통과율이 첫 측정 대상 — episode_log 와
  `_quality_meta` step 기록으로 셀 수 있다.

## 8. 배선 지도

| 자리 | 파일 | 무엇 |
|---|---|---|
| 단일 소스 | `backend/ibl/ibl_quality.py` (신설, ibl 층) | pop_criteria/apply_criteria/_judge(_call_judge=테스트 패치점) |
| 관문 | `ibl_engine.execute_ibl` | pop → 실행 → 판정 → 재시도 → quality 실패/신고 |
| step 기록 | `workflow_engine` (`_quality_meta` 승격) | 스칼라 결과의 판정 신고 통로 |
| 정직 표지 | `ibl_honesty.HONESTY_FLAG_KEYS` + 교재 12_ibl_only.md | `_criteria_retried` |
| param 어휘 | `ibl_param_vocab.RUNTIME_META_KEYS` | criteria (액션 선언 우선 규칙 주석) |
| goal | `cognition/agent_goals.py` | 라운드 실패 tb+goal 프레임 · 미달 종료 quality tb |
| 증류 신호 | `cognition/agent_pipeline.py`(`_quality_of_result`) · `cognition/ibl_usage_rag.py` | 재시도-통과 표지→반성 프롬프트 (§6) |
| 회귀 | `backend/test_ibl_criteria_contract.py` | C1~C11 (판정자 패치, 원샷 호출 0) |

## 9. 표지의 절단 생존 (2026-08-28 수리)

출하 이튿날 라이브 관찰을 시도하니 **관찰 자체가 성립하지 않았다** — 에피소드 로그는 봉투
직렬화의 꼬리를 절단하는데(`episode_logger.truncate_for_log`, 머리 보존), 판정 표지가 전부
꼬리에 실리고 있었다: `_mark` 는 결과 dict 끝에 병기, 파이프 표지(warning·traceback·
`_fallback_used`…)는 `results`·`final_result` **뒤에** append. 08-28 세 보고서 주행에서 부분
실패 봉투의 트레이스백 프레임이 로그로 확인 불능이었던 것이 이 부류다. 표지가 잘리면
"없다"와 "안 보인다"가 구별되지 않는다 — unjudged 비율·재시도 통과율을 영영 못 센다.

세 자리 수리 (JSON 키 순서는 소비자 계약이 아니다 — 파서는 이름으로 읽는다):

1. **`_mark` 머리 삽입** — 판정 표지를 결과 dict/JSON 문자열의 앞 키로.
2. **`criteria_steps` 최상위 승격** (`workflow_engine`, skipped/halted 와 같은 규약) —
   step 별 `{step, action, verdict, retried?}`. **pass 도 싣는다**: 관찰의 분모(판정 총수)가
   없으면 비율을 못 센다. fail 은 여기 안 온다(step 실패 경로가 traceback 으로 나른다).
3. **거대 필드 꼬리 재배열** (`ibl_envelope.diet_envelope`, 에이전트 경계 단일 이음매) —
   `results`·`final_result` 를 직렬화 맨 뒤로. 이 한 자리로 **모든 생산자**(성공·실패·중단
   봉투)의 최상위 표지 — criteria 만이 아니라 traceback·warning·statements_failed 전부 —
   가 절단 생존이 된다.

회귀 = C11. 관찰 계수는 이제 로그에서 직접: `grep -c criteria_verdict` 분모, `unjudged`·
`pass_after_retry` 분자.
