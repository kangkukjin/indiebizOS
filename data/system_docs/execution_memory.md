# 실행기억 (Execution Memory) & 해마 (Hippocampus)

> 사용자 명령 당 1회 생성, 파이프라인 전체가 공유하는 통합 기억 시스템

## 개요

사용자 명령이 들어오면 **파이프라인 최상단에서 실행기억을 1회 생성**하고, 이후 무의식/의식/실행/평가 에이전트가 모두 동일한 실행기억을 공유한다.

### 왜 실행기억인가

- 무의식 에이전트가 EXECUTE/THINK를 판정하려면 **관련 액션이 뭔지** 알아야 한다
- 의식 에이전트가 문제를 구성하려면 **과거 코드 사례와 액션의 구현 상세**를 알아야 한다
- 실행 에이전트가 코드를 생성하려면 **참고 사례와 파라미터 형식**을 알아야 한다
- 평가 에이전트가 검증하려면 **어떤 도구가 있었고 어떻게 동작하는지** 알아야 한다

이 모든 것이 같은 데이터에서 나온다. 한 번 만들어서 공유하는 것이 자연스럽다.

## 실행기억의 구성

```
실행기억 = {
    과거 IBL 코드 사례               ← 해마 (fine-tuned 임베딩 검색)
    키워드 기반 관련 액션             ← discover (키워드 매칭, 비용 0)
    언급된 모든 액션의 implementation ← ibl_nodes.yaml에서 조회
}
```

| 요소 | 출처 | 역할 |
|------|------|------|
| 과거 코드 사례 | 해마 (`search_hybrid`) | "비슷한 명령에 이렇게 쓰였다" — 코드 생성의 참고 |
| 추천 도구 | discover (키워드 매칭) | "이 명령에 관련된 액션은 이것이다" — 액션 탐색 |
| implementation | ibl_nodes.yaml | "이 액션은 이렇게 동작한다" — 자기 몸 인식 |

### implementation 수집 방식

1. discover가 찾은 액션 → action_details에 implementation 포함
2. RAG/해마 코드 사례에서 `[node:action]` 패턴 파싱 → 추가 implementation 조회
3. 두 출처에서 모두 수집하므로, 해마가 떠올린 액션의 implementation도 누락되지 않음

---

## 파이프라인 흐름

```
사용자 명령
    ↓
실행기억 생성 (해마 + discover + implementation, 1회, 밀리초)
    ↓
무의식 에이전트 ← 실행기억 (관련 액션 정보로 EXECUTE/THINK 판정)
    ↓
    ├─ EXECUTE → 실행 에이전트 ← 시스템 프롬프트에 실행기억 포함
    │
    └─ THINK → 의식 에이전트 ← 실행기억 (문제 구성 + 달성 기준)
                    ↓
               실행 에이전트 ← 시스템 프롬프트에 실행기억 + 의식 출력 + 달성 기준
                    ↓
               평가 에이전트 ← 실행기억 (도구 활용 적절성 검증)
```

### 주입 위치

- **무의식 에이전트**: 실행기억을 사용자 메시지 앞에 프리펜드
- **의식 에이전트**: `<ibl_nodes>` 태그 안에 실행기억 전달
- **실행 에이전트**: `prompt_builder`가 시스템 프롬프트에 실행기억 삽입 (IBL 환경 바로 뒤)
- **평가 에이전트**: 평가 프롬프트의 "실행기억" 섹션

### XML 출력 형식

```xml
<execution_memory note="실행기억: 과거 코드 사례 + 추천 도구 + 구현 상세. 반드시 execute_ibl 도구로 실행하세요.">
<ibl_references note="...">
  <ref intent="재즈 음악 틀어줘" code='[limbs:play]{query: "jazz"}' score="8.55"/>
</ibl_references>
<tools note="키워드 기반 추천 도구">
  <tool action="play" description="음악 재생" implementation="YouTube 검색 후 스트리밍" example='[limbs:play]{...}'/>
</tools>
<implementations note="코드 사례에 등장하는 도구의 구현 상세">
  <impl action="[self:schedule]" implementation="APScheduler 기반 예약 실행"/>
</implementations>
</execution_memory>
```

---

## 해마 (Hippocampus)

뇌의 해마가 의식적 사고 없이 여러 기억 저장소에서 관련 기억을 자동으로 끌어올리듯, IBL 도메인에 특화된 fine-tuned 임베딩 모델이 밀리초 내에 관련 IBL 코드 사례를 인출한다.

### 성능

| | Baseline (범용 ko-sroberta) | Fine-tuned 해마 | 개선 |
|---|---|---|---|
| Top-1 | 19.3% | **71.3%** | +52.0%p |
| Top-3 | 38.5% | **90.9%** | +52.4%p |
| Top-5 | 45.8% | **95.6%** | +49.8%p |

### 학습의 핵심 결정

**코드 정규화**: IBL 코드에서 파라미터를 제거하고 액션 패턴만으로 학습한다.
- 정규화 전: `[sense:stock_info]{symbol: "삼성전자"}`와 `{symbol: "AAPL"}`이 **다른 정답**으로 경쟁
- 정규화 후: 둘 다 `[sense:stock_info]`로 통합되어 서로 **강화**
- 489개 코드 → 356개 패턴으로 축소, 패턴당 학습 사례 증가

**패턴 내 분할**: 테스트셋을 패턴 단위가 아닌 **패턴 내 intent 단위**로 분리한다.
- 각 패턴의 intent를 80% 학습 / 20% 테스트로 나눔
- 모든 패턴이 학습과 테스트 양쪽에 존재하여 공정한 평가

### 학습 데이터

| 데이터 | 수량 | 설명 |
|--------|------|------|
| DB 원본 | 535건 | (intent, ibl_code) 쌍 |
| 규칙 기반 변형 | 1,295건 | 어미/명사 치환 (기계적) |
| Opus 직접 생성 | 2,479건 | 구어체, 의미적 도약, 비정형 표현 |
| 액션 description | 372개 | ibl_nodes.yaml에서 추출 |
| **학습 쌍** | **3,240개** | 정규화 후 356개 패턴 |
| **테스트 쌍** | **1,033개** | |

**핵심 발견: 데이터 품질 > 데이터 양.** 규칙 기반 합성 2,173건보다 Opus 395건이 더 효과적이었다.

### 학습 구조

세 가지 유형의 학습 쌍:
1. **intent ↔ intent**: 같은 액션 패턴을 공유하는 자연어 명령 쌍
2. **intent → pattern**: 자연어 → 정규화된 액션 패턴 매핑
3. **intent → description**: 자연어 → 액션 설명 매핑 (cross-modal)

- Loss: MultipleNegativesRankingLoss
- 최적 epoch: 5 (10 epoch 중)
- 하드웨어: M2 MacBook (Apple Silicon MPS)

### 학습 곡선

```
Epoch 1: 90.0%
Epoch 2: 94.4%
Epoch 3: 94.7%
Epoch 4: 95.3%
Epoch 5: 95.6%  ★ 최적
Epoch 6: 94.5%
Epoch 7: 95.5%
Epoch 8: 95.2%
Epoch 9: 94.4%
Epoch 10: 95.0%
```

---

## IBL 용례 RAG 상세

### 하이브리드 검색

검색은 **시맨틱(의미 기반) + BM25(키워드 기반)**을 결합한 하이브리드 방식이다.

```
사용자 메시지: "대구 아파트 실거래가 알려줘"
                    |
    ┌───────────────┴───────────────┐
    v                               v
 시맨틱 검색 (70%)              BM25 검색 (30%)
 - 모델: fine-tuned 해마        - FTS5 풀텍스트
 - 768차원 벡터                 - 한국어 조사 제거
 - 코사인 유사도                - OR 매칭
    |                               |
    └───────────────┬───────────────┘
                    v
          가중 합산 (alpha=0.7)
                    v
          상위 k개 결과 반환
```

### 임베딩 모델

- **모델**: `data/models/ibl_embedding/` (IBL 도메인 fine-tuned, 베이스: ko-sroberta-multitask)
- **차원**: 768
- **벡터 DB**: sqlite-vec (SQLite 확장)
- **로딩**: 서버 시작 시 백그라운드 스레드에서 비동기 로딩

### 용례 사전 DB

```sql
-- 용례 사전 (약 525개)
ibl_examples (
  id, intent TEXT,        -- 사용자 의도 (자연어)
  ibl_code TEXT,          -- IBL 코드 (정답)
  nodes TEXT,             -- 관련 노드 (sense, self 등)
  category TEXT,          -- single / pipeline / complex
  difficulty INT,         -- 난이도 (1-5)
  source TEXT,            -- curated / synthetic / auto_log / manual
  tags TEXT,
  success_count INT, fail_count INT,
  created_at TEXT, updated_at TEXT
)

-- 벡터 인덱스 (sqlite-vec, 768차원)
ibl_examples_vec (embedding float[768])

-- FTS5 키워드 인덱스
ibl_examples_fts (intent, ibl_code)

-- 실행 로그 (모든 도구 호출 기록)
ibl_execution_logs (
  id, user_input TEXT,       -- 원본 사용자 메시지
  generated_ibl TEXT,        -- 생성된 IBL 코드
  node TEXT, action TEXT,    -- 실행된 노드/액션
  target TEXT, params_json TEXT,
  success INT,               -- 성공 여부 (0/1)
  error_message TEXT,
  duration_ms INT,
  agent_id TEXT, project_id TEXT,
  created_at TEXT
)
```

### 실행 로그 자동 승격

에이전트가 도구를 성공적으로 실행하면, 그 기록이 자동으로 용례 사전에 추가된다.

```
에이전트 대화 완료
    ↓
IBLUsageDB.try_promote_session(user_input)
    ├── 성공 로그 있는가? → 없으면 종료
    ├── 같은 intent 용례가 이미 있는가? → 있으면 스킵
    ├── IBL 코드 추출 가능한가? → 불가하면 스킵
    ↓
용례 DB에 source='auto_log'로 추가 → 다음 유사 요청 시 해마가 인출
```

### 필터링

- **최소 점수**: 0.25 미만의 결과는 제외
- **IBL 관련성**: 인사, 감탄사, 짧은 메시지는 검색 스킵
- **캐시**: 동일 쿼리는 5분간 캐시 (TTL 300초)
- **허용 노드**: 에이전트의 `allowed_nodes` 범위 내 용례만 반환

### 설정

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `MAX_REFERENCES` | 5 | 최대 참조 수 |
| `DEFAULT_K` | 3 | 기본 반환 참조 수 |
| `MIN_SCORE` | 0.25 | 최소 점수 임계값 |
| `ALPHA` | 0.7 | 시맨틱 가중치 (1-ALPHA = BM25) |
| `EMBEDDING_DIM` | 768 | 벡터 차원 |

---

## 뇌 구조와의 대응

| 뇌 구조 | IndieBiz OS 컴포넌트 | 역할 |
|---------|---------------------|------|
| 기저핵 | 무의식 에이전트 | 사후 엔트로피 → EXECUTE/THINK 게이팅 |
| **해마** | **fine-tuned 임베딩 + discover** | **여러 기억 저장소에서 자동 인출 (밀리초)** |
| 전전두엽 | 의식 에이전트 | 자기 참조적 문제 구성 + 달성 기준 설정 |
| 운동피질 | 실행 에이전트 | IBL 코드 생성 및 실행 |
| 전대상피질 | 평가 에이전트 | 달성 기준 대비 검증, 최대 3라운드 |

기존 3단 인지 아키텍처(무의식/의식/평가)에 **해마(기억 인출)**가 추가되어 4단 아키텍처(게이팅/기억인출/의식적사고/평가)로 진화.

---

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `backend/ibl_usage_rag.py` | `build_execution_memory()` — 실행기억 생성 메인 함수 |
| `backend/ibl_usage_db.py` | 하이브리드 검색 엔진 (해마 모델 + FTS5) |
| `backend/node_registry.py` | `discover()` — 키워드 기반 액션 탐색 |
| `backend/agent_runner.py` | `_build_execution_memory()` — 파이프라인 통합 |
| `backend/api_websocket.py` | GUI/WebSocket 경로에서 실행기억 생성 및 전달 |
| `backend/api_system_ai.py` | 시스템 AI 경로에서 실행기억 생성 및 전달 |
| `backend/prompt_builder.py` | 시스템 프롬프트에 실행기억 삽입 |
| `data/models/ibl_embedding/` | fine-tuned 해마 모델 |
| `backend/ibl_embedding_trainer.py` | 해마 학습 스크립트 |
| `backend/ibl_synthetic_opus.py` | Opus 합성 데이터 생성기 |

---

## 확장 계획: 다중 기억 채널

현재 해마는 IBL 코드 사례 채널만 구현되어 있다. 나머지 채널:

| 채널 | Key (언제 떠올리는가) | Value (무엇을 떠올리는가) | 현재 컴포넌트 |
|------|---------------------|-------------------------|--------------|
| **IBL 기억** (구현됨) | 명령 패턴 임베딩 | IBL 코드 사례 | ibl_usage_db.py |
| 사용자 기억 | 대화 맥락 임베딩 | 사용자 선호, 습관 | system_ai_memory.db |
| 이웃 기억 | 인물/관계 맥락 | 연락처, 최근 상호작용 | business_manager.py |
| 프로젝트 기억 | 작업 맥락 임베딩 | 프로젝트 상태, 진행 중 작업 | project_manager.py |
| 대화 기억 | 대화 주제 임베딩 | 최근 대화의 핵심 맥락 | conversation_db.py |

각 채널은 `build_execution_memory()` 함수에 추가하면 파이프라인 구조 변경 없이 확장된다.

---

*마지막 업데이트: 2026-04-01*
