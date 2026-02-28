# IBL (IndieBiz Logic) 개발 계획

> indiebizOS를 위한 정보 흐름 추상화 언어
> 최종 업데이트: 2026-02-18

---

## 1. IBL이란

**IBL은 정보의 흐름을 위한 언어다.** 모든 정보 소스를 `[node:action](target)` 하나의 패턴으로 표현한다.

```
[정보 수집] → AI 사고/가공 → [정보 전달]
     IBL          Python/AI         IBL
```

### 핵심: 어디서 / 어떻게 / 무엇을 분리

| 구성요소 | 설명 | 담당 |
|---------|------|------|
| **어디서(Where)** | 정보의 출처/목적지 | IBL |
| **어떻게(How)** | 데이터 변환/가공 | Python, AI |
| **무엇을(What)** | 최종 결과물 | AI 판단, 프로그래밍 |

### 프로토콜은 드라이버가 감춘다

API든 크롤링이든 안드로이드든 DB든, IBL에서는 전부 같은 패턴이다:

```
IBL 표현 계층:     [node:action](target) { params }
                         |
드라이버 계층:     http | websocket | adb | cdp | sqlite | file_io
                         |
물리 계층:         인터넷 | USB | 로컬디스크 | 프로세스간 통신
```

리눅스 `read()`가 SSD인지 USB인지 신경 쓰지 않는 것과 같은 원리.

---

## 2. 완료된 것 (Phase 0-10)

| Phase | 내용 | 산출물 |
|-------|------|--------|
| 0 | 기반 정리 | `common/` 유틸리티, 10개 패키지 마이그레이션 |
| 1 | API 레지스트리 | `api_registry.yaml` (14개 서비스), `api_engine.py` |
| 2 | 채널 추상화 | `channel_engine.py` (Gmail, Nostr) |
| 3 | 웹 수집 | web 노드 등록 (부분 완료, 사이트 프로필 미완) |
| 4 | IBL 코어 | `ibl_engine.py`, `ibl_parser.py`, 7노드 35액션 |
| 5 | 워크플로우 | `workflow_engine.py`, 파이프라인 `>>` 실행 |
| 6 | AI 통합 | IBL 프롬프트, IBL 로깅, delegate_workflow |
| 7-1 | sqlite_driver | `drivers/base.py`, `drivers/sqlite_driver.py` → librarian(구 photo,health,blog,memory), contact (5 노드→2) |
| 7-2 | youtube 분리 | youtube 노드 (10 액션, handler 위임) |
| 7-3 | 금융/생활 통합 | finance (15 액션), location (5 액션), shopping (1 액션) |
| 7-4 | 하드웨어·자동화·서비스 | android (20), browser (15), radio (9), cctv (8), realestate (6), startup (2), culture (12), hosting (1) |
| 7-5 | 나머지 전체 통합 | desktop (9), study (11), webbuilder (13), storage (7), viz (7), media +2 (remotion, remotion_status) |
| 8 | 이벤트 & 트리거 | `event_engine.py`, event 노드 (9 액션), `calendar_manager` run_pipeline 연동 |
| 9 | 언어 정제 | `&` (병렬 실행), `??` (fallback), ThreadPoolExecutor 병렬 엔진 |
| 10 | 노드 추상화 | `node_registry.py`, 통일 디스크립터, `discover` 액션 |
| 11 | Agent as Node | 에이전트 노드 통합, `[agent:ask]`, discover 에이전트 검색 |
| 12 | Node-Centric Redesign | ibl_info/ibl_store/ibl_exec 타입 노드, 가이드 파일 on-demand 주입 |
| 13 | 동사 정규화 | 10개 공통 동사, 53 verb entries, 141 routes, 3-tier resolution |
| 14 | 노드 정리 | 37→26 노드 통합, 339 액션, 56 동사, 165 라우트 |
| 15 | 워크플로우 활성화 | pipeline YAML, 템플릿 7개, 복합 도구 분해 (337 액션) |
| 16 | IBL 단일화 | pre-IBL 중복 제거, 프롬프트/호출경로 통일, 프론트엔드 정리 |
| 17 | User 노드 + 시스템 AI IBL화 | user 노드(27번째), 시스템 AI execute_ibl 전환, 완전 통합 |
| 18 | API 자동 발견 | api_registry.yaml에 node 필드로 자동 병합, handler→api_engine 전환 24개 |
| 19 | 인프라 노드 통합 | system+user+workflow+automation+output+web일부 → orchestrator, web검색 → informant |
| 20 | 노드 재통합 | filesystem→orchestrator, webdev+design→creator, photo+blog+memory+health→librarian |
| 21 | 10-Node 최종 통합 | finance+culture+study+legal+statistics+commerce+location → informant, 31→10 노드, 321 액션 |

**Phase 0-10 완료 시점**: 30개 노드, 218개 액션, 3가지 연산자. 노드 추상화(discover) 완료.
**Phase 21 완료 시점**: 10개 노드, 321개 액션. 최종 통합 완료.

---

## 3. 앞으로 해야 할 일

### 핵심 문제: 아직 통합되지 않은 정보 소스들

현재 34개 도구 패키지가 있지만 대부분이 "어디서+어떻게+무엇을"이 뭉쳐있다. 이것들의 "어디서"를 분리해서 IBL로 통합해야 한다.

---

### Phase 7: 모든 정보 소스를 IBL로 통합

**목표**: API 이외의 정보 소스들 - 로컬 DB, 하드웨어, 브라우저, 스트림 - 을 전부 같은 `[node:action](target)` 패턴으로 사용할 수 있게 만든다.

#### 7-1. 드라이버 계층 만들기

지금 `api_client.py`가 HTTP 요청을 추상화하는 것처럼, 각 프로토콜마다 드라이버가 필요하다:

```
backend/drivers/
  http_driver.py      ← 이미 있음 (api_client.py)
  sqlite_driver.py    ← 사진, 건강, 블로그, 기억, 연락처
  adb_driver.py       ← 안드로이드 폰 (SMS, 앱, 화면)
  cdp_driver.py       ← 브라우저 자동화 (쇼핑, 정보 수집)
  stream_driver.py    ← 라디오, CCTV 실시간 스트림
  process_driver.py   ← 파이썬/노드 코드 실행
  file_driver.py      ← 파일 읽기/쓰기
```

공통 인터페이스:
```python
class Driver:
    def execute(self, action: str, target: str, params: dict) -> dict:
        """모든 드라이버가 같은 형태로 요청을 받고 결과를 반환"""
        ...
```

#### 7-2. 현재 도구에서 "어디서"를 분리해야 하는 것들

**로컬 DB 소스** (sqlite_driver):

| 현재 도구 | 정보 소스 | IBL 표현 |
|-----------|----------|----------|
| photo-manager | 사진 메타데이터 DB | `[librarian:search_photos]("2024년 봄")` (구: `[photo:search]`) |
| health-record | 건강 기록 DB | `[librarian:save_health]("혈압")` (구: `[health:query]`) |
| blog (RAG) | 블로그 글 벡터 DB | `[librarian:search_blog]("AI 에이전트")` (구: `[blog:search]`) |
| business | 연락처/이웃 DB | `[contact:search]("김사장")` |
| conversation_db | 대화 이력 | `[librarian:search_memory]("어제 약속")` (구: `[memory:search]`) |

지금 이것들은 각자 SQLite를 직접 열어서 쿼리를 실행한다. `sqlite_driver`를 만들면 전부 같은 패턴으로 접근할 수 있다.

**하드웨어 소스** (adb_driver, system_driver):

| 현재 도구 | 정보 소스 | IBL 표현 |
|-----------|----------|----------|
| android | 안드로이드 폰 | `[android:screenshot]()`, `[android:sms_list]()` |
| computer-use | macOS 데스크톱 | `[desktop:screenshot]()`, `[desktop:click](x, y)` |
| pc-manager | 로컬 파일시스템 | `[fs:scan]("~/Downloads")` |

**브라우저 소스** (cdp_driver):

| 현재 도구 | 정보 소스 | IBL 표현 |
|-----------|----------|----------|
| browser-action | 웹사이트 자동화 | `[browser:navigate](url)`, `[browser:extract]("table")` |
| shopping-assistant | 쇼핑 사이트 | `[browser:extract](danawa_url)` → 가격 정보 |
| web-builder | 웹 배포 | `[browser:deploy](site_config)` |

**스트림 소스** (stream_driver):

| 현재 도구 | 정보 소스 | IBL 표현 |
|-----------|----------|----------|
| radio | 라디오 방송 | `[radio:play]("KBS Classic FM")` |
| cctv | 교통/날씨 카메라 | `[cctv:stream](camera_id)` |
| youtube | 유튜브 동영상 | `[youtube:get_audio](url)`, `[youtube:transcript](url)` |

**복합/창작 소스**:

| 현재 도구 | 정보 소스 | IBL 표현 |
|-----------|----------|----------|
| media_producer | AI 이미지/슬라이드 | `[media:generate_image]("풍경")` |
| remotion-video | 프로그래밍 동영상 | `[media:render_video](template)` |
| music-composer | AI 작곡 | `[media:compose]("왈츠")` |
| visualization | 차트 생성 | `[media:chart](data)` |

#### 7-3. 새 노드 추가

현재 7개 노드에 다음을 추가:

```yaml
# ibl_nodes.yaml에 추가할 노드들

# 로컬 데이터 (Phase 20: photo,blog,memory,health → librarian 통합)
librarian:  # 구: photo, blog, memory, health
  search_photos, photo_stats, search_blog, search_memory, save_memory, save_health
  driver: sqlite

contact:
  search, get, list
  driver: sqlite

# 하드웨어
android:
  screenshot, tap, swipe, sms_list, contacts, install_app
  driver: adb

desktop:
  screenshot, click, type, open_app
  driver: system

# 브라우저
browser:
  navigate, click, type, extract, screenshot
  driver: cdp

# 스트림
radio:
  search, play, stop
  driver: stream (http)

cctv:
  list, stream, snapshot
  driver: stream (http)

youtube:
  search, get_audio, transcript, info
  driver: http

# 외부 서비스
shopping:
  search, compare, track_price
  driver: http + cdp

location:
  weather, restaurant, route, place_search
  driver: http

finance:
  stock_price, financial_statement, company_info, news
  driver: http (다중 API: FMP, Finnhub, DART, KRX)

# DB
db:
  query, insert, update, list_tables
  driver: sqlite
```

#### 7-4. 도구 분해 예시

```
현재: youtube_download_mp3(url)  ← 어디서+어떻게+무엇을 하나로 뭉침

IBL 분해:
  [youtube:get_audio](url)       ← 어디서: 유튜브에서 오디오 획득
  >> [media:convert]("mp3")      ← 어떻게: 포맷 변환 (범용)
  >> [fs:write]("song.mp3")      ← 무엇을: 파일 저장 (범용)

현재: search_shopping_and_compare(query)  ← 뭉침

IBL 분해:
  [shopping:search](query)       ← 어디서: 쇼핑 검색
  >> AI 비교 분석                 ← 어떻게: AI가 판단
  >> [fs:write]("비교표.md")      ← 무엇을: 결과 저장

현재: daily_news_briefing()  ← 뭉침

IBL 분해:
  [web:news]("AI")               ← 어디서: 뉴스 수집
  >> [web:news]("부동산")         ← 어디서: 다른 소스도 수집
  >> AI 요약 작성                 ← 어떻게: AI가 종합
  >> [channel:send](telegram)    ← 무엇을: 텔레그램 전송
```

이렇게 분해된 조합을 자주 쓰면 워크플로우로 저장:
```yaml
# data/workflows/youtube_to_mp3.yaml
name: "유튜브 MP3 다운로드"
steps:
  - [youtube:get_audio]($url)
  - >> [media:convert]("mp3")
  - >> [fs:write]($output_path)
```
`[orchestrator:run_pipeline](youtube_to_mp3)` 한 줄로 실행. (Phase 19: workflow:run → orchestrator:run_pipeline)

#### 7-5. 우선순위

1단계 ✅ (완료):
- `sqlite_driver` → librarian(구 photo,health,blog,memory), contact 노드 한번에 열림
- `youtube` 노드 분리 → 10개 액션 (info, transcript, play 등)

2단계 ✅ (완료):
- `finance` 노드 → 15개 액션 (DART, FMP, Finnhub, KRX, CoinGecko 통합)
- `location` 노드 → 5개 액션 (날씨, 맛집, 길찾기, 지도, 여행)
- `shopping` 노드 → 1개 액션 (네이버+다나와+중고 통합 검색)

3단계 ✅ (완료):
- `android` (20 액션), `browser` (15 액션) → 하드웨어/자동화 노드
- `radio` (9 액션), `cctv` (8 액션) → 스트림 노드
- `realestate` (6 액션), `startup` (2 액션), `culture` (12 액션), `hosting` (1 액션) → 서비스 노드

4단계 ✅ (완료):
- `desktop` (9 액션) - macOS GUI 자동화 (스크린샷, 클릭, 타이핑, 키보드, 마우스)
- `study` (11 액션) - 학술 검색 (OpenAlex, arXiv, PubMed, Semantic Scholar, Google Scholar, Guardian, World Bank, Google Books)
- `webbuilder` (13 액션) - 웹사이트 생성/빌드/배포 (Next.js + shadcn/ui, Vercel)
- `storage` (7 액션) - PC 저장소 관리 (스캔, 검색, 볼륨, 폴더 주석)
- `viz` (7 액션) - 데이터 시각화 (라인, 바, 캔들스틱, 파이, 산점도, 히트맵, 복합)
- `media` +2 액션 (remotion, remotion_status) - Remotion 프로그래밍 영상 생성

---

### Phase 8: 이벤트 & 트리거 ✅ (완료)

IBL에 push(트리거) 기능을 추가하여 pull + push 양방향 통합 완료.

#### 구현된 것

**event 노드** (9 액션):
- `list`, `get`, `create`, `update`, `delete` — 트리거 CRUD
- `enable`, `disable` — 트리거 활성화/비활성화
- `status` — 이벤트 시스템 전체 상태 (channel_poller, scheduler, auto_response)
- `history` — 트리거 실행 이력

**트리거 타입**:
- `schedule` — 시간 기반 (calendar_manager 연동, run_pipeline 액션)
- `channel` — 메시지 수신 (규칙 저장, 향후 channel_poller 연동)
- `webhook`, `file` — 향후 확장 예정

**핵심 연동**:
- `calendar_manager.py` — `run_pipeline` 액션 추가 (IBL 파이프라인 스케줄 실행)
- `event_triggers.json` — 통합 트리거 레지스트리
- 트리거 생성 시 자동으로 calendar_manager에 이벤트 등록

**사용 예시**:
```
ibl_event(action="create", target="매일 AI 뉴스", params={
    "type": "schedule",
    "config": {"repeat": "daily", "time": "08:00"},
    "pipeline": "[web:news](\"AI\") >> [channel:send](gmail)"
})
ibl_event(action="status")
ibl_event(action="history", target="trg_xxx")
```

#### 향후 확장 (Phase 8+)
- `on` 키워드 문법: `on [channel:receive](telegram) >> [ai:process] >> [channel:send](telegram)`
- 파일 변경 감지: `on [fs:watch]("~/Downloads/*.pdf") >> ...`
- 웹훅 수신: `on [webhook:receive]("/api/hook") >> ...`
- channel_poller 트리거 규칙 런타임 적용

---

### Phase 9: 언어 정제 ✅ (완료)

IBL 파이프라인 언어에 두 가지 새 연산자를 추가하여 표현력을 크게 확장.

#### 구현된 연산자

| 연산자 | 이름 | 의미 | 예시 |
|--------|------|------|------|
| `>>` | Sequential | 순차 실행, 결과 전달 | `[web:search]("AI") >> [fs:write]("out.md")` |
| `&` | Parallel | 동시 실행, 결과 합침 | `[web:search]("AI") & [web:news]("부동산")` |
| `??` | Fallback | 실패 시 대체 실행 | `[api:call](main) ?? [api:call](backup)` |

#### 파서 확장 (ibl_parser.py)
- `_parse_group()`: 각 `>>` 세그먼트 내에서 `&`와 `??` 감지
- `_split_by_operator()`: 문자열/중괄호 안의 연산자 무시하는 범용 분리기
- 연산자 우선순위: `>>` (낮음) > `??` (중간) > `&` (높음)
- 특수 노드 출력: `{"_parallel": True, "branches": [...]}`, `{"_fallback_chain": [...]}`
- 기존 `>>` 전용 파이프라인과 100% 역방향 호환

#### 엔진 확장 (workflow_engine.py)
- `_execute_parallel()`: ThreadPoolExecutor (최대 8 워커) 동시 실행, 결과를 리스트로 합침
- `_execute_fallback()`: 순차 시도, 첫 성공 시 즉시 반환, 모든 실패 시 에러 + 시도 로그
- `execute_pipeline()`: 특수 노드 분기 (`_parallel`, `_fallback_chain`) 추가

#### 혼합 파이프라인 예시
```
# 병렬 수집 → 저장 → 전송
[web:search]("AI") & [web:news]("부동산") >> [fs:write]("결과.md") >> [channel:send](gmail)

# Fallback API → 전송
[api:call](primary) ?? [api:call](backup) >> [channel:send](telegram)

# 3개 병렬 + Fallback 체인
[web:search]("A") & [web:search]("B") & [web:search]("C")
[api:call](a) ?? [api:call](b) ?? [api:call](c)
```

#### 미구현 (설계 결정: AI에게 위임)
- **조건 분기**: AI가 자연어로 판단하는 것이 IBL 철학에 더 부합. `if` 문법 대신 AI 판단 활용.
- **AI 자가 진화**: 이미 `[orchestrator:save_workflow]` (구 `ibl_workflow(save)`) 존재. AI가 직접 파이프라인을 만들어 저장 가능.

---

### Phase 10: 노드 추상화 ✅ (완료) — "Everything is a Node"

모든 정보 소스를 "노드"로 추상화. 리눅스의 "Everything is a file"과 같은 원리.

```
노드(Node) = 메시지를 받고 → 처리하고 → 결과를 돌려주는 것

API 서버    → 노드  (프로토콜: HTTP)
Python 코드 → 노드  (프로토콜: 프로세스 실행)
브라우저    → 노드  (프로토콜: CDP)
안드로이드  → 노드  (프로토콜: ADB)
로컬 DB    → 노드  (프로토콜: SQLite)
다른 에이전트 → 노드  (프로토콜: 내부 IPC)
PC 자체    → 노드  (프로토콜: 시스템 콜)
```

#### 구현된 것

**1. 통일 디스크립터 (node_registry.py)**

`ibl_nodes.yaml`에서 자동 생성되는 노드 디스크립터:
```python
{
    "id": "finance",
    "type": "handler",           # handler | driver | engine | system
    "protocol": "mixed",         # http | sqlite | internal | mixed
    "description": "한국/미국 주식...",
    "actions": [{name, description, target, router}, ...],
    "action_count": 15,
    "tags": ["주식", "재무", ...]
}
```

- `list_nodes()` → 10개 노드의 통일된 디스크립터 (Phase 21 최종)
- `get_node(node)` → 특정 노드 상세
- `node_summary()` → 전체 요약 (노드 수, 액션 수, 타입 분포)

**2. 동적 발견 (discover)**

`[orchestrator:discover]("주가")` → "informant 노드의 search_stock 액션이 적합" (Phase 19: system→orchestrator, Phase 21: finance→informant)

- 노드 설명, 액션 설명, 태그에서 키워드 매칭
- 점수 기반 정렬, 최적 suggestion 자동 생성
- IBL 통합: `execute_ibl(node="orchestrator", action="discover", target="검색어")` (Phase 19: system→orchestrator)

```
"주가"  → informant [informant:search_stock]
"날씨"  → informant [informant:weather]
"사진"  → librarian [librarian:search_photos]
"Gmail" → messenger [messenger:send]
"유튜브" → youtube [youtube:info]
```

**3. 타입 호환성 — AI에게 위임 (설계 결정)**

파이프라인 노드 간 타입 호환성은 AI가 자연어로 판단. 형식적 타입 시스템 대신 AI의 유연한 매핑 활용.

#### 노드 추상화가 열어준 것

1. **자동 라우팅**: AI가 `discover`로 최적 노드 탐색
2. **노드 조합의 자유**: 어떤 노드든 `>>`, `&`, `??`로 조합
3. **메타 노드**: orchestrator 노드가 노드를 관리하는 노드 (Phase 19: system→orchestrator)
4. **통일된 메타데이터**: 10개 노드가 같은 형식의 디스크립터 (Phase 21 최종)

#### 참고 모델

| 모델 | 핵심 | IBL과의 관계 |
|------|------|-------------|
| **Erlang Actor Model** | 모든 것은 액터, 메시지로 통신 | 노드 = 액터 |
| **Unix pipe** | stdin/stdout 표준화, 조합 | >> & ?? 파이프라인 |
| **Linux VFS** | Everything is a file | Everything is a node |
| **MCP** | 도구의 표준 인터페이스 | 노드 디스크립터 |
| **마이크로서비스** | 서비스 디스커버리, API 게이트웨이 | discover, IBL 엔진 |

### Phase 11: Agent as Node ✅ (완료) — "에이전트도 노드다"

에이전트를 IBL 노드 시스템에 통합. `discover("주식 분석")`이 도구 노드뿐 아니라 해당 전문 에이전트도 반환.

#### 핵심 변경

1. **에이전트 노드 로딩 (node_registry.py)**
   - `_load_agent_nodes()`: 모든 프로젝트의 `agents.yaml` 스캔
   - `_build_agent_descriptor()`: 에이전트 설정 → 노드 디스크립터 변환
   - `_map_tools_to_capabilities()`: `allowed_tools` → IBL 노드 capabilities 매핑
   - `_enrich_agent_status()`: 실행 중 상태(running) 주입

2. **agent 노드 (ibl_nodes.yaml)**
   - `ask`: 에이전트에게 질문/위임 (`[agent:ask](투자/투자컨설팅)`)
   - `list`: 에이전트 노드 목록
   - `info`: 에이전트 상세 정보

3. **discover 통합**
   - `list_nodes(include_agents=True)`: 노드 + 에이전트 노드 병합
   - capabilities 매칭 보너스 점수로 관련 에이전트 검색

4. **캐시 무효화**
   - AgentRunner `start()`/`stop()`에서 `invalidate_agent_cache()` 호출

#### 에이전트 노드 디스크립터

```python
{
    "id": "투자/투자컨설팅",
    "type": "agent",
    "protocol": "delegation",
    "description": "많은 경험을 가진 자산관리 전문가.",
    "actions": [{"name": "ask", ...}],
    "capabilities": ["finance", "web", "study", ...],
    "running": True,
    "project_id": "투자",
    "agent_name": "투자컨설팅",
}
```

---

## 4. 정보 소스 통합 현황

### IBL로 접근 가능 (완료)

| 소스 유형 | 드라이버 | 노드 | 상태 |
|-----------|---------|--------|------|
| 외부 API 14개 | http (api_engine) | api | Phase 1 |
| 웹 검색/크롤링 | http (handler) | informant (구 web) | Phase 3→21 |
| 파일시스템 | file_io | orchestrator (구 fs→filesystem) | Phase 4→20 |
| 코드 실행 | process | orchestrator (구 fs→filesystem) | Phase 4→20 |
| 슬라이드/영상/음악 | 복합 | creator (구 media) | Phase 4→20 |
| Gmail, Nostr | http, websocket | messenger (구 channel→contact) | Phase 2→14 |
| 에이전트 위임 | internal | orchestrator (구 system) | Phase 6→19 |
| 워크플로우 | 내부 | orchestrator (구 workflow) | Phase 5→19 |
| 사진 DB | sqlite_driver | librarian (구 photo) | Phase 7-1→20 |
| 건강 기록 DB | sqlite_driver | librarian (구 health) | Phase 7-1→20 |
| 블로그 검색 | sqlite_driver | librarian (구 blog) | Phase 7-1→20 |
| 연락처/이웃 | sqlite_driver | messenger (구 contact) | Phase 7-1→14 |
| 대화 기억 | sqlite_driver | librarian (구 memory) | Phase 7-1→20 |
| 유튜브 | handler 위임 | youtube | Phase 7-2 |
| 주식/재무/암호화폐 | handler 위임 | informant (구 finance) | Phase 7-3→21 |
| 날씨/맛집/길찾기/여행 | handler 위임 | informant (구 location) | Phase 7-3→21 |
| 쇼핑/가격비교 | handler 위임 | informant (구 shopping) | Phase 7-3→21 |
| 안드로이드 폰 | handler 위임 | android | Phase 7-4 |
| 브라우저 자동화 | handler 위임 | browser | Phase 7-4 |
| 라디오 스트리밍 | handler 위임 | radio | Phase 7-4 |
| CCTV/웹캠 | handler 위임 | informant (구 cctv→location) | Phase 7-4→21 |
| 부동산 실거래가 | handler 위임 | informant (구 realestate→commerce) | Phase 7-4→21 |
| 창업 지원 | handler 위임 | informant (구 startup→commerce) | Phase 7-4→21 |
| 공연/도서/전시 | handler 위임 | informant (구 culture) | Phase 7-4→21 |
| Cloudflare 인프라 | handler 위임 | creator (구 hosting→webdev) | Phase 7-4→20 |
| 데스크탑 GUI | handler 위임 | desktop | Phase 7-5 |
| 학술 논문/데이터 | handler 위임 | informant (구 study) | Phase 7-5→21 |
| 웹사이트 생성/배포 | handler 위임 | creator (구 webbuilder→webdev) | Phase 7-5→20 |
| PC 저장소 관리 | handler 위임 | orchestrator (구 storage→filesystem) | Phase 7-5→20 |
| 데이터 시각화 | handler 위임 | creator (구 viz→creator) | Phase 7-5→14 |
| Remotion 영상 생성 | handler 위임 | creator (구 media→creator) | Phase 7-5→14 |
| 이벤트/트리거 관리 | event_engine | orchestrator (구 event/automation) | Phase 8→19 |

### 모든 정보 소스 + 이벤트 시스템 IBL 통합 완료 ✅

모든 도구 패키지(35개)가 IBL 10개 노드로 통합됨. pull(가져오기) + push(트리거) 양방향 통합 완료.

### Phase 7-4/7-5에서 완료

| 소스 유형 | 드라이버 | 노드 | Phase |
|-----------|---------|--------|------|
| 안드로이드 폰 | handler 위임 | android | Phase 7-4 |
| 브라우저 자동화 | handler 위임 | browser | Phase 7-4 |
| 라디오 | handler 위임 | radio | Phase 7-4 |
| CCTV | handler 위임 | informant (구 cctv→location) | Phase 7-4→21 |
| 부동산 | handler 위임 | informant (구 realestate→commerce) | Phase 7-4→21 |
| 창업 정보 | handler 위임 | informant (구 startup→commerce) | Phase 7-4→21 |
| 문화/공연 | handler 위임 | informant (구 culture) | Phase 7-4→21 |
| Cloudflare | handler 위임 | creator (구 hosting→webdev) | Phase 7-4→20 |
| 데스크탑 자동화 | handler 위임 | desktop | Phase 7-5 |
| 학술/리서치 | handler 위임 | informant (구 study) | Phase 7-5→21 |
| 웹사이트 빌더 | handler 위임 | creator (구 webbuilder→webdev) | Phase 7-5→20 |
| 저장소 관리 | handler 위임 | orchestrator (구 storage→filesystem) | Phase 7-5→20 |
| 데이터 시각화 | handler 위임 | creator (구 viz→creator) | Phase 7-5→14 |
| Remotion 영상 | handler 위임 | creator (구 media→creator) | Phase 7-5→14 |

---

## 5. 아키텍처 (목표)

```
사용자/AI
    |
    v
[IBL 표현]  ──── [node:action](target) { params }
    |
    v
[IBL 엔진]  ──── ibl_engine.py: 노드 → 드라이버 라우팅
    |
    +── api_engine     ──── API 레지스트리 (14개 서비스)
    +── channel_engine ──── 채널 어댑터 (Gmail, Nostr, Telegram)
    +── workflow_engine ──── 파이프라인/워크플로우
    +── (새로) drivers/ ──── 통합 드라이버 계층
    |     +── http_driver    ──── REST API, 크롤링
    |     +── sqlite_driver  ──── 로컬 DB (사진, 건강, 블로그, 기억, 연락처)
    |     +── adb_driver     ──── 안드로이드
    |     +── cdp_driver     ──── 브라우저 자동화
    |     +── stream_driver  ──── 라디오, CCTV
    |     +── process_driver ──── 코드 실행
    |     +── file_driver    ──── 파일 I/O
    |
    v
[물리 계층]  ──── 인터넷 | USB | 로컬디스크 | 프로세스간 통신
```

---

## 6. 참고

| 프로젝트 | 참고할 점 |
|---------|----------|
| **Linux VFS** | read()가 디바이스를 감추듯 IBL이 프로토콜을 감춤 |
| **Unix 파이프** | 단일 책임, 조합 가능성, stdin/stdout 표준화 |
| **MCP** (Anthropic) | 도구 정의 스키마, AI-도구 간 프로토콜 |
| **n8n** | 노드 기반 워크플로우, 데이터 파이핑 |
| **Erlang/OTP Actor Model** | 모든 것은 액터(노드), 메시지 패싱, 장애 격리 |
| **마이크로서비스** | 서비스 디스커버리, API 게이트웨이, 느슨한 결합 |

---

### Phase 12: Node-Centric Redesign ✅ (완료) — 노드 타입 기반 재편 + 가이드 파일 해결

두 가지 근본 문제를 해결:

**문제 A — 분류 오류**: CCTV와 주식 API는 같은 "외부 정보 소스" 타입이지만 별개 노드로 분류됨. 액션은 노드 이름이 아니라 노드 타입 기준으로 나눠야 한다.

**문제 B — 가이드 파일 손실**: 25개 가이드 파일(~166KB, ~41K 토큰)이 IBL 메타도구에 연결되지 않아 노드 지식 접근 불가.

#### 구현된 것

**1. 타입 노드 3개 도구 추가 (ibl_info, ibl_store, ibl_exec)**

기존 31개 노드 도구를 기능 타입으로 재편한 3개 상위 노드:

| 노드 | 타입 | 하위 소스/저장소 | 액션 수 |
|------|------|-----------------|---------|
| `ibl_info` | info | (레거시 — finance,culture,study,cctv,location,realestate,startup,shopping → informant 통합) | ~60 |
| `ibl_store` | store | (레거시 — photo,health,blog,memory → librarian 통합), contact, storage | ~27 |
| `ibl_exec` | exec | python, node, shell, remotion, video, slides, image, music | ~9 |

```
ibl_info(source="finance", action="price", target="AAPL")
ibl_store(store="health", action="summary")
ibl_exec(action="python", target="print(1+1)")
```

**2. 가이드 파일 on-demand 주입**

- `ibl_nodes.yaml`에 `guide` 필드 추가 (16개 노드)
- `ibl_engine.py`에서 `_resolve_guide()`, `_attach_guide()` → 결과 dict에 `_ibl_guide` 메타데이터 첨부
- `system_tools.py`에서 `_inject_guide_if_needed()`가 첫 호출 시 가이드 내용 주입
- 에이전트당 가이드별 1회만 주입 (중복 방지)

**3. target_key YAML 이동**

- 기존 `_TARGET_KEYS` dict 값들을 YAML 액션 config에 `target_key` 필드로 embed (~118개)
- YAML 우선, `_get_target_key()` fallback 유지

#### 파일 변경

| 파일 | 변경 |
|------|------|
| `data/ibl_nodes.yaml` | `nodes:` 섹션 추가, 기존 노드에 guide/target_key 필드 |
| `backend/ibl_engine.py` | `_execute_node()`, info/store/exec 라우팅, `_resolve_guide()`, `_attach_guide()`, `_route_by_config()` |
| `backend/system_tools.py` | `_inject_guide_if_needed()` dict 처리, IBL guide 메타데이터, 로깅 매핑 |
| `ibl-core/handler.py` | `_TYPED_NODE_MAP`, execute() 분기 |
| `ibl-core/tool.json` | ibl_info, ibl_store, ibl_exec 3개 도구 정의 |
| `backend/node_registry.py` | `_load_node_typed_descriptors()`, list_nodes 병합 |
| `data/common_prompts/fragments/11_ibl.md` | 타입 노드 섹션 추가 |

#### 역방향 호환

기존 31개 `ibl_*` 도구 모두 유지. 새 3개 타입 노드 도구가 추가되어 총 34개. 에이전트는 둘 중 선택 사용.

---

*Phase 12 완료 시점: 34 도구, 31 노드 + 3 타입노드, ~224 액션, 3 연산자. 노드 타입 기반 재편 + 가이드 파일 on-demand 주입. "Everything is a Node" 확장. (이후 Phase 21에서 10개 노드로 최종 통합)*

---

### Phase 13: 동사 정규화 (Verb Normalization) ✅ (완료) — "10개 동사로 모든 노드를 다룬다"

#### 배경: 왜 필요한가

Phase 7~12를 거치며 37개 노드, 341개 액션으로 모든 도구 패키지를 IBL에 통합했다.
하지만 되돌아보면 **332개 도구를 341개 액션으로 1:1 매핑**한 것에 가까웠다.
도구의 형태는 그대로인데 껍데기만 IBL 문법으로 씌운 것.

341개 액션을 패턴 분석해보면 실제 행동의 형태는 **25개**뿐이고, 상위 10개 패턴이 전체의 **76%**를 차지한다:

| 패턴 | 출현 횟수 | 출현 노드 수 |
|------|----------|--------------|
| search(query) → results | 60 | 24 |
| list([filter]) → items | 50 | 22 |
| get(id) → detail | 30 | 15 |
| query(params) → data | 30 | 12 |
| create(spec) → artifact | 27 | 7 |
| control(target, command) | 24 | 5 |
| write(target, content) | 15 | 11 |
| read(source) → content | 12 | 8 |
| delete(id) | 12 | 7 |
| execute(code) → output | 11 | 6 |

`search`라는 같은 행동이 24개 노드에서 60번 반복되고 있었다.
**같은 형태의 행동을 하나의 문법으로 통일하는 것**이 IBL 언어의 진짜 가치다.

#### 목표

에이전트가 341개 액션 이름이 아니라 **10개 동사**만 알면 어떤 노드든 다룰 수 있게 한다.

#### 핵심 동사 정의

| 동사 | 의미 | 형태 | 흡수하는 기존 액션들 |
|------|------|------|---------------------|
| `search` | 찾기 | (query) → results | performance, book, exhibit, laws, news, rag_search... (60개) |
| `get` | 가져오기 (1건) | (id) → detail | price, info, detail, transcript, weather... (30+30개) |
| `list` | 나열하기 | ([filter]) → items | devices, apps, favorites, posts, genres, box_office... (50개) |
| `create` | 만들기 | (spec) → artifact | slide, video, chart, image, floor_plan... (27개) |
| `control` | 조작하기 | (target, command) | click, tap, type, scroll, swipe, key, hover, drag... (24개) |
| `save` | 저장하기 | (target, content) | write, log, annotate, save_favorite, push_file... (15개) |
| `read` | 읽기 | (source) → content | crawl, snapshot, pull_file, content... (12개) |
| `delete` | 지우기 | (id) | delete_sms, delete_contact, uninstall, remove... (12개) |
| `run` | 실행하기 | (code/command) → output | exec_python, deploy, build, evaluate... (11개) |
| `send` | 보내기 | (to, message) | notify, sms_send, call, send_email... (5개) |

보조 동사 (필요 시): `capture`, `convert`, `open`, `stop`, `status`

#### 구현 설계

**ibl_nodes.yaml 구조 변경**:

```yaml
# 현재: 액션 이름이 곧 기능 식별자
culture:
  actions:
    performance:
      tool: kopis_quick_search
    book:
      tool: library_quick_search
    performance_detail:
      tool: kopis_get_performance

# 변경 후: 동사 기반, route로 하위 분기
culture:
  description: "공연/도서/전시 정보 노드"
  verbs:
    search:
      description: "문화 정보 검색 (공연, 도서, 전시)"
      routes:
        - match: {type: performance}
          tool: kopis_quick_search
          target_key: keyword
        - match: {type: book}
          tool: library_quick_search
          target_key: keyword
        - match: {type: exhibit}
          tool: kcisa_quick_search
          target_key: keyword
        - default: true
          tool: culture_unified_search
    get:
      description: "상세 정보 조회"
      routes:
        - match: {type: performance}
          tool: kopis_get_performance
          target_key: performance_id
        - match: {type: book}
          tool: library_get_book_detail
          target_key: isbn13
    list:
      description: "인기/추천 목록"
      routes:
        - match: {type: box_office}
          tool: kopis_box_office
        - match: {type: popular_books}
          tool: library_get_popular_books
```

**에이전트가 쓰는 방식**:
```
[culture:search]("위키드")                    ← 전체에서 검색
[culture:search]("위키드") {type: "공연"}      ← 공연만 검색
[culture:get]("PF123456")                     ← ID로 상세 조회
[culture:list]() {type: "인기도서"}            ← 인기 목록
```

**역방향 호환**: 기존 액션 이름을 alias로 유지
```
[culture:performance]("위키드")  → 내부에서 search {type: performance}로 변환
```

**에이전트 프롬프트 변화**:
```
현재 (341개 액션 나열):
| culture | performance, performance_detail, box_office, venue, festival, book, book_detail, ... | 22개 액션 |

변경 후 (동사만 안내):
| culture | search, get, list | 공연/도서/전시 정보. type으로 분야 지정 |
```

#### 기대 효과

- 에이전트가 외울 것: 341개 액션 → **10개 동사 × N개 노드**
- 프롬프트 토큰 대폭 감소
- 새 노드 추가 시 "이 노드도 search, get, list를 지원합니다" 한 줄이면 충분
- IBL의 원래 비전("같은 형태를 하나의 문법으로") 실현

#### 구현 결과

**핵심 변경**:
1. `_resolve_verb()` 함수 추가 (`ibl_engine.py`) — 3-tier resolution의 2단계
   - verbs 섹션에서 공통 동사 → 실제 액션으로 해석
   - `type` 파라미터로 routes 분기 지원
2. `ibl_nodes.yaml`에 `verbs:` 섹션 추가 — 22개 노드
3. `ibl_access.py` 환경 프롬프트 — verb 테이블 렌더링 (Action 테이블 대체)

**수치**: 53개 동사 entries, 141개 routes
**역방향 호환**: 기존 `[node:action]` 직접 호출 100% 유지. verb는 action 미매칭 시 fallback.

**3-tier 해석 순서**:
```
1. 정확한 액션 매칭:  [culture:book] → culture.actions.book
2. 동사 해석:         [culture:search] {type: book} → culture.verbs.search.routes.book → book
3. 에러:             사용 가능한 액션과 동사 목록 반환
```

---

### Phase 14: 노드 정리 (Node Consolidation) ✅ (완료) — "노드 = 행동의 주체"

#### 배경

동사가 통일되면 노드의 역할은 **"어디서"만 결정**한다.

```
[finance:search]("삼성전자")   ← "금융 쪽에서 찾아줘"
[culture:search]("뮤지컬")     ← "문화 쪽에서 찾아줘"
[android:control]("설정")      ← "폰에서 조작해줘"
```

이 시점에서 노드를 점검하면:
- search밖에 없는 작은 노드(shopping 1개, startup 2개)는 합치기 자연스러움
- 같은 동사를 받는데 쪼개져 있던 것들(fs+storage, system+agent)도 합칠 수 있음
- 기기 노드(android, browser, desktop)는 실체가 다르니 독립 유지

#### 노드 설계 원칙

1. **이름만으로 "이 노드는 누구인가"가 드러나야 한다**
2. **한 노드는 5개 이상의 의미 있는 동사-route 조합을 가져야 한다** (너무 작으면 합침)
3. **에이전트가 구분을 몰라도 되는 것들은 합치고, 알아야 하는 것들은 분리한다**
4. **노드는 "카테고리"가 아니라 행동의 주체(개체)다**

#### 통합 대상

| 통합 | 현재 노드들 | → 새 노드 | 이유 |
|------|------------|----------|------|
| 합침 | fs + storage | → **filesystem** | 같은 실체(파일시스템)에 대한 행동 |
| 합침 | system + agent + api | → **system** | 시스템 제어/위임 통합 |
| 합침 | startup + realestate + shopping | → **commerce** | 사업/부동산/쇼핑 정보 |
| 합침 | webbuilder + hosting | → **webdev** | 웹사이트 만들고 배포까지 한 주체 |
| 합침 | media + viz | → **creator** | 콘텐츠 제작 통합 |
| 합침 | event + collector | → **scheduler** | 스케줄/자동화/정기수집 |
| 합침 | contact + channel | → **contact** | 연락처 관리 + 메시지 발송 |
| 합침 | location + cctv + local | → **location** | 위치/지역 관련 통합 |
| 합침 | study + legal + statistics | → **research** | 조사/연구 정보 통합 |
| 이름변경 | web | → **search** | browser와 구분 |
| 이름변경 | output | → **publisher** | 결과물 저장/전달 주체 |

#### 구현 결과: 37개 → 26개

**8개 통합**:

| 통합 | 결과 | 액션 수 |
|------|------|---------|
| fs + storage → **filesystem** | 파일+저장소 | 20 |
| startup + realestate + shopping → **commerce** | 사업/부동산/쇼핑 | 9 |
| media + viz → **creator** | 콘텐츠 제작 | 22 |
| webbuilder + hosting → **webdev** | 웹 개발/배포 | 14 |
| location + cctv + local → **location** | 위치/지역 | 16 |
| contact + channel → **messenger** | 연락/메시지 | 9 |
| event + collector → **automation** | 스케줄/자동수집 | 12 |
| system + agent + api → **system** | 시스템 제어 | 11 |

**Phase 14 시점 26개 노드** (이후 Phase 19→21에서 10개로 통합):

기기 노드: android, browser, desktop (3)
서비스 노드: youtube, radio (2)
데이터 노드: librarian (Phase 20: photo+blog+memory+health 통합), messenger (2)
정보 노드: finance, culture, study, legal, statistics, commerce, location (7) → Phase 21: informant로 통합
제작 노드: creator (Phase 20: webdev+design 통합) (1)
인프라 노드: orchestrator (Phase 19: system,workflow,automation,output,user 통합 + Phase 20: filesystem 통합), informant (Phase 19: web 검색/크롤링 → Phase 21: 정보 노드 통합)

**파일 변경**: `ibl_nodes.yaml` (노드 통합), `system_tools.py` (_IBL_TOOL_PREFIX_MAP), `ibl_access.py` (_ALWAYS_ALLOWED)
**버그 수정**: location 노드의 action 이름 충돌 해결 (cctv와 local 모두 `search` → cctv를 `cctv_search`로 변경)
**수치**: 26 노드, 339 액션, 56 동사, 165 라우트

---

### Phase 15: 워크플로우 활성화 (Workflow Activation) — "파이프라인이 진짜 의미를 갖는다"

#### 배경

Phase 13-14에서 26개 노드에 56개 동사를 정규화하고 노드를 통합했다.
`>>`, `&`, `??` 연산자와 `execute_pipeline()`, `run_pipeline` 액션이 존재하지만, **실제 워크플로우가 하나도 없다** (`data/workflows/` 비어있음).

파이프라인 인프라는 완성되어 있지만 쓸 콘텐츠가 없는 상태.

#### 접근: 두 단계로 나눔

**15-A (이번)**: 워크플로우 활성화
- 워크플로우 YAML에 `pipeline` 문자열 직접 지원
- 대표 워크플로우 템플릿 5개 생성
- workflow 노드에 verbs 추가

**15-B**: 복합 도구 분해 — 1차 ✅ (완료)
- 에이전트가 원자 액션 조합으로 대체 가능한 복합 도구 제거
- 제거 원칙: 에이전트 본연의 능력(요약, 포매팅)을 도구로 만들 필요 없음
- **제거된 도구**:
  - `summarize_youtube` → `[youtube:transcript]` + 에이전트 요약 + `[output:file]`
  - `generate_newspaper` → `[web:news]` 반복 + 에이전트 포매팅 + `[output:file]`
- ibl_nodes.yaml 액션 제거, tool.json 도구 정의 제거
- Python 코드 유지 (호출 경로 차단, 복원 가능)
- 대체 워크플로우 템플릿: `youtube_summary.yaml`, `news_newspaper.yaml`
- 결과: 339 → 337 액션

향후 추가 분해 후보 (점진적 진행):
- create_html_video, compose_and_export 등 복합 도구

#### 워크플로우 YAML 형식

**steps 형식** (기존):
```yaml
name: "주가 확인"
steps:
  - node: finance
    action: search
    target: "삼성전자"
```

**pipeline 형식** (신규):
```yaml
name: "뉴스 브리핑"
pipeline: '[web:search]("AI 뉴스") & [web:search]("부동산 뉴스")'
```

`[orchestrator:run_pipeline]("news_briefing")` 한 줄로 실행. (Phase 19: workflow:run → orchestrator:run_pipeline)

#### 파이프라인 조합 예시

```
# 병렬 수집
[informant:web_search]("AI") & [informant:web_search]("부동산")

# 순차 파이프라인
[informant:search_arxiv]("transformer") >> [orchestrator:file]("papers.md")

# Fallback
[informant:search_stock]("AAPL") ?? [informant:search_stock]("AAPL") {type: "kr"}
```

#### 기대 효과

- `>>`, `&`, `??` 연산자가 실제로 쓰이게 됨
- AI가 직접 새 파이프라인을 만들어 워크플로우로 저장 가능 ("AI 자가 진화", Phase 9에서 설계)
- 새로운 조합을 코드 변경 없이 만들 수 있음
- IBL의 원래 비전 실현:
  ```
  [정보 수집] → AI 사고/가공 → [정보 전달]
       IBL          Python/AI         IBL
  ```

---

### 실행 우선순위

| 순서 | Phase | 영향도 | 난이도 | 상태 |
|------|-------|--------|--------|------|
| 1 | **Phase 13** | 최대 | 중간 | ✅ 완료 — 동사 정규화 (56 동사, 165 라우트) |
| 2 | **Phase 14** | 높음 | 낮음 | ✅ 완료 — 노드 통합 (37→26 노드) |
| 3 | **Phase 15-A** | 중간 | 낮음 | ✅ 완료 — 워크플로우 활성화 (pipeline YAML, 템플릿 5개) |
| 4 | **Phase 15-B** | 중간 | 낮음 | ✅ 1차 완료 — 복합 도구 분해 (summarize_youtube, generate_newspaper 제거) |
| 5 | **Phase 16** | 최대 | 중간 | ✅ 완료 — IBL 단일화 (pre-IBL 중복 제거, 프롬프트/호출경로 통일) |
| 6 | **Phase 17** | 최대 | 중간 | ✅ 완료 — User 노드 + 시스템 AI IBL화 (execute_ibl 단일 도구 완전 통합) |
| 7 | **Phase 18** | 높음 | 낮음 | ✅ 완료 — API 자동 발견 + handler→api_engine 전환 (24개 액션, ibl_nodes.yaml 경량화) |
| 8 | **Phase 19** | 최대 | 중간 | ✅ 완료 — 인프라 노드 통합 (system+user+workflow+automation+output+web일부 → orchestrator, web검색/크롤링 → informant) |
| 9 | **Phase 20** | 높음 | 중간 | ✅ 완료 — 노드 재통합 (filesystem→orchestrator, webdev+design→creator, photo+blog+memory+health→librarian) |
| 10 | **Phase 21** | 최대 | 중간 | ✅ 완료 — 10-Node 최종 통합 (finance+culture+study+legal+statistics+commerce+location+web → informant, 31→10 노드) |
| 11 | **Phase 22** | 최대 | 중간 | ✅ 완료 — 6-Node 최종 통합 (10→6 노드: stream, interface, source, system, forge) |

---

## Phase 16: IBL 단일화 (Pre-IBL 중복 제거)

### 배경

IBL은 기존 시스템 위에 후발로 추가되었다. 그 결과 **pre-IBL 코드와 IBL 코드가 동시에 존재**하며 같은 일을 두 가지 경로로 하고 있다. 시스템이 마치 처음부터 IBL 기반으로 만들어진 것처럼 정리하는 것이 이 Phase의 목표다.

### 핵심 원칙

IBL은 기존 인프라 위의 **라우팅 레이어**다. 제거할 것은 AI에게 보여주는 쪽(스키마, 프롬프트)이고, 실행 함수(tool_loader, system_tools 실행 함수, Gmail/Nostr 클라이언트)는 IBL 내부 구현으로 남긴다.

### 중복 영역 6가지

#### 16-1. 프롬프트 통일 (난이도: 낮음, 영향: 높음)

**현재**: 에이전트 모드 3가지 분기
- pre-IBL: tool.json 스키마로 프롬프트 구성
- hybrid (`ibl_enabled`): tool.json 스키마 + 정적 `11_ibl.md` 동시 주입
- IBL-only (`ibl_only`): `ibl_access.build_environment()` 동적 생성

**문제**: hybrid 모드는 AI에게 같은 기능을 두 가지 표기법으로 보여줘서 혼란 유발. `11_ibl.md`는 295줄 정적 파일로 노드 변경 시 수동 동기화 필요.

**목표**: hybrid 모드 제거, 모든 에이전트를 `ibl_only`로 통일

**변경 대상**:
- `backend/prompt_builder.py`: 3분기 → 단일 경로 (`build_environment()`)
- `data/common_prompts/fragments/11_ibl.md`: 삭제 가능
- 각 프로젝트 `agents.yaml`: `ibl_only: true` 통일

#### 16-2. 시스템 도구 스키마 제거 (난이도: 낮음, 영향: 중간)

**현재**: `system_tools.py`에 `SYSTEM_TOOLS` JSON 스키마 정의 ~190줄 (call_agent, list_agents, send_notification 등). IBL system 노드와 완전 중복.

**목표**: 스키마 정의 제거. 실행 함수(`execute_call_agent` 등)는 유지 (IBL이 내부적으로 호출).

**변경 대상**:
- `backend/system_tools.py`: `SYSTEM_TOOLS` 리스트 제거, IBL 로깅 심 (~120줄) 제거
- `backend/ai_agent.py`: `self.tools = SYSTEM_TOOLS + agent_tools` 로직 제거

#### 16-3. 도구 호출 경로 통일 (난이도: 중간, 영향: 높음)

**현재**: `agent_runner._get_available_tools()`에서 3가지 분기
```python
if ibl_only:     # IBL 도구만
elif ibl_enabled: # 양쪽 다
else:            # pre-IBL 도구만
```

**목표**: 단일 경로. 모든 에이전트가 `execute_ibl` 하나로 동작.

**선행 조건**: 16-1, 16-2 완료 후 진행

**변경 대상**:
- `backend/agent_runner.py`: `_get_available_tools()` 단순화
- `backend/tool_loader.py`: AI 프롬프트용 함수 (load_agent_tools, build_tool_package_map) 내부 전용으로 변경. handler 로딩은 유지.

#### 16-4. 죽은 handler.py 정리 (난이도: 중간, 영향: 중간)

**현재**: `api_registry.yaml`로 이관된 도구의 handler.py가 남아있음. `system_tools._execute_tool_inner()`에서 `is_registry_tool()` 체크가 우선하므로 handler.py는 실행되지 않지만 코드로 남아있음.

**목표**: api_registry에 이관 완료된 handler.py 함수 정리. IBL `router: api_engine` 경로만 남김.

**변경 대상**:
- 각 도구 패키지의 handler.py: api_registry와 중복되는 함수 제거
- `backend/system_tools.py`: `is_registry_tool` 우선 체크 로직 제거 (IBL router가 이미 결정)

#### 16-5. 도구 탐색 통일 (난이도: 중간, 영향: 중간)

**현재**: `tool_selector.py`가 tool.json 스캔으로 패키지 목록 생성. `node_registry.py`가 ibl_nodes.yaml에서 노드 목록 생성. 둘 다 "사용 가능한 도구 목록"을 제공.

**문제**: `tool_selector.SystemDirector`가 프로젝트 생성 시 패키지 기반(`allowed_tools`)으로 에이전트에 도구 배분. IBL은 노드 기반(`allowed_nodes`).

**목표**: `SystemDirector`가 `allowed_nodes`로 노드를 배분하도록 변경. `tool_selector`의 스캔 로직을 `node_registry`로 대체.

**변경 대상**:
- `backend/tool_selector.py`: `get_installed_tools()` → `node_registry.list_nodes()` 대체
- `backend/tool_selector.py`: `SystemDirector` → 노드 기반 배분으로 수정
- 각 프로젝트 `agents.yaml`: `allowed_tools` → `allowed_nodes` 이관

#### 16-6. 채널 인바운드 IBL화 (난이도: 높음, 영향: 낮음)

**현재**: `agent_runner._setup_channels()` + 폴링 루프가 IBL 밖에서 독자 동작. 인바운드 메시지 수신은 IBL 노드 모델과 다른 패턴 (지속적 폴링 vs 요청/응답).

**목표**: 인바운드 채널을 `[orchestrator:watch](gmail)` 또는 유사 메커니즘으로 IBL화. 단, 현재 동작에 문제 없으므로 후순위. (Phase 19: automation → orchestrator 통합)

**변경 대상**:
- `backend/agent_runner.py`: `_setup_channels()`, 폴링 루프
- `backend/channel_engine.py`: poll/listen 액션 추가 가능성
- `orchestrator` 노드: watch/trigger 액션 설계 (Phase 19: automation → orchestrator)

### 실행 순서

```
16-1 (프롬프트)  ──→  16-2 (시스템 도구)  ──→  16-3 (호출 경로)
                                                    ↓
                      16-4 (죽은 handler)  ──→  16-5 (탐색 통일)
                                                    ↓
                                              16-6 (채널) — 후순위
```

16-1 → 16-2는 독립적으로 진행 가능. 16-3은 16-1, 16-2 완료 후. 16-4, 16-5는 병렬 가능. 16-6은 나중에.

### 예상 제거 코드량

| 대상 | 예상 줄수 |
|------|:---:|
| SYSTEM_TOOLS 스키마 (system_tools.py) | ~190 |
| IBL 로깅 심 (system_tools.py) | ~120 |
| 11_ibl.md 정적 파일 | ~295 |
| agent_runner 분기 로직 | ~25 |
| tool_selector 중복 스캔 | ~100 |
| 기타 (ai_agent.py, 죽은 handler 등) | ~100+ |
| **합계** | **~830+** |

---

### Phase 16 실행 결과 ✅ (완료) — IBL 단일화

#### 16-1. 프롬프트 통일 ✅

- `backend/prompt_builder.py`: 3분기(`pre-IBL` / `hybrid` / `ibl_only`) → 단일 경로 (`build_environment()`)로 통일
- `data/common_prompts/fragments/11_ibl.md`: 삭제 (295줄 정적 파일 제거)
- 모든 에이전트가 `ibl_access.build_environment()`의 동적 프롬프트만 사용

#### 16-2. 시스템 도구 스키마 제거 ✅

- `backend/system_tools.py`: `SYSTEM_TOOLS` JSON 스키마 정의 ~190줄 제거
- IBL 로깅 심 ~120줄 제거 (`_IBL_TOOL_PREFIX_MAP` 기반 역매핑 불필요)
- 실행 함수(`execute_call_agent`, `execute_request_user_approval` 등)는 유지 (IBL이 내부 호출)

#### 16-3. 도구 호출 경로 통일 ✅

- `backend/agent_runner.py`: `_get_available_tools()`에서 3분기 → `["execute_ibl"]` 단일 반환
- `ask_user_question`, `todo_write`, `request_user_approval`, `list_agents` 도구 제거
- `backend/tool_loader.py`: `load_tool_schema()` 함수 추가 (execute_ibl 스키마 로딩)

#### 16-5. 도구 탐색 통일 ✅

- `backend/tool_selector.py`: `SystemDirector`가 `allowed_nodes`(노드 기반)로 배분하도록 변경
- 프로젝트 생성/프롬프트 생성 시 노드 기반 도구 할당

#### 프론트엔드 정리

- `frontend/src/components/Manager.tsx`: 불필요한 코드 정리
- `frontend/src/components/manager-dialogs/dialogs/SettingsDialog.tsx`: "도구" 탭 → "노드" 탭으로 변경
- `frontend/src/components/manager-dialogs/dialogs/index.ts`: `ToolAIDialog` 제거

---

### Phase 17: User 노드 + 시스템 AI IBL화 ✅ (완료) — "도구는 execute_ibl 하나"

#### 배경

Phase 16에서 프로젝트 에이전트를 `allowed_tools` → `allowed_nodes`로 전환했지만 두 가지 불완전함이 남아있었다:

1. **에이전트가 `execute_ibl` 외에 별도 도구를 가짐**: `ask_user_question`, `todo_write`, `request_user_approval`이 독립 도구로 남아 "도구는 execute_ibl 하나"라는 원칙이 깨짐
2. **시스템 AI는 옛날 패키지 방식 유지**: `load_tools_from_packages()` 방식으로 130+ 개별 도구를 직접 사용

설계 의도: **"사용자도 하나의 노드다"**, **"시스템 AI도 프로젝트 AI와 같은 구조다 — 차이는 접근 범위뿐"**

#### 변경 1: User 노드 추가

**1-1. `data/ibl_nodes.yaml` — user 노드 추가**

27번째 노드로 `user` 추가. 에이전트가 사용자와 소통하는 모든 행위를 IBL 노드로 통합:

| 액션 | 설명 | 예시 |
|------|------|------|
| `ask` | 사용자에게 질문 | `[user:ask]("어떤 형식을 원하시나요?")` |
| `approve` | 위험 작업 전 승인 요청 | `[user:approve]("파일을 삭제합니다")` |
| `todo` | 할일 목록 생성/관리 | `[user:todo]() {todos: [...]}` |
| `notify` | 사용자에게 알림 전송 | `[user:notify]("작업이 완료되었습니다")` |

**1-2. `backend/ibl_engine.py` — _route_system() 확장**

user 노드 함수 4개 라우팅 추가:
- `ask_user_question` → `execute_ask_user_question()`
- `request_user_approval` → `execute_request_user_approval()`
- `todo_write` → `execute_todo_write()`
- `send_notification` → 기존 라우팅 유지

**1-3. `backend/system_tools.py` — 실행 함수 노출**

IBL에서 호출할 수 있도록 래퍼 함수 추가:
- `execute_ask_user_question(params, project_path)` — 신규
- `execute_todo_write(params, project_path)` — 신규
- `execute_request_user_approval()` — 기존 유지
- `execute_send_notification()` — 기존 유지

`_ibl_user_action` 마커로 프론트엔드 특수 처리 시그널링.

**1-4. `backend/agent_runner.py` — 도구 목록에서 제거**

`_get_available_tools()` → `["execute_ibl"]`만 반환. 모든 사용자 소통 도구가 user 노드로 이동.

**1-5. `backend/ibl_access.py` — user 노드를 ALWAYS_ALLOWED에 추가**

```python
# Phase 17 시점:
_ALWAYS_ALLOWED = {"system", "workflow", "automation", "output", "user"}
# Phase 19 이후:
_ALWAYS_ALLOWED = {"orchestrator"}
```

#### 변경 2: 시스템 AI IBL 전환

**2-1. `data/ibl_nodes.yaml` — 시스템 AI 전용 액션**

`system` 노드에 시스템 AI용 4개 액션 추가:

| 액션 | 함수 | 설명 |
|------|------|------|
| `list_projects` | `list_project_agents` | 모든 프로젝트/에이전트 목록 조회 |
| `delegate_project` | `call_project_agent` | 프로젝트 에이전트에게 작업 위임 |
| `manage_events` | `manage_events` | 이벤트/스케줄 관리 |
| `list_switches` | `list_switches` | 등록된 스위치 목록 조회 |

**2-2. `backend/ibl_engine.py` — 시스템 AI 전용 함수 라우팅**

`_route_system()`에 `api_system_ai`의 4개 함수 import 및 라우팅 추가.

**2-3. `backend/system_ai_runner.py` — execute_ibl 단일 도구로 전환**

기존 130+ 패키지 도구 → `execute_ibl` 단일 도구:
```python
# 기존: tools = load_tools_from_packages(SYSTEM_AI_DEFAULT_PACKAGES) + 특수도구들
# 변경: tools = [load_tool_schema("execute_ibl")]
```

`_execute_tool()` → `system_tools.execute_tool()` 경로로 통일.

**2-4. `backend/prompt_builder.py` — 시스템 AI에 IBL 환경 주입**

`build_system_ai_prompt()`에 IBL 환경 추가:
```python
from ibl_access import build_environment
ibl_env = build_environment(allowed_nodes=None)  # None = 전체 노드 접근
```

**2-5. `backend/api_system_ai.py` — 도구 목록/실행 업데이트**

- `get_all_system_ai_tools()` → `[load_tool_schema("execute_ibl")]` 반환
- `execute_system_tool()` → `system_tools.execute_tool()` 경로로 통일
- `get_anthropic_tools()` → `get_all_system_ai_tools()` 직접 반환

**2-6. `backend/api_websocket.py` — todo_write 감지 업데이트**

tool_name이 `execute_ibl`일 때 params에서 todos 추출하는 로직 추가 (프로젝트 에이전트 + 시스템 AI 양쪽):
```python
elif tool_name == "execute_ibl":
    _ibl_params = tool_input.get("params", {})
    _ibl_todos = _ibl_params.get("todos", [])
    if _ibl_todos:
        message_data["todos"] = _ibl_todos
        message_data["name"] = "todo_write"  # 프론트엔드 호환
```

#### 수정 파일 목록

| 파일 | 변경 내용 |
|------|---------|
| `data/ibl_nodes.yaml` | user 노드 추가, system 노드에 시스템AI 액션 추가 |
| `backend/ibl_engine.py` | _route_system()에 user/시스템AI 함수 라우팅 추가 |
| `backend/system_tools.py` | execute_ask_user_question, execute_todo_write 래퍼 함수 추가 |
| `backend/agent_runner.py` | _get_available_tools()에서 execute_ibl만 남김 |
| `backend/ibl_access.py` | _ALWAYS_ALLOWED에 "user" 추가 |
| `backend/system_ai_runner.py` | execute_ibl 단일 도구로 전환 |
| `backend/prompt_builder.py` | build_system_ai_prompt에 IBL 환경 주입 |
| `backend/api_system_ai.py` | 도구 목록/실행 경로 업데이트 |
| `backend/api_websocket.py` | todo_write 감지를 execute_ibl 경유 지원 |
| `backend/tool_loader.py` | load_tool_schema() 함수 추가 |

#### 버그 수정

- `execute_tool_call` → `execute_tool`: `system_ai_runner.py`와 `api_system_ai.py`에서 존재하지 않는 `execute_tool_call` 함수 참조 → `execute_tool`로 수정

#### 최종 수치 (Phase 17 시점)

- **27 노드** (26 + user) — Phase 21에서 10개로 최종 통합
- **339+ 액션**
- **58 동사, 167+ 라우트**
- **모든 에이전트(시스템 AI 포함): execute_ibl 단일 도구**
- **차이는 접근 범위뿐**: 시스템 AI = 전체 노드, 프로젝트 에이전트 = allowed_nodes
- **항상 허용**: orchestrator (Phase 19에서 system, workflow, automation, output, user 통합)

---

---

### Phase 18: API 자동 발견 + handler→api_engine 전환 ✅ (완료) — "api_registry가 노드를 안다"

**배경**: Phase 15-B에서 handler를 api_engine으로 대체하는 도구 분해를 시작했고, Phase 17에서 IBL 통합을 완성했으나 ibl_nodes.yaml이 2,379줄로 비대해지고 있었다. api_registry에 등록된 도구와 ibl_nodes.yaml의 액션 정의가 중복되는 문제를 해결해야 했다.

**핵심 발견**: api_engine.py에 이미 20+ transform 함수(kopis_list, library_docs, kosis_list 등)가 있어서 culture, legal, statistics, commerce 패키지의 handler.py가 단순 중복이었다. API 호출(api_registry)과 후처리(transform)가 이미 분리되어 있었다.

**Phase 18 작업 내용**:

#### 1단계: handler→api_engine 전환 (4개 패키지, 24개 액션)
| 패키지 | 전환 액션 수 | 남은 handler 액션 |
|--------|------------|------------------|
| legal | 6 | 0 (전부 전환) |
| statistics (kosis) | 5 | 0 (전부 전환) |
| culture | 11 | 11 (복잡 후처리: 코드 매핑, 캐시 등) |
| commerce (startup) | 2 | 7 (부동산 XML 파싱 등) |

`ibl_engine.py`의 `_route_api_engine()`에 `mapped_tool`/`target_key` 파라미터를 추가하여 노드 액션에서 api_registry 도구로 직접 라우팅.

#### 2단계: 자동 발견 아키텍처

**api_registry.yaml에 node 메타데이터 추가:**
```yaml
kosis_search_statistics:
  service: kosis
  endpoint: /statisticsList.do
  transform: kosis_list
  # IBL node binding (Phase 18)
  node: statistics
  action_name: search
  description: "통계표 목록 검색"
  target_key: keyword
  target_description: "검색 키워드"
```

**ibl_engine.py에 `_merge_api_registry_actions()` 추가:**
- `_load_nodes()` 시점에 api_registry의 node 바인딩 도구를 자동 병합
- YAML 앵커가 가리키는 동일 dict를 `dict.update()`로 in-place 변경 → nodes 섹션에도 자동 반영
- 수동 정의가 이미 있으면 덮어쓰지 않음 (안전장치)

**ibl_nodes.yaml에서 24개 api_engine 액션 제거:**
- legal, statistics: actions를 빈 dict(`{}`)로 변경 (주석: "api_registry에서 자동 병합됨")
- culture, commerce: api_engine 액션만 제거, handler 액션은 유지
- 2,379줄 → 2,243줄 (136줄 감소)

#### 수정된 파일

| 파일 | 변경 |
|------|------|
| `data/api_registry.yaml` | 24개 도구에 node/action_name/description/target_key/target_description 추가 |
| `backend/ibl_engine.py` | `_merge_api_registry_actions()` 함수 추가, `_load_nodes()`에서 호출, `_route_api_engine()`에 mapped_tool 지원 |
| `data/ibl_nodes.yaml` | 24개 api_engine 액션 제거 (자동 병합으로 대체) |

#### 최종 수치 (Phase 18 시점)

- **27 노드** (변동 없음) — Phase 21에서 10개로 최종 통합
- **341 액션** (api_engine 26, handler 261, 기타 54)
- **58 동사, 167 라우트** (변동 없음)
- **api_registry 자동 발견**: 새 API 도구 추가 시 node 필드만 넣으면 ibl_nodes.yaml 편집 불필요

---

### Phase 21: 10-Node 최종 통합 ✅ (완료) — "정보 노드는 informant 하나"

#### 배경

Phase 19에서 인프라 노드를 orchestrator로 통합하고, Phase 20에서 데이터/제작 노드를 librarian/creator로 통합했지만, 정보 노드 7개(finance, culture, study, legal, statistics, commerce, location)가 여전히 개별 노드로 존재했다.

이 7개 노드는 모두 "외부 정보를 조사해서 가져오는" 동일한 패턴을 가지고 있어 하나의 노드로 통합할 수 있었다.

#### 통합 대상

| 통합 전 | → | 통합 후 |
|---------|---|--------|
| finance, culture, study, legal, statistics, commerce, location | → | **informant** |
| web (search/crawl/news 부분) | → | **informant** (Phase 19에서 이미 이동) |

#### 주요 액션 이름 변경

| 이전 | 이후 |
|------|------|
| `[finance:search]` | `[informant:search_stock]` |
| `[web:search]` | `[informant:web_search]` |
| `[web:news]` | `[informant:search_news]` |

#### 최종 10개 노드 구조

| 노드 | 액션 수 | 역할 |
|------|---------|------|
| `orchestrator` | 64 | 시스템 관리, 사용자 소통, 워크플로우, 자동화, 결과 출력, 파일시스템 |
| `informant` | 64 | 외부 정보 조사 (금융, 문화, 학술, 법률, 통계, 부동산/쇼핑, 위치/CCTV, 웹검색) |
| `creator` | 46 | 콘텐츠 제작, 웹개발/배포, 건축설계 |
| `android` | 43 | 안드로이드 기기 관리 (ADB) |
| `librarian` | 41 | 로컬 데이터 관리 (사진, 블로그, 메모리, 건강기록) |
| `browser` | 27 | Playwright 브라우저 자동화 |
| `desktop` | 9 | macOS 데스크탑 자동화 |
| `messenger` | 9 | 연락처 관리 및 메시지 전송 |
| `youtube` | 9 | 유튜브 |
| `radio` | 9 | 라디오 |

**총 321 액션**, 10개 노드.

---

## Phase 22: 6-Node 최종 통합 (10→6 노드)

### 배경

2.0 제안서의 "동사 중심 원자적 재구성" 철학에 따라, Phase 21의 10개 노드를 6개로 최종 압축한다. AI가 보는 인터페이스를 더 간결하게 만들면서, 기존 35개 패키지 handler는 무변경으로 유지한다.

### 핵심 발견

`ibl_engine.py`(디스패처)와 35개 패키지 handler.py는 **노드 이름에 의존하지 않는다**. 변경은 주로 YAML 정의 + 접근 제어 매핑에 집중된다.

### 4단계 통합

| Step | 통합 | 위험도 |
|------|------|--------|
| Step 1 | youtube + radio → `stream` (18 액션) | 낮음 |
| Step 2 | browser + android + desktop → `interface` (79 액션) | 중간 |
| Step 3 | informant + librarian → `source` (105 액션) | 높음 |
| Step 4 | orchestrator → `system`, creator → `forge` (이름 변경) | 낮음 |

### 변경 파일

| 파일 | 변경 내용 |
|------|----------|
| `data/ibl_nodes.yaml` | 10개 노드 섹션 → 6개 노드 섹션으로 재구성 |
| `backend/ibl_access.py` | `_MERGED_TO_*` 매핑 추가, `_ALWAYS_ALLOWED` → `{"system"}`, 역호환 매핑 체인 |
| `backend/tool_selector.py` | `INFRA_NODES` → `{"system"}` |
| `backend/api_packages.py` | `always_allowed` → `{"system"}` |
| `projects/*/agents.yaml` | `allowed_nodes` 배열 치환 (migrate_nodes.py 스크립트) |

**변경 불필요 (0줄)**: `ibl_engine.py`, `ibl_parser.py`, `node_registry.py`, 35개 handler.py, 프론트엔드

### 역호환성

`ibl_access.py`의 `resolve_allowed_nodes()`에서 모든 역사적 노드 이름(31개+)을 현재 6개 노드로 매핑하는 체인을 유지한다:
- `"youtube"`, `"radio"` → `"stream"`
- `"browser"`, `"android"`, `"desktop"` → `"interface"`
- `"informant"`, `"librarian"`, `"finance"`, `"culture"`, `"study"`, `"photo"`, `"blog"` 등 → `"source"`
- `"orchestrator"`, `"user"`, `"workflow"`, `"automation"`, `"output"`, `"filesystem"` → `"system"`
- `"creator"`, `"webdev"`, `"design"` → `"forge"`

#### 최종 6개 노드 구조

| 노드 | 액션 수 | 역할 |
|------|---------|------|
| `source` | 105 | 데이터 검색/조회 (외부 정보 + 내부 저장소) |
| `interface` | 79 | UI 조작 (브라우저, 안드로이드, 데스크탑) |
| `system` | 64 | 시스템 관리, 사용자 소통, 워크플로우, 파일시스템 |
| `forge` | 46 | 콘텐츠 생성 (슬라이드, 영상, 차트, 이미지, 웹사이트) |
| `stream` | 18 | 미디어 재생 (유튜브, 라디오) |
| `messenger` | 9 | 연락처 관리 및 메시지 전송 |

**총 321 액션**, 6개 노드.

---

*현재 상태: Phase 22 완료 — 6-Node 최종 통합 (6 노드, 321 액션). source(105), interface(79), system(64), forge(46), stream(18), messenger(9).*
*Phase 22 통합: youtube+radio→stream, browser+android+desktop→interface, informant+librarian→source, orchestrator→system, creator→forge.*

---

### IBL 용례 RAG 시스템 (Phase 22 이후)

Phase 22의 6-Node 통합 이후, 에이전트의 IBL 생성 품질을 높이기 위한 용례 참조 시스템이 추가되었다.

**문제**: 321개 액션의 목록만으로는 AI가 정확한 파라미터, 파이프라인 패턴을 추론하기 어려움
**해결**: 과거 성공 사례를 하이브리드 검색(시맨틱+BM25)으로 찾아 프롬프트에 참조 주입

| 구성 요소 | 파일 | 역할 |
|-----------|------|------|
| 용례 사전 DB | `ibl_usage_db.py` | ~970개 용례 저장, 하이브리드 검색, 실행 로그 관리 |
| RAG 모듈 | `ibl_usage_rag.py` | 사용자 메시지에 유사 용례 XML 주입 |
| 데이터 생성기 | `ibl_usage_generator.py` | 합성 용례 생성 (규칙/템플릿/AI 3단계) |
| 자동 승격 | `ibl_usage_db.py` | 성공 실행 로그 → 용례 자동 변환 |

→ 상세 문서: [ibl_rag.md](ibl_rag.md)

*최종 업데이트: 2026-02-23*
