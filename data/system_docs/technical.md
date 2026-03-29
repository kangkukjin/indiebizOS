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
- `GET /system-ai/prompts/config` - 프롬프트 설정 조회
- `PUT /system-ai/prompts/config` - 프롬프트 설정 업데이트 (역할 프롬프트 토글)
- `GET /system-ai/prompts/role` - 역할 프롬프트 조회
- `PUT /system-ai/prompts/role` - 역할 프롬프트 업데이트

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

### 자동응답 V3 (/business/auto-response)
Tool Use 기반 단일 AI 호출로 판단/검색/발송 통합

- `GET /business/auto-response/status` - 자동응답 상태
- `POST /business/auto-response/start` - 자동응답 시작
- `POST /business/auto-response/stop` - 자동응답 중지

### 의식 시스템 (/world-pulse) — api_config.py에서 라우팅
- `GET /world-pulse/consciousness` - 최근 의식 펄스 조회 (hours 파라미터로 시간 범위 지정)
- `GET /world-pulse/self-checks` - 최근 자가점검 결과 (hours 파라미터로 시간 범위 지정)
- `GET /world-pulse/health` - 시스템 건강 요약 (서비스 상태, 액션 성공률, 최근 펄스)

### WebSocket (실시간 스트리밍)
- `ws://127.0.0.1:8765/ws/chat/{client_id}` - 실시간 채팅 (스트리밍)

## 스트리밍 이벤트 타입
| 타입 | 설명 |
|------|------|
| `text` | 텍스트 청크 (실시간) |
| `tool_start` | 도구 실행 시작 |
| `tool_result` | 도구 실행 결과 |
| `thinking` | AI 사고 과정 |
| `final` | 최종 응답 |
| `error` | 에러 발생 |

## IBL 도구 아키텍처 (Phase 25: 5-Node 구조)

모든 에이전트(시스템 AI 포함)는 `execute_ibl` 단일 도구를 사용합니다. 시스템 AI와 프로젝트 에이전트는 추가로 `execute_python`, `execute_node`, `run_command`, `search_guide` 도구도 보유합니다.

### execute_ibl
IBL 코드를 받아 파싱하고 실행하는 통합 실행기입니다.

```
execute_ibl(code='[node:action]{params}')

예시:
execute_ibl(code='[sense:price]{symbol: "AAPL"}')
execute_ibl(code='[sense:search_ddg]{query: "AI"} >> [self:file]{path: "result.md"}')
execute_ibl(code='[sense:price]{symbol: "AAPL"} & [sense:price]{symbol: "MSFT"}')
```

### 액션 라우팅
IBL 액션은 여러 경로로 실행됩니다:

| 라우터 | 개수 | 특성 | 등록 방식 |
|--------|------|------|----------|
| api_engine | 2 | API 호출 + transform 후처리 | api_registry.yaml에 node 필드 (자동 병합) |
| handler | 260 | 복잡한 후처리 (캐싱, 코드 매핑 등) | ibl_nodes.yaml에 수동 등록 |
| system | 22 | 시스템 내장 액션 | 시스템 레벨 직접 등록 |
| trigger_engine | 9 | 이벤트/트리거 기반 실행 | trigger_engine 등록 |
| workflow_engine | - | 워크플로우 오케스트레이션 | workflow 정의 |
| driver | - | 프로토콜 추상화 (HTTP, WebSocket, ADB, CDP 등) | 드라이버 등록 |
| channel_engine | - | 채널 추상화 계층 | 채널 설정 |

**자동 발견**: `ibl_engine.py`의 `_merge_api_registry_actions()`가 로드 시 api_registry의 node 바인딩 도구를 노드 액션에 자동 병합합니다.

### 주요 IBL 노드 액션 (기존 시스템 도구 대응)

Phase 19→22→23→25: 개인 도메인 → self, 정보 수집 → sense, 장치 제어 → limbs, 제작 → engines, 협업 → others

| IBL 액션 | 기존 도구명 | 설명 |
|----------|-----------|------|
| `[others:delegate]` | `call_agent` | 다른 에이전트에게 작업 위임 |
| `[others:ask_sync]` | - | 동기 에이전트 호출 (파이프라인용) |
| `[others:delegate_project]` | `call_project_agent` | 프로젝트 간 위임 (시스템AI 전용) |
| `[others:channel_send]` | - | 메시지 발송 (gmail, nostr 등) |
| `[others:search_contact]` | - | 연락처 검색 |
| `[self:ask_user]` | `ask_user_question` | 사용자에게 질문 |
| `[self:todo]` | `todo_write` | 할일 목록 관리 |
| `[self:approve]` | `request_user_approval` | 사용자 승인 요청 |
| `[self:notify_user]` | `send_notification` | 사용자 알림 전송 |
| `[self:file]` | - | 파일 저장/관리 |
| `[self:read]` | `read_file` | 파일 읽기 |
| `[self:write]` | `write_file` | 파일 쓰기 |
| `[self:run_command]` | `run_command` | 코드/명령 실행 |
| `[sense:search_ddg]` | `web_search` | 웹 검색 |
| `[sense:price]` | `get_stock_price` | 주가 조회 |
| `[limbs:browser_navigate]` | `browser_navigate` | 브라우저 탐색 |
| `[limbs:play]` | `play_media` | 미디어 재생 |
| `[engines:slide]` | `create_slide` | 슬라이드 생성 |

### 인프라 노드 (항상 허용)
`self`, `others` — 모든 에이전트에 자동 제공 (`_ALWAYS_ALLOWED`)

### 5-Node 구조 (Phase 25: 노드 재구조화)
| 노드 | 액션 수 | 카테고리 | 설명 |
|------|---------|---------|------|
| `sense` | 78 | search, get, list, create, delete, write | 데이터 검색/조회 (외부 정보 + 내부 저장소) |
| `limbs` | 96 | click, type, get, screenshot, control, play, stream, list | UI 조작 + 미디어 (브라우저, 안드로이드, 데스크탑, 유튜브, 라디오) |
| `self` | 75 | get, io, list, event, notify, run, control, fs, storage | 개인 도메인 (시스템 관리, 사용자 소통, 워크플로우, 파일) |
| `engines` | 46 | create, get, list, run | 콘텐츠 생성 (슬라이드, 영상, 차트, 이미지, 웹사이트) |
| `others` | 13 | search, get, send, read, delegate | 협업 통신 (에이전트 위임, 메시지 전송, 연락처) |

**카테고리**: 프롬프트 가독성용 분류 (런타임 영향 없음). `<action-categories>`로 표시되며 에이전트는 카테고리명이 아닌 구체적 액션명을 직접 사용해야 함.

## 설정 파일 위치
- **시스템 AI 설정**: `data/system_ai_config.json`
- **스위치 목록**: `data/switches.json`
- **프로젝트 목록**: `projects/projects.json`
- **프로젝트 에이전트**: `projects/{id}/agents.yaml`
- **시스템 AI 메모리**: `data/system_ai_memory.db` (SQLite)
- **World Pulse DB**: `data/world_pulse.db` (SQLite — pulse_log, self_checks 테이블)
- **대화 이력**: `projects/{id}/conversations.db` (SQLite)
- **도구 패키지**: `data/packages/installed/tools/`
- **비즈니스 DB**: `data/business.db` (SQLite)
- **IBL 사용량 DB**: `data/ibl_usage.db` (SQLite)
- **IBL 노드 정의**: `data/ibl_nodes.yaml`
- **IBL 출처 추적**: `data/_ibl_provenance.yaml`

## 지원 AI 프로바이더 (모두 스트리밍 지원)
- **Anthropic Claude**: claude-sonnet-4-20250514, claude-3-5-haiku-20241022, claude-3-5-sonnet-latest
- **OpenAI GPT**: gpt-4o, gpt-4o-mini
- **Google Gemini**: gemini-2.0-flash-exp, gemini-1.5-pro, gemini-1.5-flash
- **Ollama**: 로컬 LLM (llama3.2 등)

### Tool Result 절삭
- **기본 한도**: 16KB — tool result가 이 크기를 초과하면 절삭
- **파이프라인 시**: `_action_count × 16KB` 허용 (다중 액션 실행 시 비례 확장)

### 감각 전처리 (Sensory Preprocessing)
- 정보성 액션의 출력을 경량 AI(flash-lite)로 압축하여 컨텍스트 폭발 방지
- `ibl_actions.yaml`의 `postprocess` 블록으로 액션별 선언적 설정
- 적용 액션: `search_ddg`, `crawl`, `search_news`, `travel`
- 구현: `ibl_engine.py`의 `_postprocess()` → `_pp_compress()`

### 패키지 YAML 자동 동기화
- 서버 시작 시 `_auto_register_packages()`가 각 패키지 `ibl_actions.yaml`의 mtime을 `ibl_nodes.yaml`과 비교
- 변경된 패키지만 `register_actions()`로 재등록, 미등록은 항상 등록
- 패키지 YAML이 source of truth, `ibl_nodes.yaml`은 파생 파일

## 물리적 구조 (주요 경로)
- `backend/`: 서버 소스 코드
- `backend/providers/`: AI 프로바이더 (스트리밍)
- `data/`: 시스템 설정 및 데이터
- `data/packages/installed/tools/`: 설치된 도구 패키지 (35개)
- `data/api_registry.yaml`: API 도구 정의 (node 필드로 IBL 자동 병합, 현재 2개 액션)
- `data/packages/installed/extensions/`: 설치된 확장 패키지 (9개)
- `projects/`: 사용자 프로젝트 데이터 (20개)

## 프롬프트 구조

### XML 태그 구조 (2026-01-20 통일)
모든 프롬프트에서 AI의 정확한 파싱을 위해 XML 태그 사용:

**프래그먼트 (fragments/)**
- `<git_operations>` - Git 작업 가이드
- `<agent_delegation>` - 에이전트 위임 가이드

**히스토리 메시지 (providers/*.py)**
- `<user_message>` - 사용자 메시지
- `<assistant_message>` - AI 응답
- `<current_user_request>` - 현재 요청

**자동응답 V3 (auto_response.py - Tool Use 통합)**
- `<current_context>` - 현재 컨텍스트 (이웃 정보, 근무지침, 비즈니스 문서, 대화 기록)
- Tool Use 기반으로 판단/검색/발송을 단일 AI 호출로 처리

---
*마지막 업데이트: 2026-03-29 (감각 전처리 시스템, 패키지 YAML 자동 동기화)*
