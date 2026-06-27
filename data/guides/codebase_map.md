# 코드베이스 구조 (codebase_map)

> 자동 생성 — 직접 편집하지 마라. 원본은 `data/system_docs/system_structure.md` 의 CODEBASE_MAP 구간이다. 거기서 고치면 다음 로드 때 이 파일이 갱신된다.

## 아키텍처

```
indiebizOS/
├── backend/              # Python FastAPI 백엔드 (포트 8765) — 134개 파일
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
│   │   ├── api_launcher_web.py  # 웹 런처 API  (※ api_indienet.py 제거됨 — IndieNet은 IBL 계기로만)
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
│   ├── ibl_routing.py   # 9종 라우터 구현 (handler, system, driver 등)
│   ├── ibl_usage_db.py  # IBL 해마 DB (벡터 검색 + FTS5)
│   ├── ibl_usage_generator.py # IBL 합성 용례 생성기
│   ├── ibl_usage_rag.py # IBL 실행기억 생성 + 경험 증류
│   │   # 빌드: scripts/build_ibl_nodes.py (소스: data/ibl_nodes_src/, 산출물: data/ibl_nodes.yaml)
│   │   # 검증: --check 가 src↔tool.json↔handler.py(_OP_DISPATCHERS) 삼각 일치 AST 정확 비교
│   │   # 게이트: scripts/git-hooks/pre-commit (commit 시점) + world_pulse_health (12시간 self-check)
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
│   ├── consciousness_agent.py # 의식 에이전트 — 메타 판단 + achievement_criteria + 메타 인지 가드(자해/의심 갱신/재시도)
│   ├── world_pulse.py   # Consciousness Pulse + Self-Check (자의식/면역, 5노드 전체)
│   ├── world_pulse_health.py # Self-Check 엔진 + 정적 정합성 합류 (run_static_ibl_check, build_ibl_nodes --check 통합)
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
│   │   │   ├── tools/       # 도구 패키지 (37개 — op-bearing 10개는 _OP_DISPATCHERS 표준)
│   │   │   └── extensions/  # 백엔드 코어 모듈 (9개)
│   │   ├── not_installed/   # 미설치 패키지
│   │   └── dev/             # 개발 중
│   ├── ibl_nodes_src/   # IBL 액션 단일 진실 소스 (편집 위치, 노드별 yaml)
│   ├── training/        # 해마 학습 데이터
│   │   ├── ibl_training_balanced_20260516.json  # 학습 데이터 (android 어휘 흡수 재학습 완료 2026-06-05)
│   │   └── _archive/                            # 옛 학습 데이터
│   ├── models/          # fine-tuned 임베딩 모델 (768차원)
│   │   └── ibl_embedding/   # 해마 시맨틱 검색용
│   ├── ibl_nodes.yaml   # IBL 전체 노드/액션 레지스트리 (빌드 산출물, 직접 편집 금지)
│   ├── guide_db.json    # 가이드 검색 DB
│   ├── world_pulse.db   # World Pulse DB (SQLite: pulse_log, self_checks, action_health, episode_log, episode_summary)
│   ├── system_docs/     # 시스템 AI 문서 (장기기억, 12개 파일 — system_structure.md는 항상 프롬프트에 포함)
│   ├── guides/          # 가이드 파일 (47개, 의식 에이전트가 선택하여 프롬프트에 주입)
│   ├── common_prompts/  # 공용 프롬프트 (consciousness/evaluator/unconscious + fragments)
│   ├── system_ai_memory.db # 시스템 AI 메모리 (SQLite)
│   └── my_profile.txt   # 사용자 프로필
│
├── projects/            # 사용자 프로젝트
│   ├── projects.json    # 프로젝트 목록
│   └── {project_id}/    # 개별 프로젝트 폴더
│       ├── agents.yaml  # 에이전트 설정
│       └── conversations.db # 대화 이력
│
├── scripts/             # 빌드/배포 스크립트 (build_ibl_nodes.py + git-hooks/pre-commit)
├── mcp_server.py        # MCP 서버 엔트리포인트
├── templates/           # 프로젝트 템플릿
└── outputs/             # 출력 파일
```
