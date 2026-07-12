# 부동산 시세·매물 가이드

`[sense:realty]` 단일 액션. **`source`로 데이터 종류를 가른다:**
- `source:"molit"` (기본) — 국토부 공개 실거래가(체결된 과거 거래 = **시세**). **type × deal 매트릭스**가 핵심 분기. 링크·사진 없음.
- `source:"zigbang"` — 직방 **현재 매물**(지금 나온 호가·사진·클릭 링크). 빌라/원룸/오피스텔. ↓ "source=zigbang" 절.
- `source:"naver"` — 네이버부동산 **현재 매물**(전국 최다 풀, 아파트·단지 강함, 단지명 직조회). ↓ "source=naver" 절.

> 매물 검색 전반(당근·다가구 주인세대 등 희소 매물)은 `real_estate.md` 가이드 참조.

---

## source=molit — 핵심 분기: type × deal

```
[sense:realty]{region_code:"11680", type:"apt", deal:"trade"}
```

| | `deal:"trade"` (매매) | `deal:"rent"` (전월세) |
|---|---|---|
| `type:"apt"` (아파트) | 아파트 매매 실거래 | 아파트 전월세 |
| `type:"house"` (단독/다가구) | 단독·다가구 매매 | 단독·다가구 전월세 |
| `type:"villa"` (연립/다세대) | 연립·다세대 매매 | 연립·다세대 전월세 |

기본값: `type:"apt"`, `deal:"trade"`. 즉 파라미터 생략하면 **아파트 매매** 조회. `region` 이름(예 "강남구")만 줘도 코드 자동 해소.

---

## source=zigbang — 현재 매물(호가·링크)

```
[sense:realty]{source:"zigbang", region:"평택 죽백동", type:"villa", deal:"rent", lease:"전세"}
```
- `region`(동·지명·건물명) 또는 `lat`/`lng`. `type`=villa/oneroom/officetel. `deal`=trade/rent + `lease`=전세|월세(좁힘).
- `deposit_max`·`rent_max`(만원), `radius`(m, 기본 3000), `limit`(기본 30).
- 반환 records `{title, meta, summary, url, image}` — url=직방 매물 페이지, image=썸네일.
- **아파트·단독/다가구는 직방 약함** → `source:"naver"` 또는 real_estate.md §5·§6(당근·현지 부동산).

---

## source=naver — 네이버부동산 현재 매물(아파트 최다·단지 검색)

```
[sense:realty]{source:"naver", region:"평택 비전동", type:"apt", lease:"전세", deposit_max:25000}
[sense:realty]{source:"naver", region:"우미린센트럴파크", deal:"trade"}   # 아파트 단지명 직조회
```
- `region`=동 이름 **또는 아파트 단지명**(동 우선, 없으면 단지). `type`=apt(기본)/officetel/villa/house(단독다가구)/oneroom.
- `deal`/`lease`는 zigbang과 동일. `deposit_min`/`deposit_max`(만원, 서버필터), `rent_max`(만원), `limit`(기본 30, 최대 60).
- 반환 items `{title, meta, summary, url, image}` — url=네이버 매물 페이지(m.land), 동일매물 자동 묶음.
- 내부 API + curl_cffi TLS 위장 + 익명 JWT(자동) — 상세는 real_estate.md §4·부록 C.

---

## 파라미터

| 키 | 필수 | 설명 |
|---|---|---|
| `region_code` | ✓ | 법정동 코드 5자리 (예: `11680` 강남구). 4자리도 동작하지만 결과 범위 넓어짐 |
| `type` | (기본 apt) | `apt` \| `house` |
| `deal` | (기본 trade) | `trade` \| `rent` |
| `start_month` | (기본 이번달) | `YYYYMM` 형식 (예: `202604`) |
| `end_month` | (기본 start_month) | `YYYYMM` 형식. 범위 조회 |
| `count_per_month` | (기본 30) | 월별 반환 건수 상한 |

### region_code 조회

지역 코드를 모르면 먼저 별도 도구로 조회:
```
[sense:realty]{op:"codes", city:"서울"}     # 보조: 법정동 코드 목록
```
혹은 사용자에게 정확한 코드를 묻는다. 5자리 법정동 코드가 정확.

자주 쓰는 코드: 11680(강남) · 11650(서초) · 11710(송파) · 11500(강서) · 11200(성동) · 26110(부산 중구) · ...

---

## 표준 워크플로우

### 1) 강남 아파트 이번달 매매
```
[sense:realty]{region_code:"11680"}
→ 기본값으로 apt+trade, 이번달
```

### 2) 강남 아파트 1년 전세 추이
```
[sense:realty]{region_code:"11680", deal:"rent",
               start_month:"202504", end_month:"202604"}
```

### 3) 단독·다가구 매매 동향 (구별 비교)
```
[sense:realty]{region_code:"11680", type:"house", deal:"trade"}
[sense:realty]{region_code:"11200", type:"house", deal:"trade"}
[sense:realty]{region_code:"11500", type:"house", deal:"trade"}
→ 결과 비교
```

### 4) 월별 풍부한 표본 (검색 건수 늘리기)
```
[sense:realty]{region_code:"11680", count_per_month:100,
               start_month:"202601", end_month:"202604"}
```

### 5) 시각화로 연결
```
[sense:realty]{region_code:"11680", start_month:"202504", end_month:"202604"}
  >> [table:chart_line]{x:"month", y:"price"}
```

---

## 자주 하는 실수

- **region_code 자릿수**: 5자리가 정확. 2자리(시도 단위)는 결과 폭주.
- **start_month 형식**: `2026-04`나 `2026/04` 안 됨. 반드시 `202604`.
- **type/deal 잘못 조합**: 둘 다 enum이라 오타나면 에러. `type:"apartment"`(X), `deal:"sale"`(X).
- **count_per_month 너무 큼**: 한 번에 너무 많이 요청하면 API 응답 느려짐. 보통 30~50.
- **외국 부동산**: 이 액션은 한국만. 국토부 API 한계.

## 관련

- 현재 매물(호가·사진·링크) — `[sense:realty]{source:"naver"}`(아파트·단지) / `[sense:realty]{source:"zigbang"}`(빌라/원룸/오피스텔). 매물 검색 전반은 `real_estate.md`.
- 상권 분석 — `search_commercial_district` (real-estate 패키지에 있음)
