# IBL 용례 RAG 시스템

> 에이전트의 IBL 생성 품질을 높이기 위한 참조 용례 검색 시스템

## 개요

에이전트가 사용자 요청을 처리할 때, 321개 액션의 노드/액션 목록만으로는 정확한 IBL 코드를 생성하기 어려운 경우가 있다. 특히 파라미터 형식, 파이프라인 조합, 실제 사용 패턴 등은 목록만으로는 알 수 없다.

IBL 용례 RAG 시스템은 **과거의 성공적인 IBL 사용 사례**를 검색하여 AI 프롬프트에 참고 자료로 주입한다. AI는 이 참고 사례를 기계적으로 복사하지 않고, 현재 요청에 맞게 변형하여 새로운 IBL 코드를 생성한다.

## 시스템 구조

```
ibl_nodes.yaml ──→ [Generator] ──→ ibl_usage.db (용례 사전: ~970개)
                                        ^
실행 로그 (자동 승격) ─────────────────┘
                                        |
사용자 메시지 ──→ [RAG 검색] ──→ 유사 용례 3개 ──→ AI 프롬프트에 XML 주입
```

### 핵심 파일

| 파일 | 역할 |
|------|------|
| `backend/ibl_usage_db.py` | 용례 사전 DB + 하이브리드 검색 엔진 |
| `backend/ibl_usage_rag.py` | RAG 참조 모듈 (검색 → XML 포맷 → 프롬프트 주입) |
| `backend/ibl_usage_generator.py` | 합성 데이터 생성기 (초기 용례 구축) |
| `data/ibl_usage.db` | SQLite DB (용례 사전 + 실행 로그 + 벡터 인덱스) |

---

## 용례 사전 DB

### 테이블 구조

```sql
-- 용례 사전 (약 970개)
ibl_examples (
  id, intent TEXT,        -- 사용자 의도 (자연어)
  ibl_code TEXT,          -- IBL 코드 (정답)
  nodes TEXT,             -- 관련 노드 (source, system 등)
  category TEXT,          -- single / pipeline / complex
  difficulty INT,         -- 난이도 (1-5)
  source TEXT,            -- synthetic / synthetic_v3 / auto_log / manual
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

### 용례 출처 (source)

| source | 설명 | 생성 방식 |
|--------|------|----------|
| `synthetic` | Stage 1+2 합성 데이터 | 규칙 기반: ibl_nodes.yaml의 액션 description + target_key에서 자동 생성 |
| `synthetic_v3` | Stage 3 합성 데이터 | AI 생성: 복합 시나리오, 파이프라인 패턴 |
| `auto_log` | 실행 로그 자동 승격 | 성공한 실행 로그를 자동으로 용례로 변환 |
| `manual` | 수동 등록 | 직접 추가한 용례 |

---

## 하이브리드 검색

검색은 **시맨틱(의미 기반) + BM25(키워드 기반)**을 결합한 하이브리드 방식이다.

### 검색 구성

```
사용자 메시지: "대구 아파트 실거래가 알려줘"
                    |
    ┌───────────────┴───────────────┐
    v                               v
 시맨틱 검색 (70%)              BM25 검색 (30%)
 - 모델: jhgan/ko-sroberta     - FTS5 풀텍스트
 - 768차원 벡터                 - 한국어 조사 제거
 - 코사인 유사도                - OR 매칭
    |                               |
    └───────────────┬───────────────┘
                    v
          가중 합산 (alpha=0.7)
                    v
          상위 k개 결과 반환
```

- **시맨틱 검색**: 의미적 유사성으로 검색. "아파트 가격" ↔ "주택 매매가" 같은 동의어/유사 표현도 매칭
- **BM25 검색**: 키워드 일치로 검색. "삼성전자" 같은 정확한 용어 매칭에 강함
- **가중치**: 시맨틱 70% + BM25 30% (alpha=0.7)

### 임베딩 모델

- **모델**: `jhgan/ko-sroberta-multitask` (한국어 특화 sentence-transformer)
- **차원**: 768
- **벡터 DB**: sqlite-vec (SQLite 확장)
- **로딩**: 서버 시작 시 백그라운드 스레드에서 비동기 로딩 (서버 블로킹 없음)

---

## RAG 주입 흐름

### 1. 타이밍

RAG 참조는 **사용자 메시지 수신 시 1회만** 주입된다. 에이전트가 도구를 여러 번 호출하는 멀티 라운드 과정에서는 추가 주입하지 않는다.

이유:
- 첫 메시지가 사용자 의도를 가장 잘 표현
- 중간 라운드의 내부 메시지(도구 결과 등)는 검색 쿼리로 부적합
- 레이턴시 최소화 (검색은 1회만)
- AI 혼란 방지 (매 라운드마다 다른 참조가 주입되면 일관성 저하)

### 2. 주입 위치

```
api_websocket.py (handle_chat_message / handle_chat_message_stream)
        |
        v
agent_runner.augment_with_ibl_references(message)
        |
        v
IBLUsageRAG.inject_references(message, allowed_nodes)
        |
        v
[원본 메시지 앞에 XML 참조 블록 추가]
        |
        v
AI에게 전달 (시스템 프롬프트 + 참조 + 사용자 메시지)
```

### 3. XML 출력 형식

```xml
<ibl_references note="아래는 유사한 과거 용례입니다. 참고만 하고 현재 요청에 맞게 변형하세요.">
  <ref intent="아파트 매매 실거래가" code='[source:apt_trade]("지역코드")' score="0.88"/>
  <ref intent="부산 반여동의 최신 아파트 실거래가를 알려줘."
       code='[source:district_codes]("해운대구") >> [system:todo]("지역코드 확인")'
       score="0.87"/>
  <ref intent="아파트 전월세 실거래가" code='[source:apt_rent]("지역코드")' score="0.92"/>
</ibl_references>

대전 유성구 아파트 가격 검색해줘
```

### 4. 필터링

- **최소 점수**: 0.25 미만의 결과는 제외 (무관한 참조 방지)
- **IBL 관련성**: 인사, 감탄사, 짧은 메시지는 검색 자체를 스킵
- **캐시**: 동일 쿼리는 5분간 캐시 (TTL 300초)
- **허용 노드**: 에이전트의 `allowed_nodes` 범위 내 용례만 반환 가능

---

## 실행 로그 자동 승격

에이전트가 도구를 성공적으로 실행하면, 그 기록이 자동으로 용례 사전에 추가된다. 이를 통해 시스템은 실제 사용 패턴을 학습하며, 용례 사전이 점점 풍부해진다.

### 승격 흐름

```
에이전트 대화 완료
        |
        v
api_websocket.py finally 블록
        |
        v
IBLUsageDB.try_promote_session(user_input)
        |
        ├── 성공 로그 있는가? → 없으면 종료
        ├── 같은 intent 용례가 이미 있는가? → 있으면 스킵 (중복 방지)
        ├── IBL 코드 추출 가능한가? → 불가하면 스킵
        |
        v
용례 DB에 source='auto_log'로 추가
        |
        v
다음 유사 요청 시 RAG 참조로 활용
```

### IBL 코드 추출 전략

1. **파이프라인 코드 모드**: `[ibl:?]("코드")` 형태로 실행된 경우, 내부 코드를 추출
2. **개별 호출 조합**: 성공한 개별 도구 호출들을 `>>` 파이프라인으로 연결
3. **중복 제거**: 같은 `[node:action]` 호출은 1개만 유지

### 승격 조건

- 사용자 메시지가 6자 이상
- 성공 로그가 1개 이상 존재
- 동일 intent(대소문자 무시)의 용례가 아직 없음
- 유의미한 IBL 코드 추출 가능 (node, action이 비어있지 않음)

---

## 합성 데이터 생성

초기 용례 사전은 3단계로 생성되었다.

| 단계 | 내용 | AI 필요 | 수량 |
|------|------|---------|------|
| Stage 1 | 단일 액션 (규칙 기반) | X | ~321개 |
| Stage 2 | 파이프라인 (템플릿 기반) | X | ~50개 |
| Stage 3 | 복합 시나리오 (AI 생성) | O | ~594개 |
| **합계** | | | **~965개** |

**Stage 1**: `ibl_nodes.yaml`의 각 액션 description + target_key로 기본 용례 자동 생성
**Stage 2**: 미리 정의된 파이프라인 템플릿(검색->저장, 병렬검색, 폴백 등)에 실제 액션 대입
**Stage 3**: AI에게 노드/액션 목록을 주고 현실적인 복합 시나리오 생성 요청

CLI: `python ibl_usage_generator.py [--stages 1,2,3] [--ai]`

---

## 효과

RAG 참조 주입 전후 비교 (부동산 에이전트, 동일 요청):

| 항목 | RAG 없음 | RAG 있음 |
|------|---------|---------|
| 에이전트 라운드 수 | 13 라운드 | 3 라운드 |
| 불필요한 시행착오 | 잘못된 파라미터로 재시도 다수 | 첫 시도에 올바른 파라미터 |
| 최종 결과 | 동일 | 동일 |

에이전트가 참고 사례를 보고 올바른 파라미터 형식과 파이프라인 순서를 파악하여, 시행착오 없이 빠르게 작업을 완료한다.

---

## 설정 및 파라미터

### IBLUsageRAG 설정

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `MAX_REFERENCES` | 5 | 최대 참조 수 |
| `DEFAULT_K` | 3 | 기본 반환 참조 수 |
| `MIN_SCORE` | 0.25 | 최소 점수 임계값 |
| `CACHE_TTL` | 300 | 캐시 유지 시간 (초) |

### IBLUsageDB 검색 설정

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `ALPHA` | 0.7 | 시맨틱 가중치 (1-ALPHA = BM25 가중치) |
| `EMBEDDING_MODEL` | jhgan/ko-sroberta-multitask | 한국어 임베딩 모델 |
| `EMBEDDING_DIM` | 768 | 벡터 차원 |
| `BATCH_SIZE` | 64 | 배치 임베딩 크기 |

---

*마지막 업데이트: 2026-02-23*
