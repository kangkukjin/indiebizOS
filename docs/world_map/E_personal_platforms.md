# E. 개인 생활·사무·플랫폼 연결 (조사 2026-09-06)

## 요약 (가장 강력한 5개와 이유)
1. **Google Workspace API(Sheets·Drive·Docs·Calendar)** — 개인 지식노동자 문서·표·일정의 사실상 세계 표준. Gmail 은 어휘에 있으나 Sheets/Drive/Calendar 는 없다. OAuth 데스크톱 앱을 개인 계정으로 만들면 심사 없이 쓴다(테스트 모드). 2026-05 이후 새 프로젝트는 쿼터 초과분 과금 예고 — 개인 사용량은 무료.
2. **카카오톡 메시지 "나에게 보내기"** — 한국 개인용 푸시의 표준. 검수·비즈앱 없이 `talk_message` 동의만으로 내 폰 카톡에 도달. 현재 알림 어휘(`self:notify_user`=데스크톱, `limbs:phone`=USB)는 인터넷 너머 폰에 못 닿는다 — 이 구멍을 메운다.
3. **Telegram Bot API** — 세계 개인 알림봇 표준(BotFather 토큰, 심사·과금 0, Bot API 10.2 2026-07). 워크스페이스의 텔레그램 MCP 는 있으나 IBL 어휘 밖.
4. **Notion API** — 노트·DB 도구의 표준. 내부 통합 토큰, 무료 플랜 가능, 3 req/s. 2025-09 데이터소스 개정으로 호출 형태가 바뀌었다(버전 헤더 고정 필수).
5. **Kiwi(kiwipiepy)** — 한국어 형태소 분석의 현 표준(Java 불요, 순수 pip, 2026-02 벤치 활발). 블로그·자막·검색 파이프의 `table:` 변환자 후보.
- 경보: **AnkiConnect 기본 포트가 8765** — indiebizOS 백엔드 포트와 동일. Anki 어휘화 시 포트 충돌을 먼저 처리해야 한다.

## 표
| 등급 | 리소스 | 한 줄(무엇을 주나) | 통로(API/규격/pip + 인증·개인 키 가능?) | 무료 범위 | 왜 표준인가 | 어휘 후보 형태 | 근거 URL | 확인일 |
|---|---|---|---|---|---|---|---|---|
| S | Google Sheets / Drive / Docs API | 내 구글 드라이브 파일 목록·읽기·쓰기, 시트 행 읽기/추가 | REST + `google-api-python-client`. Google Cloud 프로젝트 무료 생성 → OAuth 데스크톱 클라이언트. 개인 계정 "테스트 모드" 100명까지 심사 불요(미검증 경고만). 개인 키 O | Sheets 300 read/300 write per min/project, 60/user/min. 표준 사용 무료, 초과분 과금 "later in 2026" 예고 | 개인 문서·표·공유의 세계 표준 | `self:gdrive`{op:list/read/write}, `self:sheet`{source:"google"} 확장 | https://developers.google.com/workspace/sheets/api/limits | 2026-09-06 |
| S | Google Calendar API | 구글 캘린더 이벤트 조회·생성·갱신 | 위와 같은 OAuth. 개인 키 O | 2026-05-01 이후 새 프로젝트 10,000 req/min/project, 600/min/user, 일 100만 과금 임계 | 캘린더 상호운용의 표준(iCal 규격 포함) | `self:manage_events`{source:"google"} 동기화 축 | https://cli.nylas.com/guides/google-calendar-api-quotas | 2026-09-06 |
| S | Notion API | 페이지·데이터베이스(데이터소스) 읽기·쓰기·검색 | REST, 내부 통합 토큰(워크스페이스 소유자가 발급, 페이지별 공유 필요). 무료 플랜 O, 개인 키 O | 무료(과금 없음), 3 req/s/통합. 2026-02 버전부터 페이지네이션 기본 50 | 개인 노트·DB 도구 표준. 2025-09-03 버전부터 database→data_source 2층 구조 | `self:notion`{op:query/page/append} | https://www.notion.com/help/create-integrations-with-the-notion-api | 2026-09-06 |
| A | Microsoft Graph | Outlook 메일·일정·연락처, OneDrive, To Do, Teams | REST + `msgraph-sdk`. Entra 앱 등록 무료, `/common` 엔드포인트로 개인 MSA 지원. 개인 계정은 **위임 권한만**(앱 권한 불가). 개인 키 O | 호출 자체 무료(데이터는 계정 라이선스 범위) | M365 생태계 단일 API. 한국 직장인 환경의 표준 | `self:m365`{op:mail/calendar/drive/todo} | https://learn.microsoft.com/en-us/answers/questions/675231/microsoft-graph-api-for-personal-accounts | 2026-09-06 |
| A | Apple Shortcuts CLI + EventKit | 맥의 캘린더·미리알림·연락처·메모를 로컬에서 읽고 쓰기 | macOS 내장 `shortcuts run <이름>` / `shortcuts list`; EventKit 직접 접근은 `ekctl`(오픈소스 Swift CLI). 키 불요(OS 권한 다이얼로그) | 무료·로컬 | 애플 생태계 자동화의 유일한 공식 CLI | `limbs:shortcut`{name}, `self:manage_events`{source:"apple"} | https://support.apple.com/guide/shortcuts-mac/run-shortcuts-from-the-command-line-apd455c82f02/mac | 2026-09-06 |
| A | iCloud CalDAV / CardDAV | 아이클라우드 캘린더·연락처를 표준 프로토콜로 | `caldav.icloud.com` / `contacts.icloud.com`, Apple 계정 + **앱 전용 비밀번호**(2FA 필수). pip `caldav`. 개인 O | 무료 | 애플 일정·주소록의 외부 접근 규격(OAuth 없음) | `self:manage_events`{source:"icloud"} | https://support.apple.com/en-us/102654 | 2026-09-06 |
| A | Todoist API v1 | 할 일·프로젝트·라벨·리마인더 CRUD | REST(통합 v1, 2025-04) + `todoist-api-python`. 설정에서 개인 API 토큰 즉시 발급. 무료 계정 O | 무료(플랜별 기능 제한, 요청 한도 있음). 구 REST v2/Sync v9 2026 초 폐기 | 개인 할 일 앱의 API 표준(Things 는 URL 스킴·로컬 SQLite 만, 공식 서버 API 없음) | `self:todo`{op:list/add/close} | https://developer.todoist.com/api/v1/ | 2026-09-06 |
| B | Slack Web API | 채널 메시지 읽기·보내기 | Bot 토큰(내 워크스페이스 앱 = 심사 불요). 개인 O | 무료 플랜: 앱 10개, 90일 이력. 비마켓플레이스 상용 앱은 `conversations.history` 15건/요청·1회/분(2025-05~2026-03 단계 적용, 내부 앱 제외) | 팀 채팅 표준이나 1인 지식노동자에겐 부차적 | `others:channel_send`{channel:"slack"} | https://api.slack.com/changelog/2025-05-terms-rate-limit-update-and-faq | 2026-09-06 |
| A | DeepL API | 고품질 기계번역(한↔영·일·중 등) | REST + pip `deepl`. 개인 키 O(카드 등록 필요). **주의**: API Free(월 50만자)는 2026-07 신규 판매 종료 보도 — 신규는 Developer(총 100만자 1회성)·Growth($26/월+종량) | 기존 Free 키 보유자는 유지. 신규는 1회성 100만자 | 전문 번역가·저술가가 쓰는 번역 API 표준 | `engines:translate`{engine:"deepl"} | https://www.eesel.ai/blog/deepl-pricing | 2026-09-06 |
| A | LibreTranslate / Argos Translate | 로컬·오프라인 번역 서버(한국어 포함) | pip `libretranslate`(서버) 또는 `argostranslate`(라이브러리). 키 불요 | 완전 무료(오픈소스, 2026-05-26 릴리스) | 자가 호스팅 번역의 사실상 표준(14.2k★) | `engines:translate`{engine:"local"} | https://github.com/LibreTranslate/LibreTranslate | 2026-09-06 |
| S | Kiwi (kiwipiepy) | 한국어 형태소 분석·품사 태깅·문장 분리·키워드 추출 | pip `kiwipiepy`(C++ 내장, Java 불요). 키 불요 | 무료·로컬 | KoNLPy(Java 의존)·Mecab-ko(설치 난이도)를 대체한 현 표준, 활발 유지 | `table:morph`{op:tokenize/nouns/split} | https://github.com/bab2min/kiwi | 2026-09-06 |
| S | Podcast Index API | 팟캐스트 검색·피드·에피소드 메타(개방 색인) | REST, 무료 개발자 키/시크릿(즉시). User-Agent 필수. 개인 O | 무료 | Apple 팟캐스트 디렉터리의 개방형 대체, Podcasting 2.0 표준 색인 | `sense:podcast`{op:search/episodes} → `sense:feed` 로 이어짐 | https://api.podcastindex.org/developer_docs | 2026-09-06 |
| A | Last.fm API | 청취 기록(스크로블)·아티스트/트랙 메타·추천 | REST, API 키 즉시 발급(쓰기는 secret+세션). 개인 O | 무료 | 20년 된 청취 기록 표준 | `self:music`{op:scrobble} 확장 또는 `sense:music_meta` | https://publicapis.io/last-fm-api | 2026-09-06 |
| B | ListenBrainz API | 개방형 청취 기록·통계(MetaBrainz) | REST + pip `liblistenbrainz`, 설정 페이지 사용자 토큰. 개인 O | 무료·오픈 | Last.fm 의 개방 대체(데이터 소유권) | `self:music`{op:scrobble, target:"listenbrainz"} | https://listenbrainz.readthedocs.io/en/latest/users/api/core.html | 2026-09-06 |
| S | TMDB API | 영화·TV·인물 메타·포스터·평점 | REST v3, 무료 계정 → 설정에서 키 즉시 발급. 비상업 무료(출처 표기). 개인 O | 무료, 경성 한도 제거(약 50 req/s 연성) | 스트리밍 앱·미디어 서버(Plex·Jellyfin·Kometa)가 다 쓰는 영화 메타 표준 | `sense:movie`{op:search/detail} | https://developer.themoviedb.org/docs/faq | 2026-09-06 |
| B | OMDb API | IMDb 평점 포함 영화 메타 | REST, 이메일로 무료 키. 개인 O | 1,000건/일(포스터는 Patreon) | TMDB 다음 대체, IMDb 평점이 필요할 때 | `sense:movie`{source:"omdb"} | https://www.omdbapi.com/apikey.aspx | 2026-09-06 |
| S | Open Food Facts API | 바코드→식품 영양성분·성분·Nutri-Score | REST v2 `/api/v2/product/{barcode}`, 키 불요(User-Agent 권장). 개인 O | 완전 무료·오픈 데이터 | 세계 최대 크라우드 식품 DB, 영양 앱 표준. 한국 제품 커버리지는 낮음 | `sense:food`{barcode} | https://openfoodfacts.github.io/openfoodfacts-server/api/ | 2026-09-06 |
| A | USDA FoodData Central API | 식재료·일반 식품 영양성분(정부 표준) | REST, api.data.gov 무료 키(DEMO_KEY 로 시험). 개인 O | 무료·유료 없음 | 영양 데이터의 학술·정부 기준 | `sense:food`{source:"usda"} | https://calorieapi.com/blog/usda-fooddata-central-api-guide | 2026-09-06 |
| B | Nutritionix API | 브랜드·외식 체인 메뉴 영양(80만 품목) | REST, 무료 개발자 플랜. 상용은 유료(엔터프라이즈 $1,850/월~) | 개발자 무료 플랜(소량) | 외식 메뉴 영양의 표준이나 미국 중심 | `sense:food`{source:"nutritionix"} | https://www.spikeapi.com/blog/top-nutrition-apis-for-developers-2026 | 2026-09-06 |
| A | Apple Health 내보내기 규격 | 건강앱 전체 기록(걸음·심박·수면·체중…) | 건강앱 → 내보내기 = `export.zip/apple_health_export/export.xml`(단일 XML). 자동화는 Health Auto Export 앱(JSON/CSV → iCloud/REST). 키 불요 | 무료(자동화 앱은 일부 유료) | 애플 건강 데이터의 유일한 공식 반출 규격 | `self:health`{op:import, format:"apple_xml"} | https://applehealthdata.com/ | 2026-09-06 |
| B | Garmin Connect (비공식) | 가민 시계 활동·심박·수면·HRV·체성분 | pip `garminconnect`(v0.3.5, 2026-06-04 — 2026-03 가민 인증 변경 후 모바일 SSO 방식으로 복구, MFA 콜백). 계정 로그인, 키 불요. 공식 Health API 는 사업자 전용 | 무료 | 가민 사용자의 사실상 유일한 개인 통로(비공식 = 깨질 수 있음) | `self:health`{op:import, source:"garmin"} | https://github.com/cyberjunky/python-garminconnect | 2026-09-06 |
| S | 카카오톡 메시지 API — 나에게 보내기 | 내 카톡 "나와의 채팅"에 텍스트/링크/리스트 템플릿 발송 | REST `/v2/api/talk/memo/default/send`, 카카오 로그인 + `talk_message` 동의. **검수·비즈앱 불요**. 개인 O. 친구 발송은 별도 권한 신청 + 일/월 쿼터·5명/회 | 무료 | 한국 개인 푸시의 표준(폰에 카톡 없는 사람 없음) | `others:channel_send`{channel:"kakao_me"} | http://developers.kakao.com/docs/ko/kakaotalk-message/rest-api | 2026-09-06 |
| A | 네이버 데이터랩 검색어 트렌드 API | 키워드(5그룹×20어) 상대 검색량 추이, 기기·성별·연령 분해 | REST, developers.naver.com 앱 등록(개인 O, 기존 `sense:search` naver 키와 동일 콘솔). 일 호출 한도 있음 | 무료 | 한국 검색 수요 측정의 유일한 공식 소스(구글 트렌드의 한국판) | `sense:trend`{keywords} | https://wooiljeong.github.io/python/naver_datalab_open_api/ | 2026-09-06 |
| A | 스마트택배(스윗트래커) API | 택배사 코드+송장 → 배송 단계·위치·시각 | REST, 회원가입 후 키 발급(개인 O). 조회 API(요청 시)/추적 API(푸시) | 무료 티어 있음(일 한도 수치 미확인 — 사이트 본문 차단) | 국내 택배 조회 앱·쇼핑몰이 쓰는 사실상 표준 | `sense:parcel`{carrier, invoice} | https://tracking.sweettracker.co.kr/ | 2026-09-06 |
| B | Delivery Tracker (tracker.delivery) | 국내외 택배 조회(오픈소스, GraphQL) | GraphQL API, 클라이언트 키 발급. 개인 O | 무료(오픈소스, 자가 호스팅 가능) | 개발자 커뮤니티의 개방 대체 | `sense:parcel`{source:"tracker.delivery"} | https://tracker.delivery/en/ | 2026-09-06 |
| S | Anki — AnkiConnect + .apkg | 플래시카드 덱·노트 생성·조회·복습 통계 | AnkiConnect 애드온 = Anki 실행 중 `localhost:8765` JSON-RPC(★indiebizOS 백엔드와 포트 충돌 — 애드온 설정으로 변경 필요). 파일 규격 `.apkg` 는 pip `genanki` 로 생성. 키 불요(apiKey 선택) | 무료·로컬 | 간격반복 학습의 압도적 표준 | `engines:flashcard`{op:add/sync} (Anki 없이 .apkg 생성) + `self:anki`{op:stats} | https://git.sr.ht/~foosoft/anki-connect | 2026-09-06 |
| S | Telegram Bot API | 봇으로 내 텔레그램에 메시지·파일·버튼 발송, 수신 폴링 | HTTPS `api.telegram.org/bot<token>`, BotFather 발급 토큰. 심사·과금 0, 봇 수 제한 없음. 개인 O. Bot API 10.2(2026-07) | 무료 | 자가 호스터·개인 알림봇의 세계 표준 | `others:channel_send`{channel:"telegram"} + `others:channel_read` | https://core.telegram.org/bots/api | 2026-09-06 |
| B | ntfy.sh | HTTP PUT 한 줄로 폰·데스크톱 푸시(토픽 구독) | REST(POST 텍스트), 키 불요(공개 토픽) / 자가 호스팅. 개인 O | 공개 서버 250건/일, 자가 호스팅 무제한 | Pushover(유료)의 오픈 대체, 셀프호스팅 표준 | `self:notify_user`{channel:"ntfy"} | https://ntfy.sh/ | 2026-09-06 |
| A | Home Assistant REST/WebSocket API | 스마트홈 기기 상태·서비스 호출 | `Authorization: Bearer <장기 토큰>`(프로필에서 발급), pip `homeassistant-api`. 개인 O | 무료·오픈소스 | 스마트홈 허브의 사실상 표준(SmartThings 는 유료화 — 아래) | `limbs:home`{op:state/call} | https://developers.home-assistant.io/docs/api/rest/ | 2026-09-06 |

(표 29행 — S 9 · A 13 · B 7)

## 겹침 메모 (기존 어휘와 겹쳐 뺀 것)
- **Gmail API** — `others:channel_send/read`(Gmail) 와 겹침. 차이=없음(이미 어휘).
- **YouTube Data API** — `sense:video`·`sense:search_youtube` 와 겹침. 차이=공식 API 는 일 10,000 유닛 쿼터·OAuth 로 내 구독/재생목록 쓰기 가능(현재 어휘는 읽기 중심). 필요 시 `sense:video`{op:subscriptions} 확장 정도.
- **카카오 로컬·내비·역지오코딩** — `sense:place`·`sense:navigate_route`·`sense:reverse_geocode` 와 겹침. 카카오 모빌리티(택시 호출)는 사업자 전용이라 제외.
- **네이버 검색·지역 API** — `sense:search`{source:naver}·`sense:restaurant` 와 겹침. 네이버 지도 지오코딩(NCP)은 카카오 역지오코딩과 기능 중복.
- **CoinGecko** — `sense:crypto` 와 겹침. 차이=없음.
- **Alpha Vantage(25건/일)·Polygon.io(5건/분, EOD·15분 지연)** — `sense:stock` 과 겹침. 차이=미국 주식 히스토리 깊이·외환·기술지표. 시세 어휘의 source 옵션으로 흡수 가능.
- **OpenBB Platform** — `sense:stock`·`sense:company`·`sense:world` 와 부분 겹침. 차이=2026-08-25 전 제품군 오픈소스화, pip `openbb` 가 100+ 프로바이더를 단일 시그니처로 묶음(스크리닝·거시·옵션). 시세 어휘를 재구축할 때 기질 후보(어휘 아님).
- **한국은행 ECOS** — `sense:world`(경제 스냅샷)·`sense:kosis` 와 겹침 가능. 다른 조사원 담당 — 개인 인증키 즉시 발급, 일 한도 있음, 한 줄만.
- **Open-Meteo/기상청** — `sense:weather` 와 겹침.
- **Google Books** — `sense:book`{source:"google"} 에 이미 있음.
- **Wikidata** — `sense:entity` 에 있음.
- **Apple Health/Garmin 결과 저장처** — `self:health` 원장이 이미 있으므로 위 표의 건강 항목은 "가져오기(import) 축"만 새 어휘.

## 죽었거나 유료화·개인 불가인 것 ("쓰지 말 것")
- **Papago 번역 API** — 네이버 개발자센터 무료 제공 2024-02-29 종료 → AI NAVER API 콘솔 2025-03-20 종료. 현재 NCP AI Services "Papago Translation" 만(글자수 종량, 100만자 단위 올림). 개인 NCP 가입은 가능하나 무료 아님. 한국어 번역은 DeepL/로컬 LibreTranslate 또는 `self:ask`(경량 모델)로.
- **Spotify Web API** — 2026-02-11 개발 모드 개정: Premium 계정 필수, 클라이언트당 사용자 5명, 검색 결과 10건, browse·인기도·타인 플레이리스트 등 엔드포인트 제거(기존 통합은 2026-03-09 연기). 확장 쿼터는 법인+MAU 25만 필요. 개인은 Premium 보유 시 "내 데이터 읽기" 정도만. 청취 기록은 Last.fm/ListenBrainz 로 우회.
- **Strava API** — 2026-06-01부터 Standard 티어도 Strava 구독($11.99/월) 필수. 정책상 API 데이터를 AI 앱의 "컨텍스트 윈도우 주입·RAG" 에 쓰는 것 자체를 금지, 타사 MCP 운영 금지(공식 MCP 커넥터만). AI 운영체제인 indiebizOS 에 넣을 수 없다. 대안=Garmin 비공식/Apple Health 내보내기.
- **Trakt API** — 2026-08 보고: API 앱 생성에 VIP 구독 필요, 무료 계정은 연결 앱 1개·리스트 5개(250건). 시청 기록은 로컬 원장(`self:ledger`)+TMDB 로.
- **Goodreads API** — 2020-12 신규 키 발급 중단 이후 부활 없음(2026 대체 서비스 목록에 Goodreads API 언급 없음). 대체: Hardcover(GraphQL API), StoryGraph(API 없음, CSV 내보내기). 도서 메타는 `sense:book` 으로 충분.
- **Pocket** — 2025-07-08 서비스 종료, API 2025-11-12 폐쇄. 나중에 읽기는 Raindrop.io(무료 API — 미검증)·Instapaper 로.
- **Google Photos Library API** — 2025-03-31부터 앱이 올린 콘텐츠만 접근, 전체 라이브러리는 Picker API(사용자가 매번 고름). 로컬 `self:photo` 가 답.
- **Google Fit REST API** — 2024-05 신규 등록 중단, 2026 말 종료. 안드로이드는 Health Connect(온디바이스 앱 권한, 서버 API 없음). 폰(A36) 건강 데이터는 Health Connect 읽는 안드로이드 앱을 폰 몸에 두는 방식만 가능.
- **X(Twitter) API** — 2026-02-06 무료 티어 폐지, 신규는 종량제(읽기 $0.005/포스트) 기본. Basic $200 도 2026-06 강제 이전.
- **Samsung SmartThings API** — PAT 24시간 만료(2024-12-30 이후), 2026-10부터 API 접근 유료(Personal Plan $4.99/월). Home Assistant 로 우회.
- **오픈뱅킹·마이데이터** — 개인 개발자는 금융결제원 테스트베드(가상 데이터)만. 실계좌는 이용기관 등록(법인·심사) 필요. 현재 몸의 방식(폰 결제 알림 포획 → `self:finance`)이 개인의 현실적 최선.
- **국세청 홈택스** — 개인용 공식 오픈 API 없음. 팝빌·CODEF·하이픈의 "홈택스 수집 API" 는 스크래핑 기반·사업자 계약·유료. 현금영수증 조회는 `limbs:browser` 자동화가 유일.
- **쿠팡 Open API** — 판매자(입점) 전용. **쿠팡 파트너스 API** 는 제휴 승인 후 개인 가능하나 광고 링크 생성용(가격·상품 조회는 `sense:search_shopping` 다나와로 충분). **네이버 커머스 API** — 커머스솔루션마켓 등록 또는 API 대행사만.
- **배달 플랫폼(배민·요기요·쿠팡이츠)** — 개인용 공개 API 없음.
- **Khan Academy / Coursera** — 개인 개발자용 공개 API 없음(Khan API 2020 폐쇄, Coursera 는 기업 파트너 API 만). 학습 기록은 로컬 원장으로.
- **Google Keep** — 소비자 계정용 API 없음(Workspace 엔터프라이즈 전용, 기억 기반 미재검증).
- **Slack 비마켓플레이스 상용 앱** — 위 표 참고(내부 앱은 예외라 개인 워크스페이스 봇은 살아 있음).
