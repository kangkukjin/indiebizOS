# Real Estate 도구 가이드 — 시세·매물 검색

## 0. 먼저 — 부동산 데이터는 3개 층이다 (무엇을 원하는지 구분)

| 층 | 무엇 | IBL 어휘 | 링크·사진 |
|----|------|----------|-----------|
| **시세(실거래가)** | *체결된 과거 거래* — 가격이 얼마에 굳었나 | `[sense:realty]{source: "molit"}` (기본) | ❌ |
| **호가(현재 매물)** | *지금 시장에 나온 매물* — 빌라·원룸·오피스텔 | `[sense:realty]{source: "zigbang"}` | ✅ (사진·클릭 링크) |
| **희소·직거래** | 다가구 주인세대·단독 전세, 입소문 매물 | ❌ 어휘 없음 → 가이드 §4 (포털 직접·현지 부동산) | ✅ |

핵심: 사용자가 **"지금 사진·링크 볼 수 있는 매물"**을 원하면 `source: "zigbang"` (빌라/원룸/오피스텔) 또는 §4(아파트·희소 매물). **"얼마에 거래됐나(시세)"**면 `source: "molit"` (기본).

---

## 1. IBL 액션

| 액션 | 설명 |
|------|------|
| `[sense:realty]{op:"query", source:"molit"}` | 국토부 실거래가(체결·시세). 기본값 |
| `[sense:realty]{op:"query", source:"zigbang"}` | 직방 현재 매물(호가·사진·링크) |
| `[sense:realty]{op:"codes"}` | 법정동 지역코드 조회(보조) |
| `[sense:commercial]` | 상권/업종 분석 |

---

## 2. source=molit — 실거래가(시세)

```
1. (보통 불필요) 지역코드:  [sense:realty]{op:"codes", city:"서울"}
2. 실거래가 (region 이름만 넣으면 코드 자동 변환):
   [sense:realty]{region:"강남구", type:"apt",   deal:"trade"}   # 아파트 매매
   [sense:realty]{region:"평택시", type:"apt",   deal:"rent"}    # 아파트 전월세
   [sense:realty]{region:"강남구", type:"house", deal:"trade"}   # 단독/다가구 매매
   [sense:realty]{region:"강남구", type:"villa", deal:"rent"}    # 연립/다세대 전월세
```
- type=apt|house|villa, deal=trade|rent. dong=법정동으로 좁히기. start_month/end_month(YYYYMM, 기본 최근 3개월).
- **단위 만원** (64,000 = 6억 4천만원). 한 번 호출로 최대 12개월. **링크·사진 없음**(통계라서).

---

## 3. source=zigbang — 직방 현재 매물 (호가·사진·링크)

지금 시장에 **실제로 나온 매물**을 가격·사진·클릭 링크와 함께 가져온다. **빌라·원룸·오피스텔 개별 호실에 강하다.**

```
[sense:realty]{source:"zigbang", region:"평택 죽백동", type:"villa", deal:"rent", lease:"전세"}
[sense:realty]{source:"zigbang", region:"강남역", type:"oneroom", deal:"rent", lease:"월세", deposit_max:1000}
[sense:realty]{source:"zigbang", region:"분당", type:"officetel", deal:"rent", lease:"전세", limit:10}
[sense:realty]{source:"zigbang", lat:37.006, lng:127.123, type:"villa", deal:"rent"}   # 좌표 직접
```

### 파라미터
| 키 | 뜻 | 기본 |
|----|----|------|
| `region` | 동·지명·**건물명**(예 "배다리도서관"). 내부에서 좌표로 자동 해소 | — |
| `lat`/`lng` | 좌표 직접 지정(region 대신) | — |
| `type` | `villa`(빌라/다세대)·`oneroom`(원룸)·`officetel`(오피스텔) | villa |
| `deal` | `trade`(매매)/`rent`(전월세) | rent |
| `lease` | `전세`/`월세` — deal=rent를 좁힘 | (둘 다) |
| `deposit_max`·`rent_max` | 보증금·월세 상한(**만원**) | — |
| `radius` | 검색 반경(m) | 3000 |
| `limit` | 최대 매물 수 | 30 |

### 반환 (records 통화)
각 매물: `{title, meta, summary, url, image}`
- `meta` = `전세 1억 5,000만 · 78㎡ · 2/4층 · 쓰리룸 · 평택시 동삭동 664-19 · 중심에서 2380m`
- `url` = `https://www.zigbang.com/home/villa/items/49460021` (클릭 시 직방 매물 페이지)
- `image` = 썸네일. `data[]`엔 lat/lng·deposit·rent·area_m2 등 원자료, `map_data`엔 지도 마커.

### ⚠️ source=zigbang가 약한 것 (여기선 §4로)
- **아파트** — 직방은 단지 단위라 이 경로는 거부됨. 아파트 매물은 네이버부동산(§4), 시세는 source=molit.
- **단독·다가구·"주인세대" 전세** — 직방에 거의 없음(희소·직거래). §4 + 현지 부동산.

---

## 4. 매물 링크·사진 더 넓게 (당근·네이버) — 2026-06 실측 기준

`source=zigbang`로 안 잡히는 아파트·희소 매물은 포털을 직접 친다. **아래는 실제로 찔러보고 확인한 사실이다.**

### 당근(daangn) — SSR JSON-LD로 빠르게 추출 가능 (browser-action 불필요)
- 경로형 URL: `https://realty.daangn.com/map/{시도}/{시군구}/{동}` (예 `…/경기도/평택시/죽백동`)을 **그냥 fetch(`sense:crawl`)** 하면 HTML 안에 **schema.org `ItemList` JSON-LD**가 박혀 온다. 로그인·JS 실행 불필요.
  - 추출 정규식: `{"@type":"ListItem","position":\d+,"name":"([^"]+)","url":"([^"]+)"}`
  - `name` = `"죽백동 아파트 전세 2억 6,000만원 73m² 매물"` (동·유형·거래·가격·면적), `url` = `https://realty.daangn.com/articles/{id}`
- ✅ **경로형 URL이 `search_region` 쿠키 문제를 우회한다** — 평택 데이터가 정상 반환됨(옛 가이드의 "browser-action으로 지역선택 UI 조작해야만"은 *정정*: 단순 목록은 경로 URL fetch로 충분).
- ⚠️ **함정 — SSR 목록은 동·필터가 안 걸린다**: 경로의 동/쿼리(`realtyType`·`tradeType`)가 SSR에 **무시**된다. 죽백동/용이동/동삭동을 따로 불러도 **article ID가 동일한 20건**(평택시 기본 목록)에 *동 이름 라벨만* 갈아끼워질 뿐, 매매·월세·상가가 섞여 온다. **"도서관 반경" 같은 정밀 검색은 SSR로 불가** — 동·필터·반경이 진짜 먹는 **당근 내부 지도 JSON API(bbox+필터)는 아직 미발굴**. SSR 목록은 "맛보기"로만 쓰고, 개별 매물 상세는 `sense:crawl`(URL 1건)로 확인.
- 참고(2026-07-12): 당근 **중고물건** 쪽(`www.daangn.com/kr/buy-sell/?in=x-{지역ID}&search=`)은 지역 필터가 **진짜 작동**하고 지역ID 해소 API(`/kr/api/v1/regions/keyword?keyword={동이름}`, 키불요)도 발굴됨 — `[sense:used]{source:"danggeun"}` 어휘로 결정화(`used_market.md`). realty.daangn.com이 같은 지역ID 체계를 쓰는지는 미검증 — 부동산 정밀 검색 재도전 시 이 API부터 시도할 것.

### 네이버부동산 — 매물 최다지만 미연동
- 단지(`cortarNo`+bbox) 2단계 비공식 JSON API. 매물량 국내 1위. **해외 IP를 강차단**하지만 이 시스템은 한국 IP라 유리. 구현 난이도 중상(단지 단위라 단독/다가구엔 부적합). **현재 미연동 — 향후 `source:"naver"` 후보.**

### 비권장
- 매물 링크에 `sense:search_youtube` 쓰지 말 것(시세 전망·임대주택 모집 영상만 나옴).
- crawl이 텍스트를 반환해도 **기대 지역명이 본문에 없으면 의심**(지오로케이션/기본지역 폴백 가능성).

---

## 5. 다가구 "주인세대" 전세 등 희소 매물 — 어휘로 안 잡힌다

신축 다가구 **주인세대**(건물주가 쓰던 제일 큰 세대) 전세 같은 매물은 *희소·직거래·입소문*이라 **어떤 플랫폼 API로도 잘 안 잡힌다**(2026-06 실측: 평택 전역 직방 0건). 이건 도구 부족이 아니라 **매물 희소성**이다. 정답:
1. **당근(§4)** — 개인 직거래에 가장 강함. 동네 키워드로.
2. **현지 부동산 직접 문의** — 주인세대·신축은 현장 매물이 다수.
3. **건축물대장 API**(공공데이터포털) — 매물 발견 후 신축 여부·다가구 호수·구조·위반건축물 **검증** 단계에 활용.

---

## 6. 매물 분석 판단 기준

### 다세대(빌라)/오피스텔 — 개별 호실
- **단가**: 전용면적당 단가(평당가)를 인근 유사 매물과 비교
- **전세가율**: 매매가 대비 전세가. 80%↑면 깡통전세 리스크
- **126% 룰(HUG 보증보험)**: `주택공시가격 × 1.26` 기준 전세보증금 반환보증 가입 가능 여부
- **호가 vs 실거래 갭**: `source:"zigbang"`(호가)와 `source:"molit"`(실거래가)를 같이 조회해 **나온 가격이 실제 체결가 대비 높은지/낮은지** 진단(같은 어휘라 바로 비교 가능)

### 다가구/상가주택 — 건물 통매매
- **수익률**: `(월세 합계 × 12) / (매매가 − 보증금 합계 − 대출금)`
- **권리관계**: 근저당 + 선순위 보증금 합계가 건물가의 70~80% 초과 시 위험
- **공실 리스크**: 인근 기업·대학·교통망 확충으로 임대 수요 예측

### 전세가율 계산
```
1. [sense:realty]{region:"강남구", type:"apt", deal:"trade"}   # 매매(실거래가)
2. [sense:realty]{region:"강남구", type:"apt", deal:"rent"}    # 전세(실거래가)
3. 전세가율 = (전세가 / 매매가) × 100
```

---

## 7. 데이터 이해

- **단위 만원**: 64,000 = 6억 4천만원 · 30,000 = 3억 · 5,000 = 5천만
- molit: 한 호출로 최대 12개월. zigbang: deposit/rent도 만원(전세는 rent=0).
- **주요 지역코드**: 강남구 11680 · 서초구 11650 · 송파구 11710. 정확한 코드는 `[sense:realty]{op:"codes"}`.

---

## 부록 A. 직방 내부 API 레퍼런스 (확장·디버깅용)

비공식(apis.zigbang.com). **키 불필요, 한국 IP 차단 약함.** 약관 리스크 상존 — 엔드포인트 변경 시 깨질 수 있음. `tool_zigbang.py`가 이 흐름을 구현.

1. **지오코딩**: `GET https://apis.zigbang.com/v2/search?q={지명}` → `items[].{lat,lng,type:"address",description}` (POI는 약함 → Nominatim 폴백)
2. **geohash precision 5** 계산(좌표 → 약 4.9km 박스 식별자)
3. **리스트(마커)**: `GET https://apis.zigbang.com/v2/items/{cat}?geohash={gh}&salesTypes[0]=전세&salesTypes[1]=월세&depositMin=0&rentMin=0&domain=zigbang&checkAnyItemWithoutFilter=true`
   - `cat` ∈ `oneroom`·`villa`·`officetel` (`apartment`·`house` → 404)
   - 반환 `{items:[{lat,lng,itemId,itemBmType}]}` — 마커만(가격 없음). **box가 넓으니 거리 후필터 필수.**
   - ⚠️ `v3/items/villa`(옛 리스트 경로)는 **404 폐기** → 반드시 `v2/items/{cat}`.
4. **상세**: `GET https://apis.zigbang.com/v3/items/{itemId}` → `{item:{...}}`
   - `salesType`(전세/월세/매매), `serviceType`(빌라/원룸/오피스텔), `residenceType`(다세대주택 등)
   - `price:{deposit, rent}`(**만원**), `area:{전용면적M2, 대지권면적M2}`, `floor:{floor, allFloors}`
   - `jibunAddress`, `location:{lat,lng}`(randomLocation=프라이버시 보정 좌표), `title`, `description`
   - `imageThumbnail`, `images[]`, `roomType`, `options[]`, `manageCost`, `moveinDate`, `elevator`, 주차
5. **매물 웹 URL**: `https://www.zigbang.com/home/{cat}/items/{itemId}` (예 `…/home/villa/items/49460021`)

## 부록 B. search_commercial_district (상권 분석)
- 위경도(`lat`/`lng`+`radius`m) 또는 행정동코드로 주변 상가 조회. 업종 `indsLclsCd`: I 음식·Q 숙박·R 학문/교육·S 소매·T 생활서비스·U 의료·V 부동산·W 관광/여가/오락.
- 결과 `data[]`(좌표 포함)를 `show_location_map`(location-services)의 `markers`로 넘기면 지도 시각화. 매물 입지의 상권 활성도 수치화에.
