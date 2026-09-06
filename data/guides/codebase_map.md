# 코드베이스 구조 (codebase_map)

> 자동 생성 — 직접 편집하지 마라. 원본은 `data/system_docs/system_structure.md` 의 CODEBASE_MAP 구간이다. 거기서 고치면 다음 로드 때 이 파일이 갱신된다.

## 아키텍처

```
indiebizOS/
├── backend/              # Python FastAPI 백엔드 (포트 8765) — .py 수는 architecture '시스템 통계'(빌드 파생)
│   │   # ★층=디렉토리(2026-08-05 물리 이동). 의존은 아래→위 한 방향만:
│   │   #   base → datastore → ibl → cognition → services → surface
│   │   #   가드=scripts/check_backend_layers.py (LAYERS 배정·역방향 간선·교차층 순환 금지,
│   │   #   동결 부채 BASELINE 7간선은 신규 추가 금지). pre-commit + self-check 합류.
│   │   # ★모듈 이름은 평면 유지(`import ibl_engine`) — backend/boot_paths.py 가 층 경로를
│   │   #   sys.path 에 얹는다. 새 backend 모듈 = 층 폴더에 두고 LAYERS 에 배정,
│   │   #   스크립트는 맨 위에 `import boot_paths`.
│   ├── api.py           # 메인 서버 엔트리포인트 (조립 층 — 층 검사 밖)
│   ├── boot_paths.py / boot_common.py # 층 경로 부트스트랩 · 공용 기동
│   │
│   ├── base/            # 의존 없는 바닥(유틸·OS·프로토콜)
│   │   ├── model_resolver.py # 모델 기어 — 역할→축→기어→티어→모델 단일 리졸버 (핫리로드)
│   │   ├── episode_logger.py # 에피소드(주행기록) 로깅 — 채팅·HTTP·위임·외부채널 전 경로
│   │   ├── thumbnails.py / hls_ladder.py # 썸네일·스트리밍 트랜스코드 · HLS 적응형 사다리
│   │   ├── desktop_notify.py # OS 네이티브 알림 폴백(의존성 0 — osascript/PowerShell/notify-send)
│   │   ├── phone_jobs.py     # 푸시 큐(폰·USB 손발 공용 아웃바운드 큐)
│   │   ├── limb_keys.py / device_registry.py # 손발 자격 원장 · 몸 등록부(capability)
│   │   ├── window_requests.py # 창 열기 pending-queue (층 역전 방지용 단일 저장소)
│   │   ├── safe_store.py / repeat_guard.py / steer_inbox.py / thread_context.py
│   │   └── nip17.py / nip44.py / r2_client.py / korean_utils.py / runtime_utils.py …
│   │
│   ├── datastore/       # 원장·DB(층 이름은 'data' 지만 런타임 폴더와 충돌해 디렉토리는 datastore)
│   │   ├── ibl_usage_db.py   # IBL 해마 DB (벡터 검색 + FTS5)
│   │   ├── forage_memory.py  # 포식 기억(공간 지도 + 주인 모델)
│   │   ├── business_manager.py / calendar_manager.py / conversation_db.py / multi_chat_db.py
│   │   ├── project_manager.py / agent_registry.py / package 원장 · system_docs.py
│   │   ├── notify_dispatch.py # 알림 도달 단일 관문(알림함→런처 WS→데스크탑 폴백)
│   │   ├── red_grant.py / red_report.py / red_watchdog.py # 자기수정(REPAIR) 한도·원장·회수 워치독
│   │   ├── warehouse_items.py / warehouse_catalog.py / warehouse_directory.py
│   │   ├── peer_cards.py / body_trust.py # 이웃 몸 명함 캐시 · 몸 신뢰=이웃 등급
│   │   └── boot_status.py / pulse_db.py / file_index.py / focus_map.py / xray_stream.py …
│   │
│   ├── ibl/             # 언어(파서·엔진·라우팅·도구 로딩)
│   │   ├── ibl_parser.py (+ ibl_parser_blocks.py / ibl_parser_values.py) # 구문 파서·블록·값
│   │   ├── ibl_engine.py     # 실행 엔진 코어 (조합 연산자 `>>`·`&`·`??`, 재귀 깊이 상한 3)
│   │   ├── ibl_executors.py / ibl_routing.py # 실행기 · 9종 라우터(handler·system·driver 등)
│   │   ├── ibl_access.py     # 접근 계층 (설치된 어휘만 로드 — 남의 어휘 배제)
│   │   ├── ibl_safety.py     # 부작용 선언(dry-run 게이팅 — 반환값 추론 아닌 자체 선언)
│   │   ├── ibl_translate.py  # 조종실 번역(자연어→IBL) · ibl_ops.py / ibl_param_vocab.py
│   │   ├── workflow_engine.py / event_engine.py / trigger_engine.py / channel_engine.py
│   │   ├── package_manager.py / tool_loader.py / tool_selector.py / tool_context.py
│   │   ├── capability_card.py # 명함(desc-프로젝션, 자기 어휘만)
│   │   └── api_engine.py / api_pipeline.py / api_transforms.py # ★이름만 api_* — 라우터 아님
│   │   #   빌드: scripts/build_ibl_nodes.py (소스 data/ibl_nodes_src/ → 산출물 data/ibl_nodes.yaml)
│   │   #   검증: --check 가 src↔tool.json↔handler.py(_OP_DISPATCHERS) 삼각 일치 AST 정확 비교
│   │   #   게이트: scripts/git-hooks/pre-commit + world_pulse_health(하루 1회 건강 점검)
│   │   #   ★파생 방향(어디를 고치면 어디로 흐르나 — 헛다리 방지, 2026-08-18 실측):
│   │   #     data/ibl_nodes_src/*.yaml        → data/ibl_nodes.yaml (액션 선언·description)
│   │   #     패키지 ibl_actions.yaml 의 tool_json 블록 → 그 패키지 tool.json **만**
│   │   #       (ibl_nodes.yaml 에는 안 간다 — 파라미터 설명을 고치고 ibl_nodes.yaml 을
│   │   #        grep 하면 안 나오는 게 정상. 정합 확인은 --check 의 'tool.json 파생 일치')
│   │   #     패키지 handler.py                → /packages/reload 로 즉시 반영
│   │   #     패키지 tool_*.py(서브모듈)       → **reload 밖** — 워커 재기동해야 반영
│   │
│   ├── cognition/       # 인지(분류→의식→실행→평가→증류)
│   │   ├── agent_runner.py   # 에이전트 실행 엔진 (파이프라인 오케스트레이션)
│   │   ├── agent_cognitive.py # 인지 믹스인 합성 지점 + 코어
│   │   ├── cognitive_recall.py # 0단계 연상 회상 (해마+심층+포식+디스크골격+손발 프레즌스)
│   │   ├── cognitive_consciousness.py # 의식·무의식 분류·framing 캐시·SESSION_RESET
│   │   ├── cognitive_distill.py / cognitive_eval.py / cognitive_trace.py
│   │   ├── consciousness_agent.py # 의식 에이전트 — 메타 판단(골격 task_framing·assumptions) + achievement_criteria; 수리 교리는 fragments/14 를 repair 턴에만 적재
│   │   ├── goal_evaluator.py / history_checkpoint.py / prompt_builder.py
│   │   ├── system_ai_core.py / system_ai_runner.py / system_tools*.py # 시스템 AI 코어·상주·도구
│   │   ├── ibl_usage_rag.py / ibl_usage_generator.py # 실행기억 생성·경험 증류 · 합성 용례
│   │   ├── ibl_description_audit.py # 설명 의미 드리프트 점검(주 1회 self-check 합류)
│   │   ├── vocab_crystallization.py / vocab_overlap_audit.py # 결정화 감지 · 어휘 중복 감사
│   │   ├── forage_consolidation.py / memory_consolidation.py # 기억 정리 패스
│   │   ├── body_ask.py       # 자연어 부탁 수신 — 자기 사전으로 컴파일→실행→통화
│   │   └── world_pulse.py / world_pulse_health.py / world_pulse_collectors.py # 자의식·면역 순찰
│   │
│   ├── services/        # 바깥 세계(스케줄·채널·NAS·발급)
│   │   ├── scheduler.py / channel_poller.py # 스케줄러 · 채널 폴링(수신 단일 관문)
│   │   ├── indienet*.py      # IndieNet(Nostr) 코어·발행·릴레이·소셜
│   │   ├── warehouse_feed.py # 이웃 창고 폴러(30분 diff, seed/new/changed) + 자격 로그인
│   │   ├── warehouse_adapters.py # 방언 어댑터(native/autoindex/RSS·Atom/Nextcloud/Neocities/page)
│   │   ├── ingest_engine.py  # 공용 적재 엔진(다형 입력→구조화→원장) — health·finance 소비
│   │   ├── cdn_provision.py / ffmpeg_provision.py / hippocampus_provision.py # 발급·조달
│   │   ├── nas_music.py / nas_subtitle.py / nas_webapp.py # NAS
│   │   ├── auto_response.py / business_sync.py / calendar_actions.py / report_html.py
│   │   └── gen_newspaper.py / generate_newspaper.py / nostr_phone_bridge.py …
│   │
│   ├── surface/         # 바깥 얼굴(HTTP 라우터·런처·공개면). 프리픽스 api_/launcher_/portal_
│   │   ├── api_ibl.py           # IBL 전용 API (조종실 translate/validate/execute/distill)
│   │   ├── api_system_ai.py / api_websocket.py # 시스템 AI · WebSocket
│   │   ├── api_agents.py / api_projects.py / api_packages.py / api_models.py / api_config.py
│   │   ├── api_nodes.py         # 몸 명함·부탁(/nodes/card·/nodes/ask)
│   │   ├── api_limb.py          # USB 손발 수신(/limb/connect·poll·result·progress)
│   │   ├── api_phone.py         # 폰 컴패니언/푸시 큐
│   │   ├── api_music.py / api_ytrelay.py # 내 음악 스트리밍 · 유튜브 릴레이(HLS)
│   │   ├── api_nas.py / api_nas_hls.py / api_nas_lite.py # NAS 서빙·적응형·경량
│   │   ├── api_xray.py          # X-ray(시스템 투시도)
│   │   ├── api_warehouse_feed.py # 이웃 창고 피드/검색 (소유자 전용)
│   │   │  # === 공개 표면 서빙(브라우저→Worker→터널→허브) ===
│   │   ├── portal_*.py / api_portal.py # 개인 포털 /h/ (게이트·인증·관리·창고면)
│   │   ├── api_showcase.py      # 공개 파일 /s/ (스트리밍 트랜스코드·자막·HLS)
│   │   ├── api_family_news.py   # 가족신문 /n/
│   │   ├── api_bulletin.py      # 자유게시판 /b/
│   │   ├── api_report.py        # 정기보고 발행 면 /r/
│   │   ├── public_face.py / face_provision.py # 직접 서빙 얼굴·프록시 · origin_host 권위
│   │   ├── warehouse_likes.py   # 좋아요·창고 점수(0~3)
│   │   │  # === 런처 웹 표면 (기질/정체 분리, 2026-07-22) ===
│   │   ├── launcher_app_*.py    # 탭별 기질 모듈 (common/warehouse/autopilot/manual/appmode)
│   │   ├── launcher_surface_remote.py # 원격 런처 조립 (PC의 일부, 5탭)
│   │   ├── launcher_surface_phone.py  # 폰 네이티브 조립 (독립 시스템, 3탭)
│   │   └── launcher_web_shell.py / launcher_web_render.py / launcher_render_core.py
│   │
│   ├── common/          # 층 밖 공용(auth_manager·http_fetch·currency·platform_utils·pkg_utils …)
│   ├── providers/       # LLM 프로바이더(anthropic·gemini(+http)·deepseek(+http)·openai·ollama·openrouter·claude_code)
│   ├── channels/        # 채널 드라이버(gmail·nostr)
│   ├── drivers/         # IBL 드라이버(sqlite 등)
│   └── test_*.py        # 회귀 배터리 (★파이프 실험 전 test_pipe_currency_failures.py 권장)
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
│   │   │   ├── tools/       # 도구 패키지 (수·목록=packages.md 빌드 파생, op 분기=_OP_DISPATCHERS 표준)
│   │   │   └── extensions/  # 백엔드 코어 모듈 (수=packages.md)
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
│   ├── system_docs/     # 시스템 AI 문서 (장기기억, 13 문서+changelog — system_structure.md 정체성 코어는 항상 프롬프트에 포함, CODEBASE_MAP 구간은 guides/codebase_map.md 로 자동 파생·온디맨드)
│   ├── guides/          # 가이드 파일 (수=architecture '시스템 통계', 의식 에이전트가 선택하여 프롬프트에 주입)
│   ├── scripts/         # 등록 스크립트 — 어휘가 아닌 절차의 거처(`[self:script]{op:run}`)
│   │   #   registry.yaml(정의) + <이름>.py. 결정화 사다리의 가운데 가로대 = 반-어휘-증식 장치.
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
│   └── system_ai_memory.db # 시스템 AI 메모리 (SQLite)
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
