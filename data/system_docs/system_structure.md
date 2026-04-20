# IndieBiz OS 시스템 구조 가이드

시스템 관리, 확장, 디버깅, 개발 작업 시 참조하는 핵심 구조 정보.

## 개요
- **경로**: `/Users/kangkukjin/Desktop/AI/indiebizOS`
- **설명**: 개인과 소규모 비즈니스를 위한 AI 기반 통합 관리 시스템
- **핵심 가치**: 개인화, 자동화, 연결성

### 주요 기능
- **다중 프로젝트 관리**: 목적에 따른 독립적인 작업 공간
- **에이전트 팀**: 역할이 정의된 여러 AI 에이전트 간의 협업
- **도구 패키지**: 에이전트가 동적으로 로딩하여 사용하는 확장 기능
- **IBL (IndieBiz Logic)**: 정보 흐름 추상화 언어 — 통합 인터페이스로 모든 정보 소스 접근
- **스케줄러**: 정기적인 정보 수집 및 리포트 자동 생성
- **IndieNet**: 외부 메신저/이메일 연동 (Gmail, Nostr)
- **NAS 연동**: 음악 스트리밍, 자막 관리, 웹앱 호스팅

---

## 시스템 문서 (System AI 참조)
- **경로**: `/Users/kangkukjin/Desktop/AI/indiebizOS/data/system_docs/`
- 시스템 AI가 장기 기억으로 참조하는 문서들
- **파일 목록** (11개):
  - `system_structure.md` - 시스템 구조 가이드 (**항상 프롬프트에 포함** — 의식/실행/평가 에이전트)
  - `architecture.md` - 시스템 개요, 아키텍처, 설계 의도 (overview.md 통합)
  - `technical.md` - 기술 문서 (API, 설정, 경로)
  - `ibl.md` - IBL 명세 (phase26, ibl_development_plan 통합)
  - `execution_memory.md` - 실행기억 & 해마 & RAG
  - `packages.md` - 패키지 시스템 (guide_file.md 통합)
  - `inventory.md` - 프로젝트/패키지 현황 (자동 생성)
  - `communication.md` - 통신/연동 (auto_response.md 통합)
  - `delegation.md` - 위임 체인 시스템
  - `scheduler_guide.md` - 스케줄러 가이드
  - `remote_access.md` - 원격 접속 문서
  - `changelog.log` - 변경 이력

---

## 아키텍처

```
indiebizOS/
├── backend/              # Python FastAPI 백엔드 (포트 8765) — 102개 파일
│   ├── api.py           # 메인 서버 엔트리포인트
│   ├── api_*.py         # 각 모듈 라우터 (25개)
│   │   ├── api_agents.py        # 에이전트 관리
│   │   ├── api_android.py       # 안드로이드 연동
│   │   ├── api_business.py      # 비즈니스/이웃 관리
│   │   ├── api_config.py        # 설정 관리
│   │   ├── api_conversations.py # 대화 관리
│   │   ├── api_engine.py        # IBL 실행 엔진 API
│   │   ├── api_gmail.py         # Gmail 연동
│   │   ├── api_ibl.py           # IBL 전용 API
│   │   ├── api_indienet.py      # IndieNet 연동
│   │   ├── api_launcher_web.py  # 웹 런처 API
│   │   ├── api_models.py        # AI 모델 관리
│   │   ├── api_multi_chat.py    # 멀티 채팅
│   │   ├── api_nas.py           # NAS 연동
│   │   ├── api_notifications.py # 알림
│   │   ├── api_packages.py      # 패키지 관리
│   │   ├── api_pcmanager.py     # PC 관리
│   │   ├── api_photo.py         # 사진 관리
│   │   ├── api_pipeline.py      # 파이프라인 관리
│   │   ├── api_projects.py      # 프로젝트 관리
│   │   ├── api_scheduler.py     # 스케줄러
│   │   ├── api_switches.py      # 스위치 관리
│   │   ├── api_system_ai.py     # 시스템 AI
│   │   ├── api_transforms.py    # 데이터 변환
│   │   ├── api_tunnel.py        # 터널 관리
│   │   └── api_websocket.py     # WebSocket
│   │
│   │   # === IBL 시스템 ===
│   ├── ibl_engine.py    # IBL 실행 엔진 코어
│   ├── ibl_parser.py    # IBL 구문 파서
│   ├── ibl_access.py    # IBL 접근 계층
│   ├── ibl_action_manager.py # IBL 액션 관리
│   ├── ibl_routing.py   # 9종 라우터 구현 (handler, system, driver 등)
│   ├── ibl_usage_db.py  # IBL 해마 DB (벡터 검색 + FTS5)
│   ├── ibl_usage_generator.py # IBL 합성 용례 생성기
│   ├── ibl_usage_rag.py # IBL 실행기억 생성 + 경험 증류
│   ├── bootstrap_ibl_actions.py # IBL 초기화
│   │
│   │   # === 실행 엔진 ===
│   ├── workflow_engine.py # 워크플로우 오케스트레이션
│   ├── event_engine.py  # 이벤트 드리븐 시스템
│   ├── trigger_engine.py # 트리거 엔진
│   ├── channel_engine.py # 채널 추상화 계층
│   │
│   │   # === 인지/자율 시스템 (3단 인지 아키텍처 + 3단계 모델 티어) ===
│   ├── agent_runner.py  # 에이전트 실행 엔진 (분류→의식→실행→평가 파이프라인)
│   ├── agent_cognitive.py # 인지 시스템 통합
│   ├── consciousness_agent.py # 의식 에이전트 — 메타 판단 + achievement_criteria
│   ├── world_pulse.py   # Consciousness Pulse + Self-Check (자의식/면역, 5노드 전체)
│   ├── goal_evaluator.py # 목표 평가 시스템
│   │
│   │   # === 코어 모듈 ===
│   ├── ai_agent.py      # AI 에이전트 코어
│   ├── android_agent.py # 안드로이드 에이전트
│   ├── android_calibrate.py # 안드로이드 캘리브레이션
│   ├── auto_response.py # 자동 응답 시스템
│   ├── business_manager.py # 비즈니스/이웃 관리
│   ├── calendar_manager.py # 캘린더 관리
│   ├── channel_poller.py # 채널 폴링
│   ├── conversation_db.py # 대화 DB 관리
│   ├── indienet.py      # IndieNet 코어
│   ├── korean_utils.py  # 한국어 유틸리티
│   ├── logging_utils.py # 로깅 유틸리티
│   ├── multi_chat_db.py # 멀티채팅 DB
│   ├── multi_chat_manager.py # 멀티채팅 매니저
│   ├── node_registry.py # 노드 탐색/등록
│   ├── notification_manager.py # 알림 매니저
│   ├── package_manager.py # 패키지 매니저
│   ├── project_manager.py # 프로젝트 매니저
│   ├── prompt_builder.py # 프롬프트 빌더
│   ├── runtime_utils.py # 런타임 유틸리티
│   ├── scheduler.py     # 스케줄러
│   ├── switch_manager.py # 스위치 매니저
│   ├── switch_runner.py # 스위치 실행기
│   ├── system_ai_core.py # 시스템 AI 코어 (AgentRunner 싱글턴, 설정, 도구 실행)
│   ├── system_ai_runner.py # 시스템 AI 실행기 (WebSocket 상주)
│   ├── system_ai_memory.py # 시스템 AI 메모리
│   ├── system_tools.py  # 시스템 도구
│   ├── system_docs.py   # 시스템 문서 관리
│   ├── system_hooks.py  # 시스템 훅
│   ├── thread_context.py # 스레드 컨텍스트
│   ├── tool_selector.py # 도구 선택/실행
│   ├── tool_loader.py   # 도구 로더
│   ├── web_collector.py # 웹 콘텐츠 수집
│   ├── websocket_manager.py # WebSocket 매니저
│   │
│   │   # === NAS 시스템 ===
│   ├── nas_music.py     # 음악 스트리밍
│   ├── nas_subtitle.py  # 자막 관리
│   ├── nas_webapp.py    # 웹앱 호스팅
│   │
│   │   # === 미디어/유틸 ===
│   ├── gen_newspaper.py # 신문 생성
│   ├── generate_newspaper.py # 신문 생성 (대안)
│   ├── migrate_nodes.py # 노드 마이그레이션
│   ├── migrate_health_persons.py # 건강/인물 DB 마이그레이션
│   └── rebuild_usage_db.py # 사용량 DB 재구축
│
├── frontend/            # Electron + React (TypeScript)
│   ├── electron/        # 메인/프리로드
│   └── src/             # React 컴포넌트
│   # 주요 의존성: React 19, Electron 39, Vite 7, Tailwind CSS 4
│   # 추가: leaflet (지도), recharts (차트), zustand (상태관리)
│
├── data/                # 런타임 데이터
│   ├── packages/        # 도구 패키지 저장소
│   │   ├── installed/
│   │   │   ├── tools/       # 도구 패키지 (34개)
│   │   │   └── extensions/  # 백엔드 코어 모듈 (9개)
│   │   ├── not_installed/   # 미설치 패키지
│   │   └── dev/             # 개발 중
│   ├── training/        # 해마 학습 데이터
│   │   ├── ibl_synthetic_opus_final_2479.json  # 학습 데이터 (2354개, memory 액션 제거 후)
│   │   └── ibl_distilled.json                  # 경험 증류 누적 데이터
│   ├── models/          # fine-tuned 임베딩 모델 (768차원)
│   │   └── ibl_embedding/   # 해마 시맨틱 검색용
│   ├── ibl_nodes.yaml   # IBL 전체 노드/액션 레지스트리
│   ├── guide_db.json    # 가이드 검색 DB
│   ├── world_pulse.db   # World Pulse DB (SQLite: pulse_log, self_checks, action_health, episode_log, episode_summary)
│   ├── system_docs/     # 시스템 AI 문서 (장기기억, 11개 파일 — system_structure.md는 항상 프롬프트에 포함)
│   ├── guides/          # 가이드 파일 (28개, 의식 에이전트가 선택하여 프롬프트에 주입)
│   ├── system_ai_memory.db # 시스템 AI 메모리 (SQLite)
│   └── my_profile.txt   # 사용자 프로필
│
├── projects/            # 사용자 프로젝트
│   ├── projects.json    # 프로젝트 목록
│   └── {project_id}/    # 개별 프로젝트 폴더
│       ├── agents.yaml  # 에이전트 설정
│       └── conversations.db # 대화 이력
│
├── scripts/             # 빌드/배포 스크립트
├── mcp_server.py        # MCP 서버 엔트리포인트
├── templates/           # 프로젝트 템플릿
└── outputs/             # 출력 파일
```

---

## 핵심 컴포넌트

### IBL (IndieBiz Logic) 시스템
- AI의 신경계 — 모든 정보 소스를 통합하는 정보 흐름 추상화 언어
- **패턴**: `[node:action]{params}` — (target) 문법은 폐지됨, 모든 값은 params에
- **5개 노드**: sense(88), self(92), limbs(79), others(12), engines(40) — 총 **311 액션**
- Phase 24에서 verb 시스템 제거, category 태그로 대체 (순수 표시용)
- 드라이버 기반 프로토콜 추상화 (HTTP, WebSocket, ADB, CDP, SQLite, File I/O)
- 병렬 실행 (`&` 연산자), 폴백 패턴 (`??` 연산자), 순차 실행 (`>>` 연산자) 지원
- 파일: `backend/ibl_engine.py`, `backend/ibl_parser.py`, `backend/ibl_access.py`, `backend/ibl_action_manager.py`, `backend/api_ibl.py`

### 시스템 AI
- IndieBiz의 관리자이자 안내자
- 사용자 정보(단기기억)와 시스템 문서(장기기억) 참조
- 프로젝트 에이전트와 동일한 AgentRunner 인지 파이프라인 사용 (`_is_system_ai` 플래그로 분기)
- 파일: `backend/system_ai_core.py` (싱글턴/설정), `backend/agent_cognitive.py` (인지 파이프라인), `backend/api_system_ai.py`

### 3단 인지 아키텍처 + 3단계 모델 티어 (Phase 28 → Phase 30)
인간의 인지 과정을 모델링: **분류(반사) -> 의식(계획) -> 실행 -> 평가(성찰)**
비용/속도 최적화를 위한 3단계 모델 티어: **경량 / 중급 / 본격**

**3단계 모델 티어:**
| 레벨 | 용도 | 설정 파일 |
|------|------|----------|
| 경량 (lightweight) | 분류, 평가, 원샷 판단 | `data/lightweight_ai_config.json` |
| 중급 (midtier) | EXECUTE/Reflex 경로 실행 | `data/midtier_ai_config.json` |
| 본격 (system_ai) | THINK 경로 의식+실행 | `data/system_ai_config.json` |

- **경량 AI (분류/평가)**: 경량 게이트키퍼
  - 요청을 EXECUTE(단순) / THINK(복잡)로 분류. EXECUTE는 의식 에이전트 건너뜀
  - 달성 기준 평가에도 사용 (`lightweight_ai_call()`)
  - 파일: `data/common_prompts/unconscious_prompt.md`, `agent_cognitive._classify_request()`
  - 프로바이더: `consciousness_agent._get_lightweight_provider()` (싱글턴)
- **중급 모델 전환**: EXECUTE/Reflex 경로에서 실행 에이전트의 provider를 중급 모델로 임시 교체
  - 전환: `system_ai_core._switch_to_midtier()` → 실행 → `_restore_provider()`
  - 중급 설정이 없으면 본격 모델 그대로 사용 (하위호환)
  - 프로바이더: `consciousness_agent._get_midtier_provider()` (싱글턴)
- **의식 에이전트 (Consciousness Agent)**: 복잡 요청에 대한 메타적 판단
  - **히스토리 요약**: 현재 문제 관련 맥락만 추려 요약
  - **태스크 프레이밍**: 도구 한계를 인식한 상태에서 문제 정의
  - **달성 기준 (achievement_criteria)**: 별도 필드로 출력 — 평가 에이전트가 활용
  - **IBL 포커싱**: 관련 노드/액션에 대한 힌트 제공 (제한이 아닌 초점 설정)
  - **가이드 파일 선택**: 읽어야 할 가이드 파일 지정
  - **상황 메모**: 세계 상태, 사용자 성향 등 배경 정보 주입
  - 파일: `backend/consciousness_agent.py`, `data/common_prompts/consciousness_prompt.md`
- **평가 에이전트 (Evaluator Agent)**: 실행 후 achievement_criteria 대비 결과 평가
  - NOT_ACHIEVED 시 피드백과 함께 재실행 (최대 3라운드)
  - 파일: `data/common_prompts/evaluator_prompt.md`, `agent_cognitive._run_goal_evaluation_loop()`
- 시스템 AI와 프로젝트 에이전트 모두에 적용 (내부 위임 제외)
- 경량/중급 AI의 API 키가 비어있으면 시스템 AI 키를 자동 사용

### Consciousness Pulse (자의식 시스템)
- 매 1시간 세계/사용자/자신 상태 업데이트 (세계 인식)
  - world: 경제 delta + 날씨 (매시간), 뉴스 (6시간마다)
  - user: 대화 수, 미처리 태스크, 다가오는 일정
  - self: 서비스 alive 체크, 디스크, 자가점검 결과
- **AI 건강 체크**: 매 6시간 시스템 AI가 미확인/실패 액션을 능동적으로 테스트 (기존 Self-Check 대체)
- **액션 건강 기록 (`action_health` 테이블)**: 모든 IBL 액션 실행 시 성공/실패를 자동 기록. 3단계 상태: verified(7일 이내 성공), assumed(기록 없음), failed(최근 실패)
- 파일: `backend/world_pulse.py`, `backend/world_pulse_health.py`, `data/world_pulse.db`
- API: `/world-pulse/consciousness`, `/world-pulse/self-checks`, `/world-pulse/health`

#### 에피소딕 메모리 (Episode Log)
- 사용자 명령 → 최종 응답까지의 한 에피소드를 로그로 기록
- **`episode_log` 테이블**: 전체 실행 로그 (최근 100개 보존, 오래된 것 자동 삭제)
- **`episode_summary` 테이블**: 요약 지표 영구 보존 (해마 점수, 무의식 판정, 의식 소요시간, 실행 라운드, 총 소요시간, 평가 결과)
- DB: `data/world_pulse.db`
- 파일: `backend/episode_logger.py`
- API: `/xray/episodes`, `/xray/episodes/{id}`, `/xray/episode-summaries`

### 목표 평가 시스템
- 목표/시간/조건 기반 평가
- 파일: `backend/goal_evaluator.py`

### 워크플로우 & 이벤트 엔진
- 파이프라인 기반 워크플로우 오케스트레이션
- 캘린더 연동 이벤트 트리거
- 파일: `backend/workflow_engine.py`, `backend/event_engine.py`, `backend/trigger_engine.py`, `backend/channel_engine.py`

### 프로젝트 매니저
- 프로젝트/에이전트 CRUD, 템플릿 기반 생성
- 파일: `backend/project_manager.py`

### 도구 패키지 시스템
- 폴더 기반 탐지 (폴더 존재만으로 인식)
- 동적 로딩, AI 친화적 구조
- 각 패키지는 `data/packages/installed/tools/{패키지ID}/`에 위치
- 패키지 구조:
  ```
  {패키지ID}/
  ├── handler.py         # 필수 — execute(tool_name, tool_input, project_path) 함수
  ├── tool.json          # 필수 — 도구 정의 (이름, 설명, input_schema)
  ├── ibl_actions.yaml   # IBL 액션 정의
  ├── __init__.py        # 빈 파일
  └── *.py               # 추가 모듈
  ```
- 파일: `backend/package_manager.py`, `backend/tool_loader.py`

### 에이전트 러너
- AI 에이전트 실행 및 대화 관리
- 파일: `backend/agent_runner.py`

### 멀티채팅
- 여러 에이전트와의 동시 대화 관리
- 파일: `backend/multi_chat_manager.py`, `backend/multi_chat_db.py`, `backend/api_multi_chat.py`

### 비즈니스/이웃 관리
- 비즈니스 관계 및 연락처 관리
- 파일: `backend/business_manager.py`, `backend/api_business.py`

### 스위치 시스템
- 스위치 기반 실행 관리
- 파일: `backend/switch_manager.py`, `backend/switch_runner.py`, `backend/api_switches.py`

### NAS 시스템
- 네트워크 스토리지 연동: 음악 스트리밍, 자막 관리, 웹앱 호스팅
- 파일: `backend/nas_music.py`, `backend/nas_subtitle.py`, `backend/nas_webapp.py`, `backend/api_nas.py`

### 해마 (실행기억 시스템)
- fine-tuned 임베딩 모델 기반 시맨틱 검색 (768차원)
- 사용자 자연어 → 과거 IBL 코드 용례 연상
- 경험 증류: 성공한 실행을 자동 학습 데이터로 축적
- 파일: `backend/ibl_usage_db.py`, `backend/ibl_usage_rag.py`
- 학습 데이터: `data/training/ibl_distilled.json`
- 모델: `data/models/ibl_embedding/`

---

## 설치된 도구 패키지 (34개)
| 패키지 | 설명 |
|--------|------|
| blog | 블로그 RAG 검색 및 인사이트 분석 |
| browser-action | Playwright 기반 브라우저 자동화 (클릭/입력/스크롤/콘텐츠 추출) |
| business | 비즈니스 관계 및 연락처(이웃) 관리 |
| cctv | CCTV 관련 도구 |
| cloudflare | Cloudflare 서비스 통합 (Pages, Workers, R2, D1, Tunnel) |
| computer-use | 컴퓨터 자동화/사용 추적 |
| context7 | Context7 라이브러리 문서 검색 |
| culture | 문화/예술 정보 (공연, 도서, 전시, Project Gutenberg 고전 원문, 한국고전종합DB) |
| health-record | 건강 기록 관리 |
| ibl-core | IBL 핵심 인프라 |
| investment | 투자 정보 및 분석 |
| kosis | 통계청 KOSIS API |
| legal | 대한민국 법률 정보 검색 (법령, 판례, 행정규칙 등) |
| local-info | 지역 정보 서비스 |
| location-services | 위치 기반 서비스 (날씨, 맛집, 길찾기, 여행 정보) |
| media_producer | 홍보용 슬라이드/영상/AI 이미지 생성 |
| memory | 심층 메모리 (자동 시스템: 연상기억 검색 + 경험 증류. IBL 액션 없음) |
| music-composer | ABC 악보 기반 작곡, MIDI 생성, 오디오 변환 |
| nodejs | JavaScript/Node.js 코드 실행 |
| pc-manager | 파일 및 저장소 관리 |
| photo-manager | 사진 관리 및 인덱싱 |
| python-exec | Python 코드 실행 |
| radio | 인터넷 라디오 검색 및 재생 (Radio Browser API + 한국 방송사 직접 스트리밍) |
| real-estate | 부동산 정보 (네이버, 국토부 API) |
| remotion-video | React/Remotion 기반 프로그래밍 방식 동영상 생성 |
| shopping-assistant | 네이버 쇼핑, 다나와 가격 비교 |
| startup | 창업 정보 및 지원 |
| study | 학습 도구 |
| system_essentials | 파일 관리, todo, 계획 모드, 이웃 조회 |
| visualization | 데이터 시각화 도구 |
| web | 웹 검색, 크롤링, 뉴스, 신문 생성, 즐겨찾기 |
| web-builder | 웹사이트 빌더 및 생성 도구 |
| web-collector | 웹 콘텐츠 수집/집계 |
| youtube | 유튜브 동영상/오디오 관리 |

## 백엔드 코어 모듈 (extensions/) - 9개
| 모듈 | 설명 |
|--------|------|
| ai-agent | AI 에이전트 실행 |
| conversation | 대화 DB 관리 |
| gmail | Gmail 연동 |
| indienet | 외부 메신저 연동 (Nostr) |
| notification-system | 알림 시스템 |
| prompt-generator | 프롬프트 생성기 |
| scheduler | 스케줄러 |
| switch-runner | 스위치 실행기 |
| websocket-chat | WebSocket 채팅 |

---

## 활성 프로젝트 (20개)
| 프로젝트 | 설명 |
|----------|------|
| 하드웨어 | 하드웨어 관리 |
| 컨텐츠 | 컨텐츠 제작 |
| 행정_서비스 | 정부24 및 민원 서비스 |
| 투자 | 주식, 채권, ETF 자산 관리 |
| 의료 | 건강 정보 관리 및 병원/약국 안내 |
| 부동산 | 건물 관리 및 부동산 투자 정보 |
| 창업 | 비즈니스 모델 연구 및 창업 지원 |
| 오락실 | 게임/엔터테인먼트 |
| 정보센터 | 정보 수집/분석 |
| study | 학습 프로젝트 |
| 사진 | 사진 관리 |
| 추천 프로젝트 | 추천 시스템 |
| 홍보 | 홍보/마케팅 |
| 구매 | 구매/쇼핑 관리 |
| 법률 | 법률 정보 및 법령 검색 |
| 음악 | 음악 스트리밍/관리 |
| CCTV | 보안 카메라 관리 |
| 지역정보 | 지역 정보 서비스 |
| 건축 | 건축/인테리어 디자인 |
| 학교 | 학교 관련 |

---

## 새 액션 추가 시 필수 체크리스트

1. 패키지 파일 생성 (handler.py, tool.json, ibl_actions.yaml)
2. `register_actions('패키지ID')` 실행 → ibl_nodes.yaml 등록
3. 해마 합성 데이터 생성 → DB + `data/training/ibl_distilled.json`
4. 임베딩 재구축 → `rebuild_index()` (서버 Python 환경에서 실행)
5. 확인: 등록 + 해마 연상 + 실제 실행

상세: `data/guides/new_action_checklist.md` 참조

---

## 데이터 흐름
```
사용자 → Electron (React UI) → HTTP/WebSocket → FastAPI 백엔드
                                                      ↓
                                              프로젝트/에이전트 관리
                                                      ↓
                                              경량 AI (EXECUTE/THINK 분류)
                                                ↓ THINK              ↓ EXECUTE
                                              의식 에이전트        실행 에이전트 [중급 모델]
                                              (문제 정의 + 달성 기준)
                                                      ↓
                                              실행 에이전트 [본격 모델]
                                                      ↓
                                              최상위 도구 9개 (IBL + Python/Node/Shell + 인지 도구 + 가이드)
                                                      ↓
                                              IBL 엔진 → 도구 패키지 동적 로딩 및 실행
                                                      ↓
                                              평가 에이전트 (달성 기준 대비 평가, 최대 3라운드)
                                                      ↓
                                              워크플로우/이벤트 엔진 → NAS/외부 서비스
```

---

## 실행 방법
```bash
# 개발 모드
cd /Users/kangkukjin/Desktop/AI/indiebizOS
./start.sh

# 개별 실행
cd backend && python3 api.py      # 백엔드
cd frontend && npm run electron:dev  # 프론트엔드

# 빌드
cd frontend
npm run electron:build:mac  # macOS
npm run electron:build:win  # Windows
```

## 개발 규칙

### 설계 원칙
1. **최소주의**: 핵심 기능만 코어에 포함
2. **확장성**: 도구 패키지로 기능 확장 (동적 로딩)
3. **독립성**: 각 컴포넌트는 독립적으로 동작
4. **AI 친화적**: 형식보다 내용, AI가 이해할 수 있는 구조
5. **IBL 우선**: 새로운 기능은 IBL 패턴으로 추상화

### 코드 스타일
- Python: PEP8, 한글 주석 OK
- TypeScript: 프로젝트 ESLint 설정 따름
- **파일 크기 제한**: 각 파일은 1500줄을 넘지 않도록 모듈화할 것

### Git
- 민감 정보 커밋 금지 (API 키, 토큰)
- 커밋 메시지: 한글/영어

---

*마지막 업데이트: 2026-04-06*
