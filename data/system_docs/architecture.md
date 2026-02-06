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
│   │   │   └── tools/      # 도구 (26개)
│   │   └── not_installed/  # 미설치 패키지
│   ├── system_docs/     # 시스템 AI 문서 (장기기억)
│   ├── business.db      # 비즈니스 DB
│   └── multi_chat.db    # 다중채팅방 DB
│
├── projects/            # 사용자 프로젝트 (16개)
│   ├── projects.json    # 프로젝트 목록 및 설정
│   └── {project_id}/    # 개별 프로젝트 폴더
│
└── templates/           # 프로젝트 템플릿
```

## 핵심 컴포넌트

### 통합 AI 아키텍처
시스템 AI와 프로젝트 에이전트가 동일한 코드베이스를 공유합니다:

```
┌─────────────────────────────────────────────────────┐
│                    AIAgent 클래스                    │
│         (ai_agent.py - 단일 코어)                    │
├─────────────────────────────────────────────────────┤
│  • process_message_stream() - 스트리밍 처리          │
│  • process_message_with_history() - 동기 처리        │
│  • 도구 실행 로직 통합                               │
└─────────────────────────────────────────────────────┘
          │                           │
          ▼                           ▼
┌──────────────────┐       ┌──────────────────┐
│    시스템 AI      │       │  프로젝트 에이전트  │
│ (api_system_ai)  │       │  (agent_runner)  │
├──────────────────┤       ├──────────────────┤
│ create_system_   │       │ AIAgent 직접     │
│ ai_agent()       │       │ 인스턴스화        │
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
- 프로바이더 코드 1회 작성으로 시스템 AI + 모든 에이전트 지원
- 스트리밍, 도구 실행 로직 일원화
- 새 프로바이더 추가 시 자동으로 전체 적용

### 프롬프트 빌더 (prompt_builder.py)
시스템 AI와 프로젝트 에이전트 모두 동일한 프롬프트 구조 사용:

```
┌─────────────────────────────────────────┐
│     공통 설정 (base_prompt_v2.md)        │
│   - AI 행동 원칙, 도구 사용 가이드       │
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

### 도구 패키지 시스템
- 폴더 기반 탐지 및 동적 로딩
- AI가 코드와 README를 읽고 직접 사용법 파악
- `tool.json` + `handler.py` 구조
- 도구 설명 구조: 한줄 요약 + 데이터 형식 + 예시
- 가이드 파일 시스템: 복잡한 도구에 on-demand 가이드 주입 → [상세 문서](guide_file.md)

### 자동응답 서비스 V3
- Tool Use 기반 단일 AI 호출로 판단/검색/발송 통합
- `search_business_items`, `no_response_needed`, `send_response` 도구
- 응답 즉시 발송 (polling 대기 없음)
→ 상세 문서: [auto_response.md](auto_response.md)

### 다중채팅방 시스템
- 독립 창에서 여러 프로젝트의 에이전트를 소환하여 그룹 대화 수행

### 원격 Finder (api_nas.py)
- Cloudflare Tunnel을 통한 외부 파일 접근
- 세션 기반 인증 (비밀번호)
- HTTP Range 요청으로 동영상 스트리밍
- 허용 경로 기반 접근 제어
- Finder 스타일 웹 앱 내장
→ 상세 문서: [remote_finder.md](remote_finder.md)

---
*마지막 업데이트: 2026-02-05*
