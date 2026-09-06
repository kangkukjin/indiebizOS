---
title: 시스템 구조 가이드
scope: 프롬프트 주입용 — 자기 인식, 디렉토리 구조, 인지 파이프라인 (의식·실행·평가에 자동 주입)
owner_code: prompt_builder.py, consciousness_agent.py, agent_cognitive.py (모두 자동 로드)
last_updated: 2026-08-22
see_also: [architecture.md, memory.md, ibl.md]
---

# IndieBiz OS 시스템 구조 가이드

시스템 관리, 확장, 디버깅, 개발 작업 시 참조하는 핵심 구조 정보.

## 개요
- **경로**: 저장소 루트(로컬 클론 위치 — 배포판은 `INDIEBIZ_BASE_PATH`)
- **설명**: AI 기반 통합 관리 시스템 (IBL 추상화 위에서 개인·조직 규모 무관하게 동작)
- **핵심 가치**: 개인화, 자동화, 연결성

### 주요 기능
- **런처 3표면 (트릴레마)**: 같은 IBL 위 세 모드 — **자율주행**(의도→AI 다단계, 구 '프로젝트') / **조종실**(구 '수동'→'계기판'→2026-07-03 개명. 경량모델이 자연어→IBL 번역→dry-run 검수→실행하는 컴파일러 프론트엔드 + 시스템 상태·모델 기어·프레즌스·주행기록 — 자율주행 포함 전체를 감독·개입하는 주권 기관. `api_ibl.py`+`ManualMode.tsx`, 내부 탭 키는 `manual` 유지) / **앱**(아이콘 GUI로 직접 조작, `ActionDesktop`+계기 — 부동산·도서검색). {속도·표현력·주권} 중 둘.
- **다중 프로젝트 관리**: 목적에 따른 독립적인 작업 공간
- **에이전트 팀**: 역할이 정의된 여러 AI 에이전트 간의 협업
- **도구 패키지**: 에이전트가 동적으로 로딩하여 사용하는 확장 기능
- **IBL (IndieBiz Logic)**: 정보 흐름 추상화 언어 — 통합 인터페이스로 모든 정보 소스 접근. 조합이 문법에 있다: 순차 `>>`(파이프 단축 `|`)·병렬 `&`·폴백 `??`, 조건/분기 **블록**(`if`/`else`/`case` — 문장 위치에도 놓인다), 고차 문장 `[table:each]{do, as, limit, on_error}`(찾은 것 *각각*에 IBL 문장 적용), 변수·`goal`. 재귀 깊이 상한 3. → ibl.md
- **스케줄러**: 정기적인 정보 수집 및 리포트 자동 생성
- **IndieNet**: 외부 메신저/이메일 연동 (Gmail, Nostr)
- **공유창고**: 몸(노드)의 공개 얼굴 — `공유창고/0..4/` 폴더가 노드 주소에서 그대로 서빙(색인·변환 없음, 파일시스템이 진실). 사람은 브라우저로, 남의 AI는 `/manifest`(JSON)로 읽는다. 레벨 0~4 = 이웃 CRM 등급과 같은 자(등급 위 파일은 403 아닌 **404**). 읽는 쪽=이웃 창고 폴러(30분, 방언 어댑터로 nginx 색인·RSS·Nextcloud·일반 웹페이지까지 같은 통화로 정규화) + 리트윗(`.url` 포인터 파일). → communication.md
- **몸 사이 소통(명함·부탁)**: 공유 사전 RPC 대신 **명함**(`GET /nodes/card`)+**자연어 부탁**(`POST /nodes/ask`, 어휘 `[others:ask]`) — 받는 몸이 *자기 사전*으로 컴파일·실행해 통화로 돌려준다. 신뢰=이웃 등급(body_trust), 특권 배관 없음. → communication.md
- **USB 손발**: 낯선 PC 에 USB 로 꽂는 얇은 몸(`[self:limb]` 발급 / `[limbs:guestpc]` 조작). 두뇌·신원은 허브에 남고 USB 엔 limb key 하나. 헬퍼가 허브로 아웃바운드 접속(폰 푸시 큐 재사용).
- **NAS 연동**: 음악 스트리밍, 자막 관리, 웹앱 호스팅 (내 음악 라이브러리는 별도 `[self:music]`)

---

## 시스템 문서 (System AI 참조)
- **경로**: `data/system_docs/`(저장소 루트 기준)
- 시스템 AI가 장기 기억으로 참조하는 문서들
- **문서 신뢰 규약**: 정본 서열 = git 커밋(사건) > docs/(설계) > system_docs/(장기기억). 문서 속 수치·파일명·함수명은 *쓰인 당시의 기록*일 수 있다 — 행동 전 `[self:body]`·`[self:grep]` 로 실재를 확인하라. `<!-- …:START/END -->` 마커 구간은 빌드가 재생성하는 기계 소유(손 수정 금지).
- **파일 목록** (13 문서 + changelog):
  - `system_structure.md` - 시스템 구조 가이드 (**항상 프롬프트에 포함** — 의식/실행/평가 에이전트)
  - `anatomy.md` - **해부도(정문)** — 신참용 전체 지도(철학→3표면→IBL→인지→메모리→검색브라우저→몸), 각 상세 문서 허브
  - `vision.md` - **비전: 인지 외골격** — 목표(자율 아닌 융합)·개발 북극성=착용감. 모든 설계 결정의 최상위 기준
  - `harness_haerye.md` - **하네스 해례** — 구현·파일명 없이 읽히는 코드 독립 아홉 원리(자기 하네스를 지으려는 사람용). 공개면 후보
  - `architecture.md` - 시스템 개요·아키텍처·설계 의도 (구 overview.md 오브젝트/에이전트 유형 흡수)
  - `technical.md` - 기술 문서 (API, 설정, 경로)
  - `ibl.md` - IBL 명세(6-Node·op 어휘화·삼각 검증) + **설계 철학**(구 ibl_design_philosophy.md)
  - `memory.md` - 메모리 7종 통합 지도 + **연상기억 심층**(해마·심층메모리 — 구 memory_architecture.md + execution_memory.md)
  - `packages.md` - 패키지 시스템 (구조·설치 절차·설치 목록. 수·표는 빌드 파생)
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
│   │   ├── consciousness_agent.py # 의식 에이전트 — 메타 판단 + achievement_criteria + 메타 인지 가드
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

**모델 기어 (계기판 변속, 2026-06-30):** 자동차 기어처럼 레버 하나로 시스템 전체 모델 등급을 변속. 자동 변속기(무의식 분류기=작업마다 티어 자동선택) 위의 **수동 변속 레버**. `backend/base/model_resolver.py`가 *역할 → 축 → 기어 → 티어 → 모델*로 해소하고 매 호출 읽기(핫리로드, `/model-gear` REST). 설정=`data/model_gear.json`.
- **3 티어 = 모델 슬롯** (한 번만 설정): 경량(`lightweight_ai_config.json`) / 중급(`midtier_ai_config.json`) / 고급(`system_ai_config.json` 재사용, UI 라벨 '고급').
- **4 축** (각 독립 티어 배정): 분류(무의식+백그라운드 정리) · 평가(GoalEval) · 실행(프로젝트 에이전트·시스템 AI·Reflex·수동 번역·android·자동응답·임베디드 텍스트생성) · 의식(consciousness).
- **기어 = 축→티어 프리셋**: ★프리셋은 **데이터**(사용자가 `/model-gear/presets` 로 편집) — 현행 값의 정본은 `data/model_gear.json` 이고, 코드의 `_DEFAULT_GEAR` 는 파일 부재·손상 시 폴백일 뿐이다. **값을 말하기 전에 그 파일을 읽어라**(2026-09-04 실측: 라이브 최대 기어의 평가 축은 **고급** — 여기 적혀 있던 '분류·평가는 최대에서도 경량'은 폴백만 맞고 라이브는 아니었다. 산문에 값을 복제하면 반드시 이렇게 썩는다). 폴백 기본값: 절약(전부 경량) / 균형(분류·평가=경량, 실행·의식=중급) / 최대(분류·평가=경량, 실행·의식=고급).
- **에이전트 핀(overrides)**: 특정 에이전트/역할만 기어 무시하고 티어 고정. 우선순위 override > role > gear. **키 = `resolve(role, agent_id)` 에 실리는 이름 그대로** — 프로젝트 에이전트만 `{project}:{agent_id}` 복합키(동명 격리)이고, 나머지는 단일 이름(`system_ai`·`forage`·`system_ai_delegation` 같은 역할·경로 이름)이다. 계기판 열거는 `api_config._list_pinnable_agents()` 하나뿐이라, 거기 없는 키로 핀이 걸리면 **효력은 있는데 화면에 없는 유령 핀**이 된다 — 그래서 그 함수는 실재 에이전트에 더해 *현재 걸려 있는 핀 전부*를 흡수해 낸다(2026-09-04).
- **per-agent 모델 폐지**: 에이전트 yaml의 provider/model/apiKey 무시 — 모델*과 키*는 실행 티어 상속. 모달리티(이미지·동영상·임베딩)는 기어 밖 패스스루.

- **연상 단계 (단계 0)** — `agent_cognitive._build_execution_memory()`
  - 해마(`ibl_usage_rag.build_execution_memory()`)와 심층메모리 지도(`_memory_map_scent()`, `<memory_map>` 목차만 — 내용은 recall 로)를 합쳐 단일 묶음 반환
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
  - 출력 필드: task_framing, achievement_criteria, history_summary, capability_focus, guide_files, imagined_ibl(상상실행 초안, 2026-08-31) (self_awareness·world_state 는 2026-06-28 폐지)
  - 입력: self-describing XML 블록들 (`<agent>`, `<history>`, `<execution_memory>`, `<memory_map>`, `<execution_map>`, `<world_pulse>`, `<user_message>` — 가이드 목차는 `<execution_map>` 의 guide: 줄, 2026-09-03)
  - 프롬프트: `consciousness_prompt.md` + `system_structure.md` + `data/common_prompts/fragments/12_ibl_only.md`
- **framing 재사용 (의식 진입 게이트, 2026-05-31)** — `_run_consciousness_or_reuse()` + `_consciousness_fit_gate()`
  - THINK 시 같은 대화의 직전 framing이 재고(30분 TTL)에 있고 경량 fit 게이트가 적합 판정하면 의식(Opus) 호출을 스킵·재사용(criteria만 갱신). 없음/안 맞음/실패 또는 SESSION_RESET·재시작 시엔 풀 의식. 상세: architecture.md
- **평가 에이전트 (경량 AI)** — `cognitive_eval._run_goal_evaluation_stream()`
  - achievement_criteria가 있을 때만 실행. NOT_ACHIEVED 시 피드백과 함께 재실행 (최대 3라운드)
  - **제너레이터** — 평가·재실행 구간의 이벤트를 그대로 흘린다(`yield from`). 재실행도 실행 단계와 같이 도구·본문이 실시간으로 보인다
  - 입력에 `## 연상기억` 섹션으로 연상 묶음 그대로 전달
  - 프롬프트: `data/common_prompts/evaluator_prompt.md` + 시스템 구조 + IBL 단편
- **공통 원칙**
  - 시스템 AI와 프로젝트 에이전트 모두 동일한 AgentRunner 인지 메서드 사용 (`_is_system_ai` 플래그로 DB·도구만 분리)
  - 모델·API 키는 모두 모델 기어가 해소한 티어에서 상속 (에이전트별 키 설정 폐지). 티어 슬롯의 키가 비면 고급(시스템 AI) 키로 폴백

---

<!-- SELF_IMAGE:START -->**현 상태 = 6노드 154 액션(sense 43·self 50·limbs 14·others 17·engines 8·table 22)·41 도구 패키지 + 5 extensions·backend .py 308(test 제외)**<!-- SELF_IMAGE:END -->

*최근 변경(2026-08-22): system_docs 목록 13문서(harness_haerye 누락분)·유령 파일(my_profile.txt) 제거·자가점검 카덴스 정정. 이력 정본=git log·changelog.log(`[self:body]` 회상) — 꼬리에 이력을 쌓지 말 것(2026-08-21 다이어트, 전문=직전 git 판).*
