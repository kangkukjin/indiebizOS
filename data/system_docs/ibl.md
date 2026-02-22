# IBL (IndieBiz Logic)

> indiebizOS의 정보 흐름 추상화 언어

## IBL이 하는 일

IBL은 에이전트가 정보를 가져오고, 가공하고, 전달하는 과정을 하나의 패턴으로 표현한다.

```
[node:action](target) {params}
```

- **node**: 어디서 (source, system, forge, ...)
- **action**: 무엇을 (search, get, create, ...)
- **target**: 대상 ("삼성전자", "https://...", ...)
- **params**: 옵션 ({type: "book", limit: 10, ...})

API든 크롤링이든 안드로이드든 DB든, 에이전트는 같은 문법으로 요청한다. 프로토콜의 차이는 드라이버가 감춘다.

```
IBL 표현 계층:     [node:action](target) {params}
                         |
드라이버 계층:     http | websocket | adb | cdp | sqlite | file_io
                         |
물리 계층:         인터넷 | USB | 로컬디스크 | 프로세스간 통신
```

---

## 동사 (Verbs)

에이전트는 321개 개별 액션 이름 대신 **10개 공통 동사**로 모든 노드를 다룰 수 있다.

| 동사 | 의미 | 사용 예시 |
|------|------|----------|
| `search` | 찾기 | `[source:search]("뮤지컬") {type: "performance"}` |
| `get` | 가져오기 | `[source:get]("AAPL")` |
| `list` | 나열하기 | `[source:list]()` |
| `create` | 만들기 | `[forge:create]("발표자료") {type: "slide"}` |
| `control` | 조작하기 | `[interface:control]("설정 앱 열기")` |
| `write` | 저장하기 | `[system:write]("memo.md") {content: "..."}` |
| `read` | 읽기 | `[system:read]("report.pdf")` |
| `delete` | 지우기 | `[source:delete]("오래된 대화") {type: "memory"}` |
| `run` | 실행하기 | `[system:run_command]("ls -la")` |
| `send` | 보내기 | `[messenger:send]("안녕하세요") {type: "email"}` |

동사는 `type` 파라미터로 세분화된다. 예를 들어 `[source:search]`에서:
- `{type: "performance"}` → 공연 검색
- `{type: "stock"}` → 주식 검색
- `{type: "news"}` → 뉴스 검색
- type 없이 → 기본 웹 검색

기존 액션 이름(`[source:search_stock]`)도 그대로 동작한다. 동사는 정확한 액션이 없을 때 fallback으로 해석된다.

---

## 노드 (Phase 22: 6-Node 통합)

### 인프라 노드 — system (항상 허용)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `system` | 64 | 시스템 관리, 사용자 소통, 워크플로우, 자동화, 결과 출력, 파일시스템 | delegate, agent_ask, ask_user, approve, todo, notify_user, send_notify, run_pipeline, list_workflows, list_events, file, open, clipboard, run_command, fs_query |

Phase 19→22에서 기존 인프라 노드(system, user, workflow, automation, output, filesystem)를 `system`(구 orchestrator)으로 통합.

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `delegate` | 다른 에이전트에게 작업 위임 | `[system:delegate]("에이전트B") {message: "..."}` |
| `agent_ask` | 에이전트에게 질문/위임 | `[system:agent_ask]("투자/투자컨설팅") {message: "..."}` |
| `ask_user` | 사용자에게 질문 | `[system:ask_user]("어떤 형식을 원하시나요?")` |
| `approve` | 위험 작업 전 승인 요청 | `[system:approve]("파일을 삭제합니다")` |
| `todo` | 할일 목록 생성/관리 | `[system:todo]() {todos: [...]}` |
| `notify_user` | 사용자에게 알림 전송 | `[system:notify_user]("작업이 완료되었습니다")` |
| `run_pipeline` | 파이프라인 실행 | `[system:run_pipeline]("news_briefing")` |
| `file` | 결과물 파일 저장 | `[system:file]("result.md") {content: "..."}` |
| `open` | URL/파일 열기 | `[system:open]("https://google.com")` |

### 인터페이스 노드 — interface (browser + android + desktop 통합)

| 노드 | 액션 수 | 설명 | 주요 동사 |
|--------|---------|------|----------|
| `interface` | 79 | UI 조작 통합: 브라우저 자동화, 안드로이드 기기 관리, macOS 데스크탑 자동화 | navigate, snapshot, click, type, control, devices 등 |

Phase 22에서 browser(27) + android(43) + desktop(9) → `interface`로 통합.

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `navigate` | 웹 페이지 탐색 | `[interface:navigate]("https://example.com")` |
| `snapshot` | 브라우저 페이지 스냅샷 | `[interface:snapshot]()` |
| `click` | 요소 클릭 | `[interface:click]("검색 버튼")` |
| `devices` | 안드로이드 기기 목록 | `[interface:devices]()` |
| `desktop_screenshot` | macOS 스크린샷 | `[interface:desktop_screenshot]()` |

### 소스 노드 — source (informant + librarian 통합)

| 노드 | 액션 수 | 설명 | 주요 동사 |
|--------|---------|------|----------|
| `source` | 105 | 외부 정보 조사 + 내부 데이터 관리 통합: 금융, 문화, 학술, 법률, 통계, 부동산/쇼핑, 위치/CCTV, 웹검색/크롤링/뉴스, 사진/블로그/메모리/건강기록 | web_search, search_news, price, crawl, search, get, search_photos, search_blog, search_memory, save_health |

Phase 22에서 informant(64) + librarian(41) → `source`로 통합.

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `web_search` | 웹 검색 | `[source:web_search]("AI 뉴스")` |
| `search_news` | 뉴스 검색 | `[source:search_news]("부동산")` |
| `price` | 주가 조회 | `[source:price]("삼성전자")` |
| `crawl` | 웹 크롤링 | `[source:crawl]("https://...")` |
| `search` | 범용 검색 (type으로 분야 지정) | `[source:search]("뮤지컬") {type: "performance"}` |
| `search_photos` | 사진 검색 | `[source:search_photos]("가족")` |
| `search_blog` | 블로그 검색 | `[source:search_blog]("AI")` |
| `search_memory` | 대화 기억 검색 | `[source:search_memory]("지난 약속")` |
| `save_health` | 건강 기록 저장 | `[source:save_health]() {type: "blood_pressure", ...}` |

### 제작 노드 — forge (구 creator)

| 노드 | 액션 수 | 설명 | 주요 동사 |
|--------|---------|------|----------|
| `forge` | 46 | 슬라이드, 영상, 차트, 이미지, 음악, 웹사이트, 건축설계 | create, create_site, create_design, list, run, get |

Phase 22에서 creator → `forge`로 이름 변경.

### 미디어 노드 — stream (youtube + radio 통합)

| 노드 | 액션 수 | 설명 | 주요 동사 |
|--------|---------|------|----------|
| `stream` | 18 | 유튜브 + 라디오 재생/관리 통합 | play, info, transcript, download, radio_play, radio_stop, search |

Phase 22에서 youtube(9) + radio(9) → `stream`으로 통합.

### 연락 노드 — messenger (유지)

| 노드 | 액션 수 | 설명 | 주요 동사 |
|--------|---------|------|----------|
| `messenger` | 9 | 연락처 관리, 메시지 전송 | search, get, send, read |

---

## 파이프라인

IBL 액션을 연산자로 연결하면 파이프라인이 된다.

| 연산자 | 이름 | 의미 |
|--------|------|------|
| `>>` | Sequential | 순차 실행, 이전 결과를 다음에 전달 |
| `&` | Parallel | 동시 실행, 결과를 합침 |
| `??` | Fallback | 실패 시 대체 실행 |

```
# 순차: 검색 → 저장
[source:web_search]("AI 뉴스") >> [system:file]("news.md")

# 병렬: 두 검색 동시 실행
[source:web_search]("AI") & [source:web_search]("부동산")

# Fallback: 첫째 실패 시 둘째 시도
[source:price]("AAPL") ?? [source:price]("AAPL") {type: "kr"}

# 혼합
[source:web_search]("AI") & [source:web_search]("부동산") >> [system:file]("briefing.md")
```

---

## 워크플로우

자주 쓰는 파이프라인을 YAML로 저장해두면 한 줄로 실행할 수 있다.

```yaml
# data/workflows/news_briefing.yaml
name: "뉴스 브리핑"
pipeline: '[source:web_search]("AI 뉴스") & [source:web_search]("부동산 뉴스")'
```

실행: `[system:run_pipeline]("news_briefing")`

steps 형식도 지원:

```yaml
name: "주가 확인"
steps:
  - node: source
    action: price
    target: "삼성전자"
```

---

## 노드 타입

노드들은 노드 타입으로 그룹화되어 상위 레벨에서 접근할 수 있다.

| 노드 | 타입 | 하위 소스 | 사용법 |
|------|------|----------|--------|
| `ibl_info` | info | (레거시 — source로 통합됨) | `ibl_info(source="finance", ...)` → `[source:search_stock]` |
| `ibl_store` | store | (레거시 — source로 통합됨) | `ibl_store(store="health", ...)` → `[source:save_health]` |
| `ibl_exec` | exec | python, node, shell | `ibl_exec(action="python", target="print(1+1)")` |

---

## 해석 순서 (3-tier Resolution)

에이전트가 `[source:search]("뮤지컬")`을 호출하면:

1. **정확한 액션 매칭**: `source.actions.search`가 있는가? → 있으면 바로 실행
2. **동사 해석**: `source.verbs.search`에서 `type` 파라미터로 라우팅 → 실제 액션 결정
3. **에러**: 사용 가능한 액션과 동사 목록 반환

---

## 핵심 파일

| 파일 | 역할 |
|------|------|
| `data/ibl_nodes.yaml` | 노드 정의 (수동 액션: handler 라우팅) |
| `data/api_registry.yaml` | API 도구 정의 (node 필드로 자동 병합) |
| `backend/ibl_engine.py` | IBL 실행 엔진, 동사 해석, 라우팅, 자동 발견 |
| `backend/api_engine.py` | API 레지스트리 실행 엔진, transform 후처리 |
| `backend/ibl_parser.py` | IBL 문법 파서 (`>>`, `&`, `??`) |
| `backend/ibl_access.py` | 에이전트별 노드 접근 제어, 환경 프롬프트 |
| `backend/workflow_engine.py` | 파이프라인 실행, 워크플로우 관리 |
| `data/workflows/` | 저장된 워크플로우 YAML |

---

## 액션 라우팅 이원화 (Phase 18)

IBL 액션은 두 가지 경로로 실행된다:

### 1. api_engine 라우팅 (자동 발견)
`api_registry.yaml`에 `node` 필드가 있는 도구는 로드 시 자동으로 해당 노드의 액션으로 병합된다. `ibl_nodes.yaml`에 별도 등록이 필요 없다.

```yaml
# api_registry.yaml — node 필드만 추가하면 끝
kosis_search_statistics:
  service: kosis
  endpoint: /statisticsList.do
  transform: kosis_list
  node: source                  # ← Phase 22: statistics → source
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

## 시스템 AI IBL 통합 (Phase 17→22)

Phase 17에서 시스템 AI도 프로젝트 에이전트와 동일한 `execute_ibl` 단일 도구 구조로 통합되었습니다.
Phase 19에서 인프라 노드가 `orchestrator`로 통합, Phase 22에서 `system`으로 이름 변경되었습니다.
Phase 22에서 최종 6개 노드 구조가 완성되었습니다: system(64), interface(79), source(105), forge(46), stream(18), messenger(9).

**차이점은 접근 범위뿐:**
- 프로젝트 에이전트: `allowed_nodes`에 지정된 노드만 접근 가능
- 시스템 AI: 모든 노드 접근 가능 + 프로젝트 간 위임(`[system:delegate_project]`)

**항상 허용되는 인프라 노드 (`_ALWAYS_ALLOWED`):**
`system` — 모든 에이전트에 자동 제공 (기존 orchestrator → system으로 이름 변경)

**시스템 AI 전용 system 액션:**
| 액션 | 설명 |
|------|------|
| `list_projects` | 모든 프로젝트/에이전트 목록 조회 |
| `delegate_project` | 다른 프로젝트의 에이전트에게 작업 위임 |
| `manage_events` | 이벤트/스케줄 통합 관리 |
| `list_switches` | 등록된 스위치 목록 조회 |

---

*Phase 20: filesystem→orchestrator, webdev+design→creator, photo+blog+memory+health→librarian 통합.*
*Phase 21: finance+culture+study+legal+statistics+commerce+location+web(search/crawl/news)→informant 통합.*
*Phase 22: youtube+radio→stream, browser+android+desktop→interface, informant+librarian→source, orchestrator→system, creator→forge. 최종 6개 노드, 321 액션.*
*최종 업데이트: 2026-02-19*
