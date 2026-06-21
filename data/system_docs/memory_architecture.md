---
title: 메모리 아키텍처 — 6종 기억 통합 지도
scope: indiebizOS의 모든 기억 하위 시스템(의미·작업·일화·절차·관계·자기상태)의 저장/사용/학습 흐름
owner_code: >
  ibl_usage_db.py, ibl_usage_rag.py, memory_db.py, agent_cognitive.py,
  episode_logger.py, world_pulse.py, world_pulse_health.py,
  system_ai_memory.py, conversation_db.py, system_docs.py, prompt_builder.py,
  workflow_engine.py, ibl_engine.py
last_updated: 2026-06-14
see_also: [execution_memory.md, architecture.md, ibl.md]
---

# 메모리 아키텍처 — 6종 기억 통합 지도

> indiebizOS의 메모리는 단일 시스템이 아니라 **여섯 개의 독립 하위 시스템**으로 구성된다.
> 각각은 인간 기억 분류와 거의 정확히 대응한다. 이 문서는 그 전체 지도다.
> (해마 단일 시스템의 상세는 `execution_memory.md` 참조 — 본 문서는 그것을 6종 중 하나로 위치시킨다.)

## 철학

하네스의 핵심 역량은 **사용하면서 사용자·세계·자신에 대한 지식을 흡수하고, 과거의 판단·지식·액션을 기억하여 반복을 빠르고 합리적으로 처리**하는 것이다. 메모리는 곧 속도·비용 최적화 장치다. 실제로 해마 점수(과거에 해본 일인가)가 인지 라우팅(반사 vs 의식)을 가른다.

기억은 두 형태로 존재한다:
- **파일/DB로 저장되는 기억** — 사실, 대화, 경험, 상태
- **IBL 액션으로 어휘화된 기억** — 자주 쓰는 복잡한 워크플로우를 하나의 이름으로 추상화한 것 (절차 기억)

---

## 한눈에 — 6종 메모리

| # | 인간 기억 | indiebizOS 구현 | 저장소 | 무엇을 기억하나 |
|---|---|---|---|---|
| 1 | **의미 기억** (정적 지식) | 시스템 문서 + 시스템 메모 | `data/system_docs/*.md`, `data/system_ai_memo.txt` | 시스템 자신에 대한 변하지 않는 지식 |
| 2 | **작업 기억** (단기) | 대화 이력 | `system_ai_memory.db:conversations`, `projects/{id}/conversations.db` | 진행 중인 대화 (Masking으로 축약) |
| 3 | **일화 기억** (경험) | 에피소드 로그/요약 | `world_pulse.db:episode_log / episode_summary` | "무슨 일이 있었나" + 인지 품질 지표 |
| 4 | **절차 기억** (방법) | IBL 액션 + 워크플로우 + **해마** | `ibl_nodes.yaml`, `data/workflows/*.yaml`, `ibl_usage.db` | "어떻게 하는가" — 자연어→IBL 코드 |
| 5 | **관계 기억** (사용자 사실) | **심층메모리** | 에이전트별 `memory.db` (memory 패키지) | 사용자 선호·결정·중요날짜·작업기록 |
| 6 | **자기 상태** (항상성) | World Pulse + Self-Check | `world_pulse.db:pulse_log / self_checks / action_health` | 세계·사용자·자신의 실시간 상태와 건강 |
| 7 | **공간 기억** (포식) | **포식 기억(냄새지도)** | `forage_memory.db:forage_map / owner_model` | "어디에 무엇이 사는가" — 디스크·웹 포식 경험 누적 |

> **핵심 연결**: 매 요청마다 단계 0에서 생성되는 **연상기억(associative memory)** 은
> #4 해마(`<execution_memory>`)와 #5 심층메모리(`<related_memory>`)를 **하나로 합성**한다.
> 둘 다 같은 fine-tuned 임베딩 모델로 검색되며, 모델은 backend에서 1회만 로드되어 공유된다.

---

## 1. 의미 기억 — 시스템 문서 / 메모 (정적 지식)

- **저장**: 마크다운·텍스트 파일. 사람 또는 시스템 AI가 명시적으로 갱신.
- **사용** (`prompt_builder.py`):
  - `system_structure.md` + `system_ai_memo.txt` → **항상** 프롬프트 안정(stable) 부분 → Anthropic 캐시 prefix에 고정
  - 나머지 문서는 **조건부**: 의식 에이전트가 `guide_files`로 지목한 것만 로드
  - 안정/가변 분리 설계 — 변하지 않는 지식은 prefix에 고정해 캐시 적중률 극대화
- **성격**: 캐시 효율을 위해 의도적으로 정적. 자주 변하면 안 됨.

## 2. 작업 기억 — 대화 이력 (단기, 압축)

- **저장**: 시스템 AI는 `system_ai_memory.db:conversations`, 프로젝트 에이전트는 각자 `conversations.db`로 **격리**.
- **사용**: `get_history_for_ai(limit=7)` — **Observation Masking** 적용
  - 최근 2턴: 원본 유지 (이미지도 최근 턴만 로드)
  - 그 이전 + 500자 초과: `[이전 대화: {첫줄}… ({길이}자)]`로 축약
- **한계**: 자동 *의미* 요약기는 없음. 길이 기준 절단만. → 다듬을 자리 ③.

## 3. 일화 기억 — 에피소드 로그/요약 (경험·반성의 재료)

- **저장** (`episode_logger.py`): 사용자 명령 1건 = 1 에피소드. stdout 전체를 가로채 종료 시 저장.
  - `episode_log`: user_message + 실행 로그 전문 + 소요시간 (최근 **1000건** 롤링)
  - `episode_summary`: 로그에서 정규식으로 추출한 **인지 품질 지표** — 해마 점수, EXECUTE/THINK 분류, 의식 지연, 실행 라운드 수, 최종 달성 여부(ACHIEVED/NOT_ACHIEVED) (**영구 보존**)
- **사용**: `get_cognitive_trends()` → 진단 리포트(`diagnostic_report.md`)의 추이 분석.
- **한계**: 현재 *집계 통계*로만 소비. 개별 일화를 회상해 행동을 교정하는 루프는 미완. → 다듬을 자리 ②.
  - (단, 프로젝트 에이전트에는 `attempt_log` 테이블에 라운드별 시도·교훈을 적는 더 미세한 메커니즘이 별도로 존재.)

## 4. 절차 기억 — IBL 액션 + 워크플로우 + 해마 (핵심 학습 루프)

세 겹으로 구성된다.

**(a) 액션 정의** — 가장 안정된 절차 지식
`ibl_nodes_src/*.yaml`(단일 진실) → `build_ibl_nodes.py`(삼각 검증) → `ibl_nodes.yaml`(런타임 캐시). 111개 액션이 곧 어휘화된 방법 지식.

**(b) 해마(실행기억)** — 가장 살아있는 자기 학습 루프 ⭐
- `ibl_usage.db:ibl_examples`에 `(자연어 의도 → IBL 코드)` 쌍 + 768차원 임베딩 저장
- **검색**: 매 요청 1회, 시맨틱(fine-tuned 모델) + FTS5 하이브리드, Top-5 → XML 주입
- **증류**: 해마 점수 < 0.7(유사 선례 없음) + 실행 성공 시 → 반성 에이전트가 일반화 → DB + `ibl_distilled.json` 누적 → 다음 검색부터 반영
- 임계값: 표시 MIN_SCORE 0.65 / 증류 DISTILL_THRESHOLD 0.7
- 상세: `execution_memory.md`

**(c) 워크플로우** — 명시적으로 저장된 조합
`data/workflows/*.yaml`에 파이프라인(`>>` 순차 / `&` 병렬 / `??` 폴백)을 이름 붙여 저장. `save_workflow()` 동적 생성, `execute_workflow(id)` 재실행.
- **한계**: 저장된 워크플로우가 1급 IBL 액션으로 *등록*되지는 않음 — `[self:workflow]{op:"run", workflow_id:"…"}`로만 호출되어 다른 IBL 코드와 합성 불가. → 다듬을 자리 ①.

## 5. 관계 기억 — 심층메모리 (사용자 지식 자동 흡수)

> **"사용하면서 사용자 지식을 흡수"의 실현체.** 매 대화 후 자동으로 사용자 사실을 추출·저장한다.

- **저장소**: 에이전트별 `memory.db` (memory 패키지, `memory_db.py`)
  - 테이블 `memories(category, keywords, content, created_at)` + 임베딩 인덱스
  - category: `사용자선호 | 작업기록 | 의사결정 | 중요날짜`
- **자동 저장** (`agent_cognitive._distill_deep_memory`): 대화 종료 후
  1. 경량 AI가 대화에서 기억할 사실 조각 추출 (이름·날짜·선호·결정·결과). **일시적 데이터(주가/날씨/환율/시세)·추론·감상은 제외**
  2. 기존 메모리에서 유사 항목 검색 → 중복이면 업데이트, 신규면 추가 (최대 5개/대화)
- **사용** (`agent_cognitive._search_related_memory`): 매 요청 시 Top-3 의미 검색 → `<related_memory>` XML로 실행기억과 함께 주입
- **#1 의미기억과의 차이**: #1은 시스템 자신에 대한 정적 파일 지식, #5는 **사용자에 대한 동적·의미검색 지식**. 자동 증류되는 살아있는 기억이다.

## 6. 자기 상태 — World Pulse / Self-Check (항상성·면역)

- **저장**:
  - `pulse_log` (매시간, 30일): world(경제/날씨/뉴스) + user(대화수/일정) + self(서비스 alive/디스크/proprioception: 메모리·CPU·스레드·태스크)
  - `self_checks` (매 6~12시간, 30일): 부작용 없는 액션 전수 점검 + 정적 정합성 검증(`run_static_ibl_check`)
  - `action_health` (실행마다): 실사용 기반 액션 건강
- **사용**: 프롬프트에 압축 주입 + 면역 순찰(만성 실패 감지) + `diagnostic_report.md`.

---

## 7. 공간 기억 — 포식 기억 / 냄새지도 (디스크·웹 탐색 경험)

> **"쓰면서 *공간*에 대한 지식을 흡수"의 실현체.** 해마(#4)가 "어떻게 하는가"를 증류한다면, 포식 기억은 "어디에 무엇이 사는가"를 증류한다.

- **문제**: AI는 stateless라 디스크를 한 시간 뒤져 알아낸 것(폴더 정체·죽은 가지·주인 관습)을 세션이 끝나면 잊고 매번 콜드 스타트한다. 그 "어떻게 뒤지나"는 *나만의 것*이라 가중치에도 없다.
- **저장소** (`backend/forage_memory.py`, `data/forage_memory.db`): **2층** — `forage_map`(이 디스크 전속: 폴더 정체·관습·죽은가지·기질) + `owner_model`(몸독립 주인모델: 정체·분야·신호·습관 — 디스크·웹·코드 공유).
- **닫힌 루프**: ③ 포식 의도 시 `<forage_memory>` 주입(`_search_forage_memory`, 해마 `<execution_memory>` 옆) → ② AI가 포식(`fs_query`/`grep`/`read`) → ④ 종료 훅에서 *일반화 가능한 지도 델타만* 증류(`_distill_forage_memory`, 날 내용·특정 파일 제외) → ⑤ 기존 라벨 위반 이질 내용은 surface 표식(필터버블 반대힘).
- **안전판 4**(누적의 그림자 방지): 폐기가능(prune_reason)·prior_class 게이팅(구조적만 committal prune)·surface 카운터패스·provenance+confidence.
- **부패 무효화**: lazy — 회상 시 폴더 mtime 비교해 `stale`/`missing` 노출(삭제 안 함, 판단은 AI. 손튜닝 감쇠 곡선 안 씀).
- **수동 액세서**(augmentation): `[self:forage]{op:recall|note|forget}` — 사람이 직접 조회·정정·재오픈.
- **맥 자아 전용**(주관적 기억은 자아별 사적). **#4 해마와의 차이**: 해마=절차(NL→IBL 코드), 포식=공간(공간→지도 지식). 둘 다 증류+정리 대칭.
- **상세**: `docs/FORAGER_MEMORY_GUIDE.md`(설명서), `docs/FORAGER_MEMORY_SCHEMA.md`(스키마), `docs/FILE_FORAGING_RESEARCH.md`(연구).
- **정리 패스**(`forage_consolidation.py`): 의미적 근접중복을 경량 AI로 병합(같은 공간지식만, surface 보호) + LRU 가지치기. `run_maintenance_bundle` item 4로 합류(24h 카덴스). 증류+정리 대칭 = 심층메모리·해마와 동일.
- **진행**: 증류+주입+surface+정리 패스 완료(2026-06-20). 루프 닫힘. 남은=surface 매칭 정교화·해마 용례 시드.

---

## 요청 1건에서 6종 메모리가 협력하는 흐름

```
사용자 입력
  │
  ├─[2 작업기억]  최근 7턴 회상 (Observation Masking)
  ├─[4b 해마]     유사 IBL 선례 검색 → 점수 산출 ┐
  ├─[5 심층메모리] 관련 사용자 사실 Top-3 검색   ┘→ 연상기억(<execution_memory>+<related_memory>) 합성
  │     │
  │     ├ 해마 점수 높음 → Reflex(EXECUTE): 의식 건너뜀, 중급 모델로 즉시 실행
  │     └ 해마 점수 낮음 → THINK: 의식 에이전트 호출
  │                          ├─[1 의미기억]  guide_files 지목 문서 로드
  │                          └─[6 자기상태]  world_pulse 압축 주입
  │
  ▼ 실행 (IBL 엔진 → 도구 / 워크플로우)
  │
  ├─[3 일화기억]   에피소드 로그 + 인지 품질 요약 저장
  ├─[5 심층메모리] 대화에서 사용자 사실 자동 증류 → 저장/업데이트  ← 사용자 지식 흡수 루프
  └─[4b 해마]      점수<0.7 & 성공 → 경험 증류 → 절차기억 누적     ← 절차 학습 루프
```

**핵심**: 메모리가 곧 라우팅이다. 해마 점수(절차 기억의 친숙도)가 "반사로 처리할지, 의식을 동원할지"를 결정한다. 두 개의 자기 학습 루프(해마 증류 / 심층메모리 증류)가 사용할수록 시스템을 빠르고 개인화되게 만든다.

---

## 진단 — 다듬을 자리 (2026-05-31 기준, 미구현)

설계 이상에 비추어 코드에 비어 있는 곳. 우선 *진단*으로만 기록하며 구현은 보류한다.

### ① 워크플로우 → 1급 IBL 액션 승격
- **현재**: 워크플로우는 저장·재실행되나 새 액션으로 등록되지 않음. `[self:workflow]{op:"run",…}`로만 호출되어 다른 IBL과 합성 불가.
- **이상**: `save_workflow("일일브리핑")` → `ibl_nodes.yaml`에 `[self:일일브리핑]` 자동 등록 → `[self:일일브리핑] >> [self:blog]{op:save}`처럼 합성. (`architecture_three_tier_cognition` 메모의 "하향 진화: 액션→단축키 미구현 빈자리"와 동일.)

### ② 일화 기억 → 개별 반성 루프 닫기
- **현재**: episode_summary는 집계 추이로만 소비.
- **이상**: 해마처럼 **유사 과거 에피소드를 회상**해 "지난번 이 작업은 NOT_ACHIEVED, 교훈 X"를 의식 에이전트에 주입. 해마=성공 코드 회상, 일화=실패 경험·교훈 회상의 짝.

### ③ 작업 기억의 의미 보존 압축
- **현재**: 길이 기준 절단(Masking)만.
- **이상**: 긴 대화가 밀려날 때 경량 AI로 1줄 의미 요약 후 보존 (openhuman의 계층적 요약 트리 청사진).

---

## 심층메모리(#5) 정밀 진단 & 정리 패스 (2026-05-31)

`memory_db.py` + `agent_cognitive._distill_deep_memory/_search_related_memory` 코드 추적 결과,
저장·검색 배관은 견고하나 **기억의 생명주기(노화·망각·정정·정리) 계층이 부재**했다.
결정적 단서: `used_at`이 기록되지만 어떤 정렬·필터·감쇠에도 읽히지 않았다.
→ consolidate-memory 스킬을 이식해 **정리 패스(consolidation)** 를 구현, Tier-1 부채를 해소했다.

### ✅ 구현됨 (2026-05-31) — 정리 패스

심층메모리는 에이전트별로 격리된 `memory_*.db`라, 정리도 **격리 유지한 채 DB별 팬아웃**한다.
정리 패스 = 쓰기 시점 중복제거의 **배치/오프라인 짝**. 쓰기는 방금 한 조각만 보지만, 정리는 축적 전체를 본다.

| 부채 | 해결 | 구현 |
|---|---|---|
| **① 망각 없음** | ✅ `used_at` LRU 가지치기 | `memory_db.prune_lru()` — cap 300 초과 시 비보호 카테고리부터 삭제. 보호: 사용자선호·사용자정보·의사결정·중요날짜 (작업기록·기타만 가지치기) |
| **② append-only 정정 불가** | ✅ REPLACE 판정 + 병합 덮어쓰기 | 쓰기: `_distill_deep_memory` dedup 어휘에 REPLACE 추가(SAME/UPDATE/REPLACE/NEW), `_merge_keywords` 합집합 dedup. 정리: 클러스터 정규 병합본으로 덮어쓰기 |
| **③ 카테고리 드리프트** | ✅ enum 정규화 | `normalize_category()` — 무효 값 → `기타`. save/update/apply_merge 진입 시 적용. 빈칸은 보존(LLM 병합이 분류) |
| **④ 얕은 중복 판정** | ✅ 임베딩 클러스터 병합 | `find_duplicate_clusters()` — `memories_vec` 쌍별 코사인(≥0.85) union-find. **LLM이 클러스터 내 '진짜 동일'만 병합**(예: 사용자 주소 vs 자녀 주소 구분) |

**아키텍처** — self-check(면역 순찰)가 정적 IBL 검증을 합류시킨 패턴과 동일:
- 기계 단계(가지치기·클러스터·정규화)는 `memory_db.py` (무LLM, 싸다)
- 의미 병합만 경량 AI에 위임 (`memory_consolidation._merge_cluster_llm`, 클러스터당 1회)
- `world_pulse_health.run_self_check` 끝에 `run_memory_consolidation()` 합류. **내부 24h/DB 카덴스 게이트**로 6h마다 호출돼도 각 DB는 하루 한 번만 실제 정리. dirty하지 않으면 즉시 스킵
- 비용 가드: `MIN_ROWS_FOR_CLUSTER=8`(미만이면 클러스터 스킵), `MAX_CLUSTERS_PER_DB=12`
- 진입점: 정기(self-check 자동) — 추후 수동 IBL op `[self:memory]{op:consolidate}` 추가 여지
- 파일: `backend/memory_consolidation.py`, `data/packages/installed/tools/memory/memory_db.py`

**검증(2026-05-31)**: 시스템 AI DB(16건)에 force 실행 → 사용자 주소 중복(id 2·3) 병합, 자녀 주소(id 1)는 분리 유지, 15건으로 정리. vec 동기화·카덴스 게이트 확인.

### ✅ 추가 구현 — ⑤ 회상 시 freshness 노출 (2026-05-31)

회상이 recency를 무시하던 문제(⑤)는 **랭킹 재가중이 아니라 타임스탬프를 함께 회상시키는** 방식으로 해결했다 (AI 친화적: 손튜닝 감쇠 곡선 대신 에이전트가 스스로 판단). `_search_related_memory`(agent_cognitive.py)의 `<related_memory>` 각 항목에 `last_seen="YYYY-MM-DD"`(마지막 확인=사용/생성일)를 부착하고, 헤더 note에 "오래된 기억은 현재와 다를 수 있음을 감안" 안내를 추가. 타임스탬프는 `read()`가 `used_at`을 갱신하기 **전** 값(search 결과)에서 취해 정확하다. (인프라가 맞아떨어짐 — search()가 이미 used_at/created_at 반환.)

### ✅ 추가 구현 — ⑦ 쓰기 경로 비용 배치화 (2026-05-31)

매 턴 경량 AI 최대 6회(추출 1 + 조각별 dedup 5)를 **최대 2회**로 줄였다. `_distill_deep_memory`의 dedup 판정은 조각마다 독립적이라, (1) 유사 후보가 없는 조각은 LLM 판정 없이 곧장 NEW 저장, (2) 후보가 있는 조각들은 **단 한 번의 배치 호출**로 verdict 배열을 한꺼번에 받는다. 검증: 사소한 턴 1회(추출이 [] 반환)·신규 사실 1회(후보 없음)·중복 사실 2회(추출+배치). verdict 누락/파싱 실패는 NEW로 안전 처리.

심층메모리(#5) 생명주기 부채는 ①~⑦ 전부 해소됨.

---

## 실행기억(#4 해마) 정밀 진단 & 피드백 루프 (2026-05-31)

`ibl_usage_rag.py`(증류·연상) + `ibl_usage_db.py`(저장·검색) 추적 결과, **증류(입력)는 작동하나 증류물의 품질을 측정·교정하는 닫힌 루프가 부재**했다. 결정적 단서: `update_success`/`log_execution`의 호출처가 0개 — 성공/실패 추적·실행 로그 인프라가 만들어졌으나 배선되지 않았다(심층메모리 `used_at` 데자뷰).

### ✅ 구현됨 (2026-05-31)

| 부채 | 해결 | 구현 |
|---|---|---|
| **① 피드백 루프 죽음** | ✅ Reflex top-1 성공/실패 기록 → success_rate 표시 | `record_recall_outcome()` — 고점수(≥0.85, 귀속 깔끔한 Reflex 경로)에서 top-1 example의 execute_ibl 성공/실패를 `update_success_by_code()`로 기록. 3개 증류 지점(websocket×2 + agent_communication)에 배선. `_format_references`가 success_rate를 표시(0.0=실패 포함, -1=미검증은 숨김) → 연상이 검증된 사례를 선호. 리랭킹이 아니라 **표시로 AI가 판단**(last_seen과 동일 철학) |
| **② 증류 검증 게이트** | ✅ 환각 액션 차단 | `_validate_ibl_actions()` — distilled code의 모든 `[node:action]`이 `ibl_nodes.yaml`에 실재하는지 정적 검증, 미존재 시 증류 폐기. add_example 전에 호출 |

**검증(2026-05-31)**: 고점수+성공→success_count, 고점수+실패→fail_count, 저점수(THINK)·비IBL→무시, 표시 가드(tried 0.5/0.0 표시·untried 숨김), 환각 액션(sense:teleport 등) 폐기 모두 확인.

### ✅ 추가 구현 — 해마 정리 패스 (③④⑤, 2026-05-31)

심층메모리 정리 패스의 대칭. 증류물(`source='distilled'`)에만 적용하고 **학습 코퍼스(synthetic/balanced/manual_seed)는 보호**한다. 증류물은 사실이 아니라 참고 코드라 LLM 병합 판단이 불필요 — **순수 기계적**이다.

| 부채 | 해결 | 구현 |
|---|---|---|
| **⑤ 증류물 가지치기 없음** | ✅ 검증실패 가지치기 | `consolidate_distilled` — `fail_count≥2 & success_count==0`인 입증된 나쁜 사례 삭제 (①의 피드백 루프가 살아나 가능해짐) |
| **③ 증류 쓰기 중복 누적** | ✅ 근접중복 제거 | 증류물끼리 임베딩 코사인≥0.92 클러스터 → 최선(성공률→시도수→최신) 1개만 유지. 0.92 미만 유사 항목은 보존 |
| **④ json 무한 append** | ✅ dedup + 상한 | `_consolidate_distilled_json` — 완전중복(intent+code) 제거 + 최신 800건만 유지 |
| 상한 | ✅ | distilled가 200 초과 시 미검증(trial 0)부터 오래된 순 삭제 |

**아키텍처**: `run_hippocampus_consolidation`을 `world_pulse_health.run_self_check`에 합류(메모리 정리 패스 바로 다음). 내부 24h 카덴스 게이트(마커 파일 `data/training/.hippocampus_consolidated`). 삭제는 행+vec 동시(`_delete_examples`, FTS는 DELETE 트리거로 자동). 파일: `backend/ibl_usage_db.py`, `backend/ibl_usage_rag.py`.

**검증(2026-05-31)**: 드라이런(실코퍼스 2267 불변), 입증된 나쁨 가지치기(fail2/success0 삭제), 근접중복(sim 0.995 병합·우량 보존·실데이터 무손실·0.92미만 제외), json dedup, 24h 카덴스 스킵 모두 확인.

> 실행기억(#4) 생명주기 부채 ①~⑤ 전부 해소. 심층메모리 정리 패스와 **대칭 완성** — 두 자기학습 기억(해마/심층메모리)이 모두 증류(입력) + 정리(위생) 양쪽을 갖췄다.

---

## 자기상태(#6) 진단 & 유지보수 번들 (2026-05-31)

World Pulse(수집·가이드·진단리포트·action_health)는 건강하나, **Self-Check가 두 메커니즘으로 분기되며 기계적 유지보수가 고아가 됐다**는 단일 문제가 있었다.

- `run_self_check` (직접 안전 액션 전수 실행) → 이벤트 비활성화됨(`register_pulse_tasks` line 462), **dormant**
- `trigger_ai_health_check` (시스템 AI에게 assumed 액션 점검 위임) → **활성, 매 6h**
- `record_action_health`(ibl_engine.py:364)는 모든 IBL 실행에서 기록 — 실시간 신호 정상

문제: `run_self_check`에 번들돼 있던 유지보수(정적 IBL 검증·만성실패 알림·**메모리/해마 정리 패스**)가 스케줄러 마이그레이션으로 정기 실행 경로에서 빠졌다. (패턴분석·진단리포트는 `generate_guide`에서 매시간 도므로 무사.)

### ✅ 구현됨 (2026-05-31)

| 부채 | 해결 |
|---|---|
| **A. 유지보수 고아** | `run_maintenance_bundle()` 추출(실패알림+메모리정리+해마정리) → **활성 경로 `trigger_ai_health_check`에 합류** + 수동 `run_self_check`도 공유. 각 항목 자체 카덴스 게이트라 양쪽 호출돼도 중복 작업 없음 |
| **B. 확률적 cleanup** | `_cleanup_old_data` 트리거를 `random()<0.04`(평균 25h, 비결정적) → **마커 파일 기반 결정적 24h 게이트**(`_cleanup_is_due`/`.world_pulse_cleanup`). 누락·중복 없고 마지막 정리 시각 기록 |

**의의**: 앞서 만든 메모리 정리 패스·해마 정리 패스가 dormant 경로에 걸려 실제로는 정기 실행되지 않던 것을 활성화. 파일: `backend/world_pulse_health.py`, `backend/world_pulse.py`. 검증: 번들이 세 작업 호출, 활성/수동 양쪽 배선, cleanup 결정적 게이트 모두 확인.

### ⚠️ 남은 빈자리 (별도)
- **C. 뉴스 게이팅이 JSON LIKE**: `world LIKE '%news%'`로 마지막 뉴스 시각 탐색(취약하나 pulse_log 30일 바운드라 실害 적음) → 전용 메타/컬럼이 깔끔.

---

## 다중 자아와 기억의 두 부류 (2026-06-14)

폰이 두 번째 독립 자아(폰-로컬 Gemini 두뇌)가 되면서, 기억은 두 부류로 갈린다:

- **사용자 세계-데이터 (객관)** — 연락처·비즈니스·일정·의료기록. 어느 자아가 보든 같은 사실이므로 **공유·동기화**(business.db는 LWW+tombstone CRDT 합집합 머지, by-need). 자동응답 같은 PC 전용 메타데이터는 PC에 수렴.
- **자아의 주관적 기억 (마음)** — 대화 이력·해마(절차기억)·자기상태(self-state). 각 자아의 체험이므로 **자아별 사적·비동기화**. 폰 자아는 응답 속도를 위해 해마를 비활성화(키워드 검색으로 충분)했고, 맥 자아만 해마를 운용한다.

정체성은 모델 위치가 아니라 **하네스(프롬프트+기억)**에 있다. 같은 사용자 세계를 보지만 각자의 마음을 가진 두 자아 — `detect_body()`가 각 자아에게 자기 몸(맥/폰)을 인지시킨다.

---

*이 문서는 6종 메모리의 통합 지도다. 개별 시스템 변경 시 본 표와 흐름도를 함께 갱신할 것.*
