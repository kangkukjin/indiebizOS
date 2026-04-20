# IndieBiz OS 아키텍처

## 정의

IndieBiz OS는 AI에게 지능적인 몸을 만들어주는 하네스(harness)다. AI의 본질적 가치는 **연결** — 사람과 세계를, 사람과 사람을, 알고 있는 것과 아직 모르는 것을 잇는 것.

하네스는 에이전틱 루프와 다르다. 에이전틱 루프는 AI의 처리량(throughput)을 올린다 — 도구를 더 많이 호출. 하네스는 AI의 판단력(intelligence)을 올린다 — 같은 모델이라도 하네스에 따라 결과의 질이 달라진다.

## 신체 구조 (생명체 메타포)

| 신체 시스템 | IndieBiz OS 구현 | 역할 |
|------------|------------------|------|
| 신경계 | IBL (5노드, 311액션) | 감각/행동의 상시 연결 |
| 감각기관 전처리 | 감각 전처리 (postprocess) | 원시 정보를 압축하여 뇌에 전달 |
| 선택적 주의력 | 의식 에이전트 | 매 턴 메타 판단 — 문제 정의, 초점, 달성 기준 |
| 반사 신경 | 경량 AI (분류) | EXECUTE/THINK 분류, 단순 요청은 의식 건너뜀 |
| 자기 교정 | 평가 에이전트 | 달성 기준 대비 평가, NOT_ACHIEVED 시 재시도 |
| 자의식/각성 | World Pulse | 매시간 세계/사용자/자기 상태 수집 |
| 면역계 | AI 건강 체크 + action_health | 매 6시간 시스템 AI가 미확인 액션 테스트, 모든 액션 실행을 자동 기록 |
| 자율신경계 | 스케줄러, 이벤트 엔진 | 의식 없이 돌아가는 리듬 |
| 해마 | 실행기억 (해마 + discover) | 1회 생성, 전 에이전트 공유. fine-tuned 임베딩으로 관련 기억 자동 인출 |
| 에피소딕 메모리 | episode_log + episode_summary | 에피소드(명령→응답)별 실행 로그 기록, 인지 품질 지표 영구 추적 |

## 4단 인지 파이프라인

```
사용자 메시지
    ↓
실행기억 생성 (해마 + discover + implementation, 1회)
    ↓
경량 AI ← 실행기억 (EXECUTE/THINK 분류)
    ↓ THINK                         ↓ EXECUTE/Reflex
의식 에이전트 (문제 정의 + 달성 기준)    실행 에이전트 [중급 모델]
    ↓                                    ↓
실행 에이전트 [본격 모델]              결과 반환
    ↓
평가 에이전트 ← 실행기억 (달성 기준 대비 평가, 최대 3라운드)
```

- **실행기억**: 파이프라인 최상단에서 1회 생성, 전 에이전트 공유. 과거 코드 사례(해마) + 추천 도구(discover) + 액션 implementation
- **해마**: IBL 도메인 fine-tuned 임베딩 모델 (Top-5 95.6%, 범용 대비 +49.8%p)
- 상세: `system_docs/execution_memory.md`

## 시스템 구조

```
indiebizOS/
├── backend/              # Python FastAPI 백엔드
│   ├── api.py           # 메인 서버 (포트 8765)
│   ├── api_*.py         # 각 모듈 라우터 (25개)
│   ├── api_nas.py       # 원격 Finder API (파일 접근/스트리밍)
│   ├── *_manager.py     # 비즈니스 로직 매니저
│   ├── ai_agent.py      # AI 에이전트 코어
│   ├── agent_runner.py  # 에이전트 실행기
│   ├── system_ai.py     # 시스템 AI 코어
│   ├── trigger_engine.py # 트리거 엔진 (이벤트/조건 기반 실행)
│   ├── calendar_manager.py # 캘린더 관리 및 스케줄 기반 위임
│   ├── system_ai_memory.py # 시스템 AI 메모리 (SQLite)
│   ├── system_docs.py   # 시스템 문서 관리
│   ├── system_hooks.py  # 시스템 훅
│   ├── node_registry.py # 노드 탐색/등록
│   ├── providers/       # AI 프로바이더 (스트리밍 지원)
│   │   ├── __init__.py  # 패키지 초기화
│   │   ├── base.py      # 프로바이더 베이스 클래스
│   │   ├── anthropic.py # Claude 프로바이더
│   │   ├── openai.py    # GPT 프로바이더
│   │   ├── gemini.py    # Gemini 프로바이더
│   │   └── ollama.py    # Ollama 로컬 LLM
│   └── ...
│
├── frontend/            # Electron + React 프론트엔드
│   ├── electron/        # Electron 메인/프리로드
│   └── src/             # React 소스
│
├── data/                # 런타임 데이터
│   ├── packages/        # 도구 패키지 저장소
│   │   ├── installed/   # 설치된 패키지
│   │   │   ├── tools/      # 도구 패키지 (34개)
│   │   │   └── extensions/ # 백엔드 코어 모듈 (9개)
│   │   └── not_installed/  # 미설치 패키지
│   ├── system_docs/     # 시스템 AI 문서 (장기기억)
│   ├── business.db      # 비즈니스 DB
│   └── multi_chat.db    # 다중채팅방 DB
│
├── projects/            # 사용자 프로젝트 (20개)
│   ├── projects.json    # 프로젝트 목록 및 설정
│   └── {project_id}/    # 개별 프로젝트 폴더
│
└── templates/           # 프로젝트 템플릿
```

## 핵심 컴포넌트

### 통합 AI 아키텍처 (5-Node + 다언어 도구)
시스템 AI와 프로젝트 에이전트가 동일한 코드베이스와 **동일한 도구 구조**를 공유합니다:

```
┌─────────────────────────────────────────────────────┐
│                    AIAgent 클래스                    │
│         (ai_agent.py - 단일 코어)                    │
├─────────────────────────────────────────────────────┤
│  최상위 도구 (9개):                                  │
│  • execute_ibl        — IBL 실행기 (311 액션)        │
│  • execute_python     — Python 코드 실행             │
│  • execute_node       — Node.js 코드 실행            │
│  • run_command        — 셸 명령 실행                  │
│  • todo_write         — 작업 목록 관리                │
│  • ask_user_question  — 사용자 질문                   │
│  • enter_plan_mode    — 계획 모드 진입                │
│  • exit_plan_mode     — 계획 승인 요청                │
│  • read_guide         — 가이드 검색                   │
└─────────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
┌──────────────────┐       ┌──────────────────┐
│    시스템 AI      │       │  프로젝트 에이전트  │
│  (agent_runner)  │       │  (agent_runner)  │
│  _is_system_ai   │       │                  │
├──────────────────┤       ├──────────────────┤
│ 전체 노드 접근    │       │ 허용 노드만 접근   │
└──────────────────┘       └──────────────────┘
          │                           │
          └───────────┬───────────────┘
                      ▼
┌─────────────────────────────────────────────────────┐
│              providers/ (스트리밍 지원)              │
│  anthropic.py | openai.py | gemini.py | ollama.py  │
└─────────────────────────────────────────────────────┘
```

**도구 계층 설계:**
- IBL 실행기(`execute_ibl`)와 범용 언어(Python/Node.js/Shell)가 같은 레벨의 최상위 도구
- 인지 도구(`todo_write`, `ask_user_question`, `enter_plan_mode`, `exit_plan_mode`)는 IBL 경유 불가(파라미터 구조 불일치)하므로 별도 최상위 도구로 제공
- IBL 코드가 실행되기 전에 언어 도구가 디코딩되어야 하므로, 같은 레벨에 배치
- 차이점은 IBL에서 접근 가능한 노드 범위뿐 (시스템 AI: 전체, 프로젝트 에이전트: 허용된 노드)
- 프로바이더 코드 1회 작성으로 시스템 AI + 모든 에이전트 지원

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

### 프롬프트 XML 구조
AI의 정확한 파싱을 위해 모든 프롬프트에 XML 태그 구조 적용:

- **프래그먼트**: `<git_operations>`, `<agent_delegation>` 등
- **히스토리**: `<user_message>`, `<assistant_message>`, `<current_user_request>`
- **자동응답**: `<response_examples>`, `<current_context>`, `<response_instructions>`
- **판단AI**: `<judgment_examples>`, `<current_context>`, `<judgment_instructions>`

### AI 프로바이더 시스템 (스트리밍)
모든 프로바이더가 실시간 스트리밍을 지원합니다:
- `process_message_stream()` - 스트리밍 제너레이터
- 이벤트 타입: `text`, `tool_start`, `tool_result`, `thinking`, `final`, `error`
- WebSocket을 통해 프론트엔드로 실시간 전달

### 위임 체인 시스템 (Delegation Chain) — Phase 27: 3단계 위임
에이전트 간 협업을 위한 핵심 메커니즘. 세 가지 위임 방식을 지원합니다:

**1. 동기/비동기 위임** (기존)
- `[others:delegate]`/`[others:delegate_project]`를 통해 작업을 위임하고 결과를 자동으로 보고받음
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
- **5개 노드, 311 액션** (Phase 25: 노드 재구조화)
  - sense(78), self(75), limbs(96), others(13), engines(46)
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

### 감각 전처리 시스템 (Sensory Preprocessing)
감각기관이 원시 데이터를 전처리해서 뇌에 보내듯, 정보성 액션의 출력을 경량 AI로 압축하여 에이전틱 루프의 컨텍스트 폭발을 방지하는 시스템:

```
액션 실행 → 결과 반환 → postprocess 필드 확인 → 경량 AI(flash-lite)로 압축 → 압축된 결과 반환
```

**YAML 기반 선언적 설정** — 각 액션의 `ibl_actions.yaml`에 `postprocess` 블록을 추가하여 전처리 유형과 파라미터를 지정:

```yaml
search_ddg:
  router: handler
  tool: ddgs_search
  postprocess:
    type: compress           # 전처리 유형
    threshold: 1500          # 이 글자 수 이상일 때만 (기본: 1500)
    prompt: "각 검색 결과를 제목, URL, 핵심 내용 1줄로 압축하라."
```

**설계 원칙:**
- **액션별 커스터마이징**: 각 액션이 자기 특성에 맞는 프롬프트/임계값 지정 (눈과 귀의 전처리가 다른 것처럼)
- **선별 적용**: engines 등 결과를 그대로 보존해야 하는 액션에는 적용하지 않음
- **안전한 폴백**: AI 압축 실패 시 원본 그대로 반환
- **확장 가능**: `type: compress` 외에 `filter`, `structure` 등 새 유형 추가 가능

**적용 액션**: `search_ddg`, `crawl`, `search_news`, `travel`
**실측 효과**: 검색 결과 65-70% 압축, 에이전트 라운드 수 감소, 503 에러 해소
- 구현: `ibl_engine.py`의 `_postprocess()`, `_pp_compress()`
- 경량 AI: `consciousness_agent.lightweight_ai_call()` (경량 AI 프로바이더 재사용)

### IBL 용례 RAG 시스템
에이전트가 IBL 코드를 생성할 때, 과거의 유사한 성공 사례를 참조할 수 있도록 하는 시스템:
- **용례 사전**: ~970개 (합성 데이터 + 실행 로그 자동 승격)
- **하이브리드 검색**: 시맨틱(70%, ko-sroberta 768차원) + BM25(30%, FTS5)
- **프롬프트 주입**: 사용자 메시지 수신 시 유사 용례 3개를 XML로 주입
- **자동 학습**: 성공한 도구 실행 로그가 자동으로 용례로 승격
- 실측 효과: 에이전트 라운드 수 13회 → 3회 (부동산 실거래가 조회 기준)

```
사용자 메시지 ──→ [RAG 검색] ──→ 유사 용례 k개 ──→ AI 프롬프트에 XML 주입
                                       ^
실행 로그 (성공) ──→ [자동 승격] ──────┘
```
→ 상세 문서: [execution_memory.md](execution_memory.md)

### 도구 패키지 시스템 (노드 구현체)
- 폴더 기반 탐지 및 동적 로딩 (34개 설치됨)
- IBL 노드의 실제 구현체로 동작
- **두 가지 실행 경로**: handler.py(복잡한 후처리) 또는 api_engine(API+transform)
- `tool.json` + `handler.py` 구조 (또는 api_registry.yaml 등록)
- 도구 설명 구조: 한줄 요약 + 데이터 형식 + 예시
- 가이드 파일 시스템: 복잡한 도구에 on-demand 가이드 주입 → [상세 문서](packages.md)

### 자동응답 서비스 V3
- Tool Use 기반 단일 AI 호출로 판단/검색/발송 통합
- `search_business_items`, `no_response_needed`, `send_response` 도구
- 응답 즉시 발송 (polling 대기 없음)
→ 상세 문서: [communication.md](communication.md)

### 다중채팅방 시스템
- 독립 창에서 여러 프로젝트의 에이전트를 소환하여 그룹 대화 수행

### 3단 인지 아키텍처 + 3단계 모델 티어 (Phase 28 → Phase 30)
인간의 인지 과정을 모델링한 3단계 처리 파이프라인 + 비용/속도 최적화를 위한 3단계 모델:

**3단계 모델 티어:**
| 레벨 | 설정 | 용도 | 설정 파일 |
|------|------|------|----------|
| 경량 | lightweight_ai | 분류, 평가, 원샷 판단 | `data/lightweight_ai_config.json` |
| 중급 | midtier_ai | EXECUTE/Reflex 경로 실행 | `data/midtier_ai_config.json` |
| 본격 | system_ai | THINK 경로 의식+실행 | `data/system_ai_config.json` |

```
사용자 메시지
    ↓
[경량 AI] → EXECUTE(단순) / THINK(복잡) 분류
    ↓ THINK                          ↓ EXECUTE/Reflex
[의식 에이전트] → 문제 정의 + 달성 기준   [실행 에이전트 — 중급 모델]
    ↓                                     ↓
[실행 에이전트 — 본격 모델]              결과 반환
    ↓
[평가 에이전트 — 경량 AI] → 달성 기준 대비 평가 → NOT_ACHIEVED 시 재실행 (최대 3라운드)
```

#### 경량 AI (분류/평가)
경량 게이트키퍼. 요청을 빠르게 분류하고, 실행 후 달성 기준 평가에도 사용.
- **EXECUTE**: 단순 명령, 인사, 도구 1개로 해결 가능한 작업 → 의식 에이전트 건너뜀, **중급 모델**로 실행
- **THINK**: 분석/비교/전략이 필요한 복잡 작업 → 의식 에이전트 경유, **본격 모델**로 실행
- 파일: `data/common_prompts/unconscious_prompt.md`, `agent_cognitive.AgentCognitiveMixin._classify_request()`
- 프로바이더: `consciousness_agent._get_lightweight_provider()` (싱글턴)
- 시스템 AI와 프로젝트 에이전트 모두 동일한 AgentRunner 인지 파이프라인 사용

#### 중급 모델 전환
EXECUTE/Reflex 경로에서 실행 에이전트의 provider를 중급 모델로 임시 교체하여 비용/속도 최적화.
- 프로바이더: `consciousness_agent._get_midtier_provider()` (싱글턴)
- 전환: `system_ai_core._switch_to_midtier()` → 실행 → `_restore_provider()`
- 중급 설정이 없으면 본격 모델을 그대로 사용 (하위호환)
- API 키가 비어있으면 시스템 AI 키를 자동 사용

#### 의식 에이전트 (Consciousness Agent)
사용자 메시지가 AI 에이전트에 도달하기 전에 메타적 판단을 수행합니다. 단순한 프롬프트 최적화가 아니라 **자기 한계 인식을 통한 문제 정의**가 핵심입니다.

**핵심 철학**: 문제는 **나의 한계**와 **환경의 제약**이 만나는 곳에서 생긴다. 도구의 한계가 문제의 난이도를 결정한다.

**역할**: 직접 문제를 풀지 않고, "지금 어떤 문제를 풀어야 하는가"를 자기 한계를 인식한 상태에서 정의
- **태스크 프레이밍** (task_framing): 도구가 주는 정보의 품질과 한계를 먼저 평가하여 문제 정의
- **달성 기준** (achievement_criteria): 별도 필드로 출력. 측정 가능한 성공 조건 — 평가 에이전트가 이를 기준으로 결과를 평가
- **자기 인식** (self_awareness): 각 IBL 액션의 `implementation` 필드를 참조하여 도구 품질/한계 판단
- **히스토리 정제** (history_summary): 현재 문제 관련 맥락만 추려 요약, 원본 히스토리 대체
- **IBL 포커싱** (capability_focus): 관련 노드/액션의 `implementation` 상세 포함 (제한이 아닌 초점)
- **가이드 파일 선택** (guide_files): 문제 해결에 필요한 가이드 파일 지정
- **상황 메모** (world_state): 세계 상태, 시간대 등 배경 정보 메모

**에이전트 베이스 프롬프트와의 연동**: 의식 에이전트가 한계를 알려주는 것에 더해, 에이전트 자신도 베이스 프롬프트(base_prompt_v5.md)에서 "네 한계를 알아라", "소스의 품질을 판단하라", "결과의 한계를 알려라"는 원칙을 갖고 있어 양방향으로 일관된 자기 인식을 유지.

**적용 범위**: 시스템 AI + 모든 프로젝트 에이전트 (내부 위임 메시지는 제외)
**구현**: 시스템 AI의 API 설정(프로바이더/모델/키)을 재사용, 원샷 JSON 응답
- 파일: `backend/consciousness_agent.py`, `data/common_prompts/consciousness_prompt.md`
- 통합: `agent_cognitive.py._run_consciousness()` (시스템 AI + 프로젝트 에이전트 공통)

#### 평가 에이전트 (Evaluator Agent)
AI 에이전트 실행 후 결과를 평가하는 사후 루프:
- 의식 에이전트가 출력한 `achievement_criteria`를 기준으로 평가
- **ACHIEVED**: 결과 그대로 반환
- **NOT_ACHIEVED**: 구체적 피드백과 함께 AI 에이전트 재실행 (최대 3라운드)
- 파일: `data/common_prompts/evaluator_prompt.md`, `agent_cognitive.AgentCognitiveMixin._run_goal_evaluation_loop()`
- 시스템 AI와 프로젝트 에이전트 모두 동일한 평가 루프 사용

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

**AI 건강 체크 (매 6시간)**: 시스템 AI가 미확인/실패 액션을 능동적으로 테스트
- 읽기 전용 액션만 선택, 적절한 파라미터를 AI가 직접 생성
- 결과는 `action_health` 테이블에 자동 기록 (실사용 액션도 동일 테이블)
- 3단계 상태: verified(7일 이내 성공), assumed(기록 없음), failed(최근 실패)

**에피소딕 메모리**: 에피소드(사용자 명령→최종 응답)별 실행 로그 기록
- `episode_log` 테이블: 전체 로그 (최근 100개 보존)
- `episode_summary` 테이블: 인지 품질 지표 영구 보존 (해마 점수, 무의식 판정, 의식 소요시간, 실행 라운드, 평가 결과)
- 파일: `backend/episode_logger.py`, DB: `data/world_pulse.db`
- API: `/xray/episodes`, `/xray/episodes/{id}`, `/xray/episode-summaries`

**서버 시작 시**: 최근 1시간 내 펄스가 없으면 즉시 수집, 있으면 건너뜀

- 비용: 사용자/자신 상태는 DB 쿼리만 (비용 0), 세계 정보는 경량 API 호출
- 파일: `backend/world_pulse.py`, `data/world_pulse.db`
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
  - 수동 연결: 에이전트가 필요할 때 `[limbs:chrome_connect]`로 연결
  - Chrome 미실행 시 Playwright로 자동 폴백
  - 같은 IBL 액션(`limbs:browser_*`)을 사용, 내부 드라이버만 다름

## 프로젝트 & 에이전트

- 프로젝트 단위로 독립된 작업 공간. 각 프로젝트에 역할별 에이전트 배치
- 에이전트 간 위임: 단일/순차/병렬 (`[others:delegate_project]`)
- 시스템 AI: 전체 노드 접근, 프로젝트 에이전트에 위임 가능
- 프로젝트 에이전트: 허용된 노드만 접근 (allowed_nodes)

## 외부 연동

- **통신**: Gmail, Nostr, Telegram
- **NAS**: 음악 스트리밍, 자막 관리, 웹앱 호스팅
- **안드로이드**: ADB 기반 기기 제어
- **원격**: Cloudflare Tunnel (Finder + 런처)
- **브라우저**: Playwright 기반 자동화

## 시스템 통계

- 활성 프로젝트: 20개, 활성 에이전트: 29개
- 도구 패키지: 34개, IBL: 5노드 311액션

## 참조

- IBL 명세: `system_docs/ibl.md`
- 실행기억 & 해마: `system_docs/execution_memory.md`
- 패키지 가이드: `system_docs/packages.md`
- 설계 철학 (백서): `WHITEPAPER.md`

---
*마지막 업데이트: 2026-04-05 (overview.md 통합)*
