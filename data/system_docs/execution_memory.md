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
    언급된 모든 액션의 implementation ← ibl_nodes.yaml에서 조회
}
```

| 요소 | 출처 | 역할 |
|------|------|------|
| 과거 코드 사례 | 해마 (`search_hybrid`) | "비슷한 명령에 이렇게 쓰였다" — 코드 생성의 참고 |
| implementation | ibl_nodes.yaml | "이 액션은 이렇게 동작한다" — 자기 몸 인식 |

implementation은 해마가 떠올린 코드 사례에서 `[node:action]` 패턴을 파싱하여 자동 조회한다.

---

## 파이프라인 흐름

```
사용자 명령
    ↓
실행기억 생성 (해마 + implementation, 1회) + 해마 점수 기록
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
    ↓
대화 완료 → 경험 증류 (해마 점수가 낮으면 반성 에이전트가 용례 생성)
```

### 주입 위치

- **무의식 에이전트**: 실행기억을 사용자 메시지 앞에 프리펜드
- **의식 에이전트**: `<ibl_nodes>` 태그 안에 실행기억 전달
- **실행 에이전트**: `prompt_builder`가 시스템 프롬프트에 실행기억 삽입 (IBL 환경 바로 뒤)
- **평가 에이전트**: 평가 프롬프트의 "실행기억" 섹션

### XML 출력 형식

```xml
<execution_memory note="실행기억: 과거 코드 사례 + 구현 상세. 반드시 execute_ibl 도구로 실행하세요.">
<ibl_references note="...">
  <ref intent="재즈 음악 틀어줘" code='[limbs:play]{query: "jazz"}' score="0.7555"/>
</ibl_references>
<implementations note="코드 사례에 등장하는 도구의 구현 상세">
  <impl action="[limbs:play]" implementation="yt-dlp로 유튜브 URL 추출 + mpv/ffplay로 스트리밍 재생"/>
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

### 검색 방식

시맨틱(의미 기반) 검색이 기본이다. BM25(키워드)는 시맨틱이 불가능할 때만 폴백으로 사용된다.

```
사용자 메시지: "대구 아파트 실거래가 알려줘"
                    ↓
             시맨틱 검색 (ALPHA=1.0)
             - 모델: fine-tuned 해마
             - 768차원 벡터
             - 코사인 유사도
                    ↓
             시맨틱 실패 시 → BM25 폴백
                    ↓
             상위 k개 결과 반환
```

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `MAX_REFERENCES` | 5 | 최대 참조 수 |
| `DEFAULT_K` | 5 | 기본 반환 참조 수 |
| `MIN_SCORE` | 0.25 | 최소 점수 임계값 |
| `ALPHA` | 1.0 | 시맨틱 100% (BM25는 폴백 전용) |

---

## 경험 증류 (Experience Distillation)

대화가 끝난 후, 해마가 모르는 패턴이었는데 실행이 성공했으면 **반성 에이전트**가 그 경험에서 용례를 추출하여 해마에 저장한다.

### 증류 조건

```
해마 점수 0.7+ → 스킵 (이미 아는 패턴)
해마 점수 0.7 미만 + IBL 호출 성공 → 반성 에이전트 호출 → 증류
```

해마가 성숙할수록 증류 빈도는 줄어든다. 처음엔 자주, 나중엔 거의 안 한다.

### 증류 파이프라인

```
대화 완료
    ↓
해마 점수 확인 (build_execution_memory 시점에 기록)
    ↓
0.7 미만? → 반성 에이전트 호출 (무의식 에이전트와 같은 경량 AI)
    ↓
실행 로그에서 교훈 추출:
  - 중복/탐색성 호출 제거
  - 핵심 액션 패턴만 남김
  - intent를 일반화 ("프로젝트 헤일메리 평" → "영화 리뷰 검색")
    ↓
add_example() → DB 저장 + 임베딩 즉시 생성 (~8ms)
    ↓
JSON 파일에도 누적 (data/training/ibl_distilled.json)
    ↓
다음 대화부터 해마가 인출 가능
```

### 반성 에이전트

- **프롬프트**: `data/common_prompts/reflection_prompt.md`
- **모델**: 무의식 에이전트와 같은 경량 AI (`lightweight_ai_call`)
- **역할**: 날것의 실행 로그에서 시행착오를 걸러내고 재사용 가능한 패턴만 추출
- **출력**: `{"intent": "일반화된 의도", "code": "IBL 코드"}` JSON

### 두 단계의 학습

| 단계 | 시점 | 효과 |
|------|------|------|
| **즉시 반영** | 매 대화 후 (조건부) | DB + 범용 임베딩 → 바로 검색 가능 (불완전하지만 없는 것보다 나음) |
| **주기적 재학습** | 수동 (누적 후) | 기존 학습 데이터 + 증류 데이터 합쳐서 해마 모델 fine-tuning |

### 도구 호출 이력 수집

증류에 필요한 도구 호출 이력은 두 경로에서 수집된다:

| 경로 | 수집 방식 |
|------|----------|
| WebSocket (GUI 대화) | `tool_start` 이벤트에서 `tool_calls_log`에 직접 수집 |
| 채널 (Gmail/Nostr) | `system_tools._log_ibl()` → `thread_context.append_tool_call()` |

---

## 학습 데이터

학습 데이터는 `data/training/` 폴더에 통합 관리된다.

```
data/training/
├── ibl_synthetic_opus_final_2479.json   ← Opus 직접 생성 (고품질, 2,479건)
└── ibl_distilled.json                   ← 경험 증류 자동 누적 (운용 중 생성)
```

**핵심 발견: 데이터 품질 > 데이터 양.** 규칙 기반 합성은 품질이 낮아 제거했다.

학습 스크립트(`ibl_embedding_trainer.py`)는 `data/training/*.json`을 전부 읽으므로, 증류 데이터가 쌓이면 재학습 시 자동 포함된다.

### 재학습 (Re-training)

재학습은 증류 데이터가 충분히 쌓였을 때 수동으로 실행한다.

```bash
cd /Users/kangkukjin/Desktop/AI/indiebizOS/backend
python ibl_embedding_trainer.py
```

**핵심 원칙:**
- **항상 원본 모델에서 시작**: 매번 범용 모델(`ko-sroberta-multitask`)에서 처음부터 fine-tuning. 기존 학습 모델에 이어서 학습하지 않음 (catastrophic forgetting 방지)
- **MPS 가속**: Apple Silicon GPU(`device="mps"`)로 학습 (CPU 대비 2~4배 속도)
- **액션별 데이터 밸런싱**: 자주 쓰는 액션의 증류 데이터가 편중 축적되는 문제를 방지. 학습 시 액션별 상한(기본 20건)을 두고, 초과분은 오래된 데이터부터 제거하여 최신 데이터 우선 유지

### 학습의 핵심 결정

**코드 정규화**: IBL 코드에서 파라미터를 제거하고 액션 패턴만으로 학습한다.
- 정규화 전: `[sense:stock_info]{symbol: "삼성전자"}`와 `{symbol: "AAPL"}`이 **다른 정답**으로 경쟁
- 정규화 후: 둘 다 `[sense:stock_info]`로 통합되어 서로 **강화**

**패턴 내 분할**: 테스트셋을 패턴 단위가 아닌 **패턴 내 intent 단위**로 분리한다.

### 학습 구조

세 가지 유형의 학습 쌍:
1. **intent ↔ intent**: 같은 액션 패턴을 공유하는 자연어 명령 쌍
2. **intent → pattern**: 자연어 → 정규화된 액션 패턴 매핑
3. **intent → description**: 자연어 → 액션 설명 매핑 (cross-modal)

- Loss: MultipleNegativesRankingLoss
- 최적 epoch: 5 (10 epoch 중)

---

## 용례 사전 DB

```sql
-- 용례 사전 (약 926개, source별: curated_v2/v3 495, curated_v4 140, manual 43 등)
ibl_examples (
  id, intent TEXT,        -- 사용자 의도 (자연어)
  ibl_code TEXT,          -- IBL 코드 (정답)
  nodes TEXT,             -- 관련 노드 (sense, self 등)
  category TEXT,          -- single / pipeline
  difficulty INT,         -- 난이도 (1-5)
  source TEXT,            -- curated_v2 / curated_v3 / curated_v4 / distilled / manual
  tags TEXT,
  success_count INT, fail_count INT,
  created_at TEXT, updated_at TEXT
)

-- 벡터 인덱스 (sqlite-vec, 768차원)
ibl_examples_vec (embedding float[768])

-- FTS5 키워드 인덱스 (시맨틱 폴백용)
ibl_examples_fts (intent, ibl_code)
```

---

## 뇌 구조와의 대응

| 뇌 구조 | IndieBiz OS 컴포넌트 | 역할 |
|---------|---------------------|------|
| 기저핵 | 무의식 에이전트 | EXECUTE/THINK 게이팅 |
| **해마** | **fine-tuned 임베딩** | **과거 경험에서 관련 기억 자동 인출 (밀리초)** |
| 전전두엽 | 의식 에이전트 | 자기 참조적 문제 구성 + 달성 기준 설정 |
| 운동피질 | 실행 에이전트 | IBL 코드 생성 및 실행 |
| 전대상피질 | 평가 에이전트 | 달성 기준 대비 검증 |
| **소뇌** | **반성 에이전트** | **경험 증류 — 성공 패턴을 해마에 저장** |

4단 인지 아키텍처(게이팅/기억인출/의식적사고/평가)에 **반성(경험 증류)**가 추가.

---

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `backend/ibl_usage_rag.py` | `build_execution_memory()` — 실행기억 생성, `distill_experience()` — 경험 증류 |
| `backend/ibl_usage_db.py` | 시맨틱 검색 엔진 (해마 모델 + FTS5 폴백) |
| `backend/agent_cognitive.py` | `_build_execution_memory()` — 파이프라인 통합 |
| `backend/api_websocket.py` | GUI/WebSocket 경로에서 실행기억 생성, 도구 이력 수집, 경험 증류 |
| `backend/agent_communication.py` | 채널 경로에서 실행기억 생성 및 경험 증류 |
| `backend/system_tools.py` | `_log_ibl()` — 도구 호출 이력을 thread_context에 기록 |
| `backend/thread_context.py` | `append_tool_call()` — 스레드별 도구 호출 이력 관리 |
| `backend/prompt_builder.py` | 시스템 프롬프트에 실행기억 삽입 |
| `data/models/ibl_embedding/` | fine-tuned 해마 모델 |
| `data/training/` | 학습 데이터 (Opus 합성 + 경험 증류 누적) |
| `data/common_prompts/reflection_prompt.md` | 반성 에이전트 프롬프트 |
| `backend/ibl_embedding_trainer.py` | 해마 학습 스크립트 |

---

*마지막 업데이트: 2026-04-06*
