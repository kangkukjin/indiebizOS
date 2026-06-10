---
title: IBL (IndieBiz Logic)
scope: IBL 명세, 5-Node 구조, 109 액션, 파서/엔진/라우팅
owner_code: ibl_engine.py, ibl_parser.py, ibl_access.py, ibl_routing.py
source_of_truth: data/ibl_nodes_src/{meta,sense,self,limbs,others,engines}.yaml
build_tool: scripts/build_ibl_nodes.py
last_updated: 2026-06-04
see_also: [execution_memory.md, packages.md, technical.md]
---

# IBL (IndieBiz Logic)

> indiebizOS의 정보 흐름 추상화 언어

## IBL이 하는 일

IBL은 에이전트가 정보를 가져오고, 가공하고, 전달하는 과정을 하나의 패턴으로 표현한다.

```
[node:action]{params}
```

- **node**: 어디서 (sense, self, limbs, others, engines)
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

## 액션 카테고리

총 111개 액션(sense 38, self 37, limbs 16, others 6, engines 14)은 프롬프트 가독성을 위해 카테고리로 그룹화된다. 카테고리는 순수 표시 목적이며, 런타임 동작에 영향을 주지 않는다. 에이전트는 항상 구체적 액션명을 직접 사용해야 한다.

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

---

## 노드 (Phase 25: 5-Node 재구조화)

### 핵심 노드 분류

총 **111 액션** (op 어휘 단일화 + 사용성 재감사 + 어휘 정리 + 안드로이드 얇은 부활 + 폰 컴패니언 후).

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `self` | 37 | 개인 도메인: 시스템 관리, 파일, 트리거/스케줄, 목표/메모리, 사용자 소통, 워크플로우 | read, write, file_find, storage, folder_note, fs_query, trigger, workflow, goal, memory |
| `limbs` | 16 | 장치 제어: UI 조작(브라우저, 데스크톱 화면, 안드로이드 폰) + 미디어 재생 | browser, screen, android, music, radio, cctv, launch, os_open |
| `sense` | 38 | 감각 확장: 외부 정보 수집 + 내부 데이터 관리 + 폰 컴패니언 피드 | search_naver, search_news, stock, company, travel, world_bank, crawl, realty, weather, phone |
| `others` | 6 | 협업 통신: 에이전트 위임 + 메시지 송수신 | delegate, channel_send, channel_read, neighbors, messages, agents |
| `engines` | 14 | 창작: 콘텐츠 생성 (슬라이드, 영상, 차트, 이미지, 웹사이트, 설계) | slide, slide_shadcn, html_video, chart, image_gemini, web, newspaper, tts |

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
| `search_contact` | 연락처 검색 | `[others:neighbors]{name: "김사장"}` |

### 수족 노드 — limbs (장치 제어 + 미디어 재생)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `limbs` | 16 | UI 조작 + 미디어 재생: 브라우저 자동화, 데스크톱 화면, 안드로이드 폰, 유튜브, 라디오, CCTV | browser, screen, android, music, radio, cctv, launch |

구성: browser(op 26종 통합) + screen(데스크톱 화면) + android(폰 화면 조작) + music/radio(미디어) + cctv + launcher

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `browser_navigate` | 웹 페이지 탐색 | `[limbs:browser]{op: "navigate", url: "https://example.com"}` |
| `snapshot` | 브라우저 페이지 스냅샷 | `[limbs:browser]{op: "snapshot"}` |
| `click` | 요소 클릭 | `[limbs:browser]{op: "click", element: "검색 버튼"}` |
| `screen` | 데스크톱 화면 제어 (op: snapshot/click/type) | `[limbs:screen]{op: "snapshot"}` |
| `android` | 안드로이드 폰 화면 조작 (op: snapshot/tap/type/swipe/key/long_press/open_app) — snapshot으로 요소 읽고 ref/좌표로 탭. ADB+uiautomator 기반, 한글 입력은 cliphelper IME | `[limbs:android]{op: "snapshot"}` → `{op: "tap", ref: "전송"}` |
| `play` | 유튜브/라디오 재생 | `[limbs:music]{op: "play", url: "유튜브 링크"}` |
| `radio_play` | 라디오 방송 재생 | `[limbs:radio]{op: "play", station: "KBS Classic FM"}` |
| `download` | 미디어 다운로드 | `[limbs:music]{op: "download", url: "유튜브 링크"}` |

### 감각 노드 — sense (외부 정보 수집 + 내부 데이터 조회)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `sense` | 38 | 외부 정보(웹 검색, API): 금융, 문화, 학술, 법률, 통계, 부동산, 위치, CCTV, 뉴스 + 폰 컴패니언 피드 | search_naver, search_news, stock, company, crawl, realty, weather, world_bank, phone |

구성: 외부 정보 수집(웹 API, 크롤링) 중심. 사진/블로그/건강 등 로컬 DB 조회는 self 노드로 이동(`[self:photo]`/`[self:blog]`/`[self:health]`).

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `search_ddg` | 웹 검색 (DuckDuckGo, 영어/글로벌에 적합) | `[sense:search_ddg]{query: "AI 뉴스"}` |
| `search_naver` | 네이버 검색 (한국어 콘텐츠 압도적, 9개 도메인: webkr/news/blog/cafe/kin/book/encyc/doc/shop) | `[sense:search_naver]{query: "청주 맛집", type: "blog"}` |
| `search_news` | 뉴스 검색 (Google News RSS) | `[sense:search_news]{keyword: "부동산"}` |
| `stock` | 주가·시세 (op 분기) | `[sense:stock]{op: "quote", ticker: "삼성전자"}` |
| `crawl` | 웹 크롤링 | `[sense:crawl]{url: "https://..."}` |
| `company` | 기업 펀더멘털 (op 분기) | `[sense:company]{op: "profile", ticker: "삼성전자"}` |
| `travel` | 여행 정보 (op 분기, 도시명→IATA·상대날짜 내부해소) | `[sense:travel]{op: "flight", to: "도쿄"}` / `{op: "hotel", city: "파리"}` |
| `world_bank` | 세계은행 지표 (지표명·국가명 자연어 내부해소) | `[sense:world_bank]{indicator: "인구", country: "한국"}` |
| `phone` | 폰 컴패니언 피드 조회 (op: notifications/location/steps) — "지금 폰에 연락 오나"의 정답 소스. 컴패니언 앱이 NIP-17로 보낸 알림·위치·걸음 | `[sense:phone]{op: "notifications"}` |
| `search_photos` | 사진 검색 | `[self:photo]{op: "search", query: "가족"}` |
| `rag_search` | 블로그 RAG 검색 | `[self:memory]{op: "search", query: "AI"}` |
| `save_health` | 건강 기록 저장 | `[self:health]{op: "save", type: "blood_pressure", ...}` |
| `cctv` | CCTV/웹캠 조회 (op 분기, 좌표·playable 보장) | `[sense:cctv]{query: "광화문"}` / `[sense:cctv]{op: "nearby", lat: 37.57, lng: 126.98}` |
| `cctv` (self) | CCTV 캐시 행정 (op 분기) — stats(기본): 전체 소스 현황 / refresh: UTIC 캐시 갱신 | `[self:cctv]` / `[self:cctv]{op: "refresh"}` |

### 엔진 노드 — engines (콘텐츠 생성)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `engines` | 14 | 콘텐츠 창작: 슬라이드, 영상, 차트, 이미지, 웹사이트 | slide, slide_shadcn, html_video, chart, image_gemini, web, newspaper, tts |

특징: 복잡한 프로세스를 기동시켜 결과물을 산출하는 엔진 노드.

---

## 파이프라인

IBL 액션을 연산자로 연결하면 파이프라인이 된다.

| 연산자 | 이름 | 의미 |
|--------|------|------|
| `>>` | Sequential | 순차 실행, 이전 결과를 다음에 전달. 앞 단계가 실패하면 즉시 중단 (에러 전파 방지) |
| `&` | Parallel | 동시 실행, 결과를 합침 |
| `??` | Fallback | 실패 시 대체 실행 |

**감각 피드백**: 파이프라인 실행 결과에는 모든 중간 단계의 결과가 누적되어 AI에게 전달된다. `_action_count` 필드로 파이프라인 내 총 액션 수가 반환되어, AI가 실행 규모를 파악할 수 있다.

```
# 순차: 검색 → 저장 (검색 실패 시 저장 단계는 실행되지 않음)
[sense:search_ddg]{query: "AI 뉴스"} >> [self:output]{op: "file", path: "news.md"}

# 병렬: 두 검색 동시 실행
[sense:search_ddg]{query: "AI"} & [sense:search_ddg]{query: "부동산"}

# Fallback: 첫째 실패 시 둘째 시도
[sense:stock]{op: "quote", ticker: "AAPL"} ?? [sense:stock]{op: "price", ticker: "AAPL"}

# 혼합
[sense:search_ddg]{query: "AI"} & [sense:search_ddg]{query: "부동산"} >> [self:output]{op: "file", path: "briefing.md"}
```

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
| `scripts/build_ibl_nodes.py` | 빌드 + 삼각 검증 (`--check`로 src↔tool.json↔handler.py `_OP_DISPATCHERS` AST 정확 비교) |
| `scripts/git-hooks/pre-commit` | 정합성 게이트 (commit 시점에 `--check` 자동 호출) |
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

**항상 허용되는 인프라 노드 (`_ALWAYS_ALLOWED`):**
`self`, `others` — 모든 에이전트에 자동 제공. self는 개인 도메인 관리, others는 협업/통신 전담.

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

IBL은 Phase 0(원시 도구 호출)에서 시작하여, 드라이버 기반 프로토콜 추상화(Phase 5-10), 노드 통합(Phase 17-25), verb 시스템 도입과 폐지(Phase 22-24), Goal/Time/Condition(Phase 26)을 거쳐 5-Node 체계로 발전했고, 이후 op 어휘화·사용성 재감사·어휘 정리로 현재 109 액션까지 압축됐다. 핵심 설계 철학은 "AI가 작성하는 언어"이며, 문법 복잡도보다 표현력을 우선한다.

*Phase 20: filesystem→orchestrator, webdev+design→creator, photo+blog+memory+health→librarian 통합.*
*Phase 21: finance+culture+study+legal+statistics+commerce+location+web(search/crawl/news)→informant 통합.*
*Phase 22: youtube+radio→stream, browser+android+desktop→interface, informant+librarian→source, orchestrator→system, creator→forge. 6개 노드, 321 액션.*
*Phase 23: system에서 위임 관련 7개 액션을 team 노드로 분리. 7개 노드(system, team, interface, source, forge, stream, messenger).*
*Phase 24: verb 시스템 제거. 런타임 verb→action 해석 삭제. 프롬프트 가독성을 위해 category 태그로 대체 (순수 표시용).*
*Phase 25: 5-Node 최종 구조 재설계. source→sense(외부 정보), system→self(개인 도메인), interface+stream→limbs(신체/장치), team+messenger→others(협업/통신), forge→engines(엔진/창작). 총 308 액션.*
*Phase 26: self 노드에 log_attempt, get_attempts (전략 에스컬레이션/라운드 메모리). sense 노드에 cctv_refresh, cctv_stats (UTIC 실시간 API).*
*최종 업데이트: 2026-06-10 — 111 액션 정합화(안드로이드 얇은 부활 [limbs:android]{op} + 폰 컴패니언 [sense:phone]{op} 반영, 음악 작곡 은퇴). 이전: 2026-04-05 (phase26_goal_time_condition.md, ibl_development_plan.md 통합)*
