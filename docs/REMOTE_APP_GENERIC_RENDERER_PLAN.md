# 원격 앱 표면 제네릭화 계획서 (Generic Instrument Rendering)

> 작성: 2026-06-11 · 상태: **전 단계 완료(2026-06-11)** — 1·2단계 + 데스크탑 흡수 + 승격 1·2차(11계기). "모든 표면이 한 정의" 달성.

## ✅ 승격 2차 + select 어휘 확장 (2026-06-11)

- **select 어휘 2종 추가(진짜 어휘 확장, 도메인 중립):**
  - **정적 `options: [{value,label}]`** — IBL 호출 없는 고정 목록(시/도·유형·거래).
  - **종속 `options_action`(cascade)** — options_action 안의 `$형제키`가 그 형제 select 변경 시 자동 재조회. 응답 배열은 option_value/option_label로, 딕셔너리 `{이름:코드}`는 자동 entries 정규화. webapp(resolveOptionsAction/selChanged) + GenericInstrument(SelectInput) 동시 구현.
- **실거래가 승격**: 시/도(정적)→구/군(종속 `[sense:realty]{op:"codes",city:"$province"}`)→유형/거래(정적). 월 생략(최근 3개월 기본). **원격에 cascade로 등장.** 데스크탑은 풍부판 RealtyInstrument 유지 — `STATIC_INSTRUMENT_IDS`로 매니페스트 중복 타일 억제(부동산 도메인 안에 중첩, 상권과 동거).
- **즐겨찾기 승격**: `launch_sites` list를 구조화 반환(`{sites:[{name,url}]}`, 텍스트→JSON)으로 고침 + card_list 링크. 링크는 폰/PC 각자 브라우저에서 열림(북마크 의미 — limbs 부작용 아님, 리모컨 note 불필요). 옛 launchpad onOpen 은퇴.
- 검증: cascade 하니스 12항목(정적 채움·딕셔너리 정규화·시/도 변경 시 구/군 재조회·required 차단·액션 코드·렌더) + validator 파손 4종 + `--check` + tsc/build + 데스크탑 브라우저(부동산 안 실거래가 풍부판 유지·즐겨찾기 카드리스트·문화공연 장르 회귀 0).
- **남은 후보:** 일정 캘린더(월그리드=custom renderer 영역), 상권(지도). 이 둘은 어휘가 아니라 escape.
- 운영 함정: launch 핸들러 변경이라 `POST /packages/reload` 필요(tool.json 아닌 handler.py는 mtime 자동무효화 대상 아님).

## ✅ 리모컨 의미론 + 승격 1차 (2026-06-11)

- **사용자 설계 결정: 원격 런처 = 집 PC 리모컨.** 폰에서 결과를 자연히 못 보여주는 계기(부작용이 집에서 발생)도 원격 노출 OK — `note:` 경고만 명확히. "폰에서 모든 것"은 폰 네이티브 배포의 일, 두 모델을 섞지 않는다. (메모리 `architecture_remote_as_remote_control`)
- **승격 2계기 (총 9계기):**
  - **신문**(`engines:newspaper`) — 키워드 입력→생성, 결과 행의 "🖥 띄우기" 버튼이 `[limbs:os_open]{path}`로 집 PC 화면에 엶. 이를 위해 **렌더 어휘 1개 확장: 리스트 프리미티브 `from: "."` = 응답 자체를 1행으로**(단일 객체 응답에 행 버튼 달기) — 양 렌더러(webapp viewList / GenericInstrument asList) 동시 구현.
  - **유튜브 뮤직**(`sense:search_youtube` + `limbs:music`, instrument: ytmusic) — 검색 탭(결과 행 ▶ = 집 스피커 재생) + 큐 탭(auto_run 조회 + 스킵/정지 버튼). **노드가 다른 두 액션의 계기 병합** 첫 사례.
- 데스크탑은 두 계기 모두 OVERRIDES로 풍부판 유지(NewspaperInstrument=electron 즉시 열기, YtMusicInstrument=다운로드·큐 UI). STATIC_DOMAINS에서 해당 항목 제거 — 타일은 이제 매니페스트가 만든다.
- 검증: promo 하니스 11항목(from:"." rowItem/rowAction, ▶ 액션 코드 조립, 빈 큐/찬 큐, trunc) ALL PASS + 데스크탑 브라우저(타일 위치 유지 + override 동작) + `--check` 통과.
- **남은 승격 후보:** 실거래가(의존 select 어휘 필요 — 시/도→구군 cascade), 즐겨찾기(`[limbs:launch]`, 탭=실행형 타일 어휘 필요), 일정 캘린더(월그리드 = custom renderer 영역).

## ✅ 데스크탑 흡수 완료 기록 (2026-06-11)

- **`GenericInstrument.tsx` 신설** — 원격 webapp과 동일한 렌더 어휘(7프리미티브 + `{path|filter}` + `$key` 액션 템플릿 + modes/chips/select(options_action)/buttons/auto_run/note + item_click 드릴)의 React 포트. 데스크탑·원격이 같은 선언을 각자의 기술로 그린다.
- **`ActionDesktop.tsx` 매니페스트 구동 전환** — `GET /launcher/instruments`를 fetch해 계기 도메인을 합성. `HOME_ORDER` 명단에 없는 새 계기는 홈 끝에 자동 추가 → **app: 블록 1개 = 데스크탑+원격 동시 등장** (코인 계기로 실증, 브라우저 스크린샷 확인).
- **escape 2층 구조 확정:** ①`OVERRIDES`(매니페스트 계기지만 데스크탑판이 더 풍부: book=대출통계·추천 드릴 / invest=recharts·3탭 / radio=즐겨찾기·볼륨) ②`STATIC_DOMAINS`(어휘 밖 영구 escape: 부동산·상권 지도, 길찾기·CCTV leaflet, 일정, 신문, 내 기기, Obsidian, 즐겨찾기, 강의, 유튜브뮤직).
- **은퇴 3계기:** WeatherInstrument/CultureInstrument/LocalInstrument.tsx 삭제(~531줄) — 매니페스트와 1:1 동등(애초에 매니페스트의 출처)이라 제네릭이 완전 대체.
- 검증: `tsc -b` 0에러(잠복 기존 에러 2건도 수정: InvestInstrument recharts Formatter 타입, RadioInstrument 미사용 import) + `npm run build` 통과 + **실브라우저(vite :3000, CORS 허용 포트) 검증** — 날씨(auto_run·metric·kv·kv_list·☔opt 필터), 문화공연(탭 2 + 장르 options_action 채움 + 포스터 21), 코인(자동 등장 + 상승빨강 trend) 전부 실렌더 확인. 주의: 브라우저 검증 시 vite 포트는 backend CORS 허용 목록(5173/3000)에 있어야 함.

---

## ✅ 2단계 완료 기록 (2026-06-11) — 단일 진실 소스 달성

- **`data/instruments.json` 소멸.** 7계기 전부 `ibl_nodes_src/sense.yaml` 액션의 `app:` 블록으로 승격(weather/book/restaurant/stock/crypto/radio 단독 + performance·exhibit가 `instrument: culture`로 병합). 액션이 자기 inputs/action 템플릿/view를 선언한다.
- **`GET /launcher/instruments` 자동 파생** — `api_launcher_web._derive_instruments()`가 ibl_nodes.yaml의 `app:` 블록을 모아 계기 합성(mtime 캐시). 같은 `instrument` id는 `mode_order`순 탭으로 병합, primary(icon+name 보유 멤버)가 계기 표시 담당, 홈 정렬=`order`. **새 IBL 액션에 `app:` 블록만 달면 원격에 자동 등장.**
- **`build_ibl_nodes.py --check`에 app 정합성 합류**(`validate_app_blocks`, 일반 빌드·pre-commit·self-check 전부에서 작동): ①템플릿의 `[node:action]` 실존(드릴·버튼·options_action 포함) ②`$key`↔inputs 대응 ③view 프리미티브 어휘(7종) + 필수 필드(from/card/드릴 action) ④표시 템플릿 필터 오타 ⑤계기 그룹(primary 정확히 1·전원 mode·mode 중복·icon/name 반쪽 선언). **의도적 파손 10종 전부 검출 확인.**
- 1단계 검증 하니스 재실행: 파생 매니페스트가 1단계 매니페스트와 의미 동등(차이=id 개명 food→restaurant + 라디오 빈 inputs 생략뿐), 렌더 16항목 + 종단 흐름 15항목 ALL PASS, 외부 무세션 401/localhost 200, `--check` exit 0(바이트 일치+삼각+코퍼스+app).
- `app:` 블록은 에이전트 프롬프트에 안 샌다(`ibl_access._emit_action_xml`은 description+ops만 직렬화) — 프롬프트 비용 0.
- 웹앱(제네릭 렌더러)은 2단계에서 **한 줄도 안 바뀜** — 1단계에서 어휘를 검증해 둔 효과.

---

## ✅ 1단계 완료 기록 (2026-06-11)

- `data/instruments.json` 신설 — 기존 6계기 전부 선언형 전환 + **실증용 7번째 계기 "코인"(`[sense:crypto]`)을 코드 0줄로 추가**(매니페스트 항목만으로 원격에 등장·렌더 확인).
- `GET /launcher/instruments` 추가(`api_launcher_web.py`) — 화이트리스트 제외, 외부 무세션 401 / localhost 200 실측.
- 웹앱 앱 표면 JS 전면 교체: 하드코딩 `INSTRUMENTS`/`INST_RENDER`/`run*` 제거 → 매니페스트 해석기(`renderView`/`buildAction`/`rowAction`/`tpl`) + `CUSTOM_RENDERERS` escape 레지스트리(메커니즘만, 현재 등록 0).
- **확정 렌더 어휘(7프리미티브):** draft 6종에 `kv`(고정 key-value 행, 날씨 습도·투자 전일가) 추가. `metric`(+`trend` 경로로 상승빨강/하락파랑), `kv`, `kv_list`, `card_list`(+`item_click` 드릴 — 투자 검색→시세, 드릴 응답에 클릭 행을 `_item`으로 주입), `image_grid`, `sparkline`, `list_action`(행별 액션 버튼 — 라디오 재생).
- **표시 템플릿:** `{path|filter}` — round/num/abs/arrow/`opt:앞,뒤`(값 없으면 통째 생략)/`trunc:N`. envelope 불균일은 view 경로가 흡수(stock=`data.quotes`).
- **입력 어휘:** text/select(+`options_action`으로 IBL 호출해 옵션 채움 — 공연 장르)/chips/required/default. 탭은 `modes[]`(문화공연 공연·전시). `buttons[]`(라디오 정지), `auto_run`, `note`.
- 검증: node --check + 렌더 하니스 16항목(7계기 live 응답 통과, 에러/빈결과/envelope 실패 경로 포함) + 종단 흐름 하니스 15항목(openInstrument→setMode→runMode, 탭 전환, 칩, 행 버튼) + 다른 두 표면 함수·id 정합 회귀 0 + 옛 하드코딩 잔재 0. 실브라우저 확인은 미수행(Chrome MCP 미연결) — 폰에서 한 번 열어보면 끝.

---
> 관련 메모리: `project_remote_launcher_modernized`, `project_remote_surfaces_auth_audit`, `architecture_ibl_nodes_build`, `architecture_avoid_vendor_layer`, `project_ibl_location_standardization`

---

## 0. 한 줄 요약

원격 런처의 "앱(계기)"을 **표면별 코드 → 선언(데이터)**으로 바꿔, 새 앱이 생길 때마다 표면마다 다시 짜는 일을 원천 차단한다.
- **1단계(이 계획의 착수점):** 원격에서 *임시 매니페스트 + 제네릭 렌더러*로 **렌더 어휘를 싼값에 검증**.
- **2단계(종착지):** 어휘가 굳으면 매니페스트를 **`ibl_nodes_src` 액션 안으로 승격** → 단일 진실 소스, 드리프트 불가능.

---

## 1. 문제 — 왜 이걸 하나

하나의 "앱(계기)"은 세 가지가 묶인 것이다:
1. **입력 스키마** — 사용자가 고르는 파라미터(도시·검색어·장르 다이얼)
2. **IBL 바인딩** — 어떤 `[node:action]{params}`를 부르는지
3. **결과 렌더링** — 돌아온 JSON을 어떻게 보여주는지(카드/포스터/가격카드/지도)

지금 이 셋이 **표면마다 코드로 박혀 있다** — 데스크탑 React 계기 12개(`frontend/src/components/*Instrument.tsx`)에도, 원격 바닐라 JS(`backend/api_launcher_web.py`의 `get_launcher_webapp_html()`)에도. 비용 = **표면 수 × 앱 수**. 새 앱마다 N번 재포팅, 그리고 드리프트(엔드포인트·필드 어긋남).

이건 IBL이 *도구*에 대해 푼 문제("어휘로 폭증을 흡수")의 **표현층 버전**이다. 같은 수를 둔다.

---

## 2. 종착지 — 액션 자기기술 (왜 이게 장기적으로 옳은가)

**IBL 액션이 자기 입력(`inputs`)과 출력 표현(`view`)을 스스로 선언하고, 모든 표면은 거기서 자동 파생.** 근거:

1. **단일 진실 소스 원칙.** `ibl_nodes_src`를 액션의 유일한 정의처로 만들려고 패키지별 yaml을 죽이고 `--check` 삼각검증을 박았다(2026-05-28). 별도 매니페스트를 *영구 구조*로 두면 액션과 별개의 두 번째 소스가 되어 드리프트 병이 표현층에서 재발한다. param은 이미 `ibl_nodes`에 있다 — 복제 금지.
2. **이미 절반 와 있음.** param·ops·description 존재 + `map_data`/`playable` 출력 봉투 표준화 시작됨. `inputs`+`view`만 더하면 자기기술 완성. 새 시스템이 아니라 기존 궤도의 연장.
3. **동거 = 드리프트 불가능.** 표현이 액션과 한 파일이면 액션 변경과 표현 변경이 한 편집·한 `--check`로 검증된다. 동기화 대상 자체가 사라진다.
4. **복리.** 같은 param 스키마가 앱 GUI + 수동모드 자동완성 + 해마 코퍼스 일관성 + 의식 에이전트 추천을 동시에 먹인다. 별도 매니페스트는 이 소비자들에게 안 닿는다.

**버린 대안 — 데스크탑 React를 그대로 터널 서빙(3안):** 코드 레벨 중복제거라 Electron 결합·이중 빌드로 깨지기 쉽고 스키마·코퍼스에 아무것도 안 먹임. 벤더가 개선하는 React 층에 원격을 사슬로 묶음(`architecture_avoid_vendor_layer` 위배). **채택 안 함.**

---

## 3. 왜 단계를 나누나 (정본 먼저 건드리면 안 되는 이유)

진짜 어렵고 불확실한 부분은 **렌더 어휘**다. 이게 실제 계기를 표현할 수 있는지 검증되기 전에 `ibl_nodes_src`(비싸고 `--check`에 묶이고 코퍼스에 파급되는 정본 층)에 박으면 **틀린 추상을 가장 비싼 곳에 굳힌다.** 그래서:

- **1단계:** 원격에서 임시 매니페스트로 어휘를 검증 — 정본 안 건드림. escape hatch가 어디 필요한지를 싼값에 발견.
- **2단계:** 어휘가 굳으면 매니페스트를 액션 src로 승격 — 매니페스트는 액션 안으로 녹아 사라짐.

**1안(매니페스트)은 2안의 대안이 아니라 1단계다.**

---

## 4. 1단계 — 매니페스트 + 제네릭 렌더러 (착수점)

### 4.1 목표
- 원격 webapp의 앱 표면이 **하드코딩된 6개 함수 → 매니페스트 해석기**로 바뀐다.
- 렌더 프리미티브 어휘와 escape hatch 경계가 **실물로 확정**된다.
- 새 앱 = `data/instruments.json`에 항목 1개 추가 → 원격에 자동 등장(재빌드 0).

### 4.2 매니페스트 스키마 (draft — 1단계에서 확정)
`data/instruments.json` (배열). 백엔드가 `GET /launcher/instruments`로 서빙(원격 인증 게이트 적용 대상 — 현재 미들웨어가 launcher 세션 요구).

```jsonc
{
  "id": "weather",
  "icon": "🌤️",
  "name": "날씨",
  "inputs": [
    { "key": "city", "type": "text", "default": "서울", "placeholder": "도시명(한/영)",
      "chips": ["서울","부산","제주","수원","인천","대구"] }
  ],
  // $key 치환. op 분기·다이얼은 select 타입으로.
  "action": "[sense:weather]{city: $city, days: 7}",
  // 응답 JSON을 어떻게 그리는가 — 프리미티브 조합
  "view": [
    { "type": "metric", "label": "$.city", "big": "$.current.temp",
      "unit": "°", "sub": "$.current.condition" },
    { "type": "kv_list", "from": "$.forecast",
      "row": { "k": "{date}", "v": "{condition} {min_temp}/{max_temp}°" } }
  ]
}
```

핵심 설계점:
- **입력 타입:** `text` / `select`(op·장르 다이얼; options는 정적 배열 또는 `options_action`으로 IBL 호출해 채움 — 예: 장르 `[sense:performance]{op:genres}`) / `chips`(빠른 선택).
- **action 템플릿:** `$key` 치환 + 따옴표 이스케이프. 빈 입력은 파라미터 생략.
- **view = 프리미티브 배열.** 각 프리미티브가 응답 JSON의 경로(`$.path`)를 읽음. 리스트는 `from` + `row` 템플릿.
- **응답 envelope 불균일 처리:** 액션마다 flat / `{success,data}` 다름(§4.6 표 참조). 매니페스트의 `view` 경로가 그 차이를 흡수(예: stock은 `$.data.quotes`).

### 4.3 렌더 프리미티브 어휘 (draft 초안 — 1단계 산출물로 확정)
지금 6개를 덮는 최소 집합:

| 프리미티브 | 용도 | 쓰는 계기 |
|---|---|---|
| `metric` | 큰 숫자 + 라벨/서브(가격·기온) | 날씨, 투자 |
| `kv_list` | key-value 행 반복(예보·상세) | 날씨, 투자 |
| `card_list` | 텍스트 카드 리스트(제목/메타/링크) | 도서, 맛집 |
| `image_grid` | 썸네일 그리드(포스터) | 문화공연 |
| `sparkline` | 작은 SVG 라인(시세 추이) | 투자 |
| `list_action` | 행마다 액션 버튼(재생 등) | 라디오 |

→ 1단계에서 6개를 옮겨보며 이 목록이 충분한지/뭘 더/뭘 합칠지 확정한다.

### 4.4 escape hatch 설계
어휘로 못 담는 계기(지도 드래그=상권·길찾기, 라이브 플레이어 등)는 매니페스트에 `"renderer": "custom:directions"`로 표기하고, webapp이 그 id에 등록된 **전용 렌더 함수**로 위임. "얇은 어휘 + 가이드" 분업의 표현층 버전. **80% 선언 / 20% 코드**가 목표. escape는 부끄러운 게 아니라 설계의 일부.

### 4.5 건드릴 파일 (1단계)
- `data/instruments.json` (신규) — 6개 시드.
- `backend/api_launcher_web.py`:
  - `GET /launcher/instruments` 엔드포인트 추가(매니페스트 서빙). **주의:** 현재 인증 미들웨어(`api.py:remote_access_guard`)는 `is_public_remote_path` 화이트리스트 외 외부요청에 launcher 세션 요구 → `/launcher/instruments`는 데이터라 **로그인 후 접근**이 맞음(화이트리스트에 넣지 말 것).
  - `get_launcher_webapp_html()` 앱 표면 JS: 하드코딩 `INSTRUMENTS`/`INST_RENDER`/`run*` 함수들 → 매니페스트 fetch + 제네릭 `renderView(view, data)` + `buildAction(template, inputs)` + escape 레지스트리로 교체.
- 데스크탑은 **안 건드림**(1단계 범위 밖).

### 4.6 6개 계기 매니페스트 시드 — 검증된 IBL 코드 + 응답 shape
(2026-06-11 live `/ibl/execute`로 직접 확인. 재검증 불필요. project_id=`앱모드`.)

| 계기 | IBL 코드 | 응답 shape (envelope 주의) |
|---|---|---|
| 날씨 | `[sense:weather]{city:$city, days:7}` | flat: `{city, current{temp,feels_like,humidity,wind_speed,condition}, forecast[{date,max_temp,min_temp,condition,precipitation_mm}]}` |
| 도서 | `[sense:book]{keyword:$q}` | flat: `{count, data[{bookname,authors,publisher,publication_year,bookImageURL,bookDtlUrl,loan_count,isbn13}], message}` |
| 맛집 | `[sense:restaurant]{query:$q}` | flat: `{query, combined[{name,category,address,phone,url,lat,lng}], map_data}` |
| 문화공연(공연) | `[sense:performance]{genre:$genre, keyword:$kw}` · 장르옵션 `[sense:performance]{op:genres}`→`{genres[{code,name,aliases}]}` | flat: `{count, data[{mt20id,prfnm,prfpdfrom,prfpdto,fcltynm,poster,area,genrenm,prfstate}], message}` |
| 문화공연(전시) | `[sense:exhibit]{keyword:$kw}` | flat: `{count, data[{title,startDate,endDate,place,realmName,area,thumbnail,gpsX,gpsY}]}` |
| 투자(검색) | `[sense:stock]{op:search, query:$q}` | **envelope**: `{success, data:{quotes[{symbol,name,exchange,type}]}}` |
| 투자(시세) | `[sense:stock]{op:price, ticker:$sym}` | **envelope**: `{success, data:{current_price,currency,change,change_percent,previous_close,open,high,low,prices[{date,close}]}, summary}` (한국색: 상승=빨강 상승, 하락=파랑) |
| 라디오(목록) | `[sense:radio]{op:korean}` | flat: `{success, count, stations[{station_id,name,broadcaster,description}]}` |
| 라디오(재생/정지) | `[limbs:radio]{op:play, station_id:$id}` / `[limbs:radio]{op:stop}` | **집 PC(서버)에서 재생** — 원격은 홈오디오 제어 의미 |

> ⚠️ 드리프트 교훈: 데스크탑 instrument의 타입 주석을 그대로 믿지 말 것(`[sense:invest]`는 틀렸고 실제 `[sense:stock]`/`[sense:crypto]`, stock 검색은 `quotes`가 아니라 `data.quotes` envelope 안). **매니페스트 작성 시 각 액션을 live 실행해 응답 shape 재확인.**

### 4.7 검증 방법 (1단계 DoD)
- `node --check`로 webapp JS 구문.
- 매니페스트 6개 전부 원격에서 렌더 → 브라우저 스크린샷(자율주행/수동 표면 회귀 없음 포함).
- 의도적으로 매니페스트에 **새 항목 1개**를 추가해 "코드 0줄로 새 앱 등장"을 실증(예: `[sense:weather]` 변형 또는 미사용 액션 하나).
- 인증: 비로그인 터널에서 `/launcher/instruments` 401, 로그인 후 200.

---

## 5. 2단계 — 액션 src 승격 (단일 진실 소스)

### 5.1 목표
1단계에서 굳은 매니페스트를 `ibl_nodes_src` 액션 정의 안으로 옮긴다. 매니페스트 파일은 소멸하고, 액션이 자기 `inputs`/`view`를 선언한다.

### 5.2 작업
- **`ibl_nodes_src` 스키마 확장:** 액션 yaml에 선택적 `app:` 블록(`inputs`, `view`, 선택 `renderer`) 추가. `scripts/build_ibl_nodes.py`가 이를 산출물로 통과시키고, **`--check`에 정합성 규칙 추가**(예: `action` 템플릿의 `$key`가 실제 param에 존재, `view` 경로 형식).
- **자동 파생 엔드포인트:** `GET /launcher/instruments`를 매니페스트 파일이 아니라 `ibl_nodes`에서 `app:` 블록 가진 액션을 모아 생성하도록 전환. → 새 IBL 액션에 `app:`만 달면 원격에 자동 등장.
- **데스크탑 흡수(선택, 별도 결정):** 데스크탑 `ActionDesktop` + 12개 `*Instrument.tsx`도 같은 매니페스트(엔드포인트)를 해석하는 **제네릭 렌더러 1개**로 교체. 진짜 "모든 표면이 한 정의 공유" 달성. escape hatch 계기(지도)는 React 전용 렌더러로 잔류. **범위 크므로 2단계 안에서 다시 쪼갤 것.**

### 5.3 완료 기준
- `app:` 블록 가진 액션이 원격에 자동 노출.
- `--check`가 `app:`–param 정합성까지 검증(드리프트 정적 차단).
- (선택 달성 시) 데스크탑도 같은 소스 해석.

---

## 6. 미해결 결정사항 (착수 시 정할 것)
- **매니페스트 위치(1단계):** `data/instruments.json` 단일 파일 vs 계기별 파일. → 단일 파일로 시작 권장(소수라).
- **`view` 경로 문법:** 간단한 `$.a.b` + 리스트 `from`/`row{template}`로 충분한가, 아니면 조건/포맷터(숫자 toLocaleString, 날짜)가 필요한가. → 1단계에서 최소로 시작, 투자 가격 포맷 정도만.
- **escape 레지스트리 형태:** webapp 내 `CUSTOM_RENDERERS = {id: fn}` 정도.
- **2단계 데스크탑 흡수 여부/시점:** 원격만 제네릭화해도 "새 앱 원천차단"은 절반 달성. 데스크탑까지 갈지는 1단계 결과 보고 결정.

## 7. 범위 밖 / 나중
- 지도 계기(상권·길찾기, Leaflet) — escape hatch로 등록, CDN leaflet 도입 시.
- 신문(`[engines:newspaper]`) — 호스트 파일 경로 생성이라 원격 뷰 엔드포인트 필요(별도 과제).
- 부동산 — 파라미터 多, 어휘 검증 후 추가.
- 차트 고도화 — 1단계는 prices[] SVG 스파크라인까지만.

## 8. 현재 상태 / 시작점 (다음 세션이 콜드로 집어들 지점)
- **원격 런처는 이미 3표면(자율주행/수동/앱)으로 현대화됨** — `backend/api_launcher_web.py` `get_launcher_webapp_html()`(약 44KB 단일 HTML). 앱 표면에 6개 계기가 **하드코딩**돼 있음(`INSTRUMENTS` 배열 + `INST_RENDER` 객체 + `run*`/`loadPrice`/`sparkline` 등 함수). **이 하드코딩을 §4가 대체 대상으로 삼는다.**
- 백엔드 IBL 엔드포인트(`api_ibl.py`): `/ibl/execute` `/ibl/validate` `/ibl/translate` `/ibl/distill` `/ibl/actions/catalog` 전부 존재·검증됨.
- 인증 미들웨어: `api.py:remote_access_guard` + `api_launcher_web.is_external_request/is_public_remote_path/verify_session`. 새 데이터 엔드포인트는 화이트리스트에 넣지 말 것(로그인 요구가 맞음).
- **1단계 첫 행동:** `data/instruments.json` 작성(§4.6 시드) → `GET /launcher/instruments` 추가 → webapp 앱 표면 JS를 제네릭 렌더러로 교체 → 6개 렌더 검증 → "코드 0줄 새 앱" 실증.
- 운영 주의: 백엔드 dev `reload=True` — `backend/*.py` 저장이 reload 유발(과거 1회 전체 다운 경험, 그땐 `cd backend && python3 api.py` + .env 로드로 재기동).
