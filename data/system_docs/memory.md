---
title: 메모리 아키텍처 — 7종 기억 통합 지도
scope: indiebizOS의 모든 기억 하위 시스템(의미·작업·일화·절차·관계·자기상태·공간(포식))의 저장/사용/학습 흐름
owner_code: >
  ibl_usage_db.py, ibl_usage_rag.py, memory_db.py, agent_cognitive.py,
  episode_logger.py, world_pulse.py, world_pulse_health.py,
  system_ai_memory.py, conversation_db.py, system_docs.py, prompt_builder.py,
  workflow_engine.py, ibl_engine.py, forage_memory.py, forage_consolidation.py
last_updated: 2026-09-03
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
| 7 | **공간 기억** (포식) | **포식 기억(냄새지도)** | 정본=문서 트리 `data/forage_surveys/<몸>/<경로>/memory.md` · `forage_memory.db:forage_map`=색인 · `owner_model`=DB | "어디에 무엇이 사는가" — 디스크·웹 포식 경험 누적 |

> **핵심 연결**: 매 요청마다 단계 0에서 생성되는 **연상기억(associative memory)** 은
> #4 해마(`<execution_memory>`)와 #5 심층메모리의 **지도**(`<memory_map>`, 목차만·내용 없음)를 **하나로 합성**한다.
> 해마는 fine-tuned 임베딩으로 검색되고, 심층메모리 내용은 자동 주입하지 않는다 — AI 가 지도를 보고 `[self:memory]{op:"recall", node}` 로 가지를 연다(2026-09-03).

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
- **요약 체크포인트** (2026-08-14, `history_checkpoint.py`): 창 밖으로 밀려난 턴은 경량 AI가 **재귀 요약**해 `history_checkpoints` 테이블(시스템 AI 는 `system_ai_memory.db`, 프로젝트/위임 쌍은 그 `conversations.db`)에 보존하고 히스토리 머리에 주입한다. 저장 깔때기(`save_conversation`/`save_message`)가 SQL 선판정 후 백그라운드로 갱신, 키별 동시 1개.
- **삭제 의미** (2026-09-02): 대화 삭제 = 원문 + 체크포인트 **한 트랜잭션** + 대화 이미지 파일(`system_ai_images/`) (`system_ai_memory.clear_conversations`). 요약만 남기면 지운 대화가 다음 대화 머리에 되살아난다. 체크포인트 갱신 스레드는 요약(LLM) 뒤 **IMMEDIATE 잠금 안에서 요약한 행이 아직 있는지 재확인**하고 저장한다 — 요약 도중 삭제가 끼면 버린다(`stale:deleted`).

## 3. 일화 기억 — 에피소드 로그/요약 (경험·반성의 재료)

- **저장** (`episode_logger.py`): 사용자 명령 1건 = 1 에피소드. stdout 전체를 가로채 종료 시 저장.
  - `episode_log`: user_message + 실행 로그 전문 + 소요시간 (최근 **1000건** 롤링)
  - `episode_summary`: 로그에서 추출한 **인지 품질 지표** — 해마 점수, EXECUTE/THINK 분류, 의식 지연, 실행 라운드 수, GoalEval 최종 판정(ACHIEVED/NOT_ACHIEVED/**NULL**) (**영구 보존**). `NULL`은 실패가 아니라 GoalEval 미실행일 수 있다: 의식이 달성 기준을 만든 THINK만 GoalEval을 타고, EXECUTE/Reflex는 조건부 SelfReflect가 별도 바닥이다. 여러 평가 라운드는 마지막 `[GoalEval] 라운드 N: ...` 구조 마커가 정본이며 산문 `평가 응답`은 구로그 폴백이다.
  - `source` 칸 (2026-08-22): `usage`(실사용) / `test`(시험 프로세스). **시험이 남긴 주행은 몸의 삶이 아니다** — 지우지 않고 표식만 붙이고, 읽는 쪽이 기본값으로 거른다(NULL=칸 신설 전 행=실사용). 판정은 픽스처 이름 규약이 아니라 **프로세스 정체**(`runtime_utils.in_test_process` — `action_health` 와 같은 한 벌). 1000건 롤링에서도 시험분이 먼저 버려져 실사용 주행이 창에 오래 남는다.
- **사용**: `get_cognitive_trends()` → 진단 리포트(`diagnostic_report.md`)의 추이 분석.
- **조인(2026-08-21)**: 에피소드에 `task_id` 가 실려 **쓰기 관문 원장(`write_ledger`) ↔ episode ↔ tasks** 3중 조인이 닫혔다 — "이 파일이 왜 바뀌었나"를 요청 원문까지 한 호출로 거슬러 오른다(`[self:body]{op:"writes"}`).
- **한계**: 현재 *집계 통계*로만 소비. 개별 일화를 회상해 행동을 교정하는 루프는 미완. → 다듬을 자리 ②.
  - (단, 프로젝트 에이전트에는 `attempt_log` 테이블에 라운드별 시도·교훈을 적는 더 미세한 메커니즘이 별도로 존재.)

## 4. 절차 기억 — IBL 액션 + 워크플로우 + 해마 (핵심 학습 루프)

세 겹으로 구성된다.

**(a) 액션 정의** — 가장 안정된 절차 지식
`data/ibl_nodes_src/*.yaml`(코어) + 설치 패키지의 `ibl_actions.yaml`(패키지 자기완결 fragment) → `scripts/build_ibl_nodes.py`(삼각 검증) → `data/ibl_nodes.yaml`(런타임 캐시). 액션 하나하나가 곧 어휘화된 방법 지식이다(총계는 system_structure.md 의 빌드 파생 줄).

**(b) 해마(실행기억)** — 가장 살아있는 자기 학습 루프 ⭐
- `ibl_usage.db:ibl_examples`에 `(자연어 의도 → IBL 코드)` 쌍 + 768차원 임베딩 저장
- **주제 트리(topic, 2026-09-03 사용자 판정 "실행기억도 주제별 폴더로")**: 용례마다 주제 가지(`보고서/AI 동향` 꼴, 가이드와 맞물림 `guide:`). 가지마다 문서 `data/hippocampus_tree/<가지>/memory.md`(표식·`> 요약`·`guide:`·`## 용례` 기계 절)가 정본, DB 는 색인(`backend/datastore/hippo_tree.py`, 사람이 고친 줄은 구문 관문을 거쳐 색인 반영). 지도는 `<execution_map>` 으로 매 턴 주입(가지·건수·요약·가이드), 가지는 `[self:memory]{op:"recall", node, store:"실행"}` 로 연다. 증류기가 지도를 보고 `topic` 을 적는다(코드 분류기 없음). **주행 절**(2026-09-04 사용자 판정): 가지 문서의 `## 주행` 에 그 주행에서 성공한 문장들을 실행 순서대로 남긴다(가지당 최근 20건·주행당 30문장, 넘치면 절단 표기) — 대표 문장이 없어 '재사용 패턴 없음'이던 프로그램급 주행이 학습 0건이 되던 자리, 지도에 `주행 n` 으로 보인다. 얼린 워크플로가 아니라 용례다. **관용구 절**(2026-09-04 저녁, 정본 `docs/IBL_IDIOM_TIER_HANDOFF.md`): 낱말(용례 한 문장)과 얼린 워크플로 사이의 층 — 독립 문장 2~8개를 `;` 로 이은 골격에 구체값은 `${슬롯}` 으로 비운 것. DB 엔 `category='phrase'`, 가지 문서 `## 관용구` 절이 정본(용례 절과 같은 규약 — 사람이 고친 블록은 구문 관문을 거쳐 색인, 지우면 삭제), 지도에 `관용구 k`. 증류기의 두 번째 질문 「이 주행에서 되풀이될 모양은?」이 뽑고(AI 몫, 코드 분류기 없음), 기계는 **순서 보존 부분열 접지**만 집행한다 — 각 문장은 슬롯을 이번 값으로 되돌렸을 때 실행 호출과 머리·인자 키가 같아야 하고 순서는 실행 순서의 부분열(★순서는 흐름이 아니다: `>>` 접지는 한 호출 안, `;` 접지는 부분열). 개인 명사(홈 경로·목록)는 거절 — 슬롯으로 비우는 것이 곧 관문. 회상은 낱말 Top-5 옆 **관용구 Top-2**(`kind="phrase"` 번호 목록, 임계 동일·저신뢰 폴백 없음, 낱말 채널은 관용구 제외라 반사 top-1 은 낱말만), 귀속은 문장 머리 열의 부분열이 실행 궤적에 절반 이상 등장했을 때(회상된 관용구가 쓰인 턴은 새 관용구를 뽑지 않음). 재학습 게이트는 관용구 Top-5 를 분리 보고하고 회귀(−0.5p)면 보류. 주행 절(녹취록)은 관용구의 증거로 남는다. **세 갈래**(같은 날 밤, 사용자 판정): 뽑기(`scripts/replay_idioms.py` 되돌려 묻기 — 에피소드 원장에 같은 반성기·같은 관문, 되풀이 증명 골격만) · 짓기(`--rehearse` — 설계한 관용구를 라이브 `/ibl/execute` 로 한 번 돌려 성공한 것만 저장, 실패=언어 공백 신호) · 가르치기(`ibl_access._idioms_block` — 환경 프롬프트 `<ibl_idioms>` 에 사용 횟수 상위 6건 상시, 나머지는 회상 Top-2). 첫 밤 14건(설계 8·뽑기 6). 관용구 색인 = 의도×3+머리 열 패턴. 코드는 `backend/cognition/ibl_idiom.py`(rag 에서 분할, 이름은 rag 가 재수출). **서명에 반환**(2026-09-05, `docs/IBL_STATIC_TYPECHECK_HANDOFF.md`): 관용구·워크플로 저장 시 정적 검사기(`ibl_typecheck.return_type_of`)가 반환 모양을 산정해 `ibl_examples.returns` 에 적고, `<ibl_idioms>`·이름 먼저 회상·가지 문서 `호출:` 줄이 `[fn:이름]{슬롯} → items⟨열⟩/prose/effect/?` 로 보인다 — 부르기 전에 무엇이 나올지 알아야 뒤 문장을 쓴다. 일괄 산정은 `scripts/replay_idioms.py --type-idioms --apply`. ★매 턴 유사도 Top-5·반사 경로는 그대로 — 트리는 대체가 아니라 축 하나(정기 작업의 성공 문장 모음 = 결정화 사다리 용례→**관용구**→워크플로→가이드).
- **검색**: 매 요청 1회, 현재 기본은 시맨틱 100%(`DEFAULT_ALPHA=1.0`) Top-5 → XML 주입. 임베딩 모델이 아직 준비되지 않았거나 사용할 수 없을 때 FTS5/BM25가 폴백한다
- **증류**: 해마 점수 < 0.7(유사 선례 없음) + 실행 성공 시 → 반성 에이전트가 일반화 → DB + `ibl_distilled.json` 누적 → 다음 검색부터 반영
- **첫 등록의 닭과 달걀**: 새 액션/op는 아직 성공 실행이 없어 자동 증류가 시작될 재료도 없다. `description`/`ops.values`는 존재를 알리지만 자연어→op 선택과 인자 모양을 대신하지 않는다. 그래서 첫 등록은 manual seed를 넣고 실제 연상 프로브를 통과시켜야 한다. 코퍼스·실행에서 관측된 키는 `ibl_param_sweep.py`가 카탈로그의 `⟨인자: …⟩`로 올린다.
- 임계값: 표시 MIN_SCORE 0.65 / 증류 DISTILL_THRESHOLD 0.7 — 단 점수 ≥ 0.7이어도 회상 top-1 액션이 실행에 실제 사용되지 않았으면(가짜 유사도) 새 패턴으로 보고 증류 진행(`_recall_was_used`, 2026-08-07 ep949 학습 유실 수리. top_code 없는 조종실 경로는 점수 게이트 그대로)
- **증류 게이트 셋째 신호 — 품질**(2026-08-27): 구조 실패·목표 미달성에 이어 **AI step 품질 미달**이 학습 회로에 붙었다. ①미달(`error_type:"quality"`) 봉투는 `success:false` → 이미 있던 증류 성공 필터가 거른다(새 코드 0줄, 사슬 핵심 고리를 회귀로 고정) ②재시도로 통과한 건은 `pass_after_retry`+`criteria_feedback` 을 봉투에서 캐 반성 프롬프트에 병기 — "첫 미달 사유가 재발하지 않게 instruction 을 다듬어라(criteria 보존)"로 먹여, 약한 지시 대신 **개선된 지시**가 증류된다. ★게이트 규칙(미달 용례를 학습하지 마라)은 판정 데이터가 쌓인 뒤에 정당화되는 것이 아니라 지금 참이다 — 미루면 그 사이 오염 용례가 코퍼스에 들어가 재학습 때 해마에 구워진다. 정본 = `docs/IBL_QUALITY_CONTRACT_HANDOFF.md`.
- 상세: 아래 **부록: 연상기억 심층**

**(c) 워크플로우** — 명시적으로 저장된 조합, **2026-08-22부터 함수 쪽으로 한 칸**
`data/workflows/*.yaml`에 문장(`>>` 순차 / `&` 병렬 / `??` 폴백 / 블록)을 이름 붙여 저장. `[self:workflow]{op:"save|run|list|get|delete"}`.
- **이름**: 저장본은 `name` 또는 `workflow_id` 로 부른다(`do` 를 직접 주면 저장 없는 즉석 실행).
- **인자(시그니처)**: 파스 후에도 남은 **미할당 `$이름`이 곧 자유 변수 = 인자**다. `save` 가 계산해 `params_required` 로 저장·보고하고 `list`/`get` 이 노출한다. 저장본 `run` 은 인자 누락을 **정직 거절**(선언 시점이 있으므로), 즉석 `run` 은 `params_warning` 만. `params_default:{이름:값}` 는 기본값이고 호출자 `params` 가 이긴다. ★한글 조사·단위가 이름에 먹히는 자리는 괄호로 끊는다(`"${n}건"`).
- **반환값**: 몸통 마지막 문장의 통화가 반환값. 몸통에 `$return = …` 이 있으면 그 결과가 반환값이 된다(마지막 문장이 알림 같은 effect 여도 된다).
- **합성**: `[self:workflow]{op:"run", name:…} >> [table:*]` 로 다음 문장에 통화를 넘긴다 — 옛 '다른 IBL 과 합성 불가'는 해소됐다. 남은 것은 *이름을 1급 어휘로 승격*하는 것뿐인데, 그건 반-어휘-증식 원칙과 정면으로 부딪힌다(아래 다듬을 자리 ①).
- **스코프·재귀**: 몸통의 `step_results` 는 run 마다 새로 나는 지역 dict — 호출 경계가 실제로 닫혀 있다. 워크플로우가 워크플로우를 부르는 사슬은 **순환(같은 id 재진입)·깊이 상한 5**에서 거절된다(`backend/ibl/workflow_contract.py`). 반복이 필요하면 `[repeat:]`/`[table:each]`.

## 5. 관계 기억 — 심층메모리 (사용자 지식 자동 흡수)

> **"사용하면서 사용자 지식을 흡수"의 실현체.** 매 대화 후 자동으로 사용자 사실을 추출·저장한다.

- **저장소**: 에이전트별 `memory.db` (memory 패키지, `memory_db.py`)
  - 테이블 `memories(category, keywords, content, created_at, node)` + 임베딩 인덱스
  - category: `사용자선호 | 사용자정보 | 작업기록 | 의사결정 | 중요날짜 | 기타` — **종류 표식**이지 축이 아니다
  - **주제 트리(node, 2026-09-03 사용자 판정 "심층기억을 평면으로 두지 말고 폴더 구조로 — 블로그와 같다")**: 행마다 주제 가지 경로(`가족/어머니` 꼴). 가지마다 문서 `<DB 옆>/memory_tree_<자아>/<가지>/memory.md` 가 **정본**(표식 + `> 한 줄 요약` + AI 산문 + `## 기억` 기계 절 + 갱신 기록), DB 는 색인 — 포식 기억 `forage_doc` 와 같은 배치. 사람이 절의 줄을 고치면 다음 회상 때 색인이 따라온다(`memory_tree.sync_node`, mtime 대조). **어디에 넣을지는 AI 가 정한다**: 증류기가 지도를 보고 `node` 를 적고(코드 분류기 없음), 남은 미배치 행은 `memory_tree.file_unfiled` 가 모델에게 배치시킨다. 어휘: `[self:memory]{op:"recall", node}`(가지 열기·생략=지도) · `save{node}` · `move{memory_id, node}` · `search{node}` 필터.
- **자동 저장** (`agent_cognitive._distill_deep_memory`): 대화 종료 후
  1. 경량 AI가 대화에서 기억할 사실 조각 추출 (이름·날짜·선호·결정·결과). **일시적 데이터(주가/날씨/환율/시세)·추론·감상은 제외**
  2. 기존 메모리에서 유사 항목 검색 → 중복이면 업데이트, 신규면 추가 (최대 5개/대화)
- **몸-명사 관문** (2026-08-28, `memory_db.body_noun_leak` — save/update 에서 raise): 이 저장소는 **세계의 명사만** 담는다(IBL 헌법 '명사의 자리'). 몸 내부 경로(backend/·docs/·data/guides/·내부 DB 등)가 기억되면 어휘를 우회한 접근로가 각인되어 회상 때 우회를 강화한다(ep2279 실측: 대화 DB 원시 경로가 `[self:recent_chats]` 대신 각인). 판정=기계 검사(절대경로 몸 루트 포함 / 상대경로 몸 루트 아래 실존), 예외=경로 마디 `outputs`(산출물 공간=세계의 산물). 증류 입구는 조각 단위로 거부 로그(`[심층메모리] 몸-명사 거부`)를 남긴다.
- **정리 패스 주간 스테이지 2종** (2026-08-28, `memory_consolidation` stage 4·5, 주 1회/DB 자체 카덴스):
  - **반증 패스**(AI 0): 낡음의 본질=사용 빈도가 아니라 '더는 참이 아님' — LRU 가 못 잡는 *자주 회상되는 틀린 사실*을 잡는다. 경로 주장은 실존 검사로 자동 수리(머리가 경로 지배 한줄이면 삭제·보충에 있으면 절단·혼합 기억은 보고만), URL 주장은 정의된 죽음(404/410/NXDOMAIN)만 보고. 오탐 가드: 첫 마디가 실존 루트 디렉토리인 절대경로만 파일시스템 주장으로 취급(/api/… 등 제외) + 공백 절단 관용 + 한글 조사 관용.
  - **원거리 모순 스캔**(배치 LLM 1회/DB): 쓰기 시점 판정·클러스터 병합은 임베딩이 가까운 쌍만 본다 — 표현이 달라 멀어진 모순은 의사결정·사용자선호 전체를 한 판에 놓는 배치 판정으로 잡고 낡은 쪽을 삭제. 가드=무판정이 오판보다 낫다 규칙+사이클당 삭제 상한, LLM 무응답 시 카덴스 미소진(다음 사이클 재시도). 로그 표식 `[반증]`·`[모순]`.
- **사용** (`cognitive_recall._memory_map_scent`): 매 요청 시 **지도(목차)만** `<memory_map>` 으로 주입 — 가지·건수·한 줄 요약, 내용 없음. 관련 가지가 보이면 AI 가 `[self:memory]{op:"recall", node}` 로 연다. (옛 Top-3 벡터 자동 주입은 2026-09-03 폐지 — 지도가 있으면 단서는 질문이 아니라 지도에서 온다; 벡터 `search` 는 가지 안에서 부르는 손으로 남는다)
- **#1 의미기억과의 차이**: #1은 시스템 자신에 대한 정적 파일 지식, #5는 **사용자에 대한 동적·의미검색 지식**. 자동 증류되는 살아있는 기억이다.

## 6. 자기 상태 — World Pulse / Self-Check (항상성·면역)

- **저장**:
  - `pulse_log` (30일 보존): 경제·뉴스·날씨·user/self 상태의 **정기 수집은 2026-06-28 폐지** — 정기 갱신은 위치+금주 일정만 `world_pulse.md` 로 쓴다(`collect_world_pulse`). on-demand `[sense:world]`·계기판 live pull 은 별도 경로. 테이블은 잔존 데이터 보존·정리 대상으로만 남아 있다.
  - `self_checks` (매일 1회, 30일): 결정론 건강 점검 — §1A 정적 정합성(`__static__:ibl_consistency`) + §1B fixture 통화 무결성 + §1C 골든 파이프. **AI 0**
  - **보존정책** (2026-09-02): `pulse_schedule.retention_days`(기본 30일) 하나가 pulse_log·self_checks·**action_health**·distill_queue 종결 행을 함께 정리(`_cleanup_old_data`). action_health 는 실행마다 한 행이라 무상한 누적이었는데 소비자(X-Ray·건강 요약·만성 실패)는 전부 최근 7일 창이다 — 읽는 이 없는 장기 집계표는 심지 않는다(소비자가 생기면 그때).
  - `action_health` (실행마다): 실사용 기반 액션 건강. 2026-08-21부터 `channel`·`error` 칸 — *어느 통로에서 왜* 실패했는지가 남는다. ★`assumed` 는 '미검증'이 아니라 '실사용 기록 없음'이다 · 시험 프로세스의 기록은 `source='test'` 로 격리(2026-08-21 B18-1) — 같은 판정을 주행기록도 쓴다(위 §3)
- **사용**: 프롬프트에 압축 주입 + 면역 순찰(만성 실패 감지) + `diagnostic_report.md`.

**몸 원장은 어디 있나 (2026-08-21)**: "내 몸이 언제 어떻게 바뀌었나"는 위 일곱 종에 새로 끼는 여덟 번째 기억이 *아니다* — 저장소가 이미 둘 있기 때문이다. **git**(추적 파일의 사건)과 **쓰기 관문 원장**(`data/write_ledger.jsonl` — git 이 못 보는 런타임 쓰기). 없던 것은 회상 통로뿐이었고, 그것이 `[self:body]{op:"changes|log|file|diff|writes"}` 어휘다. 전 op 읽기 전용이며, 관문 밖 직접 쓰기는 원리적으로 미기록이라 `writes` op 가 그 **부분성을 정직하게 광고**한다. 소유·수명 선언은 `backend/cognition/data_ownership.py` 의 `DECLARATIONS` (새 데이터 가족을 만들면 등재 의무). 상세=architecture.md '몸 원장'.

---

## 7. 공간 기억 — 포식 기억 / 냄새지도 (디스크·웹 탐색 경험)

> **"쓰면서 *공간*에 대한 지식을 흡수"의 실현체.** 해마(#4)가 "어떻게 하는가"를 증류한다면, 포식 기억은 "어디에 무엇이 사는가"를 증류한다.

- **문제**: AI는 stateless라 디스크를 한 시간 뒤져 알아낸 것(폴더 정체·죽은 가지·주인 관습)을 세션이 끝나면 잊고 매번 콜드 스타트한다. 그 "어떻게 뒤지나"는 *나만의 것*이라 가중치에도 없다.
- **저장소** (2026-09-03 개정, `backend/datastore/forage_doc.py` + `forage_memory.py`): **정본은 문서**다 — 위치마다 `data/forage_surveys/<몸>/<경로 그대로>/memory.md`(폴더 트리를 비춘 트리, 저장소 밖·개인정보) 의 `## 단언` 절. 절대 경로를 가진 단언은 몸 표기와 무관하게 `mac/<경로>/memory.md` 한 곳, URL 단언은 `host/path` 로 정규화해 `web/<host>/<path>/memory.md` 한 곳(같은 날 저녁 개정 — 몸 라벨이 `web:<url>` 이어도 무관). `code:`·`book:` 문서와 `web/memory.md` 뿌리 문서에는 경로·URL 없는 단언(주제 라벨)만 남는다. `data/forage_memory.db` 는 **2층** — `forage_map`(폴더 정체·관습·죽은가지·기질)은 그 절의 **색인**(DB 쓰기→문서 재렌더, 문서 편집→mtime 으로 색인 재동기화) + `owner_model`(몸독립 주인모델: 정체·분야·신호·습관 — 디스크·웹·코드 공유)은 DB 에만 산다(문서 이관 없음).
- **닫힌 루프**: ③ 포식 의도 시 `<forage_memory>` 주입(`_search_forage_memory`, 해마 `<execution_memory>` 옆) → ② AI가 포식(`file_find`/`grep`/`read`) → ④ 종료 훅에서 *일반화 가능한 지도 델타만* 증류(`_distill_forage_memory`, 날 내용·특정 파일 제외) → ⑤ 기존 라벨 위반 이질 내용은 surface 표식(필터버블 반대힘).
- **안전판 4**(누적의 그림자 방지): 폐기가능(prune_reason)·prior_class 게이팅(구조적만 committal prune)·surface 카운터패스·provenance+confidence.
- **★owner 빈도 게이트**(2026-07-29): 주인모델은 상시 노출이라 **1회 추론이 영구 주입**되는 구멍이 있었다(실측: 66건 전부 obs=1, 질문 *대상*이 주인의 "소속"이 되는 오염). → 첫 관측은 **임시**(`scent=0`, map처럼 query 필터), **서로 다른 포식에서 재확인**되면 상시 냄새로 결정화(`_OWNER_SCENT_PROMOTE_AT=2`, 상한 8). territory 승격과 같은 '빈도가 결정화한다' 모티프. 임시 항목도 지워지지 않아 **잃는 정보 0**, 모델에는 `provisional="1"`로 노출. 상세=`docs/FORAGER_MULTIBODY_DESIGN.md` §10-1.
- **부패 무효화**: lazy — 회상 시 폴더 mtime 비교해 `stale`/`missing` 노출(삭제 안 함, 판단은 AI. 손튜닝 감쇠 곡선 안 씀).
- **수동 액세서**(augmentation): `[self:forage]{op:recall|note|forget}` — 사람이 직접 조회·정정·재오픈.
- **프로젝트 폴더 = 프로젝트 에이전트의 CLAUDE.md**(2026-09-05 사용자 판정 "주입 쪽으로"): `projects/<프로젝트>/` 의 포식 문서를 `prompt_builder._project_memory_block` 이 안정 프롬프트에 `<project_memory doc=…>` 로 통째 싣고, 조상의 ↓ 관습·기질을 색인에서 덧붙인다(recall 의 inherit 규칙). 폴더 하나 고정이라 선택기가 없다 — 09-03 자동 주입 금지와 양립. 재조사=주 1회 트리거 `forage_resurvey_<프로젝트>` → `[others:delegate]{scope:"cross"}` 로 그 에이전트가 자기 폴더를 다시 조사(지침 `guides/folder_survey.md` '프로젝트 폴더' 절).
- **다중 몸**(`forage_map.body`=포식 *공간*): 디스크(`mac`)·코드(`code:<repo>`)·웹(`web`) 등 같은 자아가 여러 공간을 포식하면 body가 갈린다(하드웨어 자아=게이트 / 포식 공간=body 키 분리). `owner_model`은 1명·전 공간 공유 → 한 공간서 강화한 주인모델이 다른 공간 포식까지 풍부화(교차-몸 전이). **맥 자아 전용**(주관적 기억은 자아별 사적). **#4 해마와의 차이**: 해마=절차(NL→IBL 코드), 포식=공간(공간→지도 지식). 둘 다 증류+정리 대칭.
- **음성-단언 측정**: 포식 출력의 "거기 없음 vs 덜 봤음"을 측정으로 가른다(sample=미관측 균일 무작위 표본 / estimate=Wilson 이항추정). 판단은 AI 몫, 도구는 측정·중립 해석만(열거 가능한 공간 전용 — 웹은 무한·비열거라 제외). ★어휘 `[self:residual]` 은 2026-08-15 은퇴하고 **등록 스크립트**로 내려갔다: `[self:script]{op: "run", id: "잔여추정"}` (측정 절차는 낱말이 아니라 절차라는 판정 — 후보 제공자는 `backend/datastore/file_index.py`).
- **상세**: `docs/FORAGER_MEMORY_GUIDE.md`(설명서), `docs/FORAGER_MEMORY_SCHEMA.md`(스키마), `docs/FORAGER_MULTIBODY_DESIGN.md`(다중 몸), `docs/FILE_FORAGING_RESEARCH.md`(연구).
- **정리 패스**(`forage_consolidation.py`): 의미적 근접중복을 경량 AI로 병합(같은 공간지식만, surface 보호) + LRU 가지치기. `run_maintenance_bundle` item 4로 합류(24h 카덴스). 증류+정리 대칭 = 심층메모리·해마와 동일.
- **진행**: 주입→포식→증류→surface→정리 루프 완전히 닫힘 + 다중 몸(코드·웹) + 음성-단언 측정 완료(2026-06-20). **회상은 자동 주입이 아니다**(2026-09-03 사용자 판정 — 옛 항상-on 주입 폐지): AI 가 질문의 장소를 보고 `[self:forage]{op:"recall", locus}` 로 그 폴더의 문서(트리 `data/forage_surveys/mac/<경로>/memory.md`, 조상 사슬·하위 문서)를 스스로 올린다. 시스템 프롬프트 한 문장 + 어휘 입구가 전부이고 선택기는 코드로 두지 않는다. 증류(쓰기)는 전 티어 post-response 유지.

---

## 요청 1건에서 7종 메모리가 협력하는 흐름

```
사용자 입력
  │
  ├─[2 작업기억]  최근 7턴 회상 (Observation Masking)
  ├─[4b 해마]     유사 IBL 선례 검색 → 점수 산출 ┐
  ├─[5 심층메모리] 기억 지도(가지 목차) 합성      ┘→ 연상기억(<execution_memory>+<memory_map>) 합성 — 내용은 recall 로
  ├─[7 포식기억]   포식 의도 시 냄새지도 주입 (<forage_memory>, 해마 옆)
  ├─[결정원장]     사용자 판정 다이제스트 상시 + 질의 일치 상세 (<decision_ledger>, 정본=data/decisions.yaml)
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

> **결정 원장** (2026-08-29 신설): `data/decisions.yaml` — 사용자가 내린 설계 판정(기각·채택·보류)의
> 단일 원장. 회상 0단계(`cognitive_recall._decision_scent` → `decision_ledger.scent_xml`)가 활성 판정의
> 한 줄 다이제스트를 **상시** 주입하고(제안은 턴 *중간*에 생기므로 키워드 게이트만으로는 못 잡는다 —
> ep 실측: 외부 조사 턴이 노드 스코핑 기각을 모르고 재제안), 질의가 keywords 에 걸리면 사유·출처
> 상세를 얹는다. 추가·개정은 YAML 편집만(판정 이름을 코드에 넣지 말 것) · 뒤집힌 판정은 삭제 아닌
> `status: superseded`(반증 가능). 관문=`backend/test_decision_ledger.py` D1~D5.

**핵심**: 메모리가 곧 라우팅이다. 해마 점수(절차 기억의 친숙도)가 "반사로 처리할지, 의식을 동원할지"를 결정한다. 두 개의 자기 학습 루프(해마 증류 / 심층메모리 증류)가 사용할수록 시스템을 빠르고 개인화되게 만든다.

---

## 진단 — 다듬을 자리 (2026-05-31 기준, 미구현)

설계 이상에 비추어 코드에 비어 있는 곳. 우선 *진단*으로만 기록하며 구현은 보류한다.

### ① 워크플로우 → 1급 IBL 액션 승격 (2026-08-22 재평가 — 절반 해소, 절반 기각 쪽)
- **해소된 절반**: 합성은 된다. `[self:workflow]{op:"run", name:…} >> [table:*]` 로 통화가 다음 문장으로 흐르고, 인자·반환값·스코프 격리·재귀 가드까지 갖춰 **함수 호출**의 모양이 됐다(위 4-(c)).
- **남은 절반**: 이름이 `[self:일일브리핑]` 처럼 어휘가 되지는 않는다. 그런데 이건 부채라기보다 **선택**이다 — "새 낱말 만들까?"의 기본 답은 "아니오, 문장으로 얼려라"이고(반-어휘-증식), 어휘가 늘면 전 에이전트의 프롬프트 비용이 는다. 승격을 다시 논하려면 *빈도가 결정화를 정당화하는지*(앱 표면으로 굳힐 정도인지)부터 재야 한다.

### ② 일화 기억 → 개별 반성 루프 닫기
- **현재**: episode_summary는 집계 추이로만 소비.
- **이상**: 해마처럼 **유사 과거 에피소드를 회상**해 "지난번 이 작업은 NOT_ACHIEVED, 교훈 X"를 의식 에이전트에 주입. 해마=성공 코드 회상, 일화=실패 경험·교훈 회상의 짝.

### ③ 작업 기억의 의미 보존 압축 — ✅ 해소(2026-08-14, `history_checkpoint.py`)
- 밀려난 턴을 경량 AI 재귀 요약 체크포인트로 보존해 히스토리 머리에 주입(위 §2). 남은 것: 요약 품질·갱신 실패의 가시화(`last_error` 칸만 있음).

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
- `world_pulse_health.run_maintenance_bundle` 에 `run_memory_consolidation()` 합류(옛 `run_self_check` 는 2026-06-27 은퇴). **내부 24h/DB 카덴스 게이트**로 6h마다 호출돼도 각 DB는 하루 한 번만 실제 정리. dirty하지 않으면 즉시 스킵
- 비용 가드: `MIN_ROWS_FOR_CLUSTER=8`(미만이면 클러스터 스킵), `MAX_CLUSTERS_PER_DB=12`
- 진입점: 정기(self-check 자동) — 추후 수동 IBL op `[self:memory]{op:consolidate}` 추가 여지
- 파일: `backend/cognition/memory_consolidation.py`, `data/packages/installed/tools/memory/memory_db.py`

**검증(2026-05-31)**: 시스템 AI DB(16건)에 force 실행 → 사용자 주소 중복(id 2·3) 병합, 자녀 주소(id 1)는 분리 유지, 15건으로 정리. vec 동기화·카덴스 게이트 확인.

### ✅ 추가 구현 — ⑤ 회상 시 freshness 노출 (2026-05-31)

회상이 recency를 무시하던 문제(⑤)는 **랭킹 재가중이 아니라 타임스탬프를 함께 회상시키는** 방식으로 해결했다 (AI 친화적: 손튜닝 감쇠 곡선 대신 에이전트가 스스로 판단). 당시의 자동 회상(`<related_memory>` 각 항목에 `last_seen="YYYY-MM-DD"` 부착 + 헤더 note 안내 — 이 자동 주입 자체는 2026-09-03 지도 주입으로 은퇴, §5 참조). 타임스탬프는 search 결과의 `used_at`/`created_at` 에서 취한다. **자동 회상은 `read(touch=False)` 로 `used_at` 을 올리지 않는다**(2026-09-02) — 검색에 걸린 것과 쓰인 것은 다르며, 자동 조회가 used_at 을 갱신하면 오검색 기억이 LRU 가지치기를 영원히 피한다. used_at 을 올리는 것은 명시 읽기(`[self:memory]` read)·증류 SAME/UPDATE 뿐.

### ✅ 추가 구현 — ⑦ 쓰기 경로 비용 배치화 (2026-05-31)

매 턴 경량 AI 최대 6회(추출 1 + 조각별 dedup 5)를 **최대 2회**로 줄였다. `_distill_deep_memory`의 dedup 판정은 조각마다 독립적이라, (1) 유사 후보가 없는 조각은 LLM 판정 없이 곧장 NEW 저장, (2) 후보가 있는 조각들은 **단 한 번의 배치 호출**로 verdict 배열을 한꺼번에 받는다. 검증: 사소한 턴 1회(추출이 [] 반환)·신규 사실 1회(후보 없음)·중복 사실 2회(추출+배치). verdict 누락/파싱 실패는 NEW로 안전 처리.

심층메모리(#5) 2026-05-31 진단분 ①~⑦은 해소됐다. **남은 부채(2026-09-02 감사)**: 저장소 간(의미기억·포식기억) 교차 충돌 판정 없음 · 보호 카테고리에 검증일/만료 없음 · `retrieved/used/verified` 의 완전 분리는 used_at 비갱신까지만(verified 축 미구현).

---

## 실행기억(#4 해마) 정밀 진단 & 피드백 루프 (2026-05-31)

`ibl_usage_rag.py`(증류·연상) + `ibl_usage_db.py`(저장·검색) 추적 결과, **증류(입력)는 작동하나 증류물의 품질을 측정·교정하는 닫힌 루프가 부재**했다. 결정적 단서: `update_success`/`log_execution`의 호출처가 0개 — 성공/실패 추적·실행 로그 인프라가 만들어졌으나 배선되지 않았다(심층메모리 `used_at` 데자뷰).

### ✅ 구현됨 (2026-05-31)

| 부채 | 해결 | 구현 |
|---|---|---|
| **① 피드백 루프 죽음** | ✅ Reflex top-1 성공/실패 기록 → success_rate 표시 | `record_recall_outcome()` — 고점수(≥0.85, 귀속 깔끔한 Reflex 경로)에서 top-1 example의 execute_ibl 성공/실패를 `update_success_by_code()`로 기록. 3개 증류 지점(websocket×2 + agent_communication)에 배선(→2026-08 `_after_response` 초크포인트로 흡수). `_format_references`가 success_rate를 표시(0.0=실패 포함, -1=미검증은 숨김) → 연상이 검증된 사례를 선호. 리랭킹이 아니라 **표시로 AI가 판단**(last_seen과 동일 철학) |
| **② 증류 검증 게이트** | ✅ 환각 액션 차단 | `_validate_ibl_actions()` — distilled code의 모든 `[node:action]`이 `ibl_nodes.yaml`에 실재하는지 정적 검증, 미존재 시 증류 폐기. add_example 전에 호출 |

**시간·토큰 선택압 (2026-08-30)**: 시간·토큰이 좌표/총계로만 있고 **비용**으로는 없어 같은 목표를 싸고 빠르게 이루는 표현에 유인이 없던 공백(사용자 판정 2건: "더 빨리 하는 것에 인센티브가 없어" → "토큰 소모를 상관없어하는 태도도 문제. 단 품질을 깎아 아끼는 것은 금물")을 ①의 같은 배선에 비용 축 둘로 추가. 두 축은 **다른 낭비**를 잰다 — `avg_ms`=IBL 실행의 빠르기(`agent_pipeline._collect`가 tool_start→tool_result 이음매에서 `elapsed_ms` 도장), `avg_tokens`=그 표현을 두른 턴의 모델 소요(불필요한 서치·재시도가 찍히는 자리 — `providers.base` **턴 토큰 원장**: contextvar 에 record_request 단일 길목이 겹쳐 적어 프로바이더 스왑·평가/반성 oneshot 까지 한 턴으로 합산, `[턴비용] tokens=` 로그). `record_recall_outcome`이 **성공 실행만** EWMA(α=0.3, -1=미측정)로 귀속, 증류는 출생 실측을 심음. 소비 2곳 — 회상 XML `avg_ms`·`avg_tokens` 속성(표시로 AI가 판단, note 에 "품질을 깎아 아끼는 것은 금물" 계약 명기) + 근접중복 정리 생존키(`_dedup_quality`: 성공률→시도수→**빠르기**→**토큰 검약**→최신 — 비용은 신뢰를 넘지 못하고, 실측이 미측정을 이긴다). 훈계 0 — 전부 이음매. 폰 렌트 인덱스도 동반(export_hippo_index). 관문=`test_time_selection.py` T1~T9.

**검증(2026-05-31)**: 고점수+성공→success_count, 고점수+실패→fail_count, 저점수(THINK)·비IBL→무시, 표시 가드(tried 0.5/0.0 표시·untried 숨김), 환각 액션(sense:teleport 등) 폐기 모두 확인.

### ✅ 추가 구현 — 해마 정리 패스 (③④⑤, 2026-05-31)

심층메모리 정리 패스의 대칭. 증류물(`source='distilled'`)에만 적용하고 **학습 코퍼스(synthetic/balanced/manual_seed)는 보호**한다. 증류물은 사실이 아니라 참고 코드라 LLM 병합 판단이 불필요 — **순수 기계적**이다.

| 부채 | 해결 | 구현 |
|---|---|---|
| **⑤ 증류물 가지치기 없음** | ✅ 검증실패 가지치기 | `consolidate_distilled` — `fail_count≥2 & success_count==0`인 입증된 나쁜 사례 삭제 (①의 피드백 루프가 살아나 가능해짐) |
| **③ 증류 쓰기 중복 누적** | ✅ 근접중복 제거 | 증류물끼리 임베딩 코사인≥0.92 클러스터 → 최선(성공률→시도수→빠르기→최신, `_dedup_quality`) 1개만 유지. 0.92 미만 유사 항목은 보존 |
| **④ json 무한 append** | ✅ dedup + 상한 | `_consolidate_distilled_json` — 완전중복(intent+code) 제거 + 최신 800건만 유지 |
| 상한 | ✅ | distilled가 200 초과 시 미검증(trial 0)부터 오래된 순 삭제 |

**아키텍처**: `run_hippocampus_consolidation`을 `world_pulse_health.run_maintenance_bundle`에 합류(메모리 정리 패스 바로 다음 — 옛 `run_self_check` 는 2026-06-27 은퇴). 내부 24h 카덴스 게이트(마커 파일 `data/training/.hippocampus_consolidated`). 삭제는 행+vec 동시(`_delete_examples`, FTS는 DELETE 트리거로 자동). 파일: `backend/datastore/ibl_usage_db.py`, `backend/cognition/ibl_usage_rag.py`.

**검증(2026-05-31)**: 드라이런(실코퍼스 2267 불변), 입증된 나쁨 가지치기(fail2/success0 삭제), 근접중복(sim 0.995 병합·우량 보존·실데이터 무손실·0.92미만 제외), json dedup, 24h 카덴스 스킵 모두 확인.

> 실행기억(#4) 2026-05-31 진단분 ①~⑤ 해소. 심층메모리 정리 패스와 **대칭 완성** — 두 자기학습 기억(해마/심층메모리)이 모두 증류(입력) + 정리(위생) 양쪽을 갖췄다.
>
> **귀속 관문(2026-09-02)**: `record_recall_outcome` 은 회상 top-1 의 액션이 실행 궤적에 실제 등장했을 때만(`_recall_was_used`) 성공/실패를 귀속한다. 증류 쪽은 2026-08 부터 이 관문을 썼으나 귀속 쪽이 빠져, 표면 어휘만 닮은 고점수 회상이 안 쓰인 턴의 결과까지 흡수하고 있었다(잘못된 강화·감쇠). 남은 부채: `run_command` 등 비-IBL 도구 실행은 해마에 증류·귀속되지 않는다(설계상 — 승격은 `[self:script]` 로).

---

## 자기상태(#6) 진단 & 유지보수 번들 (2026-05-31)

World Pulse(수집·가이드·진단리포트·action_health)는 건강하나, **Self-Check가 두 메커니즘으로 분기되며 기계적 유지보수가 고아가 됐다**는 단일 문제가 있었다.

- `run_self_check` (직접 안전 액션 전수 실행) → 이벤트 비활성화, **dormant**
- `trigger_ai_health_check` (시스템 AI에게 assumed 액션 점검 위임) → 당시 활성, 매 6h
- `record_action_health` 는 모든 IBL 실행에서 기록 — 실시간 신호 정상

> **현행(2026-08-22)**: 위 두 함수는 **은퇴했다.** 정기 경로는 `run_daily_health_check()` 하나이고(하루 1회, `world_pulse.py` 가 등록·옛 이름 `self_check`/`ai_health_check` 는 하위 호환 별칭), 그 꼬리에서 `run_maintenance_bundle()` 이 돈다. AI 순찰은 없다 — 아래 표의 'A. 유지보수 고아' 해결은 그대로 유효하고, 합류 지점 이름만 바뀌었다.

문제: `run_self_check`에 번들돼 있던 유지보수(정적 IBL 검증·만성실패 알림·**메모리/해마 정리 패스**)가 스케줄러 마이그레이션으로 정기 실행 경로에서 빠졌다. (패턴분석·진단리포트는 `generate_guide`에서 매시간 도므로 무사.)

### ✅ 구현됨 (2026-05-31)

| 부채 | 해결 |
|---|---|
| **A. 유지보수 고아** | `run_maintenance_bundle()` 추출(실패알림+메모리정리+해마정리) → **활성 경로 `trigger_ai_health_check`에 합류** + 수동 `run_self_check`도 공유. 각 항목 자체 카덴스 게이트라 양쪽 호출돼도 중복 작업 없음 |
| **B. 확률적 cleanup** | `_cleanup_old_data` 트리거를 `random()<0.04`(평균 25h, 비결정적) → **마커 파일 기반 결정적 24h 게이트**(`_cleanup_is_due`/`.world_pulse_cleanup`). 누락·중복 없고 마지막 정리 시각 기록 |

**의의**: 앞서 만든 메모리 정리 패스·해마 정리 패스가 dormant 경로에 걸려 실제로는 정기 실행되지 않던 것을 활성화. 파일: `backend/cognition/world_pulse_health.py`, `backend/cognition/world_pulse.py`. 검증: 번들이 세 작업 호출, 활성/수동 양쪽 배선, cleanup 결정적 게이트 모두 확인.

### ⚠️ 남은 빈자리 (별도)
- **C. 뉴스 게이팅이 JSON LIKE**: `world LIKE '%news%'`로 마지막 뉴스 시각 탐색(취약하나 pulse_log 30일 바운드라 실害 적음) → 전용 메타/컬럼이 깔끔.

---

## 다중 자아와 기억의 두 부류 (2026-06-14)

폰이 두 번째 독립 자아(폰-로컬 Gemini 두뇌)가 되면서, 기억은 두 부류로 갈린다:

- **사용자 세계-데이터 (객관)** — 연락처·비즈니스·일정·의료기록. 어느 자아가 보든 같은 사실이므로 **공유·동기화**(business.db는 LWW+tombstone CRDT 합집합 머지, by-need). 자동응답 같은 PC 전용 메타데이터는 PC에 수렴.
- **자아의 주관적 기억 (마음)** — 대화 이력·해마(절차기억)·자기상태(self-state). 각 자아의 체험이므로 **자아별 사적·비동기화**. 폰 자아는 응답 속도를 위해 해마를 비활성화(키워드 검색으로 충분)했고, 맥 자아만 해마를 운용한다.

정체성은 모델 위치가 아니라 **하네스(프롬프트+기억)**에 있다. 같은 사용자 세계를 보지만 각자의 마음을 가진 두 자아 — `detect_body()`가 각 자아에게 자기 몸(맥/폰)을 인지시킨다.

---

### 가이드 — 절차 기억의 시민 (2026-08-17)

가이드(`data/guides/`)는 액션 desc 의 10~30배 길이로 절차를 가르치는 **절차 기억**인데, 오래 증류도 순찰도 없는 유일한 기억이었다. 네 겹으로 봉합:
- **신선도 표식**(`backend/datastore/guide_registry.py`): 주입 시 `작성·최종수정(N일 전)·이후 무수정 사용 M회` 를 동반 — 읽는 에이전트가 낡음을 안다(나이=git 이력 기반).
- **주간 산문 감사**(`backend/cognition/guide_audit.py`, `__ibl_health__:guide_drift`): 회차당 6개, 신선도 역순.
- **사용 후 증류**(`backend/cognition/guide_feedback.py`): 턴 종료 증류 4단계 — 실제 사용된 가이드의 갱신 필요를 경량 AI 가 판정(깃발만, 수정은 사람/AI 별도 턴).
- 죽은 참조·고아는 build `--check` 의 가이드 부패 경고(비차단)가 잡는다.
- **입구는 지도 하나**(2026-09-03): 가이드는 실행기억 가지의 산문이다 — 가지 문서 `guide:` 줄(쉼표 목록)이 `<execution_map>` 목차에 실리고, 의식은 거기서 `guide_files` 를 고르며 실행자는 `read_guide` 에 파일명을 그대로 넣어 연다(파일명 정확 일치 빠른길). 옛 `<available_guides>`(guide_db 키워드 점수로 고른 최대 10개 목록)와 "작업 전 항상 read_guide 검색" 지시는 폐지 — 검색은 지도에 가지가 없을 때의 폴백. 가지 문서는 몸-사적(gitignore)이라 씨앗은 `guide_db.json` 의 `topic` 필드(추적)로 나르고, 문서의 `guide:` 줄이 있으면 그것이 이긴다(`hippo_tree.seed_guides`). 생명주기는 둘 다 참조자(`tree:<가지>`·`tree-seed:<가지>`)로 센다.

### 구성요소 생명주기 — 세포 사멸과 수면 후반부 (2026-09-02, 사용자 판정 2건 승인)

기억 7종 중 DB 기억(심층·해마·포식)에는 LRU·cap 가지치기가 있었지만 **가이드·워크플로우·스크립트·낱말**에는
망각이 없었다 — 깃발 순찰 일곱이 보고만 하고 정리는 사람 손이었다(2026-08-17 81KB, 09-02 세 가이드 다이어트).
세대 교체가 없는 한 개체는 죽음을 구성요소 수준으로 들여와야 한다는 설계(docs/COMPONENT_APOPTOSIS_HANDOFF.md):
- **죽음**(`backend/cognition/component_lifecycle.py`, 일일·무LLM): 생존 = 영양 지지(가이드·프롬프트·트리거·일정·
  경험 코퍼스·어휘 `guides:`·phone_only 몸의 **살아 있는** 참조) ∨ 쓸모 실행(success∧usage∧≠self_check∧¬빈 items —
  `action_health.n_items`·`workflow_run` 원장 신설·스크립트 last_run·가이드 주입). 유예 30일 → candidate(보이는
  표식: 가이드 첫 줄 주석·yaml `lifecycle` 필드 — **숨김 아님**) → 90일 더 무신호면 retired. 결정권=가역성: git 층은
  `_retired/` 이동+guide_db 항목 제거+`[self:body]{op:commit}` 라벨 `apoptosis:`, **낱말은 항상 판정 큐**(언어 개정),
  비가역 층(`_backups` 30일)도 판정 큐. 부활은 `lifecycle_state.json` revivals 에 남아 정책(`lifecycle_policy.yaml`)
  재조정 근거. 후보끼리의 참조는 지지가 아니다(고아 섬).
- **하향 정규화**(`backend/cognition/guide_downscale.py`, 주간·LLM): 가이드 바이트 예산 36KB(`check_file_size.py` 두 번째
  규칙 집합, pre-commit) 초과분과 `guide_audit` 깃발 가이드를 죽은 참조 → 은퇴 문구 → 미사용 절 순으로 압축.
  미사용 절은 **절 단위 사용 귀속**(`guide_registry.guide_section_use` — guide_feedback 이 매 턴 실행 궤적의 `[node:action]`
  으로 어느 절이 쓰였는지 적는다, 해마 `_recall_was_used` 와 같은 판정)이 3턴 이상 관측했을 때만 말한다(아니면 '못 봤음').
  **기계 대조가 관문**: 살아 있는 어휘 참조·절 제목·코드 경로 보존 + 더 짧음. 탈락은 파일 무접촉·`unchecked`.
- 회귀 고정물 `backend/test_component_lifecycle.py`·`backend/test_guide_downscale.py`. 자기점검 노드 `__telemetry__:component_lifecycle`·`guide_downscale`.

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
| **기억 지도** (`<memory_map>`) | 심층메모리 — 에이전트별 SQLite + 가지별 memory.md | 가지 이름·건수·한 줄 요약 (내용 없음 — `[self:memory]{op:"recall", node}` 로 연다) |

해마는 fine-tuned 임베딩 모델로 검색된다(backend 에서 한 번만 로드). 심층메모리의 벡터 `search` 는 가지 안에서 부르는 손으로 남고, 자동 주입은 지도만이다(2026-09-03).

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
related = self._memory_map_scent()          # 심층 기억은 지도(목차)만 (2026-09-03)
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
       <execution_memory> + <memory_map> 결합
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
[4a] THINK: GoalEval ← `## 연상기억` + 의식의 달성 기준, 미달이면 재실행
[4b] EXECUTE: GoalEval 없음; 실패·복잡성·세계 변경이면 실행기 SelfReflect 1회
    ↓
[5] 증류
    ├─ 해마: top_score < 0.7(또는 ≥0.7이나 회상 미사용) + 도구 호출 성공 → distill_experience()
    └─ 심층메모리: _distill_deep_memory() — 경량 AI로 사실 추출 → NEW/UPDATE/SAME
```

### 주입 위치 (모든 에이전트가 동등하게 self-describing 블록을 받음)

- **무의식**: 사용자 메시지 앞에 prepend
- **의식**: 외부 래퍼 없이 `<execution_memory>` + `<memory_map>` 직접 노출 (2026-05-17 정리, 2026-09-03 지도로 교체)
- **실행** (프로젝트/시스템 AI): `prompt_builder`가 시스템 프롬프트에 그대로 삽입
- **평가**: THINK의 GoalEval에만 markdown `## 연상기억` 헤더로 그룹화 (2026-05-17 정정 — 옛 "실행기억" 헤더는 부정확). EXECUTE/Reflex는 이 평가를 받지 않는다.
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
<memory_map note="이 자아의 심층 기억 지도(목차) — 가지 (건수) — 요약. 내용은 실리지 않는다. 답하기 전에 [self:memory]{op:&quot;recall&quot;, node:&quot;<가지>&quot;} 로 연다. 새로 안 사실은 save 에 node 를 붙인다.">
  취향/음악 (3) — 즐겨 듣는 장르·연주자
</memory_map>
```

각 태그가 self-describing이라 별도 외부 래퍼는 불필요.

---

## 해마 (Hippocampus)

뇌의 해마처럼 fine-tuned 임베딩 모델이 밀리초 내에 관련 IBL 코드 사례를 인출한다.

### 현재 라이브 모델 (2026-08-21 재학습 — 몸 원장 어휘 세대, 코퍼스 **3,448**, epoch 3·검증 0.886)

`[self:body]` 3 op 시드 16 + `writes` 시드 5 + 증류분(+35)을 흡수한 세대 — 게이트(1,245쌍·607패턴)에서 **code Top-5 +3.1p(88.3→91.4)**·desc T5 +0.7p, T1 −0.7/−0.9p(노이즈)로 채택. 백업=`data/models/ibl_embedding.bak.20260821_114913`. 몸 원장 어휘가 연상 직행하고, ★08-20 세대의 관찰 항목이던 "네이버 블로그 후기" 경계가 대조 시드 흡수로 잡혔다(라이브 translate 실증: `source:naver`·`type:blog` 정확). 신어휘 프로브 40/45 — 잔여 실패 5(`table:since`·`table:ai`·`table:brief`)는 코퍼스 희소가 원인이라 다음 시드 후보. 직전 세대 2026-08-20(epoch 7·0.864) · 2026-08-17(epoch 4·0.878).

**재학습 대기열(2026-08-22 기준)**: 프로그램급 IBL M1~M6 시드 36건이 아직 코퍼스에만 있고 모델에는 안 들어갔다 — 새 문법(술어·try/catch·repeat·식 할당·블록-인-파이프)의 연상은 당분간 FTS·문법 교재에 기댄다.

> ★**채택 판단에서 회귀 프로브를 액면 그대로 믿지 말 것**(이번 세대의 교훈): 자동 비교는 "보류"를 권고했는데
> 실측하니 회귀로 보인 항목이 **desc-공간 인공물**이었다(같은 문장을 코퍼스에서 인출하는 정확도는 1.000).
> 정작 중요한 *조합 문장* 인출은 새 모델이 우세였고, 라이브 일반화(새 상품명·임계값·요일 변주)도 정확했다.
> 그래서 권고를 뒤집어 채택했다. **비교표가 아니라 라이브 인출을 봐야 한다.**
>
> 직전 세대: 2026-08-16(epoch 6·검증 0.877 — 블록·`table:rename`/`flatten` 어휘 흡수) · 2026-08-04(epoch 5·검증 0.882).

아래는 2026-08-04 세대의 측정표 — **세대-비교 방법론의 본보기**로 남긴다(163 액션 어휘, 2,988 코퍼스, batch=8).
★**직전 라이브 모델과 같은 seed42 분할**에서 잰 값이다 — baseline(범용 ko-sroberta) 대비
수치는 크게 나오지만 채택 판단엔 못 쓴다(§재학습 절차는 `data/guides/hippocampus_retraining.md`):

| 지표 | 직전 모델 (07-21) | 새 모델 (08-04) | 개선 |
|---|---|---|---|
| Top-1 (code) | 64.0% | **66.3%** | +2.3%p |
| Top-3 (code) | 82.7% | **86.6%** | +3.9%p |
| Top-5 (code) | 88.9% | **92.2%** | +3.3%p |
| Top-1 (description) | 68.0% | **72.7%** | +4.7%p |
| Top-5 (description) | 92.2% | **94.2%** | +2.0%p |

> **분할이 다르면 비교가 안 된다**: 07-21 자체 측정치(code Top-5 92.5%)와 위 88.9% 는 모순이
> 아니다 — 코퍼스가 2,871→2,988 로 커지며 분할이 935쌍/393패턴 → 1,003쌍/399패턴으로 바뀌었다.
> 같은 분할에서 재면 새 모델이 6지표 전부 우세다(회귀 0). 세대 간 숫자를 나란히 놓지 말 것.

> held-out %가 직전(2026-06-12 92.6%)보다 소폭 낮은 건 코퍼스가 커지고(distilled placeholder 슬롯 등) 노이즈가 늘어 *측정 난이도*가 오른 영향 — 실연상은 멀쩡(아래 ~99% 및 시장-보고 쿼리 검증 0.635→1.0). 더 짜내려면 노이즈 distilled 가지치기.

- **재학습 경로 = 로컬**: 클라우드(Modal/Colab)는 옛 맥에어 OOM 때문이었음. 현 Mac M4 Pro 24GB는 OOM 없고 데이터셋이 작아 로컬 MPS가 더 빠름(클라우드 콜드스타트·400MB 다운로드 회피). lib 버전도 트레이너 검증값과 일치(torch/MPS·st 5.2.2·transformers 5.1.0). 파이프라인=백업→`backend/ibl_embedding_trainer.py`→rebuild_index→백엔드 touch.
- **실제 런타임 검색 정확도 ~99%**: 위 벤치마크(query→벌거벗은 코드 패턴)는 보수적 프록시다. 런타임은 query→저장용례(`intent×3 + code`)로 검색하므로(아래 "검색 방식") 액션단위 Top-5 ≈ **99%**로 천장.
- **어휘 정합**: 코퍼스(usage_db)는 항상 최신 어휘로 마이그·재색인한다(현재 건수는 빠르게 변하므로 `SELECT count(*) FROM ibl_examples`가 정본; 문서에 고정하지 않는다). ★**어휘를 지우면 코퍼스도 따라온다** — 음악앱 5기능 은퇴 때 `--check` 의 코퍼스 param 정합 가드가 죽은 파라미터를 잡아 용례 15건 삭제를 강제했고, 2026-08-15 지역정보·연락처·사업원장 은퇴에서도 코퍼스 이관(41행·27행 등)이 은퇴의 일부였다. 은퇴어의 용례는 **후계어로 재배선**하되, 후계가 없으면 삭제한다.
- **시딩은 단일 경로**: `add_examples_batch`(source=`manual_seed`). ★두 함정 — ①직후엔 임베딩 모델이 백그라운드 로딩 중이라 **벡터가 조용히 안 붙는다**(FTS 로만 걸려 회상되는 척함. 신호=`export_hippo_index` 의 '누락 N') → `_load_model_sync()` 후 `_index_batch` 재색인 ②시딩은 **`.venv` 파이썬 필수**(시스템 python3 엔 sqlite_vec 이 없다).
- 학습 환경: **로컬 Mac M4 Pro(MPS)**, batch=8(로컬최선), max_seq 64, 10 epoch, patience 3. 베이스 `jhgan/ko-sroberta-multitask`. (클라우드 Modal 경로 cloud_training/ 은 보존하되 기본은 로컬 — OOM 없는 M4 Pro에선 로컬이 빠름.)

> **당시 결론(2026-06-04): 모델은 런타임 천장(99.3%)이라 재학습은 거의 무차별.** batch 스윕(b4~b64)·트레이너 변수 조정 모두 런타임 검색을 의미 있게 못 올림 — 해마는 IBL *어휘*가 아니라 query↔저장 intent *의미*를 매칭해 vocab 변경에 본질적으로 강건하기 때문. 당시에는 하이브리드 alpha/FTS5를 품질 레버로 보았지만, 이후 키워드 artifact 때문에 현행 기본은 `DEFAULT_ALPHA=1.0`(시맨틱 100%, FTS5는 폴백 전용)으로 바뀌었다.

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
| **DB 위치** | 시스템 AI: `data/system_ai_state/memory_system_ai.db`<br>프로젝트 에이전트: `projects/{id}/memory_{agent}.db`<br>귀속 관문(2026-09-02): project_path 가 몸(저장소 루트·`data/`)이거나 agent 가 `system_ai` 면 시스템 DB, agent 가 비면 `MemoryOwnerError` 로 거부 — 이름 없는 호출이 `memory_None.db` 를 만들던 경로 봉쇄. 자동 회상·증류는 스레드 신원이 없으면 `self.agent_id` 로 폴백 |
| **격리** | 에이전트별 분리 (설계 의도 — 각 에이전트가 자기 도메인 지식만 유지) |
| **현재 규모** | 28개 DB / 622건 |
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
해마 점수 0.7+ & 회상 액션이 실행에 사용됨 → 스킵 (이미 아는 패턴)
해마 점수 0.7+ & 회상 미사용(가짜 유사도) → 새 패턴으로 증류 진행
해마 점수 0.7 미만 + IBL 도구 호출 성공 → distill_experience() → 해마에 추가
```

해마가 성숙할수록 증류 빈도는 줄어든다.

### 증류 꼬리의 비용 (2026-08-01)

증류는 응답 *뒤에* 붙는 꼬리라 사용자가 기다리는 시간이 아니어야 하는데, 실측 6분이 걸린 턴이 있었다(에피소드 889 — 증류 7콜 4.5분). 원인과 처방 셋:

- **하이브리드 추론 모델의 thinking**: 증류·분류 같은 **원샷 호출**에서 모델이 추론에 `max_tokens` 를 전부 쓰고 본문 0자를 냈다 → 프로바이더 층에서 원샷 경로의 thinking 차단 파라미터를 명시(DeepSeek 계열 실측).
- **0자 응답 가드**: 길이 초과로 빈 응답이 오면 그 자리에서 판정(조용한 재시도 루프 방지).
- **`_after_response` 백그라운드화**: 응답 전송 후 처리를 에피소드 refresh 와 함께 백그라운드로 — 꼬리 6분 → **4초**.
- **증류 영속 큐** (2026-09-02, `distill_queue.py`): 백그라운드가 데몬 스레드 한 장이라 프로세스와 함께 죽고 실패는 print 한 줄이었다. 이제 `world_pulse.db:distill_queue` 행으로 먼저 남기고(영속) 단일 워커가 순서대로 소비 — 성공=행 삭제, 실패=attempts·last_error 원장 후 재시도(상한 3 → failed), 종료=drain(유한 대기, 남은 행은 pending), 부팅=resume(러너를 다시 찾아 재개, 못 찾으면 orphaned 로 신고). 워커 하나라 증류끼리 경량 프로바이더 잠금을 다투지 않고, 워커는 배경으로 표식돼 원샷 잠금이 **전경 우선**(다음 턴 분류기가 기다리면 배경은 다음 잡기에서 양보, 진행 중 호출은 선점 없음)으로 돈다. 종결 행(failed/orphaned)은 보존기간(§6) 으로 정리.

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
├── ibl_distilled.json                    ← 경험 증류 누적(정리 패스 상한 800). 시딩은 `add_examples_batch` 단일 경로 (정적 시드 스크립트 rebuild_usage_db.py·generate_missing_intents.py 는 2026-07-22 폐기)
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

> **절차 정본 = `data/guides/hippocampus_retraining.md`** (백업·A/B 판정·프로브 갱신·롤백까지).
> 아래는 요약이다. ★**두 함정**: ①학습기가 **라이브 모델 폴더에 직접 덮어쓰므로** 돌리기 전
> 백업 필수(없으면 비교할 A 면이 사라져 채택 판단 불가) ②**재색인 없이 백엔드를 재시작하면**
> 새 모델 질의를 옛 벡터와 비교하게 되는데 **에러가 안 난다**.
> 순서 = 백업 → 학습 → `compare_models.py` A/B → 채택 → `epoch_*` 삭제 → `rebuild_index()` → 재시작.

```bash
cp -R data/models/ibl_embedding "data/models/ibl_embedding.bak.$(date +%Y%m%d_%H%M%S)"   # ★먼저
cd <repo>/backend
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
| `backend/cognition/ibl_usage_rag.py` | `build_execution_memory()` — (xml, top_score, top_code) 반환, `distill_experience()` |
| `backend/datastore/ibl_usage_db.py` | 해마 검색 엔진 (시맨틱 + FTS5 폴백, 점수 0~1 정규화) |
| `backend/ibl_embedding_trainer.py` | 해마 학습 스크립트 (베이스 모델에서 fine-tuning) |
| `backend/cognition/cognitive_recall.py` | `_build_execution_memory()` — 해마+기억 지도 합성, `_memory_map_scent()` (agent_cognitive 믹스인) |
| `data/packages/installed/tools/memory/memory_db.py` | 심층메모리 (시맨틱 우선 + LIKE 폴백, 2026-05-16 시맨틱 추가) |
| `backend/surface/api_websocket.py` | GUI/WS 경로 — 연상 단계 → Reflex 분기 → 실행 |
| `backend/cognition/agent_communication.py` | 채널 경로 — 동일 패턴 (2026-05-17 중급 모델 전환 추가로 일관성 확보) |
| `backend/cognition/system_ai_core.py` | 시스템 AI 경로 — 동일 패턴 |
| `backend/cognition/prompt_builder.py` | 시스템 프롬프트에 연상기억 삽입 (외부 래퍼 없이 직접) |
| `backend/cognition/system_tools.py` | `_log_ibl()` — 도구 호출 이력 |
| `backend/base/thread_context.py` | 스레드별 도구 호출 이력 |
| `data/models/ibl_embedding/` | fine-tuned 모델 (해마+심층메모리 공유, 422MB) |
| `data/training/ibl_training_balanced_20260516.json` | 현재 학습 데이터 |

---

*최근 변경(2026-08-28): 증류 게이트 셋째 신호(품질) — quality 실패의 학습 배제와 재시도-통과 신호가 반성 프롬프트로 들어가는 통로 명문화. 이력 정본=git log·changelog.log(`[self:body]` 회상).*
