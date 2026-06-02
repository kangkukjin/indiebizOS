# 부동산 실거래가 가이드

`[sense:realty]` 단일 액션으로 국토부 공개 실거래가 API 4종(아파트 매매/전월세, 단독·다가구 매매/전월세)을 통합 조회한다. **type × deal 매트릭스**가 핵심 분기.

부동산 *시세 정보*(현재 매물 호가)는 별도 — 네이버/다나와류는 `real-estate` 패키지의 다른 도구 또는 `shopping-assistant` 영역. 이 액션은 **거래 완료된 실거래** 데이터다.

---

## 핵심 분기: type × deal

```
[sense:realty]{region_code:"11680", type:"apt", deal:"trade"}
```

| | `deal:"trade"` (매매) | `deal:"rent"` (전월세) |
|---|---|---|
| `type:"apt"` (아파트) | 아파트 매매 실거래 | 아파트 전월세 |
| `type:"house"` (단독/다가구) | 단독·다가구 매매 | 단독·다가구 전월세 |

기본값: `type:"apt"`, `deal:"trade"`. 즉 파라미터 생략하면 **아파트 매매** 조회.

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
[sense:district_codes]{city:"서울"}        # 보조 도구가 있다면
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
  >> [engines:chart_line]{x:"month", y:"price"}
```

---

## 자주 하는 실수

- **region_code 자릿수**: 5자리가 정확. 2자리(시도 단위)는 결과 폭주.
- **start_month 형식**: `2026-04`나 `2026/04` 안 됨. 반드시 `202604`.
- **type/deal 잘못 조합**: 둘 다 enum이라 오타나면 에러. `type:"apartment"`(X), `deal:"sale"`(X).
- **count_per_month 너무 큼**: 한 번에 너무 많이 요청하면 API 응답 느려짐. 보통 30~50.
- **외국 부동산**: 이 액션은 한국만. 국토부 API 한계.

## 관련

- 시세(현재 호가) — 별도 영역. shopping-assistant나 네이버부동산 액션이 있으면 그쪽.
- 상권 분석 — `search_commercial_district` (real-estate 패키지에 있음)
