# 앱모드 렌더 프리미티브 확장 — 핸드오프 (map·video·lightbox + 상호작용 문법)

한 줄: **bespoke 계기가 *반복해서 손으로 다시 짜는* 세 블록(지도·영상·라이트박스)을 선언형 렌더 프리미티브로 승격한다. 빈도가 어휘로 결정화하는 정상 경로이며, 한 번 만들면 commercial·directions가 부산물로 은퇴하고 제3자의 같은 도메인 앱까지 코어 편집 없이 열린다.**

> 작성: 2026-06-28 (측정·코드 grounded). **1·2단계 + commercial 데스크탑 은퇴 + STEP0 클릭스루(버그수정) + STEP1 marker→영상 완료. directions 은퇴=사용자 보류(아키텍처 결정). lightbox=불요(아래 §arc 종결).**

---

## ▶▶ ARC 상태 (2026-06-29 종결 평가) ◀◀

**정당화되는 고빈도 결정화는 완료. 남은 두 항목은 보류/불요로 정리.** 빈도가 어휘를 만든다는 원칙대로, 빈도 없는 건 *안 만드는 것*이 맞다(헌법: apparatus 짓지마·land-grab 금지).

| 항목 | 상태 | 근거 |
|---|---|---|
| 인터랙티브 map(leaflet) | ✅ 완료 | freq 강함(commercial·directions·cctv). 데스크탑 정적+`on:` 인터랙티브 |
| `on:` 뷰-이벤트(moveend 재조회 · marker_click 액션/**stream**) | ✅ 완료 | 상호작용을 데이터로. STEP1 에서 stream 변형 추가 |
| 동적 필터 `filter.from_field` | ✅ 완료(+버그수정) | commercial bespoke 칩 승격. STEP0 에서 rowDrill 인덱스 버그 잡음 |
| marker_click → 영상 | ✅ 완료 | 별도 video 타입 대신 `{stream:true}`(오버레이 재생이 이미 그 역할). CCTV 라이브 검증 |
| **directions 은퇴** | ⏸️ **보류**(사용자 결정 2026-06-29) | 유일 막힘=route+별도CCTV 동시오버레이. 풀려면 ⒜선언형 보조-오버레이 capability(소비자 1개=apparatus) 또는 ⒝navigate_route↔cctv 패키지 결합(독립성 위배). 둘 다 부당 → bespoke 유지. **CCTV가 directions 와 무관하게 가치 생기거나 2번째 소비자 나오면 재개.** |
| **lightbox** | ❌ **불요** | 소비자 0(순신규): commercial 상세=item_click 드릴(STEP0)·image_grid 풀스크린=**이미** `openMediaFromEl`/`mediaOverlay`(api_launcher_web.py:1427)·photo 풍부창=의도된 bespoke 예외. 새 view 타입은 apparatus. |

**결론**: 이 arc 는 *고빈도 블록의 결정화*가 목표였고(§0), 그건 끝났다("0 bespoke"가 목표가 아님). directions 의 닫힌 1개 예외는 정당(§4 "닫힌·작은 예외"). 새 작업은 새 빈도가 나타날 때.

---

## ▶▶ RESUME HERE (2026-06-29 후속: STEP 1 — marker_click→영상 프리미티브 완료 / directions 은퇴는 잔여) ◀◀

STEP 1(`video`)을 **설계 재해석**해서 핵심 조각을 라이브로 박았다. 핸드오프 원안은 `video`를 별도 view 타입으로 등록하자 했으나, **오버레이 재생(원격 `playStream`/hls.js·데스크탑 `StreamPlayer`)이 이미 "video 프리미티브" 역할**을 하고 있었고 *인라인* video 를 쓰는 소비자가 없었다(헌법: apparatus 짓지마·land-grab 금지). 실제 빈도가 정당화하는 결손은 **마커 클릭 → 영상**(directions 가 bespoke 로 갖는 바로 그 동작)이라, 새 view 타입 대신 **`on: {marker_click: {stream: true}}` 문법 변형**을 추가했다.

### ✅ `marker_click: {stream: true}` — 마커 클릭으로 영상 재생 (3-동기, 라이브)
지도 마커 클릭의 두 의미를 분기: **IBL 템플릿(문자열)=재조회**(기존) vs **`{stream: true}`=마커 url 을 클라이언트 영상 재생**(신규, IBL 0). CCTV 가 첫 소비자.
- **체커**(`build_ibl_nodes.py`): `_app_check_view` 의 `on` 루프에서 `marker_click` 값이 dict 면 `{stream: true}` 만 허용(그 외 키 RED), 아니면 기존대로 IBL 문자열. `_app_action_templates` 는 dict 값을 자동 무시(템플릿 아님→참조검증 면제). `APP_VIEW_EVENTS` 주석에 stream 변형 명기.
- **데스크탑**(`GenericInstrument.tsx` `MapPrim`): `onStream` prop 추가(ViewPrim→MapPrim 배선). `clickSpec=on.marker_click` 를 `clickStream`(객체+stream) vs `clickTpl`(문자열)로 분기 — stream 이면 마커 클릭이 `onStream(item)`(행 데이터 url/playable/name/lat/lng → 기존 `StreamPlayer` 오버레이, list '▶보기'와 동일 경로). **★`interactive`(viewport 보존=첫 로드만 fit) 재정의**: 이전 `!!on` → **`on.moveend||on.center_drag` 유무**. marker_click 만으론 *이동-재조회*가 없어 정적 fit 유지해야 CCTV 가 매 검색마다 새 결과로 재fit 됨(안 그러면 첫 검색 viewport 에 갇힘).
- **원격**(`api_launcher_web.py` `initMaps`): `clickStream` 분기 — 마커에 `mk.on('click',()=>playStream(i))`(url 을 `_streamUrls` 에 push). **★stream 클릭은 `_mapKeepView` 를 안 건드림**(재렌더·재조회 없음=오버레이만) → CCTV 재검색 재fit 무영향.
- **CCTV app 블록**(`sense.yaml`): map 에 `'on': {marker_click: {stream: true}}` 추가(YAML 1.1 함정 회피 위해 `'on':` 따옴표). 목록 '▶ 보기'(stream:true)와 *같은* 스트림, **진입점만 마커로 확장**.

### 검증 (이번 턴, 원격 라이브 + 데스크탑 코드)
- **build --check 142 GREEN**(체커가 marker_click 객체형 수용)·바이트 일치·phone_manifest 일치 / **서빙된 원격 JS node --check OK**(clickStream 반영).
- **원격 라이브**(8765/launcher/app via preview 브라우저): CCTV 해운대 auto_run → 마커 10·`_streamUrls` 10. **마커 클릭 → `#streamVideo` 오버레이 + 실제 스트림 URL**(`cctvsec.ktict.co.kr/...` KT ICT, marker[0].url 일치) 재생. **무회귀**: 목록 '▶ 보기' 버튼도 여전히 스트림 오픈·`closeStream` 오버레이 `display:none` 정상. commercial(moveend·marker_click 없음)은 STEP 0 에서 검증·이번 분기는 else(팝업) 불변.
- **데스크탑**: CORS(5199 미허용)·5173 타 챗 점유로 라이브 보류. 단 marker→`onStream`→`StreamPlayer` 는 list '▶보기' 가 쓰는 *동일* 검증된 경로(신규 코드 0의 재사용)라 코드상 안전.
- **tsc ✅ GREEN(2026-06-29 정정·수정)**: 내 변경(MapPrim·ViewPrim) 타입 클린. ★처음엔 3 에러를 "타 챗 미완 리팩터"로 *오귀속*했으나 **git으로 전부 HEAD 베이스라인 에러로 판명**(DirectionsInstrument git-clean인데 에러 / GenericInstrument modes·compose는 diff에 없고 HEAD에 동일하게 깨짐). 즉 프로젝트 tsc가 원래 클린이 아니었음. **3개 모두 최소·동작보존 수정**: DirectionsInstrument:36 `summary.fare?` 옵셔널 추가 / GenericInstrument:977 `(mode as {modes?})` 구조캐스트(런타임상 mode=instrument일 수 있어 항상 undefined=동작불변) / :928 `extra: Record<string,string>` 명시. tsc 0 errors.

### ⏳ 잔여 = directions 은퇴 (이번 턴 미완 — 구조적 선결 있음)
marker→영상 배관은 섰지만 **directions 은퇴는 못 했다.** `DirectionsInstrument`(378L) 가 app 블록이 *표현 못 하는* 기능을 가짐:
1. **route 지도 + 별도 CCTV 마커 *동시* 오버레이** — 핵심 막힘. 현 MapPrim 은 `from: map_data`(경로) **또는** `markers: <한 리스트>` 를 그리는데, directions 는 *경로(navigate_route 결과)* 위에 *별도 쿼리한 CCTV* 를 얹는다. 선언형 모델은 모드당 액션 1개라 "두 번째 쿼리를 지도에 오버레이"가 없음. → **선결 = ⒜navigate_route 가 map_data.markers 에 주변 CCTV 를 번들(백엔드 결합) 또는 ⒝app 블록에 '보조 마커 쿼리' capability 신설** 둘 중 하나. 큰 결정이라 별도 턴.
2. 지도 클릭으로 출발/도착 찍기 → 텍스트 입력으로 단순화(핸드오프 수용). 우리집 localStorage → 소소(text default 로 대체 가능).
- 경로 지도·요약·안내는 directions app 블록(`sense.yaml` navigate_route, `type:map from:map_data`+metric+kv_list)에 *이미* 있음. CCTV 오버레이(1번)만 풀면 realty 선례로 은퇴.
- ★이제 마커가 영상을 열 수 있으니, CCTV 마커를 directions 지도에 얹기만 하면 `'on': {marker_click: {stream: true}}` 한 줄로 영상까지 따라온다.

### 이번 세션 변경 파일 (STEP 1)
| 파일 | 변경 |
|---|---|
| `scripts/build_ibl_nodes.py` | `_app_check_view` on 루프: marker_click `{stream:true}` 객체형 허용(그 외 키 RED) + APP_VIEW_EVENTS 주석 |
| `frontend/src/components/GenericInstrument.tsx` | `MapPrim` onStream prop + clickStream/clickTpl 분기 + `interactive=moveend/center_drag 유무`(재정의) + fireMove/effect `on` 캐스트 + ViewPrim→MapPrim onStream 배선 |
| `backend/api_launcher_web.py` | `initMaps` 마커 clickStream 분기(playStream, _mapKeepView 면제) |
| `data/ibl_nodes_src/sense.yaml` (+빌드산출) | cctv map 에 `'on': {marker_click: {stream:true}}` |

→ **다음 = directions 은퇴(위 §잔여 1번 선결부터)** · 그 후 `lightbox`(4단계).

---

## ▶▶ RESUME HERE (2026-06-29: STEP 0 라이브 클릭스루 완료 + 실버그 1건 수정) ◀◀

지난 세션이 보류한 **STEP 0(진짜-DOM 클릭스루 1바퀴)**를 원격 표면에서 완수했고, **그 과정에서 실제 회귀 버그 1건을 잡아 고쳤다.** 라이브 검증이 단위테스트가 못 덮은 곳을 정확히 짚은 사례.

### ✅ STEP 0 — 원격 commercial 라이브 클릭스루 3검증 PASS
preview MCP가 5173/3000(타 챗 점유)·5199(CORS 미허용)에 못 붙는 제약은 **백엔드가 직접 서빙하는 `http://127.0.0.1:8765/launcher/app`(동일 origin, CORS 무관)로 preview 브라우저를 `location.href` 이동**시켜 우회했다(향후 원격 검증의 정답 경로). 격리 vite(`frontend-iso`, 5199)는 8765로 네비게이트하는 *브라우저 셸*로만 씀.
- **ⓐ 업종 칩 → 그 업종만, 재조회 없이, viewport 보존**: 한식 칩 → 마커 1500→441·첫 카드 진흥공조→돈가네·**메트릭 6385 유지**(클라이언트 필터=재조회 아님 확증)·지도 재생성됐지만 `_mapKeepView`로 center/zoom 동일·`_LMAPS` 1개(누수 0). ✓
- **ⓑ 가게 카드 → restaurant 드릴 → 복귀**: (버그 수정 후) 한식 필터 상태에서 돈가네 클릭 → 돈가네 교대점·김치찌개(☎·카카오 링크)로 정상 드릴 → ‹목록으로 복귀. ✓
- **ⓒ 지도 팬 → 재조회 시 칩 초기화**: 한식 필터 → 삼성동으로 setView → moveend 재조회(11764개)→ 칩 전체로 리셋. ✓
- **CCTV 무회귀**: 같은 렌더러로 CCTV 계기 정상 오픈(크래시 0). 8765 원격 페이지 콘솔 에러 0(leaflet·rowDrill 무에러).

### 🐞 잡아 고친 버그 — 동적필터 활성 시 item_click 이 *원본 인덱스*로 드릴 (원격 전용)
**증상**: 한식으로 필터한 뒤 첫 카드(돈가네)를 누르면 *필터 전* 원본 목록의 첫 항목(진흥공조)으로 드릴됨. 필터 없을 땐 정상(돈가네→돈가네).
**원인**(`api_launcher_web.py` `rowDrill`): 카드는 `renderView(view, applyCatFilter(mode,data))`로 **필터된 배열**을 렌더해 `ri`(행 인덱스)가 필터 기준인데, `rowDrill`은 `viewList(src.data,...)[ri]` 로 **원본** `src.data`를 인덱싱 → 필터 활성 시 어긋남.
**수정**: rowDrill 의 item 조회를 `const drillData = SPLIT ? src.data : applyCatFilter(CUR.mode, src.data);` 후 `viewList(drillData,...)[ri]` 로 변경(비분할만 필터 적용, split=master_detail 은 동적필터 없음). 필터 비활성이면 applyCatFilter 가 데이터 그대로 반환 → 무필터·CCTV·realty 동작 불변.
**검증**: 라이브 재현→수정→라이브 재검(돈가네→돈가네) / build --check 142 GREEN·바이트 일치·phone_manifest 일치 / 서빙된 원격 JS node --check OK.

### 데스크탑은 *구조적으로* 이 버그 없음 (코드 검증)
`GenericInstrument.tsx`의 드릴은 인덱스가 아니라 **항목 객체 자체**를 넘긴다 — `<Card onClick={() => onDrill(p, it)}>`(629행, 매핑된 `it` 클로저)·비분할 ViewRenderer는 `viewData`(필터된) 매핑. 객체-기반이라 인덱스 불일치가 발생 불가. (라이브 미실행 이유=React 앱 5199가 CORS로 8765 미도달, 5173은 타 챗 점유. 코드상 명백히 안전.) **남은 데스크탑 라이브 1바퀴는 5199를 ALLOWED_ORIGINS에 넣고 백엔드 재시작하면 가능** — 단 8765 공유 인프라라 타 챗 영향 주의.

### 이번 세션 변경 파일
| 파일 | 변경 |
|---|---|
| `backend/api_launcher_web.py` | `rowDrill` item 조회를 `applyCatFilter` 적용 후 인덱싱(동적필터+드릴 인덱스 버그 수정, 2024행대) |

→ **STEP 0 완전 종료. 다음 = STEP 1(`video` 프리미티브 + directions 은퇴), 아래 §3.**

---

## ▶▶ RESUME HERE (2026-06-28 후속: commercial 데스크탑 은퇴 = 검증1 완료) ◀◀

### ✅ 동적 필터 capability `filter.from_field` 신설 (3-동기, 라이브)
정적 필터(`filter.items`=재조회 칩)와 별개로 **결과-필드 파생 동적 필터**를 추가했다 — 결과 items 의 한 필드 distinct 값으로 칩 생성 + **클라이언트 측 거르기(재조회 없음)**. bespoke `CommercialInstrument` 의 `cats=Array.from(new Set(...))` 칩을 선언으로 승격.
- **체커**(`build_ibl_nodes.py`): `_app_check_filter_block` 신설(filter=items XOR from_field, from=배열경로). from_field 필터는 재조회 $key 없음 → input_keys 합류 안 함(정적 filter 만 합류).
- **데스크탑**(`GenericInstrument.tsx`): `AppFilter.from_field?/from?` + ModePane 에 `catFilter` state. `dynCats`(distinct)·`activeCat`(없으면 자동 null)·`viewData`(필터 적용된 `{...data, items: filtered}`) 파생 → 비분할 ViewRenderer 에 `viewData` 주입(map 마커·card_list 동시 거름). 칩 클릭=state 만(지도 재생성 없음=viewport 자동 보존, didFit 가드). 재조회(run/onViewEvent/모드변경) 시 catFilter 초기화.
- **원격**(`api_launcher_web.py`): `dynFilterOf`/`applyCatFilter`/`renderDynFilter`/`renderModeBody`/`setCatFilter`. runMode 비분할·mapViewEvent(refresh==='mode')가 `renderModeBody` 공유. setCatFilter 는 재렌더 전 `_mapKeepView` 캡처(원격은 재렌더가 지도 재생성 → viewport 보존 필요, 데스크탑과 비대칭). **★칩 값은 `data-c` 속성(esc)+`getAttribute` 로 읽어 onclick 인라인 따옴표 이스케이프 회피**(setFilter `\\'` 관례의 함정 회피).

### ✅ 가게 상세 = 기존 `item_click` 드릴 재사용 (렌더러 무변경)
commercial card_list 에 `item_click: {action: '[sense:restaurant]{query:"{name}", x:{lng}, y:{lat}, radius:300}', view: [card_list(맛집 name/category/☎phone/카카오 링크)]}`. bespoke 의 가게 상세 모달(카카오 평점·전화 enrichment)을 드릴로 대체. **양 렌더러의 item_click 경로가 이미 검증돼 있어 신규 코드 0**(realty/messenger 선례).

### ✅ commercial 데스크탑 은퇴 배선 (realty 선례)
`ActionDesktop.tsx`: STATIC_DOMAINS commercial 줄에서 `el` 제거(타일 유지) + realty 주입 블록을 일반화(`manById` 로 realty·commercial 둘 다 manifest→GenericInstrument 주입). `CommercialInstrument.tsx`(268L) **삭제** + import 정리. 맥·폰·원격이 단일 app 선언 공유(드리프트 근절).

### 검증 (이번 턴)
- **build --check 142 GREEN**(체커가 filter.from_field·item_click·on 검증, 바이트 일치) / **tsc 0** / python ast OK / **node --check on 디코딩된 원격 JS(75KB) OK**.
- **원격 동적-필터 로직 단위검증**(Node, 실데이터 형태): distinct dedup(한식 1회·null 드롭)·HTML escape(`광고&빛`→`광고&amp;빛`)·`applyCatFilter('한식')`=A,C+total_count 보존·null passthrough=동일 ref.
- **라이브 데이터 종단**: `[sense:commercial]{강남,radius:300}`=3285건 category distinct(본사·경영컨설팅 382/의원 323/한식 152…) / `[sense:restaurant]{본죽,…}`=카카오+네이버 6건 place.map.kakao.com 링크·전화. 백엔드 핫리로드로 새 원격 JS 서빙 확인(함수 10회).
- **⏳ 미실행 = 진짜-DOM 클릭스루**(칩 클릭→필터·드릴→상세, 데스크탑/원격 브라우저): 이번 턴 인프라 제약(다른 챗이 Vite/preview 포트 점유 + Chrome 확장 미연결)으로 보류. 로직은 위 단위검증·tsc·node로 덮였으나, 다음 세션에서 라이브 1바퀴 권장(§0 viewport 40px·leaflet 합성이벤트 함정 주의).

### 이번 세션 변경 파일·좌표 (다음 세션 재발견 없이)
| 파일 | 변경 | 핵심 심볼 |
|---|---|---|
| `data/ibl_nodes_src/sense.yaml` | commercial app: `filter: {from_field: category}` + card_list `item_click`(restaurant 드릴) | 903행 commercial 블록 |
| `data/ibl_nodes.yaml` / `phone_manifest.json` | 빌드 산출(★src 수정 후 `python3 scripts/build_ibl_nodes.py` 필수 — 안 하면 매니페스트 안 바뀜) | — |
| `scripts/build_ibl_nodes.py` | `_app_check_filter_block` 신설 + filter 블록 검증 합류 + from_field 면 input_keys 미합류 | `_app_check_filter_block`, 블록루프 `_pd` 분기 |
| `frontend/src/components/GenericInstrument.tsx` | `AppFilter.from_field?/from?` · `catFilter` state(3곳 reset: run/onViewEvent/모드변경) · `dynField/dynCats/activeCat/viewData` 파생 · 동적칩 JSX · 비분할 ViewRenderer 가 `viewData` 사용 | `ModePane`, `viewData` |
| `frontend/src/components/ActionDesktop.tsx` | import 제거 · STATIC_DOMAINS commercial `el` 제거 · realty 주입블록을 `manById` 일반화(realty+commercial) | `DOMAINS` useMemo 118행대 |
| `frontend/src/components/CommercialInstrument.tsx` | **삭제**(268L) | — |
| `backend/api_launcher_web.py` | `dynFilterOf/applyCatFilter/renderDynFilter/renderModeBody/setCatFilter` 신설 · runMode 비분할·mapViewEvent(refresh==='mode')·setMode 통합 | renderView 직후 블록 |

### 다음 세션 STEP 0 — 보류한 라이브 클릭스루 1바퀴 (먼저)
무엇을: **데스크탑·원격에서 commercial 을 열어** ⓐ업종 칩 클릭→목록·지도 마커가 그 업종만 남는지(재조회 없이, 지도 viewport 보존) ⓑ가게 카드 클릭→restaurant 드릴(카카오 링크·☎)로 들어갔다 '‹ 목록으로' 복귀 ⓒ지도 팬→재조회 시 칩 초기화. **CCTV·realty 무회귀**.
- **데스크탑 도달**: 이번 턴엔 다른 챗이 Vite(5173)+preview(3000) 점유라 막혔다. 방법 = ⒜그 챗 종료 후 `npm run dev`(frontend) 직접 + 브라우저 5173 → 앱 탭 → 부동산 → 상권. 또는 ⒝Electron 이미 떠 있으면 그 창에서 바로(HMR 반영). app/preview 둘 다 백엔드 8765(상시 ON)를 IBL_ENDPOINT 로 씀.
- **원격 도달**: 백엔드가 직접 서빙 → `http://127.0.0.1:8765/launcher/app` 를 브라우저(또는 Chrome MCP)로 열면 됨. preview MCP 는 8765 가 비-preview 서버라 못 잡음 → **그냥 브라우저로 URL 열기**가 정답. (Chrome 확장 연결돼 있으면 navigate → read_page/click 으로 자동 검증 가능.)
- **§0 함정 재확인**: 프리뷰 viewport 40px 접힘(→resize+새로고침)·leaflet 합성이벤트는 인터랙션 못 깨움(→`window.__testMap.setView()` 또는 실드래그)·commercial 6385 느린 로드(→READY 폴링 후 검증). 검증 끝나면 임시 노출 제거.
- 클릭스루에서 버그 없으면 = commercial 은퇴 *완전* 종료. 그다음 STEP 1(video).

### 재사용 메모 — `filter.from_field` 는 commercial 전용 아님
결과에 분류 필드가 있는 **모든 app: 블록**이 한 줄로 동적 필터를 얻는다(`filter: {from_field: <필드>, from: <배열경로, 기본 items>}`). 후보=culture(genre)·shopping(브랜드)·book(분류) 등. 정적 `filter.items`(재조회)와 상호배타(체커가 강제). 빈도가 차면 결정화하되 land-grab 금지.

---

---

## ▶▶ RESUME HERE (2026-06-28 1·2단계 완료) ◀◀

### ✅ 1단계 — 데스크탑 정적 `map` 분기 신설 (라이브·검증)
**데스크탑 `GenericInstrument.tsx`가 이제 `type: map`을 그린다.** 이전엔 type 분기에 map이 없어 데스크탑에서 type:map 앱블록이 *아무것도 안 그렸다*(§1 비대칭의 핵심) — 이제 원격(api_launcher_web `initMaps`)과 동치.
- **변경(GenericInstrument.tsx, 4곳)**: ①`import L from 'leaflet'` + `leaflet/dist/leaflet.css` ②AppViewPrim union 에 `'map'` 추가 ③`MapPrim` 컴포넌트 신설(useRef+useEffect, 원격 initMaps 충실 이식: `p.from`(기본 map_data) 봉투의 center/path/origin/destination + `p.markers` 리스트(items)→마커, `p.max` 상한, fitBounds/center 폴백) ④ViewPrim 에 `if (p.type === 'map') return <MapPrim …>` 분기.
- **마커 아이콘**=이미지 의존 없는 `L.divIcon`(DirectionsInstrument `dotIcon` 선례 — 번들러 아이콘 깨짐 회피). popup 텍스트는 `escHtml`.
- **검증(브라우저 프리뷰, 데스크탑)**: 앱모드 → 📹CCTV 계기(이미 GenericInstrument 경로 — STATIC_DOMAINS/OVERRIDES 어디에도 없음, 그래서 step1의 무위험 검증 대상). `[sense:cctv]{op:search, query:해운대}` auto_run → **leaflet 지도(높이 320px) + 마커 10개**(items 10건 일치) + "검색 결과 10개" metric + list_action ▶보기. tsc 0 err·콘솔 에러 0. **이전엔 이 자리가 빈 칸이었음.**
- **체커·build 무변경**: `map`은 이미 `APP_VIEW_TYPES`에 등록돼 있었음(원격이 이미 씀). src yaml·build_ibl_nodes 미변경. video/lightbox/on 추가는 2~4단계 소관.

### ✅ 2단계 — `on:` 뷰-이벤트 문법 + map 인터랙티브화 (라이브·검증, 양 렌더러)
**`on:` 문법 신설 = 상호작용을 데이터로.** map 프리미티브가 사용자 조작(지도 이동·마커클릭)을 액션 템플릿+페이로드로 흘려 재조회한다.
- **체커**(`build_ibl_nodes.py`): 상수 `APP_VIEW_EVENTS={marker_click,moveend,center_drag}`·`APP_EVENT_VARS={lat,lng,id,name,radius,url}` 신설. `_app_check_view` 가 map 프리미티브의 `on`(event→IBL 템플릿) 검증·`_app_action_templates` 가 on 템플릿의 `[node:action]` 실존 검증·`_block_local_keys` 가 이벤트 변수를 `$key↔input` 검사에 합류(이벤트가 `$lat/$lng/$radius` 등 주입). **★APP_KEYS 불변**(on 은 *뷰-항목* 키지 app-레벨 키 아님).
- **★YAML 1.1 함정 가드**: `on:` 무인용 키는 불리언 `True` 로 파싱돼 조용히 무시됨(매니페스트에 `'true'` 키로 샜다). 소스 YAML 은 `'on':` 따옴표 필수 + 체커가 view 프림의 불리언 키(`True in p`)를 RED 로 잡도록 추가(재발 방지).
- **데스크탑**(`GenericInstrument.tsx` `MapPrim`): 정적→인터랙티브로 확장. 지도 1회 생성(data 변경에도 재생성 안 함=viewport 보존)·마커는 layerGroup in-place 갱신·`moveend`(디바운스 600ms)→`onViewEvent`→재조회·`marker_click`→액션. **★피드백 루프 가드=`readyRef`**(초기 fit 정착 후 700ms 에 true → 프로그래매틱 fit 의 moveend 는 무시). 재조회는 `loading` 안 켬(지도 언마운트 방지)·`didFit` 로 인터랙티브는 첫 로드만 fit(이후 viewport 보존). `onViewEvent` 를 ViewPrim/ViewRenderer 통해 ModePane 까지 배선.
  - ★함정(실측): 초기 `progMove` 불리언 가드는 React StrictMode 이중마운트/재렌더에서 true 에 stuck → 재조회 영영 안 됨. `readyRef`(시간 기반)로 교체해 해결.
- **원격**(`api_launcher_web.py` `initMaps`): 같은 `on` 의미. `mapViewEvent(tpl,payload)` 가 재조회 후 view 재렌더·`_mapProg`(프로그래매틱 가드)+`_mapKeepView`(재렌더 너머 viewport 보존). marker_click 바인딩. **+지도 누수 수정**: 재렌더로 분리된 옛 leaflet 지도를 initMaps 시작부에서 `.remove()`(데스크탑 useEffect cleanup 의 원격판 — 안 하면 _LMAPS 누적 + 전역 가드 간섭).
- **commercial app 블록**(`sense.yaml`): map 에 `'on': {moveend: '[sense:commercial]{lat:"$lat",lng:"$lng",radius:"$radius"}'}` 추가(지도 viewport 가 입력=lat/lng 텍스트박스 대체)·max 200→1500.
- **검증**: build --check 142 GREEN(체커가 on 검증) / tsc 0 / **원격 라이브**: commercial 강남(6385)→부산 팬→재조회 4131, viewport 보존, 누수 0(라이브 지도 1), 루프 0 / **데스크탑 라이브**(throwaway unmask): 강남(6385)→부산 setView→`moveend ready=true`→`fireMove`→재조회 4886, viewport 보존, 루프 0 / CCTV 정적 무회귀.

### ⏳ 다음 = commercial *데스크탑* 은퇴(검증1 잔여) + video/lightbox(3·4단계)
**commercial 은퇴는 보류**(이번 턴 미실행) — 이유: bespoke `CommercialInstrument` 는 선언형 app 블록에 *없는* 두 기능을 더 갖는다 → 지금 은퇴하면 **회귀**:
  1. **업종(category) 필터 칩** — 결과에서 *동적 파생*(declarative `filter` 는 정적 칩만 — 새 capability "결과-필드-파생 필터" 필요).
  2. **가게 상세 모달**(`[sense:restaurant]` 카카오 평점 enrichment) — `card_list`+`item_click` 드릴로 재현 가능(기존 어휘).
→ 무회귀 은퇴 = ①동적-필터 capability + ②detail 드릴 작성 후 realty 선례(`ActionDesktop` 118–128 주입 + bespoke 삭제). 그 전엔 remote=인터랙티브 선언형 / desktop=bespoke 의 *기존* 드리프트 유지(무해, app 블록은 이미 준비됨).
**그 다음 = `video`(3단계, HLS·directions 은퇴)·`lightbox`(4단계).** marker_click 문법은 이미 섰으니 video 프리미티브가 생기면 `marker_click: '[sense:cctv]{op:stream,id:"$id"}'` 가 바로 붙는다.

---

## ▶ 다음 세션 실행 계획 (상세 — 재발견 없이 바로) ◀

### 0. 먼저 읽고 시작 — 이번 세션에 *피 흘려 얻은* 함정 (반복 금지)
- **YAML `on:` = 불리언**: 소스 yaml 에서 뷰-이벤트 키는 **반드시 `'on':`**(따옴표). 무인용이면 YAML 1.1 이 `True` 키로 파싱→매니페스트에 `'true'` 로 새고 인터랙티브 조용히 죽음. 체커가 이제 `True in p` 로 잡지만(RED), 새 yaml 작성 시 처음부터 따옴표.
- **데스크탑 인터랙티브 가드는 `readyRef`(시간 기반)이지 `progMove`(불리언) 아님**: React StrictMode 이중마운트에서 불리언 가드는 stuck 된다. 새 인터랙티브 프리미티브도 "초기 프로그래매틱 정착 후 ready" 패턴 쓸 것.
- **프리뷰 검증 함정 4종(실측)**:
  1. **합성 이벤트(click/wheel/mousedown)는 leaflet 인터랙션을 못 깨운다** → 지도 재조회 검증은 ⒜라이브 map 인스턴스를 임시 `window.__testMap=map` 노출 후 `.setView()` 호출(진짜 moveend) 또는 ⒝READY 로깅을 폴링 후 setView. 검증 끝나면 노출 *반드시 제거*.
  2. **`_LMAPS`(원격)는 재렌더로 옛 지도 누적** → 테스트가 `Object.keys(_LMAPS)[0]`(죽은 지도) 잡으면 거짓 실패. `document.body.contains(m.getContainer())` 로 라이브만. (이번에 purge 추가했으니 이제 1개 유지.)
  3. **프리뷰 뷰포트가 ~40px 로 접히는 일** 발생 → ModePane 전체 40px·지도 width 0. `preview_resize {width:1280,height:820}` 후 **페이지 새로고침**(리사이즈만으론 reflow 안 됨).
  4. **commercial 6385 카드 렌더가 느려 auto_run/맵 마운트가 늦다** → 검증 setView 를 너무 일찍 하면 READY 전이라 무시됨. `window.__md`(또는 READY 신호) 폴링 후 진행.
- **백엔드 reload**: `api_launcher_web.py`·`sense.yaml`(빌드 후)는 uvicorn `--reload`(reload_delay 2s)로 자동 반영. 원격 HTML 은 `/launcher/app`(라우터 prefix `/launcher`). 매니페스트 `/launcher/instruments`.

### 1. (선택) 간단 소품 — CCTV 지도 마커 클릭 → 스트림 재생
현재 CCTV 목록의 "▶ 보기"(stream:true)는 StreamPlayer 를 열지만 **지도 마커 클릭은 무동작**. 마커 클릭으로도 재생되게.
- **설계 결정 필요**: `marker_click` 의 두 의미 분기 — ⒜IBL 액션(현재, onViewEvent 재조회) vs ⒝클라이언트 스트림(StreamPlayer, IBL 없음). CCTV 스트림은 *클라이언트 측*(행의 url/playable/stream_type → StreamPlayer)이라 IBL 액션이 아님.
- **제안**: 마커가 스트림 행이면(`playable`/`stream_type` 보유) marker_click 을 `onStream(markerRow)`(데스크탑) / `playStream`(원격)로 라우팅. app 선언은 예: `'on': {marker_click: {stream: true}}`(IBL 템플릿 대신 `{stream:true}` 객체) — 체커에 이 변형 허용 추가. 또는 더 단순히 map 프리미티브에 `marker_stream: true` 플래그.
- **검증**: CCTV(이미 데스크탑 GenericInstrument) 마커 클릭 → StreamPlayer 오버레이. 무위험(CCTV 단일계기 도메인이라 viewport 함정 없음).
- 규모: 작음(반나절). 단 marker_click 의미 분기 설계가 핵심.

### 2. commercial 데스크탑 은퇴 — *무회귀* 조건 (검증1 완성)
**선결 2개 없으면 회귀**(bespoke `CommercialInstrument.tsx` 가 가진 것):
- **(a) 업종 동적 필터** — bespoke 는 결과 `items` 의 `category` 들로 칩을 *동적* 생성(148행 `cats=Array.from(new Set(...))`). 선언형 `filter` 는 정적 칩뿐. → **새 capability**: app `filter` 에 `from_field: category`(결과-필드 파생) 추가. 렌더러(양쪽)가 현재 data 의 그 필드 distinct 값으로 칩 생성 + 선택 시 *클라이언트 측* items 필터(재조회 아님 — 같은 결과 내 거르기). 체커: `filter` 에 `from_field` 허용.
- **(b) 가게 상세 모달** — bespoke 는 가게 클릭 → `[sense:restaurant]{query,x,y,radius}` → 카카오 평점 링크/전화(`runRestaurant` 41행, kakao place URL 우선). → `card_list` + `item_click` 드릴: `item_click: {action: '[sense:restaurant]{query:"{name}", x:{lng}, y:{lat}, radius:300}', view: [kv/카드 + 링크]}`. **단 map 마커엔 item_click 없음** — 드릴은 카드 목록 경유(또는 marker_click 을 드릴로 — 1번 의미 분기와 합류). restaurant `combined` 통화 형태 확인 필요.
- **(c) 은퇴 배선**(realty 선례 = `ActionDesktop.tsx`): STATIC_DOMAINS 의 commercial 줄(41행)은 *유지*하되 `el` 제거, useMemo(118–128 realty 주입 블록)에 commercial 도 `el: <GenericInstrument instrument={commInst}/>` 주입. 그 후 `CommercialInstrument.tsx` 삭제 + import(11행) 정리.
- **검증**: 부동산 도메인 안 상권 = 인터랙티브 지도(드래그 재조회) + 동적 업종 칩 + 가게 드릴 상세. CCTV·realty 무회귀. (★프리뷰 viewport 40px 함정·6385 느린 로드 주의 — §0.)
- **참고**: commercial app 블록은 이미 `'on':moveend` + max1500 준비됨(이번 세션). 남은 건 filter(a)·item_click(b)·은퇴배선(c).

### 3. `video` 프리미티브 (HLS) + directions 은퇴
- **video 프리미티브**: `APP_VIEW_TYPES` 에 `video` 추가(체커). 양 렌더러:
  - 데스크탑: 기존 `StreamPlayer`(`./StreamPlayer`, GenericInstrument 이미 import) 재사용 — `video` 프림이 `{src|from}` 의 스트림을 인라인/오버레이 재생.
  - 원격: 기존 `playStream`/hls.js(`api_launcher_web` 이미 `_streamUrls`·hls CDN). `video` 프림 렌더.
- **marker_click → video 통합**: 2단계의 marker_click 이 이미 액션을 흘린다. CCTV 스트림이 클라이언트라면 1번의 `{stream:true}` 변형, IBL 액션화하려면 `[sense:cctv]{op:stream}` 액션 신설(현재 없음 — 확인). 핸드오프 원안은 `marker_click: '[sense:cctv]{op:stream,id:"$id"}'` → video 프림.
- **directions 은퇴**(= commercial 급 패리티): `DirectionsInstrument.tsx`(378L) = 경로 폴리라인(navigate_route map_data.path) + 출발/도착 지오코딩 입력 + CCTV 마커(`[sense:cctv]`) + StreamPlayer. directions app 블록(`sense.yaml` navigate_route, 이미 `type:map from:map_data` + metric 보유)에 CCTV 마커 + video 통합 후 realty 선례로 은퇴. **경로형 지도는 이미 MapPrim 이 path/origin/destination 그림**(2단계서 이식 완료) — 남은 건 CCTV 마커 오버레이 + video.
- **사전 확인(원안 미해결)**: GenericInstrument 에 `<video>` 썸네일 분기 있는지(없음 확정적). image_grid 동영상 썸네일은 `mediaSrc`+`/photo/video-thumbnail` 경유(photo 한정).

### 4. `lightbox` 프리미티브 (풀스크린 상세/이미지)
- `APP_VIEW_TYPES` 에 `lightbox` 추가 **또는** `image_grid` 에 fullscreen 옵션. 카드/마커 클릭 → 풀스크린 오버레이(이미지 줌·상세 필드).
- 소비자: commercial 가게 상세(2b 와 합류 가능)·photo 풍부창 라이트박스(별개·저우선).
- 데스크탑은 이미 `image_grid` 클릭 → 원본/동영상(`openMediaFromEl`, 원격) 패턴 일부 있음 — 통일.

### 5. 3-동기 + 코드 좌표 (현재값)
프리미티브/문법 하나당 **세 곳 항상 동기**:
1. `scripts/build_ibl_nodes.py` — `APP_VIEW_TYPES`(674행 근처)·`APP_VIEW_EVENTS`·`_app_check_view`(프림 검증)·`_app_action_templates`·`_block_local_keys`.
2. `frontend/src/components/GenericInstrument.tsx`(현재 ~1100L) — `AppViewPrim` union·`ViewPrim` 분기·프림 컴포넌트·`ViewEvent`/`onViewEvent` 배선(ViewPrim/ViewRenderer/ModePane).
3. `backend/api_launcher_web.py` — `renderPrim`(프림 HTML)·`initMaps`(map)·`mapViewEvent`(재조회).
- **MapPrim**(GenericInstrument): 인터랙티브 지도 레퍼런스 구현 — 새 인터랙티브 프림의 `readyRef`/`didFit`/`onViewEvent` 패턴 복제.
- bespoke(은퇴 대상): `CommercialInstrument.tsx`(268L)·`DirectionsInstrument.tsx`(378L). 배선: `ActionDesktop.tsx:41`(commercial el)·`:64-69`(directions 도메인)·`:118-128`(realty 주입 선례).

---

## 0. 왜 지금 (빈도 = 결정화 신호)

bespoke 계기들이 *같은* 빌딩블록을 재구현하는 빈도를 측정함(frontend/src/components/*Instrument*.tsx 전수):

| 블록 | 재구현하는 bespoke | 신호 |
|---|---|---|
| **인터랙티브 지도**(leaflet) | CommercialInstrument(268L)·DirectionsInstrument(378L) + *은퇴한 realty-풍부판·cctv·photo 지도* | ★강함 |
| **영상/스트림**(HLS) | DirectionsInstrument(CCTV StreamPlayer) | 중 |
| **라이트박스/풀스크린 상세** | CommercialInstrument(점포 상세 팝업) + *photo 풍부창* | 중 |

**규칙(헌법)**: bespoke ≥2가 같은 블록을 재구현 = 프리미티브로 승격(비용이 여러 케이스 + 미래 제3자 도메인에 분산). 빈도 1은 bespoke 유지. → **out of scope**: `calendar`(CalendarInstrument 1곳뿐, freq=1)·오디오(신호 0, ytmusic도 raw audio 안 씀). `chart`/`sparkline`은 *이미* 이 길로 어휘가 된 선례.

근본 동기: 통화(items)·preload와 같은 **좁은 허리** — 도메인은 데이터(`app:` 블록)에, 렌더러는 중립. 지금은 인터랙티브 UX가 전부 프론트 코어(ActionDesktop)로 샌다.

---

## 1. ★현재 상태 (grounded·verified) — 비대칭이 핵심

> ⚠️ **이 §1 표는 작업 *시작 전* 스냅샷이다(아래 map 행 = 이제 해결됨).** 현재 상태는 상단 RESUME(1·2단계 ✅) 참조. map 데스크탑 분기·`on:` 문법은 이미 라이브. video/lightbox 만 미등록.

렌더 프리미티브는 **세 곳이 동기화**되어야 한다(기존 규약):
1. `scripts/build_ibl_nodes.py` `APP_VIEW_TYPES`(674행) — 체커가 아는 어휘.
2. `frontend/src/components/GenericInstrument.tsx` — 데스크탑 React 렌더러(현재 1029L).
3. `backend/api_launcher_web.py` — 원격/폰 HTML 렌더러.

**등록된 12 프리미티브**(674행): `metric, kv, kv_list, card_list, image_grid, sparkline, list_action, thread, form, editable_list, map, calendar`.

검증된 비대칭(이게 작업의 출발점):

| 프리미티브 | 체커 등록 | 원격(api_launcher_web) | 데스크탑(GenericInstrument) |
|---|---|---|---|
| **map** | ✅ 있음 | ✅ 있으나 **정적**(1599행 `if(p.type==='map')`, leaflet, `{type:'map', from:'map_data', markers:'cctvs'}`; CDN 361–363, lazy `initMaps` 1507–) | ❌ **분기 자체가 없음**(447–576행 type 분기에 map 없음) → 데스크탑에서 `type:map` 앱블록은 *아무것도 안 그림* |
| **video** | ❌ 미등록 | (확인 필요) | ❌ 없음 — HLS 재생은 `DirectionsInstrument`의 bespoke StreamPlayer뿐 |
| **lightbox** | ❌ 미등록 | ❌ | ❌ — 데스크탑의 "detail"은 `master_detail`(card_list 2분할/드릴, 832–833행)이지 *풀스크린 이미지 라이트박스 아님*. 풍부 라이트박스는 photo bespoke 창 |

**왜 realty는 은퇴됐는데 commercial/directions는 못 했나**: realty의 app 블록(sense.yaml 1078~)은 `type: metric` + 목록 — *지도가 없다.* 데스크탑 제네릭이 map을 못 그려서, 지도형 계기는 전부 bespoke로 남았다. (realty 은퇴 배선 선례: `ActionDesktop.tsx:40, 118–126` — 타일은 정적, `el`만 manifest→GenericInstrument 주입.)

**다음 세션 선확인 1건**: GenericInstrument에 `<video>`가 썸네일 용도로라도 있는지(image_grid의 video 썸네일 분기 등) — 본 핸드오프는 "HLS *스트리밍* 프리미티브는 없다"까지만 확정. grep은 `master_detail`만 잡았다.

---

## 2. 스코프 — 3 프리미티브 + 1 문법 선결

### 2A. `map` (인터랙티브) — 1순위·최대 레버
- **데스크탑에 `map` 분기 신설**(GenericInstrument.tsx): leaflet(이미 commercial/directions가 import). `from: map_data` 봉투의 center/zoom + `items`의 lat/lng를 마커로. 우선 *정적*으로 원격과 동치까지.
- **양 렌더러를 정적→인터랙티브로 확장**: 마커 클릭→액션(팝업/영상), **중심 드래그→재조회**.
- **은퇴**: CommercialInstrument(지도+반경+카테고리+상세)·DirectionsInstrument(지도+경로 폴리라인+CCTV 마커)의 *지도 부분*.
- `map_data`는 **통화가 아니라 의도된 봉투 면제**(single-currency §3) — 새 통화 만들지 말 것. 지도 위젯이 봉투를 직독한다.

### 2B. `video`(HLS 스트림) — directions를 닫는 조각
- `APP_VIEW_TYPES`에 `video` 추가 + 양 렌더러 구현(hls.js). DirectionsInstrument의 StreamPlayer 패턴 이식.
- 2A의 지도 마커가 *이* video 프리미티브를 열게 통합 → directions 완전 은퇴.

### 2C. `lightbox`(풀스크린 상세/이미지) — commercial·photo 공통
- `APP_VIEW_TYPES`에 `lightbox` 추가(또는 `image_grid`에 fullscreen 모드 옵션). 카드/마커 클릭→풀스크린 오버레이(이미지 줌·상세 필드).
- **은퇴**: CommercialInstrument 점포 상세 팝업. photo 풍부창의 라이트박스도 후보(별개·저우선).

### 2D. ★선결: 뷰-이벤트 → 액션 바인딩 (가장 깊고·가장 일반적)
2A의 "드래그→재조회", "마커→영상"이 선언형이 되려면 **`app:` 문법에 *뷰가 이벤트를 내보내 액션을 트리거*하는 길**이 필요하다. 현재 문법은 `inputs→action→view`(한 방향)뿐.
- 제안 형태: view 항목에 `on:` 맵.
  ```yaml
  - type: map
    from: map_data
    on:
      marker_click: '[sense:cctv]{op: stream, id: "$id"}'   # → video 프리미티브로
      center_drag:  '[sense:commercial]{lat: "$lat", lng: "$lng", radius: "$radius"}'  # → 재조회·재렌더
  ```
- 이벤트 페이로드 변수(`$lat,$lng,$id,$radius`)를 액션에 주입. dispatch는 기존 form/list_action의 액션 실행 경로 재사용.
- **이게 일반형**: 인터랙티브 지도는 이 문법의 *한 사례*. 미래의 드래그-슬라이더·클릭-드릴 차트도 같은 문법으로 풀린다. **상호작용을 데이터로** — 통화·preload와 같은 동작.
- 체커: `validate_app_blocks`(build_ibl_nodes.py:927)에 `on:` 키 + 액션 IBL 파싱 검증 추가. `APP_KEYS`에 `on` 등록.

---

## 3. 구현·검증 절차

1. **체커 먼저**: `APP_VIEW_TYPES`에 `video`·`lightbox` 추가, `APP_KEYS`에 `on` 추가, `validate_app_blocks`에 `on:` 검증. `map`은 이미 등록됨.
2. **데스크탑 `map` 분기 신설**(정적) → 원격과 동치 확인.
3. **2D 문법 + 인터랙티브화**(양 렌더러 동기): 마커 클릭·중심 드래그.
4. **video·lightbox 프리미티브**(양 렌더러).
5. **app: 블록 작성**: commercial·directions를 src yaml app 블록으로(지도+on+video+lightbox 조합). `build --check` 142+ GREEN, `validate_app_blocks` 통과.
6. **bespoke 은퇴**: `ActionDesktop.tsx`의 STATIC_DOMAINS에서 commercial(41행)·directions(67행) 제거, `CommercialInstrument.tsx`·`DirectionsInstrument.tsx` 삭제, realty 선례(118–126)대로 manifest 주입 배선. import(11–12행) 정리.
7. **회귀**: 데스크탑·원격·폰 세 표면에서 지도/영상/라이트박스 라이브 렌더 + 드래그-재조회·마커-영상 동작. realty(기존 선언형) 무회귀.

---

## 4. 함정·메모

- **두 렌더러 동기**가 핵심 위험: GenericInstrument.tsx(React)와 api_launcher_web.py(HTML 문자열). 한쪽만 고치면 표면 드리프트 — 이번 확장이 *없애려는* 바로 그 병. 프리미티브 하나당 두 곳 + 체커 한 곳, 항상 3-동기.
- **프론트는 백엔드보다 저위험**: Vite HMR로 즉시 반영, 자기-reload 자해 없음(백엔드 코어 편집의 그 위험 아님). 단 api_launcher_web.py는 backend라 핸들러처럼 `/packages/reload` 또는 서버 재시작 영향 확인.
- **2D(상호작용 문법)가 진짜 난이도.** 정적 map은 쉽고(원격에 있음), *드래그→재조회*가 어렵다. 여기서 시간이 간다 — 정적부터 세우고 인터랙션을 얹을 것.
- **map_data는 통화 아님**(§3 면제). items로 접지 말 것 — center/zoom은 봉투 직독.
- **`calendar`도 같은 보트**(등록됐으나 데스크탑 bespoke=CalendarInstrument). 단 freq=1이라 *이번 스코프 아님* — 지도 인터랙션 문법이 서면 그때 재평가.
- **닫힌·작은 예외는 정당**: 진짜 네이티브 별창(OS 지도 등)이 남아야 하면 통화의 map_data 면제처럼 *닫힌 소수 bespoke*로 두는 것도 OK. 목표는 "0 bespoke"가 아니라 "빈도 높은 블록의 결정화".

---

## 5. 추천 순서 (한 번에 다 말고)

1. **체커 + 데스크탑 정적 `map`** → 원격과 동치(작은 첫 승, 위험 낮음).
2. **2D 뷰-이벤트 문법** → `map` 인터랙티브화 → **commercial 은퇴**(검증 1).
3. **`video` 프리미티브** + 마커→영상 통합 → **directions 은퇴**(검증 2).
4. **`lightbox`** → commercial 상세 대체 + photo 라이트박스 후보.

각 단계가 *독립적으로 라이브·은퇴*되게 — 빅뱅 금지. 1단계만으로도 "데스크탑이 map을 그린다"는 즉시 이득.

---

## 참고 (코드 좌표)
- 체커: `scripts/build_ibl_nodes.py:674`(APP_VIEW_TYPES)·`:817`(미지 type 거부)·`:927`(validate_app_blocks)
- 데스크탑 렌더러: `frontend/src/components/GenericInstrument.tsx`(447–576 type 분기, map/calendar 없음)
- 원격 렌더러: `backend/api_launcher_web.py:361`(leaflet CDN)·`:1507`(initMaps)·`:1599`(정적 map)
- bespoke(은퇴 대상): `CommercialInstrument.tsx`(268L)·`DirectionsInstrument.tsx`(378L) / 배선: `ActionDesktop.tsx:30`(OVERRIDES)·`:36`(STATIC_DOMAINS)·`:118-126`(realty 선언형 주입 선례)
- map_data 면제 근거: `docs/SINGLE_CURRENCY_MIGRATION_HANDOFF.md` §3 / `architecture_single_currency_items`
