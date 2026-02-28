# IndieBiz OS 아키텍처

## 시스템 구조

```
indiebizOS/
├── backend/              # Python FastAPI 백엔드
│   ├── api.py           # 메인 서버 (포트 8765)
│   ├── api_*.py         # 각 모듈 라우터 (19개)
│   ├── api_nas.py       # 원격 Finder API (파일 접근/스트리밍)
│   ├── *_manager.py     # 비즈니스 로직 매니저
│   ├── ai_agent.py      # AI 에이전트 코어
│   ├── agent_runner.py  # 에이전트 실행기
│   ├── system_ai.py     # 시스템 AI 코어
│   ├── providers/       # AI 프로바이더 (스트리밍 지원)
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
│   │   │   └── tools/      # 도구 (35개)
│   │   └── not_installed/  # 미설치 패키지
│   ├── system_docs/     # 시스템 AI 문서 (장기기억)
│   ├── business.db      # 비즈니스 DB
│   └── multi_chat.db    # 다중채팅방 DB
│
├── projects/            # 사용자 프로젝트 (24개)
│   ├── projects.json    # 프로젝트 목록 및 설정
│   └── {project_id}/    # 개별 프로젝트 폴더
│
└── templates/           # 프로젝트 템플릿
```

## 핵심 컴포넌트

### 통합 AI 아키텍처 (Phase 22: 6-Node 통합)
시스템 AI와 프로젝트 에이전트가 동일한 코드베이스와 **동일한 도구 구조**를 공유합니다:

```
┌─────────────────────────────────────────────────────┐
│                    AIAgent 클래스                    │
│         (ai_agent.py - 단일 코어)                    │
├─────────────────────────────────────────────────────┤
│  • process_message_stream() - 스트리밍 처리          │
│  • process_message_with_history() - 동기 처리        │
│  • execute_ibl 단일 도구로 모든 기능 접근            │
└─────────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
┌──────────────────┐       ┌──────────────────┐
│    시스템 AI      │       │  프로젝트 에이전트  │
│ (api_system_ai)  │       │  (agent_runner)  │
├──────────────────┤       ├──────────────────┤
│ execute_ibl      │       │ execute_ibl      │
│ (전체 노드)       │       │ (허용 노드)       │
└──────────────────┘       └──────────────────┘
          │                           │
          └───────────┬───────────────┘
                      ▼
┌─────────────────────────────────────────────────────┐
│              providers/ (스트리밍 지원)              │
│  anthropic.py | openai.py | gemini.py | ollama.py  │
└─────────────────────────────────────────────────────┘
```

**통합 효과:**
- 시스템 AI와 프로젝트 에이전트 모두 `execute_ibl` 단일 도구 사용
- 차이점은 접근 가능한 노드 범위뿐 (시스템 AI: 전체, 프로젝트 에이전트: 허용된 노드)
- 사용자 소통(질문, 할일, 승인, 알림)도 `[system:*]` 액션으로 통합
- 프로바이더 코드 1회 작성으로 시스템 AI + 모든 에이전트 지원
- 새 프로바이더 추가 시 자동으로 전체 적용

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
│   - 시스템 AI: 전체 노드                │
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

### 위임 체인 시스템 (Delegation Chain)
에이전트 간 비동기 협업을 위한 핵심 메커니즘. `call_agent()`를 통해 작업을 위임하고 결과를 자동으로 보고받음.
→ 상세 문서: [delegation.md](delegation.md)

### IBL (IndieBiz Logic) 시스템
- 노드 기반 추상화: `[node:action](target) {params}` 문법
- execute_ibl 단일 도구로 모든 노드 접근
- **6개 노드, 321 액션** (Phase 22: 10→6 노드 통합)
  - source(105), interface(79), system(64), forge(46), stream(18), messenger(9)
- **액션 라우팅 이원화**: api_engine(자동 발견) + handler(수동)
- `api_registry.yaml`에 `node` 필드 추가 시 자동으로 노드 액션에 병합 — `ibl_nodes.yaml` 편집 불필요
- 에이전트별 접근 제어: `allowed_nodes`로 노드 필터링
- 인프라 노드(`system`)는 모든 에이전트에 자동 허용
→ 상세 문서: [ibl.md](ibl.md)

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
→ 상세 문서: [ibl_rag.md](ibl_rag.md)

### 도구 패키지 시스템 (노드 구현체)
- 폴더 기반 탐지 및 동적 로딩 (35개 설치됨)
- IBL 노드의 실제 구현체로 동작
- **두 가지 실행 경로**: handler.py(복잡한 후처리) 또는 api_engine(API+transform)
- `tool.json` + `handler.py` 구조 (또는 api_registry.yaml 등록)
- 도구 설명 구조: 한줄 요약 + 데이터 형식 + 예시
- 가이드 파일 시스템: 복잡한 도구에 on-demand 가이드 주입 → [상세 문서](guide_file.md)

### 자동응답 서비스 V3
- Tool Use 기반 단일 AI 호출로 판단/검색/발송 통합
- `search_business_items`, `no_response_needed`, `send_response` 도구
- 응답 즉시 발송 (polling 대기 없음)
→ 상세 문서: [auto_response.md](auto_response.md)

### 다중채팅방 시스템
- 독립 창에서 여러 프로젝트의 에이전트를 소환하여 그룹 대화 수행

### 원격 접근 시스템
Cloudflare Tunnel을 통해 외부에서 IndieBiz OS를 제어합니다:

- **원격 Finder** (`api_nas.py`): 파일 탐색, 동영상 스트리밍, 다운로드 — 개인 NAS처럼 활용
- **원격 런처** (`api_launcher_web.py`): 시스템 AI/프로젝트 에이전트 채팅, 스위치 실행 — 모든 AI 에이전트를 원격으로 구동
- 세션 기반 인증 (기능별 별도 비밀번호)
- 모바일 반응형 다크 테마 UI
→ 상세 문서: [remote_access.md](remote_access.md)

---
*마지막 업데이트: 2026-02-19 (Phase 22: 6-Node 통합)*
