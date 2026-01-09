# IndieBiz OS 기술 문서

## API 엔드포인트

### 프로젝트 관리
- `GET /projects` - 프로젝트 목록 조회
- `POST /projects` - 프로젝트 생성
- `DELETE /projects/{project_id}` - 프로젝트 삭제
- `PUT /projects/{project_id}/position` - 프로젝트 위치 업데이트
- `POST /projects/{project_id}/trash` - 휴지통으로 이동
- `PUT /projects/{project_id}/rename` - 이름 변경
- `POST /projects/{project_id}/copy` - 프로젝트 복사
- `GET /projects/{project_id}/config` - 프로젝트 설정 조회
- `PUT /projects/{project_id}/config` - 프로젝트 설정 업데이트

### 에이전트 관리
- `GET /projects/{project_id}/agents` - 에이전트 목록
- `POST /projects/{project_id}/agents` - 에이전트 생성
- `PUT /projects/{project_id}/agents/{agent_id}` - 에이전트 업데이트
- `DELETE /projects/{project_id}/agents/{agent_id}` - 에이전트 삭제
- `POST /projects/{project_id}/agents/{agent_id}/start` - 에이전트 시작
- `POST /projects/{project_id}/agents/{agent_id}/stop` - 에이전트 중지
- `POST /projects/{project_id}/agents/{agent_id}/command` - 명령 전송
- `GET /projects/{project_id}/agents/{agent_id}/role` - 역할 조회
- `PUT /projects/{project_id}/agents/{agent_id}/role` - 역할 업데이트
- `PUT /projects/{project_id}/agents/role-descriptions` - 역할 설명 일괄 업데이트
- `GET /projects/{project_id}/agents/{agent_id}/note` - 메모 조회
- `PUT /projects/{project_id}/agents/{agent_id}/note` - 메모 저장

### 스위치 관리
- `GET /switches` - 스위치 목록
- `POST /switches` - 스위치 생성
- `DELETE /switches/{switch_id}` - 스위치 삭제
- `POST /switches/{switch_id}/execute` - 스위치 실행
- `PUT /switches/{switch_id}/position` - 위치 업데이트

### 시스템 AI
- `GET /system-ai` - 시스템 AI 설정 조회
- `PUT /system-ai` - 시스템 AI 설정 업데이트
- `POST /system-ai/chat` - 시스템 AI와 대화

### 도구 패키지 관리
- `GET /packages` - 전체 패키지 목록
- `GET /packages/installed` - 설치된 패키지 목록
- `GET /packages/available` - 설치 가능한 패키지 목록
- `GET /packages/{package_id}` - 패키지 상세 정보
- `POST /packages/{package_id}/install` - 패키지 설치
- `POST /packages/{package_id}/uninstall` - 패키지 제거
- `POST /packages/analyze-folder` - 폴더 분석
- `POST /packages/analyze-folder-ai` - AI 폴더 분석
- `POST /packages/register` - 외부 도구 등록

### 도구 관리
- `GET /tools` - 활성 도구 목록
- `GET /tool-settings` - 도구 AI 설정 조회
- `GET /tool-settings/{tool_key}` - 특정 도구 설정
- `PUT /tool-settings/{tool_key}` - 도구 설정 업데이트
- `POST /projects/{project_id}/auto-assign-tools` - 도구 자동 배분

### 프롬프트 생성
- `POST /projects/{project_id}/generate-prompts` - 프롬프트 생성
- `POST /projects/{project_id}/save-prompts` - 프롬프트 저장

### 스케줄러
- `GET /scheduler/tasks` - 예약 작업 목록
- `POST /scheduler/tasks` - 예약 작업 생성
- `PUT /scheduler/tasks/{task_id}` - 예약 작업 수정
- `DELETE /scheduler/tasks/{task_id}` - 예약 작업 삭제
- `POST /scheduler/tasks/{task_id}/toggle` - 활성화/비활성화
- `POST /scheduler/tasks/{task_id}/run` - 즉시 실행

### 휴지통
- `GET /trash` - 휴지통 목록
- `POST /trash/{item_id}/restore` - 복구
- `DELETE /trash` - 휴지통 비우기

### 비즈니스 관리 (/business)
- `GET /business` - 비즈니스 목록
- `POST /business` - 비즈니스 생성
- `PUT /business/{id}` - 비즈니스 수정
- `DELETE /business/{id}` - 비즈니스 삭제
- `GET /business/{id}/items` - 비즈니스 항목 목록
- `POST /business/{id}/items` - 비즈니스 항목 생성
- `PUT /business/items/{id}` - 비즈니스 항목 수정
- `DELETE /business/items/{id}` - 비즈니스 항목 삭제

### 이웃 관리 (/business/neighbors)
- `GET /business/neighbors` - 이웃 목록
- `POST /business/neighbors` - 이웃 생성
- `PUT /business/neighbors/{id}` - 이웃 수정
- `DELETE /business/neighbors/{id}` - 이웃 삭제
- `GET /business/neighbors/{id}/contacts` - 연락처 목록
- `POST /business/neighbors/{id}/contacts` - 연락처 추가
- `DELETE /business/contacts/{id}` - 연락처 삭제

### 메시지 관리 (/business/messages)
- `GET /business/messages` - 메시지 목록
- `POST /business/messages` - 메시지 생성
- `POST /business/messages/{id}/processed` - 처리 완료 표시
- `POST /business/messages/{id}/replied` - 응답 완료 표시

### 채널 설정 (/business/channels)
- `GET /business/channels` - 채널 설정 목록
- `GET /business/channels/{type}` - 특정 채널 설정
- `PUT /business/channels/{type}` - 채널 설정 수정
- `POST /business/channels/{type}/poll` - 즉시 폴링
- `GET /business/channels/poller/status` - 폴러 상태

### 자동응답 V2 (/business/auto-response)
2단계 처리: AI 판단 → 비즈니스 검색 → 응답 생성

- `GET /business/auto-response/status` - 자동응답 상태 (running, check_interval, processed_count)
- `POST /business/auto-response/start` - 자동응답 시작
- `POST /business/auto-response/stop` - 자동응답 중지

**AI 판단 결과:**
- `NO_RESPONSE`: 자동응답 불필요 (개인적 대화, 스팸 등) → replied=1 마킹
- `BUSINESS_RESPONSE`: 자동응답 필요 → 비즈니스 검색 후 응답 생성

### WebSocket
- `ws://127.0.0.1:8765/ws/chat/{client_id}` - 실시간 채팅

## 에이전트 기본 도구 (System Tools)

에이전트가 기본으로 사용할 수 있는 시스템 도구입니다.

| 도구 | 설명 |
|------|------|
| `call_agent(agent_name, message)` | 다른 에이전트에게 작업 위임 (비동기) |
| `list_agents()` | 사용 가능한 에이전트 목록 조회 |
| `get_my_tools()` | 현재 에이전트의 도구 목록 확인 |
| `send_notification(title, message)` | 시스템 알림 전송 |
| `get_project_info()` | 현재 프로젝트 정보 조회 |

### 위임 체인 DB 스키마 (tasks 테이블)

| 컬럼 | 타입 | 설명 |
|------|------|------|
| task_id | TEXT (PK) | 작업 고유 ID (예: task_abc123) |
| requester | TEXT | 최초 요청자 (예: user@gui) |
| requester_channel | TEXT | 요청 채널 (gui, email, nostr) |
| original_request | TEXT | 원래 요청 내용 |
| delegated_to | TEXT | 현재 담당 에이전트 이름 |
| delegation_context | TEXT | 위임 컨텍스트 JSON |
| parent_task_id | TEXT | 부모 태스크 ID (계층적 위임 추적) |
| pending_delegations | INTEGER | 대기 중인 위임 수 (병렬 위임용) |
| status | TEXT | 상태 (pending, in_progress, completed) |
| result | TEXT | 작업 결과 |
| ws_client_id | TEXT | WebSocket 클라이언트 ID |
| created_at | TIMESTAMP | 생성 시간 |
| completed_at | TIMESTAMP | 완료 시간 |

### delegation_context 구조

```json
{
  "original_request": "사용자의 원래 요청",
  "requester": "user@gui",
  "delegations": [
    {
      "child_task_id": "task_xxx",
      "delegated_to": "대장장이",
      "delegation_message": "위임 시 전달한 메시지",
      "delegation_time": "2026-01-08T21:00:00"
    }
  ],
  "responses": [
    {
      "child_task_id": "task_xxx",
      "from_agent": "대장장이",
      "response": "작업 결과",
      "completed_at": "2026-01-08T21:05:00"
    }
  ]
}
```

## 설정 파일 위치
- **시스템 AI 설정**: `data/system_ai_config.json`
- **스위치 목록**: `data/switches.json`
- **프로젝트 목록**: `projects/projects.json`
- **프로젝트 에이전트**: `projects/{id}/agents.yaml`
- **시스템 AI 메모리**: `data/system_ai_memory.db` (SQLite)
- **대화 이력**: `projects/{id}/conversations.db` (SQLite)
- **도구 패키지**: `data/packages/installed/tools/`
- **비즈니스 DB**: `data/business.db` (SQLite)

## 지원 AI 프로바이더
- **Anthropic Claude**: claude-sonnet-4-20250514, claude-3-5-haiku-20241022, claude-opus-4-5-20251101
- **OpenAI GPT**: gpt-4o, gpt-4o-mini
- **Google Gemini**: gemini-2.0-flash-exp, gemini-1.5-pro, gemini-1.5-flash, gemini-3-flash-preview

## 기술 스택
- **백엔드**: Python 3.x, FastAPI, uvicorn
- **프론트엔드**: React 18, TypeScript, Vite, TailwindCSS
- **데스크톱**: Electron (IPC를 통한 백엔드 통신)

## 물리적 구조 (주요 경로)
- `backend/`: 서버 소스 코드
- `data/`: 시스템 설정 및 데이터
- `data/packages/installed/tools/`: 설치된 도구 패키지 (11개)
- `data/packages/installed/extensions/`: 설치된 확장 (9개)
- `projects/`: 사용자 프로젝트 데이터 (11개)

---
*마지막 업데이트: 2026-01-09*
