---
title: 시스템 구조 가이드
scope: 프롬프트 주입용 — 자기 인식, 디렉토리 구조, 인지 파이프라인 (의식·실행·평가에 자동 주입)
owner_code: prompt_builder.py, consciousness_agent.py, agent_cognitive.py (모두 자동 로드)
last_updated: 2026-08-06
see_also: [architecture.md, memory.md]
---

# IndieBiz OS 시스템 구조 가이드

시스템 관리, 확장, 디버깅, 개발 작업 시 참조하는 핵심 구조 정보.

## 개요
- **경로**: `/Users/kangkukjin/Desktop/AI/indiebizOS`
- **설명**: AI 기반 통합 관리 시스템 (IBL 추상화 위에서 개인·조직 규모 무관하게 동작)
- **핵심 가치**: 개인화, 자동화, 연결성

### 주요 기능
- **런처 3표면 (트릴레마)**: 같은 IBL 위 세 모드 — **자율주행**(의도→AI 다단계, 구 '프로젝트') / **조종실**(구 '수동'→'계기판'→2026-07-03 개명. 경량모델이 자연어→IBL 번역→dry-run 검수→실행하는 컴파일러 프론트엔드 + 시스템 상태·모델 기어·프레즌스·주행기록 — 자율주행 포함 전체를 감독·개입하는 주권 기관. `api_ibl.py`+`ManualMode.tsx`, 내부 탭 키는 `manual` 유지) / **앱**(아이콘 GUI로 직접 조작, `ActionDesktop`+계기 — 부동산·도서검색). {속도·표현력·주권} 중 둘.
- **다중 프로젝트 관리**: 목적에 따른 독립적인 작업 공간
- **에이전트 팀**: 역할이 정의된 여러 AI 에이전트 간의 협업
- **도구 패키지**: 에이전트가 동적으로 로딩하여 사용하는 확장 기능
- **IBL (IndieBiz Logic)**: 정보 흐름 추상화 언어 — 통합 인터페이스로 모든 정보 소스 접근
- **스케줄러**: 정기적인 정보 수집 및 리포트 자동 생성
- **IndieNet**: 외부 메신저/이메일 연동 (Gmail, Nostr)
- **공유창고**: 몸(노드)의 공개 얼굴 — `공유창고/0..4/` 폴더가 노드 주소에서 그대로 서빙(색인·변환 없음, 파일시스템이 진실). 사람은 브라우저로, 남의 AI는 `/manifest`(JSON)로 읽는다. 레벨 0~4 = 이웃 CRM 등급과 같은 자(등급 위 파일은 403 아닌 **404**). 읽는 쪽=이웃 창고 폴러(30분, 방언 어댑터로 nginx 색인·RSS·Nextcloud·일반 웹페이지까지 같은 통화로 정규화) + 리트윗(`.url` 포인터 파일). → communication.md
- **몸 사이 소통(명함·부탁)**: 공유 사전 RPC 대신 **명함**(`GET /nodes/card`)+**자연어 부탁**(`POST /nodes/ask`, 어휘 `[others:ask]`) — 받는 몸이 *자기 사전*으로 컴파일·실행해 통화로 돌려준다. 신뢰=이웃 등급(body_trust), 특권 배관 없음. → communication.md
- **USB 손발**: 낯선 PC 에 USB 로 꽂는 얇은 몸(`[self:limb]` 발급 / `[limbs:guestpc]` 조작). 두뇌·신원은 허브에 남고 USB 엔 limb key 하나. 헬퍼가 허브로 아웃바운드 접속(폰 푸시 큐 재사용).
- **NAS 연동**: 음악 스트리밍, 자막 관리, 웹앱 호스팅 (내 음악 라이브러리는 별도 `[self:music]`)

---

## 시스템 문서 (System AI 참조)
- **경로**: `/Users/kangkukjin/Desktop/AI/indiebizOS/data/system_docs/`
- 시스템 AI가 장기 기억으로 참조하는 문서들
- **파일 목록** (12 문서 + changelog):
  - `system_structure.md` - 시스템 구조 가이드 (**항상 프롬프트에 포함** — 의식/실행/평가 에이전트)
  - `anatomy.md` - **해부도(정문)** — 신참용 전체 지도(철학→3표면→IBL→인지→메모리→검색브라우저→몸), 각 상세 문서 허브
  - `vision.md` - **비전: 인지 외골격** — 목표(자율 아닌 융합)·개발 북극성=착용감. 모든 설계 결정의 최상위 기준
  - `architecture.md` - 시스템 개요·아키텍처·설계 의도 (구 overview.md 오브젝트/에이전트 유형 흡수)
  - `technical.md` - 기술 문서 (API, 설정, 경로)
  - `ibl.md` - IBL 명세(6-Node·op 어휘화·삼각 검증) + **설계 철학**(구 ibl_design_philosophy.md)
  - `memory.md` - 메모리 7종 통합 지도 + **연상기억 심층**(해마·심층메모리 — 구 memory_architecture.md + execution_memory.md)
  - `packages.md` - 패키지 시스템 (40개 도구 + 8개 extensions, ai-agent 폐기)
  - `inventory.md` - 프로젝트/패키지 현황 (자동 생성)
  - `communication.md` - 통신/연동 + **위임 체인**(구 delegation.md)
  - `scheduler_guide.md` - 스케줄러 가이드
  - `remote_access.md` - 원격 접속 문서
  - `changelog.log` - 변경 이력

---

<!-- CODEBASE_MAP:START -->
## 아키텍처

```
indiebizOS/
├── backend/              # Python FastAPI 백엔드 (포트 8765) — 198개 파일
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
│   │   │   ├── tools/       # 도구 패키지 (40개 — op 분기 패키지는 _OP_DISPATCHERS 표준)
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
<!-- CODEBASE_MAP:END -->

---

## 인지 파이프라인 (연상 → Reflex/무의식 → 의식 → 실행 → 평가)

사용자 메시지가 들어오면 다음 순서로 처리된다. 모든 에이전트(시스템 AI / 프로젝트 에이전트)가 동일한 단계를 밟는다.

```
[0] 연상 단계        — 해마(IBL 사례) + 심층메모리(연상기억) 검색 1회로 자료 묶음
                       (top_score, top_code 함께 추출 — 중복 검색 제거)
     ↓
[1] Reflex 분기      — top_score ≥ 0.85 이면 무의식 호출 스킵, 곧장 EXECUTE
     ↓ 미만
[1B] 무의식 분류     — 경량 AI로 EXECUTE / THINK 판정
     ↓
EXECUTE                                THINK ( = "framing이 필요하다"는 수요)
   │                                     ↓
   │                              [2] framing 재고 확인 (_run_consciousness_or_reuse)
   │                                  ├─ 재고 있고 fit? → 재사용(criteria만 갱신, 의식 Opus 스킵)
   │                                  └─ 없음/안맞음 → 의식 에이전트(본격 AI): task_framing / achievement_criteria / …
   ↓                                     ↓
[3] 실행 에이전트
     · Reflex(해마 고확신)  → 중급 모델로 전환
     · EXECUTE / THINK     → 본격 모델 유지 (무의식 EXECUTE 오분류여도 품질 방어)
     · 도구: execute_ibl + run_command + read_guide + 인지도구(4) — Python/Node.js는 [self:write]→run_command 패턴
   ↓
[4] 평가 루프        — achievement_criteria 있을 때만 (경량 AI, 최대 3라운드)
   ↓
[5] 증류             — 해마 경험 증류 + 심층메모리 증류 (자동)
```

**모델 기어 (계기판 변속, 2026-06-30):** 자동차 기어처럼 레버 하나로 시스템 전체 모델 등급을 변속. 자동 변속기(무의식 분류기=작업마다 티어 자동선택) 위의 **수동 변속 레버**. `backend/model_resolver.py`가 *역할 → 축 → 기어 → 티어 → 모델*로 해소하고 매 호출 읽기(핫리로드, `/model-gear` REST). 설정=`data/model_gear.json`.
- **3 티어 = 모델 슬롯** (한 번만 설정): 경량(`lightweight_ai_config.json`) / 중급(`midtier_ai_config.json`) / 고급(`system_ai_config.json` 재사용, UI 라벨 '고급').
- **4 축** (각 독립 티어 배정): 분류(무의식+백그라운드 정리) · 평가(GoalEval) · 실행(프로젝트 에이전트·시스템 AI·Reflex·수동 번역·android·자동응답·임베디드 텍스트생성) · 의식(consciousness).
- **기어 = 축→티어 프리셋**: 절약(전부 경량) / 균형(분류·평가=경량, 실행·의식=중급) / 최대(분류·평가=경량, 실행·의식=고급). 분류·평가는 원샷이라 최대에서도 경량 유지(속도 명제).
- **에이전트 핀(overrides)**: 특정 에이전트만 기어 무시하고 티어 고정. 우선순위 override > role > gear. 키=`{project}:{agent_id}` 복합키(동명 격리).
- **per-agent 모델 폐지**: 에이전트 yaml의 provider/model/apiKey 무시 — 모델*과 키*는 실행 티어 상속. 모달리티(이미지·동영상·임베딩)는 기어 밖 패스스루.

- **연상 단계 (단계 0)** — `agent_cognitive._build_execution_memory()`
  - 해마(`ibl_usage_rag.build_execution_memory()`)와 심층메모리(`_search_related_memory()`)를 합쳐 단일 묶음 반환
  - 반환: `(xml, top_score, top_code)` — 검색 한 번으로 점수/코드까지 확보 (이전 3회 중복 호출 제거)
  - 모든 에이전트(무의식/의식/실행/평가)가 같은 묶음을 공유
- **Reflex 분기** — 호출 측(`agent_communication`, `api_websocket`, `system_ai_core`)이 직접 분기
  - `top_score >= REFLEX_SCORE_THRESHOLD (0.85)` 이면 무의식 모델 호출 스킵
  - reflex_hint로 매칭된 IBL 코드를 실행 에이전트에 힌트로 전달
- **무의식 (경량 AI)** — `_classify_request()`
  - 단순 분류만 담당 (Reflex 로직 분리됨)
  - 프롬프트: `data/common_prompts/unconscious_prompt.md` (단일 파일, 가볍게 유지)
- **Reflex 모델 전환** — `model_resolver.get_provider_for('reflex')`로 위임 (2026-06-30 기어 통합)
  - reflex_hint가 있을 때만 provider를 'reflex' 축 티어(균형 기어 기본=중급)로 교체 후 try/finally로 복원
  - 무의식 EXECUTE는 'execute' 축 유지 — 분류 오판이 품질 저하로 이어지지 않게 하는 방어. 덕분에 무의식은 EXECUTE 쪽으로 과감하게 기울 수 있다
- **의식 에이전트** — `consciousness_agent.py` ('consciousness' 축, 균형 기어 기본=중급)
  - 출력 필드: task_framing, achievement_criteria, history_summary, capability_focus, guide_files, self_awareness, world_state
  - 입력: self-describing XML 블록들 (`<agent>`, `<history>`, `<execution_memory>`, `<related_memory>`, `<world_pulse>`, `<available_guides>`, `<user_message>`)
  - 프롬프트: `consciousness_prompt.md` + `system_structure.md` + `fragments/12_ibl_only.md`
- **framing 재사용 (의식 진입 게이트, 2026-05-31)** — `_run_consciousness_or_reuse()` + `_consciousness_fit_gate()`
  - THINK 시 같은 대화의 직전 framing이 재고(30분 TTL)에 있고 경량 fit 게이트가 적합 판정하면 의식(Opus) 호출을 스킵·재사용(criteria만 갱신). 없음/안 맞음/실패 또는 SESSION_RESET·재시작 시엔 풀 의식. 상세: architecture.md
- **평가 에이전트 (경량 AI)** — `_run_goal_evaluation_loop()`
  - achievement_criteria가 있을 때만 실행. NOT_ACHIEVED 시 피드백과 함께 재실행 (최대 3라운드)
  - 입력에 `## 연상기억` 섹션으로 연상 묶음 그대로 전달
  - 프롬프트: `data/common_prompts/evaluator_prompt.md` + 시스템 구조 + IBL 단편
- **공통 원칙**
  - 시스템 AI와 프로젝트 에이전트 모두 동일한 AgentRunner 인지 메서드 사용 (`_is_system_ai` 플래그로 DB·도구만 분리)
  - 모델·API 키는 모두 모델 기어가 해소한 티어에서 상속 (에이전트별 키 설정 폐지). 티어 슬롯의 키가 비면 고급(시스템 AI) 키로 폴백

---

*마지막 업데이트: 2026-08-16 — **table:rename·flatten 신설**(관계대수 ρ·unnest — 소스 다른 통화의 join 전 키 맞추기 + each 결과 모으기, 닫힌 계급의 완결): <!-- SELF_IMAGE:START -->**현 상태 = 6노드 144 액션(sense 40·self 48·limbs 14·others 17·engines 9·table 16)·40 도구 패키지 + 5 extensions**<!-- SELF_IMAGE:END -->. 2026-08-05 개념중복 압축(163→150: 싼 병합 5건·검색 통합 `[sense:search]{source}`[web-kr 은퇴]·book군 `[sense:book]{source:"google"}`·슬라이드 일원화 `[self:slide]{op:create}`·영상 `[self:deck]{op:"video"}`)이 changelog 에만 기록되고 이 문서의 수치가 낡아, 에피소드 935 에서 시스템이 자기 액션 수를 "163+"로 잘못 말한 것의 수리(자기상도 임시적 명사 — 낡으면 노출·수정). + 헌법 부속 조항 **"명사의 자리"** 추가(`ibl.md` — 몸의 명사는 코드에·세계의 명사는 반증 가능한 데이터에, 선행 명사 스키마 금지). 이전(2026-08-04) — backend 파일 수 197→**198** 정합화. 이전 — **코드베이스 지도 정합화 + 새 기관 다섯**(backend 192→**197 파일**, 6노드 **163 액션**): `notify_dispatch.py`·`desktop_notify.py`(알림이 사용자에게 닿는 단일 관문 — 런처 연결 시 OS 네이티브 알림, 미연결이면 의존성 0 폴백), `boot_status.py`(lifespan 의 '실패(무시)' 블록 계측 → `/world-pulse/health` `boot` 절), `warehouse_catalog.py`(비즈니스 아이템 → 자족 카탈로그 HTML, 지문 게이트), `warehouse_directory.py`(이웃 창고 둘러보기 — 장르별 후보). 어휘는 `[self:webapp]` 하나 늘었다(system_essentials, 웹앱 등기부=파생 우선). 축소도 있었다 — 음악 관련곡 그래프 계기(`MusicGraphInstrument.tsx`)와 `library.db` 의 `edges` 테이블, 클립박스(`clipbox.json`), 웹 푸시가 전부 은퇴. 이전(2026-07-25) — **몸의 주소·몸 사이 소통·손발·음악**: ①**공유창고**(2026-07-18~21)가 몸의 공개 얼굴로 자람 — `공유창고/0..4/` 폴더 그대로 서빙 + `/manifest` 기계 얼굴 + 이웃 창고 폴러(30분, 방언 어댑터 native/autoindex/RSS/Nextcloud/page) + 리트윗(`.url`) + 회원 자격 폴링 + 창고 점수(0~3). 몸의 주소는 이제 **파생**(`origin_host`, 권위=`public_face.provider`) 이고 Cloudflare 발급이 터널·Worker·R2 캐시까지 만든다(`cdn_provision.py`). ②**몸 사이 소통 = 명함+부탁**(2026-07-22): `GET /nodes/card`(명함) + `POST /nodes/ask`(자연어 부탁, 어휘 `[others:ask]`) — 공유 사전 RPC 은퇴, **사전 물리 분리**(설치=자기 어휘만·해마 소유-필터) + 신뢰=이웃 등급(`body_trust`). **표면 분리**: 원격 런처(PC의 일부, 5탭)와 폰 네이티브(독립 시스템, 3탭)를 조립 모듈로 가름. **특권 소멸**: 몸 간 특권 배관 철거 방향 확정(클립보드는 원격 런처 clipbox 로 재배치). ③**USB 손발**(2026-07-23): `[self:limb]` 발급 / `[limbs:guestpc]` 조작 — 낯선 PC 에 꽂는 얇은 몸(Go 헬퍼, 허브로 아웃바운드). `runs_on mac_only`→**`pc_only`** 전역 개명. ④**신문 발행 결정화**(`[engines:newspaper]`) + 에피소드 로깅 전 경로 배선. ⑤**내 음악 라이브러리**(`[self:music]`, 2026-07-24) + 관련곡 그래프(랜덤 산책·🕸️ 그래프 계기), **공개 파일 동영상 생방송 재생**(스트리밍 트랜스코드·자막·오프셋 시크). **현 상태: 6노드 162 액션(sense 48·self 51·limbs 18·others 18·engines 14·table 13)·42 도구 패키지 + 8 extensions·backend 192 파일**. 이전(2026-07-17) — **공개 표면 가족(커뮤니티당 노드 하나) + table 노드 분리**: `others` 노드에 공개 웹 표면(portal `/h/`·showcase `/s/`·family_news `/n/`·bulletin `/b/` + 정기보고 `/r/`) 자람 — 신규 패키지 community-portal·public-files·family-news·bulletin. 그 외 신규 어휘: `[sense:stay]`·`[sense:entity]`·`[sense:used]`·`[self:install_lib]`·`[engines:icon]`. **table 노드 분리**(2026-06-30, engines 변환자/emitter 13종→신규 table 노드). **현 상태: 6노드 157 액션(sense 48·self 49·limbs 17·others 17·engines 13·table 13)·40 도구 패키지 + 8 extensions**. 이전(2026-06-30) — 모델 기어(계기판 변속) + per-agent 모델 폐지: 모델 선택 ~15곳을 `model_resolver.py`(역할→축→기어→티어)로 통합. 레버(절약/균형/최대)·프리셋 편집기·에이전트 핀, 핫리로드(`/model-gear` REST). 4축=분류·평가·실행·의식. per-agent 모델 폐지(모델·키 티어 상속). 폰 엔진 번들=`data/bodies/*.json` 파생. 142 액션·38 도구 패키지. 이전(2026-06-27) — 앱 표면 품질 일괄 개선(라디오 즐겨찾기·CCTV 인앱 재생 stream 버튼·여행 날짜+한국 지방공항·투자 TIGER200·날씨 오송·문화 지역·길찾기 거리/예상시간) + 부동산 직방 호가(sense:realty source:zigbang)·AI 공모/창업(sense:contest/startup) + read_guide claude_code 노출 + 폰 네이티브 재빌드. 142 액션(sense 44·self 44·limbs 17·others 11·engines 26)·38 도구 패키지. 이전(2026-06-22) — 국회도서관 국가학술정보(LOSI) 인물/학위논문 액션 추가: `[sense:researcher]`·`[sense:paper]{source: "nanet"}`(연구자·학위논문 검색, study 패키지). 키=`.env` `NANET_API_KEY` + auth_manager 'nanet' 레지스트리. 포식기억(forager) 추가로 기억 7종. 5-Node 142 액션(sense 44·self 44·limbs 17·others 11·engines 26) / 38 패키지 / backend 134 파일. 이전(2026-06-15) — 통화 대수(engines 변환자 9: filter/sort/take/select/dedup/groupby/join/union/merge + 파이프 문법 `|` + 문서 IR emitter) → 122~124에서 136 액션. 이전(2026-06-14) — 폰이 두 번째 독립 자아로: 폰-로컬 in-process Gemini 두뇌(경량+본격 티어) + 하드웨어 자기감지(detect_body — 자신을 맥 아닌 "폰"으로 인식) + 상주 스케줄러(self:trigger/schedule 폰 바인딩) + runs_on 정직성(anywhere/mac_only/phone_only) + 사용자 세계-데이터 CRDT 동기화(비즈니스·의료기록, 단 주관적 기억은 자아별 사적) + 의료 에이전트 환자차트 자동주입. 폰 온디맨드 감각 삼각(sense:here/listen/see) + self:show_calendar 폐지 → 125→124 액션. 이전(2026-06-12): 메신저/커뮤니티/비즈니스 IBL 앱모드 계기화 + 자동응답 IBL화 + 폰↔PC business.db 동기화 + neighbor 통합 + 해마 로컬 재학습(M4 Pro, code Top-5 92.6%/desc 92.8%). 이전(2026-06-10): 인지 경로 개편. 이전(2026-06-02): 런처 3표면.*
