---
title: 연상기억 — 해마 + 심층메모리
scope: 시맨틱 검색, fine-tuned 임베딩, 경험 증류, 학습 데이터, 인지 파이프라인 단계 0
owner_code: ibl_usage_db.py, ibl_usage_rag.py, ibl_embedding_trainer.py, agent_cognitive.py, memory_db.py
last_updated: 2026-05-28
see_also: [architecture.md, ibl.md]
---

# 연상기억 (Associative Memory) — 해마 + 심층메모리 통합

> 사용자 명령 당 1회 생성, 파이프라인 전체가 공유하는 통합 기억 시스템

## 개요

사용자 명령이 들어오면 **파이프라인 최상단(단계 0)에서 연상기억을 1회 생성**하고, 이후 무의식·의식·실행·평가 에이전트가 모두 동일한 연상기억을 공유한다.

연상기억은 두 종류의 기억으로 구성된다:

| 종류 | 출처 | 내용 |
|------|------|------|
| **실행기억** (`<execution_memory>`) | 해마 — IBL Usage DB | 과거 IBL 코드 사례 + 도구 implementation |
| **관련기억** (`<related_memory>`) | 심층메모리 — 에이전트별 SQLite | 사용자 사실·선호·결정·작업 이력 |

두 종류 모두 동일한 fine-tuned 임베딩 모델로 검색된다. 모델은 backend에서 한 번만 로드되어 두 시스템이 공유한다 (메모리 중복 없음).

### 왜 연상기억인가

- 무의식이 EXECUTE/THINK를 판정하려면 **관련 액션과 메모리**가 뭔지 알아야 한다
- 의식이 문제를 구성하려면 **과거 코드 사례, 도구 구현 상세, 사용자 맥락**을 알아야 한다
- 실행이 코드를 생성하려면 **참고 사례, 파라미터 형식, "내 ~", "방금 ~" 같은 사용자 컨텍스트**를 알아야 한다
- 평가가 검증하려면 **어떤 도구가 있었고 어떻게 동작하는지**를 알아야 한다

이 모든 것이 같은 데이터에서 나온다. 한 번 만들어서 공유하는 것이 자연스럽다.

---

## 단일 검색 일원화 (2026-05-17 재설계)

이전에는 해마 검색이 한 메시지당 **3번** 일어났다 (build_execution_memory, _get_top_score, _try_reflex). 검증 후 단일 검색으로 일원화했다.

```python
# agent_cognitive._build_execution_memory()
exec_xml, top_score, top_code = build_execution_memory(user_message, allowed_set)
related = self._search_related_memory(user_message)
result = (exec_xml + "\n" + related) if related else exec_xml
return (result, top_score, top_code)   # 한 번의 검색으로 점수/코드까지 확보
```

호출 측(`agent_communication`, `api_websocket`, `system_ai_core`)이 top_score를 받아 직접 Reflex 분기를 결정한다 — 무의식 모델을 거치지 않는다.

---

## 파이프라인 흐름

```
사용자 명령
    ↓
[0] 연상 단계 — _build_execution_memory()
    └─ 해마 검색 1회로 (xml, top_score, top_code) 확보
       <execution_memory> + <related_memory> 결합
    ↓
[1] Reflex 분기 (호출 측에서 결정)
    ├─ top_score ≥ 0.85 → 무의식 스킵, 곧장 EXECUTE + reflex_hint
    └─ 미만 → 무의식 (경량 AI) — EXECUTE/THINK 판정
    ↓
THINK → 의식 에이전트 ← 연상기억 (문제 정의 + 달성 기준)
    ↓
[3] 실행 에이전트 ← 시스템 프롬프트에 연상기억 + (의식 출력)
    EXECUTE/Reflex → 중급 모델 / THINK → 본격 모델
    ↓
[4] 평가 에이전트 ← `## 연상기억` 섹션으로 전달
    ↓
[5] 증류
    ├─ 해마: top_score < 0.7 + 도구 호출 성공 → distill_experience()
    └─ 심층메모리: _distill_deep_memory() — 경량 AI로 사실 추출 → NEW/UPDATE/SAME
```

### 주입 위치 (모든 에이전트가 동등하게 self-describing 블록을 받음)

- **무의식**: 사용자 메시지 앞에 prepend
- **의식**: 외부 래퍼 없이 `<execution_memory>` + `<related_memory>` 직접 노출 (2026-05-17 정리)
- **실행** (프로젝트/시스템 AI): `prompt_builder`가 시스템 프롬프트에 그대로 삽입
- **평가**: markdown `## 연상기억` 헤더로 그룹화 (2026-05-17 정정 — 옛 "실행기억" 헤더는 부정확)
- **에이전트 간 위임**: 메시지 prepend

### XML 출력 형식 (현재)

```xml
<execution_memory note="과거 코드 사례 + 구현 상세">
  <ibl_references note="참고 용례. execute_ibl 도구로 실행하고, 텍스트 응답에 IBL 코드를 넣지 마라.">
    <ref intent="아이유 밤편지 틀어" code='[limbs:play]{query: "아이유 밤편지"}' score="0.9827"/>
  </ibl_references>
  <implementations note="코드 사례에 등장하는 도구의 구현 상세">
    <impl action="[limbs:play]" implementation="yt-dlp로 유튜브 URL 추출 + mpv/ffplay로 스트리밍 재생"/>
  </implementations>
</execution_memory>
<related_memory note="심층 메모리에서 연상된 관련 기억입니다. 참고용.">
  <memory category="사용자선호" keywords="바흐,클래식음악">바흐의 음악을 즐김</memory>
</related_memory>
```

각 태그가 self-describing이라 별도 외부 래퍼는 불필요.

---

## 해마 (Hippocampus)

뇌의 해마처럼 fine-tuned 임베딩 모델이 밀리초 내에 관련 IBL 코드 사례를 인출한다.

### 현재 성능 (2026-06-04 Modal GPU 재학습 — 144 액션 어휘 기준)

| 지표 | Baseline (범용 ko-sroberta) | Fine-tuned 해마 | 개선 |
|---|---|---|---|
| Top-1 (code) | 24.3% | **72.1%** | +47.8%p |
| Top-3 (code) | 38.5% | **89.2%** | +50.7%p |
| Top-5 (code) | 45.4% | **94.5%** | +49.1%p |
| Top-5 (description) | 67.0% | **93.5%** | +26.5%p |

- **실제 런타임 검색 정확도 ~99%**: 위 벤치마크(query→벌거벗은 코드 패턴)는 보수적 프록시다. 런타임은 query→저장용례(`intent×3 + code`)로 검색하므로(아래 "검색 방식") 액션단위 Top-5 ≈ **99.3%**(Top-1 96.4%)로 천장.
- 학습 데이터: usage_db 2,324건 + 규칙 변형 → 236 고유 패턴 (144 액션 커버)
- 학습 환경: **Modal 서버리스 GPU(T4, cuda)**, batch=16, max_seq 128, 10 epoch. 트레이너 개선(조기종료 code+desc 블렌드 모니터·`torch.manual_seed`·밸런싱 상한 30). 베이스 `jhgan/ko-sroberta-multitask`.

> **결론(2026-06-04): 모델은 런타임 천장(99.3%)이라 재학습은 거의 무차별.** batch 스윕(b4~b64)·트레이너 변수 조정 모두 런타임 검색을 의미 있게 못 올림 — 해마는 IBL *어휘*가 아니라 query↔저장 intent *의미*를 매칭해 vocab 변경에 본질적으로 강건하기 때문. 검색 품질을 더 올리려면 임베딩이 아니라 **하이브리드 alpha/FTS5**가 레버. (관찰된 오랭킹 사례는 FTS5 키워드 artifact였지 임베딩 실패가 아님.)

### 검색 방식

`search_hybrid` — 시맨틱(의미 기반) 우선. BM25(키워드)는 모델이 미준비된 짧은 시간(시작 직후 ~10초)에만 폴백으로 사용.

```
사용자 메시지
    ↓
시맨틱 검색 (ALPHA=1.0)
  - 모델: fine-tuned 해마 (768d)
  - 코사인 유사도 → similarity = 1 - distance²/2 (0~1 범위)
    ↓
시맨틱 실패 시 → BM25 폴백 (max-normalize로 0~1 보장, 2026-05-17 정정)
    ↓
상위 k개 결과 반환 (모든 경로에서 점수 0~1)
```

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `MAX_REFERENCES` | 5 | 최대 참조 수 |
| `DEFAULT_K` | 5 | 기본 반환 참조 수 |
| `MIN_SCORE` | 0.25 | 최소 점수 임계값 |
| `DEFAULT_ALPHA` | 1.0 | 시맨틱 100% (BM25는 폴백 전용) |
| `REFLEX_SCORE_THRESHOLD` | 0.85 | 이 이상이면 의식·무의식 모두 스킵하고 EXECUTE |

### 점수 정규화 (2026-05-17)

이전에는 FTS5 단독 폴백 시 raw BM25 점수(0~10+)가 반환되어 REFLEX 임계값 0.85가 무력화되는 문제가 있었다. `_combine_scores` 외에 단독 분기에도 max-normalize를 적용해 모든 경로에서 점수 0~1을 보장한다.

---

## 심층메모리 (Deep Memory / 연상 풀)

에이전트별 SQLite DB로 운영되는 장기 사실 저장소. 어제(2026-05-16) 해마와 같은 fine-tuned 모델로 시맨틱 검색을 추가했다.

### 구조

| 측면 | 설명 |
|---|---|
| **DB 위치** | 시스템 AI: `data/system_ai_state/memory_system_ai.db`<br>프로젝트 에이전트: `projects/{id}/memory_{agent}.db` |
| **격리** | 에이전트별 분리 (설계 의도 — 각 에이전트가 자기 도메인 지식만 유지) |
| **현재 규모** | 21개 DB / 162건 |
| **검색** | **시맨틱 우선 + LIKE 폴백** (해마와 동일 패턴) |
| **인덱스** | vec0 가상 테이블 (`memories_vec`) — fine-tuned 모델 임베딩 768d |
| **자동 동기** | save / update / delete 시 vec 인덱스 자동 갱신 |

### 자동 증류 (`_distill_deep_memory`)

대화 완료 후 경량 AI가 응답에서 기억할 가치 있는 정보(사실·선호·결정·작업 이력)를 추출하여 저장한다. 휘발성 정보(날씨, 주가, 시세 등)는 제외.

- NEW: 기존에 없는 새 정보
- UPDATE: 기존 항목의 보충/수정
- SAME: 이미 알고 있음 → used_at만 갱신

### 검색 동작 (예시)

```
쿼리: "지난 금요일 미국 증시가 크게 요동친 이유가 뭐지?"
  ↓
LIKE 매칭: 0건 (글자 일치 없음)
시맨틱 매칭:
  ★ id=7 "5/15 연준 의장 교체"  (관련성 0.6+)
  ★ id=4 "코스닥 하락"            (관련성 0.5+)
```

LIKE만 있던 시절(2026-05-16 이전)에는 0건 반환 → "방금 저장한 것도 못 찾는" 문제가 있었다. 시맨틱 도입으로 동의어/의미 매칭이 가능해짐.

---

## 경험 증류 (Experience Distillation)

대화가 끝난 후, 해마가 모르는 패턴이었는데 실행이 성공했으면 경량 AI가 그 경험에서 용례를 추출하여 해마에 저장한다.

### 증류 조건

```
해마 점수 0.7+ → 스킵 (이미 아는 패턴)
해마 점수 0.7 미만 + IBL 도구 호출 성공 → distill_experience() → 해마에 추가
```

해마가 성숙할수록 증류 빈도는 줄어든다.

### 증류 파이프라인

```
대화 완료
    ↓
top_score 확인 (단계 0에서 이미 계산된 값 재사용)
    ↓
0.7 미만 + 도구 호출 있음? → distill_experience() (경량 AI)
    ↓
실행 로그에서 패턴 추출:
  - 중복/탐색성 호출 제거
  - 핵심 액션 패턴만 남김
  - intent를 일반화
    ↓
IBLUsageDB.add_example() → DB 저장 + 임베딩 즉시 생성 (~8ms)
    ↓
다음 대화부터 해마가 인출 가능
```

### 두 단계의 학습

| 단계 | 시점 | 효과 |
|---|---|---|
| **즉시 반영** | 매 대화 후 (조건부) | DB + 임베딩 → 바로 검색 가능 |
| **주기적 재학습** | 수동 (누적 후) | 데이터 정리 → 베이스 모델에서 처음부터 fine-tuning |

### 도구 호출 이력 수집

증류에 필요한 도구 호출 이력은 두 경로에서 수집된다:

| 경로 | 수집 방식 |
|---|---|
| WebSocket (GUI 대화) | `tool_start` 이벤트에서 `tool_calls_log`에 직접 수집 |
| 채널 (Gmail/Nostr) | `system_tools._log_ibl()` → `thread_context.append_tool_call()` |

---

## 학습 데이터 관리

```
data/training/
├── ibl_training_balanced_20260516.json   ← 현재 학습 데이터 (144 액션 어휘로 마이그·재학습됨, usage_db 2,324건)
└── _archive/                              ← 옛 학습 데이터 및 중간 산출물
    ├── ibl_synthetic_opus_final_2479.json
    ├── ibl_distilled.json
    ├── _new_*.json                        (영역별 신규 작성분)
    └── ibl_training_cleaned_*.json
```

### 정리 작업 (2026-05-16)

- 원본 2,500건 → 정리 후 2,019건 (96% 보존)
- obsolete 액션 학습 항목 제거 (안드로이드/구식 도구 등 736건)
- 신규 64개 미커버 액션에 대해 직접 작성 (384건 추가)
- 상위 5개 액션 다운샘플링 (35건 cap) — 분포 균형
- 결과: 311/311 액션 100% 커버, sense:stock_info 등 편중 완화

### 재학습 (Re-training)

```bash
cd /Users/kangkukjin/Desktop/AI/indiebizOS/backend
python ibl_embedding_trainer.py
```

**핵심 원칙:**
- **항상 베이스 모델에서 시작**: 매번 `ko-sroberta-multitask`에서 처음부터 fine-tuning (catastrophic forgetting 방지)
- **MPS 가속**: Apple Silicon GPU (`device="mps"`)
- **액션별 데이터 밸런싱**: 학습 시 액션별 상한(기본 20건)을 두고, 초과분은 무작위 샘플링
- **`data/training/*.json` 글로빙**: 폴더의 모든 JSON을 합쳐 학습. 정리 시 중간 산출물은 `_archive/`로 이동 필요

### 학습 구조

세 가지 유형의 학습 쌍:
1. **intent ↔ intent**: 같은 액션 패턴을 공유하는 자연어 명령 쌍
2. **intent → pattern**: 자연어 → 정규화된 액션 패턴
3. **intent → description**: 자연어 → 액션 설명 (cross-modal)

- Loss: MultipleNegativesRankingLoss
- 10 epoch 학습, 검증 점수 기준 Best 자동 선택

---

## 용례 사전 DB

```sql
-- 용례 사전 (현재 2,019건, source=balanced_20260516)
ibl_examples (
  id, intent TEXT,        -- 사용자 의도 (자연어)
  ibl_code TEXT,          -- IBL 코드 (정답)
  nodes TEXT,             -- 관련 노드 (sense, self 등)
  category TEXT,          -- single / pipeline / parallel / fallback / complex
  difficulty INT,         -- 난이도 (1-3)
  source TEXT,            -- balanced_20260516 (재구축 결과)
  tags TEXT,
  success_count INT, fail_count INT,
  created_at TEXT, updated_at TEXT
)

-- 벡터 인덱스 (sqlite-vec, 768차원)
ibl_examples_vec (embedding float[768])

-- FTS5 키워드 인덱스 (시맨틱 폴백용)
ibl_examples_fts (intent, ibl_code)
```

심층메모리 DB(에이전트별):
```sql
memories (
  id, category TEXT, keywords TEXT, content TEXT,
  created_at DATETIME, used_at DATETIME
)
memories_vec (embedding float[768])   -- 2026-05-16 추가
```

---

## 뇌 구조와의 대응

| 뇌 구조 | IndieBiz OS 컴포넌트 | 역할 |
|---|---|---|
| 기저핵 | 무의식 (경량 AI) + Reflex 분기 | EXECUTE/THINK 게이팅 |
| **해마** | **IBL Usage DB + fine-tuned 임베딩** | **과거 IBL 코드 사례 인출** |
| **연합피질** | **심층메모리 (memory_db)** | **사용자·세계에 대한 장기 사실 인출** |
| 전전두엽 | 의식 에이전트 (본격 AI) | 자기 참조적 문제 구성 + 달성 기준 |
| 운동피질 | 실행 에이전트 (중급/본격 AI) | IBL 코드 생성 및 실행 |
| 전대상피질 | 평가 에이전트 (경량 AI) | 달성 기준 대비 검증 |
| 소뇌 | distill_experience + _distill_deep_memory | 경험 증류 — 성공 패턴을 해마/심층메모리에 저장 |

---

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `backend/ibl_usage_rag.py` | `build_execution_memory()` — (xml, top_score, top_code) 반환, `distill_experience()` |
| `backend/ibl_usage_db.py` | 해마 검색 엔진 (시맨틱 + FTS5 폴백, 점수 0~1 정규화) |
| `backend/ibl_embedding_trainer.py` | 해마 학습 스크립트 (베이스 모델에서 fine-tuning) |
| `backend/agent_cognitive.py` | `_build_execution_memory()` — 해마+심층메모리 합성, `_search_related_memory()` |
| `data/packages/installed/tools/memory/memory_db.py` | 심층메모리 (시맨틱 우선 + LIKE 폴백, 2026-05-16 시맨틱 추가) |
| `backend/api_websocket.py` | GUI/WS 경로 — 연상 단계 → Reflex 분기 → 실행 |
| `backend/agent_communication.py` | 채널 경로 — 동일 패턴 (2026-05-17 중급 모델 전환 추가로 일관성 확보) |
| `backend/system_ai_core.py` | 시스템 AI 경로 — 동일 패턴 |
| `backend/prompt_builder.py` | 시스템 프롬프트에 연상기억 삽입 (외부 래퍼 없이 직접) |
| `backend/system_tools.py` | `_log_ibl()` — 도구 호출 이력 |
| `backend/thread_context.py` | 스레드별 도구 호출 이력 |
| `data/models/ibl_embedding/` | fine-tuned 모델 (해마+심층메모리 공유, 422MB) |
| `data/training/ibl_training_balanced_20260516.json` | 현재 학습 데이터 |

---

*마지막 업데이트: 2026-06-04 — 해마 Modal GPU 재학습(144 액션 어휘, batch=16, code Top-5 94.5%/런타임 ~99%). 모델은 런타임 천장이라 재학습 거의 무차별로 판명. 이전: 2026-05-31 199액션 재학습, 2026-05-17 단일 검색 일원화·심층메모리 시맨틱 검색·점수 정규화*
