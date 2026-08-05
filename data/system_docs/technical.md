---
title: 기술 참조
scope: API 엔드포인트, 설정 파일 위치, AI 프로바이더, 프롬프트 XML 구조, 감각 전처리
owner_code: api_*.py, providers/, ibl_engine.py
last_updated: 2026-08-04
see_also: [architecture.md, ibl.md]
---

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
- `DELETE /business/neighbors/{id}` - 이웃 삭제 (소프트 삭제 — tombstone)
- `GET /business/neighbors/{id}/contacts` - 연락처 목록
- `POST /business/neighbors/{id}/contacts` - 연락처 추가
- `DELETE /business/contacts/{id}` - 연락처 삭제

### 폰↔PC 동기화 (/business/sync)
- `GET /business/sync/export` - business.db 동기화 스냅샷(삭제 tombstone 포함)
- `POST /business/sync/merge` - 다른 기기 export를 합집합 머지(LWW+tombstone) 후 최신 스냅샷 반환
- 주소록 메타데이터(이웃·연락처·사업·아이템·문서·지침)만 대상. 메시지/글 내용은 릴레이/Gmail 수렴이라 제외.
- 인증: `remote_access_guard`가 외부(터널) 요청에 launcher 세션 강제, localhost(데스크탑) 통과.
- 트리거: `[self:phone_sync]` IBL 액션(맥 주도 USB adb) 또는 폰 `phone_api` 직접 호출.
- ※ IndieNet 전용 REST(`/indienet/*`)는 제거됨 — 커뮤니티/메신저는 IBL 계기(others:feed/board/messages/nostr)로만 접근.

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

### 몸 사이 소통 (/nodes) — api_nodes.py
- `GET /nodes/card` - 내 **명함**(capability card): 레지스트리 파생 desc-프로젝션(표준 코어 제외·params 미포함·몸 인식 필터·`dictionary_hash`)
- `POST /nodes/ask` - 이웃 몸의 **자연어 부탁** 수신 → 자기 사전으로 컴파일→실행→통화 회신(1회 자가교정, 어휘 밖=정직 거절). 어휘 진입점은 `[others:ask]`
- 신뢰=이웃 등급(`body_trust`) 게이트. 몸 사이 전용 특권 배관은 두지 않는다.

### USB 손발 (/limb) — api_limb.py
- `POST /limb/connect` - 헬퍼 등록(limb key 인증, device 단위)
- `GET /limb/poll` - 셸 봉투 롱폴(아웃바운드 — 게스트 PC 방화벽 무설정)
- `POST /limb/result` - 실행 결과 회신
- 발급·폐기는 `[self:limb]{op: issue/list/revoke}`, 하달은 `[limbs:guestpc]{op}`. 큐는 폰 푸시 큐(`phone_jobs`) 재사용.

### 공개 표면 서빙 (브라우저 → Cloudflare Worker → 터널 → 허브)
공유 `X-Showcase-Secret` + `is_public_remote_path` 화이트리스트.
- `/h/<slug>/` 개인 포털(api_portal) · `/s/<slug>/` 공개 파일(api_showcase — 동영상 스트리밍 트랜스코드·`/sub` 자막) · `/n/<slug>/` 가족신문(api_family_news) · `/b/<slug>/` 게시판(api_bulletin) · `/r/<slug>/` 정기보고(api_report, 볼 때 렌더)
- 창고(노드 맨 주소): `GET /` 사람 페이지 · `GET /manifest` 기계 얼굴(JSON) · `GET /f?path=` 파일 · 쿠키 로그인. **이게 계약의 전부.**
- 몸의 주소는 `origin_host()`가 실제 서빙 얼굴에서 파생(권위=`public_face.provider`), 발급은 `cdn_provision.provision_cdn`(터널+Worker+R2 캐시).

### 이웃 창고 피드 (/warehouse-feed) — api_warehouse_feed.py, 소유자 전용
- `POST /warehouse-feed/neighbors` 등록(즉시 seed 폴링) · `DELETE …` 해제 · `POST /warehouse-feed/poll` 즉시 폴링
- `GET /warehouse-feed/feed` 타임라인(seed/new/changed) · `GET /warehouse-feed/search` 동네 전체 파일명 검색 · `POST /warehouse-feed/retweet` 리트윗(`.url` 포인터 파일)
- 어댑터: native / autoindex(nginx·Apache) / rss(HTML 자동발견) / nextcloud / page — `poll_status.adapter` 캐시, 실패 시 재감지(자가치유). **모델 호출 0**.

### 내 음악 (/music) — api_music.py
- `GET /music/stream` 부분 응답(Range 206, 소스 폴더 화이트리스트) · `GET /music/cover` 앨범아트(내장 태그→폴더 아트→SVG 폴백)
- 어휘는 `[self:music]{op}`. 재생은 **서버 무음** — 통화의 `stream` 필드를 보는 표면의 `<audio>`가 문다.

### 알림 도달 (notify_dispatch)
- 수신 단일 관문(`channel_poller._save_message_to_db`) 직후 `notify_dispatch.notify_user()` — ①알림함 기록 ②런처 연결 시 `/ws/launcher` `show_notification`(`api_websocket.send_launcher_command_sync`, 워커 스레드 안전) → Electron OS 네이티브 알림+배지 ③미연결이면 `desktop_notify.py`(의존성 0 — osascript / PowerShell WinRT / notify-send). `[self:notify_user]` 도 같은 관문을 쓴다.
- ★웹 푸시(경로 C)와 클립박스(`/launcher/clipbox`)는 둘 다 **은퇴**(2026-07-28~08-01): 전자는 같은 origin 다중 PWA 의 알림 위임 때문에 실기기 도달 실패, 후자는 '폰으로'가 종전 푸시 큐로 원복.

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

## IBL 도구 — execute_ibl

모든 에이전트는 `execute_ibl(code='[node:action]{params}')` 단일 도구로 IBL을 호출. 6노드(sense/self/limbs/others/engines/table) 163 액션의 정의·카테고리·라우팅 방식은 **ibl.md** 참조.

예시:
```
execute_ibl(code='[sense:stock]{op: "quote", ticker: "AAPL"}')
execute_ibl(code='[sense:search_ddg]{query: "AI"} >> [self:write]{path: "result.md"}')
execute_ibl(code='[sense:stock]{op: "quote", ticker: "AAPL"} & [sense:stock]{op: "quote", ticker: "MSFT"}')
```

**자동 발견**: `ibl_engine._merge_api_registry_actions()`가 로드 시 `api_registry.yaml`의 node 바인딩 도구를 노드 액션에 자동 병합.

**인프라 노드 (항상 허용)**: `self`, `others`, `table` — 모든 에이전트에 자동 제공. 노드 yaml의 `always_on: true` 플래그가 단일 소스 (`ibl_access._always_allowed()`가 레지스트리에서 읽음, 노드 on/off 기능의 토대)

## 설정 파일 위치
- **모델 기어 (계기판 변속)**: `data/model_gear.json` — 현재 기어(절약/균형/최대) + 프리셋(기어 × 축 → 티어) + 에이전트 핀(overrides). `backend/model_resolver.py`가 *역할 → 축 → 기어 → 티어*로 해소하고 매 호출 읽기(핫리로드). 아래 3개 티어 설정은 이제 **모델 슬롯**(고급=system_ai 재사용)이고, 어느 축이 어느 슬롯을 쓰는지는 기어가 정함. 에이전트별 모델 설정은 폐지(yaml provider/model/apiKey 무시, 모델·키 모두 티어 상속).
- **고급 AI 슬롯 (구 '본격' / 시스템 AI config 재사용)**: `data/system_ai_config.json`
- **중급 AI 슬롯**: `data/midtier_ai_config.json`
- **경량 AI 슬롯 (원샷=분류·평가·증류 등)**: `data/lightweight_ai_config.json`
- **스위치 목록**: `data/switches.json`
- **프로젝트 목록**: `projects/projects.json`
- **프로젝트 에이전트**: `projects/{id}/agents.yaml`
- **시스템 AI 대화 이력**: `data/system_ai_memory.db` (SQLite)
- **시스템 AI 심층메모리**: `data/system_ai_state/memory_system_ai.db` (SQLite, 시맨틱 검색)
- **프로젝트 에이전트 심층메모리**: `projects/{id}/memory_{agent}.db` (SQLite, 시맨틱 검색)
- **World Pulse DB**: `data/world_pulse.db` (SQLite — pulse_log, self_checks, action_health, episode_log, episode_summary)
- **대화 이력**: `projects/{id}/conversations.db` (SQLite)
- **도구 패키지**: `data/packages/installed/tools/`
- **비즈니스 DB**: `data/business.db` (SQLite)
- **해마 (IBL 사용량) DB**: `data/ibl_usage.db` (SQLite — ibl_examples + FTS5 + vec0)
- **해마 임베딩 모델**: `data/models/ibl_embedding/` (fine-tuned `jhgan/ko-sroberta-multitask`, 422MB. 해마 + 심층메모리 공유)
- **해마 학습 데이터**: `data/training/ibl_training_balanced_20260516.json` + `ibl_distilled.json`. usage_db ~2,988건. **2026-08-04 로컬 맥미니 M4 Pro 재학습 완료**(batch=8·epoch 5 최적·검증 0.882, 직전 모델 대비 code Top-5 88.9→92.2%/desc 92.2→94.2%/런타임 ~99%). 절차·함정은 `data/guides/hippocampus_retraining.md`.
- **폰 컴패니언 피드 DB**: `data/phone_notifications.db` (SQLite — 알림·위치·걸음. `backend/phone_notifications.py`가 NIP-17 수신분 저장, 인가 폰 신원은 `data/phone_agent.json`). 조회 API `/phone/notifications|locations|steps` (`backend/api_phone.py`) + `[sense:phone]{op}`
- **NIP-17/NIP-44 모듈**: `backend/nip17.py` (gift-wrap DM) + `backend/nip44.py` (암호화, 공식 테스트 벡터 150/150). channel_engine 송신은 NIP-17, 수신은 NIP-04+NIP-17 병행 fan-out
- **외부 API 키 (`.env`)**: 패키지 핸들러가 외부 서비스 호출 시 `.env`에서 로드. 예: `NANET_API_KEY` — 국회도서관 국가학술정보(LOSI) OpenAPI (losi-open.nanet.go.kr, 연구자·학위논문 검색 `[sense:researcher]`·`[sense:paper]{source: "nanet"}`, study 패키지, auth_manager 'nanet' 레지스트리).
- **IBL 노드 정의 (소스)**: `data/ibl_nodes_src/{meta,sense,self,limbs,others,engines,table}.yaml` — 단일 진실 소스, 직접 편집. op-bearing 액션은 `ops: {default, values}` 블록 의무.
- **IBL 노드 정의 (빌드 산출물)**: `data/ibl_nodes.yaml` — `scripts/build_ibl_nodes.py`로 생성, 런타임 로드, 직접 편집 금지
- **웹앱 등기부**: `data/webapps.json` — **파생 밖 예외만** 담는 수동 보충분(원장 아님). 진실 소스 7곳(포털·게시판·가족신문·공개파일·정기보고·web-builder `sites.json`·`outputs/web-projects/*/wrangler.toml`)은 `backend/../system_essentials/webapp_registry.py` 가 매 호출 재계산. 어휘 `[self:webapp]{op}`.
- **이웃 창고 둘러보기 시드**: `data/warehouse_directory.json` — 장르별 후보 목록(자가 생성·사용자 편집 가능). live 경로는 Neocities 태그 브라우즈를 요청 1회로 파싱.
- **IBL 검증 게이트**: `scripts/git-hooks/pre-commit` (commit 시점) + `backend/world_pulse_health.run_static_ibl_check` (12시간 self-check)
- **이음매 가드(액션 아닌 것의 시민권, 2026-07-25~26)**: `scripts/check_event_loop.py`(async 본문의 동기 블로킹 = 자기교착 부류) · `scripts/check_public_routes.py`(공개 노출 ↔ 인증 대조 — 오라클은 살아있는 `app.routes`, 공허한 통과 금지) · `scripts/check_win_portability.py`(유닉스 전용 stdlib 무가드 import — ★위험지대는 `data/packages/`) · `scripts/ci_import_smoke.py`. pre-commit + `.github/workflows/`(우분투 정적 스캔 + windows-latest 부팅 등가 스모크 + **신선 clone** 게이트).
- **부팅 관측**: `backend/boot_status.py` — lifespan 의 '실패(무시)' 블록 10개를 성패 계측, `/world-pulse/health` 의 `boot` 절로 노출(하나라도 실패면 overall=degraded).
- **표준 코어 경계 (설치·업데이트 이음매, 2026-07-10~)**: `data/core_manifest.json` — 코어 vs 사용자(어휘·앱) 경계의 **단일 진실**. `scripts/build_core_manifest.py`가 **git 추적 집합**(=배포에 딸려오는 것)에서 파생·커밋(installed+not_installed 양쪽 패키지·계기·중앙 어휘). 손목록 없음. **opt-out**: 개인 패키지·앱을 커밋해도 코어에서 빼려면 `<패키지>/.origin` 파일에 `user`(또는 계기 yaml 최상위 `origin: user`). 런타임 origin은 `backend/package_manager.resolve_package_origin()`가 이 매니페스트로 해소해 `/packages` 응답에 `origin: core|user` 노출. **가드**: pre-commit + `build_ibl_nodes.py --check`에 core_manifest·dist_filter 신선도 합류.
- **설치 파일 필터 (코어 기준 배포)**: `scripts/build_dist_filter.py` — `frontend/package.json`의 electron-builder `data` 필터에서 sentinel(`!__GEN_START/END__`) 구간을 매니페스트 주도로 생성(비-코어 패키지·계기 제외 + 개인 크러프트 `.fuse_hidden*`·최상위 `*.md/*.html/*.png`·`*.bak*` 제외). 기존 secret 손목록은 보존(순수 추가). `npm run electron:build*`가 `dist:filter`(predist=매니페스트 재생성)를 프리스텝으로 실행.
- **업데이트 시 사용자 보존 규칙 (`frontend/electron/main.js` `initUserData`)**: 재설치·업데이트가 **코어 소유 파일만 갱신**하고 사용자 것은 불가침. (1) 코어 어휘 산출물(`ibl_nodes.yaml`·코어 패키지 `ibl_actions.yaml`·코어 계기 yaml)은 매니페스트 기준 강제 갱신(`makeCoreForceOverwrite`). (2) 패키지 **설치 상태**(installed/not_installed 폴더 배치=사용자의 켜고/끈 선택)는 `syncPackagesPreservingState`가 userData의 *현재 위치*에서 그 자리 갱신, 신규만 번들 기본 폴더로 추가 → 사용자 선택 불가침. (3) 대화(`.db`)·설정(json)·사용자 직접만든(미추적) 패키지는 애초에 건드리지 않음.

## 지원 AI 프로바이더 (모두 스트리밍 지원)
`backend/providers/`: anthropic · openai · gemini · gemini_http · deepseek · openrouter · ollama · claude_code
- **Anthropic Claude** / **OpenAI GPT** / **Google Gemini**(HTTP 경량 경로 `gemini_http` 포함 — 폰도 쓰는 키-only 경로) / **DeepSeek**(V4 Pro·Flash, OpenAI 호환 API, 2026-07-22 신설) / **OpenRouter** / **Ollama**(로컬) / **claude_code**(맥 하네스 렌트)
- 모델·API 키는 **모델 기어**가 해소한 티어에서 상속(에이전트별 설정 폐지). 구체 모델 ID 는 `data/*_ai_config.json` 슬롯이 보유 — 이 문서는 목록만 유지(모델명은 빨리 낡는다).
- ★함정: Gemini `flash-latest` 별칭은 `thinkingConfig.thinkingBudget:0` 을 400 으로 거부 — 버전 명시(`gemini-2.5-flash`) 필요.

### Tool Result 절삭
- **기본 한도**: 16KB — tool result가 이 크기를 초과하면 절삭
- **파이프라인 시**: `_action_count × 16KB` 허용 (다중 액션 실행 시 비례 확장)

### 감각 전처리 (Sensory Preprocessing)
- 정보성 액션의 출력을 경량 AI(flash-lite)로 압축하여 컨텍스트 폭발 방지
- `data/ibl_nodes_src/<node>.yaml`의 `postprocess` 블록으로 액션별 선언적 설정
- 적용 액션: `search_ddg`, `crawl`, `search_gnews`, `travel`
- 구현: `ibl_engine.py`의 `_postprocess()` → `_pp_compress()`

### IBL 액션 단일 진실 소스 (2026-05-28~)
- `data/ibl_nodes_src/` 7개 yaml(meta + 6개 노드: sense/self/limbs/others/engines/table)이 사람이 편집하는 단일 소스
- `python3 scripts/build_ibl_nodes.py`로 `data/ibl_nodes.yaml` 빌드 (명시적, 자동 등록 없음)
- 패키지 설치/제거가 IBL 어휘를 자동 변경하지 않음 — 어휘 추가/삭제는 src 수동 편집
- **삼각 검증** (`--check`): src ↔ tool.json ↔ handler.py `_OP_DISPATCHERS` 3중 일치 AST 정확 비교
  - 등록: src.tool ↔ tool.json.name
  - op enum: src.ops.values 키 ↔ tool.json input_schema.properties.op.enum
  - default: src.ops.default ↔ tool.json input_schema.properties.op.default
  - dispatcher: src.ops.values 키 ↔ handler.py `_OP_DISPATCHERS[tool_name]` dict 키
- **이중 게이트**: pre-commit 훅(commit 시점) + self-check 사이클(12시간, `__static__:ibl_consistency` 식별자)
- **dispatcher 표준** (op 분기 26 패키지 / 액션 67개, 그중 12개는 패키지 밖 backend-native): `_OP_DISPATCHERS = {tool_name: {op: handler_or_None}}` 모듈 레벨 dict 노출 의무

## 물리적 구조 (주요 경로)
- `backend/`: 서버 소스 코드
- `backend/providers/`: AI 프로바이더 (스트리밍)
- `data/`: 시스템 설정 및 데이터
- `data/packages/installed/tools/`: 설치된 도구 패키지 (42개 — op 분기 26개가 `_OP_DISPATCHERS` 표준)
- `data/api_registry.yaml`: API 도구 정의 (node 필드로 IBL 자동 병합, 현재 2개 액션)
- `data/packages/installed/extensions/`: 백엔드 코어 모듈 (8개, ai-agent 폐기)
- `projects/`: 사용자 프로젝트 데이터 (24개 — 시스템 프로젝트 수동모드·앱모드 포함)
- `scripts/`: 빌드/배포 스크립트 (`build_ibl_nodes.py` + `build_core_manifest.py`[표준 코어 매니페스트] + `build_dist_filter.py`[설치 파일 필터] + `build_body_bundle.py`[폰 번들] + `git-hooks/pre-commit`)
- `data/core_manifest.json`: 표준 코어 vs 사용자 경계의 단일 진실 (git 파생, 배포 동봉)

## 프롬프트 구조

### XML 태그 구조 (2026-01-20 통일, 2026-05-17 정리)
모든 프롬프트에서 AI의 정확한 파싱을 위해 XML 태그 사용:

**연상기억 (모든 인지 에이전트에 동등하게 주입)** — self-describing
- `<execution_memory>` - 해마 결과 (과거 IBL 코드 사례 + 도구 구현)
  - `<ibl_references>` - 참고 용례 (intent + code + score)
  - `<implementations>` - 액션별 구현 상세
- `<related_memory>` - 심층메모리 결과 (사용자 사실·선호·결정 등 시맨틱 매칭)
  - `<memory category="..." keywords="...">` - 개별 기억 항목

(이전 `<ibl_nodes>` 외부 래퍼는 2026-05-17 제거 — 자식 태그가 self-describing이라 불필요)

**의식 에이전트 입력 블록 (`consciousness_agent._build_input`)**
- `<agent name="...">` - 이름 + `<role>` + `<notes>`
- `<world_pulse>` - 매시간 갱신되는 세계/사용자/시스템 상태
- `<history>` - 대화 히스토리 (`<turn index="..." role="...">`)
- `<available_guides>` - 가이드 파일 목록
- `<user_message>` - 현재 사용자 메시지

**프래그먼트 (fragments/)**
- `<git_operations>` - Git 작업 가이드
- `12_ibl_only.md` - IBL 환경 설명 (의식·평가 에이전트에 주입)

**히스토리 메시지 (providers/*.py)**
- `<user_message>` - 사용자 메시지
- `<assistant_message>` - AI 응답
- `<current_user_request>` - 현재 요청

**자동응답 V3 (auto_response.py - Tool Use 통합)**
- `<current_context>` - 현재 컨텍스트 (이웃 정보, 근무지침, 비즈니스 문서, 대화 기록)

---
*마지막 업데이트: 2026-08-04 — dispatcher 표준 수치 정정(op 분기 27→**26 패키지**/68→**67 액션**, 그중 12개는 패키지 밖 backend-native). 이전 — **등기부·알림·이음매 가드의 기술면**: ①**웹앱 등기부**(2026-08-01): `[self:webapp]{op: list/status/register/remove}` — 진실 소스 7곳 매 호출 재계산(파생 우선)+`data/webapps.json` 수동 보충, `status`=전 함대 병렬 HTTP 생존 실측. ②**알림 도달 경로**(2026-07-28): 수신 관문 직후 `notify_dispatch.notify_user()` 단일 지점 → 런처 WS 명령(OS 네이티브 알림·배지·트레이 상주) / 미연결 시 `desktop_notify.py`(의존성 0, 3 OS). 웹 푸시(RFC 8291)는 구현 후 실기기 불발로 **제거**, 클립박스도 철회. ③**이음매 가드**(2026-07-25~26): 인증 게이트 **fail-closed**(판정 불능=503) · 공개 노출↔인증 대조(`check_public_routes.py`, 오라클=살아있는 라우트 테이블) · 이벤트 루프 규율(`check_event_loop.py`) · 윈도우 이식성 · **신선 clone CI**(main 이 clone 에서 `--check` 실패였다 — 원인 둘 다 커밋되지 않은 로컬 상태) · 부팅 관측(`boot_status.py` → `/world-pulse/health` `boot` 절). ④**터널 종료에 소유권**: uvicorn 리로드 시 옛 워커의 정리가 새 워커의 터널까지 걷어차 공개 얼굴이 이틀간 Cloudflare 1033 이던 것 봉합. ⑤감각층 정정 셋: `sense:crawl` 인코딩 자동 판별(BOM→헤더→`<meta charset>`→자동감지, 각 단계 strict 검증 — 헤더가 charset 을 안 주면 curl_cffi 가 utf-8 로 단정해 옛 가드가 발동조차 못 했다) · `sense:stock` 통화는 Yahoo `meta.currency` 를 권위로(접미사 이진 추측이 환율쌍·도쿄 종목을 USD 로 오라벨) + 한국 종목·지수 **현재가만 네이버 폴링(delayTime=0) 오버레이**(KRX 20분 지연 해소, 일봉은 Yahoo 유지·실패 시 폴백) · PC 관리 파일탐색을 `os.scandir` 로(SMB 왕복 폭풍) + 드라이브/UNC/POSIX 겸용 경로 유틸. ⑥`claude_code` 세션 리셋 임계 300K→500K(사용자 결정 — 주요 세션이 임계 부근에 상시 체류). **현 상태: 6노드 163 액션(sense 48·self 52·limbs 18·others 18·engines 14·table 13)·42 도구 패키지 + 8 extensions·backend 197 파일(api_*.py 38)·가이드 58**. 이전(2026-07-25) — **몸의 주소·몸 사이 소통·손발·음악의 기술면**: ①**공유창고 서빙**(2026-07-18~21): 노드 맨 주소에서 `공유창고/0..4/` 직접 서빙 + `GET /manifest`(기계 얼굴) + `GET /f?path=` + 쿠키 로그인이 계약의 전부. 이웃 창고 폴러(`/warehouse-feed/*`, 30분 diff·모델 호출 0) + **방언 어댑터**(native/autoindex/rss/nextcloud/page, `poll_status.adapter` 캐시·자가치유) + 리트윗(`.url` 포인터). 몸의 공개 주소는 `origin_host()`가 실제 서빙 얼굴에서 **파생**(권위=`public_face.provider`), 발급은 `cdn_provision.provision_cdn`(터널+Worker+R2 캐시, 워커명=몸-유일). 인증 게이트 **fail-closed**(미등록 호스트=외부, 프록시 신호를 `Host` 보다 먼저 — cloudflared 가 Host 를 재작성). ②**몸 사이 소통**(2026-07-22): `GET /nodes/card`(명함) + `POST /nodes/ask`(부탁, 어휘 `[others:ask]`) + 신뢰=이웃 등급(`body_trust`). 사전 물리 분리(설치=자기 어휘만·해마 소유-필터). **DeepSeek 프로바이더** 신설(V4 Pro/Flash, OpenAI 호환). 채널 어휘 `gmail`→`email` 단일화(별칭만 잔존). ③**USB 손발**(2026-07-23): `/limb/connect·poll·result`(limb key 인증, 아웃바운드 롱폴) + `[self:limb]`/`[limbs:guestpc]`. `runs_on mac_only`→**`pc_only`** 전역 개명. ④**내 음악**(2026-07-24): `/music/stream`(Range 206·소스 폴더 화이트리스트)·`/music/cover`, 어휘 `[self:music]`. **공개 파일 동영상 생방송 재생**: 비재생 코덱을 fMP4 로 흘리며 같은 인코딩이 캐시를 만들고(중단해도 백그라운드 완주), 길이는 init 세그먼트 mvhd+tkhd+mdhd 3박스 패치로 표시, 첫 시청 시크는 커스텀 시크바+`?t=` 오프셋 스트림(+`sub?shift=`). ★인프로세스 프록시(httpx ASGITransport)는 스트리밍 불가 → 공개 얼굴은 **루프백 HTTP** 로 전환. 당시: 6노드 162 액션(sense 48·self 51·limbs 18·others 18·engines 14·table 13)·42 도구 패키지 + 8 extensions·backend 192 파일(api_*.py 38). 이전(2026-07-17) — **공개 표면 가족(커뮤니티당 노드 하나) + 3층 서빙**: `others` 노드 공개 웹 표면(portal `/h/`·showcase `/s/`·family_news `/n/`·bulletin `/b/` + 정기보고 `/r/`)이 브라우저→Cloudflare Worker→터널→맥 3층으로 서빙(공유 `X-Showcase-Secret`·`is_public_remote_path` 화이트리스트). 개인 포털=아이디/비번 또는 운영자 열쇠 로그인·회원=이웃 CRM(business.db) 레벨 0~4·포털별 오디오 프록시(`/h/<주소>/tune/`). 그 외 신규 어휘: `[sense:stay]`·`[sense:entity]`(Wikidata)·`[sense:used]`·`[self:install_lib]`(공급망 승인 게이트, auth 불필요)·`[engines:icon]`(폰-로컬, GEMINI_API_KEY). **table 노드 분리**(2026-06-30). **현 상태: 6노드 157 액션(sense 48·self 49·limbs 17·others 17·engines 13·table 13)·40 도구 패키지**. 이전(2026-06-30) — 모델 기어(계기판 변속) + per-agent 모델 폐지: 모델 선택 ~15곳을 `model_resolver.py`(역할→축→기어→티어)로 통합 + `data/model_gear.json`(기어·프리셋·핀) + `/model-gear` REST(GET/PUT, 핫리로드). 4축=분류·평가·실행·의식. per-agent 모델 폐지(yaml provider/model/apiKey 무시, 모델·키 티어 상속). 폰 엔진 번들=`data/bodies/*.json` 프로파일 파생(`build_body_bundle.py`). 142 액션·38 도구 패키지. 이전(2026-06-27) — 앱 표면 품질 일괄 개선(라디오 즐겨찾기·CCTV 인앱 재생 stream 버튼·여행 날짜+한국 지방공항·투자 TIGER200·날씨 오송·문화 지역·길찾기 거리/예상시간) + 부동산 직방 호가(sense:realty source:zigbang)·AI 공모/창업(sense:contest/startup) + read_guide claude_code 노출 + 폰 네이티브 재빌드. 142 액션(sense 44·self 44·limbs 17·others 11·engines 26)·38 도구 패키지. 이전(2026-06-22) — 국회도서관 국가학술정보(LOSI) 인물/학위논문 액션 추가: `[sense:researcher]`·`[sense:paper]{source: "nanet"}`(연구자·학위논문 검색, study 패키지). 외부 API 키 `NANET_API_KEY`(`.env`, losi-open.nanet.go.kr) + auth_manager 'nanet' 레지스트리. 5-Node 142 액션(sense 44·self 44·limbs 17·others 11·engines 26) / 38 패키지. 포식기억(forager) 추가로 기억 7종. 이전(2026-06-17) — 맥↔폰 양방향 연합 인증 라이브: 환경변수 `INDIEBIZ_PHONE_URL`(맥→폰 LAN)·`INDIEBIZ_PHONE_TOKEN`(공유 인증 토큰, 맥·폰 동일)·`INDIEBIZ_BIND_HOST`(폰 바인드 오버라이드; 미설정 시 토큰 있으면 0.0.0.0·없으면 127.0.0.1). 폰 `phone_api` 미들웨어가 비localhost 요청 토큰 검증, `AgentForegroundService`가 앱 없이 백엔드 상주, `provision_phone_keys.py`가 `.env`→폰 keys.json 토큰 푸시. 이전(2026-06-15) — 통화 대수(engines 변환자 9: filter/sort/take/select/dedup/groupby/join/union/merge + 파이프 문법 `|` + 문서 IR emitter) → 122~124에서 136 액션. 이전(2026-06-14) — 폰-로컬 in-process Gemini 두뇌(claude_code 원격 렌트 은퇴) + detect_body() 하드웨어 자기감지 + 상주 스케줄러(self:trigger/schedule 폰 바인딩) + 의료기록 CRDT 동기화/삭제 op + channel 트리거 맥 발화 경로 + 124 액션 정합화(폰 감각 삼각 + self:show_calendar 폐지). 이전(2026-06-12): /business/sync/* 동기화 엔드포인트(LWW+tombstone, self:phone_sync) + api_indienet REST 제거(IndieNet→IBL 계기) + 122 액션 + 해마 로컬 M4 Pro 재학습(code Top-5 92.6%/desc 92.8%). 이전(2026-06-10): 중급 모델 Reflex 전용화, 폰 컴패니언 피드(/phone API), NIP-17/44 모듈. 이전(2026-05-28): op 어휘 단일화 + 삼각 검증. 이전(2026-05-17): 3단계 모델 티어, 심층메모리 DB, XML 구조.*
