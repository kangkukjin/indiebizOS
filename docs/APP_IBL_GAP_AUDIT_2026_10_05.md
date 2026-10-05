# 앱 전수 감사 — IBL 위에 서지 않은 앱과, 그 이유가 된 언어의 공백

작성일: 2026-10-05. 상태: **조사 보고(판정·집행 전)**. 독자: 앱을 IBL 기반으로 재구성할 구현자, 언어 개정 판정자.
전제(사용자, 2026-10-05): *앱은 충분히 튼튼한 IBL 위에서 만들어져야 한다. 지금 앱들은 어휘·문법이 익기 전에 하나씩 만들어졌다. IBL로 될 수 있는데 그렇게 하지 않은 것을 찾고, 그보다 중요하게 IBL이 더 많은 앱의 기반이 되기 위해 아직 갖지 못한 것을 찾아라.*

같은 날의 [공통 기반 위의 앱 구성 — 코딩·문서·스프레드시트](APP_COMPOSITION_ON_IBL_PLAN_2026_10_05.md)는 세 앱을 다뤘다. 이 문서는 **나머지 전부**를 같은 축으로 조사하고, 세 앱 계획서가 전제한 것 중 지금 언어가 받쳐 주지 못하는 지점(§3-G4)을 짚는다.
판정 기준은 [IBL 진화 목적](IBL_EVOLUTION_PURPOSE.md), [ibl.md](../data/system_docs/ibl.md) "언어의 경계"·"표현 언어의 층위"·"뷰 어휘 승격 4기준", [앱=매니페스트](APP_AS_MANIFEST_DESIGN.md) "순증 어휘 0"이다.

## 0 조사 방법과 범위

- 대상: `app:` 블록 33개 + 독립 매니페스트 2장(`data/instruments/`) + 전용 React·REST 앱 약 20개 + 회원 앱(`/m/*`) + 원격·폰 렌더러. 코딩·문서·스프레드시트는 위 계획서 수치를 인용만 한다.
- 각 앱마다 (1) 백엔드 호출이 `/ibl/execute`로 가는 비율, (2) 전용 REST 각각에 같은 일을 하는 IBL 낱말이 있는가, (3) 우회를 강제한 것이 **(a) 어휘 공백 / (b) 뷰 프리미티브·이벤트 공백 / (c) 언어·런타임 공백 / (d) 정당한 코드(엔진·드라이버)** 중 무엇인가를 기록했다.
- 숫자는 전부 대략치다(줄 수는 `wc -l`, 비율은 호출 지점 수 기준). 성능은 측정하지 않았다.

## 1 전체 그림 — 앱은 세 부류다

| 부류 | 앱 | 비고 |
| --- | --- | --- |
| **A. 순수 선언형** (IBL ≈100%) | 라디오·CCTV·음악·노트북·일정·웹앱·정기보고·비즈니스·재무·건강·메신저·IndieNet·게시판·가족신문·쇼케이스·포털(소유자면)·날씨·도서·맛집·투자·실거래가·상권·숙소·공연·공모전·외주·사업공고 | 바이트(썸네일·스트림)와 폰 동기화만 REST. **이 부류의 REST 잔재는 대부분 죽은 코드다**(§2-1) |
| **B. 혼합** (제어는 IBL, 표현은 escape) | 신문·유튜브뮤직·지도·빈노트·폴더 기억판 | "능력은 어휘, 표현은 컴포넌트"(철칙 0)를 지킨다. 우회는 표면 언어의 공백 때문 |
| **C. IBL 0~25%** (전용 REST + 전용 React) | 사진 전용창·PC관리(탐색·분석)·폴더 창·검색브라우저·강의·매니저·멀티채팅·팀채팅·공유창고·업무기록 화면·NAS Finder·외부사용자·(코딩·문서·스프레드시트) | 우회 코드 합계 약 **3만 줄** |

C 부류의 규모(프론트+백엔드, 약):

| 앱 | 우회 줄 수 | IBL 비율 | 같은 일을 하는 IBL 낱말이 이미 있는 REST |
| --- | --- | --- | --- |
| 강의 만들기 | 5,900 | 5% | 34개 중 18개(슬라이드 6개는 `handler_mod.execute`로 IBL 핸들러를 그대로 감쌈) |
| 코딩·문서·스프레드시트 | 5,600 | — | 계획서 참조 |
| 공유창고 | 4,300 | 15% | neighbors/add·score·remove = `[others:neighbor]` |
| 사진 전용창 | 3,270 | 0% | save = `[self:copy]`, open-external = `[limbs:os_open]`, gallery·stats = `self:photo >> table:groupby` |
| NAS Finder | 2,700 | 0% | files = `self:list`, text/epub = `self:read`, music/stream = `limbs:music relay` |
| 매니저 | 2,360 | 0% | agents 목록 = `[others:agents]`, command = `[others:delegate]` |
| 검색브라우저 | 2,350 | 25% | enrich = `each + sense:crawl`, boards = `self:ledger`, history 읽기 = `sense:sqlite` |
| PC관리 탐색·분석 | 1,940 | 25% | list = `self:list`, analyze/* = `self:storage` |
| 멀티·팀채팅 | 1,830 | 0% | 없음(방 어휘 부재) |
| 폴더 창 | 870 | 0% | 없음(프로젝트·폴더 레지스트리 어휘 부재) |
| 업무기록 화면 | 260 | 전송 0% / 의미 80% | actions/{id}가 `[self:record]`와 **같은** `record_facade.execute`로 들어감 |

### 1-1 A 부류도 "조합"은 아니다 — 앱 = 액션 1개 × op 다발

33개 `app:` 블록이 참조하는 IBL 액션은 평균 1.5개, **31개는 자기 호스트 액션 하나만** 부른다(예외: 지도 7개, 메신저·라디오·커뮤니티 3개). `[fn:]` 호출은 **0건**, 저장 관용구는 전체 4건. 호스트 액션의 op 수는 `self:music` 14, `self:notebook` 13, `others:portal` 12, `others:family_news`·`showcase` 10, `self:business` 8이고, 각 패키지가 자기 SQLite(`photo_db`·`storage_db`·`notebook_core`·`finance_storage`…)를 따로 가진다.

즉 A 부류는 "일반 어휘 위의 얇은 매니페스트"가 아니라 **서비스 API를 1:1로 되비춘 전용 낱말 + 그 낱말의 뷰**다. [앱=매니페스트](APP_AS_MANIFEST_DESIGN.md)가 report-viewer에서 비판한 형태가, 이름만 `op`로 바뀌어 전수에 퍼져 있다. 자율주행이 이 op들을 조합해 쓰는가는 별도 확인이 필요하다(해마 용례 빈도). 이것은 §3의 공백과 별개의 **어휘 가꾸기(garden)** 과제다.

## 2 "IBL로 될 수 있는데 하지 않은 것" — 세 층

### 2-1 낱말이 이미 있는데 REST·코드로 다시 짠 것 (수리, 판정 불요)
- **신문** `issue()`: 키워드마다 `[sense:search]`를 React `Promise.all`로 팬아웃하고 판·아카이브·md·html을 각각 `[self:write]` — 한 발행에 IBL 호출 약 20회. 같은 레시피가 `[engines:newspaper]{wait:true}`로 이미 결정화돼 있다(`tool_newspaper.py`). HTML 조판도 서버와 중복(서버판은 마스트헤드 누락).
- **강의** `/lectures/*` 34개 중 18개가 `self:lecture`·`self:slide`·`self:material`·`self:deck`과 동등. 일괄 생성은 React `for` 루프로 `createSlide`를 순차 호출(`lecture/panels.tsx:289-330`) — `[table:each]` 자리.
- **공유창고** `neighbors/add`·`score`·`remove` → `[others:neighbor]{op:"save"|"contact_delete"}`. 커뮤니티 계기는 IBL을 쓰는데 창고 패널은 REST.
- **매니저** `agents` 목록 → `[others:agents]`; `/agents/{id}/command`(background=True 후 conversations.db 폴링) → `[others:delegate]`.
- **PC관리** `list` → `[self:list]`; `analyze/volumes|scan|summary` → `[self:storage]`(같은 `storage_db`).
- **사진** `save` → `[self:copy]`(주석이 "같은 코드"라고 명시, `api_photo.py:401-406`); `open-external` → `[limbs:os_open]`.
- **스위치** `/switches`·`/execute` → `[self:switch]{op:list|run}`.
- **주행기록·트레이스 창** `/world-pulse/episodes*`·`/trace/*` → `[self:body]{op:"trajectory", view:…}`(같은 `get_episode_journal`·`ExecutionTrace`).
- **일정 레거시** `/scheduler/calendar/events` = `[self:manage_events]{op:list}`; `calendar/view` HTML은 calendar 프리미티브로 대체된 잔재.
- **헬퍼 중복**: `YtMusicInstrument.runIBL`(원격 세션 검사·판본 언랩 누락)과 `generic/manifest.ts runIBL` — 정본은 `lib/instrument.ts iblExecuteApp`.
- **죽은 코드**: `api-business.ts` 37메서드 중 31개·`api_business.py` 45개 중 대다수, `api_gmail.py` 9개, `gen_newspaper.py`·`generate_newspaper.py`, `lib/api.ts`의 `/scheduler/tasks` 래퍼, `api_scheduler.py`의 goals·tasks 대다수, 원격 `CUSTOM_RENDERERS` 훅(등록 0).

### 2-2 기존 어휘의 조합으로 되는데 코드로 둔 것 (수리)
신문 섹션 조립 · 사진 gallery/stats/timemap(`self:photo >> table:groupby`, `sense:reverse_geocode`) · 검색브라우저 enrich(`items >> [table:each]{[sense:crawl]{metadata}}`)·boards(`self:ledger`)·history 읽기(`sense:sqlite`) · PC 분석 treemap/extensions/folders의 **데이터**(`sense:sqlite + table:groupby`; 그림은 §3-G7).

### 2-3 op 몇 개만 더하면 되는 것 (어휘 소폭, 언어 개정 아님)
강의 `duplicate`·메타 `patch`·`memo`·`outline`·design 목록 / 스위치 create·update·delete·rename·copy·position·trash / 즐겨찾기 add·remove(핸들러에 있음, 매니페스트 미노출) / calendar `update`·`toggle`·`run_now`(어휘에 있음, 뷰에 없음) / 업무기록 관리 op(validate·create·publish·migrate·export·import·pause·membership) / 채널 설정(활성·폴링 주기) / `self:recent_chats`의 에이전트 쌍 조회 / Finder reveal / 사진 해시 중복.

### 2-4 진짜 새 낱말이 필요한 것 (몸의 명사라 코드 명사로 정당, 어휘 가능)
에이전트·프로젝트·폴더·휴지통 생애주기(매니저·폴더 창) · 채팅방 CRUD·참가자·발화(멀티채팅) · 창고 피드 `poll`·`feed`·`browse`·`like`·`retweet`·레벨·휴지통(공유창고) · 미디어 probe·transcode·자막 추출(NAS). 이것들은 §3의 공백이 메워진 뒤에야 앱으로 조립된다.

## 3 핵심 — IBL(언어·런타임·표면 언어)에 없는 것

앱이 escape한 이유를 전부 모아 겹치는 순서로 세웠다. **G1·G3·G4·G5가 1급**이다 — 여럿을 한 번에 풀고, 없으면 2-1~2-4를 다 해도 앱이 다시 REST로 새어 나간다.

### G1. 긴 작업의 1급 계약 — 접수증·진행·완료·취소 (c) — 10개 앱
신문 발행(약 1분, `@hub` 30초 상한 때문에 백그라운드 + 상태 JSON 버튼), 사진 스캔(1만 4천 파일이 이벤트 루프를 막은 사고 → 스레드·진행 dict·2초 폴링, `api_photo.py:71-74`), PC 스캔(진행률 없이 블로킹), 노트북 digest/card(LLM n회), 강의 비디오(`setInterval`)·일괄 생성(5~30초 블로킹), 매니저 command(DB 폴링), 유튜브 큐(4초 폴링), 회원 앱 `/m/run`(NDJSON+heartbeat), 멀티채팅 응답.

런타임에는 조각이 **이미 있다**: `/ibl/execute`의 `ticket`(끊겨도 봉투 보존, `/ibl/recover`, step 경계 진행 기록)·`completion_channel`(취소)·`resume`/`reuse`, `[self:script]{background:true}` → job_id + `op:status`, `[others:delegate]` 접수증(`task_ref`·`status_url`), guestpc `op:result`. 그러나 (i) 접수증 모양이 액션마다 다르고, (ii) `status_url`이 HTTP 경로여서 **그걸 읽는 IBL 낱말이 없고**, (iii) 두 렌더러가 `code·project_id·surface`만 보내 ticket·취소를 **한 곳도 쓰지 않으며**, (iv) 매니페스트 mode 버튼은 성공 결과를 그리지 않아 "발행 상태" 버튼 출력이 버려진다.
→ 필요한 것: 접수증 **통화 1종**(`{task_ref, state, progress, result_ref}`), 그것을 기다리거나 읽는 **보편 낱말 1개**(새 낱말이 아니라 `self:goal`/`self:script status`/delegate 영수증의 통일이 먼저), 표면 선언 `await:`/`poll:`(진행률 막대·완료 시 재조회·취소 버튼).

### G2. 구독·푸시·타이머 (c)+(b) — 6개 앱
메신저 새 메시지(`channel_poller` 1,337줄이 상주하지만 thread는 정적 렌더), 유튜브 재생 상태·seek 진행바, 멀티채팅 스트리밍, 라디오 재생 상태, 지도 CCTV. 두 렌더러 모두 `setInterval` 0, 푸시 구독 0. 웹소켓 라우터(`api_websocket.py`)는 있다.
→ 뷰 이벤트 `tick`(주기 재조회)과 `push`(채널 구독) 2종. G1의 진행 수신과 같은 배관.

### G3. 주체(principal)와 권한 범위 (c) — 8개 앱, "정당한 REST"의 뿌리
주인 표면의 봉투에 principal이 **없다**(`agent_id="system_ai"`, `origin="user"` 기본값). 그래서 각자 우회한다: 포털 관문은 계기 템플릿 화이트리스트 일치 검사(`portal_gate.py`, "범용 /ibl/execute 직결 금지"), 회원 앱은 서버가 해소하는 **동작 ID** 전송(IBL을 감싼 것이지 별도 엔진은 아니다), `human_authority`가 무인 호출을 거절(어휘 활성화·외부사용자), `self:package`는 "사람 권한을 전달하지 않아 변경 제안만", 업무기록은 CSRF+120초 **사람 확인 토큰**, NAS는 별도 쿠키 세션, 라디오·창고는 액션이 `is_web_surface()`로 "누가 보고 있나"를 런타임 전역에서 엿본다. 매니저·모델·설정·외부사용자 창이 REST로 남은 공식 사유도 전부 이것이다.
→ 봉투에 principal(`owner_human / owner_agent / member(level) / anonymous`) + 액션 선언 `requires:`(지금 `human_required` 플래그의 일반화) + 표면 주입 변수 `$principal`. 이것이 서면 포털 화이트리스트·동작 ID·human_authority가 **한 규칙**으로 접힌다.

### G4. 매니페스트 바인딩 언어가 IBL과 충돌한다 (표면 언어 개정) — 전 앱
확인한 사실(`scripts/iblbuild_appview.py:583-590`, `backend/static/app_render_core.js:69-77`, `generic/manifest.ts:157-166`):
- 템플릿 `$key`는 **문자열 스플라이스**다. IBL 변수 `$x`를 먹어 빈 문자열로 만들고, 검증자는 input 없는 `$x`를 거절한다. 객체·배열을 넘길 수 없다(업무기록이 REST로 간 명시 사유: "객체·목록·첨부가 IBL 문자열 치환을 거치지 않는다").
- `[fn:이름]`·`[def:]`는 커밋된 정본에서 "미존재 액션"으로 **빌드가 거절**했다 → 결정화 사다리(용례→관용구→워크플로→앱)가 맨 윗단에서 끊겨 있었고, 33개 앱의 `[fn:]` 0건은 그 결과다. **2026-10-05 작업 트리에서 허용으로 바뀌었다**(`iblbuild_appview.py`, 판본 1 파서도 `[fn:]`를 실행하므로 바로 동작). 아래 두 항목은 그대로 남는다.
- 렌더러가 `edition`을 보내지 않아 앱의 모든 호출은 **판본 1(구문법)**로 실행된다(`source_edition` 기본 1). 판본 2 문법(변수·람다·블록)을 앱이 쓸 길이 없다.
- `{field}` 치환은 값의 `"`를 삭제한다(손실).
- **세 앱 계획서 §4의 `ai_dock: {action: '[fn:선택교정]{…}'}`는 지금 빌드를 통과하지 못한다.** 그 계획의 전제가 이 개정이다.
→ `/ibl/execute`의 `inputs`(이미 있음)로 입력·행·이벤트 페이로드를 **타입 보존**해 넘기고, 템플릿은 `$input.key`/`$item`을 IBL 변수로 읽는 판본 2 프로그램이 되게 한다. `[fn:]` 참조는 저장 관용구 레지스트리로 검증. 치환 정규식 3개가 사라진다.

### G5. 바이트 평면 — 미디어·파일에 통화가 없다 (c) — 전 미디어 앱
썸네일·스트림·HLS·업로드가 패키지마다 라우터다(`/music` 2, `/yt` 4, `/photo` 27 중 다수, `/nas` 30, `/showcase` 5, `/lectures` 4, `/launcher/file`). 렌더러는 `BACKEND_MEDIA_ROUTES` 화이트리스트를 손으로 관리하고("새 미디어 라우트를 낼 땐 여기 한 줄"), 500곡 preload 폭주를 휴리스틱으로 막는다. 업로드는 `/launcher/upload`가 서버 절대경로 **문자열**을 돌려주는 1파일 통로이고, 폼 필드 `images/files`는 데스크탑 네이티브 선택기라 원격에서 강등된다. 매니페스트 사진 앱조차 이미지는 REST다.
→ 통화에 **미디어 핸들 1종**(`{$blob: handle, mime, bytes, range}`)과 범용 서빙 경로 1개. 패키지는 핸들만 반환하고 라우터를 갖지 않는다. 업로드는 같은 핸들의 역방향.

### G6. 표면 상태·선택·페이지네이션 (b)+(c)
다중선택 → 일괄 액션(사진 저장, 창고 이동), 순서 바꾸기(강의 슬라이드, 재생 큐), `selection`(세 앱 계획서), 클라이언트 초안·세션 상태(신문 EditFlow의 후보 풀 교체, 빈노트 자동저장, 지도 집주소·마지막 경로, 드릴 경로·스크롤), cursor 소비(`self:record query`에 cursor가 있는데 두 렌더러는 소비 0; 멀티채팅·메신저 무한 스크롤). 데스크탑은 모드 전환 시 상태 리셋, 원격은 입력값만 localStorage — 파리티도 어긋난다.
→ 이벤트 `select`(다중)·`reorder`, 뷰 공통 `page:`(cursor 자동 소비), 표면 로컬 상태 선언(`state:` 키 — 영속은 명시 IBL 쓰기로).

### G7. 뷰 프리미티브 — 승격 4기준을 **이미 충족**하는 것만
- **트리/파인더**: 폴더 창·공유창고·PC 탐색·NAS Finder·빈노트 폴더·강의 재료 — escape **6개**가 같은 것을 손으로 그린다(기준 ① 압도적 충족). recursive 드릴은 back 스택이 없어 대체가 안 된다.
- **데이터 표**(열 정렬 grid)와 **차트**: `blocks.table`은 정적, `table:chart`는 파일 effect라 blocks image로만 우회. PC 분석(treemap·scatter·timeline)·투자가 소비자.
- **지도** `map_click`·`layers`(저장 별+검색 결과+경로+CCTV 동시): 데스크탑 지도 escape의 전부.
- **HLS 비디오 정식화**: 지금은 `stream:true` 버튼 플래그 + `StreamPlayer`가 호스트명을 하드코딩해 HLS를 판정.
- **다화자 thread + 첨부·카메라 입력창**(멀티채팅·팀채팅·빈노트 AI 패널).
- 진행률 막대·스트리밍 텍스트(G1·G2의 표현).
정당한 escape로 남는 것: 슬라이드 캔버스·오버레이 좌표 편집(세 앱 계획의 `engine` 뷰로 흡수 가능)·녹음 스튜디오·창 간 네이티브 드래그·webview.

### G8. "도구를 쓰는 동기 AI 1턴" (a)+(c) — 4개 앱
빈노트 `/system-ai/chat`, 검색브라우저 `/forage/chat`(`force_role="forage"`, `allowed_set=sense+self+table`, 사냥판 스냅샷 주입), 강의 `slide_ai.py`(`get_provider` 직접 호출+자체 캐시), 문서 `generate_selection`. `[self:ask]`(도구 없음)·`[table:ai]`(행 변환)·`[others:delegate]{mode:sync}`(프로젝트 에이전트) 사이의 구멍: **역할·허용 어휘·구조화 맥락을 지정한 동기 에이전트 턴**. `delegate{scope:"system", mode:"sync", role, allowed, context}` 확장이면 새 낱말 없이 닫힐 가능성이 크다. 그러면 앱 안의 AI 수정이 전부 인지 파이프라인(회상·평가·증류)을 지난다 — 세 앱 계획서 §3-b와 같은 결론.

### G9. 표면 지시 채널 (c)
`play_in_client`·`stop_in_client`·`download_in_client`·`pc_only`·`stream:true`·`[MAP:]`·`[STREAM:]` 텍스트 태그를 렌더러 3곳(`GenericInstrument`·`launcher_web_render`·`portal_gate`)이 각자 덕타이핑한다. "결과를 어디서 어떻게 재생·저장하라"는 지시가 통화 봉투의 정식 필드가 아니다.
→ 봉투 `surface:{play|open|download|share}` 1필드로 정식화.

## 4 판정 요청 (언어 개정·파괴적 변경만)

1. **G4** 표면 템플릿 → `inputs` 통로 + 판본 2 + `[fn:]` 허용 (표면 언어 개정). 세 앱 계획서의 선행 조건.
2. **G3** 봉투 principal + 액션 `requires:` + `$principal` (언어 개정). 포털 화이트리스트·동작 ID·human_authority 흡수.
3. **G1+G2** 접수증 통화 통일 + 표면 `await/poll/push` 선언 + 이벤트 `tick`/`push` (통화·뷰 어휘 개정).
4. **G5** 미디어 핸들 통화 + 범용 서빙 경로, 패키지 라우터 은퇴 (통화 개정 + 파괴적).
5. **G7** 뷰 낱말: `tree`, `grid`(표), `chart`, map `map_click`·`layers`, `video`(HLS), 이벤트 `select`·`reorder` (뷰 어휘 개정). 각각 은퇴시킬 escape를 §3-G7이 지정한다.
6. **G8** `delegate{scope:system, mode:sync, role, allowed}` 확장으로 앱 속 원샷 AI 호출 4곳 은퇴 (파괴적).
7. §2-1의 죽은 REST·중복 헬퍼 삭제 (파괴적, 소비자 0 확인된 것만).

§2-1~2-3은 수리 범주라 판정 없이 집행할 수 있다. 다만 **순서가 중요하다**: G4 없이 2-1을 하면 앱은 여전히 판본 1 문자열 치환 위에 서고, 관용구를 못 부른다.

## 5 세 앱 계획서에 대한 보정

- 같은 날 작업 트리에서 계획서 §6-1~3이 집행됐다: `[self:workspace]` 12 op + `workspace_sessions.py`, 뷰 `engine`, 이벤트 `selection`/`saved`, keep 규약, `[fn:]` 템플릿 허용, 관용구 6건 시딩. 이 문서의 G4 중 "`[fn:]` 거절"은 그로써 닫혔고, `$` 스플라이스·타입 없는 값·판본 미명시는 남아 있다. 두 출처를 합친 설치 목록은 [앱 공통 기반 — 설치가 필요한 것](APP_COMMON_FOUNDATION_GAPS_2026_10_05.md)이 정본이다.
- 계획서의 추가안은 강의 앱에도 그대로 맞는다(덱=자료, slide_id=selector, `versions/restore`가 지금 없는 되돌리기를 준다). 매니저·스위치·조종실에는 무관하다.
- 계획서가 다루지 않은 것: G1(진행·푸시), G3(principal), G5(바이트), G6의 cursor·reorder, G7의 트리.

## 6 위험과 미측정

- 비율·줄 수는 호출 지점 수와 `wc -l` 기준의 대략치다. 회원 프레임 CSP가 map·media_player를 막는다는 추정은 실측하지 않았다.
- "죽은 코드"는 저장소 내 호출처 검색 결과다. 폰 컴패니언·외부 Worker가 부르는 경로(`/business/sync`, 쇼케이스 공개 라우터)는 살아 있다고 분류했다.
- 이 문서는 무엇이 빠졌는지를 말한다. 각 공백의 설계(통화 모양·이벤트 이름)는 판정 뒤 별도 설계 문서의 몫이다.
