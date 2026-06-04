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
- "전부" → 전체 episode_log (최대 100개)

---

## 2. 데이터 소스 — 어디서 무엇을 가져오는가

당신은 Claude Code provider이므로 **Bash 명령으로 SQLite를 직접 쿼리**할 수 있다. 다음이 주요 데이터 소스:

### A. episode_log (가장 중요)
모든 사용자 요청의 실행 흐름 — 분류·의식·도구 호출·결과·평가 다 들어있음.

```bash
sqlite3 data/world_pulse.db "
SELECT id, started_at, agent, substr(user_message, 1, 80) AS msg,
       length(log) AS log_len, total_ms
FROM episode_log
WHERE started_at > datetime('now', '-7 days')
ORDER BY id DESC;
"
```

특정 에피소드 전체 로그:
```bash
sqlite3 data/world_pulse.db "SELECT log FROM episode_log WHERE id = ?;"
```

### B. episode_summary
요약된 메트릭 (영구 보존).

```bash
sqlite3 data/world_pulse.db "
SELECT * FROM episode_summary
WHERE started_at > datetime('now', '-30 days')
ORDER BY id DESC;
"
```

### C. self-check 결과
World Pulse의 IBL 액션 자가점검 이력.

```bash
sqlite3 data/world_pulse.db "
SELECT * FROM self_check_log
WHERE created_at > datetime('now', '-7 days')
ORDER BY id DESC;
"
```

(또는 직접 트리거: `[sense:self_check]` IBL 액션 호출)

### D. 시스템 AI 메모리
시스템 AI의 자체 메모리 (이전 점검 보고서 등이 여기 누적).

```bash
sqlite3 data/system_ai_memory.db "
SELECT id, category, substr(content, 1, 100) AS content, created_at
FROM memory
ORDER BY id DESC LIMIT 30;
"
```

### E. 심층 메모리 (사용자에 대한 사실)
중복·모순 검사용.

`[self:memory]{op: "search", query: "키워드"}` 또는:
```bash
sqlite3 data/system_ai_memory.db "
SELECT id, keywords, substr(content, 1, 100) AS content
FROM deep_memory ORDER BY id DESC LIMIT 50;
"
```

### F. 가이드 파일들
```bash
ls -la data/guides/*.md
```
파일별 내용은 Read 도구로.

### G. 프롬프트 파일들
```bash
ls -la data/common_prompts/*.md
```
역할·의식·평가·무의식 프롬프트들.

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
```bash
# episode_log에서 IBL_DEBUG 라인 추출 → 액션별 빈도·실패율 집계
sqlite3 data/world_pulse.db "SELECT log FROM episode_log WHERE started_at > datetime('now', '-7 days');" | \
  grep -E "IBL_DEBUG|execute_ibl" | head -200

# self_checks 테이블에서 최근 실패 액션 목록 (자동 자가점검 결과)
sqlite3 data/world_pulse.db "
SELECT node, action, COUNT(*) AS fail_cnt, MAX(timestamp) AS last_at,
       substr(error_message, 1, 120) AS err
FROM self_checks
WHERE success = 0 AND timestamp > datetime('now', '-7 days')
GROUP BY node, action, substr(error_message, 1, 120)
ORDER BY fail_cnt DESC;
"
```

**검증 절차 (실패 액션 재시도)**

위 신호로 잡힌 실패 액션은 보고 전 다음 절차로 검증한다. 단순히 "N회 실패" 보고에서 끝내지 말고, **진짜 고장인지 / 쉽게 고칠 수 있는지**까지 분류해야 보고가 행동 가능한 정보가 된다.

1. **idempotent 판단**
   - 안전 (재시도 OK): `sense:*`, `self:search_*` 등 모든 read-only 조회 액션
   - 금지 (원본 로그만 보고): `others:send_*`, `limbs:write_*`, `limbs:exec_*` 등 외부에 메시지를 보내거나 파일·DB를 쓰는 부수효과 액션
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

**데이터 수집:**
```bash
# 심층메모리 중복 후보
sqlite3 data/system_ai_memory.db "
SELECT keywords, COUNT(*) as cnt
FROM deep_memory GROUP BY keywords HAVING cnt > 1 ORDER BY cnt DESC;
"
```

---

### 6. 시스템 프롬프트

**찾을 신호:**
- consciousness_prompt가 지시한 JSON 형식이 깨진 의식 응답 빈도
- evaluator의 ACHIEVED/NOT_ACHIEVED 비율 (NOT_ACHIEVED가 30% 이상이면 prompt 문제 가능)
- 의식 에이전트가 achievement_criteria를 비워둔 케이스 빈도
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
- 가이드끼리 내용 충돌

**데이터 수집:**
```bash
# 의식 에이전트가 언급한 가이드 빈도 (episode_log의 guide_files JSON 필드)
sqlite3 data/world_pulse.db "SELECT log FROM episode_log WHERE log LIKE '%guide_files%' AND started_at > datetime('now', '-30 days');" | \
  grep -oE '"guide_files":\s*\[[^]]*\]' | sort | uniq -c | sort -rn
```

---

### 9. 인지 프로세스

**찾을 신호:**
- 분류 EXECUTE인데 짧은 시간 안에 같은 사용자가 후속 메시지로 보완 요청 (THINK였어야 함)
- 분류 THINK인데 의식 frame이 사실상 비어있음 (EXECUTE면 충분했음)
- GoalEval NOT_ACHIEVED 후 재실행해도 또 NOT_ACHIEVED (3라운드 다 소진)
- REFLEX_SCORE_THRESHOLD(0.88) 부근 점수에서 잘못된 분기 (해마 hit인데 결과 부적합)
- 같은 사용자 의도가 매번 다른 분류로 갈림 (분류기 일관성 문제)

---

## 10. 어휘 진화 후보 (점검의 핵심 산출물)

학습 누적 섹션의 정체성 선언에 따라, indiebizOS의 핵심 가치는 **누적된 어휘(IBL + 해마 + 가이드)** 이다. 따라서 자기 점검의 **가장 가치 있는 발견은 "어휘를 키울 기회" 의 식별**이다.

모든 점검에서 다음 신호를 **능동적으로** 찾고, 발견 시 다른 발견들보다 **한 단계 위 우선순위**로 보고하라. 단순 버그 발견보다 어휘 진화 후보가 indiebizOS의 정체성에 부합하는 발견이다.

### A. IBL 매크로 액션 후보 (조합 패턴 → 단일 어휘)

**찾을 신호**:
- 동일한 IBL 조합 패턴이 여러 에피소드에서 반복됨
- 의식 에이전트가 같은 hint(파이프라인 형태)를 반복 생성
- 한 에이전트가 매번 같은 도구 시퀀스를 자가 보정해서 만듦
- 가이드에 명시된 절차가 매번 같은 IBL 조합으로 실행됨

**제안 형식 예시**:
```
[발견] `[sense:paper]{op:"search", source:"pubmed", q:X} & [sense:search_ddg]{q:X}` 조합이
       의료 에이전트 최근 7일 12회 반복
[해석] 의학 정보 다각도 검색을 매번 모델이 재구성. 토큰·시간 비용 누적.
[제안] `[engines:medical_research]{query: ...}` 등록.
       내부 구현: PubMed + DDG 병렬 + 결과 정리
[검증] 등록 후 1주 — 의료 에이전트의 직접 호출이 매크로 호출로 대체되는지
[위험] 매크로가 너무 좁으면 어휘 비대. 본 패턴은 3개 이상 에이전트가
       쓰는지 확인 후 등록.
```

### B. 새 가이드 후보 (반복 절차 → 절차 메모리)

**찾을 신호**:
- 같은 종류의 task가 매번 처음부터 frame됨 (의식 에이전트 출력 구조 반복)
- 사용자가 자주 묻는 영역인데 해당 가이드가 없음
- 여러 에피소드의 task_framing이 사실상 같은 방법론을 재발견

**제안 형식 예시**:
```
[발견] "복약 상호작용 분석" 종류 질문이 N회, frame 구조 일관됨
[제안] `data/guides/medication_interaction_guide.md` 생성.
       핵심 절차: 약물 식별 → 상호작용 검색 → 부작용 검토.
       데이터 소스: PubMed + DrugBank
```

### C. 가이드 흡수 → 액션 격상 후보 (절차 → 어휘)

**찾을 신호**:
- 특정 가이드가 자주 highlight되고 그 절차가 항상 유사하게 수행됨
- 가이드 내용이 정형화된 IBL 파이프라인으로 환원 가능

**제안 형식 예시**:
```
[발견] `newspaper_guide.md` 가 지난 30일 N회 highlight, 매번 동일한 5단계 절차
[제안] 가이드 본문을 `[engines:newspaper_pipeline]` 매크로 액션으로 캡슐화.
       가이드는 사용 예시집으로 축소.
```

### D. 기존 어휘 개선 후보 (액션·가이드 수정)

신규 추가만이 진화가 아니다. 이미 있는 어휘를 다듬는 것도 진화. **자주 쓰이지만 매끄럽지 않은** 어휘를 찾아 다듬을 기회를 제안하라.

**IBL 액션 수정 신호**:
- 같은 액션이 같은 에러 패턴으로 자주 실패 (시그니처·검증·에러 메시지 부적정)
- 파라미터 명명 불일치로 자가 보정 빈번 (district_code vs region_code 같은)
- 의식 에이전트가 hint에서 액션 사용법을 매번 길게 설명 (시그니처가 직관적이지 않음)
- 같은 결과를 얻으려고 매번 다른 파라미터 조합을 시도
- 액션의 반환 형식이 후속 처리하기 어려움 (예: 파싱 매번 필요)

**가이드 수정 신호**:
- 가이드가 highlight되었으나 task가 자주 실패 또는 GoalEval NOT_ACHIEVED
- 가이드 안의 IBL 액션 참조가 stale (시그니처·이름 변경됨)
- 가이드가 다룬 시나리오 외 빈번한 변형이 episode_log에 등장 (커버리지 부족)
- 가이드끼리 같은 주제에 다른 방법론 제시 (충돌 해소 필요)
- 사용자가 자주 묻는 후속 질문이 가이드가 안 다룬 부분 (보강 필요)
- 가이드의 예시가 시대에 안 맞음 (옛 모델·옛 API 사용 등)

**제안 형식 예시 (액션 수정)**:
```
[발견] `[sense:house_rent]`이 `district_code` 잘못 쓰여 자가 보정 12회 발생
[해석] `[sense:apt_rent]`는 `district_code`, `[sense:house_rent]`는 `region_code` —
       명명 불일치가 매번 시간 낭비
[제안] 두 액션 모두 `region_code`로 통일.
       옛 명 `district_code`는 deprecation 경고와 함께 6개월 호환 유지
[검증] 통일 후 1주 — 해당 자가 보정 빈도 감소 측정
[위험] 외부에서 옛 명으로 호출하는 코드가 있으면 경고 발생 → 사용자가 정리
```

**제안 형식 예시 (가이드 수정)**:
```
[발견] `real_estate.md` 가이드 highlight 후에도 다가구 주택 영역에서 NOT_ACHIEVED 4회
[해석] 가이드가 아파트(apt_*) 위주, 다가구 주인세대 같은 비-아파트 시나리오 미흡
[제안] 가이드에 "다가구·단독주택 시세 조회" 섹션 추가.
       핵심: apt_* 액션은 아파트 한정 → house_rent + search_ddg 조합 사용.
       시·군별 행정구역 매핑 표 포함
[검증] 1주일 — 다가구·단독 관련 질문의 ACHIEVED 비율 측정
[위험] 가이드가 길어짐 → 의식 에이전트의 컨텍스트 부담 약간 ↑
```

---

### 보고 시 표기

위 네 카테고리의 발견은 보고서에서 **`[어휘진화]` 태그 + 우선순위 ★★★** 로 마킹하라:

```
## 발견 1 [어휘진화-A] (우선순위: ★★★)
**관찰**: ...
**해석**: ...
**제안**: ...
```

→ 사용자가 보고서를 읽을 때 "이건 시스템 키우는 발견" 임을 즉시 인식하게 된다.

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

- **사용자 명시 승인 없이 코드·설정·DB 변경 금지** — 점검 단계에선 read-only. 단, idempotent IBL 액션(`sense:*`, `self:search_*` 등)의 1회 재시도는 관찰 행위로 허용 (섹션 4 검증 절차 참고)
- 백업·git checkpoint 없이 변경 금지 (수정 단계에서)
- 데이터 마이그레이션 같은 비가역 작업은 **제안만**, 직접 실행 절대 금지
- 아키텍처 큰 결정(새 모듈, DB 스키마 변경, 새 provider 통합)은 보고만 — 사용자가 외부 Claude Code와 협의할 작업이라 명시
- 사용자 개인 정보(건강·연락처 등) 보고서에 포함 금지 — 메타 통계만

---

## 13. 학습 누적 (시간이 지나며 채워짐)

이전 점검에서 얻은 교훈·고정된 사실들이 여기 쌓인다. 이 가이드를 따를 때 참고한다.

**누적 항목 형식**:
```
- [YYYY-MM-DD] [영역] 관찰·교훈 (이전 점검 보고서 ID 참조 가능)
```

**현재 누적**:

- [2026-05-25] [정체성] indiebizOS의 핵심 가치는 **IBL 액션(언어) + 해마(패턴) + 가이드(절차)** 의 누적 어휘이다. 모델 파워(opus 등)는 commodity가 되어가지만 이 어휘는 사용자별로 시간이 쌓아올린 이전 불가능한 자산이다. 따라서 자기 점검의 우선순위는 **어휘의 정확성·일관성·풍부함을 보존·확장하는** 방향으로 정렬한다. 단순 버그픽스보다 어휘 건강에 영향을 주는 발견(IBL 액션 정의 명료화, 해마 학습 루프 신뢰성, 가이드의 현실 정합성 등)을 더 높은 우선순위로 보고한다.

- [2026-05-25] [Read 휴리스틱] **자기가 직전 턴에 수정한 파일을 점검에서 다시 읽을 때**, 옛 범위 감각이 어긋난다 — 자기 patch로 함수가 길어졌다는 사실을 잊고 좁은 limit으로 읽어 본문이 잘림. 다음 순서로 읽어라:
  1. `Grep` 으로 함수/클래스 시그니처 라인 찾기 (`pattern: "^def 함수명\|^class 클래스명"`, `-n: true`)
  2. 종료 라인은 다음 같은 인덴트의 `def`/`class` 또는 파일 끝
  3. `Read` 의 `offset`/`limit` 을 정확한 범위로 전달
  - 대안 (빠른 휴리스틱): 자기 patch한 파일은 평소 추정 limit의 **1.5배**로 읽기. 잘리면 한 번 더 호출하는 게 토큰 손실보다 디버깅 손실이 큼.
  - 출처: episode 206 (2026-05-25 19:21) — `agent_cognitive.py`의 `_classify_request` 검증 시 `offset=603 limit=45` 로 읽어 본문 끝부분(약 668줄)이 잘려 `offset=647 limit=25` 보충 호출 발생.

- [2026-05-25] [방법론] 어휘 진화 후보 (섹션 10)는 4유형으로 구성된다:
  - **A**: IBL 액션 신규 등록 (조합 패턴 → 매크로 어휘)
  - **B**: 새 가이드 작성 (반복 frame → 절차 메모리)
  - **C**: 가이드 → 액션 격상 (정형 절차의 어휘화)
  - **D**: 기존 어휘 (액션·가이드) 수정 — 시그니처·파라미터·내용 다듬기

  특히 **D는 점검 사이클이 누적되어야 드러나는 신호**다 — 한 번의 점검만으론 "이 파라미터가 매번 헷갈리는지" 판단하기 어렵고, 여러 점검에서 같은 신호가 반복돼야 명확해진다. 따라서:
  - **첫 점검**: A·B 위주 발견. D는 적거나 0개. 정상.
  - **시간이 지나면**: D 발견이 늘어남. 이는 시스템이 자기를 깊이 보고 있다는 신호.
  - **D가 계속 0이면**: 신호 정의를 다듬을 시점. 13번 학습 누적의 새 항목으로 보강.

---

## 마무리

점검은 시스템이 자기 자신을 보는 행위이다. 무엇을 발견했는지보다 **무엇을 발견했다고 보고했는지** 가 중요하다. 사용자가 그 보고를 읽고 시스템을 어디로 키울지 결정한다.

당신은 점검자이지 수리공이 아니다. 본 것을 정직하게 보고하라.
