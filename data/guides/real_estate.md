# Real Estate 도구 가이드

## IBL 액션

| 액션 | 설명 |
|------|------|
| `sense:realty` | 실거래가 조회 (type=apt|house, deal=trade|rent) |
| `sense:district_codes` | 법정동 지역코드 조회 |
| `sense:commercial` | 상권/업종 분석 |

---

## 기본 워크플로우

```
1. 지역코드 확인
   [sense:district_codes]{city: "서울"}   # → 강남구=11680 등

2. 실거래가 조회 (type × deal 조합)
   [sense:realty]{type: "apt",   deal: "trade", region_code: "11680"}  # 아파트 매매
   [sense:realty]{type: "apt",   deal: "rent",  region_code: "11680"}  # 아파트 전월세
   [sense:realty]{type: "house", deal: "trade", region_code: "11680"}  # 주택 매매
   [sense:realty]{type: "house", deal: "rent",  region_code: "11680"}  # 주택 전월세

   선택 파라미터: start_month, end_month, count_per_month (월별 건수, 기본 30)
```

---

## 실매물 링크·사진 찾기 (실거래가 ≠ 매물)

`sense:realty`는 **국토부 실거래 통계**다 — 시세는 주지만 **매물 링크·사진은 없다**. 사용자가 "지금 사진 볼 수 있는 매물 링크"를 원하면 포털(당근·네이버 부동산)로 가야 한다.

### 도구 선택: 무엇을 크롤하느냐가 핵심
- **특정 매물 상세 URL** → `sense:crawl` 로 충분. (JS 페이지는 Playwright 폴백이 자동 렌더링 — 본문·매물 정보 확보됨)
- **지역으로 필터링한 매물 목록** → `sense:crawl` **불가**. 아래 ⚠️ 참고. → **browser-action(상호작용)** 필요.

### ⚠️ 당근(daangn) — 지역은 URL이 아니라 "상태(쿠키)"다
- daangn은 지역을 **`search_region` 쿠키**(`{"regionId":"4784","regionName":"동삭동"}`)로 읽는다. **`?in=동삭동-11138` URL 파라미터는 무시**된다(슬러그 id ≠ 쿠키 regionId, 별개 체계).
- 그래서 `?in=...` 리스트 URL을 그냥 crawl하면 **서버 IP 기준 기본 지역**(예: dev 환경=청주)이 반환된다. geolocation 오버라이드도 안 먹음(서버 IP만 봄).
- **올바른 방법 = browser-action으로 지역 선택 UI를 실제 조작**:
  1. `navigate` → `https://www.daangn.com/kr/realty/`
  2. 현재 지역명 버튼 클릭 → 지역 선택 패널 열기
  3. 입력창 **"지역이나 동네로 검색하기"** 에 동/지역명 입력 (예: "동삭동")
  4. 옵션 **"경기도, 평택시, 동삭동"** 선택 → `search_region` 쿠키가 갱신됨
  5. 이제 목록을 읽거나, 개별 매물 상세 URL을 `sense:crawl`로 확인
  - (regionId를 이미 알면 `search_region` 쿠키 직접 주입 후 로드도 가능)
- **원리**: daangn은 상태 기반(stateful) 사이트라 지역을 쿠키 상태로 들고 있다. 상태를 바꾸려면 사용자 행동(클릭·입력)을 흉내내야 하므로 **한 방 fetch인 crawl이 아니라 browser-action의 영역**이다.

### 비권장
- 매물 링크 작업에 `sense:search_youtube` 쓰지 말 것 — 시세 전망·임대주택 모집 영상만 나와 무관하다.
- crawl이 텍스트는 충분히 반환했더라도 **기대한 지역명이 본문에 없으면 의심**할 것(지오로케이션 폴백 가능성).

---

## 데이터 이해

- **단위**: 만원
  - 64,000 = 6억 4천만원
  - 30,000 = 3억원
  - 5,000 = 5천만원
- **반환량**: 한 번 호출로 최대 12개월 데이터 반환

---

## 주요 지역 코드

| 지역 | 코드 |
|------|------|
| 강남구 | 11680 |
| 서초구 | 11650 |
| 송파구 | 11710 |

정확한 코드는 `get_region_codes`로 확인할 것.

---

## 매물 분석 판단 기준

### 다세대(빌라) / 오피스텔 — 개별 호실
- **단가 분석**: 전용면적당 단가(평당가)를 산출하여 인근 유사 매물과 비교
- **전세가율**: 매매가 대비 전세가 비중. 80% 이상이면 깡통전세 리스크 진단
- **126% 룰 (HUG 보증보험)**: `주택공시가격 × 1.26` 기준으로 전세보증금 반환보증 가입 가능 여부 판단

### 다가구 / 상가주택 — 건물 통매매
- **수익률**: `(월세 합계 × 12) / (매매가 - 보증금 합계 - 대출금)` = 실투자금 대비 수익률
- **권리관계**: 근저당권 설정액 + 선순위 임차인 보증금 합계가 건물 가액의 70~80% 초과 시 위험
- **공실 리스크**: 인근 기업/대학, 교통망 확충 계획으로 임대 수요 예측

### 시장 판단
- **상승/하락 신호**: 실거래가 대비 호가 상승 여부, 매물 적체량(증감)
- **입지 평가**: `search_commercial_district`로 주변 상권 활성도와 편의시설 접근성 수치화

---

## 전세가율 계산

전세가율을 구하려면 매매가와 전세가를 함께 조회해야 한다.

```
1. [sense:realty]{type: "apt", deal: "trade", region_code: "11680"}  # 매매
2. [sense:realty]{type: "apt", deal: "rent",  region_code: "11680"}  # 전세
3. 전세가율 = (전세가 / 매매가) x 100
```

---

## search_commercial_district (상권 분석)

### 검색 방식

- **위경도로 검색**: 좌표 기반으로 주변 상권 조회
- **행정동코드로 검색**: 특정 행정동의 상권 조회

### 업종코드

| 코드 | 업종 |
|------|------|
| I | 음식 |
| Q | 숙박 |
| R | 학문/교육 |
| S | 소매 |
| T | 생활서비스 |
| U | 의료 |
| V | 부동산 |
| W | 관광/여가/오락 |

### 지도 시각화 연계

`search_commercial_district` 결과를 `show_location_map` (location-services 패키지)의 `markers`로 전달하면 상권 데이터를 지도 위에 시각화할 수 있다.

```
1. search_commercial_district로 상권 데이터 조회
2. 결과에서 좌표/상호 정보 추출
3. show_location_map의 markers 파라미터로 전달
4. 지도 위에 상권 분포 시각화
```
