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

~320개 액션은 프롬프트 가독성을 위해 카테고리로 그룹화된다. 카테고리는 순수 표시 목적이며, 런타임 동작에 영향을 주지 않는다. 에이전트는 항상 구체적 액션명을 직접 사용해야 한다.

| 카테고리 | 의미 | 올바른 사용 예시 |
|---------|------|----------------|
| `search` | 찾기 | `[sense:web_search]{query: "AI 뉴스"}` |
| `get` | 가져오기 | `[sense:price]{symbol: "AAPL"}` |
| `list` | 나열하기 | `[sense:posts]{}` |
| `create` | 만들기 | `[engines:slide]{title: "발표자료"}` |
| `control` | 조작하기 | `[limbs:open_app]{name: "설정"}` |
| `fs` | 파일 조작 | `[self:read]{path: "report.pdf"}` |
| `io` | 결과 출력 | `[self:file]{path: "result.md"}` |
| `send` | 보내기 | `[others:channel_send]{channel_type: "gmail", to: "user@mail.com", subject: "제목", body: "내용"}` |

프롬프트에서 `<action-categories>` 태그로 표시되며, 각 카테고리에 속한 구체적 액션명이 나열된다. RAG 시스템이 정확한 액션명을 안내하므로, 에이전트는 카테고리명이 아닌 액션명을 직접 써야 한다.

## 액션 group

각 액션은 `group` 필드를 가진다. group은 같은 노드 안에서 액션의 소속/맥락을 나타낸다. 예: limbs 노드의 `contacts`는 `group: android`이므로 안드로이드폰 연락처, `click`은 `group: browser`이므로 Playwright 브라우저 클릭이다. discover에서 group명으로 검색할 수 있다.

| 노드 | 주요 group | 설명 |
|------|-----------|------|
| limbs | android, browser, desktop, media, cloudflare, launcher | 각 제어 대상별 구분 |
| sense | investment, culture, research, location, cctv, web, real_estate, youtube, radio, shopping, world | 정보 소스별 구분 |
| self | photo, blog, memory, health, file, storage, schedule, workflow, event, collect, output, system | 관리 영역별 구분 |
| engines | media_produce, music, chart, web_builder, architecture | 생산물 유형별 구분 |
| others | delegation, channel, business | 소통 유형별 구분 |

---

## 노드 (Phase 25: 5-Node 재구조화)

### 핵심 노드 분류

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `self` | ~57 | 개인 도메인: 시스템 관리, 파일, 설정, 사용자 소통, 워크플로우 | ask_user, approve, todo, notify_user, file, open, clipboard, run_command |
| `limbs` | 97 | 장치 제어: UI 조작(브라우저, 안드로이드, 데스크톱) + 미디어 재생 | navigate, snapshot, click, devices, play, stream, download, radio_play |
| `sense` | 105 | 감각 확장: 외부 정보 수집 + 내부 데이터 관리 | web_search, search_news, price, crawl, search_photos, rag_search, save_health |
| `others` | 15 | 협업 통신: 에이전트 위임 + 메시지 송수신 | delegate, ask, ask_sync, delegate_project, channel_send, channel_read, search_contact |
| `engines` | 46 | 창작: 콘텐츠 생성 (슬라이드, 영상, 차트, 이미지, 음악, 웹사이트, 설계) | create, create_site, create_design, run, get |

**Phase 25 통합 맥락:**
- source(105) → sense: 외부 정보 인식의 "감각 기관" 역할
- system(57) → self: 개인 영역 관리의 "자기 중심"
- interface(79) + stream(18) → limbs: 장치/미디어 조작의 "손발"
- team(7) + messenger(9) → others: 타인/협업의 "다른 개체"
- forge(46) → engines: 복잡한 프로세스를 기동시켜 결과물을 생성하는 "엔진"

**self 주요 액션:**

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `ask_user` | 사용자에게 질문 | `[self:ask_user]{question: "어떤 형식을 원하시나요?"}` |
| `approve` | 위험 작업 전 승인 요청 | `[self:approve]{message: "파일을 삭제합니다"}` |
| `todo` | 할일 목록 생성/관리 | `[self:todo]{todos: [...]}` |
| `notify_user` | 사용자에게 알림 전송 | `[self:notify_user]{message: "작업이 완료되었습니다"}` |
| `file` | 결과물 파일 저장 | `[self:file]{path: "result.md", content: "..."}` |
| `open` | URL/파일 열기 | `[self:open]{path: "https://google.com"}` |
| `run_command` | 코드/명령 실행 | `[self:run_command]{command: "python", args: "script.py"}` |
| `list_goals` | 등록된 목표 목록 조회 | `[self:list_goals]{status: "active"}` |
| `goal_status` | 목표 상태/진행도 조회 | `[self:goal_status]{goal_id: "goal_001"}` |
| `kill_goal` | 목표 취소/중단 | `[self:kill_goal]{goal_id: "goal_001"}` |
| `log_attempt` | 시도 기록 (전략 에스컬레이션) | `[self:log_attempt]{task_id: "T1", approach_category: "api", description: "REST 호출", result: "failure"}` |
| `get_attempts` | 시도 이력 조회 | `[self:get_attempts]{task_id: "T1"}` |

**others 주요 액션:**

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `delegate` | 동료 에이전트에게 작업 위임 | `[others:delegate]{agent_id: "심장전문", message: "..."}` |
| `ask` | 에이전트에게 질문 (비동기) | `[others:ask]{agent_id: "투자컨설팅", message: "..."}` |
| `ask_sync` | 에이전트에게 질문 (동기) | `[others:ask_sync]{agent_id: "투자컨설팅", message: "..."}` |
| `delegate_project` | 다른 프로젝트 에이전트에게 위임 | `[others:delegate_project]{project_path: "투자/투자컨설팅", message: "..."}` |
| `channel_send` | 메시지 발송 (gmail/nostr) | `[others:channel_send]{channel_type: "gmail", to: "user@mail.com", subject: "제목", body: "내용"}` |
| `search_contact` | 연락처 검색 | `[others:search_contact]{name: "김사장"}` |

### 수족 노드 — limbs (장치 제어 + 미디어 재생)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `limbs` | 97 | UI 조작(79) + 미디어 재생(18): 브라우저 자동화, 안드로이드 기기, 데스크톱, 유튜브, 라디오 | navigate, snapshot, click, devices, play, stream, download, radio_play |

구성: browser(27) + android(43) + desktop(9) + youtube(9) + radio(9)

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `navigate` | 웹 페이지 탐색 | `[limbs:navigate]{url: "https://example.com"}` |
| `snapshot` | 브라우저 페이지 스냅샷 | `[limbs:snapshot]{}` |
| `click` | 요소 클릭 | `[limbs:click]{element: "검색 버튼"}` |
| `devices` | 안드로이드 기기 목록 | `[limbs:devices]{}` |
| `play` | 유튜브/라디오 재생 | `[limbs:play]{url: "유튜브 링크"}` |
| `radio_play` | 라디오 방송 재생 | `[limbs:radio_play]{station: "KBS Classic FM"}` |
| `download` | 미디어 다운로드 | `[limbs:download]{url: "유튜브 링크"}` |

### 감각 노드 — sense (외부 정보 수집 + 내부 데이터 조회)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `sense` | 105 | 외부 정보(웹 검색, API) + 내부 DB(사진, 블로그, 기억, 건강): 금융, 문화, 학술, 법률, 통계, 부동산, 위치, CCTV, 뉴스 | web_search, search_news, price, crawl, search_photos, rag_search, search_memory, save_health |

구성: 정보 수집(웹 API, 크롤링) + 로컬 DB 조회(사진, 블로그, 메모리, 건강)

| 주요 액션 | 설명 | 예시 |
|----------|------|------|
| `search` | **종합 검색** (웹+뉴스+유튜브+논문 병렬) | `[sense:search]{query: "AI 뉴스"}` |
| `web_search` | 웹만 검색 (DuckDuckGo) | `[sense:web_search]{query: "AI 뉴스"}` |
| `search_news` | 뉴스 검색 | `[sense:search_news]{keyword: "부동산"}` |
| `price` | 주가 조회 | `[sense:price]{symbol: "삼성전자"}` |
| `crawl` | 웹 크롤링 | `[sense:crawl]{url: "https://..."}` |
| `stock_info` | 주식 상세 정보 | `[sense:stock_info]{symbol: "삼성전자"}` |
| `search_photos` | 사진 검색 | `[sense:search_photos]{query: "가족"}` |
| `rag_search` | 블로그 RAG 검색 | `[sense:rag_search]{query: "AI"}` |
| `search_memory` | 대화 기억 검색 | `[sense:search_memory]{query: "지난 약속"}` |
| `save_health` | 건강 기록 저장 | `[sense:save_health]{type: "blood_pressure", ...}` |
| `cctv_search` | CCTV 통합 검색 (UTIC→ITS→Windy) | `[sense:cctv_search]{query: "광화문"}` |
| `cctv_refresh` | UTIC API 최신 데이터 갱신 | `[sense:cctv_refresh]` |
| `cctv_stats` | CCTV 데이터 소스 통계 | `[sense:cctv_stats]` |

### 엔진 노드 — engines (콘텐츠 생성)

| 노드 | 액션 수 | 설명 | 주요 액션 |
|--------|---------|------|----------|
| `engines` | 46 | 콘텐츠 창작: 슬라이드, 영상, 차트, 이미지, 음악, 웹사이트, 건축설계 | create, create_site, create_design, run, get |

특징: 복잡한 프로세스를 기동시켜 결과물을 산출하는 엔진 노드.

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
[sense:web_search]{query: "AI 뉴스"} >> [self:file]{path: "news.md"}

# 병렬: 두 검색 동시 실행
[sense:web_search]{query: "AI"} & [sense:web_search]{query: "부동산"}

# Fallback: 첫째 실패 시 둘째 시도
[sense:price]{symbol: "AAPL"} ?? [sense:price]{symbol: "AAPL", type: "kr"}

# 혼합
[sense:web_search]{query: "AI"} & [sense:web_search]{query: "부동산"} >> [self:file]{path: "briefing.md"}
```

---

## 워크플로우

자주 쓰는 파이프라인을 YAML로 저장해두면 한 줄로 실행할 수 있다.

```yaml
# data/workflows/news_briefing.yaml
name: "뉴스 브리핑"
pipeline: '[sense:web_search]{query: "AI 뉴스"} & [sense:web_search]{query: "부동산 뉴스"}'
```

실행: `[self:run_pipeline]{name: "news_briefing"}`

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
| `ibl_info` | info | (레거시 — sense로 통합됨) | `ibl_info(source="finance", ...)` → `[sense:search_stock]` |
| `ibl_store` | store | (레거시 — sense로 통합됨) | `ibl_store(store="health", ...)` → `[sense:save_health]` |
| `ibl_exec` | exec | python, node, shell | `ibl_exec(action="python", target="print(1+1)")` |

---

## 해석 순서

에이전트가 `[sense:web_search]{query: "AI"}`을 호출하면:

1. **액션 매칭**: `sense.actions.web_search`가 있는가? → 있으면 실행
2. **에러**: 없으면 사용 가능한 액션 목록 반환

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
| `backend/goal_evaluator.py` | Goal 조건 평가, 비용 산출 (Phase 26) |

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

### 조건문 (if/else) — 상황에 따른 분기

```
[if: sense:kospi < 2400]{
  [goal: "방어적 포트폴리오 재편"]{deadline: "즉시", max_rounds: 10}
} [else]{
  [goal: "성장주 모니터링 유지"]{every: "매일 09:00", max_rounds: 30}
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
[self:list_goals]{status: "active"}       # 진행 중인 목표 조회
[self:goal_status]{goal_id: "goal_001"}   # 특정 목표 상태 조회
[self:kill_goal]{goal_id: "goal_001"}     # 목표 중단
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
    "하락": [sense:apt_trade]{region: "청주", depth: "deep"},
    "상승": [goal: "관망"]{max_rounds: 1},
    default: [sense:apt_trade]{region: "청주", depth: "shallow"}
  }
}
```
| `backend/ibl_usage_db.py` | IBL 용례 사전 DB + 하이브리드 검색 |
| `backend/ibl_usage_rag.py` | 용례 RAG 참조 모듈 |
| `data/ibl_usage.db` | 용례 사전 + 실행 로그 DB |

---

## 용례 RAG 참조 시스템

에이전트가 IBL 코드를 생성할 때, 유사한 과거 성공 사례를 자동으로 참조한다.

사용자 메시지가 들어오면 용례 사전에서 하이브리드 검색(시맨틱 70% + BM25 30%)으로 유사 용례를 찾아 XML 형태로 프롬프트에 주입한다. AI는 이 참조를 기계적으로 복사하지 않고, 현재 상황에 맞게 변형한다.

```xml
<ibl_references note="참고만 하고 현재 요청에 맞게 변형하세요.">
  <ref intent="아파트 매매 실거래가" code='[sense:apt_trade]{region_code: "지역코드"}' score="0.88"/>
</ibl_references>
```

성공한 도구 실행 로그는 자동으로 용례 사전에 승격되어, 시스템이 사용할수록 참조 품질이 향상된다.

→ 상세 문서: [ibl_rag.md](ibl_rag.md)

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
Phase 19-22에서 점진적으로 노드를 통합했으며, Phase 25에서 최종 5개 노드 구조로 재구조화되었습니다: self(~57), limbs(97), sense(105), others(16), engines(46).

**차이점은 접근 범위뿐:**
- 프로젝트 에이전트: `allowed_nodes`에 지정된 노드만 접근 가능
- 시스템 AI: 모든 노드 접근 가능 + 프로젝트 간 위임(`[others:delegate_project]`)

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

*Phase 20: filesystem→orchestrator, webdev+design→creator, photo+blog+memory+health→librarian 통합.*
*Phase 21: finance+culture+study+legal+statistics+commerce+location+web(search/crawl/news)→informant 통합.*
*Phase 22: youtube+radio→stream, browser+android+desktop→interface, informant+librarian→source, orchestrator→system, creator→forge. 6개 노드, 321 액션.*
*Phase 23: system에서 위임 관련 7개 액션을 team 노드로 분리. 7개 노드(system, team, interface, source, forge, stream, messenger).*
*Phase 24: verb 시스템 제거. 런타임 verb→action 해석 삭제. 프롬프트 가독성을 위해 category 태그로 대체 (순수 표시용).*
*Phase 25: 5-Node 최종 구조 재설계. source→sense(외부 정보), system→self(개인 도메인), interface+stream→limbs(신체/장치), team+messenger→others(협업/통신), forge→engines(엔진/창작). 총 321 액션 유지.*
*Phase 26: self 노드에 log_attempt, get_attempts (전략 에스컬레이션/라운드 메모리). sense 노드에 cctv_refresh, cctv_stats (UTIC 실시간 API).*
*최종 업데이트: 2026-03-09*
