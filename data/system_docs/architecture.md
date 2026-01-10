# IndieBiz OS 아키텍처

## 시스템 구조

```
indiebizOS/
├── backend/              # Python FastAPI 백엔드
│   ├── api.py           # 메인 서버 (포트 8765)
│   ├── api_*.py         # 각 모듈 라우터
│   │   ├── api_agents.py      # 에이전트 CRUD/제어
│   │   ├── api_projects.py    # 프로젝트 관리
│   │   ├── api_switches.py    # 스위치 관리
│   │   ├── api_config.py      # 설정 관리
│   │   ├── api_system_ai.py   # 시스템 AI
│   │   ├── api_packages.py    # 도구 패키지 관리
│   │   ├── api_tools.py       # 도구 관리
│   │   ├── api_conversations.py # 대화 이력
│   │   ├── api_websocket.py   # 실시간 통신
│   │   ├── api_indienet.py    # IndieNet (Nostr)
│   │   ├── api_scheduler.py   # 스케줄러
│   │   ├── api_business.py    # 비즈니스/이웃/메시지/자동응답
│   │   ├── api_multi_chat.py  # 다중채팅방 API
│   │   ├── api_notifications.py # 알림
│   │   └── api_prompt_generator.py # 프롬프트 생성
│   ├── *_manager.py     # 비즈니스 로직 매니저
│   │   ├── project_manager.py # 프로젝트 매니저
│   │   ├── switch_manager.py  # 스위치 매니저
│   │   ├── package_manager.py # 도구 패키지 매니저
│   │   ├── business_manager.py # 비즈니스/이웃/메시지 매니저
│   │   ├── multi_chat_manager.py # 다중채팅방 매니저
│   │   └── notification_manager.py # 알림 매니저
│   ├── multi_chat_db.py    # 다중채팅방 DB 관리
│   ├── ai_agent.py      # AI 에이전트 코어
│   ├── agent_runner.py  # 에이전트 실행기
│   ├── system_ai.py     # 시스템 AI 코어
│   ├── auto_response.py # 자동응답 서비스 V2 (AI 판단 + 비즈니스 검색)
│   ├── ai_judgment.py   # AI 판단 서비스 (메시지 분류/키워드 추출)
│   ├── channel_poller.py # 다중채널 메시지 수신 (Gmail/Nostr)
│   ├── prompt_generator.py # 프롬프트 생성기
│   ├── scheduler.py     # 스케줄러
│   ├── indienet.py      # IndieNet 코어
│   ├── tool_selector.py # 도구 선택/실행
│   └── conversation_db.py # 대화 DB 관리
│
├── frontend/            # Electron + React 프론트엔드
│   ├── electron/        # Electron 메인/프리로드
│   │   ├── main.js      # 메인 프로세스
│   │   └── preload.js   # IPC 브릿지
│   └── src/
│       ├── components/  # React 컴포넌트
│       │   ├── Launcher.tsx   # 메인 런처 (바탕화면)
│       │   ├── Manager.tsx    # 프로젝트 매니저
│       │   ├── Chat.tsx       # 채팅 인터페이스
│       │   ├── FolderView.tsx # 폴더 뷰
│       │   ├── IndieNet.tsx   # IndieNet 뷰
│       │   ├── BusinessManager.tsx # 비즈니스 관리
│       │   ├── NeighborManagerDialog.tsx # 이웃 관리 다이얼로그
│       │   └── MultiChat.tsx  # 다중채팅방 UI
│       ├── lib/         # API 클라이언트
│       │   └── api.ts   # API 클라이언트 클래스
│       ├── stores/      # 상태 관리
│       └── types/       # TypeScript 타입
│
├── data/                # 런타임 데이터
│   ├── packages/        # 도구 패키지 저장소
│   │   ├── not_installed/tools/ # 설치 가능한 패키지 (미설치)
│   │   ├── installed/tools/     # 설치된 도구 패키지 (활성)
│   │   ├── installed/extensions/ # 설치된 확장 (gmail 등)
│   │   └── dev/tools/           # 개발 중인 패키지
│   ├── health/          # 건강 기록 데이터
│   │   ├── health_records.db    # 건강 정보 DB (측정값, 증상, 투약, 문서)
│   │   └── images/              # 검사결과/처방전 이미지
│   ├── system_docs/     # 시스템 AI 문서 (장기기억)
│   ├── system_ai_memory.db # 시스템 AI 메모리 (SQLite)
│   ├── system_ai_config.json # 시스템 AI 설정
│   ├── business.db      # 비즈니스/이웃/메시지 DB (SQLite)
│   ├── multi_chat.db    # 다중채팅방 DB (SQLite)
│   └── switches.json    # 스위치 설정
│
├── projects/            # 사용자 프로젝트
│   ├── projects.json    # 프로젝트 목록 및 설정
│   └── {project_id}/    # 개별 프로젝트 폴더
│       ├── agents.yaml  # 에이전트 설정
│       ├── conversations.db # 대화 이력 (SQLite)
│       └── agent_*_role.txt # 에이전트 역할 파일
│
├── templates/           # 프로젝트 템플릿
│
└── outputs/             # 출력 파일
```

## 핵심 컴포넌트

### 시스템 AI
- IndieBiz의 관리자이자 안내자
- 시스템 설정의 AI 프로바이더 사용
- 사용자 정보(단기기억)와 시스템 문서(장기기억) 참조
- 파일 위치: `backend/system_ai.py`, `backend/api_system_ai.py`

### 프로젝트 매니저
- 프로젝트 생성, 수정, 삭제
- 템플릿 기반 프로젝트 생성
- 에이전트 관리 (CRUD, 역할 설명)
- 대화 이력 관리
- 휴지통 기능
- 파일 위치: `backend/project_manager.py`, `backend/api_projects.py`

### 에이전트 시스템
- 에이전트 시작/중지/명령 전송
- 역할(role) 및 역할 설명(role_description) 관리
- 도구 할당 (allowed_tools)
- **위임 체인 시스템**: 에이전트 간 비동기 협업 및 자동 보고
- 파일 위치: `backend/api_agents.py`, `backend/ai_agent.py`, `backend/agent_runner.py`

### 위임 체인 시스템 (Delegation Chain)
에이전트 간 비동기 협업을 위한 핵심 메커니즘입니다.

**핵심 개념:**
- `call_agent()`: 다른 에이전트에게 작업 위임 (비동기)
- `task_id`: 각 작업의 고유 식별자
- `parent_task_id`: 위임 체인 연결 (부모-자식 관계)
- `delegation_context`: 위임 시 저장되는 컨텍스트 (원래 요청, 위임 메시지 등)

**작동 흐름:**
```
1. 사용자 요청 → task_001 생성 (에이전트 A)
2. A가 call_agent("B", "...") 호출
   → delegation_context 저장 (왜 위임했는지)
   → task_002 생성 (parent: task_001)
   → A의 턴 종료
3. B가 작업 완료
   → 시스템이 자동으로 A에게 결과 보고
   → delegation_context 복원 (A가 "기억"할 수 있게)
4. A가 결과 수신 + 컨텍스트로 상황 파악
   → 남은 작업 처리
   → 사용자에게 최종 보고
```

**병렬 위임:**
- 하나의 에이전트가 여러 에이전트에게 동시 위임 가능
- `pending_delegations` 카운터로 대기 중인 위임 추적
- 모든 결과가 도착해야 통합 보고 전송
- 결과는 `[병렬 위임 결과 통합 보고]` 형식으로 수집

**주요 도구:**
- `call_agent(agent_name, message)`: 다른 에이전트에게 작업 위임
- `list_agents()`: 사용 가능한 에이전트 목록 조회
- `get_my_tools()`: 현재 에이전트의 도구 목록 확인 (위임 전 자가 처리 가능 여부 판단)

파일 위치: `backend/agent_runner.py`, `backend/ai_agent.py`, `backend/conversation_db.py`, `backend/thread_context.py`

### 도구 패키지 시스템
- **폴더 기반 탐지**: 폴더 존재만으로 패키지 인식 (installed, not_installed, dev)
- **도구 패키지**: 에이전트가 동적으로 로딩하여 사용하는 기능
- **설치/제거**: not_installed ↔ installed 간 폴더 이동
- **AI 친화적**: 코드와 README만으로 AI가 이해 가능
- **외부 폴더 등록**: 사용자 폴더를 패키지로 등록 가능
- 파일 위치: `backend/package_manager.py`, `backend/api_packages.py`

### 비즈니스 관리 시스템
- **비즈니스**: 레벨별 비즈니스 항목 관리 (나눕니다, 구합니다, 팔아요 등)
- **이웃(파트너)**: 연락처 관리, 정보 레벨 설정
- **메시지**: 수신/발송 메시지 관리, 응답 상태 추적
- **채널 설정**: Gmail, Nostr 등 통신 채널 설정
- 파일 위치: `backend/business_manager.py`, `backend/api_business.py`

### 다중채널 메시지 수신 (Channel Poller)
- **Gmail**: 주기적 폴링으로 이메일 수신
- **Nostr**: 실시간 WebSocket으로 DM 수신
- IndieNet identity.json과 키 연동
- 파일 위치: `backend/channel_poller.py`

### 자동응답 서비스 V2
kvisual-mcp의 2단계 자동응답 시스템을 Python으로 포팅.

**처리 흐름:**
```
1. 미응답 메시지 확인 (10초 주기)
2. AI 판단 (ai_judgment.py)
   - NO_RESPONSE: 자동응답 불필요 → replied=1 표시 후 스킵
   - BUSINESS_RESPONSE: 자동응답 필요 → 다음 단계
3. 비즈니스 검색
   - AI가 추출한 카테고리/키워드로 비즈니스 아이템 검색
   - 검색 결과를 컨텍스트에 포함
4. 응답 생성
   - 시스템 AI 설정 재사용 (프로바이더, 모델, API 키)
   - 컨텍스트: 근무지침, 비즈니스 문서, 대화 기록, 검색 결과
5. 응답 저장 (status='pending')
```

**비즈니스 카테고리:**
- 나눕니다 (무료 나눔)
- 구합니다 (필요한 것 요청)
- 놉시다 (함께 하기)
- 빌려줍니다 (대여 서비스)
- 소개합니다 (인맥/서비스 소개)
- 팔아요 (판매)
- 할수있습니다 (서비스 제공)

**무한 루프 방지:**
- replied=1 마킹으로 중복 처리 방지
- 연속 자동응답 5개 초과 시 스킵

파일 위치: `backend/auto_response.py`, `backend/ai_judgment.py`

### 다중채팅방 시스템 (Multi Chat)
여러 에이전트와 사용자가 함께하는 그룹 채팅방 시스템입니다.

**핵심 기능:**
- **별도 창 운영**: 프로젝트 창처럼 다중채팅방을 독립 창으로 열기
- **에이전트 소환**: 다른 프로젝트에서 에이전트를 불러와 참여시킴
- **원본 AI 설정 유지**: 소환 시 에이전트의 원래 AI 설정(provider, model, api_key) 보존
- **전체 시작/중단**: 모든 참여 에이전트를 한 번에 활성화/비활성화
- **도구 할당**: 에이전트에게 도구 선택 가능 (드롭다운)
- **창 닫기 자동 정리**: 창 닫을 때 에이전트 자동 비활성화

**DB 스키마:**
- `rooms`: 채팅방 정보 (id, name, description, icon_position)
- `room_participants`: 참여자 (room_id, agent_name, agent_source, system_prompt, ai_provider, ai_model, ai_api_key)
- `room_messages`: 메시지 (room_id, speaker, content, created_at)

**대화 규칙:**
- 대화만 가능 (도구 미사용 시)
- @지목으로 특정 에이전트 호출 가능
- 지목 없으면 랜덤 2명 응답

파일 위치: `backend/multi_chat_manager.py`, `backend/multi_chat_db.py`, `backend/api_multi_chat.py`, `frontend/src/components/MultiChat.tsx`

### Electron IPC
- 네이티브 폴더 선택 다이얼로그
- 외부 URL 열기
- 다중 창 관리 (프로젝트, 폴더, IndieNet, 비즈니스, 다중채팅방)

### 스케줄러
- 예약된 작업 자동 실행
- 크론 표현식 지원
- 파일 위치: `backend/scheduler.py`, `backend/api_scheduler.py`

## 데이터 흐름

### 일반 에이전트 대화
```
사용자 → Electron (React UI) → HTTP/WebSocket → FastAPI 백엔드
                                                      ↓
                                              프로젝트/에이전트 관리
                                                      ↓
                                              AI 프로바이더 (Claude/GPT/Gemini/Ollama)
                                                      ↓
                                              도구 패키지 동적 로딩 및 실행
```

### 메시지 수신 및 자동응답
```
Gmail/Nostr → ChannelPoller → DB 저장 (replied=0)
                                    ↓
                           AutoResponseService (10초 주기)
                                    ↓
                           컨텍스트 수집 (이웃, 대화기록, 근무지침, 비즈니스문서)
                                    ↓
                           시스템 AI로 응답 생성
                                    ↓
                           응답 저장 (status='pending')
```

## 설계 원칙
1. 최소주의: 핵심 기능만 코어에 포함
2. 확장성: 도구 패키지로 기능 확장 (동적 로딩)
3. 독립성: 각 컴포넌트는 독립적으로 동작
4. AI 친화적: 형식보다 내용, AI가 이해할 수 있는 구조

### 에이전트 간 협업 흐름
```
사용자 요청 → 에이전트 A (task_001)
                   ↓ call_agent("B")
              task_002 생성 (parent: task_001)
              delegation_context 저장
                   ↓
              에이전트 B 작업 수행
                   ↓ 작업 완료
              시스템 자동 보고 (B → A)
                   ↓
              에이전트 A가 결과 수신
              delegation_context 복원
                   ↓
              에이전트 A 최종 처리
                   ↓
              사용자에게 최종 보고
```

---
*마지막 업데이트: 2026-01-10*
