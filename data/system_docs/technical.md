---
title: 기술 참조
scope: API 엔드포인트, 설정 파일 위치, AI 프로바이더, 프롬프트 XML 구조, 감각 전처리
owner_code: api_*.py, providers/, ibl_engine.py
last_updated: 2026-08-31
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
- `GET /system-ai/status` - 준비 판정. `ready` 는 provider 를 본다(무키 프로바이더 claude_code·codex·ollama 는 키 없이 ready — `provider_needs_api_key` 정본, 2026-09-02 수리)
- `GET /system-ai/candidates` - 이 기계가 이미 가진 AI 후보 `{items:[{provider, model, source, kind, login?}]}` — 환경변수 키 · 설치된 CLI · 로컬 모델 서버 (`backend/base/ai_candidates.py`, 카탈로그=`data/ai_provider_catalog.yaml`)
- `POST /system-ai/probe` - `{provider, model, api_key?}` 실응답 1턴 검증. 실패는 원인별 kind(no_key/auth/model/cli_login/local_down/timeout…). 저장 안 함 — 검증 → 저장 순서 (첫 성공 온보딩, `api_onboarding.py`, 로컬 전용)
- `GET /system-ai/onboarding` · `POST /system-ai/onboarding/dismiss` - 온보딩 상태(`data/onboarding_state.json`, first_reply_at = `save_conversation("assistant")` 첫 기록)

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

### IBL 실행·번역 (/ibl) — api_ibl.py
- `POST /ibl/execute` — 문장 실행. `POST /ibl/translate`(자연어→IBL, 조종실) · `POST /ibl/validate`(dry-run: 부작용 미리보기 + `typecheck`{ok, issues, types, fn_returns} — 정적 통화 검사, 2026-09-05; `/ibl/execute` 의 `check: true` 도 같은 검사만 돌려준다) · `POST /ibl/distill`(성공 실행을 해마에 증류) · `GET /ibl/actions/catalog` · `POST /ibl/read_guide` · `POST /ibl/embed`(폰-자아 해마 인코더 렌트) · `POST /ibl/recover`(표면 티켓 회수 — 아래)
- **요청 봉투 = 행위자 3칸 + 표면**(2026-08-21): `agent_id`(발신 신원 — 없으면 `system_ai`, 이 표면은 전부 소유자 게이트 뒤다) · `task_id`(위임 체인 — 아웃오브프로세스 재진입이 부모 태스크를 복원하는 통로) · `origin`(출처. `user`=사람의 직접 명령, 포털 경유는 `portal`. 없으면 무출처로 원장에 남는다) · `surface`(`web`=원격런처/포털/폰 WebView — "소리가 어디서 나야 하는가"의 판정 축. 데스크탑은 보내지 않는다) · `project_id`/`project_path`.
- **응답 봉투 = 다이어트**(2026-08-22 M1): `results[]` 는 step 요약(shape·count·bytes·columns·preview, 실패 step 은 오류문 원형), `final_result` 만 원형. 옛 모양은 `verbose: true`. 실패 시 `resume:{from_step, prev_ref}` 가 실리고 `execute_ibl(code, resume)` 로 앞 단 재실행 0으로 이어붙인다.
- **자동 스필**: 이음매 통화가 200K자를 넘으면 `data/spill/` 참조 봉투로 바뀐다(소비자 투명 해소, cache 계급 24h GC). `[self:write]{spill: true}` 는 명시적 싱크.
- **표면 티켓 회수 규약**(2026-08-27 F51-1): 표면(MCP 등)이 `ticket`(hex 12자, 전송 계층 필드)을 실어 보내면 백엔드가 시작·결말 봉투를 `data/spill/` 에 남긴다(24h GC 동승). 표면의 HTTP 대기가 먼저 끊겨도 그것은 "실행이 죽었다"가 아니라 **"기다림이 끝났다"** 이므로, 정직한 봉투(ticket + 회수법)를 돌려주고 결과는 `execute_ibl{recover}` → `POST /ibl/recover` 로 회수한다. 상태 셋(`done`/`running`/`unknown`)을 뭉개지 않는다. **유한 대기**(2026-09-01): 회수에 `wait` 초(≤240, `[self:script]{op:"status", wait}` 와 같은 계약)를 주면 결말이 날 때까지 기다렸다 돌려준다 — 대기가 먼저 끝나면 `waited` 와 함께 진행 상태를 준다(기다림이 끝난 것이지 실행이 죽은 것이 아니다). 이 통로가 없던 동안 부르는 쪽은 셸 `sleep` 으로 대기를 흉내 내다 몇 초 간격 폴링으로 무너졌다(09-01 실측: 한 주행의 도구 호출 45건 중 16건이 기다림). ★타임아웃 연장은 임시방편이다 — 어떤 한도든 더 긴 문장에 진다. 유한 대기의 반복이라야 어떤 길이의 실행도 덮는다. 티켓 검증은 hex 만 통과(네트워크 값이 파일명이 되는 자리 — 경로 탈출 차단). 가드 `backend/test_surface_ticket_recovery.py` T1~T8. **2026-09-05**: `execute_ibl` 의 `wait`(≤240) 는 처음 실행에도 통한다 — 120초를 넘길 것을 아는 호출은 처음부터 표면 대기를 늘려 타임아웃 봉투→회수 왕복을 없앤다(ep2829 세 번).
- **진행 신고 규약 — 좌표는 소유하고 움직임은 공유한다**(2026-09-01, 정본=`backend/ibl/ibl_progress.py`): `running` 회수는 프로그램 좌표(`step`/`of`/`action`)와 회차(`detail`: each 의 `row`/`rows`, 하위 파이프의 `substep`/`substeps`)를 함께 싣는다. 좌표는 **프로그램의 좌표를 아는 자**가 한 번만 집고(파이프면 `execute_pipeline`, 단일 step 이면 초크포인트 `system_tools_ibl`), 그 아래 모든 깊이는 `detail` 칸만 갱신한다 — 안쪽이 바깥의 좌표를 덮으면 좌표가 거짓이 된다. `updated_at` 은 **마지막 움직임** 시각이라, 회수를 두 번 물어 그 값이 바뀌면 도는 중이고 안 바뀌면 멈춘 것이다(멈춤 ↔ 느림 판별의 유일한 증거 — 이게 없어 23분 무한 대기를 눈감고 기다린 09-01 사고). 가드 `backend/test_each_progress_visibility.py`.
- 실행은 워커 스레드에서 돈다(`asyncio.to_thread`) — 블로킹 핸들러가 이벤트 루프를 잡으면 그 대기를 풀어줄 요청 자체를 못 받아 자기교착한다.

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

### GoalEval과 SelfReflect의 실행 조건

- `THINK`: ConsciousnessAgent가 `achievement_criteria`를 만들면 GoalEval이 최대 3라운드 평가·재실행한다.
- `EXECUTE`: `consciousness_output=None`이므로 GoalEval에 진입하지 않는다. 도구 실패·복잡 궤적·세계 변경이 있으면 실행기 자신의 SelfReflect가 한 번 돈다.
- `Reflex`와 강제 역할 실행은 SelfReflect도 생략한다.
- `episode_summary.evaluation_result`는 GoalEval 구조 마커의 마지막 라운드를 저장한다. `NULL`은 평가 미실행이며 실패와 동의어가 아니다.
- **현재 실패 의미론 주의**: 평가 모델이 빈 응답/API 오류를 내면 `_evaluate_achievement()`는 턴을 깨지 않기 위해 성공으로 통과시키고 로그에 `AI 응답 없음 (API 오류 등), 통과 처리`를 남긴다. 그러므로 `ACHIEVED`만으로 외부 효과 완료를 단정하지 말고 action ledger·생성 파일·배포/HTTP 같은 증거를 함께 본다. 이 fail-open은 현행 동작을 정직하게 기록한 것이며, 신뢰성 개선 대상이다.

## IBL 도구 — execute_ibl

모든 에이전트는 `execute_ibl(code='[node:action]{params}')` 단일 도구로 IBL을 호출. 6노드(sense/self/limbs/others/engines/table) 전 액션의 정의·카테고리·라우팅 방식은 **ibl.md** 참조(액션 수는 아래 '물리적 구조'의 빌드 파생 수치).

예시:
```
execute_ibl(code='[sense:stock]{op: "quote", ticker: "AAPL"}')
execute_ibl(code='[sense:search]{query: "AI"} >> [self:write]{path: "result.md"}')
execute_ibl(code='[sense:stock]{op: "quote", ticker: "AAPL"} & [sense:stock]{op: "quote", ticker: "MSFT"}')

# 고차 문장 — 찾은 것 *각각*에 IBL 문장을 적용 (2026-08-15 신설)
execute_ibl(code='[sense:search]{query: "AI"} >> [table:each]{as: "row", do: "[self:notify_user]{message: \'{row.title}\'}"}')

# 블록 — 조건 분기. 문장 위치에 통째로 쓰거나, 2026-08-22부터 **파이프 한 칸**으로도 쓴다
#   (`[A] >> [if: count($items) > 0]{…} >> [B]` — 블록이 직전 통화를 $items 로 받는다).
#   좌변은 IBL 소스 참조 `node:action{params}[.field]` 또는 `$변수[.경로]`·count()/empty()/exists() —
#   자연어 조건은 평가되지 않는다(판정 불능은 조용한 false 가 아니라 오류).
execute_ibl(code='[if: sense:host{op: "status"}.cpu_percent > 80]{[self:notify_user]{message: "CPU 과부하"}}')
```

문법 정본은 교재 `data/common_prompts/fragments/12_ibl_only.md`(에이전트 + 조종실 번역기 공용, **캐시 없음 = 수정 즉시 라이브**)와 **ibl.md**.

**자동 발견**: `ibl_engine._merge_api_registry_actions()`가 로드 시 `api_registry.yaml`의 node 바인딩 도구를 노드 액션에 자동 병합.

**인프라 노드 (항상 허용)**: `self`, `others`, `table` — 모든 에이전트에 자동 제공. 노드 yaml의 `always_on: true` 플래그가 단일 소스 (`ibl_access._always_allowed()`가 레지스트리에서 읽음, 노드 on/off 기능의 토대)

## 설정 파일 위치
- **모델 기어 (계기판 변속)**: `data/model_gear.json` — 현재 기어(절약/균형/최대) + 프리셋(기어 × 축 → 티어) + 에이전트 핀(overrides). `backend/base/model_resolver.py`가 *역할 → 축 → 기어 → 티어*로 해소하고 매 호출 읽기(핫리로드). 아래 3개 티어 설정은 이제 **모델 슬롯**(고급=system_ai 재사용)이고, 어느 축이 어느 슬롯을 쓰는지는 기어가 정함. 에이전트별 모델 설정은 폐지(yaml provider/model/apiKey 무시, 모델·키 모두 티어 상속).
- **고급 AI 슬롯 (구 '본격' / 시스템 AI config 재사용)**: `data/system_ai_config.json`
- **중급 AI 슬롯**: `data/midtier_ai_config.json`
- **경량 AI 슬롯 (원샷=분류·평가·증류 등)**: `data/lightweight_ai_config.json`
- **비전 슬롯 (`modality.image`, 2026-08-27)**: `data/vision_ai_config.json` — `{provider, model}` **데이터**(키는 `.env` 정본). 텍스트 4축 티어에는 비전이 없어 기어의 예약석을 실채운 자리다. `get_vision_provider()` 가 해소하고, 원샷(`oneshot`/`system_ai_call`)이 `images` 를 감지하면 **0차로 우선**한다 — GoalEval 의 시각 평가까지 같은 이음매를 타므로 프리셋과 무관하다. 미설정이면 `(None, 사유)` 를 돌려 role-축 프로바이더로 **정직하게 폴백**한다(새 설치가 조용히 깨지지 않는다). ★**벤더 이름이 코드에 박히면 그 모델의 은퇴가 곧 몸의 고장이다** — 실제로 구 하드코딩 모델의 은퇴 404 를 데이터 한 줄 교체로 흡수했다. 벤더 URL·키 직참조 금지는 관문(`test_vision_gear_contract`)이 지킨다. 정본 = `docs/MODEL_GEAR_DESIGN.md` 모달리티 절.
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
- **해마 학습 데이터**: `data/training/ibl_training_balanced_20260516.json` + `data/training/ibl_distilled.json`. 빠르게 변하는 usage DB 건수는 `SELECT count(*) FROM ibl_examples` 실측이 정본이다. 라이브 세대·측정표·재학습 대기열은 **memory.md '현재 라이브 모델'** 이 정본이고, 절차·함정은 `data/guides/hippocampus_retraining.md`. 재학습 경로는 **로컬 Mac M4 Pro(MPS)** 가 정본(클라우드 Modal 경로는 보존만).
- **폰 컴패니언 피드 DB**: `data/phone_notifications.db` (SQLite — 알림·위치·걸음. `backend/services/phone_notifications.py`가 NIP-17 수신분 저장, 인가 폰 신원은 `data/phone_agent.json`). 조회 API `/phone/notifications|locations|steps` (`backend/surface/api_phone.py`) + `[sense:phone]{op}`
- **NIP-17/NIP-44 모듈**: `backend/base/nip17.py` (gift-wrap DM) + `backend/base/nip44.py` (암호화, 공식 테스트 벡터 150/150). channel_engine 송신은 NIP-17, 수신은 NIP-04+NIP-17 병행 fan-out
- **외부 API 키 (`.env`)**: 패키지 핸들러가 외부 서비스 호출 시 `.env`에서 로드. 예: `NANET_API_KEY` — 국회도서관 국가학술정보(LOSI) OpenAPI (losi-open.nanet.go.kr, 연구자·학위논문 검색 `[sense:researcher]`·`[sense:paper]{source: "nanet"}`, study 패키지, auth_manager 'nanet' 레지스트리).
- **IBL 노드 정의 (소스)**: `data/ibl_nodes_src/{meta,sense,self,limbs,others,engines,table}.yaml` — 단일 진실 소스, 직접 편집. op-bearing 액션은 `ops: {default, values}` 블록 의무.
- **IBL 노드 정의 (빌드 산출물)**: `data/ibl_nodes.yaml` — `scripts/build_ibl_nodes.py`로 생성, 런타임 로드, 직접 편집 금지
- **웹앱 등기부**: `data/webapps.json` — **파생 밖 예외만** 담는 수동 보충분(원장 아님). 진실 소스 7곳(포털·게시판·가족신문·공개파일·정기보고·web-builder `sites.json`·`outputs/web-projects/*/wrangler.toml`)은 `data/packages/installed/tools/system_essentials/webapp_registry.py` 가 매 호출 재계산. 어휘 `[self:webapp]{op}`.
- **이웃 창고 둘러보기 시드**: `data/warehouse_directory.json` — 장르별 후보 목록(자가 생성·사용자 편집 가능). live 경로는 Neocities 태그 브라우즈를 요청 1회로 파싱.
- **IBL 검증 게이트**: `scripts/git-hooks/pre-commit` (commit 시점) + `world_pulse_health.run_daily_health_check` (**하루 1회** — `scripts/ibl_health_check.py` 를 subprocess 로 돌려 §1A 정적·§1B fixture 통화·§1C 골든 파이프를 `self_checks` 에 기록, `__static__:ibl_consistency` 식별자. AI 0)
- **이음매 가드(액션 아닌 것의 시민권, 2026-07-25~26)**: `scripts/check_event_loop.py`(async 본문의 동기 블로킹 = 자기교착 부류) · `scripts/check_public_routes.py`(공개 노출 ↔ 인증 대조 — 오라클은 살아있는 `app.routes`, 공허한 통과 금지) · `scripts/check_win_portability.py`(유닉스 전용 stdlib 무가드 import — ★위험지대는 `data/packages/`) · `scripts/ci_import_smoke.py`. pre-commit + `.github/workflows/`(우분투 정적 스캔 + windows-latest 부팅 등가 스모크 + **신선 clone** 게이트).
- **경로 펼침 단일 해소점 (2026-09-02)**: `backend/base/runtime_utils.expand_body_path` — `~workspace/…`(몸의 기준 경로 = `get_base_path()`)·`~` 를 펼치는 유일한 자리. IBL 표면의 경로 파라미터는 전부 이 함수를 지난다(`scripts/check_body_path_expansion.py`, pre-commit — 직접 `expanduser` 금지, 예외는 `# path-ok: <사유>`). 셸 표면은 `$INDIEBIZ_BASE_PATH`(api.py 가 부팅 때 수출). 언어 조항은 ibl.md scope 절.
- **부팅 관측**: `backend/datastore/boot_status.py` — lifespan 의 '실패(무시)' 블록 10개를 성패 계측, `/world-pulse/health` 의 `boot` 절로 노출(하나라도 실패면 overall=degraded).
- **표준 코어 경계 (설치·업데이트 이음매, 2026-07-10~)**: `data/core_manifest.json` — 코어 vs 사용자(어휘·앱) 경계의 **단일 진실**. `scripts/build_core_manifest.py`가 **git 추적 집합**(=배포에 딸려오는 것)에서 파생·커밋(installed+not_installed 양쪽 패키지·계기·중앙 어휘). 손목록 없음. **opt-out**: 개인 패키지·앱·절차를 커밋해도 코어에서 빼려면 `<패키지>/.origin` 파일에 `user`(계기 yaml 최상위 `origin: user`, 등록 스크립트는 `data/scripts/registry.yaml` 항목의 `origin: user` — 2026-09-02, 매니페스트 `core.scripts`·설치 필터 `!scripts/<파일>` 로 집행). 런타임 origin은 `backend/package_manager.resolve_package_origin()`가 이 매니페스트로 해소해 `/packages` 응답에 `origin: core|user` 노출. **가드**: pre-commit + `build_ibl_nodes.py --check`에 core_manifest·dist_filter 신선도 합류.
- **설치 파일 필터 (코어 기준 배포)**: `scripts/build_dist_filter.py` — `frontend/package.json`의 electron-builder `data` 필터에서 sentinel(`!__GEN_START/END__`) 구간을 매니페스트 주도로 생성(비-코어 패키지·계기 제외 + 개인 크러프트 `.fuse_hidden*`·최상위 `*.md/*.html/*.png`·`*.bak*` 제외). 기존 secret 손목록은 보존(순수 추가). `npm run electron:build*`가 `dist:filter`(predist=매니페스트 재생성)를 프리스텝으로 실행.
- **git 경로 업그레이드 레시피**: `scripts/update.py`(bootstrap.py 의 짝, 2026-09-02) — 코어 패키지의 사용자 배치(installed↔not_installed, git 기본과 다른 것)를 걷었다가 `git pull --ff-only` 뒤 다시 놓는다. 폴더 위치=진실 규칙은 그대로(런타임 독자 20여 곳 무변경), 당기는 동안만 배치를 비운다. 실패 시 배치 원복·정직한 중단(stash 없음). 양쪽에 다 있는 패키지(맨손 pull 의 흔적 — 상류가 고친 파일만 옛 자리에 되살아난 반쪽)는 충돌로 신고. requirements 변경 시 .venv 재설치. 상류 은퇴 패키지는 신고만.
- **모델 프로바이더 카탈로그**: `data/ai_provider_catalog.yaml` — 프로바이더별 env 변수·CLI 명령·로그인 흔적·로컬 tags URL·기본 모델(세계의 명사=데이터). `model_resolver.env_var_for_provider` 와 온보딩 후보 탐지가 읽는다. 새 벤더는 코드가 아니라 여기.
- **스키마 버전 레지스트리**: `backend/datastore/schema_migrations.py` — SQLite `PRAGMA user_version` 기준, DB 이름별 `(version, 설명, fn)` 목록. 각 DB 모듈 `_init_db` 가 CREATE TABLE 뒤 `apply()`. 한 버전=한 트랜잭션, 실패=예외(반쯤 적용 금지 → 서브시스템 실패로 boot_status 기록). 옛 `migrate_storage_action.py`·`migrate_cctv_action.py` 의 DB 부분은 v1 로 흡수·은퇴.
- **업데이트 시 사용자 보존 규칙 (`frontend/electron/userdata_sync.js`, 2026-09-02 트랜잭션화 — 종전 `bootstrap.js` `initUserData` 위임)**: 덮어쓰기 전 원본을 `data/_backups/<날짜>_upgrade/files/` 로 뜨고 저널(`journal.jsonl`, `{op, path, backup}`)에 한 줄 → `data/.upgrade_pending` 표식 → 완료 시 회수. 다음 기동에 표식이 남아 있으면(도중 죽음) 저널로 되감고 재동기화. 내용 같은 파일은 무변경(같은 버전 재기동=저널 0줄). 매니페스트 `retired`(코어였다가 사라진 패키지·계기·어휘 조각, `build_core_manifest.py` 가 직전 매니페스트 차집합을 누적)는 **격리 이동**(`_backups/<날짜>_upgrade/retired/`, 실삭제 아님 — 사용자 판정). 관문=`scripts/ci_upgrade_smoke.py`(직전 태그 설치본 → 업그레이드 → 부팅·보존·롤백·은퇴, CI `upgrade-smoke`). 종전 규칙: 재설치·업데이트가 **코어 소유 파일만 갱신**하고 사용자 것은 불가침. (1) 코어 어휘 산출물(`ibl_nodes.yaml`·코어 패키지 `ibl_actions.yaml`·코어 계기 yaml)은 매니페스트 기준 강제 갱신(`makeCoreForceOverwrite`). (2) 패키지 **설치 상태**(installed/not_installed 폴더 배치=사용자의 켜고/끈 선택)는 `syncPackagesPreservingState`가 userData의 *현재 위치*에서 그 자리 갱신, 신규만 번들 기본 폴더로 추가 → 사용자 선택 불가침. (3) 대화(`.db`)·설정(json)·사용자 직접만든(미추적) 패키지는 애초에 건드리지 않음.

## 지원 AI 프로바이더 (모두 스트리밍 지원)
`backend/providers/`: anthropic · openai · gemini · gemini_http · deepseek · openrouter · ollama · claude_code · codex
- **Anthropic Claude** / **OpenAI GPT** / **Google Gemini**(HTTP 경량 경로 `gemini_http` 포함 — 폰도 쓰는 키-only 경로) / **DeepSeek**(V4 Pro·Flash, OpenAI 호환 API, 2026-07-22 신설) / **OpenRouter** / **Ollama**(로컬) / **claude_code**·**codex**(하네스 렌트)
- **아웃오브프로세스 CLI 프로바이더 두 종**(`claude_code`·`codex`, 2026-08-31 codex 신설): CLI 를 subprocess 로 띄워 JSONL 을 내부 이벤트 어휘로 번역한다. 몸통은 `providers/cli_provider.py` 의 `CliSubprocessProvider` 공유 — 세션 영속(resume+크기 리셋)·신원 전파(episode/run/task/origin/agent_id 를 env·헤더로)·지도 봉투 재주입·정직 표지 요약·resume 실패 폴백·과부하 backoff 가 전부 거기 산다. 벤더 파일에는 바이너리 탐지·인증 격리·이벤트 번역·도구 정책만 남는다. 둘 다 **구독 인증**이라 API 키가 없다(`model_resolver._NO_KEY_PROVIDERS`; 판정은 `provider_needs_api_key()` 한 곳에서만 — 손복사 집합은 관문 `test_cli_provider_gates` 가 금지한다). 도구 브리지는 같은 `mcp_server.py`(execute_ibl·read_guide)를 공유하며 실명도 `mcp__indiebizos__*` 로 같다.
  - ★**어휘 누수 방어가 서로 다르다**: claude_code 는 `--disallowed-tools` 로 Read·Grep·WebSearch 를 하드 차단해 IBL 등가물을 강제하지만, codex 의 파일 접근은 전부 shell 하나로 들어와 끌 수 없다(끄면 아무 일도 못 한다). codex 에서 설정으로 막는 건 web_search 뿐이고 나머지는 프롬프트가 감당한다 — 즉 **codex 쪽 누수 위험이 구조적으로 크다**. 누수가 의심되면 프롬프트를 덧대지 말고 `episode_log` 로 실측한 뒤 판정할 것.
  - **codex 의 모델 표기 = `슬러그` 또는 `슬러그:추론강도`**(예: `gpt-5.6-sol:high`). Codex 는 모델과 추론강도가 **별개 축**이라(`-m` 과 `-c model_reasoning_effort`), 티어 설정의 `model` 한 칸이 둘을 함께 싣는다. ★별도 설정 칸이 아닌 이유는 편의가 아니라 캐시 정합이다 — 프로바이더 캐시 키가 `bucket|provider|model|keyhash` 라, 강도가 그 문자열 밖에 있으면 같은 슬러그를 쓰는 두 티어(고급=`sol:max` · 중급=`sol:low`)가 **캐시에서 충돌해 에러 없이 강도가 뒤바뀐다**. 강도를 안 적으면 사용자의 `~/.codex/config.toml` 을 따른다(ChatGPT 데스크톱 앱이 바꾸는 값이므로, 재현 가능한 비용·품질을 원하면 티어에 적을 것). 철자가 틀리면 경고 후 무시한다. **모델 슬러그·지원 강도의 정본은 우리가 아니라 `~/.codex/models_cache.json`**(원격 갱신 캐시) — 목록을 문서에 베끼지 않는다(모델명 하드코딩은 은퇴로 죽는다).
  - `--ignore-user-config` 를 원샷 다이어트에 **쓰지 않는다**(2026-08-31 실측 기각): 같은 질문에서 17,222→16,270 토큰(5.5%)만 아끼면서 사용자의 `model_reasoning_effort` 를 빼앗아 원샷만 모델 기본 강도로 떨어뜨린다 — 경로마다 강도가 다르면 비용도 품질도 재현되지 않는다. 남는 16K 는 Codex 자신의 기본 지침·AGENTS.md·작업공간 맥락이라 이 플래그로는 못 깎는다.
  - ★**codex 는 시스템 프롬프트를 붙일 플래그가 없다**(`--append-system-prompt` 등가물 부재). fresh 턴 프롬프트 머리에 싣고 resume 턴엔 생략하므로, 프롬프트가 바뀌면 세션 키(`키#프롬프트해시`)가 바뀌어 자동으로 fresh 로 끊긴다. '새 대화' 리셋은 `providers.clear_cli_sessions_for_agent` 가 접두 스윕으로 파생 키까지 지운다.
- 모델·API 키는 **모델 기어**가 해소한 티어에서 상속(에이전트별 설정 폐지). 구체 모델 ID 는 `data/*_ai_config.json` 슬롯이 보유 — 이 문서는 목록만 유지(모델명은 빨리 낡는다).
- ★함정: Gemini `flash-latest` 별칭은 `thinkingConfig.thinkingBudget:0` 을 400 으로 거부 — 버전 명시(`gemini-2.5-flash`) 필요.

### Tool Result 절삭
- **기본 한도**: 16KB — tool result가 이 크기를 초과하면 절삭
- **파이프라인 시**: `_action_count × 16KB` 허용 (다중 액션 실행 시 비례 확장)
- **계기: 결과천자**(2026-08-28) — 등록 스크립트 `에피소드통계` 가 에피소드별로 **모델이 도구 결과로 읽은 문자수**를 낸다. `tool_result` 줄의 보이는 몫 + 절단 표식 `(+N자)` 의 숨긴 글자수 = 정확값(로그 절단은 기록을 자른 것이지 모델이 받은 결과를 자른 게 아니다). 옛 `...` 행은 하한 표지 동반, 결과 줄이 없는 in-process 방언은 `None`(0 과 구분).
- **왜 재는가**: 15일 실측에서 도구 실행은 총 시간의 한 자릿수 %이고 거의 전부가 모델 왕복인데, **왕복당 모델 시간이 읽는 양에 따라 20~28초로 움직였다** — 속도의 지렛대는 왕복 수가 아니라 읽은 문자수다. 처방은 목록·후보를 표 꼬리로 얇게 흘리고 원문 정독은 선별 통과분에만 하는 **읽기-접기**(내용 판단에 필요한 정독까지 접는 것은 아니다).

### 감각 전처리 (Sensory Preprocessing)
- 액션 출력을 경량 AI로 압축해 컨텍스트 폭발을 막는 층. 코어 src 또는 패키지 `ibl_actions.yaml`의 `postprocess` 블록으로 액션별 선언
- **현재 선언한 액션은 0개**(2026-06-27~): 압축이 구조화 통화 `items[]`를 문자열로 파괴하던 결함이 드러나, 검색·여행계가 전부 `items` + 사람용 `message`로 옮겨가며 compress가 폐지됐다. 엔진의 기계와 우회 플래그(`params._raw`)는 남아 있다
- 컨텍스트 폭발의 현행 대책은 압축이 아니라 **봉투 다이어트 + 자동 스필**(위 `/ibl/execute` 절)
- 구현: `backend/ibl/ibl_engine.py`의 `_postprocess()` → `_pp_compress()`

### IBL 액션 단일 진실 소스 (2026-05-28~)
- 어휘 소스는 소유권에 따라 둘이다: `data/ibl_nodes_src/` 7개 yaml(meta + 6개 노드)은 패키지와 무관한 코어 어휘, 설치 패키지의 `ibl_actions.yaml`은 그 능력과 함께 설치·제거되는 패키지 어휘다
- `python3 scripts/build_ibl_nodes.py`로 `data/ibl_nodes.yaml` 빌드 (명시적, 자동 등록 없음)
- 빌드는 설치된 package fragment만 합쳐 `ibl_nodes.yaml`·`tool.json`·fixture·문서 마커를 파생한다. 패키지 폴더 이동만 하고 빌드하지 않으면 런타임 레지스트리는 바뀌지 않는다
- **삼각 검증** (`--check`): src ↔ tool.json ↔ handler.py `_OP_DISPATCHERS` 3중 일치 AST 정확 비교
  - 등록: src.tool ↔ tool.json.name
  - op enum: src.ops.values 키 ↔ tool.json input_schema.properties.op.enum
  - default: src.ops.default ↔ tool.json input_schema.properties.op.default
  - dispatcher: src.ops.values 키 ↔ handler.py `_OP_DISPATCHERS[tool_name]` dict 키
- **이중 게이트**: pre-commit 훅(commit 시점) + 일일 건강 점검(하루 1회, `__static__:ibl_consistency` 식별자)
- **dispatcher 표준** (op 분기 패키지·액션 수는 아래 '물리적 구조'의 빌드 파생 수치; 일부 op 액션은 패키지 밖 backend-native): `_OP_DISPATCHERS = {tool_name: {op: handler_or_None}}` 모듈 레벨 dict 노출 의무

### 에이전트가 새 액션/op를 알게 되는 경로

실행 스키마와 에이전트의 IBL 교재는 다른 층이다.

- `description`과 `ops.values`: `ibl_access._emit_action_line()`이 매 턴 카탈로그에 방출 — 기능의 존재와 op 의미
- `target_description`: UI/저술용 상세 산문. 현재 에이전트 카탈로그에는 직접 실리지 않는다
- `tool_json.input_schema`: 라우팅·검증·도구 스키마 파생용. 자연어에서 IBL을 고르는 해마 사례를 대신하지 않는다
- `ibl_usage.db:ibl_examples`: 자연어→IBL 코드의 즉시 검색 교재. 첫 등록은 `add_examples_batch`로 시드하고 재학습용 데이터에도 남긴다
- `data/ibl_param_shapes.json`: 코퍼스와 실제 실행에서 관측한 인자 키. `scripts/ibl_param_sweep.py`가 생성하며 카탈로그의 `⟨인자: …⟩`가 된다
- `data/ibl_partners.json`: 코퍼스와 실제 실행에서 관측한 **조합 파트너**(그 낱말 뒤에 실제로 이어진 낱말). `scripts/ibl_partner_sweep.py`가 생성하며 카탈로그의 `⟨동반: …⟩`가 된다(상위 2·최소 3회, 주간 재관측). 자기 자신으로 가는 `>>`는 동반이 아니라 접힐 자리라 싣지 않는다. 관측이 없어 안 붙은 줄은 '조합 불가'가 아니며, 그 규칙(items를 내는 액션은 `>> [table:*]`)은 범례가 한 번만 말한다

따라서 빌드·fixture 통과는 “실행 가능”, 카탈로그 노출은 “존재 인지”, 해마 연상 프로브는 “자연어 선택 가능”, param sweep은 “호출 모양 인지”, partner sweep은 “이웃 인지(조합 가능성)”를 각각 증명한다. `/packages/reload`는 `handler.py`만 라이브 교체하므로 `tool_*.py`·서브모듈 변경은 백엔드 재기동이 필요하다.

## 물리적 구조 (주요 경로)

> 아래 마커 구간의 수치는 `scripts/build_ibl_nodes.py`가 재생성한다(손 수정 금지). 계수 기준=git 추적·test_* 제외.

<!-- IBL_STATS:START -->
- `backend/`: 서버 소스 코드 — **층=디렉토리**(2026-08-05 물리 이동). 의존은 아래→위 한 방향:
  `base`(26) → `datastore`(40) → `ibl`(42) → `cognition`(48) → `services`(28) → `surface`(61). `.py` 총 301개(test 제외).
  - ★**모듈 이름은 평면**(`import ibl_engine`) — `backend/boot_paths.py` 가 층 경로를 `sys.path` 에 얹는다.
  - 새 backend 모듈 = 층 폴더에 두고 `scripts/check_backend_layers.py` 의 `LAYERS` 에 배정. 독립 스크립트는 맨 위에 `import boot_paths`.
  - 층 밖 공용: `backend/common/`(16) · `backend/providers/`(13, AI 프로바이더 스트리밍) · `backend/channels/`(4) · `backend/drivers/`(3)
- `data/`: 시스템 설정 및 데이터
- `data/packages/installed/tools/`: 설치된 도구 패키지 (**41개** — op 분기 **29개**가 `_OP_DISPATCHERS` 표준)
- `data/packages/installed/extensions/`: 백엔드 코어 모듈 (**5개**)
- `data/api_registry.yaml`: API 도구 정의 — 45개 도구 중 37개가 `node: sense` 로 바인딩돼 로드 시 노드 액션에 자동 병합(`ibl_engine._merge_api_registry_actions`, 2026-08-22 실측)
- `data/scripts/`: **등록 스크립트**(`registry.yaml` + `<이름>.py`) — `[self:script]{op: run}` 이 id 로만 실행. 어휘가 아니라 *절차*의 거처
- `data/private_nouns.txt`: **개인 명사 관문 목록**(gitignore, 로컬 전용) — `scripts/check_private_nouns.py`(pre-commit, 모든 스테이지 파일)가 가족·개인 이름·목소리 키가 몸(코드·어휘·가이드·문서)에 박히는 것을 막는다. 한 줄=정규식, `allow: <glob>`=면제(저자 서명·연구 기록). 이름 자체가 저장소에 들어오지 않는 구조(2026-09-02)
- `data/instruments/`: standalone 앱 매니페스트 (어휘 없는 계기 — report·newspaper·audio_briefing)
- `data/guides/`: 가이드 71개 (guide_db 등록 70). `codebase_map.md` 는 system_structure.md 에서 **자동 파생**이므로 직접 편집 금지
<!-- IBL_STATS:END -->
- `projects/`: 사용자 프로젝트 데이터 (24개 — 시스템 프로젝트 수동모드·앱모드 포함)
- `data/_backups/YYYY-MM-DD_<이름>/`: **일회성 백업의 유일한 주소**(2026-08-14 규약). 작업 폴더·`data/` 루트에 `*_backup*` 사본 금지. **git 추적 대상이 아니다** — 규약 정본 `README.md` 하나만 `!` 예외
- `scripts/`: 빌드/배포 스크립트 (`build_ibl_nodes.py` + `build_core_manifest.py`[표준 코어 매니페스트] + `build_dist_filter.py`[설치 파일 필터] + `build_body_bundle.py`[폰 번들] + `check_backend_layers.py`[층 가드] + `check_tracked_ignored.py`[추적∩무시=0] + `git-hooks/pre-commit`)
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
- `<execution_map>` - 실행기억 지도(가지·용례 수·요약·`guide:` 가이드 목차 — 옛 `<available_guides>` 대체, 2026-09-03)
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
*최근 변경(2026-08-28): `/ibl/recover` 표면 티켓 회수 규약, 비전 슬롯(`modality.image`)의 벤더 중립화, Tool Result 절삭 절에 '결과천자' 계기 추가. 모델명·수치는 슬롯 설정과 파생 마커가 정본. 이력 정본=git log·changelog.log(`[self:body]` 회상).*
