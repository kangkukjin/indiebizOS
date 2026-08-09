---
title: 시스템 아키텍처
scope: 설계 의도, 신체 구조 비유, 인지 파이프라인 큰 그림, 핵심 컴포넌트 개요
owner_code: 전체 backend/ (개념 수준)
last_updated: 2026-08-06
see_also: [system_structure.md, memory.md, ibl.md, packages.md, technical.md]
---

# IndieBiz OS 아키텍처

## 정의

IndieBiz OS는 AI에게 지능적인 몸을 만들어주는 하네스(harness)다. AI의 본질적 가치는 **연결** — 사람과 세계를, 사람과 사람을, 알고 있는 것과 아직 모르는 것을 잇는 것.

하네스는 에이전틱 루프와 다르다. 에이전틱 루프는 AI의 처리량(throughput)을 올린다 — 도구를 더 많이 호출. 하네스는 AI의 판단력(intelligence)을 올린다 — 같은 모델이라도 하네스에 따라 결과의 질이 달라진다.

## 신체 구조 (생명체 메타포)

| 신체 시스템 | IndieBiz OS 구현 | 역할 |
|------------|------------------|------|
| 신경계 | IBL (6노드, 150 액션) | 감각/행동의 상시 연결 |
| 감각기관 전처리 | 감각 전처리 (postprocess) | 원시 정보를 압축하여 뇌에 전달 |
| 선택적 주의력 | 의식 에이전트 | 매 턴 메타 판단 — 문제 정의, 초점, 달성 기준 |
| 반사 신경 | 경량 AI (분류) | EXECUTE/THINK 분류 — 의식 각성(THINK)은 **장기 작업 또는 위험 작업**일 때만(2026-08-10 기준 상향), 그 외 전부 의식 건너뜀 |
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
    모델은 **모델 기어**가 결정 (model_resolver: 역할→축→기어→티어).
    Reflex(해마 고확신)는 'reflex' 축(균형 기어 기본=중급), EXECUTE·THINK는 'execute'·'consciousness' 축.
    (자동 변속기[무의식 분류기]가 작업마다 티어를 고르고, 수동 레버[절약/균형/최대]가 전체를 변속.
     상세: system_structure.md "모델 기어")
    ↓
[4] 평가 (경량 AI, 달성 기준 있을 때만, 최대 3라운드)
    ↓
[5] 증류 (해마 경험 증류 + 심층메모리 증류)
```

- **연상기억**: 파이프라인 최상단에서 1회 생성. 해마(과거 IBL 사례)와 심층메모리(사용자 사실)를 합친 self-describing XML 묶음 (`<execution_memory>` + `<related_memory>`)
- **단일 검색**: 검색 1회로 top_score까지 확보 (이전 3회 중복 호출 제거, 2026-05-17)
- **해마**: 베이스 `ko-sroberta-multitask`에서 fine-tuning. code Top-5 92.2%/desc 94.2%, **실제 런타임 검색 ~99%** (2026-08-04 **로컬 맥미니 M4 Pro 재학습** — 클라우드는 옛 맥에어 OOM 한정이었음, 코퍼스 2,988). 모델은 런타임 천장이라 재학습 거의 무차별 — 어휘 아닌 intent 의미를 매칭해 vocab에 강건. 절차·함정은 `data/guides/hippocampus_retraining.md`.
- **심층메모리**: 같은 fine-tuned 모델로 시맨틱 검색 (2026-05-16 도입)
- **점수 정규화**: 모든 검색 경로(시맨틱·하이브리드·FTS5 폴백)에서 0~1 보장
- 상세: `system_docs/memory.md`

## 사용자 표면 — 런처의 세 모드 (트릴레마)

위 인지 파이프라인은 **자율주행** 모드의 내부다. 같은 IBL 신경계 위에 사용자가 직접 모는 세 표면이 있고, 각각 {속도·표현력·주권} 중 둘을 갖고 하나를 내준다.

| 모드 | 무엇 | 비용 | 큐레이션 |
|------|------|------|----------|
| 자율주행 | 의도 → 플래그십 AI가 다단계 처리 (위 파이프라인). 구 '프로젝트' | 비쌈(Opus급) | AI |
| 조종실 (구 '수동'→'계기판', 2026-07-03 개명) | 경량 모델이 자연어→IBL 번역(해마 기반) → 효과 dry-run 검수 → 실행 → (승인 시) 해마 증류. 컴파일러 프론트엔드: 모델은 번역만, 지능은 IBL 어휘에 누적. 여기에 시스템 상태·모델 기어 레버·프레즌스·주행기록이 모여 **자율주행을 포함한 전체를 감독·개입하는 조종실**로 승격(내부 탭 키는 `manual` 유지) | 거의 0 | 인간+언어 |
| 앱 | 결정화된 sense 호출을 아이콘/GUI로 직접 조작 (부동산 실거래가·상권, 도서검색). 구 '액션' | 0(코드 실행) | 결정화된 워크플로 |

**생애주기**: 새 일은 자율주행이 탐색 → IBL 흔적이 조종실 초안으로 → 검증된 고빈도 워크플로가 앱으로 결정화. *굳히는 건 증명된 것만.*

- 조종실: `backend/api_ibl.py` (`/ibl/translate`·`/ibl/validate`(dry-run)·`/ibl/execute`·`/ibl/distill`) + `frontend/.../ManualMode.tsx`. 부작용 step은 명시적 확인 게이팅, 해마 증류는 사용자 승인 시에만.
- 앱: **선언 기반 단일소스**. 각 계기는 IBL 액션의 `app:` 블록(`data/ibl_nodes_src/`)이고 `/launcher/instruments`로 자동 파생 → **데스크탑(`GenericInstrument.tsx`)·원격 런처·폰이 같은 선언을 같은 어휘로 렌더**(app 블록 1개 = 전 표면 동시 등장). 어휘: modes 탭, view 프리미티브 12종(metric/kv/kv_list/card_list+드릴/image_grid/sparkline/list_action/thread/form/editable_list/map(인터랙티브 leaflet)/calendar), `on:` 뷰-이벤트(지도 moveend→재조회·marker_click→IBL 액션 또는 `{stream:true}`→HLS 영상), filter 필터칩(정적 단일선택 재조회 + 동적 `from_field`=결과-필드 distinct 칩, 클라이언트 측 거르기), 표시 템플릿 `{path|filter}`. 0토큰 IBL 직접 실행. escape hatch 2층: OVERRIDES(photo 풍부창·네이티브 창 등 손제작 풍부판) + STATIC_DOMAINS(부동산 실거래가·길찾기 등 렌더 어휘 밖 — 2026-06-29 상권은 인터랙티브 map+동적필터+드릴로 흡수돼 은퇴). `build_ibl_nodes --check`에 app 블록 정합성 합류.
- `_raw: true` 파라미터로 `postprocess:compress`(검색계 액션의 AI 요약)를 우회 — 앱·파이프라인이 구조화 원본을 받는다.

## 시스템 구조
디렉토리 트리는 **system_structure.md** 참조 (의식·실행·평가 에이전트의 시스템 프롬프트에 자동 주입되는 정전 문서).

## 핵심 컴포넌트

### 통합 AI 아키텍처 (6-Node + 쉘)
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
│   - 시스템 AI: 6개 노드 전체            │
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
- **6개 노드, 150 액션** (sense 43·self 49·limbs 18·others 18·engines 9·table 13. 2026-08-05 개념중복 압축 163→150[검색 통합 `[sense:search]{source}`·book군·슬라이드 `[self:slide]{op:create}`·영상 `[self:deck]{op:"video"}`·싼 병합 5건] + engines 변환자/emitter를 table 노드로 분리 + 라운드 2 통합 + op 어휘화 + 사용성 재감사 + 어휘 정리 + 메신저/비즈니스 IBL화 + neighbor 통합 + 폰 온디맨드 감각 삼각 + 통화 대수/문서 IR emitter + 국회도서관 국가학술정보 인물/학위논문 + 공개 표면 가족[포털/공개파일/가족신문/게시판/발행/팔로우] + 숙박/개체해소/중고/공급망게이트/아이콘 + **몸 부탁[others:ask]** + **USB 손발[self:limb·limbs:guestpc]** + **신문 발행 결정화[engines:newspaper]** + **내 음악[self:music]** + **웹앱 등기부[self:webapp]** 후)
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
- 인프라 노드(`self`, `others`, `table`)는 모든 에이전트에 자동 허용 — 노드 yaml의 `always_on: true` 플래그가 단일 소스 (`ibl_access._always_allowed()`가 레지스트리에서 읽음)
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
정보성 액션의 출력을 경량 AI로 압축하여 컨텍스트 폭발을 방지. `data/ibl_nodes_src/<node>.yaml`의 `postprocess` 블록으로 액션별 선언. 적용 액션: `search_ddg`, `crawl`, `search_gnews`, `travel`. 실측 65-70% 압축.
설정 형식과 디테일은 **technical.md** 참조. 구현: `ibl_engine.py`의 `_postprocess()`.

### 연상기억 (해마 + 심층메모리)
fine-tuned 임베딩(768d)으로 과거 IBL 사례(해마)와 사용자 사실(심층메모리)을 단계 0에서 1회 검색해 모든 에이전트에 self-describing XML로 주입.
- 해마: 2026-08-04 로컬 맥미니 M4 Pro 재학습, code Top-5 92.2%/desc 94.2%/런타임 ~99% — 자동 경험 증류 (점수 < 0.7 시)
- 심층메모리: 같은 모델 공유로 시맨틱 검색 (2026-05-16 도입)
- 상세 (단계별 흐름·증류 조건·DB 스키마·학습 절차): **memory.md**

### 도구 패키지 시스템 (노드 구현체)
42개 패키지가 IBL 노드의 실제 구현체로 동작. 폴더 기반 탐지 + 동적 로딩. op 분기 26개 패키지가 `_OP_DISPATCHERS` 표준 채택(2026-05-28~) — `build_ibl_nodes.py --check`가 AST 정확 비교로 src↔tool.json↔handler 일치 검증. 패키지 구조·설치·생성 절차는 **packages.md** 참조.

### 자동응답 서비스 V3
- Tool Use 기반 단일 AI 호출로 판단/검색/발송 통합
- `search_business_items`, `no_response_needed`, `send_response` 도구
- 응답 즉시 발송 (polling 대기 없음)
→ 상세 문서: [communication.md](communication.md)

### 다중채팅방 시스템
- 독립 창에서 여러 프로젝트의 에이전트를 소환하여 그룹 대화 수행

### 의식·평가 에이전트
인지 파이프라인의 전체 흐름과 단계별 디테일은 위 "인지 파이프라인" 섹션과 `memory.md` 참조.

- **의식 에이전트 (본격 AI)** — `backend/consciousness_agent.py`
  - 직접 문제를 풀지 않고 "지금 어떤 문제를 풀어야 하는가"를 자기 한계 인식 기반으로 정의
  - 핵심 철학: 문제는 **나의 한계** × **환경의 제약**이 만나는 곳에서 생긴다
  - 출력: task_framing, achievement_criteria, history_summary, capability_focus, guide_files, self_awareness, world_state
  - 프롬프트: `data/common_prompts/consciousness_prompt.md`
  - 베이스 프롬프트(base_prompt_v6.md)의 "네 한계를 알아라" 원칙과 양방향 일관
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

### 공유창고 (몸의 공개 얼굴, 2026-07-18~21)

공개 표면(포털·공개파일·가족신문·게시판)이 *만드는 목적지*라면, 창고는 **노드 자신이 주소를 갖는 것**이다.

- **발행 = 폴더에 파일 놓기**: `공유창고/0..4/` 가 노드의 맨 주소에서 그대로 서빙된다. 색인도 변환도 없고 파일시스템이 진실 — 바이트를 그대로 내주고(schema-on-read) 해석은 읽는 쪽 AI 몫.
- **레벨이 문**: 방문자 등급(0~4) = 이웃 CRM 등급과 **같은 자**. 보는 사람은 `0..자기 레벨`을 한 장의 평평한 목록으로 보고(같은 이름은 높은 레벨이 이김), 위 레벨 파일은 403 아닌 **404**(존재 자체가 정보). 유일한 의도적 누출은 `has_restricted` 한 비트(냄새).
- **기계 얼굴**: `GET /manifest`(제목·파일·크기·mtime·URL·`about`·`login` 블록) + `GET /f?path=` + 쿠키 로그인. **이게 계약의 전부** — IBL도 인지 파이프라인도 계약에 없다.
- **읽는 쪽(이웃 피드)**: `warehouse_feed.py` 폴러가 등록된 이웃 창고의 매니페스트를 30분마다 가져와 경로·mtime diff → `seed`/`new`/`changed` 타임라인. **AI·토큰 0의 순수 기계층**. 보존 스냅샷은 곧 동네 전체 파일명 색인(검색). 이웃이 indiebizOS 가 아니어도 된다 — `warehouse_adapters.py` 가 nginx/Apache 색인·RSS/Atom(HTML 자동발견)·Nextcloud 공개공유·일반 웹페이지를 같은 통화로 정규화(콜드 스타트 우회).
- **창고 주소 = 연락 방법**: 이웃의 `contacts`에 `contact_type='warehouse'` 행으로 저장(이메일·Nostr 키 옆). 리트윗은 내 창고에 떨어뜨린 `.url` 포인터 파일 — 구독자 클릭이 원본 창고로 직행(FOAF 발견이 프로토콜 아니라 파일).
- **둘러보기(2026-07-29)**: 어댑터가 생긴 뒤로 세상엔 이미 창고가 많은데 볼 방법이 없었다 → 이웃찾기가 두 갈래 — *소개글*(나를 알린 사람이 오는 수신면)과 *둘러보기*(`warehouse_directory.py`: Neocities 태그 브라우즈를 요청 1회로 파싱 + 사용자가 고칠 수 있는 시드 목록). 이웃 카드의 📣 **공개 추천**은 기계가 사실만 채운 초안을 사용자가 고쳐 발행하고(공개 발행이라 2단 확인), 본문이 `공유창고 Warehouse : <url>` 계약을 지켜 받는 쪽 이웃찾기에 '＋ 등록' 버튼이 그 자리에 붙는다. 방언에 **neocities** 어댑터가 합류(프로필의 update 이벤트=변화 피드, 루트 링크=파일 목록. 커스텀 도메인은 `api/info` 대조로만 채택 — 남의 사이트를 잘못 물지 않게).
- **AI 가 채우는 진열**: 비즈니스 아이템(나눔·판매·가능)이 창고 폴더로 물질화될 때 사람이 여는 표지 한 장(`<비즈니스> 카탈로그.html`, `warehouse_catalog.py`)이 함께 발행된다 — 사진을 data URI 로 실은 **자족 문서**(받아가서 열어도 그대로 산다)에 연락처 꼬리는 비즈니스 문서와 같은 소스(`api_portal._contact_pairs`). 매 공개 요청마다 도는 자리라 **지문 게이트**(첫 줄 `<!-- catalog:<sha1> -->`)로 내용이 같으면 재생성 0 — 괜히 다시 쓰면 mtime 이 흔들려 이웃 폴러가 `changed` 로 오독한다.
- **자격·평가 두 축**: 상대가 준 접근 **레벨**(가입/로그인 자격을 폴러가 그대로 사용, 만료 시 자가치유·실패 시 익명 폴백)과 내가 매기는 **창고 점수 0~3**(피드·검색 필터)은 독립.
- **주소는 파생**: 몸의 공개 주소는 흩어진 설정이 아니라 창고가 실제로 서빙하는 얼굴에서 파생(`origin_host()`, 권위=`public_face.provider`). Cloudflare 발급이 터널·Worker·R2 캐시까지 만들고(`cdn_provision.py`), 인증 게이트는 fail-closed(미등록 호스트=외부 취급, 프록시 신호를 `Host`보다 먼저).
→ 상세: [communication.md](communication.md)

### 몸 사이 소통 — 명함과 부탁 (2026-07-22)

여러 몸(맥·폰·낯선 PC)이 서로를 부리는 방식을, **공유 사전 RPC**(내 어휘로 남의 몸을 원격 호출)에서 **명함 + 자연어 부탁**으로 바꿨다.

- **명함** `GET /nodes/card` — 레지스트리에서 파생한 desc-프로젝션(표준 코어 제외·params 미포함·몸 인식 필터). 등록 시 상호 자동 교환·캐시(`peer_cards.py`), 프롬프트 냄새 ~70토큰/몸.
- **부탁** `POST /nodes/ask` (어휘 `[others:ask]`) — 받는 몸이 **자기 사전으로** 컴파일→실행→통화로 회신(1회 자가교정, 어휘 밖이면 정직한 거절). 컴파일러 능력 축은 *해마 유무*(용례 있으면 조종실 경로, 없으면 사전-동봉 경량 모델).
- **사전 물리 분리**: 배포물=전체 사전집, 설치=자기 어휘만(로더 필터 + 폰 번들 물리 필터). 카탈로그·해마 회상이 **소유-필터**를 지나 "남의 어휘를 학습하지 않는다".
- **신뢰 = 이웃 등급**(`body_trust.py`): 특별함은 배관이 아니라 레벨. 낯선 몸의 부탁은 거절되고, 폰-맥도 "최고 레벨 이웃"일 뿐이다 — **몸 사이 특권 배관을 두지 않는다**가 설계 원칙.
- **표면 분리**: 원격 런처(=PC의 일부, 5탭)와 폰 네이티브(=독립 시스템, 3탭)를 조립 모듈로 가름(`launcher_surface_remote/phone.py`). 폰 조종실은 로컬 완결(translate/validate/distill/catalog).

### USB 손발 (게스트 PC 헬퍼, 2026-07-23)

낯선 PC 에 USB 로 꽂아 셸·파일 작업을 시키는 **얇은 몸**. 두뇌·신원은 허브에 남고 USB 엔 limb key 하나(맥 비밀번호가 아니다).
- 어휘 2: `[self:limb]{op: issue/list/revoke}`(발급=USB 페이로드 생성) + `[limbs:guestpc]{op: shell/read/write/list/info}`(허브에서 하달).
- 연결=헬퍼(Go 단일파일)가 그 PC 에서 허브로 **아웃바운드** 접속 → 폰 푸시 큐(`phone_jobs`)를 재사용해 셸 봉투를 당겨가 실행·회신. 그 PC 방화벽 설정 불필요.
- 눈 없음(셸·파일만). 발급은 이름 명시가 원칙이고(오배송 방어), 폐기(revoke)는 그 키만 죽인다.

### 웹앱 등기부 (몸이 낳은 웹앱들, 2026-08-01)

이 시스템은 공개면·계기·외부 배포로 웹앱을 계속 낳는데, 정작 그것들의 목록을 갖고 있지 않았다. `[self:webapp]{op: list/status/register/remove}`(system_essentials, `webapp_registry.py`)가 그 등기부다.

- **파생 우선**(수동 원장은 드리프트한다): 진실 소스 7곳 — 포털(`portal_state`)·게시판·가족신문·공개파일 바스켓·정기보고 발행면·web-builder `sites.json`·`outputs/web-projects/*/wrangler.toml`(야생 Worker) — 에서 **매 호출 재계산** + 고정 2면(런처·NAS PWA). 파생 밖 예외만 `data/webapps.json` 에 수동 보충.
- `status`=전 함대 **병렬 HTTP 생존 실측**(🟢/🔴·응답코드·지연). 🕸️ 계기 3탭(함대/생존/등록)이라 전 표면에 자동 등장.
- 판단 기준은 가이드 `webapp.md`: 웹앱 4부류 결정 트리(몸 공개면 / 포털 계기 대여 / 외부 서버리스 / 자족 단일 HTML)·몸 공개면 5조각 레시피·PWA 함정(★같은 origin 다중 PWA 는 알림 권한이 한쪽 WebAPK 로 위임된다 — 알림 권한은 앱이 아니라 **origin 단위**).

### 알림 도달 경로 (2026-07-28)

수신한 메시지(Nostr/Gmail)가 DB 에 저장만 되고 사용자에게 닿는 경로가 0이던 것을 봉합. 수신 단일 관문(`channel_poller._save_message_to_db`) 직후 `notify_dispatch.notify_user()` 하나로 모인다 — ①알림함 기록 ②**A: 런처 연결 시** WebSocket `show_notification` → Electron OS 네이티브 알림+배지+클릭=메신저 창 ③**B: 미연결 폴백** `desktop_notify.py`(의존성 0 — osascript / PowerShell WinRT 토스트 / notify-send). win·linux 트레이 상주로 창을 다 닫아도 수신·알림이 계속된다.
★**경로 C(웹 푸시)는 은퇴**: RFC 8291 구현까지 마쳤으나 실기기 도달 실패 — 같은 origin 의 PWA 둘 중 하나에만 알림 권한이 위임되는 안드로이드 동작이 진범이었다. 재활 조건(런처 서브도메인 분리로 origin 독점)만 주석에 남기고 코드는 전부 제거했다.

### 원격 접근 시스템
Cloudflare Tunnel을 통해 외부에서 IndieBiz OS를 제어합니다:

- **원격 Finder** (`api_nas.py`): 파일 탐색, 동영상 스트리밍, 다운로드 — 개인 NAS처럼 활용. 홈 화면 설치 시 별도 앱(**IBFind**).
- **원격 런처** (`api_launcher_web.py` + `launcher_surface_remote.py`): 자율주행·조종실·앱·공유창고·포식 5탭 — 브라우저면 어디서나 같은 표면. 웹앱 매니페스트로 홈 화면 설치 가능(서비스워커는 캐시하지 않음 = 항상 라이브).
- **표면이 곧 착지점**: 결과가 어디로 떨어지는지는 *어느 표면이 물었나*로 정해진다(폰 브라우저에서 누른 재생은 폰에서 난다). ★클립보드 수신면(clipbox)은 2026-07-28 철회 — '폰으로'는 종전 푸시 큐를 그대로 쓴다.
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

## 프로젝트 & 에이전트 (데스크탑 3오브젝트)

바탕화면 공간에 세 종류의 오브젝트를 배치한다 (구 overview.md 흡수):
- **프로젝트(Project)**: AI 에이전트들의 팀. 역할별 에이전트를 담고, 통째로 복사·템플릿화 가능. 대화DB·에이전트·심층메모리가 프로젝트별로 물리 격리(공간에 맥락 경계 위탁). 모델·API 키는 에이전트별이 아니라 시스템 전체 모델 기어가 결정.
- **스위치(Switch)**: 자연어 명령을 저장해 한 번의 클릭으로 실행하는 자동화 오브젝트.
- **폴더(Folder)**: 프로젝트·스위치를 정리하는 컨테이너(중첩 가능).

에이전트 유형:
- **외부 에이전트(External)**: Nostr/Gmail/Telegram 채널을 가져 원격에서 명령을 받고 IndieNet으로 타 노드와 소통.
- **내부 에이전트(Internal)**: 채널 없이 OS 내부에서만 동작(프로젝트 내 협업·보안 작업).

동작·접근:
- 프로젝트 단위로 독립된 작업 공간. 각 프로젝트에 역할별 에이전트 배치
- 에이전트 간 위임: 단일/순차/병렬 (`[others:delegate]{scope: "cross"}`) — 상세: communication.md
- 시스템 AI: 전체 노드 접근, 프로젝트 에이전트에 위임 가능
- 프로젝트 에이전트: 허용된 노드만 접근 (allowed_nodes)

## 외부 연동

- **통신**: Gmail, Nostr (DM은 NIP-17 gift-wrap, 구 NIP-04 호환 수신), Telegram
- **NAS**: 음악 스트리밍, 자막 관리, 웹앱 호스팅
- **안드로이드 (양방향)**: 제어=ADB 기반 `[limbs:android]{op}` (snapshot→요소 탭) / 감각=폰 컴패니언 앱(NotificationListener)이 알림·위치·걸음을 NIP-17 한방향 피드로 전송 → `[sense:phone]{op}` + `/phone/*` API.
- **폰 네이티브 (두 번째 독립 자아)**: phone-companion/ (Kotlin+Chaquopy) 네이티브 앱이 **폰에서 온디바이스 Python 백엔드**를 띄워 앱모드 슈퍼앱을 서빙하고 **실제 IBL 엔진**이 폰 안전 패키지(`build_ibl_nodes.PHONE_VERIFIED_PACKAGES`)를 로컬 실행한다. **두뇌도 폰-로컬**: 빌린 맥 두뇌(claude_code 원격 렌트)에서 **폰 인-프로세스 Gemini**(경량 3.1-flash-lite / 본격 3.5-flash)로 전환 — 빌린 두뇌는 자기 몸(맥)을 데려오지만 Gemini API는 폰서 직접 호출하므로, away-case 역방향 장치(WS/remote_turn)를 통째 은퇴하고 outbound(/embed·_forward_to_mac)만 유지. 모델은 `runtime_utils.detect_body()`로 **자기 하드웨어를 감지**(맥=sysctl 칩명, 폰=Build jclass)해 자신을 맥 아닌 "폰"으로 인식 → 두 HW = 두 정체성(정체성은 하네스=프롬프트+기억에 있지 모델 위치 무관). 빌드가 정본 트리(엔진+패키지+`ibl_nodes.yaml`)+하네스(prompt_builder/agent)를 `indiebiz_base.zip` 에셋으로 번들→filesDir 추출(BaseBundle은 APK 업그레이드 때만 wipe). `runs_on` 능력 태그(`anywhere`/`pc_only`/`phone_only`)와 `data/phone_manifest.json`이 폰 못 도는 계기/액션을 숨기거나 허브(데스크톱)에 단건 위임. 온디맨드 감각=`sense:here`(위치)·`sense:listen`(마이크)·`sense:see`(카메라)·`sense:phone`(알림), 조작=네이티브 AccessibilityService(`limbs:android`, USB 불필요). 폰서 Python 인-프로세스 실행(`execute_python`)도 가능 — 기기 프로그래밍 에이전트. 라디오는 stream URL을 WebView(hls.js)로 돌려 **폰 스피커** 재생. **기억 두 부류**: 사용자 세계-데이터(연락처·비즈니스·일정·의료기록)=공유·CRDT 동기화 / 각 자아의 주관적 기억(대화·해마·자기상태)=자아별 사적·비동기화. 폰=리모컨 아닌 두 번째 독립 자아.
- **원격**: Cloudflare Tunnel (Finder + 런처). 원격 런처=집 PC 리모컨 의미론(라디오 재생은 집 PC 스피커).
- **브라우저**: Playwright 기반 자동화

## 표준 코어 vs 사용자 경계 (설치·업데이트 이음매)

IndieBiz OS는 **표준 코어**(IBL 문법 + 기능어 노드 + 백엔드/프론트 엔진 + 도구 패키지·앱 카탈로그)를 배포하지만, 설치되는 순간 *사용자의 인스턴스*가 된다 — 사용자는 어휘를 더하고, 앱을 설치·저술하고, 대화·설정을 쌓는다. 이 둘의 경계는 **단일 진실** `data/core_manifest.json` 하나로 그어진다(`scripts/build_core_manifest.py`가 **git 추적 집합**=배포에 딸려오는 것에서 파생, 손목록 없음). 원래 이 경계는 `.gitignore`·electron-builder 필터·업데이트 heuristic 셋에서 제각각 인코딩돼 서로 어긋났는데(어휘가 stale 보존되는 등), 이 매니페스트로 접어 네 곳이 한 진실을 향하게 했다.

두 불변식:

- **설치가 다 깔지 않는다.** 많은 패키지가 자기 API 키를 요구해, 다 활성화하면 못 쓰는 것에 파묻힌다. 전체 카탈로그는 배포되되(`not_installed/`에 대기) **큐레이션된 소수만 기본 활성**. 각 패키지는 `origin`(core/user)을 갖고, 설치 파일 패키징(`build_dist_filter.py`)이 매니페스트 주도라 사용자의 커밋한 개인 앱·파일은 배포로 새지 않는다. 개인 패키지를 커밋해도 코어에서 빼려면 opt-out(`.origin`=`user`).
- **업데이트가 사용자 것을 안 덮는다.** 재설치·업데이트는 코어 소유 파일만 갱신한다(`main.js` `initUserData`). 사용자의 **설치 상태**(어떤 패키지를 켜고/껐는지=폴더 배치), 저술한 어휘·앱, 설정, 대화 이력은 그대로 살아남는다 — 업데이터가 번들 기본 배치를 다시 강요하지 않고 사용자가 고른 폴더 위치를 존중(`syncPackagesPreservingState`). 코어 어휘 산출물만 매니페스트 기준 강제 갱신.

헌법적으로 이건 하부/상부 이음매(substrate/superstructure)와 표준-코어(기능어 self/others/table=표준 vs 내용어=사전) 원칙을 **패키지·앱·설치·업데이트 층까지 밀어낸 것**이다. 상세: technical.md '설정 파일 위치'.

## 이음매 시민권 (커밋·부팅 게이트, 2026-07-25~26)

액션(어휘)은 `--check` 삼각 검증이라는 시민권을 오래 가졌지만, **액션이 아닌 것**(이음매 = 인증 게이트·이벤트 루프 규율·공개 라우트·파생물·부팅)은 주석과 관습으로만 지켜졌다. 같은 부류의 검사를 이음매에도 준다 — 전부 AST/실측 기반, 의존성 0, pre-commit + CI(`.github/workflows/`).

- **인증 게이트 fail-closed**: `remote_access_guard` 가 블록 전체를 `except: pass` 로 감싸 "보수적"이라 불렀지만 실제로는 fail-open 이었다(판정자 `is_external_request` 는 "로컬임이 증명될 때만 로컬"인데 래퍼 한 줄이 그 규율을 무효화). 판정 불능 → **503**(조용히 열리는 대신 시끄럽게 멈춘다), 인증 실패 → 401.
- **공개 노출 ↔ 인증 대조 가드**(`check_public_routes.py`): "자체 시크릿 게이트 보유"라는 주석을 검사로 승격. 오라클은 코드가 아니라 **살아있는 라우트 테이블**(실제 `app.routes` 를 훑고 실제 `is_public_remote_path` 에 묻는다 — 등록 목록을 재파싱하면 그 파서가 또 드리프트한다). 헬퍼 안에서 검사하는 간접 호출까지 추적하고, **공허한 통과를 금지**(거짓 초록은 붉은 것보다 나쁘다).
- **이벤트 루프 규율 가드**(`check_event_loop.py`): async 본문의 동기 블로킹 호출은 단일 프로세스 백엔드를 세우고, 이 서버는 자기 자신을 부르는 경로가 잦아(창고 폴러→공개 얼굴→터널→자기) 자기교착이 된다 — 같은 부류가 세 번 재발했다. ★정확도가 전부라 중첩 sync 함수·람다·클래스 메서드를 허용 규칙으로 두고 **음성 픽스처를 미탐 픽스처보다 중히** 본다(오탐 한 번이면 가드가 꺼지고 미탐도 같이 사라진다).
- **신선 clone 게이트**: main 이 개발 기계에서만 통과하고 clone 에서는 `--check` 실패였다(원인 둘 다 *커밋되지 않은 로컬 상태*) → 커밋된 것만 보는 눈을 CI 에 붙이고, 파생물 3종을 추적으로 돌리고, 파생 결정성(auth 레지스트리를 import 아닌 AST 로)까지 고쳤다.
- **부팅 관측**(`boot_status.py`): lifespan 의 `except: print(...실패 무시)` 블록 10개를 성패 양쪽 계측(제어 흐름 무변경). `/world-pulse/health` 가 `boot` 절을 함께 내보내고 부팅 실패가 하나라도 있으면 overall 을 degraded 로 올린다 — 사흘 뒤 "왜 스케줄이 안 도나"의 답이 터미널 스크롤 저편에 있지 않게.
- **윈도우 이식성 게이트**(`check_win_portability.py`): 유닉스 전용 stdlib 의 무가드 톱레벨 import 탐지. ★위험지대는 규율 잡힌 `backend/` 가 아니라 **데이터 취급되는 실행 코드** `data/packages/`.

## 시스템 통계

- 활성 프로젝트: 24개 (시스템 프로젝트 수동모드·앱모드 포함), 에이전트 33개
- 도구 패키지: 40개 (+ 백엔드 extensions 8개), IBL: 6노드 150 액션 (sense 43·self 49·limbs 18·others 18·engines 9·table 13. 2026-08-05 개념중복 압축 163→150 + op 어휘화 + 안드로이드 통합 + 메신저/비즈니스 IBL화 + 통화 대수 table 노드 분리 + 폰 온디맨드 감각 삼각 + 국회도서관 국가학술정보 + 공개 표면 가족[포털/공개파일/가족신문/게시판] + 숙박/개체해소/중고/공급망게이트/아이콘 + 몸 부탁/USB 손발/신문 발행/내 음악/웹앱 등기부)
- backend 198 파일 (api_*.py 38개), 가이드 61개(data/guides/ 파일은 68 — 자동생성·미등재분 포함)
- op 분기 액션 67개 — 핸들러 구현은 전부 `_OP_DISPATCHERS` 표준(26개 패키지, 12개는 패키지 밖 backend-native), `--check` 가 src↔tool.json↔handler 를 AST 정확 비교. 부작용 여부는 통화(`returns`)에서 분리된 `side_effect:` 선언(true 37·false 16)
- 해마 코퍼스 2,988 용례 (2026-08-04 로컬 재학습 반영 — epoch 5·검증 0.882)

## 참조

- IBL 명세: `system_docs/ibl.md`
- 실행기억 & 해마: `system_docs/memory.md`
- 패키지 가이드: `system_docs/packages.md`
- 설계 철학 (백서): `WHITEPAPER.md`

---
*마지막 업데이트: 2026-08-06 — 수치 정합화: 6노드 **150 액션**(sense 43·self 49·limbs 18·others 18·engines 9·table 13)·**40 도구 패키지**(2026-08-05 개념중복 압축 163→150 반영 — 에피소드 935 가 자기 액션 수를 낡게 말한 것의 수리). 본문 불변. 이전(2026-08-04) — 현 상태 정합화: backend 197→**198 파일**·가이드 58→**61**(hippocampus_retraining 신설 포함)·op 분기 68→**67 액션/26 패키지**(location-services 는 유일 op 액션 `sense:travel` 은퇴로 목록에서 빠짐)·해마 코퍼스 **2,988**(2026-08-04 로컬 재학습 반영). 액션 수 163 불변 — 이 기간 변경은 어휘 *추가*가 아니라 `[sense:search_shopping]` 의 중고 축(site=used/all) *은퇴*였다. 이전 — **낳은 것을 세고, 받은 것을 알리고, 이음매에 시민권을 주다**: ①**웹앱 등기부 `[self:webapp]`**(2026-08-01, 162→**163 액션**) — 이 시스템이 계속 낳는 웹앱들의 목록이 없던 것을 **파생 우선 등기부**로(진실 소스 7곳 매 호출 재계산 + `status`=전 함대 병렬 생존 실측). 가이드 `webapp.md` 가 4부류 결정 트리와 PWA 함정(★알림 권한은 앱이 아니라 **origin 단위**)을 붙든다. ②**알림 도달 경로 A+B**(2026-07-28): 수신이 DB 에 저장만 되고 사용자에게 닿지 않던 것을 `notify_dispatch` 단일 관문으로(런처 연결 시 OS 네이티브 알림+배지, 미연결이면 의존성 0 데스크탑 폴백, win·linux 트레이 상주). 경로 C(웹 푸시)는 구현 후 실기기 불발로 **은퇴**(재활 조건만 주석에 기록). ③**이음매 시민권**(2026-07-25~26, 위 절): 인증 게이트 fail-closed·공개 노출↔인증 대조·이벤트 루프 규율·신선 clone·부팅 관측 — 액션만 갖던 검사 시민권을 이음매로 확장. 부수로 uvicorn 리로드가 새 터널을 죽여 공개 얼굴이 이틀간 1033 이던 것을 **소유권 있는 종료 정리**로 봉합. ④**창고가 바깥을 보다**(2026-07-29): 이웃찾기 두 갈래(소개글/둘러보기)+📣 공개 추천, neocities 어댑터로 169만 개인 홈페이지 편입, 비즈니스 아이템이 **자족 카탈로그**로 창고에 자동 진열(지문 게이트). ⑤**축의 분리 두 건**: 부작용을 통화(`returns`)에서 뽑아 `side_effect:` 선언으로(조종실 dry-run 이 삭제를 '부작용 없음'으로 통과시키던 것), 목록을 내면서 `effect` 를 선언해 파이프가 끊겨 있던 액션 부류 종결. **현 상태: 6노드 163 액션**(sense 48·self 52·limbs 18·others 18·engines 14·table 13), 도구 패키지 42개 + extensions 8개. 이전(2026-07-25) — **몸이 주소를 갖고, 몸끼리 말을 트다**: ①**공유창고**(2026-07-18~21, 위 "공유창고" 절): 발행=폴더에 파일 놓기, 레벨 0~4=이웃 CRM과 같은 자(위 레벨은 404), 기계 얼굴 `/manifest`, 이웃 창고 폴러(30분 diff·AI 0)와 **방언 어댑터**(nginx 색인·RSS/Atom·Nextcloud·일반 웹페이지)로 "설치 안 한 이웃"까지 편입, 리트윗=`.url` 파일, 창고 주소=이웃의 contact_type, 창고 점수 0~3(접근 레벨과 독립인 내 평가 축). 몸의 공개 주소는 **파생**(`origin_host`, 권위=public_face.provider)이고 CF 발급이 터널·Worker·R2 캐시까지 만든다. 인증 게이트 fail-closed. ②**몸 사이 소통 = 명함+부탁**(2026-07-22): `GET /nodes/card` + `POST /nodes/ask`(`[others:ask]`) — 공유 사전 RPC 은퇴, 사전 물리 분리(설치=자기 어휘만·해마 소유-필터), 신뢰=이웃 등급(`body_trust`), **몸 사이 특권 배관 없음**. 표면 분리(원격 런처 5탭=PC의 일부 / 폰 네이티브 3탭=독립 시스템), 클립보드는 원격 런처 clipbox 로 재배치. ③**USB 손발**(2026-07-23): `[self:limb]`·`[limbs:guestpc]` + Go 헬퍼(아웃바운드·푸시 큐 재사용). `runs_on mac_only`→**`pc_only`** 전역 개명(맥 중심 이름 제거). ④신문 발행 결정화(`[engines:newspaper]`)·에피소드 로깅 전 경로(HTTP·위임·외부채널)·손발 프레즌스 상시 주입. ⑤**내 음악 라이브러리**(`[self:music]`)+관련곡 그래프(가중 간선·랜덤 산책·🕸️ 그래프 계기), **공개 파일 동영상 생방송 재생**(스트리밍 트랜스코드·자막·오프셋 시크). 당시: 6노드 162 액션(sense 48·self 51·limbs 18·others 18·engines 14·table 13), 도구 패키지 42개 + extensions 8개. 이전(2026-07-17) — **공개 표면 가족(커뮤니티당 노드 하나) + table 노드 분리 정합화**: `others` 노드에 공개 웹 표면이 자라 남이 브라우저로 닿는 표면 완성 — `[others:portal]`(개인 포털 `/h/<주소>/`, 다중 포털·아이디/비번 또는 열쇠 로그인·회원=이웃 CRM 레벨 0~4·오디오 프록시)·`[others:showcase]`(공개 파일 `/s/`)·`[others:family_news]`(가족신문 `/n/`)·`[others:bulletin]`(로그인 없는 게시판 `/b/`)·`[others:publish]`(관점 발행)·`[others:follow]`(팔로우 피드) + 정기보고 발행 면(`/r/`, 어휘 없음). 그 외 신규: `[sense:stay]`(숙박/한달살기 3소스)·`[sense:entity]`(Wikidata 개체 해소)·`[sense:used]`(중고)·`[self:install_lib]`(공급망 승인 게이트)·`[engines:icon]`(폰-로컬 아이콘)·크롤 에스컬레이션 사다리. **table 노드 분리**(2026-06-30): engines 변환자/emitter 13종을 신규 `table` 노드로 이관(engines=순수 미디어 생성). **현 상태: 6노드 157 액션**(sense 48·self 49·limbs 17·others 17·engines 13·table 13), 도구 패키지 40개. 이전(2026-06-30) — 모델 기어(계기판 변속) + per-agent 모델 폐지: 모델 선택 ~15곳을 단일 리졸버(`model_resolver.py`, 역할→축→기어→티어)로 통합. 계기판 레버(절약/균형/최대) + 프리셋 편집기 + 에이전트 핀, 전부 핫리로드(`/model-gear` REST). per-agent 모델 설정 폐지(에이전트 yaml의 provider/model/apiKey 무시, 모델·키는 실행 티어 상속). 폰 엔진 번들=`data/bodies/*.json` 프로파일에서 파생(`build_body_bundle.py`, 3겹 게이트). 142 액션 불변·38 도구 패키지. 이전(2026-06-29) — 앱 인터랙티브 렌더 프리미티브 종결: 인터랙티브 `map`(leaflet) + `on:` 뷰-이벤트(moveend 재조회·marker_click IBL 액션 또는 `{stream:true}` HLS 영상) + 결과-필드 동적 필터 `filter:{from_field}`(클라이언트 측 거르기). bespoke CommercialInstrument 은퇴(선언형 흡수)·directions 은퇴 보류·lightbox 불요. 버그수정: 원격 동적필터+카드드릴 인덱스(applyCatFilter 후 인덱싱)·tsc 베이스라인 에러 3개. 단일통화(items) records producer=0 종합확인. 142 액션 불변(렌더링 레이어 변경)·38 도구 패키지. 이전(2026-06-27) — 앱 표면 품질 일괄 개선(라디오 즐겨찾기·CCTV 인앱 재생 stream 버튼·여행 날짜+한국 지방공항·투자 TIGER200·날씨 오송·문화 지역·길찾기 거리/예상시간) + 부동산 직방 호가(sense:realty source:zigbang)·AI 공모/창업(sense:contest/startup) + read_guide claude_code 노출 + 폰 네이티브 재빌드. 142 액션(sense 44·self 44·limbs 17·others 11·engines 26)·38 도구 패키지. 이전(2026-06-22) — 국회도서관 국가학술정보 API 흡수: `sense:researcher`(연구자 동명이인 분리)·`sense:paper source:nanet`(학위논문) 신설 → 인물·학위논문 찾기. 5노드 142 액션(sense 44, self 44, limbs 17, others 11, engines 26)·도구 패키지 38개. 기억 7종(2026-06-20 포식 기억 forager가 7번째로 추가 — 디스크/코드/웹 공간을 뒤져 배운 것을 세션 너머로 누적). 이전(2026-06-15) — 통화 대수(engines 변환자 9: filter/sort/take/select/dedup/groupby/join/union/merge + 파이프 문법 `|` + 문서 IR emitter) → 122~124에서 136 액션. 이전(2026-06-14) — **폰이 두 번째 독립 자아로**: 폰 두뇌를 claude_code 원격 렌트 → 폰-로컬 in-process Gemini(경량 3.1-flash-lite/본격 3.5-flash)로 전환(away-case 역방향 장치 은퇴, outbound만 유지) + `detect_body()` 하드웨어 자기감지(자신을 맥 아닌 "폰"으로 인식, 두 HW=두 정체성) + 상주 스케줄러(self:trigger/schedule 폰 바인딩) + runs_on 정직성(validate_phone_reachability self-check 합류) + 사용자 세계-데이터 CRDT 동기화(비즈니스·의료기록, 단 주관적 기억은 자아별 사적) + 의료 에이전트 환자차트 자동주입(읽기 조회 0번) + channel 트리거 맥 발화 경로. 폰 온디맨드 감각 삼각(sense:here/listen/see) + self:show_calendar 폐지(해마 게이트 capability化) → 125→124 액션. 이전(2026-06-12): 메신저/커뮤니티/비즈니스 IBL 앱모드 계기화(옛 BusinessManager·NeighborManager·IndieNet 창 은퇴, api_indienet REST 제거) + 자동응답 IBL화 + NIP-17 멀티릴레이 실시간 수신 + 폰↔PC business.db 합집합 동기화(LWW+tombstone CRDT, self:phone_sync) + neighbor 통합 + 해마 로컬 재학습(M4 Pro) → 122 액션. 이전(2026-06-11): 폰 네이티브 정착(Chaquopy 온디바이스 백엔드 + 실제 IBL 엔진 + runs_on + phone_manifest) + 앱 표면 선언 단일소스화 + 라디오 스트림 URL 수정. 이전(2026-06-10): 인지 경로 개편: 중급 모델을 Reflex 전용으로 좁히고 무의식 EXECUTE는 본격 모델 유지(오분류 품질 방어) + 무의식 분류기 재조정(THINK 과잉 축소) + 의식 프롬프트에 "좋은 문제 규정"(메타-메타)·"IBL과 코딩의 우선순위" 섹션. 이전(2026-06-05~06): 안드로이드 얇은 부활([limbs:android]{op}) + 폰 컴패니언 앱(NIP-17 한방향 피드 + [sense:phone]) + Nostr DM NIP-17 전환 + 음악 작곡 은퇴 → 111 액션. 이전(2026-06-04): IBL 사용성 재감사 종결 + ACTION_PARAM_ALIASES 중앙 적용. 이전(2026-05-31): THINK 경로 framing 재사용 게이트. 이전(2026-05-28): 라운드 2 정리 + op 어휘 단일화 + 삼각 검증 인프라.*
