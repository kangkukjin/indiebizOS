---
title: 시스템 아키텍처
scope: 설계 의도, 신체 구조 비유, 인지 파이프라인 큰 그림, 핵심 컴포넌트 개요
owner_code: 전체 backend/ (개념 수준)
last_updated: 2026-05-28
see_also: [system_structure.md, execution_memory.md, ibl.md, packages.md, technical.md]
---

# IndieBiz OS 아키텍처

## 정의

IndieBiz OS는 AI에게 지능적인 몸을 만들어주는 하네스(harness)다. AI의 본질적 가치는 **연결** — 사람과 세계를, 사람과 사람을, 알고 있는 것과 아직 모르는 것을 잇는 것.

하네스는 에이전틱 루프와 다르다. 에이전틱 루프는 AI의 처리량(throughput)을 올린다 — 도구를 더 많이 호출. 하네스는 AI의 판단력(intelligence)을 올린다 — 같은 모델이라도 하네스에 따라 결과의 질이 달라진다.

## 신체 구조 (생명체 메타포)

| 신체 시스템 | IndieBiz OS 구현 | 역할 |
|------------|------------------|------|
| 신경계 | IBL (5노드, 111액션) | 감각/행동의 상시 연결 |
| 감각기관 전처리 | 감각 전처리 (postprocess) | 원시 정보를 압축하여 뇌에 전달 |
| 선택적 주의력 | 의식 에이전트 | 매 턴 메타 판단 — 문제 정의, 초점, 달성 기준 |
| 반사 신경 | 경량 AI (분류) | EXECUTE/THINK 분류, 단순 요청은 의식 건너뜀 |
| 자기 교정 | 평가 에이전트 | 달성 기준 대비 평가, NOT_ACHIEVED 시 재시도 |
| 자의식/각성 | World Pulse | 매시간 세계/사용자/자기 상태 수집 |
| 면역계 | AI 건강 체크 + action_health | 매 12시간 시스템 AI가 부작용 없는 액션 전수 테스트, 모든 액션 실행을 자동 기록 |
| 자율신경계 | 스케줄러, 이벤트 엔진 | 의식 없이 돌아가는 리듬 |
| 해마 | 실행기억 (해마 + discover) | 1회 생성, 전 에이전트 공유. fine-tuned 임베딩으로 관련 기억 자동 인출 |
| 에피소딕 메모리 | episode_log + episode_summary | 에피소드(명령→응답)별 실행 로그 기록, 인지 품질 지표 영구 추적 |

## 인지 파이프라인 (연상 → Reflex/무의식 → 의식 → 실행 → 평가)

```
사용자 메시지
    ↓
[0] 연상 단계 (해마 + 심층메모리, 단일 검색)
     → (xml, top_score, top_code)
    ↓
[1] Reflex 분기 (호출 측 결정)
    ├─ top_score ≥ 0.85 → EXECUTE + reflex_hint (무의식 스킵)
    └─ 미만 → [1B] 무의식 (경량 AI) → EXECUTE/THINK
    ↓                                              ↓ THINK ( = framing 수요)
EXECUTE/Reflex                          [2] framing 재고 확인 → 있고 맞으면 재사용(의식 스킵)
    │                                      없음/안맞음 → 의식 에이전트(본격 AI): task_framing + 달성 기준
    ↓                                              ↓
[3] 실행 에이전트
    Reflex(해마 고확신) → 중급 모델 / EXECUTE·THINK → 본격 모델
    (2026-06-10: EXECUTE를 중급→본격으로 — 무의식 오분류가 품질 저하로 이어지지 않게 하는 방어.
     덕분에 무의식 분류기는 EXECUTE 쪽으로 과감하게 기울 수 있다)
    ↓
[4] 평가 (경량 AI, 달성 기준 있을 때만, 최대 3라운드)
    ↓
[5] 증류 (해마 경험 증류 + 심층메모리 증류)
```

- **연상기억**: 파이프라인 최상단에서 1회 생성. 해마(과거 IBL 사례)와 심층메모리(사용자 사실)를 합친 self-describing XML 묶음 (`<execution_memory>` + `<related_memory>`)
- **단일 검색**: 검색 1회로 top_score까지 확보 (이전 3회 중복 호출 제거, 2026-05-17)
- **해마**: 베이스 `ko-sroberta-multitask`에서 fine-tuning. code Top-5 92.8%/desc 94.5%, **실제 런타임 검색 ~99%** (2026-06-05 Modal GPU 재학습, android 어휘 흡수, 코퍼스 ~2,316). 모델은 런타임 천장이라 재학습 거의 무차별 — 어휘 아닌 intent 의미를 매칭해 vocab에 강건.
- **심층메모리**: 같은 fine-tuned 모델로 시맨틱 검색 (2026-05-16 도입)
- **점수 정규화**: 모든 검색 경로(시맨틱·하이브리드·FTS5 폴백)에서 0~1 보장
- 상세: `system_docs/execution_memory.md`

## 사용자 표면 — 런처의 세 모드 (트릴레마)

위 인지 파이프라인은 **자율주행** 모드의 내부다. 같은 IBL 신경계 위에 사용자가 직접 모는 세 표면이 있고, 각각 {속도·표현력·주권} 중 둘을 갖고 하나를 내준다.

| 모드 | 무엇 | 비용 | 큐레이션 |
|------|------|------|----------|
| 자율주행 | 의도 → 플래그십 AI가 다단계 처리 (위 파이프라인). 구 '프로젝트' | 비쌈(Opus급) | AI |
| 수동 | 경량 모델이 자연어→IBL 번역(해마 기반) → 효과 dry-run 검수 → 실행 → (승인 시) 해마 증류. 컴파일러 프론트엔드: 모델은 번역만, 지능은 IBL 어휘에 누적 | 거의 0 | 인간+언어 |
| 앱 | 결정화된 sense 호출을 아이콘/GUI로 직접 조작 (부동산 실거래가·상권, 도서검색). 구 '액션' | 0(코드 실행) | 결정화된 워크플로 |

**생애주기**: 새 일은 자율주행이 탐색 → IBL 흔적이 수동 초안으로 → 검증된 고빈도 워크플로가 앱으로 결정화. *굳히는 건 증명된 것만.*

- 수동: `backend/api_ibl.py` (`/ibl/translate`·`/ibl/validate`(dry-run)·`/ibl/execute`·`/ibl/distill`) + `frontend/.../ManualMode.tsx`. 부작용 step은 명시적 확인 게이팅, 해마 증류는 사용자 승인 시에만.
- 앱: **선언 기반 단일소스**. 각 계기는 IBL 액션의 `app:` 블록(`data/ibl_nodes_src/`)이고 `/launcher/instruments`로 자동 파생 → **데스크탑(`GenericInstrument.tsx`)·원격 런처·폰이 같은 선언을 같은 어휘로 렌더**(app 블록 1개 = 전 표면 동시 등장). 어휘: modes 탭, view 프리미티브(metric/kv/kv_list/card_list+드릴/image_grid/sparkline/list_action), periods 기간토글, 표시 템플릿 `{path|filter}`. 0토큰 IBL 직접 실행. escape hatch 2층: OVERRIDES(지도·네이티브 창 등 손제작 풍부판) + STATIC_DOMAINS(부동산 실거래가·길찾기 등 렌더 어휘 밖). `build_ibl_nodes --check`에 app 블록 정합성 합류.
- `_raw: true` 파라미터로 `postprocess:compress`(검색계 액션의 AI 요약)를 우회 — 앱·파이프라인이 구조화 원본을 받는다.

## 시스템 구조
디렉토리 트리는 **system_structure.md** 참조 (의식·실행·평가 에이전트의 시스템 프롬프트에 자동 주입되는 정전 문서).

## 핵심 컴포넌트

### 통합 AI 아키텍처 (5-Node + 쉘)
시스템 AI와 프로젝트 에이전트가 **동일한 `AIAgent` 코어(ai_agent.py) + 동일한 최상위 도구 7개**를 공유. `_is_system_ai` 플래그가 IBL 접근 노드 범위만 분리 (시스템 AI: 전체 노드, 프로젝트: 허용 노드).

**최상위 도구 7개**: `execute_ibl` / `run_command` / `todo_write` / `ask_user_question` / `enter_plan_mode` / `exit_plan_mode` / `read_guide`.
- 코드 실행은 **write→run 패턴**: 멀티라인은 `[self:write]`로 파일에 쓴 뒤 `run_command`로 실행, 한 줄은 `run_command "python3 -c '...'"`. 별도 Python/Node.js 실행기 도구는 없다 (이스케이프 충돌과 traceback 손실을 피하기 위해 제거됨).
- 인지 도구(todo/ask/plan)는 IBL 경유 불가(파라미터 구조 불일치)하여 별도 최상위. 상세 도구 schema는 `tool_loader.build_execute_ibl_tool()` 등 참조.

IBL 노드/액션 정의는 **ibl.md** 참조. 프로바이더는 **technical.md** 참조.

### 프롬프트 빌더 (prompt_builder.py)
시스템 AI와 프로젝트 에이전트 모두 동일한 프롬프트 구조 사용:

```
┌─────────────────────────────────────────┐
│     공통 설정 (base_prompt_v2.md)        │
│   - AI 행동 원칙, 도구 사용 가이드       │
├─────────────────────────────────────────┤
│      IBL 환경 (ibl_access.py)           │
│   - 사용 가능한 노드/액션 목록           │
│   - IBL 문법 가이드                     │
│   - 시스템 AI: 5개 노드 전체            │
│   - 에이전트: 허용된 노드만             │
├─────────────────────────────────────────┤
│       조건부 프래그먼트 (fragments/)     │
│   - 06_git.md: git_enabled=true일 때    │
│   - 09_delegation.md: 에이전트 2개+     │
│   - 10_system_ai_delegation.md          │
├─────────────────────────────────────────┤
│            개별 역할 프롬프트            │
│   - 시스템 AI: system_ai_role.txt       │
│   - 에이전트: agents.yaml의 role        │
├─────────────────────────────────────────┤
│         IBL 용례 RAG 참조 (동적 주입)    │
│   - 유사 과거 용례 XML 블록              │
│   - 사용자 메시지 수신 시 1회 주입        │
├─────────────────────────────────────────┤
│           컨텍스트 (동적 주입)           │
│   - 사용자 프로필, 시스템 상태 등        │
└─────────────────────────────────────────┘
```

### 프롬프트 XML 구조 / AI 프로바이더
모든 프롬프트의 XML 태그 구조와 지원 AI 프로바이더 목록은 **technical.md** 참조.
프로바이더는 모두 실시간 스트리밍 지원 (`process_message_stream()`, 이벤트: `text`/`tool_start`/`tool_result`/`thinking`/`final`/`error`).

### 위임 체인 시스템 (Delegation Chain) — Phase 27: 3단계 위임
에이전트 간 협업을 위한 핵심 메커니즘. 세 가지 위임 방식을 지원합니다:

**1. 동기/비동기 위임** (기존)
- `[others:delegate]`/`[others:delegate]{scope: "cross"}`를 통해 작업을 위임하고 결과를 자동으로 보고받음
- 순차 위임: `completed[]` 사이클 병합으로 이전 결과 보존
- 병렬 위임: EXCLUSIVE 트랜잭션 내 원자적 `responses[]` 추가로 race condition 방지
- 시스템 AI 위임: 3-레이어 감지 (도구명 / IBL 결과 / DB pending)

**2. 스케줄 기반 위임** (Phase 27)
- 에이전트 소유 스케줄: 모든 스케줄 이벤트에 `owner_project_id`/`owner_agent_id` 부여
- 크로스 위임: `target_project_id`/`target_agent_id` 지정 시 대상 에이전트 소유로 등록
- `calendar_manager.py`가 실행 시 소유 에이전트의 컨텍스트로 파이프라인 실행

### IBL (IndieBiz Logic) 시스템
- 노드 기반 추상화: `[node:action]{params}` 문법
- execute_ibl + 범용 언어 + 인지 도구 (총 9개 최상위 도구)
- **5개 노드, 109 액션** (라운드 2 통합 + op 어휘화 + 사용성 재감사 + 어휘 정리 후)
  - sense(39), self(42), limbs(40), others(6), engines(17)
- **액션 해석**: 직접 매칭만 사용 (verb 런타임 해석 제거)
- **프롬프트 가독성**: 액션에 category 태그 부여 → `<action-categories>`로 그룹 표시 (순수 표시용)
- **액션 라우팅 8종 체계**:
  - handler(260): 패키지 handler.py에서 처리
  - api_engine(2): API+transform 자동 발견
  - system(22): 시스템 내부 함수 직접 호출
  - trigger_engine(9): 트리거/이벤트 기반 실행
  - workflow_engine(6): 워크플로우 오케스트레이션
  - driver(5): 드라이버 프로토콜 추상화
  - channel_engine(3): 채널 추상화 계층
  - web_collector(1): 웹 콘텐츠 수집
- `api_registry.yaml`에 `node` 필드 추가 시 자동으로 노드 액션에 병합 — `ibl_nodes.yaml` 편집 불필요
- 에이전트별 접근 제어: `allowed_nodes`로 노드 필터링
- 인프라 노드(`self`, `others`)는 모든 에이전트에 자동 허용 (`_ALWAYS_ALLOWED`)
→ 상세 문서: [ibl.md](ibl.md)

### $file:N 파라미터 시스템
IBL 파서 밖에서 코드나 긴 텍스트를 전달하기 위한 메커니즘:
- `execute_ibl`의 `files` 파라미터로 긴 콘텐츠를 별도 전달
- IBL 파라미터에서 `$file:0`, `$file:1` 등으로 참조
- IBL 파서가 파라미터 내부의 코드를 잘못 해석하는 문제 방지
- 코드 블록, 긴 텍스트, 멀티라인 콘텐츠에 적합

### 감각 피드백 (Sensory Feedback) 시스템
파이프라인으로 묶어도 AI가 각 단계의 결과를 전부 볼 수 있어야 한다는 원칙:

**Provider tool result 절삭 정책**
- 기본: 8KB → **16KB**로 확대
- 파이프라인 실행 시: `_action_count × 16KB`로 동적 확장 — 액션 수에 비례하여 결과 보존

**중간 결과 보존**
- `workflow_engine`/`ibl_engine`: 중간 결과 500자 절삭 제거, 전체 결과 누적
- AI가 파이프라인의 모든 단계 결과를 온전히 확인 가능

**>> 연산자 실패 즉시 중단**
- 순차 실행(`>>`) 시 앞 단계가 실패하면 즉시 중단하여 불필요한 후속 실행 방지

**검색 결과 후속 액션 안내**
- 검색 결과에 `_note` 필드로 후속 액션 안내 (crawl, video_transcript 등)
- AI가 다음 단계로 자연스럽게 이어갈 수 있도록 힌트 제공

### 감각 전처리 (Sensory Preprocessing)
정보성 액션의 출력을 경량 AI로 압축하여 컨텍스트 폭발을 방지. `data/ibl_nodes_src/<node>.yaml`의 `postprocess` 블록으로 액션별 선언. 적용 액션: `search_ddg`, `crawl`, `search_news`, `travel`. 실측 65-70% 압축.
설정 형식과 디테일은 **technical.md** 참조. 구현: `ibl_engine.py`의 `_postprocess()`.

### 연상기억 (해마 + 심층메모리)
fine-tuned 임베딩(768d)으로 과거 IBL 사례(해마)와 사용자 사실(심층메모리)을 단계 0에서 1회 검색해 모든 에이전트에 self-describing XML로 주입.
- 해마: 2026-06-05 Modal GPU 재학습 (android 어휘 흡수), code Top-5 92.8%/런타임 ~99% — 자동 경험 증류 (점수 < 0.7 시)
- 심층메모리: 같은 모델 공유로 시맨틱 검색 (2026-05-16 도입)
- 상세 (단계별 흐름·증류 조건·DB 스키마·학습 절차): **execution_memory.md**

### 도구 패키지 시스템 (노드 구현체)
35개 패키지가 IBL 노드의 실제 구현체로 동작. 폴더 기반 탐지 + 동적 로딩. op-bearing 10 패키지는 `_OP_DISPATCHERS` 표준 채택(2026-05-28, android 합류 2026-06-05) — `build_ibl_nodes.py --check`가 AST 정확 비교로 src↔tool.json↔handler 일치 검증. 패키지 구조·설치·생성 절차는 **packages.md** 참조.

### 자동응답 서비스 V3
- Tool Use 기반 단일 AI 호출로 판단/검색/발송 통합
- `search_business_items`, `no_response_needed`, `send_response` 도구
- 응답 즉시 발송 (polling 대기 없음)
→ 상세 문서: [communication.md](communication.md)

### 다중채팅방 시스템
- 독립 창에서 여러 프로젝트의 에이전트를 소환하여 그룹 대화 수행

### 의식·평가 에이전트
인지 파이프라인의 전체 흐름과 단계별 디테일은 위 "인지 파이프라인" 섹션과 `execution_memory.md` 참조.

- **의식 에이전트 (본격 AI)** — `backend/consciousness_agent.py`
  - 직접 문제를 풀지 않고 "지금 어떤 문제를 풀어야 하는가"를 자기 한계 인식 기반으로 정의
  - 핵심 철학: 문제는 **나의 한계** × **환경의 제약**이 만나는 곳에서 생긴다
  - 출력: task_framing, achievement_criteria, history_summary, capability_focus, guide_files, self_awareness, world_state
  - 프롬프트: `data/common_prompts/consciousness_prompt.md`
  - 베이스 프롬프트(base_prompt_v5.md)의 "네 한계를 알아라" 원칙과 양방향 일관
- **framing 재사용 게이트 (2026-05-31)** — `agent_cognitive._run_consciousness_or_reuse()` + `_consciousness_fit_gate()`
  - 설계 원리: THINK = "framing이 필요하다"는 *수요* 선언. 분류기(무의식)는 history-blind라 "직전 태스크의 변주"를 알 수 없다 — 그래서 의식 호출 직전에 "그 수요를 *재고*로 충당할 수 있나"를 별개 신호로 묻는다 (분류기를 재심사하지 않음)
  - 같은 대화(registry_key)에서 만든 framing이 30분 내 재고에 있고 경량 fit 게이트가 적합 판정 → 의식(Opus) 호출 스킵, 재사용. turn마다 바뀌는 achievement_criteria만 게이트가 새로 생성 (비싼 framing 재사용 / 싼 criteria 갱신)
  - 캐시: 모듈 레벨 `_FRAMING_CACHE` (30분 TTL), SESSION_RESET·재시작 시 폐기. fits=false·재고 없음·게이트 실패 시 풀 의식 폴백(품질 손실 0)
  - 효과: 연속 THINK turn에서 의식 40~54초 + Opus 호출 제거. 주제 전환은 명시적=SESSION_RESET / 암묵적=fit 게이트가 분담
- **평가 에이전트 (경량 AI)** — `agent_cognitive._run_goal_evaluation_loop()`
  - achievement_criteria 대비 평가. NOT_ACHIEVED 시 재실행 (최대 3라운드)
  - 프롬프트: `data/common_prompts/evaluator_prompt.md`

### 의식 시스템 (Consciousness Pulse & Self-Check)
시스템에 자기인식을 부여하는 주기적 상태 수집 및 자가 점검 시스템:

```
┌─────────────────────────────────────────────────────────┐
│              Consciousness Pulse (매 1시간)               │
├──────────────┬──────────────────┬────────────────────────┤
│  World Delta │   User State     │     Self State          │
│  경제 지표    │   최근 대화 수   │   서비스 alive 체크     │
│  날씨 (매시간)│   미처리 태스크   │   디스크/메모리         │
│  뉴스 (6시간) │   다가오는 일정   │   최근 자가점검 결과    │
└──────────────┴──────────────────┴────────────────────────┘
                           ↓
              world_pulse.db (SQLite)
                           ↓
              world_pulse.md 가이드 파일 갱신
```

**AI 건강 체크 (매 12시간)**: 시스템 AI가 부작용 없는 IBL 액션을 전수 테스트
- 읽기 전용 액션만 선택, 캐시된 테스트 계획(`data/self_check_plan.json`)에서 파라미터 사용
- 결과는 `action_health` 및 `self_checks` 테이블에 자동 기록 (실사용 액션도 동일 테이블)
- 3단계 상태: verified(7일 이내 성공), assumed(기록 없음), failed(최근 실패)
- 사용자가 "자기 점검해줘" 명령 시 시스템 AI가 이 데이터를 `self_inspection_guide.md`의 검증 절차(실패 액션 재시도 → transient/reproducible 분류 → 수정 난이도 평가)에 따라 분석

**정적 정합성 검증 합류 (2026-05-28)**: `run_static_ibl_check()` — `build_ibl_nodes.py`의 삼각 검증(src ↔ tool.json ↔ handler.py `_OP_DISPATCHERS`)을 self-check 사이클 시작부에 통합. 결과를 `self_checks` 테이블에 `__static__:ibl_consistency` 식별자로 합류. 정적 부채(누락된 등록, op 키 drift)와 런타임 부채(액션 실패)가 같은 사이클에서 잡힘. pre-commit 훅(commit 시점)과 self-check 사이클(12시간 정기)의 이중 검증 채널.

**의식 에이전트 메타 인지 가드 (2026-05-28)**: consciousness_prompt에 3 가드 — backend 자기 편집=자기 reload 자해 인식, 첫 호출 성공 시 의심 즉시 갱신, timeout/실패 후 같은 코드 재시도 금지. 어제 dispatcher audit 사고에서 시스템 AI가 보인 자해/의심 휴리스틱 패턴을 후속으로 처치.

**에피소딕 메모리**: 에피소드(사용자 명령→최종 응답)별 실행 로그 기록
- `episode_log` 테이블: 전체 로그 (최근 100개 보존)
- `episode_summary` 테이블: 인지 품질 지표 영구 보존 (해마 점수, 무의식 판정, 의식 소요시간, 실행 라운드, 평가 결과)
- 파일: `backend/episode_logger.py`, DB: `data/world_pulse.db`
- API: `/xray/episodes`, `/xray/episodes/{id}`, `/xray/episode-summaries`

**서버 시작 시**: 최근 1시간 내 펄스가 없으면 즉시 수집, 있으면 건너뜀

- 비용: 사용자/자신 상태는 DB 쿼리만 (비용 0), 세계 정보는 경량 API 호출
- 파일: `backend/world_pulse.py`, `backend/world_pulse_health.py`, `data/world_pulse.db`
- 설정: `data/world_pulse_config.json`
- API (`api_config.py` 내): `/world-pulse/config`, `/world-pulse/refresh`, `/world-pulse/today`, `/world-pulse/trend`, `/world-pulse/pulses`, `/world-pulse/self-checks`, `/world-pulse/health`

### 원격 접근 시스템
Cloudflare Tunnel을 통해 외부에서 IndieBiz OS를 제어합니다:

- **원격 Finder** (`api_nas.py`): 파일 탐색, 동영상 스트리밍, 다운로드 — 개인 NAS처럼 활용
- **원격 런처** (`api_launcher_web.py`): 시스템 AI/프로젝트 에이전트 채팅, 스위치 실행 — 모든 AI 에이전트를 원격으로 구동
- 세션 기반 인증 (기능별 별도 비밀번호)
- 모바일 반응형 다크 테마 UI
→ 상세 문서: [remote_access.md](remote_access.md)

### 브라우저 자동화 (browser-action 패키지)
두 가지 드라이버를 통한 브라우저 제어:

- **Playwright 드라이버**: 별도 Chromium 인스턴스를 띄워 자동화. 항상 사용 가능.
- **Chrome MCP 드라이버** (계획): 사용자의 실제 Chrome 브라우저를 MCP 프로토콜로 제어. Chrome 확장 프로그램(MCP 서버)이 `localhost`에서 SSE/HTTP로 노출, IndieBiz OS가 MCP 클라이언트로 연결.
  - 수동 연결: 에이전트가 필요할 때 `[limbs:browser]{op: "chrome"}`로 연결
  - Chrome 미실행 시 Playwright로 자동 폴백
  - 같은 IBL 액션(`limbs:browser_*`)을 사용, 내부 드라이버만 다름

## 프로젝트 & 에이전트

- 프로젝트 단위로 독립된 작업 공간. 각 프로젝트에 역할별 에이전트 배치
- 에이전트 간 위임: 단일/순차/병렬 (`[others:delegate]{scope: "cross"}`)
- 시스템 AI: 전체 노드 접근, 프로젝트 에이전트에 위임 가능
- 프로젝트 에이전트: 허용된 노드만 접근 (allowed_nodes)

## 외부 연동

- **통신**: Gmail, Nostr (DM은 NIP-17 gift-wrap, 구 NIP-04 호환 수신), Telegram
- **NAS**: 음악 스트리밍, 자막 관리, 웹앱 호스팅
- **안드로이드 (양방향)**: 제어=ADB 기반 `[limbs:android]{op}` (snapshot→요소 탭) / 감각=폰 컴패니언 앱(NotificationListener)이 알림·위치·걸음을 NIP-17 한방향 피드로 전송 → `[sense:phone]{op}` + `/phone/*` API.
- **폰 네이티브 (indiebizOS 폰 자체 구동)**: phone-companion/ (Kotlin+Chaquopy) 네이티브 앱이 **폰에서 온디바이스 Python 백엔드**를 띄워 앱모드 슈퍼앱을 서빙하고 **실제 IBL 엔진**이 폰 안전 패키지(`build_ibl_nodes.PHONE_VERIFIED_PACKAGES`)를 로컬 실행한다. 빌드가 정본 트리(엔진+패키지+`ibl_nodes.yaml`)를 `indiebiz_base.zip` 에셋으로 번들→filesDir 추출. `runs_on` 능력 태그(`anywhere`/`home_only`/`phone_only`)와 `data/phone_manifest.json`이 폰 못 도는 계기/액션을 숨기거나 거부. 캡처 알림은 폰 로컬 JSONL→`[sense:phone]`, 라디오는 mpv 대신 stream URL을 WebView(hls.js)로 돌려 **폰 스피커** 재생. API 키는 app-private `filesDir/secrets/keys.json`로 주입(APK 밖). 폰=리모컨 아닌 진짜 sense+limbs 노드.
- **원격**: Cloudflare Tunnel (Finder + 런처). 원격 런처=집 PC 리모컨 의미론(라디오 재생은 집 PC 스피커).
- **브라우저**: Playwright 기반 자동화

## 시스템 통계

- 활성 프로젝트: 24개 (시스템 프로젝트 수동모드·앱모드 포함)
- 도구 패키지: 35개, IBL: 5노드 111액션 (라운드 2 + op 어휘화 + 사용성 재감사 + 안드로이드 통합)
- op-bearing 액션 24개, 모두 `_OP_DISPATCHERS` 표준 채택, AST 정확 비교 검증

## 참조

- IBL 명세: `system_docs/ibl.md`
- 실행기억 & 해마: `system_docs/execution_memory.md`
- 패키지 가이드: `system_docs/packages.md`
- 설계 철학 (백서): `WHITEPAPER.md`

---
*마지막 업데이트: 2026-06-11 — 폰 네이티브 정착(M1-M3: Chaquopy 온디바이스 백엔드 + 실제 IBL 엔진 + runs_on 능력 태그 + phone_manifest + API키 프로비저닝 + 수신알림→[sense:phone] + 라디오 폰 스피커 재생 hls.js) + 앱 표면 선언 단일소스화(투자/도서/라디오 OVERRIDE 제거, GenericInstrument에 periods 추가 → 데스크탑·폰·원격 같은 선언) + 라디오 한국 방송국 스트림 URL 부패 수정(CBS/EBS 갱신, SBS 토큰보호 제거). 이전(2026-06-10): 인지 경로 개편: 중급 모델을 Reflex 전용으로 좁히고 무의식 EXECUTE는 본격 모델 유지(오분류 품질 방어) + 무의식 분류기 재조정(THINK 과잉 축소) + 의식 프롬프트에 "좋은 문제 규정"(메타-메타)·"IBL과 코딩의 우선순위" 섹션. 이전(2026-06-05~06): 안드로이드 얇은 부활([limbs:android]{op}) + 폰 컴패니언 앱(NIP-17 한방향 피드 + [sense:phone]) + Nostr DM NIP-17 전환 + 음악 작곡 은퇴 → 111 액션. 이전(2026-06-04): IBL 사용성 재감사 종결 + ACTION_PARAM_ALIASES 중앙 적용. 이전(2026-05-31): THINK 경로 framing 재사용 게이트. 이전(2026-05-28): 라운드 2 정리 + op 어휘 단일화 + 삼각 검증 인프라.*
