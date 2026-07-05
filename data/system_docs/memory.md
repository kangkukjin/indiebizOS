---
title: 메모리 아키텍처 — 7종 기억 통합 지도
scope: indiebizOS의 모든 기억 하위 시스템(의미·작업·일화·절차·관계·자기상태·공간(포식))의 저장/사용/학습 흐름
owner_code: >
  ibl_usage_db.py, ibl_usage_rag.py, memory_db.py, agent_cognitive.py,
  episode_logger.py, world_pulse.py, world_pulse_health.py,
  system_ai_memory.py, conversation_db.py, system_docs.py, prompt_builder.py,
  workflow_engine.py, ibl_engine.py, forage_memory.py, forage_consolidation.py
last_updated: 2026-06-22
see_also: [architecture.md, ibl.md]
---

# 메모리 아키텍처 — 7종 기억 통합 지도

> indiebizOS의 메모리는 단일 시스템이 아니라 **일곱 개의 독립 하위 시스템**으로 구성된다.
> 각각은 인간 기억 분류와 거의 정확히 대응한다. 이 문서는 그 전체 지도다.
> (해마 단일 시스템의 상세는 아래 **부록: 연상기억 심층** 참조 — 본 문서는 그것을 7종 중 하나로 위치시킨다.)

## 철학

하네스의 핵심 역량은 **사용하면서 사용자·세계·자신에 대한 지식을 흡수하고, 과거의 판단·지식·액션을 기억하여 반복을 빠르고 합리적으로 처리**하는 것이다. 메모리는 곧 속도·비용 최적화 장치다. 실제로 해마 점수(과거에 해본 일인가)가 인지 라우팅(반사 vs 의식)을 가른다.

기억은 두 형태로 존재한다:
- **파일/DB로 저장되는 기억** — 사실, 대화, 경험, 상태
- **IBL 액션으로 어휘화된 기억** — 자주 쓰는 복잡한 워크플로우를 하나의 이름으로 추상화한 것 (절차 기억)

---

## 한눈에 — 7종 메모리

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
`ibl_nodes_src/*.yaml`(단일 진실) → `build_ibl_nodes.py`(삼각 검증) → `ibl_nodes.yaml`(런타임 캐시). 142개 액션이 곧 어휘화된 방법 지식.

**(b) 해마(실행기억)** — 가장 살아있는 자기 학습 루프 ⭐
- `ibl_usage.db:ibl_examples`에 `(자연어 의도 → IBL 코드)` 쌍 + 768차원 임베딩 저장
- **검색**: 매 요청 1회, 시맨틱(fine-tuned 모델) + FTS5 하이브리드, Top-5 → XML 주입
- **증류**: 해마 점수 < 0.7(유사 선례 없음) + 실행 성공 시 → 반성 에이전트가 일반화 → DB + `ibl_distilled.json` 누적 → 다음 검색부터 반영
- 임계값: 표시 MIN_SCORE 0.65 / 증류 DISTILL_THRESHOLD 0.7
- 상세: 아래 **부록: 연상기억 심층**

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
- **다중 몸**(`forage_map.body`=포식 *공간*): 디스크(`mac`)·코드(`code:<repo>`)·웹(`web`) 등 같은 자아가 여러 공간을 포식하면 body가 갈린다(하드웨어 자아=게이트 / 포식 공간=body 키 분리). `owner_model`은 1명·전 공간 공유 → 한 공간서 강화한 주인모델이 다른 공간 포식까지 풍부화(교차-몸 전이). **맥 자아 전용**(주관적 기억은 자아별 사적). **#4 해마와의 차이**: 해마=절차(NL→IBL 코드), 포식=공간(공간→지도 지식). 둘 다 증류+정리 대칭.
- **음성-단언 측정** `[self:residual]{op:sample|estimate}`: 포식 출력의 "거기 없음 vs 덜 봤음"을 측정으로 가른다(sample=미관측 균일 무작위 표본 / estimate=Wilson 이항추정). 판단은 AI 몫, 도구는 측정·중립 해석만(열거 가능한 공간 전용 — 웹은 무한·비열거라 제외).
- **상세**: `docs/FORAGER_MEMORY_GUIDE.md`(설명서), `docs/FORAGER_MEMORY_SCHEMA.md`(스키마), `docs/FORAGER_MULTIBODY_DESIGN.md`(다중 몸), `docs/FILE_FORAGING_RESEARCH.md`(연구).
- **정리 패스**(`forage_consolidation.py`): 의미적 근접중복을 경량 AI로 병합(같은 공간지식만, surface 보호) + LRU 가지치기. `run_maintenance_bundle` item 4로 합류(24h 카덴스). 증류+정리 대칭 = 심층메모리·해마와 동일.
- **진행**: 주입→포식→증류→surface→정리 루프 완전히 닫힘 + 다중 몸(코드·웹) + 음성-단언 측정 완료(2026-06-20). 회상은 실행기억처럼 항상-on, owner 모델은 query 면제(상시 노출=냄새). 증류(쓰기)는 전 티어 post-response 유지.

---

## 요청 1건에서 7종 메모리가 협력하는 흐름

```
사용자 입력
  │
  ├─[2 작업기억]  최근 7턴 회상 (Observation Masking)
  ├─[4b 해마]     유사 IBL 선례 검색 → 점수 산출 ┐
  ├─[5 심층메모리] 관련 사용자 사실 Top-3 검색   ┘→ 연상기억(<execution_memory>+<related_memory>) 합성
  ├─[7 포식기억]   포식 의도 시 냄새지도 주입 (<forage_memory>, 해마 옆)
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
  ├─[4b 해마]      점수<0.7 & 성공 → 경험 증류 → 절차기억 누적     ← 절차 학습 루프
  └─[7 포식기억]   포식 시 지도 델타 증류 → surface 표식 → 정리     ← 공간 학습 루프
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

*마지막 업데이트: 2026-06-27 — 앱 표면 품질 일괄 개선(라디오 즐겨찾기·CCTV 인앱 재생 stream 버튼·여행 날짜+한국 지방공항·투자 TIGER200·날씨 오송·문화 지역·길찾기 거리/예상시간) + 부동산 직방 호가(sense:realty source:zigbang)·AI 공모/창업(sense:contest/startup) + read_guide claude_code 노출 + 폰 네이티브 재빌드. 142 액션(sense 44·self 44·limbs 17·others 11·engines 26)·38 도구 패키지. 이전(2026-06-22) — 포식 기억(forager)을 7번째 메모리로 정합화(제목·"한눈에" 표·흐름도 6종→7종, 다중 몸·`[self:residual]` 음성-단언 측정 반영). 절차기억(#4a) 액션수 111→141. 국회도서관 국가학술정보 인물/학위논문 액션 추가로 코퍼스 갱신.*

*이 문서는 7종 메모리의 통합 지도다. 개별 시스템 변경 시 본 표와 흐름도를 함께 갱신할 것.*


---

> **부록**: 아래는 구 `execution_memory.md` — 위 #4 절차기억(해마)·#5 관계기억(심층메모리)의 상세 구현이다.


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
    모델은 모델 기어가 결정(역할→축→기어→티어): Reflex='reflex' 축, EXECUTE·THINK='execute'/'consciousness' 축 (균형 기어 기본=중급/중급)
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
    <ref intent="아이유 밤편지 틀어" code='[limbs:music]{op: "play", query: "아이유 밤편지"}' score="0.9827"/>
  </ibl_references>
  <implementations note="코드 사례에 등장하는 도구의 구현 상세">
    <impl action="[limbs:music]{op: "play"}" implementation="yt-dlp로 유튜브 URL 추출 + mpv/ffplay로 스트리밍 재생"/>
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

### 현재 성능 (2026-06-30 **로컬 Mac M4 Pro 재학습** — code Top-5 88.9%/desc 91.2%)

2026-06-30 재학습(142 액션 어휘, 2,624 코퍼스, batch=8, 10 epochs)의 측정표:

| 지표 | Baseline (범용 ko-sroberta) | Fine-tuned 해마 | 개선 |
|---|---|---|---|
| Top-1 (code) | 18.0% | **59.3%** | +41.4%p |
| Top-3 (code) | 31.4% | **82.7%** | +51.4%p |
| Top-5 (code) | 38.0% | **88.9%** | +50.9%p |
| Top-5 (description) | 63.5% | **91.2%** | +27.7%p |

> held-out %가 직전(2026-06-12 92.6%)보다 소폭 낮은 건 코퍼스가 커지고(distilled placeholder 슬롯 등) 노이즈가 늘어 *측정 난이도*가 오른 영향 — 실연상은 멀쩡(아래 ~99% 및 시장-보고 쿼리 검증 0.635→1.0). 더 짜내려면 노이즈 distilled 가지치기.

- **재학습 경로 = 로컬**: 클라우드(Modal/Colab)는 옛 맥에어 OOM 때문이었음. 현 Mac M4 Pro 24GB는 OOM 없고 데이터셋이 작아 로컬 MPS가 더 빠름(클라우드 콜드스타트·400MB 다운로드 회피). lib 버전도 트레이너 검증값과 일치(torch/MPS·st 5.2.2·transformers 5.1.0). 파이프라인=백업→`backend/ibl_embedding_trainer.py`→rebuild_index→백엔드 touch.
- **실제 런타임 검색 정확도 ~99%**: 위 벤치마크(query→벌거벗은 코드 패턴)는 보수적 프록시다. 런타임은 query→저장용례(`intent×3 + code`)로 검색하므로(아래 "검색 방식") 액션단위 Top-5 ≈ **99%**로 천장.
- **어휘 정합**: neighbor 통합 후 `[others:neighbors]`→`[others:neighbor]{op}` relabel + phone_sync·neighbor save/favorite 용례 보강. 코퍼스(usage_db)는 항상 최신 어휘로 마이그·재색인 유지(~2,600건, rebuild_index 2605 — 통화 대수·비즈니스·국회도서관 인물/학위논문 용례 누적. 현 5노드 **142 액션** 어휘. 06-12 122-액션 어휘 재학습 이후 신규 액션은 capability 게이트로 보강, 미재학습).
- 학습 환경: **로컬 Mac M4 Pro(MPS)**, batch=8(로컬최선), max_seq 64, 10 epoch, patience 3. 베이스 `jhgan/ko-sroberta-multitask`. (클라우드 Modal 경로 cloud_training/ 은 보존하되 기본은 로컬 — OOM 없는 M4 Pro에선 로컬이 빠름.)

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
├── ibl_training_balanced_20260516.json   ← 현재 학습 데이터 (로컬 M4 Pro 재학습 2026-06-30, usage_db ~2,624건)
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

*마지막 업데이트: 2026-06-30 — **해마 재학습 + 코퍼스 정돈**: "시장 보고" 류 연상 미스(query→`[self:schedule]` 0.635, 의도-클래스 불일치) 진단 = 모델/내용이 아니라 **색인 적체**(좋은 예가 학습 json엔 있고 라이브 색인엔 0건). 정돈=올바른 패턴 앵커 5건 curated 추가(지수=stock quote·시장뉴스=search_gnews, news="market" 버그 교훈 박음) + consolidation → 코퍼스 2,624. 로컬 M4 Pro 재학습(batch=8·10ep, code Top-5 88.9%/desc 91.2%; held-out 직전 92.6%보다 소폭↓=커진 코퍼스 노이즈, 실연상 무손상) → rebuild_index. **검증: 그 쿼리 0.635→1.0**(올바른 시장-보고 패턴 연상). ★백엔드 모델 리로드(touch/재시작) 후 라이브. 이전(2026-06-27) — 앱 표면 품질 일괄 개선(라디오 즐겨찾기·CCTV 인앱 재생 stream 버튼·여행 날짜+한국 지방공항·투자 TIGER200·날씨 오송·문화 지역·길찾기 거리/예상시간) + 부동산 직방 호가(sense:realty source:zigbang)·AI 공모/창업(sense:contest/startup) + read_guide claude_code 노출 + 폰 네이티브 재빌드. 142 액션(sense 44·self 44·limbs 17·others 11·engines 26)·38 도구 패키지. 이전(2026-06-22) — 현 5노드 **142 액션**(sense 44·self 44·limbs 17·others 11·engines 26), 해마 코퍼스 ~2,600(rebuild_index 2605 — 국회도서관 국가학술정보 인물/학위논문 액션 추가 등 용례 누적). 코퍼스는 06-12 122-액션 어휘 기준 재학습 이후 미재학습 — 신규 액션은 capability 게이트로 보강(해마는 query↔intent 의미 매칭이라 vocab 변경에 강건). 절차기억(해마)은 7종 메모리의 #4b — 통합 지도는 이 문서 상단. 이전(2026-06-15) — 통화 대수(engines 변환자 9: filter/sort/take/select/dedup/groupby/join/union/merge + 파이프 문법 `|` + 문서 IR emitter) → 122~124에서 136 액션. 이전(2026-06-14) — 5노드 136 액션(해마 코퍼스는 06-12 122-액션 어휘 기준, 이후 미재학습 — 신규 액션은 capability 게이트로 보강). **폰 자아는 해마 비활성**(시스템 AI 응답 속도 위해, 사용자 결정) — 폰은 키워드 검색으로 충분, 해마는 맥-자아 전용. 해마 증류/심층기억 시맨틱 검색의 폰 이식은 불필요로 결정(2026-06-14). 이전(2026-06-12): 해마 **로컬 Mac M4 Pro 재학습**(batch=8, code Top-5 92.6%/desc 92.8%/런타임 ~99%, 코퍼스 ~2,424). 클라우드는 옛 맥에어 OOM 한정 — 이제 재학습=로컬 5~10분. neighbor 통합 relabel + phone_sync·neighbor save/favorite 용례 보강. 이전: 2026-06-05 Modal GPU 재학습(android 어휘), 2026-06-04 144 액션 재학습(런타임 천장 판명), 2026-05-17 단일 검색 일원화·심층메모리 시맨틱 검색·점수 정규화*
