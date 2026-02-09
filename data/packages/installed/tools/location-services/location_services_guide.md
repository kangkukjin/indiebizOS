# Location Services 도구 가이드

## 도구 선택 가이드

| 목적 | 도구 | 설명 |
|------|------|------|
| 날씨/대기질 | `get_api_ninjas_data` | endpoint='weather' 또는 'airquality' |
| 맛집 검색 | `search_restaurants` | 카카오+네이버 통합, 최대 15개 결과 |
| 길찾기 | `kakao_navigation` | 자동차 길찾기, HTML 지도 생성 |
| 지도 표시 | `show_location_map` | 대화창 내 지도 |
| 여행 | `amadeus_travel_search` | 항공권, 호텔, 관광지 |

---

## get_api_ninjas_data

API Ninjas를 통한 다양한 데이터 조회.

### 사용 가능한 endpoint 목록

| endpoint | 설명 | 주요 파라미터 |
|----------|------|---------------|
| `weather` | 날씨 정보 | city, country, lat, lon |
| `airquality` | 대기질 정보 | city, country, lat, lon |
| `geocoding` | 주소 → 좌표 변환 | city, country |
| `reversegeocoding` | 좌표 → 주소 변환 | lat, lon |
| `recipe` | 레시피 검색 | query |
| `cocktail` | 칵테일 레시피 | name, ingredients |

---

## search_restaurants (맛집 검색)

카카오와 네이버 검색을 통합하여 최대 15개 결과를 반환한다.

### 검색 팁

- **'지역 + 음식종류' 조합**이 가장 효과적이다
  - 예: '강남 파스타', '홍대 라멘', '을지로 한식'
- **한 번 호출로 충분**: 카카오+네이버 통합 결과가 한 번에 반환되므로 별도로 두 번 호출할 필요 없음
- 결과에는 상호명, 주소, 전화번호, 평점 등이 포함됨

---

## kakao_navigation (길찾기)

자동차 경로 탐색 및 HTML 지도 생성.

### 좌표 형식

- 기본: `'경도,위도'` (예: `'127.0276,37.4979'`)
- 장소명 포함: `'경도,위도,name=장소명'` (예: `'127.0276,37.4979,name=강남역'`)

### 경로 옵션

| 옵션 | 설명 |
|------|------|
| `RECOMMEND` | 추천 경로 (기본값) |
| `TIME` | 최단 시간 |
| `DISTANCE` | 최단 거리 |

### 회피 옵션

| 옵션 | 설명 |
|------|------|
| `toll` | 유료도로 회피 |
| `motorway` | 고속도로 회피 |

---

## show_location_map (지도 표시)

대화창 내에 지도를 표시한다.

### 사용 방법

- **장소명으로 검색**: `query` 파라미터에 장소명 입력
- **좌표 직접 지정**: `lat`, `lng` 파라미터 사용
- **여러 마커 표시**: `markers` 파라미터로 복수의 위치를 한 지도에 표시

### 상권 분석과의 연계

`search_commercial_district` (real-estate 패키지) 결과를 `show_location_map`의 `markers`로 전달하면 상권 데이터를 지도 위에 시각화할 수 있다.

```
1. search_commercial_district로 상권 데이터 조회
2. 결과의 좌표/상호 정보를 markers 배열로 구성
3. show_location_map에 markers 전달하여 지도에 표시
```

---

## amadeus_travel_search (여행)

항공권, 호텔, 관광지 정보를 검색한다.
