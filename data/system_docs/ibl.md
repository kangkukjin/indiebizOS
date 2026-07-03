---
title: IBL (IndieBiz Logic)
scope: IBL 명세, 5-Node 구조, 143 액션, 파서/엔진/라우팅
owner_code: ibl_engine.py, ibl_parser.py, ibl_access.py, ibl_routing.py
source_of_truth: data/ibl_nodes_src/{meta,sense,self,limbs,others,engines}.yaml
build_tool: scripts/build_ibl_nodes.py
last_updated: 2026-06-22
see_also: [execution_memory.md, packages.md, technical.md]
---

# IBL (IndieBiz Logic)

> indiebizOS의 정보 흐름 추상화 언어

## IBL이 하는 일

IBL은 에이전트가 정보를 가져오고, 가공하고, 전달하는 과정을 하나의 패턴으로 표현한다.

```
[node:action]{params}
```

- **node**: 어디서 (sense, self, limbs, others, engines, table)
- **action**: 무엇을 (search, get, create, ...)
- **params**: 매개변수 ({query: "AI 뉴스", limit: 10, ...})

API든 크롤링이든 안드로이드든 DB든, 에이전트는 같은 문법으로 요청한다. 프로토콜의 차이는 드라이버가 감춘다.

> **주의**: 이전 `(target)` 문법은 더 이상 권장되지 않습니다. 이제 모든 매개변수(target 포함)는 `{}` 안에 키-값 형태로 전달합니다.

```
IBL 표현 계층:     [node:action]{params}
                         |
드라이버 계층:     http | websocket | adb | cdp | sqlite | file_io
                         |
물리 계층:         인터넷 | USB | 로컬디스크 | 프로세스간 통신
```

---

## 언어의 경계 — 표준과 사전 (헌법 조항)

브라우저 / HTML / 사용자의 HTML 파일이 서로 다른 것이듯, **하네스 / IBL 표준 / 개인 사전**은 서로 다른 층이며 섞이지 않는다. 이 구분이 두 이동성을 만든다: 다른 사용자는 같은 IBL 위에 자기 어휘를 가질 수 있고(어휘와 그에 키잉된 축적물 — 해마 코퍼스·임베딩·증류 — 은 사람을 따라감), 하네스(모델·에이전트 러너)는 갈아끼워도 언어와 축적물은 무사하다.

**IBL 표준** — 모든 IndieBiz 인스턴스가 공유하는 언어. 두 부분:
1. **문법**: `[node:action]{params}` 패턴, 연산자(`>>` 순차, `&` 병렬, `??` 폴백), `$변수`·`$file:N`, if/case/goal 블록, 파이프 설탕(`| where:` 등 → `[table:*]` desugar). 파서(`ibl_parser.py`)는 이름-무검증 — 모르는 어휘도 문법적으로 파싱한다.
2. **기능어 코어**: `self` / `others` / `table` — 노드 yaml의 `always_on: true` 플래그가 단일 소스. 언어학의 기능어(조사·전치사)처럼 닫힌 부류라 모든 화자가 공유하며, 특히 table(통화 변환 문법)은 파이프라인 생존에 필수라 어떤 노드 선별에서도 꺼지지 않는다.

**개인 사전** — 그 외 모든 내용어(sense·limbs·engines의 액션들). 정의(`ibl_nodes_src/`·패키지 `ibl_actions.yaml`)·구현(패키지 핸들러)·파라미터 별칭(`aliases:`)·프롬프트 설명까지 전부 데이터가 소유한다.

**규칙**:
- 내용어의 추가·개명·제거는 **사전 편집**이다 — yaml+핸들러만 바뀌고 파서·엔진 코드는 무수정이 불변식. 어휘 이름이 backend 코드에 박히면 경계 위반.
- 표준(문법·기능어 코어)을 바꾸는 것은 **언어 개정**이다 — 파서·desugar·always_on 플래그·이 조항·빌드의 `STANDARD_CORE_NODES` 선언을 함께, 의식적으로 바꾼다. 선언 없이 바꾸면 표준-코어 가드가 빌드를 멈춘다.
- 하네스 쪽 이음매는 `execute_ibl` 단 하나 — 하네스 기능(분류·의식·평가·회상)은 언어에 스며들지 않는다.

**집행**: `build_ibl_nodes.py --check`의 **표준-코어 가드**(always_on 집합 = `STANDARD_CORE_NODES` 선언 일치, 파서 desugar 타깃이 표준 코어의 실존 액션인지) — pre-commit 훅과 self-check 12h 순찰에 합류.

### 표현 언어의 층위 (부속 조항, 2026-07-03)

IBL(실행 언어) 위에 표현을 맡는 언어가 두 부류 더 있고, 셋은 섞이지 않는다. 판별축은 **파이프를 타는가**:

1. **페이로드 IR** — 파이프 안을 데이터로 흐르는 산출물 기술 언어: 문서 IR(blocks), 슬라이드 IR(slides), 차트 스펙(chart_type·bands·Plotly spec). 각각 특정 액션의 파라미터 계약이며 emitter가 소비해 산출물이 된다. 규율: 표준 외부 언어와 동형인 구간(문서 IR↔Markdown, 차트↔Plotly figure JSON)은 변환자로 왕복 가능하게 유지 — 언제든 표준 쪽으로 접을 수 있는 상태가 목표.
2. **표면 언어(`app:` 뷰 어휘)** — 파이프 밖에서 표면(계기)이 읽는 선언: 뷰 프리미티브·form 필드·뷰-이벤트. 렌더링 언어가 아니라 **통화↔액션 바인딩 언어**다(외부 표준이 존재하지 않는 유일한 층 — 픽셀·문서·차트는 전부 표준어에 위임돼 있다). 표현력 경쟁은 이 언어의 종목이 아니다(그건 escape=React·HTML 표준어의 일). 이 언어의 존재 이유는 {0토큰 표면 · 결정론(주권) · 저술 시점 검증 · 경량 모델 저술 가능}.

**표면 언어의 표준/사전 경계**: 어휘 집합과 해석기 — `build_ibl_nodes.py`의 `APP_VIEW_TYPES`·`APP_FORM_FIELD_TYPES`·`APP_VIEW_EVENTS` 선언 + 렌더러 2곳(`GenericInstrument.tsx`/`api_launcher_web.py`) + `validate_app_blocks` — 은 **표준**(본체 코드, 기본 설치)이다. 패키지는 뷰 단어를 추가할 수 없다(리트머스). `app:` 블록(어휘의 *사용*)은 **사전**(패키지 yaml·`data/instruments/` 데이터)이다.

**뷰 어휘 승격 기준(4)** — 새 뷰 단어는 전부 만족할 때만:
1. 기존 escape(bespoke 컴포넌트) 하나 이상을 은퇴시킨다 — 계기 하나의 미감은 사유가 아님(투기적 승격 금지)
2. 통화(items/blocks)를 소비한다
3. 3표면(데스크탑·원격·폰) 투영이 모두 의미 있다
4. 데이터-패턴/상호작용 계약이다 — **레이아웃·스타일(간격·색·열 배치)을 기술하기 시작하면 거부**. 그건 HTML 재발명의 냄새 = 정지 신호, escape로 보낸다. (UI 원자는 유한한 닫힌 부류라 이 어휘는 점근 수렴해야 정상 — escape 수가 다시 늘면 어휘 부족이 아니라 애초에 어휘로 풀 문제가 아니었는지부터 의심.)

**변경 = 언어 개정**: 뷰 단어의 추가·제거는 렌더러 2곳+검증자+문서 2곳(이 문서 "앱 표면 노출" 절 · `new_action_checklist.md`)을 함께 바꾸는 행위다. **집행**: 빌드의 **뷰-어휘 문서-동기 가드**가 두 문서의 어휘 줄("view 프리미티브 N종: …" / "form 필드 N종: …")을 코드 선언과 대조해 어긋나면 차단.

---

## 액션 카테고리

총 141개 액션(sense 44, self 44, limbs 17, others 11, engines 12, table 13)은 프롬프트 가독성을 위해 카테고리로 그룹화된다. 카테고리는 순수 표시 목적이며, 런타임 동작에 영향을 주지 않는다. 에이전트는 항상 구체적 액션명을 직접 사용해야 한다.

| 카테고리 | 의미 | 올바른 사용 예시 |
|---------|------|----------------|
| `search` | 찾기 | `[sense:search_ddg]{query: "AI 뉴스"}` |
| `get` | 가져오기 | `[sense:stock]{op: "quote", ticker: "AAPL"}` |
| `list` | 나열하기 | `[self:blog]{op: "posts"}` |
| `create` | 만들기 | `[engines:slide_shadcn]{slides: [{layout: "hero", title: "발표자료"}]}` |
| `control` | 조작하기 | `[limbs:screen]{op: "click", x: 100, y: 200}` |
| `fs` | 파일 조작 | `[self:read]{path: "report.pdf"}` |
| `io` | 결과 출력 | `[self:output]{op: "file", path: "result.md"}` |
| `send` | 보내기 | `[others:channel_send]{channel_type: "gmail", to: "user@mail.com", subject: "제목", body: "내용"}` |

프롬프트에서 `<action-categories>` 태그로 표시되며, 각 카테고리에 속한 구체적 액션명이 나열된다. RAG 시스템이 정확한 액션명을 안내하므로, 에이전트는 카테고리명이 아닌 액션명을 직접 써야 한다.

## 액션 group

각 액션은 `group` 필드를 가진다. group은 같은 노드 안에서 액션의 소속/맥락을 나타낸다. 예: limbs 노드의 `music`은 `group: media`이므로 미디어 재생, `browser`는 `group: browser`이므로 Playwright 브라우저 자동화다. discover에서 group명으로 검색할 수 있다.

| 노드 | 주요 group | 설명 |
|------|-----------|------|
| limbs | browser, screen, device(android), media, cctv, cloudflare, launcher | 각 제어 대상별 구분 |
| sense | investment, culture, research, location, cctv, web, real_estate, youtube, radio, shopping, world, device(phone) | 정보 소스별 구분 |
| self | photo, blog, memory, health, file, storage, schedule, workflow, event, collect, output, system | 관리 영역별 구분 |
| engines | media_produce, music, chart, web_builder, architecture | 생산물 유형별 구분 |
| others | delegation, channel, business | 소통 유형별 구분 |

## 액션 runs_on (어디서 도는가 — 폰 네이티브)

각 액션은 선택 필드 `runs_on`으로 실행 환경을 선언한다 (미지정=`anywhere`).
- `anywhere`(기본): 이식 가능 로직/HTTP. 단 handler/driver 라우터는 **검증된 폰 패키지**일 때만 폰서 실행.
- `mac_only`: 집 PC 하드웨어·무거운 의존·미검증 패키지(예: `limbs:os_open`/`open_window`=데스크탑 GUI, `self:manage_events`=무거운 api_system_ai 의존). 폰서 직접 실행 못 함 → **맥에 단건 라우팅**(아래 분산 IBL).
- `phone_only`: 폰 하드웨어 전용. 입력=`sense:phone`(알림 피드)·`sense:here`(현재위치)·`sense:listen`(마이크 받아쓰기/녹음)·`sense:see`(카메라 촬영), 출력=`limbs:phone`(알림·진동·토스트·복사·TTS·앱실행 + 문자·전화는 스테이징=작성창/다이얼러를 채워 열고 전송·통화는 사용자 탭). PC에선 graceful 거부(또는 INDIEBIZ_PHONE_URL 설정 시 분산 IBL 로 폰에 포워드).

**분산 IBL — 액션이 실행 단위(폰↔맥 연합)**: 폰 프로파일에서 엔진(`ibl_engine.execute_ibl`)은 폰서 못 도는 액션을 거부하지 않고 **맥에 단건 위임**(`_forward_to_mac` ↔ 맥→폰 `_forward_to_phone` 대칭). 이 chokepoint를 합성 code(`&`/`>>`/`??`)의 각 leaf가 거치므로 **혼합 code도 액션별로 쪼개져** 일부는 폰·일부는 맥서 실행되고 결과가 한 봉투로 결합된다(예: `[sense:weather] & [sense:world_bank]` → weather=폰·world_bank=맥). 맥 도달=`INDIEBIZ_MAC_URL`+`INDIEBIZ_MAC_PASSWORD`(원격 런처 세션), 미설정이면 graceful 에러. **맥→폰 도달(2026-06-17 라이브)**=`INDIEBIZ_PHONE_URL`+`INDIEBIZ_PHONE_TOKEN`: 폰 `phone_api` 미들웨어가 비localhost 요청에 `X-Phone-Token`을 검증(hmac.compare_digest, localhost=WebView 자기접속은 통과), 맥 `_forward_to_phone`가 그 토큰을 자동 동봉. 폰 백엔드는 **앱 UI 없이 상주**(`AgentForegroundService`가 `App.ensureBackend()` 기동·START_STICKY·부팅 재기동)하고 **토큰이 있을 때만 `0.0.0.0`(LAN) 바인드**(노출과 인증을 한 묶음 — 토큰 없으면 `127.0.0.1` 전용). 빌린 산출 파일은 `_pull_remote_artifacts`로 양방향 회수(맥←phone_only·폰←mac_only). 보안: 양방향 게이트(맥→폰=토큰/폰→맥=HTTPS 터널+런처 비번), 인터넷 비노출(폰=LAN 한정), caveat=맥→폰 LAN 평문 HTTP(가정 WPA2 저위험·공용 WiFi 금지). 폰=몸(센서·신원·렌더) 자급·머리(연산)는 맥 연합 — 클라이언트-서버 아니라 주권 피어들의 협력(미래 피어=같은 뼈대+허가 층).

계기 가시성은 실행 위치와 **직교**: app 블록은 폰서 기본 노출(실행은 라우팅이 로컬/맥 결정), `app.phone_render: false`만 숨긴다(폰서 못 보여주는 출력=맥 브라우저·네이티브창, 또는 미검증 보류=ytmusic 오디오).

빌드가 `runs_on` + 검증 패키지(`build_ibl_nodes.PHONE_VERIFIED_PACKAGES`)에서 `data/phone_manifest.json`을 파생한다 —
폰 임베드 빌드의 번들 패키지·앱 계기 필터·엔진 라우팅의 단일 진실 소스. PC에선 무영향(전 액션 실행).

---

## 노드 (Phase 25: 5-Node 재구조화)

### 핵심 노드 분류

총 **143 액션** (능력 자기완결화 Phase 2: `self:package` 생애주기 어휘 신설 → 142에서 143. 이전: sense:researcher + sense:paper nanet source 추가, 포식 기억 self:forage/residual 등 → 138에서 141. 이전: engines에 통화 변환자 9 신설(단항 filter/sort/take/select/dedup/groupby + 이항 join/union/merge) → 124에서 136).

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `self` | 45 | 개인 도메인: 시스템 관리, 파일, 트리거/스케줄, 목표/메모리/포식기억, 비즈니스(사업·아이템·문서·지침), 폰 동기화, 워크플로우, 패키지 생애주기 | read, write, file_find, storage, trigger, workflow, goal, memory, forage, residual, business, business_item, phone_sync, package |
| `limbs` | 17 | 장치 제어: UI 조작(브라우저, 데스크톱 화면, 안드로이드 폰) + 폰 네이티브 동작(phone) + 미디어 재생 | browser, screen, android, phone, music, radio, cctv, launch, os_open |
| `sense` | 44 | 감각 확장: 외부 정보 수집(연구자·학술 포함) + 내부 데이터 관리 + 폰 온디맨드 감각(알림·위치·마이크·카메라) | search_naver, stock, travel, crawl, realty, weather, researcher, paper, phone, here, listen, see |
| `others` | 11 | 협업·통신: 에이전트 위임 + 메시지/커뮤니티 + 이웃 CRM | delegate, channel_send, channel_read, messages, feed, board, nostr, auto_response, neighbor, contact, agents |
| `engines` | 13 | 창작: 슬라이드·영상·이미지(생성 image_gemini·평가 image_critic·읽기 image_read)·신문·웹·TTS. 통화 변환 문법(document/structure 포함)은 `table` 노드로 분리(2026-06-30). | slide_shadcn, newspaper, image_read, image_gemini, image_critic, html_video, tts, web |
| `table` | 13 | 표·통화 변환 문법(관계대수 9 + emitter 4). engines에서 분리(2026-06-30) — 무거운 engines를 꺼도(노드 on/off) 가벼운 문법은 생존. | filter, sort, take, select, dedup, groupby, join, union, merge, chart, spreadsheet, document, structure |

**Phase 25 통합 맥락:**
- source → sense(78): 외부 정보 인식의 "감각 기관" 역할
- system → self(75): 개인 영역 관리의 "자기 중심"
- interface + stream → limbs(96): 장치/미디어 조작의 "손발"
- team + messenger → others(13): 타인/협업의 "다른 개체"
- forge(46) → engines: 복잡한 프로세스를 기동시켜 결과물을 생성하는 "엔진"

**self 주요 액션:**

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `notify_user` | 사용자에게 알림 전송 | `[self:notify_user]{message: "작업이 완료되었습니다"}` |
| `output` | 결과를 목적지로 내보냄 (op: gui/file/clipboard) | `[self:output]{op: "file", path: "result.md", content: "..."}` |
| `goal` (op: list) | 등록된 목표 목록 조회 | `[self:goal]{op: "list", status: "active"}` |
| `goal` (op: status) | 목표 상태/진행도 조회 | `[self:goal]{op: "status", goal_id: "goal_001"}` |
| `goal` (op: kill) | 목표 취소/중단 | `[self:goal]{op: "kill", goal_id: "goal_001"}` |
| `goal` (op: log) | 시도 기록 (전략 에스컬레이션) | `[self:goal]{op: "log", task_id: "T1", approach_category: "api", description: "REST 호출", result: "failure"}` |
| `goal` (op: attempts) | 시도 이력 조회 | `[self:goal]{op: "attempts", task_id: "T1"}` |

**others 주요 액션:**

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `delegate` | 동료 에이전트에게 작업 위임 | `[others:delegate]{agent_id: "심장전문", message: "..."}` |
| `delegate` (비동기) | 에이전트에게 작업 위임 (비동기) | `[others:delegate]{agent_id: "투자컨설팅", message: "..."}` |
| `delegate_project` | 다른 프로젝트 에이전트에게 위임 | `[others:delegate]{scope: "cross", project_path: "투자/투자컨설팅", message: "..."}` |
| `channel_send` | 메시지 발송 (gmail/nostr) | `[others:channel_send]{channel_type: "gmail", to: "user@mail.com", subject: "제목", body: "내용"}` |
| `messages` | 메신저 — 대화 목록/스레드 (op 분기) | `[others:messages]{op: "inbox"}` · `[others:messages]{op: "thread", neighbor_id: 3}` |
| `feed` | 커뮤니티 피드 (IndieNet) 조회/게시 | `[others:feed]{op: "read"}` · `[others:feed]{op: "post", content: "..."}` |
| `board` | 커뮤니티 보드 관리 | `[others:board]{op: "list"}` |
| `nostr` | IndieNet/Nostr 계정 (신원·릴레이) | `[others:nostr]{op: "profile"}` · `[others:nostr]{op: "rename", name: "..."}` |
| `neighbor` | 이웃 CRM — 조회/관리 (op: list/detail/save/delete/favorite) | `[others:neighbor]{op: "list"}` · `[others:neighbor]{op: "detail", name: "김사장"}` · `[others:neighbor]{op: "save", name: "..."}` |
| `contact` | 이웃 연락처 CRUD | `[others:contact]{op: "add", neighbor_id: 3, contact_type: "gmail", contact_value: "a@b.c"}` |
| `auto_response` | 자동응답 토글 (PC 전용) | `[others:auto_response]{op: "status"}` · `[others:auto_response]{op: "start"}` |

### 수족 노드 — limbs (장치 제어 + 미디어 재생)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `limbs` | 17 | UI 조작 + 폰 네이티브 동작 + 미디어 재생: 브라우저 자동화, 데스크톱 화면, 안드로이드 폰, phone(진동/알림/TTS), 유튜브, 라디오, CCTV | browser, screen, android, phone, music, radio, cctv, launch |

구성: browser(op 26종 통합) + screen(데스크톱 화면) + android(폰 화면 조작) + music/radio(미디어) + cctv + launcher

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `browser_navigate` | 웹 페이지 탐색 | `[limbs:browser]{op: "navigate", url: "https://example.com"}` |
| `snapshot` | 브라우저 페이지 스냅샷 | `[limbs:browser]{op: "snapshot"}` |
| `click` | 요소 클릭 | `[limbs:browser]{op: "click", element: "검색 버튼"}` |
| `screen` | 데스크톱 화면 제어 (op: snapshot/click/type) | `[limbs:screen]{op: "snapshot"}` |
| `android` | 안드로이드 폰 화면 조작 (op: snapshot/tap/type/swipe/key/long_press/open_app) — snapshot으로 요소 읽고 ref/좌표로 탭. 집 PC=ADB+uiautomator(USB), 폰 자신=네이티브 AccessibilityService(USB 불필요, 한글은 ACTION_SET_TEXT라 IME 불필요). 핸들러가 INDIEBIZ_PROFILE로 분기 | `[limbs:android]{op: "snapshot"}` → `{op: "tap", query: "전송"}` |
| `play` | 유튜브/라디오 재생 | `[limbs:music]{op: "play", url: "유튜브 링크"}` |
| `radio_play` | 라디오 방송 재생 | `[limbs:radio]{op: "play", station: "KBS Classic FM"}` |
| `download` | 미디어 다운로드 | `[limbs:music]{op: "download", url: "유튜브 링크"}` |

### 감각 노드 — sense (외부 정보 수집 + 내부 데이터 조회)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `sense` | 43 | 외부 정보(웹 검색, API): 금융, 문화, 학술(연구자·논문), 법률, 통계, 부동산, 위치, CCTV, 뉴스 + 폰 온디맨드 감각(알림·위치·마이크·카메라) | search_naver, search_gnews, stock, company, crawl, realty, weather, world_bank, researcher, paper, phone, here, listen, see |

구성: 외부 정보 수집(웹 API, 크롤링) 중심. 사진/블로그/건강 등 로컬 DB 조회는 self 노드로 이동(`[self:photo]`/`[self:blog]`/`[self:health]`).

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `search_ddg` | 웹 검색 (DuckDuckGo, 영어/글로벌에 적합) | `[sense:search_ddg]{query: "AI 뉴스"}` |
| `search_naver` | 네이버 검색 (한국어 콘텐츠 압도적, 9개 도메인: webkr/news/blog/cafe/kin/book/encyc/doc/shop) | `[sense:search_naver]{query: "청주 맛집", type: "blog"}` |
| `search_gnews` | 뉴스 검색 (Google News RSS) | `[sense:search_gnews]{keyword: "부동산"}` |
| `stock` | 주가·시세 (op 분기) | `[sense:stock]{op: "quote", ticker: "삼성전자"}` |
| `crawl` | 웹 크롤링 | `[sense:crawl]{url: "https://..."}` |
| `company` | 기업 펀더멘털 (op 분기) | `[sense:company]{op: "profile", ticker: "삼성전자"}` |
| `travel` | 여행 정보 (op 분기, 도시명→IATA·상대날짜 내부해소) | `[sense:travel]{op: "flight", to: "도쿄"}` / `{op: "hotel", city: "파리"}` |
| `world_bank` | 세계은행 지표 (지표명·국가명 자연어 내부해소) | `[sense:world_bank]{indicator: "인구", country: "한국"}` |
| `researcher` | 연구자 검색 (op: find/coauthor) — 국회도서관 국가학술정보(LOSI). 동명이인을 소속·생년으로 분리, 공저자 추적. 인물 찾기 | `[sense:researcher]{op: "find", name: "홍길동"}` |
| `paper` | 학술·학위논문 검색/다운로드 (op: search/download, source 분기 openalex/arxiv/pubmed/semantic + `nanet`=국회도서관 학위논문·국내학술) | `[sense:paper]{op: "search", query: "베이지안", source: "nanet"}` |
| `phone` | 폰 컴패니언 피드 조회 (op: notifications/location/steps) — "지금 폰에 연락 오나"의 정답 소스. 컴패니언 앱이 NIP-17로 보낸 알림·위치·걸음 | `[sense:phone]{op: "notifications"}` |
| `search_photos` | 사진 검색 | `[self:photo]{op: "search", query: "가족"}` |
| `rag_search` | 블로그 RAG 검색 | `[self:memory]{op: "search", query: "AI"}` |
| `save_health` | 건강 기록 저장 | `[self:health]{op: "save", type: "blood_pressure", ...}` |
| `cctv` | CCTV/웹캠 조회 (op 분기, 좌표·playable 보장) | `[sense:cctv]{query: "광화문"}` / `[sense:cctv]{op: "nearby", lat: 37.57, lng: 126.98}` |
| `cctv` (self) | CCTV 캐시 행정 (op 분기) — stats(기본): 전체 소스 현황 / refresh: UTIC 캐시 갱신 | `[self:cctv]` / `[self:cctv]{op: "refresh"}` |

### 엔진 노드 — engines (콘텐츠 생성)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `engines` | 26 | 변환·창작: 통화 변환자·문서IR·차트·표·슬라이드·영상·이미지 | filter, sort, join, document, structure, chart, spreadsheet, slide_shadcn, newspaper, image_read |

특징: 복잡한 프로세스를 기동시켜 결과물을 산출하는 엔진 노드.

---

## 파이프라인

IBL 액션을 연산자로 연결하면 파이프라인이 된다.

| 연산자 | 이름 | 의미 |
|--------|------|------|
| `>>` | Sequential | 순차 실행, 이전 결과를 다음에 전달. 앞 단계가 실패하면 즉시 중단 (에러 전파 방지) |
| `&` | Parallel | 동시 실행, 결과를 합침 |
| `??` | Fallback | 실패 시 대체 실행 |
| `\| op:` | Pipe (통화 변환 단축) | `\| where:/sort:/take:/select:/dedup:` — 목록·표 결과를 거르고·정렬·추리는 단항 변환자 단축. 각각 `>> [table:filter/sort/take/select/dedup]{...}` 로 풀림 (ibl_parser desugar) |

**감각 피드백**: 파이프라인 실행 결과에는 모든 중간 단계의 결과가 누적되어 AI에게 전달된다. `_action_count` 필드로 파이프라인 내 총 액션 수가 반환되어, AI가 실행 규모를 파악할 수 있다.

```
# 순차: 검색 → 저장 (검색 실패 시 저장 단계는 실행되지 않음)
[sense:search_ddg]{query: "AI 뉴스"} >> [self:output]{op: "file", path: "news.md"}

# 병렬: 두 검색 동시 실행
[sense:search_ddg]{query: "AI"} & [sense:search_ddg]{query: "부동산"}

# Fallback: 첫째 실패 시 둘째 시도
[sense:stock]{op: "quote", ticker: "AAPL"} ?? [sense:stock]{op: "info", ticker: "AAPL"}

# 혼합
[sense:search_ddg]{query: "AI"} & [sense:search_ddg]{query: "부동산"} >> [self:output]{op: "file", path: "briefing.md"}
```

### 통화와 변환자 (Currency & Transformers)

조합성의 핵심은 **공유 통화(명사)**다. 통화는 단 하나 — **`items`** = `[{…열린 dict…}]`. (2026-06-27 단일 통화 이행 완료: 옛 records/table/document 전부 items로 흡수.)
- 가장 흔한 관습은 카드 `{title, meta, summary, url, image?}`(검색·매물·뉴스) — 단 `title`조차 보장 아닌 **열린 항목**.
- 같은 items가 통계/시세는 **수치 칸을 담은 행 dict**(첫 키=x축)로, 문서는 **문단 항목**(type·text)으로 흐른다 — *받는 쪽(소비자)이 필요한 view로 재구성*한다.
- 액션은 `returns:` 로 자기 역할을 선언한다: **items**(생성=통화 냄) · **transform**(변환=통화→통화) · **scalar**(단일값·통화 아님) · **effect**(행동·종착).

`engines`의 **변환자**(returns:transform)는 통화를 받아 *같은 통화*를 내므로(closure) `>>`로 임의 깊이 조합된다(도메인 무관):
- **단항**(앞 결과 1개): `filter{where}` · `sort{by, desc}` · `take{n}` · `select{columns}` · `dedup{by}` · `groupby{by, agg}` — 단항은 `|` 단축 문법 지원
- **이항**(`&` 두 입력): `join{on}` · `union` · `merge`

통화는 산출물 emitter로 흐른다: `document`(html/pdf/docx/pptx/typst) · `chart` · `spreadsheet`. 패턴: **[검색/조회] → [변환자 체인] → [산출물]**. 명제="언어는 명사에 산다" — 명사(통화)가 coverage를, 변환자가 depth를 곱한다. (data-ops 패키지, 2026-06-15)

```
[sense:realty]{region: "강남구"} | where: "전세" | sort: price | take: 5 >> [table:document]{}
[sense:stock]{op: "history", symbol: "005930"} & [sense:world_bank]{country: "KR"} >> [table:join]{on: "연도"} >> [table:chart]{}
```

---

## IBL 건강 유지·확인 시스템

IBL은 단순하다 — 액션 한 항목 = **세 얼굴(src 정의 ↔ tool.json 스키마 ↔ handler 구현)이 일치**하고, 자기 `returns:` 역할의 통화 계약을 지키는 것. 그래서 건강도 단순하게 — **어휘를 쓸 때 만들고, 커밋 때 강제하고, 하루 한 번 회귀 그물로 확인.** 폴링 sweep도, AI 턴도 없다(전부 AI 0). (2026-06-27 단순화)

### 건강의 두 종류

| 종류 | 무엇 | 언제 변하나 |
|------|------|------------|
| **구조 건강 (정적)** | 세 얼굴 정합 + `returns:` enum + fixture 완전성 | **어휘를 쓸 때만** (편집 안 하면 안 깨짐) |
| **행동 건강 (실행)** | 좋은 파라미터 하나로 실행 시 유효한 통화를 내는가 | 외부 의존(API·키·네트워크) — 실사용 시 드러남 |

### 검사는 두 군데에서만 돈다

1. **커밋 시 `scripts/build_ibl_nodes.py --check`** (pre-commit 훅, AI 0, 즉각) — 어휘가 변하는 유일한 순간을 막는다:
   - 삼각 정합: `src.tool` ↔ tool.json name, `src.ops` ↔ op.enum/default ↔ handler `_OP_DISPATCHERS`(AST)
   - `returns:` 필수·enum(`items|transform|scalar|effect`)·transform 정합
   - **fixture 완전성**: `returns: items|scalar` 액션은 `data/ibl_fixtures.json`에 fixture 또는 exempt(사유 명시) 필수 → **신규 액션이 검사망을 못 빠져나가고, 삭제 시 고아 fixture도 잡힌다.**

2. **하루 1회 `scripts/ibl_health_check.py`** (`run_daily_health_check`, AI 0, 수 초) — 그 정적·행동·흐름 검사를 회귀 그물로 한 번 더:
   - **§1A 정적**: `--check` 호출
   - **§1B 통화(fixture)**: `data/ibl_fixtures.json`의 "올바른 파라미터 예 하나"를 라이브 실행 → items 통화 유효성 단언 (GREEN/YELLOW/RED)
   - **§1C 골든 파이프**: 고정 파이프 몇 개를 돌려 `>>` 흐름 단언
   - RED면 알림 한 통(notification). GREEN이면 끝. self_checks 테이블에 기록 → x-ray 노출.

위 둘은 *구조·행동*을 본다(AI 0). 그러나 `description:` 산문은 자유 자연어라 동작이 바뀌어도(예: 통화 records/table→items) 설명이 조용히 stale해진다(좀비 어휘). 그 빈틈은 세 번째 검사가 메운다:

3. **주 1회 `backend/ibl_description_audit.py`** (`run_maintenance_bundle` 합류, 카덴스 게이트) — `--check`의 *의미* 판:
   - **결정적 교차참조**(AI 0): 설명이 가리키는 `[node:action]`이 실재하는지. 끊긴 참조(개명·삭제된 액션을 가리킴)를 LLM 없이 잡는다.
   - **의미 드리프트**(경량 LLM, role=background): 정본 어휘 앵커(`_VOCAB_ANCHOR` — 통화는 items 하나 등)에 비춰 각 설명이 ①옛 통화 어휘 ②returns/op와 모순 을 쓰는지 플래그. *교차참조 존재 검사는 LLM에 안 맡긴다*(결정적 검사가 더 정확). 경량 모델이라 오탐 꼬리가 있어 — 구조 `--check`가 커밋을 *막는다*면 이건 self_checks에 *깃발만 꽂고*, 판단·수정은 사람.

### fixture — 행동 건강의 단일 진실 소스

`data/ibl_fixtures.json`이 액션별 **"올바른 파라미터 예 하나"**를 담는다. "좋은 입력 하나로 제대로 돌면 정상"이라는 원리 — AI가 파라미터를 추론할 필요가 없다(사람이 한 번 큐레이션). `--check`가 완전성을 강제하므로 어휘 생성·삭제 시 fixture 한 줄이 *권고가 아니라 게이트*다.
- **effect**(부작용)는 정기 실행 불가 → fixture 면제, 구조검사만.
- **transform**은 골든 파이프(§1C)로 흐름 검증.

### 라이프사이클 (어휘를 만들·고치·지울 때)

가이드가 절차를 나르고, `--check`가 빠질 수 없는 부분을 강제한다:
- **생성**: `data/guides/new_action_checklist.md` — 0.5단계(역할·통화 계약) + 2.5단계(fixture 한 줄 추가).
- **삭제**: `data/guides/action_removal.md` — src·tool.json·handler·**fixture** 줄 + 해마·건강기록 정리.
- 절차서·처리 플레이북: `docs/IBL_MAINTENANCE_MANUAL.md`.

### 수동 점검

- 수동 모드 런처의 **🩺 건강 확인** 버튼 → `POST /world-pulse/ibl-health-check`(동기) → §1A/§1B/§1C 결과 표시.
- 또는 직접: `python scripts/ibl_health_check.py` (단독 실행, 외부 인프라 비의존 — 레지스트리 + `/ibl/execute`만).
- IBL 액션으로도: `[*:self_check]` = `run_daily_health_check`.

---

## 변수 바인딩 ($variable)

IBL 코드 내에서 액션의 실행 결과를 변수에 저장하고 이후 단계에서 참조할 수 있다.

**문법**: `$변수명 = [node:action]{params}`

```
# 검색 결과를 변수에 저장
$result = [sense:search_ddg]{query: "AI 뉴스"}

# 변수를 다음 액션에서 참조
[self:output]{op: "file", path: "news.md", content: $result}
```

- `$변수명 = 액션` 형태로 할당
- `$변수명`으로 이전 결과를 참조
- 파이프라인(`>>`) 없이도 중간 결과를 명시적으로 전달 가능
- 변수명은 영문/숫자/밑줄(`_`)로 구성

---

## $file:N 파라미터 (파일 참조)

코드 파일이나 긴 텍스트를 IBL 파라미터로 직접 넣으면 이스케이프 문제가 발생한다. `$file:N` 메커니즘은 이를 해결한다.

**원리**: `execute_ibl`의 `files` 파라미터로 코드/긴 텍스트를 별도 전달하고, IBL 코드 내에서 `$file:0`, `$file:1` 등의 플레이스홀더로 참조한다. IBL 파서가 `$file:N`을 만나면 `files[N]`의 실제 내용으로 치환한다.

```
# execute_ibl 호출 시
{
  "ibl_code": "[self:output]{op: \"file\", path: \"script.py\", content: $file:0}",
  "files": ["print('hello world')\nfor i in range(10):\n    print(i)"]
}
```

- `$file:0` → files 배열의 첫 번째 항목으로 치환
- `$file:1` → files 배열의 두 번째 항목으로 치환
- 이스케이프 문제 없이 코드, JSON, 마크다운 등 모든 텍스트를 안전하게 전달 가능

---

## 워크플로우

자주 쓰는 파이프라인을 YAML로 저장해두면 한 줄로 실행할 수 있다.

```yaml
# data/workflows/news_briefing.yaml
name: "뉴스 브리핑"
pipeline: '[sense:search_ddg]{query: "AI 뉴스"} & [sense:search_ddg]{query: "부동산 뉴스"}'
```

실행: `[self:run_pipeline]{name: "news_briefing"}`

steps 형식도 지원:

```yaml
name: "주가 확인"
steps:
  - node: sense
    action: price
    target: "삼성전자"
```

---

## 액션 스코프 (Phase 30)

액션마다 데이터 경계가 다르다. 모든 액션이 특정 프로젝트의 폴더에서 작동하는 건 아니고, 인스턴스 전체에 걸친 워크스페이스에서 작동하거나 indiebizOS 자체를 다루는 액션도 있다. `data/ibl_nodes_src/<node>.yaml`에 `scope`를 명시.

| scope | 의미 | base path | 용도 예시 |
|-------|------|-----------|----------|
| `project` (기본) | 특정 프로젝트의 데이터 | 활성 프로젝트 폴더 | `self:read`, `self:write` — 프로젝트 폴더 안 파일 |
| `workspace` | 인스턴스 전체에 걸친 데이터 | `get_base_path()` (indiebizOS 루트 / userData) | `self:lecture_list`, `self:lecture_open` — `outputs/lectures/` |
| `system` | indiebizOS 자체 작업 | `get_base_path()` | 설정·패키지 관리 등 (향후 권한 모델 분리 예정) |

**선언 위치** — `ibl_nodes_src/<node>.yaml`에 두 곳에 쓸 수 있음:
- **노드 레벨** (전체 액션 기본값): 해당 노드 dict 안에 `scope: workspace`
- **액션 레벨** (개별 오버라이드): 해당 액션 dict 안에 `scope:`

```yaml
self:
  scope: workspace        # 이 노드의 모든 액션 기본값
  actions:
    lecture_list: { router: handler, tool: lecture_list, ... }
    lecture_create: { router: handler, tool: lecture_create, ... }
    special_action:
      router: handler
      tool: special
      scope: project      # 이 액션만 오버라이드
```

**라우팅 동작** — `_route_handler`(`backend/ibl_routing.py`)가 scope를 보고:
- `project`: `_resolve_project_path` 4단 폴백 (인자 → thread_context → params.project_path → params.project_id). 모두 실패하면 에러.
- `workspace`/`system`: `get_base_path()`를 ToolContext에 주입. project_path/project_id 무시 — 의도적 격리.

**왜 필요한가** — 강의 만들기 워크스페이스 같은 패키지는 `outputs/lectures/` 같은 공유 폴더에 데이터를 두는데, 라우팅이 이를 모르고 모든 액션에 프로젝트 컨텍스트를 강요하면 AI가 "프로젝트 하나 골라서 컨텍스트 끌어오기" 같은 부자연스러운 우회를 한다. scope 선언으로 이 마찰을 제거.

---

## 앱 표면 노출 — `app:` 블록 (2026-06-11)

액션을 **앱 모드 계기(GUI)**로 노출하려면 src 액션 정의에 선택적 `app:` 블록을 단다. 액션이 자기 입력 폼·IBL 호출 템플릿·결과 표현을 스스로 선언하고, 표면(데스크탑 `GenericInstrument.tsx` / 원격 런처 웹앱)은 이를 해석만 한다 — **app: 블록 1개 = 모든 표면에 동시 등장, 표면별 코드 0줄.**

```yaml
      crypto:
        ...                       # 일반 액션 필드
        app:
          icon: 🪙
          name: 코인              # 계기 표시명 (단독 계기는 icon+name 필수)
          order: 6                # 홈 그리드 정렬
          auto_run: true          # 열자마자 기본값으로 실행
          inputs:                 # text/select(+options_action)/chips/required/default
          - { key: coin, type: text, default: BTC, chips: [BTC, ETH] }
          action: '[sense:crypto]{coin_id: "$coin"}'   # $key=입력 치환, 빈 입력 파라미터 자동 제거
          view:                   # 프리미티브 목록은 아래 어휘 줄 참조(빌드 가드가 동기 검증)
          # compose: 하단 작성바 — $text=작성, {field}=드릴 데이터. 전송 후 새로고침
          # item_click.tabs: 드릴 상세 탭(대화↔이웃정보 등) — 한 액션 데이터를 탭별 view 로 분할
          # form/editable_list: $field=입력값, {field}=드릴 데이터 → 저장/추가/삭제 액션 실행 후 새로고침
          - { type: metric, big: '{data.current_price_krw|num}', trend: data.change_24h_percent }
```

- view 프리미티브 14종: metric / kv / kv_list / card_list / image_grid / sparkline / list_action / thread / form / editable_list / map / calendar / group / blocks — card_list=+item_click 드릴·탭·compose, thread=채팅 버블+status, form=편집 필드+저장, editable_list=행 CRUD, map=leaflet 지도, calendar=월 그리드, group=파티션 콤비네이터(`by` 키 템플릿으로 items를 나눠 그룹마다 내부 `view:` 재귀 렌더 — table:groupby(집계)와 달리 멤버 유지, 뷰-계층의 groupby), blocks=**문서 IR 렌더**(heading/paragraph/list/table/quote/code/divider/image 블록 배열을 문서로 — `[self:read]{blocks:true}`·`[table:structure]` 출력 직결. 표현 언어 층위 조항의 "정적 표현 원자 공유": 페이로드 IR의 읽기 전용 부분집합이 표면 언어에도 그대로 옴).
- form 필드 9종: text / select / toggle / textarea / images / date / time / datetime / recurrence
- ★위 두 어휘 줄은 빌드의 **뷰-어휘 문서-동기 가드**가 코드 선언(`APP_VIEW_TYPES`/`APP_FORM_FIELD_TYPES`)과 자동 대조 — `new_action_checklist.md`의 같은 줄과 함께, 뷰 어휘 변경 시 두 문서를 같이 고쳐야 빌드 통과.
- 표시 템플릿 `{path|filter}` — 필터: round/num/abs/arrow/`opt:앞,뒤`/`trunc:N`. 드릴 응답엔 클릭 행이 `_item`으로 주입.
- 리스트 프리미티브의 `from: "."` = 응답 자체를 1행으로 (단일 객체 응답에 행 버튼 달기 — 예: 신문 생성 결과에 "띄우기").
- **select 입력 2종:** ①정적 `options: [{value,label}]` (IBL 호출 없음 — 시/도·유형 등 고정 목록) ②동적 `options_action`+`options_from` (IBL로 옵션 조회; 응답이 배열이면 option_value/option_label로, 딕셔너리 `{이름:코드}`면 자동 entries 정규화). **종속(cascade):** options_action 안에 `$형제키`를 쓰면 그 형제 select가 바뀔 때 자동 재조회 — 예: 구/군 `options_action: '[sense:realty]{op:"codes", city:"$province"}'` 가 시/도 선택에 따라 갱신. 실거래가 계기가 시연.
- **인터랙티브 지도 — `map` 프리미티브 + `on:` 뷰-이벤트(2026-06-29):** `type: map`은 봉투(`from: map_data`의 center/path/origin/destination)와 마커 리스트(`markers: items`)를 leaflet으로 그린다. `on:` 맵으로 *사용자 조작을 액션으로* 흘린다 — `moveend`(지도 팬/줌 → `$lat/$lng/$radius` 주입해 재조회, 위치 입력박스 대체) / `marker_click`(마커 클릭 → IBL 템플릿 재조회 `$id/$name/$lat/$lng/$url`, **또는** `{stream: true}` = 마커 url 을 HLS 영상 오버레이로 재생, CCTV). 상호작용도 선언이다 — 표면별 코드 0. **★YAML 함정:** `on:`은 따옴표 필수(`'on':`) — 무인용은 YAML 1.1 불리언으로 파싱돼 무시된다(체커가 RED 로 차단).
- **결과-필드 동적 필터 — `filter`:** ①정적 `filter: {items: [{label,value}], key}` = 칩 클릭 시 그 값으로 *재조회*. ②동적 `filter: {from_field: <필드>}` = 결과 items 의 그 필드 distinct 값으로 칩 자동 생성 + **클라이언트 측 거르기(재조회 없음, 같은 결과 내 필터)** — 지도 마커·목록 동시 거름. 상권(category)·검색 결과 분류 등. 둘은 상호배타(체커 강제).
- 탭 계기는 여러 액션이 같은 `instrument:` id + `mode:` 이름 공유 (예: performance+exhibit → 문화공연, search_youtube+music → 유튜브 뮤직). 노드가 달라도 병합된다.
- **리모컨 의미론(2026-06-11 사용자 결정):** 부작용이 집 PC에서 일어나는 계기(라디오·유튜브뮤직 재생, 신문 띄우기)도 원격 노출 OK — `note:`로 "집 PC에서 실행됩니다" 경고만 명확히. 폰-로컬 실행은 폰 네이티브 배포의 일이므로 섞지 말 것.
- `GET /launcher/instruments`가 app: 블록을 모아 계기 매니페스트로 자동 파생 (api_launcher_web._derive_instruments).
- 정합성은 `build_ibl_nodes.py --check`의 `validate_app_blocks`가 정적 차단 (참조 액션 실존·$key↔inputs·view 어휘·계기 그룹).
- app: 블록은 에이전트 프롬프트에 직렬화되지 않는다 (프롬프트 비용 0). 해마 용례·임베딩과도 무관 — 에이전트가 호출하는 어휘가 아니라 표면이 읽는 선언이다.
- 전체 어휘 명세: `docs/REMOTE_APP_GENERIC_RENDERER_PLAN.md`.

---

## 노드 타입

노드들은 노드 타입으로 그룹화되어 상위 레벨에서 접근할 수 있다.

| 노드 | 타입 | 하위 소스 | 사용법 |
|------|------|----------|--------|
| `ibl_info` | info | (레거시 — sense로 통합됨) | `ibl_info(source="finance", ...)` → `[sense:stock]{op: "search"}` |
| `ibl_store` | store | (레거시 — sense로 통합됨) | `ibl_store(store="health", ...)` → `[self:health]{op: "save"}` |
| `ibl_exec` | exec | python, node, shell | `ibl_exec(action="python", target="print(1+1)")` |

---

## 해석 순서

에이전트가 `[sense:search_ddg]{query: "AI"}`을 호출하면:

1. **액션 매칭**: `sense.actions.web_search`가 있는가? → 있으면 실행
2. **에러**: 없으면 사용 가능한 액션 목록 반환

---

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `data/ibl_nodes_src/` | **IBL 액션 단일 진실 소스** — 노드별 yaml (sense/self/limbs/others/engines + meta) |
| `data/ibl_nodes.yaml` | **빌드 산출물** — 직접 편집 금지. `scripts/build_ibl_nodes.py`로 생성 |
| `scripts/build_ibl_nodes.py` | 빌드 + 삼각 검증 (`--check`로 src↔tool.json↔handler.py `_OP_DISPATCHERS` AST 정확 비교 + **fixture 완전성** 강제) |
| `scripts/git-hooks/pre-commit` | 정합성 게이트 (commit 시점에 `--check` 자동 호출) |
| `scripts/ibl_health_check.py` | **건강 점검 단일 소스** — §1A 정적 + §1B fixture 통화 + §1C 골든 파이프 (AI 0) |
| `data/ibl_fixtures.json` | **행동 건강 fixture 단일 소스** — 액션별 올바른 파라미터 예 하나 (+ exempt) |
| `backend/world_pulse_health.py` | `run_daily_health_check`(하루 1회·RED면 알림) · `run_ibl_health_check`(스크립트 실행·파싱) |
| `data/api_registry.yaml` | API 도구 정의 (node 필드로 자동 병합) |
| `backend/ibl_engine.py` | IBL 실행 엔진, 동사 해석, 라우팅, 자동 발견 |
| `backend/api_engine.py` | API 레지스트리 실행 엔진, transform 후처리 |
| `backend/ibl_parser.py` | IBL 문법 파서 (`>>`, `&`, `??`) |
| `backend/ibl_access.py` | 에이전트별 노드 접근 제어, 환경 프롬프트(`_emit_action_xml` — op 자식 노출) |
| `backend/workflow_engine.py` | 파이프라인 실행, 워크플로우 관리 |
| `backend/trigger_engine.py` | 이벤트/트리거 기반 실행 엔진 |
| `data/workflows/` | 저장된 워크플로우 YAML |
| `backend/goal_evaluator.py` | Goal 조건 평가, 비용 산출 (Phase 26) |

---

## op 어휘 단일화 (2026-05-28)

단일 액션 + op 분기 패턴(예: `[limbs:browser]{op: "click", mode: "double", ref: "..."}`)에서 op 값들을 src yaml에 어휘로 선언:

```yaml
click:
  description: 브라우저 요소 클릭 (op 분기). single/double/right.
  target_key: op
  router: handler
  tool: browser_click_op
  ops:                          # 신규 (2026-05-28)
    default: single
    values:
      single: 좌클릭 (기본)
      double: 더블클릭 — 표 셀 편집·파일 열기
      right: 우클릭 — 컨텍스트 메뉴
```

**규약**:
- `target_key: op` 인 모든 액션에 `ops` 블록 의무 (라우터 무관 — handler/system/workflow_engine/trigger_engine 모두).
- `ops.values` 키들은 시스템 프롬프트에 `<op>` 자식 요소로 노출되어 실행 에이전트가 정확한 op를 선택.
- 24개 op 액션(limbs 13 + self 11) 마이그레이션 완료.

**삼각 검증** (`build_ibl_nodes.py --check`):
1. **등록**: src.tool ↔ tool.json.name (어제 dispatcher audit의 16건 누락 패턴 재발 방지)
2. **op enum**: src.ops.values 키 ↔ tool.json input_schema.properties.op.enum (exact set)
3. **default**: src.ops.default ↔ tool.json input_schema.properties.op.default
4. **handler**: src.ops.values 키 ↔ handler.py 모듈 레벨 `_OP_DISPATCHERS[tool_name]` dict 키 (AST 파싱, exact set)

**dispatcher 표준** (handler.py 측 규약):
```python
_OP_DISPATCHERS = {
    tool_name: {op: handler_or_None, ...},
    ...
}
_OP_DEFAULTS = {tool_name: default_op, ...}  # 기본값 있을 때만
```
op-bearing 10 패키지(browser-action / youtube / computer-use / radio / cctv / photo-manager / memory / health-record / lecture_workspace / android) 모두 이 패턴 채택.

**이중 게이트**:
- `pre-commit` 훅: commit 시점, 정적 검증
- `world_pulse_health.run_static_ibl_check()`: 12시간 self-check 사이클 합류, `self_checks` 테이블에 `__static__:ibl_consistency` 식별자로 기록

---

## 목적/시간/조건 (Phase 26: Goal/Time/Condition)

### Goal Block — 목적 선언

에이전트에게 "왜"를 알려주는 상위 레이어. 목적이 있으면 에이전트가 스스로 달성 여부를 판단하고 반복한다.

```
[goal: "에어컨 최적 구매"]{
  success_condition: "가격/성능/배송 비교 완료",
  resources: ["shopping-assistant", "web"],
  max_rounds: 20,
  max_cost: 1000,
  by: "오늘 저녁",
  report_to: "사용자"
}
```

**필수 안전장치**: 모든 Goal에 `max_rounds` 또는 `max_cost` 중 하나 이상 필수.

**시간 표현**:

| 표현 | 의미 | 예시 |
|------|------|------|
| `deadline` | 최종 기한 | `deadline: "2026-12-31"` |
| `until` | 조건 달성까지 | `until: "매수결정"` |
| `within` | 기한 내 완료 | `within: "2h"` |
| `by` | 특정 시점까지 보고 | `by: "오늘 저녁"` |
| `every` | 반복 실행 주기 | `every: "매일 08:00"` |
| `schedule` | 일회성 예약 실행 | `schedule: "2026-04-01 09:00"` |

**Goal 상태**: `pending` → `active` → `achieved` / `expired` / `limit_reached` / `cancelled`

**종료 우선순위**: `until` 충족 > `deadline` 도달 > `max_rounds`/`max_cost` 도달

### 조건문 (if/else if/else) — 상황에 따른 분기

```
[if: sense:kospi < 2400]{
  [goal: "방어적 포트폴리오 재편"]{deadline: "즉시", max_rounds: 10}
} [else]{
  [goal: "성장주 모니터링 유지"]{every: "매일 09:00", max_rounds: 30}
}
```

`else if`로 다중 조건 분기도 가능하다:

```
[if: sense:kospi < 2400]{
  [goal: "방어적 포트폴리오 재편"]{deadline: "즉시", max_rounds: 10}
} [else if: sense:kospi < 2600]{
  [goal: "중립 포지션 유지"]{every: "매일 09:00", max_rounds: 20}
} [else]{
  [goal: "공격적 매수 검토"]{max_rounds: 15}
}
```

### 케이스문 (case) — 다중 분기

```
[case: sense:market_status]{
  "상승장": [goal: "공격적 매수"]{max_rounds: 20},
  "하락장": [goal: "손절 점검"]{max_rounds: 10},
  "> 20%": [goal: "즉시 구매"]{max_rounds: 5},
  "10~20%": [goal: "추가 비교"]{max_rounds: 15},
  default: [goal: "관망"]{max_rounds: 5}
}
```

범위 표현식: `> N`, `>= N`, `< N`, `<= N`, `== N`, `N~M` 지원.

### Goal 프로세스 관리

```
[self:goal]{op: "list", status: "active"}       # 진행 중인 목표 조회
[self:goal]{op: "status", goal_id: "goal_001"}   # 특정 목표 상태 조회
[self:goal]{op: "kill", goal_id: "goal_001"}     # 목표 중단
```

### 통합 예시

```
[goal: "청주 투자 적기 판단"]{
  every: "매일 08:00",
  deadline: "2026-09-30",
  until: "매수 결정",
  max_rounds: 200,
  max_cost: 50000,
  strategy: [case: sense:interest_rate]{
    "하락": [sense:realty]{op: "query", region: "청주", depth: "deep"},
    "상승": [goal: "관망"]{max_rounds: 1},
    default: [sense:realty]{op: "query", region: "청주", depth: "shallow"}
  }
}
```
### 전략 에스컬레이션 & 라운드 메모리 (Phase 26b)

에이전트가 동일 유형의 시도를 반복하는 문제를 방지하는 메커니즘.

**전략 전환 규칙** (`<strategy_rules>`로 시스템 프롬프트에 주입):
1. 매 시도 후 `[self:goal]{op: "log"}`로 접근 범주, 결과, 교훈을 기록
2. 동일 `approach_category`가 3회 연속 실패 시 범주 포기, 다른 접근으로 전환
3. 모든 범주 소진 시 사용자에게 보고
4. 새 시도 전 `[self:goal]{op: "attempts"}`로 이전 이력 확인

**라운드 메모리** (`attempt_log` 테이블):
- `task_id`: 같은 작업의 시도를 묶는 키
- `approach_category`: 접근 범주 (예: "cv2_import", "pillow_fallback")
- `result`: "success" / "failure"
- `lesson`: 교훈
- 시스템 프롬프트의 `<attempt_history>` 섹션으로 동적 주입, 포기된 범주는 `<exhausted_categories>`로 명시

**구현 파일**: `conversation_db.py` (attempt_log 테이블), `ibl_nodes.yaml` (log_attempt, get_attempts), `ibl_engine.py` (핸들러), `ibl_access.py` (규칙/이력 주입)

---

| `backend/ibl_usage_db.py` | IBL 용례 사전 DB + 하이브리드 검색 |
| `backend/ibl_usage_rag.py` | 용례 RAG 참조 모듈 |
| `data/ibl_usage.db` | 용례 사전 + 실행 로그 DB |

---

## 용례 RAG 참조 시스템

에이전트가 IBL 코드를 생성할 때, 유사한 과거 성공 사례를 자동으로 참조한다.

사용자 메시지가 들어오면 용례 사전에서 하이브리드 검색(시맨틱 70% + BM25 30%)으로 유사 용례를 찾아 XML 형태로 프롬프트에 주입한다. AI는 이 참조를 기계적으로 복사하지 않고, 현재 상황에 맞게 변형한다.

```xml
<ibl_references note="아래는 유사한 과거 용례입니다. code의 IBL 코드를 참고하되, 반드시 execute_ibl 도구의 code 파라미터로 실행하세요. 절대 텍스트 응답에 IBL 코드를 포함하지 마세요. 분석/판단/정리가 필요한 작업은 파이프라인(>>)으로 엮지 말고 액션을 하나씩 호출하면서 중간에 생각하세요.">
  <ref intent="아파트 매매 실거래가" code='[sense:realty]{op: "query", region_code: "지역코드"}' score="0.88"/>
</ibl_references>
```

성공한 도구 실행 로그는 자동으로 용례 사전에 승격되어, 시스템이 사용할수록 참조 품질이 향상된다.

→ 상세 문서: [ibl_rag.md](ibl_rag.md)

---

## 액션 라우팅 이원화 (Phase 18)

IBL 액션은 라우터 타입에 따라 여러 경로로 실행된다. 현재 9종의 라우터가 존재한다:

| 라우터 | 설명 |
|--------|------|
| `handler` | 패키지의 handler.py로 라우팅 (복잡한 후처리) |
| `api_engine` | api_registry.yaml 기반 API 호출 + transform 후처리 |
| `system` | 시스템 내장 액션 (ask_user, approve 등) |
| `trigger_engine` | 이벤트/트리거 기반 실행 |
| `workflow_engine` | 워크플로우/파이프라인 실행 |
| `channel_engine` | 채널 추상화 (메시지 송수신) |
| `web_collector` | 웹 콘텐츠 수집/집계 |
| `driver` | 드라이버 기반 프로토콜 직접 접근 |
| `stub` | 미구현 예약 액션 (Phase 표시) |

주요 두 가지 경로:

### 1. api_engine 라우팅 (자동 발견)
`api_registry.yaml`에 `node` 필드가 있는 도구는 로드 시 자동으로 해당 노드의 액션으로 병합된다. `ibl_nodes.yaml`에 별도 등록이 필요 없다.

```yaml
# api_registry.yaml — node 필드만 추가하면 끝
kosis_search_statistics:
  service: kosis
  endpoint: /statisticsList.do
  transform: kosis_list
  node: sense                  # ← Phase 25: statistics → sense
  action_name: search_statistics
  description: "통계표 목록 검색"
  target_key: keyword
```

이 방식은 API 호출 + transform 후처리로 완결되는 도구에 적합하다. 현재 api_engine 라우팅 액션들이 이 방식을 사용한다.

### 2. handler 라우팅 (수동 등록)
복잡한 후처리(캐싱, 코드 매핑, 다단계 API 호출 등)가 필요한 도구는 `ibl_nodes.yaml`에 수동 등록하고 `handler.py`가 처리한다.

```yaml
# ibl_nodes.yaml — handler 패키지의 handler.py로 라우팅
performance:
  router: handler
  tool: kopis_quick_search
  target_key: keyword
```

### 자동 병합 메커니즘
`ibl_engine.py`의 `_merge_api_registry_actions()`가 `_load_nodes()` 시점에 호출되어, `api_registry.yaml`의 node 바인딩된 도구를 `ibl_nodes.yaml`의 actions dict에 in-place로 병합한다. YAML 앵커(`&id005` 등)가 가리키는 동일 dict 객체를 직접 변경하므로 nodes 섹션에도 자동 반영된다.

---

## 시스템 AI IBL 통합 (Phase 17→25)

Phase 17에서 시스템 AI도 프로젝트 에이전트와 동일한 `execute_ibl` 단일 도구 구조로 통합되었습니다.
Phase 19-22에서 점진적으로 노드를 통합했으며, Phase 25에서 최종 5개 노드 구조로 재구조화되었습니다: self(75), limbs(96), sense(78), others(13), engines(46). 총 308개 액션.

**차이점은 접근 범위뿐:**
- 프로젝트 에이전트: `allowed_nodes`에 지정된 노드만 접근 가능
- 시스템 AI: 모든 노드 접근 가능 + 프로젝트 간 위임(`[others:delegate]{scope: "cross"}`)

**항상 허용되는 인프라 노드 (노드 yaml `always_on: true` 플래그, 단일 소스):**
`self`, `others`, `table` — 모든 에이전트에 자동 제공. self는 개인 도메인 관리, others는 협업/통신 전담, table은 통화 변환 문법 계층(파이프 생존 보장).

**시스템 AI 전용 others 액션:**
| 액션 | 설명 |
|------|------|
| `list_projects` | 모든 프로젝트/에이전트 목록 조회 |
| `delegate_project` | 다른 프로젝트의 에이전트에게 작업 위임 |

**시스템 AI 전용 self 액션:**
| 액션 | 설명 |
|------|------|
| `manage_events` | 이벤트/스케줄 통합 관리 |
| `list_switches` | 등록된 스위치 목록 조회 |

---

### IBL 진화 요약

IBL은 Phase 0(원시 도구 호출)에서 시작하여, 드라이버 기반 프로토콜 추상화(Phase 5-10), 노드 통합(Phase 17-25), verb 시스템 도입과 폐지(Phase 22-24), Goal/Time/Condition(Phase 26)을 거쳐 5-Node 체계로 발전했고, 이후 op 어휘화·사용성 재감사·어휘 정리·메신저/비즈니스 IBL화·neighbor 통합·폰 온디맨드 감각 삼각·통화 대수(engines 변환자)·포식 기억(self:forage/residual)·국가학술정보(sense:researcher/paper)·능력 자기완결화(self:package)로 현재 143 액션이 됐다. 핵심 설계 철학은 "AI가 작성하는 언어"이며, 문법 복잡도보다 표현력을 우선한다.

*Phase 20: filesystem→orchestrator, webdev+design→creator, photo+blog+memory+health→librarian 통합.*
*Phase 21: finance+culture+study+legal+statistics+commerce+location+web(search/crawl/news)→informant 통합.*
*Phase 22: youtube+radio→stream, browser+android+desktop→interface, informant+librarian→source, orchestrator→system, creator→forge. 6개 노드, 321 액션.*
*Phase 23: system에서 위임 관련 7개 액션을 team 노드로 분리. 7개 노드(system, team, interface, source, forge, stream, messenger).*
*Phase 24: verb 시스템 제거. 런타임 verb→action 해석 삭제. 프롬프트 가독성을 위해 category 태그로 대체 (순수 표시용).*
*Phase 25: 5-Node 최종 구조 재설계. source→sense(외부 정보), system→self(개인 도메인), interface+stream→limbs(신체/장치), team+messenger→others(협업/통신), forge→engines(엔진/창작). 총 308 액션.*
*Phase 26: self 노드에 log_attempt, get_attempts (전략 에스컬레이션/라운드 메모리). sense 노드에 cctv_refresh, cctv_stats (UTIC 실시간 API).*
*최종 업데이트: 2026-07-01 — **능력 자기완결화 Phase 0~3(어휘를 패키지에 co-locate) + Phase 2(`self:package` 생애주기 어휘)**: 어휘(액션 정의)를 중앙 `data/ibl_nodes_src/`에서 각 패키지 폴더의 `ibl_actions.yaml`로 옮겨 패키지=자기완결 능력으로 만듦(설치/철거가 코드+어휘를 원자적으로 넣고 뺌). `scripts/build_ibl_nodes.py` 병합기(설치된 패키지 fragment 흡수) + `scripts/migrate_package_vocab.py` 마이그레이션 하네스(추출→기록→제거→리빌드→의미동일 단언, 실패 시 자동 롤백) 신설. radio 파일럿 + 나머지 33개 패키지(118액션) 전량 이관 — 중앙 src는 이제 backend-native 25액션만(sense2·self14·limbs2·others7). 신규 `[self:package]{op: list|info|install|remove}` 어휘로 시스템이 *자기 언어로* 능력을 설치/철거(라이브 IBL 호출만으로 왕복 검증, `/packages/reload` 사람 개입 불필요 — `backend/ibl_routing.py`의 `_package_op`/`_rebuild_ibl_vocab`). 142→**143 액션**(self 44→45). 부수 발견·수정: `merge_fragments`의 None-병합 크래시(노드 액션 전량 이관 시), `.gitignore`의 `CCTV*` 패턴이 cctv 패키지 폴더를 통째로 가리던 버그. 다음=Phase 4(needs_key/weight/locale 메타 + 부재-패키지 관용). 상세=`docs/CAPABILITY_SELF_CONTAINMENT_HANDOFF.md`. 이전(2026-06-30) — **카탈로그 어휘 정리 + 설명 의미 드리프트 점검 신설**: ①단일통화 이행이 코드는 끝났는데 *프롬프트-대면 설명*은 stale했음(프리앰블 `12_ibl_only.md`·engines 변환자 desc가 옛 "records/table 두 통화"를 가르침) → 정본 어휘(통화는 `items` 하나)로 단일 소스화(프리앰블 한 곳 정의, 변환자 desc는 보일러플레이트 제거). ②카탈로그 프리앰블의 "대표 op 액션" 목록(본문 중복) 제거. ③장황·부정확 desc 정리(slide의 "유일한 액션"=slide_shadcn도 슬라이드를 만드므로 부정확, photo의 records→items). ④끊긴 교차참조 1건(`self:local_save`→없는 `sense:save`) 수정. ⑤**`backend/ibl_description_audit.py` 신설** — `--check`가 *구조*만 보고 *산문*은 안 보던 빈틈(좀비 어휘)을 메움: 결정적 교차참조(AI 0) + 경량 LLM 의미 드리프트(통화·모순), 주 1회 `run_maintenance_bundle` 합류, self_checks에 깃발만(판단은 사람). 142 액션 불변, 카탈로그 -742자. 이전(2026-06-29) — **앱 인터랙티브 렌더 프리미티브 종결 + 단일통화 마무리**: 액션 수 불변(142, 렌더링 레이어 변경). app: 블록 view 어휘에 인터랙티브 `map`(leaflet, 데스크탑·원격 동치) + `on:` 뷰-이벤트(`moveend`→재조회·`marker_click`→IBL 액션 또는 `{stream: true}`→HLS 영상) + 결과-필드 동적 필터 `filter: {from_field}`(클라이언트 측 거르기, 재조회 없음) 추가. bespoke `CommercialInstrument` 은퇴(선언형으로 흡수). 빈도 없는 directions 은퇴=보류·lightbox=불요(image_grid 가 이미 풀스크린). 버그수정: 동적필터 활성 시 원격 카드 드릴이 원본 인덱스로 가던 것(`applyCatFilter` 후 인덱싱). 단일통화(items) records producer=0 종합확인(backend·tools 전수), data-ops 변환자 vestigial `records:[]` 출력 제거. 이전(2026-06-27) — **건강 유지·확인 시스템 단순화**(위 "IBL 건강 유지·확인 시스템" 절): 폴링 sweep·매일 AI 턴·AI 테스트계획 은퇴 → 건강 = 가이드(절차) + `--check`(커밋 게이트, **fixture 완전성 강제**) + `ibl_health_check.py`(하루 1회·AI 0). `data/ibl_fixtures.json`=행동 건강 fixture 단일 소스(items/scalar 76 전수=fixture 68+exempt 8). 단일 통화 = `items` 하나(records/table/document 흡수). 수동 모드에 🩺 건강 확인 버튼. 이전(2026-06-22) — **142 액션**(sense 44·self 44·limbs 17·others 11·engines 26). 국회도서관 국가학술정보(LOSI) API로 `sense:researcher`(op find/coauthor — 연구자 검색, 동명이인을 소속·생년으로 분리·공저자 추적)·`sense:paper`에 `source: nanet` 추가(학위논문·국내학술) — 인물·학위논문 찾기 목적, study 패키지. 기억 6종→**7종**: 포식 기억(forager, `[self:forage]{recall/note/forget}`, 맥 전용) + `[self:residual]{sample/estimate}`(음성-단언 측정). 이전(2026-06-17) — **engines:image_read 신설**(Gemini Vision 시각 읽기/OCR/검증 — 스크린샷 숫자·이미지 텍스트를 자유서술로 읽음, image_critic의 합격/점수 채점과 분리) + image_critic의 image_path가 path 표준 param 폴백 수용. 액션 137→**138**(engines 26). 동기=image_critic을 OCR로 오용하던 패턴 해소(빠진 비전-읽기 어휘 보강). 이전 동일자 — **맥→폰 분산 IBL 인증 라이브**(`INDIEBIZ_PHONE_TOKEN`·`X-Phone-Token` 게이트·토큰 있을 때만 `0.0.0.0` 바인드·폰 백엔드 앱 UI 없이 상주 `AgentForegroundService`). `table:join`이 레코드 통화도 inner join(table 외, merge/union과 대칭). 자가점검 평가기=폰/맥 일시 미가용을 fail 아닌 skip 분류. 버그수정: `run_pipeline` 문자열 steps 파싱(만성 'str' object has no attribute 'get' 해소)·`self:grep` 단일파일 경로/`~` 확장(file 액션 전반)·KOSIS 통합검색 엔드포인트(`/statisticsSearch.do`)·Claude Code 프로바이더 execute_ibl 정규화. 이전(2026-06-15) — **136 액션**(sense 42, self 41, limbs 17, others 11, engines 25). 통화 대수: engines에 통화→통화 변환자 9 신설(단항 filter/sort/take/select/dedup/groupby + 이항 join/union/merge, data-ops) + 파이프 문법 단축 `|` + 문서 IR emitter(document/structure, html/pdf/docx/pptx/typst) — 124→136. 이전(2026-06-14): 124 액션 정합화(engines 14). 폰 온디맨드 감각 삼각(sense:here/listen/see, phone_only) + self:show_calendar 폐지(해마 게이트는 capability로) → 125→124. 폰이 두 번째 독립 자아로(폰-로컬 Gemini 두뇌·detect_body 하드웨어 자기감지·상주 스케줄러 self:trigger/schedule 폰 바인딩) + runs_on 정직성(anywhere/mac_only/phone_only, build_ibl_nodes.validate_phone_reachability self-check 합류) + channel 트리거 맥 발화 경로. 이전(2026-06-12): 122 액션 — 메신저/커뮤니티/비즈니스 IBL 앱모드 계기화(others:messages/feed/board/nostr, self:business/business_item/business_document/work_guideline) + 자동응답 IBL화(others:auto_response) + 폰↔PC business.db 합집합 동기화(self:phone_sync) + neighbor 통합. 이전(2026-06-10): 111 액션(안드로이드 얇은 부활 + 폰 컴패니언, 음악 작곡 은퇴).*
