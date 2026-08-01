# 코드베이스 구조 (codebase_map)

> 자동 생성 — 직접 편집하지 마라. 원본은 `data/system_docs/system_structure.md` 의 CODEBASE_MAP 구간이다. 거기서 고치면 다음 로드 때 이 파일이 갱신된다.

## 아키텍처

```
indiebizOS/
├── backend/              # Python FastAPI 백엔드 (포트 8765) — 197개 파일
│   ├── api.py           # 메인 서버 엔트리포인트
│   ├── api_*.py         # 각 모듈 라우터 (38개)
│   │   ├── api_agents.py        # 에이전트 관리
│   │   ├── api_android.py       # 안드로이드 연동
│   │   ├── api_business.py      # 비즈니스/이웃 관리
│   │   ├── api_config.py        # 설정 관리
│   │   ├── api_conversations.py # 대화 관리
│   │   ├── api_engine.py        # IBL 실행 엔진 API
│   │   ├── api_env.py           # .env 설정(API 키) UI
│   │   ├── api_gmail.py         # Gmail 연동
│   │   ├── api_health.py        # 건강 기록
│   │   ├── api_ibl.py           # IBL 전용 API (조종실 translate/validate/execute/distill)
│   │   ├── api_launcher_web.py  # 웹 런처 API  (※ api_indienet.py 제거됨 — IndieNet은 IBL 계기로만)
│   │   ├── api_limb.py          # USB 손발 수신(/limb/connect·poll·result)
│   │   ├── api_models.py        # AI 모델 관리
│   │   ├── api_multi_chat.py    # 멀티 채팅
│   │   ├── api_music.py         # 내 음악 스트리밍/커버(/music/stream·cover)
│   │   ├── api_nas.py           # NAS 연동
│   │   ├── api_nodes.py         # 몸 명함·부탁(/nodes/card·/nodes/ask)
│   │   ├── api_notifications.py # 알림
│   │   ├── api_packages.py      # 패키지 관리
│   │   ├── api_pcmanager.py     # PC 관리
│   │   ├── api_phone.py         # 폰 컴패니언/푸시 큐
│   │   ├── api_photo.py         # 사진 관리
│   │   ├── api_pipeline.py      # 파이프라인 관리
│   │   ├── api_projects.py      # 프로젝트 관리
│   │   ├── api_scheduler.py     # 스케줄러
│   │   ├── api_switches.py      # 스위치 관리
│   │   ├── api_system_ai.py     # 시스템 AI
│   │   ├── api_transforms.py    # 데이터 변환
│   │   ├── api_tunnel.py        # 터널 관리
│   │   ├── api_websocket.py     # WebSocket
│   │   ├── api_xray.py          # X-ray(시스템 투시도)
│   │   │  # === 공개 표면 서빙(브라우저→Worker→터널→허브) ===
│   │   ├── api_portal.py        # 개인 포털 /h/
│   │   ├── api_showcase.py      # 공개 파일 /s/ (스트리밍 트랜스코드·자막)
│   │   ├── api_family_news.py   # 가족신문 /n/
│   │   ├── api_bulletin.py      # 자유게시판 /b/
│   │   ├── api_report.py        # 정기보고 발행 면 /r/
│   │   └── api_warehouse_feed.py # 이웃 창고 피드/검색 (소유자 전용)
│   │
│   │   # === IBL 시스템 ===
│   ├── ibl_engine.py    # IBL 실행 엔진 코어
│   ├── ibl_parser.py    # IBL 구문 파서 (+ ibl_parser_blocks.py / ibl_parser_values.py)
│   ├── ibl_access.py    # IBL 접근 계층 (설치된 어휘만 로드 — 남의 어휘 배제)
│   ├── ibl_routing.py   # 9종 라우터 구현 (handler, system, driver 등)
│   ├── ibl_executors.py # IBL 실행기
│   ├── ibl_safety.py    # 부작용 분류(dry-run 게이팅)
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
│   │   # === 인지/자율 시스템 (3단 인지 아키텍처 + 모델 기어 변속) ===
│   ├── agent_runner.py  # 에이전트 실행 엔진 (분류→의식→실행→평가 파이프라인)
│   ├── agent_cognitive.py # 인지 믹스인 합성 지점 + 코어 (2026-07-17 모듈화)
│   ├── cognitive_recall.py # 0단계 연상 회상 (해마+심층+포식+디스크골격+손발 프레즌스)
│   ├── cognitive_consciousness.py # 의식·무의식 분류·framing 캐시·SESSION_RESET
│   ├── cognitive_distill.py # 턴 종료 후 증류 (심층+포식)
│   ├── cognitive_eval.py  # Goal 평가 루프
│   ├── cognitive_trace.py # 도구 trace 직렬화·액션 원장·자기반성
│   ├── episode_logger.py # 에피소드(주행기록) 로깅 — 채팅·HTTP·위임·외부채널 전 경로
│   ├── consciousness_agent.py # 의식 에이전트 — 메타 판단 + achievement_criteria + 메타 인지 가드(자해/의심 갱신/재시도)
│   ├── model_resolver.py # 모델 기어 — 역할→축→기어→티어→모델 단일 리졸버 (data/model_gear.json, 핫리로드)
│   ├── world_pulse.py   # Consciousness Pulse + Self-Check (자의식/면역, 6노드 전체)
│   ├── world_pulse_health.py # Self-Check 엔진 + 정적 정합성 합류 (run_static_ibl_check, build_ibl_nodes --check 통합)
│   ├── ibl_description_audit.py # IBL 설명 의미 드리프트 점검 (결정적 교차참조 + 경량 LLM, 주 1회 self-check 합류)
│   ├── goal_evaluator.py # 목표 평가 시스템
│   ├── boot_status.py   # 부팅 서브시스템 성패 계측 (/world-pulse/health 의 boot 절)
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
│   ├── notify_dispatch.py # 알림 도달 단일 관문(알림함→런처 WS→데스크탑 폴백)
│   ├── desktop_notify.py # OS 네이티브 알림 폴백(의존성 0 — osascript/PowerShell/notify-send)
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
│   │   # === 공유창고 · 공개 얼굴 (몸의 주소) ===
│   ├── public_face.py   # 직접 서빙 얼굴(터널/tailscale) + 프록시
│   ├── cdn_provision.py # Cloudflare 발급(터널·Worker·R2 캐시) — 새 몸=새 주소
│   ├── face_provision.py # 얼굴 개폐·origin_host 권위
│   ├── warehouse_feed.py # 이웃 창고 폴러(30분 diff, seed/new/changed) + 자격 로그인
│   ├── warehouse_adapters.py # 방언 어댑터(native/autoindex/RSS·Atom/Nextcloud/Neocities/page)
│   ├── warehouse_items.py # 비즈니스 아이템 → 창고 진열(파생 존)
│   ├── warehouse_likes.py # 좋아요·창고 점수(0~3)
│   ├── warehouse_catalog.py # 비즈니스 아이템 → 자족 카탈로그 HTML(data URI·지문 게이트)
│   ├── warehouse_directory.py # 이웃 창고 둘러보기(장르별 후보 — live 파싱 + 시드 목록)
│   ├── r2_client.py     # R2 캐시 클라이언트
│   ├── thumbnails.py    # 썸네일 + 공개 동영상 스트리밍 트랜스코드(fMP4·자막·오프셋)
│   ├── report_html.py   # 정기보고 md→HTML(볼 때 렌더)
│   │
│   │   # === 몸 사이 소통 (특권 배관 없음) ===
│   ├── capability_card.py # 명함(desc-프로젝션, 자기 어휘만)
│   ├── body_ask.py      # 자연어 부탁 수신 — 자기 사전으로 컴파일→실행→통화
│   ├── peer_cards.py    # 이웃 몸 명함 캐시(등록 시 상호 교환)
│   ├── body_trust.py    # 몸 신뢰 원장 = 이웃 등급(부여식)
│   ├── limb_keys.py     # USB 손발 자격 원장(발급·승인·폐기)
│   ├── phone_jobs.py    # 푸시 큐(폰·손발 공용 아웃바운드 큐)
│   ├── device_registry.py # 몸 등록부(capability·required_capability)
│   │
│   │   # === 런처 웹 표면 (기질/정체 분리, 2026-07-22) ===
│   ├── launcher_app_*.py # 탭별 기질 모듈 (common/warehouse/autopilot/manual/appmode)
│   ├── launcher_surface_remote.py # 원격 런처 표면 조립 (PC의 일부, 5탭)
│   ├── launcher_surface_phone.py  # 폰 네이티브 표면 조립 (독립 시스템, 3탭)
│   ├── launcher_web_shell.py / launcher_web_render.py # 셸 조각 · 선언형 렌더러
│   │
│   │   # === NAS 시스템 ===
│   ├── nas_music.py     # NAS 음악 스트리밍
│   ├── nas_subtitle.py  # 자막 관리
│   ├── nas_webapp.py    # 웹앱 호스팅
│   │
│   │   # === 미디어/유틸 ===
│   ├── gen_newspaper.py # 신문 생성
│   ├── generate_newspaper.py # 신문 생성 (대안)
│   ├── migrate_nodes.py # 노드 마이그레이션
│   └── migrate_health_persons.py # 건강/인물 DB 마이그레이션
│
├── helper/              # USB 손발 헬퍼 (Go 단일파일, win/mac/linux 크로스컴파일)
│
├── frontend/            # Electron + React (TypeScript)
│   ├── electron/        # 메인/프리로드
│   └── src/             # React 컴포넌트
│   #   - Launcher.tsx / ManualMode.tsx(조종실) / ActionDesktop.tsx(앱)
│   #   - GenericInstrument.tsx(매니페스트 해석 제네릭 렌더러) + escape 2층(OVERRIDES / STATIC_DOMAINS)
│   #   - WarehouseView.tsx(공유창고 파인더 + 이웃 탭[소개글/둘러보기·📣 공개 추천])
│   #   - useRetryingLoad(콜드스타트 첫 조회 재시도 — 새 화면의 규약)
│   # 주요 의존성: React 19, Electron 39, Vite 7, Tailwind CSS 4
│   # 추가: leaflet (지도), recharts (차트), zustand (상태관리)
│
├── data/                # 런타임 데이터
│   ├── packages/        # 도구 패키지 저장소
│   │   ├── installed/
│   │   │   ├── tools/       # 도구 패키지 (42개 — op 분기 27개 패키지는 _OP_DISPATCHERS 표준)
│   │   │   └── extensions/  # 백엔드 코어 모듈 (8개, ai-agent 폐기)
│   │   ├── not_installed/   # 미설치 패키지
│   │   └── dev/             # 개발 중
│   ├── ibl_nodes_src/   # IBL 액션 단일 진실 소스 (편집 위치, 노드별 yaml)
│   ├── training/        # 해마 학습 데이터
│   │   ├── ibl_distilled.json                   # 경험 증류 누적 (시딩=add_examples_batch 단일 경로)
│   │   └── _archive/                            # 옛 학습 데이터
│   ├── models/          # fine-tuned 임베딩 모델 (768차원)
│   │   └── ibl_embedding/   # 해마 시맨틱 검색용
│   ├── ibl_nodes.yaml   # IBL 전체 노드/액션 레지스트리 (빌드 산출물, 직접 편집 금지)
│   ├── model_gear.json  # 모델 기어 — 현재 기어(절약/균형/최대)·프리셋(축→티어)·에이전트 핀
│   ├── bodies/          # 몸 프로파일 (android.json 등) → 폰 엔진 번들 파생 소스 (build_body_bundle.py)
│   ├── guide_db.json    # 가이드 검색 DB
│   ├── world_pulse.db   # World Pulse DB (SQLite: pulse_log, self_checks, action_health, episode_log, episode_summary)
│   ├── system_docs/     # 시스템 AI 문서 (장기기억, 12 문서+changelog — system_structure.md 정체성 코어는 항상 프롬프트에 포함, CODEBASE_MAP 구간은 guides/codebase_map.md 로 자동 파생·온디맨드)
│   ├── guides/          # 가이드 파일 (65개 / guide_db 등록 58, 의식 에이전트가 선택하여 프롬프트에 주입)
│   ├── common_prompts/  # 공용 프롬프트 (consciousness/evaluator/unconscious + fragments)
│   ├── instruments/     # standalone 앱 매니페스트 (어휘 없는 계기, 예: report.yaml)
│   ├── warehouse.json / warehouse_feed.db  # 내 창고 설정 · 이웃 창고 스냅샷·피드
│   ├── portal_state.json / showcase_state.json / bulletin/ / family_news/  # 공개 표면 상태
│   ├── limb_keys.json / device_registry.json / peer_cards/  # 손발 자격 · 몸 등록부 · 이웃 몸 명함
│   ├── public_face.json / tunnel_config.json  # 공개 얼굴(프로바이더=권위) · 터널
│   ├── music/           # 내 음악 라이브러리 (library.db — 트랙·앨범아트·폴더. 관련곡 간선 edges 는 2026-07-28 폐기)
│   ├── webapps.json     # 웹앱 등기부의 수동 보충분(본체는 진실 소스 7곳에서 매 호출 파생)
│   ├── warehouse_directory.json # 창고 둘러보기 시드(사용자 편집 가능)
│   ├── forage_memory.db # 포식 기억 (공간 지도 + 주인 모델)
│   ├── system_ai_memory.db # 시스템 AI 메모리 (SQLite)
│   └── my_profile.txt   # 사용자 프로필
│
├── projects/            # 사용자 프로젝트
│   ├── projects.json    # 프로젝트 목록
│   └── {project_id}/    # 개별 프로젝트 폴더
│       ├── agents.yaml  # 에이전트 설정
│       └── conversations.db # 대화 이력
│
├── scripts/             # 빌드/배포 스크립트 (build_ibl_nodes.py + build_core_manifest.py[표준 코어 경계] + build_dist_filter.py[설치필터] + git-hooks/pre-commit)
│   │   # 코어/사용자 경계: data/core_manifest.json (git 파생 단일 진실) → package_manager origin(core|user) + main.js initUserData(코어만 갱신·설치상태 보존) + dist_filter(코어 기준 배포)
├── mcp_server.py        # MCP 서버 엔트리포인트
├── templates/           # 프로젝트 템플릿
└── outputs/             # 출력 파일
```
