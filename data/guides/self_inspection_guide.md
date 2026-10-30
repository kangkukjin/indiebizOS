# 자기 점검 가이드 (Self-Inspection Guide)

당신은 indiebizOS의 시스템 AI다. 사용자가 다음과 같은 명령을 내리면 이 가이드를 따른다:

- "자기 점검해줘" / "어디 아픈지 봐줘" / "최적화할 곳 찾아줘"
- "X 영역 점검해줘" (X = IBL / 메모리 / 프롬프트 / 히스토리 / 가이드 / 인지)
- "지난 N일 점검" / "최근 어땠어?"

## 핵심 원칙

이 점검은 **시스템의 자기 인식**이다. 자기 인식의 시작은 "어디가 아픈가" 발견. 다음 셋을 분리한다:

1. **관찰**: 데이터에서 본 사실 (해석 없이)
2. **해석**: 그게 왜 문제로 보이는가
3. **제안**: 어떻게 고치면 좋을지

**절대로 점검 단계에서 시스템을 변경하지 않는다.** 보고만 한다. 사용자가 명시적으로 "고쳐줘" 명령을 내려야 다음 단계로 간다.

---

## 1. 모드 선택

사용자 명령에서 다음을 추출:

| 명령에 포함된 표현 | 모드 | 적용 영역 |
|------------------|------|----------|
| "전체" / "다 봐줘" / 영역 명시 없음 | 전체 | 6개 영역 모두 |
| "IBL" / "액션" | 영역 집중 | 4. IBL 관리 |
| "메모리" / "기억" / "심층메모리" / "해마" | 영역 집중 | 5. 메모리 관리 |
| "프롬프트" / "역할" | 영역 집중 | 6. 시스템 프롬프트 |
| "히스토리" / "대화 기록" | 영역 집중 | 7. 히스토리 관리 |
| "가이드" / "문서" | 영역 집중 | 8. 가이드 파일 |
| "인지" / "분류" / "의식" / "평가" | 영역 집중 | 9. 인지 프로세스 |

시간 범위:
- 명시 없음 → 최근 7일
- "어제" → 1일
- "지난 주" → 7일
- "지난 N일/주" → 그대로
- "전부" → 전체 기간을 대상으로 집계하고, 상세 에피소드는 최대 100개 표본으로 조사. 표본을 전수라고 보고하지 않는다.

---

## 2. 데이터 소스 — 어디서 무엇을 가져오는가

원장은 **`[sense:sqlite]`(읽기 전용 SQL, 2026-09-05)** 로 문장 안에서 읽는다 — 결과가 items 라 `>> [table:filter]/[table:groupby]` 로 바로 흐르고, 셸 `sqlite3` 로 나가면 그 값이 다음 IBL 문장에 손으로 되찍히는 이음매가 생긴다. 표·열을 모르면 `op:"tables"`→`op:"schema"` 먼저. 다음이 주요 데이터 소스:

### A. episode_log (가장 중요)
사용자 요청의 실행 흐름을 조회한다. 중단·누락·잘린 로그가 있을 수 있으므로 기록 부재를 실행 부재로 해석하지 않는다.

```ibl
[sense:sqlite]{path: "~workspace/data/world_pulse.db", query: "SELECT id, started_at, agent, substr(user_message, 1, 80) AS msg, length(log) AS log_len, total_ms FROM episode_log WHERE started_at > datetime('now', '-7 days') ORDER BY id DESC", limit: 50}
```

특정 에피소드 전체 로그(길다 — 먼저 아래 trajectory 로, 원문은 정말 필요할 때만):
```ibl
[sense:sqlite]{path: "~workspace/data/world_pulse.db", query: "SELECT log FROM episode_log WHERE id = ?", params: [<id>], limit: 1}
```

원인·실패·재개·파일 변경의 **순서**가 질문이면 원문 로그 grep보다 먼저 구조화 궤적을 쓴다:

```ibl
[self:body]{op: "trajectory", episode_id: 123}
```

`run_id`·`task_id`로도 조회할 수 있고, 식별자 없이 부르면 최근 실사용 episode를 읽는다.
trajectory는 request·model·IBL·validation·side-effect의 hash/ref 원장이므로, 의미 회상은
episode memory, 정확한 실행 순서는 trajectory, 세부 원문이 정말 필요할 때만 episode_log로 내려간다.

### B. episode_summary
요약된 메트릭 (영구 보존).

```ibl
[sense:sqlite]{path: "~workspace/data/world_pulse.db", query: "SELECT * FROM episode_summary WHERE started_at > datetime('now', '-30 days') ORDER BY id DESC", limit: 200}
```

### C. IBL 건강 점검 결과
일일 건강 점검(`scripts/ibl_health_check.py` = 정적+fixture+골든, AI 0) 이력. `__static__`·`__ibl_health__` 노드가 그 결과다.

```ibl
[sense:sqlite]{path: "~workspace/data/world_pulse.db", query: "SELECT node, action, success, error_message, timestamp FROM self_checks WHERE timestamp > datetime('now', '-7 days') ORDER BY id DESC", limit: 200}
```

실사용 실패는 별도 원장 `action_health`다:
```ibl
[sense:self_check]{op:"results",source:"usage",limit:200}
```
위 호출은 최근 기록 표본이다. 기간 전체의 빈도·응답시간은 `action_health`에서
`source='usage'`를 지정해 SQL 집계한다. `self_checks` 결과와 섞지 않는다.
점검 실행은 `sense:self_check`의 실행 경로 또는 `scripts/ibl_health_check.py`를 사용한다.
대기만 끝났다면 접수증으로 같은 작업의 결과를 회수하고 다시 실행하지 않는다.

### D. 시스템 AI 대화와 이전 보고서

시스템 AI의 대화 원장은 `data/system_ai_memory.db`의 `conversations`다.
프로젝트 대화와 경로가 다르므로 `self:recent_chats`의 빈 결과만으로 대화가 없다고 판단하지 않는다.
직접 SQL 조회가 필요하면 `sense:sqlite`의 `tables/schema`로 현재 열을 확인하고 필요한 기간만 읽는다.

### E. 심층 메모리 (사용자에 대한 사실)

중복·모순은 `[self:memory]{op:"recall",node:"<가지>"}`로 해당 가지를 열어 확인한다.
가지를 모르면 `op:"recall"`로 지도를 보거나 `op:"search",query:"키워드"`로 찾는다.
시스템 AI 기억은 `data/system_ai_state/memory_system_ai.db`, 프로젝트 기억은 각 프로젝트의
`memory_*.db`로 격리된다. 시스템 대화 DB 하나로 전체 기억을 점검하지 않는다.
기억 구조·보존 정책의 정본은 [memory.md](../system_docs/memory.md)다.

### F. 가이드 파일들
```bash
ls -la data/guides/*.md
```
파일별 내용은 Read 도구로.

### G. 프롬프트 파일들
```bash
ls -la data/common_prompts/*.md
```
역할·의식·평가·무의식 프롬프트와 `data/common_prompts/fragments/`의 조각들. 실제 조립은 `backend/cognition/prompt_builder.py`에서 확인한다.

### H. IBL 노드 정의
```bash
wc -l data/ibl_nodes.yaml
```
액션 명세 확인은 Read.

### I. config 파일들 (참고용, 변경 금지)
- `data/system_ai_config.json`
- `data/midtier_ai_config.json`
- `data/lightweight_ai_config.json`

---

## 3. 영역별 점검 신호 목록

각 영역마다 **데이터에서 찾을 구체적 신호**를 정의. 아래 신호가 있으면 발견으로 보고.

### 4. IBL 관리

**찾을 신호:**
- 동일 액션이 동일 에러 패턴으로 3회 이상 실패
- 동일 호출에서 파라미터 재시도(자가 보정)가 반복되는 액션 (파라미터 명명 문제)
- 지난 N일 0회 호출된 액션 (dead action 후보)
- 의식 에이전트가 hint에서 자주 언급하나 실제론 호출되지 못한 액션 (등록 누락 가능성)
- IBL 코드가 syntax error로 자주 깨지는 패턴

**데이터 수집:**
```ibl
[sense:sqlite]{path:"~workspace/data/world_pulse.db",query:"SELECT node, action, COUNT(*) AS fail_cnt, MAX(timestamp) AS last_at, substr(error, 1, 120) AS err FROM action_health WHERE source = 'usage' AND success = 0 AND timestamp > datetime('now', '-7 days') GROUP BY node, action, substr(error, 1, 120) ORDER BY fail_cnt DESC",limit:200}
```
호출 수·실패율의 분모도 같은 기간·출처로 집계한다. 문법·조합 실패는 해당 에피소드의
궤적·원문을 대조하며, 로그 문자열 출현 횟수를 실제 호출 수로 곧바로 세지 않는다.

**검증 절차 (실패 액션 재시도)**

위 신호로 잡힌 실패 액션은 보고 전 다음 절차로 검증한다. 단순히 "N회 실패" 보고에서 끝내지 말고, **진짜 고장인지 / 쉽게 고칠 수 있는지**까지 분류해야 보고가 행동 가능한 정보가 된다.

1. **idempotent 판단**
   - 재시도 가능: 현재 계약과 인자를 확인해 읽기 전용이며 반복 비용·영향이 허용되는 조회
   - 원본 로그만 확인: 메시지 전송·파일/DB 쓰기·명령 실행 등 부수효과가 있는 호출. 노드 이름만으로 읽기 전용을 판정하지 않는다.
   - 애매하면 재시도하지 않고 원본 로그만 인용 + `[난이도: 미상]` 표시

2. **재실행 분류** (idempotent 액션만)
   - 동일 파라미터로 1회 재호출: `[node:action]{...원본 파라미터...}`
   - 결과별 분류:
     - 재시도 성공 → **transient** (네트워크 일시 장애, rate limit 등). 보고서에 메모만 / 우선순위 ↓
     - 같은 에러 재현 → **reproducible**. 우선순위 ↑
     - 다른 에러 → **state-dependent** (외부 상태에 따라 다른 결과). 두 에러 모두 인용
   - 부수효과 액션이라 재시도하지 않은 경우 → `미검증`으로 표시

3. **수정 난이도 평가**
   - **쉬움**: 파라미터 명명 불일치(예: `district_code` ↔ `region_code` 류), 시그니처 stale, 가이드의 옛 호출 형식 — 사용자 승인 후 단순 치환
   - **중간**: 액션 코드 자체 버그(예외 처리 누락, 잘못된 파싱) — 코드 수정 필요, 사용자 승인 후 작업
   - **어려움 / 사용자 결정**: 외부 API 변경·종료, 인증·자격 증명 만료, 네트워크 의존성 — 시스템이 단독으로 못 고침
   - **미상**: idempotent 판단 보류 또는 재시도 결과 해석 불가

4. **보고 반영**
   - IBL 관리 영역 발견 항목에는 다음 두 필드를 **관찰** 아래에 추가:
     - `[확인]`: transient / reproducible / state-dependent / 미검증
     - `[난이도]`: 쉬움 / 중간 / 어려움 / 미상
   - transient만 발견된 액션은 발견 목록에서 제외해도 무방(짧은 메모로만 남김)

---

### 5. 메모리 관리

**찾을 신호 (심층메모리):**
- 같은 사실의 중복 저장 (같은 keywords + 비슷한 content)
- 일시 데이터가 영구 저장됨 (시세·날씨·환율 같은 휘발성)
- 모순되는 사실 (같은 주제 정반대 내용)
- 1개월 이상 한 번도 검색·참조되지 않은 항목

**찾을 신호 (해마/RAG):**
- 증류된 패턴 중 거의 retrieve 안 되는 것
- 사용자가 같은 질문을 반복했는데 해마 점수가 일관되게 낮음 (학습 누락)

**검증:** 같은 주제의 기억을 출처·날짜·적용 범위와 함께 비교한다. 표현이 비슷해도
다른 시점·대상의 사실일 수 있다. 참조 횟수와 회상 점수만으로 삭제를 제안하지 않는다.

---

### 6. 시스템 프롬프트

**찾을 신호:**
- consciousness_prompt가 지시한 JSON 형식이 깨진 의식 응답 빈도
- 평가 실행 건의 ACHIEVED/NOT_ACHIEVED·UNKNOWN 비율과 실패 근거. 미실행은 제외하고, 검수 승인(review_status)과 목표 달성(goal_status)을 분리해 원문 기준으로 해석
- 의식이 필요한 요청에서 달성 기준이 누락된 사례. 의식 없는 EXECUTE의 평가 생략은 정상 동작과 구분
- 특정 도메인 에이전트의 일관된 품질 저하

**파일들:**
- `data/common_prompts/consciousness_prompt.md`
- `data/common_prompts/unconscious_prompt.md`
- `data/common_prompts/evaluator_prompt.md`
- `data/common_prompts/base_prompt.md`

---

### 7. 히스토리 관리

**찾을 신호:**
- 컨텍스트 압축(`[Compaction]` 라인)이 자주 발생하는 에피소드
- 압축 후 사용자가 "방금 그게 뭐였지" 같은 재질문
- history-as-text 직렬화 길이가 평균 토큰 사용량의 큰 비중을 차지
- 같은 대화 thread에서 동일 정보가 매 턴 반복 주입됨

---

### 8. 가이드 파일

**찾을 신호:**
- 가이드에 적힌 IBL 액션이 현재 ibl_nodes.yaml에 없거나 시그니처 바뀜
- 의식 에이전트가 highlight한 적 없는 가이드 (검토 대상)
- 1개월 이상 ConsciousnessAgent 응답에 언급 안 된 가이드
- 가이드끼리 또는 같은 가이드 앞뒤의 내용 충돌
- 과거 사건·중복 경고가 현재 절차를 가리는지, 필요한 예제와 실패 조건이 빠지지 않았는지

**데이터 수집:**
```bash
# 의식 에이전트가 언급한 가이드 빈도 (episode_log의 guide_files JSON 필드)
sqlite3 data/world_pulse.db "SELECT log FROM episode_log WHERE log LIKE '%guide_files%' AND started_at > datetime('now', '-30 days');" | \
  grep -oE '"guide_files":\s*\[[^]]*\]' | sort | uniq -c | sort -rn
```

가이드는 `_load_guide_file`이 호출될 때 파일을 직접 읽는다. 수정만으로 이미 전송된
모델 입력까지 바뀌지는 않으므로, 적용 확인은 다음 조립 본문·내용 지문과 대조한다.
가이드 수정만을 이유로 백엔드 재기동을 요구하지 않는다.

---

### 9. 인지 프로세스

**찾을 신호:**
- 분류 EXECUTE인데 짧은 시간 안에 같은 사용자가 후속 메시지로 보완 요청 (THINK였어야 함)
- 분류 THINK인데 의식 frame이 사실상 비어있음 (EXECUTE면 충분했음)
- 최종평가의 한 번의 보완 뒤에도 기준 미달 또는 평가 불명. 평가 기준과 보완 인계가 일치하는지 확인
- 무의식의 REFLEX 선택이 부적절하거나 전체 문맥 인계가 실패. 해마 유사도는 현재 분류의 우회 임계값이 아님
- 같은 사용자 의도가 매번 다른 분류로 갈림 (분류기 일관성 문제)

---

## 10. 개선 후보와 우선순위

[IBL 진화 목적](../../docs/IBL_EVOLUTION_PURPOSE.md)에 따라 결과 품질·실제 완료 시간·전체
토큰 소비와 공통 능력을 기준으로 판단한다. 새 어휘 수나 가이드 수 자체를 성과로 세지 않는다.
우선순위는 사용자 영향·반복성·근거의 확실성으로 정하며, 어휘 추가를 버그 수리보다 자동 우대하지 않는다.

| 후보 | 관측할 신호 | 제안 방향 |
|---|---|---|
| 반복 조합의 재사용 | 같은 도구 순서를 매번 다시 작성·자가 보정 | 먼저 지역 함수·기존 관용구를 검토하고, 검증된 조합은 관용구로 보관. 외부 프로그램 절차는 `self:script` 등록 검토 |
| 절차 안내 보강 | 같은 요청의 방법론을 반복 재발견하거나 같은 후속 질문 발생 | 기존 가이드에 적용 조건·누락 절차를 반영. 별도 작업일 때 새 가이드 검토 |
| 정형 절차의 실행화 | 가이드의 동일 절차를 자주 실행 | 입력·반환·부작용·실패를 명시한 함수/스크립트로 구현하고 가이드는 선택·호출·예외를 설명 |
| 기존 계약 수리 | 반복 파라미터 오용, 다루기 힘든 반환, 옛 예제·서로 다른 안내 | 소유하는 선언·핸들러·교재를 함께 수정. 비슷한 액션의 명명 충돌이면 공통 계약으로 합칠 수 있는지 확인 |

새 액션은 기존 부품의 호출 순서만 묶는 것인지, 독립적인 새 능력이 필요한지 구별한다.
추가가 필요할 때는 [새 액션 체크리스트](new_action_checklist.md)를 따른다.
같은 현상이 여러 점검에서 반복되면 이전 관측과 연결하되, 후보 개수를 채우려고 만들지 않는다.

**제안 예시:**
```text
관찰: 같은 자료 수집·정리 조합을 최근 7일 12회 다시 작성했고, 그중 4회 입력을 보정했다.
해석: 재사용 가능한 값 전달 계약이 없어 매번 연결을 복원한다.
제안: 공통 조합을 입력·반환·실패가 명시된 함수로 만들고, 검증 후 관용구로 보관한다.
검증: 다른 입력과 후속 소비자에서도 같은 계약을 지키는지 확인한다.
      같은 목표의 품질·시간·전체 토큰은 측정한 범위에서 비교한다.
위험: 작업마다 다른 조건을 숨기거나 부분 실패를 전체 성공으로 바꾸지 않는다.
```

---

## 11. 보고 형식

발견사항을 다음 구조로 출력한다. 여러 발견은 **우선순위 순으로 최대 5개** (의사결정 마비 방지).

```
# indiebizOS 자기 점검 보고서
점검 시점: 2026-MM-DD HH:MM
모드: [전체 / 영역 집중 (X)]
대상 기간: 최근 N일
조사한 에피소드 수: N건

## 발견 1 (우선순위: 높음)
**관찰**: [데이터에서 본 사실, 횟수, 영향 시간/에이전트]
**해석**: [왜 문제로 보는지 — 시스템 어디에 어떤 영향]
**제안**: [어떤 수정이 효과적일지, 영향 범위]
**검증**: [수정 후 어떻게 확인할지]
**위험**: [수정의 부작용 가능성, 롤백 방법]

## 발견 2 (우선순위: 중간)
...

## 점검에서 보지 않은 영역
[영역 집중 모드인 경우, 보지 않은 다른 영역 명시]

## 다음 행동
사용자께서 처리하실 발견을 선택해주세요:
- "발견 1 고쳐줘" — 시스템 AI(나)에게 위임
- "발견 2는 외부 Claude Code 부르겠음" — 사용자가 직접 외부 호출
- "모두 보류" — 다음 점검 때 다시 검토

```

> **IBL 액션 실패 발견의 경우**: 위 템플릿에 더해 `[확인]`(transient / reproducible / state-dependent / 미검증)과 `[난이도]`(쉬움 / 중간 / 어려움 / 미상) 필드를 **관찰** 아래에 추가하라. 분류 기준은 섹션 4 "검증 절차" 참고.

---

## 12. 절대 금지 (안전선)

- **점검 요청만으로 코드·설정·DB를 변경하지 않는다.** 조회 재시도는 섹션 4의 계약·부수효과 판단을 따른다. 사용자가 수리를 요청한 경우 그 승인 범위에서 수리 절차로 진행한다.
- 백업·git checkpoint 없이 변경 금지 (수정 단계에서)
- 데이터 마이그레이션 같은 비가역 작업은 **제안만**, 직접 실행 절대 금지
- 아키텍처 큰 결정(새 모듈, DB 스키마 변경, 새 provider 통합)은 보고만 — 사용자가 외부 Claude Code와 협의할 작업이라 명시
- 사용자 개인 정보(건강·연락처 등) 보고서에 포함 금지 — 메타 통계만

---

## 13. 관측의 누락과 점검 영향

- 자동 통계는 원문 표본과 대조한다. 잘린 로그·`truncated`·조회 limit·미관측값을 전수·0건으로 해석하지 않는다.
- 로그가 비었거나 종료 시각이 없으면 궤적·쓰기 원장·`self:body diff`로 보완한다. 파일 mtime은 보조 단서이며 실행 주체의 증명이 아니다.
- 함수·클래스는 현재 시그니처와 다음 같은 들여쓰기 경계를 찾아 본문 전체를 읽는다. 예전 줄 번호와 길이를 그대로 쓰지 않는다.
- 진단 호출도 실행 기록·실패를 남길 수 있다. 실사용과 점검·훈련을 분리하고, 점검 자체가 기다리는 작업을 검사에서 다시 기다리는 순환 대기를 주의한다.
- 코드 수리 후 검사는 [회귀 규약](../../docs/REGRESSION_TESTING.md)을 따른다. 같은 후보·환경의 통과 결과를 재사용하고, 점검 환경에서만 생긴 실패를 시스템 고장이나 기존 실패로 단정하지 않는다.
- 새 교훈은 해당 절의 현재 지침에 통합한다. 사건별 수치·옛 상태는 [과거 관측 기록](../../docs/GUIDE_OBSERVATIONS_2026_10_30.md#자기-점검-실측)이나 해당 작업 기록에 남긴다.
