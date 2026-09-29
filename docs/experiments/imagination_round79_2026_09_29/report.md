# 상상 훈련 79회차 결과보고서 (2026-09-29) — 가족 나들이·생활 조회

훈련 턴 · **무수정**(가이드 §4-3). 아래 갭 원장의 근거는 셋이다.
- [before.json](before.json)·[baseline.json](baseline.json)
- 셸로 읽은 패키지 코드(`location-services`·`culture`·`shopping-assistant`)
- 원천 원응답 대조(당근 셸 curl 3회, 카카오 길찾기 코드 경로 2회 — `.env`를 불러온 독립 프로세스에서 핸들러 함수 직접 호출)

집행 완료 절은 비워 두었다.

★**사용자 위치**:
- `sense:here`의 결과(선언 위치)는 before.json에 모양(shape)만 남겼다. 이 보고서에도 좌표·주소를 싣지 않았다. 실은 것은 `source:"declared"`·`accuracy_m`·건수뿐이다.
- 좌표를 쓴 문장에는 공공 시설(오송역·청주시립미술관·국립현대미술관 청주 등)의 좌표만 썼다.
- 저장 후 선언 위치 값으로 before.json을 대조했다. 싣지 않았음을 확인했다.

## 축 선정

- **축**: 행동 기준 미조합 메뉴의 위치·생활 어휘다. 모두 선언과 describe로 op·인자·반환을 확인했다.
  - 날씨·문화: `sense:weather`·`performance`·`exhibit`
  - 위치: `sense:place`·`restaurant`·`navigate_route`(자동차·대중교통)·`reverse_geocode`·`here`, `limbs:show_map`
  - 소비: `sense:stay`·`search_shopping`·`used`·`contest`
  - 13액션 모두 교재 코퍼스에는 조합이 있다. 행동에서는 한 번도 조합된 적이 없다("가르쳤으나 안 씀").
- **도메인**: 사용자 생활권 청주·오송·세종에서 이번 주말(2026-10-03 토·10-04 일) 가족 나들이를 준비한다.
  - 맑은 날 고르기 → 비 오면 실내 대안(`[if]`)
  - 근처 공연·전시 → 주변 맛집(후기·거리) → 후보 여러 곳을 이동 시간으로 정렬(자동차·대중교통)
  - 숙소 1박·2박 가격
  - 아이 선물의 새것 최저가와 중고 시세
  - 지금 위치 근처 약국, 좌표↔주소 왕복
  - 원천 0건, 지도 표시, 나들이 계획표 축적
- **축 선정 관문 질문**("기계로 열거 가능한가")
  - 원천의 기본값·후필터·드리프트가 사용자 질문의 뜻을 어떻게 바꾸는지는 실제로 불러 봐야 드러난다. 그래서 훈련 축이다.
  - 발견 중 둘은 열거 가능하므로 census로 넘긴다.
    - B79-3: 파싱 실패를 빈 성공으로 받는 생산자
    - B79-6: 필터·선택을 원천 절단으로 적는 `bounded_selection` 생산자
- **닫힌 밭**: 값 표기 격자·날짜 표기·절단 표지 누락은 다시 갈지 않았다. 숫자 문자열 `"619"`의 정렬은 값 의미론대로 숫자순이었다.
  - 침묵 클램프 관문 어휘 밖의 자리(weather `days`·place `radius`)는 새 항목이 아니라 **관문 누출 증거**로 재확인에만 적었다.
- **탐침**: `agent_id:"IT79_probe"`·`task_id:"IT79_task"`. 모든 요청이 `edition:2`·`project_id:"컨텐츠"`·`origin:"training"`이다. t24만 판본 1 대조라 `edition:1`이다.
- **쓰기**: `projects/컨텐츠/outputs/IT79_나들이.json` 한 개만 썼다(t21). 끝에 삭제했다. 저장한 장소 원장(`projects/앱모드/outputs/map/places.json`)은 건드리지 않았다(해시 불변).

## 지표 스냅샷 (훈련 전)

- 행동 미조합 140/168 · 파이프 길이 중앙값 3 · 문형 4(조회 26·축적 8·적용 6·조건 2) · 파트너 다양성 중앙값 2
- 78회차와 같다. 원본은 [metrics.json](metrics.json)이다.
- 지표는 몸의 현황이며, 훈련 실측은 증류에 담기지 않는다(§6).

## 과제 표

원문·판정식: [probe.py](probe.py) · 응답(위치 마스킹): [before.json](before.json) · 기준선과 회차 후 diff: [baseline.json](baseline.json).

**24과제 중 기계 판정 9통과 · 15실패.** 결함 8부류 · 마찰 3부류 · 어휘 후보 1. 실행 21 · check만 2(t22 코퍼스 273용례·t23 부작용 판정) · 판본 1 대조 1(t24).

탐색 중 훈련자 문장 잘못은 결함 판정에서 뺐다. 거절 안내가 모두 위치를 정확히 짚었다.
- 순수 식 자리의 파이프: `unique($x >> each)`·`any(...)`·`sorted(...)`, 슬라이스한 파이프 식, 내장 함수 인자 안의 `??`
- `table:join{with:…}`: UNKNOWN_ARGUMENT, 사용 가능 인자 목록이 함께 왔다
- 예약 바인딩 `$i`: READONLY
- `table:union` 결과(Record)에 `.items` 누락: TYPE
- `round(x, 0)`을 인덱스로 사용: F79-3

| # | 상상 의도 | 결과 | 분류 |
| --- | --- | --- | --- |
| T01 | 주말 청주 날씨 → 비 없는 날 → 실내(전시)/야외(관광명소) 분기 | 토 흐림 0mm·일 이슬비 0.8mm → 야외·토요일·관광명소 3곳 | 깨끗 |
| T02 | 같은 주말 날씨를 도시명 vs 청주시청 좌표로 | 최고기온 차 최대 0.9도. `resolved`가 해소 이름을 정직하게 싣는다("청주"→청주역 부근 흥덕구) | 깨끗 |
| T03 | 이번 주말 충북 공연(날짜 범위) | 기본 4건 vs `status:"공연예정"` 5건 — 주말에 열리는 9건 중 **5건 누락**(어린이 벌룬쇼 포함) | 결함 B79-1 |
| T04 | "청주 공연" — region에 시 이름 | 충북 4 vs 청주 **0**("총 0개" success), 장르 "어린이극" 0, check 경고 0 | 결함 B79-2 |
| T05 | 주말 공연 ∪ 전시 → dedup(title) | 13행에 같은 공연 "무명의 용병사"가 두 번 남음(KOPIS·KCISA 표기 차이) | 마찰 F79-1 |
| T06 | 주말 전시·공연(전시 원천)을 지도에 | 5행 **전부 원천 좌표 보유** → 마커 3·탈락 2(이름 지오코딩 실패) | 결함 B79-7 |
| T07 | 미술관 반경 700m 돈까스, 가까운 순 | 14행 중 **5행이 전국 네이버 결과**(대전·경기·여수·춘천·광주, distance null) | 결함 B79-5 |
| T08 | 미술관 근처 후기 많은 맛집 표 | select `MISSING_FIELD` `details:{}`(어느 열인지 없음). 우회 시 15행 중 6행 blog_count null, 네이버 5행 전부 타 시도 | 결함 B79-5 · F72-2 재확인 |
| T09 | 오송역에서 후보 3곳 자동차 소요시간 정렬 + 직선거리 근사 대조 | 수목원 20분·시립미술관 23분·국현 28분, 도로/직선 1.23·1.14·1.47, 해소 이름 일치 | 깨끗 |
| T10 | 대중교통 vs 자동차, 청주→세종 대중교통 | 10경로, 최단 39분 2,050원 vs 자동차 23분. 시 경계 경로 `complete:true` 86분 | 깨끗 |
| T11 | 세종 호텔 1박 vs 2박 가격, "1박 10만원 이하" | 2박 price = 두 1박의 **합계**(80,000+70,000=150,000). `max_price:100000` 2박 → 0건 + `PARTIAL_SOURCE` 실패 | 결함 B79-6 |
| T12 | 세종 가족 호텔 — 세종 밖 숙소가 섞이나 | 7행 중 춘천·서울 중구 호텔 2. 주소는 meta 문자열뿐 | 꼬임(F77-1 재확인) |
| T13 | 스위치 2 새것 최저가 vs 중고 본체 중앙값 | 727,600 vs 730,000(미개봉 매물 포함), 본체 9행 | 깨끗 |
| T14 | 청주에서 파는 스위치 2 중고(번개장터) | `region:"청주"` → `total:0`. 지역 없이 받으면 15행 중 위치 표기 4행 | 결함 B79-4 |
| T15 | 우리 동네(오송읍) 당근 매물 | 스위치·자전거 둘 다 0, success. note "결과 없음 또는 페이지 구조 변경". 셸 대조로 원천 구조 변경 확인 | 결함 B79-3 |
| T16 | 지금 위치 근처 약국 5곳(마스킹) | 5곳 거리순. `source:declared`·`accuracy_m:3000`인데 반경 1000m — 정밀도 경고 없음(조합자 몫) | 깨끗 |
| T17 | 좌표 → 주소 → 다시 장소(공공 시설 좌표) | 역지오코딩은 행정동 수준만 → 되찾은 곳이 다른 장소(96m 떨어진 시설) | 꼬임(V79-1) |
| T18 | 없는 말로 10원천 두드리기 | place·restaurant·exhibit·performance·stay·shopping·used·contest는 성공 0건(정직). weather·route는 해소 실패 `TOOL` | 깨끗(F77-2 재확인) |
| T19 | 아이 그림 공모전 | contest 0건, 안내 없음. 기본 목록은 Kaggle 10(Gemma·ARC…). 코퍼스 4755 "디자인" 필터 0 | 마찰 F79-2 |
| T20 | 열흘 날씨 + 반경 50km 약국 | 7일만(무표지). 반경은 message에만 "20000m" | 재확인(관문 누출) |
| T21 | 나들이 계획표 JSON 저장 → 다시 읽기 | 칸 5개 보존·값 일치(스크래치 삭제) | 깨끗 |
| T22 | 코퍼스 축 13액션 273용례 check | invalid 52(TYPE 58·UNKNOWN_ARGUMENT 8·PIPE_COLLISION 6…), LITERAL_DOLLAR 11. 최신 4768·4197 `markers:"$items"` → PIPE_COLLISION | check(교재 드리프트 재확인) |
| T23 | 부작용 사전 판정 | show_map·notify_user·weather effects `unknown`, write `write_external` | check(B75-4 재확인) |
| T24 | 판본 1 정렬 내림차순 | `desc:true` → [3,2,1] · `descending:true` → **[1,2,3]** + 자기모순 경고. 판본 2 `desc` UNKNOWN_ARGUMENT | 결함 B79-8 |

튼튼했던 것:
- 날씨의 해소 이름 echo와 두 경로 일치
- 장소 검색: 카테고리·거리순·`lon` 별칭·`truncations.scope:"selection"` 정직 신고
- 숙소 날짜 별칭(`check_in`·`start_date` → `checkin`, 데이터화된 aliases)
- 길찾기: 지도 봉투의 해소 이름, 없는 목적지의 정직한 실패, 대중교통 10경로와 시 경계 완결
- 원천 0건: 8원천이 성공·빈 목록으로 정직하게 답했다
- `self:write`/`read` JSON 왕복

실패는 한 자리에서 났다. **원천 어댑터의 기본값·후필터·병합·드리프트가 사용자 질문의 뜻을 조용히 바꾸는 자리**다.
- 사용자는 "주말 공연", "청주 매물", "700m 안", "1박 10만원"을 물었다.
- 몸은 각각 "지금 공연 중인 것", "최신 40건 중", "반경 안 + 전국 인기", "합계 10만원"에 답했다.
- 응답은 모두 success였다.

## 갭의 원장

### B79-1 ★ `sense:performance`의 기본 `status:"공연중"`이 **오늘 기준**이라, 날짜 범위·기간 검색에서 아직 개막 전인 공연을 전부 뺀다

- **요약**
  - `culture/handler.py` `_perf_search`는 `date_from`·`date_to`가 있어도, 없어도(`search_by_keyword`, `days` 기본 90) `status` 기본값을 `"공연중"`으로 넣는다(`ti.get("status", "공연중")`, 55·62행; `tool_kopis.search_by_keyword` 395행 기본 인자도 같음). (보고서 저장 전 세 자리를 직접 확인했다.)
  - KOPIS `prfstate`는 **조회 시점의 상태**다. 그래서 "이번 주말(10-03~04)에 볼 수 있는 공연"을 물어도 오늘(09-29) 기준 이미 공연 중인 것만 돌아온다. 주말 전에 개막하는 공연, 주말에 개막하는 공연은 빠진다.
  - 선언(`target_description`)은 "status… 옵션"이라고만 쓰고 기본값을 말하지 않는다. 결과의 `search_params.status`에만 `"공연중"`이 남는다.
- **최소 재현**: `return [sense:performance]{date_from:"2026-10-03", date_to:"2026-10-04", region:"충북", rows:50}` vs 같은 문장 + `status:"공연예정"`
- **실측**
  - T03: 기본 4건 vs 공연예정 5건(개막 10-01·10-02·10-03×3). 주말에 열리는 9건 중 **5건(56%) 누락**이다. 누락분에 가족 과제의 핵심인 "어린이 벌룬쇼, 상상 풍선 마술단 [청주]"(10-03 개막)가 있다.
  - 격리: `{region:"충북", days:14}` 기본 5건 vs `status:"공연예정"` 15건 → "앞으로 2주 공연"의 **75% 누락**이다.
  - 코퍼스 3984·3825(`{query:"청주"}`)·4780·4781도 같은 기본값을 탄다.
- **제안(수리성)**
  1. 기간(`date_from`/`date_to`/`days`)이 있으면 `status` 기본값을 비운다(범위와 겹치는 모든 상태). 또는 공연중+공연예정을 합친다.
  2. `status`를 명시했을 때만 상태를 거른다.
  3. message에 적용한 상태 필터를 적는다.
  - 결과가 넓어지는 쪽이라 기존 문장이 깨지지 않는다(비파괴).
  - 가드: 개막 전 공연 fixture가 기간 검색 기본값에 포함되어야 한다.

### B79-2 `sense:performance`의 region·genre가 코드표 밖 값이면 원문 그대로 원천에 넘어가 **성공 0건**이 된다 (★B77-1 census에 '값 영역' 축)

- **요약**
  - `tool_kopis._resolve_region`은 사전에 없는 값을 **그대로** 돌려준다(`REGION_CODES.get(region, region)`). 사전은 시도 17개뿐이다.
  - "청주" 같은 시·군 이름, 사전 밖 장르 "어린이극"이 KOPIS에 코드로 가서 0건이 된다.
  - 응답은 "총 0개의 공연을 찾았습니다" success이고, check는 `incomplete`·경고 0이다.
  - `op:"regions"`가 코드표를 주지만, 입구가 그 표로 값을 검증하지 않는다.
- **최소 재현**: `return [sense:performance]{date_from:"2026-10-03", date_to:"2026-10-04", region:"청주"}` → 0건 success. `region:"충북"`은 4건이고 그중 제목에 "[청주]"가 붙은 것이 2건이다.
- **실측**(T04): `cheongju:0`, `cheongju_region_echo:"청주"`, `genre_bad:0`(`genre_echo:"어린이극"`), check warn=[]
- **제안(수리성)**
  1. region·genre·status를 선언된 enum/alias 표로 검증하고, 모르는 값은 후보 목록과 함께 거절한다.
  2. 시·군 이름은 KOPIS 시군구 코드(`signgucodesub`)로 풀거나 "시도로 검색 후 제목·장소 필터"를 안내한다.
  - B77-1(원천별 인자 **이름**의 침묵 무시)이 이관된 census에 **인자 값 영역** 축을 더한다. 같은 모양이 `_resolve_genre`·`_resolve_status`에도 있다(`GENRE_CODES.get(genre, genre)`).
  - 가드: 모르는 region·genre → 거절 또는 경고, 침묵 0건 0.

### B79-3 ★ `sense:used` 당근 원천이 바뀌었는데 몸은 **success·0건**으로 받는다 (★밭 이관: B77-3과 같은 속, 두 번째 — 원천 드리프트 침묵)

- **요약**
  - `shopping-assistant/tool_used.search_danggeun`은 `/kr/buy-sell/?in=x-{id}&search=` HTML의 JSON-LD ItemList를 읽는다.
  - 지금 이 주소는 **301로 `/kr/search/buy-sell/?in=…&q=…`에 리다이렉트**된다. 새 페이지(87KB)에는 `application/ld+json`이 0개다.
  - 핸들러는 ItemList를 못 찾으면 `{source:"danggeun", total:0, items:[], note:"결과 없음 또는 페이지 구조 변경(JSON-LD ItemList 미발견)"}`를 success로 준다. "없음"과 "고장"을 한 문장에 접었다.
  - `shopping.md`가 옛 `site:"used"`를 은퇴시킨 이유가 "`except: pass`라 실패가 침묵해서 '매물이 없다'와 '긁기가 깨졌다'를 구별할 수 없었다"였다. 그 결함이 후계 어휘에서 재발했다.
- **최소 재현**: `return [sense:used]{source:"danggeun", query:"자전거", region:"오송읍"}` → `total:0` success
- **실측**
  - T15: "닌텐도 스위치"·"자전거" 둘 다 0건, `success:true`
  - 셸 대조(원천 원응답)
    - 지역 해소 `regions/keyword?keyword=오송읍` → id 2121(충청북도 청주시 흥덕구 오송읍) 정상
    - 검색 `…/kr/buy-sell/?in=x-2121&search=…` → 200(리다이렉트 후 `/kr/search/buy-sell/`), ld+json 0, "“닌텐도 스위치” 중고거래 검색 결과 … 오송읍" 머리글만 있음(목록은 클라이언트 렌더로 보임)
- **보이지 않는 이유**
  - `sense:used`의 fixture는 `{source:"bunjang", …}` 하나다(`ibl_actions.yaml` 31행). 당근 경로는 자가점검에 안 닿는다.
  - action_health도 이번 회차 used 13호출을 전부 success=1로 적었다.
- **제안(수리성, ★밭 이관 — 다음 수리 턴 항목)**
  1. 당근: 새 검색 주소를 해석하거나(내부 JSON 경로 탐색), 못 하면 `success:false`·`error_type:"source_changed"`로 정직하게 실패한다.
  2. **census**: 생산자 중 "파서가 목표 구조를 못 찾으면 빈 성공"인 자리를 AST·패턴으로 전수한다. 예: `if not products: return {… total:0 …}`, `except: return []`, `.get("name","")`류(B77-3).
  3. 관문: "구조 미발견 ≠ 0건"을 강제한다.
  4. source별 fixture를 요구하고(변이 축), fixture 결과에 "0건·빈 칸 비율" 경보를 둔다.
  - 가드: 구조가 바뀐 HTML fixture → 실패, 정상 빈 결과 fixture → 성공 0건.

### B79-4 `sense:used` 번개장터 `region`은 최신 40건 표본의 후필터다 — "청주 중고 스위치 2"가 `total:0`으로 나온다

- **요약**
  - `search_bunjang`은 `find_v2.json`에서 **최신순 `max(limit*2, 40)`건** 한 쪽만 받는다. 그 행의 `location`에 region 문자열이 있는 것만 남기고, `total:len(records)`로 신고한다.
  - 전국 최신 40건 중 청주 매물이 없으면 "청주 매물 0건"이 사실처럼 나온다. 위치 표기가 없는 매물(표본의 대다수)은 region을 주는 순간 전부 빠진다.
  - 선언은 "위치 substring 후필터(반경 아님)"까지만 말하고 **표본 크기**는 말하지 않는다.
- **최소 재현**: `return [sense:used]{source:"bunjang", query:"닌텐도 스위치 2", region:"청주", limit:15}` → `{total:0, items:[]}`
- **실측**(T14): region 없이 받은 15행 중 위치 표기 4행(구리·관악·강남·안산). region "청주" → `total:0`, `truncations` 없음.
- **제안(수리성)**
  1. region이 있으면 목표 수를 채우거나 상한 쪽 수까지 페이지를 넘긴다.
  2. 봉투에 `scanned`(훑은 원천 행 수)·`truncations:[{scope:"source", reason:"scan_limit", …}]`를 싣는다.
  3. 위치 미표기 행 수(`unlocated`)를 따로 센다.
  4. 원천 API에 지역 파라미터가 있으면 그것을 쓴다.
  - 가드: 청주 매물이 41번째에 있는 fixture → 찾거나 scan_limit 표지.

### B79-5 ★ `sense:restaurant` 좌표·반경 검색에 **네이버 전국 결과가 섞인다** — 반경도 질의도 지키지 않는 행이 "검색 결과 N개"에 들어간다

- **요약**: `location-services/handler.py` `search_restaurants_combined`의 문제는 셋이다.
  - 카카오 검색에는 x·y·radius를 넘긴다. 네이버 지역검색(`search_naver_local(query, 5, "comment")`)은 **좌표 없이 질의어만**으로 부른다. 네이버는 좌표 필터가 없어 전국 인기 결과 5건을 준다.
  - 이 5건은 카카오 결과와 중복이 아니면 그대로 `combined`에 붙는다. 반경 필터는 없고 `distance` 칸도 없다.
  - 블로그 근거 보강은 상위 12행만 한다(`_enrich_with_blogs(top_n=12)`). 나머지는 `blog_count`가 없어 정렬에서 0 취급을 받는다. 지역어는 `query.split()[0]`(질의 첫 낱말)이라 "맛집"·"돈까스" 같은 질의에서는 지역어가 음식 이름이 된다.
- **최소 재현**: `return [sense:restaurant]{query:"돈까스", x:"127.4783", y:"36.6347", radius:700, limit:30, enrich:false}` → 14행 중 5행 `source:"naver"`, distance null, 주소 대전·경기 시흥·여수·춘천·광주
- **실측**
  - T07: message "'돈까스' 검색 결과 14개 (카카오 9 + 네이버 5, 중복 병합)". 네이버 5행은 "청춘조개 오이도본점"·"꽃돌게장1번가"·"통나무집닭갈비 본점" 등 질의와도 무관하다.
  - T08: "맛집" 1.5km. 네이버 5행(대전·군산·천안·서울)은 블로그 정렬 뒤 잘려 나갔지만, 15행 중 6행이 `blog_count` null이다. 카카오 결과가 limit보다 적은 좁은 반경·구체 질의에서는 T07처럼 섞여 나온다.
  - 행마다 칸이 달라 `[table:select]{columns:[…,"distance","blog_count"]}`가 `MISSING_FIELD`로 실패하고, 진단이 어느 열인지 말하지 않는다(F72-2 재확인).
  - 칸 타입: restaurant `distance`는 문자열 `"619"`, place `distance`는 정수(F76-1 재확인).
- **제안(수리성)**
  1. 좌표가 있으면 네이버 결과를 좌표로 필터(카카오 반경과 같은 haversine)하거나, 좌표 검색에서는 네이버를 설명 병합에만 쓴다(새 행 추가 금지).
  2. 모든 행에 같은 칸 집합을 싣는다(`distance`·`blog_count` 항상 존재, 미측정은 null + `blog_measured:false`).
  3. 블로그 지역어는 좌표의 역지오코딩 구/동 또는 행 주소에서 뽑는다.
  4. `distance`를 정수로 통일한다.
  - 가드: 좌표·반경 fixture → 반경 밖 행 0, 칸 집합 동일.

### B79-6 `sense:stay` goodchoice의 `price`는 **숙박 합계**인데 선언은 1박이다 — "1박 10만원 이하"가 2박 검색에서 틀리게 거르고, 그 0건이 원천 절단으로 **실패**한다 (★B78-1 속 세 번째 — 이관된 census에 생산자 추가)

- **요약**: 문제는 둘이다.
  1. 여기어때 `discountTotalPrice`는 체크인~체크아웃 **합계**다. 그런데 선언은 "max_price=1박 상한(원)"이다. 핸들러는 합계를 `max_price`와 비교한다(`_to_int(pay) > max_price`). 행에는 박 수·1박가 칸이 없다.
     - summary 문구는 1박 정가와 합계를 섞는다. 격리 실측: 2박 "21만원 (정가 22만원, 52%할인)".
  2. 필터로 줄어든 결과를 `truncated: total > len(items)` + `bounded_selection(...)`이 `truncations:[{scope:"source", reason:"limit", limit:9, retained:0}]`로 적는다. 요청 limit 9가 total 5보다 큰데도 그렇게 적는다. 판본 2 어댑터는 이를 원천 불완전으로 올려 **`PARTIAL_SOURCE` 실패**를 낸다.
     - 사용자가 준 필터(선택)를 원천 절단으로 오분류한 것이다. B78-1(미리보기 절단)·B76-4(표본 요청)와 같은 속이다.
- **최소 재현**: `return [sense:stay]{region:"세종", checkin:"2026-10-10", checkout:"2026-10-12", max_price:100000, limit:9}` → `success:false`, `diagnostic.code:"PARTIAL_SOURCE"`, partial `{count:0, total:5, truncations:[{scope:"source", reason:"limit", limit:9, retained:0}]}`
- **실측**(T11): 초정약수 세종스파텔
  - 10-10 1박 80,000 + 10-11 1박 70,000 = 2박 **150,000**(`sum_equals:true`)
  - 1박 평균 75,000원이라 "1박 10만원 이하"에 들어가야 하는데 빠졌다.
  - 격리: 다른 4곳도 2박 가격 = 두 날짜 1박의 합이다(184,640=101,552+83,088, 440,000=242,000+198,000, 210,000=120,000+90,000).
- **제안(수리성)**
  1. 행에 `nights`·`price_total`·`price_per_night` 칸을 싣고 `price`의 뜻을 선언에 적는다.
  2. `max_price`는 1박가로 비교한다(선언을 지키는 쪽).
  3. 필터 선택은 `truncations:[{scope:"selection", reason:"filter"}]`로 신고한다.
  - ★census 항목: `bounded_selection`을 부르는 생산자 전수(place·stay·…)에서 "서버/클라이언트 필터로 줄어든 행"이 source scope로 가는 자리를 찾는다. B78-1 이관 항목(봉투 truncated scope 필수 + 생산자 census)에 이 생산자 부류를 더한다.
  - 가드: 2박 fixture → 1박가 필터 정확, 필터 0건 → 성공·빈 목록·selection scope.

### B79-7 `sense:exhibit` 행이 **좌표 계약 밖**이다 — 원천 좌표(gpsX/gpsY)가 있는데 `limbs:show_map`이 버리고 이름으로 찾아 2/5를 떨어뜨린다 (F76-1 속 새 자리)

- **요약**
  - location-services는 "좌표 계약(#1): 위치 액션 출력 항목은 lat/lng float 보장"을 place·restaurant·stay·cctv에 적용한다.
  - culture 패키지의 exhibit(KCISA)는 좌표를 `gpsX`(경도)·`gpsY`(위도) **문자열**로만 싣는다. `lat`/`lng`가 없다.
  - `show_map._normalize_markers`는 `mk["lat"]`/`mk["lng"]`만 좌표로 읽는다. 없으면 `place`·`query`·`address` 칸을 카카오 키워드 검색으로 지오코딩한다(size 1, 합치 검사 없음). 그래서 원천이 준 정확한 좌표를 버리고, 이름이 흔치 않은 장소는 탈락한다.
- **최소 재현**: `$e=[sense:exhibit]{query:"청주"}` → 주말 행 filter → `[limbs:show_map]{markers:$now}`
- **실측**(T06)
  - 주말 행 5개 **전부 gpsX 보유** → 마커 3, `unresolved` 2("CGV청주(서문) 갤러리원 1층 "·"예술나눔 터")
  - 나머지 3개는 "카카오 검색: 청주시립미술관" 등으로 지오코딩됐다(부수 외부 호출).
- **제안(수리성)**
  1. exhibit(과 같은 규약을 쓰는 culture 생산자)이 `lat`/`lng` float을 병기한다(원명 보존).
  2. `show_map`은 흔한 좌표 칸 별칭(`gpsY/gpsX`·`y/x`·`latitude/longitude`)을 읽는다. 지오코딩은 좌표가 없을 때만 한다.
  3. 좌표 계약을 패키지 경계 밖(모든 `lat/lng`를 내는 액션)으로 넓히는 관문: "행에 좌표류 칸이 있으면 lat/lng 필수".
  - F76-1(통화 칸 규약 census)의 좌표 칸 항목으로 합친다.
  - 가드: exhibit fixture → lat/lng float, show_map 마커 수 = 좌표 보유 행 수.

### B79-8 판본 1 `table:sort`가 `descending:true`를 **무시**하고 자기모순 경고를 낸다 — 판본 2는 거꾸로 `desc`를 거절한다

- **요약**
  - 판본 1 `[table:sort]{…, descending:true}`는 오름차순으로 돌려준다. `param_warning`은 "미인식 파라미터 ['descending'] … 비슷한 키: descending→descending. 이 액션의 주요 키: ['by','desc','descending','items','op','order']"다.
  - 모르는 키라면서 제안과 주요 키 목록에는 그 키가 들어 있다. 경고 생성기가 아는 선언 키와 핸들러가 실제 읽는 키(`desc`·`order`)가 다르다.
  - 판본 2 서명은 `descending`만 받고 `desc`는 UNKNOWN_ARGUMENT다.
  - 코퍼스 49건이 `desc:true`(판본 2에서 invalid)다. 판본 2를 익힌 모델이 판본 1 저장 프로그램·스케줄을 고치면 `descending`을 써서 조용히 오름차순이 된다. 예: "평점 높은 순 take 5" → 최저 평점 5.
- **최소 재현**(판본 1): `[table:sort]{items:[{a:1},{a:3},{a:2}], by:"a", descending:true}` → `[1,2,3]` + 위 경고
- **실측**(T24): `desc:true` → [3,2,1] · `descending:true` → [1,2,3]. 판본 2 `desc` check `invalid`/`UNKNOWN_ARGUMENT`.
- **제안(수리성)**
  1. 판본 1 sort가 `descending`을 `desc`의 별칭으로 읽는다(aliases 데이터 — 비파괴).
  2. 경고 생성기와 핸들러의 키 목록을 한 소스로 맞춘다. 제안 키가 입력 키와 같으면 경고 문구 자체가 모순이므로 관문으로 막는다.
  3. 코퍼스 `desc:true` 49건은 용례 재검토 대상이다.
  - 가드: 판본 1 `descending:true` → 내림차순, 모순 경고 0.

### F79-1 공연·전시 교차 식별이 안 된다 — 같은 공연이 두 원천에서 다른 제목으로 온다

- T05: KOPIS "무명의 용병사 [청주]" vs KCISA "[청주] 무명의 용병사 "(끝 공백). 장소는 둘 다 "예술나눔 터"다. `dedup{by:"title"}` 뒤 13행에 둘 다 남는다. "청주짜글이"도 같다.
- 전시 원천(KCISA)이 연극·뮤지컬·축제를 함께 주므로 공연 ∪ 전시는 중복이 구조적으로 생긴다. 코퍼스 3984·3825·3878이 이 union+dedup를 가르친다.
- 제안(수리성): 두 생산자가 비교용 정규 제목 칸(`title_key`: 지역 괄호 태그·공백·구두점 제거)을 병기한다. 교재에는 "공연∪전시는 `title_key`+장소로 dedup"을 적는다.

### F79-2 `sense:contest` — 한국어 공모전 질의 0건이 길을 말하지 않고, 코퍼스가 Kaggle을 "공모전"으로 가르친다

- T19: "어린이 그림 공모전" → `count:0`, message·note 없음. 선언은 "국내 공모전은 [sense:search]가 정직한 경로"인데 응답은 이를 말하지 않는다.
- 코퍼스 4755("디자인" 제목 필터 — Kaggle 목록에서 구조적으로 0)·4756("진행 중인 공모전" 문서)이 Kaggle 목록을 일반 공모전으로 가르친다.
- 제안(수리성): 한글 질의나 0건일 때 `hint:"국내 공모전은 [sense:search]"`를 싣는다. 코퍼스 두 건은 용례 재검토 대상이다.

### F79-3 산술 표면의 교재 드리프트

- `**`(거듭제곱)·`//`(정수 나눗셈)는 동작한다(`2 ** 0.5` → Decimal 1.414…, `7 // 2` → 3). 교재 `12_ibl_only.md`는 이를 말하지 않는다(`**`는 레코드 펼침으로만 나온다).
  - T09·T17의 직선거리 근사는 이것으로 됐다. 삼각함수가 없어 위도 고정 상수(89.3 km/deg)로 근사했다.
- `round(x, 0)`은 인덱스로 못 쓰는 값을 낸다. `round(x)`는 정수라 된다. `3 / 3`도 인덱스로 못 쓴다.
- INDEX 오류 "인덱스가 범위를 벗어났거나 정수가 아닙니다"가 인덱스 값·타입·목록 길이를 말하지 않는다(F72-2 재확인).
- 제안(수리성): 교재 값·식 절에 산술 연산자 표(`+ - * / // % **`)와 "인덱스는 정수 — `round(x)`·`//`"를 적는다. INDEX 진단에 값·타입·길이를 싣는다.

### V79-1 (후보) 좌표 → 도로명·지번 주소가 없다

- T17: `sense:reverse_geocode`는 행정구역(카카오 `coord2regioncode`)만 준다. 그 주소로 다시 찾으면 원래 장소가 아니라 96m 떨어진 다른 시설이 나온다.
- 지도에서 찍은 곳의 주소를 저장하거나, 사진 좌표의 주소를 쓰는 요구는 도로명이 필요하다(카카오 `coord2address`).
- **어휘 신설은 제안하지 않는다.** 기존 액션의 선택 칸(`detail:"road"`)으로 가능한지는 현실 반복이 인준할 일이다.

## 재확인 (앞 회차 갭·수리의 증거 — 새 항목 아님)

- **B78-8**(문자열 실패 봉투의 성공 기록): 이번 회차 action_health 124행이 **전부 success=1**이다.
  - `sense:navigate_route` shape=error 3행(없는 목적지 "찾을 수 없습니다")
  - `sense:weather` shape=error 1행
  - `sense:stay` PARTIAL_SOURCE 2회(핸들러는 success:true, 판본 2만 실패)
- **B78-1/B76-4**(절단 오분류): B79-6이 세 번째 생산자 부류다(필터 선택 → source scope).
- **B77-1**(원천별 인자 침묵 무시): B79-2가 **값 영역** 차원을 더한다.
  - 반대로 지켜진 자리: stay 날짜 별칭(`check_in`·`start_date`), place `lon` 별칭이 제대로 동작했다(aliases 데이터화 수리 살아 있음).
- **B77-3**(외부 원천 스키마 드리프트 침묵): B79-3이 같은 속 두 번째다 → 밭 이관.
- **F77-1**(meta 접기):
  - stay의 시군구·주소가 `meta`("3성급 · 호텔 · 춘천시 · 평점 8.5(331)")에만 있다. 세종 밖 숙소를 거르려면 문자열 포함 검사뿐이다(T12).
  - used의 매물 위치("경기도 구리시 인창동")와 contest의 상금·마감·팀 수("상금 35,000 Usd · … · 마감 2026-11-12 · 64팀")도 meta뿐이다.
- **F76-1**(통화 칸 규약 반쪽):
  - restaurant `distance` 문자열 vs place 정수
  - search_shopping `price` 문자열 `"727600"` vs used 정수. T13은 `number()`로 맞췄다.
  - exhibit 좌표(B79-7)
- **F72-2**(진단 안내 부족): select `MISSING_FIELD`의 `details:{}`, INDEX 오류(F79-3)
- **F77-2**(실패 코드 구별): 없는 도시(weather)·없는 목적지(route)가 원천 장애·키 누락과 같은 `TOOL`이다. "장소 해소 실패"를 값으로 가를 수 없다(T18).
- **닫힌 밭 관문 누출 증거**(침묵 클램프 — 새 항목 아님): `scripts/check_silent_clamp.py`의 요청량 어휘(limit/count/rows/display…) 밖이라 잡히지 않은 자리가 둘이다.
  - `get_weather_openmeteo`의 `"forecast_days": min(days, 7)`: `days:10` → 7일, 표지 없음(T20)
  - `tool_place`의 `min(radius, _MAX_RADIUS)`: 50000 → 20000, message에만
  - 관문 어휘에 기간·반경류(`days`·`radius`)를 더하는 것은 관문 소유자 몫이다.
- **교재·코퍼스 드리프트**(F76-3·F78-3 계열):
  - 축 13액션 코퍼스 273용례 중 판본 2 check **invalid 52**
    - TYPE 58: 대부분 봉투를 `.items` 없이 파이프, `where:{field,op,value}` 옛 필터형 7
    - UNKNOWN_ARGUMENT 8: `desc` 5·`keep` 2·`fields`, `collect`
    - PIPE_COLLISION 6
    - LITERAL_DOLLAR 경고 11
  - 가장 최근 용례 4768(`here → place 약국 → show_map{markers:"$items"}`)과 4197이 판본 2에서 PIPE_COLLISION이다.
- **B75-4**(check의 액션별 사전 판정 부재): `limbs:show_map`(화면)·`self:notify_user`(발신)·`sense:weather` check effects가 `unknown`이다. `self:write`만 `write_external`로 정확했다(T23).
- **잠재(재현 못 함, 코드만)**
  - `navigate_route`의 자동차 응답 압축은 `routes[0]`의 요약만 싣는다. 선언 인자 `alternatives:true`는 실측 두 경로에서 카카오가 1경로만 줘서 효과를 확인하지 못했다(코드 경로 직접 호출로 대조).
  - 대안 경로가 오는 날에는 조용히 버려진다. 수리 턴이 fixture로 확인할 것.

## 시드 후보 (실행 검증 통과만 — 자동 등록 안 함)

- T01(weather → filter 주말 → filter 무강수 → `[if]` 실내 exhibit / 야외 place 관광명소 → take)
- T02(weather 도시명 vs place 좌표 → weather lat/lon → zip → abs 차)
- T09(후보 목록 → each{place + navigate_route → map_data.origin 대조 → `** 0.5` 직선 근사} → sort duration)
- T10(navigate_route transit → sort duration_min/fare_krw → take, 자동차와 대조)
- T13(search_shopping → number(price) → min / used bunjang → filter 가격·제목 → sorted → `//` 중앙값)
- T16(here → place category 약국 lat/lng radius sort distance → take) — 좌표는 here의 값으로만
- T21(weather·exhibit·restaurant → 계획 레코드 → self:write json → self:read .data)

문장 안의 지명·가게·상품은 자리표로 바꿔 심을 것(생활권 지명은 사용자 위치 단서).

**빼는 것**:
- T03·T04: B79-1·2 수리 전 기본값·값 영역 함정
- T05: F79-1
- T06: B79-7
- T07·T08: B79-5
- T11: B79-6
- T12: F77-1 꼬임
- T14·T15: B79-4·3
- T17: V79-1 꼬임
- T19: F79-2
- T20: 관문 누출
- T22~T24: check·판본 1
- 코퍼스 4755·4756·4768·4197·4770과 `desc:true` 49건은 용례 재검토 대상이다.

## 판정 요청 (언어 개정·파괴적 변경 2종만)

**없음.**
- B79-1~8·F79-1~3은 모두 수리성이다.
  - B79-1(기본 status 해제)은 결과가 **넓어지는** 쪽이라 기존 문장을 깨지 않는다.
  - B79-6(1박가 비교)은 선언을 지키는 쪽이다.
  - B79-8(판본 1 별칭)은 가산적이다.
- V79-1은 어휘 후보일 뿐이다(현실 반복이 인준).

**다음 수리 턴의 첫 항목(밭 이관)**:
1. B79-3(+B77-3): "구조 미발견·파싱 실패 = 빈 성공" 생산자 census → 관문, source별 fixture 변이 축과 채움률 경보
2. B79-6(+B78-1·B76-4): 봉투 truncated scope 필수 + `bounded_selection` 생산자의 필터/선택 → selection scope
3. B79-2(+B77-1): 원천 인자 격자 census에 값 영역(enum·alias 검증) 축

## 72~79회차 공통 뿌리에 79회차가 더하는 것 (훈련자 관찰)

- 77·78회차의 "원천의 결과 없음·한도·상태가 몸의 분류로 정직하게 번역되지 않는다"가 이번에는 **원천 어댑터의 기본값·후필터·병합**에서 났다. 넷 모두 사용자 질문의 뜻을 조용히 바꾼다.
  - 오늘 기준 status가 기간 질문을 좁힌다(B79-1).
  - 표본 후필터가 지역 질문에 "없다"고 답한다(B79-4).
  - 좌표 없는 병합이 반경 질문에 전국 행을 섞는다(B79-5).
  - 합계가 1박 질문을 거른다(B79-6).
  - 공통점: 응답은 success이고, 그 해석을 말하는 칸이 없다(`search_params` echo·message 한 줄뿐). 뿌리 2(**선언과 실제 동작의 대조 관문 부재**)의 가장 흔한 모양은 "선언이 말하지 않는 기본값·표본·단위"다.
- 좌표 계약·칸 규약이 **패키지 경계**에서 끊긴다(B79-7). location-services 안에서는 "lat/lng 보장"이 지켜지지만, culture가 낸 좌표를 location의 show_map이 못 읽는다. 규약이 패키지별 주석이 아니라 관문이어야 하는 이유다(F76-1 census).
- 드리프트 침묵이 **은퇴 사유를 되풀이**했다(B79-3). `site:"used"`를 은퇴시킨 근거("긁기 고장 = 매물 없음")가 후계 `sense:used{source:"danggeun"}`에서 같은 모양으로 재발했다. 수리 이력이 개별 자리를 고쳤지 부류를 닫지 않았다는 증거다(pitfall hand-picked-sweep-leaks).
- 판본 두 개가 **인자 이름을 반대로** 안다(B79-8). 판본 1은 `desc`, 판본 2는 `descending`이다. 판본 경계의 별칭 표가 한 벌이 아니다. 코퍼스가 판본 1 이름을 가르치는 동안 판본 2 교재는 반대를 가르친다.

## 위생

- **기준선**: 탐침 전 02:24:25에 떴다([baseline.json](baseline.json)). 담은 것은 다음과 같다.
  - action_health max id 244555, notify_log 6260, 알림함 2통, since 1스트림 25행
  - 저장한 장소 원장·선언 위치의 크기·mtime·해시, 스크래치 목록, 코퍼스 3,735
- **회차 후 diff**(02:41:19)
  - action_health 새 행 122(그 뒤 격리 2행 추가 → 124), **전부 `training`/agent**. B78-8 때문에 실패도 success=1로 적혔다.
  - notify_log 0 · 알림 추가 0 · since 불변
  - 저장한 장소 원장·선언 위치 해시 불변 · 코퍼스 3,735 불변 · episode_log 불변
- **호출**
  - 외부 조회 113회(action_health 기준): stay 18·place 17·navigate_route 16·used 13·performance 12·weather 11·restaurant 7·exhibit 6·contest 5·search_shopping 4·reverse_geocode 2·show_map 2
    - 부수 호출은 별도다: 맛집 블로그 보강 2회분 약 24회, 마커 지오코딩 3회
    - `sense:here`(로컬) 3회
  - 셸·코드 경로 대조 5회: 당근 curl 3, 카카오 길찾기 핸들러 직접 호출 2
  - 유료 AI 0 · 발신 0 · 해마 시딩 0
  - 고친 문장 재실행 일부는 `reuse`로 읽기 영수증을 재사용했다.
- **스크래치**(전부 삭제 확인): `projects/컨텐츠/outputs/IT79_나들이.json`(T21), 스크래치패드의 탐색 파일(당근 HTML 사본·코퍼스 check 결과·탐침 조각)
- **화면**: `limbs:show_map`을 `/ibl/execute`로 2회 불렀다. 값(map_data)만 반환하고 채팅 렌더러(execute_tool 래퍼)를 거치지 않아 띄운 창은 없다.
- **사용자 데이터 무손상**: 저장한 장소 원장·선언 위치는 읽지도 쓰지도 않았다. 사용자 위치는 `sense:here`로만 읽었고 before.json에는 모양으로 남겼다(저장 후 선언 위치 값으로 대조 0).
- **나머지**: 라이브 코어 편집 0 · 커밋 0
- **백엔드**: 회차 내내 `state.json` phase `ACTIVE`(`last_result.outcome: restarted`), 재기동·FAILED 없음.

## 집행 완료

(1차) `747d5103` — B79-1·2·3(정직 실패)·5·6·7·8 수리([77~81 공통 경계 수리](../../IMAGINATION_77_81_REPAIRS_2026_09_29.md)).

(2차 · 2026-09-29) 라이브 재탐침으로 샌 것을 골라 수리 — 정본 [78·79 잔여 수리](../../IMAGINATION_78_79_RESIDUAL_REPAIRS_2026_09_29.md).
- B79-3: 당근 Remix 로더 JSON 파서 복구, 동네 불일치·구조 미발견 = `source_changed`, region 없는 호출 거절. 관문 `iblbuild_source_honesty.py` → 다나와·TOPIS 형제. source 별 실행 예시 필수.
- B79-4: 번개장터 최대 5쪽 훑기 + `scanned`·`unlocated`·`scan_limit` 표지.
- B79-5 잔여: 블로그 지역어를 행 주소에서. B79-7 잔여: show_map 좌표 별칭. B79-2 잔여: 코드표 거절 문구·hint.
- B79-8 잔여: 액션 aliases 를 판본 2 계약에 투영(별칭 표 한 벌), 경고 생성기 모순 관문. `desc`·`descending` 두 판본 공통.
- F79-1: `title_key`·`place_key`. F79-2: 공모전 hint. F79-3: 정수 값 인덱스(`integer_value`)·INDEX 진단·산술 교재.
- 침묵 클램프: 관문에 기간·반경 어휘 → 형제 8곳, 날씨 16일까지 + clamped 신고. 잠재: 길찾기 대안 경로 요약.
- 교재: 3701·3906·4094·3825·3878·4755·4756 개별 교정(영수증은 잔여 수리 문서).
